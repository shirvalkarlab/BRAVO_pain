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
            "significant": sig,
            "peaks": peaks,
            "peak_scatter": peak_scatter,
        })
    return {"freqs": [float(x) for x in f], "channels": channels,
            "transform": td_detail.get("transform", "log"),
            "p_significant": p_significant, "q_significant": q_significant,
            "significance_method": "BH-FDR over displayed channel x freq family"}


# --- Exploratory spectral feature-importance scan (DESIGN §8b) -------------------------------
def _binarize_labels(values, strategy="tertile", low_pct=33.3333, high_pct=66.6667,
                     pain_cutoff=None, finite_mask=None):
    """Binary 0/1 label (NaN for the excluded middle) from a 1-D continuous PRO array.

    Mirrors adapter._threshold_pain_level but operates on a flat array (one value per matched
    neural sample, NOT daily-broadcast — the matching already gave us one PRO per session). The cut
    is computed on the FINITE values present:
      * "tertile"/"percentile": <= low_pct quantile -> 0, >= high_pct quantile -> 1, middle -> NaN
      * "median": >= median -> 1 else 0
      * "cutoff": >= pain_cutoff (default = median) -> 1 else 0
      * "kmeans": 2-cluster split on the 1-D values (>= cluster midpoint -> 1)

    `finite_mask` (optional bool array, same shape) restricts BOTH the cut reference and the output
    to a subset of rows — used by the glmer/stim-stability click-validate path to binarize on a
    single channel's own labels (PARITY audit §6b), reproducing the offline per-channel cut. Rows
    outside the mask stay NaN. When None, the cut is global over all finite values (scan behaviour).
    """
    v = np.asarray(values, dtype=float)
    out = np.full(v.shape, np.nan)
    fin = np.isfinite(v)
    if finite_mask is not None:
        fin = fin & np.asarray(finite_mask, dtype=bool)
    ref = v[fin]
    if ref.size == 0:
        return out
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


def _spectral_cv_threads():
    """Worker count for the per-band CV-AUC/logit-p parallel pass in spectral_feature_importance.

    DEFAULTS TO 1 (serial) on purpose. spectral_feature_importance already runs as ONE task inside the
    analytics `td_tasks` ThreadPool, CONCURRENT with the powerdomain pool's threshold work, and the
    per-band fits are sklearn LogisticRegression + StratifiedGroupKFold — GIL- and BLAS-bound. With the
    outer pools already saturating the cores, an inner thread pool here adds scheduling overhead for no
    wall-clock gain (measured: 46.8 s serial vs 47.8 s at 16 threads end-to-end; per-band AUC/n/p are
    bit-identical either way — the fixed-seed CV is order-independent). The parallel path is kept,
    fully equivalence-tested, behind an explicit opt-in so it can be switched on if the outer threading
    model changes (e.g. a process-pool refactor that frees the GIL): set BRAVO_SPECTRAL_CV_THREADS=N
    (or the shared BRAVO_BIOMARKER_THREADS=N). Returns >= 1.
    """
    import os as _os
    for var in ("BRAVO_SPECTRAL_CV_THREADS", "BRAVO_BIOMARKER_THREADS"):
        try:
            v = int(_os.environ.get(var, "0"))
            if v > 0:
                return v
        except (TypeError, ValueError):
            pass
    return 1


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


def spectral_feature_importance(td_detail, *, strategy="tertile", low_pct=33.3333,
                                high_pct=66.6667, pain_cutoff=None, band_width_hz=5.0,
                                step_hz=1.0, fmax=100.0, adaptive_band=(8.0, 30.0),
                                region_map=None, n_peaks=6, max_scatter=400,
                                rating_aware_auc=None, feature="lsb",
                                pro_lsb_spectrum_by_channel=None):
    """Exploratory 5 Hz sliding-band feature-importance scan (DESIGN §8b).

    Slides a `band_width_hz`-wide window in `step_hz` increments. For each (channel, band):
      * a per-epoch band feature (see `feature` below) — one scalar per session
      * Pearson r vs the CONTINUOUS pain label (the exploratory signal, no binarization)
      * ROC-AUC of the BINARIZED label via cross-validated single-feature logistic regression
      * a cluster-robust (rating-clustered) logistic Wald p — the inferential twin of the AUC,
        the predictive analog of a per-rating random intercept (the "mixed-effects" readout)

    `feature` selects the per-band quantity all three readouts run on:
      * "lsb" (DEFAULT, per PI): CALIBRATED device LSB from the SHARED per-pair CS-1…CS-4 cache
        (`pro_lsb_spectrum_by_channel`, required for this mode). Per matched (channel, PRO), the
        LSB vector was computed once by `bravo_service._pro_lsb_spectrum_cached`:
          - TD-transform route (k=352.62, analytics.td_transform_band_power): any TD-bearing recording
            covering the rating → 30 s rating-centered window → vectorized rFFT over all centers.
          - CS-3 PSD-bridge route (k≈73.63, analytics.device_psd_to_lsb): no TD + coincident PSD-only
            patient event → device_psd_band_power over all centers. Full 0–100 Hz; bands outside
            [7.8, 30] carry calibrated=False (exploratory; the UI flags them). Bridge shown full-
            spectrum per PI 2026-06-27 ("calculate it anyway … make it clear outside 7.8–30 Hz
            this hasn't been validated").
        The old Welch-density × k=269 / device-FFT rescale path is REMOVED (PI 2026-06-27). Falls
        back to "logpsd" if pro_lsb_spectrum_by_channel is None (e.g. back-compat callers).
      * "logpsd": mean LINEAR PSD over the band → 10*log10 (dB). Kept for parity/debugging.

    The r and AUC curves are returned per channel on a shared band-center x-axis so the UI can
    overlay them; `adaptive_band` is flagged per band. Per band a compact click-scatter (band feature
    vs continuous label, with dates) is returned. NOTHING here is a validated biomarker — discovery.
    """
    if not td_detail:
        return None
    f = np.asarray(td_detail.get("f_set"), dtype=float)
    psd = np.asarray(td_detail.get("psd"), dtype=float)          # (E, C, F) power (linear or prelog)
    labels = np.asarray(td_detail.get("labels"), dtype=float)    # (E,) continuous PRO
    chans = td_detail.get("chan_order", [])
    times = td_detail.get("times")
    # `prelog`: the stored `psd` feature is ALREADY 10*log10 (and within-source z-scored), as the
    # pooled-PSD builder emits. Then a logpsd band feature = mean over the band directly (no re-log).
    prelog = bool(td_detail.get("prelog", False))
    if f.size == 0 or psd.ndim != 3 or labels.size == 0:
        return None

    # --- Feature selection: CS-1…CS-4 shared LSB cache (default) vs legacy log-PSD ----------------
    # "lsb" mode: per-band LSB comes from the shared per-pair spectrum cache
    # (bravo_service._pro_lsb_spectrum_cached), threaded in as `pro_lsb_spectrum_by_channel`.
    # The old psd_abs_uv2_per_hz × k=269 / device-FFT rescale path is REMOVED (PI 2026-06-27).
    use_lsb = (str(feature).lower() == "lsb" and pro_lsb_spectrum_by_channel is not None)
    if use_lsb:
        if fmax is None:
            fmax = float(np.nanmax(f))
        feature_used = "lsb_cs14"
        n_demoted = 0
        # Build (N, C, F_centers) LSB matrix from the cache. Each cell is log10(LSB) for matched
        # rows whose (channel, PRO) has a spectrum entry; unmatched or unresolved → NaN.
        # We use the SAME center grid as the cache (bravo_service._LSB_SPECTRUM_CENTERS) and map
        # each scan band center to the nearest cache center. Falls back to logpsd per band if no
        # cache entry covers a given (channel, rating).
        rgroup = np.asarray(td_detail.get("rating_group", []))
        labels_arr = labels  # already extracted above
        pro_times_epoch = td_detail.get("pro_times_epoch")   # injected by bravo_service if available
        # The per-band LSB look-up is deferred to the per-channel inner loop below; store the
        # pre-indexed cache here once so the loop doesn't re-index per band.
        _lsb_cache = pro_lsb_spectrum_by_channel  # { raw_ch: [{t,tier,lsb,calibrated,...},...] }
    else:
        feature_used = "logpsd_db"
        n_demoted = 0

    # Rating-aware AUC: in "all" mode many epochs share one pain rating (double-dipping), so the
    # binary classifier's cross-validation should keep each rating wholly within a fold (grouped CV)
    # — the predictive analog of a per-rating random intercept. Auto-on when the detail is the "all"
    # pool AND carries a rating_group; off for one_per_rating (already independent). Caller can force
    # with `rating_aware_auc=True/False`.
    rating_group = td_detail.get("rating_group")
    rg = np.asarray(rating_group) if rating_group is not None else None
    agg_mode = td_detail.get("aggregate", "all")
    if rating_aware_auc is None:
        rating_aware_auc = (agg_mode == "all" and rg is not None and rg.size == labels.size)
    auc_groups = rg if (rating_aware_auc and rg is not None and rg.size == labels.size) else None

    fmax = float(fmax) if fmax is not None else float(np.nanmax(f))
    w = float(band_width_hz)
    # Band CENTERS from w/2 up to fmax - w/2 so every band lies fully within [0, fmax].
    # In LSB mode the scan still runs the FULL 0–100 Hz range (centers 2.5–97.5 Hz with the
    # default 5 Hz window and fmax=100). Bands outside 8–30 Hz are flagged adaptive_valid=False
    # and the UI renders them at reduced opacity with a green tint over the 8–30 Hz region —
    # the user sees the full spectral landscape while the deployable range is clearly marked.
    # Previously the first center was clamped to adaptive_band[0] + w/2 = 10.5 Hz, making
    # 10.5 Hz the LOWEST displayed center and losing the 8.0–10.0 Hz bands entirely. The fix:
    # always start at w/2 (= 2.5 Hz) regardless of mode; adaptive_valid already gates correctness.
    lo_c = w / 2.0
    hi_c = fmax - w / 2.0
    if hi_c <= lo_c:
        return None
    centers = np.arange(lo_c, hi_c + 1e-9, float(step_hz))
    a_lo, a_hi = (None, None) if adaptive_band is None else (float(adaptive_band[0]), float(adaptive_band[1]))

    # Binarize the continuous label ONCE (same split for every band).
    y_bin = _binarize_labels(labels, strategy=strategy, low_pct=low_pct, high_pct=high_pct,
                             pain_cutoff=pain_cutoff)

    band_meta = []
    for c in centers:
        b0, b1 = c - w / 2.0, c + w / 2.0
        # adaptive_valid is True when the CENTER frequency (not the full band) lies within the
        # validated/deployable range [a_lo, a_hi]. This means the 8–30 Hz green tint starts at
        # the first center that IS 8 Hz (≈ 8.5 Hz on the 1.0 Hz-step, half-integer grid), not at the
        # first center whose entire 5 Hz window clears 8 Hz (which was 10.5 Hz — wrong).
        # The integration still uses the full ±2.5 Hz window; adaptive_valid is purely a UI marker.
        adaptive_valid = bool(a_lo is not None and a_lo - 1e-9 <= c <= a_hi + 1e-9)
        band_meta.append({"center": float(c), "lo": float(b0), "hi": float(b1),
                          "adaptive_valid": adaptive_valid})

    out_channels = []
    C = psd.shape[1]
    label_fin_all = np.isfinite(labels)            # epochs with a matched PRO label
    n_pooled = int(label_fin_all.sum())            # pooled matched PSDs across ALL channels
    for ci in range(C):
        raw = chans[ci] if ci < len(chans) else f"ch{ci}"
        region = region_map.get(raw) if region_map else None
        fmt = format_channel(raw, region=region)
        # Per-channel sample CEILING: matched epochs that were actually recorded on THIS channel.
        # The pooled matched count (`n_pooled`) splits across the C bipolar montages because each
        # PSD recording captures one montage, so this is the max n any band on this channel's curve
        # / scatter can use. Surfaced so the UI can show pooled-vs-per-channel honestly.
        chan_fin = np.isfinite(psd[:, ci, :]).any(axis=1) & label_fin_all
        n_channel = int(chan_fin.sum())
        # `p_pearson_curve` is the independence-assuming Pearson p (treats every PSD as independent).
        # It is NOT the inferential headline — that's the rating-clustered logit `p_curve`. We keep
        # it only so the FDR pass below can quantify the pseudoreplication inflation (naive bands
        # at FDR vs rigorous bands at FDR), which is the rigor-pass UI annotation.
        r_curve, auc_curve, n_curve, n_r_curve, p_curve = [], [], [], [], []
        p_pearson_curve = []
        band_power_by_center = []   # (n_centers, E) log band power, for click-scatter
        _cv_jobs = []               # (curve_index, bp_log) for the parallel CV-AUC + logit-p pass
        for c in centers:
            bmask = (f >= c - w / 2.0) & (f < c + w / 2.0)
            if not bmask.any():
                r_curve.append(None); auc_curve.append(None); n_curve.append(0)
                n_r_curve.append(0); p_curve.append(None); p_pearson_curve.append(None)
                band_power_by_center.append(None)
                continue
            with np.errstate(invalid="ignore", divide="ignore"), \
                 warnings.catch_warnings():
                # All-NaN slices (epochs not recorded on this channel) are expected — nanmean's
                # "Mean of empty slice" RuntimeWarning is noise here, not a problem.
                warnings.simplefilter("ignore", category=RuntimeWarning)
                if use_lsb:
                    # CS-1…CS-4 SHARED LSB CACHE: look up the per-PRO LSB spectrum for this
                    # channel and band center. The cache was built by
                    # bravo_service._pro_lsb_spectrum_cached (TD-transform k=352.62 / CS-3 bridge
                    # k≈73.63) on the same matched (channel, PRO) pairs this scan uses. Each cache
                    # entry holds an LSB value per band center (0–100 Hz); we pick the nearest
                    # center. The scan row corresponds to one matched PSD record whose `rating_group`
                    # index identifies which PRO it was matched to. We recover the PRO's LSB at this
                    # band from the cache and log10 it. Rows with no cache entry (unmatched, no TD
                    # or event PSD near the PRO) → NaN, same as the old path for unresolved rows.
                    # look up by raw name first, then by any matching key (uppercase comparison)
                    ch_spectra = _lsb_cache.get(raw)
                    if ch_spectra is None:
                        raw_up = str(raw).upper()
                        ch_spectra = next(
                            (v for k, v in _lsb_cache.items() if str(k).upper() == raw_up),
                            None)
                    E = psd.shape[0]
                    bp_log = np.full(E, np.nan)
                    if ch_spectra is not None:
                        # build center→cache_index lookup once per (channel, band_center)
                        _cspec0 = ch_spectra[0] if ch_spectra else None
                        if _cspec0 is not None:
                            cache_centers = np.asarray(_cspec0.get("center_hz", []), dtype=float)
                            ci_cache = int(np.argmin(np.abs(cache_centers - c))) if cache_centers.size else None
                        else:
                            ci_cache = None
                        rg_arr = np.asarray(td_detail.get("rating_group", []))
                        for row_i in range(E):
                            if not label_fin_all[row_i]:
                                continue   # unmatched row
                            pro_i = int(rg_arr[row_i]) if rg_arr.size > row_i else -1
                            if pro_i < 0 or pro_i >= len(ch_spectra):
                                continue
                            spec = ch_spectra[pro_i]
                            if spec is None or ci_cache is None:
                                continue
                            lsb_vals = spec.get("lsb") or []
                            if ci_cache >= len(lsb_vals):
                                continue
                            v = lsb_vals[ci_cache]
                            if v is not None and v > 0:
                                bp_log[row_i] = float(np.log10(v))
                    # full band outside calibrated range → keep value, UI flags via adaptive_valid
                elif prelog:
                    # Already log (+ z-scored): the band feature is the mean over the band's bins.
                    bp_log = np.nanmean(psd[:, ci, bmask], axis=1)
                else:
                    bp = np.nanmean(psd[:, ci, bmask], axis=1)   # (E,) mean linear power in band
                    bp_log = 10.0 * np.log10(np.where(bp > 0, bp, np.nan))
            band_power_by_center.append(bp_log)
            # Pearson r vs CONTINUOUS label (ALL matched samples — no binarization). We also
            # compute the naive two-sided Pearson p here so the rigor pass can quantify the
            # pseudoreplication inflation (it is the independence-assuming p, not the inferential
            # number to report — that's `p_curve`).
            m = np.isfinite(bp_log) & np.isfinite(labels)
            n_r_curve.append(int(m.sum()))
            r = p_pearson = None
            if m.sum() >= 4 and np.nanstd(bp_log[m]) > 0 and np.nanstd(labels[m]) > 0:
                from scipy.stats import pearsonr as _pr
                _r, _p = _pr(bp_log[m], labels[m])
                r = float(_r); p_pearson = float(_p)
            r_curve.append(_f(r) if r is not None else None)
            p_pearson_curve.append(_f(p_pearson) if (p_pearson is not None and np.isfinite(p_pearson)) else None)
            # AUC vs BINARIZED label (CV logistic) + its cluster-robust logit-p inference twin are the
            # two expensive per-band fits (StratifiedGroupKFold + LogisticRegression). They depend only
            # on this band's `bp_log` (y_bin/auc_groups are constant across bands) and are independent
            # band-to-band, so we COLLECT them here and run them in parallel after the cheap pass below
            # (see `_band_cv_stats`). Placeholders keep auc/n/p aligned with the curve indices; the
            # parallel map overwrites them by index, so the result is identical to the serial loop.
            auc_curve.append(None)
            n_curve.append(0)
            p_curve.append(None)
            _cv_jobs.append((len(auc_curve) - 1, bp_log))

        # --- Parallel CV pass: the per-band CV-logistic AUC and cluster-robust logit-p are the two
        # heaviest fits in the scan and are independent across bands, so run them concurrently across
        # cores (sklearn fits release the GIL). Results are written back BY INDEX, so auc/n/p land in
        # exactly the positions the serial loop would have produced — numerically identical, only the
        # wall-clock differs. Each job is self-contained (constant y_bin/auc_groups, this band's bp_log).
        def _band_cv_stats(bp_log):
            auc, n_used = _cv_logistic_auc(bp_log, y_bin, groups=auc_groups)
            with np.errstate(invalid="ignore", divide="ignore"), warnings.catch_warnings():
                warnings.simplefilter("ignore")
                p_band, _np_n, _np_g = _cluster_robust_logit_p(bp_log, y_bin, groups=auc_groups)
            return (_f(auc) if np.isfinite(auc) else None, int(n_used),
                    _f(p_band) if np.isfinite(p_band) else None)

        if _cv_jobs:
            n_workers = max(1, min(len(_cv_jobs), _spectral_cv_threads()))
            if n_workers == 1:
                results = [_band_cv_stats(bp) for _idx, bp in _cv_jobs]
            else:
                from concurrent.futures import ThreadPoolExecutor as _TPE
                with _TPE(max_workers=n_workers) as _pool:
                    results = list(_pool.map(lambda job: _band_cv_stats(job[1]), _cv_jobs))
            for (idx, _bp), (auc_v, n_v, p_v) in zip(_cv_jobs, results):
                auc_curve[idx] = auc_v
                n_curve[idx] = n_v
                p_curve[idx] = p_v

        # Peaks on the |r| curve (continuous-signal peaks, the primary exploratory lens).
        from scipy.signal import find_peaks
        absr = np.array([abs(x) if x is not None else 0.0 for x in r_curve], dtype=float)
        pk, _ = find_peaks(absr, prominence=0.05)
        pk = sorted(pk, key=lambda k: -absr[k])[:n_peaks]
        peaks = [{"center": float(centers[k]), "r": r_curve[k], "auc": auc_curve[k]}
                 for k in sorted(pk)]

        out_channels.append({
            "name": fmt["label"], "short": fmt["short"], "region": fmt["region"], "raw": fmt["raw"],
            "r": r_curve,            # Pearson r vs continuous PRO, per band center
            "auc": auc_curve,        # CV-logistic AUC vs binarized PRO, per band center
            "n": n_curve,            # AUC samples used per band (binarized hi+lo, middle dropped)
            "n_r": n_r_curve,        # Pearson samples per band (ALL matched continuous, this channel)
            "p": p_curve,            # rating-clustered logistic Wald p per band (AUC's inference twin)
            # Per-band naive Pearson p (independence-assuming) — kept so the FDR pass below can
            # quantify the pseudoreplication inflation vs the rating-clustered logit p.
            "p_pearson": p_pearson_curve,
            "n_channel": n_channel,  # matched PSDs recorded on THIS channel (per-channel ceiling)
            "peaks": peaks,
            # Keep the per-band log power around for click-to-scatter (server-side cache; the
            # frontend reads scatter via the band index). Stored compact (one row per center).
            "_band_power": band_power_by_center,
        })

    # Build click-scatter payloads: for each channel & band center, (band power, continuous label,
    # date) for matched sessions. Done here (not in the loop) so we can cap the payload size.
    label_fin = np.isfinite(labels)
    for ch in out_channels:
        bp_list = ch.pop("_band_power")
        scat = []
        for bp_log in bp_list:
            if bp_log is None:
                scat.append(None); continue
            m = np.isfinite(bp_log) & label_fin
            idx = np.where(m)[0]
            if idx.size < 3:
                scat.append(None); continue
            if idx.size > max_scatter:
                idx = idx[np.linspace(0, idx.size - 1, max_scatter).astype(int)]
            # Per-sample binarization group from the SAME high/low/excluded split the AUC uses
            # (y_bin: 1.0=high, 0.0=low, NaN=excluded middle), so the click panel's violin can
            # color points by pain group without recomputing the cut client-side.
            def _grp(i):
                v = y_bin[i]
                if v == 1.0:
                    return "high"
                if v == 0.0:
                    return "low"
                return "mid"
            gs = [_grp(i) for i in idx]
            xs = np.array([bp_log[i] for i in idx], dtype=float)
            ga = np.array(gs)
            # Effect size of the low-vs-high band-power separation (the click panel's headline):
            #   * cohens_d  — pooled-SD standardized mean difference (high minus low). Positive => the
            #     band is higher in high-pain samples. |d|: 0.2 small / 0.5 medium / 0.8 large.
            #   * median_delta — median(high) - median(low). x is ALREADY standardized log band power
            #     (z within channel/source), so this is expressed directly in standard-deviation units.
            x_lo, x_hi = xs[ga == "low"], xs[ga == "high"]
            cohens_d = median_delta = None
            if x_lo.size >= 2 and x_hi.size >= 2:
                s_lo, s_hi = np.nanstd(x_lo, ddof=1), np.nanstd(x_hi, ddof=1)
                n_lo, n_hi = x_lo.size, x_hi.size
                sp2 = ((n_lo - 1) * s_lo ** 2 + (n_hi - 1) * s_hi ** 2) / max(n_lo + n_hi - 2, 1)
                if sp2 > 0:
                    cohens_d = _f(float((np.nanmean(x_hi) - np.nanmean(x_lo)) / np.sqrt(sp2)))
                median_delta = _f(float(np.nanmedian(x_hi) - np.nanmedian(x_lo)))
            scat.append({
                # In LSB mode x = log10 calibrated LSB (NOT z-scored); in logpsd mode x = standardized
                # log band power. `x_unit` (set on the channel below) tells the UI which.
                "x": [_f(bp_log[i]) for i in idx],          # band feature (see x_unit)
                "y": [_f(labels[i]) for i in idx],          # continuous PRO
                "g": gs,                                    # pain group: high | low | mid (excluded)
                "cohens_d": cohens_d,                       # standardized mean diff, high - low
                "median_delta": median_delta,               # median(high) - median(low), in SD units
                "n_grp": {"high": int((ga == "high").sum()), "low": int((ga == "low").sum()),
                          "mid": int((ga == "mid").sum())},
                "dates": ([str(times[i]) for i in idx] if times is not None else None),
            })
        ch["scatter"] = scat

    # --------------------------------------------------------------------------------------------
    # Rigor pass: BH-FDR over the full band x channel family, separately for the rating-clustered
    # logit p (the inferential headline) and the naive Pearson p (a foil). We do TWO families
    # because the user-facing annotation is a contrast: "naive Pearson reports N FDR-significant
    # bands, rating-clustered logistic reports M" — typically M << N on rating-pseudoreplicated
    # data. Each channel gets a per-band `q` (clustered-logit q, the deployment number) plus an
    # `is_fdr_sig` boolean so the frontend can style dots without recomputing the cutoff.
    #
    # Implementation: flatten all channel p-curves into one vector per family, BH-correct, scatter
    # back to per-channel arrays. nan-aware (None entries treated as missing, get q=None).
    try:
        from statsmodels.stats.multitest import multipletests
    except Exception:
        multipletests = None
    fdr_summary = None
    if multipletests is not None and out_channels:
        def _bh_per_band_grid(p_field):
            """Run BH over the union of channels' per-band p values; return list-of-lists q (per channel, per band)."""
            flat, locator = [], []   # locator[k] = (chan_idx, band_idx) for flat[k]
            for ci, ch in enumerate(out_channels):
                arr = ch.get(p_field) or []
                for bi, pv in enumerate(arr):
                    if pv is not None and np.isfinite(pv):
                        flat.append(float(pv)); locator.append((ci, bi))
            if not flat:
                return [[None] * len(centers) for _ in out_channels], 0
            _, qvals, _, _ = multipletests(np.asarray(flat, dtype=float), alpha=0.05, method="fdr_bh")
            qmat = [[None] * len(centers) for _ in out_channels]
            n_sig = 0
            for (ci, bi), q in zip(locator, qvals):
                qmat[ci][bi] = float(q)
                if q < 0.05:
                    n_sig += 1
            return qmat, n_sig

        q_logit_mat, n_rigorous_fdr = _bh_per_band_grid("p")
        q_pearson_mat, n_naive_fdr = _bh_per_band_grid("p_pearson")
        for ci, ch in enumerate(out_channels):
            ch["q"] = q_logit_mat[ci]                 # rating-clustered logit FDR q per band (the headline)
            ch["q_pearson"] = q_pearson_mat[ci]       # naive Pearson FDR q per band (for the contrast)
            ch["is_fdr_sig"] = [
                (q is not None and q < 0.05) for q in q_logit_mat[ci]
            ]
        fdr_summary = {
            "n_bands_total": int(sum(1 for ch in out_channels for q in (ch.get("q") or []) if q is not None)),
            "n_rigorous_fdr": int(n_rigorous_fdr),    # bands surviving FDR under rating-clustered logit
            "n_naive_fdr": int(n_naive_fdr),          # bands surviving FDR under naive Pearson (pseudoreplicated)
            "alpha": 0.05,
            "method": "BH-FDR",
            "family": "band x channel (per metric)",
        }
    # --------------------------------------------------------------------------------------------

    return {
        "centers": [float(c) for c in centers],
        "bands": band_meta,
        "channels": out_channels,
        "band_width_hz": w,
        "step_hz": float(step_hz),
        "fmax": fmax,
        "adaptive_band": ([a_lo, a_hi] if a_lo is not None else None),
        "strategy": strategy,
        "transform": "log_bandpower",
        # The per-band feature that r / AUC / clustered-logit p all run on.
        #   "lsb_cs14"  -> log10(CS-1…CS-4 shared LSB cache): TD-transform k=352.62 or CS-3 bridge
        #                   k≈73.63, per matched (channel, PRO), rating-centered 30 s window.
        #   "logpsd_db" -> 10*log10(mean band PSD), legacy fallback
        "feature": feature_used,
        "feature_unit": ("log10 LSB (CS-1…CS-4: TD-transform k=352.62 / PSD-bridge k≈73.63)"
                         if use_lsb else "dB (10·log10 band PSD)"),
        "feature_note": (
            "Band feature is the CALIBRATED device LSB from the shared CS-1…CS-4 per-pair cache "
            "(bravo_service._pro_lsb_spectrum_cached). Per matched (channel, PRO) report: "
            "TD-bearing recordings (streaming, montage/survey, all 250 Hz) → 30 s rating-centered "
            "window → transform DSP (Hann-windowed zero-padded FFT, 50% overlap) × k=352.62 "
            "(LSB_PER_UV2_TRANSFORM). PSD-only patient events with no coincident TD → CS-3 bridge "
            "(device_psd_band_power × k≈73.63). Full 0–100 Hz per PI 2026-06-27. "
            "TD-transform bands are calibrated across the full spectrum (k=352.62 is band-agnostic). "
            "CS-3 bridge bands outside [7.8, 30] Hz carry calibrated=False (exploratory, shown at "
            "reduced opacity — the bridge has no validated meaning there). "
            "The old Welch-density × k=269 / per-channel device-FFT rescale path is REMOVED."
            if use_lsb else "Legacy dB band-power feature; not LSB-calibrated."),
        # Rigor-pass output: BH-FDR over the full band x channel grid for both the inferential
        # (rating-clustered logit) and naive (Pearson) families. Per-band q lives on each channel
        # dict; this summary is the UI's pseudoreplication-contrast annotation source.
        "fdr_summary": fdr_summary,
        "n_pooled": n_pooled,        # matched PSDs pooled across ALL channels (the preview total)
        # Aggregation + AUC mode so the UI can state what the numbers mean. aggregate: "all" (every
        # matched PSD a sample) vs "one_per_rating" (each (channel,rating) collapsed to one). auc_mode:
        # "rating_grouped" => folds split by rating so the AUC n is the count of INDEPENDENT ratings;
        # "pooled" => plain stratified CV (used in one_per_rating, where samples are already independent).
        "aggregate": agg_mode,
        "auc_mode": ("rating_grouped" if auc_groups is not None else "pooled"),
        # Finalized binarization actually used by the logistic AUC (high vs low; the excluded
        # middle is dropped). Lets the UI show how many of the matched samples the AUC ran on.
        "binarization": {
            "strategy": strategy,
            "n_low": int(np.nansum(y_bin == 0)),
            "n_high": int(np.nansum(y_bin == 1)),
            "n_excluded_middle": int(np.isfinite(labels).sum() - np.isfinite(y_bin).sum()),
        },
        # PRO-independence (double-dipping) audit, carried through from the pooled matcher so the
        # UI can report how many neural samples share one pain score (effective n < matched n).
        "pro_independence": (td_detail.get("pool_meta", {}) or {}).get("pro_independence"),
        "pro_independence_per_channel": (td_detail.get("pool_meta", {}) or {}).get(
            "pro_independence_per_channel"),
        # Matching policy + usage, carried through so the UI can state it transparently: the per-rating
        # cap, refractory gap, match direction, how many PSDs the cap dropped, the survey-usage view
        # (PROs used / available / reused), and the TD Welch epoch length (mean +/- SD).
        "match_direction": (td_detail.get("pool_meta", {}) or {}).get("match_direction"),
        "max_per_rating": (td_detail.get("pool_meta", {}) or {}).get("max_per_rating"),
        "refractory_min": (td_detail.get("pool_meta", {}) or {}).get("refractory_min"),
        "n_capped_dropped": (td_detail.get("pool_meta", {}) or {}).get("n_capped_dropped"),
        "survey_usage": (td_detail.get("pool_meta", {}) or {}).get("survey_usage"),
        "td_welch_duration": (td_detail.get("pool_meta", {}) or {}).get("td_welch_duration"),
        "note": ("Exploratory only. r is Pearson vs the continuous PRO (ALL matched samples); AUC "
                 "is cross-validated single-feature logistic on the FINALIZED high-vs-low split "
                 "(excluded-middle tertile dropped), so the AUC n (legend 'n') is generally < the "
                 "Pearson n ('n_r'). Neither is a validated biomarker. Each curve/scatter uses only "
                 "the PSDs recorded on THAT channel, so its n is a fraction of the pooled "
                 "matched-sample count in the binarization preview (one montage per recording). "
                 "PRO-independence is audited below: several neural samples can share one pain "
                 "score, so the effective n is smaller than the matched n."),
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
    return int(min(max(decay, n13), max(2, K // 3)))


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
    y_all = _binarize_labels(labels, strategy=strategy, low_pct=low_pct, high_pct=high_pct,
                             pain_cutoff=pain_cutoff)
    m = np.isfinite(bp_log) & np.isfinite(y_all)
    if m.sum() < 12 or len(np.unique(y_all[m])) < 2:
        return {"available": False, "reason": "too few matched high/low samples for an ROC"}
    x = bp_log[m].astype(float)
    y = y_all[m].astype(int)
    g = rating_group[m]

    raw_auc = float(metrics.roc_auc_score(y, x))
    flip = raw_auc < 0.5                       # orient so higher score = higher pain
    use_score = -x if flip else x
    auc = float(max(raw_auc, 1.0 - raw_auc))
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
    if block_len > 1 and var_iid > 0 and var_block > 0:
        deff = float(min(5.0, max(1.0, var_block / var_iid)))
    else:
        deff = 1.0

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

    return {
        "available": True,
        "auc": auc, "auc_lo": auc_lo, "auc_hi": auc_hi,
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
        "auc_lo_iid": (float(np.percentile(boot_iid, 2.5)) if len(boot_iid) >= 20 else None),
        "auc_hi_iid": (float(np.percentile(boot_iid, 97.5)) if len(boot_iid) >= 20 else None),
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

    return {
        "available": True,
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
    bp_log, labels, _rating_group, times = feat
    y_all = _binarize_labels(labels, strategy=strategy, low_pct=low_pct, high_pct=high_pct,
                             pain_cutoff=pain_cutoff)
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
    return {"available": True, "status": status,
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
    y_all = _binarize_labels(labels, strategy=strategy, low_pct=low_pct, high_pct=high_pct,
                             pain_cutoff=pain_cutoff)
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

    return {
        "available": True,
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


# ── welch256 route — PSD→LSB EXPLORATION BACKUP ONLY (NOT the primary TD→LSB route) ──────────────
# Power-domain LSB <-> µV² calibration, VALIDATED on RCS08 ground truth (on-demand BrainSense
# Streaming: BrainSenseLfp device LSB + BrainSenseTimeDomain 250 Hz TD on the SAME signal, 50 stim-off
# paired blocks). Welch 256-pt PSD of the TD integrated over the sensed band, regressed on the device's
# own LFP power: k = 269 LSB/µV² (1 LSB ≈ 0.0037 µV²), log-log slope 0.835, R² 0.94, 5-fold CV fold-
# error 1.19×, 1σ multiplicative scatter 1.26×. This MATCHES the design-ledger empirical 0.0034 µV²/LSB
# to within 9% and is 0.37× the Medtronic 0.01-µV²/LSB rule of thumb. It is far tighter than the older
# empirical_lsb_ratio FYI (which was rated to ~3×) because TD and LSB come from the identical signal —
# no time-matching slop. This is the time-domain ADC LSB's DISTINCT power-domain sibling: 146 nV/LSB
# (ADC_NV_PER_LSB) is the exact time-domain count scale; the constant below is the firmware's band-
# power LSB, which is normalization-dependent and remains a CONFIDENCE-RATED estimate (use the device's
# own Timeline LSB percentile anchor for the actual deployed threshold; use this only to translate a
# physical µV² target into LSB when the device never sensed the band).
#
# ROUTE STATUS (PI decision 2026-06-27, HANDOFF_TD_LSB_calibration_2026-06-27.md): k=269 is the
# **welch256 route**, demoted to the PSD→LSB EXPLORATION BACKUP — used only to turn a power-domain
# PSD into LSB when NO coincident time-domain stream exists for a match. The PRIMARY TD→LSB source of
# truth is now the **transform route, k = LSB_PER_UV2_TRANSFORM = 352.62** (below). Do NOT feed a
# transform-DSP µV² through k=269, and do NOT feed a welch256 µV² through 352.62 — each DSP carries its
# own scale (see ERROR 3 in the handoff). The two are NOT interchangeable.
LSB_PER_UV2_VALIDATED = 269.0          # k, welch256 route — PSD→LSB exploration backup ONLY
UV2_PER_LSB_VALIDATED = 1.0 / LSB_PER_UV2_VALIDATED   # ≈ 0.00372 µV²/LSB
LSB_UV2_LOGLOG_SLOPE = 0.835           # firmware power-law slope (≠1: device band ≠ offline band exactly)
LSB_UV2_SIGMA_FOLD = 1.26              # 1σ multiplicative scatter of the calibration
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


def lsb_from_uv2(uv2, *, k=LSB_PER_UV2_VALIDATED):
    """Translate an offline band power in µV² to device power-domain LSB using the validated
    proportional constant k (default = RCS08 stim-off fit, 269 LSB/µV²). Pass a participant-specific
    k when one has been fitted. Returns float LSB, or NaN for non-positive/invalid input.

    This is the DIRECT route the back-translation analysis confirmed is sufficient: device LFP Power is
    the band integral of the PSD, and a band integral is phase-independent, so reconstructing a time
    series from the PSD (PSD→TD→LSB) cannot add information — band power from a phase-randomized
    reconstruction matched the direct integral to within 0.8% across 113 RCS08 blocks. Only the 256-pt
    FFT modes (Dual, Single-Inverse) are valid targets; Single Threshold's 64-pt band is a different
    quantity (see THRESHOLD_MODES / COMPATIBLE_THRESHOLD_MODES).

    **Frequency coverage:** the default k (269) is validated on RCS08 paired blocks at 7.8–28.3 Hz
    only (approximately band-flat within that range, 1.23× span excluding the anomalous 7.8 Hz n=4
    point). Bands outside ~8–28 Hz have NO ground truth — k there is an untested extrapolation. This
    is not clinically restrictive for the adaptive modes (firmware-limited to 8–30 Hz), but sensing-
    only bands at higher frequencies (e.g. high-gamma) would need their own streaming calibration.
    """
    try:
        x = float(uv2)
    except (TypeError, ValueError):
        return float("nan")
    if not np.isfinite(x) or x <= 0:
        return float("nan")
    return float(k) * x


def uv2_from_lsb(lsb, *, k=LSB_PER_UV2_VALIDATED):
    """Inverse of lsb_from_uv2: device power-domain LSB → offline band power in µV². Returns NaN for
    non-positive/invalid input."""
    try:
        x = float(lsb)
    except (TypeError, ValueError):
        return float("nan")
    if not np.isfinite(x) or x <= 0 or k == 0:
        return float("nan")
    return float(x) / float(k)


def _freq_extrapolated(center_hz, lo=LSB_VALIDATED_HZ_LO, hi=LSB_VALIDATED_HZ_HI):
    """True iff center_hz is outside the validated [7.8, 28.3] Hz calibration range (None -> False).

    Mirrors psd_lsb_model._freq_extrapolated so the proportional (k=269) route and the frozen per-band
    model share ONE definition of "outside the calibrated range". Kept module-local (vs imported) to
    avoid a routines->routines import cycle; the two constants are asserted equal by test.
    """
    try:
        c = float(center_hz)
    except (TypeError, ValueError):
        return False
    if not np.isfinite(c):
        return False
    return bool(c < float(lo) or c > float(hi))


def psd_band_to_lsb(psd_uv2_per_hz, freq, center_hz, *, half_hz=2.5, k=LSB_PER_UV2_VALIDATED,
                    threshold_mode="Dual"):
    """Convert a physical PSD (µV²/Hz) to device power-domain LSB over a band, via the Welch256
    band-integral × k=269 route. This is the **PSD→LSB EXPLORATION BACKUP** — used only to turn a
    power-domain PSD into LSB when NO coincident time-domain stream exists for a match. When TD is
    available, the PRIMARY route is td_to_lsb (transform DSP × LSB_PER_UV2_TRANSFORM = 352.62); do not
    route a TD trace through here.

    This is a MODELED value either way — native device LSB (Timeline / BrainSenseLfp) is always
    preferred when the band was actually sensed (see DESIGN §4). The default k=269 is RCS08-validated
    and approximately band-flat across 7.8–28.3 Hz; outside that range the conversion is an untested
    extrapolation and is flagged (never silently trusted).

    Route history (do not re-litigate): a 2026-06-25 "Step-0" pass chose fixed-269 over the transform
    for the timeline. That decision was SUPERSEDED on 2026-06-27 (PI; HANDOFF_TD_LSB_calibration_
    2026-06-27.md): the transform route (k=352.62), reproduced bit-for-bit against the lab repo, is now
    the primary TD→LSB source of truth for the EXPLORATION timeline (availability.lsb_series, switched
    in CS-1). The k switch is safe there because k cancels in the r/AUC curves (it is multiplicative on
    a log band-power feature) — only the absolute displayed LSB moves to the lab-consistent scale.

    SCOPE (as of CS-1): the bravo_service DEPLOYMENT modeled fallback is NOT switched — it converts a
    frozen-model physical µV² cut-point via lsb_from_uv2 (k=269, the population constant), not a TD
    trace, so it legitimately keeps k=269 (each DSP carries its own scale; do not feed a cut-point
    through 352.62). This psd_band_to_lsb function itself currently has NO production caller after the
    CS-1 switch — it is the intended PSD→LSB backup for the no-TD case, but that backup is NOT yet
    wired and the welch256 DSP is anyway the wrong front end for a device PSD (it re-derives a PSD from
    TD; a device montage/event PSD is in a different normalization). The proper no-TD backup needs its
    OWN device-PSD→LSB refit — tracked as a follow-up, see INGEST/HANDOFF notes — not this function.

    Parameters
    ----------
    psd_uv2_per_hz, freq : array-like
        PSD power density (µV²/Hz) and matching frequency axis (Hz). Same length.
    center_hz : float
        Band center frequency (Hz). Snapped to nothing here — caller picks the sensing center.
    half_hz : float, default 2.5
        Half-bandwidth; the integral runs over [center-half, center+half) (≈5 Hz device band).
    k : float, default 269 (LSB_PER_UV2_VALIDATED)
        Proportional LSB/µV² constant. Pass a participant-specific k once one is fitted.
    threshold_mode : str, default "Dual"
        Percept adaptive mode whose FFT size the k assumes. k=269 is a 256-pt-equivalent fit, valid
        only for COMPATIBLE_THRESHOLD_MODES (256-pt: Dual, SingleInverse). The 64-pt Single mode
        integrates a different set of bins, so the conversion is flagged fft_incompatible there.

    Returns
    -------
    dict with keys:
        lsb : float | nan          modeled device LSB (nan if band has <2 bins or non-positive power)
        uv2 : float | nan          integrated band power in µV²
        k_used : float             the k applied
        freq_extrapolated : bool   center outside the validated 7.8–28.3 Hz range
        fft_compatible : bool      threshold_mode's FFT size matches the 256-pt calibration
        validated_hz_range : [lo, hi]
        method : str               provenance label
        note : str                 human-readable caveat (extrapolation / fft-incompat / ok)
    """
    f = np.asarray(freq, dtype=float)
    P = np.asarray(psd_uv2_per_hz, dtype=float)
    extrap = _freq_extrapolated(center_hz)
    fft_compatible = str(threshold_mode) in COMPATIBLE_THRESHOLD_MODES
    out = {
        "lsb": float("nan"), "uv2": float("nan"), "k_used": float(k),
        "freq_extrapolated": bool(extrap), "fft_compatible": bool(fft_compatible),
        "validated_hz_range": [LSB_VALIDATED_HZ_LO, LSB_VALIDATED_HZ_HI],
        "method": f"welch256_band_integral_x_k={float(k):.0f}",
        "note": "",
    }
    if f.ndim != 1 or P.ndim != 1 or f.size != P.size or f.size < 2:
        out["note"] = "PSD/freq axis missing, mismatched, or too short (<2 bins)"
        return out

    uv2 = _band_power_notched(f, P, float(center_hz), float(half_hz))
    out["uv2"] = uv2
    if not np.isfinite(uv2) or uv2 <= 0:
        out["note"] = f"band [{center_hz - half_hz:.1f}, {center_hz + half_hz:.1f}) Hz has <2 bins or non-positive power"
        return out

    out["lsb"] = lsb_from_uv2(uv2, k=k)

    notes = []
    if extrap:
        notes.append(
            f"center {float(center_hz):.1f} Hz is EXTRAPOLATED beyond the validated "
            f"{LSB_VALIDATED_HZ_LO:.1f}–{LSB_VALIDATED_HZ_HI:.1f} Hz range; k is an untested "
            f"extrapolation here (needs streaming calibration at this frequency)")
    if not fft_compatible:
        notes.append(
            f"threshold_mode={threshold_mode} uses a non-256-pt FFT; k=269 is a 256-pt-equivalent "
            f"fit and does NOT translate to this mode's band (Medtronic: LFP Power is not comparable "
            f"across threshold modes)")
    out["note"] = " · ".join(notes) if notes else "in validated range, 256-pt-compatible"
    return out


def welch256_density(samples_uv, fs):
    """Welch 256-pt power-density PSD of a time-domain µV trace — the EXACT transform the k=269
    calibration was fit against (scipy welch, hann window, nperseg=256, detrend='constant',
    scaling='density'). Returns (freq, psd_uv2_per_hz) or (None, None) if the trace is too short.

    This is the load-bearing detail for the timeline's psd_modeled tier: k=269 maps a *Welch-256
    band integral* of the 250 Hz TD to device LSB. The device's own montage/event `FFTBinData` is a
    DIFFERENT normalization and must NOT be fed to psd_band_to_lsb with k=269 — convert from TD via
    this helper instead. No mains notch (implanted device; matches _band_power_notched default).
    """
    try:
        from scipy.signal import welch as _welch
    except Exception:
        return None, None
    v = np.asarray(samples_uv, dtype=float)
    v = v[np.isfinite(v)]
    fs = float(fs)
    if v.size < 256 or fs <= 0:
        return None, None
    f, p = _welch(v, fs=fs, window="hann", nperseg=min(256, v.size),
                  detrend="constant", scaling="density")
    return f, p


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
    blocks) pinned this far more tightly than the "~3×" caveat once suggested — k = 269 LSB/µV²
    (≈ 0.0037 µV²/LSB), R² 0.94, CV fold-error 1.19×, i.e. 0.37× the 0.01 rule of thumb (see
    LSB_PER_UV2_VALIDATED / lsb_from_uv2). The absolute constant is still normalization-dependent, so
    the deployable threshold remains percentile-anchored on the device's own Timeline LSB (see the
    service layer); use the validated constant only to translate a physical µV² target into LSB when
    the device never sensed the band. `sensing_hz_for_pd(pd_rec, contact)` resolves a PowerDomain
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


def auc_power(auc, n_pos, n_neg, *, alpha=0.05, target_power=0.80, auc_lo=None, design_effect=1.0):
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
        return {"available": False, "reason": f"scipy unavailable: {e}"}
    auc = float(max(auc, 1.0 - auc))
    n_pos_raw = int(n_pos); n_neg_raw = int(n_neg)
    if n_pos_raw < 2 or n_neg_raw < 2:
        return {"available": False, "reason": "too few independent ratings for a power estimate"}
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
        return {"available": True, "auc": auc, "power_current": float(alpha), "se_auc": None,
                "n_ratings_current": n_pos_raw + n_neg_raw, "n_ratings_needed": None,
                "design_effect": deff,
                "more_data_needed": True, "alpha": alpha, "target_power": target_power,
                "curve": None,
                "note": "AUC at or below chance — no power to detect a real effect."}
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
    power_lo = None; n_need_hi = None; auc_lo_used = None
    if auc_lo is not None:
        try:
            a_lo = float(max(float(auc_lo), 1.0 - float(auc_lo)))  # fold defensively (display is oriented >=0.5)
        except (TypeError, ValueError):
            a_lo = None
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
            # undefined (the band could be null). Gate must not pass.
            auc_lo_used = a_lo; power_lo = float(alpha); n_need_hi = None

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
    n_top = int(max(N0_raw, n_need) * 1.35) + 4
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

    note = ("Hanley–McNeil AUC variance on the count of independent ratings (clustered "
            "effective n). Power to reject AUC = 0.5.")
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


def band_mixedmodel_inference(td_detail, channel_raw, center_hz, *, band_width_hz=5.0,
                              strategy="tertile", low_pct=33.3333, high_pct=66.6667,
                              pain_cutoff=None, cluster="era"):
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
    y = _binarize_labels(labels, strategy=strategy, low_pct=low_pct, high_pct=high_pct,
                         pain_cutoff=pain_cutoff, finite_mask=chan_finite)
    # PARITY (audit §6a): cluster = integer ELAPSED-week index from the first sample (phase2),
    # not the ISO-calendar-week string. Elapsed-week buckets that straddle a Monday split across two
    # ISO weeks (and vice versa), giving a different random-intercept structure -> different SE/p/CI.
    cl = _elapsed_week_cluster(times, len(bp_log))
    m = np.isfinite(bp_log) & np.isfinite(y)
    if m.sum() < 12 or len(np.unique(y[m])) < 2:
        return {"available": False, "reason": "too few matched samples for a mixed model"}
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
            "coef": _f(est), "odds_ratio": _f(odds),
            "or_lo": _f(or_lo) if or_lo is not None else None,
            "or_hi": _f(or_hi) if or_hi is not None else None,
            "z": _f(z), "p": _f(p), "separation": False, "singular": singular,
            "note": "Random intercept per weekly era; band power z-scored. Exploratory inference.",
        }
    except Exception as e:
        return {"available": False, "reason": f"glmer fit failed: {e}"}


def band_stim_stability(td_detail, channel_raw, center_hz, stim_series=None, *,
                        band_width_hz=5.0, strategy="tertile", low_pct=33.3333, high_pct=66.6667,
                        off_max=0.1, low_max=1.5):
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
        with _rpy2_converter_ctx():
            m0 = Lmer(formula_red, data=df, family="binomial"); m0.fit(summarize=False)
            m1 = Lmer(formula_full, data=df, family="binomial"); m1.fit(summarize=False)
        # PARITY (audit §6): compute the LRT exactly as offline phase2b — chi2 = 2*(ll_full -
        # ll_reduced), p from chi2 with df = number of interaction terms added = (n_eras - 1). The
        # previous live path used R's anova(m0, m1), whose df accounting for the lme4 nested fit
        # differed (df=1 vs the 2 interaction terms a 3-era model adds), shifting borderline p's
        # across 0.05 (e.g. vas@61.5 ZERO_TWO_LEFT: anova p=0.048 -> dependent, but the validated
        # report's 2-df LRT p=0.127 -> stable).
        ll0 = float(m0.logLike); ll1 = float(m1.logLike)
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
    return {
        "available": True, "model": "band x stim_era LRT (glmer logistic, lme4 via pymer4)",
        "formula_reduced": formula_red, "formula_full": formula_full,
        "n": int(m.sum()), "n_clusters": n_clusters,
        "chisq": _f(chisq), "lrt_p": _f(p_lrt),
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
