"""Unit tests for the statistical-rigor helpers (routines/stats_utils.py).

Run inside the container:
    docker exec -w /usr/src/BRAVO bravo_pain-bravo-server-1 python3 -W ignore \
        modules/Biomarkers/tests/test_stats_utils.py
"""
import os
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from Biomarkers.routines import stats_utils as su  # noqa: E402


def test_bh_fdr():
    # All-null-ish small p's should be inflated by BH; a single tiny p stays significant.
    p = np.array([0.001, 0.04, 0.30, 0.50, 0.90])
    q = su.bh_fdr(p)
    assert q.shape == p.shape
    assert np.all((q >= 0) & (q <= 1))
    assert np.all(np.diff(np.sort(q)) >= -1e-12)         # monotone after sorting
    assert q[0] < 0.05 and q[2] > 0.05                    # smallest survives, mid does not
    # NaNs preserved
    q2 = su.bh_fdr(np.array([0.01, np.nan, 0.02]))
    assert np.isnan(q2[1]) and np.isfinite(q2[0]) and np.isfinite(q2[2])


def test_partial_corr_removes_confound():
    rng = np.random.default_rng(0)
    c = rng.normal(size=400)                              # confound (e.g. stim amplitude)
    x = c + 0.3 * rng.normal(size=400)                   # both driven by c, otherwise independent
    y = c + 0.3 * rng.normal(size=400)
    raw = np.corrcoef(x, y)[0, 1]
    partial = su.partial_corr(x, y, c)
    assert raw > 0.7                                      # spurious association via the confound
    assert abs(partial) < 0.25                            # removed after adjusting for c


def test_effective_n_shrinks_with_autocorrelation():
    rng = np.random.default_rng(1)
    iid = rng.normal(size=500)
    # strongly autocorrelated series (random walk-ish)
    ac = np.cumsum(rng.normal(size=500))
    n_iid = su.effective_n(iid, rng.normal(size=500))
    n_ac = su.effective_n(ac, np.cumsum(rng.normal(size=500)))
    assert n_iid > n_ac                                   # serial dependence shrinks effective N
    assert n_ac >= 2


def test_balanced_metrics():
    m = su.balanced_metrics(sens=1.0, spec=0.0, n_pos=10, n_neg=90)
    assert abs(m["balanced_accuracy"] - 0.5) < 1e-9
    assert abs(m["prevalence"] - 0.1) < 1e-9
    # Chance for BALANCED accuracy is ALWAYS 0.5, independent of imbalance.
    assert abs(m["chance_accuracy"] - 0.5) < 1e-9
    # The majority fraction (0.9 here) is the RAW-accuracy chance level, reported separately.
    assert abs(m["majority_accuracy"] - 0.9) < 1e-9


def test_balanced_metrics_chance_invariant_across_imbalance():
    """The BALANCED-accuracy chance level is ALWAYS 0.5, no matter the class imbalance, while the
    majority fraction (the RAW-accuracy reference) tracks max(n_pos,n_neg)/total. Balanced accuracy
    itself is mean(sens,spec) and is likewise independent of the prevalence."""
    for n_pos, n_neg in [(10, 90), (50, 50), (1, 999), (80, 20)]:
        m = su.balanced_metrics(sens=0.7, spec=0.6, n_pos=n_pos, n_neg=n_neg)
        total = n_pos + n_neg
        assert abs(m["chance_accuracy"] - 0.5) < 1e-12        # chance is 0.5 for EVERY ratio
        assert abs(m["majority_accuracy"] - max(n_pos, n_neg) / total) < 1e-12
        assert abs(m["balanced_accuracy"] - 0.65) < 1e-12     # mean(0.7,0.6), prevalence-free
        assert abs(m["prevalence"] - n_pos / total) < 1e-12
    # Degenerate folds must not divide-by-zero: chance stays 0.5, majority well-defined.
    m0 = su.balanced_metrics(sens=0.0, spec=1.0, n_pos=0, n_neg=50)
    assert abs(m0["chance_accuracy"] - 0.5) < 1e-12
    assert m0["prevalence"] == 0.0 and m0["majority_accuracy"] == 1.0


def test_block_perm_pvalue():
    rng = np.random.default_rng(2)
    N, M = 120, 20
    X = rng.normal(size=(N, M))
    y_null = rng.normal(size=N)                           # no real association
    fn = lambda Xm, ym: float(np.max(np.abs([np.corrcoef(Xm[:, j], ym)[0, 1] for j in range(Xm.shape[1])])))
    p_null, used = su.block_perm_pvalue(fn(X, y_null), X, y_null, fn, n_perm=200, seed=3)
    assert used > 0 and 0 < p_null <= 1.0
    # planted strong association in one column -> small p
    y_real = X[:, 0] + 0.2 * rng.normal(size=N)
    p_real, _ = su.block_perm_pvalue(fn(X, y_real), X, y_real, fn, n_perm=200, seed=3)
    assert p_real < p_null


def test_fisher_z_ci():
    lo, hi = su.fisher_z_ci(0.5, 50)
    assert lo < 0.5 < hi and -1 < lo and hi < 1
    assert su.fisher_z_ci(0.5, 3) == (float("nan"), float("nan")) or np.isnan(su.fisher_z_ci(0.5, 3)[0])


def test_circular_block_perm_matrix_valid():
    """The vectorized generator must return (n_perm, n) with EVERY row a valid permutation of
    range(n), for block==1 and block>1 (including a block that does not divide n)."""
    rng = np.random.default_rng(5)
    for n in (7, 50, 113):
        for block in (1, 2, 7, max(1, n // 4)):
            P = su.circular_block_perm_matrix(n, block, 150, rng)
            assert P.shape == (150, n)
            assert np.array_equal(np.sort(P, axis=1), np.tile(np.arange(n), (150, 1)))


def test_block_length_for():
    rng = np.random.default_rng(6)
    iid = rng.normal(size=400)
    assert su.block_length_for(iid) == 1                       # ~no autocorrelation -> block 1
    ar = np.zeros(400); e = rng.normal(size=400)
    for t in range(1, 400):
        ar[t] = 0.9 * ar[t - 1] + e[t]
    assert su.block_length_for(ar) > 1                          # strong autocorrelation -> longer block


if __name__ == "__main__":
    test_bh_fdr()
    test_partial_corr_removes_confound()
    test_effective_n_shrinks_with_autocorrelation()
    test_balanced_metrics()
    test_balanced_metrics_chance_invariant_across_imbalance()
    test_block_perm_pvalue()
    test_fisher_z_ci()
    test_circular_block_perm_matrix_valid()
    test_block_length_for()
    print("All stats_utils tests passed.")
