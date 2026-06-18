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
    use_score = score if raw_auc >= 0.5 else -score
    fpr, tpr, _ = metrics.roc_curve(y, use_score)
    if max_points and len(fpr) > max_points:                  # thin for plotting only (keep endpoints)
        idx = np.unique(np.linspace(0, len(fpr) - 1, int(max_points)).astype(int))
        fpr, tpr = fpr[idx], tpr[idx]
    return {"fpr": [float(x) for x in fpr], "tpr": [float(x) for x in tpr],
            "auc": float(max(raw_auc, 1 - raw_auc)), "n_points_full": int(len(df))}


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
