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


def _find_best_threshold_for_metric(train_df, thresholds, metric="sens"):
    """
    metric='sens' -> maximize sensitivity, tie-break by specificity, then accuracy
    metric='spec' -> maximize specificity, tie-break by sensitivity, then accuracy
    """
    true_labels = train_df["pain_level"].astype(int).values

    best_thr  = thresholds[0]
    best_sens = -1
    best_spec = -1
    best_acc  = -1

    for thr in thresholds:
        pred = (train_df["LFP_smoothed"] >= thr).astype(int).values
        sens, spec = _sens_spec(true_labels, pred)
        acc = metrics.accuracy_score(true_labels, pred)

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

def run_chronic_threshold(cv_df, *, thresholds=None, train_days=7, gap_days=1, test_days=2):
    """
    Convenience wrapper: derive the series bounds from `cv_df` and call the verbatim
    `run_sliding_window_dual` unchanged.

    Parameters
    ----------
    cv_df : DataFrame with columns `timestamp`, `LFP_smoothed`, `pain_level` (0/1).
    thresholds : iterable[int] | None
        Candidate LFP thresholds; default np.arange(60, 200, 1) (the notebook grid).
    train_days, gap_days, test_days : int
        Sliding-window geometry (notebook defaults 7 / 1 / 2 -> needs >= ~10 days of data).
    """
    if thresholds is None:
        thresholds = np.arange(60, 200, 1)
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
