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
    use_score = score if raw_auc >= 0.5 else -score
    fpr, tpr, _ = metrics.roc_curve(y, use_score)
    if max_points and len(fpr) > max_points:                  # thin for plotting only (keep endpoints)
        idx = np.unique(np.linspace(0, len(fpr) - 1, int(max_points)).astype(int))
        fpr, tpr = fpr[idx], tpr[idx]
    return {"fpr": [float(x) for x in fpr], "tpr": [float(x) for x in tpr],
            "auc": float(max(raw_auc, 1 - raw_auc)), "n_points_full": int(len(df))}


def lfp_distribution(cv_df, bins=40):
    """LFP histogram + Otsu threshold (threshold_biomarker.ipynb cell 9)."""
    lfp = cv_df["LFP_smoothed"].dropna().astype(float).values
    if lfp.size == 0:
        return {"bin_edges": [], "counts": [], "otsu": None}
    counts, edges = np.histogram(lfp, bins=bins)
    return {"bin_edges": [float(x) for x in edges], "counts": [int(x) for x in counts],
            "otsu": _otsu_threshold(lfp)}


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
    if finite_sess.sum() < min_sessions:
        return empty
    # Robust time span: some sessions decode to corrupt StartTimes (e.g. ~1677, pandas' min date),
    # which would stretch the grid to centuries and create thousands of empty windows. A percentile
    # clip fails when the corrupt cluster is more than ~1% of sessions, so use a MAD filter on the
    # timestamps (drop |t - median| > 5*MAD) — robust as long as corrupt times are a minority — and
    # hard-cap the window count as a backstop.
    ft = tv[finite_sess]
    med = np.median(ft)
    mad = np.median(np.abs(ft - med))
    tkeep = (np.abs(ft - med) <= 5.0 * mad) if mad > 0 else np.ones(ft.shape, bool)
    ftk = ft[tkeep] if tkeep.any() else ft
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


def corr_spectrum(td_detail, ignore_band=None, p_significant=0.001, region_map=None, n_peaks=6):
    """Pearson-R-vs-frequency correlation spectrum per channel
    (biomarker_analysis_streaming.ipynb cell 12). `td_detail` is the streaming_psd result dict.

    `ignore_band` defaults to None (no 55–66 Hz mask — 60 Hz is preserved, consistent with the
    notch removal). Each channel also gets `peaks`: the strongest |R| local maxima (freq, r) so the
    UI can HIGHLIGHT peaks instead of relying on hover. `region_map` (raw-channel -> region) lets
    the brain region come from the patient's device metadata instead of a static map.
    """
    if not td_detail:
        return None
    from scipy.signal import find_peaks
    f = np.asarray(td_detail["f_set"], dtype=float)
    corr = np.asarray(td_detail["corr"], dtype=float)   # (C, F)
    pval = np.asarray(td_detail["pval"], dtype=float)
    chans = td_detail.get("chan_order", [])
    ignore = np.zeros(len(f), bool) if not ignore_band else ((f > ignore_band[0]) & (f < ignore_band[1]))

    channels = []
    for ci in range(corr.shape[0]):
        raw = chans[ci] if ci < len(chans) else f"ch{ci}"
        fmt = format_channel(raw, region=(region_map or {}).get(raw, ""))
        r_row = corr[ci].copy()
        p_row = pval[ci].copy()
        r_row[ignore] = np.nan
        sig = [(_f(r_row[k]) if (np.isfinite(p_row[k]) and p_row[k] < p_significant and not ignore[k]) else None)
               for k in range(len(f))]
        # Peaks: strongest |R| local maxima, for highlighting (no hover tips needed on the TD plot).
        absr = np.abs(np.nan_to_num(r_row, nan=0.0))
        pk, _props = find_peaks(absr, prominence=0.05)
        pk = sorted(pk, key=lambda k: -absr[k])[:n_peaks]
        peaks = [{"freq": float(f[k]), "r": _f(r_row[k])} for k in sorted(pk)]
        channels.append({
            "name": fmt["label"], "short": fmt["short"], "region": fmt["region"], "raw": fmt["raw"],
            "r": [_f(x) for x in r_row],
            "p": [_f(x) for x in p_row],
            "significant": sig,
            "peaks": peaks,
        })
    return {"freqs": [float(x) for x in f], "channels": channels,
            "transform": td_detail.get("transform", "log"), "p_significant": p_significant}


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
