"""
Visualization analytics for the Biomarkers card.

These functions reproduce the figures from Yiyuan Han's notebooks
(threshold_biomarker.ipynb, biomarker_analysis_streaming.ipynb) as JSON-able series the React
card plots. They build on the verbatim science in `threshold_biomarker.py` / `streaming_psd.py`
(per-window threshold by train AUC, test sens/spec/acc/AUC, ROC, Otsu histogram, KMeans cluster
scatter, and the Pearson-R-vs-frequency correlation spectrum).
"""

import numpy as np
import pandas as pd

from .threshold_biomarker import _sens_spec


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
        contacts = f"{digits[0]}⁻-{digits[1]}⁺"   # e.g. 0⁻-2⁺  (cathode/anode)
    elif len(digits) == 1:
        contacts = digits[0]
    else:
        contacts = raw

    reg = region or _DEMO_REGIONS.get(up) or _DEMO_REGIONS.get(raw) or ""
    short = (f"{hemi} {contacts}").strip()
    label = f"{short} · {reg}" if reg else short
    return {"raw": raw, "label": label, "short": short, "hemisphere": hemi_full,
            "contacts": contacts, "region": reg}


def _f(x):
    """Float or None (JSON-safe, NaN -> None)."""
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if not np.isfinite(x) else x


def _otsu_threshold(values, nbins=128):
    """Standard between-class-variance Otsu threshold on a 1-D value array."""
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if values.size == 0:
        return None
    counts, edges = np.histogram(values, bins=nbins)
    centers = (edges[:-1] + edges[1:]) / 2.0
    total = counts.sum()
    if total == 0:
        return float(np.median(values))
    wB = np.cumsum(counts).astype(float)
    sumv = np.cumsum(counts * centers)
    grand = sumv[-1]
    best_var, best_t = -1.0, centers[0]
    for i in range(1, nbins):
        wb = wB[i - 1]
        wf = total - wb
        if wb == 0 or wf == 0:
            continue
        muB = sumv[i - 1] / wb
        muF = (grand - sumv[i - 1]) / wf
        var = wb * wf * (muB - muF) ** 2
        if var > best_var:
            best_var, best_t = var, centers[i]
    return float(best_t)


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
    best_auc, best_thr = -1.0, float(thresholds[0])
    for thr in thresholds:
        cls = (btr["LFP_smoothed"] >= thr).astype(int)
        if cls.nunique() < 2:
            continue
        try:
            a = metrics.roc_auc_score(btr["pain_level"].astype(int).values, cls.values)
            a = max(a, 1 - a)
            if a > best_auc:
                best_auc, best_thr = a, float(thr)
        except Exception:
            continue
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
                             test_days=4, step_days=None, sliding=True):
    """Per-sliding-window metrics over time (mirrors threshold_biomarker.ipynb cells 12 & 14).

    For each window: pick the LFP threshold maximizing train AUC, then on the held-out test fold
    report sensitivity, specificity, accuracy, AUC (roc_auc on the continuous LFP_smoothed), and a
    point-biserial Pearson R (LFP_smoothed vs pain_level). Returns a list of per-window dicts.

    `train_days` is driven by the user's window-months selection. When `sliding=False`, returns a
    single all-data entry (no temporal windows) via `_all_data_window`.
    """
    from sklearn import metrics
    from scipy.stats import pearsonr

    if thresholds is None:
        thresholds = np.arange(60, 200, 1)

    df = cv_df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp", "pain_level"]).sort_values("timestamp").reset_index(drop=True)
    if len(df) == 0:
        return []

    if not sliding:
        return _all_data_window(df, thresholds)

    # Step between windows. Default scales with the training window (step ~ train/14) so a large
    # multi-month window doesn't produce hundreds of near-identical windows (which is slow and
    # over-plots); small windows keep step=1 (unchanged behavior). This only changes how densely
    # the performance curve is SAMPLED in time -- each window's metric is still computed on full data.
    if step_days is None:
        step_days = max(1, int(round(train_days / 14.0)))

    series_start = df["timestamp"].min().normalize()
    series_end = df["timestamp"].max()

    windows = []
    t = series_start + pd.Timedelta(days=train_days + gap_days)
    while t < series_end:
        test_start = t
        test_end = test_start + pd.Timedelta(days=test_days)
        gap_start = test_start - pd.Timedelta(days=gap_days)
        train_start = gap_start - pd.Timedelta(days=train_days)
        t += pd.Timedelta(days=step_days)

        test = df[(df["timestamp"] >= test_start) & (df["timestamp"] < test_end)].dropna(subset=["pain_level"])
        train = df[(df["timestamp"] >= train_start) & (df["timestamp"] < gap_start)].dropna(subset=["pain_level"])
        if len(test) == 0 or len(train) == 0 or train["pain_level"].nunique() < 2:
            continue

        # Class-balance the train fold, then pick threshold by train AUC (cell 14).
        min_count = int(train["pain_level"].value_counts().min())
        btr = pd.concat([train[train["pain_level"] == c].sample(min_count, random_state=42)
                         for c in train["pain_level"].unique()])
        best_auc, best_thr = -1.0, float(thresholds[0])
        for thr in thresholds:
            cls = (btr["LFP_smoothed"] >= thr).astype(int)
            if cls.nunique() < 2:
                continue
            try:
                a = metrics.roc_auc_score(btr["pain_level"].astype(int).values, cls.values)
                a = max(a, 1 - a)
                if a > best_auc:
                    best_auc, best_thr = a, float(thr)
            except Exception:
                continue

        true = test["pain_level"].astype(int).values
        score = test["LFP_smoothed"].astype(float).values
        pred = (score >= best_thr).astype(int)
        sens, spec = _sens_spec(true, pred)
        acc = metrics.accuracy_score(true, pred)

        auc = np.nan
        r = np.nan
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

        windows.append({
            "test_start": test_start.isoformat(),
            "threshold": _f(best_thr), "sens": _f(sens), "spec": _f(spec),
            "acc": _f(acc), "auc": _f(auc), "r": _f(r),
        })
    return windows


def roc_analysis(cv_df):
    """Overall ROC curve (FPR/TPR) + AUC for LFP_smoothed vs pain_level."""
    from sklearn import metrics

    df = cv_df.dropna(subset=["pain_level", "LFP_smoothed"])
    y = df["pain_level"].astype(int).values
    score = df["LFP_smoothed"].astype(float).values
    if len(np.unique(y)) < 2:
        return {"fpr": [], "tpr": [], "auc": None}

    raw_auc = metrics.roc_auc_score(y, score)
    # Orient so the LFP-high = pain-high direction gives AUC >= 0.5 (matches the notebook's max(auc,1-auc)).
    use_score = score if raw_auc >= 0.5 else -score
    fpr, tpr, _ = metrics.roc_curve(y, use_score)
    return {"fpr": [float(x) for x in fpr], "tpr": [float(x) for x in tpr], "auc": float(max(raw_auc, 1 - raw_auc))}


def lfp_distribution(cv_df, bins=40):
    """LFP histogram + Otsu threshold (threshold_biomarker.ipynb cell 9)."""
    lfp = cv_df["LFP_smoothed"].dropna().astype(float).values
    if lfp.size == 0:
        return {"bin_edges": [], "counts": [], "otsu": None}
    counts, edges = np.histogram(lfp, bins=bins)
    return {"bin_edges": [float(x) for x in edges], "counts": [int(x) for x in counts],
            "otsu": _otsu_threshold(lfp)}


def cluster_scatter(cv_df):
    """KMeans pain-level cluster scatter on [left_leg_vas, mpq_sum] (cell 10), if present."""
    if "left_leg_vas" not in cv_df.columns or "mpq_sum" not in cv_df.columns:
        return None
    d = cv_df.dropna(subset=["left_leg_vas", "mpq_sum"])
    if len(d) == 0:
        return None
    return {
        "left_leg_vas": [float(x) for x in d["left_leg_vas"]],
        "mpq_sum": [float(x) for x in d["mpq_sum"]],
        "pain_level": [None if pd.isna(x) else int(x) for x in d["pain_level"]],
    }


def corr_spectrum(td_detail, ignore_band=(55, 66), p_significant=0.001):
    """Pearson-R-vs-frequency correlation spectrum per channel
    (biomarker_analysis_streaming.ipynb cell 12). `td_detail` is the streaming_psd result dict.
    """
    if not td_detail:
        return None
    f = np.asarray(td_detail["f_set"], dtype=float)
    corr = np.asarray(td_detail["corr"], dtype=float)   # (C, F)
    pval = np.asarray(td_detail["pval"], dtype=float)
    chans = td_detail.get("chan_order", [])
    ignore = (f > ignore_band[0]) & (f < ignore_band[1])

    channels = []
    for ci in range(corr.shape[0]):
        fmt = format_channel(chans[ci] if ci < len(chans) else f"ch{ci}")
        r_row = corr[ci].copy()
        p_row = pval[ci].copy()
        r_row[ignore] = np.nan
        # Significant points (for the "+" markers in the notebook).
        sig = [(_f(r_row[k]) if (np.isfinite(p_row[k]) and p_row[k] < p_significant and not ignore[k]) else None)
               for k in range(len(f))]
        channels.append({
            "name": fmt["label"], "short": fmt["short"], "region": fmt["region"], "raw": fmt["raw"],
            "r": [_f(x) for x in r_row],
            "p": [_f(x) for x in p_row],
            "significant": sig,
        })
    return {"freqs": [float(x) for x in f], "channels": channels,
            "transform": td_detail.get("transform", "log"), "p_significant": p_significant}


# --- Time-domain (streaming) analytics -------------------------------------------------------
def psd_spectra(td_detail, db=True):
    """Mean PSD per channel split by pain group (high vs low, by median label).
    Returns {freqs, unit, channels:[{name, short, region, high:[...], low:[...]}]}.
    `td_detail` is the streaming_psd result (psd (E,C,F), labels (E,), f_set, chan_order).
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
        fmt = format_channel(chans[ci] if ci < len(chans) else f"ch{ci}")
        channels.append({"name": fmt["label"], "short": fmt["short"], "region": fmt["region"],
                         "high": grp(hi, ci), "low": grp(lo, ci)})
    return {"freqs": [float(x) for x in f], "unit": "dB" if db else "power", "channels": channels}


def psd_spectrogram(td_detail, times, db=True, fmax=100.0):
    """Per-channel PSD heatmap over sessions (z = freq x session). times: list[str] per epoch."""
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
        fmt = format_channel(chans[ci] if ci < len(chans) else f"ch{ci}")
        channels.append({"name": fmt["label"], "short": fmt["short"], "region": fmt["region"],
                         "z": [[_f(v) for v in row] for row in zt]})
    return {"freqs": [float(x) for x in fz], "times": list(times),
            "unit": "dB" if db else "power", "channels": channels}
