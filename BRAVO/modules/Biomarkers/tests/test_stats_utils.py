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


def test_bh_fdr_matches_statsmodels_independent_implementation():
    """`bh_fdr` is hand-rolled (rank, adjust, enforce monotonicity by reverse cummin). Nothing
    before this test checked it against an independent, published implementation of the same
    procedure -- a review found this gap: two mistakes in a hand-rolled BH pass the same way (a
    self-consistency test wouldn't catch either), an off-the-shelf one would not.
    """
    from statsmodels.stats.multitest import multipletests

    rng = np.random.default_rng(11)
    for trial, p in enumerate([
        np.array([0.001, 0.04, 0.30, 0.50, 0.90]),                 # the docstring's own example
        rng.uniform(0.0, 1.0, size=1),                              # a single test
        rng.uniform(0.0, 1.0, size=22),                             # this project's own family size
        np.full(30, 0.5),                                           # every p-value tied
        rng.uniform(0.0, 1e-6, size=15),                            # every p-value near zero
    ]):
        q_ours = su.bh_fdr(p)
        _, q_ref, _, _ = multipletests(p, method="fdr_bh")
        assert np.allclose(q_ours, q_ref, atol=1e-10), (
            f"trial {trial}: bh_fdr disagrees with statsmodels' fdr_bh -- "
            f"ours={q_ours} ref={q_ref}")

    # NaNs: statsmodels has no NaN handling of its own, so compare only on the finite subset,
    # which is exactly what bh_fdr's own docstring promises (NaNs preserved, not dropped).
    p_with_nan = np.array([0.01, np.nan, 0.02, 0.5, np.nan, 0.001])
    finite = np.isfinite(p_with_nan)
    q_ours = su.bh_fdr(p_with_nan)
    _, q_ref, _, _ = multipletests(p_with_nan[finite], method="fdr_bh")
    assert np.all(np.isnan(q_ours[~finite]))
    assert np.allclose(q_ours[finite], q_ref, atol=1e-10)
    print("OK bh_fdr agrees with statsmodels.stats.multitest.multipletests(method='fdr_bh') "
          "across 5 constructed families and a family carrying NaNs")


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
    # Anti-persistence (negative lag-1 autocorrelation) must NOT extend the block length: a strongly
    # alternating series needs no long blocks, and taking abs() of r1 used to wrongly inflate it.
    alt = np.tile([1.0, -1.0], 200)                             # lag-1 autocorr ~ -1
    assert su.block_length_for(alt) == 1


def test_auc_block_perm_null():
    rng = np.random.default_rng(0)
    n = 300
    labels = (rng.random(n) < 0.4).astype(float)
    # Pure null: score independent of labels -> observed AUC near 0.5, p not significant.
    null_score = rng.normal(size=n)
    r_null = su.auc_block_perm_null(null_score, labels, n_perm=1000, seed=1)
    assert r_null["observed"] is not None
    assert 0.45 <= r_null["observed"] <= 0.65, r_null["observed"]
    assert r_null["p_value"] > 0.05, r_null["p_value"]
    # Real signal: score shifted by label -> high AUC, significant p.
    sig_score = rng.normal(size=n) + 1.2 * labels
    r_sig = su.auc_block_perm_null(sig_score, labels, n_perm=1000, seed=1)
    assert r_sig["observed"] > 0.7, r_sig["observed"]
    assert r_sig["p_value"] < 0.01, r_sig["p_value"]
    # Observed AUC matches direction-folded sklearn AUC (within downsample-free exactness).
    from sklearn.metrics import roc_auc_score
    raw = roc_auc_score(labels.astype(int), sig_score)
    assert abs(r_sig["observed"] - max(raw, 1 - raw)) < 1e-9
    # Autocorrelated labels -> block length > 1 detected (preserves persistence).
    ac_labels = np.repeat((rng.random(n // 10) < 0.4).astype(float), 10)[:n]
    r_ac = su.auc_block_perm_null(rng.normal(size=n), ac_labels, n_perm=500, seed=2)
    assert r_ac["block"] >= 2, r_ac["block"]
    # add-one estimator: p strictly in (0, 1], never exactly 0.
    assert 0 < r_sig["p_value"] <= 1
    # Degenerate (single class) returns None observed, not a crash.
    deg = su.auc_block_perm_null(null_score, np.ones(n), n_perm=50)
    assert deg["observed"] is None and deg["p_value"] is None
    print("OK auc_block_perm_null: null p=%.3f signal p=%.4f ac-block=%d"
          % (r_null["p_value"], r_sig["p_value"], r_ac["block"]))


if __name__ == "__main__":
    test_bh_fdr_matches_statsmodels_independent_implementation()
    test_partial_corr_removes_confound()
    test_effective_n_shrinks_with_autocorrelation()
    test_balanced_metrics()
    test_balanced_metrics_chance_invariant_across_imbalance()
    test_fisher_z_ci()
    test_circular_block_perm_matrix_valid()
    test_block_length_for()
    test_auc_block_perm_null()
    print("All stats_utils tests passed.")
