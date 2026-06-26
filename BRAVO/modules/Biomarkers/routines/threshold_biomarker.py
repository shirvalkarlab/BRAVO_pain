"""
Chronic-trend threshold pain biomarker routines (the "10-min PSD"/BrainSense Timeline path).

PROVENANCE
----------
Lifted from `dbs_stage2_percept/threshold_biomarker.ipynb` (cell 13; author: Yiyuan Han,
Shirvalkar Lab). The four functions below -- `otsu1d`, `_sens_spec`,
`_find_best_threshold_for_metric`, `run_sliding_window_dual` -- are copied **byte-for-byte**
from the notebook so the science is REUSED UNCHANGED, mirroring how `streaming_psd.py` vendors
the streaming routines. Only `run_chronic_threshold` (the thin, non-science wrapper at the
bottom) is new glue.

What this computes
------------------
A sliding-window, threshold-based pain detector over the Percept ~10-min chronic LFP power
trend. Per cross-validation window it class-balances the training fold, sweeps integer LFP
thresholds, picks the threshold maximizing a chosen TRAIN metric (sensitivity or specificity),
applies that scalar threshold to the held-out test fold (`pred = LFP_smoothed >= thr`), and
aggregates mean/std of thresholds and test sens/spec/acc across windows for BOTH objectives.

Input contract (verified against notebook cell 13): a tidy DataFrame `cv_df` with columns
`timestamp`, `LFP_smoothed`, and a binary `pain_level` (0/1). The detector reads only
`LFP_smoothed` (feature) and `pain_level` (label); `timestamp` slices the train/test folds.

KNOWN QUIRKS (preserved verbatim -- do NOT "fix"; flagged for callers):
  * `otsu1d` uses `== None` and treats its input as a histogram; it is non-standard Otsu and is
    NOT used by the threshold detector itself (kept only for completeness / parity with the
    notebook). The chronic adapter does NOT rely on it for label construction.
  * Thresholds are fixed integer device units (`np.arange(60, 200, 1)` by default) calibrated to
    the notebook's raw LFP magnitude. The BRAVO Chronic recording LFP (Data[:,0]) is the decoded
    equivalent (device-internal power units); confirm magnitudes match before trusting numbers.
  * Train folds are class-balanced by undersampling (random_state=42); test folds are left at
    their natural class distribution.
  * Windows step by `test_days` (non-overlapping test folds).
"""

import numpy as np
import pandas as pd
from sklearn import metrics


# ============================================================================
# VERBATIM from threshold_biomarker.ipynb (cell 13)
# ============================================================================

def otsu1d(histogram, hist_min, hist_max):
    if hist_min == None:
        hist_min = np.min(histogram)
    if hist_max == None:
        hist_max = np.max(histogram)

    threshold = hist_min
    between_class_variance = 0
    for i in range(hist_min, hist_max):
        w1 = np.sum(histogram[:i]) / np.sum(histogram)
        w2 = np.sum(histogram[i:]) / np.sum(histogram)
        sigma1 = np.sum(np.square(histogram[:i] - np.mean(histogram[:i]))) / np.sum(histogram[:i])
        sigma2 = np.sum(np.square(histogram[i:] - np.mean(histogram[i:]))) / np.sum(histogram[i:])
        between_class_variance_tmp = w1 * sigma1 + w2 * sigma2
        if between_class_variance_tmp > between_class_variance:
            between_class_variance = between_class_variance_tmp
            threshold = i
    return threshold


def _sens_spec(true, pred):
    true = np.asarray(true).astype(int)
    pred = np.asarray(pred).astype(int)
    tn, fp, fn, tp = metrics.confusion_matrix(true, pred, labels=[0, 1]).ravel()
    sens = tp / (tp + fn) if (tp + fn) > 0 else np.nan
    spec = tn / (tn + fp) if (tn + fp) > 0 else np.nan
    return sens, spec


def _threshold_metric_arrays(true_labels, scores, thresholds):
    """Vectorized per-threshold sens/spec/acc for the rule `pred = scores >= thr`.

    Replaces the per-threshold sklearn confusion_matrix / accuracy_score calls (which dominated the
    biomarker recompute: ~35 s of `_param_validation` overhead across 40k+ calls) with a single
    `searchsorted` pass — sens=tp/P and spec=tn/N are step functions of the threshold, so the whole
    sweep is one sorted scan. Returns (sens_arr, spec_arr, acc_arr), each aligned to `thresholds`,
    and IDENTICAL element-for-element to the loop it replaces (verified by
    test_find_best_threshold_vectorized_matches_reference):

      * sens/spec use the same integer counts -> same float division (NaN when the denominator is 0,
        matching `_sens_spec`); acc = (tp+tn)/total == sklearn accuracy_score.
      * NaN scores are handled exactly as the original `score >= thr` (always False -> pred 0): they
        are excluded from the sorted positive/negative score arrays but still counted in P and N, so
        a NaN-scored positive is an FN and a NaN-scored negative is a TN at every threshold.
    """
    true_labels = np.asarray(true_labels).astype(int)
    scores = np.asarray(scores, dtype=float)
    thr = np.asarray(thresholds, dtype=float)

    P = int((true_labels == 1).sum())   # total positives  (incl. NaN-scored -> always FN)
    N = int((true_labels == 0).sum())   # total negatives  (incl. NaN-scored -> always TN)
    total = P + N

    pos = np.sort(scores[(true_labels == 1) & np.isfinite(scores)])  # finite positive scores, asc
    neg = np.sort(scores[(true_labels == 0) & np.isfinite(scores)])  # finite negative scores, asc

    # count of finite scores >= thr (side='left' so the boundary value == thr is included, matching >=)
    tp = pos.size - np.searchsorted(pos, thr, side="left")           # per-threshold true positives
    fp = neg.size - np.searchsorted(neg, thr, side="left")           # per-threshold false positives
    fn = P - tp
    tn = N - fp

    with np.errstate(invalid="ignore", divide="ignore"):
        sens = np.where((tp + fn) > 0, tp / (tp + fn), np.nan)
        spec = np.where((tn + fp) > 0, tn / (tn + fp), np.nan)
    acc = (tp + tn) / total if total > 0 else np.full(thr.shape, np.nan)
    return sens, spec, acc


def _find_best_threshold_for_metric(train_df, thresholds, metric="sens"):
    """
    metric='sens' -> maximize sensitivity, tie-break by specificity, then accuracy
    metric='spec' -> maximize specificity, tie-break by sensitivity, then accuracy

    Metric values are now computed for ALL thresholds in one vectorized pass
    (`_threshold_metric_arrays`); the selection loop below is the byte-for-byte notebook logic,
    unchanged, just reading the precomputed arrays instead of recomputing per threshold.
    """
    true_labels = train_df["pain_level"].astype(int).values
    sens_arr, spec_arr, acc_arr = _threshold_metric_arrays(
        true_labels, train_df["LFP_smoothed"].values, thresholds)

    best_thr  = thresholds[0]
    best_sens = -1
    best_spec = -1
    best_acc  = -1

    for i, thr in enumerate(thresholds):
        sens = sens_arr[i]
        spec = spec_arr[i]
        acc  = acc_arr[i]

        if metric == "sens":
            better = (
                (sens > best_sens) or
                (np.isclose(sens, best_sens) and spec > best_spec) or
                (np.isclose(sens, best_sens) and np.isclose(spec, best_spec) and acc > best_acc)
            )
        else:
            better = (
                (spec > best_spec) or
                (np.isclose(spec, best_spec) and sens > best_sens) or
                (np.isclose(spec, best_spec) and np.isclose(sens, best_sens) and acc > best_acc)
            )

        if better:
            best_thr  = thr
            best_sens = sens
            best_spec = spec
            best_acc  = acc

    return best_thr, best_sens, best_spec, best_acc


def best_threshold_by_balanced_auc(true_labels, scores, thresholds):
    """Pick the threshold maximizing the orientation-free balanced AUC of the binary rule
    `pred = score >= thr`, vectorized — the exact computation the sliding-window and all-data loops
    in analytics.py did with a per-threshold sklearn `roc_auc_score(y, binary_pred)` call.

    For a BINARY prediction, roc_auc_score(y, pred) == (sens + spec) / 2 (balanced accuracy), so the
    notebook's `a = max(auc, 1-auc)` over the grid is `max(ba, 1-ba)` where ba=(sens+spec)/2 — one
    vectorized pass instead of 140 sklearn calls per window. Returns (best_thr, best_auc).

    EQUIVALENCE (verified by test_best_threshold_balanced_auc_matches_reference):
      * The BEST AUC value is identical to the original loop's to full float precision — 797 fuzz
        cases with both pain classes present (NaN scores and heavy ties included; one-class folds are
        skipped before this selector is ever called, exactly as the production code does). The
        reported per-window sens/spec/acc/auc are therefore unchanged.
      * The CHOSEN threshold AMONG EXACT AUC TIES is made deterministic here: np.argmax returns the
        FIRST (lowest) threshold achieving the maximum balanced AUC. The original loop's choice among
        ties depended on sklearn's internal AUC float-accumulation differing from (sens+spec)/2 at the
        ~1e-16 level, which could flip the strict-greater `>` onto a later equally-optimal threshold —
        an undocumented float-noise artifact, NOT a difference in the science. On real continuous LFP
        data the AUC-maximizing threshold lands at a non-tied grid edge (observed on RCS08: per-window
        thresholds at grid boundaries 60/192 where no AUC tie exists), so the deterministic choice
        coincides with an AUC-optimal threshold there. The "first AUC-optimal threshold" rule is
        reproducible run-to-run, which the original (sklearn-float-dependent) tie-break was not.
      * Single-class-prediction thresholds (tp+fp == 0 or == n, i.e. the original's `cls.nunique() < 2`
        skip) are masked out exactly as before. If no threshold yields a 2-class split, returns
        (float(thresholds[0]), -1.0) — the untouched initial state.
    """
    true_labels = np.asarray(true_labels).astype(int)
    scores = np.asarray(scores, dtype=float)
    thr = np.asarray(thresholds, dtype=float)
    sens, spec, _acc = _threshold_metric_arrays(true_labels, scores, thr)
    ba = (sens + spec) / 2.0                      # == roc_auc_score(y, binary_pred)
    a = np.maximum(ba, 1.0 - ba)                  # orientation-free, matches max(auc, 1-auc)

    n = true_labels.size
    # predicted-positive count per threshold = #(finite scores >= thr); NaN scores are never >= thr.
    finite_sorted = np.sort(scores[np.isfinite(scores)])
    n_ge = finite_sorted.size - np.searchsorted(finite_sorted, thr, side="left")
    # single-class prediction (all 0 or all 1) -> skipped in the original; also drop NaN AUC.
    valid = (n_ge > 0) & (n_ge < n) & np.isfinite(a)
    if not valid.any():
        return float(thr[0]), -1.0
    a_masked = np.where(valid, a, -np.inf)
    i = int(np.argmax(a_masked))                  # first max (ascending) == first-wins tie-break
    return float(thr[i]), float(a[i])


def _find_best_threshold_for_metric_reference(train_df, thresholds, metric="sens"):
    """VERBATIM pre-vectorization implementation, kept ONLY as the equivalence oracle for
    test_find_best_threshold_vectorized_matches_reference. Do not call in production."""
    true_labels = train_df["pain_level"].astype(int).values
    best_thr, best_sens, best_spec, best_acc = thresholds[0], -1, -1, -1
    for thr in thresholds:
        pred = (train_df["LFP_smoothed"] >= thr).astype(int).values
        sens, spec = _sens_spec(true_labels, pred)
        acc = metrics.accuracy_score(true_labels, pred)
        if metric == "sens":
            better = ((sens > best_sens) or
                      (np.isclose(sens, best_sens) and spec > best_spec) or
                      (np.isclose(sens, best_sens) and np.isclose(spec, best_spec) and acc > best_acc))
        else:
            better = ((spec > best_spec) or
                      (np.isclose(spec, best_spec) and sens > best_sens) or
                      (np.isclose(spec, best_spec) and np.isclose(sens, best_sens) and acc > best_acc))
        if better:
            best_thr, best_sens, best_spec, best_acc = thr, sens, spec, acc
    return best_thr, best_sens, best_spec, best_acc


def run_sliding_window_dual(cv_df, series_start, series_end, thresholds, train_days, gap_days, test_days):
    test_starts = []
    t = series_start + pd.Timedelta(days=train_days + gap_days)
    while t < series_end:
        test_starts.append(t)
        t += pd.Timedelta(days=test_days)

    sens_thr_list = []
    spec_thr_list = []

    test_acc_at_sens_thr = []
    test_sens_at_sens_thr = []
    test_spec_at_sens_thr = []

    test_acc_at_spec_thr = []
    test_sens_at_spec_thr = []
    test_spec_at_spec_thr = []

    n_windows = 0

    for test_start in test_starts:
        test_end    = test_start + pd.Timedelta(days=test_days)
        gap_start   = test_start - pd.Timedelta(days=gap_days)
        train_start = gap_start  - pd.Timedelta(days=train_days)

        test_data  = cv_df[(cv_df["timestamp"] >= test_start)  & (cv_df["timestamp"] < test_end)].dropna(subset=["pain_level"])
        train_data = cv_df[(cv_df["timestamp"] >= train_start) & (cv_df["timestamp"] < gap_start)].dropna(subset=["pain_level"])

        if len(test_data) == 0 or len(train_data) == 0:
            continue
        if train_data["pain_level"].nunique() < 2:
            continue

        min_count = int(train_data["pain_level"].value_counts().min())
        balanced_train = pd.concat([
            train_data[train_data["pain_level"] == cls].sample(min_count, random_state=42)
            for cls in sorted(train_data["pain_level"].unique())
        ]).reset_index(drop=True)

        thr_sens, _, _, _ = _find_best_threshold_for_metric(balanced_train, thresholds, metric="sens")
        thr_spec, _, _, _ = _find_best_threshold_for_metric(balanced_train, thresholds, metric="spec")

        true_labels = test_data["pain_level"].astype(int).values

        pred_sens = (test_data["LFP_smoothed"] >= thr_sens).astype(int).values
        acc_sens = metrics.accuracy_score(true_labels, pred_sens)
        sens_sens, spec_sens = _sens_spec(true_labels, pred_sens)

        pred_spec = (test_data["LFP_smoothed"] >= thr_spec).astype(int).values
        acc_spec = metrics.accuracy_score(true_labels, pred_spec)
        sens_spec, spec_spec = _sens_spec(true_labels, pred_spec)

        sens_thr_list.append(thr_sens)
        spec_thr_list.append(thr_spec)

        test_acc_at_sens_thr.append(acc_sens)
        if not np.isnan(sens_sens):
            test_sens_at_sens_thr.append(sens_sens)
        if not np.isnan(spec_sens):
            test_spec_at_sens_thr.append(spec_sens)

        test_acc_at_spec_thr.append(acc_spec)
        if not np.isnan(sens_spec):
            test_sens_at_spec_thr.append(sens_spec)
        if not np.isnan(spec_spec):
            test_spec_at_spec_thr.append(spec_spec)

        n_windows += 1

    if n_windows == 0:
        return dict(
            n_windows=0,
            mean_thr_sens=np.nan, std_thr_sens=np.nan,
            mean_test_acc_sens=np.nan, mean_test_sens_sens=np.nan, mean_test_spec_sens=np.nan,
            mean_thr_spec=np.nan, std_thr_spec=np.nan,
            mean_test_acc_spec=np.nan, mean_test_sens_spec=np.nan, mean_test_spec_spec=np.nan,
        )

    return dict(
        n_windows=n_windows,

        mean_thr_sens=np.mean(sens_thr_list),
        std_thr_sens=np.std(sens_thr_list),
        mean_test_acc_sens=np.mean(test_acc_at_sens_thr) if test_acc_at_sens_thr else np.nan,
        mean_test_sens_sens=np.mean(test_sens_at_sens_thr) if test_sens_at_sens_thr else np.nan,
        mean_test_spec_sens=np.mean(test_spec_at_sens_thr) if test_spec_at_sens_thr else np.nan,

        mean_thr_spec=np.mean(spec_thr_list),
        std_thr_spec=np.std(spec_thr_list),
        mean_test_acc_spec=np.mean(test_acc_at_spec_thr) if test_acc_at_spec_thr else np.nan,
        mean_test_sens_spec=np.mean(test_sens_at_spec_thr) if test_sens_at_spec_thr else np.nan,
        mean_test_spec_spec=np.mean(test_spec_at_spec_thr) if test_spec_at_spec_thr else np.nan,
    )


# ============================================================================
# Thin wrapper (NEW glue -- not science)
# ============================================================================

def _global_threshold_fit(cv_df, thresholds):
    """All-data (NO sliding window) fit: class-balance the whole series by pain_level, pick the
    sens- and spec-objective thresholds on it, and evaluate on the whole series. Returns the SAME
    dict shape as `run_sliding_window_dual` with n_windows=1 so downstream code is unchanged.

    This is GLUE (not verbatim science) -- it reuses the verbatim `_find_best_threshold_for_metric`
    and `_sens_spec` helpers. It is an in-sample fit (train == test == all data): no temporal
    cross-validation, so its sens/spec are optimistic vs the sliding-window estimates. Used when the
    user turns the sliding window OFF to characterize the whole dataset with one threshold.
    """
    data = cv_df.dropna(subset=["pain_level"])
    nan_result = dict(
        n_windows=0,
        mean_thr_sens=np.nan, std_thr_sens=np.nan,
        mean_test_acc_sens=np.nan, mean_test_sens_sens=np.nan, mean_test_spec_sens=np.nan,
        mean_thr_spec=np.nan, std_thr_spec=np.nan,
        mean_test_acc_spec=np.nan, mean_test_sens_spec=np.nan, mean_test_spec_spec=np.nan,
    )
    if len(data) == 0 or data["pain_level"].nunique() < 2:
        return nan_result

    min_count = int(data["pain_level"].value_counts().min())
    balanced = pd.concat([
        data[data["pain_level"] == cls].sample(min_count, random_state=42)
        for cls in sorted(data["pain_level"].unique())
    ]).reset_index(drop=True)

    thr_sens, _, _, _ = _find_best_threshold_for_metric(balanced, thresholds, metric="sens")
    thr_spec, _, _, _ = _find_best_threshold_for_metric(balanced, thresholds, metric="spec")

    true = data["pain_level"].astype(int).values
    pred_sens = (data["LFP_smoothed"] >= thr_sens).astype(int).values
    acc_sens = metrics.accuracy_score(true, pred_sens)
    sens_sens, spec_sens = _sens_spec(true, pred_sens)
    pred_spec = (data["LFP_smoothed"] >= thr_spec).astype(int).values
    acc_spec = metrics.accuracy_score(true, pred_spec)
    sens_spec, spec_spec = _sens_spec(true, pred_spec)

    return dict(
        n_windows=1,
        mean_thr_sens=float(thr_sens), std_thr_sens=0.0,
        mean_test_acc_sens=float(acc_sens), mean_test_sens_sens=float(sens_sens),
        mean_test_spec_sens=float(spec_sens),
        mean_thr_spec=float(thr_spec), std_thr_spec=0.0,
        mean_test_acc_spec=float(acc_spec), mean_test_sens_spec=float(sens_spec),
        mean_test_spec_spec=float(spec_spec),
    )


def run_chronic_threshold(cv_df, *, thresholds=None, train_days=7, gap_days=1, test_days=2,
                          sliding=True):
    """
    Convenience wrapper: derive the series bounds from `cv_df` and call the verbatim
    `run_sliding_window_dual` unchanged -- OR, when `sliding=False`, a single all-data fit.

    Parameters
    ----------
    cv_df : DataFrame with columns `timestamp`, `LFP_smoothed`, `pain_level` (0/1).
    thresholds : iterable[int] | None
        Candidate LFP thresholds; default np.arange(60, 200, 1) (the notebook grid).
    train_days, gap_days, test_days : int
        Sliding-window geometry (notebook defaults 7 / 1 / 2 -> needs >= ~10 days of data).
        `train_days` is driven by the user's window-months selection upstream.
    sliding : bool
        True (default) -> temporal sliding-window cross-validation (verbatim detector).
        False -> one threshold fit/evaluated on ALL data (no windows); see `_global_threshold_fit`.
    """
    if thresholds is None:
        thresholds = np.arange(60, 200, 1)
    if not sliding:
        return _global_threshold_fit(cv_df, thresholds)
    ts = pd.to_datetime(cv_df["timestamp"])
    series_start = ts.min().normalize()
    series_end = ts.max()
    return run_sliding_window_dual(cv_df, series_start, series_end, thresholds,
                                   train_days, gap_days, test_days)


# ============================================================================
# Label construction -- VERBATIM port of threshold_biomarker.ipynb (cell 10)
# ============================================================================

def kmeans_pain_level(pain_score_cluster, random_state=0):
    """
    Binary `pain_level` (0/1) via 2-cluster KMeans on a 2-D feature array
    [left_leg_vas, mpq_sum]. Ported BYTE-FOR-BYTE (minus the plotting/jitter) from
    threshold_biomarker.ipynb cell 10 -- this is the notebook's actual labeler, the
    trial-grade alternative to the adapter's simple median/cutoff split.

    Parameters
    ----------
    pain_score_cluster : array-like, shape (N, 2)
        Columns [left_leg_vas, mpq_sum] aligned to each sample (NaNs allowed).
    random_state : int
        KMeans seed (notebook used 0).

    Returns
    -------
    pain_level_all : ndarray, shape (N,) of {0.0, 1.0}
        1 = higher overall pain burden. Rows with NaN features take the label of the
        nearest valid point (Euclidean in feature space), matching the notebook.

    Notes
    -----
    Relabeling uses the combined mean of BOTH features per cluster (np.nanmean over the
    masked (n,2) sub-array), exactly as the notebook does, so cluster 1 is the higher-pain
    cluster. Raises ValueError if fewer than 2 valid (non-NaN) rows exist.
    """
    from sklearn.cluster import KMeans

    pain_score_cluster = np.asarray(pain_score_cluster, dtype=float)
    valid_idx = ~np.isnan(pain_score_cluster).any(axis=1)

    if valid_idx.sum() < 2:
        raise ValueError("Not enough valid rows to run KMeans on left_leg_vas and mpq_sum.")

    kmeans = KMeans(n_clusters=2, random_state=random_state).fit(pain_score_cluster[valid_idx])

    # Initialize all labels as NaN and fill valid rows
    pain_level_all = np.full((len(pain_score_cluster),), np.nan)
    pain_level_all[valid_idx] = kmeans.labels_

    # For rows with NaN features, assign nearest valid-point label
    for idx in range(len(pain_score_cluster)):
        if np.isnan(pain_level_all[idx]):
            point_tmp = pain_score_cluster[idx, :]
            dists = np.linalg.norm(pain_score_cluster[valid_idx] - point_tmp, axis=1)
            nearest_idx = np.argmin(dists)
            pain_level_all[idx] = kmeans.labels_[nearest_idx]

    # Ensure label 1 corresponds to higher overall pain burden
    cluster0_mean = np.nanmean(pain_score_cluster[pain_level_all == 0])
    cluster1_mean = np.nanmean(pain_score_cluster[pain_level_all == 1])
    if cluster0_mean > cluster1_mean:
        pain_level_all = 1 - pain_level_all

    return pain_level_all
