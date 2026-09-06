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
def _mad_keep(x, k=None):
    """Boolean KEEP-mask under the ONE canonical MAD rule (stats_utils.mad_keep_mask).

    Delegates rather than reimplementing. This function used to carry its own copy of the rule with
    a default of k=3.0, which disagreed with the analytics module's 5 MAD and used the opposite
    polarity convention; the PI consolidated the plate onto a single 5 MAD filter on 2026-08-30.
    ``k=None`` means the canonical threshold (stats_utils.MAD_N_DEFAULT).

    Scale: the features reaching this function are post-daywise-normalization log/z quantities and
    the label is a bounded ordinal score, so both are additive and the rule is applied on the raw
    scale. Do NOT pass a raw-linear power/LSB feature here — that needs scale="log" (see
    stats_utils.mad_outlier_flags).
    """
    from .stats_utils import mad_keep_mask
    return mad_keep_mask(x, n_mad=k, scale="raw")

def pearson_corr_psd_label(psd_feat, label, mad_k=None, rating_group=None, return_extra=False):
    """
    psd_feat: (E, C, F) features AFTER daywise normalization
    label:    (E,)
    mad_k:    MAD outlier rejection applied per (channel,
              frequency) on the feature AND on the label before each correlation, so a single
              artifact session can't drive the Pearson R. None = canonical threshold; 0 disables.
    rating_group: (E,) integer grouping factor, one code per matched pain report (-1 = ungrouped;
              see pipeline.rating_group_from_identity). WHEN GIVEN, `pval` is CLUSTER-ROBUST on
              rating clusters with df = G-1 instead of a naive t with df = n-2. This matters a lot:
              several epochs share one pain report, so the naive df overstates the information by
              roughly the average cluster size. Measured on RCS08 at the selected cell, the naive
              p was 9.24e-10 against 1.56e-04 cluster-robust — an SE inflation of about 1.65x, and
              the BH-significant count over the displayed family fell from 20 cells to 4.
              When omitted, behaviour is unchanged (naive p), so existing callers are unaffected.
    return_extra: also return a dict with `pval_naive`, `n_clusters`, `se_cluster` and `method`,
              so the panel can show the corrected and naive families side by side rather than
              silently swapping one for the other.
    Returns: corr (C,F), pval (C,F)[, extra dict]
    """
    X = np.asarray(psd_feat, dtype=float)
    y = np.asarray(label, dtype=float)
    E, C, F = X.shape
    corr = np.full((C, F), np.nan)
    pval = np.full((C, F), np.nan)
    pval_naive = np.full((C, F), np.nan)
    n_clusters = np.full((C, F), np.nan)
    se_cluster = np.full((C, F), np.nan)
    g_all = None
    if rating_group is not None:
        g_all = np.asarray(rating_group, dtype=int)
        if g_all.size != E:
            raise ValueError(f"rating_group has {g_all.size} entries for {E} epochs")

    yv = np.isfinite(y)
    # Label-side MAD keep-mask (computed once; the feature side is per (c,f) below).
    # `mad_k is None` means USE THE CANONICAL THRESHOLD, not "disabled" — a plain truthiness test
    # here would silently switch the correlation spectrum's outlier rejection off for every default
    # call. Explicit disable is mad_k=0 or mad_k=False.
    _mad_on = not (mad_k is False or (isinstance(mad_k, (int, float)) and float(mad_k) == 0.0))
    y_keep = _mad_keep(y, k=mad_k) if _mad_on else yv

    for c in range(C):
        for f in range(F):
            x = X[:, c, f]
            x_keep = _mad_keep(x, k=mad_k) if _mad_on else np.isfinite(x)
            v = x_keep & y_keep
            n = v.sum()
            if n < 3:
                continue
            # z-score on the SURVIVING samples (robust median/MAD already removed the outliers).
            x_z = (x[v] - np.nanmean(x[v])) / (np.nanstd(x[v]) + 1e-12)
            y_z = (y[v] - np.nanmean(y[v])) / (np.nanstd(y[v]) + 1e-12)
            r = np.mean(x_z * y_z)
            corr[c, f] = r
            # NAIVE p: t on r with df = n-2, where n counts EPOCHS. Kept as an explicit contrast
            # because it is what the panel used to present as its only p-value.
            tstat = r * np.sqrt((n - 2) / (1 - r**2 + 1e-12))
            pval_naive[c, f] = 2 * (1 - t.cdf(abs(tstat), df=n - 2))

            if g_all is None:
                pval[c, f] = pval_naive[c, f]
                continue
            # CLUSTER-ROBUST p on RATING clusters. Several epochs are matched to the same pain
            # report, so the epochs are not independent and df = n-2 overstates the information by
            # roughly the average cluster size. With both variables standardized, r IS the OLS slope
            # of y_z on x_z, so the cluster-robust (Liang-Zeger) sandwich for a simple regression
            # reduces to a few lines: with residuals u = y_z - r*x_z,
            #     Var(r) = c * sum_g (sum_{i in g} x_i u_i)^2 / (sum_i x_i^2)^2
            # and c the usual finite-cluster correction G/(G-1) * (N-1)/(N-2).
            # Done in closed form rather than via statsmodels because this runs per (channel,
            # frequency) — hundreds of cells on every request — and the closed form is validated
            # against statsmodels' cov_type="cluster" in the test suite.
            g = g_all[v]
            ok = g >= 0
            if ok.sum() < 3:
                pval[c, f] = np.nan
                continue
            xz_o, yz_o, g_o = x_z[ok], y_z[ok], g[ok]
            uniq = np.unique(g_o)
            G = uniq.size
            if G < 3:
                # Too few clusters for a sandwich to mean anything. Report NOTHING rather than a
                # number that would be read as inference.
                pval[c, f] = np.nan
                n_clusters[c, f] = G
                continue
            u = yz_o - r * xz_o
            sxx = float(np.sum(xz_o * xz_o))
            if sxx <= 0:
                pval[c, f] = np.nan
                continue
            # per-cluster score sums, vectorized over clusters
            score = xz_o * u
            sums = np.zeros(G, dtype=float)
            np.add.at(sums, np.searchsorted(uniq, g_o), score)
            N = xz_o.size
            corr_factor = (G / (G - 1.0)) * ((N - 1.0) / max(N - 2.0, 1.0))
            var_r = corr_factor * float(np.sum(sums * sums)) / (sxx * sxx)
            se_r = float(np.sqrt(max(var_r, 1e-300)))
            t_cl = r / se_r if se_r > 0 else np.nan
            # df = G - 1, the standard choice for cluster-robust inference (NOT n - 2)
            pval[c, f] = float(2 * t.sf(abs(t_cl), df=G - 1)) if np.isfinite(t_cl) else np.nan
            n_clusters[c, f] = G
            se_cluster[c, f] = se_r

    if return_extra:
        return corr, pval, {"pval_naive": pval_naive, "n_clusters": n_clusters,
                            "se_cluster": se_cluster,
                            "method": ("cluster-robust sandwich on rating clusters, t with df=G-1"
                                       if g_all is not None else "naive t on epochs, df=n-2")}
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

# TD-streaming Welch epoch length (seconds). Set to 30 s so the time-domain PSD is computed over the
# SAME duration as the onboard patient-event / montage snapshot PSDs (~30 s), making the sources
# directly comparable. Recordings shorter than this use all available samples. This value is part of
# the matrix-cache key (bravo_service): changing it invalidates the cache so PSDs are re-Welch'd.
WELCH_MAX_SECONDS = 30.0

# Maximum fraction of a Welch window that may be MISSING (zero-filled) before the window is rejected.
# Background: BrainSenseStream.saveBrainSenseStreams' FixBreaking block concatenates consecutive,
# time-separated TD recordings and ZERO-FILLS the inter-recording gap (up to a 30 s ceiling), marking
# those samples 1 in the recording's `Missing` array (verified firing on real RCS08 data:
# AUDIT_streaming_concatenation_RCS08.md). Those zeros are not neural signal — Welch'ing over them
# deflates broadband power and leaks spectrally. A window whose missing fraction exceeds this
# threshold is dropped (centered path) or flagged (first-window path) rather than returned as a
# trustworthy spectrum. The PowerDomain adapter already drops missing>0 samples; this brings the TD
# Welch path to parity. Part of the TD PSD cache key (bravo_service `_TD_MISSING_VERSION`): changing
# it invalidates the cache so PSDs are re-Welch'd.
WELCH_MAX_MISSING_FRAC = 0.10


def welch_psd_for_instance(channel_data, channel_names, fs, chan_order,
                           f_set=F_SET, max_seconds=WELCH_MAX_SECONDS,
                           missing=None, max_missing_frac=WELCH_MAX_MISSING_FRAC):
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
        Use only the first `max_seconds` of each group. Default 30 s to match the duration of the
        onboard patient-event / montage PSDs (those are ~30 s snapshots), so the TD-streaming Welch
        PSD is computed over the SAME epoch length and the sources are directly comparable. If a
        recording is shorter than 30 s, all available samples are used.
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

    # (a') Missing-aware rejection. `missing` is the recording's per-sample Missing flag (1 where the
    # decoder zero-filled a dropped packet or a FixBreaking concatenation gap). Truncate it the SAME
    # way as the data, then reject the whole window if too much of it is fabricated zeros — Welch over
    # zero-fill biases the spectrum (see WELCH_MAX_MISSING_FRAC). Returning a NaN-filled PSD lets the
    # downstream nan-aware aggregation (nanmean/nanstd across epochs) exclude it cleanly instead of
    # pooling a deflated spectrum.
    if missing is not None:
        miss = np.asarray(missing, dtype=float).ravel()
        if miss.size >= data.shape[-1]:
            miss = miss[:data.shape[-1]]
            if miss.size and float(np.mean(miss > 0)) > float(max_missing_frac):
                return np.full((1, len(chan_order), len(f_set)), np.nan)

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


# Rating-centered TD-streaming Welch
# ============================================================================
# PROBLEM this solves: `welch_psd_for_instance` Welch's only the FIRST `max_seconds` of each
# streaming session and stamps the resulting PSD at the session START time. A long IndefiniteStream
# (hours -> days) therefore contributes a single spectrum from its opening 30 s, timestamped at t0.
# A pain rating sitting in the MIDDLE of that coverage is hours away from t0, so timestamp matching
# reports "no neural match" even though raw time-domain data blankets the rating. (See the Jan-6
# VAS-47 case: TD coverage present, PSD un-matchable.)
#
# FIX: for each rating that falls inside a session's [t0, t0+dur] coverage, cut a `win_s`-long
# window CENTERED on the rating, Welch THAT, and stamp the PSD at the rating's own timestamp (so the
# match offset is ~0 and survives any tolerance window). The window is CLIPPED to the session
# boundary and never slid across it: a rating 5 s before a session end yields an asymmetric
# [rating-15 s, rating+5 s] = 20 s window, not a 30 s window padded from a gap or a different
# session. Welch returns a per-Hz power DENSITY averaged over segments, so a 20 s and a 30 s window
# estimate the SAME spectrum (the shorter one is merely noisier — fewer averaging segments), which
# is why heterogeneous-duration windows pool cleanly after the downstream per-(channel,source)
# z-score. Windows whose clipped duration is below `min_s` are DROPPED (too few Welch segments to
# trust); that rating then matches a montage/event PSD if one is in window, else stays unmatched.
WELCH_CENTERED_MIN_SECONDS = 10.0   # floor: clipped windows shorter than this are not emitted


def welch_rating_centered(channel_data, channel_names, fs, chan_order, centers_s, *,
                          f_set=F_SET, win_s=WELCH_MAX_SECONDS,
                          min_s=WELCH_CENTERED_MIN_SECONDS,
                          missing=None, max_missing_frac=WELCH_MAX_MISSING_FRAC):
    """Welch one rating-centered window per entry in `centers_s`, for ONE streaming recording.

    Parameters
    ----------
    channel_data : array-like
        2-D (n_ch, n_samples) or list of 1-D per-channel arrays for one streaming session.
    channel_names : list[str]
        Channel names aligned to the rows of `channel_data`.
    fs : float
        Sampling rate (Hz).
    chan_order : list[str]
        Canonical channel ordering; output frequency rows are placed at chan_order.index(name).
    centers_s : array-like of float
        Rating offsets, in SECONDS FROM THE SESSION START (i.e. t_rating - t0), one per rating that
        overlaps this session's coverage. May be empty.
    f_set : ndarray
        Frequency grid to interpolate onto (default F_SET).
    win_s : float
        Centered window length (s); default WELCH_MAX_SECONDS (30 s) to match the onboard PSDs.
    min_s : float
        Minimum CLIPPED window length (s). Windows shorter than this (rating near a session edge
        with little coverage on one side) are dropped. Default WELCH_CENTERED_MIN_SECONDS.

    Returns
    -------
    psd : ndarray (K, len(chan_order), len(f_set))
        One PSD per KEPT center, in the same channel layout as `welch_psd_for_instance`.
    used_dur_s : ndarray (K,)
        Actual clipped window length (s) Welch'd for each kept PSD (== win_s for full windows,
        shorter for edge-clipped ones). Carried so the report's TD-epoch stat stays honest.
    kept_mask : ndarray (len(centers_s),) bool
        True where a center produced a PSD (>= min_s of coverage), False where it was dropped.
        Lets the caller map kept PSDs back to the originating ratings.

    Signal processing is IDENTICAL to `welch_psd_for_instance` (4th-order Butterworth high-pass at
    Wn=1/nyq, Welch nperseg<=1024, linear interp onto f_set, NO 60 Hz notch), so a centered TD PSD
    and a first-30 s TD PSD are directly comparable and pool under the same "TD streaming" source.
    """
    fs = float(fs)
    nyq = fs / 2.0
    b, a = butter(4, 1 / nyq, btype='high', analog=False, output='ba')

    data = np.atleast_2d(np.asarray(channel_data, dtype=float))  # (n_ch, N)
    N = data.shape[-1]
    n_ch = len(chan_order)
    f_set = np.asarray(f_set, dtype=float)

    centers = np.asarray(centers_s, dtype=float)
    half = int(round(win_s * fs / 2.0))
    win_n = 2 * half
    min_n = int(round(min_s * fs))

    ci = np.round(centers * fs).astype(int)
    lo = np.clip(ci - half, 0, N)
    hi = np.clip(ci + half, 0, N)
    dur_n = hi - lo
    kept_mask = dur_n >= min_n

    # Missing-aware rejection (per rating-centered window). `missing` is the recording's per-sample
    # Missing flag; a FixBreaking concatenation zero-fills the gap BETWEEN two merged sub-recordings,
    # so a window centered on a PRO that sits near such a gap can be mostly fabricated zeros. Reject
    # any window whose clipped [lo, hi) span is more than `max_missing_frac` missing — its PSD would
    # be a deflated/leaked estimate, not neural signal. Uses a prefix-sum so the per-window fraction
    # is O(1). A rejected center is treated exactly like an under-length one (dropped from kept_mask),
    # so the caller's first-window fallback still gets a chance to match the rating to a cleaner PSD.
    if missing is not None:
        miss = np.asarray(missing, dtype=float).ravel()
        if miss.size >= N:
            miss = (miss[:N] > 0).astype(np.int64)
            csum = np.concatenate(([0], np.cumsum(miss)))   # csum[k] = #missing in [0, k)
            win_missing = csum[hi] - csum[lo]
            frac = np.where(dur_n > 0, win_missing / np.maximum(dur_n, 1), 0.0)
            kept_mask = kept_mask & (frac <= float(max_missing_frac))

    kept_idx = np.nonzero(kept_mask)[0]
    if kept_idx.size == 0:
        return (np.zeros((0, n_ch, len(f_set))), np.zeros((0,)), kept_mask)

    # Precompute the welch->f_set interpolation matrix ONCE on the full-window f-grid, so the
    # full-length windows (the common case) interpolate via a single matmul instead of a per-(row,
    # channel) np.interp loop. Edge-clipped windows have a shorter f-grid and interp individually.
    f_full, _ = welch(np.zeros((1, win_n)), fs=fs, nperseg=min(1024, win_n), axis=-1)
    idx = np.clip(np.searchsorted(f_full, f_set), 1, f_full.size - 1)
    x0 = f_full[idx - 1]; x1 = f_full[idx]
    w = (f_set - x0) / (x1 - x0 + 1e-12)
    interp_M = np.zeros((f_set.size, f_full.size))
    interp_M[np.arange(f_set.size), idx - 1] = 1.0 - w
    interp_M[np.arange(f_set.size), idx] = w

    psd = np.zeros((kept_idx.size, n_ch, len(f_set)))
    used = np.zeros(kept_idx.size)
    row_of = {int(gi): k for k, gi in enumerate(kept_idx)}

    # Channel local-row -> global chan_order slot, computed once.
    slot = [(li, chan_order.index(nm)) for li, nm in enumerate(channel_names) if nm in chan_order]

    # Full-length, in-bounds windows -> one batched Welch + one interp matmul.
    full = kept_mask & (ci - half >= 0) & (ci + half <= N)
    full_idx = np.nonzero(full)[0]
    if full_idx.size:
        starts = ci[full_idx] - half
        gather = starts[:, None] + np.arange(win_n)[None, :]        # (B, win_n)
        batch = data[:, gather]                                     # (n_raw_ch, B, win_n)
        batch = np.moveaxis(batch, 0, 1)                            # (B, n_raw_ch, win_n)
        batch = filtfilt(b, a, batch, axis=-1)
        _, P = welch(batch, fs=fs, nperseg=min(1024, win_n), axis=-1)  # (B, n_raw_ch, F_welch)
        Pi = P @ interp_M.T                                        # (B, n_raw_ch, len(f_set))
        for bk, gi in enumerate(full_idx):
            for li, gslot in slot:
                psd[row_of[int(gi)], gslot, :] = Pi[bk, li, :]
            used[row_of[int(gi)]] = win_n / fs

    # Edge-clipped windows (asymmetric, shorter than win_s) -> individual Welch.
    for gi in kept_idx:
        if full[gi]:
            continue
        seg = data[:, lo[gi]:hi[gi]]
        seg = filtfilt(b, a, seg, axis=-1)
        nper = int(min(1024, seg.shape[-1]))
        f, P = welch(seg, fs=fs, nperseg=max(nper, 8), axis=-1)
        for li, gslot in slot:
            psd[row_of[int(gi)], gslot, :] = np.interp(f_set, f, P[li, :])
        used[row_of[int(gi)]] = seg.shape[-1] / fs

    return psd, used, kept_mask


def _match_to_pro(times_s, pro_times_s, pro_values, tolerance_min, direction="nearest",
                  channels=None, max_per_rating=None):
    """Match each PSD timestamp to a PRO report within the window.

    `times_s` (N,) epoch seconds per PSD; `pro_times_s` / `pro_values` the PRO report timestamps +
    the chosen continuous metric value. Returns (labels (N,), dt_min (N,), pro_idx (N,)): the matched
    continuous PRO value (NaN if no report within tolerance), the signed minutes PRO-minus-PSD, and
    the index of the matched PRO report in the caller's ORIGINAL pro ordering (-1 if unmatched) so
    callers can audit how many neural samples share one PRO (double-dipping).

    `direction`:
      * "nearest"   — PSD-first. Each PSD is matched to its closest PRO in EITHER time direction
                       (symmetric ± tolerance). The intuitive symmetric matcher for discovery.
      * "prior"     — PSD-first FORECASTING semantics: a PSD is matched to the nearest PRO at or
                       after it within the window. Every matched PSD precedes the rating it pairs
                       with. dt_min then >= 0. The causal direction for closed-loop deployment.
      * "pro_first" — Walk PROs (the units of independence), and for each PRO claim up to
                       `max_per_rating` closest PSDs PER CHANNEL within tolerance (either
                       direction). A PSD already claimed by an earlier-walked PRO cannot be
                       claimed again. This maximizes PRO coverage instead of PSD coverage — every
                       PRO with neural coverage in the window contributes, which is the right
                       framing for biomarker discovery (each PRO is one independent observation).
                       Requires `channels` (N,) array and `max_per_rating` (int).
    Vectorized via searchsorted on the sorted PRO times."""
    import numpy as _np
    n = len(times_s)
    lab = _np.full(n, _np.nan)
    dt = _np.full(n, _np.nan)
    pro_idx = _np.full(n, -1, dtype=int)
    pt = _np.asarray(pro_times_s, dtype=float)
    pv = _np.asarray(pro_values, dtype=float)
    order = _np.argsort(pt)             # order[k] = original index of the k-th sorted PRO
    pt, pv = pt[order], pv[order]
    if pt.size == 0 or tolerance_min is None or tolerance_min <= 0:
        return lab, dt, pro_idx
    tol_s = float(tolerance_min) * 60.0

    # --- PRO-FIRST branch ----------------------------------------------------------------------
    # Walk PROs, claim the K closest PSDs PER CHANNEL within tolerance. This inverts the natural
    # PSD-first loop so a PRO with sparse PSD coverage still contributes to discovery — every
    # PRO with neural data in its window emits at least one matched row per channel that has it.
    # Each PSD can be claimed by AT MOST ONE PRO (closeness wins on contention), so the
    # downstream per-(channel, rating) cap is still well-defined.
    if direction == "pro_first":
        if channels is None or max_per_rating is None or int(max_per_rating) < 1:
            # Misuse: fall through to PSD-first nearest so we never silently emit zero matches.
            direction = "nearest"
        else:
            ts_arr = _np.asarray(times_s, dtype=float)
            ch_arr_local = _np.asarray(channels, dtype=object)
            claimed = _np.zeros(n, dtype=bool)
            kpr = int(max_per_rating)
            # Walk PROs in temporal order (pt is already sorted). The `order` array maps the
            # k-th sorted PRO back to the caller's original PRO ordering, which is what
            # pro_idx stores.
            for k in range(pt.size):
                t_pro = pt[k]
                pv_k = pv[k]
                if not _np.isfinite(t_pro) or not _np.isfinite(pv_k):
                    continue
                # Candidates: unclaimed, finite-time PSDs within tol of this PRO.
                near = (_np.isfinite(ts_arr)
                        & ~claimed
                        & (_np.abs(ts_arr - t_pro) <= tol_s))
                if not near.any():
                    continue
                # Per-channel: pick the kpr PSDs closest to t_pro.
                for ch in _np.unique(ch_arr_local[near]):
                    cand = _np.where(near & (ch_arr_local == ch))[0]
                    if cand.size == 0:
                        continue
                    # closeness ranking; ties broken by PSD-time order (deterministic).
                    d_cand = _np.abs(ts_arr[cand] - t_pro)
                    take = cand[_np.argsort(d_cand)[:kpr]]
                    lab[take] = pv_k
                    dt[take] = (t_pro - ts_arr[take]) / 60.0
                    pro_idx[take] = int(order[k])
                    claimed[take] = True
            return lab, dt, pro_idx

    # --- PSD-first branches ("prior", "nearest") -----------------------------------------------
    for i, t in enumerate(times_s):
        if not _np.isfinite(t):
            continue
        pos = int(_np.searchsorted(pt, t))
        best, best_d = -1, None
        if direction == "prior":
            # PSD must precede the rating: consider only PRO times at or after t (pt[k] >= t), and
            # pick the nearest such within tolerance. searchsorted(pt, t) is the first index with
            # pt[k] >= t, so the candidate is pos (and pos itself if pt[pos]==t).
            k = pos
            if 0 <= k < pt.size:
                d = pt[k] - t
                if 0 <= d <= tol_s:
                    best, best_d = k, d
        else:
            for k in (pos - 1, pos):
                if 0 <= k < pt.size:
                    d = abs(pt[k] - t)
                    if d <= tol_s and (best_d is None or d < best_d):
                        best, best_d = k, d
        if best >= 0:
            lab[i] = pv[best]
            dt[i] = (pt[best] - t) / 60.0
            pro_idx[i] = int(order[best])   # map back to caller's original PRO ordering
    return lab, dt, pro_idx


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
    logs, ts, chs, srcs, durs = [], [], [], [], []
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
        # Welch epoch length (s) for this PSD; NaN for sources without a time-domain epoch
        # (event/montage onboard PSDs). Carried so the report can show the TD epoch mean +/- SD.
        d = r.get("dur")
        durs.append(float(d) if d is not None else float("nan"))
    if not logs:
        return None
    return {"logX": np.vstack(logs), "t": np.asarray(ts, dtype=float),
            "channel": np.asarray(chs, dtype=object), "source": np.asarray(srcs, dtype=object),
            "dur": np.asarray(durs, dtype=float), "f_set": f_set}


def build_pooled_detail_from_matrix(mat, pro_times_s, pro_values, *, tolerance_min=60.0,
                                    min_per_group=3, aggregate="all",
                                    max_per_rating=3, refractory_min=2.0,
                                    match_direction="pro_first"):
    """Cheap per-compute step: z-score within (channel, source), match each PSD to the nearest
    continuous PRO within the window, and pack into a scan-ready detail dict. Consumes the cached
    matrix from `psd_rows_to_matrix` so the Welch/interp work is never repeated.

    `aggregate` controls how repeated PSDs that match the SAME pain rating are handled:
      * "all" (default): every matched PSD is its own sample. Many neural samples can share one
        rating (a Streaming burst -> one survey), so the samples are non-independent; the downstream
        AUC should be run rating-group-aware (see `rating_group` in the return). Reported by the
        PRO-independence audit.
      * "one_per_rating": collapse each (channel, matched-rating) cluster to ONE mean feature vector
        BEFORE the scan, so every remaining sample is an independent (channel, rating) observation.
        Unmatched PSDs are dropped (they carry no rating to aggregate on).
    Either way the return carries `rating_group` (N,) — the matched PRO's index per row (-1 if
    unmatched) — so the binary classifier can model the rating as a grouping factor.
    """
    f_set = np.asarray(mat["f_set"], dtype=float)
    F = f_set.size
    X = np.asarray(mat["logX"], dtype=float)
    t_arr = np.asarray(mat["t"], dtype=float)
    ch_arr = np.asarray(mat["channel"], dtype=object)
    src_arr = np.asarray(mat["source"], dtype=object)
    dur_arr = (np.asarray(mat["dur"], dtype=float) if "dur" in mat
               else np.full(t_arr.shape, np.nan))
    # TD-streaming Welch epoch length stats (mean +/- SD over the TD PSDs that carry a finite
    # duration). Computed up-front on the full matrix (before any cap/aggregation reshapes arrays).
    _td_dur = dur_arr[np.array([str(s) == "TD streaming" for s in src_arr]) & np.isfinite(dur_arr)] \
        if dur_arr.size else np.array([])
    td_welch_duration = ({
        "n": int(_td_dur.size),
        "mean_s": round(float(np.mean(_td_dur)), 1),
        "sd_s": round(float(np.std(_td_dur)), 1),
        "min_s": round(float(np.min(_td_dur)), 1),
        "max_s": round(float(np.max(_td_dur)), 1),
    } if _td_dur.size else None)

    # ABSOLUTE linear PSD density (µV²/Hz), recovered from the cached log matrix BEFORE the
    # Per-row source tag (unchanged z-score machinery uses src_arr directly; the short
    # _lsb_tier tag is kept so callers can label rows as td/survey/patient_event in the UI).
    # NOTE: the old Welch-density × k=269 / device-FFT rescale path was REMOVED 2026-06-27 (PI).
    # Per-band LSB for the spectral scan now comes from the shared per-pair cache (CS-1…CS-4 routes,
    # k=352.62 transform / k≈73.63 bridge) via bravo_service._pro_lsb_spectrum_cached, threaded in
    # as `pro_lsb_spectrum_by_channel` to spectral_feature_importance. psd_abs_uv2_per_hz and
    # device_psd_scale_by_channel are no longer emitted from this function.
    src_str = np.array([str(s) for s in src_arr]) if src_arr.size else np.zeros(0, dtype=object)
    _is_td = np.isin(src_str, ("TD streaming", "Montage/survey")) if src_str.size else np.zeros(0, bool)
    _lsb_tier = np.full(src_str.shape, "patient_event", dtype=object)
    _lsb_tier[_is_td] = np.where(src_str[_is_td] == "TD streaming", "td", "survey")

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

    # PRO-first matching gets the channels array and max_per_rating up-front so the matcher can
    # claim PSDs per channel per PRO; PSD-first ignores those args.
    labels, dt_min, pro_idx = _match_to_pro(t_arr, pro_times_s, pro_values, tolerance_min,
                                            direction=match_direction,
                                            channels=ch_arr, max_per_rating=max_per_rating)

    # --- Per-(channel, rating) CAP with refractory window ---------------------------------------
    # A single pain rating can sit within tolerance of a whole BURST of PSDs (the patient triggered
    # streaming many times around one survey), which double-counts that rating in every downstream
    # stat. Cap how many PSDs any one rating absorbs PER CHANNEL: keep the `max_per_rating` matched
    # PSDs closest in time to the rating, but never two closer together than `refractory_min` minutes
    # (so the kept set is temporally spread, not a tight cluster). Dropped PSDs become unmatched
    # (label NaN, pro_idx -1) — they stay in the pool as unmatched samples but feed no rating.
    # When matching is PRO-first the matcher already enforced max_per_rating per channel, so this
    # cap would be a no-op at best and a double-cap at worst — skip it cleanly.
    n_capped_dropped = 0
    if (match_direction != "pro_first") and max_per_rating is not None and max_per_rating >= 1:
        ref_s = float(refractory_min or 0.0) * 60.0
        matched_i = np.where(np.isfinite(labels) & (pro_idx >= 0))[0]
        # group matched rows by (channel, matched-PRO index)
        groups = {}
        for i in matched_i:
            groups.setdefault((ch_arr[i], int(pro_idx[i])), []).append(i)
        for key, idxs in groups.items():
            if len(idxs) <= 1:
                continue
            idxs = np.asarray(idxs)
            # order candidates by closeness to the rating (|dt|), then greedily keep up to N that
            # respect the refractory gap among the KEPT set.
            order_close = idxs[np.argsort(np.abs(dt_min[idxs]))]
            kept_t = []
            for i in order_close:
                if len(kept_t) >= int(max_per_rating):
                    labels[i] = np.nan; dt_min[i] = np.nan; pro_idx[i] = -1; n_capped_dropped += 1
                    continue
                ti = float(t_arr[i])
                if ref_s > 0 and any(abs(ti - tk) < ref_s for tk in kept_t):
                    labels[i] = np.nan; dt_min[i] = np.nan; pro_idx[i] = -1; n_capped_dropped += 1
                    continue
                kept_t.append(ti)

    # --- Optional one-per-rating aggregation ----------------------------------------------------
    # Collapse every (channel, matched-PRO) cluster of z-scored spectra to a single mean vector, so
    # each surviving row is an INDEPENDENT (channel, rating) observation (no double-dipping). Done
    # on the z-scored features (averaging standardized spectra), after the within-source z-score.
    if aggregate == "one_per_rating":
        keep = (pro_idx >= 0) & np.isfinite(labels)
        if keep.any():
            keys = {}
            for i in np.where(keep)[0]:
                keys.setdefault((ch_arr[i], int(pro_idx[i])), []).append(i)
            rows_Xz, rows_ch, rows_src, rows_t, rows_lab, rows_dt, rows_pidx = ([] for _ in range(7))
            rows_Xabs = []
            rows_tier = []
            # LSB-fidelity priority within a (channel, rating) cluster: a real TD reading outranks a
            # montage/survey sweep, which outranks a scaled device-FFT, which outranks an
            # uncalibrated one. The cluster's calibrated-LSB density is the LINEAR mean over ONLY the
            # highest tier present (so a survey or device-PSD reading never dilutes a TD one); the
            # z-scored dB view still averages the whole cluster as before.
            _tier_rank = {"td": 0, "survey": 1, "device_psd_scaled": 2,
                          "device_psd_uncalibrated": 3, "excluded": 9}
            for (ch, pidx), idxs in keys.items():
                idxs = np.asarray(idxs)
                rows_Xz.append(np.nanmean(Xz[idxs], axis=0))
                tiers_here = [_lsb_tier[i] for i in idxs]
                ranks = [_tier_rank.get(t, 9) for t in tiers_here]
                best = min(ranks) if ranks else 9
                if best >= 9:
                    rows_Xabs.append(np.full(F, np.nan)); rows_tier.append("excluded")
                else:
                    sel = idxs[np.asarray(ranks) == best]
                    # Absolute density aggregates in LINEAR space (mean µV²/Hz), so the band integral
                    # × 269 stays a physical LSB. Only the top-tier rows define it.
                    rows_Xabs.append(np.nanmean(Xabs[sel], axis=0))
                    rows_tier.append({0: "td", 1: "survey", 2: "device_psd_scaled",
                                      3: "device_psd_uncalibrated"}[best])
                rows_ch.append(ch)
                su = np.unique(src_arr[idxs])
                rows_src.append(str(su[0]) if su.size == 1 else "aggregated")
                rows_t.append(float(np.nanmean(t_arr[idxs])))
                rows_lab.append(float(labels[idxs[0]]))      # same rating across the cluster
                rows_dt.append(float(np.nanmean(dt_min[idxs])))
                rows_pidx.append(int(pidx))
            Xz = np.vstack(rows_Xz)
            Xabs = np.vstack(rows_Xabs)
            ch_arr = np.asarray(rows_ch, dtype=object)
            src_arr = np.asarray(rows_src, dtype=object)
            _lsb_tier = np.asarray(rows_tier, dtype=object)
            t_arr = np.asarray(rows_t, dtype=float)
            labels = np.asarray(rows_lab, dtype=float)
            dt_min = np.asarray(rows_dt, dtype=float)
            pro_idx = np.asarray(rows_pidx, dtype=int)
        else:
            Xz = Xz[:0]; Xabs = Xabs[:0]; ch_arr = ch_arr[:0]; src_arr = src_arr[:0]
            _lsb_tier = _lsb_tier[:0]
            t_arr = t_arr[:0]; labels = labels[:0]; dt_min = dt_min[:0]; pro_idx = pro_idx[:0]

    chan_order = list(np.unique(ch_arr)) if ch_arr.size else []
    C = len(chan_order)
    N = Xz.shape[0]
    psd_stack = np.full((N, C, F), np.nan)
    for ci, ch in enumerate(chan_order):
        m = ch_arr == ch
        psd_stack[m, ci, :] = Xz[m]

    def _src_breakdown(mask):
        u, c = np.unique(src_arr[mask], return_counts=True)
        return {str(k): int(v) for k, v in zip(u, c)}

    matched_mask = np.isfinite(labels)

    # --- Double-dipping audit (PRO independence) ---------------------------------------------
    # Ideally each neural sample is matched to its OWN pain rating. With a finite match window and
    # many PSDs near one report, several neural samples can collapse onto the SAME PRO, so their
    # contributions to a correlation/AUC are not independent. Report this so it is never silent.
    # Global: across all matched samples (any channel). Per-channel: the unit each correlation
    # actually runs on, so within-channel reuse is what inflates that channel's effective n.
    def _dipstats(mask):
        idx = pro_idx[mask & matched_mask]
        idx = idx[idx >= 0]
        n = int(idx.size)
        if n == 0:
            return {"n_matched": 0, "n_unique_pro": 0, "n_pro_reused": 0,
                    "n_excess_matches": 0, "max_reuse": 0, "pct_nonindependent": 0.0}
        u, c = np.unique(idx, return_counts=True)
        n_unique = int(u.size)
        n_reused = int((c > 1).sum())                 # PRO scores hit by >1 neural sample
        n_excess = n - n_unique                       # duplicate matches (non-independent samples)
        return {
            "n_matched": n,
            "n_unique_pro": n_unique,
            "n_pro_reused": n_reused,                  # how many distinct PROs are double-dipped
            "n_excess_matches": int(n_excess),         # neural samples beyond 1-per-PRO
            "max_reuse": int(c.max()),                 # worst single PRO's reuse count
            "pct_nonindependent": round(100.0 * n_excess / n, 1),
        }

    all_mask = np.ones(N, bool)
    dip_global = _dipstats(all_mask)
    dip_per_channel = {ch: _dipstats(ch_arr == ch) for ch in chan_order}

    # --- Pain-survey usage --------------------------------------------------------------------
    # The matcher is PSD-centric, but the clinician also wants the survey-centric view: of all the
    # pain ratings AVAILABLE in the window-eligible PRO series, how many were actually used (matched
    # to >=1 PSD), and how many were REUSED (matched by >1 PSD, i.e. repeat-assigned). n_pro_total is
    # the count of finite PRO values supplied. Counts collapse across channels (a rating used on two
    # channels is one used survey) AND per the still-matched rows after the cap.
    pv_all = np.asarray(pro_values, dtype=float)
    n_pro_total = int(np.isfinite(pv_all).sum())
    used_idx = pro_idx[np.isfinite(labels) & (pro_idx >= 0)]
    used_unique = np.unique(used_idx) if used_idx.size else np.array([], dtype=int)
    n_pro_used = int(used_unique.size)
    # reuse counts the SAME (channel, rating) cell only once, then tallies ratings matched by more
    # than one DISTINCT (channel, PSD) pairing — i.e. assigned to multiple neural samples.
    if used_idx.size:
        u, c = np.unique(used_idx, return_counts=True)
        n_pro_reused = int((c > 1).sum())     # ratings assigned to >1 neural sample (repeat-assigned)
    else:
        n_pro_reused = 0
    # Mean / median number of PSDs ASSIGNED PER USED PRO -- the headline depth-of-coverage stat
    # for the PRO-first framing. If a rating has multiple channels worth of PSDs, each (channel,
    # PSD) pair counts once (matching the rating_group emission).
    if used_idx.size:
        u, c = np.unique(used_idx, return_counts=True)
        psd_per_pro_mean = float(np.mean(c)); psd_per_pro_median = float(np.median(c))
        psd_per_pro_max = int(c.max())
    else:
        psd_per_pro_mean = psd_per_pro_median = 0.0; psd_per_pro_max = 0
    survey_usage = {
        "n_pro_total": n_pro_total,           # finite pain ratings available
        "n_pro_used": n_pro_used,             # ratings matched to >=1 PSD after the cap
        "n_pro_unused": int(max(0, n_pro_total - n_pro_used)),
        "n_pro_reused": n_pro_reused,         # ratings assigned to >1 neural sample
        "pct_pro_used": (round(100.0 * n_pro_used / n_pro_total, 1) if n_pro_total else 0.0),
        # PRO-first depth stats: per rating that got data, how many neural samples did it get?
        "psd_per_pro_mean": round(psd_per_pro_mean, 2),
        "psd_per_pro_median": round(psd_per_pro_median, 1),
        "psd_per_pro_max": psd_per_pro_max,
    }

    return {
        "f_set": f_set,
        "psd": psd_stack,                    # (N, C, F) — log + within-(channel,source) z-scored
        "feature": psd_stack,
        # Per-row source label ("TD streaming" | "Montage/survey" | "Patient event" | "Snapshot" |
        # "aggregated") and the row's channel.
        # NOTE: psd_abs_uv2_per_hz and device_psd_scale_by_channel were REMOVED 2026-06-27 (PI).
        # The old Welch × k=269 / device-FFT rescale path is superseded by the CS-1…CS-4
        # transform/bridge cache (bravo_service._pro_lsb_spectrum_cached), threaded into
        # spectral_feature_importance as `pro_lsb_spectrum_by_channel`.
        "row_source": np.asarray(src_arr, dtype=object),
        "row_channel": np.asarray(ch_arr, dtype=object),
        # Per-row source tier: "td" | "survey" | "patient_event". Used for UI fidelity display.
        "row_lsb_tier": np.asarray(_lsb_tier, dtype=object),
        "labels": labels,                    # continuous PRO matched within the window (NaN = none)
        "rating_group": pro_idx,             # (N,) matched PRO index per row (-1 unmatched) = the
                                             # grouping factor for rating-aware AUC ("all" mode)
        "aggregate": aggregate,
        "chan_order": chan_order,
        "times": [_dt.datetime.utcfromtimestamp(float(t)).isoformat(sep=" ") for t in t_arr],
        "prelog": True,                      # spectral_feature_importance: do NOT re-log
        "transform": "log_zscore_within_channel_source",
        "pool_meta": {
            "n_psds": int(N),
            "n_matched": int(matched_mask.sum()),
            "aggregate": aggregate,
            "match_direction": match_direction,
            "max_per_rating": (None if max_per_rating is None else int(max_per_rating)),
            "refractory_min": float(refractory_min or 0.0),
            "n_capped_dropped": int(n_capped_dropped),
            "survey_usage": survey_usage,
            "td_welch_duration": td_welch_duration,
            "tolerance_min": (None if tolerance_min is None else float(tolerance_min)),
            "per_source": _src_breakdown(np.ones(N, bool)),
            "per_source_matched": _src_breakdown(matched_mask),
            "per_channel": {ch: int((ch_arr == ch).sum()) for ch in chan_order},
            "median_abs_offset_min": (float(np.nanmedian(np.abs(dt_min)))
                                      if np.isfinite(dt_min).any() else None),
            # PRO-independence audit (double-dipping): global + per-channel.
            "pro_independence": dip_global,
            "pro_independence_per_channel": dip_per_channel,
        },
    }


def compute_psd_pain_correlation(streams, labels, chan_order, f_set=F_SET,
                                 transform="log", rating_group=None):
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

    corr, pval, _pextra = pearson_corr_psd_label(
        feature, np.asarray(labels, dtype=float), rating_group=rating_group, return_extra=True)
    return {
        "f_set": f_set,
        "psd": psd,
        "feature": feature,
        "corr": corr,
        "pval": pval,                       # cluster-robust on ratings when rating_group is given
        # The naive t-on-epochs family, kept alongside rather than discarded so the panel can show
        # the contrast (this is the same pattern the scan already uses with p_pearson/q_pearson).
        "pval_naive": _pextra["pval_naive"],
        "n_clusters_per_cell": _pextra["n_clusters"],
        "se_cluster": _pextra["se_cluster"],
        "pval_method": _pextra["method"],
        "chan_order": list(chan_order),
        "transform": transform,
        "labels": np.asarray(labels, dtype=float),
    }
