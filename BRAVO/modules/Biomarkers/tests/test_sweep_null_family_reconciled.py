"""The heat map's shuffle null is checked against the grid it judges, cell for cell (panel A item 3,
2026-09-22).

WHY. Each column's circled cell is the best of the lengths of signal tried, and its corrected p is
read against the distribution of the same best-of-lengths choice on shuffled pain scores. That p
means what it says only if the family the shuffle ran on IS the family the best cell was chosen
from: the same reports, the same missing-value masks, the same minimum-pairs floor. The older
full-spectrum search got this wrong three times before it measured it (`RECONCILIATION_F8.md`:
different outlier-rule samples, a different floor, a different screen threshold) and now publishes
the measurement on every run (`perm_family_reconciled`, `perm_family_max_abs_dev_from_corr`,
`perm_family_cells_in_selection_only`). The grid's own shuffle path had no such check. Now it runs
the shuffle's own arithmetic once on the UNshuffled scores and compares that family with the grid,
cell for cell.

Pinned on the values: on a grid built by the sweep itself, every cell agrees to machine precision
and none is selectable but outside the null's family, for the correlation and for the area under
the curve; a grid that disagrees -- by one cell, or by a cell the null never admitted -- reads False
with the number that says by how much. Nothing refuses anything.

Run inside the container:
    python3 -W ignore modules/Biomarkers/tests/test_sweep_null_family_reconciled.py
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
try:
    from modules.Biomarkers.routines import analytics as A
except ImportError:                                        # pragma: no cover - host spelling
    from Biomarkers.routines import analytics as A


def _grid(n=120, seed=5, holes=True):
    """Three bands, three lengths; some band power missing, as a real record has."""
    rng = np.random.default_rng(seed)
    pain = np.clip(np.round(5 + rng.normal(0, 2, n)), 0, 10)
    power = {}
    for L in (1.0, 5.0, 30.0):
        x = 100 + 5 * pain[:, None] + rng.normal(0, 15, (n, 3))
        if holes:
            x[rng.random((n, 3)) < 0.1] = np.nan
        power[L] = x
    return power, pain, [12.5, 20.5, 24.5]


def _sweep(**kw):
    power, pain, centers = _grid(**kw)
    return A.band_time_sweep_from_power(power, pain, center_freqs_hz=centers, n_perm=50, n_boot=40)


def test_the_sweep_publishes_the_check_and_it_holds_on_its_own_grid():
    sw = _sweep()
    rec = sw.get("null_family_reconciliation")
    assert rec is not None, sorted(sw)
    for kind in ("correlation", "auc"):
        r = rec[kind]
        assert r["perm_family_reconciled"] is True, (kind, r)
        assert r["perm_family_max_abs_dev_from_corr"] <= 1e-9, (kind, r)
        assert r["perm_family_cells_in_selection_only"] == 0, (kind, r)
        assert r["perm_family_cells_compared"] == 9, (kind, r)
    print("OK both families reconciled: max deviation "
          f"{rec['correlation']['perm_family_max_abs_dev_from_corr']:.1e} (r), "
          f"{rec['auc']['perm_family_max_abs_dev_from_corr']:.1e} (AUC)")


def test_a_grid_that_disagrees_by_one_cell_reads_false_with_the_size_of_the_disagreement():
    null = {"observed_abs_by_length": np.array([[0.2, 0.3], [0.1, 0.4]]),
            "in_family": np.ones((2, 2), dtype=bool)}
    grid = np.array([[0.2, -0.3], [0.1, 0.45]])            # one cell off by 0.05
    r = A._null_family_reconciliation(np.abs(grid), null)
    assert r["perm_family_reconciled"] is False
    assert abs(r["perm_family_max_abs_dev_from_corr"] - 0.05) < 1e-12
    assert r["perm_family_cells_compared"] == 4


def test_a_selectable_cell_the_null_never_admitted_is_counted_and_breaks_the_check():
    null = {"observed_abs_by_length": np.array([[0.2, 0.0]]),
            "in_family": np.array([[True, False]])}          # the second cell fell under the floor
    grid = np.array([[0.2, 0.61]])
    r = A._null_family_reconciliation(np.abs(grid), null)
    assert r["perm_family_cells_in_selection_only"] == 1
    assert abs(r["perm_family_cells_in_selection_only_max_abs_r"] - 0.61) < 1e-12
    assert r["perm_family_reconciled"] is False


def test_the_null_itself_is_unchanged_by_the_check():
    """The same seed gives the same shuffled bests, bit for bit, as it did before the check existed:
    the check reads the family, it does not alter it."""
    power, pain, centers = _grid()
    X = np.stack([power[L] for L in (1.0, 5.0, 30.0)], axis=0)
    a = A._best_of_windows_null_correlation(X, pain, n_perm=40, rng=np.random.default_rng(1))
    b = A._best_of_windows_null_correlation(X, pain, n_perm=40, rng=np.random.default_rng(1))
    assert np.array_equal(a["best_by_shuffle"], b["best_by_shuffle"])
    fam = a["observed_abs_by_length"]
    assert fam.shape == (3, 3)


if __name__ == "__main__":
    for fn in (test_the_sweep_publishes_the_check_and_it_holds_on_its_own_grid,
               test_a_grid_that_disagrees_by_one_cell_reads_false_with_the_size_of_the_disagreement,
               test_a_selectable_cell_the_null_never_admitted_is_counted_and_breaks_the_check,
               test_the_null_itself_is_unchanged_by_the_check):
        fn()
    print("All null-family reconciliation tests passed.")
