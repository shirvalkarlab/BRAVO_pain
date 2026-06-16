"""
One-patient, library-mode runner for the biomarker module.

Supports TWO biomarker DATA SOURCES, selected via `source`:
  * "timedomain" : raw 250 Hz BrainSense streaming -> streaming PSD <-> pain correlation
  * "chronic"    : the ~10-min BrainSense Timeline LFP power trend -> sliding-window threshold
  * "both"       : run each independently, then merge onto ONE aligned timeline (the "same page")

End-to-end (library mode, no Django / no React):
    decoded recordings  ->  adapter reshape / chronic tidy-frame
    REDCap PROs         ->  adapter.align_pros (session | chronic) + label
    science routine     ->  streaming_psd OR threshold_biomarker (verbatim, unchanged)
    -> unified `combined` timeline -> write combined_<patient>_<source>.{csv,npz}

Architecture note: source selection is a flat enum + if/elif dispatch, matching this module's
flat-dict / free-function house style (no classes). If a 3rd data source ever appears, promote
this enum to a registry then -- cheap later, not worth carrying now.

DEFERRED HOOKS (intentionally not built here -- see plan):
  * Percept JSON decode: `decode_percept_session` is the attach point. BRAVO decodes a
    clinician session via modules/MedtronicPercept (Percept.py -> BrainSenseStream.py
    `saveBrainSenseStreams`, ChronicBrainSense.py `saveChronicBrainSense`). That path depends
    on the Django models layer, so library-mode runs take already-decoded recordings instead.
  * Django persistence: the `write_combined` step is where
    `DataAnalysis.saveAnalysisProcessedData(Data, type=..., metadata={codeVersion,...},
    recording=...)` would later attach.
  * DRF endpoint + React plot: would consume the `combined` timeline produced here.
"""

import os
import json
import argparse
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from .routines import streaming_psd
from .routines import threshold_biomarker
from .routines import redcap_client
from .routines import stats_utils
from .routines.analytics import format_channel
from . import adapter

# Per-source code versions; stamped into every output file. Bump when a source's math changes.
STREAMING_CODE_VERSION = "streaming_psd-0.1.0"
CHRONIC_CODE_VERSION = "chronic_threshold-0.1.0"
# Back-compat alias (old name referenced the streaming version).
CODE_VERSION = STREAMING_CODE_VERSION


def decode_percept_session(*_args, **_kwargs):
    """Attach point for BRAVO Percept decode (deferred).

    Later this calls modules/MedtronicPercept BrainSenseStream.saveBrainSenseStreams() to
    turn a clinician session JSON into TimeDomain/PowerDomain/Chronic recordings. For now,
    library-mode callers pass already-decoded `recordings` to `run_streaming_biomarker`.
    """
    raise NotImplementedError(
        "Percept JSON decode is a deferred hook. In library mode, pass already-decoded "
        "BRAVO recordings to run_streaming_biomarker(recordings=...). Wiring "
        "modules/MedtronicPercept.BrainSenseStream.saveBrainSenseStreams is a later phase."
    )


def _autocorr_adjusted_pgrid(result):
    """Per-(channel, freq) two-tailed p-grid for the corr-vs-pain test, computed on the
    AUTOCORRELATION-ADJUSTED effective sample size rather than the raw session count.

    Rigor fix (FDR family honesty): daily pain (and log band power) are serially correlated, so the
    iid t-test in streaming_psd (df = n-2) yields anti-conservative p. Feeding those into BH makes
    the whole FDR family — and hence band SELECTION and the fdr_significant flag — anti-conservative.
    Here we recompute each cell's t and df CONSISTENTLY with the Bartlett/Bretherton effective N
    (stats_utils.effective_n), on the SAME transformed feature actually correlated (result['feature'],
    not the raw psd). The block-permutation perm_p in _band_inference remains the headline
    significance for the SELECTED band; this only makes the multiple-comparison gate honest.
    """
    feat = np.asarray(result["feature"], dtype=float)          # (E, C, F) — the correlated feature
    labels = np.asarray(result["labels"], dtype=float)
    corr = np.asarray(result["corr"], dtype=float)
    C, F = corr.shape
    pgrid = np.full((C, F), np.nan)
    yv = np.isfinite(labels)
    from scipy.stats import t as _t
    for c in range(C):
        for f in range(F):
            r = corr[c, f]
            if not np.isfinite(r) or abs(r) >= 1:
                continue
            x = feat[:, c, f]
            v = np.isfinite(x) & yv
            n_eff = stats_utils.effective_n(x[v], labels[v])
            df = n_eff - 2.0
            if not np.isfinite(n_eff) or df < 1:
                continue
            tstat = r * np.sqrt(df / (1 - r ** 2 + 1e-12))
            pgrid[c, f] = float(2 * (1 - _t.cdf(abs(tstat), df=df)))
    return pgrid


def select_biomarker_band(result, q_threshold=0.05, ignore_band=None):
    """Pick the (channel, frequency) with the strongest |corr| vs pain that survives FDR.

    Returns (chan_index, freq_index, r, p, freq_hz, fdr_q, fdr_significant) or None.
    NOTE: the returned `r`/`p`/`fdr_q` are CONDITIONAL on this band being the max|R| winner over the
    whole (channel x freq) grid — i.e. selection-biased (winner's curse). The only selection-corrected
    significance statement is the block-permutation perm_p computed in _band_inference. Callers should
    present r/p/fdr_q as descriptive and lead with perm_p.

    Rigor fix: the per-test p over ~101 freqs x channels is BOTH multiple-comparison inflated AND
    anti-conservative under serial correlation. We therefore (1) recompute each cell's p on the
    autocorrelation-adjusted effective N (_autocorr_adjusted_pgrid) and (2) Benjamini-Hochberg-correct
    that honest p-grid, selecting among bands with FDR q < `q_threshold`. If none survive, we still
    return the strongest |R| band but flag fdr_significant=False.

    `ignore_band`: optional (lo, hi) Hz excluded from SELECTION. Default None — 60 Hz remains
    selectable (per PI request); callers warn when the chosen band falls in the mains region.
    """
    corr = np.asarray(result["corr"], dtype=float)
    # Honest (effective-N) p-grid for the FDR family; the raw iid p stays available for reference.
    pval = _autocorr_adjusted_pgrid(result)
    f_set = np.asarray(result["f_set"], dtype=float)

    finite = np.isfinite(corr) & np.isfinite(pval)
    if ignore_band is not None:
        finite[:, (f_set > ignore_band[0]) & (f_set < ignore_band[1])] = False
    if not finite.any():
        return None
    q = stats_utils.bh_fdr(np.where(finite, pval, np.nan))
    sig = finite & np.isfinite(q) & (q < q_threshold)
    pool = sig if sig.any() else finite                      # fall back to strongest band, flagged
    c_idx, f_idx = np.unravel_index(np.argmax(np.where(pool, np.abs(corr), -np.inf)), pool.shape)
    qv = float(q[c_idx, f_idx]) if np.isfinite(q[c_idx, f_idx]) else float("nan")
    return (int(c_idx), int(f_idx), float(corr[c_idx, f_idx]), float(pval[c_idx, f_idx]),
            float(f_set[f_idx]), qv, bool(sig.any() and sig[c_idx, f_idx]))


# ---------------------------------------------------------------------------
# Per-source branches. Each returns a "SourceRun" dict with a namespaced `timeline`:
#   {source, code_version, timeline (DataFrame), detail (raw science), summary (headline)}
# The timeline columns are prefixed td_* / chronic_* so source="both" merges without collision.
# ---------------------------------------------------------------------------
def run_timedomain_branch(recordings, pro_df, chan_order, *, align="session",
                          label_metric="nrs", label_reduce="min",
                          transform="log", stim_amplitudes=None):
    """Time-domain (250 Hz streaming) PSD<->pain branch -> SourceRun with a td_* timeline.

    `align` is accepted for signature back-compat but no longer changes the timeline: the
    time-domain timeline is always session-resolution (one row per streaming session). The
    chronic spine, when present, comes from the chronic branch.
    """
    # TIME-ORDER the sessions before anything downstream. The raw recording list is NOT sorted by
    # time (~47% of consecutive pairs go backwards), which silently defeats every serial-dependence
    # correction: lag-1 autocorrelation of the scrambled label series collapses to ~0, so the
    # effective-N FDR adjustment (_autocorr_adjusted_pgrid), the Fisher-z CI's effective n, and the
    # block-permutation null's block length all degrade to the iid (anti-conservative) case. Daily
    # pain is in fact strongly autocorrelated (lag-1 ~0.86 once sorted), so honest inference REQUIRES
    # chronological order. Sorting here also fixes the plotted td_* timeline. None StartTimes sort last.
    recordings = sorted(recordings, key=lambda r: (r.get("StartTime") is None, r.get("StartTime") or 0.0))
    streams = adapter.bravo_timedomain_recordings_to_streams(recordings)
    metrics = (label_metric,) if label_metric not in ("nrs", "vas", "mpq_sum") else ("nrs", "vas", "mpq_sum")
    session_df = adapter.align_pros(
        pro_df, target="session", recordings=recordings,
        metrics=metrics, stim_amplitudes=stim_amplitudes,
    )
    label_col = f"{label_metric}_{label_reduce}"
    labels = session_df[label_col].to_numpy(dtype=float)

    result = streaming_psd.compute_psd_pain_correlation(streams, labels, chan_order, transform=transform)
    band = select_biomarker_band(result)

    timeline = pd.DataFrame({
        "time": pd.to_datetime(session_df["session_start"]),
        "date": session_df["session_date"],
    })
    if band is not None:
        c_idx, f_idx, r, p, f_hz, fdr_q, fdr_sig = band
        timeline["td_biomarker_value"] = result["psd"][:, c_idx, f_idx]
        # Numeric contact-pair label (e.g. "R 0⁻-2⁺"), never the raw word form ("ZERO_TWO_RIGHT").
        timeline["td_biomarker_channel"] = format_channel(result["chan_order"][c_idx])["short"]
        timeline["td_biomarker_freq_hz"] = f_hz
        timeline["td_biomarker_r"] = r
        timeline["td_biomarker_p"] = p
    else:
        timeline["td_biomarker_value"] = np.nan
    timeline["td_stim_amplitude"] = session_df.get("stim_amplitude", np.nan)
    for m in metrics:
        for red in ("mean", "min"):
            col = f"{m}_{red}"
            if col in session_df.columns:
                timeline[f"td_{col}"] = session_df[col].to_numpy()

    summary = {"band": band}
    if band is not None:
        c_idx, f_idx, r, p, f_hz, fdr_q, fdr_sig = band
        ch = format_channel(result["chan_order"][c_idx])
        summary.update(_band_inference(result, c_idx, f_idx, r, p, f_hz, fdr_q, fdr_sig,
                                       session_df.get("stim_amplitude")))
        summary.update({"channel": ch["short"], "channel_raw": ch["raw"]})
    return {"source": "timedomain", "code_version": STREAMING_CODE_VERSION,
            "timeline": timeline, "detail": result, "summary": summary}


def _maxabs_corr(X, y, min_n=4):
    """Max |Pearson r| over the columns of X (N x M) vs y (N,), with PAIRWISE deletion of NaNs per
    column (so a feature column with zero->NaN gaps still contributes on its own finite rows, exactly
    like the per-cell selection/FDR). Columns with < min_n valid pairs or zero variance are ignored.
    Fully vectorized so it can be the statistic for the block-permutation family-max null.

    Matching the feature grid used for r/FDR (not the raw psd) makes perm_p a significance statement
    about the SAME quantity that was selected and reported — no cross-space ambiguity."""
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    M = np.isfinite(X) & np.isfinite(y)[:, None]              # (N, K) valid-pair mask per column
    n = M.sum(axis=0).astype(float)                          # per-column valid count
    Xz = np.where(M, X, 0.0)
    yz = np.where(M, y[:, None], 0.0)
    sx = Xz.sum(axis=0); sy = yz.sum(axis=0)
    sxx = (Xz * Xz).sum(axis=0); syy = (yz * yz).sum(axis=0); sxy = (Xz * yz).sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        cov = sxy - sx * sy / n
        vx = sxx - sx * sx / n
        vy = syy - sy * sy / n
        rr = cov / np.sqrt(vx * vy)
    rr = rr[(n >= min_n) & np.isfinite(rr)]
    return float(np.max(np.abs(rr))) if rr.size else np.nan


def _block_perm_maxcorr_pvalue(X, y, n_perm=1000, block=None, seed=0, min_n=4):
    """FULLY VECTORIZED circular-block permutation p-value for the family max|R| statistic with
    pairwise-NaN deletion. Replaces the per-permutation Python loop (block_perm_pvalue + _maxabs_corr
    x n_perm) with a handful of matrix ops.

    `X` (N x K) feature columns, `y` (N,) labels. Subset to label-valid rows UPSTREAM so y is finite;
    then each column's NaN mask is FIXED across permutations (only y is permuted), which lets every
    permutation's column correlations be computed as three matmuls. For P permutations:
        Sxy = Yp @ Xm,  Sy = Yp @ M,  Syy = (Yp*Yp) @ M           (each P x K)
    with Xm = mask*X, M the 0/1 column mask, and the per-column sx/sxx/n/vx precomputed once. The
    Pearson r per (permutation, column) then follows in closed form and we take max|r| over columns.
    Mathematically identical to looping _maxabs_corr over circular_block permutations.

    Returns (empirical_p, n_perm_used)."""
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    N, K = X.shape
    obs = _maxabs_corr(X, y, min_n=min_n)
    if not np.isfinite(obs) or N < 4:
        return (np.nan, 0)
    if block is None:
        block = stats_utils.block_length_for(y, N)
    rng = np.random.default_rng(seed)
    perm = stats_utils.circular_block_perm_matrix(N, block, int(n_perm), rng)   # (P, N)

    M = np.isfinite(X).astype(float)                  # (N, K) fixed column masks (y is finite)
    Xm = np.where(M > 0, X, 0.0)                      # (N, K)
    nj = M.sum(axis=0)                                # (K,)
    sx = Xm.sum(axis=0)                               # (K,)
    sxx = (Xm * Xm).sum(axis=0)                       # (K,)
    with np.errstate(invalid="ignore", divide="ignore"):
        vx = sxx - sx * sx / nj                       # (K,)

    Yp = y[perm]                                      # (P, N) permuted labels
    Sxy = Yp @ Xm                                     # (P, K)
    Sy = Yp @ M                                       # (P, K)
    Syy = (Yp * Yp) @ M                               # (P, K)
    with np.errstate(invalid="ignore", divide="ignore"):
        cov = Sxy - Sy * sx[None, :] / nj[None, :]
        vy = Syy - Sy * Sy / nj[None, :]
        rr = cov / np.sqrt(vx[None, :] * vy)          # (P, K)
    good = (nj >= min_n)[None, :] & np.isfinite(rr)
    rr = np.where(good, np.abs(rr), -np.inf)
    stat = rr.max(axis=1)                             # (P,) family max|R| per permutation
    finite = np.isfinite(stat) & (stat > -np.inf)
    used = int(finite.sum())
    if used == 0:
        return (np.nan, 0)
    ge = int(np.sum(stat[finite] >= obs))
    return ((ge + 1) / (used + 1), used)              # +1: never report p=0


def _band_inference(result, c_idx, f_idx, r, p, f_hz, fdr_q, fdr_sig, stim, n_perm=1000):
    """Honest inference for the selected time-domain band.

    HEADLINE significance = the temporal-block PERMUTATION p (perm_p) for the family max|R|: it is
    the ONLY statistic that corrects for BOTH the multiple comparisons / max|R| band SELECTION
    (winner's curse) AND the temporal autocorrelation. The reported r / p / fdr_q / r_ci are all
    CONDITIONAL on this band being the selected winner and are therefore selection-biased descriptive
    numbers, NOT unbiased effect sizes — callers must present them as such and lead with perm_p.

    All selected-band scalar diagnostics (stim-adjusted partial r, effective N, Fisher-z CI) are
    computed on the SAME transformed feature actually correlated (result['feature']), not the raw
    psd, so they are apples-to-apples with the headline r (rigor fix). The family-wide permutation
    null runs on the same FEATURE grid (max|R| over every channel x freq), matching r/FDR.
    """
    feat = np.asarray(result["feature"], dtype=float)        # (N, C, F) — the correlated feature
    labels = np.asarray(result["labels"], dtype=float)
    bandpow = feat[:, c_idx, f_idx]                          # feature slice == what produced r
    valid = np.isfinite(labels) & np.isfinite(bandpow)
    n = int(valid.sum())

    # Stim-adjusted partial correlation. Only meaningful when stim amplitude was actually recorded
    # AND varies (you cannot regress out a confound that is missing or constant). Distinguish those
    # cases from a genuine "adjustment shrank it to ~0" so the card never misreads a null.
    stim_adj = None
    stim_note = "no stim-amplitude data recorded for these sessions"
    if stim is not None:
        stim_arr = np.asarray(stim, dtype=float)
        sm = valid & np.isfinite(stim_arr)
        if sm.sum() < 4:
            stim_note = "no stim-amplitude data recorded for these sessions"
        elif np.nanstd(stim_arr[sm]) == 0:
            stim_note = "stim amplitude constant across sessions — no confound to adjust for"
        else:
            stim_adj = stats_utils.partial_corr(bandpow, labels, stim_arr)
            stim_note = None if (stim_adj is not None and np.isfinite(stim_adj)) else "stim adjustment degenerate"
    n_eff = stats_utils.effective_n(bandpow[valid], labels[valid])
    r_lo, r_hi = stats_utils.fisher_z_ci(r, n_eff)

    # CI honesty notes. (a) When n_eff falls in [2,4) the Fisher-z CI is undefined (n<4 guard) even
    # though n_effective prints a number — say why instead of showing a blank interval silently.
    # (b) The interval is conditional on the selected band and is NOT corrected for the max|R| search
    # (winner's curse) — perm_p is the selection-aware statement. (c) n_effective barely deflates from
    # n when band power is near-white at the session-sampling cadence; on irregularly-spaced sessions
    # that under-counts day-to-day pain persistence, so treat it as an UPPER bound.
    ci_note = None
    if np.isfinite(n_eff) and not (np.isfinite(r_lo) and np.isfinite(r_hi)):
        ci_note = "effective n < 4: too little independent information for a Fisher-z CI"
    else:
        notes = ["conditional on the selected band; not corrected for the max|R| band search (see perm p)"]
        if np.isfinite(n_eff) and n > 0 and n_eff >= 0.95 * n:
            notes.append("effective n ≈ n (band power near-white at session cadence); on irregular "
                         "sampling this is an upper bound, so the CI may be optimistically narrow")
        ci_note = "; ".join(notes)

    # Instrumental-line heuristic: a sharp peak confined to a single ~1 Hz frequency bin on a
    # stimulated lead can be a stim/sensing line artifact rather than a broad neural rhythm. Flag
    # when |R| at the selected freq is much larger than at its immediate neighbours.
    f_set = np.asarray(result["f_set"], dtype=float)
    corr_abs = np.abs(np.asarray(result["corr"], dtype=float)[c_idx])
    narrow_peak = False
    if 0 < f_idx < len(f_set) - 1:
        nb = np.nanmax([corr_abs[f_idx - 1], corr_abs[f_idx + 1]])
        narrow_peak = bool(np.isfinite(nb) and corr_abs[f_idx] > 0 and nb < 0.5 * corr_abs[f_idx])

    # Family-max permutation null over the FULL FEATURE grid (every channel x freq), so the max|R|
    # statistic controls for the band SEARCH on the SAME transformed feature that produced r and the
    # FDR — no raw-vs-feature space mismatch. _maxabs_corr does pairwise NaN deletion per column, so
    # feature cells with zero->NaN gaps still contribute on their finite rows (like selection/FDR).
    # Restricts to label-valid rows; the block-permutation block length comes from the (now time-
    # ordered) label autocorrelation, so the null preserves serial dependence.
    perm_valid = np.isfinite(labels)
    perm_p, perm_used = (np.nan, 0)
    if perm_valid.sum() >= 4:
        X = feat.reshape(feat.shape[0], -1)[perm_valid]
        yv = labels[perm_valid]
        perm_p, perm_used = _block_perm_maxcorr_pvalue(X, yv, n_perm=n_perm, seed=0)
    return {
        "freq_hz": f_hz, "r": r, "p": p, "fdr_q": fdr_q, "fdr_significant": bool(fdr_sig),
        "selection_biased": True,   # r/p/fdr_q/r_ci are conditional on the max|R| winner
        "stim_adjusted_r": (None if stim_adj is None or not np.isfinite(stim_adj) else float(stim_adj)),
        "stim_adjusted_note": stim_note,
        "n": n, "n_effective": (round(float(n_eff), 1) if np.isfinite(n_eff) else None),
        "r_ci": [None if not np.isfinite(r_lo) else r_lo, None if not np.isfinite(r_hi) else r_hi],
        "r_ci_note": ci_note,
        "perm_p": (None if not np.isfinite(perm_p) else float(perm_p)), "perm_n": int(perm_used),
        "mains_region_warning": bool(55.0 <= f_hz <= 66.0),
        "narrow_peak_warning": narrow_peak,
    }


def run_powerdomain_branch(pro_df, *, chronic, label_metric="nrs", pain_cutoff=None,
                           label_strategy="kmeans", kmeans_features=("left_leg_vas", "mpq_sum"),
                           thresholds=None, train_days=7, gap_days=1, test_days=2, sliding=True):
    """Power-domain (band-power-over-time) sliding-window threshold branch -> SourceRun with a
    powerdomain_* timeline. The "power domain" is the complement to the time domain: it merges the
    ~10-min Chronic LFP-power timeline with the per-session BrainSense Power-Domain band power
    (both already concatenated into `chronic` upstream as chronic-shaped power dicts).

    `chronic` is one chronic-shaped power recording dict OR a list of them (concatenated +
    time-sorted into one long trend -- the detector needs ~train+gap+test days of data).
    `label_strategy` ("kmeans" | "cutoff") selects the pain_level labeler; "kmeans" matches the
    source notebook (clusters [left_leg_vas, mpq_sum]) and falls back to "cutoff" if those
    columns are absent from pro_df.
    """
    if chronic is None:
        raise ValueError('a "powerdomain" source requires `chronic` (a power recording or list).')
    cv_df = adapter.bravo_chronic_to_lfp_df(chronic, pro_df, label_metric=label_metric,
                                            pain_cutoff=pain_cutoff, label_strategy=label_strategy,
                                            kmeans_features=kmeans_features)
    detail = threshold_biomarker.run_chronic_threshold(
        cv_df, thresholds=thresholds, train_days=train_days, gap_days=gap_days, test_days=test_days,
        sliding=sliding)
    thr = detail.get("mean_thr_sens", np.nan)

    lfp_s = cv_df["LFP_smoothed"].to_numpy(dtype=float)
    timeline = pd.DataFrame({
        "time": pd.to_datetime(cv_df["timestamp"]),
        "date": pd.to_datetime(cv_df["timestamp"]).dt.date,
        "powerdomain_biomarker_value": lfp_s,
        "powerdomain_lfp_raw": cv_df["LFP"].to_numpy(dtype=float),
        "powerdomain_threshold": thr,
        "powerdomain_stim_amplitude": cv_df["stim_amplitude"].to_numpy(dtype=float),
        "powerdomain_pain_level": cv_df["pain_level"].to_numpy(dtype=float),
    })
    timeline["powerdomain_pred"] = (lfp_s >= thr).astype(float) if np.isfinite(thr) else np.nan
    timeline[f"powerdomain_{label_metric}"] = cv_df[label_metric].to_numpy(dtype=float)

    # run_sliding_window_dual is a DUAL detector: it returns two independent operating points
    # -- a sensitivity-optimized threshold (mean_thr_sens, with mean_test_*_sens metrics) and a
    # specificity-optimized threshold (mean_thr_spec, with mean_test_*_spec metrics). The headline
    # summary reports ONE self-consistent operating point: the sens-objective threshold and the
    # metrics ACTUALLY achieved at THAT threshold (so `spec` is mean_test_spec_SENS, not _spec --
    # pairing mean_thr_sens with mean_test_spec_spec would overstate specificity, since no single
    # threshold attains both). chronic_threshold / chronic_pred above also use mean_thr_sens, so
    # they stay consistent with this summary. The spec-objective point is preserved explicitly.
    sens = detail.get("mean_test_sens_sens", np.nan)
    spec = detail.get("mean_test_spec_sens", np.nan)
    summary = {
        "objective": "sens",
        "best_threshold": thr,                                   # mean_thr_sens
        "sens": sens,                                            # sens at best_threshold
        "spec": spec,                                            # spec at best_threshold (self-consistent)
        "acc": detail.get("mean_test_acc_sens", np.nan),         # raw acc at best_threshold
        "n_windows": detail.get("n_windows", 0),
        # The alternative (specificity-optimized) operating point, kept explicit, not mixed in:
        "spec_objective_threshold": detail.get("mean_thr_spec", np.nan),
        "spec_objective_sens": detail.get("mean_test_sens_spec", np.nan),
        "spec_objective_spec": detail.get("mean_test_spec_spec", np.nan),
        "spec_objective_acc": detail.get("mean_test_acc_spec", np.nan),
    }
    # HONEST metrics for an imbalanced binary test set. NOTE the reference sets differ and are
    # labeled as such (rigor review): sens/spec/balanced_accuracy come from the held-out sliding
    # TEST folds (cross-validated), while prevalence/chance_accuracy below are over the WHOLE series
    # (a coarse baseline, not the test-fold reference).
    pl = cv_df["pain_level"].to_numpy(dtype=float)
    n_pos = int(np.nansum(pl == 1)); n_neg = int(np.nansum(pl == 0))
    summary.update(stats_utils.balanced_metrics(sens, spec, n_pos, n_neg))
    summary["metrics_reference_note"] = (
        "sens/spec/balanced_accuracy are held-out sliding TEST-fold (cross-validated) metrics; "
        "prevalence/chance_accuracy are over the WHOLE series, not the test folds.")

    def _auc(labels01, score):
        """Directed ROC AUC (sklearn 'higher score -> positive class', matching pred = lfp_s>=thr).
        Returns None if degenerate. NOT folded by max(auc, 1-auc): AUC<0.5 honestly signals an
        inverse/null association consistent with the directed detector."""
        try:
            from sklearn.metrics import roc_auc_score
            mm = np.isfinite(labels01) & np.isfinite(score)
            if mm.sum() >= 2 and len(set(labels01[mm])) == 2:
                return float(roc_auc_score(labels01[mm].astype(int), score[mm]))
        except Exception:
            pass
        return None

    # DIRECTED, threshold-free AUC of the continuous biomarker vs pain. This is ALWAYS in-sample
    # (computed over the whole series with no train/test split), regardless of `sliding` — labeled
    # accordingly so it is never read as an out-of-fold generalization estimate. (rigor review #6/#7)
    summary["auc_in_sample"] = _auc(pl, lfp_s)
    summary["auc"] = summary["auc_in_sample"]   # back-compat key; same directed, in-sample value
    summary["auc_is_in_sample"] = True
    # Overfit / generalization-gap flag: strong in-sample discrimination NOT reproduced by the
    # cross-validated thresholded accuracy is the signature of an over-optimistic in-sample AUC.
    ba = summary.get("balanced_accuracy"); ch = summary.get("chance_accuracy")
    if (summary["auc_in_sample"] is not None and summary["auc_in_sample"] > 0.65
            and ba is not None and ch is not None and ba <= ch + 0.02):
        summary["overfit_warning"] = (
            f"In-sample AUC={summary['auc_in_sample']:.2f} is not reproduced out-of-fold "
            f"(cross-validated balanced accuracy={ba:.2f} ≈ chance={ch:.2f}); the in-sample AUC is "
            f"optimistic — treat balanced accuracy as the generalization estimate.")
    else:
        summary["overfit_warning"] = None

    # TWO-SOURCE BATCH/SCALE CONFOUND DIAGNOSTIC (rigor review #8). The power-domain series merges two
    # sensing modalities in RAW units (Chronic ~10-min LFP power vs per-session Power-Domain band
    # power, ~8x scale gap). If the LFP scale separates the sources AND pain prevalence differs by
    # source (different collection periods), a single pooled threshold/AUC can separate SOURCE rather
    # than pain — manufacturing discrimination. Surface both AUCs and a warning.
    summary["batch_confound_warning"] = None
    if "source" in cv_df.columns:
        src = cv_df["source"].astype(str).to_numpy()
        uniq = sorted({s for s in src if s and s != "nan"})
        if len(uniq) >= 2:
            is_pd = (src == "powerdomain").astype(float)   # source identity as a 0/1 label
            auc_src_lfp = _auc(is_pd, lfp_s)               # does LFP scale separate the sources?
            auc_src_pain = _auc(is_pd, pl)                 # does pain prevalence differ by source?
            # Source identity has NO inherent positive direction, so the strength of separation is the
            # UNDIRECTED max(auc, 1-auc): an AUC of 0.21 is as separating as 0.79. Directed AUCs are
            # kept for transparency, but the warning thresholds on the undirected separation so a
            # strongly-separating below-0.5 AUC is not silently missed.
            sep_lfp = None if auc_src_lfp is None else max(auc_src_lfp, 1.0 - auc_src_lfp)
            sep_pain = None if auc_src_pain is None else max(auc_src_pain, 1.0 - auc_src_pain)
            summary["sources"] = uniq
            summary["source_vs_lfp_auc"] = auc_src_lfp
            summary["source_vs_pain_auc"] = auc_src_pain
            summary["source_vs_lfp_separation"] = sep_lfp
            summary["source_vs_pain_separation"] = sep_pain
            if (sep_lfp is not None and sep_pain is not None
                    and sep_lfp >= 0.75 and sep_pain >= 0.60):
                summary["batch_confound_warning"] = (
                    f"Merged-source batch/scale confound: the two unnormalized sensing modalities "
                    f"({', '.join(uniq)}) are separable by LFP scale (source↔LFP separation="
                    f"{sep_lfp:.2f}) and differ in pain prevalence (source↔pain separation="
                    f"{sep_pain:.2f}); the pooled AUC may reflect cross-source separation rather "
                    f"than within-source biomarker–pain coupling. Interpret per source.")

    # Label provenance + a threshold-free association against the CONTINUOUS pain metric, so AUC /
    # balanced-accuracy are not read as detection against an external gold standard (pain_level is an
    # UNSUPERVISED KMeans dichotomization of subjective PROs). (rigor review, detector lens)
    summary["label_strategy"] = label_strategy
    summary["kmeans_features"] = list(kmeans_features)
    summary["lfp_vs_continuous_pain_spearman"] = None
    if label_metric in cv_df.columns:
        cont = cv_df[label_metric].to_numpy(dtype=float)
        mm = np.isfinite(cont) & np.isfinite(lfp_s)
        if mm.sum() >= 4 and np.nanstd(cont[mm]) > 0 and np.nanstd(lfp_s[mm]) > 0:
            from scipy.stats import spearmanr
            rho, _p = spearmanr(lfp_s[mm], cont[mm])
            summary["lfp_vs_continuous_pain_spearman"] = float(rho) if np.isfinite(rho) else None
    summary["pain_level_note"] = (
        "AUC/accuracy measure agreement of the LFP biomarker with an UNSUPERVISED KMeans "
        "dichotomization of subjective PROs (" + ", ".join(kmeans_features) + "), not detection of "
        "an external ground truth.") if label_strategy == "kmeans" else None

    # When the sliding window is OFF the THRESHOLD is fit and scored on the SAME data (in-sample) —
    # flag it for the threshold metrics. (The AUC is separately ALWAYS in-sample; see auc_in_sample.)
    summary["in_sample"] = (not sliding)
    summary["note"] = ("All-data fit: threshold chosen and scored on the same data (in-sample, "
                       "optimistic — not a generalization estimate)." if not sliding else None)
    return {"source": "powerdomain", "code_version": CHRONIC_CODE_VERSION,
            "timeline": timeline, "detail": detail, "summary": summary,
            # Expose the full-resolution tidy frame so the analytics step can reuse it instead of
            # rebuilding (a second KMeans + Savitzky-Golay over 100k+ rows). Not serialized.
            "cv_df": cv_df}


# Back-compat: the chronic branch was renamed to the power-domain branch (chronic timeline is now
# merged with per-session power-domain band power upstream). Keep the old name as an alias.
run_chronic_branch = run_powerdomain_branch


def run_biomarker(recordings, pro_df, chan_order, *, source="timedomain", chronic=None,
                  align="session", label_metric="nrs", label_reduce="min", transform="log",
                  pain_cutoff=None, label_strategy="kmeans",
                  kmeans_features=("left_leg_vas", "mpq_sum"),
                  thresholds=None, train_days=7, gap_days=1, test_days=2,
                  stim_amplitudes=None, sliding=True):
    """
    Run biomarker identification with a selectable data source.

    source : {"timedomain", "powerdomain", "both"}  ("chronic" accepted as alias of "powerdomain")
        "timedomain"  -> 250 Hz streaming PSD<->pain (needs `recordings`).
        "powerdomain" -> band-power-over-time threshold detector (needs `chronic`: the merged
                         Chronic timeline + per-session Power-Domain band power as chronic-shaped dicts).
        "both"        -> run each independently and merge onto one timeline.

    Returns
    -------
    dict: {"source", "timedomain": SourceRun|None, "powerdomain": SourceRun|None,
           "combined": DataFrame}  -- `combined` is the unified, NaN-tolerant same-page timeline.
    """
    if source == "chronic":           # back-compat alias
        source = "powerdomain"
    if source not in ("timedomain", "powerdomain", "both"):
        raise ValueError('source must be "timedomain", "powerdomain", or "both"')

    def _td():
        return run_timedomain_branch(recordings, pro_df, chan_order, align=align,
                                     label_metric=label_metric, label_reduce=label_reduce,
                                     transform=transform, stim_amplitudes=stim_amplitudes)

    def _power():
        return run_powerdomain_branch(pro_df, chronic=chronic, label_metric=label_metric,
                                      pain_cutoff=pain_cutoff, label_strategy=label_strategy,
                                      kmeans_features=kmeans_features, thresholds=thresholds,
                                      train_days=train_days, gap_days=gap_days, test_days=test_days,
                                      sliding=sliding)

    td = ch = None
    if source == "both":
        # The two branches are independent (separate data sources + science), so compute them
        # concurrently — "both" wall-clock becomes max(td, powerdomain) instead of their sum.
        with ThreadPoolExecutor(max_workers=2) as ex:
            fut_td, fut_power = ex.submit(_td), ex.submit(_power)
            td, ch = fut_td.result(), fut_power.result()
    elif source == "timedomain":
        td = _td()
    elif source == "powerdomain":
        ch = _power()

    combined = adapter.merge_timelines(td["timeline"] if td else None,
                                       ch["timeline"] if ch else None)
    return {"source": source, "timedomain": td, "powerdomain": ch, "combined": combined}


def run_streaming_biomarker(recordings, pro_df, chan_order, *, align="session",
                            label_metric="nrs", label_reduce="min",
                            transform="log", chronic=None, stim_amplitudes=None):
    """Back-compat shim -> run_biomarker(source="timedomain").

    Preserves the original return shape {"result", "band", "combined"} so existing callers
    and tests stay green.
    """
    run = run_biomarker(recordings, pro_df, chan_order, source="timedomain", align=align,
                        label_metric=label_metric, label_reduce=label_reduce,
                        transform=transform, stim_amplitudes=stim_amplitudes)
    td = run["timedomain"]
    return {"result": td["detail"], "band": td["summary"]["band"], "combined": run["combined"]}


def write_combined(run_output, patient, out_dir="."):
    """Write the unified `combined` timeline + per-source detail as flat files.

    Stems as `combined_<patient>_<source>.{csv,npz}` and tags each present branch's
    code_version into the npz. This is the deferred Django-persistence attach point.
    Returns (csv_path, npz_path).
    """
    os.makedirs(out_dir, exist_ok=True)
    source = run_output.get("source", "timedomain")
    stem = f"combined_{patient}_{source}"
    csv_path = os.path.join(out_dir, f"{stem}.csv")
    npz_path = os.path.join(out_dir, f"{stem}.npz")

    run_output["combined"].to_csv(csv_path, index=False)

    arrays = {"source": source}
    td = run_output.get("timedomain")
    ch = run_output.get("powerdomain") or run_output.get("chronic")  # back-compat key
    if td is not None:
        r = td["detail"]
        arrays.update({
            "timedomain_code_version": td["code_version"],
            "td_f_set": r["f_set"], "td_psd": r["psd"], "td_corr": r["corr"], "td_pval": r["pval"],
            "td_chan_order": np.array(r["chan_order"], dtype=object),
            "td_transform": r["transform"], "td_labels": r["labels"],
            "td_band": np.array(td["summary"]["band"], dtype=object) if td["summary"]["band"] else np.array([]),
        })
    if ch is not None:
        arrays.update({
            "chronic_code_version": ch["code_version"],
            "chronic_summary": np.array(list(ch["summary"].items()), dtype=object),
            "chronic_detail": np.array(list(ch["detail"].items()), dtype=object),
        })
    np.savez(npz_path, **arrays)
    return csv_path, npz_path


def _load_chan_order(pt_config_path):
    cfg = json.load(open(pt_config_path, "r"))
    return list(cfg["channel_names"].keys())


def _load_chronic_npz(path):
    blob = np.load(path, allow_pickle=True)["chronic"]
    return blob.item() if getattr(blob, "ndim", None) == 0 else list(blob)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Biomarker identification (library mode): time-domain | chronic | both.")
    ap.add_argument("--patient", required=True, help="Patient id, e.g. RCS08")
    ap.add_argument("--source", choices=["timedomain", "chronic", "both"], default="timedomain")
    ap.add_argument("--align", choices=["session", "chronic"], default="session")
    ap.add_argument("--pro-csv", required=True, help="Processed PRO CSV (pt_data/<pt>_redcap_proc.csv)")
    ap.add_argument("--pt-config", required=True, help="pt_config/<pt>_config.json (for channel order)")
    ap.add_argument("--recordings-npz",
                    help="NPZ with key 'recordings' = list of BRAVO TimeDomain dicts (timedomain/both).")
    ap.add_argument("--chronic-npz",
                    help="NPZ with key 'chronic' = a Chronic recording dict or list (chronic/both).")
    ap.add_argument("--transform", default="log")
    ap.add_argument("--label-metric", default="nrs")
    ap.add_argument("--label-strategy", choices=["kmeans", "cutoff"], default="kmeans",
                    help="Chronic pain_level labeler: 'kmeans' (notebook: clusters "
                         "[left_leg_vas, mpq_sum]) or 'cutoff' (single-metric threshold).")
    ap.add_argument("--pain-cutoff", type=float, default=None,
                    help="Chronic 'cutoff' strategy threshold (default: median of the metric).")
    ap.add_argument("--out-dir", default=".")
    args = ap.parse_args(argv)

    chan_order = _load_chan_order(args.pt_config)
    pro_df = redcap_client.load_processed_pro_csv(args.pro_csv)

    recordings = None
    if args.recordings_npz:
        recordings = list(np.load(args.recordings_npz, allow_pickle=True)["recordings"])
    chronic = _load_chronic_npz(args.chronic_npz) if args.chronic_npz else None

    if args.source in ("timedomain", "both") and recordings is None:
        ap.error("--recordings-npz is required for source timedomain/both")
    if args.source in ("chronic", "both") and chronic is None:
        ap.error("--chronic-npz is required for source chronic/both")

    run_output = run_biomarker(recordings, pro_df, chan_order, source=args.source,
                               chronic=chronic, align=args.align, transform=args.transform,
                               label_metric=args.label_metric, pain_cutoff=args.pain_cutoff,
                               label_strategy=args.label_strategy)
    csv_path, npz_path = write_combined(run_output, args.patient, out_dir=args.out_dir)
    print(f"Wrote {csv_path}\nWrote {npz_path}")

    td = run_output.get("timedomain")
    ch = run_output.get("powerdomain") or run_output.get("chronic")  # back-compat key
    if td is not None:
        b = td["summary"]["band"]
        if b is not None:
            print(f"[timedomain] top band: ch={td['detail']['chan_order'][b[0]]} "
                  f"{b[4]:.2f} Hz  r={b[2]:.3f} p={b[3]:.4g}")
        else:
            print("[timedomain] no significant biomarker band found.")
    if ch is not None:
        s = ch["summary"]
        print(f"[chronic] threshold={s['best_threshold']}  sens={s['sens']}  "
              f"spec={s['spec']}  n_windows={s['n_windows']}")


if __name__ == "__main__":
    main()
