"""Unit tests for the statistical-rigor helpers (routines/stats_utils.py).

Run inside the container:
    docker exec -w /usr/src/BRAVO bravo_pain-bravo-server-1 python3 -W ignore         modules/Biomarkers/tests/test_stats_utils.py

Merged here 2026-10-05: test_pipeline_stats.py.
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
    # Autocorrelated labels are rotated like any others: every other rotation once (decision 315),
    # which keeps their persistence whole, however many shuffles were asked for.
    ac_labels = np.repeat((rng.random(n // 10) < 0.4).astype(float), 10)[:n]
    r_ac = su.auc_block_perm_null(rng.normal(size=n), ac_labels, n_perm=500, seed=2)
    assert r_ac["block"] == 1 and r_ac["n_perm"] == n - 1, (r_ac["block"], r_ac["n_perm"])
    # add-one estimator: p strictly in (0, 1], never exactly 0.
    assert 0 < r_sig["p_value"] <= 1
    # Degenerate (single class) returns None observed, not a crash.
    deg = su.auc_block_perm_null(null_score, np.ones(n), n_perm=50)
    assert deg["observed"] is None and deg["p_value"] is None
    print("OK auc_block_perm_null: null p=%.3f signal p=%.4f rotations=%d"
          % (r_null["p_value"], r_sig["p_value"], r_ac["n_perm"]))


# --------------------------------------------------------------------------------------------------
# merged from test_pipeline_stats.py
# Regression tests for the pipeline-level statistics helpers added in the rigor review.
#
# Run inside the container:
#     docker exec -w /usr/src/BRAVO bravo_pain-bravo-server-1 python3 -W ignore         modules/Biomarkers/tests/test_pipeline_stats.py


from Biomarkers import pipeline  # noqa: E402


def test_select_biomarker_band_enforces_50hz_cap():
    """The 50 Hz biomarker cap: even when the globally strongest |R| sits at/above 50 Hz, the
    selector must NEVER pick it — it returns the strongest band strictly below 50 Hz. A grid whose
    only finite cells are >=50 Hz returns None (nothing selectable)."""
    rng = np.random.default_rng(0)
    N = 60
    f_set = np.array([10.0, 20.0, 40.0, 55.0, 60.0])
    labels = np.linspace(0, 10, N) + rng.normal(0, 0.3, N)
    feat = rng.normal(0, 1, (N, 1, f_set.size))
    feat[:, 0, 4] = labels * 2 + rng.normal(0, 0.05, N)   # 60 Hz: near-perfect, strongest GLOBALLY
    feat[:, 0, 1] = labels + rng.normal(0, 0.6, N)         # 20 Hz: strong but weaker, < 50
    corr = np.array([[np.corrcoef(feat[:, 0, j], labels)[0, 1] for j in range(f_set.size)]])
    result = {"corr": corr, "f_set": f_set, "feature": feat, "labels": labels,
              "pval": np.full((1, f_set.size), 0.001)}
    # The global argmax |R| is the 60 Hz cell -- the cap must override it.
    assert f_set[int(np.argmax(np.abs(corr[0])))] >= 50.0
    sel = pipeline.select_biomarker_band(result, q_threshold=0.05)
    assert sel is not None
    assert sel[4] < pipeline.MAX_BIOMARKER_FREQ_HZ, f"selected band {sel[4]} Hz violates the 50 Hz cap"
    assert sel[4] == 20.0
    # When every finite cell is >= 50 Hz, NOTHING is selectable.
    res_all_high = dict(result, f_set=np.array([50.0, 55.0, 60.0, 70.0, 80.0]))
    assert pipeline.select_biomarker_band(res_all_high) is None


def test_available_frequencies_counts_and_split():
    """_available_frequencies reports per-band sample/day/label counts pooling chronic+streaming,
    and never mixes bands."""
    import pandas as pd
    base = pd.Timestamp("2025-09-01")
    rows = []
    # 7.8 Hz band: 3 days, mixed labels (chronic + streaming pooled — source is irrelevant here).
    for d in range(3):
        for k in range(4):
            rows.append({"timestamp": base + pd.Timedelta(days=d, hours=k), "frequency_hz": 7.8,
                         "pain_level": float(d % 2)})              # day0=0, day1=1, day2=0
    # 22.5 Hz band: 2 days, one fully unlabeled (pain_level NaN) -> counts as samples/days but not labeled.
    for d in range(2):
        for k in range(3):
            rows.append({"timestamp": base + pd.Timedelta(days=10 + d, hours=k), "frequency_hz": 22.5,
                         "pain_level": (1.0 if d == 0 else np.nan)})
    cv = pd.DataFrame(rows)
    av = pipeline._available_frequencies(cv)
    by = {round(a["frequency_hz"], 1): a for a in av}
    assert set(by) == {7.8, 22.5}
    assert by[7.8]["n_samples"] == 12 and by[7.8]["n_days"] == 3
    assert by[7.8]["n_labeled"] == 12 and by[7.8]["n_pos"] == 4 and by[7.8]["n_neg"] == 8
    assert by[22.5]["n_samples"] == 6 and by[22.5]["n_days"] == 2
    assert by[22.5]["n_labeled"] == 3 and by[22.5]["n_days_labeled"] == 1
    # No frequency column -> empty (legacy data).
    assert pipeline._available_frequencies(cv.drop(columns=["frequency_hz"])) == []


def test_decode_by_frequency_never_pools_bands():
    """_decode_by_frequency slices the frame per sensing band and computes ROC/Otsu/binarization on
    that band ALONE — a contact's 7.8 Hz and 22.5 Hz samples never mix, and a band with too few
    labeled samples reports counts but no AUC."""
    import pandas as pd
    base = pd.Timestamp("2025-09-01")
    rows = []
    # 7.8 Hz: 12 labeled days, power separates the classes (decodable).
    for d in range(12):
        hi = (d % 2 == 0)
        for k in range(5):
            rows.append({"timestamp": base + pd.Timedelta(days=d, hours=k),
                         "frequency_hz": 7.8, "LFP_smoothed": (150.0 if hi else 110.0),
                         "pain_level": (1.0 if hi else 0.0), "nrs": (8.0 if hi else 2.0)})
    # 22.5 Hz: a single day, one class -> too little to fit a detector.
    for k in range(4):
        rows.append({"timestamp": base + pd.Timedelta(days=40, hours=k),
                     "frequency_hz": 22.5, "LFP_smoothed": 130.0, "pain_level": 1.0, "nrs": 7.0})
    cv = pd.DataFrame(rows)
    fd = pipeline._decode_by_frequency(cv, "nrs")
    assert set(fd) == {"7.8", "22.5"}
    # 7.8 band: decodable, perfectly separable -> AUC == 1.0, Otsu between the two power levels.
    assert fd["7.8"]["n_samples"] == 60 and fd["7.8"]["n_days"] == 12
    assert fd["7.8"]["roc"]["auc"] == 1.0
    assert 110.0 < fd["7.8"]["distribution"]["otsu"] < 150.0
    assert fd["7.8"]["binarization"]["n_pos_days"] == 6 and fd["7.8"]["binarization"]["n_neg_days"] == 6
    assert len(fd["7.8"]["binarization"]["daily"]) == 12
    # 22.5 band: insufficient -> no AUC, but counts still reported.
    assert fd["22.5"]["roc"]["auc"] is None and fd["22.5"]["n_samples"] == 4
    # No frequency column -> empty.
    assert pipeline._decode_by_frequency(cv.drop(columns=["frequency_hz"]), "nrs") == {}
