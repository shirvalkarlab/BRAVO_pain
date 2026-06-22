"""
Streaming PSD <-> pain biomarker routines.

PROVENANCE
----------
The science in this file is lifted from `dbs_stage2_percept/biomarker_analysis_streaming.ipynb`
(author: Yiyuan Han, Shirvalkar Lab). The intent is to REUSE the existing routines unchanged
so BRAVO can run them on its decoded Percept recordings.

What is verbatim vs. ported:
  * The PSD transform / correlation functions below (`_mad`, `normalize_psd_across_epochs`,
    `pearson_corr_psd_label`, `zscore_per_freq`, `remove_aperiodic`, `relative_power`,
    `align_and_standardize_label`) are copied BYTE-FOR-BYTE from the notebook (cell 19).
  * `welch_psd_for_instance` ports the signal-processing logic of notebook cell 8
    (Butterworth high-pass + Welch nperseg=1024 + interp to F_SET). The Welch parameters and
    interpolation are identical to the notebook. The cell-8 60 Hz IIR notch is INTENTIONALLY
    OMITTED here (PI request: preserve 60 Hz — no powerline notch).
    Two LATENT INDEXING/GLUE issues in the original cell are corrected here and flagged:
      (a) time-axis truncation to 5 min: the notebook used `len(inst_data)` which truncates
          only single-channel (1-D) groups, never multi-channel (2-D) groups. Here we always
          truncate along the time axis (`shape[-1]`), matching the stated "first five minutes"
          intent for every group.
      (b) channel placement: the notebook indexed the per-instance Welch output with a GLOBAL
          channel-order index (`Pxx_tmp[ch_name_idx]` after reassigning `ch_name_idx`), which
          only works when each group already contains all channels in `chan_order` order.
          Here we place each channel using its LOCAL row index, so arbitrary channel subsets
          and orderings (as BRAVO produces) map correctly.
    These are GLUE corrections, not changes to the analysis math. See module-level note.

The transform functions operate on PSD arrays of shape (E, C, F):
    E = epochs (e.g. days / sessions), C = channels, F = frequency bins (== len(F_SET)).
"""

import datetime as _dt

import numpy as np
from scipy.signal import welch, butter, filtfilt
from scipy.stats import t

# Frequency grid the notebook interpolates every PSD onto (cell 8).
# np.linspace(0.95, 100, int(round((100-0.95)/0.98)))  -> ~101 bins at ~0.98 Hz spacing.
F_SET = np.linspace(0.95, 100, int(round((100 - 0.95) / 0.98)))


# ============================================================================
# Transform / correlation functions -- VERBATIM from notebook cell 19
# ============================================================================

# ---------- Day-wise normalization (NaN-safe) ----------
def _mad(a, axis=0, scale_gaussian=True):
    med = np.nanmedian(a, axis=axis, keepdims=True)
    mad = np.nanmedian(np.abs(a - med), axis=axis, keepdims=True)
    if scale_gaussian:
        mad = 1.4826 * mad
    return mad


# --- Normalize PSD across epochs (axis=0) ---
def normalize_psd_across_epochs(psd, method="zscore", scale_gaussian=True):
    """
    psd: (E, C, F)
    method: 'zscore' | 'medianmad' | 'demean'
    scale_gaussian: only used for 'medianmad' (1.4826 factor)
    Returns: (E, C, F) normalized across epochs
    """
    X = np.asarray(psd, dtype=float)
    # sanitize non-finite inputs
    X[~np.isfinite(X)] = np.nan
    # X = np.log10(X)

    if method == "zscore":
        mu = np.nanmean(X, axis=0, keepdims=True)
        sd = np.nanstd(X, axis=0, keepdims=True) + 1e-12
        Z = (X - mu) / sd
        return Z
    elif method == "medianmad":
        med = np.nanmedian(X, axis=0, keepdims=True)
        mad = _mad(X, axis=0, scale_gaussian=scale_gaussian) + 1e-12
        Z = (X - med) / mad
        return Z
    elif method == "demean":
        mu = np.nanmean(X, axis=0, keepdims=True)
        return X - mu
    else:
        raise ValueError("method must be 'zscore'|'medianmad'|'demean'")


# ---------- Pearson correlation (NaN-safe) ----------
def _mad_keep(x, k=3.0):
    """Boolean KEEP-mask: True for finite samples within k median-absolute-deviations of the median.
    Excludes artifact spikes where |x - median| > k*MAD. Returns the finite mask when MAD==0 (all
    equal) or fewer than 3 finite points (MAD undefined). Robust (median/MAD), so a few extreme
    sessions can't drag a Pearson correlation. Mirrors adapter.mad_outlier_mask; duplicated here to
    keep streaming_psd dependency-free."""
    x = np.asarray(x, dtype=float)
    finite = np.isfinite(x)
    if finite.sum() < 3:
        return finite
    med = np.median(x[finite])
    mad = np.median(np.abs(x[finite] - med))
    if mad <= 0:
        return finite
    return finite & (np.abs(x - med) <= k * mad)


def pearson_corr_psd_label(psd_feat, label, mad_k=3.0):
    """
    psd_feat: (E, C, F) features AFTER daywise normalization
    label:    (E,)
    mad_k:    MAD outlier rejection (>=k MADs from the median is dropped) applied per (channel,
              frequency) on the feature AND on the label before each correlation, so a single
              artifact session can't drive the Pearson R. Set None to disable.
    Returns: corr (C,F), pval (C,F)
    """
    X = np.asarray(psd_feat, dtype=float)
    y = np.asarray(label, dtype=float)
    E, C, F = X.shape
    corr = np.full((C, F), np.nan)
    pval = np.full((C, F), np.nan)

    yv = np.isfinite(y)
    # Label-side MAD keep-mask (computed once; the feature side is per (c,f) below).
    y_keep = _mad_keep(y, k=mad_k) if mad_k else yv

    for c in range(C):
        for f in range(F):
            x = X[:, c, f]
            x_keep = _mad_keep(x, k=mad_k) if mad_k else np.isfinite(x)
            v = x_keep & y_keep
            n = v.sum()
            if n < 3:
                continue
            # z-score on the SURVIVING samples (robust median/MAD already removed the outliers).
            x_z = (x[v] - np.nanmean(x[v])) / (np.nanstd(x[v]) + 1e-12)
            y_z = (y[v] - np.nanmean(y[v])) / (np.nanstd(y[v]) + 1e-12)
            r = np.mean(x_z * y_z)
            corr[c, f] = r
            tstat = r * np.sqrt((n - 2) / (1 - r**2 + 1e-12))
            pval[c, f] = 2 * (1 - t.cdf(abs(tstat), df=n - 2))
    return corr, pval


# ------------------------------
# 1) Log-transform + z-score (per channel & frequency across epochs), NaN-safe
# ------------------------------
def zscore_per_freq(psd, eps=1e-12):
    """
    psd: (E, C, F) non-negative power values (Nas allowed)
    Returns: (E, C, F) log10 power, z-scored across epochs per (channel, freq).
             Ignores NaNs when computing mean/std.
    """
    psd = np.asarray(psd, dtype=float)
    # logp = np.log10(psd + eps)

    # nanmean / nanstd across epochs (axis=0)
    mu = np.nanmean(psd, axis=0, keepdims=True)               # (1, C, F)
    sd = np.nanstd(psd, axis=0, keepdims=True) + 1e-12        # avoid /0

    out = (psd - mu) / sd
    return out  # NaNs propagate only where inputs are NaN or all-NaN along axis


# ------------------------------
# 2) Aperiodic (1/f) removal, NaN-safe
#    - Tries specparam/FOOOF per spectrum with freq-masking
#    - Falls back to log-log linear detrend with NaN masks
# ------------------------------
def remove_aperiodic(psd, freqs, use_specparam=True, aperiodic_mode="knee",
                     peak_width_limits=(1, 12), max_n_peaks=6, eps=1e-12):
    """
    psd:   (E, C, F)
    freqs: (F,)
    Returns: (E, C, F) log10 residuals after aperiodic removal, NaN-safe.
             If a spectrum has <2 valid points, residuals are NaN for that row.
    """
    psd = np.asarray(psd, dtype=float)
    freqs = np.asarray(freqs, dtype=float)
    if np.any(freqs <= 0):
        raise ValueError("All freqs must be > 0 for log/aperiodic fitting.")

    E, C, F = psd.shape
    logp = np.log10(psd + eps)
    residuals = np.full_like(logp, np.nan)  # initialize with NaN

    # ---- Try specparam if available
    if use_specparam:
        try:
            from specparam import SpectralModel
            # Fit per (epoch, channel) to allow NaN-masking of freqs
            for e in range(E):
                for c in range(C):
                    y = psd[e, c, :]
                    valid = np.isfinite(y) & np.isfinite(freqs)
                    if valid.sum() < 2:
                        continue
                    sm = SpectralModel(aperiodic_mode=aperiodic_mode,
                                       peak_width_limits=peak_width_limits,
                                       max_n_peaks=max_n_peaks,
                                       verbose=False)
                    # specparam wants linear power (no logs); it logs internally
                    sm.fit(freqs[valid], y[valid])
                    # Build aperiodic fit (in log10 units) on valid bins
                    ap = sm.get_params('aperiodic_params')
                    if aperiodic_mode == 'fixed':        # [offset, exponent]
                        offset, exponent = ap
                        ap_fit_valid = offset - exponent * np.log10(freqs[valid])
                    else:                                 # 'knee': [offset, knee, exponent]
                        offset, knee, exponent = ap
                        ap_fit_valid = offset - np.log10(knee + freqs[valid]**exponent)
                    # residuals (log10)
                    residuals[e, c, valid] = np.log10(y[valid] + eps) - ap_fit_valid
            return residuals
        except Exception:
            # Fall through to simple detrend
            pass

    # ---- Fallback: log-log linear fit per spectrum with NaN masks
    lf = np.log10(freqs)
    for e in range(E):
        for c in range(C):
            y = logp[e, c, :]                      # (F,)
            valid = np.isfinite(y) & np.isfinite(lf)
            if valid.sum() < 2:
                continue
            x = lf[valid]
            X = np.vstack([np.ones_like(x), x]).T  # (n_valid, 2)
            # Solve least squares on valid points
            a, b = np.linalg.lstsq(X, y[valid], rcond=None)[0]
            ap_fit = a + b * lf
            residuals[e, c, valid] = y[valid] - (a + b * lf[valid])
    return residuals


# ------------------------------
# 3) Relative (fractional) power across frequency, NaN-safe
# ------------------------------
def relative_power(psd, axis_freq=2, eps=1e-12):
    """
    psd: (E, C, F)
    Returns: (E, C, F) where each (epoch, channel) sums to ~1 across freq,
             using NaN-ignoring sums. If all-NaN across freq, returns NaN row.
    """
    psd = np.asarray(psd, dtype=float)
    # Sum ignoring NaNs along freq axis
    denom = np.nansum(psd, axis=axis_freq, keepdims=True).astype(float)  # (E,C,1)
    denom = denom + eps  # keep numerical stability even if tiny
    out = psd / denom    # NaNs in psd stay NaN; valid entries scale properly
    return out


# ------------------------------
# Optional: NaN-safe label standardization
# ------------------------------
def align_and_standardize_label(label):
    """
    label: (E,)
    Returns: z-scored label ignoring NaNs; positions that were NaN stay NaN.
    """
    lab = np.asarray(label, dtype=float)
    valid = np.isfinite(lab)
    out = np.full_like(lab, np.nan)
    if valid.sum() > 0:
        m = np.nanmean(lab[valid])
        s = np.nanstd(lab[valid]) + 1e-12
        out[valid] = (lab[valid] - m) / s
    return out


# ============================================================================
# Welch PSD epoching -- PORTED from notebook cell 8 (see PROVENANCE note)
# ============================================================================

def welch_psd_for_instance(channel_data, channel_names, fs, chan_order,
                           f_set=F_SET, max_seconds=5 * 60):
    """
    Compute one PSD epoch, shaped (1, len(chan_order), len(f_set)), from one streaming
    group. Signal-processing: 4th-order Butterworth high-pass at Wn=1/nyq, Welch nperseg=1024,
    linear interp onto `f_set`. (The notebook cell 8's 60 Hz IIR notch is intentionally omitted
    per PI request — 60 Hz is preserved, not attenuated.)

    Parameters
    ----------
    channel_data : array-like
        Either a 2-D array (n_ch, n_samples) or a list of 1-D per-channel arrays for one group.
    channel_names : list[str]
        Channel names aligned to the rows of `channel_data`.
    fs : float
        Sampling rate (Hz), e.g. 250.
    chan_order : list[str]
        Canonical channel ordering; output frequency rows are placed at chan_order.index(name).
    f_set : ndarray
        Frequency grid to interpolate the PSD onto (default F_SET).
    max_seconds : float
        Use only the first `max_seconds` of each group (notebook intent: first 5 minutes).
    """
    fs = float(fs)
    nyq = fs / 2.0
    # Butterworth high-pass (cell 8: `butter(4, 1/nyq, btype='high')`) for DC/drift removal.
    # NOTE: the notebook's 60 Hz IIR notch is INTENTIONALLY OMITTED (per PI request: no powerline
    # notch, so 60 Hz is preserved in the PSD and can be a biomarker). This deviates from cell 8.
    b, a = butter(4, 1 / nyq, btype='high', analog=False, output='ba')

    data = np.atleast_2d(np.asarray(channel_data, dtype=float))  # (n_ch, n_samples)

    # (a) Truncate to the first `max_seconds` along the TIME axis for every group.
    n_keep = int(max_seconds * fs)
    if data.shape[-1] > n_keep:
        data = data[:, :n_keep]

    data = filtfilt(b, a, data, axis=-1)

    # nperseg can't exceed the (possibly short) segment length; guard explicitly so Welch averages
    # over real segments and doesn't emit a "nperseg > input length" warning + degenerate estimate.
    nper = int(min(1024, data.shape[-1]))
    f, Pxx = welch(data, fs=fs, nperseg=max(nper, 8), axis=-1)  # (n_ch, F_welch)
    Pxx = np.array([np.interp(f_set, f, Pxx[i, :]) for i in range(Pxx.shape[0])])

    psd = np.zeros((1, len(chan_order), len(f_set)))
    # (b) Place each channel by its LOCAL row index into the global chan_order slot.
    for local_idx, ch_name in enumerate(channel_names):
        if ch_name not in chan_order:
            continue
        psd[0, chan_order.index(ch_name), :] = Pxx[local_idx]
    return psd


def _match_to_pro(times_s, pro_times_s, pro_values, tolerance_min):
    """Nearest-PRO-within-window match for a vector of PSD timestamps.

    `times_s` (N,) epoch seconds per PSD; `pro_times_s` / `pro_values` the (sorted-by-time) PRO
    report timestamps + the chosen continuous metric value. Returns (labels (N,), dt_min (N,)):
    the matched continuous PRO value (NaN if no report within +/- tolerance) and the signed minutes
    PRO-minus-PSD. Vectorized via searchsorted on the sorted PRO times."""
    import numpy as _np
    n = len(times_s)
    lab = _np.full(n, _np.nan)
    dt = _np.full(n, _np.nan)
    pt = _np.asarray(pro_times_s, dtype=float)
    pv = _np.asarray(pro_values, dtype=float)
    order = _np.argsort(pt)
    pt, pv = pt[order], pv[order]
    if pt.size == 0 or tolerance_min is None or tolerance_min <= 0:
        return lab, dt
    tol_s = float(tolerance_min) * 60.0
    for i, t in enumerate(times_s):
        if not _np.isfinite(t):
            continue
        pos = int(_np.searchsorted(pt, t))
        best, best_d = -1, None
        for k in (pos - 1, pos):
            if 0 <= k < pt.size:
                d = abs(pt[k] - t)
                if d <= tol_s and (best_d is None or d < best_d):
                    best, best_d = k, d
        if best >= 0:
            lab[i] = pv[best]
            dt[i] = (pt[best] - t) / 60.0
    return lab, dt


def build_pooled_psd_detail(psd_rows, pro_times_s, pro_values, *, tolerance_min=15.0,
                            f_set=F_SET, min_per_group=3):
    """Assemble ALL full-spectrum PSDs (time-domain, montage/survey, snapshot, patient events) into
    one scan-ready detail dict, KEYED BY ELECTRODE CHANNEL (DESIGN: channel is the top-level gate),
    each PSD matched to the nearest continuous PRO within the window.

    Every full-spectrum source contributes rows; rows on the SAME bipolar channel pool together no
    matter which source they came from (streaming session, montage sweep, snapshot, patient event).
    Each spectrum is interpolated onto a common `f_set`, taken to 10*log10, then Z-SCORED PER
    FREQUENCY WITHIN (channel, source) so heterogeneous units (uV^2 vs LSB vs FFT bins) become
    comparable before pooling (§8c "within-stream standardization removes the need for unit
    conversion to pool"). Pearson r and single-feature logistic AUC are invariant to this affine
    transform, so a single-source channel is unaffected; the standardization only matters where two
    sources share a channel.

    Parameters
    ----------
    psd_rows : list[dict]
        One dict per (recording, channel) spectrum:
            {"channel": str (canonical bipolar, e.g. "ZERO_THREE_LEFT"),
             "source":  str ("TD streaming" | "Montage/survey" | "Snapshot" | "Patient event"),
             "t":       epoch_s,
             "freq":    array-like, "power": array-like}
    pro_times_s, pro_values : array-like
        Continuous PRO report timestamps (epoch s) and the chosen metric value, aligned.
    tolerance_min : float
        Match window (minutes). None / <=0 -> no PSD carries a label (all NaN).

    Returns
    -------
    dict shaped like compute_psd_pain_correlation's output (so spectral_feature_importance consumes
    it unchanged) with `prelog=True`, channel axis = the bipolar channels found, plus `pool_meta`.
    """
    mat = psd_rows_to_matrix(psd_rows, f_set=f_set)
    if mat is None:
        return None
    return build_pooled_detail_from_matrix(mat, pro_times_s, pro_values,
                                           tolerance_min=tolerance_min, min_per_group=min_per_group)


def psd_rows_to_matrix(psd_rows, *, f_set=F_SET):
    """Interpolate raw per-(recording, channel) spectra onto a common grid -> a CACHEABLE matrix.

    This is the expensive-to-recompute artifact (the upstream Welch/decode feeds it): a fixed-shape
    (N, F) log-power matrix plus parallel channel/source/timestamp arrays. It depends ONLY on the
    recordings — NOT on the match tolerance or the pain metric — so it can be computed once (eagerly,
    while the availability timeline loads) and reloaded on every subsequent compute.

    `psd_rows`: list of {"channel", "source", "t": epoch_s, "freq", "power"}.
    Returns {"logX": (N,F) float, "t": (N,), "channel": (N,) str, "source": (N,) str, "f_set": (F,)}.
    """
    f_set = np.asarray(f_set, dtype=float)
    logs, ts, chs, srcs = [], [], [], []
    for r in psd_rows or []:
        t = r.get("t")
        ch = r.get("channel")
        if t is None or not ch:
            continue
        fr = np.asarray(r.get("freq"), dtype=float)
        pw = np.asarray(r.get("power"), dtype=float)
        ok = np.isfinite(fr) & np.isfinite(pw) & (pw > 0)
        if ok.sum() < 4:
            continue
        logs.append(10.0 * np.log10(np.interp(f_set, fr[ok], pw[ok])))
        ts.append(float(t)); chs.append(str(ch)); srcs.append(str(r.get("source") or "?"))
    if not logs:
        return None
    return {"logX": np.vstack(logs), "t": np.asarray(ts, dtype=float),
            "channel": np.asarray(chs, dtype=object), "source": np.asarray(srcs, dtype=object),
            "f_set": f_set}


def build_pooled_detail_from_matrix(mat, pro_times_s, pro_values, *, tolerance_min=15.0,
                                    min_per_group=3):
    """Cheap per-compute step: z-score within (channel, source), match each PSD to the nearest
    continuous PRO within the window, and pack into a scan-ready detail dict. Consumes the cached
    matrix from `psd_rows_to_matrix` so the Welch/interp work is never repeated."""
    f_set = np.asarray(mat["f_set"], dtype=float)
    F = f_set.size
    X = np.asarray(mat["logX"], dtype=float)
    t_arr = np.asarray(mat["t"], dtype=float)
    ch_arr = np.asarray(mat["channel"], dtype=object)
    src_arr = np.asarray(mat["source"], dtype=object)

    # Within-(channel,source) per-frequency z-score so sources sharing a channel become poolable.
    Xz = X.copy()
    for ch in np.unique(ch_arr):
        for sc in np.unique(src_arr[ch_arr == ch]):
            m = (ch_arr == ch) & (src_arr == sc)
            if m.sum() >= min_per_group:
                mu = np.nanmean(X[m], axis=0); sd = np.nanstd(X[m], axis=0)
                sd[~np.isfinite(sd) | (sd == 0)] = 1.0
                Xz[m] = (X[m] - mu) / sd
            else:
                # too few to standardize -> center only (keeps it on a comparable additive scale)
                Xz[m] = X[m] - np.nanmean(X[m], axis=0)

    labels, dt_min = _match_to_pro(t_arr, pro_times_s, pro_values, tolerance_min)

    chan_order = list(np.unique(ch_arr))
    C = len(chan_order)
    N = X.shape[0]
    psd_stack = np.full((N, C, F), np.nan)
    for ci, ch in enumerate(chan_order):
        m = ch_arr == ch
        psd_stack[m, ci, :] = Xz[m]

    def _src_breakdown(mask):
        u, c = np.unique(src_arr[mask], return_counts=True)
        return {str(k): int(v) for k, v in zip(u, c)}

    matched_mask = np.isfinite(labels)
    return {
        "f_set": f_set,
        "psd": psd_stack,                    # (N, C, F) — log + within-(channel,source) z-scored
        "feature": psd_stack,
        "labels": labels,                    # continuous PRO matched within the window (NaN = none)
        "chan_order": chan_order,
        "times": [_dt.datetime.utcfromtimestamp(float(t)).isoformat(sep=" ") for t in t_arr],
        "prelog": True,                      # spectral_feature_importance: do NOT re-log
        "transform": "log_zscore_within_channel_source",
        "pool_meta": {
            "n_psds": int(N),
            "n_matched": int(matched_mask.sum()),
            "tolerance_min": (None if tolerance_min is None else float(tolerance_min)),
            "per_source": _src_breakdown(np.ones(N, bool)),
            "per_source_matched": _src_breakdown(matched_mask),
            "per_channel": {ch: int((ch_arr == ch).sum()) for ch in chan_order},
            "median_abs_offset_min": (float(np.nanmedian(np.abs(dt_min)))
                                      if np.isfinite(dt_min).any() else None),
        },
    }


def compute_psd_pain_correlation(streams, labels, chan_order, f_set=F_SET,
                                 transform="log"):
    """
    Orchestrates the streaming biomarker: build a per-epoch PSD stack, normalize, and
    correlate each (channel, frequency) feature against a pain label.

    This mirrors the notebook flow cells 8 -> 11 -> 12/14 but keeps each step delegated to
    the verbatim functions above so the analysis math is unchanged.

    Parameters
    ----------
    streams : list of dict
        One entry per epoch with keys:
            "stream_data"    : list of per-group channel arrays (or 2-D (n_ch, n_samples))
            "channel_names"  : list aligned to stream_data groups (list of lists)
            "sample_rate"    : float
        This is exactly the shape `adapter.bravo_timedomain_to_streamdata` emits, and is
        also what `dbs_io.Stream.Stream` exposes (`.stream_data`, `.channel_names`,
        `.sample_rate`).
    labels : array-like, shape (E,)
        Pain label per epoch (e.g. NRS), aligned to `streams`.
    chan_order : list[str]
        Canonical channel ordering.
    transform : str
        One of "log" (10*log10 PSD), "log_zscore", "fooof", "relative_power",
        "relative_power_log". Selects which transformed feature feeds the correlation.

    Returns
    -------
    dict with keys:
        "f_set"      : (F,) frequency grid
        "psd"        : (E, C, F) raw interpolated PSD stack
        "feature"    : (E, C, F) transformed feature actually correlated
        "corr"       : (C, F) Pearson r vs labels
        "pval"       : (C, F) two-tailed p-value
        "chan_order" : list[str]
        "transform"  : str
        "labels"     : (E,) labels used
    """
    psd_epochs = []
    for ep in streams:
        sd = ep["stream_data"]
        cn = ep["channel_names"]
        fs = ep["sample_rate"]
        # A "stream" may hold several groups; average their per-group PSDs into one epoch.
        group_psds = []
        for g_idx, group in enumerate(sd):
            names = cn[g_idx] if isinstance(cn[g_idx], (list, tuple)) else [cn[g_idx]]
            group_psds.append(
                welch_psd_for_instance(group, names, fs, chan_order, f_set=f_set)
            )
        psd_epochs.append(np.nanmean(np.concatenate(group_psds, axis=0), axis=0, keepdims=True))

    psd = np.concatenate(psd_epochs, axis=0)  # (E, C, F)
    psd_nz = psd.copy()
    psd_nz[psd_nz == 0] = np.nan  # cell 11: zeros -> NaN before transforms

    if transform == "log":
        feature = 10 * np.log10(psd_nz)
    elif transform == "log_zscore":
        feature = zscore_per_freq(10 * np.log10(psd_nz))
    elif transform == "fooof":
        feature = remove_aperiodic(psd_nz, f_set)
    elif transform == "relative_power":
        feature = relative_power(psd_nz)
    elif transform == "relative_power_log":
        feature = relative_power(10 * np.log10(psd_nz))
    else:
        raise ValueError(
            "transform must be one of "
            "'log'|'log_zscore'|'fooof'|'relative_power'|'relative_power_log'"
        )

    corr, pval = pearson_corr_psd_label(feature, np.asarray(labels, dtype=float))
    return {
        "f_set": f_set,
        "psd": psd,
        "feature": feature,
        "corr": corr,
        "pval": pval,
        "chan_order": list(chan_order),
        "transform": transform,
        "labels": np.asarray(labels, dtype=float),
    }
