"""
Visualization analytics for the Biomarkers card.

These functions reproduce the figures from Yiyuan Han's notebooks
(threshold_biomarker.ipynb, biomarker_analysis_streaming.ipynb) as JSON-able series the React
card plots. They build on the verbatim science in `threshold_biomarker.py` / `streaming_psd.py`
(per-window threshold by train AUC, test sens/spec/acc/AUC, ROC, Otsu histogram, KMeans cluster
scatter, and the Pearson-R-vs-frequency correlation spectrum).
"""

import threading as _threading
import warnings

import numpy as np
import pandas as pd

from .threshold_biomarker import _sens_spec, best_threshold_by_balanced_auc


# Audit [8] — below this many independent ratings (rating clusters), the asymptotic-normal AUC
# variance (Hanley–McNeil) and the Gaussian power approximation are only roughly valid, and the
# clustered-bootstrap CI rests on few resamples. We do NOT change any computed value at small n;
# we attach a `small_sample` advisory flag so the UI can tag the readout "small-sample, approximate".
# 10 is a conventional floor for trusting asymptotic AUC inference; it is advisory, not a gate.
SMALL_SAMPLE_CLUSTER_FLOOR = 10

# Audit [3]-floor: minimum number of VALID (class-non-degenerate) bootstrap replicates required to
# report an AUC confidence interval at all. Raised from the original 20 to 100 — below 100 surviving
# replicates the percentile/BCa tails are too noisy to trust, so the CI is SUPPRESSED (auc_lo/hi=None)
# rather than reported on a handful of resamples. The existing "[3]-display" tag already labels a CI
# built on <100 replicates as "unstable"; this makes the suppression threshold match that warning.
BOOT_CI_VALID_FLOOR = 100

# F4 (2026-09-02): moving-block bootstrap calibration guards. A block bootstrap is only calibrated
# when a replicate contains enough blocks to represent the resampling distribution; the old K//3 cap
# allowed as few as 4. Simulated coverage of the 95% AUC interval on this study's real structure was
# 0.850 at the auto-chosen L=12 (K=48) versus 0.945 at L=1, i.e. the interval was materially too
# narrow. MIN_BOOT_BLOCKS is the floor on blocks per replicate; below SMALL_K_BLOCK_BOOT clusters we
# use L=1 outright, because at those counts the variance mis-calibration costs more than the
# under-represented serial dependence.
MIN_BOOT_BLOCKS = 10
SMALL_K_BLOCK_BOOT = 60


# --- Channel-name formatting -----------------------------------------------------------------
_WORD2DIGIT = {"ZERO": "0", "ONE": "1", "TWO": "2", "THREE": "3", "FOUR": "4",
               "FIVE": "5", "SIX": "6", "SEVEN": "7", "EIGHT": "8", "NINE": "9"}

# Brain-region labels per channel. Real recordings should pass regions from the electrode
# metadata (Target/CustomName); these demo defaults are plausible chronic-pain DBS targets so
# the formatted label is visible in the demo.
_DEMO_REGIONS = {
    "ZERO_TWO_LEFT": "Sensory Thalamus (VPL)",
    "ZERO_TWO_RIGHT": "Ant. Cingulate (ACC)",
}


def format_channel(name, region=None):
    """Turn a raw Percept channel name (e.g. 'ZERO_TWO_LEFT') into a clean bipolar-pair label.

    Uses contact NUMBERS (not words), marks polarity for the bipolar sensing pair (lower contact
    cathode '−', higher contact anode '+'), the hemisphere, and the brain region.
    Returns {raw, label, short, hemisphere, contacts, region}. `region` arg (from electrode
    metadata) wins over the demo map.
    """
    raw = str(name)
    up = raw.upper()
    hemi = "L" if "LEFT" in up else ("R" if "RIGHT" in up else "")
    hemi_full = "Left" if hemi == "L" else ("Right" if hemi == "R" else "")

    toks = [t for t in up.replace("-", "_").split("_") if t in _WORD2DIGIT or t.isdigit()]
    digits = [(_WORD2DIGIT[t] if t in _WORD2DIGIT else t) for t in toks]
    if len(digits) >= 2:
        contacts = f"{digits[0]}⁻{digits[1]}⁺"   # e.g. 0⁻2⁺  (cathode/anode, no separator)
    elif len(digits) == 1:
        contacts = digits[0]
    else:
        contacts = raw

    # region=None -> fall back to the demo map (back-compat for direct callers / demo data).
    # region="" (explicit) -> NO region: show the numeric label only, never a static/guessed region.
    # region=<str> (from device metadata) -> use it.
    if region is None:
        reg = _DEMO_REGIONS.get(up) or _DEMO_REGIONS.get(raw) or ""
    else:
        reg = region or ""
    short = (f"{hemi} {contacts}").strip()
    label = f"{short} · {reg}" if reg else short
    return {"raw": raw, "label": label, "short": short, "hemisphere": hemi_full,
            "contacts": contacts, "region": reg}


def sensing_center_hz(therapy_hemi):
    """Pull the BrainSense sensing-band CENTER FREQUENCY (Hz) from one hemisphere's Therapy
    snapshot. Medtronic stores it at SensingSetup.FrequencyInHertz; firmware/processing drift puts
    the SensingSetup at slightly different depths, so probe the known key paths and return the
    first finite positive frequency found (rounded to 0.01 Hz), else None. Defensive — any
    malformed/absent snapshot returns None rather than raising.
    """
    if not isinstance(therapy_hemi, dict):
        return None
    setups = []
    # Streaming Power-Domain (BrainSenseLfp) TherapySnapshot puts FrequencyInHertz DIRECTLY on the
    # hemisphere dict — so the hemisphere dict itself is the first candidate.
    setups.append(therapy_hemi)
    # Chronic / other firmware paths nest it inside a SensingSetup subdict.
    ss = therapy_hemi.get("SensingSetup")
    if isinstance(ss, dict):
        setups.append(ss)
    sensing = therapy_hemi.get("sensing")
    if isinstance(sensing, dict) and isinstance(sensing.get("SensingSetup"), dict):
        setups.append(sensing["SensingSetup"])
    rc = therapy_hemi.get("RecordingConfiguration")
    if isinstance(rc, dict):
        cfg = rc.get("Config")
        if isinstance(cfg, dict) and isinstance(cfg.get("SensingSetup"), dict):
            setups.append(cfg["SensingSetup"])
    for ss in setups:
        for key in ("FrequencyInHertz", "Frequency", "CenterFrequency", "CenterFrequencyInHertz"):
            v = ss.get(key)
            try:
                fv = float(v)
                if np.isfinite(fv) and fv > 0:
                    return round(fv, 2)
            except (TypeError, ValueError):
                continue
    return None


def power_center_freqs(powerdomain_list):
    """Map each power CONTACT (e.g. 'ZERO_THREE_LEFT') to its sensing-band center frequency (Hz),
    read from each recording's Descriptor.Therapy snapshot. A recording's Therapy carries 'Left'
    and 'Right' hemisphere keys; each power channel's hemisphere token (LEFT/RIGHT in the contact
    name) is matched to that hemisphere's SensingSetup.FrequencyInHertz. Last writer wins per
    contact (snapshots within one session share the sensing config).
    """
    freqs = {}
    for r in powerdomain_list or []:
        if not isinstance(r, dict):
            continue
        desc = r.get("Descriptor")
        therapy = desc.get("Therapy") if isinstance(desc, dict) else None
        if not isinstance(therapy, dict):
            continue
        hemi_hz = {"LEFT": sensing_center_hz(therapy.get("Left")),
                   "RIGHT": sensing_center_hz(therapy.get("Right"))}
        for nm in r.get("ChannelNames", []) or []:
            s = str(nm)
            if "POWER" not in s.upper():
                continue
            contact = s.rsplit(" ", 1)[0] if " " in s else s
            cu = contact.upper()
            hz = hemi_hz["LEFT"] if "LEFT" in cu else (hemi_hz["RIGHT"] if "RIGHT" in cu else None)
            if hz is not None:
                freqs[contact] = hz
    return freqs


def chronic_center_freqs(groups):
    """Map each hemisphere to its chronic-trend (BrainSense Timeline / LFPTrendLogs) sensing-band
    center frequency (Hz). Unlike the streaming Power-Domain frequency (on the per-recording Therapy
    snapshot, read by power_center_freqs), the chronic trend's sensing frequency lives at the GROUP
    level: Groups.Final[].ProgramSettings.SensingChannel[].SensingSetup.FrequencyInHertz, tagged by
    HemisphereLocation (e.g. 'HemisphereLocationDef.Left'). Returns {'LeftHemisphere': hz,
    'RightHemisphere': hz} (keys matching the chronic recording's ChannelNames tokens), omitting a
    hemisphere whose frequency is absent. The ACTIVE group wins; otherwise the last group with a
    finite frequency for that hemisphere. Defensive: any malformed structure yields {}.

    `groups` is the raw JSON's "Groups" dict (has "Final"/"Initial"), or directly a list of group
    dicts. The decoder does not currently attach this to the stored chronic recording, so this is
    called with the raw session JSON when available.
    """
    if isinstance(groups, dict):
        group_list = groups.get("Final") or groups.get("Initial") or []
    elif isinstance(groups, list):
        group_list = groups
    else:
        return {}
    freqs = {}
    # Prefer the active group: collect (is_active, hz) per hemisphere and let active, then later,
    # writers win.
    for grp in group_list:
        if not isinstance(grp, dict):
            continue
        active = bool(grp.get("ActiveGroup"))
        ps = grp.get("ProgramSettings")
        if not isinstance(ps, dict):
            continue
        for ch in ps.get("SensingChannel", []) or []:
            if not isinstance(ch, dict):
                continue
            hemi_raw = str(ch.get("HemisphereLocation") or ch.get("Hemisphere") or "")
            if "Left" in hemi_raw:
                hemi = "LeftHemisphere"
            elif "Right" in hemi_raw:
                hemi = "RightHemisphere"
            else:
                continue
            hz = sensing_center_hz(ch)
            if hz is None:
                continue
            prev = freqs.get(hemi)
            # active group always wins; otherwise take it if none yet or prior was non-active
            if prev is None or active:
                freqs[hemi] = hz
    return freqs


def _f(x):
    """Float or None (JSON-safe, NaN -> None)."""
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if not np.isfinite(x) else x


def _otsu_threshold(values, nbins=256):
    """Between-class-variance Otsu threshold on a 1-D value array.

    Canonical formulation, verified to match skimage.filters.threshold_otsu bit-for-bit on the
    histogram grid. The previous implementation had two defects that biased the cut high:
      (1) it weighted the background by bins [0..i-1] but REPORTED centers[i] (the first foreground
          bin) — an off-by-one that shifted the threshold up by ~0.5–1 bin width; and
      (2) it used only 128 bins, coarsening the grid further.
    Here the candidate split sits BETWEEN bin i and bin i+1: the background class is bins [0..i]
    (weight w1, mean m1) and the foreground class is bins [i+1..] (weight w2, mean m2), and the
    returned threshold is centers[argmax(w1*w2*(m1-m2)^2)] — the standard convention where
    `value > threshold` is the high (foreground) class. nbins defaults to 256 (skimage's default)
    for a finer grid.
    """
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if values.size == 0:
        return None
    counts, edges = np.histogram(values, bins=nbins)
    centers = (edges[:-1] + edges[1:]) / 2.0
    counts = counts.astype(float)
    if counts.sum() == 0:
        return float(np.median(values))
    # Cumulative class weights/means from the left (background) and right (foreground).
    w1 = np.cumsum(counts)                                  # weight of bins [0..i]
    w2 = np.cumsum(counts[::-1])[::-1]                      # weight of bins [i..]
    # Class means (guard the empty-class divisions; those bins are excluded from bcv below anyway).
    with np.errstate(invalid="ignore", divide="ignore"):
        m1 = np.cumsum(counts * centers) / w1
        m2 = (np.cumsum((counts * centers)[::-1]) / w2[::-1])[::-1]
    # Between-class variance for the split between bin i and bin i+1 (i = 0..nbins-2).
    bcv = w1[:-1] * w2[1:] * (m1[:-1] - m2[1:]) ** 2
    bcv = np.where(np.isfinite(bcv), bcv, -1.0)
    if not np.any(bcv > 0):
        return float(np.median(values))
    return float(centers[int(np.argmax(bcv))])


def _all_data_window(df, thresholds):
    """Single all-data 'window' (sliding OFF): threshold by AUC on the class-balanced full series,
    then sens/spec/acc/AUC/R on the full series. Same dict shape as a sliding window (+ all_data:
    True) so the frontend renders it as one point. In-sample, so optimistic vs sliding windows."""
    from sklearn import metrics
    from scipy.stats import pearsonr

    data = df.dropna(subset=["pain_level"])
    if len(data) == 0 or data["pain_level"].nunique() < 2:
        return []
    min_count = int(data["pain_level"].value_counts().min())
    btr = pd.concat([data[data["pain_level"] == c].sample(min_count, random_state=42)
                     for c in data["pain_level"].unique()])
    # Threshold by balanced AUC, vectorized (see best_threshold_by_balanced_auc); identical selection.
    best_thr, best_auc = best_threshold_by_balanced_auc(
        btr["pain_level"].astype(int).values, btr["LFP_smoothed"].values, thresholds)
    true = data["pain_level"].astype(int).values
    score = data["LFP_smoothed"].astype(float).values
    pred = (score >= best_thr).astype(int)
    sens, spec = _sens_spec(true, pred)
    acc = metrics.accuracy_score(true, pred)
    auc = r = np.nan
    if len(np.unique(true)) > 1:
        try:
            auc = metrics.roc_auc_score(true, score)
            auc = max(auc, 1 - auc)
        except Exception:
            pass
        if np.std(score) > 0:
            try:
                r = pearsonr(score, true.astype(float))[0]
            except Exception:
                pass
    return [{
        "test_start": df["timestamp"].min().isoformat(),
        "threshold": _f(best_thr), "sens": _f(sens), "spec": _f(spec),
        "acc": _f(acc), "auc": _f(auc), "r": _f(r), "all_data": True,
    }]


def sliding_window_analytics(cv_df, *, thresholds=None, train_days=4, gap_days=2,
                             test_days=4, step_days=None, sliding=True,
                             max_test_days=None):
    """Per-sliding-window metrics over time (mirrors threshold_biomarker.ipynb cells 12 & 14).

    For each window: pick the LFP threshold maximizing train AUC, then on the held-out test fold
    report sensitivity, specificity, accuracy, AUC (roc_auc on the continuous LFP_smoothed), and a
    point-biserial Pearson R (LFP_smoothed vs pain_level). Returns a dict
    `{windows: [...], summary: {n_total, n_with_auc, n_skipped_test_one_class, n_skipped_no_data,
                                test_days, test_days_expanded}}`.

    When `sliding=False`, returns a single all-data window in the same shape via `_all_data_window`.

    Test-fold robustness: when the user-supplied `test_days` window contains only one pain class
    (common with tertile binarization — the middle band is excluded, so most short windows are
    homogeneous), the window is EXPANDED forward by `step_days` until both classes appear or the
    expansion reaches `max_test_days` (default 3 * test_days, capped at 14d). Windows that still
    have only one class after expansion are skipped (no half-NaN row) and counted in the summary.

    `train_days` is driven by the user's window-months selection.
    """
    from sklearn import metrics
    from scipy.stats import pearsonr

    if thresholds is None:
        thresholds = np.arange(60, 200, 1)

    df = cv_df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp", "pain_level"]).sort_values("timestamp").reset_index(drop=True)
    if len(df) == 0:
        return {"windows": [], "summary": {"n_total": 0, "n_with_auc": 0,
                                            "n_skipped_test_one_class": 0,
                                            "n_skipped_no_data": 0,
                                            "test_days": int(test_days),
                                            "max_test_days": None}}

    if not sliding:
        w = _all_data_window(df, thresholds)
        with_auc = sum(1 for r in w if r.get("auc") is not None)
        return {"windows": w, "summary": {"n_total": len(w), "n_with_auc": with_auc,
                                          "n_skipped_test_one_class": 0,
                                          "n_skipped_no_data": 0,
                                          "test_days": int(test_days),
                                          "max_test_days": None}}

    # Step between windows. Default scales with the training window (step ~ train/14) so a large
    # multi-month window doesn't produce hundreds of near-identical windows (which is slow and
    # over-plots); small windows keep step=1 (unchanged behavior). This only changes how densely
    # the performance curve is SAMPLED in time -- each window's metric is still computed on full data.
    if step_days is None:
        step_days = max(1, int(round(train_days / 14.0)))
    # Test-fold expansion cap. Default to 3x test_days, but never exceed 14 days (or the training
    # window, whichever is smaller — expanding past `train_days` makes the test fold the dominant
    # signal, which defeats the point of a held-out test).
    if max_test_days is None:
        max_test_days = min(14, max(int(test_days) * 3, int(test_days) + 2))
    max_test_days = max(int(test_days), int(max_test_days))

    series_start = df["timestamp"].min().normalize()
    series_end = df["timestamp"].max()

    windows = []
    n_skipped_one_class = 0
    n_skipped_no_data = 0
    t = series_start + pd.Timedelta(days=train_days + gap_days)
    while t < series_end:
        test_start = t
        # Try the requested test window first; if it has only one pain class, EXPAND forward by
        # step_days until both classes appear or we hit max_test_days. Common with tertile labels:
        # consecutive days within one tertile collapse a short test window to a single class.
        test = df.iloc[0:0]
        eff_test_days = int(test_days)
        for cur in range(int(test_days), int(max_test_days) + 1, max(1, int(step_days))):
            test_end = test_start + pd.Timedelta(days=cur)
            test = df[(df["timestamp"] >= test_start) & (df["timestamp"] < test_end)].dropna(subset=["pain_level"])
            eff_test_days = cur
            if len(test) > 0 and test["pain_level"].nunique() >= 2:
                break
        gap_start = test_start - pd.Timedelta(days=gap_days)
        train_start = gap_start - pd.Timedelta(days=train_days)
        t += pd.Timedelta(days=step_days)

        train = df[(df["timestamp"] >= train_start) & (df["timestamp"] < gap_start)].dropna(subset=["pain_level"])
        # Categorize skips for the panel caption:
        #   NO_DATA   = either fold is empty, OR train has only one pain class (no usable
        #               threshold can be picked).
        #   ONE_CLASS = both folds non-empty and train has both classes, but test never
        #               reached both classes within the expansion cap.
        train_unusable = (len(train) == 0) or (train["pain_level"].nunique() < 2)
        test_unusable = (len(test) == 0) or (test["pain_level"].nunique() < 2)
        if train_unusable or len(test) == 0:
            n_skipped_no_data += 1
            continue
        if test_unusable:
            n_skipped_one_class += 1
            continue

        # Class-balance the train fold, then pick threshold by train AUC (cell 14).
        min_count = int(train["pain_level"].value_counts().min())
        btr = pd.concat([train[train["pain_level"] == c].sample(min_count, random_state=42)
                         for c in train["pain_level"].unique()])
        # Threshold by train AUC (cell 14), vectorized: roc_auc_score on a BINARY prediction equals
        # (sens+spec)/2, so the whole grid is one searchsorted pass instead of 140 sklearn calls.
        # Selection (first-wins on strict-greater, single-class thresholds skipped) preserved exactly.
        best_thr, best_auc = best_threshold_by_balanced_auc(
            btr["pain_level"].astype(int).values, btr["LFP_smoothed"].values, thresholds)

        true = test["pain_level"].astype(int).values
        score = test["LFP_smoothed"].astype(float).values
        pred = (score >= best_thr).astype(int)
        sens, spec = _sens_spec(true, pred)
        acc = metrics.accuracy_score(true, pred)

        # Both classes are guaranteed here (loop above), so AUC/R are always defined.
        try:
            auc = metrics.roc_auc_score(true, score)
            auc = max(auc, 1 - auc)
        except Exception:
            auc = np.nan
        try:
            r = pearsonr(score, true.astype(float))[0] if np.std(score) > 0 else np.nan
        except Exception:
            r = np.nan

        # Per-window ROC curve (FPR/TPR on the held-out TEST fold) so the frontend can overlay one
        # ROC per window when a sliding window is active. Orient the score so the LFP-high =
        # pain-high direction gives AUC >= 0.5 (matches roc_analysis and the notebook's
        # max(auc, 1-auc)); downsample to <= ROC_MAX_PTS monotone vertices (endpoints kept) so the
        # payload stays small. Guarded: a degenerate test fold leaves roc absent (auc still set).
        roc = None
        try:
            raw_auc = metrics.roc_auc_score(true, score)
            use_score = score if raw_auc >= 0.5 else -score
            fpr, tpr, _ = metrics.roc_curve(true, use_score)
            ROC_MAX_PTS = 60
            if len(fpr) > ROC_MAX_PTS:
                idx = np.unique(np.linspace(0, len(fpr) - 1, ROC_MAX_PTS).astype(int))
                fpr, tpr = fpr[idx], tpr[idx]
            roc = {"fpr": [float(x) for x in fpr], "tpr": [float(x) for x in tpr]}
        except Exception:
            roc = None

        windows.append({
            "test_start": test_start.isoformat(),
            "test_days_used": int(eff_test_days),
            "threshold": _f(best_thr), "sens": _f(sens), "spec": _f(spec),
            "acc": _f(acc), "auc": _f(auc), "r": _f(r),
            "roc": roc,
        })
    n_with_auc = sum(1 for w in windows if w.get("auc") is not None)
    summary = {"n_total": len(windows) + n_skipped_one_class + n_skipped_no_data,
               "n_with_auc": n_with_auc,
               "n_skipped_test_one_class": n_skipped_one_class,
               "n_skipped_no_data": n_skipped_no_data,
               "test_days": int(test_days),
               "max_test_days": int(max_test_days)}
    return {"windows": windows, "summary": summary}


def roc_analysis(cv_df, max_points=400):
    """Overall ROC curve (FPR/TPR) + AUC for LFP_smoothed vs pain_level.

    The AUC is computed on the FULL data; only the plotted curve is thinned. roc_curve emits one
    vertex per unique score, which for the ~60k-sample merged series is tens of thousands of points —
    far more than a browser needs and a bloated payload. Downsample to `max_points` evenly-spaced,
    monotonicity-preserving vertices (endpoints kept) for display.
    """
    from sklearn import metrics

    df = cv_df.dropna(subset=["pain_level", "LFP_smoothed"])
    y = df["pain_level"].astype(int).values
    score = df["LFP_smoothed"].astype(float).values
    if len(np.unique(y)) < 2:
        return {"fpr": [], "tpr": [], "auc": None}

    raw_auc = metrics.roc_auc_score(y, score)
    # Orient so the LFP-high = pain-high direction gives AUC >= 0.5 (matches the notebook's max(auc,1-auc)).
    flip = raw_auc < 0.5
    use_score = -score if flip else score
    fpr, tpr, thr = metrics.roc_curve(y, use_score)
    # Map decision thresholds back to the device-unit band-power scale. With the high-pain = high-power
    # convention the rule is `power >= thr_device`; when the AUC had to be flipped (so the score was
    # negated) the device threshold is -thr. Aligned with fpr/tpr index-for-index.
    thr_device_full = (-thr if flip else thr).astype(float)

    # Default (cost-symmetric) operating point = Youden's J statistic: the threshold maximizing
    # (TPR - FPR), i.e. the ROC point furthest above the chance diagonal. The frontend exposes a cost
    # slider that re-solves the operating point live; this default is what shows when the slider sits
    # at 1:1 (false-positive cost == false-negative cost). Skip the sentinel first vertex (thr=+inf).
    op = None
    if len(thr) > 1:
        j = tpr - fpr
        j_valid = j.copy()
        j_valid[~np.isfinite(thr)] = -np.inf
        k = int(np.argmax(j_valid))
        op = {
            "fpr": float(fpr[k]), "tpr": float(tpr[k]),
            "threshold": float(thr_device_full[k]),
            "sensitivity": float(tpr[k]),
            "specificity": float(1.0 - fpr[k]),
            "youden_j": float(j_valid[k]),
            "direction": "ge",
        }

    # Prevalence on the SAME data the curve was built on (the pain-high rate). Used by the frontend
    # cost-sensitive picker: the optimal ROC tangent slope under (FP, FN) cost (cFP, cFN) and
    # prevalence p is m = (cFP/cFN) * ((1-p)/p), and the optimal point maximizes TPR - m * FPR.
    n_pos = int(np.sum(y == 1))
    n_neg = int(np.sum(y == 0))
    prevalence = float(n_pos) / float(n_pos + n_neg) if (n_pos + n_neg) > 0 else None

    # Downsample fpr/tpr/thr TOGETHER so the frontend picker sees a parallel, oriented set of vertices.
    fpr_out, tpr_out, thr_out = fpr, tpr, thr_device_full
    if max_points and len(fpr_out) > max_points:
        idx = np.unique(np.linspace(0, len(fpr_out) - 1, int(max_points)).astype(int))
        fpr_out, tpr_out, thr_out = fpr_out[idx], tpr_out[idx], thr_out[idx]
    return {"fpr": [float(x) for x in fpr_out], "tpr": [float(x) for x in tpr_out],
            # thresholds parallel to fpr/tpr; +inf sentinel at the (0,0) vertex stays as null in JSON.
            "thr": [None if not np.isfinite(t) else float(t) for t in thr_out],
            "auc": float(max(raw_auc, 1 - raw_auc)), "n_points_full": int(len(df)),
            "prevalence": prevalence, "n_pos": n_pos, "n_neg": n_neg,
            "operating_point": op}


def lfp_distribution(cv_df, bins=40):
    """LFP histogram + Otsu threshold (threshold_biomarker.ipynb cell 9).

    The raw merged power-domain series (Chronic + per-session band power, un-normalized) can span an
    enormous device-unit range with a few extreme outliers, which collapses a naive histogram into a
    single bar. Outliers are EXCLUDED (MAD rejection, >=3 MADs from the median) from BOTH the Otsu
    threshold AND the displayed histogram, so the threshold and the bars describe the same
    outlier-free distribution. n_clipped reports how many outlier samples were excluded; n_total is
    the pre-exclusion count."""
    lfp = cv_df["LFP_smoothed"].dropna().astype(float).values
    if lfp.size == 0:
        return {"bin_edges": [], "counts": [], "otsu": None, "n_clipped": 0, "n_total": 0}
    # MAD outlier rejection (>=3 MADs from the median). Falls back to the full series when MAD is
    # undefined (all-equal or < 3 samples). The SAME outlier-free set drives both Otsu and the bars.
    med = np.median(lfp)
    mad = np.median(np.abs(lfp - med))
    keep = np.abs(lfp - med) <= 3.0 * mad if (mad > 0 and lfp.size >= 3) else np.ones(lfp.size, dtype=bool)
    lfp_robust = lfp[keep]
    if lfp_robust.size < 3:
        lfp_robust = lfp
        keep = np.ones(lfp.size, dtype=bool)
    otsu = _otsu_threshold(lfp_robust)
    n_clipped = int(np.count_nonzero(~keep))     # outliers excluded from BOTH threshold and plot
    # Bin over the outlier-free range. A residual 1st-99th-pct trim keeps a long inlier tail from
    # squashing the bulk, but every outlier is already gone from lfp_robust.
    lo, hi = np.percentile(lfp_robust, [1, 99])
    if not (np.isfinite(lo) and np.isfinite(hi)) or hi <= lo:
        lo, hi = float(np.min(lfp_robust)), float(np.max(lfp_robust))
    counts, edges = np.histogram(lfp_robust, bins=bins, range=(float(lo), float(hi)))
    return {"bin_edges": [float(x) for x in edges], "counts": [int(x) for x in counts],
            "otsu": (None if otsu is None else float(otsu)), "n_clipped": n_clipped,
            "n_total": int(lfp.size)}


def power_pain_scatter(cv_df, label_metric, *, max_points=2000):
    """Continuous power-biomarker vs continuous pain score, with Pearson r and p.

    The ROC/Otsu panels treat pain as a BINARY label; this panel keeps pain CONTINUOUS and shows the
    raw association — one point per chronic sample, x = smoothed band power (LFP_smoothed), y = the
    selected pain score (the `label_metric` column carried onto cv_df). Returns the paired points plus
    Pearson r and its two-sided p so the card can show the correlation of THIS contact's power against
    ONLY the selected pain metric, updating with the toggle.

    Outliers in power are excluded by the same MAD rule used for the Otsu histogram, so the scatter
    and the distribution describe the same inlier set. p is the ordinary Pearson p (not corrected for
    the band search — this is a descriptive per-contact panel, and the headline inference stays the
    block-permutation perm_p elsewhere)."""
    out = {"x": [], "y": [], "r": None, "p": None, "n": 0, "x_label": "band power",
           "y_label": str(label_metric), "n_clipped": 0}
    if cv_df is None or len(cv_df) == 0 or "LFP_smoothed" not in cv_df.columns:
        return out
    if label_metric not in cv_df.columns:
        return out
    sub = cv_df[["LFP_smoothed", label_metric]].dropna()
    if len(sub) < 3:
        return out
    power = sub["LFP_smoothed"].astype(float).values
    pain = sub[label_metric].astype(float).values
    # MAD outlier rejection on power (consistent with lfp_distribution).
    med = np.median(power)
    mad = np.median(np.abs(power - med))
    keep = np.abs(power - med) <= 3.0 * mad if (mad > 0 and power.size >= 3) else np.ones(power.size, dtype=bool)
    n_clipped = int(np.count_nonzero(~keep))
    if keep.sum() >= 3:
        power, pain = power[keep], pain[keep]
    else:
        n_clipped = 0
    r = p = None
    if power.size >= 3 and np.std(power) > 0 and np.std(pain) > 0:
        try:
            from scipy.stats import pearsonr
            rr, pp = pearsonr(power, pain)
            r, p = float(rr), float(pp)
        except Exception:
            r = p = None
    # Downsample points for the payload while keeping r/p over the full set.
    n = int(power.size)
    if n > max_points:
        rng = np.random.default_rng(0)
        idx = np.sort(rng.choice(n, size=max_points, replace=False))
        px, py = power[idx], pain[idx]
    else:
        px, py = power, pain
    out.update({"x": [float(v) for v in px], "y": [float(v) for v in py],
                "r": r, "p": p, "n": n, "n_clipped": n_clipped})
    return out


# ---------------------------------------------------------------------------------------------
# Outlier exclusion (PI request, 2026-08-30)
# ---------------------------------------------------------------------------------------------
# ONE outlier rule for the whole biomarker plate, defined in stats_utils and imported here.
#
# PI decision, 2026-08-30: 5 MAD everywhere, applied uniformly to the FEATURE, the LABEL and the
# chronic LFP-power column, with the three previously-separate filters consolidated into a single
# implementation. Before this there were three copies with two thresholds (analytics 5 MAD dropping,
# streaming_psd._mad_keep 3 MAD keeping, adapter.mad_outlier_mask 3 MAD keeping) and inverted
# polarity between them. Change `stats_utils.MAD_N_DEFAULT` to move the whole plate at once — that
# single point of control is the reason for the consolidation.
#
# Consequence to be aware of when comparing against older figures: 5 MAD is LOOSER than the 3 MAD
# the correlation spectrum and chronic path used before, so those reject fewer samples than they did.
from .stats_utils import MAD_N_DEFAULT as OUTLIER_N_MAD  # noqa: E402  (5.0)
from .stats_utils import mad_outlier_flags  # noqa: E402  (True == outlier; see stats_utils)

# Scale for the pain LABEL. Pain scores are bounded ordinal scales, not multiplicative quantities,
# so the rule is applied to them directly rather than in log space.
OUTLIER_LABEL_SCALE = "raw"

# The exclusion also covers extreme pain RATINGS, not just extreme features (PI, 2026-08-30) —
# uniform treatment of feature and label, matching what `streaming_psd._mad_keep` has always done.
OUTLIER_INCLUDE_LABEL = True

# SCALE ON WHICH THE RULE IS APPLIED. This is a real statistical decision, not a detail.
# The LSB band-power feature is multiplicative and heavy-tailed (roughly 0.1 to 15000), so a
# symmetric +/- MAD window on the RAW scale is far tighter above the median than below it in
# proportional terms: it deletes the upper tail almost exclusively, which biases every downstream
# statistic in a fixed direction. On the log scale the distribution is roughly symmetric, so the
# rule removes genuine two-sided outliers. The exclusion is DETECTED on the log scale and then
# applied to both the raw display feature and the log fit feature, so exactly one set of samples
# is dropped everywhere. Set to "raw" only to reproduce a literal raw-scale reading.
OUTLIER_SCALE = "log"


def apply_outlier_exclusion(arrays, detect_on, n_mad=OUTLIER_N_MAD, scale=OUTLIER_SCALE,
                            extra_mask=None):
    """Blank one shared set of outliers out of EVERY array in ``arrays``.

    The point of this helper is that a single exclusion set must reach every statistic. Excluded
    samples are set to NaN rather than removed by index, so any downstream computation already
    masking on ``isfinite`` — the correlation, the cross-validated AUC and its cluster-robust
    logit p, the effect size — drops the same samples without each needing its own filter and
    without disturbing row alignment against the label and cluster vectors.

    ``detect_on`` is the array the rule is evaluated on (the fit-scale feature); ``arrays`` is the
    list of arrays to blank, which should include ``detect_on`` itself.

    ``extra_mask`` is OR-ed into the feature-derived mask. It carries the LABEL-side exclusion: the
    shared label vector must not itself be mutated (that would corrupt the binarization, the rating
    groups and every other channel's view of the same ratings), so label outliers are dropped by
    blanking the FEATURE at those rows instead. The effect on every statistic is identical, and row
    alignment is preserved.

    Returns ``(blanked_arrays, info)``; ``info`` gains ``n_removed_feature`` / ``n_removed_label_only``
    so the report can separate the two sources rather than presenting one opaque total.
    """
    mask, info = mad_outlier_flags(detect_on, n_mad=n_mad, scale=scale)
    info["n_removed_feature"] = int(mask.sum())
    info["n_removed_label_only"] = 0
    if extra_mask is not None:
        em = np.asarray(extra_mask, dtype=bool)
        if em.shape == mask.shape:
            info["n_removed_label_only"] = int((em & ~mask).sum())
            mask = mask | em
            info["n_removed"] = int(mask.sum())
    out = []
    for a in arrays:
        b = np.asarray(a, dtype=float).copy()
        if b.shape == mask.shape:
            b[mask] = np.nan
        out.append(b)
    return out, info


def cluster_scatter(cv_df, kmeans_features=("left_leg_vas", "mpq_sum")):
    """KMeans pain-level clusters over the ACTUAL clustering feature(s) (cell 10), colored by the
    derived pain_level. Generic in the number of features so it renders for ANY selected metric:
      * 2 features (e.g. the MPQ+VAS composite -> [left_leg_vas, mpq_sum]) -> a 2-D scatter;
      * 1 feature (e.g. nrs / vas)                                         -> a 1-D distribution.
    cv_df is per-LFP-sample (the daily PRO values repeat across thousands of 10-min samples), so we
    DE-DUPLICATE to the unique (feature(s), pain_level) observations — both correct (one point per
    PRO reading, not per LFP sample) and far lighter than emitting ~280k overplotted points."""
    feats = [f for f in kmeans_features if f in cv_df.columns]
    if not feats:
        return None
    subset = feats + (["pain_level"] if "pain_level" in cv_df.columns else [])
    d = cv_df.dropna(subset=subset).drop_duplicates(subset=subset)
    if len(d) == 0:
        return None
    out = {"features": feats, "x": [float(v) for v in d[feats[0]]], "x_label": feats[0],
           "pain_level": ([None if pd.isna(x) else int(x) for x in d["pain_level"]]
                          if "pain_level" in d.columns else [])}
    if len(feats) >= 2:
        out["y"] = [float(v) for v in d[feats[1]]]
        out["y_label"] = feats[1]
    return out


def pain_binarization(cv_df, label_metric, kmeans_features=("left_leg_vas", "mpq_sum"),
                      pro_df=None, strategy="kmeans", low_pct=None, high_pct=None):
    """Demonstrate how the SELECTED pain score is split into the binary pain_level the detector uses.

    For each clustering feature: the raw value distribution (the daily PRO observations when pro_df is
    supplied — one per reading, not per LFP sample), the EMPIRICAL decision boundary derived from the
    actual labels in cv_df, the percentile that boundary lands at, and 30th/70th-percentile reference
    lines. The binarizer is the notebook's 2-cluster KMeans (kmeans_pain_level), so for a single
    feature the boundary is the cluster split (NOT a fixed percentile) — we report where it lands."""
    if "pain_level" not in cv_df.columns:
        return None
    feats = [f for f in kmeans_features if f in cv_df.columns]
    if not feats:
        return None
    items = []
    for f in feats:
        d = cv_df[[f, "pain_level"]].dropna()
        if d.empty:
            continue
        lo = d.loc[d["pain_level"] == 0, f].to_numpy(dtype=float)
        hi = d.loc[d["pain_level"] == 1, f].to_numpy(dtype=float)
        # Orient so `hi` is the higher-value (higher-pain) cluster, regardless of KMeans label order.
        if lo.size and hi.size and np.nanmean(lo) > np.nanmean(hi):
            lo, hi = hi, lo
        boundary = None
        if lo.size and hi.size:
            a, b = float(np.max(lo)), float(np.min(hi))
            boundary = (a + b) / 2.0 if a <= b else (float(np.median(lo)) + float(np.median(hi))) / 2.0
        # Distribution: prefer the PRO-level daily values (one per reading); else the cv values.
        if pro_df is not None and f in pro_df.columns:
            vals = pd.to_numeric(pro_df[f], errors="coerce").dropna().to_numpy(dtype=float)
        else:
            vals = d[f].to_numpy(dtype=float)
        if vals.size == 0:
            continue
        pct = float(np.mean(vals < boundary) * 100.0) if boundary is not None else None
        n_low = int(np.count_nonzero(vals < boundary)) if boundary is not None else None
        n_high = int(np.count_nonzero(vals >= boundary)) if boundary is not None else None
        item = {
            "name": f,
            "values": [float(v) for v in vals],
            "boundary": (None if boundary is None else float(boundary)),
            "boundary_percentile": pct,
            "p30": float(np.percentile(vals, 30)),
            "p70": float(np.percentile(vals, 70)),
            "n_low": n_low, "n_high": n_high, "n_obs": int(vals.size),
        }
        # For the tertile/percentile labeler, surface the two daily-distribution cuts so the panel
        # can draw both lines + the excluded middle band (the cut is on the DAILY values).
        if strategy in ("tertile", "percentile") and low_pct is not None and high_pct is not None:
            item["p_low"] = float(np.percentile(vals, float(low_pct)))
            item["p_high"] = float(np.percentile(vals, float(high_pct)))
        items.append(item)
    if not items:
        return None
    out = {"strategy": strategy, "metric": label_metric, "features": items}
    if strategy in ("tertile", "percentile") and low_pct is not None and high_pct is not None:
        # The middle band (between the low and high cuts) is EXCLUDED from training — surface
        # the cut percentiles and how many days were dropped so the abstention is explicit.
        out["low_pct"] = float(low_pct)
        out["high_pct"] = float(high_pct)
        if "pain_level" in cv_df.columns:
            pl = cv_df["pain_level"].to_numpy(dtype=float)
            out["n_excluded_middle"] = int(np.isnan(pl).sum())
            out["n_labeled"] = int(np.isfinite(pl).sum())
    return out


def td_sliding_corr_spectrum(td_detail, times, *, window_days=30, step_days=7, min_sessions=3,
                             region_map=None):
    """Sliding R-vs-frequency-over-time heatmap for the time-domain biomarker.

    For every sliding TIME window, computes the Pearson R between each (channel, frequency) PSD
    power and the pain label, across the streaming sessions whose StartTime falls in that window.
    Result is a correlation heatmap of R over (frequency x window-time) per channel.

    FULLY VECTORIZED — no per-window or per-frequency Python loop. A window-membership matrix
    `W` (n_windows x n_sessions, 0/1) reduces every window's mean/variance/covariance to a handful
    of BLAS matmuls (`W @ X`), so the whole heatmap is a few matrix products that run multithreaded
    in BLAS. At this scale (hundreds of sessions x ~100 freqs x a few channels) this is far faster
    than a GPU, whose host<->device transfer/launch overhead would dominate — hence no TensorFlow/
    Metal path (also unavailable: a Linux container cannot reach the macOS Metal GPU).

    Pearson R per window/element uses the single-pass identity
        r = (Sxy - Sx*Sy/n) / sqrt((Sxx - Sx^2/n) * (Syy - Sy^2/n)),
    with all of Sx, Sxx, Sxy, Sy, Syy obtained as `W @ ...`. Windows with < `min_sessions` finite
    sessions, or a constant x or y (zero variance), yield NaN.

    Parameters
    ----------
    td_detail : streaming_psd result dict (needs "psd" (E,C,F), "labels" (E,), "f_set" (F,), "chan_order").
    times : per-session StartTimes (E,) — anything pandas can parse to datetime.
    window_days, step_days : sliding-window length and stride (days).

    Returns {"channels":[{channel, freqs:[F], window_starts:[W ISO], r:[F][W]}], "window_days", "step_days"}.
    """
    psd = np.asarray(td_detail.get("psd"), dtype=float)
    labels = np.asarray(td_detail.get("labels"), dtype=float).ravel()
    f_set = np.asarray(td_detail.get("f_set"), dtype=float).ravel()
    chans = list(td_detail.get("chan_order") or [])
    empty = {"channels": [], "window_days": window_days, "step_days": step_days}
    if psd.ndim != 3 or psd.shape[0] == 0 or labels.size != psd.shape[0]:
        return empty
    E, C, F = psd.shape

    tv = pd.to_datetime(pd.Series(times), errors="coerce").values.astype("datetime64[ns]").astype("float64")
    if tv.size != E:
        return empty
    day_ns = 86400.0e9
    w = float(window_days) * day_ns
    s = max(float(step_days), 1e-9) * day_ns

    X = psd.reshape(E, C * F)                                   # (E, M)
    # A session is usable only if its time, label, and all PSD values are finite.
    finite_sess = np.isfinite(tv) & np.isfinite(labels) & np.isfinite(X).all(axis=1)
    # Session-level MAD outlier rejection on the pain label (>=3 MADs from the median), consistent
    # with the correlation spectrum and the chronic detector — an extreme-label session is dropped
    # from every window rather than distorting the windowed R. (Per-frequency feature MAD is left to
    # the static spectrum; the windowed correlation here is a vectorized diagnostic over many cells.)
    lv = labels[np.isfinite(labels)]
    if lv.size >= 3:
        lmed = np.median(lv)
        lmad = np.median(np.abs(lv - lmed))
        if lmad > 0:
            finite_sess = finite_sess & (np.abs(labels - lmed) <= 3.0 * lmad)
    if finite_sess.sum() < min_sessions:
        return empty
    # Robust time span: some sessions decode to corrupt StartTimes (e.g. ~1677, pandas' min date),
    # which would stretch the grid to centuries and create thousands of empty windows. Earlier code
    # used a 5*MAD clip, but with a legitimately SKEWED distribution (a dense stage-0 block + a
    # sparse chronic tail, as in RCS08) the MAD is tiny and the clip wrongly truncated valid recent
    # sessions — terminating the grid months before the true last recording. Instead, drop only
    # timestamps that are ABSOLUTELY implausible (outside a sane calendar window) and keep every
    # real session, so the grid always extends to the most recent recording. A hard window cap is
    # the backstop against any corrupt time that slips through.
    ft = tv[finite_sess]
    lo_bound = pd.Timestamp("2015-01-01").value          # device era; corrupt ~1677 dates fall below
    hi_bound = (pd.Timestamp.utcnow().tz_localize(None) + pd.Timedelta(days=365)).value
    plausible = (ft >= lo_bound) & (ft <= hi_bound)
    ftk = ft[plausible] if plausible.any() else ft
    tmin, tmax = float(np.min(ftk)), float(np.max(ftk))
    if not (tmax > tmin):
        tmin, tmax = float(np.nanmin(ft)), float(np.nanmax(ft))
    end = max(tmax - w, tmin)
    max_windows = 400
    if s > 0 and (end - tmin) / s > max_windows:
        s = (end - tmin) / max_windows
    starts = np.arange(tmin, end + s, s)                       # (Wn,)
    if starts.size == 0:
        starts = np.array([tmin])

    inwin = (tv[None, :] >= starts[:, None]) & (tv[None, :] < starts[:, None] + w)
    Wm = (inwin & finite_sess[None, :]).astype(float)          # (Wn, E)
    Xf = np.where(np.isfinite(X), X, 0.0)                       # excluded sessions get weight 0
    y = np.where(np.isfinite(labels), labels, 0.0)             # (E,)

    n = Wm.sum(axis=1)                                          # (Wn,)
    with np.errstate(invalid="ignore", divide="ignore"):
        nn = n[:, None]
        Sx = Wm @ Xf; Sxx = Wm @ (Xf * Xf); Sxy = Wm @ (Xf * y[:, None])
        Sy = Wm @ y;  Syy = Wm @ (y * y)
        cov = Sxy - Sx * Sy[:, None] / nn
        vx = Sxx - Sx * Sx / nn
        vy = (Syy - Sy * Sy / n)[:, None]
        r = cov / np.sqrt(vx * vy)                             # (Wn, M)
    r[n < min_sessions, :] = np.nan
    r[~np.isfinite(r)] = np.nan
    R = r.reshape(-1, C, F)                                     # (Wn, C, F)

    win_iso = [str(pd.Timestamp(int(st))) for st in starts]
    channels = []
    for ci in range(C):
        raw = chans[ci] if ci < len(chans) else f"ch{ci}"
        fmt = format_channel(raw, region=(region_map or {}).get(raw, ""))
        name = fmt["label"] if fmt["region"] else fmt["short"]
        rc = R[:, ci, :].T                                      # (F, Wn)
        channels.append({
            "channel": name,
            "freqs": [float(v) for v in f_set],
            "window_starts": win_iso,
            "r": [[_f(v) for v in row] for row in rc],
        })
    return {"channels": channels, "window_days": window_days, "step_days": step_days}


def corr_spectrum(td_detail, ignore_band=None, p_significant=0.001, region_map=None, n_peaks=6,
                  max_freq_hz=50.0, q_significant=0.05):
    """Pearson-R-vs-frequency correlation spectrum per channel
    (biomarker_analysis_streaming.ipynb cell 12). `td_detail` is the streaming_psd result dict.

    `ignore_band` defaults to None (no 55–66 Hz mask — 60 Hz is preserved, consistent with the
    notch removal). Each channel also gets `peaks`: the strongest |R| local maxima (freq, r) so the
    UI can HIGHLIGHT peaks instead of relying on hover. `region_map` (raw-channel -> region) lets
    the brain region come from the patient's device metadata instead of a static map.

    Each channel also carries `peak_scatter`: per-session (feature value at the peak frequency,
    pain label, date) for the scatterplot of observed correlation at the peak frequency vs pain.
    The peak is the frequency with the single largest |R| for that channel — NOT the family max
    over all channels (which is what `perm_obs` captures). This is the biologically meaningful
    "best frequency for this electrode" that the permutation test is really interrogating.
    """
    if not td_detail:
        return None
    from scipy.signal import find_peaks
    f = np.asarray(td_detail["f_set"], dtype=float)
    corr = np.asarray(td_detail["corr"], dtype=float)   # (C, F)
    pval = np.asarray(td_detail["pval"], dtype=float)
    # `pval` is now CLUSTER-ROBUST on rating clusters when the caller supplied a grouping
    # (streaming_psd.pearson_corr_psd_label). The naive t-on-epochs family is carried alongside so
    # the panel can show the contrast instead of silently swapping one p-value for another — the
    # same pattern the exploration scan uses with p_pearson/q_pearson.
    _pv_naive = td_detail.get("pval_naive")
    pval_naive = (np.asarray(_pv_naive, dtype=float) if _pv_naive is not None else None)
    _pval_method = td_detail.get("pval_method") or "naive t on epochs, df=n-2"
    chans = td_detail.get("chan_order", [])
    ignore = np.zeros(len(f), bool) if not ignore_band else ((f > ignore_band[0]) & (f < ignore_band[1]))
    # Enforce the biomarker frequency cap: frequencies at/above max_freq_hz are excluded from peak
    # picking, the peak-scatter, and significance markers (a biomarker can't be selected there).
    if max_freq_hz is not None:
        ignore = ignore | (f >= float(max_freq_hz))

    # Per-session feature (E, C, F) and labels (E,) for scatter data.
    feature = td_detail.get("feature")   # may be None for legacy callers
    feat = np.asarray(feature, dtype=float) if feature is not None else None
    raw_labels = td_detail.get("labels")
    labels_arr = np.asarray(raw_labels, dtype=float) if raw_labels is not None else None
    times = td_detail.get("times")   # (E,) ISO strings or None

    # Significance markers are FDR-corrected, not raw p<p_significant. The spectrum shows ~101
    # frequencies x C channels, so an uncorrected p<0.001 marker over-states significance to a
    # viewer reading the panel directly. Build a Benjamini-Hochberg q-grid over the DISPLAYED family
    # (all non-ignored channel x freq cells) and mark a cell significant only when its FDR q is
    # below q_significant. Ignored cells (>=cap / notch) are excluded from the family. (Band
    # SELECTION still uses the autocorrelation-adjusted FDR in pipeline; the headline statement is
    # the permutation perm_p — this only makes the on-panel green markers honest.)
    from .stats_utils import bh_fdr
    pflat = pval.astype(float).copy()
    pflat[:, ignore] = np.nan                     # drop capped/notched cells from the FDR family
    qgrid = bh_fdr(pflat.ravel()).reshape(pval.shape)
    # Second BH family on the NAIVE p over exactly the same displayed cells, so the panel can state
    # how much of its apparent significance came from treating correlated epochs as independent.
    _q_naive_grid = None
    if pval_naive is not None and pval_naive.shape == pval.shape:
        _pn = pval_naive.astype(float).copy()
        _pn[:, ignore] = np.nan
        _q_naive_grid = bh_fdr(_pn.ravel()).reshape(pval.shape)

    channels = []
    for ci in range(corr.shape[0]):
        raw = chans[ci] if ci < len(chans) else f"ch{ci}"
        fmt = format_channel(raw, region=(region_map or {}).get(raw, ""))
        r_row = corr[ci].copy()
        p_row = pval[ci].copy()
        q_row = qgrid[ci]
        r_row[ignore] = np.nan
        # Significant = survives BH-FDR (q < q_significant) on the displayed family, not raw p.
        sig = [(_f(r_row[k]) if (np.isfinite(q_row[k]) and q_row[k] < q_significant and not ignore[k]) else None)
               for k in range(len(f))]

        # Peaks: strongest |R| local maxima, for highlighting.
        absr = np.abs(np.nan_to_num(r_row, nan=0.0))
        pk, _props = find_peaks(absr, prominence=0.05)
        pk = sorted(pk, key=lambda k: -absr[k])[:n_peaks]
        peaks = [{"freq": float(f[k]), "r": _f(r_row[k])} for k in sorted(pk)]

        # Peak-scatter: per-session feature at this channel's single best-|R| frequency.
        # Uses argmax |R| (the strongest individual correlation for this channel), NOT the
        # family-max used by perm_obs (which ranges over ALL channels x frequencies).
        peak_scatter = None
        best_fi = int(np.argmax(absr)) if absr.any() else None
        if best_fi is not None and feat is not None and labels_arr is not None:
            peak_feat = feat[:, ci, best_fi]           # (E,) feature values at peak freq
            valid = np.isfinite(peak_feat) & np.isfinite(labels_arr)
            if valid.sum() >= 3:
                peak_scatter = {
                    "peak_freq": float(f[best_fi]),
                    "peak_r": _f(r_row[best_fi]),
                    "x": [_f(v) for v in peak_feat[valid]],   # feature (log power) per session
                    "y": [_f(v) for v in labels_arr[valid]],  # pain label per session
                    "dates": ([str(times[i]) for i, ok in enumerate(valid) if ok]
                              if times is not None else None),
                }

        channels.append({
            "name": fmt["label"], "short": fmt["short"], "region": fmt["region"], "raw": fmt["raw"],
            "r": [_f(x) for x in r_row],
            "p": [_f(x) for x in p_row],
            "q": [_f(x) for x in q_row],          # BH-FDR q over the displayed family
            # The naive t-on-epochs family, for the contrast. NOT the headline.
            "p_naive": ([_f(x) for x in pval_naive[ci]] if pval_naive is not None else None),
            "q_naive": ([_f(x) for x in _q_naive_grid[ci]] if _q_naive_grid is not None else None),
            "significant": sig,
            "peaks": peaks,
            "peak_scatter": peak_scatter,
        })
    return {"freqs": [float(x) for x in f], "channels": channels,
            "transform": td_detail.get("transform", "log"),
            "p_significant": p_significant, "q_significant": q_significant,
            "significance_method": "BH-FDR over displayed channel x freq family",
            "pval_method": _pval_method,
            # How many displayed cells survive BH under each p definition. The gap IS the
            # pseudoreplication: epochs sharing one pain report are not independent, and the naive
            # t with df = n-2 counts each epoch as a fresh observation.
            "n_sig_cluster": int(np.sum(np.isfinite(qgrid) & (qgrid < q_significant)
                                        & ~ignore[None, :])),
            "n_sig_naive": (int(np.sum(np.isfinite(_q_naive_grid) & (_q_naive_grid < q_significant)
                                       & ~ignore[None, :])) if _q_naive_grid is not None else None),
            "n_cells_displayed": int(np.sum(~ignore) * corr.shape[0])}


# --- Exploratory spectral feature-importance scan (DESIGN §8b) -------------------------------
def _binarize_labels(values, strategy="tertile", low_pct=33.3333, high_pct=66.6667,
                     pain_cutoff=None, finite_mask=None, rating_group=None):
    """Binary 0/1 label (NaN for the excluded middle) from a 1-D continuous PRO array.

    Mirrors adapter._threshold_pain_level but operates on a flat array (one value per matched
    neural sample). The cut is computed on the FINITE values present:
      * "tertile"/"percentile": <= low_pct quantile -> 0, >= high_pct quantile -> 1, middle -> NaN
      * "median": >= median -> 1 else 0
      * "cutoff": >= pain_cutoff (default = median) -> 1 else 0
      * "kmeans": 2-cluster split on the 1-D values (>= cluster midpoint -> 1)

    `finite_mask` (optional bool array, same shape) restricts BOTH the cut reference and the output
    to a subset of rows — used by the glmer/stim-stability click-validate path to binarize on a
    single channel's own labels (PARITY audit §6b), reproducing the offline per-channel cut. Rows
    outside the mask stay NaN. When None, the cut is global over all finite values (scan behaviour).

    `rating_group` (optional int/str array, same shape) defeats pseudoreplication of the CUT
    REFERENCE: when supplied, the tertile/median/cutoff threshold is computed on ONE value per
    unique rating group (the unique daily PRO distribution) rather than on the per-sample vector,
    where a rating matched by k neural windows would otherwise appear k times and pull the cut
    toward whichever pain state had more recording activity (remediation R11 / audit A7). The
    resulting thresholds are then applied to EVERY finite sample, so n_high/n_low still count
    per-sample. Output labels are unchanged in shape; only the percentile reference is deduplicated.
    """
    v = np.asarray(values, dtype=float)
    out = np.full(v.shape, np.nan)
    fin = np.isfinite(v)
    if finite_mask is not None:
        fin = fin & np.asarray(finite_mask, dtype=bool)
    ref = v[fin]
    if ref.size == 0:
        return out
    # R11: build the cut REFERENCE from one representative value per unique rating group so the
    # threshold reflects the PRO distribution, not the matched-sample multiplicity. Samples in the
    # same group share their rating's PRO value, so the per-group representative is well-defined.
    if rating_group is not None:
        rg = np.asarray(rating_group)
        if rg.shape == v.shape:
            seen = {}
            for gid, val, ok in zip(rg[fin], v[fin], np.ones(int(fin.sum()), dtype=bool)):
                if gid not in seen:
                    seen[gid] = float(val)
            if seen:
                ref = np.asarray(list(seen.values()), dtype=float)
    if strategy in ("tertile", "percentile"):
        lo_q = 33.3333 if strategy == "tertile" else float(low_pct)
        hi_q = 66.6667 if strategy == "tertile" else float(high_pct)
        lo = float(np.percentile(ref, lo_q))
        hi = float(np.percentile(ref, hi_q))
        out[fin & (v <= lo)] = 0.0
        out[fin & (v >= hi)] = 1.0
        # values strictly between lo and hi stay NaN (excluded middle)
    elif strategy == "kmeans":
        s = np.sort(ref)
        # 1-D 2-means via the largest gap is unstable; use the midpoint of the two cluster means
        # from a single Lloyd step seeded at the tertiles — adequate for an exploratory split.
        c0, c1 = float(np.percentile(ref, 25)), float(np.percentile(ref, 75))
        for _ in range(25):
            a = ref[np.abs(ref - c0) <= np.abs(ref - c1)]
            b = ref[np.abs(ref - c0) > np.abs(ref - c1)]
            nc0 = float(a.mean()) if a.size else c0
            nc1 = float(b.mean()) if b.size else c1
            if abs(nc0 - c0) < 1e-9 and abs(nc1 - c1) < 1e-9:
                break
            c0, c1 = nc0, nc1
        mid = (c0 + c1) / 2.0
        out[fin] = (v[fin] >= mid).astype(float)
    else:  # "median" / "cutoff"
        cut = float(pain_cutoff) if (strategy == "cutoff" and pain_cutoff is not None) \
            else float(np.median(ref))
        out[fin] = (v[fin] >= cut).astype(float)
    return out


def matched_sample_counts(labels, strategy="tertile", low_pct=33.3333, high_pct=66.6667,
                          pain_cutoff=None, match_dt_min=None, tolerance_min=None):
    """Count, ON THE PSD/NEURAL SAMPLES, how many carry a matched pain label and how that label
    binarizes into high/low (+ excluded middle).

    `labels` is the per-session continuous PRO already matched within the tolerance window (NaN
    where no PRO fell inside the window). This is the count the binarization histogram must report:
    distinct matched neural samples, not raw daily pain surveys. `match_dt_min` (signed minutes,
    optional) lets us report the median |offset| of the matches so the user sees how tight the
    window actually bit.
    """
    y = np.asarray(labels, dtype=float)
    n_sessions = int(y.size)
    matched = np.isfinite(y)
    n_matched = int(matched.sum())
    pl = _binarize_labels(y, strategy=strategy, low_pct=low_pct, high_pct=high_pct,
                          pain_cutoff=pain_cutoff)
    n_high = int(np.nansum(pl == 1.0))
    n_low = int(np.nansum(pl == 0.0))
    # Excluded middle only exists for the tertile/percentile labelers.
    n_excluded = int(n_matched - n_high - n_low) if strategy in ("tertile", "percentile") else 0
    out = {
        "n_sessions": n_sessions,          # total streaming/PSD sessions
        "n_matched": n_matched,            # sessions with a pain report inside the window
        "n_unmatched": int(n_sessions - n_matched),
        "n_high": n_high,
        "n_low": n_low,
        "n_excluded_middle": max(n_excluded, 0),
        "strategy": strategy,
        "tolerance_min": (None if tolerance_min is None else float(tolerance_min)),
    }
    if match_dt_min is not None:
        d = np.asarray(match_dt_min, dtype=float)
        d = d[np.isfinite(d)]
        if d.size:
            out["median_abs_offset_min"] = float(np.median(np.abs(d)))
            out["max_abs_offset_min"] = float(np.max(np.abs(d)))
    return out


def _cv_logistic_auc(x, y, n_splits=5, seed=0, groups=None):
    """Cross-validated logistic-regression AUC for a SINGLE feature `x` against binary `y`.

    Out-of-fold predicted probabilities -> one ROC-AUC over all held-out samples (so each sample is
    scored by a model that did not see it). Oriented to >= 0.5 (max(auc, 1-auc)) because the
    feature's sign vs pain is itself part of the exploration. Returns (auc, n_used). NaN when a
    class is missing or too few samples to split.

    `groups` (optional, same length as x/y): a per-sample cluster id (the matched PRO/rating). When
    given, folds are split with StratifiedGroupKFold so all samples sharing a rating stay on the
    same side of every train/test split — the predictive analog of a per-rating random intercept.
    This removes the optimism that double-dipping injects when many neural samples share one rating
    (a plain StratifiedKFold would leak a rating's near-duplicate samples across folds and inflate
    the AUC). `n_used` is then reported as the number of independent groups, not raw samples."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedKFold, StratifiedGroupKFold
    from sklearn.metrics import roc_auc_score
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    g = np.asarray(groups) if groups is not None else None
    m = np.isfinite(x) & np.isfinite(y)
    if g is not None:
        m = m & (g >= 0)
    x, y = x[m], y[m]
    g = g[m] if g is not None else None
    n = x.size
    if n < 8 or len(np.unique(y)) < 2:
        return np.nan, int(n)
    pos, neg = int((y == 1).sum()), int((y == 0).sum())
    # n_used reported as independent units: groups when grouping, else samples.
    n_units = int(np.unique(g).size) if g is not None else n
    X = x.reshape(-1, 1)
    oof = np.full(n, np.nan)
    if g is not None:
        # Need >=2 groups per class to form grouped folds without a rating crossing the split.
        n_grp = int(np.unique(g).size)
        # groups-per-class count
        gpos = int(np.unique(g[y == 1]).size); gneg = int(np.unique(g[y == 0]).size)
        k = int(min(n_splits, gpos, gneg))
        if k < 2:
            return np.nan, n_units
        splitter = StratifiedGroupKFold(n_splits=k, shuffle=True, random_state=seed)
        split_iter = splitter.split(X, y, groups=g)
    else:
        k = int(min(n_splits, pos, neg))
        if k < 2:
            return np.nan, int(n)
        splitter = StratifiedKFold(n_splits=k, shuffle=True, random_state=seed)
        split_iter = splitter.split(X, y)
    for tr, te in split_iter:
        if len(np.unique(y[tr])) < 2:
            continue
        clf = LogisticRegression(max_iter=200)
        clf.fit(X[tr], y[tr])
        oof[te] = clf.predict_proba(X[te])[:, 1]
    ok = np.isfinite(oof)
    if ok.sum() < 4 or len(np.unique(y[ok])) < 2:
        return np.nan, n_units
    auc = float(roc_auc_score(y[ok], oof[ok]))
    return max(auc, 1.0 - auc), n_units


def _cluster_robust_logit_p(x, y, groups=None):
    """Two-sided Wald p-value for the band-power coefficient in a single-feature logistic fit.

    When `groups` is given (the matched pain rating per sample), the standard error is cluster-robust
    (sandwich estimator clustered on rating) — the inference companion to the rating-grouped AUC: it
    models each rating as a cluster so repeated PSDs sharing one rating don't shrink the SE and
    fabricate significance. This is the rating-as-random-effect p the binary classification reports.
    Without groups it's the ordinary logistic Wald p. Returns (p, n_used, n_clusters) — NaN p when
    the fit can't run (a class missing, separation, or too few samples)."""
    import numpy as _np
    x = _np.asarray(x, dtype=float); y = _np.asarray(y, dtype=float)
    g = _np.asarray(groups) if groups is not None else None
    m = _np.isfinite(x) & _np.isfinite(y)
    if g is not None:
        m = m & (g >= 0)
    x, y = x[m], y[m]
    g = g[m] if g is not None else None
    n = x.size
    if n < 8 or len(_np.unique(y)) < 2:
        return _np.nan, int(n), 0
    if _np.nanstd(x) <= 0:
        return _np.nan, int(n), (int(_np.unique(g).size) if g is not None else 0)
    n_clusters = int(_np.unique(g).size) if g is not None else 0
    try:
        import statsmodels.api as sm
        X = sm.add_constant(x)
        if g is not None and n_clusters >= 2:
            res = sm.GLM(y, X, family=sm.families.Binomial()).fit(
                cov_type="cluster", cov_kwds={"groups": g})
        else:
            res = sm.GLM(y, X, family=sm.families.Binomial()).fit()
        p = float(res.pvalues[1])
        if not _np.isfinite(p):
            return _np.nan, int(n), n_clusters
        return p, int(n), n_clusters
    except Exception:
        return _np.nan, int(n), n_clusters


def outlier_report_for_feature(x, *, n_mad=None, context=""):
    """Outlier REPORT (never a removal) for a device-facing log/dB band-power feature.

    Used by the deployment and threshold-detector readouts. The policy differs from the exploration
    scan on purpose: those readouts produce an OPERATING POINT the device will run against, and the
    device meets the full distribution including the extremes. A cut fitted on a trimmed sample
    would not deliver the sensitivity printed beside it. So here the rule is evaluated and reported,
    and the caller decides whether any associational statistic is worth re-running without the
    flagged samples as a labelled sensitivity analysis.

    ``x`` must ALREADY be on the log/dB scale (which is what every caller passes), so the rule is
    applied with ``scale="raw"`` — that IS the log scale for band power. Passing a raw linear feature
    here would apply a one-sided rule; use ``apply_outlier_exclusion`` with ``scale="log"`` for that.
    """
    x = np.asarray(x, dtype=float)
    n_mad = float(OUTLIER_N_MAD if n_mad is None else n_mad)
    mask, info = mad_outlier_flags(x, n_mad=n_mad, scale="raw")
    n_fin = int(np.isfinite(x).sum())
    return mask, {
        "policy": "REPORTED, NOT REMOVED (operating point must reflect the full distribution)",
        "rule": f"|x - median| >= {n_mad:g} x MAD on the log/dB band-power feature",
        "n_mad": n_mad,
        "n_flagged": int(info["n_removed"]),
        "n_samples": n_fin,
        "pct_flagged": (100.0 * info["n_removed"] / n_fin) if n_fin else None,
        "median": info["median"], "mad": info["mad"], "skipped": info["skipped"],
        "context": context or None,
    }


def _band_feature_from_detail(td_detail, channel_raw, center_hz, band_width_hz=5.0):
    """Extract the per-sample log band-power feature + matched labels + rating clusters + times for
    ONE (channel, band) from a pooled td_detail — the SAME feature definition the glmer uses.

    Returns (bp_log (N,), labels (N,), rating_group (N,), times (N,)) restricted to finite-feature
    rows, or None on any structural failure (channel/band not found). Caller binarizes labels.
    """
    if not td_detail:
        return None
    f = np.asarray(td_detail.get("f_set"), dtype=float)
    psd = np.asarray(td_detail.get("psd"), dtype=float)
    labels = np.asarray(td_detail.get("labels"), dtype=float)
    chans = td_detail.get("chan_order", [])
    rating_group = td_detail.get("rating_group")
    times = td_detail.get("times")
    ci = None
    for i, raw in enumerate(chans):
        if raw == channel_raw or format_channel(raw)["short"] == channel_raw:
            ci = i
            break
    if ci is None:
        return None
    w = float(band_width_hz)
    bmask = (f >= center_hz - w / 2.0) & (f < center_hz + w / 2.0)
    if not bmask.any():
        return None
    with np.errstate(invalid="ignore", divide="ignore"):
        sub = np.nanmean(psd[:, ci, bmask], axis=1)
        bp_log = sub if td_detail.get("prelog", False) else 10.0 * np.log10(np.where(sub > 0, sub, np.nan))
    rg = (np.asarray(rating_group) if rating_group is not None
          else np.arange(len(bp_log)))
    tt = (np.asarray([str(t) for t in times]) if times is not None
          else np.array([""] * len(bp_log)))
    return bp_log, labels, rg, tt


def _auto_block_len(cluster_series):
    """Auto block length for the moving-block bootstrap (audit [16]/[19]), chosen from the temporal
    autocorrelation of the per-cluster pain series (clusters in TIME ORDER).

    Returns 1 when there is no meaningful positive autocorrelation — so uncorrelated ratings reproduce
    the i.i.d. rating-cluster bootstrap EXACTLY (the prior behaviour). Otherwise returns the larger of
    the n^(1/3) rule-of-thumb and the autocorrelation decay length (first lag where the ACF drops below
    0.1), capped at K//3 so a block never spans most of the record. `cluster_series` is the mean
    continuous pain value per cluster, ordered by time.
    """
    x = np.asarray(cluster_series, dtype=float)
    x = x[np.isfinite(x)]
    K = x.size
    if K < 8:
        return 1
    x = x - x.mean()
    denom = float(np.dot(x, x))
    if denom <= 0:
        return 1
    maxlag = int(min(K // 2, 20))
    acf = np.array([float(np.dot(x[:-k], x[k:])) / denom for k in range(1, maxlag + 1)])
    if acf.size == 0 or acf[0] <= 0.1:
        return 1                                  # no positive lag-1 autocorrelation -> i.i.d.
    below = np.where(acf < 0.1)[0]
    decay = int(below[0] + 1) if below.size else maxlag   # first lag with ACF < 0.1 (1-indexed)
    n13 = max(2, int(round(K ** (1.0 / 3.0))))
    L = int(min(max(decay, n13), max(2, K // 3)))

    # F4: A MOVING-BLOCK BOOTSTRAP NEEDS ENOUGH BLOCKS TO BE CALIBRATED, and the K//3 cap does not
    # deliver that. At K = 48 the old rule returned L = 12, i.e. only 4 blocks per replicate, and
    # simulated coverage of the resulting 95% interval was 0.850 against 0.945 for L = 1 — the
    # interval was too narrow because a replicate built from 4 blocks cannot represent the
    # resampling distribution. Two guards:
    #   * require at least MIN_BOOT_BLOCKS blocks, so L <= K / MIN_BOOT_BLOCKS;
    #   * below SMALL_K_BLOCK_BOOT clusters, fall back to L = 1 (the i.i.d. cluster bootstrap),
    #     which is the calibrated choice at these counts even when some autocorrelation is present.
    # This trades a little bias (serial dependence under-represented) for a lot of variance
    # calibration, which is the right trade when the interval is the deliverable.
    if K < SMALL_K_BLOCK_BOOT:
        return 1
    return int(max(1, min(L, K // MIN_BOOT_BLOCKS)))


def _block_bootstrap_aucs(use_score, y, cluster_of_row, K, n_boot, block_len, rng):
    """Vectorized (moving-)block bootstrap of the DE-FOLDED AUC over rating clusters.

    `cluster_of_row` maps each row to a cluster index 0..K-1 in TIME ORDER. With block_len<=1 this is
    the i.i.d. rating-cluster bootstrap (resample whole clusters with replacement); with block_len>1
    it is a circular moving-block bootstrap (Politis–Romano) that preserves serial dependence across
    adjacent ratings. Each replicate's AUC is the fixed-orientation (de-folded, audit C1) tie-aware
    Mann–Whitney statistic on the cluster multiplicities — computed for ALL replicates at once with
    a single sort + segment-sum (np.add.reduceat), no Python per-replicate loop and no sklearn call.

    Returns a (n_boot,) float array; replicates that lose a class are NaN (caller filters them).
    """
    B = int(n_boot)
    # ---- draw cluster picks: (B, K) cluster indices ----
    if block_len is None or block_len <= 1:
        picks = rng.integers(0, K, size=(B, K))
    else:
        L = int(block_len)
        n_blocks = int(np.ceil(K / L))
        starts = rng.integers(0, K, size=(B, n_blocks))
        offs = np.arange(L)
        idx = (starts[:, :, None] + offs[None, None, :]) % K     # circular blocks
        picks = idx.reshape(B, -1)[:, :K]
    # ---- per-replicate cluster multiplicities -> per-row weights (B, N) ----
    cl_counts = np.zeros((B, K), dtype=np.float64)
    np.add.at(cl_counts, (np.arange(B)[:, None], picks), 1.0)
    W = cl_counts[:, cluster_of_row]                              # (B, N)
    return _weighted_auc_matrix(use_score, y, W)


def _weighted_auc_matrix(use_score, y, W):
    """De-folded, tie-aware Mann–Whitney AUC for EVERY row of a (B, N) weight matrix at once.

    `W[b, j]` is the (non-negative) multiplicity of row j in replicate b — integer counts for a
    bootstrap, 0/1 masks for a jackknife. Fixed orientation (no per-row re-fold, audit C1). Returns a
    (B,) float array; rows that lose a class are NaN. One mergesort + np.add.reduceat segment-sum; no
    Python loop over replicates.
    """
    W = np.asarray(W, dtype=np.float64)
    perm = np.argsort(use_score, kind="mergesort")
    ss = use_score[perm]
    ys = y[perm]
    Wp = W[:, perm]
    pos_w = Wp * (ys == 1)[None, :]
    neg_w = Wp * (ys == 0)[None, :]
    npos = pos_w.sum(1)
    nneg = neg_w.sum(1)
    # group boundaries at distinct score values (ss is sorted ascending)
    bounds = np.concatenate([[0], np.where(np.diff(ss) > 0)[0] + 1])
    gpos = np.add.reduceat(pos_w, bounds, axis=1)                 # (B, G)
    gneg = np.add.reduceat(neg_w, bounds, axis=1)
    cum_before = np.cumsum(gneg, axis=1) - gneg                   # neg weight strictly before group
    U = (gpos * (cum_before + 0.5 * gneg)).sum(1)                 # ties get 0.5 credit
    auc = np.full(W.shape[0], np.nan)
    ok = (npos > 0) & (nneg > 0)
    auc[ok] = U[ok] / (npos[ok] * nneg[ok])
    return auc


def bootstrap_auc_from_row_picks(use_score, y, picks):
    """The same de-folded, tie-aware area under the curve that ``_weighted_auc_matrix`` returns for
    a resample, computed straight from the drawn row numbers without ever building the
    (resamples by rows) matrix of multiplicities.

    IT RETURNS THE SAME DOUBLES, NOT MERELY THE SAME QUANTITY. Let ``W[b, j]`` be the number of
    times row ``j`` was drawn into resample ``b``. Then
    ``bootstrap_auc_from_row_picks(use_score, y, picks)`` is equal, element by element and bit for
    bit, to ``_weighted_auc_matrix(use_score, y, W)``. Two things make that true rather than
    approximately true:

    * Every quantity on the way to the answer is a WHOLE NUMBER (or a whole number of halves), and
      small: a multiplicity is at most the number of rows drawn, a running total of low-pain weight
      is at most that same number, and their product summed over the tie groups is at most the
      number of rows cubed. For the sizes this module works at -- a few hundred to a few thousand
      pain reports -- that is far below the largest whole number a double holds exactly (about
      9.0e15), so none of the additions or multiplications rounds at all. Where nothing rounds, the
      order the additions are done in cannot change the answer, which is what lets the low-pain
      running total be accumulated over tie groups here instead of over rows there.
    * The division at the end is the identical division of two exactly-equal doubles.

    The last multiplication is arranged as ``2 * running total - low-pain weight``, halved once at
    the end, so that no intermediate is a half-integer. That is a whole-number rearrangement of
    ``running total before the group + half the group's own low-pain weight``, which is the tie
    convention ``_weighted_auc_matrix`` uses and this function must not depart from.

    ``use_score`` is one score per row, ``y`` is 1 for a high-pain row, 0 for a low-pain one, and
    anything else for a row the split left out (such a row contributes nothing, exactly as it
    contributes nothing there). ``picks`` is the drawn row numbers, one row per resample. Returns
    one area under the curve per resample; a resample that lost either state comes back non-finite.
    """
    s = np.asarray(use_score, dtype=np.float64)
    yy = np.asarray(y, dtype=np.float64)
    picks = np.asarray(picks)
    if picks.ndim == 1:
        picks = picks[None, :]
    B = int(picks.shape[0])
    n = int(s.size)
    if n == 0 or B == 0:
        return np.full(B, np.nan)
    # THE SAME SORT AND THE SAME GROUPING RULE as _weighted_auc_matrix: a mergesort of the scores,
    # and a new tie group wherever the sorted score strictly increases.
    perm = np.argsort(s, kind="mergesort")
    ss = s[perm]
    starts = np.empty(n, dtype=bool)
    starts[0] = True
    if n > 1:
        starts[1:] = np.diff(ss) > 0
    gid_sorted = np.cumsum(starts) - 1
    G = int(gid_sorted[-1]) + 1
    gid = np.empty(n, dtype=np.int64)
    gid[perm] = gid_sorted
    # Three lanes so that a row the split left out lands in a lane nothing reads, rather than being
    # miscounted as a low-pain row. The lane is the FASTEST-moving part of the bin number, which
    # was measured against the other way round: putting the lane first makes the two lanes
    # contiguous to read but scatters the counting across three distant regions of memory, and it
    # came out slower (0.101 s against 0.094 s over twenty-three band centres at the live size).
    lane = np.where(yy == 1, 0, np.where(yy == 0, 1, 2)).astype(np.int64)
    key_of_row = gid * 3 + lane
    keys = key_of_row[picks]
    keys += (np.arange(B, dtype=np.int64) * (3 * G))[:, None]
    counts = np.bincount(keys.ravel(), minlength=B * 3 * G).reshape(B, G, 3)
    gpos = counts[:, :, 0].astype(np.float64)
    gneg = counts[:, :, 1].astype(np.float64)
    npos = gpos.sum(axis=1)
    nneg = gneg.sum(axis=1)
    run = np.cumsum(gneg, axis=1)
    run *= 2.0
    run -= gneg
    run *= gpos
    u = 0.5 * run.sum(axis=1)
    auc = np.full(B, np.nan)
    ok = (npos > 0) & (nneg > 0)
    auc[ok] = u[ok] / (npos[ok] * nneg[ok])
    return auc


def _jackknife_cluster_aucs(use_score, y, cluster_of_row, K):
    """Delete-one-CLUSTER jackknife AUCs (de-folded), vectorized. Row i of the (K, N) weight matrix is
    all-ones with cluster i zeroed -> the AUC on every sample EXCEPT cluster i. Used for the BCa
    acceleration term (the empirical influence/skew of the AUC), which is a property of the statistic
    and so is estimated the same way regardless of the block-resampling scheme."""
    W = np.ones((K, use_score.size), dtype=np.float64)
    for i in range(K):
        W[i, cluster_of_row == i] = 0.0
    return _weighted_auc_matrix(use_score, y, W)


def _bca_ci(theta_hat, boot, jack, alpha=0.05):
    """Bias-corrected & accelerated (BCa) percentile interval (Efron). `boot` is the REPORTED
    bootstrap distribution (here the moving-block resamples) and `jack` the delete-one-cluster
    jackknife estimates for the acceleration. Returns (lo, hi, z0, a). The BCa percentile shift is read
    from `boot`, so the interval keeps the block bootstrap's honest width while correcting median bias
    (z0) and skew (a). Falls back to a plain percentile interval (z0=a=0) when bias/accel are
    undefined (all replicates on one side of theta, or a degenerate jackknife)."""
    from scipy import stats as _st
    boot = np.asarray(boot, dtype=float); boot = boot[np.isfinite(boot)]
    jack = np.asarray(jack, dtype=float); jack = jack[np.isfinite(jack)]
    if boot.size < 2:
        return None, None, 0.0, 0.0
    prop = float(np.mean(boot < theta_hat))
    z0 = 0.0 if (prop <= 0.0 or prop >= 1.0) else float(_st.norm.ppf(prop))
    a = 0.0
    if jack.size >= 3:
        jbar = jack.mean()
        d = jbar - jack
        den = 6.0 * (np.sum(d * d) ** 1.5)
        if den != 0:
            a = float(np.sum(d ** 3) / den)
    zlo = float(_st.norm.ppf(alpha / 2.0)); zhi = float(_st.norm.ppf(1.0 - alpha / 2.0))

    def _adj(zq):
        denom = 1.0 - a * (z0 + zq)
        if denom == 0:
            denom = 1e-12
        return float(_st.norm.cdf(z0 + (z0 + zq) / denom))

    a1, a2 = _adj(zlo), _adj(zhi)
    lo = float(np.percentile(boot, 100.0 * a1))
    hi = float(np.percentile(boot, 100.0 * a2))
    return lo, hi, z0, a


def _solve_roc_operating_point(fpr, tpr, thr_device, rule, prevalence, cost_ratio=1.0):
    """Pick the operating-point vertex on the ROC for one cut-point rule.

    Audit [5]: this is the SAME selection the deployment ROC frontend used to run in the browser
    (Youden J / max-F1 / cost-sensitive tangent), lifted server-side so it can run on the FULL,
    un-downsampled fpr/tpr/thr arrays. The browser previously re-solved on the DOWNSAMPLED curve, so
    its chosen vertex could differ slightly from the backend's own full-array Youden default and that
    drift propagated to Phases C–E. `thr_device` is the oriented log-power threshold (rule: power >=
    thr) aligned index-for-index with fpr/tpr; the +inf/-inf sentinel vertex at the (0,0) corner is
    skipped. Strictly-greater keeps the first (lowest-index) maximizer so ties never flip.

    Returns {k, fpr, tpr, threshold, sensitivity, specificity, rule, degenerate} or None.
    """
    n = len(fpr)
    if n == 0:
        return None
    p = prevalence
    p_ok = (p is not None) and np.isfinite(p) and (0.0 < p < 1.0)
    best_k, best_u = -1, -np.inf
    for i in range(n):
        t = thr_device[i]
        if t is None or not np.isfinite(t):
            continue                                   # skip the +/-inf sentinel at (0,0)
        f_i = float(fpr[i]); t_i = float(tpr[i])
        if rule == "f1":
            if not p_ok:
                u = t_i - f_i
            else:
                tp = t_i * p; fp = f_i * (1.0 - p); fn = (1.0 - t_i) * p
                denom = 2.0 * tp + fp + fn
                u = (2.0 * tp) / denom if denom > 0 else -np.inf
        elif rule == "cost":
            # Cost-sensitive tangent: maximize tpr - slope*fpr, slope = cost_ratio*(1-p)/p.
            u = (t_i - f_i) if not p_ok else (t_i - (cost_ratio * (1.0 - p) / p) * f_i)
        else:                                          # youden (default / unknown rule)
            u = t_i - f_i
        if u > best_u:
            best_u, best_k = u, i
    if best_k < 0:
        return None
    sens = float(tpr[best_k]); fpr_k = float(fpr[best_k]); spec = 1.0 - fpr_k
    # Same degeneracy guard as the frontend: a tangent at an extreme cost ratio (or F1 at high
    # prevalence) can land on an ROC corner — "alarm almost always" (spec~0) or "almost never"
    # (sens~0) — a valid optimum but a useless controller. Flag it so the UI can warn.
    degenerate = (spec < 0.10) or (sens < 0.30) or (fpr_k > 0.95) or (fpr_k < 0.02 and sens < 0.5)
    return {
        "k": int(best_k), "fpr": fpr_k, "tpr": sens,
        "threshold": float(thr_device[best_k]),
        "sensitivity": sens, "specificity": spec,
        "rule": rule, "degenerate": bool(degenerate),
    }


def deployment_roc(td_detail, channel_raw, center_hz, *, band_width_hz=5.0,
                   strategy="tertile", low_pct=33.3333, high_pct=66.6667, pain_cutoff=None,
                   n_boot=500, max_points=300, seed=0):
    """Deployment-grade ROC for ONE committed (channel, band), with a RATING-CLUSTERED bootstrap CI
    on the AUC and a full operating-point table for the cut-point search panel.

    Why clustered: many neural samples share a single PRO rating (the matched cluster). A naive
    per-sample bootstrap treats those near-duplicate samples as independent and reports an
    over-tight AUC CI — the same double-dipping the cross-validation guards against on the discovery
    side. Here we resample WHOLE rating clusters with replacement (the deployment analog of the
    per-rating random intercept), so the CI reflects the count of INDEPENDENT ratings, not raw
    samples.

    The band feature is z-scored-log power oriented so AUC >= 0.5; the threshold scale returned is
    the same oriented log-power feature the device sees (Phase C converts it to LSB). The operating
    point defaults to Youden's J; the frontend re-solves F1 / cost-sensitive / net-benefit live from
    the returned (fpr, tpr, thr, prevalence).

    Returns {available, auc, auc_lo, auc_hi, n_boot_ok, fpr[], tpr[], thr[], prevalence, n_pos,
    n_neg, n_samples, n_clusters, operating_point{...}, flip, note} or {available: False, reason}.
    """
    from sklearn import metrics

    feat = _band_feature_from_detail(td_detail, channel_raw, center_hz, band_width_hz)
    if feat is None:
        return {"available": False, "reason": f"channel {channel_raw} / band not found in detail"}
    bp_log, labels, rating_group, _times = feat
    # F12: the tertile cut must reference the UNIQUE-RATING distribution, not the per-sample
    # vector. Without rating_group the cut point is itself pseudoreplicated — a rating with many
    # matched PSD rows drags the percentile toward its own value, so "high pain" and "low pain" get
    # defined partly by how often a rating happened to be sampled. The audit named deployment_roc;
    # the same omission was present in deployment_roc_by_era and threshold_drift_by_week.
    y_all = _binarize_labels(labels, strategy=strategy, low_pct=low_pct, high_pct=high_pct,
                             pain_cutoff=pain_cutoff, rating_group=rating_group)
    m = np.isfinite(bp_log) & np.isfinite(y_all)
    if m.sum() < 12 or len(np.unique(y_all[m])) < 2:
        return {"available": False, "reason": "too few matched high/low samples for an ROC"}
    x = bp_log[m].astype(float)
    y = y_all[m].astype(int)
    g = rating_group[m]

    # F13: THE POINT ESTIMATE AND ITS CONFIDENCE INTERVAL MUST BE ON THE SAME UNIT.
    #
    # An unweighted AUC is the probability that a randomly chosen HIGH-pain sample scores above a
    # randomly chosen LOW-pain sample. Because the AUC is an average over positive-negative PAIRS, a
    # rating contributing k samples to one class enters k times on that side, and against a rating
    # contributing k' on the other side it supplies k*k' of the pairs. So a rating's influence on the
    # estimate grows with the PRODUCT of sample counts, which means a rating that happened to be
    # matched to many PSD rows can dominate a rating matched to one. The number of rows a rating
    # attracted is an artefact of recording coverage, not of how informative that rating is.
    #
    # This also made the estimate and its interval describe different quantities. The bootstrap below
    # resamples WHOLE RATING CLUSTERS, so the confidence interval is already an interval for a
    # rating-level estimand — while the point estimate it brackets was sample-level.
    #
    # The clinically meaningful question is whether the band discriminates for a randomly chosen
    # RATING, since a rating is the unit of pain measurement and of any future deployment decision.
    # So each sample is weighted by the reciprocal of its rating's sample count, making every rating
    # contribute equally regardless of coverage, and that becomes the headline. The old sample-level
    # value is retained beside it as `auc_sample_weighted` so the change is visible and auditable
    # rather than a silent redefinition.
    _cl, _inv = np.unique(g, return_inverse=True)
    _cl_n = np.bincount(_inv).astype(float)
    w_rating = 1.0 / _cl_n[_inv]                     # each rating carries total weight 1
    raw_auc = float(metrics.roc_auc_score(y, x, sample_weight=w_rating))
    raw_auc_sample = float(metrics.roc_auc_score(y, x))
    flip = raw_auc < 0.5                       # orient so higher score = higher pain
    use_score = -x if flip else x
    auc = float(max(raw_auc, 1.0 - raw_auc))
    auc_sample_weighted = float(max(raw_auc_sample, 1.0 - raw_auc_sample))
    # F5: THIS STATISTIC DOES NOT AVERAGE 0.5 UNDER THE NULL. Orientation is chosen from the same
    # data (`flip`), so the reported value is max(A, 1-A) = 0.5 + |A - 0.5| and its null expectation
    # is 0.5 + E|A - 0.5| > 0.5. For A approximately normal about 0.5 with SD s,
    # E|A - 0.5| = s*sqrt(2/pi), so the reference the point AUC should be read against is
    #     null_reference_auc = 0.5 + s*sqrt(2/pi),   s = bootstrap SD of the AUC.
    # Computed rather than hardcoded, and it reproduces the 0.570 obtained independently by direct
    # null simulation on this band's real structure. Comparing `auc` to 0.5 overstates
    # discrimination by exactly this offset. Filled in after the bootstrap below.
    _null_ref_auc = None
    _auc_excess = None
    fpr, tpr, thr = metrics.roc_curve(y, use_score)
    # Map decision thresholds back to the ORIGINAL oriented log-power scale (rule: power >= thr).
    thr_device = (-thr if flip else thr).astype(float)

    n_pos = int(np.sum(y == 1)); n_neg = int(np.sum(y == 0))
    prevalence = float(n_pos) / float(n_pos + n_neg) if (n_pos + n_neg) > 0 else None
    n_clusters = int(len(np.unique(g)))

    # ---- rating-clustered bootstrap CI on AUC ----
    # Resample whole clusters with replacement; recompute AUC per replicate. Skip replicates that
    # lose a class. CI = percentile 2.5 / 97.5 over the valid replicates.
    #
    # DE-FOLDED (audit C1): the score is oriented ONCE on the full sample (use_score above, so the
    # point AUC >= 0.5). Each replicate must append the FIXED-DIRECTION AUC — NOT max(ab, 1-ab).
    # Re-folding per replicate reflects any replicate whose weak signal reverses back above 0.5,
    # which CENSORS the lower tail of the CI at chance: the lower bound can essentially never fall
    # below 0.5, manufacturing a floor that reads as "beats chance" even for a true-null band
    # (simulated folded lower 95% ~0.505 vs an honest ~0.411). Appending the un-folded ab lets the
    # lower bound honestly drop below 0.5 when the data do not support the band, so the CI is a valid
    # percentile interval for the oriented AUC. Power (auc_power) and the PE credible-CI/powered
    # gates inherit this CI, so the de-fold is what makes those downstream readouts honest too.
    rng = np.random.default_rng(seed)
    uniq_clusters = np.unique(g)
    n_cl = len(uniq_clusters)

    # ---- order clusters in TIME so a moving block spans temporally-adjacent ratings ----
    # Per-cluster representative time = the first parseable sample time in that cluster. Clusters whose
    # times don't parse keep their natural (id) order, which for rating_group ids is already the
    # match order. The block bootstrap below preserves serial dependence across adjacent ratings.
    g_masked = g
    t_rows = _times[m] if (_times is not None and len(_times) == len(bp_log)) else None
    if t_rows is not None:
        cl_time = {}
        t_epoch = pd.to_datetime(pd.Series([str(s) for s in t_rows]), errors="coerce", utc=True)
        t_sec = t_epoch.astype("int64").to_numpy() / 1e9  # NaT -> large negative; masked out below
        for c in uniq_clusters:
            vals = t_sec[g_masked == c]
            vals = vals[np.isfinite(vals) & (vals > 0)]
            cl_time[c] = float(vals.min()) if vals.size else np.inf
        order = sorted(range(n_cl), key=lambda i: (cl_time[uniq_clusters[i]], uniq_clusters[i]))
    else:
        order = list(range(n_cl))
    ordered_clusters = uniq_clusters[np.asarray(order, dtype=int)]
    cl_pos = {c: i for i, c in enumerate(ordered_clusters)}
    cluster_of_row = np.array([cl_pos[c] for c in g_masked], dtype=int)

    # Per-cluster mean pain label (time-ordered) drives the auto block length from autocorrelation.
    cl_mean_label = np.array([float(np.nanmean(labels[m][g_masked == c])) for c in ordered_clusters])
    block_len = _auto_block_len(cl_mean_label)

    # ---- moving-block bootstrap CI (audit [16]); i.i.d. cluster bootstrap retained for DEFF ----
    # The block CI is the honest interval (it absorbs serial autocorrelation in the weekly ratings);
    # the i.i.d. CI is computed too, ONLY so the design effect DEFF = var_block / var_iid can discount
    # the effective n in the power readout (audit [19]). Both use the SAME de-folded, tie-aware,
    # fully-vectorized AUC engine; at block_len==1 the block path reproduces the i.i.d. path exactly.
    boot_block = _block_bootstrap_aucs(use_score, y, cluster_of_row, n_cl, n_boot, block_len, rng)
    boot_block = boot_block[np.isfinite(boot_block)]
    rng_iid = np.random.default_rng(seed)  # independent stream so DEFF isn't self-correlated
    boot_iid = _block_bootstrap_aucs(use_score, y, cluster_of_row, n_cl, n_boot, 1, rng_iid)
    boot_iid = boot_iid[np.isfinite(boot_iid)]
    boot_aucs = boot_block                                       # the CI we report is the block CI

    # ---- BCa interval on the reported (block) bootstrap (audit [3]) ----
    # Bias-corrected & accelerated percentile interval. z0 corrects median bias in the block
    # distribution; the acceleration `a` comes from a delete-one-CLUSTER jackknife (the empirical
    # influence of the AUC — a property of the statistic, so the same regardless of the block scheme).
    # The CI is SUPPRESSED below BOOT_CI_VALID_FLOOR valid replicates (audit [3]-floor) rather than
    # reported on a noisy handful. ci_lo/hi_bca falls back to plain percentiles when bias/accel are
    # undefined (handled inside _bca_ci).
    # The de-folded PLAIN percentile bounds are the audit-C1 guard: because the score is oriented once
    # on the full sample, this lower bound can honestly fall below 0.5 on a true-null band. BCa's bias
    # term (z0) re-centers on the orientation-inflated point AUC, which near chance pushes the BCa lower
    # bound back up to ~0.5 — re-creating the "manufactured beats-chance floor" C1 removed. So the
    # headline CI is full BCa (bias + skew corrected, audit [3]), but the "beats chance" gate reads the
    # de-folded percentile guard below, NOT the BCa bound, so absence-of-signal can never read as
    # significance. Both are reported.
    bca_z0 = bca_a = None
    auc_lo_defold = auc_hi_defold = None
    if len(boot_block) >= BOOT_CI_VALID_FLOOR:
        auc_lo_defold = float(np.percentile(boot_block, 2.5))
        auc_hi_defold = float(np.percentile(boot_block, 97.5))
        jack = _jackknife_cluster_aucs(use_score, y, cluster_of_row, n_cl)
        auc_lo, auc_hi, bca_z0, bca_a = _bca_ci(auc, boot_block, jack, alpha=0.05)
    else:
        auc_lo = auc_hi = None
    # Design effect: variance inflation from serial dependence. >=1 by construction (block widens);
    # clamped to [1, 5] defensively and set to 1.0 when either resample is degenerate or block_len==1.
    var_iid = float(np.var(boot_iid)) if len(boot_iid) >= 20 else 0.0
    var_block = float(np.var(boot_block)) if len(boot_block) >= 20 else 0.0
    deff_raw = None
    if block_len > 1 and var_iid > 0 and var_block > 0:
        deff_raw = float(var_block / var_iid)
        deff = float(min(5.0, max(1.0, deff_raw)))
    else:
        deff = 1.0
    # F6: the CLAMP is load-bearing and must be visible. The raw ratio falls below 1 in 57.7% of
    # null simulations on this structure — block resampling does not always widen the variance at
    # these cluster counts — so clamping at 1 silently turns a measured deflation into "no
    # inflation". `deff` stays clamped, because a deff < 1 would inflate the effective n and make
    # the power readout optimistic; `deff_raw` is published so the clamp is auditable, not tacit.

    # F5 continued: null reference for the FOLDED point AUC, from the bootstrap SD.
    _boot_sd = (float(np.std(boot_block)) if len(boot_block) >= 20
                else (float(np.std(boot_iid)) if len(boot_iid) >= 20 else None))
    if _boot_sd is not None and np.isfinite(_boot_sd) and _boot_sd > 0:
        _null_ref_auc = float(0.5 + _boot_sd * np.sqrt(2.0 / np.pi))
        _auc_excess = float(auc - _null_ref_auc)

    # ---- default operating point: Youden's J ----
    op = None
    if len(thr) > 1:
        j = tpr - fpr
        j[~np.isfinite(thr)] = -np.inf
        k = int(np.argmax(j))
        op = {
            "fpr": float(fpr[k]), "tpr": float(tpr[k]),
            "threshold": float(thr_device[k]),
            "sensitivity": float(tpr[k]),
            "specificity": float(1.0 - fpr[k]),
            "youden_j": float(tpr[k] - fpr[k]),
            "direction": "ge",
            "rule": "youden",
        }

    # ---- full-array operating points (audit [5]) ----
    # Solve every cut-point rule the frontend offers on the FULL (un-downsampled) curve, so the
    # displayed/propagated operating point is exact rather than re-solved on the downsampled arrays.
    # `youden` and `f1` are prevalence-determined (no slider); `cost` is solved at a grid of cost
    # ratios so the slider can snap to the nearest precomputed full-array point. The frontend keeps
    # its live solver as a fallback for older payloads, but prefers operating_points when present.
    thr_dev_list = [None if not np.isfinite(t) else float(t) for t in thr_device]
    operating_points = {
        "youden": _solve_roc_operating_point(fpr, tpr, thr_dev_list, "youden", prevalence),
        "f1": _solve_roc_operating_point(fpr, tpr, thr_dev_list, "f1", prevalence),
    }
    # Cost-sensitive points across the slider's log2 range (-3..3, step 0.25 — matches the UI Slider).
    cost_points = []
    for log_cost in np.arange(-3.0, 3.0 + 1e-9, 0.25):
        cr = float(2.0 ** log_cost)
        cp = _solve_roc_operating_point(fpr, tpr, thr_dev_list, "cost", prevalence, cost_ratio=cr)
        if cp is not None:
            cp = dict(cp); cp["log_cost"] = float(log_cost); cp["cost_ratio"] = cr
            cost_points.append(cp)
    operating_points["cost"] = cost_points

    # ---- downsample the curve (keep thr parallel) ----
    fpr_o, tpr_o, thr_o = fpr, tpr, thr_device
    if max_points and len(fpr_o) > max_points:
        sel = np.unique(np.linspace(0, len(fpr_o) - 1, int(max_points)).astype(int))
        fpr_o, tpr_o, thr_o = fpr_o[sel], tpr_o[sel], thr_o[sel]

    # ---- feature-distribution histogram (pain-high vs pain-low) ----
    # The single most direct view of WHY this band separates pain: the per-sample band-power feature
    # split by the binarized label. Drawn beneath the ROC with the cut-point threshold line on top,
    # it shows the clinician the overlap the AUC summarizes and where any threshold falls in it.
    # Binned on `x` (= bp_log[m], the RAW oriented-log-power feature), the SAME scale the cut-point
    # threshold (thr_device / operating_point.threshold) lives on, so the threshold line maps directly
    # (Phase C percentile-anchors that same value to device LSB). Shared bin edges across both classes.
    feature_hist = None
    x_lo = float(np.min(x)); x_hi = float(np.max(x))
    if np.isfinite(x_lo) and np.isfinite(x_hi) and x_hi > x_lo:
        n_bins = int(min(30, max(8, round(np.sqrt(x.size)))))
        edges = np.linspace(x_lo, x_hi, n_bins + 1)
        c_hi, _ = np.histogram(x[y == 1], bins=edges)
        c_lo, _ = np.histogram(x[y == 0], bins=edges)
        centers = 0.5 * (edges[:-1] + edges[1:])
        feature_hist = {
            "bin_edges": [float(v) for v in edges],
            "bin_centers": [float(v) for v in centers],
            "counts_high": [int(v) for v in c_hi],
            "counts_low": [int(v) for v in c_lo],
            "n_high": int(np.sum(y == 1)), "n_low": int(np.sum(y == 0)),
            "x_min": x_lo, "x_max": x_hi,
            "feature_units": "oriented log10 band power (same scale as the cut-point threshold)",
        }

    # ---- OUTLIER HANDLING FOR A DEVICE-FACING READOUT (2026-08-30) ----------------------------
    # Deliberately NOT the same policy as the exploration scan, and the difference is the point.
    #
    # This function returns two KINDS of number. The AUC is associational: it answers "does this band
    # carry signal", and trimming a heavy tail there is defensible. The cut-point threshold and its
    # sensitivity/specificity are an OPERATING POINT the device will run against, and the device will
    # encounter the full distribution including the extremes. A threshold fitted on a trimmed
    # distribution therefore would NOT deliver the sensitivity reported next to it — the reported
    # performance would be measured on a population the device never sees.
    #
    # So: the headline AUC, ROC curve, thresholds and operating points above are computed on the FULL
    # matched sample, unchanged. The exclusion is reported, and the AUC is recomputed with outliers
    # removed as a clearly-labelled SENSITIVITY ANALYSIS. If the two AUCs disagree materially, that
    # is information about how much of the discrimination rests on tail samples — it is not a
    # licence to substitute the trimmed number.
    #
    # NOTE ON SCALE: `x` here is ALREADY log/dB band power (10*log10), so the rule is applied with
    # scale="raw" — that IS the log scale for this quantity. Passing scale="log" would take log10 of
    # a dB value, which is negative for sub-unit powers and would silently drop those samples from
    # the rule instead of testing them.
    _o_mask, _o_info = mad_outlier_flags(x, n_mad=OUTLIER_N_MAD, scale="raw")
    _sens = {"computed": False, "reason": None}
    if _o_info["n_removed"] > 0:
        keep = ~_o_mask
        y_k, s_k = y[keep], use_score[keep]
        if np.unique(y_k).size == 2 and keep.sum() >= 8:
            _raw_k = float(metrics.roc_auc_score(y_k, s_k))
            _sens = {"computed": True, "reason": None,
                     "auc_excluding_outliers": float(max(_raw_k, 1.0 - _raw_k)),
                     "auc_full_sample": auc,
                     "delta_auc": float(max(_raw_k, 1.0 - _raw_k) - auc),
                     "n_used": int(keep.sum()), "n_pos": int(np.sum(y_k == 1)),
                     "n_neg": int(np.sum(y_k == 0))}
        else:
            _sens["reason"] = ("excluding outliers left one class empty or fewer than 8 samples; "
                               "the sensitivity analysis is not estimable")
    else:
        _sens["reason"] = "no samples met the outlier rule, so the analysis is identical to the headline"
    outlier_block = {
        "policy": "REPORTED, NOT REMOVED for the operating point",
        "rule": (f"|x - median| >= {OUTLIER_N_MAD:g} x MAD on the log/dB band-power feature"),
        "n_mad": float(OUTLIER_N_MAD),
        "n_flagged": int(_o_info["n_removed"]),
        "n_samples": int(x.size),
        "pct_flagged": (100.0 * _o_info["n_removed"] / x.size) if x.size else None,
        "median": _o_info["median"], "mad": _o_info["mad"], "skipped": _o_info["skipped"],
        "rationale": ("The threshold and its sensitivity/specificity are computed on the FULL "
                      "sample because the device will encounter the full distribution; a cut fitted "
                      "on a trimmed distribution would not deliver the reported sensitivity in "
                      "deployment. The AUC excluding these samples is provided as a sensitivity "
                      "analysis only."),
        "sensitivity_analysis": _sens,
    }

    return {
        "available": True,
        "auc": auc, "auc_lo": auc_lo, "auc_hi": auc_hi,
        "outliers": outlier_block,
        "n_boot_ok": len(boot_aucs),
        "fpr": [float(v) for v in fpr_o], "tpr": [float(v) for v in tpr_o],
        "thr": [None if not np.isfinite(t) else float(t) for t in thr_o],
        "prevalence": prevalence, "n_pos": n_pos, "n_neg": n_neg,
        "n_samples": int(m.sum()), "n_clusters": n_clusters,
        # Audit [8]: advisory only — flags that asymptotic AUC inference / Gaussian power are
        # approximate below SMALL_SAMPLE_CLUSTER_FLOOR independent ratings. Changes no computed value.
        "small_sample": bool(n_clusters < SMALL_SAMPLE_CLUSTER_FLOOR),
        "small_sample_floor": int(SMALL_SAMPLE_CLUSTER_FLOOR),
        # Audit [16]/[19]: moving-block bootstrap parameters. `block_len` is the auto-chosen block
        # length (1 = ratings uncorrelated -> identical to the i.i.d. cluster bootstrap). `deff` is the
        # design effect (var_block / var_iid, >=1) used downstream to discount the effective n in the
        # power readout. `auc_lo_iid`/`auc_hi_iid` retain the i.i.d. CI for transparency/regression.
        "block_len": int(block_len), "deff": float(deff),
        # F7: suppressed under the SAME floor as auc_lo/auc_hi. These were emitted whenever 20
        # replicates survived, so when the headline CI was withheld as uncalibrated a consumer could
        # still read an i.i.d. interval built from too few replicates and treat it as the interval.
        # A suppressed CI has to be suppressed on every channel it is exposed through.
        "auc_lo_iid": (float(np.percentile(boot_iid, 2.5))
                       if len(boot_iid) >= BOOT_CI_VALID_FLOOR else None),
        "auc_hi_iid": (float(np.percentile(boot_iid, 97.5))
                       if len(boot_iid) >= BOOT_CI_VALID_FLOOR else None),
        "deff_raw": (None if deff_raw is None else round(float(deff_raw), 4)),
        "deff_was_clamped": bool(deff_raw is not None and not (1.0 <= deff_raw <= 5.0)),
        # F5: read the point AUC against THIS, never against 0.5.
        # F13: both estimands, so the reader can see how much the coverage weighting mattered.
        # `auc` is rating-equal (each rating contributes once) and is the unit the bootstrap CI is
        # on; `auc_sample_weighted` is the old per-PSD-row value.
        "auc_sample_weighted": round(auc_sample_weighted, 4),
        "auc_weighting": ("rating-equal: each sample weighted 1/(its rating's sample count), so a "
                          "rating matched to many PSD rows does not outweigh one matched to few. "
                          "The bootstrap CI resamples whole rating clusters, so this is the "
                          "estimand the interval brackets."),
        "auc_weighting_delta": round(auc - auc_sample_weighted, 4),
        "null_reference_auc": (None if _null_ref_auc is None else round(float(_null_ref_auc), 4)),
        "auc_excess_over_null": (None if _auc_excess is None else round(float(_auc_excess), 4)),
        "auc_folding_note": ("The point AUC is max(A, 1-A) with orientation chosen from the same "
                             "data, so its null expectation is null_reference_auc (> 0.5), not 0.5. "
                             "auc_excess_over_null is discrimination above that reference."),
        # Audit [3]: BCa interval. ci_method names the resampling scheme; the interval itself is
        # bias-corrected & accelerated (bca_z0 = bias correction, bca_a = acceleration from the
        # delete-one-cluster jackknife). CI suppressed (auc_lo/hi None) below BOOT_CI_VALID_FLOOR.
        "ci_interval": "BCa", "bca_z0": (None if bca_z0 is None else float(bca_z0)),
        "bca_a": (None if bca_a is None else float(bca_a)),
        "ci_valid_floor": int(BOOT_CI_VALID_FLOOR),
        # Audit C1 guard: de-folded PLAIN percentile bounds. The "beats chance" gate reads
        # auc_lo_defold (never the BCa auc_lo), so a true-null band's lower bound can honestly fall
        # below 0.5 instead of being re-floored by BCa's bias correction. See CI block comment.
        "auc_lo_defold": (None if auc_lo_defold is None else float(auc_lo_defold)),
        "auc_hi_defold": (None if auc_hi_defold is None else float(auc_hi_defold)),
        "operating_point": op, "flip": bool(flip), "feature_hist": feature_hist,
        # Audit [5]: full-array operating-point table (solved on the un-downsampled curve). Keys:
        # 'youden', 'f1' (single points), 'cost' (list across the slider's log2 cost-ratio grid).
        # The frontend snaps to these instead of re-solving on the downsampled fpr/tpr/thr.
        "operating_points": operating_points,
        "ci_method": (("moving-block bootstrap, BCa (de-folded; fixed orientation; block_len=%d)" % int(block_len))
                      if block_len > 1 else "rating-clustered bootstrap, BCa (de-folded; fixed orientation)"),
        "feature_units": "oriented log10 band power (z-scored within channel/source on the detail); Phase C maps to LSB",
        "note": (f"Rating-clustered {'moving-block ' if block_len > 1 else ''}bootstrap, BCa interval "
                 f"({len(boot_aucs)}/{int(n_boot)} valid replicates over {n_clusters} independent "
                 f"ratings; CI suppressed below {int(BOOT_CI_VALID_FLOOR)}). The point AUC is oriented "
                 f">= 0.5 and is optimistic near chance for borderline bands; the BCa CI is de-folded "
                 f"(fixed orientation) and bias/skew-corrected, so its lower bound can honestly fall "
                 f"below 0.5 when the band does not beat chance. Class-collapsed replicates are "
                 f"dropped (mildly narrows the CI at low prevalence)."),
    }


#: WEEKS OF RECORD EXCLUDED FROM THE VALIDATION MIXED MODEL, and only from that model.
#:
#: PI decision, 2026-09-05: "in the biomarker module, when we're doing the validation check for the
#: across-eras logistic regression mixed-effect model, I need to make sure to exclude the first
#: three weeks due to signal drift in the biomarker exploration. Keep all data everywhere else."
#:
#: The rationale is that the first weeks after implant carry signal drift — impedance settling and
#: post-operative change — that is not the physiology the biomarker is meant to track, so a
#: random-intercept model fitted across weekly eras spends its early eras describing recovery
#: rather than pain. This is a PROSPECTIVE, DECLARED exclusion of a fixed window, not a
#: data-dependent one: it is chosen from the implant timeline rather than by looking at which weeks
#: help the odds ratio, which is what keeps it out of the selective-inference problem the fourteen
#: finding audit was about.
#:
#: MEASURED EFFECT ON RCS08, 2026-09-05: this exclusion currently removes NOTHING from any fit, and
#: the reason is structural rather than incidental. **No pain rating exists before week 5.** The
#: fit-population census by elapsed week is {5: 6, 7: 2, 9: 2, 10: 3, 11: 5, ...} with weeks 0 to 4
#: empty, so the window ends two weeks before the first usable sample. 22 samples in weeks 0-2 do
#: carry finite band power, but 0 of them carry a pain label.
#:
#: This was verified under FOUR binarization schemes, because an earlier explanation of mine was
#: wrong. I first attributed the no-op to the tertile split discarding the middle third, and the PI
#: correctly objected that a median split excludes nothing and the burn-in samples would then
#: enter. They do not: under median and under fixed cutoffs at 5 and at 6 the fit population rises
#: from 84 to 94 samples, yet weeks 0-2 still contribute zero, because the missing thing is the
#: LABEL and not the class assignment. So the guard is correct and the objection is answered by the
#: data rather than by the tertile rule.
#:
#: OPEN DECISION, deliberately not taken here. The window above is IMPLANT-anchored: three weeks
#: from the first sample of the record. A DATA-anchored window — three weeks from the first sample
#: the fit can use — would bind, and its cost is measured: n falls 84 -> 63, weekly eras 29 -> 24,
#: and the odds ratio moves from 2.330 (95% CI 0.669-8.109, p 0.184) to 1.651 (0.501-5.443,
#: p 0.410). Going further is hazardous on this record: dropping six weeks of usable data leaves 58
#: samples in 22 eras and returns OR 2.200 with a CI of width 0.011 and p = 0.0000, which lme4
#: itself flags as "nearly unidentifiable: very large eigenvalue" — the same variance-collapse
#: signature that the closed-loop module now guards against with a cluster-count floor. Any move to
#: a data-anchored window needs the PI's decision and a degeneracy guard, not an inference from
#: this note.
#:
#: SCOPE, deliberately narrow. This applies to `band_mixedmodel_inference` ONLY. The sweep, the
#: per-band scan, the deployment ROC, the era-stability LRT and everything else continue to use the
#: whole record, because they answer different questions and the PI asked for the whole record
#: everywhere else. Anything that widens this scope needs its own decision, not an inference from
#: this one.
VALIDATION_EXCLUDE_FIRST_WEEKS = 3


def _elapsed_week_cluster(times, n):
    """Integer elapsed-week index from the first sample, as the offline validation (phase2) derives
    its random-intercept cluster: ((t_epoch - t0) / (7*86400)).astype(int). PARITY audit §6a — the
    live path previously used the ISO-calendar-week STRING, which splits elapsed-week buckets across
    Monday boundaries and gives a different random-effect structure (hence different SE/p/OR-CI).

    Returns an int array length n. Unparseable-time rows get cluster -1 (they are dropped by the
    finite-time mask in the caller). Times parsed with explicit ISO8601 (mixed microsecond forms).
    """
    if times is None or len(times) != n:
        return np.zeros(n, dtype=int)
    t_dt = pd.to_datetime(pd.Series([str(t) for t in times]), errors="coerce", format="ISO8601")
    # Resolution-independent ns epoch: Series.view is deprecated (removed in pandas 3.0) and, under
    # pandas 3.0's datetime64[us] default, a bare .astype("int64") would silently yield microseconds.
    # Pinning to datetime64[ns] first makes this identical on pandas 2.x ([ns]) and 3.x ([us]).
    te = (t_dt.to_numpy().astype("datetime64[ns]").astype("int64") / 1e9)
    nat = t_dt.isna().to_numpy()
    if (~nat).sum() == 0:
        return np.zeros(n, dtype=int)
    t0 = np.nanmin(np.where(nat, np.nan, te))
    wk = np.where(nat, -1, ((te - t0) / (7.0 * 86400.0)))
    return np.where(nat, -1, wk.astype(int)).astype(int)


def _assign_stim_eras(times, stim_series, off_max=0.1, low_max=1.5):
    """Map per-sample times to a stim era (OFF/LOW/HIGH) by carrying the stim trajectory forward
    (LOCF) onto each sample. Returns an object-array of era tags aligned to `times`, or None when
    no usable stim series is available. Shared by band_stim_stability and deployment_roc_by_era so
    the era boundaries are identical across the stability LRT and the per-era refit.

    LOCF (last-observation-carried-forward) is the physically correct semantics: a PSD sample's stim
    context is the amplitude *in effect at or before* it was recorded, NOT the next programmed change.
    `searchsorted(side='right') - 1` gives the index of the latest stim reading at-or-before each
    sample time; clipped to >=0 so a sample preceding the first reading carries that first value.
    (The prior next-sample/NOCB form mislabeled ~17% of samples' era and biased the stim-stability
    LRT that selects closed-loop anchors — see PARITY_audit §7.)"""
    if not stim_series or not stim_series.get("t") or not stim_series.get("y"):
        return None
    if times is None:
        return None
    # NOTE: parse with an explicit ISO8601 format. The sample-time strings are a mix of values WITH
    # fractional seconds ("...:28.850000") and WITHOUT ("...:20:05"); pandas 2.x infers ONE format
    # from the first element and coerces every non-matching string to NaT — which here silently
    # NaT'd ~83% of rows, clipping them to the first stim reading and ballooning the HIGH era. The
    # NaT mask drives the None-era guard below.
    t_dt = pd.to_datetime(pd.Series([str(t) for t in times]), errors="coerce", format="ISO8601")
    nat = t_dt.isna().to_numpy()
    # Resolution-independent ns epoch (see _elapsed_week_cluster): identical on pandas 2.x and 3.x,
    # and free of the deprecated Series.view.
    t_epoch = (t_dt.to_numpy().astype("datetime64[ns]").astype("int64") / 1e9)
    stim_t = np.asarray(stim_series["t"], dtype=float)
    stim_y = np.asarray(stim_series["y"], dtype=float)
    if len(stim_t) < 2:
        return None
    order = np.argsort(stim_t)
    stim_t = stim_t[order]; stim_y = stim_y[order]
    # LOCF: latest stim reading at or before each sample. Look the NaT rows up at the first reading
    # (harmless — they are masked out to None immediately after) so searchsorted sees no NaN.
    lookup = np.where(nat, stim_t[0], t_epoch)
    idx = (np.searchsorted(stim_t, lookup, side="right") - 1).clip(0, len(stim_t) - 1)
    stim_mA = stim_y[idx]
    era = np.where(stim_mA < off_max, "OFF", np.where(stim_mA <= low_max, "LOW", "HIGH"))
    era = np.where(nat, None, era)
    return era


def deployment_roc_by_era(td_detail, channel_raw, center_hz, stim_series, *, band_width_hz=5.0,
                          strategy="tertile", low_pct=33.3333, high_pct=66.6667, pain_cutoff=None,
                          n_boot=300, off_max=0.1, low_max=1.5, seed=0):
    """Refit the deployment ROC + cut-point WITHIN each stimulation era (OFF / LOW / HIGH).

    The pooled `deployment_roc` answers "how well does this band predict pain overall?"; this answers
    the closed-loop-critical follow-up "does the SAME threshold hold once stim is actually on?" — a
    band whose AUC or Youden cut-point swings across eras is a fragile controller anchor even if its
    pooled AUC looks good. Eras are assigned with the SAME nearest-time stim interpolation +
    bucketing as band_stim_stability, so the per-era refit and the stability LRT agree on boundaries.

    Returns {available, eras:{OFF:{...roc}, LOW:{...}, HIGH:{...}}, pooled:{...roc}, cutpoint_spread,
             era_counts, thresholds_mA, note} or {available: False, reason}.
    """
    feat = _band_feature_from_detail(td_detail, channel_raw, center_hz, band_width_hz)
    if feat is None:
        return {"available": False, "reason": f"channel {channel_raw} / band not found"}
    bp_log, labels, rating_group, times = feat
    era = _assign_stim_eras(times, stim_series, off_max=off_max, low_max=low_max)
    if era is None:
        return {"available": False, "reason": "no usable stim series for era assignment"}

    from sklearn import metrics

    def _roc_for(mask, fixed_flip=None):
        """Compact ROC + Youden cut-point + clustered bootstrap CI over a boolean sample mask.

        `fixed_flip` carries the POOLED orientation onto an era (audit C3). When None (the pooled
        call) the sign is chosen from this mask's own data so the pooled AUC is oriented >= 0.5.
        When a bool is passed (each era) that SAME sign is applied, so an era whose band-pain
        relationship REVERSES under stim is reported as a SIGNED AUC below 0.5 — the worst
        closed-loop failure (controller would ramp the wrong way) — instead of being folded back
        above 0.5 and mis-read as "still portable". The fixed sign also puts every era's Youden
        threshold on one comparable scale, so cutpoint_spread is meaningful across eras.
        """
        x = bp_log[mask]; yv = labels[mask]; gv = rating_group[mask]
        y = _binarize_labels(yv, strategy=strategy, low_pct=low_pct, high_pct=high_pct,
                             pain_cutoff=pain_cutoff)
        ok = np.isfinite(x) & np.isfinite(y)
        x = x[ok].astype(float); y = y[ok].astype(int); gv = gv[ok]
        if x.size < 12 or len(np.unique(y)) < 2:
            return {"available": False, "reason": "too few high/low samples in this era",
                    "n_samples": int(x.size)}
        raw = float(metrics.roc_auc_score(y, x))
        flip = (raw < 0.5) if fixed_flip is None else bool(fixed_flip)
        use = -x if flip else x
        # Pooled (fixed_flip=None) is oriented to its own data -> auc >= 0.5. Eras reuse the pooled
        # sign and report the SIGNED AUC (no fold), so a reversal shows as auc < 0.5.
        auc = float(metrics.roc_auc_score(y, use))
        # `auc < 0.5` as a POINT estimate is NOT evidence of a true sign reversal — a band with no
        # real stim-state dependence scatters its per-era AUCs around the pooled value, and a noisy
        # era easily lands below 0.5 by chance. Calling that a "direction reversal" (the worst,
        # deploy-blocking verdict) on a point estimate flags noise as a hard failure. We therefore
        # report two distinct things: `auc_below_half` (the raw point fact, descriptive) and
        # `reversed` (an INFERENTIAL claim — the whole 95% bootstrap CI sits below 0.5, set after the
        # bootstrap below). A controller-blocking reversal requires the inferential flag.
        auc_below_half = bool(auc < 0.5)
        fpr, tpr, thr = metrics.roc_curve(y, use)
        thr_dev = (-thr if flip else thr).astype(float)
        # Youden cut-point
        op = None
        if len(thr) > 1:
            j = tpr - fpr
            j[~np.isfinite(thr)] = -np.inf
            k = int(np.argmax(j))
            op = {"threshold": float(thr_dev[k]), "sensitivity": float(tpr[k]),
                  "specificity": float(1.0 - fpr[k]), "fpr": float(fpr[k]), "tpr": float(tpr[k])}
        # clustered bootstrap CI — DE-FOLDED (audit C1): fixed orientation, append float(ab), never
        # max(ab, 1-ab), so the lower bound can honestly fall below 0.5 (and below the pooled CI when
        # the era reverses or genuinely fails to separate).
        rng = np.random.default_rng(seed)
        uc = np.unique(gv); rows = {c: np.where(gv == c)[0] for c in uc}
        baucs = []
        for _b in range(int(n_boot)):
            pick = rng.choice(uc, size=len(uc), replace=True)
            ii = np.concatenate([rows[c] for c in pick])
            if len(np.unique(y[ii])) < 2:
                continue
            try:
                ab = metrics.roc_auc_score(y[ii], use[ii]); baucs.append(float(ab))
            except ValueError:
                continue
        # Audit [3]-floor: suppress the era CI below BOOT_CI_VALID_FLOOR valid replicates (was 20).
        lo = float(np.percentile(baucs, 2.5)) if len(baucs) >= BOOT_CI_VALID_FLOOR else None
        hi = float(np.percentile(baucs, 97.5)) if len(baucs) >= BOOT_CI_VALID_FLOOR else None
        # INFERENTIAL reversal: the era's band→pain direction is confidently opposite the pooled sign
        # only when the ENTIRE 95% CI lies below chance (upper bound < 0.5). If the CI straddles 0.5
        # the era is merely uninformative under the pooled orientation, not a proven reversal — that
        # must not trigger the deploy-blocking "ramps the wrong way" verdict. When the CI can't be
        # estimated (too few bootstrap resamples), fall back to None (unknown), never to the point
        # estimate.
        reversed_dir = (bool(hi < 0.5) if hi is not None else None)
        return {"available": True, "auc": auc, "auc_lo": lo, "auc_hi": hi,
                "reversed": reversed_dir, "auc_below_half": auc_below_half,
                "n_boot_ok": int(len(baucs)),
                "n_samples": int(x.size), "n_clusters": int(len(uc)),
                "n_pos": int(np.sum(y == 1)), "n_neg": int(np.sum(y == 0)),
                "operating_point": op, "flip": bool(flip),
                "prevalence": float(np.mean(y == 1))}

    # Orient ONCE from the pooled fit, then refit every era under that fixed sign.
    pooled = _roc_for(np.ones(len(bp_log), dtype=bool))
    pooled_flip = pooled.get("flip") if pooled.get("available") else None
    eras_out = {}
    for tag in ["OFF", "LOW", "HIGH"]:
        eras_out[tag] = _roc_for(era == tag, fixed_flip=pooled_flip)

    # Cut-point portability: spread of the per-era Youden thresholds that are actually estimable.
    # With the shared pooled orientation these thresholds are on one comparable signed scale.
    era_thr = [eras_out[t]["operating_point"]["threshold"] for t in ["OFF", "LOW", "HIGH"]
               if eras_out[t].get("available") and eras_out[t].get("operating_point")]
    cutpoint_spread = (float(np.max(era_thr) - np.min(era_thr)) if len(era_thr) >= 2 else None)
    era_aucs = [eras_out[t]["auc"] for t in ["OFF", "LOW", "HIGH"] if eras_out[t].get("available")]
    auc_spread = (float(np.max(era_aucs) - np.min(era_aucs)) if len(era_aucs) >= 2 else None)

    # ---- portability by INFERENCE, not raw spread (audit C3) ----
    # A band is portable only if (a) NO estimable era's direction reverses (signed AUC >= 0.5) and
    # (b) every estimable era's bootstrap CI OVERLAPS the pooled CI (the eras do not differ from the
    # pooled estimate beyond sampling error). Raw auc_spread / cutpoint_spread are retained as
    # DESCRIPTIVE annotations only. The band×era LRT (band_stim_stability) is the formal test and is
    # surfaced alongside this by the service layer; this CI signal is the figure-level companion.
    est = [eras_out[t] for t in ["OFF", "LOW", "HIGH"] if eras_out[t].get("available")]
    # `reversed` is now the INFERENTIAL flag (whole CI below 0.5); None (CI unknown) is NOT a
    # reversal. Only a confidently-below-chance era counts. `any_below_half` keeps the descriptive
    # point-estimate tally so the UI can distinguish "an era dipped below 0.5" (common, noisy) from
    # "an era's direction is confidently reversed" (rare, deploy-blocking).
    any_reversed = bool(any(e.get("reversed") is True for e in est))
    any_below_half = bool(any(e.get("auc_below_half") for e in est))

    def _ci_overlap(a, b):
        if a is None or b is None:
            return None
        if None in (a.get("auc_lo"), a.get("auc_hi"), b.get("auc_lo"), b.get("auc_hi")):
            return None
        return bool(a["auc_lo"] <= b["auc_hi"] and b["auc_lo"] <= a["auc_hi"])

    ci_overlaps_pooled = {}
    for t in ["OFF", "LOW", "HIGH"]:
        e = eras_out[t]
        ci_overlaps_pooled[t] = (_ci_overlap(e, pooled)
                                 if (e.get("available") and pooled.get("available")) else None)
    ov_vals = [v for v in ci_overlaps_pooled.values() if v is not None]
    portable_by_ci = ((len(ov_vals) >= 1 and all(ov_vals) and not any_reversed)
                      if len(est) >= 2 else None)

    _, _outl_era = outlier_report_for_feature(bp_log, context="deployment_roc_by_era")
    return {
        "available": True,
        "outliers": _outl_era,
        "eras": eras_out, "pooled": pooled,
        "cutpoint_spread": cutpoint_spread, "auc_spread": auc_spread,
        "any_reversed": any_reversed, "any_below_half": any_below_half,
        "ci_overlaps_pooled": ci_overlaps_pooled,
        "portable_by_ci": portable_by_ci,
        "era_counts": {t: int(np.sum(era == t)) for t in ["OFF", "LOW", "HIGH"]},
        "thresholds_mA": {"off_max": off_max, "low_max": low_max},
        "n_eras_estimable": int(sum(1 for t in ["OFF", "LOW", "HIGH"] if eras_out[t].get("available"))),
        "note": ("Per-era refit of the deployment ROC + Youden cut-point, all oriented to the POOLED "
                 "sign. A direction reversal is flagged ONLY when an era's entire 95% CI lies below "
                 "0.5 (an inferential claim) — a point AUC below 0.5 with a CI straddling chance is "
                 "reported as 'auc_below_half' but is NOT a reversal, since that is consistent with "
                 "no stim-state effect. Portability keys on CI overlap with pooled and the band×era "
                 "LRT, not raw spread; a band whose direction confidently reverses or whose per-era "
                 "CIs miss the pooled CI is a fragile controller anchor even with a strong pooled "
                 "AUC. Eras share band_stim_stability's boundaries."),
    }


# Audit [18]: per-week threshold-drift diagnostic gates.
DRIFT_MIN_SAMPLES_PER_WEEK = 6     # a week needs >= this many matched samples to yield a cut-point
DRIFT_MIN_WEEKS = 4                # need >= this many qualifying weeks to fit a calendar-time trend


def threshold_drift_by_week(td_detail, channel_raw, center_hz, *, band_width_hz=5.0,
                            strategy="tertile", low_pct=33.3333, high_pct=66.6667,
                            pain_cutoff=None):
    """Audit [18]: does the deployment cut-point DRIFT over calendar time?

    The deployment threshold is fit once on all data; if the optimal Youden cut-point moves
    systematically week-to-week (non-stationarity), a single fixed device threshold will be
    miscalibrated in later weeks. This buckets the matched samples by ELAPSED WEEK (the same index the
    offline random-intercept uses), computes each qualifying week's Youden cut-point under the POOLED
    orientation (so all weekly cut-points share one signed scale), and runs a trend test: OLS of weekly
    cut-point on week index. Drift is FLAGGED when the slope is significantly non-zero.

    A week qualifies only with >= DRIFT_MIN_SAMPLES_PER_WEEK matched samples AND both pain-high and
    pain-low present (a cut-point is otherwise undefined). The trend test needs >= DRIFT_MIN_WEEKS
    qualifying weeks; below that the diagnostic is 'not_assessed' (fail-closed — never a spurious flag
    from sparse weeks).

    Returns {available, status, n_weeks_qualifying, slope_per_week, slope_p, total_drift, drift_flag,
    weekly:[{week, threshold, n, prevalence}], pooled_threshold, note} or {available: False, reason}.
    status is one of 'stable' | 'drift_detected' | 'not_assessed'.
    """
    from sklearn import metrics
    feat = _band_feature_from_detail(td_detail, channel_raw, center_hz, band_width_hz)
    if feat is None:
        return {"available": False, "reason": f"channel {channel_raw} / band not found", "status": "not_assessed"}
    # No longer unused: the tertile cut below needs the rating identity (F12).
    bp_log, labels, rating_group, times = feat
    # F12: the tertile cut must reference the UNIQUE-RATING distribution, not the per-sample
    # vector. Without rating_group the cut point is itself pseudoreplicated — a rating with many
    # matched PSD rows drags the percentile toward its own value, so "high pain" and "low pain" get
    # defined partly by how often a rating happened to be sampled. The audit named deployment_roc;
    # the same omission was present in deployment_roc_by_era and threshold_drift_by_week.
    y_all = _binarize_labels(labels, strategy=strategy, low_pct=low_pct, high_pct=high_pct,
                             pain_cutoff=pain_cutoff, rating_group=rating_group)
    weeks_all = _elapsed_week_cluster(times, len(bp_log))
    m = np.isfinite(bp_log) & np.isfinite(y_all) & (weeks_all >= 0)
    if m.sum() < DRIFT_MIN_SAMPLES_PER_WEEK * 2 or len(np.unique(y_all[m])) < 2:
        return {"available": False, "reason": "too few matched samples for a drift assessment",
                "status": "not_assessed"}
    x = bp_log[m].astype(float)
    y = y_all[m].astype(int)
    wk = weeks_all[m].astype(int)

    # Orient ONCE on the pooled fit so every weekly cut-point is on the same signed scale.
    raw_auc = float(metrics.roc_auc_score(y, x))
    flip = raw_auc < 0.5
    use = -x if flip else x

    def _youden_cut(uu, yy):
        """Youden-J optimal cut-point on the oriented score; mapped back to the original log-power
        scale (rule power >= thr). None when a class is absent."""
        if len(np.unique(yy)) < 2:
            return None
        fpr, tpr, thr = metrics.roc_curve(yy, uu)
        j = tpr - fpr
        j[~np.isfinite(thr)] = -np.inf
        k = int(np.argmax(j))
        t = thr[k]
        if not np.isfinite(t):
            return None
        return float(-t if flip else t)

    pooled_thr = _youden_cut(use, y)

    weekly = []
    for w in np.unique(wk):
        sel = wk == w
        if int(sel.sum()) < DRIFT_MIN_SAMPLES_PER_WEEK:
            continue
        yy = y[sel]
        if len(np.unique(yy)) < 2:
            continue
        t = _youden_cut(use[sel], yy)
        if t is None:
            continue
        weekly.append({"week": int(w), "threshold": float(t), "n": int(sel.sum()),
                       "prevalence": float(np.mean(yy == 1))})

    n_weeks = len(weekly)
    if n_weeks < DRIFT_MIN_WEEKS:
        return {"available": True, "status": "not_assessed",
                "n_weeks_qualifying": int(n_weeks), "pooled_threshold": pooled_thr,
                "weekly": weekly, "slope_per_week": None, "slope_p": None, "total_drift": None,
                "drift_flag": False,
                "note": (f"Only {n_weeks} week(s) had >= {DRIFT_MIN_SAMPLES_PER_WEEK} matched samples "
                         f"with both classes (need >= {DRIFT_MIN_WEEKS}); calendar-time drift not "
                         f"assessed.")}

    # OLS trend test: weekly cut-point ~ week index. Significant non-zero slope = systematic drift.
    wks = np.array([d["week"] for d in weekly], dtype=float)
    thrs = np.array([d["threshold"] for d in weekly], dtype=float)
    from scipy import stats as _st
    lin = _st.linregress(wks, thrs)
    slope = float(lin.slope); slope_p = float(lin.pvalue)
    span = float(wks.max() - wks.min())
    total_drift = float(slope * span)
    drift_flag = bool(slope_p < 0.05 and np.isfinite(slope))
    status = "drift_detected" if drift_flag else "stable"
    verdict_txt = ("DRIFT DETECTED — a single fixed device threshold will be miscalibrated in later "
                   "weeks; consider periodic recalibration." if drift_flag else
                   "No significant calendar-time drift; the pooled cut-point is stationary over the "
                   "record.")
    _, _outl_drift = outlier_report_for_feature(bp_log, context="threshold_drift_by_week")
    return {"available": True, "status": status, "outliers": _outl_drift,
            "n_weeks_qualifying": int(n_weeks),
            "pooled_threshold": pooled_thr,
            "slope_per_week": slope, "slope_p": slope_p, "total_drift": total_drift,
            "week_span": span, "drift_flag": drift_flag,
            "weekly": weekly,
            "note": (f"Youden cut-point trend over {n_weeks} qualifying weeks "
                     f"(>= {DRIFT_MIN_SAMPLES_PER_WEEK} matched samples, both classes each). "
                     f"Slope {slope:+.3g}/week (p={slope_p:.3g}); total drift {total_drift:+.3g} over "
                     f"{span:.0f} weeks on the oriented log-power scale. " + verdict_txt),
            }


def deployment_forward_chaining(td_detail, channel_raw, center_hz, *, band_width_hz=5.0,
                                strategy="tertile", low_pct=33.3333, high_pct=66.6667,
                                pain_cutoff=None, min_train_clusters=8, test_block_weeks=1,
                                max_test_expand_weeks=4, n_boot=500, seed=0):
    """Expanding-window, blocked-by-week FORWARD-CHAINING validation for ONE committed (channel,
    band) — the held-out / out-of-sample companion to deployment_roc (audit C2).

    deployment_roc fits AND evaluates the AUC, the orientation, and the Youden operating point on
    one contiguous record, so every number it reports is in-sample. For a controller that will run
    forward in time the decision-relevant quantity is next-week performance: train on weeks 1..k,
    test on week k+1, never letting the future inform the threshold. This routine does exactly that.

    Anti-look-ahead discipline (the whole point):
      * Rating CLUSTERS (not raw samples) are the unit, assigned to a single elapsed-week by their
        earliest sample, so a cluster's near-duplicate PSDs never straddle the train/test boundary.
      * Within each fold the band's SIGN (flip) and the Youden THRESHOLD are estimated on the TRAIN
        clusters ALONE; the held-out clusters are scored with that fixed sign + threshold. Any
        look-ahead would inflate the held-out number, so none is permitted.
      * Test folds are NON-OVERLAPPING and strictly after their train window, so every held-out
        cluster is scored exactly once by a model that never saw it (out-of-fold). The per-fold
        oriented test scores are concatenated into one out-of-fold (OOF) vector and a single pooled
        held-out AUC is taken over it.
      * The held-out AUC is NOT re-folded (no max(auc, 1-auc)): it can honestly fall to or below 0.5
        when the train-fold sign does not generalize — the exact failure C1's de-fold also protects.

    Returns {available, n_folds, reliable, in_sample_auc, held_out_auc, held_out_auc_lo,
    held_out_auc_hi, held_out_auc_mean_fold, beats_chance_forward, held_out_sens, held_out_spec,
    optimism, n_test_clusters, n_test_samples, folds:[{test_week_start, n_train_clusters,
    n_test_clusters, train_auc, test_auc, sens, spec}], note} or {available: False, reason}.
    """
    from sklearn import metrics

    feat = _band_feature_from_detail(td_detail, channel_raw, center_hz, band_width_hz)
    if feat is None:
        return {"available": False, "reason": f"channel {channel_raw} / band not found in detail"}
    bp_log, labels, rating_group, times = feat
    # F12: the tertile cut must reference the UNIQUE-RATING distribution, not the per-sample
    # vector. Without rating_group the cut point is itself pseudoreplicated — a rating with many
    # matched PSD rows drags the percentile toward its own value, so "high pain" and "low pain" get
    # defined partly by how often a rating happened to be sampled. The audit named deployment_roc;
    # the same omission was present in deployment_roc_by_era and threshold_drift_by_week.
    y_all = _binarize_labels(labels, strategy=strategy, low_pct=low_pct, high_pct=high_pct,
                             pain_cutoff=pain_cutoff, rating_group=rating_group)
    m = np.isfinite(bp_log) & np.isfinite(y_all)
    if m.sum() < 12 or len(np.unique(y_all[m])) < 2:
        return {"available": False, "reason": "too few matched high/low samples for forward-chaining"}
    x = bp_log[m].astype(float)
    y = y_all[m].astype(int)
    g = np.asarray(rating_group)[m]
    t = np.asarray(times)[m]

    # Elapsed-week index per retained sample (same bucketing as the glmer's weekly random intercept).
    weeks = _elapsed_week_cluster(t, int(m.sum()))
    ok = weeks >= 0                            # drop unparseable-time rows (week == -1)
    if ok.sum() < 12:
        return {"available": False, "reason": "too few rows with parseable times for weekly folds"}
    x, y, g, weeks = x[ok], y[ok], g[ok], weeks[ok]

    # Assign each rating cluster to ONE week (its earliest), so a cluster is never split across folds.
    uniq_clusters = np.unique(g)
    cl_week = {c: int(np.min(weeks[g == c])) for c in uniq_clusters}
    cl_rows = {c: np.where(g == c)[0] for c in uniq_clusters}
    cl_y = {c: int(round(np.mean(y[cl_rows[c]]))) for c in uniq_clusters}   # cluster label (clusters are single-rating)
    present_weeks = sorted(set(cl_week.values()))
    if len(present_weeks) < 2:
        return {"available": False, "reason": "ratings span < 2 elapsed weeks; no forward split possible"}

    def _clusters_with(pred):
        return [c for c in uniq_clusters if pred(cl_week[c])]

    def _both_classes(clusters):
        labs = {cl_y[c] for c in clusters}
        return len(labs) >= 2

    # ---- expanding-window walk over weeks: train = all clusters strictly before the test block ----
    folds = []
    oof_score, oof_y, oof_cluster = [], [], []
    oof_cluster_ids = []
    wi = 0
    nW = len(present_weeks)
    while wi < nW:
        test_start = present_weeks[wi]
        train_clusters = _clusters_with(lambda w: w < test_start)
        # Need a usable training set before we can validate forward at all.
        if len(train_clusters) < int(min_train_clusters) or not _both_classes(train_clusters):
            wi += 1
            continue
        # Grow the test block forward (week by week) until it carries both classes or hits the cap.
        wj = wi
        test_clusters = []
        while wj < nW and (present_weeks[wj] - test_start) <= int(max_test_expand_weeks) - 1:
            lo, hi = test_start, present_weeks[wj]
            test_clusters = _clusters_with(lambda w: lo <= w <= hi)
            if (wj - wi + 1) >= int(test_block_weeks) and _both_classes(test_clusters):
                break
            wj += 1
        if not test_clusters or not _both_classes(test_clusters):
            wi = wj + 1
            continue

        tr_rows = np.concatenate([cl_rows[c] for c in train_clusters])
        te_rows = np.concatenate([cl_rows[c] for c in test_clusters])
        xtr, ytr = x[tr_rows], y[tr_rows]
        xte, yte = x[te_rows], y[te_rows]
        # Orient + pick the Youden threshold on TRAIN ONLY.
        raw_tr = float(metrics.roc_auc_score(ytr, xtr))
        flip = raw_tr < 0.5
        s_tr = -xtr if flip else xtr
        s_te = -xte if flip else xte                       # SAME sign carried to the held-out fold
        fpr, tpr, thr = metrics.roc_curve(ytr, s_tr)
        finite = np.isfinite(thr)
        jvals = np.where(finite, tpr - fpr, -np.inf)
        thr_op = float(thr[int(np.argmax(jvals))])
        # Score the held-out fold with the fixed train sign + threshold.
        pred = (s_te >= thr_op).astype(int)
        sens, spec = _sens_spec(yte, pred)
        test_auc = float(metrics.roc_auc_score(yte, s_te))  # NOT re-folded: honest, can be < 0.5
        folds.append({
            "test_week_start": int(test_start),
            "n_train_clusters": int(len(train_clusters)),
            "n_test_clusters": int(len(test_clusters)),
            "train_auc": float(max(raw_tr, 1.0 - raw_tr)),
            "test_auc": test_auc,
            "sens": None if sens is None or not np.isfinite(sens) else float(sens),
            "spec": None if spec is None or not np.isfinite(spec) else float(spec),
        })
        oof_score.append(s_te); oof_y.append(yte)
        # Give every held-out cluster a globally-unique id so the held-out-AUC bootstrap resamples
        # independent ratings (te_rows preserves the per-cluster row order of `test_clusters`).
        base_id = len(oof_cluster_ids)
        oof_cluster.append(np.repeat(np.arange(base_id, base_id + len(test_clusters)),
                                     [len(cl_rows[c]) for c in test_clusters]))
        oof_cluster_ids.extend(range(base_id, base_id + len(test_clusters)))
        wi = wj + 1                                        # non-overlapping: advance past this block

    if not folds:
        return {"available": False,
                "reason": f"no forward fold met the {int(min_train_clusters)}-train-cluster / both-class floor"}

    oof_score = np.concatenate(oof_score)
    oof_y = np.concatenate(oof_y)
    oof_cluster = np.concatenate(oof_cluster)
    # In-sample oriented AUC (the deployment_roc number) for the side-by-side comparison.
    raw_all = float(metrics.roc_auc_score(y, x))
    in_sample_auc = float(max(raw_all, 1.0 - raw_all))

    held_out_auc = None
    held_out_auc_lo = held_out_auc_hi = None
    if len(np.unique(oof_y)) >= 2:
        held_out_auc = float(metrics.roc_auc_score(oof_y, oof_score))
        # Cluster bootstrap CI on the pooled held-out AUC: resample WHOLE held-out clusters so the
        # CI reflects the count of independent held-out ratings, then percentile 2.5/97.5. The gate
        # downstream requires this lower bound to clear chance ("CI clears 0.5").
        rng = np.random.default_rng(seed)
        uoc = np.unique(oof_cluster)
        rows_by = {c: np.where(oof_cluster == c)[0] for c in uoc}
        boot = []
        for _b in range(int(n_boot)):
            pick = rng.choice(uoc, size=len(uoc), replace=True)
            idx = np.concatenate([rows_by[c] for c in pick])
            yb = oof_y[idx]
            if len(np.unique(yb)) < 2:
                continue
            try:
                boot.append(float(metrics.roc_auc_score(yb, oof_score[idx])))
            except ValueError:
                continue
        if len(boot) >= BOOT_CI_VALID_FLOOR:   # audit [3]-floor: was 20
            held_out_auc_lo = float(np.percentile(boot, 2.5))
            held_out_auc_hi = float(np.percentile(boot, 97.5))

    # Pooled held-out sens/spec averaged across folds at each fold's train operating point.
    held_out_sens = held_out_spec = None
    n_pos = int(np.sum(oof_y == 1)); n_neg = int(np.sum(oof_y == 0))
    fold_sens = [f["sens"] for f in folds if f["sens"] is not None]
    fold_spec = [f["spec"] for f in folds if f["spec"] is not None]
    if fold_sens:
        held_out_sens = float(np.mean(fold_sens))
    if fold_spec:
        held_out_spec = float(np.mean(fold_spec))

    mean_fold_auc = float(np.mean([f["test_auc"] for f in folds]))
    n_folds = len(folds)
    reliable = bool(n_folds >= 2 and len(np.unique(oof_cluster)) >= int(min_train_clusters))
    beats_chance_forward = bool(held_out_auc_lo is not None and held_out_auc_lo > 0.5)

    _, _outl_fc = outlier_report_for_feature(bp_log, context="deployment_forward_chaining")
    return {
        "available": True, "outliers": _outl_fc,
        "n_folds": n_folds,
        "reliable": reliable,
        "in_sample_auc": in_sample_auc,
        "held_out_auc": held_out_auc,
        "held_out_auc_lo": held_out_auc_lo,
        "held_out_auc_hi": held_out_auc_hi,
        "held_out_auc_mean_fold": mean_fold_auc,
        "beats_chance_forward": beats_chance_forward,
        "held_out_sens": held_out_sens,
        "held_out_spec": held_out_spec,
        "optimism": (None if held_out_auc is None else float(in_sample_auc - held_out_auc)),
        "n_test_clusters": int(len(np.unique(oof_cluster))),
        "n_test_samples": int(oof_y.size),
        "n_pos_test": n_pos, "n_neg_test": n_neg,
        "folds": folds,
        "ci_method": "held-out-cluster bootstrap (de-folded; train-fold orientation fixed)",
        "note": (f"Expanding-window forward-chaining over {n_folds} non-overlapping weekly test "
                 f"folds. Orientation and the Youden threshold are fit on the TRAIN weeks only and "
                 f"applied to the held-out future weeks, so the held-out AUC is genuinely "
                 f"out-of-sample and is NOT re-folded (it can fall below 0.5 when the band does not "
                 f"generalize forward). The held-out-AUC CI is a cluster bootstrap over independent "
                 f"held-out ratings; 'forward-validated' requires its lower bound to clear 0.5. "
                 f"Compare held_out_auc against in_sample_auc to read the forward optimism."),
    }


ADC_NV_PER_LSB = 146.0   # Percept time-domain ADC scale (nV per LSB), exact per Medtronic.


# Percept RC adaptive threshold modes — verified from Medtronic white paper UC202012929dEN (FY25),
# Table 1, p.14, and cross-checked against DESIGN_biomarker_pipeline_v2.md §1. The FFT SIZE is the
# load-bearing field for calibration: "LFP Power" is the sum of squared FFT magnitude over the sensed
# band, so a different FFT size integrates a DIFFERENT set of frequency bins (bin width = fs / N_fft;
# 250/256 ≈ 0.98 Hz for 256-pt vs 250/64 ≈ 3.91 Hz for 64-pt). The white paper (p.9) states outright
# that "LFP Power values collected in differing threshold modes should not be directly compared." A
# k (LSB-per-µV²) fit on 256-pt data is therefore INVALID for 64-pt Single Threshold data — the band
# is not the same quantity. `averaging_ms` is (adaptive, sensing-only) — the controller uses the
# adaptive value; our streaming calibration is recorded in the sensing-only value and adjusted.
THRESHOLD_MODES = {
    "Dual": {
        "label": "Dual Threshold",
        "fft_size": 256,
        "fft_update_hz": (5.0, 2.0),       # (adaptive, sensing-only)
        "averaging_ms": (1200.0, 3000.0),  # (adaptive, sensing-only)
        "onset_ms": 1200.0,
        "blanking_ms": 2000.0,
        "adaptive": True,
        "reaction": "minutes",
        "adaptive_band_hz": (8.0, 30.0),
    },
    "Single": {
        "label": "Single Threshold",
        "fft_size": 64,                    # <-- DIFFERENT FFT size: NOT calibration-compatible with 256-pt
        "fft_update_hz": (20.0, 2.0),
        "averaging_ms": (100.0, 1000.0),
        "onset_ms": 200.0,
        "blanking_ms": 550.0,
        "adaptive": True,
        "reaction": "milliseconds",
        "adaptive_band_hz": (8.0, 30.0),
    },
    "SingleInverse": {
        "label": "Single Threshold Inverse",
        "fft_size": 256,
        "fft_update_hz": (2.0, 2.0),       # sensing-only mode (no adaptive actuation)
        "averaging_ms": (3000.0, 3000.0),
        "onset_ms": None,
        "blanking_ms": None,
        "adaptive": False,                 # Sensing Only — review against a threshold, no stim change
        "reaction": "n/a",
        "adaptive_band_hz": (1.0, 96.0),   # sensing range
    },
}
# Calibration compatibility: our PSD/TD→LSB conversion is built from 256-pt-equivalent band integrals
# (chronic Timeline + 3000 ms streaming both use 256-pt FFT). Modes that share fft_size==256 can use
# that k directly; the 64-pt Single Threshold mode cannot and must be flagged as un-translatable.
CONVERSION_FFT_SIZE = 256
COMPATIBLE_THRESHOLD_MODES = tuple(m for m, v in THRESHOLD_MODES.items()
                                   if v["fft_size"] == CONVERSION_FFT_SIZE)  # ("Dual","SingleInverse")


# ── TD→LSB conversion routes (PI decision 2026-06-27, HANDOFF_TD_LSB_calibration_2026-06-27.md) ──
# The PRIMARY TD→LSB source of truth is the **transform route, k = LSB_PER_UV2_TRANSFORM = 352.62**
# (below); the PSD-only no-TD case uses the **device-PSD bridge, LSB_PER_DEVICE_PSD = 73.63** (CS-3,
# below). The deployment fallback ladder anchors an offline-Welch µV² cut-point to LSB via the
# per-participant frozen PSD→LSB model (psd_lsb_model.estimate_lsb), which is itself fit on the SAME
# offline-Welch µV²→device-LSB mapping (RCS08.json), so the cut-point and the converter share units.
#
# REMOVED 2026-06-28: the standalone Welch-256 population constant k=269 (LSB_PER_UV2_VALIDATED /
# UV2_PER_LSB_VALIDATED / LSB_UV2_LOGLOG_SLOPE) and its converters lsb_from_uv2 / uv2_from_lsb, plus
# the Welch-256 DSP helpers psd_band_to_lsb / welch256_density (all without a production caller after
# the bridge + frozen-model rewire). The deployment last-resort population-constant TIER was retired:
# when neither a native device threshold nor a frozen per-participant model entry exists, the modeled
# threshold is now returned as indeterminate (fail-closed) rather than a population-average guess.
# 146 nV/LSB (ADC_NV_PER_LSB) remains the exact time-domain count scale — a DISTINCT quantity from the
# power-domain band-power LSB the conversion routes above produce.
MODELED_LSB_SIGMA_FOLD = 1.26          # 1σ multiplicative scatter of the modeled-LSB conversion (±band
                                       # on TIER-1/TIER-2 estimates; per-participant resid_log_sigma_fold
                                       # overrides it when the frozen model carries one)
# Frequency range over which the PSD→LSB gain is actually calibrated on RCS08 paired blocks.
# Outside this range the conversion (whether the population k or a per-band model intercept) is an
# UNTESTED EXTRAPOLATION — the device gain anchor is not band-flat (it falls ≈0.80 log10/decade
# within range), so a request at e.g. 55.5 Hz high-gamma snapped to the nearest fitted band (26.4 Hz)
# would mis-state the LSB threshold by ≈1.7× if the in-range trend continues. Callers must flag any
# estimate whose center frequency lands outside [LSB_VALIDATED_HZ_LO, LSB_VALIDATED_HZ_HI].
LSB_VALIDATED_HZ_LO = 7.8
LSB_VALIDATED_HZ_HI = 28.3

# ── transform route — PRIMARY TD→LSB source of truth (PI decision 2026-06-27) ─────────────────────
# k for the percept-spectral-repro "transform" DSP (RC+S-Hann / 256-pt zero-padded FFT / peak-
# amplitude / mean-magnitude band power), reproduced bit-for-bit on the user's Stage-1 RCS08 JSONs:
# all-stim median k = 352.62, r = 0.9927, RMSE 60.6 LSB (see HANDOFF_TD_LSB_calibration_2026-06-27.md,
# transform_3s_blocks.csv). This is the deployable + exploratory TD→LSB constant. The stim-off variant
# (356.61) is recorded for provenance ONLY and is NOT deployed — use 352.62 exactly, do not round.
# k is multiplicative on a LOG band-power feature, so within a SINGLE-SOURCE feature (every point
# scaled by the same k) it CANCELS inside Pearson r / AUC — the correlation/AUC panels are identical
# whether k is 269, 352.62, or 1. SCOPE: this holds only when the feature column is homogeneous in k.
# It does NOT hold for a feature that POOLS native device LSB (raw units, no k) with modeled points
# (k=352.62) on the same axis — there, raising modeled k from 269→352.62 shifts only the modeled
# subset by +log(352.62/269)≈+0.272 relative to native, which CAN move r/AUC. The native-preferred
# masking (is_modeled) keeps modeled points out of the deployable threshold and the measured-r path, so
# no mixed feature reaches a correlation; test_k_cancels_in_correlation_and_auc pins the single-source
# case and test_modeled_excluded_from_native_correlation_path pins the segregation. k matters only for
# (a) the absolute LSB values displayed and (b) the deployable LSB threshold — which is why switching
# the exploration TD path from welch256×269 to transform×352.62 moves the displayed scale to the
# lab-consistent value WITHOUT moving any r/AUC result.
LSB_PER_UV2_TRANSFORM = 352.62         # k, transform route — RCS08 all-stim median; PRIMARY TD→LSB
# Device adaptive-sensing ceiling. Distinct from LSB_VALIDATED_HZ_HI (28.3 Hz = where paired-block
# CALIBRATION ground truth exists, used by the extrapolation guard _freq_extrapolated). 30 Hz is the
# firmware HARD limit on where an adaptive sensing band can be placed: a deployable modeled LSB is
# offered only in [LSB_VALIDATED_HZ_LO, LSB_DEPLOYABLE_HZ_HI]; the 0–100 Hz exploration sweep is not
# band-restricted (k cancels in r/AUC; displayed LSB is illustrative). Keep these two bounds separate —
# 28.3 is a data-coverage fact, 30.0 is a device-capability fact; do not collapse them.
# NOTE (CS-1): FORWARD DECLARATION — no code reads this yet. CS-2 wires the [LO, 30.0] band gate on the
# deployable modeled path; until then this constant only documents the intended invariant.
LSB_DEPLOYABLE_HZ_HI = 30.0


# ── PSD→LSB BRIDGE (CS-3) — for PSD-ONLY patient-triggered snapshot events ───────────────────────────
# The device emits a frequency-domain "onboard FFT" magnitude spectrum on its montage surveys
# (Descriptor.MedtronicPSD[].LFPMagnitude, linear µV, 0 negatives) AND on patient-triggered LFP
# snapshot events (PatientControllerEvent metadata FFTBinData, same linear-µV unit but baseline-
# subtracted so ~1/3 of bins read slightly negative). Patient events carry NO time-domain, so they
# cannot use the direct TD→LSB transform; this bridge converts their device-PSD band power to LSB.
#
# Derivation (RCS08, 2026-06-27 — CS3_FFTBinData_units_recon doc + paired montage fit, n=10476
# contact-band points across 219 surveys; ps-statsmodels rigor):
#   1. UNITS: event FFTBinData ≡ survey LFPMagnitude (same linear-µV onboard-FFT magnitude). Paired
#      log-log slope 1.0 (CI brackets ~1), proportionality ≈1.04 — i.e. identity after clamping the
#      negative (sub-noise-floor) bins to 0. So both device-PSDs use ONE band-power definition:
#      bp = Σ(in-band magnitude)²  (negatives clamped first).
#   2. MONTAGE TD↔PSD LAW: on surveys (TD + device-PSD on the SAME recording), device-PSD band power is
#      proportional to the TD-transform band power: PSD_bp = K_TD_PSD · TD_bp, K_TD_PSD = 4.789
#      (geomean, 95% CI [4.772, 4.806]; slope 1.022, r=0.987; offset 6.80 dB ≈ the onboard-FFT-vs-Welch
#      ~6 dB note; per-contact K 4.73–4.87, fold 1.22× < the 1.26× calibration scatter).
#   3. COMPOSE: TD→LSB is LSB = LSB_PER_UV2_TRANSFORM · TD_bp (= 352.62 · TD_bp). Substituting
#      TD_bp = PSD_bp / K_TD_PSD gives LSB = (352.62 / 4.789) · PSD_bp = K_PSD_LSB · PSD_bp.
# End-to-end check on montage (LSB via this bridge vs direct TD→LSB): geomean fold 1.000 (unbiased),
# scatter 1.21×, r=0.987. The bridge reproduces the direct transform to within calibration scatter.
#
# Apply ONLY to PSD-only patient-triggered snapshot events. Montage/survey/snapshot products carry their
# own TD and MUST use td_to_lsb (k=352.62) directly — they are this bridge's CALIBRATION SOURCE, never
# a consumer of it. The event PSD must be negative-clamped (clamp_device_psd) before band-integration.
LSB_PER_UV2_DEVICE_PSD_TD_RATIO = 4.789   # K_TD_PSD: device-PSD band power / TD-transform band power
LSB_PER_DEVICE_PSD = LSB_PER_UV2_TRANSFORM / LSB_PER_UV2_DEVICE_PSD_TD_RATIO  # K_PSD_LSB ≈ 73.63


def _freq_extrapolated(center_hz, lo=LSB_VALIDATED_HZ_LO, hi=LSB_VALIDATED_HZ_HI):
    """True iff center_hz is outside the validated [7.8, 28.3] Hz calibration range (None -> False).

    Mirrors psd_lsb_model._freq_extrapolated so the deployment fallback and the frozen per-band model
    share ONE definition of "outside the calibrated range". Kept module-local (vs imported) to avoid
    a routines->routines import cycle; the two constants are asserted equal by test.
    """
    try:
        c = float(center_hz)
    except (TypeError, ValueError):
        return False
    if not np.isfinite(c):
        return False
    return bool(c < float(lo) or c > float(hi))


# Default sliding-window geometry for the transform DSP (the PRIMARY TD→LSB route). A 1-second
# (TRANSFORM_WIN_SECONDS) rcs-Hann window, zero-padded to 256 points, is the percept-spectral-repro
# "transform" unit; the repo reproduction slides it NON-overlapping (step = win). The deployed
# per-PRO sweep slides it at TRANSFORM_STEP_SECONDS = 0.5 s (50% overlap) across a ~30 s rating-
# centered extent and takes the median band power, which only reduces estimator variance (the 50%-
# vs non-overlap median band power agrees to ≪ the 1.26× calibration scatter — verified on RCS08).
TRANSFORM_N_FFT = 256
TRANSFORM_WIN_SECONDS = 1.0
TRANSFORM_STEP_SECONDS = 0.5
TRANSFORM_MAX_FREQ_HZ = 96.68          # repo percept_frequency_bins ceiling (bins ≤ this are kept)


def _rcs_hann(nonzero):
    """RC+S Hann taper over `nonzero` samples: 0.5*(1 - cos(2πn/nonzero)). Verbatim from
    percept-spectral-repro (note the period is `nonzero`, NOT nonzero-1 — matches the device)."""
    n = np.arange(int(nonzero))
    return 0.5 * (1.0 - np.cos(2.0 * np.pi * n / float(nonzero)))


def td_transform_band_power(samples_uv, fs, center_hz, *, half_hz=2.5,
                            win_samples=None, step_samples=None,
                            n_fft=TRANSFORM_N_FFT, maxf=TRANSFORM_MAX_FREQ_HZ, agg="median"):
    """Transform-DSP band power (µV²) of a time-domain µV trace — the PRIMARY TD→LSB front end.

    This is the percept-spectral-repro "transform": per sliding sub-window, mean-detrend → rcs-Hann
    taper over `win_samples` nonzero samples → ZERO-PAD to `n_fft` → rFFT → peak scale (2/n_fft) →
    magnitude → band power = sum of squared magnitudes over [center−half_hz, center+half_hz].
    Aggregated (median, default) across sub-windows. This is a Hann-windowed zero-padded FFT, **not**
    Welch — do not confuse with welch256_density. A NON-overlapping call (step == win) reproduces the
    lab repo bit-for-bit (k=352.62, r=0.9927); the deployed sweep passes a 50%-overlap step.

    Fully vectorized: one strided window matrix → ONE batched rFFT over all windows → one band-mask
    matmul over all requested centers → median across the window axis. No per-window or per-band loop,
    so the whole 0–100 Hz / 1 Hz-step sweep shares a single rFFT per extent.

    Parameters
    ----------
    samples_uv : array-like
        1-D time-domain trace in µV (non-finite samples are dropped first).
    fs : float
        Sampling rate (Hz). win/step default to 1 s / 1 s in samples when not given.
    center_hz : float or array-like
        Band center(s) in Hz. Scalar in → float out; array in → ndarray out (shared FFT).
    half_hz : float, default 2.5
        Half-bandwidth; the band is [center−half, center+half] (≈5 Hz device band).
    win_samples, step_samples : int, optional
        Window length / hop in SAMPLES. Defaults: win = round(fs*TRANSFORM_WIN_SECONDS) (=250 @ 250
        Hz), step = win (non-overlapping). Pass step = round(fs*TRANSFORM_STEP_SECONDS) for 50% overlap.
    n_fft : int, default 256
        Zero-pad / FFT length. The k=352.62 calibration assumes 256.
    maxf : float, default 96.68
        Keep only FFT bins ≤ maxf (the repo's percept_frequency_bins ceiling).
    agg : {"median","mean","none"}, default "median"
        Across-window aggregation. The repo and the deployed sweep both use the median. "none" returns
        the PER-WINDOW band power without aggregating — shape (W,) for a scalar center, (W, C) for a
        vector center — for the sliding-window overlay / within-window QC (CS-4). The window start
        times are `arange(0, n-win+1, step)`.

    Returns
    -------
    float (scalar center) or ndarray (vector center) of band power in µV² for agg in {median,mean}.
    For agg="none": ndarray of per-window band power, (W,) scalar-center or (W, C) vector-center.
    NaN / all-NaN when the trace has fewer than `win_samples` finite samples (the 1-window / 1-second
    minimum), or when win > n_fft / fs<=0. A center whose band lies entirely ABOVE `maxf` (≈96.68 Hz)
    has no kept bins and returns ~0 BY DESIGN (td_to_lsb then maps it to NaN via its >0 guard) — read
    that as out-of-range, not a real null.
    """
    v = np.asarray(samples_uv, dtype=float)
    v = v[np.isfinite(v)]
    fs = float(fs)
    scalar_in = np.ndim(center_hz) == 0
    centers = np.atleast_1d(np.asarray(center_hz, dtype=float))
    win = int(win_samples) if win_samples else int(round(fs * TRANSFORM_WIN_SECONDS))
    step = int(step_samples) if step_samples else win
    # win > n_fft would overflow the zero-pad buffer (buf[:, :win] broadcast error). At the percept
    # 250 Hz TD, win=250 < 256, so this never triggers in production; the guard keeps the scalar-in ->
    # NaN-out contract intact for an unexpected fs (>256) instead of raising.
    if win <= 0 or step <= 0 or fs <= 0 or win > n_fft or v.size < win:
        nan = float("nan")
        if agg == "none":
            # no windows -> empty per-window series (preserve center axis for vector centers)
            return np.empty((0,), dtype=float) if scalar_in else np.empty((0, centers.size), dtype=float)
        return nan if scalar_in else np.full(centers.size, nan)

    # Strided window matrix (W, win): one row per sub-window. No Python loop over windows.
    starts = np.arange(0, v.size - win + 1, step)
    M = v[starts[:, None] + np.arange(win)[None, :]]
    M = M - M.mean(axis=1, keepdims=True)                  # per-window mean detrend
    buf = np.zeros((M.shape[0], n_fft), dtype=float)
    buf[:, :win] = M * _rcs_hann(win)[None, :]             # rcs-Hann taper + zero pad
    mag = 2.0 * np.abs(np.fft.rfft(buf, n=n_fft, axis=-1)) / n_fft   # ONE batched rFFT (W, n_fft//2+1)
    freqs = np.round(np.arange(n_fft // 2 + 1) * fs / n_fft, 2)
    if maxf is not None:
        keep = freqs <= float(maxf) + 1e-9
        mag = mag[:, keep]; freqs = freqs[keep]
    p2 = mag ** 2                                          # (W, Fb) squared magnitudes
    # Band-mask matrix (C, Fb); one matmul → in-band summed power for every center at once.
    band = ((freqs[None, :] >= centers[:, None] - half_hz) &
            (freqs[None, :] <= centers[:, None] + half_hz)).astype(float)
    pw = p2 @ band.T                                       # (W, C)
    if agg == "none":
        # per-window band power, no aggregation (sliding-window overlay / QC). (W,) scalar, (W,C) vector.
        return pw[:, 0] if scalar_in else pw
    out = (np.median(pw, axis=0) if agg == "median" else np.mean(pw, axis=0))
    return float(out[0]) if scalar_in else out


TRANSFORM_CENTERED_EXTENT_SECONDS = 30.0   # rating-centered TD extent fed to the per-PRO LSB sweep
# Tile width for the match-AGNOSTIC raw LSB cache (availability.raw_lsb_spectrum_cache). The whole
# recording is sliced into fixed RAW_LSB_WINDOW_SECONDS non-overlapping tiles, INDEPENDENT of any PRO;
# each tile's LSB is the validated 1 s-Hann/256-FFT transform (k=352.62) median across its internal
# 50%-overlap sub-windows. Matching (median of the tiles falling inside a rating-centered extent) is
# done LIVE downstream, not baked into this cache. 3 s holds ~5 sub-windows per tile.
RAW_LSB_WINDOW_SECONDS = 3.0


def transform_centered_window(samples_uv, fs, center_offset_s, *,
                              extent_s=TRANSFORM_CENTERED_EXTENT_SECONDS,
                              missing=None, max_missing_frac=0.10):
    """Cut the rating-centered TD extent for the per-PRO transform LSB sweep (CS-2 consumer).

    For a PRO whose timestamp sits `center_offset_s` seconds into this recording, return the slice of
    `samples_uv` spanning [center − extent_s/2, center + extent_s/2], CLIPPED to the recording bounds
    (asymmetric near an edge; never slid across into padding) — i.e. 30 s centered on the rating, or
    "whatever's available" when the recording is shorter. The caller then runs td_transform_band_power
    / td_to_lsb on the returned slice with a 50%-overlap step (step_samples = round(fs*
    TRANSFORM_STEP_SECONDS)); the transform's own ≥1-window rule enforces the 1 s minimum.

    Mirrors streaming_psd.welch_rating_centered's clip-don't-slide contract and its >max_missing_frac
    Missing rejection (FixBreaking zero-fill protection), but for the transform DSP rather than Welch.

    Returns (slice_uv, used_seconds) or (None, 0.0) when the clipped extent is below one transform
    window or is more than `max_missing_frac` Missing.
    """
    v = np.asarray(samples_uv, dtype=float)
    fs = float(fs)
    n = v.size
    win = int(round(fs * TRANSFORM_WIN_SECONDS))
    if n < win or fs <= 0:
        return None, 0.0
    half = int(round(extent_s * fs / 2.0))
    ci = int(round(float(center_offset_s) * fs))
    lo = max(0, ci - half)
    hi = min(n, ci + half)
    if hi - lo < win:
        return None, 0.0
    if missing is not None:
        miss = np.asarray(missing, dtype=float).ravel()
        # FAIL CLOSED on a malformed mask: a missing array that does not cover the cut span cannot be
        # trusted to certify the window clean (a short/misaligned FixBreaking mask would otherwise skip
        # the rejection and pass possibly-corrupt samples downstream). Drop the window instead.
        if miss.size < hi:
            return None, 0.0
        frac = float(np.mean(miss[lo:hi] > 0))
        if frac > float(max_missing_frac):
            return None, 0.0
    return v[lo:hi], (hi - lo) / fs


def td_to_lsb(samples_uv, fs, center_hz, *, half_hz=2.5, k=LSB_PER_UV2_TRANSFORM, **win_kw):
    """PRIMARY TD→LSB: device power-domain LSB from a time-domain µV trace via the transform DSP ×
    k (default LSB_PER_UV2_TRANSFORM = 352.62). One helper, one constant, used by both the Biomarker
    exploration panels and the deployment modeled fallback. `win_kw` forwards win_samples/step_samples/
    agg to td_transform_band_power (pass step_samples for the 50%-overlap deployed sweep). Returns
    float LSB (or ndarray for a vector center); NaN where the band power is NaN/non-positive."""
    uv2 = td_transform_band_power(samples_uv, fs, center_hz, half_hz=half_hz, **win_kw)
    arr = np.atleast_1d(np.asarray(uv2, dtype=float))
    lsb = np.where(np.isfinite(arr) & (arr > 0), float(k) * arr, np.nan)
    return float(lsb[0]) if np.ndim(uv2) == 0 else lsb


def clamp_device_psd(magnitude):
    """Reconcile a device onboard-FFT magnitude spectrum into the linear-µV frame the bridge expects.

    The device's montage-survey PSD (LFPMagnitude) is already linear µV with no negatives; the
    patient-event PSD (FFTBinData) is the SAME unit but baseline-subtracted, so sub-noise-floor bins
    read slightly negative (down to about −1 quantum). Clamping those to 0 puts both on the same linear
    magnitude footing (CS3_FFTBinData_units recon: paired FFTBinData↔LFPMagnitude slope≈1, ratio≈1.04).
    Returns a float ndarray with negatives set to 0; NaNs preserved."""
    m = np.asarray(magnitude, dtype=float)
    return np.where(m < 0, 0.0, m)


def device_psd_band_power(freq, magnitude, center_hz, *, half_hz=2.5):
    """Band power of a device onboard-FFT magnitude spectrum over [center±half_hz], in the SAME
    definition as td_transform_band_power: Σ(in-band magnitude)² after negative-clamping, with the
    band edges inclusive on both sides exactly as that function masks them (so the K_TD_PSD ratio the
    bridge composes is measured between commensurable band-power definitions). Vectorized: one
    band-mask sum over all centers, no per-center Python loop. Works for a scalar center (→ float) or
    a vector of centers (→ ndarray). NaN if no in-band bin."""
    f = np.asarray(freq, dtype=float)
    m = clamp_device_psd(magnitude)
    c = np.atleast_1d(np.asarray(center_hz, dtype=float))
    finite = np.isfinite(m)
    p2 = np.where(finite, m, 0.0) ** 2                       # squared clamped in-band magnitudes
    # Band-mask matrix (C, Fb); one masked sum -> in-band power for every center at once. Edges
    # [center-half, center+half] INCLUSIVE on both sides, IDENTICAL to td_transform_band_power's
    # mask (the bridge's calibration partner) so the two sides stay commensurable at the band edge.
    band = ((f[None, :] >= c[:, None] - half_hz) &
            (f[None, :] <= c[:, None] + half_hz) & finite[None, :])
    out = np.where(band.any(axis=1), (band * p2[None, :]).sum(axis=1), np.nan)
    return float(out[0]) if np.ndim(center_hz) == 0 else out


def device_psd_to_lsb(freq, magnitude, center_hz, *, half_hz=2.5, k=LSB_PER_DEVICE_PSD):
    """PSD→LSB BRIDGE (CS-3): device power-domain LSB from a PSD-ONLY patient-triggered snapshot event's
    onboard-FFT magnitude spectrum (Frequency + FFTBinData), via device_psd_band_power × k
    (default LSB_PER_DEVICE_PSD ≈ 73.63 = LSB_PER_UV2_TRANSFORM / LSB_PER_UV2_DEVICE_PSD_TD_RATIO).

    Use ONLY for PSD-only patient events (no TD). Montage/survey/snapshot products carry TD → td_to_lsb.
    Returns float LSB (or ndarray for a vector center); NaN where band power is NaN/non-positive."""
    pbp = device_psd_band_power(freq, magnitude, center_hz, half_hz=half_hz)
    arr = np.atleast_1d(np.asarray(pbp, dtype=float))
    lsb = np.where(np.isfinite(arr) & (arr > 0), float(k) * arr, np.nan)
    return float(lsb[0]) if np.ndim(center_hz) == 0 else lsb


def empirical_lsb_ratio(td_recs, pd_recs, sensing_hz_for_pd, *, adc_nv_per_lsb=ADC_NV_PER_LSB,
                        band_half_hz=2.5, stim_off_mA=0.1, pair_tol_s=5.0, min_secs=5.0):
    """Measure the empirical µV²-per-LSB conversion from CONCURRENT on-demand streaming TD + device
    PowerDomain LSB (DESIGN §4). For each BrainSense TD streaming session paired (within pair_tol_s)
    to a PowerDomain session, compute the band-power in µV² from the raw 250 Hz TD (Welch, integrated
    over the device's sensing band) and the median device LSB over the same window/channel at near-
    zero stim, then take µV²/LSB per (session, channel).

    This is a CONFIDENCE-RATED FYI cross-check, NOT the deployable threshold. NOTE: a later paired-
    block validation (BrainSenseLfp + BrainSenseTimeDomain on the SAME signal, 50 RCS08 stim-off
    blocks) pinned the µV²↔LSB scatter far more tightly than the "~3×" caveat once suggested (R² 0.94,
    CV fold-error 1.19×). The absolute ratio is still normalization-dependent, so the deployable
    threshold remains percentile-anchored on the device's own Timeline LSB (see the service layer);
    an offline µV² cut-point is translated to LSB only via the per-participant frozen PSD→LSB model
    (psd_lsb_model.estimate_lsb) on bands the device never sensed natively. `sensing_hz_for_pd(pd_rec, contact)` resolves a PowerDomain
    recording's sensing center frequency for a contact (the TD recording itself carries no Therapy
    snapshot).

    Returns {available, n, median, iqr_lo, iqr_hi, cv, p10, p90, fold_off_rule, rule_of_thumb,
             confidence, note} or {available: False, reason}.
    """
    try:
        from scipy import signal as _sig
    except Exception as e:
        return {"available": False, "reason": f"scipy unavailable: {e}"}

    def _epoch(r):
        st = r.get("StartTime")
        try:
            return float(st)
        except (TypeError, ValueError):
            return None

    pd_idx = {}
    for r in pd_recs or []:
        s = _epoch(r)
        if s is not None:
            pd_idx.setdefault(round(s), []).append(r)

    def _find_pd(s):
        base = round(s)
        for d in range(-int(pair_tol_s), int(pair_tol_s) + 1):
            if base + d in pd_idx:
                return pd_idx[base + d]
        return []

    ratios = []
    for tr in td_recs or []:
        s = _epoch(tr)
        if s is None:
            continue
        pds = _find_pd(s)
        if not pds:
            continue
        chans = tr.get("ChannelNames") or []
        data = np.asarray(tr.get("Data"), dtype=float)
        fs = float(tr.get("SamplingRate") or 250.0)
        if data.ndim != 2:
            continue
        for ci, ch in enumerate(chans):
            if ci >= data.shape[1]:
                continue
            hz = None
            for pr in pds:
                hz = sensing_hz_for_pd(pr, ch)
                if hz is not None:
                    break
            if hz is None:
                continue
            x = data[:, ci] * adc_nv_per_lsb / 1000.0    # device counts -> µV (nV/1000)
            x = x[np.isfinite(x)]
            if len(x) < fs * min_secs:
                continue
            f, P = _sig.welch(x, fs=fs, nperseg=int(fs))   # µV²/Hz
            bmask = (f >= hz - band_half_hz) & (f < hz + band_half_hz)
            if not bmask.any():
                continue
            uV2 = float(np.trapezoid(P[bmask], f[bmask]))  # µV² in band (np.trapz removed in numpy 2.0)
            for pr in pds:
                pnames = pr.get("ChannelNames") or []
                pdata = np.asarray(pr.get("Data"), dtype=float)
                if pdata.ndim != 2:
                    continue
                pcol = scol = None
                cu = ch.upper()
                for pi, nm in enumerate(pnames):
                    u = str(nm).upper()
                    if cu in u and "POWER" in u:
                        pcol = pi
                    if cu in u and "STIM" in u:
                        scol = pi
                if pcol is None or pcol >= pdata.shape[1]:
                    continue
                lsb = pdata[:, pcol]
                mA = (pdata[:, scol] if (scol is not None and scol < pdata.shape[1])
                      else np.zeros_like(lsb))
                off = (mA < stim_off_mA) & np.isfinite(lsb) & (lsb > 0)
                if off.sum() < 3:
                    continue
                med_lsb = float(np.median(lsb[off]))
                if med_lsb <= 0:
                    continue
                ratio = uV2 / med_lsb
                if np.isfinite(ratio) and ratio > 0:
                    ratios.append(ratio)
                break

    if len(ratios) < 5:
        return {"available": False, "reason": f"only {len(ratios)} paired TD/LSB sessions (need >= 5)"}
    a = np.asarray(ratios, dtype=float)
    med = float(np.median(a))
    cv = float(np.std(a) / np.mean(a)) if np.mean(a) > 0 else None
    fold = med / 0.01 if med > 0 else None
    # Confidence: the §4 ceiling is ~3×; flag low whenever the spread or the rule-of-thumb
    # divergence exceeds that, which on RCS08 it does (so this is honestly "low").
    conf = "moderate"
    if (cv is not None and cv > 0.5) or (fold is not None and (fold > 3.0 or fold < 1.0 / 3.0)):
        conf = "low"
    return {
        "available": True, "n": int(len(a)),
        "median": med, "iqr_lo": float(np.percentile(a, 25)), "iqr_hi": float(np.percentile(a, 75)),
        "cv": cv, "p10": float(np.percentile(a, 10)), "p90": float(np.percentile(a, 90)),
        "fold_off_rule": fold, "rule_of_thumb": 0.01, "confidence": conf,
        "note": ("Empirical µV²/LSB from concurrent on-demand TD + device LSB at ~0 mA. FYI cross-"
                 "check only — the deployable threshold is percentile-anchored on the device Timeline, "
                 "not via this absolute conversion (normalization-dependent, trust to ~3×)."),
    }


def _hm_auc_power_at(auc, n_pos, n_neg, za):
    """Hanley–McNeil power to reject AUC=0.5 at a single (n_pos, n_neg), given the two-sided
    critical z (za). Factored out of auc_power so the same formula drives both the scalar readout
    and the power-vs-N curve. Returns a float power, or None when a class is too small."""
    n_pos = int(n_pos); n_neg = int(n_neg)
    if n_pos < 2 or n_neg < 2:
        return None
    auc = float(max(auc, 1.0 - auc))
    if auc <= 0.5:
        return None
    Q1 = auc / (2.0 - auc)
    Q2 = 2.0 * auc * auc / (1.0 + auc)
    var = (auc * (1 - auc) + (n_pos - 1) * (Q1 - auc * auc)
           + (n_neg - 1) * (Q2 - auc * auc)) / (n_pos * n_neg)
    se = float(np.sqrt(max(var, 1e-12)))
    var0 = (0.25 + (n_pos - 1) * (1.0 / 3 - 0.25) + (n_neg - 1) * (1.0 / 3 - 0.25)) / (n_pos * n_neg)
    se0 = float(np.sqrt(max(var0, 1e-12)))
    from scipy import stats as _st
    return float(_st.norm.cdf((auc - 0.5) / se - za * se0 / se))


def _band_power_notched(freq, power, center_hz, half_hz, *, notch=False,
                        line_lo=58.5, line_hi=61.5):
    """Integrate a raw PSD (µV²/Hz) over [center-half, center+half). Returns µV² (area), or NaN if
    the band has <2 usable bins.

    Mains-notch is OFF by default. The Percept is an IMPLANTED, battery-powered neurostimulator with
    no galvanic connection to building mains, so there is no 60 Hz line-noise component to remove —
    blanking 58.5–61.5 Hz would delete real neural power from any band near 60 Hz (e.g. high-gamma).
    The interpolation capability is retained behind ``notch=True`` for the rare case of a genuinely
    mains-contaminated offline recording (e.g. a bench/tethered capture), but it must be requested
    explicitly. (The name is kept for call-site compatibility; the default behaviour is now a plain
    band integral.)
    """
    freq = np.asarray(freq, dtype=float)
    power = np.asarray(power, dtype=float).copy()
    if notch:
        inb = (freq >= line_lo) & (freq <= line_hi)
        if inb.any() and (~inb).sum() >= 2:
            power[inb] = np.interp(freq[inb], freq[~inb], power[~inb])
    m = (freq >= center_hz - half_hz) & (freq < center_hz + half_hz)
    if int(np.count_nonzero(m)) < 2:
        return float("nan")
    return float(np.trapezoid(power[m], freq[m]))


def psd_lsb_conversion(psd_bandpower_uv2, device_lsb, *, n_boot=2000, seed=0):
    """Derive a PSD→device-LSB conversion from TIME-MATCHED pairs of (offline PSD band power, device
    LSB) on the same channel/band.

    The Percept reports its on-board band power in device "LSB" units; an offline Welch PSD reports
    physical µV²/Hz. The firmware's mapping is a linear gain (LSB is proportional to in-band power),
    so the physically-meaningful model is the PROPORTIONAL law ``LSB = k · µV²`` (one constant, no
    intercept). We ALSO fit the free log-log line ``log10(LSB) = a + b·log10(µV²)`` purely as a
    falsification check: if the firmware really applies a linear gain, the free slope ``b`` must land
    near 1.0. A slope far from 1 means the offline band and the device's sensed band are not the same
    quantity (wrong channel/centre, aperiodic drift, or a non-linear on-device transform) and the
    proportional constant should not be trusted.

    Inputs are paired 1-D arrays (NaN/≤0 dropped pairwise). Returns a JSON-able dict:
      available, n_pairs,
      loglog_slope, loglog_slope_ci (95%), loglog_intercept, r2, spearman,
      k_lsb_per_uv2 (+ 95% bootstrap CI), uv2_per_lsb,
      resid_log_sigma (1σ multiplicative scatter, as a fold factor),
      slope_consistent_with_unity (bool: does the 95% CI include 1.0?),
      note.

    This is a CROSS-SCALE CALIBRATION, not a clinical control law — it lets the deployment view show a
    physical µV² target in the LSB units the device actually programs, with an honest scatter band.
    """
    P = np.asarray(psd_bandpower_uv2, dtype=float)
    L = np.asarray(device_lsb, dtype=float)
    m = np.isfinite(P) & np.isfinite(L) & (P > 0) & (L > 0)
    P, L = P[m], L[m]
    n = int(P.size)
    if n < 20:
        return {"available": False, "reason": f"only {n} usable matched pairs (need >=20)", "n_pairs": n}
    logP, logL = np.log10(P), np.log10(L)
    from scipy import stats as _st
    b, a, r, p, se_b = _st.linregress(logP, logL)
    tcrit = float(_st.t.ppf(0.975, n - 2))
    slope_ci = [float(b - tcrit * se_b), float(b + tcrit * se_b)]
    # Proportional constant k = median(L/P) == 10**median(logL - logP) (robust to outliers).
    logk = float(np.median(logL - logP))
    k = float(10.0 ** logk)
    rng = np.random.default_rng(seed)
    ks = np.array([10.0 ** np.median((logL - logP)[rng.integers(0, n, n)]) for _ in range(int(n_boot))])
    k_ci = [float(np.percentile(ks, 2.5)), float(np.percentile(ks, 97.5))]
    resid = logL - (logk + logP)                       # log10 ratio L / predicted
    sigma_fold = float(10.0 ** np.percentile(np.abs(resid), 68))
    return {
        "available": True,
        "n_pairs": n,
        "loglog_slope": float(b),
        "loglog_slope_ci": slope_ci,
        "loglog_intercept": float(a),
        "r2": float(r * r),
        "spearman": float(_st.spearmanr(P, L).correlation),
        "k_lsb_per_uv2": k,
        "k_ci": k_ci,
        "uv2_per_lsb": float(1.0 / k) if k > 0 else None,
        "resid_log_sigma_fold": sigma_fold,
        "slope_consistent_with_unity": bool(slope_ci[0] <= 1.0 <= slope_ci[1]),
        "note": ("Proportional law LSB = k·µV²(band) from time-matched chronic streams. The free "
                 "log-log slope is a falsification check — it must sit near 1.0 for a linear "
                 "firmware gain; a slope far from 1 means the offline and on-device bands are not the "
                 "same quantity and k is unreliable. Multiplicative scatter is the 1σ fold factor."),
    }


# Ceiling above which "ratings needed for 80% power" stops being a data-collection plan and becomes
# a statement that the effect is indistinguishable from chance. Rationale, in this study's own units:
# RCS08 accumulated ~48 INDEPENDENT (cluster-effective) pain ratings over roughly a year of chronic
# daily reporting, so ~50/year is the realistic accrual rate for one participant. 500 is therefore a
# deliberately GENEROUS ~10-year horizon — anything beyond it cannot be collected by any plausible
# study, so presenting it as a shortfall ("collect N more ratings") misleads the reader into thinking
# more data would rescue the biomarker. Observed in the wild at 270,660 ratings (~5,400 years) for a
# band whose AUC was 0.5036. Raise it if a multi-site pooled analysis ever makes larger N feasible;
# the raw requirement is always reported alongside, so nothing is hidden by this threshold.
FEASIBLE_N_RATINGS_MAX = 500

# Power-status vocabulary, so callers branch on a value instead of re-deriving the logic from floats.
POWER_STATUS_POWERED = "powered"                      # target power already met
POWER_STATUS_FEASIBLE = "more_data_feasible"          # underpowered, but the shortfall is collectable
POWER_STATUS_INFEASIBLE = "requirement_infeasible"    # finite requirement, but beyond any real study
POWER_STATUS_AT_CHANCE = "at_or_below_chance"         # AUC <= 0.5: no finite N reaches target power


def _power_result_blank(**over):
    """One canonical key set for EVERY auc_power return path.

    The unavailable/at-chance paths used to return a SHORTER dict than the main path, so a consumer
    reading e.g. ``power["power_current_lo"]`` raised KeyError on exactly the degenerate inputs where
    it most needed a value. Every path now fills this template, so the shape is invariant and only
    the values differ.
    """
    out = {
        "available": False, "reason": None, "note": None,
        "auc": None, "auc_lo": None, "se_auc": None,
        "n_pos": None, "n_neg": None,
        "power_current": None, "power_current_lo": None,
        "ci_crosses_chance": None,
        "n_ratings_current": None, "n_ratings_needed": None, "n_ratings_needed_hi": None,
        "more_data_needed": None,
        "alpha": None, "target_power": None,
        "design_effect": None, "n_ratings_effective": None,
        "small_sample": None, "small_sample_floor": int(SMALL_SAMPLE_CLUSTER_FLOOR),
        "curve": None, "curve_truncated": False,
        # feasibility of the requirement itself (see FEASIBLE_N_RATINGS_MAX)
        "status": None, "requirement_feasible": None,
        "feasible_n_max": int(FEASIBLE_N_RATINGS_MAX),
    }
    out.update(over)
    return out


def auc_power(auc, n_pos, n_neg, *, alpha=0.05, target_power=0.80, auc_lo=None, design_effect=1.0,
              feasible_n_max=FEASIBLE_N_RATINGS_MAX):
    """Power / sample-size readout for a deployment AUC, on the count of INDEPENDENT ratings (the
    clustered effective n, NOT raw samples). Uses the Hanley & McNeil AUC variance.

    Reports the current power to reject AUC=0.5 at the given alpha, and the number of independent
    ratings (at the observed prevalence) needed for `target_power`. The honest 'do we have enough
    pain ratings to trust this cut-point yet?' number — pairs with the bootstrap CI from the ROC.

    **audit C4 — power on the optimistic AUC.** Power is monotone in AUC, so feeding the in-sample,
    fold-biased, selection-optimistic POINT auc overstates current power and understates ratings
    needed — exactly at the deploy/no-deploy margin. When `auc_lo` (the de-folded clustered-bootstrap
    CI lower bound from deployment_roc) is supplied, this function ALSO reports the conservative end
    of the power band (power_current_lo, n_ratings_needed_hi) computed at auc_lo, and makes
    `more_data_needed` fail-closed on that conservative bound — so the "powered" gate cannot pass on
    optimism alone. The point-AUC numbers are retained for display; the gate reads the band.

    Returns {available, auc, auc_lo, power_current, power_current_lo, n_ratings_current,
             n_ratings_needed, n_ratings_needed_hi, more_data_needed, se_auc, alpha, target_power,
             curve} or {available: False, reason}.
    """
    try:
        from scipy import stats as _st
    except Exception as e:
        return _power_result_blank(reason=f"scipy unavailable: {e}")
    auc = float(max(auc, 1.0 - auc))
    n_pos_raw = int(n_pos); n_neg_raw = int(n_neg)
    if n_pos_raw < 2 or n_neg_raw < 2:
        return _power_result_blank(reason="too few independent ratings for a power estimate",
                                   n_pos=n_pos_raw, n_neg=n_neg_raw,
                                   n_ratings_current=n_pos_raw + n_neg_raw,
                                   alpha=alpha, target_power=target_power)
    # Audit [19] — DESIGN-EFFECT DISCOUNT. Weekly pain ratings are serially autocorrelated, so the
    # independent-rating count overstates the information content. `design_effect` (DEFF >= 1, the
    # moving-block/i.i.d. bootstrap variance ratio from deployment_roc) discounts the EFFECTIVE n:
    # the Hanley–McNeil variance scales ~1/N, so dividing each class count by DEFF inflates the
    # variance by DEFF (= the block bootstrap's honest variance). DEFF==1 reproduces the prior math
    # EXACTLY (no-op), so uncorrelated ratings and all existing fixtures are unchanged. The RAW counts
    # are retained for display; only the inference math runs on the discounted counts.
    deff = float(design_effect) if (design_effect and design_effect >= 1.0) else 1.0
    n_pos = max(2.0, n_pos_raw / deff)
    n_neg = max(2.0, n_neg_raw / deff)
    if auc <= 0.5:
        # At exactly-chance discrimination there is NO finite N that reaches target power, so
        # n_ratings_needed is None by mathematics, not by a failure to compute. power_current is
        # alpha because the probability of rejecting AUC=0.5 when AUC really is 0.5 is just the
        # Type I error rate. Both are correct; what was missing is that callers could not tell this
        # apart from "the computation broke", hence the explicit status.
        return _power_result_blank(
            available=True, auc=auc, power_current=float(alpha), se_auc=None,
            n_pos=n_pos_raw, n_neg=n_neg_raw,
            n_ratings_current=n_pos_raw + n_neg_raw, n_ratings_needed=None,
            design_effect=deff, n_ratings_effective=float((n_pos_raw + n_neg_raw) / deff),
            more_data_needed=True, alpha=alpha, target_power=target_power,
            small_sample=bool((n_pos_raw + n_neg_raw) < SMALL_SAMPLE_CLUSTER_FLOOR),
            status=POWER_STATUS_AT_CHANCE, requirement_feasible=False,
            feasible_n_max=int(feasible_n_max),
            note="AUC at or below chance — no finite number of additional ratings reaches target "
                 "power, so the requirement is undefined rather than large. power_current is alpha "
                 "by definition (rejecting AUC=0.5 when it is true happens at the Type I rate).")
    Q1 = auc / (2.0 - auc)
    Q2 = 2.0 * auc * auc / (1.0 + auc)
    var = (auc * (1 - auc) + (n_pos - 1) * (Q1 - auc * auc)
           + (n_neg - 1) * (Q2 - auc * auc)) / (n_pos * n_neg)
    se = float(np.sqrt(max(var, 1e-12)))
    var0 = (0.25 + (n_pos - 1) * (1.0 / 3 - 0.25) + (n_neg - 1) * (1.0 / 3 - 0.25)) / (n_pos * n_neg)
    se0 = float(np.sqrt(max(var0, 1e-12)))
    za = float(_st.norm.ppf(1 - alpha / 2.0))
    zb = float(_st.norm.ppf(target_power))
    power = float(_st.norm.cdf((auc - 0.5) / se - za * se0 / se))
    N0 = n_pos + n_neg            # EFFECTIVE total (discounted); drives all the power math below
    N0_raw = n_pos_raw + n_neg_raw  # REAL ratings the clinician has; what we DISPLAY as "current"
    # SE^2 * N is ~constant in N; solve (auc-0.5)*sqrt(N) = za*sqrt(se0^2 N0) + zb*sqrt(se^2 N0).
    rhs = za * np.sqrt(se0 * se0 * N0) + zb * np.sqrt(se * se * N0)
    n_need_eff = int(np.ceil((rhs / (auc - 0.5)) ** 2))
    # Effective ratings needed -> REAL ratings the clinician must collect (each real rating is worth
    # 1/deff effective under autocorrelation). At deff==1 this is the identity.
    n_need = int(np.ceil(n_need_eff * deff))

    # ---- audit C4: conservative power band at the de-folded CI lower bound -----------------------
    # Re-run the SAME Hanley–McNeil math at auc_lo (the clustered-bootstrap CI lower bound). This is
    # the power we'd actually have if the true AUC sat at the pessimistic edge of the CI — the number
    # the "powered" deployment gate should fail-closed on, instead of the optimistic point estimate.
    power_lo = None; n_need_hi = None; auc_lo_used = None; ci_crosses_chance = None
    if auc_lo is not None:
        try:
            # DO NOT FOLD. This line used to read max(auc_lo, 1 - auc_lo), "fold defensively", and
            # that mirrored a sub-chance lower bound up above 0.5 — destroying the one piece of
            # information the caller's de-folded bootstrap CI exists to carry.
            #
            # Two consequences, both verified on live RCS08 data (2026-08-30):
            #   1. The fail-closed branch below (`a_lo <= 0.5` -> no power, gate must not pass) became
            #      UNREACHABLE for exactly the bands it was written for. With the real bound
            #      auc_lo = 0.3484 the fold gave 0.6516, which fails `a_lo <= auc` (auc = 0.5036) AND
            #      fails `a_lo <= 0.5`, so NEITHER branch ran and auc_lo_used / power_current_lo /
            #      n_ratings_needed_hi all came back None. The conservative gate was silently inert.
            #   2. Worse, it could report a FALSE PASS. At auc = 0.85 with auc_lo = 0.20 the fold
            #      returns 0.80, which satisfies `a_lo <= auc`, so power is computed at a
            #      "conservative" bound of 0.80 and the status comes back `powered` — a band whose
            #      interval badly crosses chance reading as deployable.
            #
            # Correct handling: keep the SIGNED bound. Clamp it at the point estimate (a lower bound
            # above the point estimate is nonsense and means the caller passed an upper bound), but
            # never mirror it across 0.5.
            a_lo = float(auc_lo)
        except (TypeError, ValueError):
            a_lo = None
        if a_lo is not None and np.isfinite(a_lo) and a_lo > 0.5:
            a_lo = min(a_lo, float(auc))          # clamp, never mirror
        if a_lo is not None and np.isfinite(a_lo) and a_lo > 0.5 and a_lo <= auc:
            auc_lo_used = a_lo
            Q1l = a_lo / (2.0 - a_lo)
            Q2l = 2.0 * a_lo * a_lo / (1.0 + a_lo)
            var_l = (a_lo * (1 - a_lo) + (n_pos - 1) * (Q1l - a_lo * a_lo)
                     + (n_neg - 1) * (Q2l - a_lo * a_lo)) / (n_pos * n_neg)
            se_l = float(np.sqrt(max(var_l, 1e-12)))
            power_lo = float(_st.norm.cdf((a_lo - 0.5) / se_l - za * se0 / se_l))
            rhs_l = za * np.sqrt(se0 * se0 * N0) + zb * np.sqrt(se_l * se_l * N0)
            n_need_hi_eff = int(np.ceil((rhs_l / (a_lo - 0.5)) ** 2))
            n_need_hi = int(np.ceil(n_need_hi_eff * deff))   # -> real ratings (deff==1 -> identity)
        elif a_lo is not None and np.isfinite(a_lo) and a_lo <= 0.5:
            # CI lower bound touches/crosses chance: conservatively, no power and ratings-needed is
            # undefined (the band could be null). Gate must not pass. THIS BRANCH WAS UNREACHABLE
            # before the fold above was removed — it is the whole point of the conservative gate.
            auc_lo_used = a_lo; power_lo = float(alpha); n_need_hi = None
            ci_crosses_chance = True

    # The gate reads the conservative bound when we have one: more data is needed unless we clear the
    # target at the CI lower bound. Comparisons are in REAL ratings (n_need_* already × deff, N0_raw
    # is the real current count) — equivalent to comparing effective-vs-effective, so deff cancels in
    # the gate logic and the gate is unchanged at deff==1.
    if auc_lo_used is not None:
        more_data = bool(n_need_hi is None or n_need_hi > N0_raw or (power_lo is not None and power_lo < target_power))
    else:
        more_data = bool(n_need > N0_raw)

    # ---- power-vs-N curve (replaces the 3-number readout with a sufficiency curve) ----
    # Sample total ratings N from a small floor up past whichever is larger of the current count and
    # the 80%-power requirement, holding the observed prevalence fixed, and evaluate the SAME
    # Hanley–McNeil power at each N. The frontend draws this as power rising with N, with the target
    # line, the current-N marker and the needed-N marker on it. Prevalence is held at n_pos/N0 so
    # n_pos(N) and n_neg(N) scale together the way more ratings would actually accrue.
    prev = float(n_pos) / float(N0) if N0 > 0 else 0.5
    # x-axis is REAL ratings the clinician collects; power is evaluated at the corresponding EFFECTIVE
    # count N/deff (autocorrelation discount, audit [19]). At deff==1 these coincide -> identical curve.
    # Cap the x-axis at the feasibility ceiling. Without this, an at-chance band with n_need =
    # 270,660 produced a 40-point grid running to ~365,000 ratings, on which the clinician's actual
    # 48 ratings sit invisibly against the origin and the curve reads as a flat line at alpha — a
    # plot that hides the only region anyone can act in. Truncation is FLAGGED, not silent.
    n_top_uncapped = int(max(N0_raw, n_need) * 1.35) + 4
    n_top = min(n_top_uncapped, int(max(N0_raw * 1.35, feasible_n_max)) + 4)
    curve_truncated = bool(n_top < n_top_uncapped)
    n_grid = np.unique(np.clip(np.linspace(4, n_top, 40).astype(int), 4, None))
    curve_n, curve_p = [], []
    for N in n_grid:
        N_eff = max(4.0, N / deff)
        np_i = int(round(N_eff * prev)); nn_i = int(round(N_eff - np_i))
        pw = _hm_auc_power_at(auc, np_i, nn_i, za)
        if pw is not None:
            curve_n.append(int(N)); curve_p.append(float(pw))
    curve = ({"n": curve_n, "power": curve_p, "prevalence": prev}
             if len(curve_n) >= 2 else None)

    # ---- is the REQUIREMENT itself a plan, or a restatement of "indistinguishable from chance"? ----
    # `n_need` is finite whenever auc > 0.5, but it grows as 1/(auc-0.5)^2, so an AUC of 0.5036
    # yields 270,660 ratings — ~5,400 years at this participant's accrual rate. Reporting that as a
    # shortfall invites the reader to think more data would fix the biomarker. Decide feasibility on
    # the CONSERVATIVE requirement when a CI lower bound gave us one (fail-closed, consistent with
    # the gate above), else on the point requirement.
    _need_for_feasibility = n_need_hi if (auc_lo_used is not None and n_need_hi is not None) else n_need
    requirement_feasible = bool(_need_for_feasibility <= int(feasible_n_max))
    if not more_data:
        status = POWER_STATUS_POWERED
    elif requirement_feasible:
        status = POWER_STATUS_FEASIBLE
    else:
        status = POWER_STATUS_INFEASIBLE

    note = ("Hanley–McNeil AUC variance on the count of independent ratings (clustered "
            "effective n). Power to reject AUC = 0.5.")
    if status == POWER_STATUS_INFEASIBLE:
        note += (f" REQUIREMENT NOT FEASIBLE: reaching {target_power:.0%} power would take "
                 f"{_need_for_feasibility:,} independent ratings, beyond the {int(feasible_n_max):,} "
                 "ceiling for a realistic single-participant study. Because the required n scales as "
                 "1/(AUC-0.5)^2, this is a restatement of 'this band is indistinguishable from "
                 "chance', NOT a data-collection target.")
    if deff > 1.0:
        note += (f" Effective n is DISCOUNTED by a design effect of {deff:.2f} (audit [16]/[19]): "
                 "weekly ratings are serially autocorrelated, so the moving-block bootstrap variance "
                 "exceeds the i.i.d. cluster bootstrap by this factor. Power and ratings-needed are "
                 "reported on the discounted effective n; the x-axis is real ratings collected.")
    if auc_lo_used is not None:
        note += (" Power BAND reported across [auc_lo, auc]; the 'powered' gate reads the "
                 "conservative auc_lo end (audit C4) so it cannot pass on the optimistic point AUC.")
    return {
        "available": True, "auc": auc, "auc_lo": auc_lo_used,
        # DISPLAY the real (un-discounted) class counts; the discounted effective counts are exposed
        # separately so a reader can see both. (audit [19])
        "n_pos": n_pos_raw, "n_neg": n_neg_raw,
        "se_auc": se,
        "power_current": power, "power_current_lo": power_lo,
        # True when the CI lower bound touches or crosses 0.5, i.e. the band may be null. Before
        # 2026-08-30 this state was UNREACHABLE because the bound was folded above 0.5, which left
        # the conservative gate inert and could even report a false pass.
        "ci_crosses_chance": ci_crosses_chance,
        "n_ratings_current": int(N0_raw), "n_ratings_needed": n_need, "n_ratings_needed_hi": n_need_hi,
        "more_data_needed": more_data, "alpha": alpha, "target_power": target_power,
        # Audit [19]: design-effect discount. design_effect==1.0 -> no discount (identical to prior).
        "design_effect": deff,
        "n_ratings_effective": float(N0_raw / deff),
        # Audit [8]: advisory only — Gaussian power approximation is rough below the cluster floor.
        # Keyed on REAL ratings (what the clinician has), consistent with n_ratings_current.
        "small_sample": bool(N0_raw < SMALL_SAMPLE_CLUSTER_FLOOR),
        "small_sample_floor": int(SMALL_SAMPLE_CLUSTER_FLOOR),
        "curve": curve,
        "curve_truncated": curve_truncated,
        "status": status,
        "requirement_feasible": requirement_feasible,
        "feasible_n_max": int(feasible_n_max),
        "reason": None,
        "note": note,
    }


# Process-wide gate serializing all embedded-R (pymer4/lme4 glmer) access within a worker. Embedded R
# is single-threaded; concurrent fits from sibling requests corrupt it and silently kill the worker.
# Reentrant so the LRT path (two fits inside one converter ctx) does not self-deadlock. See
# _rpy2_converter_ctx for the full rationale.
_R_GLOBAL_LOCK = _threading.RLock()


def _rpy2_converter_ctx():
    """Activate a NON-EMPTY rpy2 conversion context on the CURRENT thread for a pymer4 fit.

    rpy2 >= 3.5 stores the active conversion rules in a `contextvars.ContextVar`. pymer4 calls
    `pandas2ri.activate()` once at import (on the main/import thread), but a ContextVar set on one
    thread does NOT propagate to others — Django serves each request on a worker thread (and the
    PSD/validation machinery also uses ThreadPoolExecutor). On that worker the converter is empty,
    so pymer4's R calls raise:
        "Conversion rules for `rpy2.robjects` appear to be missing. Those rules are in a Python
         contextvars.ContextVar. This could be caused by multithreading code not passing context
         to the thread."
    Entering this context manager around every Lmer construction + .fit() re-establishes a
    non-empty converter for the duration of the fit, so the call works regardless of which thread
    runs it.

    IMPORTANT — use the PLAIN default_converter here, NOT (default_converter + pandas2ri.converter).
    We only need *some* non-empty converter active to silence the "rules missing" error above;
    pymer4 0.8.2 performs its OWN pandas<->R DataFrame conversion internally (pymer4.bridge.pandas2R
    and R2pandas each open their own localconverter(default + pandas2ri)), so the outer context does
    not need pandas2ri — and must NOT add it. With pandas2ri's rpy2py rules active in the outer
    context, the R control object that pymer4 builds via `robjects.r("glmerControl(...)")` /
    `lmerControl(...)` is eagerly converted to a Python `rpy2.rlike.container.OrdDict` and loses its
    R class. rpy2 3.5.15 then has no `py2rpy` rule for OrdDict when pymer4 passes it back into
    `lme4::glmer(control=...)` ("Conversion 'py2rpy' not defined for ... OrdDict"); and even a
    hand-registered OrdDict->ListVector converter yields a plain R list that glmer rejects ("unused
    arguments checkControl/checkConv"), because the nested glmer.control structure/class is gone.
    default_converter alone leaves the control object as a native R ListVector, and the fit (plus
    coef/CI/OR extraction) succeeds. Verified in-container against rpy2 3.5.15 / pymer4 0.8.2.

    Returns a no-op nullcontext when rpy2 isn't importable (the caller already guards pymer4
    availability separately and degrades to {available: False}).

    CONCURRENCY: embedded R (the single libR the rpy2 process loads) is NOT thread-safe — there is
    one R interpreter per worker process, and two threads calling into it at once corrupt its state
    and kill the worker (the connection drops with NO 500 in the log; the client just sees "request
    failed"). The deploy page fires several glmer-backed panels (ROC, per-era refit, sign-off) on
    mount, and under the async UvicornWorker those land on ONE worker concurrently. We therefore hold
    a process-wide reentrant lock for the whole duration of every fit, so concurrent R work QUEUES
    instead of racing. This serializes only the R section (seconds) and changes no numeric result.
    The LRT path runs its two fits inside ONE converter ctx (a single acquire), so reentrancy is not
    exercised today — RLock is chosen defensively (harmless, future-proofs against a nested ctx); a
    plain Lock would behave identically given the current call sites.
    """
    try:
        import rpy2.robjects as ro
        from rpy2.robjects.conversion import localconverter
        from contextlib import contextmanager

        @contextmanager
        def _locked_converter():
            _R_GLOBAL_LOCK.acquire()
            try:
                with localconverter(ro.default_converter) as cv:
                    yield cv
            finally:
                _R_GLOBAL_LOCK.release()

        return _locked_converter()
    except Exception:
        from contextlib import nullcontext
        return nullcontext()


# =============================================================================================
# RELATING BAND POWER TO PAIN WITH HONEST CLUSTERED UNCERTAINTY
#
# WHY THIS BLOCK IS IN THIS FILE. Everything below used to live in
# ``modules/ClosedLoopDeployment/edges.py``, where it was written to answer the closed-loop
# module's second question: does this frequency band track the patient's pain while the
# stimulation settings are held still? That is the same question the biomarker page exists to
# answer, so the calculation belongs on the biomarker page and the closed-loop module should ask
# for it rather than keep a second copy. It was moved here, not copied, and ``edges.py`` now
# imports these names back out so that nothing in the closed-loop module had to change its
# spelling.
#
# The import can only go one way. ClosedLoopDeployment is allowed to import Biomarkers; Biomarkers
# must never import ClosedLoopDeployment, because that would be a loop and Python would fail to
# load either one. That is why the whole toolkit had to move rather than only the estimator that
# uses it: an estimator living here cannot reach back into the closed-loop module for its standard
# errors.
#
# WHAT THE TOOLKIT IS FOR. Every estimate in this project is built on a handful of independent
# observations. One pain rating is matched to a stretch of recording that contains many spectral
# samples, and all of those samples share the one rating between them, so they are one observation
# of the power-to-pain relationship and not many. Ordinary standard errors assume the samples are
# independent, so they come out far too small and turn a coincidence into a finding. That was the
# single largest source of overstated significance found in the fourteen-finding audit of this
# project. The standard errors here are computed instead by grouping the samples that share a
# rating and letting each group count once.
#
# Grouping is not enough on its own when there are only a few groups. The grouped (CR0) standard
# error is trustworthy as the NUMBER OF GROUPS grows, and this participant has at most 35 exposure
# epochs in any band and usually about 7, so below a stated number of groups the p-value and the
# interval are taken from the wild cluster bootstrap instead. Both estimators are here, the switch
# between them is a single named number, and every result says which one produced it.
# =============================================================================================

#: The number of clusters at or above which the cluster-robust (CR0) variance estimator is used
#: directly, and BELOW which inference is taken from the wild cluster bootstrap-t instead.
#:
#: This constant used to be a disqualification: any estimate with fewer clusters than this was
#: flagged unreliable and could not be assessed. The diagnosis behind that flag is correct and is
#: measured on this dataset. With few clusters CR0 is anti-conservative, meaning its intervals are
#: too NARROW, so it manufactures resolution rather than losing it; on the RCS08 record, cells with
#: three setting epochs reported all eighteen bands as resolved while the whole-epoch permutation on
#: the same cells returned a family-wise p of 1.00. But the RCS08 record has a maximum of 35 setting
#: epochs in any band-cell and a median of 7, so a floor of 40 disqualified every cell that exists
#: and will ever exist here, which is a refusal wearing the clothes of a criterion.
#:
#: The threshold is therefore now a SWITCH between two estimators rather than a gate. Below it, the
#: reported p-value and confidence interval come from the wild cluster bootstrap-t with Rademacher
#: weights imposed under the null (Cameron, Gelbach and Miller 2008), which is the inference method
#: with demonstrated size properties in the five-to-forty cluster range; the simulation in
#: tests/test_bootstrap.py measures both estimators against a known null and records what each one
#: actually does. The few-cluster condition is still reported on the estimate, but as information
#: about which estimator produced the numbers, not as a reason to withhold them.
#:
#: The value 40 itself follows the conventional rule of thumb in the clustered-inference literature
#: (Cameron and Miller 2015, "A Practitioner's Guide to Cluster-Robust Inference", section VI):
#: there is no sharp cutoff, and 40 is the commonly cited point above which the asymptotic
#: cluster-robust approximation is usually adequate. It is deliberately conservative, because using
#: the bootstrap when it was not needed costs computer time, whereas using CR0 when it was not
#: warranted costs a false claim about a patient's brain.
MIN_RELIABLE_CLUSTERS = 40


def estimator_for(n_clusters):
    """Which inference estimator the reported interval and p-value came from.

    THE SINGLE DEFINITION OF THE SWITCH, so that nothing downstream has to restate it. The
    JavaScript in the deployment panel previously hardcoded the number 40 with a comment saying it
    mirrored this module, and by then it was wrong twice over: the constant had stopped being a
    disqualification floor and become a choice between two estimators, so the front end was both
    duplicating a value it could not see change AND describing it as something it no longer was.

    Returns a small mapping rather than a bare string, because a reader who is told the name of an
    estimator still needs to know why that one and not the other.
    """
    if n_clusters is None:
        return {"estimator": None, "switch_clusters": MIN_RELIABLE_CLUSTERS,
                "why": "the cluster count is not recorded, so the estimator cannot be named"}
    n = int(n_clusters)
    if n >= MIN_RELIABLE_CLUSTERS:
        return {
            "estimator": "cluster-robust (CR0)",
            "switch_clusters": MIN_RELIABLE_CLUSTERS,
            "why": (f"{n} clusters is at or above {MIN_RELIABLE_CLUSTERS}, where the "
                    f"cluster-robust sandwich estimator is reliable enough to report directly. "
                    f"Its measured rejection rate against a true null in this regime is 0.060 to "
                    f"0.076 against a nominal 0.05."),
        }
    return {
        "estimator": "wild cluster bootstrap-t (Rademacher, imposed null)",
        "switch_clusters": MIN_RELIABLE_CLUSTERS,
        "why": (f"{n} clusters is below {MIN_RELIABLE_CLUSTERS}, where the cluster-robust "
                f"sandwich is anti-conservative: at five clusters it rejects a true null about "
                f"29 per cent of the time against a nominal 5 per cent. The interval and the "
                f"p-value therefore come from the wild cluster bootstrap-t instead. Note that the "
                f"bootstrap has a discreteness floor — with G clusters the smallest attainable "
                f"two-sided p-value is 2/2^G, so at five clusters no test at the 5 per cent level "
                f"exists at all."),
    }

#: At or below this many clusters the whole Rademacher weight space is ENUMERATED rather than
#: sampled, because there are only 2**G distinct sign vectors and sampling 999 of them would draw
#: the same handful repeatedly while pretending to a resolution of one in a thousand. 2**12 = 4096,
#: which is the point where enumeration stops being cheaper than the usual 999 replications.
#:
#: This is also the range in which a reader has to be TOLD that the p-value is coarse. Two of the
#: 2**G sign vectors — all plus one and all minus one — reproduce the observed sample exactly under
#: the imposed null, so the enumerated p-value can never fall below 2 / 2**G. At eight clusters
#: that floor is 0.0078, at six it is 0.031, and at five it is 0.0625, which is ABOVE the
#: conventional five percent: with five clusters and Rademacher weights no result can be called
#: significant at the five percent level no matter how large the effect. That is a known and
#: deliberate property of the method (Cameron, Gelbach and Miller 2008, section IV; Webb 2013
#: proposes a six-point weight distribution specifically to relieve it), and it is reported on every
#: result through the `enumerable`, `n_sign_vectors` and `p_resolution` fields rather than hidden.
MAX_ENUMERABLE_CLUSTERS = 12


def _cluster_ols(y, X, groups, *, names=None):
    """OLS with cluster-robust (CR0) standard errors. Returns (params, bse, n_clusters).

    statsmodels is used rather than a hand-rolled sandwich because the conventional implementation
    handles the small-sample correction and the singular cases consistently, and because a
    re-implementation would be one more thing to audit.
    """
    import statsmodels.api as sm
    y = np.asarray(y, float)
    X = np.asarray(X, float)
    g = np.asarray(groups)
    ok = np.isfinite(y) & np.isfinite(X).all(axis=1) & pd.notna(g)
    y, X, g = y[ok], X[ok], g[ok]
    if y.size < 3 or np.unique(g).size < 2:
        return None, None, int(np.unique(g).size if g.size else 0)
    res = sm.OLS(y, X).fit(cov_type="cluster", cov_kwds={"groups": g})
    return res, np.asarray(res.bse, float), int(np.unique(g).size)


# --------------------------------------------------------------------------------------------
# The wild cluster bootstrap-t
#
# WHY THIS EXISTS. Everything in this module is estimated on a handful of clusters: a setting epoch
# is a stretch during which the stimulation settings did not change, and RCS08 has at most 35 of
# them in any band-cell and typically 7. Cluster-robust standard errors are consistent as the
# NUMBER OF CLUSTERS grows, not as the number of observations grows, so at these cluster counts the
# CR0 sandwich has no asymptotic argument behind it and is known to be biased downward. Adding more
# spectral samples inside an epoch does not help, because those samples are not independent
# observations of the amplitude-power relationship; only more epochs would help, and the historical
# record contains the epochs it contains.
#
# The wild cluster bootstrap-t of Cameron, Gelbach and Miller (2008), "Bootstrap-Based Improvements
# for Inference with Clustered Errors", Review of Economics and Statistics 90(3), is the standard
# answer in this regime. Instead of trusting the sandwich to give the right standard error, it
# builds the sampling distribution of the t STATISTIC itself by re-generating the outcome many
# times under a null-imposed model, flipping the sign of each cluster's whole residual vector, and
# recomputing the same t statistic each time. The observed t is then read against that distribution
# rather than against a normal or t table. Because the statistic's own denominator is recomputed in
# every replication, the method corrects for the downward bias of the denominator instead of
# assuming it away.
#
# WHAT MUST NOT BE GOT WRONG. The sign is drawn ONCE PER CLUSTER and applied to every observation in
# that cluster. Drawing a sign per observation destroys exactly the within-cluster dependence the
# procedure exists to respect, and silently degrades the method to an ordinary residual bootstrap
# whose intervals are as narrow as the ones being replaced. There is a test for this
# (tests/test_bootstrap.py) that checks the weight structure directly rather than trusting the
# output to look reasonable.
# --------------------------------------------------------------------------------------------
def _rademacher_weights(n_clusters, n_boot, seed):
    """Return (W, method, n_sign_vectors) where W has one row per replication and one column per
    CLUSTER, with entries +1 or -1.

    One column per cluster, not one per observation. The caller expands each row across that
    cluster's rows, so this shape is what makes the per-cluster requirement structural rather than
    a matter of remembering to do it.

    When the number of clusters is small enough that the whole weight space fits
    (``n_clusters <= MAX_ENUMERABLE_CLUSTERS``) every one of the 2**G sign vectors is returned
    exactly once. Sampling in that regime would draw the same few vectors repeatedly and report a
    resolution of one in a thousand that the weight space cannot deliver; enumerating instead makes
    the p-value exact for the chosen weight distribution and makes its coarseness visible.
    """
    G = int(n_clusters)
    if G <= MAX_ENUMERABLE_CLUSTERS:
        n_vec = 2 ** G
        bits = (np.arange(n_vec, dtype=np.int64)[:, None] >> np.arange(G)[None, :]) & 1
        return (1.0 - 2.0 * bits).astype(float), "enumerated", n_vec
    rng = np.random.default_rng(seed)
    W = rng.integers(0, 2, size=(int(n_boot), G)).astype(float) * 2.0 - 1.0
    return W, "sampled", 2 ** G


def _cr0_variance(X, resid, seg_starts, XtX_inv):
    """The CR0 cluster-robust covariance matrix, computed here rather than taken from statsmodels.

    Computed locally for one reason: the bootstrap has to apply the SAME variance formula to every
    replication that it applies to the observed sample, and reaching into statsmodels once per
    replication would cost a model fit per replication for a quantity that is three matrix products.
    No small-sample correction factor is applied. Any correction that depends only on the number of
    observations, regressors and clusters — statsmodels' default ``(n-1)/(n-k) * G/(G-1)`` among
    them — is the same constant in the observed sample and in every replication, so it multiplies
    both sides of the comparison ``|t*| >= |t_obs|`` and cancels exactly. Leaving it out therefore
    changes no bootstrap p-value, and putting it in would invite the reader to think it did.

    ``resid`` may be a single vector or a (replications, observations) matrix; rows of X must be
    sorted by cluster and ``seg_starts`` gives the first row index of each cluster.
    """
    R = np.atleast_2d(np.asarray(resid, float))                     # (B, n)
    k = X.shape[1]
    S = np.empty((k, R.shape[0], seg_starts.size), float)           # (k, B, G)
    for i in range(k):
        S[i] = np.add.reduceat(R * X[:, i], seg_starts, axis=1)
    meat = np.einsum("ibg,jbg->bij", S, S)                          # (B, k, k)
    return np.einsum("ip,bpq,qj->bij", XtX_inv, meat, XtX_inv)


class _BootstrapPlan:
    """Everything needed to evaluate the bootstrap-t at ANY candidate coefficient value, computed
    once.

    The reason this is a prepared object rather than a function call per candidate value is that
    confidence intervals here are formed by INVERTING the test — asking which candidate values the
    bootstrap-t would not reject — and a naive implementation redraws and refits for every candidate
    on the grid, which multiplies the cost by the grid size. That is avoidable exactly, not
    approximately. Under the imposed null at candidate value b0 the restricted residuals are

        u(b0) = M_r y - b0 * M_r x_j

    where M_r annihilates the OTHER regressors, so they are affine in b0. Everything downstream is
    then either affine in b0 (the bootstrap coefficient and the bootstrap residuals) or quadratic in
    b0 (the CR0 meat matrix, being a sum of outer products of affine terms). So the two affine
    pieces and the three quadratic-form pieces are accumulated once here, and each candidate value
    costs a handful of small matrix products instead of a fresh set of replications. The interval
    that comes out is the genuine inverted-test interval, not a normal approximation dressed up.
    """

    def __init__(self, y, X, groups, *, coef_index, n_boot, seed, impose_null, chunk=256):
        y = np.asarray(y, float)
        X = np.asarray(X, float)
        g = np.asarray(groups)
        ok = np.isfinite(y) & np.isfinite(X).all(axis=1) & pd.notna(g)
        y, X, g = y[ok], X[ok], g[ok]
        self.available, self.reason = False, ""
        self.n, k = X.shape[0], X.shape[1]
        if not (0 <= int(coef_index) < k):
            self.reason = f"coef_index {coef_index} is not a column of the design"
            return
        self.j = int(coef_index)
        order = np.argsort(g, kind="stable")
        y, X, g = y[order], X[order], g[order]
        uniq, self.seg_starts, counts = np.unique(g, return_index=True, return_counts=True)
        self.n_clusters = int(uniq.size)
        if self.n_clusters < 2:
            self.reason = (f"{self.n_clusters} cluster(s); the sign-flip distribution needs at "
                           "least two clusters to have any support")
            return
        if self.n <= k or np.linalg.matrix_rank(X) < k:
            self.reason = "design matrix is rank deficient or has no residual degrees of freedom"
            return

        XtX_inv = np.linalg.inv(X.T @ X)
        A = XtX_inv @ X.T                                            # (k, n)
        self.b_hat = float((A @ y)[self.j])
        resid = y - X @ (A @ y)
        V = _cr0_variance(X, resid, self.seg_starts, XtX_inv)[0]
        var_j = float(V[self.j, self.j])
        if not np.isfinite(var_j) or var_j <= 0:
            self.reason = "the observed CR0 variance is zero or not finite"
            return
        self.se_cr0 = float(np.sqrt(var_j))

        # The two residual pieces. Under the restricted (null-imposed) variant the residuals are
        # taken from the model that FORCES the coefficient to the candidate value, which is what
        # gives the method its size properties, and they are affine in that value. Under the
        # unrestricted variant they are the ordinary residuals and do not depend on it at all.
        if impose_null:
            keep = [i for i in range(k) if i != self.j]
            if keep:
                Xr = X[:, keep]
                Pr = Xr @ np.linalg.pinv(Xr)
                u0 = y - Pr @ y
                u1 = X[:, self.j] - Pr @ X[:, self.j]
            else:
                u0, u1 = y.copy(), X[:, self.j].copy()
            self.centre_at_bhat = False
        else:
            u0, u1 = resid, np.zeros_like(resid)
            self.centre_at_bhat = True

        W, self.method, self.n_sign_vectors = _rademacher_weights(self.n_clusters, n_boot, seed)
        self.n_boot = int(W.shape[0])
        self.impose_null = bool(impose_null)

        # Accumulate, in blocks of replications to bound memory: the affine pieces of the bootstrap
        # coefficient, and the three matrices that make the CR0 meat a quadratic in the candidate
        # value.
        self.num0 = np.empty(self.n_boot, float)
        self.num1 = np.empty(self.n_boot, float)
        self.M0 = np.empty((self.n_boot, k, k), float)
        self.M1 = np.empty((self.n_boot, k, k), float)
        self.M2 = np.empty((self.n_boot, k, k), float)
        Aj = A[self.j]
        for s in range(0, self.n_boot, chunk):
            Wb = np.repeat(W[s:s + chunk], counts, axis=1)           # (b, n) sign per CLUSTER
            # One sign-flipped copy of each residual piece. The bootstrap coefficient is read off
            # with the ordinary OLS operator, and the bootstrap residuals are formed by removing the
            # fitted part, both of which are linear in the weighted residuals.
            U0w, U1w = Wb * u0[None, :], Wb * u1[None, :]
            self.num0[s:s + Wb.shape[0]] = U0w @ Aj
            self.num1[s:s + Wb.shape[0]] = U1w @ Aj
            E0 = U0w - (U0w @ A.T) @ X.T
            E1 = U1w - (U1w @ A.T) @ X.T
            Sp = np.empty((k, Wb.shape[0], self.n_clusters), float)
            Sq = np.empty_like(Sp)
            for i in range(k):
                Sp[i] = np.add.reduceat(E0 * X[:, i], self.seg_starts, axis=1)
                Sq[i] = np.add.reduceat(E1 * X[:, i], self.seg_starts, axis=1)
            self.M0[s:s + Wb.shape[0]] = np.einsum("ibg,jbg->bij", Sp, Sp)
            self.M1[s:s + Wb.shape[0]] = np.einsum("ibg,jbg->bij", Sp, Sq)
            self.M2[s:s + Wb.shape[0]] = np.einsum("ibg,jbg->bij", Sq, Sq)
        self.XtX_inv = XtX_inv
        self.available = True

    # -- the achievable resolution of the p-value ---------------------------------------------
    @property
    def enumerable(self):
        return self.n_clusters <= MAX_ENUMERABLE_CLUSTERS

    @property
    def p_resolution(self):
        """The smallest p-value this configuration can return.

        When the weight space is enumerated the floor is 2 / 2**G, not 1 / 2**G, because the
        all-plus-one and all-minus-one sign vectors both reproduce the observed sample under the
        imposed null and therefore always tie with the observed statistic. When it is sampled the
        floor is the usual 1 / (n_boot + 1).
        """
        if self.method == "enumerated":
            return 2.0 / float(self.n_sign_vectors)
        return 1.0 / float(self.n_boot + 1)

    def t_star(self, b0):
        """The bootstrap distribution of the t statistic at candidate value ``b0``."""
        num = self.num0 - b0 * self.num1
        meat = self.M0 - b0 * (self.M1 + np.swapaxes(self.M1, 1, 2)) + (b0 ** 2) * self.M2
        V = np.einsum("ip,bpq,qj->bij", self.XtX_inv, meat, self.XtX_inv)
        var = V[:, self.j, self.j]
        with np.errstate(invalid="ignore", divide="ignore"):
            return num / np.sqrt(np.where(var > 0, var, np.nan))

    def t_obs(self, b0):
        """The observed statistic, always the studentised distance from the candidate value."""
        return (self.b_hat - b0) / self.se_cr0

    def p_value(self, b0=0.0):
        """Two-sided bootstrap-t p-value for the hypothesis that the coefficient equals ``b0``."""
        ts = self.t_star(b0)
        tob = abs(self.t_obs(b0))
        good = np.isfinite(ts)
        # A tolerance is needed because the all-plus-one weight vector reconstructs the observed
        # sample exactly in arithmetic but only to rounding in floating point, and that replication
        # must be counted as the tie it is rather than dropped by a strict comparison.
        tol = 1e-9 * max(1.0, tob)
        hits = int((np.abs(ts[good]) >= tob - tol).sum())
        n_used = int(good.sum())
        if n_used == 0:
            return float("nan"), 0, 0
        if self.method == "enumerated":
            return float(hits) / float(n_used), hits, n_used
        return float(1 + hits) / float(n_used + 1), hits, n_used


def wild_cluster_bootstrap_t(y, X, groups, *, coef_index=1, n_boot=999, seed=0, impose_null=True,
                             null_value=0.0):
    """Wild cluster bootstrap-t p-value for one coefficient, valid at small cluster counts.

    Cameron, Gelbach and Miller (2008). The outcome is re-generated many times from a model that
    holds the coefficient at ``null_value``, with the sign of each cluster's residual vector flipped
    at random, and the same cluster-robust t statistic is recomputed on every replication. The
    observed statistic is then compared with that distribution.

    WHY THE RESTRICTED VARIANT IS THE DEFAULT. ``impose_null=True`` re-generates the data from the
    model in which the null is TRUE (the WCR variant of the original paper). This is the choice that
    gives the method its size properties, because the distribution being built is then the
    distribution of the statistic under the hypothesis actually being tested; the unrestricted
    variant builds it around the estimate instead, and Cameron, Gelbach and Miller (2008, section
    IV) report that it over-rejects in exactly the few-cluster range this module works in. The
    argument is left as an explicit keyword rather than hard-wired because the two variants differ
    by a diagnosis rather than a detail, and a reader of this code should be able to see which was
    used and reproduce the other.

    Returns a dictionary with the p-value, the number of replications actually used, the number of
    clusters, the observed t statistic, and the achievable resolution of the p-value. It also
    reports whether the weight space was small enough to enumerate and how many distinct sign
    vectors exist, so a reader can see when the p-value is coarse rather than having to know that
    Rademacher weights on G clusters admit only 2**G possibilities.
    """
    plan = _BootstrapPlan(y, X, groups, coef_index=coef_index, n_boot=n_boot, seed=seed,
                          impose_null=impose_null)
    if not plan.available:
        return {"available": False, "reason": plan.reason, "p": None, "n_clusters": plan.n_clusters,
                "n_boot": 0, "t_obs": None, "p_resolution": None}
    p, hits, used = plan.p_value(null_value)
    return {"available": True, "p": p, "n_boot": used, "n_boot_requested": plan.n_boot,
            "n_clusters": plan.n_clusters, "t_obs": float(plan.t_obs(null_value)),
            "p_resolution": plan.p_resolution, "enumerable": plan.enumerable,
            "n_sign_vectors": int(plan.n_sign_vectors), "weights": "rademacher",
            "draw": plan.method, "impose_null": plan.impose_null, "coef_index": int(coef_index),
            "null_value": float(null_value), "estimate": plan.b_hat, "se_cr0": plan.se_cr0,
            "n": int(plan.n), "n_exceedances": hits,
            "note": ("wild cluster bootstrap-t, Rademacher weights drawn once per cluster, "
                     f"{plan.method} weight space of {plan.n_sign_vectors} sign vectors "
                     f"(Cameron, Gelbach and Miller 2008)")}


def wild_cluster_bootstrap_ci(y, X, groups, *, coef_index=1, n_boot=999, seed=0, alpha=0.05,
                              n_grid=161, max_widen=6, refine_steps=48):
    """Confidence interval for one coefficient by INVERTING the bootstrap-t test.

    The interval is the set of candidate coefficient values the bootstrap-t does not reject at level
    ``alpha``. This is the only way to get an interval with the same small-sample properties as the
    p-value: taking the bootstrap p-value and then reporting the CR0 interval beside it would pair
    valid inference with the invalid interval it was brought in to replace, and a reader comparing
    the two would find the interval excluding zero while the p-value did not.

    THE COST, SINCE THE ALTERNATIVE WAS TO SUBSTITUTE SOMETHING CHEAPER. Full inversion is done, not
    approximated. It is affordable because the restricted residuals are affine in the candidate
    value, so one set of replications serves the whole grid (see ``_BootstrapPlan``); the grid
    therefore costs a few small matrix products per candidate instead of a full set of bootstrap
    refits, and the endpoints are then refined by bisection to well past the precision anyone
    reports. Measured on a band-cell of the size this module sees — of the order of seven hundred
    spectral samples spread over eight to thirty-five setting epochs — a full inversion takes
    between 30 and 75 milliseconds against 0.2 to 0.3 milliseconds for the CR0 fit it replaces, so
    it is one to four hundred times the cost of the thing it replaces and still under a tenth of a
    second per edge. Scanning the 324 era-stratified band-cells of the RCS08 record takes about
    eleven seconds. The cost grows with the number of ROWS, not with the grid, so a cell with tens
    of thousands of samples takes seconds rather than milliseconds; that is worth knowing before
    calling this on a table that has not been reduced to band powers.

    The grid is centred on the point estimate, which is always inside the interval because the
    observed statistic is zero there and every replication ties with it. If the accepted set reaches
    the edge of the grid the grid is widened and retried; if it still reaches the edge, or if the
    achievable p-value floor is above ``alpha`` so that nothing can be rejected at all, the interval
    is UNBOUNDED and is reported as absent with the reason stated. An absent interval is not a
    failure of the computation, it is the honest answer when a five-cluster sign-flip distribution
    cannot deliver a five percent test.
    """
    plan = _BootstrapPlan(y, X, groups, coef_index=coef_index, n_boot=n_boot, seed=seed,
                          impose_null=True)
    out = {"available": False, "ci": None, "alpha": float(alpha), "reason": ""}
    if not plan.available:
        out["reason"] = plan.reason
        out["n_clusters"] = plan.n_clusters
        return out
    p0, _, _ = plan.p_value(0.0)
    out.update({"available": True, "p_at_null": p0, "estimate": plan.b_hat,
                "se_cr0": plan.se_cr0, "n_clusters": plan.n_clusters, "n_boot": plan.n_boot,
                "draw": plan.method, "enumerable": plan.enumerable,
                "n_sign_vectors": int(plan.n_sign_vectors),
                "p_resolution": plan.p_resolution, "n": int(plan.n)})
    if plan.p_resolution > alpha:
        out["ci_unbounded"] = True
        out["reason"] = (f"the {plan.method} Rademacher weight space on {plan.n_clusters} clusters "
                         f"cannot produce a p-value below {plan.p_resolution:.4f}, which is above "
                         f"alpha = {alpha}, so no candidate value is rejected and the interval is "
                         "unbounded in both directions")
        return out

    half = 10.0 * plan.se_cr0
    grid = accept = None
    for _ in range(int(max_widen)):
        grid = plan.b_hat + np.linspace(-half, half, int(n_grid))
        accept = np.array([plan.p_value(float(b))[0] > alpha for b in grid])
        if not (accept[0] or accept[-1]):
            break
        half *= 4.0
    else:
        out["ci_unbounded"] = True
        out["reason"] = ("the accepted set still reached the edge of a grid spanning "
                         f"+/- {half / plan.se_cr0:.0f} CR0 standard errors, so the interval is "
                         "treated as unbounded rather than silently truncated at the grid")
        return out

    centre = int(np.argmin(np.abs(grid - plan.b_hat)))
    lo_i = centre
    while lo_i > 0 and accept[lo_i - 1]:
        lo_i -= 1
    hi_i = centre
    while hi_i < accept.size - 1 and accept[hi_i + 1]:
        hi_i += 1

    def _boundary(inside, outside):
        for _ in range(int(refine_steps)):
            mid = 0.5 * (inside + outside)
            if plan.p_value(float(mid))[0] > alpha:
                inside = mid
            else:
                outside = mid
        return 0.5 * (inside + outside)

    lo = _boundary(grid[lo_i], grid[lo_i - 1])
    hi = _boundary(grid[hi_i], grid[hi_i + 1])
    out["ci"] = (float(lo), float(hi))
    out["ci_unbounded"] = False
    out["n_grid"] = int(n_grid)
    # The accepted set of a bootstrap test need not be an interval. When it is not, the reported
    # interval is the connected component containing the point estimate, and the reader is told,
    # because quietly reporting the hull of a disconnected set would overstate what was accepted.
    outside = int(accept.sum()) - (hi_i - lo_i + 1)
    out["acceptance_nonconvex"] = bool(outside > 0)
    out["n_accepted_outside_reported_interval"] = int(max(outside, 0))
    return out


def _small_sample_inference(y, X, groups, *, coef_index=1, n_boot=999, seed=0, alpha=0.05):
    """The p-value and interval that the three edges use when the cluster count is below
    ``MIN_RELIABLE_CLUSTERS``, together with the sentence that says so on the estimate.

    Factored out so that all three edges switch estimators identically. An edge that switched on a
    slightly different condition, or described the switch differently, would leave a reader
    comparing two edges unable to tell whether a difference between them was in the data or in the
    inference.
    """
    ci = wild_cluster_bootstrap_ci(y, X, groups, coef_index=coef_index, n_boot=n_boot, seed=seed,
                                   alpha=alpha)
    if not ci.get("available"):
        return None, None, ("INFERENCE UNAVAILABLE: the wild cluster bootstrap could not be formed "
                            f"({ci.get('reason')}), and the CR0 interval is not reported in its "
                            "place because at this cluster count it would be too narrow."), ci
    floor = ci["p_resolution"]
    where = ("the whole Rademacher weight space of "
             f"{ci['n_sign_vectors']} sign vectors was enumerated exactly"
             if ci["draw"] == "enumerated" else
             f"{ci['n_boot']} replications were drawn from the {ci['n_sign_vectors']} possible "
             "sign vectors")
    note = (f"INFERENCE FROM THE WILD CLUSTER BOOTSTRAP-t, not from CR0. With {ci['n_clusters']} "
            f"clusters — below the {MIN_RELIABLE_CLUSTERS} at which the cluster-robust variance "
            "estimator has an asymptotic argument behind it — CR0 intervals are too narrow and "
            "manufacture resolution. The p-value and interval reported here come instead from the "
            "restricted wild cluster bootstrap-t with Rademacher weights drawn once per cluster "
            f"(Cameron, Gelbach and Miller 2008); {where}, and the smallest p-value this weight "
            f"space can return is {floor:.4g}. The interval is the set of coefficient values that "
            "test does not reject, obtained by inverting it.")
    if ci.get("ci_unbounded"):
        note += (" THE INTERVAL IS UNBOUNDED and is reported as absent: " + ci.get("reason", "")
                 + ". The edge is therefore unresolved, which is a statement about how few "
                   "clusters there are and not about how large the effect is.")
    if ci.get("acceptance_nonconvex"):
        note += (f" The bootstrap accepted {ci['n_accepted_outside_reported_interval']} candidate "
                 "values outside the reported interval; the interval given is the connected "
                 "component containing the point estimate.")
    return ci["p_at_null"], ci["ci"], note, ci


# --- What the closed-loop page inherits: how well a band tells high pain from low pain ------
#
# WHY THIS IS A CLASSIFICATION QUANTITY AND NOT A SLOPE. The stimulator changes what it is doing
# when band power crosses a value that has been programmed into it. That is a yes-or-no decision
# about the state of the brain signal: either the power is above the programmed value or it is
# below it. So the number that says whether a band is worth using to drive that decision should be
# a number about telling two states apart, and the area under the curve is exactly that: it is the
# chance that a randomly chosen high-pain moment has more power in the band than a randomly chosen
# low-pain moment. A straight-line slope answers a different question (how many pain points go with
# one unit of power) and it does not tell a reader how well the two pain states can be separated.
# The earlier version of this code fitted that slope; it has been removed, on the PI's instruction,
# and replaced by the two tables below.
#
# 0.5 IS THE VALUE THAT MEANS NOTHING WAS FOUND. An area under the curve of 0.5 is what coin
# flipping gives. So the question a reader asks of every row of the table below is whether the
# confidence interval stays wholly on one side of 0.5. An interval that touches or crosses 0.5
# means nothing was established for that band, which is NOT the same as establishing that the band
# is useless.
#
# THE THREE ANSWERS ARE WORDS, NOT True OR False. This project has been damaged three separate
# times by turning this answer into a yes-or-no value. "We could not work this out" and "we worked
# it out and this band separates high pain from low pain no better than coin flipping" are
# completely different statements, and a True/False value has no room for the first one, so it gets
# stored as False and then read as a negative finding. A band that was never assessed then appears
# in a report as a band that failed, which is how a real biomarker gets thrown away. The three
# words below cannot be collapsed by accident, because nothing downstream can treat a string as a
# yes-or-no value without saying so in its own source.
#: The interval stays wholly on one side of the no-relationship value, so something was established.
BAND_PAIN_ESTABLISHED = "established"
#: The number was computed, but its interval includes the no-relationship value. Nothing established.
BAND_PAIN_NOT_RESOLVED = "not_resolved"
#: The number was never computed, because the data it needs was not there. Nothing established.
BAND_PAIN_NOT_ASSESSED = "not_assessed"

#: The band centre frequencies both export tables cover by default: every whole number of hertz
#: from 8 to 30 inclusive, which with the 5 Hz band width used throughout this project means bands
#: spanning 5.5-10.5 Hz up to 27.5-32.5 Hz. 8 to 30 Hz is the range the PI asked for and it is also
#: the range the Percept stimulator will sense a band in. Note that the bands at the two ends of
#: this list stick out past 8 Hz and past 30 Hz, so every row of both tables carries a column
#: saying whether that row's band lies wholly inside 8 to 30 Hz.
DEFAULT_PAIN_BAND_CENTERS_HZ = tuple(float(c) for c in range(8, 31))


def _report_clusters_in_time_order(group_ids, row_times, row_values):
    """Put the pain reports in the time order they happened, and choose the resampling block length.

    Both export tables get their confidence interval by resampling whole pain reports, and one of
    the two resampling schemes (the moving block) only means anything if neighbouring positions in
    the list of reports are neighbouring in time. So the reports are sorted by the earliest sample
    time belonging to each of them. A report whose sample times will not parse is put at the end,
    keeping the order its identifier already had, which for the identifiers this project uses is
    the order the pain reports were matched in.

    ``group_ids`` is one pain-report identifier per row, ``row_times`` one time string per row (or
    None), and ``row_values`` one continuous pain score per row, which is what the block length is
    chosen from. Returns (cluster_of_row, n_reports, block_len).
    """
    uniq = np.unique(group_ids)
    n_cl = len(uniq)
    if n_cl == 0:
        return np.zeros(0, dtype=int), 0, 1
    if row_times is not None and len(row_times) == len(group_ids):
        t_epoch = pd.to_datetime(pd.Series([str(s) for s in row_times]), errors="coerce", utc=True)
        t_sec = t_epoch.astype("int64").to_numpy() / 1e9
        cl_time = {}
        for c in uniq:
            vals = t_sec[group_ids == c]
            vals = vals[np.isfinite(vals) & (vals > 0)]
            cl_time[c] = float(vals.min()) if vals.size else np.inf
        order = sorted(range(n_cl), key=lambda i: (cl_time[uniq[i]], uniq[i]))
    else:
        order = list(range(n_cl))
    ordered = uniq[np.asarray(order, dtype=int)]
    cl_pos = {c: i for i, c in enumerate(ordered)}
    cluster_of_row = np.array([cl_pos[c] for c in group_ids], dtype=int)
    vals = np.asarray(row_values, dtype=float)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        cl_mean = np.array([float(np.nanmean(vals[group_ids == c])) for c in ordered])
    return cluster_of_row, n_cl, _auto_block_len(cl_mean)


def _one_report_one_vote_weights(cluster_of_row, n_reports):
    """One weight per row, so that every pain report counts once no matter how many spectral
    samples happened to be matched to it.

    A pain report that the recording happened to cover with twenty spectral samples is not twenty
    independent observations of that patient's pain; it is one observation looked at twenty times.
    How many samples a report attracted is a fact about when the device was recording, not about
    how informative that report is. So each row is weighted by one divided by the number of rows
    belonging to its pain report, which makes every report carry a total weight of exactly one.

    This matters more than it looks. Both numbers below are averages over PAIRS of samples, one
    high-pain and one low-pain, so without this weighting a report with many samples on one side
    contributes its own sample count MULTIPLIED BY the other side's sample count of the pairs, and
    a single well-covered day can decide the answer for the whole band.
    """
    counts = np.bincount(cluster_of_row, minlength=int(n_reports)).astype(float)
    counts[counts <= 0] = 1.0
    return 1.0 / counts[cluster_of_row]


def _weighted_pearson_matrix(x, y, W):
    """Pearson correlation between x and y for EVERY row of a (B, N) weight matrix at once.

    ``W[b, j]`` is how many times row j appears in resample b (whole numbers for a bootstrap, ones
    and zeros for leaving one report out), multiplied by that row's one-report-one-vote weight. The
    same weighted-mean, weighted-variance and weighted-covariance formulas as an ordinary Pearson
    correlation, just carrying the weights through. Returns a (B,) array; resamples with no spread
    left in either variable come back as NaN, and the caller drops those.
    """
    W = np.asarray(W, dtype=np.float64)
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    wsum = W.sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        mx = (W * x[None, :]).sum(axis=1) / wsum
        my = (W * y[None, :]).sum(axis=1) / wsum
        dx = x[None, :] - mx[:, None]
        dy = y[None, :] - my[:, None]
        cxy = (W * dx * dy).sum(axis=1)
        cxx = (W * dx * dx).sum(axis=1)
        cyy = (W * dy * dy).sum(axis=1)
        r = cxy / np.sqrt(cxx * cyy)
    r = np.asarray(r, dtype=float)
    r[~np.isfinite(wsum) | (wsum <= 0)] = np.nan
    r[~np.isfinite(r)] = np.nan
    return r


def _resample_weight_matrix(cluster_of_row, n_reports, n_boot, block_len, rng, row_weight=None):
    """The (B, N) weight matrix that resamples whole pain reports with replacement.

    With ``block_len`` of 1 this draws pain reports one at a time with replacement, which is the
    ordinary bootstrap over reports. With a longer block length it draws runs of neighbouring
    reports instead (a circular moving block, Politis and Romano), which keeps the tendency of pain
    scores on nearby days to resemble each other; ``_auto_block_len`` chooses the length from the
    measured autocorrelation of the pain scores and returns 1 when there is none.

    Written out here rather than reusing ``_block_bootstrap_aucs`` because that function goes
    straight on to compute an area under the curve, while both export tables need the SAME weight
    matrix fed to two different statistics. The drawing rules are identical to that function's, and
    there is a test that checks the two agree when both are given the same seed.
    """
    B = int(n_boot)
    K = int(n_reports)
    if block_len is None or block_len <= 1:
        picks = rng.integers(0, K, size=(B, K))
    else:
        L = int(block_len)
        n_blocks = int(np.ceil(K / L))
        starts = rng.integers(0, K, size=(B, n_blocks))
        offs = np.arange(L)
        idx = (starts[:, :, None] + offs[None, None, :]) % K
        picks = idx.reshape(B, -1)[:, :K]
    cl_counts = np.zeros((B, K), dtype=np.float64)
    np.add.at(cl_counts, (np.arange(B)[:, None], picks), 1.0)
    W = cl_counts[:, cluster_of_row]
    if row_weight is not None:
        W = W * np.asarray(row_weight, dtype=np.float64)[None, :]
    return W


def _leave_one_report_out_weight_matrix(cluster_of_row, n_reports, row_weight=None):
    """The (K, N) weight matrix that leaves out one whole pain report at a time.

    Row i is every sample except the ones belonging to report i. This is what the lopsidedness
    correction on the confidence interval is estimated from (see ``_bca_ci``): how much the answer
    moves when any single pain report is dropped.
    """
    K = int(n_reports)
    W = np.ones((K, len(cluster_of_row)), dtype=np.float64)
    for i in range(K):
        W[i, cluster_of_row == i] = 0.0
    if row_weight is not None:
        W = W * np.asarray(row_weight, dtype=np.float64)[None, :]
    return W


def _bootstrap_two_sided_p(boot, null_value):
    """A two-sided p-value read off the resamples, against the value that means no relationship.

    Twice the smaller of the share of resamples at or below the no-relationship value and the share
    at or above it, capped at 1. The smallest number this can return is one divided by one more
    than the count of usable resamples, and that number is returned alongside it so that nobody
    reads a p-value of 0.002 from 500 resamples as though it had been measured to that precision.
    """
    b = np.asarray(boot, dtype=float)
    b = b[np.isfinite(b)]
    n = int(b.size)
    if n < 2:
        return None, None
    resolution = 1.0 / (n + 1.0)
    lo_share = float(np.mean(b <= null_value))
    hi_share = float(np.mean(b >= null_value))
    p = min(1.0, 2.0 * min(lo_share, hi_share))
    return float(max(p, resolution)), float(resolution)


def _pain_split(labels, *, strategy="tertile", low_pct=33.3333, high_pct=66.6667,
                pain_cutoff=None, rating_group=None):
    """Split the continuous pain scores into high pain and low pain, and say in words how.

    The splitting itself is ``_binarize_labels``, which is what the biomarker page already uses, so
    the two agree by construction. What this adds is the sentence and the two numbers that have to
    travel with every exported row: a reader who is shown a number for how well a band separates
    high pain from low pain cannot interpret it at all without being told where the line between
    high and low was drawn.

    THE LINE IS DRAWN ON ONE PAIN SCORE PER PAIN REPORT, not on one per spectral sample. If it were
    drawn on the samples, a pain report that the device happened to cover with many recordings would
    appear many times in the list the percentiles are computed from and would drag the line towards
    its own value, so whether a pain score counted as high or low would depend partly on when the
    device was recording. ``_binarize_labels`` does this when it is given the report identifiers,
    and it is given them here.

    Returns (binary_labels, description_sentence, low_cut, high_cut).
    """
    y = _binarize_labels(labels, strategy=strategy, low_pct=low_pct, high_pct=high_pct,
                         pain_cutoff=pain_cutoff, rating_group=rating_group)
    v = np.asarray(labels, dtype=float)
    ref = v[np.isfinite(v)]
    if rating_group is not None:
        rg = np.asarray(rating_group)
        if rg.shape == v.shape:
            seen = {}
            fin = np.isfinite(v)
            for gid, val in zip(rg[fin], v[fin]):
                seen.setdefault(gid, float(val))
            if seen:
                ref = np.asarray(list(seen.values()), dtype=float)
    if ref.size == 0:
        return y, "no pain scores were present, so no split could be made", None, None
    if strategy in ("tertile", "percentile"):
        lo_q = 33.3333 if strategy == "tertile" else float(low_pct)
        hi_q = 66.6667 if strategy == "tertile" else float(high_pct)
        lo = float(np.percentile(ref, lo_q))
        hi = float(np.percentile(ref, hi_q))
        why = (f"the pain scores were split into thirds, using one score per pain report: a score "
               f"of {lo:.3g} or below counts as low pain, {hi:.3g} or above counts as high pain, "
               f"and the scores in between were left out of this comparison")
        return y, why, lo, hi
    if strategy == "kmeans":
        why = ("the pain scores were split into two groups by clustering the scores themselves, "
               "using one score per pain report; the halfway point between the two group averages "
               "is the line between low pain and high pain")
        return y, why, None, None
    cut = (float(pain_cutoff) if (strategy == "cutoff" and pain_cutoff is not None)
           else float(np.median(ref)))
    named = "the number the caller supplied" if strategy == "cutoff" else "the middle pain score"
    why = (f"the pain scores were split at {cut:.3g}, which is {named}, using one score per pain "
           f"report: that score or above counts as high pain, below it counts as low pain, and no "
           f"score was left out")
    return y, why, cut, cut


def _blank_band_answer(reason, *, n_samples=0, n_reports=0, **extra):
    """The result for a band that could not be assessed at all: no number, and the reason why."""
    out = dict(extra)
    out["answer"] = BAND_PAIN_NOT_ASSESSED
    out["why"] = reason
    out["n_spectral_samples"] = int(n_samples)
    out["n_pain_reports"] = int(n_reports)
    return out


def band_pain_auc(power, pain_labels, report_group, *, times=None, strategy="tertile",
                  low_pct=33.3333, high_pct=66.6667, pain_cutoff=None, n_boot=500, seed=0,
                  alpha=0.05, power_feature="band power"):
    """How well one band's power tells this patient's high-pain moments from the low-pain ones.

    THE LITERAL QUANTITY. The number returned as ``auc`` is the chance that a randomly picked
    high-pain moment has MORE power in this band than a randomly picked low-pain moment, with tied
    values counting as half. 0.5 is what coin flipping gives. Above 0.5 means more power in the band
    goes with more pain; below 0.5 means more power goes with less pain. Both are informative and
    both are reported as they come out.

    WHICH WAY ROUND THE COMPARISON GOES IS FIXED IN ADVANCE, and this is a deliberate difference
    from ``deployment_roc``. That function reports the larger of the value and one minus the value,
    which can never fall below 0.5, so its interval cannot honestly straddle 0.5 and it needs a
    correction term to be read against. Here the comparison is fixed before the data is looked at --
    more power against more pain -- so a value below 0.5 is a real reading (more power in this band
    goes with LESS pain) and 0.5 is exactly what no relationship gives, with no correction needed.
    That is what makes the interval-against-0.5 test in the exported table mean what a reader will
    take it to mean.

    EVERY PAIN REPORT COUNTS ONCE, however many spectral samples were matched to it, and the
    confidence interval comes from resampling whole pain reports rather than individual samples.
    Both of those are the same choice for the same reason: the pain report is the thing that carries
    one independent observation of this patient's pain, and the number of spectral samples attached
    to one report is a fact about recording coverage. See ``_one_report_one_vote_weights``.

    WHICH POWER SCALE, AND WHY IT DOES NOT MATTER FOR THIS NUMBER. This number depends only on the
    ORDER of the power values, not on their size, so it comes out identically whether the power is
    in the stimulator's own units, in a logarithm of those units, or in any other rescaling that
    keeps the values in the same order. That is worth stating because everything else in this
    project has to be careful to stay in the stimulator's units. Here it makes no difference, and
    there is a test that checks it. ``power_feature`` is carried through to the result purely so the
    exported table can say what the numbers were computed on.

    THE INTERVAL IS REPORTED TWICE. ``auc_low``/``auc_high`` are the plain 2.5th and 97.5th
    percentiles of the resamples, and that is the interval the three-word answer reads, because it
    is the more cautious of the two and it is the one this project's earlier work settled on for
    deciding whether anything beats coin flipping. ``auc_low_corrected``/``auc_high_corrected``
    additionally correct for the resamples sitting off-centre and for their lopsidedness (the
    bias-corrected and accelerated interval of Efron, see ``_bca_ci``). Both are published, so the
    choice is visible rather than tacit.

    Returns a dictionary whose ``answer`` is one of ``BAND_PAIN_ESTABLISHED``,
    ``BAND_PAIN_NOT_RESOLVED`` or ``BAND_PAIN_NOT_ASSESSED`` -- never a True or False value.
    """
    base = {"auc": None, "auc_low": None, "auc_high": None,
            "auc_low_corrected": None, "auc_high_corrected": None,
            "auc_per_sample": None, "no_relationship_value": 0.5,
            "p_two_sided": None, "p_smallest_reportable": None,
            "n_high_pain_samples": 0, "n_low_pain_samples": 0,
            "pain_split_rule": None, "pain_low_cut": None, "pain_high_cut": None,
            "n_resamples_used": 0, "resampling_unit": "one pain report",
            "block_length_reports": None, "power_feature": str(power_feature),
            "confidence_level": float(1.0 - alpha)}
    x = np.asarray(power, dtype=float)
    lab = np.asarray(pain_labels, dtype=float)
    if x.size == 0 or lab.size != x.size:
        return _blank_band_answer("no band power values were available for this contact and band",
                                  **base)
    if report_group is None:
        return _blank_band_answer(
            "the pain report identifiers were not supplied, so every spectral sample would have to "
            "be counted as its own independent observation of this patient's pain. That is the "
            "pseudoreplication this project's audit was called to find, and it makes a band look "
            "more convincing than the data can support, so no number is computed here",
            n_samples=int(x.size), **base)
    rg = np.asarray(report_group)
    y_all, split_why, lo_cut, hi_cut = _pain_split(
        lab, strategy=strategy, low_pct=low_pct, high_pct=high_pct, pain_cutoff=pain_cutoff,
        rating_group=rg)
    base["pain_split_rule"] = split_why
    base["pain_low_cut"] = lo_cut
    base["pain_high_cut"] = hi_cut
    m = np.isfinite(x) & np.isfinite(y_all)
    n_ok = int(m.sum())
    if n_ok == 0:
        return _blank_band_answer(
            "no spectral sample had both a usable band power value and a pain score on one side of "
            "the high-or-low split", **base)
    xs = x[m]
    ys = y_all[m].astype(int)
    gs = rg[m]
    ts = (np.asarray(times)[m] if (times is not None and len(times) == x.size) else None)
    n_pos = int(np.sum(ys == 1))
    n_neg = int(np.sum(ys == 0))
    base["n_high_pain_samples"] = n_pos
    base["n_low_pain_samples"] = n_neg
    n_rep_seen = int(len(np.unique(gs)))
    if n_pos == 0 or n_neg == 0:
        return _blank_band_answer(
            f"all {n_ok} usable samples fell on the same side of the high-or-low pain split "
            f"({n_pos} high pain, {n_neg} low pain), so there is nothing to tell apart",
            n_samples=n_ok, n_reports=n_rep_seen, **base)
    cluster_of_row, n_reports, block_len = _report_clusters_in_time_order(gs, ts, lab[m])
    base["block_length_reports"] = int(block_len)
    if n_reports < 2:
        return _blank_band_answer(
            f"only {n_reports} pain report is behind these samples; resampling pain reports needs "
            "at least two, and a comparison resting on one report would say nothing about this "
            "patient beyond that single day",
            n_samples=n_ok, n_reports=n_reports, **base)
    w = _one_report_one_vote_weights(cluster_of_row, n_reports)
    auc = float(_weighted_auc_matrix(xs, ys, w[None, :])[0])
    auc_per_sample = float(_weighted_auc_matrix(xs, ys, np.ones((1, n_ok)))[0])
    if not np.isfinite(auc):
        return _blank_band_answer(
            "the comparison could not be formed on these samples even though both pain states are "
            "present, which happens when every band power value is the same number",
            n_samples=n_ok, n_reports=n_reports, **base)
    base["auc"] = auc
    base["auc_per_sample"] = (auc_per_sample if np.isfinite(auc_per_sample) else None)
    base["n_spectral_samples"] = n_ok
    base["n_pain_reports"] = n_reports
    rng = np.random.default_rng(seed)
    W = _resample_weight_matrix(cluster_of_row, n_reports, n_boot, block_len, rng, row_weight=w)
    boot = _weighted_auc_matrix(xs, ys, W)
    boot = boot[np.isfinite(boot)]
    base["n_resamples_used"] = int(boot.size)
    p, res = _bootstrap_two_sided_p(boot, 0.5)
    base["p_two_sided"] = p
    base["p_smallest_reportable"] = res
    if boot.size < BOOT_CI_VALID_FLOOR:
        base["answer"] = BAND_PAIN_NOT_RESOLVED
        base["why"] = (
            f"the value came out at {auc:.3f}, but only {int(boot.size)} of the {int(n_boot)} "
            f"resamples kept both pain states present, which is fewer than the "
            f"{BOOT_CI_VALID_FLOOR} this project requires before it will quote a confidence "
            "interval. No interval is given, so nothing is established either way. This says how "
            "few pain reports there are, not how small the effect is")
        return base
    lo = float(np.percentile(boot, 100.0 * alpha / 2.0))
    hi = float(np.percentile(boot, 100.0 * (1.0 - alpha / 2.0)))
    jack = _weighted_auc_matrix(
        xs, ys, _leave_one_report_out_weight_matrix(cluster_of_row, n_reports, row_weight=w))
    c_lo, c_hi, _z0, _a = _bca_ci(auc, boot, jack, alpha=alpha)
    base.update({"auc_low": lo, "auc_high": hi,
                 "auc_low_corrected": c_lo, "auc_high_corrected": c_hi})
    if lo > 0.5 or hi < 0.5:
        which = ("more power in this band goes with MORE pain" if auc > 0.5
                 else "more power in this band goes with LESS pain")
        base["answer"] = BAND_PAIN_ESTABLISHED
        base["why"] = (
            f"the value is {auc:.3f} and its {100 * (1 - alpha):.0f}% interval runs from {lo:.3f} "
            f"to {hi:.3f}, which stays wholly on one side of the 0.5 that coin flipping would "
            f"give, so this band does tell high pain from low pain in this patient: {which}")
        # A COLLAPSED INTERVAL IS NOT A PRECISE ONE, and saying so is not optional. When the two
        # pain states do not overlap at all in this band, every resample returns the same value and
        # the interval comes out with no width. Quoting "0.000 to 0.000" without this sentence
        # would invite a reader to take the value as known exactly, when what has actually happened
        # is that resampling a handful of pain reports has run out of ways to disagree with itself.
        if abs(hi - lo) < 1e-12:
            base["why"] += (
                f". THE INTERVAL HAS NO WIDTH, and that is a limit of the method rather than a "
                f"claim of certainty: the high-pain and low-pain samples do not overlap at all in "
                f"this band, so every one of the {int(boot.size)} resamples returned the same "
                f"value. With only {n_reports} pain reports behind it, a complete separation is "
                f"still consistent with a range of true values, and this interval cannot show that "
                f"range")
    else:
        base["answer"] = BAND_PAIN_NOT_RESOLVED
        base["why"] = (
            f"the value is {auc:.3f} but its {100 * (1 - alpha):.0f}% interval runs from {lo:.3f} "
            f"to {hi:.3f}, which includes the 0.5 that coin flipping would give. Nothing is "
            f"established for this band: it may separate high pain from low pain, it may separate "
            f"them the other way round, or it may not separate them at all. This is not a finding "
            f"that the band is useless")
    return base


def band_pain_correlation(power, pain_labels, report_group, *, times=None, n_boot=500, seed=0,
                          alpha=0.05, power_feature="band power"):
    """The Pearson correlation between one band's power and the patient's pain score.

    THE LITERAL QUANTITY. ``pearson_r`` is the ordinary Pearson correlation coefficient between the
    band power of a spectral sample and the continuous pain score matched to it, on a scale from -1
    to +1. Nothing is split into high and low here; that is what ``band_pain_auc`` does. This is
    the quantity the plot at the bottom of the biomarker exploration page shows, and the PI asked
    for it to be exported as a table so the closed-loop side can read it beside the classification
    number.

    EVERY PAIN REPORT COUNTS ONCE. The correlation reported is weighted so that each pain report
    carries a total weight of one however many spectral samples were matched to it, for the reason
    set out in ``_one_report_one_vote_weights``. The unweighted per-sample correlation is reported
    beside it as ``pearson_r_per_sample``, because that is the number the page's own plot draws and
    a silent redefinition would leave a reader unable to reconcile the two.

    THE CONFIDENCE INTERVAL IS NOT THE TEXTBOOK ONE, on purpose. The usual interval for a
    correlation assumes every point is an independent observation. Here many spectral samples share
    a single pain report and therefore share its pain score exactly, so that assumption is false
    and the textbook interval comes out far too narrow. The interval here is obtained by resampling
    whole pain reports, which is the same resampling the classification number above uses, so the
    two tables' intervals mean the same kind of thing.

    THE POWER SCALE MATTERS FOR THIS NUMBER, unlike for the classification number. A correlation
    changes when the power is put through a logarithm, because a correlation is about straight-line
    agreement and a logarithm is not a straight line. ``power_feature`` therefore has to be read
    off every exported row before the number means anything.

    Returns a dictionary whose ``answer`` is one of the three words, never True or False. The value
    that means no relationship is 0 here, not 0.5.
    """
    base = {"pearson_r": None, "pearson_r_low": None, "pearson_r_high": None,
            "pearson_r_low_corrected": None, "pearson_r_high_corrected": None,
            "pearson_r_per_sample": None, "no_relationship_value": 0.0,
            "p_two_sided": None, "p_smallest_reportable": None,
            "pain_split_rule": ("none: this number uses the continuous pain score as it stands and "
                                "does not split it into high pain and low pain"),
            "n_resamples_used": 0, "resampling_unit": "one pain report",
            "block_length_reports": None, "power_feature": str(power_feature),
            "confidence_level": float(1.0 - alpha)}
    x = np.asarray(power, dtype=float)
    lab = np.asarray(pain_labels, dtype=float)
    if x.size == 0 or lab.size != x.size:
        return _blank_band_answer("no band power values were available for this contact and band",
                                  **base)
    if report_group is None:
        return _blank_band_answer(
            "the pain report identifiers were not supplied, so every spectral sample would have to "
            "be counted as its own independent observation of this patient's pain. That is the "
            "pseudoreplication this project's audit was called to find, and it makes a band look "
            "more convincing than the data can support, so no number is computed here",
            n_samples=int(x.size), **base)
    rg = np.asarray(report_group)
    m = np.isfinite(x) & np.isfinite(lab)
    n_ok = int(m.sum())
    if n_ok < 3:
        return _blank_band_answer(
            f"only {n_ok} spectral samples had both a usable band power value and a matched pain "
            "score, and a correlation needs at least three",
            n_samples=n_ok, n_reports=(int(len(np.unique(rg[m]))) if n_ok else 0), **base)
    xs = x[m]
    ys = lab[m]
    gs = rg[m]
    ts = (np.asarray(times)[m] if (times is not None and len(times) == x.size) else None)
    cluster_of_row, n_reports, block_len = _report_clusters_in_time_order(gs, ts, ys)
    base["block_length_reports"] = int(block_len)
    if n_reports < 3:
        return _blank_band_answer(
            f"only {n_reports} pain report(s) are behind these samples. A correlation against pain "
            "needs at least three different pain reports to be about this patient rather than "
            "about one or two particular days",
            n_samples=n_ok, n_reports=n_reports, **base)
    w = _one_report_one_vote_weights(cluster_of_row, n_reports)
    r = float(_weighted_pearson_matrix(xs, ys, w[None, :])[0])
    r_per_sample = float(_weighted_pearson_matrix(xs, ys, np.ones((1, n_ok)))[0])
    base["pearson_r_per_sample"] = (r_per_sample if np.isfinite(r_per_sample) else None)
    base["n_spectral_samples"] = n_ok
    base["n_pain_reports"] = n_reports
    if not np.isfinite(r):
        return _blank_band_answer(
            "the correlation could not be formed because the band power values, or the pain "
            "scores, are all the same number once each pain report is counted once",
            n_samples=n_ok, n_reports=n_reports, **base)
    base["pearson_r"] = r
    rng = np.random.default_rng(seed)
    W = _resample_weight_matrix(cluster_of_row, n_reports, n_boot, block_len, rng, row_weight=w)
    boot = _weighted_pearson_matrix(xs, ys, W)
    boot = boot[np.isfinite(boot)]
    base["n_resamples_used"] = int(boot.size)
    p, res = _bootstrap_two_sided_p(boot, 0.0)
    base["p_two_sided"] = p
    base["p_smallest_reportable"] = res
    if boot.size < BOOT_CI_VALID_FLOOR:
        base["answer"] = BAND_PAIN_NOT_RESOLVED
        base["why"] = (
            f"the correlation came out at {r:+.3f}, but only {int(boot.size)} of the "
            f"{int(n_boot)} resamples produced a usable value, which is fewer than the "
            f"{BOOT_CI_VALID_FLOOR} this project requires before it will quote a confidence "
            "interval. Nothing is established either way. This says how few pain reports there "
            "are, not how small the correlation is")
        return base
    lo = float(np.percentile(boot, 100.0 * alpha / 2.0))
    hi = float(np.percentile(boot, 100.0 * (1.0 - alpha / 2.0)))
    jack = _weighted_pearson_matrix(
        xs, ys, _leave_one_report_out_weight_matrix(cluster_of_row, n_reports, row_weight=w))
    c_lo, c_hi, _z0, _a = _bca_ci(r, boot, jack, alpha=alpha)
    base.update({"pearson_r_low": lo, "pearson_r_high": hi,
                 "pearson_r_low_corrected": c_lo, "pearson_r_high_corrected": c_hi})
    if lo > 0.0 or hi < 0.0:
        which = ("more power in this band goes with a higher pain score" if r > 0
                 else "more power in this band goes with a lower pain score")
        base["answer"] = BAND_PAIN_ESTABLISHED
        base["why"] = (
            f"the correlation is {r:+.3f} and its {100 * (1 - alpha):.0f}% interval runs from "
            f"{lo:+.3f} to {hi:+.3f}, which stays wholly on one side of zero, so a relationship is "
            f"established: {which}")
    else:
        base["answer"] = BAND_PAIN_NOT_RESOLVED
        base["why"] = (
            f"the correlation is {r:+.3f} but its {100 * (1 - alpha):.0f}% interval runs from "
            f"{lo:+.3f} to {hi:+.3f}, which includes zero. Nothing is established for this band: "
            f"the relationship may go either way or may not be there at all. This is not a finding "
            f"that the band is unrelated to pain")
    return base


def band_pain_auc_from_table(table, *, channel, center_hz, pain_column="nrs",
                             power_column="power_linear", group_column="report_id",
                             time_column=None, strategy="tertile", low_pct=33.3333,
                             high_pct=66.6667, pain_cutoff=None, n_boot=500, seed=0, alpha=0.05):
    """``band_pain_auc`` for a caller that already holds a tidy table of spectral samples.

    The closed-loop module builds its own table, one row per spectral sample, with columns for the
    sensing channel, the band centre frequency, the band power, the pain score and the pain report
    the sample belongs to. This pulls out the rows for one channel and one band centre and hands
    them to the same estimator the exported tables use, so the closed-loop page and the biomarker
    page cannot print two different numbers for the same band.
    """
    need = {power_column, pain_column, "channel", "center_hz"}
    have = set(table.columns) if table is not None else set()
    if table is None or len(table) == 0 or not need.issubset(have):
        return _blank_band_answer(
            f"the table handed in does not have the columns this needs: {sorted(need - have)}",
            auc=None, no_relationship_value=0.5, power_feature=str(power_column))
    d = table[(table.channel == channel) & (np.isclose(table.center_hz, center_hz))]
    if group_column not in d.columns:
        return _blank_band_answer(
            f"no {group_column} column: the grouping that makes each pain report count once is not "
            "there, and computing this without it would treat every spectral sample as an "
            "independent observation of the patient's pain, which is the pseudoreplication this "
            "project's audit was called to find",
            n_samples=int(len(d)), auc=None, no_relationship_value=0.5,
            power_feature=str(power_column))
    d = d.dropna(subset=[power_column, pain_column, group_column])
    if len(d) == 0:
        return _blank_band_answer(
            f"no rows are left for channel {channel} at a band centred on {float(center_hz):g} Hz "
            "once the rows missing the band power, the pain score or the pain report are dropped",
            auc=None, no_relationship_value=0.5, power_feature=str(power_column))
    times = (d[time_column].to_numpy() if (time_column and time_column in d.columns) else None)
    return band_pain_auc(d[power_column].to_numpy(float), d[pain_column].to_numpy(float),
                         d[group_column].to_numpy(), times=times, strategy=strategy,
                         low_pct=low_pct, high_pct=high_pct, pain_cutoff=pain_cutoff,
                         n_boot=n_boot, seed=seed, alpha=alpha, power_feature=str(power_column))


def _pooled_power_feature_name(td_detail):
    """A plain sentence naming what the band power values in these pooled spectra actually are.

    Written out on every row of both exported tables. Without it a reader has no way to know that
    the numbers are not the stimulator's own band power, and the correlation table in particular
    cannot be interpreted at all without knowing whether a logarithm was taken.
    """
    if td_detail is None:
        return "unknown"
    if td_detail.get("prelog", False):
        return ("the average over the band of a logarithm of power that was already standardised "
                "within each recording source before pooling; NOT the stimulator's own units, and "
                "the stimulator's units cannot be recovered from it")
    return ("ten times the base-ten logarithm of the average power over the band, computed here "
            "from the linear power in the pooled spectra")


def _sweep_contacts_and_bands(td_detail, channels, centers, band_width_hz):
    """Yield (channel name, band centre, band power per sample, pain scores, report identifiers,
    sample times) for every sensing contact pair and every band centre asked for.

    One place decides which contacts and which band centres a sweep covers, so the two exported
    tables cannot end up covering different ones and then being compared row for row by a reader
    who assumes they match.
    """
    chans = list(channels) if channels is not None else list(td_detail.get("chan_order", []))
    cens = list(centers) if centers is not None else list(DEFAULT_PAIN_BAND_CENTERS_HZ)
    for ch in chans:
        for fc in cens:
            feat = _band_feature_from_detail(td_detail, ch, float(fc),
                                             band_width_hz=float(band_width_hz))
            if feat is None:
                yield str(ch), float(fc), None, None, None, None
                continue
            bp, labels, rg, times = feat
            yield str(ch), float(fc), bp, labels, rg, times


def _band_row_header(channel, center_hz, band_width_hz):
    """The columns that name which contact pair, which side of the brain and which band a row is
    about.

    A channel name fixes the side of the brain: ZERO_THREE_RIGHT is contacts 0 and 3 on the RIGHT
    electrode. Both are spelled out as their own columns so no reader has to decode the device's
    spelling, and so a row can never be quoted without saying which side of the brain it came from.
    """
    fmt = format_channel(channel)
    w = float(band_width_hz)
    lo = float(center_hz) - w / 2.0
    hi = float(center_hz) + w / 2.0
    return {
        "channel": str(channel),
        "contacts": fmt.get("contacts"),
        "brain_side": (fmt.get("hemisphere") or "unknown"),
        "band_center_hz": float(center_hz),
        "band_low_hz": lo,
        "band_high_hz": hi,
        "band_width_hz": w,
        "band_fully_inside_8_to_30_hz": bool(lo >= 8.0 - 1e-9 and hi <= 30.0 + 1e-9),
    }


#: The columns both exported tables start with, in the order they appear.
_BAND_ROW_HEADER_COLUMNS = ["channel", "contacts", "brain_side", "band_center_hz", "band_low_hz",
                           "band_high_hz", "band_width_hz", "band_fully_inside_8_to_30_hz"]


def _order_export_columns(out, preferred):
    """Put the naming columns first, then the numbers a reader looks at first, then the rest."""
    lead = [c for c in _BAND_ROW_HEADER_COLUMNS if c in out.columns]
    tail = [c for c in preferred if c in out.columns and c not in lead]
    rest = [c for c in out.columns if c not in lead + tail]
    return out[lead + tail + rest]


def band_pain_auc_export(td_detail, *, channels=None, centers=None, band_width_hz=5.0,
                         strategy="tertile", low_pct=33.3333, high_pct=66.6667, pain_cutoff=None,
                         n_boot=500, seed=0, alpha=0.05):
    """THE TABLE THE CLOSED-LOOP PAGE INHERITS: one row per sensing contact pair per band centre,
    saying how well that band's power tells this patient's high-pain moments from the low-pain ones.

    One row for every contact pair present in the pooled spectra and every band centre in
    ``centers`` (by default every whole hertz from 8 to 30). Each row carries the value, its
    confidence interval, how many pain reports are behind it, how the pain scores were split into
    high and low, and a three-word answer that is never a True or False value.

    HOW TO READ A ROW. ``auc`` of 0.5 is what coin flipping gives, so the question is whether the
    interval from ``auc_low`` to ``auc_high`` stays wholly on one side of 0.5. When it does,
    ``answer`` is "established". When it crosses 0.5, ``answer`` is "not_resolved", and that means
    nothing was established for that band -- it is NOT a finding that the band is useless. When the
    number could not be computed at all, ``answer`` is "not_assessed" and there is no value in the
    row. Those three are different and must stay different.

    WHAT THE POWER IS. The band power here is whatever ``_band_feature_from_detail`` returns for the
    pooled spectra it is handed, which for the biomarker page's own pooled spectra is the average
    over the band of a logarithm of power that has already been standardised within each recording
    source so that recordings of different kinds can be pooled. That is NOT the stimulator's own
    units, and the stimulator's units cannot be recovered from it, because the standardising step
    threw the scale away. It does not matter for THIS table -- the value above depends only on the
    order of the power values, so any rescaling that keeps them in order gives the same answer --
    but it does matter for the companion correlation table, and the ``power_feature`` column says
    what the numbers were computed on, on every row of both.

    BANDS OVERLAP HEAVILY, and no correction for having looked at many of them is applied here. A
    5 Hz wide band centred on 15 Hz and one centred on 16 Hz share most of their frequencies, so
    the 23 default centres are nowhere near 23 independent looks at the data. A reader counting how
    many rows came out "established" must not treat that count as a count of independent findings.
    """
    if not td_detail:
        return pd.DataFrame(columns=_BAND_ROW_HEADER_COLUMNS + ["answer", "why"])
    feat_name = _pooled_power_feature_name(td_detail)
    rows = []
    for ch, fc, bp, labels, rg, times in _sweep_contacts_and_bands(
            td_detail, channels, centers, band_width_hz):
        row = _band_row_header(ch, fc, band_width_hz)
        if bp is None:
            row.update(_blank_band_answer(
                f"contact pair {ch}, or the band centred on {fc:g} Hz, is not present in the "
                "pooled spectra handed in", auc=None, no_relationship_value=0.5,
                power_feature=feat_name))
        else:
            row.update(band_pain_auc(bp, labels, rg, times=times, strategy=strategy,
                                     low_pct=low_pct, high_pct=high_pct, pain_cutoff=pain_cutoff,
                                     n_boot=n_boot, seed=seed, alpha=alpha,
                                     power_feature=feat_name))
        rows.append(row)
    return _order_export_columns(
        pd.DataFrame(rows),
        ["answer", "auc", "auc_low", "auc_high", "no_relationship_value", "p_two_sided",
         "n_pain_reports", "n_spectral_samples", "n_high_pain_samples", "n_low_pain_samples",
         "pain_split_rule", "pain_low_cut", "pain_high_cut", "why"])


def band_pain_correlation_export(td_detail, *, channels=None, centers=None, band_width_hz=5.0,
                                 n_boot=500, seed=0, alpha=0.05):
    """The companion table: one row per sensing contact pair per band centre, giving the Pearson
    correlation between that band's power and the patient's continuous pain score.

    The same contacts and the same band centres as ``band_pain_auc_export``, so the two tables can
    be read side by side row for row. Each row carries the correlation, its confidence interval, how
    many pain reports are behind it, and the same three-word answer. The value that means no
    relationship is 0 here rather than 0.5, and the ``no_relationship_value`` column says so on
    every row, so the two tables can never be read against the wrong comparison.

    A CORRELATION DOES DEPEND ON THE POWER SCALE, so the ``power_feature`` column has to be read
    before the number means anything. For the biomarker page's pooled spectra the power is a
    logarithm that has been standardised within each recording source, which is what the page's own
    plot draws. The extra ``pearson_r_after_undoing_the_logarithm`` column gives the same
    correlation computed after undoing that logarithm, so a reader can see whether the answer turns
    on the scale; that column is proportional to power rather than being in the stimulator's units,
    because the standardising step threw the scale away and it cannot be recovered from these
    spectra.

    Bands overlap heavily and no correction for having looked at many of them is applied; see
    ``band_pain_auc_export``.
    """
    if not td_detail:
        return pd.DataFrame(columns=_BAND_ROW_HEADER_COLUMNS + ["answer", "why"])
    feat_name = _pooled_power_feature_name(td_detail)
    rows = []
    for ch, fc, bp, labels, rg, times in _sweep_contacts_and_bands(
            td_detail, channels, centers, band_width_hz):
        row = _band_row_header(ch, fc, band_width_hz)
        if bp is None:
            row.update(_blank_band_answer(
                f"contact pair {ch}, or the band centred on {fc:g} Hz, is not present in the "
                "pooled spectra handed in", pearson_r=None, no_relationship_value=0.0,
                power_feature=feat_name))
            rows.append(row)
            continue
        row.update(band_pain_correlation(bp, labels, rg, times=times, n_boot=n_boot, seed=seed,
                                         alpha=alpha, power_feature=feat_name))
        # The same correlation after undoing the logarithm, so a reader can see whether the answer
        # turns on the scale the power is expressed in. Same resampling and same seed, so the only
        # thing that differs between the two numbers is the scale.
        undone = band_pain_correlation(10.0 ** (np.asarray(bp, dtype=float) / 10.0), labels, rg,
                                       times=times, n_boot=n_boot, seed=seed, alpha=alpha,
                                       power_feature=feat_name + ", with the logarithm undone")
        row["pearson_r_after_undoing_the_logarithm"] = undone.get("pearson_r")
        row["pearson_r_after_undoing_the_logarithm_low"] = undone.get("pearson_r_low")
        row["pearson_r_after_undoing_the_logarithm_high"] = undone.get("pearson_r_high")
        row["answer_after_undoing_the_logarithm"] = undone.get("answer")
        rows.append(row)
    return _order_export_columns(
        pd.DataFrame(rows),
        ["answer", "pearson_r", "pearson_r_low", "pearson_r_high", "no_relationship_value",
         "p_two_sided", "pearson_r_per_sample", "n_pain_reports", "n_spectral_samples",
         "pain_split_rule", "pearson_r_after_undoing_the_logarithm",
         "pearson_r_after_undoing_the_logarithm_low", "pearson_r_after_undoing_the_logarithm_high",
         "answer_after_undoing_the_logarithm", "why"])


def read_band_pain_auc_from_export(auc_table, *, channel, center_hz, tol_hz=0.01):
    """Look up one contact pair and one band centre in a table from ``band_pain_auc_export``.

    THE ONE PLACE THAT DOES THIS LOOKUP, so the closed-loop page and anything else reading the
    exported table agree on what counts as a match and on what happens when there is no row. A band
    centre is matched within ``tol_hz`` hertz rather than exactly, because a centre frequency that
    has been through a comma-separated file comes back as 15.000000000000002 often enough to matter.

    Returns the row as a dictionary, or a "not assessed" dictionary naming what was looked for and
    not found. A missing row is never returned as a value near 0.5, because a reader would take
    that for a measurement showing no separation when in fact nothing was measured.
    """
    if auc_table is None or len(auc_table) == 0:
        return _blank_band_answer(
            "the exported table of how well each band tells high pain from low pain is empty, so "
            "there is nothing to read for any band", auc=None, no_relationship_value=0.5)
    need = {"channel", "band_center_hz", "auc", "answer"}
    if not need.issubset(set(auc_table.columns)):
        return _blank_band_answer(
            "the table handed in is not a table of how well each band tells high pain from low "
            f"pain; it is missing the columns {sorted(need - set(auc_table.columns))}",
            auc=None, no_relationship_value=0.5)
    sel = auc_table[(auc_table["channel"].astype(str) == str(channel))
                    & (np.abs(pd.to_numeric(auc_table["band_center_hz"], errors="coerce")
                              - float(center_hz)) <= float(tol_hz))]
    if len(sel) == 0:
        return _blank_band_answer(
            f"the exported table has no row for contact pair {channel} at a band centred on "
            f"{float(center_hz):g} Hz, so how well that band tells high pain from low pain has not "
            "been worked out. This is an absent row, not a measurement showing no separation",
            auc=None, no_relationship_value=0.5)
    return {k: (None if (isinstance(v, float) and not np.isfinite(v)) else v)
            for k, v in sel.iloc[0].to_dict().items()}


def band_mixedmodel_inference(td_detail, channel_raw, center_hz, *, band_width_hz=5.0,
                              strategy="tertile", low_pct=33.3333, high_pct=66.6667,
                              pain_cutoff=None, cluster="era",
                              exclude_first_weeks=VALIDATION_EXCLUDE_FIRST_WEEKS):
    """Cluster-robust inference for ONE selected (channel, band) via a logistic MIXED-EFFECTS model
    (pymer4 -> R lme4 glmer): pain_high ~ band_power + (1 | session_cluster).

    Run ONLY on the band the user clicks (one glmer fit), not across the sweep. Returns the fixed
    effect of band power (coef, OR, z, p) with the within-cluster correlation modelled explicitly —
    the honest 'is this band real?' number for clustered repeated measures. Degrades to
    {available: False, reason: ...} when pymer4/R is unavailable, so the sweep still works without R.
    """
    try:
        from pymer4.models import Lmer
    except Exception as e:        # pymer4 or its R backend not installed
        return {"available": False, "reason": f"pymer4 unavailable: {e}"}
    if not td_detail:
        return {"available": False, "reason": "no detail"}
    f = np.asarray(td_detail.get("f_set"), dtype=float)
    psd = np.asarray(td_detail.get("psd"), dtype=float)
    labels = np.asarray(td_detail.get("labels"), dtype=float)
    chans = td_detail.get("chan_order", [])
    times = td_detail.get("times")
    # Resolve the channel index from the raw name (or the formatted short).
    ci = None
    for i, raw in enumerate(chans):
        if raw == channel_raw or format_channel(raw)["short"] == channel_raw:
            ci = i
            break
    if ci is None:
        return {"available": False, "reason": f"channel {channel_raw} not found"}
    w = float(band_width_hz)
    bmask = (f >= center_hz - w / 2.0) & (f < center_hz + w / 2.0)
    if not bmask.any():
        return {"available": False, "reason": "empty band"}
    with np.errstate(invalid="ignore", divide="ignore"):
        sub = np.nanmean(psd[:, ci, bmask], axis=1)
        bp_log = sub if td_detail.get("prelog", False) else 10.0 * np.log10(np.where(sub > 0, sub, np.nan))
    # PARITY (audit §6b): binarize on THIS CHANNEL's own labels, not the global pooled cut. The
    # offline validated set (phase2) cuts the tertile on labels restricted to the rows where this
    # channel's band power is finite; a global cut flips borderline samples high/low between the two
    # and changes n / OR / p. _binarize_labels with an explicit channel mask reproduces phase2.
    chan_finite = np.isfinite(bp_log)

    # THE DECLARED BURN-IN EXCLUSION (see VALIDATION_EXCLUDE_FIRST_WEEKS), applied HERE — before
    # binarization and before the z-score — and that ordering is a choice worth stating.
    #
    # The tertile cut and the standardisation are both computed over whatever mask reaches them. If
    # the exclusion were applied afterwards, the pain classes and the power scale would be defined
    # on a record that includes the weeks being excluded, and the retained window would inherit a
    # cut struck against data it is not being compared to. On this participant pain fell over the
    # year, so a full-record cut would label a disproportionate share of the retained samples "low"
    # and the two classes would no longer be tertiles of the analysed population. Excluding first
    # makes the model self-consistent: the cut, the scale and the fit all describe the same window.
    #
    # The window is anchored on the FIRST sample of the whole record, not on the first retained one,
    # so the exclusion cannot walk forward as data accumulates.
    _cl_all = _elapsed_week_cluster(times, len(bp_log))
    n_weeks_before = int(len(np.unique(_cl_all[chan_finite & (_cl_all >= 0)])))
    burn_in = int(exclude_first_weeks or 0)
    if burn_in > 0:
        keep_week = _cl_all >= burn_in
        n_dropped_burn_in = int(np.count_nonzero(chan_finite & ~keep_week & (_cl_all >= 0)))
        chan_finite = chan_finite & keep_week
    else:
        n_dropped_burn_in = 0
    if burn_in > 0 and not chan_finite.any():
        return {"available": False,
                "reason": (f"the declared {burn_in}-week burn-in exclusion removed every sample on "
                           f"this channel and band; nothing is left to fit, which is reported "
                           f"rather than silently falling back to the full record")}

    y = _binarize_labels(labels, strategy=strategy, low_pct=low_pct, high_pct=high_pct,
                         pain_cutoff=pain_cutoff, finite_mask=chan_finite)
    # PARITY (audit §6a): cluster = integer ELAPSED-week index from the first sample (phase2),
    # not the ISO-calendar-week string. Elapsed-week buckets that straddle a Monday split across two
    # ISO weeks (and vice versa), giving a different random-intercept structure -> different SE/p/CI.
    cl = _cl_all
    m = np.isfinite(bp_log) & np.isfinite(y) & chan_finite
    if m.sum() < 12 or len(np.unique(y[m])) < 2:
        return {"available": False,
                "reason": ("too few matched samples for a mixed model"
                           + (f" after the declared {burn_in}-week burn-in exclusion removed "
                              f"{n_dropped_burn_in} of them" if burn_in > 0 else "")),
                "excluded_first_weeks": burn_in,
                "n_excluded_burn_in": n_dropped_burn_in}
    # PARITY (audit §6 minor): z-score with ddof=1 (phase2), matching the offline sample SD.
    _bpm = bp_log[m]
    _sd = np.nanstd(_bpm, ddof=1)
    df = pd.DataFrame({"pain_high": y[m].astype(int),
                       "band_power": (_bpm - np.nanmean(_bpm)) / (_sd if _sd and np.isfinite(_sd) else 1.0),
                       "cluster": cl[m]})
    n_clusters = int(df["cluster"].nunique())
    formula = "pain_high ~ band_power + (1|cluster)" if n_clusters > 1 else "pain_high ~ band_power"
    try:
        # The fit + the pandas<->R conversion it triggers must run with rpy2's converter active in
        # THIS thread (see _rpy2_converter_ctx). pymer4 populates .coefs/.ranef_var as plain pandas
        # during fit, so only the construction + fit need the context.
        with _rpy2_converter_ctx():
            mod = Lmer(formula, data=df, family="binomial")
            mod.fit(summarize=False)
        coefs = mod.coefs
        row = coefs.loc["band_power"]
        est = float(row.get("Estimate"))
        # pymer4 exposes OR / P-val / Z-stat directly for a binomial fit; fall back to exp(coef)
        # and the alternate p-value column name across pymer4 versions.
        p = float(row["P-val"]) if "P-val" in row else (float(row["Pr(>|z|)"]) if "Pr(>|z|)" in row else np.nan)
        z = float(row["Z-stat"]) if "Z-stat" in row else np.nan
        odds = float(row["OR"]) if "OR" in row else float(np.exp(est))
        # OR confidence interval — pymer4 reports the Wald CI on the linear predictor scale as
        # '2.5_ci' / '97.5_ci'; exponentiate to OR space. Falls back to None if columns missing
        # (older pymer4) so the caller never crashes when the bounds aren't available.
        def _ci_or(col):
            try:
                v = float(row[col]); return float(np.exp(v)) if np.isfinite(v) else None
            except (KeyError, TypeError, ValueError):
                return None
        or_lo = _ci_or("2.5_ci"); or_hi = _ci_or("97.5_ci")
        # Complete/quasi-complete separation: the predictor (z-scored) drives an implausibly large
        # coefficient and the SE/p-value explode (Hessian singular). Report it as unreliable rather
        # than a spurious OR ~ 1e90. PARITY (audit §6 minor): phase2 flags |beta| > 50 — use the
        # same threshold so a band the validated set kept isn't dropped here as "separated".
        if not np.isfinite(est) or abs(est) > 50.0:
            return {
                "available": True, "model": "glmer logistic (lme4 via pymer4)",
                "formula": formula, "n": int(m.sum()), "n_clusters": n_clusters,
                # The exclusion travels WITH the estimate. A reader comparing this odds
                # ratio against an earlier one, or against the sweep, must be able to see
                # that they were fitted on different windows; a footnote elsewhere on the
                # page is not enough, because the number gets quoted on its own.
                "excluded_first_weeks": burn_in,
                "n_excluded_burn_in": n_dropped_burn_in,
                "n_weeks_before_exclusion": n_weeks_before,
                "coef": _f(est), "odds_ratio": None,
                "or_lo": None, "or_hi": None,
                "z": None, "p": None,
                "separation": True, "singular": False,
                "note": ("Complete/quasi-complete separation — band power separates high/low "
                         "pain perfectly at this window, so the logistic estimate is degenerate. "
                         "Widen the match window or loosen the binarization to get a stable fit."),
            }
        # Singular random-effect variance: lme4 returns a fit but the era-level variance has
        # collapsed to ~0, meaning the random intercept added nothing (effectively pooled OLS).
        # We still report the fit but flag it so the UI can downgrade confidence.
        singular = False
        try:
            # ranef_var can lazily pull from the fitted R object, so read it under the converter
            # context too (the try/except already keeps a conversion hiccup from crashing the fit).
            with _rpy2_converter_ctx():
                ranef = mod.ranef_var
            if "Var" in ranef.columns and len(ranef):
                singular = bool(float(ranef["Var"].iloc[0]) < 1e-6)
        except Exception:
            pass
        return {
            "available": True, "model": "glmer logistic (lme4 via pymer4)",
            "formula": formula, "n": int(m.sum()), "n_clusters": n_clusters,
                # The exclusion travels WITH the estimate. A reader comparing this odds
                # ratio against an earlier one, or against the sweep, must be able to see
                # that they were fitted on different windows; a footnote elsewhere on the
                # page is not enough, because the number gets quoted on its own.
                "excluded_first_weeks": burn_in,
                "n_excluded_burn_in": n_dropped_burn_in,
                "n_weeks_before_exclusion": n_weeks_before,
            "coef": _f(est), "odds_ratio": _f(odds),
            "or_lo": _f(or_lo) if or_lo is not None else None,
            "or_hi": _f(or_hi) if or_hi is not None else None,
            "z": _f(z), "p": _f(p), "separation": False, "singular": singular,
            "note": "Random intercept per weekly era; band power z-scored. Exploratory inference.",
        }
    except Exception as e:
        return {"available": False, "reason": f"glmer fit failed: {e}"}


#: Declared equivalence margin for the stim-stability verdict, on the log-odds-ratio scale.
#: log(2) means "the band's slope may differ between stimulation states by up to a factor of two in
#: odds before we call the biomarker stim-dependent". This is a DECLARED judgement, not an estimate;
#: it is stated here so it can be argued with rather than buried in a p-value.
STABILITY_EQUIVALENCE_MARGIN_LOG_OR = float(np.log(2.0))

#: Percept time-domain sampling rate, used to place stimulation harmonics in the scanned spectrum.
DEVICE_TD_FS_HZ = 250.0


def _locf_values(times, series):
    """Carry a {t:[epoch_s], y:[value]} trajectory forward onto per-sample `times`.

    Same last-observation-carried-forward semantics as _assign_stim_eras, and deliberately a
    separate function rather than a generalisation of it: that one is load-bearing for the era
    boundaries shared with deployment_roc_by_era, and widening its contract to carry arbitrary
    values would put those boundaries at risk for no benefit. Returns a float array aligned to
    `times`, NaN where the timestamp is unparseable or the series is unusable.
    """
    n = 0 if times is None else len(times)
    out = np.full(n, np.nan, dtype=float)
    if not series or not series.get("t") or not series.get("y") or n == 0:
        return out
    t_dt = pd.to_datetime(pd.Series([str(t) for t in times]), errors="coerce", format="ISO8601")
    nat = t_dt.isna().to_numpy()
    t_epoch = (t_dt.to_numpy().astype("datetime64[ns]").astype("int64") / 1e9)
    st = np.asarray(series["t"], dtype=float)
    sy = np.asarray(series["y"], dtype=float)
    if len(st) < 1:
        return out
    order = np.argsort(st)
    st, sy = st[order], sy[order]
    idx = np.clip(np.searchsorted(st, t_epoch, side="right") - 1, 0, len(st) - 1)
    out = sy[idx].astype(float)
    out[nat] = np.nan
    return out


def harmonic_landings_hz(rate_hz, f_lo, f_hi, *, fs=DEVICE_TD_FS_HZ, max_harmonic=8):
    """Frequencies inside [f_lo, f_hi] where harmonics of `rate_hz` appear after sampling at `fs`.

    ARITHMETIC, AND ONLY ARITHMETIC. Percept time-domain sensing runs at 250 Hz, so a whole multiple
    of the stimulation rate that lies above half the sampling rate reappears at a lower frequency
    after the sampling folds it down. This function reports the frequencies inside [f_lo, f_hi] where
    that happens. Saying a band CARRIES A FOLDED MULTIPLE OF THE STIMULATION RATE is a statement
    about where numbers land and needs no assumption about what is being measured.

    WHAT MUST NOT BE SAID, corrected 2026-09-06 after the PI rejected the stronger claim on the
    evidence below. A band that carries a folded multiple of the stimulation rate is NOT thereby
    measuring the stimulator rather than the brain, and this function's output must not be described
    as marking contamination. Earlier revisions of this docstring said both, and both were wrong:

      * A stimulation artefact grows with the current and keeps growing. On the RCS08 record
        (2026-08-18 visit) the bands that carry 55 Hz itself do exactly that, rising monotonically
        to 18.2 times their starting value. The bands whose folded landing sits between 22 and
        30 Hz instead rise and then FALL, peaking near 1.8 mA, and the PI has independently observed
        a two-peaked shape in the same recordings. A quantity that comes back down as the current
        keeps rising is not that artefact, so the landing alone does not establish what the band is
        measuring.
      * The affected bands do NOT split cleanly along the landing frequencies. The curvature
        p-values run smoothly across frequency; the apparent clean split was a 0.05 cutoff drawn
        across a continuous gradient, not a boundary in the data.

    SO THE FLAG IS ADVISORY FOR BOTH QUESTIONS IT IS USED ON, and what it advises is care with the
    amplitude response of the flagged band, not disbelief in it:

      * Pain biomarker. Tested on the RCS08 record (2026-09-03): responding bands were NOT closer to
        these landings than non-responding ones (at 110 Hz, 4.52 Hz mean distance for responding
        against 3.90 Hz for non-responding, i.e. slightly farther), so the folding did not explain
        the pain associations and bands are flagged for review rather than excluded.
      * Amplitude response. Measured 2026-09-05 by aligning 13,102 three-second tiles to the moment
        a clinician logged an amplitude change: during a change the power rise is concentrated at
        the landings (peak 0.81 log10 per 100 s at 57.5 Hz under 55 Hz stimulation, against a median
        of -0.003 in bands away from the landings). That is a measured concentration and it is the
        reason to treat a slope estimated at a landing with care; it is not evidence about what the
        band is measuring, and the shape of the response with current (above) argues against reading
        it as the stimulator. ClosedLoopDeployment.clinic_steps.amplitude_response_band_mask calls
        this function rather than reimplementing it, and owns what it does with the flag.

    Build the landing set PER RATE. Pooling rates defeats the test: RCS08's ten rates place landings
    roughly every 5 Hz across the 2.5-99.5 Hz axis, and with a 2.5 Hz tolerance that covers the whole
    axis: only 8 of 98 bands survive the union of RCS08's nine rates, against 65 for 55 Hz
    alone. Per rate the landings are sparse and specific.
    """
    if rate_hz is None or not np.isfinite(rate_hz) or rate_hz <= 0:
        return []
    out = []
    for k in range(1, int(max_harmonic) + 1):
        raw = float(rate_hz) * k
        a = abs(raw - round(raw / fs) * fs)          # fold about Nyquist
        if f_lo <= a <= f_hi:
            out.append({"harmonic": k, "raw_hz": round(raw, 3), "lands_at_hz": round(a, 3)})
    return out


def _era_slope_table(df, era_col="stim_era", x="band_power", y="pain_high", min_n=6):
    """Per-era logistic slope on `x` with its standard error, for the equivalence test."""
    import statsmodels.api as sm
    out = {}
    for tag in list(df[era_col].cat.categories) if hasattr(df[era_col], "cat") else sorted(df[era_col].unique()):
        sub = df[df[era_col] == tag]
        if len(sub) < min_n or sub[y].nunique() < 2:
            out[str(tag)] = None
            continue
        try:
            X = sm.add_constant(sub[x].to_numpy())
            r = sm.GLM(sub[y].to_numpy(), X, family=sm.families.Binomial()).fit()
            b, se = float(r.params[1]), float(r.bse[1])
            out[str(tag)] = ({"slope_log_or": b, "se": se, "n": int(len(sub))}
                             if np.isfinite(b) and np.isfinite(se) else None)
        except Exception:
            out[str(tag)] = None
    return out


def stability_equivalence(slope_table, lrt_p, *, margin=STABILITY_EQUIVALENCE_MARGIN_LOG_OR,
                          conf=0.90):
    """Turn "the interaction was not significant" into a verdict that distinguishes SHOWN-STABLE
    from MERELY-UNDERPOWERED.

    Why this exists. The original verdict was `stim_stable = (p_lrt >= 0.05)`, which is a failure to
    reject. With three eras and modest counts that reads "stable" precisely when the test has no
    power — the situation in which a false reassurance is most costly, because the biomarker is
    about to anchor a threshold on a device that actuates. Equivalence testing inverts the burden:
    the biomarker is called stable only when the largest between-era difference in its slope is
    demonstrably SMALLER than a declared margin.

    Two one-sided tests, implemented as the conventional (1-2*alpha) interval on the largest
    pairwise era difference. A 90% interval corresponds to alpha = 0.05 on each side.

    Verdicts:
      "stim-dependent"  the interaction LRT rejects; the slope demonstrably differs by era.
      "stable"          LRT does not reject AND the interval on the largest difference lies wholly
                        inside +/- margin, so equivalence is demonstrated.
      "inconclusive"    LRT does not reject but the interval is wider than the margin: the data
                        cannot distinguish a stable biomarker from a materially unstable one.
    """
    from scipy.stats import norm
    usable = {k: v for k, v in (slope_table or {}).items() if v}
    if len(usable) < 2:
        return {"verdict": "inconclusive", "reason": "fewer than two eras with an estimable slope",
                "max_abs_diff_log_or": None, "ci": None, "margin_log_or": float(margin),
                "n_eras_compared": len(usable)}
    z = float(norm.ppf(0.5 + conf / 2.0))
    worst = None
    keys = sorted(usable)
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a, b = usable[keys[i]], usable[keys[j]]
            diff = a["slope_log_or"] - b["slope_log_or"]
            se = float(np.sqrt(a["se"] ** 2 + b["se"] ** 2))
            if worst is None or abs(diff) > abs(worst["diff"]):
                worst = {"pair": f"{keys[i]} vs {keys[j]}", "diff": diff, "se": se}
    lo, hi = worst["diff"] - z * worst["se"], worst["diff"] + z * worst["se"]
    inside = bool(np.isfinite(lo) and np.isfinite(hi) and lo > -margin and hi < margin)
    rejected = bool(np.isfinite(lrt_p) and lrt_p < 0.05)
    verdict = "stim-dependent" if rejected else ("stable" if inside else "inconclusive")
    return {"verdict": verdict, "pair": worst["pair"],
            "max_abs_diff_log_or": float(abs(worst["diff"])),
            "ci": [float(lo), float(hi)], "ci_level": conf,
            "margin_log_or": float(margin), "equivalence_shown": inside,
            "n_eras_compared": len(usable),
            "reason": ("interaction LRT rejects" if rejected else
                       ("largest between-era slope difference lies inside the declared margin"
                        if inside else
                        "not rejected, but the interval is wider than the margin: underpowered "
                        "rather than shown stable"))}


#: Fit the reduced/full binomial GLMM pair and return ONLY their log-likelihoods, which is all the
#: band x stim-era LRT below actually consumes (`chisq = 2*(ll1 - ll0)`).
#:
#: WHY THIS BYPASSES pymer4. Measured on the live container, on the exact frame this function builds
#: (421 rows, 37 clusters, 2026-09-09): one `Lmer(...).fit()` took 0.359 s, of which R's own
#: `system.time` attributed 0.216 s to `glmer` itself. The other 0.143 s -- 40% -- was pymer4
#: assembling coefficient tables, random-effect frames and design information into pandas, which it
#: does even with `summarize=False`, and every byte of which this call path discards. Moving the
#: frame into R is NOT the cost: that measured 0.002 s.
#:
#: THIS IS NOT A DIFFERENT ESTIMATOR. It is the same `lme4::glmer` call, on the same data frame,
#: with the same formula and family. pymer4 itself is a wrapper around exactly this.
#:
#: The pymer4 path is kept as the REFERENCE IMPLEMENTATION behind `USE_DIRECT_GLMER`, the same
#: contract `USE_CHANNEL_INDEX` already established for `per_pro_lsb` (decision 43): the switch is
#: what makes an equality proof possible on live data, and gives an off switch that needs no
#: deployment if the direct path is ever suspected.
USE_DIRECT_GLMER = True


def _binomial_glmer_loglik_pair(df, formula_red, formula_full):
    """Returns (ll_reduced, ll_full) as plain floats. Raises on failure, like the code it replaces --
    `band_stim_stability`'s own `except` turns that into {"available": False, "reason": "LRT failed"}.
    """
    if not USE_DIRECT_GLMER:
        from pymer4.models import Lmer
        with _rpy2_converter_ctx():
            m0 = Lmer(formula_red, data=df, family="binomial"); m0.fit(summarize=False)
            m1 = Lmer(formula_full, data=df, family="binomial"); m1.fit(summarize=False)
        return float(m0.logLike), float(m1.logLike)

    import rpy2.robjects as ro
    from rpy2.robjects import pandas2ri
    from rpy2.robjects.conversion import localconverter

    # The conversion must run with rpy2's converter active in THIS thread, the same reason the
    # pymer4 path is wrapped -- otherwise a worker thread raises the "conversion rules ... missing"
    # ContextVar error.
    with _rpy2_converter_ctx():
        with localconverter(ro.default_converter + pandas2ri.converter):
            r_df = ro.conversion.py2rpy(df)
        ro.r('suppressMessages(library(lme4))')
        # A distinctive name rather than `d`: this lands in R's global environment, which is shared
        # by everything else in this process that talks to R.
        ro.globalenv['.bravo_glmer_df'] = r_df
        def _ll(formula):
            return float(ro.r(
                f'as.numeric(logLik(glmer({formula}, data = .bravo_glmer_df, '
                f'family = binomial)))')[0])
        ll0 = _ll(formula_red)
        ll1 = _ll(formula_full)
    return ll0, ll1


def band_stim_stability(td_detail, channel_raw, center_hz, stim_series=None, *,
                        band_width_hz=5.0, strategy="tertile", low_pct=33.3333, high_pct=66.6667,
                        off_max=0.1, low_max=1.5,
                        rate_series=None,
                        equivalence_margin_log_or=STABILITY_EQUIVALENCE_MARGIN_LOG_OR):
    """Test whether one (channel, band)'s pain-prediction holds across stim states (band x stim-era
    LRT). Compares pain_high ~ band_power + stim_era + (1|era)  (m0, reduced) against
    pain_high ~ band_power * stim_era + (1|era)  (m1, full). The LRT p answers
    "does the band's effect depend on stim?" — small p means the biomarker is stim-state-dependent
    (i.e. a poor closed-loop threshold anchor); large p means the biomarker is stim-stable.

    Per-era ORs are computed via separate per-era GLM fits (slope on band_power) so the UI can show
    OFF / LOW / HIGH OR side-by-side.

    `stim_series` is the chronic stim trajectory {t:[epoch_s], y:[mA]} from bravo_service. We
    nearest-time-interpolate sample-level stim_mA from the td_detail times and bin into eras:
      OFF   stim_mA < off_max  (default <0.1 mA)
      LOW   off_max <= stim_mA <= low_max
      HIGH  stim_mA > low_max
    Returns {available: False, reason: ...} on failure (no R, no stim, fit fails, only 1 era).

    `rate_series` (optional, added 2026-09-03) is the stimulation RATE trajectory
    {t:[epoch_s], y:[Hz]}, carried forward onto sample times the same way. Until it was added the
    scan was amplitude-aware and rate-BLIND: the string `rate_hz` appeared nowhere in this module,
    so nothing here could know where the stimulation artifact and its aliases fell in the spectrum,
    nor whether an apparent amplitude effect was really a rate change. Supplying it adds three
    things to the output and changes none of the existing keys:

      * `rate_composition` — how many samples sat at each rate, and how rate is distributed across
        the amplitude eras. When rate and amplitude era are strongly associated, the era test is
        partly a rate test, and the output says so via `rate_confounded_with_era`.
      * `harmonic_landings` — where this rate's harmonics fold into the scanned band (see
        harmonic_landings_hz). Advisory, not exclusionary.
      * `band_near_harmonic_hz` — the distance from this band's centre to the nearest landing.

    `equivalence_margin_log_or` declares how large a between-era difference in the band's slope
    would have to be to count as instability; see stability_equivalence for why a p-value alone is
    not enough.
    """
    try:
        from pymer4.models import Lmer
        import rpy2.robjects as ro
    except Exception as e:
        return {"available": False, "reason": f"pymer4/rpy2 unavailable: {e}"}
    if not td_detail or not stim_series or not stim_series.get("t") or not stim_series.get("y"):
        return {"available": False, "reason": "no stim series"}
    f = np.asarray(td_detail.get("f_set"), dtype=float)
    psd = np.asarray(td_detail.get("psd"), dtype=float)
    labels = np.asarray(td_detail.get("labels"), dtype=float)
    chans = td_detail.get("chan_order", [])
    times = td_detail.get("times")
    if times is None or len(times) != len(labels):
        return {"available": False, "reason": "missing sample times"}
    # Resolve channel
    ci = None
    for i, raw in enumerate(chans):
        if raw == channel_raw or format_channel(raw)["short"] == channel_raw:
            ci = i; break
    if ci is None:
        return {"available": False, "reason": f"channel {channel_raw} not found"}
    w = float(band_width_hz)
    bmask = (f >= center_hz - w / 2.0) & (f < center_hz + w / 2.0)
    if not bmask.any():
        return {"available": False, "reason": "empty band"}
    with np.errstate(invalid="ignore", divide="ignore"):
        sub = np.nanmean(psd[:, ci, bmask], axis=1)
        bp_log = sub if td_detail.get("prelog", False) else 10.0 * np.log10(np.where(sub > 0, sub, np.nan))
    # PARITY (audit §6b): per-channel binarization (cut on this channel's own labels), matching the
    # offline phase2b stim-stability LRT. Shares the same basis as band_mixedmodel_inference.
    chan_finite = np.isfinite(bp_log)
    y = _binarize_labels(labels, strategy=strategy, low_pct=low_pct, high_pct=high_pct,
                         finite_mask=chan_finite)
    # Sample-time -> era via the SHARED nearest-time interpolation + bucketing (identical boundaries
    # to deployment_roc_by_era so the stability LRT and the per-era refit agree).
    era = _assign_stim_eras(times, stim_series, off_max=off_max, low_max=low_max)
    if era is None:
        return {"available": False, "reason": "stim series too short"}
    era_none = np.array([e is None for e in era])
    # PARITY (audit §6a): random-intercept cluster = integer ELAPSED-week index (phase2b), not the
    # ISO-calendar-week string. -1 marks unparseable-time rows (dropped by the mask below).
    cl = _elapsed_week_cluster(times, len(bp_log))
    t_finite = cl >= 0
    # Drop unparseable-time / no-era rows from the LRT (do NOT relabel them OFF).
    m = np.isfinite(bp_log) & np.isfinite(y) & t_finite & (~era_none)
    if m.sum() < 20 or len(np.unique(y[m])) < 2 or len(np.unique(era[m])) < 2:
        return {"available": False, "reason": "too few samples / eras for an interaction test"}
    # PARITY (audit §6 minor): ddof=1 z-score (phase2b).
    _bpm = bp_log[m]; _sd = np.nanstd(_bpm, ddof=1)
    df = pd.DataFrame({
        "pain_high": y[m].astype(int),
        "band_power": (_bpm - np.nanmean(_bpm)) / (_sd if _sd and np.isfinite(_sd) else 1.0),
        "stim_era": pd.Categorical(era[m], categories=["OFF", "LOW", "HIGH"]),
        "cluster": cl[m],
    })
    n_clusters = int(df["cluster"].nunique())
    re_term = "+ (1|cluster)" if n_clusters > 1 else ""
    formula_red = f"pain_high ~ band_power + stim_era {re_term}"
    formula_full = f"pain_high ~ band_power * stim_era {re_term}"
    n_eras_present = int(df["stim_era"].cat.remove_unused_categories().nunique())
    try:
        # Both fits + their pandas<->R conversions must run with rpy2's converter active in THIS
        # thread (see _rpy2_converter_ctx) — otherwise the worker thread raises the "conversion rules
        # ... missing" ContextVar error. logLike is a cached float after fit, read outside the ctx.
        ll0, ll1 = _binomial_glmer_loglik_pair(df, formula_red, formula_full)
        # PARITY (audit §6): compute the LRT exactly as offline phase2b — chi2 = 2*(ll_full -
        # ll_reduced), p from chi2 with df = number of interaction terms added = (n_eras - 1). The
        # previous live path used R's anova(m0, m1), whose df accounting for the lme4 nested fit
        # differed (df=1 vs the 2 interaction terms a 3-era model adds), shifting borderline p's
        # across 0.05 (e.g. vas@61.5 ZERO_TWO_LEFT: anova p=0.048 -> dependent, but the validated
        # report's 2-df LRT p=0.127 -> stable).
        chisq = 2.0 * (ll1 - ll0)
        from scipy.stats import chi2 as _chi2dist
        dof = max(n_eras_present - 1, 1)
        p_lrt = float(1.0 - _chi2dist.cdf(chisq, df=dof))
    except Exception as e:
        return {"available": False, "reason": f"LRT failed: {e}"}
    # Per-era ORs via simple per-era GLM (no random intercept — each era is one block already).
    try:
        import statsmodels.api as sm
        or_by_era = {}
        for tag in ["OFF", "LOW", "HIGH"]:
            sub = df[df["stim_era"] == tag]
            if len(sub) < 6 or sub["pain_high"].nunique() < 2:
                or_by_era[tag] = None; continue
            X = sm.add_constant(sub["band_power"].to_numpy())
            try:
                res = sm.GLM(sub["pain_high"].to_numpy(), X, family=sm.families.Binomial()).fit()
                or_by_era[tag] = float(np.exp(res.params[1])) if np.isfinite(res.params[1]) else None
            except Exception:
                or_by_era[tag] = None
    except Exception:
        or_by_era = {"OFF": None, "LOW": None, "HIGH": None}
    # --- rate as a covariate, and the equivalence verdict (2026-09-03) -----------------------
    rate_vals = _locf_values(times, rate_series)[m] if rate_series else np.full(int(m.sum()), np.nan)
    rate_info = {"available": False, "reason": "no rate series supplied"}
    if np.isfinite(rate_vals).any():
        rr = pd.Series(rate_vals).round(1)
        comp = rr.value_counts(dropna=True).sort_index()
        xt = pd.crosstab(df["stim_era"].to_numpy(), rr.to_numpy())
        # Cramer's V between era and rate. If they move together the era LRT is partly a rate test,
        # which is exactly the confound the closed-loop screen blocks on and which this module had
        # no way to see before.
        try:
            from scipy.stats import chi2_contingency
            chi2v, _, _, _ = chi2_contingency(xt.to_numpy()) if min(xt.shape) > 1 else (0.0, 1, 0, None)
            nn = float(xt.to_numpy().sum()); k = min(xt.shape)
            cramers_v = float(np.sqrt(chi2v / (nn * (k - 1)))) if nn > 0 and k > 1 else float("nan")
        except Exception:
            cramers_v = float("nan")
        landings = harmonic_landings_hz(float(rr.mode().iloc[0]) if len(rr.mode()) else np.nan,
                                        float(f.min()), float(f.max()))
        near = min([abs(float(center_hz) - x["lands_at_hz"]) for x in landings], default=None)
        rate_info = {
            "available": True,
            "n_rates": int(comp.size),
            "rate_composition": {str(kk): int(vv) for kk, vv in comp.items()},
            "modal_rate_hz": (float(rr.mode().iloc[0]) if len(rr.mode()) else None),
            "cramers_v_rate_vs_era": (_f(cramers_v) if np.isfinite(cramers_v) else None),
            # 0.3 is the conventional "moderate association" mark for Cramer's V; above it, treat the
            # era result as carrying a rate component rather than a pure amplitude one.
            "rate_confounded_with_era": (bool(np.isfinite(cramers_v) and cramers_v >= 0.30)
                                         if np.isfinite(cramers_v) else None),
            "harmonic_landings": landings,
            "band_near_harmonic_hz": (_f(near) if near is not None else None),
        }
    slope_tbl = _era_slope_table(df)
    equiv = stability_equivalence(slope_tbl, p_lrt, margin=equivalence_margin_log_or)
    return {
        "available": True, "model": "band x stim_era LRT (glmer logistic, lme4 via pymer4)",
        "formula_reduced": formula_red, "formula_full": formula_full,
        "n": int(m.sum()), "n_clusters": n_clusters,
        "chisq": _f(chisq), "lrt_p": _f(p_lrt),
        "slope_by_era": slope_tbl,
        "equivalence": equiv,
        # Three-way verdict replacing the binary one. `stim_stable` below is retained unchanged for
        # back-compatibility, but it cannot distinguish "shown stable" from "underpowered"; prefer
        # this. See stability_equivalence.
        "stability_verdict": equiv.get("verdict"),
        "rate": rate_info,
        # The headline interpretation flag: stim-stable iff the interaction LRT is NOT significant.
        # We carry the raw p here; the calling endpoint can FDR if it's running across many bands.
        "stim_stable": (np.isfinite(p_lrt) and p_lrt >= 0.05),
        "or_by_era": {k: (_f(v) if v is not None else None) for k, v in or_by_era.items()},
        "era_counts": {tag: int((df["stim_era"] == tag).sum()) for tag in ["OFF", "LOW", "HIGH"]},
        "thresholds_mA": {"off_max": off_max, "low_max": low_max},
    }


# --- Time-domain (streaming) analytics -------------------------------------------------------
def psd_spectra(td_detail, db=True, region_map=None):
    """Mean PSD per channel split by pain group (high vs low, by median label).
    Returns {freqs, unit, channels:[{name, short, region, high:[...], low:[...]}]}.
    `td_detail` is the streaming_psd result (psd (E,C,F), labels (E,), f_set, chan_order).
    `region_map` (raw-channel -> region) sources the region from device metadata.
    """
    if not td_detail:
        return None
    psd = np.asarray(td_detail.get("psd"), dtype=float)
    if psd.ndim != 3 or psd.shape[0] == 0:
        return None
    labels = np.asarray(td_detail.get("labels"), dtype=float)
    f = np.asarray(td_detail["f_set"], dtype=float)
    chans = td_detail.get("chan_order", [])

    valid = np.isfinite(labels)
    if valid.sum() >= 2 and np.unique(labels[valid]).size >= 2:
        thr = np.nanmedian(labels[valid])
        hi = labels >= thr
        lo = labels < thr
    else:  # not enough label variety -> everything is one group
        hi = np.ones(len(labels), bool)
        lo = np.zeros(len(labels), bool)

    def grp(mask, ci):
        if mask.sum() == 0:
            return [None] * len(f)
        m = np.nanmean(psd[mask, ci, :], axis=0)
        with np.errstate(divide="ignore", invalid="ignore"):
            m = 10 * np.log10(m) if db else m
        return [_f(x) for x in m]

    channels = []
    for ci in range(psd.shape[1]):
        raw = chans[ci] if ci < len(chans) else f"ch{ci}"
        fmt = format_channel(raw, region=(region_map or {}).get(raw, ""))
        channels.append({"name": fmt["label"], "short": fmt["short"], "region": fmt["region"],
                         "high": grp(hi, ci), "low": grp(lo, ci)})
    return {"freqs": [float(x) for x in f], "unit": "dB" if db else "power", "channels": channels}


def psd_spectrogram(td_detail, times, db=True, fmax=100.0, region_map=None):
    """Per-channel PSD heatmap over sessions (z = freq x session). times: list[str] per epoch.
    `region_map` (raw-channel -> region) sources the region from device metadata."""
    if not td_detail:
        return None
    psd = np.asarray(td_detail.get("psd"), dtype=float)
    if psd.ndim != 3 or psd.shape[0] == 0:
        return None
    f = np.asarray(td_detail["f_set"], dtype=float)
    chans = td_detail.get("chan_order", [])
    fmask = f <= fmax
    fz = f[fmask]

    channels = []
    for ci in range(psd.shape[1]):
        z = psd[:, ci, :][:, fmask]  # (E, Fz)
        with np.errstate(divide="ignore", invalid="ignore"):
            z = 10 * np.log10(z) if db else z
        zt = z.T  # (Fz, E) -> rows=freq, cols=session
        raw = chans[ci] if ci < len(chans) else f"ch{ci}"
        fmt = format_channel(raw, region=(region_map or {}).get(raw, ""))
        channels.append({"name": fmt["label"], "short": fmt["short"], "region": fmt["region"],
                         "z": [[_f(v) for v in row] for row in zt]})
    return {"freqs": [float(x) for x in fz], "times": list(times),
            "unit": "dB" if db else "power", "channels": channels}


# =================================================================================================
# HOW WELL EACH BAND TRACKS PAIN, AT EVERY LENGTH OF SIGNAL AVERAGED INTO ONE MEASUREMENT
# =================================================================================================
#
# WHAT THIS SECTION IS FOR. The panel at the bottom of the biomarker exploration page asks one
# question over a grid: if the band power fed to a decision were the average over the last N
# seconds of recording, how well would that number track the patient's own pain score? The grid
# runs over band centre on one axis and over the length of signal averaged into one measurement on
# the other. It is meant for looking at the SHAPE of that surface, which is why the whole grid is
# returned and not only the best cell in each row.
#
# TWO NUMBERS PER CELL, AND THEY MEAN DIFFERENT THINGS.
#   * The Pearson correlation between the band power and the continuous pain score. The value that
#     means no relationship is 0, and the value runs from -1 to +1.
#   * The area under the curve of a one-predictor logistic regression that predicts whether a pain
#     report was a high-pain one or a low-pain one from that band's power. THE VALUE THAT MEANS NO
#     DISCRIMINATION IS 0.5, NOT 0. Every interval, colour scale and verdict in this section is
#     referenced to 0.5, and an interval that spans 0.5 means the question was not settled -- it is
#     never a negative result.
#
# THE LENGTH OF SIGNAL IS NOT FREELY CHOOSABLE. The module's band power comes from a cache that
# slices the whole recording history into fixed non-overlapping tiles of RAW_LSB_WINDOW_SECONDS
# (3 s). A request for N seconds is served by the nearest max(1, round(N / 3)) tiles, so the
# shortest measurement that exists at all is one 3 s tile: a request for 1 s is delivered as 3 s.
# `integration_time_tile_count` computes the tile count and the seconds ACTUALLY delivered, and
# every row of every table below carries both the requested and the delivered figure. Reading the
# requested figure as though it had been delivered would misstate the shortest measurement by
# threefold.
#
# WHY THE BEST CELL IN A ROW IS AN OPTIMISTIC NUMBER. Taking the largest of ten values, one per
# length of signal, is a choice made after seeing the answers. The ten are strongly related to one
# another (a 45 s average and a 60 s average share most of their tiles), so they are nowhere near
# ten independent looks, but they are not one look either: the largest of them is larger than the
# value that same length of signal would give on a fresh set of pain reports, and its ordinary
# p-value is not the probability of what was actually done. This module therefore reports, beside
# every best cell, the largest value the SAME best-of-ten selection produced when the pain scores
# were shuffled -- so a reader compares the observed best against the distribution of bests under
# no relationship rather than against the distribution of a single value.

#: The lengths of signal, in seconds, that one band-power measurement may be averaged over. The
#: PI's list. Requests shorter than one tile are delivered as one tile; see the module note above.
BAND_TIME_SWEEP_SECONDS = (1.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 45.0, 60.0, 300.0)

#: The span of band centres the sweep covers, in hertz. The firmware can only place an adaptive
#: sensing band between 8 and 30 Hz (design ledger section 1), so a centre outside this span could
#: not be acted on from this page even if it tracked pain perfectly.
BAND_TIME_SWEEP_CENTER_LO_HZ = 8.0
BAND_TIME_SWEEP_CENTER_HI_HZ = 30.0

#: The width of every band in the sweep, in hertz. The device's own band is about this wide.
BAND_TIME_SWEEP_WIDTH_HZ = 5.0

#: The value of the area under the curve that means the band power tells high-pain moments from
#: low-pain ones no better than coin flipping. NOT zero. Named so that no colour scale, interval or
#: verdict in this module can be written against the wrong comparison by accident.
AUC_NO_DISCRIMINATION = 0.5

#: The value of a correlation that means no relationship.
CORRELATION_NO_RELATIONSHIP = 0.0

#: How many shuffles of the pain scores the selection-aware reference is built from, and how many
#: resamples of the pain reports the interval on the best cell is built from. Both are matrix
#: operations over the whole grid at once, so these counts cost tens of milliseconds, not seconds.
BAND_TIME_SWEEP_N_PERM = 1000
BAND_TIME_SWEEP_N_BOOT = 1000

#: Decision 63: the target false-discovery rate for correcting across the grid's own 22 band
#: centres (never pooled with the older full-spectrum routine's much wider range, which is why the
#: field name below says "8_to_30hz" rather than reusing the older routine's own field). Matches
#: BIOMARKER_FDR_Q, this project's one other precedent for this choice of rate.
BAND_TIME_SWEEP_FAMILY_WISE_Q = 0.05


def sweep_tile_seconds():
    """The width of one cache tile, in seconds. One place reads it so a change cannot land in half
    the module."""
    return float(RAW_LSB_WINDOW_SECONDS)


def integration_time_tile_count(requested_seconds, window_s=None):
    """How many cache tiles a request for this many seconds of signal is actually served by, and how
    many seconds that is.

    MIRRORS ONE LINE OF THE MATCHER ON PURPOSE. ``availability.live_lsb_spectrum_match`` decides the
    count itself as ``max(1, round(td_quantity_s / window_s))`` and reports it back as
    ``td_n_epochs_cap`` in its statistics. This function computes the same thing so that a table can
    be labelled with the delivered length BEFORE the matcher runs, and there is a test that asserts
    the two agree for every length in ``BAND_TIME_SWEEP_SECONDS`` by reading the matcher's own
    reported count rather than by repeating the arithmetic.

    Returns ``(n_tiles, delivered_seconds)``. A request for 1 s comes back as ``(1, 3.0)``, because
    one tile is the smallest measurement the cache holds.
    """
    w = float(sweep_tile_seconds() if window_s is None else window_s)
    if w <= 0:
        return 1, 0.0
    n = max(1, int(round(float(requested_seconds) / w)))
    return int(n), float(n * w)


def sweep_center_freqs(cache_centers_hz, lo_hz=None, hi_hz=None):
    """The band centres the sweep can actually cover, taken from the cache's own grid.

    THE CACHE'S GRID DECIDES, NOT THE REQUEST. The band powers this sweep reads were computed on a
    fixed list of band centres when the cache was built, and a centre that is not on that list does
    not exist in the data. So the sweep covers the cache's centres that fall inside the requested
    span rather than a list of its own, and the payload reports which ones those were. Asking for
    whole-hertz centres when the cache holds half-hertz ones would otherwise silently return nothing.
    """
    lo = float(BAND_TIME_SWEEP_CENTER_LO_HZ if lo_hz is None else lo_hz)
    hi = float(BAND_TIME_SWEEP_CENTER_HI_HZ if hi_hz is None else hi_hz)
    c = np.atleast_1d(np.asarray(cache_centers_hz, dtype=float))
    keep = np.isfinite(c) & (c >= lo - 1e-9) & (c <= hi + 1e-9)
    return np.sort(c[keep])


def mad_outlier_columns(X, n_mad=None, scale="raw"):
    """The outlier mask for EVERY column of a band-power stack at once, by the same median-absolute-
    deviation rule ``stats_utils.mad_outlier_flags`` applies to one column.

    THE RULE IS NOT RESTATED, IT IS VECTORISED. Every clause of the scalar function is reproduced
    here: the logarithm first when ``scale`` is ``"log"``, the strict inequality, no consistency
    rescaling of the deviation, non-finite entries never flagged, fewer than four usable entries in
    a column means nothing is flagged in it, and a column whose deviation comes out as zero (a
    majority of its entries sharing one value) has nothing flagged rather than everything. There is
    a test that asserts this function and the scalar one agree column by column, including on those
    edge cases, because the only reason to have two is speed and a faster rule that is a different
    rule would be worse than the loop.

    ``X`` may be two-dimensional (rows by columns) or three-dimensional (lengths of signal by rows
    by columns); the rule is evaluated down the ROW axis in both cases. Returns a boolean mask the
    same shape as ``X``, True where the entry is an outlier.
    """
    X = np.asarray(X, dtype=float)
    n = float(OUTLIER_N_MAD if n_mad is None else n_mad)
    if str(scale) == "log":
        with np.errstate(divide="ignore", invalid="ignore"):
            V = np.log10(np.where(X > 0, X, np.nan))
    else:
        V = X
    ok = np.isfinite(V)
    row_axis = -2
    n_ok = ok.sum(axis=row_axis, keepdims=True)
    Vm = np.where(ok, V, np.nan)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        med = np.nanmedian(Vm, axis=row_axis, keepdims=True)
        dev = np.abs(Vm - med)
        mad = np.nanmedian(dev, axis=row_axis, keepdims=True)
    usable = (n_ok >= 4) & np.isfinite(mad) & (mad > 0)
    with np.errstate(invalid="ignore"):
        out = ok & usable & (dev > n * mad)
    return np.asarray(out, dtype=bool)


def pearson_r_columns(X, y):
    """The Pearson correlation between the pain score and EVERY column of a band-power matrix at
    once, as one set of matrix operations rather than a loop over bands.

    ``X`` is one row per pain report and one column per band, and may hold non-finite entries where
    a band had no usable measurement for that report. ``y`` is one pain score per report. Each
    column is correlated on its own usable rows, so two bands with different amounts of missing
    signal are each given their full sample rather than both being cut down to the rows they share.

    Returns ``{"r": (C,), "n": (C,)}`` where ``n`` is the count of pain reports behind each column.
    A column with fewer than three usable reports, or with no spread left in either quantity, comes
    back as a non-finite correlation rather than a number.
    """
    X = np.asarray(X, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    if X.ndim == 1:
        X = X[:, None]
    M = np.isfinite(X) & np.isfinite(y)[:, None]
    Xf = np.where(M, X, 0.0)
    Yf = np.where(M, y[:, None], 0.0)
    n = M.sum(axis=0).astype(np.float64)
    with np.errstate(invalid="ignore", divide="ignore"):
        sx = Xf.sum(axis=0)
        sy = Yf.sum(axis=0)
        cxy = (Xf * Yf).sum(axis=0) - sx * sy / n
        cxx = (Xf * Xf).sum(axis=0) - sx * sx / n
        cyy = (Yf * Yf).sum(axis=0) - sy * sy / n
        r = cxy / np.sqrt(cxx * cyy)
    r = np.asarray(r, dtype=float)
    r[(n < 3) | ~np.isfinite(r)] = np.nan
    return {"r": r, "n": n.astype(int)}


def average_ranks_columns(X):
    """The rank of every entry within its own column, with tied entries sharing the average of the
    ranks they span, computed for all columns at once.

    Non-finite entries are pushed above every real value so that they take the highest ranks and
    leave the ranks of the real values exactly as they would have been had the non-finite entries
    not been there. The caller must still exclude them by mask; their ranks are meaningless.

    Written out here rather than reached through scipy because the whole point of this section is to
    avoid a loop over bands, and this is the one primitive that makes the classification number a
    matrix operation.
    """
    X = np.asarray(X, dtype=np.float64)
    if X.ndim == 1:
        X = X[:, None]
    P, C = X.shape
    Xf = np.where(np.isfinite(X), X, np.inf)
    order = np.argsort(Xf, axis=0, kind="mergesort")
    Xs = np.take_along_axis(Xf, order, axis=0)
    starts = np.empty(Xs.shape, dtype=bool)
    starts[0, :] = True
    if P > 1:
        starts[1:, :] = Xs[1:, :] != Xs[:-1, :]
    gid = np.cumsum(starts, axis=0) - 1                 # tie-group index within each column
    pos = np.repeat(np.arange(1, P + 1, dtype=np.float64)[:, None], C, axis=1)
    cols = np.repeat(np.arange(C)[None, :], P, axis=0)
    sums = np.zeros((P, C), dtype=np.float64)
    cnts = np.zeros((P, C), dtype=np.float64)
    np.add.at(sums, (gid, cols), pos)
    np.add.at(cnts, (gid, cols), 1.0)
    avg_sorted = sums[gid, cols] / cnts[gid, cols]
    ranks = np.empty((P, C), dtype=np.float64)
    np.put_along_axis(ranks, order, avg_sorted, axis=0)
    return ranks


def rank_auc_columns(X, y_binary):
    """The area under the ROC curve of the BAND POWER ITSELF, for every column at once, keeping the
    direction rather than folding it away.

    A value above 0.5 means the band power tends to be HIGHER on high-pain reports, below 0.5 that
    it tends to be LOWER, and 0.5 that it is neither. This is the area under the curve of the
    threshold detector the device would actually run, since the device compares one band power
    against one threshold and nothing else.

    HOW THIS RELATES TO A FITTED LOGISTIC REGRESSION, MEASURED AND NOT ASSUMED. A logistic
    regression with a single predictor turns that predictor into a predicted probability through a
    curve that either only rises or only falls, and an area under the ROC curve depends solely on
    the order the scores put the observations in. So the fitted regression's own area under the
    curve, scored on the data it was fitted to, is EXACTLY one of two numbers -- this value, or one
    minus this value -- and which of the two is decided by the sign of the fitted slope. That much
    is exact and there is a test that checks it on every cell of a grid.

    WHICH OF THE TWO IT IS, IS THE PART THAT HAD TO BE MEASURED, and an earlier revision of this
    docstring got it wrong. The fitted slope follows the COVARIANCE between the pain state and the
    band power, which uses the band powers' values, while the ordering uses only their ranks; on a
    skewed band power a few large values can pull the covariance one way while the ranks point the
    other. When they point the same way the fitted number is the larger of the two, i.e. the
    direction-folded separability this module uses elsewhere; when they point opposite ways it is
    the smaller one and lands BELOW 0.5. Measured on a 220-cell grid: fitting on the base-ten
    logarithm of the band power, which is this module's own feature scale, the two point the same
    way in 209 of 220 cells, and the 11 that differ are all cells whose ordering sits close to 0.5
    in the first place. Fitting on the linear band power instead they agree in only 170 of 220.

    THE CONSEQUENCE FOR READING THE PANEL. The folded number cannot fall below 0.5 wherever the two
    directions agree, so 0.5 is close to a floor for it rather than a neutral middle, and a band
    carrying nothing lands a little above 0.5 rather than on it. That is why the level a folded
    value has to beat is the shuffled best-of-ten reference in the table, not 0.5. The grid the page
    draws is this UNFOLDED value, which does straddle 0.5 in both directions and for which 0.5 is
    the genuine no-discrimination point.

    ``logistic_auc_columns_fitted`` fits the regressions. The relationship above is what lets a
    220-cell grid be filled by two matrix operations instead of 220 model fits.

    Ties are given half credit, which is the ordinary Mann-Whitney convention and the same
    convention ``_weighted_auc_matrix`` already uses elsewhere in this module.

    ``y_binary`` is 1 for a high-pain report, 0 for a low-pain one, and non-finite for a report the
    split left out. Returns ``{"auc", "n_pos", "n_neg"}``, each one value per column.
    """
    X = np.asarray(X, dtype=np.float64)
    y = np.asarray(y_binary, dtype=np.float64)
    if X.ndim == 1:
        X = X[:, None]
    labelled = np.isfinite(y)
    Xl = X[labelled, :]
    yl = y[labelled]
    C = X.shape[1]
    if Xl.shape[0] == 0:
        nan = np.full(C, np.nan)
        return {"auc": nan, "n_pos": np.zeros(C, int), "n_neg": np.zeros(C, int)}
    ok = np.isfinite(Xl)
    ranks = average_ranks_columns(Xl)
    pos = ok & (yl == 1)[:, None]
    neg = ok & (yl == 0)[:, None]
    n_pos = pos.sum(axis=0).astype(np.float64)
    n_neg = neg.sum(axis=0).astype(np.float64)
    rank_sum_pos = np.where(pos, ranks, 0.0).sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        u = rank_sum_pos - n_pos * (n_pos + 1.0) / 2.0
        auc = u / (n_pos * n_neg)
    auc = np.asarray(auc, dtype=float)
    auc[(n_pos < 1) | (n_neg < 1) | ~np.isfinite(auc)] = np.nan
    return {"auc": auc, "n_pos": n_pos.astype(int), "n_neg": n_neg.astype(int)}


def logistic_auc_columns_fitted(X, y_binary, feature_scale="raw", n_jobs=None):
    """The same area under the curve, obtained by actually FITTING a one-predictor logistic
    regression per column and scoring it on the data it was fitted to.

    THIS IS THE CHECK, NOT THE PRODUCTION PATH, and it exists for two reasons. The first is that the
    identity ``rank_auc_columns`` documents has to be tested against a real fit rather than
    asserted, and it is: ``test_analytics`` fits every cell of a grid and compares. The second is
    that the cost of the two routes has to be measured rather than guessed before choosing one.

    The regression is the unpenalised maximum-likelihood fit (``statsmodels.api.Logit``), which is
    the conventional one-predictor logistic regression, rather than a penalised solver whose
    shrinkage would move the fitted slope and so change what is being compared. The single predictor
    is centred and scaled to unit spread first, purely so the solver converges on bands whose powers
    differ by orders of magnitude; a linear rescaling cannot change an area under the curve, which
    depends only on the order of the fitted scores.

    ``feature_scale="log"`` fits on the base-ten logarithm of the band power. A logarithm is
    increasing, so it cannot change the area under the curve of the band power itself; it changes
    only whether the fitted STRAIGHT LINE points the same way as that ordering, which is the one
    thing that decides whether the fitted number comes out folded or not.

    ``n_jobs`` fits the columns on that many worker threads. Measured on the live record and
    reported in the session notes: parallelising was NOT worth it here, because the fits are
    milliseconds each and every one of them releases and reacquires the interpreter lock around a
    very short amount of numerical work, so thread overhead swamps the gain. It is kept as an
    argument, defaulting to serial, so the measurement can be repeated rather than re-litigated.

    Returns ``{"auc": (C,), "slope": (C,), "converged": (C,)}``, non-finite where no fit was made.
    """
    import statsmodels.api as sm
    from sklearn.metrics import roc_auc_score
    X = np.asarray(X, dtype=np.float64)
    y = np.asarray(y_binary, dtype=np.float64)
    if X.ndim == 1:
        X = X[:, None]
    if str(feature_scale) == "log":
        with np.errstate(divide="ignore", invalid="ignore"):
            X = np.log10(np.where(X > 0, X, np.nan))
    labelled = np.isfinite(y)
    C = X.shape[1]

    def _one(c):
        m = labelled & np.isfinite(X[:, c])
        if int(m.sum()) < 8:
            return np.nan, np.nan, False
        yy = y[m].astype(int)
        if len(np.unique(yy)) < 2:
            return np.nan, np.nan, False
        xx = X[m, c]
        sd = float(np.std(xx))
        if not np.isfinite(sd) or sd <= 0:
            return np.nan, np.nan, False
        xs = (xx - float(np.mean(xx))) / sd
        design = sm.add_constant(xs)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                res = sm.Logit(yy, design).fit(disp=0)
            # SCORED ON THE LINEAR PREDICTOR, NOT THE FITTED PROBABILITY. The two order the
            # observations identically, so the area under the curve is the same quantity, but a
            # strongly separating band drives the fitted probabilities to exactly 1.0 and exactly
            # 0.0 in floating point, and those saturated values TIE observations that the predictor
            # itself orders strictly. Ties are given half credit, so scoring the probability moved
            # the area under the curve by up to 0.03 on the live record purely as an artefact of
            # the number format. The linear predictor never saturates.
            return (float(roc_auc_score(yy, design @ np.asarray(res.params))),
                    float(np.asarray(res.params)[1]), bool(getattr(res, "mle_retvals", {})
                                                           .get("converged", True)))
        except Exception:
            return np.nan, np.nan, False

    if n_jobs and int(n_jobs) > 1:
        with ThreadPoolExecutor(max_workers=int(n_jobs)) as pool:
            got = list(pool.map(_one, range(C)))
    else:
        got = [_one(c) for c in range(C)]
    return {"auc": np.asarray([g[0] for g in got], dtype=float),
            "slope": np.asarray([g[1] for g in got], dtype=float),
            "converged": np.asarray([g[2] for g in got], dtype=bool)}


def _sweep_blank(reason, *, n_reports=0):
    """The result when the sweep could not be run at all: no grid, and the reason in words."""
    return {
        "answer": BAND_PAIN_NOT_ASSESSED,
        "why": str(reason),
        "n_pain_reports": int(n_reports),
        "center_freqs_hz": [],
        "integration_seconds_requested": [float(s) for s in BAND_TIME_SWEEP_SECONDS],
        "integration_seconds_delivered": [],
        "correlation_grid": [],
        "auc_grid": [],
        "n_grid": [],
        # Present and empty rather than absent, for the same reason every other grid here is: the
        # page reads a missing key as "this does not apply to me" and would draw an unmarked grid.
        "device_spectrum_n_grid": [],
        "device_spectrum_total_grid": [],
        "device_spectrum_share_grid": [],
        "device_spectrum_n_grid_auc": [],
        "device_spectrum_total_grid_auc": [],
        "device_spectrum_share_grid_auc": [],
        "n_pain_reports_from_device_spectrum": None,
        "best_correlation_rows": [],
        "best_auc_rows": [],
        "notes": [],
    }


#: ==========================================================================================
#: THE BAND-BY-LENGTH SWEEP'S OWN OUTLIER RULE, replacing the 5-MAD/log-scale rule for this one
#: quantity only (PI decision, 2026-09-09) -- the "plate-wide" 5 MAD rule two sections above is
#: UNCHANGED and still governs every other outlier exclusion on this page (the correlation
#: spectrum, the chronic LFP-power column, etc.); this table applies to the calibrated
#: band-by-length grid alone.
#:
#: THE RULE: discard a measurement above the historical 99.5th-percentile ceiling for that EXACT
#: (contact, band centre) pair, precomputed ONCE from this participant's ENTIRE recorded history --
#: never recomputed from the window being checked -- the same reasoning decision 52 already used
#: for the device's own saturation ceiling in `ClosedLoopDeployment.ceiling_thresholds`. His own
#: framing: "discard the top 0.5% of data using a list of precalculated thresholds... hard coded
#: now and applied to individual windows in future analysis."
#:
#: POOLED, NOT SPLIT, BY SOURCE. He explicitly asked to "forget applying [the rule] by source":
#: a channel's ceiling is one number per band centre, computed from every LSB value this
#: participant's history holds for that (contact, centre) regardless of whether it derived from
#: the time-domain-transform tier or the PSD-bridge tier -- unlike the (separate, still-unwired)
#: `ClosedLoopDeployment.ceiling_thresholds.TIME_DOMAIN_CEILINGS`/`RAW_LSB_CEILINGS`, which keep
#: those two tiers apart. Confirmed before building this that the sweep's own `X` matrix is
#: genuinely in device LSB units already ("BUT MAKE SURE" was the direct instruction) --
#: `availability.live_lsb_spectrum_match`'s own return-value docstring says so explicitly
#: ("LINEAR LSB (NOT logged) per band center"), and it draws from the identical
#: `_raw_lsb_cache_cached` tile cache this table was computed from, so the units and the source
#: data are the same population, not merely the same convention.
#:
#: COMPUTED, NOT DERIVED AT RUNTIME. Built once by `_agent_bridge/_sweep_ceiling_export.py`
#: (disposable, gitignored) against RCS08 (`2e3c75c00d7f4f37b53a048d195f11da`), at exactly the
#: sweep's own 22 band centres (8.5-29.5 Hz), pooling every `td`/`psd` LSB value the tile cache
#: holds per (channel, centre): 582 (channel, centre) groups, 145,894 of 29,103,915 values
#: excluded (0.5013%, matching "top 0.5%" by construction), no group under the 20-sample floor.
#: Recomputing this table for a new participant or after a large new upload means re-running that
#: script and replacing this dict -- there is no runtime recomputation path, matching
#: `ceiling_thresholds.py`'s own committed-constant convention.
#:
#: APPLIED TO SINGLE 3 s PIECES, NOT TO THE AVERAGED CELL (PI, 2026-09-09, revising the first
#: build of this rule). These numbers are percentiles of INDIVIDUAL 3 s chunk values, so the only
#: place they can honestly be compared is against individual 3 s chunk values -- before any
#: averaging. `availability.live_lsb_band_medians_by_length` is where that happens, and its own
#: docstring carries the measurements behind the change: applying them to the averaged cell instead
#: discarded 0.708% of the 1 s row but only 0.300% from the 20 s row up, because an average of 100
#: chunks sits far closer to the middle than any single chunk does.
#:
#: FALLS BACK TO THE OLD MAD RULE FOR ANY CHANNEL THIS TABLE DOES NOT COVER -- a synthetic test
#: channel, the demo participant, or a real contact this table has not yet been rebuilt for --
#: so outlier exclusion is never silently skipped rather than merely using a different method.
#: This is also why every existing test of `band_time_sweep_from_power`'s outlier behaviour still
#: passes unchanged: none of them pass one of these six real channel names, so they all still
#: exercise the MAD path exactly as before.
BAND_SWEEP_LSB_CEILINGS = {
    "ZERO_THREE_RIGHT": {8.5: 5229.9, 9.5: 4623.2, 10.5: 3875.9, 11.5: 3210.1, 12.5: 2397.3,
        13.5: 1596.9, 14.5: 1012.0, 15.5: 750.7, 16.5: 639.6, 17.5: 615.4, 18.5: 622.7,
        19.5: 660.7, 20.5: 661.7, 21.5: 628.9, 22.5: 566.0, 23.5: 499.5, 24.5: 498.6,
        25.5: 2061.0, 26.5: 3438.3, 27.5: 3459.9, 28.5: 3460.9, 29.5: 3394.6},
    "ONE_THREE_LEFT": {8.5: 2157.9, 9.5: 1773.0, 10.5: 1438.9, 11.5: 1254.8, 12.5: 1120.7,
        13.5: 978.0, 14.5: 910.7, 15.5: 844.5, 16.5: 816.8, 17.5: 784.4, 18.5: 787.5,
        19.5: 814.3, 20.5: 898.3, 21.5: 1002.0, 22.5: 1106.9, 23.5: 1149.7, 24.5: 1124.9,
        25.5: 1025.8, 26.5: 882.0, 27.5: 724.8, 28.5: 599.5, 29.5: 486.1},
    "ZERO_THREE_LEFT": {8.5: 2989.7, 9.5: 2591.7, 10.5: 2251.4, 11.5: 1948.8, 12.5: 1679.0,
        13.5: 1448.3, 14.5: 1267.4, 15.5: 1188.2, 16.5: 1118.7, 17.5: 1042.0, 18.5: 973.1,
        19.5: 928.3, 20.5: 887.9, 21.5: 912.0, 22.5: 929.8, 23.5: 924.8, 24.5: 906.6,
        25.5: 847.5, 26.5: 757.4, 27.5: 630.4, 28.5: 522.9, 29.5: 435.3},
    "ZERO_TWO_LEFT": {8.5: 1957.4, 9.5: 1763.8, 10.5: 1586.1, 11.5: 1424.6, 12.5: 1284.2,
        13.5: 1108.8, 14.5: 987.9, 15.5: 920.9, 16.5: 849.7, 17.5: 787.6, 18.5: 730.7,
        19.5: 679.2, 20.5: 643.5, 21.5: 631.4, 22.5: 629.8, 23.5: 632.2, 24.5: 608.6,
        25.5: 564.6, 26.5: 517.4, 27.5: 456.9, 28.5: 392.1, 29.5: 352.5},
    "ONE_THREE_RIGHT": {8.5: 4747.9, 9.5: 4115.1, 10.5: 3298.7, 11.5: 2414.9, 12.5: 1819.9,
        13.5: 1201.0, 14.5: 815.6, 15.5: 572.4, 16.5: 434.6, 17.5: 389.3, 18.5: 380.7,
        19.5: 369.6, 20.5: 357.9, 21.5: 335.7, 22.5: 298.8, 23.5: 267.0, 24.5: 245.5,
        25.5: 222.8, 26.5: 201.5, 27.5: 180.0, 28.5: 157.1, 29.5: 137.0},
    "ZERO_TWO_RIGHT": {8.5: 4526.1, 9.5: 4840.0, 10.5: 4724.2, 11.5: 4250.1, 12.5: 3400.6,
        13.5: 2025.0, 14.5: 1026.9, 15.5: 645.9, 16.5: 509.4, 17.5: 510.0, 18.5: 571.2,
        19.5: 602.7, 20.5: 618.2, 21.5: 582.7, 22.5: 521.0, 23.5: 455.0, 24.5: 400.6,
        25.5: 353.1, 26.5: 318.6, 27.5: 274.1, 28.5: 236.7, 29.5: 198.9},
}


def band_sweep_lsb_ceiling(channel, centre_hz):
    """The historical 99.5th-percentile ceiling for one (contact, band centre), or `None` if this
    channel has no table entry at all (falls back to the MAD rule) or this exact centre is
    missing from an otherwise-covered channel (that one column gets no ceiling exclusion)."""
    table = BAND_SWEEP_LSB_CEILINGS.get(channel)
    if not table:
        return None
    return table.get(round(float(centre_hz), 1))


#: The sentence that travels with the device-spectrum mark wherever it is reported. Written once so
#: the page, the notes and any exported copy cannot drift into three different explanations.
DEVICE_SPECTRUM_AXIS_NOTE = (
    "A pain report with no voltage trace within the match window is answered from the device's "
    "own FFT snapshots instead. Each snapshot covers 30 s, so a row of N seconds takes the nearest "
    "ceil(N / 30) snapshots within the window, and a report without that many contributes nothing "
    "to that row -- which is why the taller rows can hold fewer reports than the short ones.")


def _device_spectrum_cell_counts(X, pain, from_device_spectrum):
    """Per cell: how many of the pain reports behind it came from the device's own spectrum.

    Counted HERE, where the cell is, rather than once per sensing contact, because a contact-wide
    share pasted onto every cell would be wrong in both directions: a report drops out of one cell
    and not its neighbour when its own band value is missing or was excluded, and the number of
    reports behind a cell changes down the length-of-signal axis as short lengths run out of clean
    recording. The denominator is exactly the rows the correlation used -- a finite band power AND
    a finite pain score -- so share and value describe the same set of reports.

    Returns `(n_device, n_total)`, both (T, C) integer arrays. `from_device_spectrum` of the wrong
    length, or missing, gives all-zero device counts rather than raising: the mark is a caveat, and
    a caveat that could break a page is worse than one that is absent.
    """
    T, P, C = X.shape
    ok = np.isfinite(X) & np.isfinite(np.asarray(pain, dtype=float))[None, :, None]
    n_total = ok.sum(axis=1).astype(int)
    dev = np.zeros(P, dtype=bool)
    flags = list(from_device_spectrum or [])
    if len(flags) == P:
        dev = np.asarray([bool(v) for v in flags], dtype=bool)
    n_device = (ok & dev[None, :, None]).sum(axis=1).astype(int)
    return n_device, n_total


def _attach_device_spectrum_to_rows(rows, n_device, n_total, requested_seconds):
    """Copy the winning cell's device-spectrum counts onto each band centre's headline row.

    Rows come back one per band centre in centre order, so the row's position IS its column in the
    grid; the length of signal is looked up by the row's OWN reported requested seconds rather than
    assumed, so a row that names a length is never handed another length's count. A row that never
    found a usable length carries the fields as "not assessed" rather than absent -- an absent key
    reads on the page as "does not apply", which here would be the opposite of the truth.
    """
    req = [float(s) for s in (requested_seconds or [])]
    for c, row in enumerate(rows or []):
        row["n_pain_reports_from_device_spectrum"] = None
        row["device_spectrum_share"] = None
        if c >= n_total.shape[1]:
            continue
        s = row.get("integration_seconds_requested")
        if s is None:
            continue
        try:
            t = req.index(float(s))
        except ValueError:
            continue
        tot = int(n_total[t, c])
        row["n_pain_reports_from_device_spectrum"] = int(n_device[t, c])
        row["device_spectrum_share"] = (float(n_device[t, c]) / tot) if tot > 0 else None


def band_time_sweep_from_power(power_by_seconds, pain_scores, *, center_freqs_hz,
                               band_width_hz=BAND_TIME_SWEEP_WIDTH_HZ,
                               strategy="tertile", low_pct=33.3333, high_pct=66.6667,
                               pain_cutoff=None, outlier_n_mad=None, outlier_scale=None,
                               n_perm=BAND_TIME_SWEEP_N_PERM, n_boot=BAND_TIME_SWEEP_N_BOOT,
                               seed=0, power_feature="band power", channel=None,
                               metric_key=None, metric_label=None,
                               tile_seconds=None, requested_seconds=None, chunk_exclusion=None,
                               from_device_spectrum=None):
    """The whole grid: for every band centre and every length of signal averaged into one
    measurement, how well that band's power tracks the chosen pain score.

    ``power_by_seconds`` maps a requested length of signal in seconds to a band-power matrix with
    one row per pain report (in the order the pain scores are given) and one column per band centre.
    Assembling those matrices is the caller's job, because it is the caller that owns the matching
    of recordings to pain reports; this function does the arithmetic and the honesty accounting.

    ONE PAIN REPORT IS ONE ROW. The matching this reads gives each pain report a single band-power
    vector per length of signal, so there is no question of one well-covered report counting many
    times, and no one-report-one-vote weighting is needed. ``n_pain_reports`` on every row is
    therefore also the number of independent observations behind the number.

    WHAT COMES BACK. ``correlation_grid`` and ``auc_grid`` are both one row per length of signal and
    one column per band centre, so the surface can be drawn. ``best_correlation_rows`` and
    ``best_auc_rows`` are one row per band centre carrying the best value in that band's column, the
    length of signal that produced it, the count behind it, an interval, and the selection-aware
    reference described in the section note above. The area-under-the-curve rows are referenced to
    0.5 throughout and carry ``no_relationship_value`` saying so.
    """
    rng = np.random.default_rng(int(seed))
    tile_s = float(sweep_tile_seconds() if tile_seconds is None else tile_seconds)
    req = list(BAND_TIME_SWEEP_SECONDS if requested_seconds is None else requested_seconds)
    centers = np.atleast_1d(np.asarray(center_freqs_hz, dtype=float))
    pain = np.asarray(pain_scores, dtype=float)
    n_reports_in = int(pain.size)
    if centers.size == 0:
        return _sweep_blank("no band centre inside the range asked for is present in the cached "
                            "spectra, so there is nothing to sweep", n_reports=n_reports_in)
    if n_reports_in == 0:
        return _sweep_blank("no pain reports were handed in, so there is nothing to correlate the "
                            "band power against")

    # ---- assemble the grid's band-power matrices in the order of the requested lengths ----------
    stacks, delivered, tiles, kept_req = [], [], [], []
    for s in req:
        mat = power_by_seconds.get(s)
        if mat is None:
            mat = power_by_seconds.get(float(s))
        if mat is None:
            continue
        m = np.asarray(mat, dtype=np.float64)
        if m.ndim != 2 or m.shape[0] != n_reports_in or m.shape[1] != centers.size:
            continue
        n_tiles, deliv = integration_time_tile_count(s, tile_s)
        stacks.append(m)
        delivered.append(float(deliv))
        tiles.append(int(n_tiles))
        kept_req.append(float(s))
    if not stacks:
        return _sweep_blank("no band-power measurements were produced for any of the lengths of "
                            "signal asked for", n_reports=n_reports_in)
    X = np.stack(stacks, axis=0)                      # (T, P, C)
    T, P, C = X.shape

    # ---- outlier exclusion --------------------------------------------------------------------
    # `chunk_exclusion` means the contaminated 3 s chunks were ALREADY left out, one at a time,
    # before any of them were averaged into these cells (PI decision, 2026-09-09;
    # `availability.live_lsb_band_medians_by_length` carries the full reasoning). There is nothing
    # left to exclude here, and re-running a cell-level rule on top would be a second, different
    # exclusion applied to values that have already been cleaned.
    n_mad = float(OUTLIER_N_MAD if outlier_n_mad is None else outlier_n_mad)
    o_scale = str(OUTLIER_SCALE if outlier_scale is None else outlier_scale)
    n_excluded = 0
    outlier_rule = "none"
    if chunk_exclusion:
        n_excluded = int(chunk_exclusion.get("n_chunk_band_values_excluded") or 0)
        outlier_rule = "historical_99p5_ceiling_per_chunk"
    elif n_mad > 0:
        # Applied separately for each band centre and each length of signal, because band powers
        # differ by orders of magnitude between bands and a threshold pooled across bands would be
        # set by whichever band carries the largest numbers. Same rule and same reasoning as the
        # full-spectrum scan on this page, computed here for every column of every length of
        # signal in one pass -- see `mad_outlier_columns`.
        drop = mad_outlier_columns(X.reshape(T * P, C).reshape(T, P, C), n_mad=n_mad,
                                   scale=o_scale)
        n_excluded = int(drop.sum())
        X[drop] = np.nan
        outlier_rule = f"{n_mad:g}_mad_{o_scale}"

    # ---- the continuous half: Pearson correlation, all bands at once per length of signal ------
    corr = np.full((T, C), np.nan)
    corr_n = np.zeros((T, C), dtype=int)
    for t in range(T):
        got = pearson_r_columns(X[t], pain)
        corr[t] = got["r"]
        corr_n[t] = got["n"]

    # ---- the classification half: split the pain scores once, then rank ------------------------
    y_bin, split_why, low_cut, high_cut = _pain_split(
        pain, strategy=strategy, low_pct=low_pct, high_pct=high_pct, pain_cutoff=pain_cutoff)
    y_bin = np.asarray(y_bin, dtype=float)
    auc = np.full((T, C), np.nan)
    auc_pos = np.zeros((T, C), dtype=int)
    auc_neg = np.zeros((T, C), dtype=int)
    for t in range(T):
        got = rank_auc_columns(X[t], y_bin)
        auc[t] = got["auc"]
        auc_pos[t] = got["n_pos"]
        auc_neg[t] = got["n_neg"]
    # The direction-folded value is what a fitted one-predictor logistic regression returns in
    # sample; see the identity documented on `rank_auc_columns`. It is carried alongside rather than
    # instead, because folding throws the direction away AND puts a floor at 0.5, and the grid the
    # page draws needs both sides of 0.5 to be visible.
    with np.errstate(invalid="ignore"):
        auc_folded = np.maximum(auc, 1.0 - auc)

    # ---- which cells the length-of-signal axis does not apply to (open item 26) ----------------
    # Computed on the SAME X the two grids above were computed from, after the outlier step, so the
    # mark counts the reports those cells actually used.
    dev_n, dev_tot = _device_spectrum_cell_counts(X, pain, from_device_spectrum)
    # THE TWO GRIDS DO NOT USE THE SAME PAIN REPORTS, so they do not get the same mark. Splitting
    # the pain scores into thirds throws the middle third away, so an area-under-the-curve cell is
    # computed from FEWER reports than the correlation cell directly above it, and the share of
    # those that came from the device's own spectrum need not be the same. Marking both from one
    # count would put a number on the screen that belongs to the other grid.
    dev_n_auc, dev_tot_auc = _device_spectrum_cell_counts(X, y_bin, from_device_spectrum)
    with np.errstate(invalid="ignore", divide="ignore"):
        dev_share = np.where(dev_tot > 0, dev_n / np.maximum(dev_tot, 1), np.nan)
        dev_share_auc = np.where(dev_tot_auc > 0, dev_n_auc / np.maximum(dev_tot_auc, 1), np.nan)
    _dev_flags = [bool(v) for v in (from_device_spectrum or [])]
    # Reported as None, not 0, when the flag did not arrive: "none of them" and "nobody checked"
    # are different answers, and a page that shows a confident zero for the second is lying quietly.
    n_dev_reports = int(sum(_dev_flags)) if len(_dev_flags) == P else None

    # ---- the selection-aware reference: the distribution of the BEST OF TEN under no relationship
    corr_null = _best_of_windows_null_correlation(X, pain, n_perm=int(n_perm), rng=rng)
    auc_null = _best_of_windows_null_auc(X, y_bin, n_perm=int(n_perm), rng=rng)

    # ---- one row per band centre, naming the winning length of signal --------------------------
    best_corr_rows = _best_rows_correlation(
        corr, corr_n, X, pain, centers, kept_req, delivered, tiles, corr_null,
        band_width_hz=band_width_hz, n_boot=int(n_boot), rng=rng,
        power_feature=power_feature, channel=channel)
    best_auc_rows = _best_rows_auc(
        auc, auc_pos, auc_neg, X, y_bin, centers, kept_req, delivered, tiles, auc_null,
        band_width_hz=band_width_hz, n_boot=int(n_boot), rng=rng,
        power_feature=power_feature, channel=channel, split_why=split_why,
        low_cut=low_cut, high_cut=high_cut)

    # DECISION 63: a second, independent correction across the grid's own 22 band centres, on top
    # of (never instead of) each row's existing best-of-ten-lengths answer. `p_selection_aware`
    # already corrects for picking the best of ten lengths at one centre; feeding those 22
    # per-centre p-values into the SAME Benjamini-Hochberg function the older full-spectrum routine
    # already uses (`stats_utils.bh_fdr`) corrects for having tested 22 centres at once too. The
    # family is exactly this grid's own 22 points, restricted to 8-30 Hz by the device's own limits
    # -- never pooled with the older routine's much wider range, which is why this has its own
    # field name rather than reusing that routine's. This is a LABEL, never a gate (the PI's own
    # words): a row that fails it is unchanged in every other respect and remains fully readable,
    # selectable and exportable.
    _apply_family_wise_correction(best_corr_rows)
    _apply_family_wise_correction(best_auc_rows)

    # The headline row for each band centre names ONE cell -- the length of signal that won. The
    # mark has to travel with it, or a reader who never looks at the grid itself would see a
    # winning length chosen partly from reports for which no length was ever read.
    _attach_device_spectrum_to_rows(best_corr_rows, dev_n, dev_tot, kept_req)
    _attach_device_spectrum_to_rows(best_auc_rows, dev_n_auc, dev_tot_auc, kept_req)

    crosscheck = logistic_fit_crosscheck(
        {float(kept_req[t]): X[t] for t in range(T)}, y_bin, best_auc_rows)
    # The two keys naming which grid cell a row came from existed only so the cross-check could
    # refit exactly that cell. They are dropped before the rows leave, so they cannot turn up as
    # unexplained columns in a saved comma-separated file.
    for _r in best_auc_rows:
        _r.pop("_grid_time_index", None)
        _r.pop("_grid_center_index", None)
    notes = _sweep_notes(kept_req, delivered, tiles, tile_s, T, C, n_mad, o_scale, n_excluded,
                         int(n_perm), split_why, crosscheck, outlier_rule=outlier_rule)
    # Added only when this contact actually has such reports, and it carries the count, so a reader
    # can check the sentence against a number instead of taking it on trust. A contact with none
    # gets no note at all rather than a reassuring one -- there is nothing to reassure about.
    if n_dev_reports:
        _worst = float(np.nanmax(dev_share)) if np.isfinite(dev_share).any() else 0.0
        notes.append(
            "%d of this contact pair's matched pain reports were answered from the device's own "
            "FFT snapshots rather than the voltage trace, and the most affected cell drew %.0f%% of "
            "its reports that way. %s" % (n_dev_reports, 100.0 * _worst, DEVICE_SPECTRUM_AXIS_NOTE))
    n_used = int(np.nanmax(corr_n)) if corr_n.size and np.isfinite(corr).any() else 0
    return {
        "answer": (BAND_PAIN_ESTABLISHED
                   if any(r.get("answer") == BAND_PAIN_ESTABLISHED for r in best_auc_rows)
                   else (BAND_PAIN_NOT_RESOLVED if best_auc_rows else BAND_PAIN_NOT_ASSESSED)),
        "why": ("one row per band centre below; each row's own answer is the one to read, and the "
                "answer here only says whether ANY band centre reached one"),
        "channel": (str(channel) if channel is not None else None),
        "metric_key": (str(metric_key) if metric_key is not None else None),
        "metric_label": (str(metric_label) if metric_label is not None else None),
        "power_feature": str(power_feature),
        "band_width_hz": float(band_width_hz),
        "tile_seconds": float(tile_s),
        "center_freqs_hz": [float(c) for c in centers],
        "band_fully_inside_8_to_30_hz": [
            bool(c - band_width_hz / 2.0 >= BAND_TIME_SWEEP_CENTER_LO_HZ - 1e-9
                 and c + band_width_hz / 2.0 <= BAND_TIME_SWEEP_CENTER_HI_HZ + 1e-9)
            for c in centers],
        "integration_seconds_requested": [float(s) for s in kept_req],
        "integration_seconds_delivered": delivered,
        "integration_tiles": tiles,
        "correlation_grid": [[_f(v) for v in row] for row in corr],
        "auc_grid": [[_f(v) for v in row] for row in auc],
        "auc_direction_folded_grid": [[_f(v) for v in row] for row in auc_folded],
        "n_grid": [[int(v) for v in row] for row in corr_n],
        "auc_n_high_grid": [[int(v) for v in row] for row in auc_pos],
        "auc_n_low_grid": [[int(v) for v in row] for row in auc_neg],
        # OPEN ITEM 26. Same shape as the two grids above, one entry per cell: how many of the pain
        # reports behind that cell were answered from the device's OWN spectrum, how many reports
        # the cell used in total, and the share. Those reports carry no length of signal, so the
        # higher the share, the less of that cell's column is a trend at all.
        "device_spectrum_n_grid": [[int(v) for v in row] for row in dev_n],
        "device_spectrum_total_grid": [[int(v) for v in row] for row in dev_tot],
        "device_spectrum_share_grid": [[_f(v) for v in row] for row in dev_share],
        # The same three for the area-under-the-curve grid, which is computed from fewer reports
        # because the split throws the middle third of the pain scores away.
        "device_spectrum_n_grid_auc": [[int(v) for v in row] for row in dev_n_auc],
        "device_spectrum_total_grid_auc": [[int(v) for v in row] for row in dev_tot_auc],
        "device_spectrum_share_grid_auc": [[_f(v) for v in row] for row in dev_share_auc],
        "n_pain_reports_from_device_spectrum": n_dev_reports,
        "device_spectrum_axis_note": DEVICE_SPECTRUM_AXIS_NOTE,
        "best_correlation_rows": best_corr_rows,
        "best_auc_rows": best_auc_rows,
        "logistic_fit_crosscheck": crosscheck,
        "correlation_no_relationship_value": CORRELATION_NO_RELATIONSHIP,
        "auc_no_relationship_value": AUC_NO_DISCRIMINATION,
        "auc_grid_is": ("the area under the curve of the band power itself, keeping its direction: "
                        "above 0.5 the band power is higher on high-pain reports, below 0.5 it is "
                        "lower, and 0.5 means neither"),
        "auc_direction_folded_grid_is": ("the same value with its direction folded away, which is "
                                         "what a fitted one-predictor logistic regression returns "
                                         "in sample; it cannot fall below 0.5, so for THAT number "
                                         "0.5 is a floor and the shuffled level in the table below "
                                         "is what it has to beat"),
        "pain_split_rule": split_why,
        "pain_low_cut": (float(low_cut) if low_cut is not None else None),
        "pain_high_cut": (float(high_cut) if high_cut is not None else None),
        "n_pain_reports": n_used,
        "n_pain_reports_handed_in": n_reports_in,
        "n_measurements_excluded_as_outliers": int(n_excluded),
        "outlier_rule": outlier_rule,
        # The exclusion's own counts, so a reader can check the note against them rather than
        # taking the sentence on trust: how many pieces were eligible, how many single band values
        # were left out, and how many cells could not be refilled to the count their row asked for
        # because the rating simply had no more clean recording nearby.
        "chunk_exclusion": (dict(chunk_exclusion) if chunk_exclusion else None),
        "outlier_n_mad": float(n_mad),
        "outlier_scale": o_scale,
        "n_shuffles": int(n_perm),
        "n_resamples": int(n_boot),
        "notes": notes,
    }


def _best_of_windows_null_correlation(X, pain, *, n_perm, rng):
    """The distribution of the LARGEST correlation over the ten lengths of signal, when the pain
    scores carry no relationship to the band power.

    THIS IS THE COMPARISON THE PANEL'S BEST CELL HAS TO BE READ AGAINST. The reported best cell in a
    band's row was chosen after seeing ten values, so comparing it against the distribution of a
    single correlation overstates how unusual it is. Here the same best-of-ten choice is made on
    each shuffle, so the observed best is compared against a distribution of bests.

    The shuffling is a circular block permutation of the pain scores, the same null the rest of this
    module uses (``stats_utils.circular_block_perm_matrix``), because pain scores on nearby days
    resemble each other and an independent shuffle would make the reference too easy to beat. The
    block length is chosen from the measured autocorrelation of the pain scores.

    Every shuffle's whole grid is TWO matrix products in total -- not two per length of signal --
    so the entire reference costs a handful of matrix operations rather than n_perm * 10 * C
    correlations. The ten lengths of signal are stood side by side into one right-hand side so that
    the shuffled pain scores are read from memory twice instead of thirty times, which is where the
    time was going; see the note in the body about why that leaves every number unchanged and how
    that is checked.
    Returns ``{"p95", "p99", "max_abs_by_perm", "block_length", "p_selection_aware" (C,)}``.
    """
    from .stats_utils import block_length_for, circular_block_perm_matrix, permutation_null_resolution
    T, P, C = X.shape
    y = np.asarray(pain, dtype=np.float64)
    usable = np.isfinite(y)
    if usable.sum() < 4 or int(n_perm) < 10:
        return {"p95": None, "p99": None, "block_length": None, "n_used": 0,
                "p_resolution": None, "best_abs_by_shuffle": [], "p_selection_aware": None}
    yu = y[usable]
    Xu = X[:, usable, :]
    nP = int(yu.size)
    block = int(block_length_for(yu, nP))
    perm = circular_block_perm_matrix(nP, block, int(n_perm), rng)        # (S, nP)
    Yp = yu[perm]                                                        # (S, nP)
    S = Yp.shape[0]
    best = np.zeros((S, C), dtype=np.float64)
    # ALL TEN LENGTHS' MATRIX PRODUCTS ARE TAKEN IN TWO PRODUCTS RATHER THAN THIRTY. The shuffled
    # pain scores are the same thousand-by-a-few-hundred matrix for every length of signal, so
    # written a length at a time that matrix is read from memory thirty times to produce only
    # twenty-two columns of answer each time, which is what the product spends its time on rather
    # than on the multiplying. Standing the ten lengths' right-hand sides side by side reads it
    # twice and asks for all the columns at once: measured on the real record, twenty of these
    # products take 0.063 s written separately and 0.021 s written as one.
    #
    # THE NUMBERS ARE THE SAME ONES, AND THAT IS CHECKED RATHER THAN ASSUMED. A matrix product
    # accumulates each answer over the pain reports in an order the linear-algebra library chooses,
    # and in principle a library could choose differently when asked for more columns at once,
    # which would move the last bit of a correlation and could in turn move a verdict. On the build
    # this runs on it does not: the two forms agree on every one of 440,000 numbers. That is a
    # measured property of the library, not a guarantee about every future version of it, so
    # `test_sweep_statistics_exact.py` asserts it directly. If a library upgrade ever breaks it the
    # test fails loudly instead of the verdicts moving quietly.
    masks, filled = [], []
    for t in range(T):
        Mt = np.isfinite(Xu[t])
        masks.append(Mt)
        filled.append(np.where(Mt, Xu[t], 0.0))
    rhs_masks = np.concatenate([m.astype(np.float64) for m in masks], axis=1)   # (nP, T*C)
    rhs = np.concatenate([rhs_masks] + filled, axis=1)                          # (nP, 2*T*C)
    g_lin = Yp @ rhs                                                            # (S, 2*T*C)
    g_sq = (Yp * Yp) @ rhs_masks                                                # (S, T*C)
    for t in range(T):
        M = masks[t]                                                     # (nP, C)
        Xf = filled[t]
        n = M.sum(axis=0).astype(np.float64)                             # (C,)
        sx = Xf.sum(axis=0)
        sxx = (Xf * Xf).sum(axis=0)
        sy = g_lin[:, t * C:(t + 1) * C]                                 # (S, C)
        syy = g_sq[:, t * C:(t + 1) * C]
        sxy = g_lin[:, (T + t) * C:(T + t + 1) * C]
        with np.errstate(invalid="ignore", divide="ignore"):
            cxy = sxy - sx[None, :] * sy / n[None, :]
            cxx = (sxx - sx * sx / n)[None, :]
            cyy = syy - sy * sy / n[None, :]
            r = cxy / np.sqrt(cxx * cyy)
        r = np.abs(np.where(np.isfinite(r), r, 0.0))
        r[:, n < 3] = 0.0
        best = np.maximum(best, r)
    flat = best[np.isfinite(best)]
    _, p_floor, _ = permutation_null_resolution(nP, block)
    return {
        "p95": (float(np.percentile(flat, 95)) if flat.size else None),
        "p99": (float(np.percentile(flat, 99)) if flat.size else None),
        "block_length": block,
        "n_used": int(S),
        "p_resolution": (float(p_floor) if p_floor is not None else None),
        "best_by_shuffle": best,
    }


def _best_of_windows_null_auc(X, y_binary, *, n_perm, rng):
    """The distribution of the LARGEST distance from 0.5 over the ten lengths of signal, when the
    high-pain and low-pain labels carry no relationship to the band power.

    Same argument as the correlation reference above, and referenced to 0.5 throughout: what is
    maximised over the ten lengths is ``|area under the curve - 0.5|``, because a band that
    separates the two states in either direction is a finding and 0.5 is the value that means
    neither direction.

    The ranks of the band power do not change when the labels are shuffled, so the whole reference
    is one matrix product against the fixed ranks -- one product in total, with the ten lengths of
    signal stood side by side, for the reason and with the check described on the correlation
    reference above.
    """
    from .stats_utils import block_length_for, circular_block_perm_matrix
    T, P, C = X.shape
    yb = np.asarray(y_binary, dtype=np.float64)
    labelled = np.isfinite(yb)
    if labelled.sum() < 4 or int(n_perm) < 10:
        return {"p95": None, "p99": None, "block_length": None, "n_used": 0,
                "best_by_shuffle": None}
    yl = yb[labelled]
    Xl = X[:, labelled, :]
    nL = int(yl.size)
    if len(np.unique(yl)) < 2:
        return {"p95": None, "p99": None, "block_length": None, "n_used": 0,
                "best_by_shuffle": None}
    block = int(block_length_for(yl, nL))
    perm = circular_block_perm_matrix(nL, block, int(n_perm), rng)
    Yp = yl[perm]                                                        # (S, nL) still 0/1
    S = Yp.shape[0]
    best = np.zeros((S, C), dtype=np.float64)
    # ONE MATRIX PRODUCT FOR ALL TEN LENGTHS instead of twenty, for the reason written out on the
    # correlation reference above, and with the same requirement that the numbers be the same ones
    # and the same test asserting it.
    oks, rank_blocks = [], []
    for t in range(T):
        ok_t = np.isfinite(Xl[t])
        oks.append(ok_t)
        rank_blocks.append(np.where(ok_t, average_ranks_columns(Xl[t]), 0.0))   # (nL, C)
    rhs = np.concatenate([o.astype(np.float64) for o in oks] + rank_blocks, axis=1)
    g = Yp @ rhs                                                         # (S, 2*T*C)
    for t in range(T):
        ok = oks[t]
        n_pos = g[:, t * C:(t + 1) * C]                                  # (S, C)
        n_all = ok.sum(axis=0).astype(np.float64)[None, :]
        n_neg = n_all - n_pos
        rank_sum_pos = g[:, (T + t) * C:(T + t + 1) * C]                 # (S, C)
        with np.errstate(invalid="ignore", divide="ignore"):
            u = rank_sum_pos - n_pos * (n_pos + 1.0) / 2.0
            a = u / (n_pos * n_neg)
        d = np.abs(np.where(np.isfinite(a), a, AUC_NO_DISCRIMINATION) - AUC_NO_DISCRIMINATION)
        d[(n_pos < 1) | (n_neg < 1)] = 0.0
        best = np.maximum(best, d)
    flat = best[np.isfinite(best)]
    return {
        "p95": (float(np.percentile(flat, 95)) if flat.size else None),
        "p99": (float(np.percentile(flat, 99)) if flat.size else None),
        "block_length": block,
        "n_used": int(S),
        "best_by_shuffle": best,
    }


#: The sentence that goes in the panel itself, not only in a caption. The PI's requirement: a reader
#: must not be able to see the best cell without being told that it was chosen as the best of ten.
#: Condensed for open item 7's display cleanup (decision, 2026-09-09) -- same claim, fewer words.
BEST_OF_WINDOWS_OPTIMISM_NOTE = (
    "The value in each row is the LARGEST of the ten lengths of signal tried for that band -- "
    "chosen after seeing the results, so it runs larger than a fresh set of ratings would give. "
    "Its own p-value isn't a real probability; compare it to the shuffled best-of-ten value "
    "beside it, the level chance alone reaches under the same selection."
)

#: The sentence about what 0.5 means, carried with every area-under-the-curve row and figure.
#: Condensed for open item 7's display cleanup (decision, 2026-09-09) -- same claim, fewer words.
AUC_REFERENCE_NOTE = (
    "0.5, not 0, is what no discrimination between high and low pain looks like. An interval "
    "spanning 0.5 means the question is unsettled for that band, not that it carries nothing."
)

#: The direction-and-folding note, moved up next to AUC_REFERENCE_NOTE (open item 7, decision
#: 2026-09-09): both explain how to read the AUC quantity itself, so both belong with the other
#: non-negotiable interpretation notes rather than after the sweep's own mechanical bookkeeping.
AUC_DIRECTION_NOTE = (
    "The AUC heat map keeps direction: above 0.5 means higher power in high-pain reports, below "
    "means lower. The table's own number instead comes from a fitted logistic regression, which "
    "folds direction away and can't go below 0.5."
)


def _sweep_notes(requested, delivered, tiles, tile_s, n_times, n_centers, n_mad, o_scale,
                 n_excluded, n_perm, split_why, crosscheck=None, outlier_rule="none"):
    """The sentences the panel prints beside the grid, every one of them computed from what actually
    ran rather than written in advance.

    The first three are how to read the grid's own statistics -- the two the PI made non-negotiable,
    plus the direction/folding note, ordered together (open item 7, decision 2026-09-09) since a
    reader needs all three before the rest, which is mechanical bookkeeping about how the sweep ran.
    """
    notes = [BEST_OF_WINDOWS_OPTIMISM_NOTE, AUC_REFERENCE_NOTE, AUC_DIRECTION_NOTE]
    short = [(float(r), float(d)) for r, d in zip(requested, delivered) if abs(d - r) > 1e-9]
    if short:
        pairs = ", ".join(f"{r:g} s asked for, {d:g} s delivered" for r, d in short)
        notes.append(
            f"Length of signal is delivered in whole {tile_s:g} s pieces: {len(short)} of "
            f"{len(requested)} requested lengths could not be delivered exactly ({pairs}). "
            f"Every label shows the length delivered.")
    else:
        notes.append(f"Every requested length of signal is a whole number of {tile_s:g} s pieces, "
                     f"so each was delivered exactly.")
    notes.append(f"The grid's {n_times * n_centers} cells ({n_times} lengths x {n_centers} band "
                 f"centres, each {BAND_TIME_SWEEP_WIDTH_HZ:g} Hz wide, 1 Hz apart) overlap heavily "
                 f"and are not independent of each other.")
    if outlier_rule == "historical_99p5_ceiling_per_chunk":
        notes.append(f"{n_excluded} single {tile_s:g} s pieces were left out before anything was "
                     f"averaged, each one above this contact's own historical ceiling for that "
                     f"band -- the top 0.5% of everything this contact has ever recorded there, "
                     f"fixed in advance rather than judged from the data on screen. Each piece "
                     f"left out was replaced by the next closest clean one, so every cell still "
                     f"averages the number of pieces its row asks for.")
    elif n_mad > 0:
        notes.append(f"{n_excluded} measurements were excluded as outliers ({n_mad:g} median "
                     f"absolute deviations on the {o_scale} scale), per band and length.")
    else:
        notes.append("Outlier exclusion was switched off for this sweep; every measurement is "
                     "included.")
    notes.append(f"The shuffled reference is {n_perm} circular block shuffles of the pain scores "
                 f"(preserving day-to-day similarity), making the same best-of-ten choice each "
                 f"time, in either direction.")
    notes.append(f"High vs low pain: {split_why}.")
    if crosscheck and int(crosscheck.get("n_cells") or 0):
        n_ag = int(crosscheck.get("n_agree") or 0)
        n_all = int(crosscheck.get("n_cells") or 0)
        notes.append(
            f"A logistic regression fit at each of the {n_all} cells matched the folded ordering "
            f"in {n_ag} of them; a mismatch means that band's own fit runs against its power "
            f"values, which happens where the band carries little.")
    return notes


def _percentile_interval(draws, alpha=0.05):
    """The interval that holds the middle 1 - alpha of the resampled values, and the count of
    resamples that could be used."""
    d = np.asarray(draws, dtype=float)
    d = d[np.isfinite(d)]
    if d.size < 20:
        return None, None, int(d.size)
    lo = float(np.percentile(d, 100.0 * alpha / 2.0))
    hi = float(np.percentile(d, 100.0 * (1.0 - alpha / 2.0)))
    return lo, hi, int(d.size)


def _verdict_against(lo, hi, null_value, *, observed=None, shuffled_p95=None):
    """The three-word answer for one row, read against the value that means no relationship AND
    against the level the same best-of-ten choice reaches on shuffled pain scores.

    BOTH TESTS HAVE TO PASS FOR "established", and that is the point of this function. An interval
    that excludes the no-relationship value answers the question "is this particular cell's value
    different from no relationship"; it does NOT answer "is the LARGEST of ten values different from
    no relationship", which is the question the reported number actually poses, because the cell was
    chosen after seeing all ten. Before this gate existed the row could read ``established`` while
    its own figure headline said the value does not clear the shuffled best-of-ten level -- two
    surfaces contradicting each other about one number, which is exactly the class of error this
    section was asked to avoid.

    Never True or False, and never a fourth word. An interval that spans the no-relationship value,
    or a value that does not clear the shuffled level, is ``not_resolved``: the question was NOT
    settled. That is deliberately a different word from ``not_assessed``, which means no number
    could be produced at all.
    """
    if lo is None or hi is None or not (np.isfinite(lo) and np.isfinite(hi)):
        return BAND_PAIN_NOT_ASSESSED
    if not (lo > null_value or hi < null_value):
        return BAND_PAIN_NOT_RESOLVED
    if observed is not None and shuffled_p95 is not None:
        try:
            if abs(float(observed) - float(null_value)) <= abs(float(shuffled_p95)
                                                               - float(null_value)):
                return BAND_PAIN_NOT_RESOLVED
        except (TypeError, ValueError):
            pass
    return BAND_PAIN_ESTABLISHED


def _apply_family_wise_correction(rows):
    """Decision 63: Benjamini-Hochberg across one grid's own band centres, in place.

    `rows` is `best_correlation_rows` or `best_auc_rows`, one entry per band centre, each already
    carrying `p_selection_aware` (the permutation-based p-value that corrects for choosing the best
    of ten lengths of signal at that one centre). This adds two fields per row: the corrected
    q-value, and whether it clears `BAND_TIME_SWEEP_FAMILY_WISE_Q` -- both computed ONLY from this
    grid's own rows, never pooled with any other grid or any other channel's rows. A row with no
    `p_selection_aware` (nothing was measured for that centre) gets both fields as `None`, matching
    how every other "not assessed" case on this page is represented -- absence of evidence, not a
    negative finding.
    """
    from .stats_utils import bh_fdr
    p = np.array([r.get("p_selection_aware") for r in rows], dtype=float)
    q = bh_fdr(p)
    for row, qi in zip(rows, q):
        finite = np.isfinite(qi)
        row["family_wise_q_8_to_30hz"] = (float(qi) if finite else None)
        row["family_wise_significant_8_to_30hz"] = (
            bool(qi < BAND_TIME_SWEEP_FAMILY_WISE_Q) if finite else None)


def _best_rows_correlation(corr, corr_n, X, pain, centers, requested, delivered, tiles, null,
                           *, band_width_hz, n_boot, rng, power_feature, channel):
    """One row per band centre: the strongest correlation any length of signal produced for that
    band, which length produced it, and how to read it.

    The strongest is chosen by SIZE IGNORING SIGN, because a band whose power falls as pain rises
    tracks pain just as informatively as one whose power rises, and the sign is reported separately
    so the direction is never lost.
    """
    T, C = corr.shape
    y = np.asarray(pain, dtype=np.float64)
    best_shuf = null.get("best_by_shuffle")
    rows = []
    with np.errstate(invalid="ignore"):
        mag = np.abs(corr)
    for c in range(C):
        col = mag[:, c]
        header = _band_row_header(channel if channel is not None else "", float(centers[c]),
                                  band_width_hz)
        if not np.isfinite(col).any():
            row = dict(header)
            row.update(_blank_band_answer(
                "no length of signal produced a usable correlation for this band, so nothing was "
                "measured here. This is an absent measurement, not a correlation of zero",
                pearson_r=None, no_relationship_value=CORRELATION_NO_RELATIONSHIP,
                power_feature=power_feature))
            rows.append(row)
            continue
        t = int(np.nanargmax(col))
        r_obs = float(corr[t, c])
        n_obs = int(corr_n[t, c])
        x = X[t, :, c]
        m = np.isfinite(x) & np.isfinite(y)
        # An interval by resampling whole pain reports. Each report is one row here, so resampling
        # rows IS resampling reports and the interval means what it says.
        boot_lo = boot_hi = None
        n_res = 0
        if int(m.sum()) >= 8:
            idx = np.where(m)[0]
            picks = rng.integers(0, idx.size, size=(int(n_boot), idx.size))
            xb = x[idx][picks]
            yb = y[idx][picks]
            # THE SAME SUBTRACTIONS, THE SAME PRODUCTS AND THE SAME ROW SUMS as the plain form
            # (mean, then difference, then three sums along the row), only with the differences
            # written back over the drawn values and one buffer reused for all three products
            # instead of five new arrays of a thousand resamples by a few hundred pain reports.
            # Correlating real-valued band powers DOES round, unlike the whole-number counting the
            # high-pain-against-low-pain resample does, so the order of every addition here is left
            # exactly as it was; only the allocations are gone.
            with np.errstate(invalid="ignore", divide="ignore"):
                xb -= xb.mean(axis=1, keepdims=True)
                yb -= yb.mean(axis=1, keepdims=True)
                prod = xb * yb
                sxy = prod.sum(axis=1)
                np.multiply(xb, xb, out=prod)
                sxx = prod.sum(axis=1)
                np.multiply(yb, yb, out=prod)
                syy = prod.sum(axis=1)
                rb = sxy / np.sqrt(sxx * syy)
            boot_lo, boot_hi, n_res = _percentile_interval(rb)
        shuf_p95 = shuf_p99 = None
        p_sel = None
        if best_shuf is not None and best_shuf.shape[1] == C:
            colshuf = best_shuf[:, c]
            colshuf = colshuf[np.isfinite(colshuf)]
            if colshuf.size:
                shuf_p95 = float(np.percentile(colshuf, 95))
                shuf_p99 = float(np.percentile(colshuf, 99))
                p_sel = float((int((colshuf >= abs(r_obs)).sum()) + 1) / (colshuf.size + 1))
        row = dict(header)
        row.update({
            "pearson_r": r_obs,
            "pearson_r_abs": float(abs(r_obs)),
            "direction": ("band power rises as pain rises" if r_obs > 0
                          else "band power falls as pain rises"),
            "no_relationship_value": CORRELATION_NO_RELATIONSHIP,
            "integration_seconds_requested": float(requested[t]),
            "integration_seconds_delivered": float(delivered[t]),
            "integration_tiles": int(tiles[t]),
            "n_pain_reports": n_obs,
            "pearson_r_low": boot_lo,
            "pearson_r_high": boot_hi,
            "n_resamples_used": int(n_res),
            "answer": _verdict_against(boot_lo, boot_hi, CORRELATION_NO_RELATIONSHIP,
                                       observed=r_obs, shuffled_p95=shuf_p95),
            "chosen_as_best_of_n_windows": int(T),
            "shuffled_best_of_windows_p95": shuf_p95,
            "shuffled_best_of_windows_p99": shuf_p99,
            "p_selection_aware": p_sel,
            "beats_shuffled_best_of_windows_p95": (None if shuf_p95 is None
                                                   else bool(abs(r_obs) > shuf_p95)),
            "power_feature": str(power_feature),
            "why": _corr_row_sentence(
                _verdict_against(boot_lo, boot_hi, CORRELATION_NO_RELATIONSHIP,
                                 observed=r_obs, shuffled_p95=shuf_p95),
                r_obs, boot_lo, boot_hi, float(delivered[t]), int(T), shuf_p95),
        })
        rows.append(row)
    return rows


def _best_rows_auc(auc, auc_pos, auc_neg, X, y_bin, centers, requested, delivered, tiles, null,
                   *, band_width_hz, n_boot, rng, power_feature, channel, split_why,
                   low_cut, high_cut):
    """One row per band centre: the length of signal at which that band told high-pain reports from
    low-pain ones best, and how to read it.

    THE BEST IS THE FURTHEST FROM 0.5, in either direction, because a band whose power is LOWER on
    high-pain reports separates the two states exactly as well as one whose power is higher. The
    value itself is reported unfolded, so its direction is visible, and ``no_relationship_value`` is
    0.5 on every row.
    """
    T, C = auc.shape
    yb = np.asarray(y_bin, dtype=float)
    best_shuf = null.get("best_by_shuffle")
    rows = []
    with np.errstate(invalid="ignore"):
        dist = np.abs(auc - AUC_NO_DISCRIMINATION)
    for c in range(C):
        col = dist[:, c]
        header = _band_row_header(channel if channel is not None else "", float(centers[c]),
                                  band_width_hz)
        if not np.isfinite(col).any():
            row = dict(header)
            row.update(_blank_band_answer(
                "no length of signal produced a usable value for this band, so how well it tells "
                "high pain from low pain has not been worked out. This is an absent measurement, "
                "not a measurement showing no discrimination",
                auc=None, no_relationship_value=AUC_NO_DISCRIMINATION,
                power_feature=power_feature))
            row["pain_split_rule"] = split_why
            rows.append(row)
            continue
        t = int(np.nanargmax(col))
        a_obs = float(auc[t, c])
        x = X[t, :, c]
        m = np.isfinite(x) & np.isfinite(yb)
        boot_lo = boot_hi = None
        n_res = 0
        if int(m.sum()) >= 8 and len(np.unique(yb[m])) == 2:
            idx = np.where(m)[0]
            picks = rng.integers(0, idx.size, size=(int(n_boot), idx.size))
            # THE ORIENTATION IS FIXED ONCE, ON THE WHOLE SAMPLE, AND NEVER RE-CHOSEN INSIDE A
            # RESAMPLE. Re-folding each resample would push every one of them to or above 0.5 and
            # produce an interval that cannot include 0.5 however little the band carries, which is
            # the audited convention `_weighted_auc_matrix` was written for. Fixing it instead lets
            # a resample fall below 0.5, which is what makes an interval spanning 0.5 mean
            # something.
            #
            # The drawn row numbers go straight into the counting, rather than first being turned
            # into a thousand-by-a-few-hundred matrix of multiplicities and then handed to
            # `_weighted_auc_matrix`. The two return the same doubles, bit for bit, because every
            # step is whole-number arithmetic small enough for a double to hold exactly; the
            # argument is written out on `bootstrap_auc_from_row_picks` and there is a test that
            # asserts the equality on constructed cases including ties, a constant band and missing
            # measurements. THE DRAW ITSELF IS UNCHANGED -- same generator, same call, same size,
            # same place in the order -- so every resample is the same resample it was before.
            ab = bootstrap_auc_from_row_picks(x[idx], yb[idx], picks)
            boot_lo, boot_hi, n_res = _percentile_interval(ab)
        shuf_p95 = shuf_p99 = None
        p_sel = None
        if best_shuf is not None and best_shuf.shape[1] == C:
            colshuf = best_shuf[:, c]
            colshuf = colshuf[np.isfinite(colshuf)]
            if colshuf.size:
                shuf_p95 = float(AUC_NO_DISCRIMINATION + np.percentile(colshuf, 95))
                shuf_p99 = float(AUC_NO_DISCRIMINATION + np.percentile(colshuf, 99))
                p_sel = float((int((colshuf >= abs(a_obs - AUC_NO_DISCRIMINATION)).sum()) + 1)
                              / (colshuf.size + 1))
        verdict = _verdict_against(boot_lo, boot_hi, AUC_NO_DISCRIMINATION,
                                   observed=a_obs, shuffled_p95=shuf_p95)
        row = dict(header)
        row.update({
            "auc": a_obs,
            "auc_direction_folded": float(max(a_obs, 1.0 - a_obs)),
            "auc_direction_folded_is": ("the value a fitted one-predictor logistic regression "
                                        "returns in sample; it cannot fall below 0.5"),
            "auc_distance_from_no_discrimination": float(abs(a_obs - AUC_NO_DISCRIMINATION)),
            "direction": ("band power is higher on high-pain reports" if a_obs > AUC_NO_DISCRIMINATION
                          else "band power is lower on high-pain reports"),
            "no_relationship_value": AUC_NO_DISCRIMINATION,
            "integration_seconds_requested": float(requested[t]),
            "integration_seconds_delivered": float(delivered[t]),
            "integration_tiles": int(tiles[t]),
            "n_pain_reports": int(auc_pos[t, c] + auc_neg[t, c]),
            "n_high_pain_reports": int(auc_pos[t, c]),
            "n_low_pain_reports": int(auc_neg[t, c]),
            "auc_low": boot_lo,
            "auc_high": boot_hi,
            "n_resamples_used": int(n_res),
            "answer": verdict,
            "interval_spans_no_discrimination": (
                None if (boot_lo is None or boot_hi is None)
                else bool(boot_lo <= AUC_NO_DISCRIMINATION <= boot_hi)),
            "chosen_as_best_of_n_windows": int(T),
            "shuffled_best_of_windows_p95": shuf_p95,
            "shuffled_best_of_windows_p99": shuf_p99,
            "p_selection_aware": p_sel,
            "beats_shuffled_best_of_windows_p95": (
                None if shuf_p95 is None
                else bool(abs(a_obs - AUC_NO_DISCRIMINATION)
                          > shuf_p95 - AUC_NO_DISCRIMINATION)),
            "pain_split_rule": split_why,
            "pain_low_cut": (float(low_cut) if low_cut is not None else None),
            "pain_high_cut": (float(high_cut) if high_cut is not None else None),
            "power_feature": str(power_feature),
            "_grid_time_index": float(requested[t]),
            "_grid_center_index": int(c),
            "why": _auc_row_sentence(verdict, a_obs, boot_lo, boot_hi, float(delivered[t]),
                                     int(T), shuffled_p95=shuf_p95),
        })
        rows.append(row)
    return rows


def _corr_row_sentence(verdict, r_value, lo, hi, delivered_s, n_windows, shuffled_p95=None):
    """The sentence for one row of the correlation table, naming which of the two tests it failed.

    Same two-test structure as the high-pain-against-low-pain table: the interval has to stay off 0
    AND the value has to be larger in size than what the same best-of-ten choice reaches on shuffled
    pain scores. A row that fails either one says the question was not settled, never that the band
    carries nothing.
    """
    at = (f"the strongest of {n_windows} lengths of signal for this band, reached when one "
          f"measurement averaged {delivered_s:g} s of recording")
    if verdict == BAND_PAIN_ESTABLISHED:
        tail = (f" and larger in size than the {float(shuffled_p95):.3f} the same choice reaches on "
                f"shuffled pain scores" if shuffled_p95 is not None else "")
        return (f"the interval from {lo:.3f} to {hi:.3f} stays wholly off 0{tail}, so this band's "
                f"power does track this pain score for this patient; {at}")
    if verdict == BAND_PAIN_NOT_RESOLVED:
        if lo is not None and hi is not None and lo <= 0.0 <= hi:
            return (f"the interval from {lo:.3f} to {hi:.3f} includes 0, so whether this band's "
                    f"power tracks this pain score was NOT SETTLED; {at}")
        ref = (f"{float(shuffled_p95):.3f}" if shuffled_p95 is not None else "the shuffled level")
        return (f"the interval from {lo:.3f} to {hi:.3f} does stay off 0, but the value is no "
                f"larger in size than {ref}, which is what the SAME best-of-ten choice reaches on "
                f"shuffled pain scores, so once that choice is accounted for nothing was SETTLED "
                f"here; {at}")
    return f"an interval could not be formed, so nothing was established either way; {at}"


def _auc_row_sentence(verdict, auc_value, lo, hi, delivered_s, n_windows, shuffled_p95=None):
    """The sentence for one row of the high-pain-against-low-pain table, written so that an
    unsettled row cannot read as a negative result and so that it names WHICH of the two tests the
    row failed.

    The three answers get three different sentences on purpose, and ``not_resolved`` gets two
    versions of its own: one for an interval that includes 0.5, and one for a value that clears 0.5
    but does not clear the level the same best-of-ten choice reaches on shuffled pain scores.
    Neither of them ever says the band carries nothing.
    """
    at = (f"reached when one measurement averaged {delivered_s:g} s of recording, chosen as the "
          f"furthest from 0.5 of {n_windows} lengths of signal tried")
    if verdict == BAND_PAIN_ESTABLISHED:
        side = "above" if auc_value > AUC_NO_DISCRIMINATION else "below"
        which = "higher" if auc_value > AUC_NO_DISCRIMINATION else "lower"
        tail = ""
        if shuffled_p95 is not None:
            tail = (f", and it is further from 0.5 than the {float(shuffled_p95):.3f} the same "
                    f"best-of-ten choice reaches on shuffled pain scores")
        return (f"the interval from {lo:.3f} to {hi:.3f} stays wholly {side} 0.5{tail}, so this "
                f"band does separate high-pain reports from low-pain ones for this patient, with "
                f"the band power {which} on the high-pain ones; {at}")
    if verdict == BAND_PAIN_NOT_RESOLVED:
        if lo is not None and hi is not None and lo <= AUC_NO_DISCRIMINATION <= hi:
            return (f"the interval from {lo:.3f} to {hi:.3f} includes 0.5, so whether this band "
                    f"separates high-pain reports from low-pain ones was NOT SETTLED. That is an "
                    f"unsettled question, not a finding that the band carries nothing; {at}")
        ref = (f"{float(shuffled_p95):.3f}" if shuffled_p95 is not None else "the shuffled level")
        return (f"the interval from {lo:.3f} to {hi:.3f} does stay off 0.5, but the value is no "
                f"further from 0.5 than {ref}, which is what the SAME best-of-ten choice reaches on "
                f"shuffled pain scores, so once that choice is accounted for nothing was SETTLED "
                f"here. That is an unsettled question, not a finding that the band carries nothing; "
                f"{at}")
    return f"an interval could not be formed, so nothing was established either way; {at}"


def logistic_fit_crosscheck(X_by_time, y_binary, best_rows, *, feature_scale="log"):
    """Fit the real logistic regression at each band's WINNING cell and report whether its own area
    under the curve matches the ordering the grid was built from.

    WHY ONLY THE WINNING CELLS, with the costs measured rather than guessed. Timed warm (that is,
    after the first fit, so the one-off cost of loading the solver is not counted against either
    route): fitting all 220 cells of a grid takes about 168 ms, fitting only the 22 cells that reach
    the summary table takes about 17 ms, and the matrix route that actually fills the grid computes
    the same 220 cells in about 0.7 ms. So the check on the 22 reported cells costs a tenth of the
    full-grid check while covering every number the table shows, and the matrix route is roughly 230
    times faster than fitting the grid it replaces. On the live RCS08 record the same check came out
    at 14 to 22 ms per contact pair. An earlier revision of this docstring said the 22-cell check
    cost a twentieth of the full-grid one; that was wrong, and the first measurement of it (387 ms)
    was itself inflated because it included loading the solver.

    The count of cells where the fitted straight line points against the ordering is
    reported rather than hidden, because that disagreement is itself informative: it marks a band
    where a straight-line fit on that band's power disagrees with the order of its own values, which
    happens where the band carries little and the values are skewed.

    Returns ``{"n_cells", "n_agree", "n_disagree", "max_abs_difference", "fitted_by_center_hz",
    "feature_scale", "seconds"}``.
    """
    import time as _t
    t0 = _t.perf_counter()
    out = {"n_cells": 0, "n_agree": 0, "n_disagree": 0, "max_abs_difference": None,
           "n_rows_dropped_by_the_transform": 0, "fitted_by_center_hz": {},
           "feature_scale": str(feature_scale), "seconds": 0.0}
    y = np.asarray(y_binary, dtype=float)
    worst = 0.0
    for row in (best_rows or []):
        a = row.get("auc")
        if a is None or not np.isfinite(float(a)):
            continue
        key = row.get("_grid_time_index")
        c = row.get("_grid_center_index")
        if key is None or c is None:
            continue
        X = X_by_time.get(key)
        if X is None:
            continue
        col = X[:, [int(c)]]
        got = logistic_auc_columns_fitted(col, y, feature_scale=feature_scale)
        fitted = float(got["auc"][0]) if np.isfinite(got["auc"][0]) else None
        # COMPARED ON THE SAME ROWS THE FIT USED, which is not automatic. Fitting on the logarithm
        # of the band power drops any row whose power is not strictly positive, and a Percept LSB
        # band power can be exactly zero on an empty or saturated window. Comparing the fit against
        # the grid's value, which was computed on the raw scale and so kept those rows, made the two
        # differ by up to 0.032 on the live record purely because they were computed on different
        # sets of pain reports. The ordering is therefore recomputed here on the same transformed
        # column, and the number of rows the transform dropped is reported.
        if str(feature_scale) == "log":
            with np.errstate(divide="ignore", invalid="ignore"):
                col_cmp = np.log10(np.where(col > 0, col, np.nan))
        else:
            col_cmp = col
        n_dropped = int((np.isfinite(col) & ~np.isfinite(col_cmp)).sum())
        unfolded_same_rows = float(rank_auc_columns(col_cmp, y)["auc"][0])
        folded = (float(max(unfolded_same_rows, 1.0 - unfolded_same_rows))
                  if np.isfinite(unfolded_same_rows) else float(max(float(a), 1.0 - float(a))))
        out["n_rows_dropped_by_the_transform"] = (
            out.get("n_rows_dropped_by_the_transform", 0) + n_dropped)
        out["n_cells"] += 1
        if fitted is None:
            continue
        d = abs(fitted - folded)
        worst = max(worst, d)
        if d <= 1e-9:
            out["n_agree"] += 1
        else:
            out["n_disagree"] += 1
        out["fitted_by_center_hz"][f"{float(row['band_center_hz']):g}"] = {
            "auc_fitted_logistic": fitted,
            "auc_direction_folded": folded,
            "auc_direction_folded_on_the_grid_rows": float(max(float(a), 1.0 - float(a))),
            "n_rows_dropped_by_the_transform": n_dropped,
            "slope": (float(got["slope"][0]) if np.isfinite(got["slope"][0]) else None),
            "matches_the_ordering": bool(d <= 1e-9),
        }
    out["max_abs_difference"] = (float(worst) if out["n_cells"] else None)
    out["seconds"] = float(_t.perf_counter() - t0)
    return out


def band_time_sweep_tables(sweep):
    """The two summary tables and the full grid, as data frames a reader can save and open.

    Returns ``(correlation_table, auc_table, grid_table)``. The first two are one row per band
    centre -- the two matrices the PI asked for -- each carrying the best value, the length of
    signal that produced it, the count behind it, the interval, and the shuffled best-of-ten
    reference. The third is one row per cell of the whole grid, because the shape of the surface is
    what the panel is for and a reader who wants to check a sliders' worth of the surface needs the
    cells and not only the winners.
    """
    corr = pd.DataFrame(sweep.get("best_correlation_rows") or [])
    auc = pd.DataFrame(sweep.get("best_auc_rows") or [])
    if len(corr):
        corr = _order_export_columns(corr, [
            "answer", "pearson_r", "pearson_r_abs", "direction",
            "integration_seconds_delivered", "integration_seconds_requested", "integration_tiles",
            "pearson_r_low", "pearson_r_high", "no_relationship_value",
            "chosen_as_best_of_n_windows", "shuffled_best_of_windows_p95", "p_selection_aware",
            "beats_shuffled_best_of_windows_p95", "n_pain_reports", "n_resamples_used",
            "power_feature", "why"])
    if len(auc):
        auc = _order_export_columns(auc, [
            "answer", "auc", "auc_direction_folded",
            "auc_distance_from_no_discrimination", "direction",
            "integration_seconds_delivered", "integration_seconds_requested", "integration_tiles",
            "auc_low", "auc_high", "no_relationship_value", "interval_spans_no_discrimination",
            "chosen_as_best_of_n_windows", "shuffled_best_of_windows_p95", "p_selection_aware",
            "beats_shuffled_best_of_windows_p95", "n_pain_reports", "n_high_pain_reports",
            "n_low_pain_reports", "pain_split_rule", "power_feature", "why"])
    centers = list(sweep.get("center_freqs_hz") or [])
    req = list(sweep.get("integration_seconds_requested") or [])
    deliv = list(sweep.get("integration_seconds_delivered") or [])
    tiles = list(sweep.get("integration_tiles") or [])
    cg = sweep.get("correlation_grid") or []
    ag = sweep.get("auc_grid") or []
    fg = sweep.get("auc_direction_folded_grid") or []
    ng = sweep.get("n_grid") or []
    inside = list(sweep.get("band_fully_inside_8_to_30_hz") or [])
    w = float(sweep.get("band_width_hz") or BAND_TIME_SWEEP_WIDTH_HZ)
    grid_rows = []
    for t in range(len(req)):
        for c in range(len(centers)):
            grid_rows.append({
                "channel": sweep.get("channel"),
                "band_center_hz": float(centers[c]),
                "band_low_hz": float(centers[c]) - w / 2.0,
                "band_high_hz": float(centers[c]) + w / 2.0,
                "band_width_hz": w,
                "band_fully_inside_8_to_30_hz": (bool(inside[c]) if c < len(inside) else None),
                "integration_seconds_requested": float(req[t]),
                "integration_seconds_delivered": (float(deliv[t]) if t < len(deliv) else None),
                "integration_tiles": (int(tiles[t]) if t < len(tiles) else None),
                "pearson_r": (cg[t][c] if t < len(cg) and c < len(cg[t]) else None),
                "auc": (ag[t][c] if t < len(ag) and c < len(ag[t]) else None),
                "auc_direction_folded": (fg[t][c] if t < len(fg) and c < len(fg[t]) else None),
                "auc_no_relationship_value": AUC_NO_DISCRIMINATION,
                "correlation_no_relationship_value": CORRELATION_NO_RELATIONSHIP,
                "n_pain_reports": (ng[t][c] if t < len(ng) and c < len(ng[t]) else None),
                "power_feature": sweep.get("power_feature"),
                "metric_key": sweep.get("metric_key"),
            })
    return corr, auc, pd.DataFrame(grid_rows)


def _sweep_headline_correlation(sweep):
    """The correlation figure's headline, computed from the numbers in the same pass that draws it.

    Never asserted. It names the band and the length of signal that came out strongest, states the
    value, and says in the same breath whether that value clears the level the same best-of-ten
    choice reaches on shuffled pain scores -- which is the only way the number can be read.
    """
    rows = [r for r in (sweep.get("best_correlation_rows") or [])
            if r.get("pearson_r") is not None]
    if not rows:
        return ("No band centre produced a usable correlation with this pain score at any length "
                "of signal")
    top = max(rows, key=lambda r: abs(float(r["pearson_r"])))
    r = float(top["pearson_r"])
    fc = float(top["band_center_hz"])
    s = float(top["integration_seconds_delivered"])
    n = int(top.get("n_pain_reports") or 0)
    p95 = top.get("shuffled_best_of_windows_p95")
    lead = (f"Strongest tracking is {r:+.2f} at {fc:g} Hz when one measurement averages {s:g} s of "
            f"recording, on {n} pain reports")
    if p95 is None:
        return lead + "; no shuffled reference could be built, so it cannot yet be read"
    if abs(r) > float(p95):
        return (lead + f"; that exceeds the {float(p95):.2f} the same best-of-ten choice reaches on "
                f"19 of 20 shuffles")
    return (lead + f"; the same best-of-ten choice reaches {float(p95):.2f} on shuffled pain "
            f"scores, so this is NOT above chance")


def _sweep_headline_auc(sweep):
    """The classification figure's headline, computed from the numbers, and referenced to 0.5.

    An interval that spans 0.5 is reported as unsettled in the headline itself, so a reader who only
    ever sees the headline cannot take it for a negative result.
    """
    rows = [r for r in (sweep.get("best_auc_rows") or []) if r.get("auc") is not None]
    if not rows:
        return ("No band centre produced a usable value for telling high-pain reports from low-pain "
                "ones at any length of signal")
    top = max(rows, key=lambda r: abs(float(r["auc"]) - AUC_NO_DISCRIMINATION))
    a = float(top["auc"])
    fc = float(top["band_center_hz"])
    s = float(top["integration_seconds_delivered"])
    est = sum(1 for r in rows if r.get("answer") == BAND_PAIN_ESTABLISHED)
    unres = sum(1 for r in rows if r.get("answer") == BAND_PAIN_NOT_RESOLVED)
    lead = (f"Furthest from 0.5 is {a:.2f} at {fc:g} Hz when one measurement averages {s:g} s of "
            f"recording")
    p95 = top.get("shuffled_best_of_windows_p95")
    if p95 is not None:
        lead += (f", against {float(p95):.2f} for the same best-of-ten choice on shuffled pain "
                 f"scores")
    if est:
        return (lead + f"; {est} of {len(rows)} band centres have an interval that stays off 0.5 "
                f"and {unres} do not settle the question")
    return (lead + f"; every one of the {len(rows)} band centres has an interval that includes 0.5, "
            f"so none of them settles the question either way")


def band_time_sweep_figures(sweep):
    """The two heat maps the browser draws: band centre against length of signal, one for the
    correlation and one for telling high pain from low pain.

    ONE CONTEXT, AND NOTHING IS RENDERED HERE. The module returns Plotly figure descriptions as
    plain data and the browser draws them; nothing on the server needs a headless browser. Both
    figures take their headline and every piece of their text from ``sweep``, computed in this pass,
    so a figure cannot carry a claim the numbers do not support.

    THE TWO COLOUR SCALES ARE NOT INTERCHANGEABLE. The correlation scale is centred on 0 and the
    classification scale is centred on 0.5, because those are the two values that mean no
    relationship for the two quantities. A diverging scale centred anywhere else on the
    classification figure would make a band that discriminates nothing look like a result.
    """
    centers = [float(c) for c in (sweep.get("center_freqs_hz") or [])]
    deliv = [float(s) for s in (sweep.get("integration_seconds_delivered") or [])]
    req = [float(s) for s in (sweep.get("integration_seconds_requested") or [])]
    cg = sweep.get("correlation_grid") or []
    ag = sweep.get("auc_grid") or []
    ng = sweep.get("n_grid") or []
    if not centers or not deliv:
        return {}
    ylab = [(f"{d:g} s" if abs(d - r) < 1e-9 else f"{d:g} s (asked {r:g} s)")
            for d, r in zip(deliv, req)]
    small = len(centers) * len(deliv) <= 320       # small enough to print every value and read it
    notes = list(sweep.get("notes") or [])
    footer = "  ".join(notes[:2])
    inside = list(sweep.get("band_fully_inside_8_to_30_hz") or [])
    outside = [centers[i] for i in range(len(centers))
               if i < len(inside) and not inside[i]]
    half = float(sweep.get("band_width_hz") or BAND_TIME_SWEEP_WIDTH_HZ) / 2.0

    def _hover(grid, name, null_value):
        return [[(f"{name} {grid[t][c]:.3f}<br>band {centers[c]:g} Hz "
                  f"({centers[c] - half:g}-{centers[c] + half:g} Hz)<br>"
                  f"{deliv[t]:g} s of recording per measurement<br>"
                  f"{(ng[t][c] if t < len(ng) and c < len(ng[t]) else 0)} pain reports<br>"
                  f"no relationship = {null_value:g}")
                 if (t < len(grid) and c < len(grid[t]) and grid[t][c] is not None)
                 else "not measured"
                 for c in range(len(centers))] for t in range(len(deliv))]

    def _shapes():
        """Faint marks over the band centres whose 5 Hz window reaches outside the 8-30 Hz range the
        firmware can place an adaptive sensing band in. Drawn under the data so printed values stay
        readable."""
        out = []
        for fc in outside:
            out.append({"type": "rect", "xref": "x", "yref": "paper",
                        "x0": fc - 0.5, "x1": fc + 0.5, "y0": 0, "y1": 1,
                        "fillcolor": "rgba(120,120,120,0.14)", "line": {"width": 0},
                        "layer": "below"})
        return out

    def _figure(grid, title, colorscale, zmid, zmin, zmax, fmt, name, null_value, cbtitle):
        return {
            "data": [{
                "type": "heatmap",
                "x": centers,
                "y": ylab,
                "z": grid,
                # The value is printed in every cell only while the grid is small enough for the
                # printed numbers to be readable; above that the keys are left out entirely rather
                # than set to nothing, which Plotly reads as an instruction it cannot follow.
                **({"text": [[("" if (t >= len(grid) or c >= len(grid[t])
                                      or grid[t][c] is None) else format(grid[t][c], fmt))
                              for c in range(len(centers))] for t in range(len(deliv))],
                    "texttemplate": "%{text}",
                    "textfont": {"size": 8}} if small else {}),
                "customdata": _hover(grid, name, null_value),
                "hovertemplate": "%{customdata}<extra></extra>",
                "colorscale": colorscale,
                "zmid": zmid, "zmin": zmin, "zmax": zmax,
                "colorbar": {"title": {"text": cbtitle, "side": "right"}, "thickness": 14},
                "xgap": 1, "ygap": 1,
            }],
            "layout": {
                "title": {"text": title, "font": {"size": 15}, "x": 0.01, "xanchor": "left"},
                "xaxis": {"title": {"text": "Band centre (Hz), each band 5 Hz wide"},
                          "dtick": 2, "tickmode": "linear", "showgrid": False},
                "yaxis": {"title": {"text": "Seconds of recording averaged into one measurement"},
                          "type": "category", "showgrid": False},
                "shapes": _shapes(),
                "annotations": [{
                    "text": footer, "xref": "paper", "yref": "paper", "x": 0, "y": -0.30,
                    "xanchor": "left", "yanchor": "top", "showarrow": False,
                    "align": "left", "font": {"size": 9.5, "color": "#444"},
                }],
                "margin": {"l": 130, "r": 20, "t": 46, "b": 130},
                "height": 420,
                "uirevision": "band-time-sweep",
            },
        }

    finite_c = [v for row in cg for v in row if v is not None and np.isfinite(v)]
    cmax = max(0.1, min(1.0, max((abs(v) for v in finite_c), default=0.1)))
    finite_a = [v for row in ag for v in row if v is not None and np.isfinite(v)]
    amax = max(0.05, min(0.5, max((abs(v - AUC_NO_DISCRIMINATION) for v in finite_a), default=0.05)))
    out = {}
    if cg:
        out["correlation"] = _figure(
            cg, _sweep_headline_correlation(sweep), "RdBu", 0.0, -cmax, cmax, ".2f",
            "correlation", CORRELATION_NO_RELATIONSHIP,
            "Correlation<br>(0 = none)")
    if ag:
        out["auc"] = _figure(
            ag, _sweep_headline_auc(sweep), "RdBu",
            AUC_NO_DISCRIMINATION,
            AUC_NO_DISCRIMINATION - amax, AUC_NO_DISCRIMINATION + amax, ".2f",
            "area under the curve", AUC_NO_DISCRIMINATION,
            "High vs low pain<br>(0.5 = none)")
    return out
