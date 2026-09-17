"""The PI, 2026-09-16: every cell of the two heat maps carries its own uncorrected p-value on the
response, so the page prints it (the hover's "X ratings, p = Y", the line above the violin) instead
of working it out in the browser. Pearson's p for the correlation grid; for the AUC grid the rank
test's p (Mann-Whitney U -- the AUC IS that test's
statistic divided by n_high * n_low; scipy's own `mannwhitneyu(method="asymptotic")`, vectorised over
the band centres) -- not a t-test on the two groups' means.
"""
import numpy as np
from scipy import stats

try:
    from modules.Biomarkers.routines import analytics as A
except ImportError:                                        # pragma: no cover - host spelling
    from Biomarkers.routines import analytics as A


def _grid(seed=5, n=120):
    rng = np.random.default_rng(seed)
    pain = np.clip(np.round(rng.normal(6, 2, n)), 0, 10)
    x1 = 100 - 6 * pain + rng.normal(0, 15, n)             # a real relationship
    x2 = rng.normal(100, 15, n)                            # none
    power = {1.0: np.column_stack([x1, x2]), 5.0: np.column_stack([x2, x1])}
    return power, pain, [12.5, 20.5]


def test_every_cell_carries_pearsons_p_computed_from_its_own_r_and_n():
    power, pain, centers = _grid()
    sw = A.band_time_sweep_from_power(power, pain, center_freqs_hz=centers, n_perm=20, n_boot=50)
    assert "p_grid" in sw and np.shape(sw["p_grid"]) == np.shape(sw["correlation_grid"])
    for t in range(2):
        for c in range(2):
            r, n, p = sw["correlation_grid"][t][c], sw["n_grid"][t][c], sw["p_grid"][t][c]
            tstat = r * np.sqrt((n - 2) / (1 - r * r))
            want = 2 * stats.t.sf(abs(tstat), n - 2)
            assert abs(p - want) < 1e-12, (t, c, p, want)
    # the cell with the planted relationship is far below 0.05, the one without is not tiny
    assert sw["p_grid"][0][0] < 1e-4 and sw["p_grid"][0][1] > 1e-3


def test_every_auc_cell_carries_scipys_asymptotic_mann_whitney_p():
    power, pain, centers = _grid()
    sw = A.band_time_sweep_from_power(power, pain, center_freqs_hz=centers, n_perm=20, n_boot=50)
    assert "auc_p_grid" in sw and np.shape(sw["auc_p_grid"]) == np.shape(sw["auc_grid"])
    for t in range(2):
        for c in range(2):
            assert 0 < sw["auc_p_grid"][t][c] <= 1
    assert sw["auc_p_grid"][0][0] < 1e-3 and sw["auc_p_grid"][0][1] > 1e-3


def test_the_column_helper_is_scipys_own_result_per_column_with_missing_values_left_out():
    rng = np.random.default_rng(11)
    X = rng.normal(100, 15, (75, 3)); X[:40, 0] += 10; X[3, 1] = np.nan; X[50, 2] = np.nan
    y = np.r_[np.ones(40), np.zeros(35)]
    got = A.mann_whitney_p_columns(X, y)
    for c in range(3):
        hi, lo = X[:40, c], X[40:, c]
        want = stats.mannwhitneyu(hi[np.isfinite(hi)], lo[np.isfinite(lo)],
                                  alternative="two-sided", method="asymptotic").pvalue
        assert abs(got[c] - want) < 1e-12, (c, got[c], want)
    assert got[0] < 0.01


def test_an_empty_cell_carries_no_p():
    X = np.array([[1.0, np.nan], [2.0, np.nan], [3.0, 5.0], [4.0, 6.0]])
    p = A.mann_whitney_p_columns(X, np.array([1, 1, 0, 0]))
    assert np.isfinite(p[0]) and np.isnan(p[1])
    p = A.pearson_p_from_r(np.array([0.3, np.nan, 0.99999]), np.array([2, 30, 30]))
    assert np.isnan(p[0]) and np.isnan(p[1]) and np.isfinite(p[2])


def test_the_blank_response_carries_the_two_grids_empty_rather_than_absent():
    sw = A.band_time_sweep_from_power({}, np.array([]), center_freqs_hz=[12.5], n_perm=5, n_boot=5)
    assert sw["p_grid"] == [] and sw["auc_p_grid"] == []
