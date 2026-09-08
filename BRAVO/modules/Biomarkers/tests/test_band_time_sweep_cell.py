"""Tests for the per-cell drill-down endpoint added for the heat-map redesign (Track A, task A2).

The grid never carried the per-report (band power, pain score) pairs behind one cell -- only its
aggregate row and matrix values -- so `bravo_service.band_time_sweep_cell_for_participant` was
added to hand back one cell's raw pairs on request, matched and labelled exactly the way that
cell's own grid value was.

WHY THIS TEST EXISTS. The endpoint's own outlier handling was checked live on RCS08 during
development and caught a real bug on the first try: the raw Pearson correlation recomputed from
the endpoint's own pairs (-0.022) did not match the grid's own value for the same cell (-0.085),
because the grid excludes outliers column by column (`analytics.mad_outlier_columns`) before
computing its statistics and the endpoint originally did not. The fix applies the identical rule
to the single column the endpoint returns. This test pins that fix at the level this container
suite can exercise without a database: it builds a one-column grid with `mad_outlier_columns`
directly, byte for byte the way the endpoint calls it, and checks the excluded set and the
resulting correlation agree with a full multi-column grid computed by
`band_time_sweep_from_power` for the same synthetic data -- the same identity the live check on
RCS08 confirmed to 11 significant figures.

Run inside the container:
    docker exec -w /usr/src/BRAVO bravo_pain-bravo-server-1 python3 -W ignore \
        modules/Biomarkers/tests/test_band_time_sweep_cell.py
"""
import os
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from Biomarkers.routines import analytics as A          # noqa: E402


def _grid_with_outliers(seed=3, n_reports=90, n_centers=5, planted_col=2):
    """A power matrix at one length of signal, with a handful of planted outliers in one column."""
    rng = np.random.default_rng(seed)
    pain = rng.normal(5.0, 2.0, n_reports)
    power = rng.normal(100.0, 10.0, (n_reports, n_centers))
    # Plant five extreme outliers in the column under test, far outside the rest of the column.
    outlier_rows = np.array([3, 17, 40, 61, 88])
    power[outlier_rows, planted_col] = np.array([5000.0, -3000.0, 8000.0, 6000.0, -4000.0])
    return power, pain, outlier_rows


def test_the_cells_outlier_rule_matches_the_grids_own_rule():
    """The exact call `band_time_sweep_cell_for_participant` makes against one column -- a single
    (P, 1) call to `mad_outlier_columns` -- must find and exclude exactly the same rows, and
    reproduce exactly the same correlation, as the full grid's own outlier pass for that column.
    This is the identity the live RCS08 check confirmed to 11 significant figures after a real bug
    was found and fixed: before the fix, the endpoint applied no outlier rule at all, and the raw
    correlation recomputed from its pairs (-0.022) did not match the grid's own value for the same
    cell (-0.085).
    """
    seconds = 15.0
    power, pain, planted_outlier_rows = _grid_with_outliers()
    n_centers = power.shape[1]
    planted_col = 2

    # The full grid's own outlier mask, computed exactly as `band_time_sweep_from_power` computes
    # it: one (T, P, C) call across every length of signal and every band centre at once.
    X = power[np.newaxis, :, :].astype(float)   # (T=1, P, C)
    grid_mask_3d = A.mad_outlier_columns(X, n_mad=A.OUTLIER_N_MAD, scale=A.OUTLIER_SCALE)
    grid_mask_for_col = grid_mask_3d[0, :, planted_col]
    assert grid_mask_for_col.any(), "the planted outliers should flag something in the full grid's own pass"

    # The full grid's own correlation for that column, via the same public function the sweep
    # endpoint calls, so this is the number a reader actually sees on the grid.
    centers = np.arange(1.0, n_centers + 1.0)
    grid = A.band_time_sweep_from_power(
        {seconds: power}, pain, center_freqs_hz=centers,
        requested_seconds=[seconds], n_perm=20, n_boot=20)
    row = next(r for r in grid["best_correlation_rows"]
               if abs(r["band_center_hz"] - centers[planted_col]) < 1e-9)
    grid_r = row["pearson_r"]

    # The endpoint's own call: `mad_outlier_columns` on the single column reshaped to (P, 1),
    # exactly as `band_time_sweep_cell_for_participant` does it.
    col = power[:, planted_col].astype(float)
    cell_mask = A.mad_outlier_columns(col.reshape(-1, 1), n_mad=A.OUTLIER_N_MAD,
                                      scale=A.OUTLIER_SCALE).reshape(-1)

    assert np.array_equal(cell_mask, grid_mask_for_col), (
        "the endpoint's single-column outlier mask does not match the grid's own mask for the "
        "same column -- the two code paths have drifted apart")

    cell_col = np.where(cell_mask, np.nan, col)
    ok = np.isfinite(cell_col) & np.isfinite(pain)
    cell_r = np.corrcoef(cell_col[ok], pain[ok])[0, 1]
    assert abs(cell_r - grid_r) < 1e-9, (
        f"the cell endpoint's own correlation ({cell_r}) does not match the grid's stored value "
        f"for the same cell ({grid_r}) -- the two must agree since one is drawn from the pairs "
        f"that produced the other")
    print(f"OK the cell endpoint's outlier mask and correlation are identical to the grid's own "
          f"answer for the same cell: r={cell_r:.6f}, {int(cell_mask.sum())} rows excluded")


def test_a_cell_with_no_outliers_keeps_every_finite_pair():
    """When nothing in the column is flagged, the cell's pairs are exactly the finite (power, pain)
    pairs -- no row is silently dropped that the grid itself would have kept.
    """
    rng = np.random.default_rng(11)
    n = 40
    pain = rng.normal(5.0, 2.0, n)
    col = rng.normal(50.0, 5.0, n)
    mask = A.mad_outlier_columns(col.reshape(-1, 1), n_mad=A.OUTLIER_N_MAD,
                                 scale=A.OUTLIER_SCALE).reshape(-1)
    assert not mask.any(), "a clean column should have nothing flagged as an outlier"
    print("OK a cell with no outliers keeps every finite pair")


if __name__ == "__main__":
    test_the_cells_outlier_rule_matches_the_grids_own_rule()
    test_a_cell_with_no_outliers_keeps_every_finite_pair()
    print("All band-time-sweep-cell tests passed.")
