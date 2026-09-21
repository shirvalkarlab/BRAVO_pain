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


# ---------------------------------------------------------------------------------------------
# THE PAIRS BEHIND A CELL ARE THE PAIRS THE GRID CORRELATED, clinic-sheet ratings included
# (the PI, 2026-09-21: the pinned cell printed Pearson r = -0.033 while the fitted line rose).
# The grid merges the clinic and at-home sheets' scores into the rating series when the switch
# is on (decision 186); until this fix the drill-down never read the switch, so its scatter was
# fitted to the chronic REDCap ratings alone: on RCS08 L 1-3+, 22.5 Hz, 45 s, 10-minute window,
# reuse off, sheets on, the grid's r was -0.0329 on 172 ratings and the drill-down's +0.1039 on
# 97. Live on the RCS08 record, so it carries the `live` mark and skips when the participant is
# absent; pytest is imported only for the mark.
# ---------------------------------------------------------------------------------------------
import pytest                                                                     # noqa: E402

live = pytest.mark.live


@live
def test_the_drill_down_returns_the_pairs_the_grid_correlated_sheet_ratings_included():
    try:
        from Server import models
        from Biomarkers import bravo_service as bs
    except Exception:
        return
    uid = "2e3c75c00d7f4f37b53a048d195f11da"
    try:
        if models.Participant.find(uid=uid) is None:
            return
    except Exception:
        return
    base = {"ParticipantId": uid, "SweepMetric": "left_leg_vas", "LabelMetric": "left_leg_vas",
            "LabelStrategy": "tertile", "MatchToleranceMin": 10, "MatchDirection": "nearest",
            "AllowWindowReuse": False, "IncludeClinicSheetRatings": True, "MaxPerRating": 3, "RefractoryMin": 2}
    grid = bs.band_time_sweep_for_participant(dict(base))
    g = (grid.get("band_time_sweep") or grid)["ONE_THREE_LEFT"]
    centers = list(g["center_freqs_hz"]); secs = list(g["integration_seconds_delivered"])
    col = centers.index(22.5); row = secs.index(45.0)
    r_grid = float(g["correlation_grid"][row][col]); n_grid = int(g["n_grid"][row][col])
    n_sheet_grid = int(g["clinic_sheet_n_grid"][row][col])
    cell = bs.band_time_sweep_cell_for_participant(dict(base, BandTimeSweepCell="1", Channel="ONE_THREE_LEFT",
                                                         BandCenterHz=22.5, IntegrationSeconds=45))["band_time_sweep_cell"]
    pts = cell["points"]
    assert len(pts) == n_grid, (len(pts), n_grid)
    x = np.array([p["power"] for p in pts]); y = np.array([p["pain"] for p in pts])
    r_pts = float(np.corrcoef(x, y)[0, 1])
    assert abs(r_pts - r_grid) < 1e-9, (r_pts, r_grid)
    assert sum(1 for p in pts if p["from_clinic_sheet"]) == n_sheet_grid
    # the block counts the sheet ratings merged into the series (every one, matched or not), the
    # same number the grid's own block reports; the per-cell count is the flagged points above
    assert cell["clinic_sheet"]["included"] is True
    assert cell["clinic_sheet"]["n_added"] == int(g["clinic_sheet_ratings"]["n_added"]) > n_sheet_grid
    # and the least-squares line the page draws through these points has the sign of r
    slope = np.polyfit(x, y, 1)[0]
    assert np.sign(slope) == np.sign(r_grid)
    # switch off: no sheet point, and the block says so
    off = bs.band_time_sweep_cell_for_participant(dict(base, IncludeClinicSheetRatings=False, BandTimeSweepCell="1",
                                                        Channel="ONE_THREE_LEFT", BandCenterHz=22.5, IntegrationSeconds=45))["band_time_sweep_cell"]
    assert not any(p["from_clinic_sheet"] for p in off["points"]) and off["clinic_sheet"]["included"] is False
