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
import logging
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

# This module had no logging at all. The rating_group fallback below needs to be able to say
# something when the session/epoch alignment it depends on does not hold, rather than failing
# silently — or, as a first draft of that code did, raising NameError on `_log`.
_log = logging.getLogger(__name__)


def rating_group_from_identity(session_df, labels):
    """Grouping factor for rating-aware statistics: one group per MATCHED REPORT.

    Extracted from ``run_timedomain_branch`` so it can be tested directly — the three tests added
    with the original fix all exercised ``adapter.align_pros``, leaving this half of it backed only
    by a live measurement.

    Returns an int array, one entry per epoch: a distinct code per distinct matched report, and -1
    for an epoch that has no matched report or no usable label.

    WHY IDENTITY AND NOT VALUE. This used to reconstruct the grouping by searching ``pro_df`` for a
    report whose VALUE equalled the session's label and taking the first hit. On an integer pain
    scale that collapses every session sharing a score into ONE "rating": measured on RCS08, 72
    genuinely distinct matched reports were represented as 7 groups under ``nrs``, because there were
    only 7 distinct NRS values. That corrupted the cluster-robust logit p (7 clusters instead of 72,
    far too few for sandwich variance) and — worse — made ``StratifiedGroupKFold``'s folds a function
    of the outcome being predicted, holding whole pain levels out together.

    There is deliberately NO value-matching fallback. If the session/epoch alignment this depends on
    does not hold, the grouping is left unset and a warning is logged, because reverting to a
    grouping that clusters on the outcome is worse than having no grouping at all.
    """
    labels = np.asarray(labels, dtype=float)
    rating_group = np.full(len(labels), -1, dtype=int)
    has_col = "matched_pro_time" in getattr(session_df, "columns", ())
    if has_col and len(session_df) == len(labels):
        ids = pd.to_datetime(session_df["matched_pro_time"], errors="coerce")
        codes, _ = pd.factorize(ids, use_na_sentinel=True)   # NaT -> -1, which is what we want
        rating_group = np.asarray(codes, dtype=int)
        # An epoch whose label is unusable carries no information for a rating-aware statistic, so
        # it must not occupy a group either.
        rating_group[~np.isfinite(labels)] = -1
    else:
        _log.warning(
            "Biomarkers: cannot build rating_group from matched-report identity (session_df rows=%d, "
            "epochs=%d, has column=%s) — leaving it unset rather than falling back to value-matching, "
            "which collapses every session sharing a pain score into one group.",
            len(session_df) if session_df is not None else -1, len(labels), has_col)
    return rating_group

# Per-source code versions; stamped into every output file. Bump when a source's math changes.
STREAMING_CODE_VERSION = "streaming_psd-0.1.0"
CHRONIC_CODE_VERSION = "chronic_threshold-0.1.0"


# Percept sensing-frequency bin width (FFT bin spacing ~250/256 Hz). The programmed center frequency
# is reported at slightly different sub-bin values across files (e.g. 8.78 vs 8.79), so we snap to a
# clean bin so the same physical band gets ONE color/label in the frequency ribbon.
_PERCEPT_FREQ_BIN_HZ = 250.0 / 256.0


def _snap_freq(hz):
    """Snap a reported center frequency to the nearest Percept FFT bin (1 decimal)."""
    if hz is None:
        return None
    try:
        hz = float(hz)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(hz):
        return None
    return round(round(hz / _PERCEPT_FREQ_BIN_HZ) * _PERCEPT_FREQ_BIN_HZ, 1)


def _parse_time_ms(t):
    """Parse a recording's Time array to a UTC DatetimeIndex, handling BOTH encodings.

    Chronic Time is epoch SECONDS as float (ChronicBrainSense stamps t.timestamp()); power-domain
    synthesizes float seconds too. But pd.to_datetime on a float Series defaults to NANOSECONDS,
    which maps ~1.7e9 -> 1970. Detect the numeric case and pass unit='s'; otherwise parse as ISO/strings.
    """
    try:
        s = pd.Series(t)
    except Exception:
        return None
    if len(s) == 0:
        return None
    if pd.api.types.is_numeric_dtype(s):
        return pd.to_datetime(s, unit="s", utc=True, errors="coerce").dropna()
    return pd.to_datetime(s, utc=True, errors="coerce").dropna()


def _channel_time_extent_ms(ch_list):
    """[min_ms, max_ms] over every recording's Time array in ch_list, or None if no parseable time."""
    lo = hi = None
    for c in ch_list:
        if not isinstance(c, dict):
            continue
        tarr = _parse_time_ms(c.get("Time"))
        if tarr is None or len(tarr) == 0:
            continue
        t0 = int(tarr.min().value // 1_000_000)
        t1 = int(tarr.max().value // 1_000_000)
        lo = t0 if lo is None else min(lo, t0)
        hi = t1 if hi is None else max(hi, t1)
    if lo is None:
        return None
    return [lo, hi]


def _collect_freq_schedule_ms(ch_list):
    """Union of every recording's stamped FreqScheduleHz into one sorted change-point list.

    FreqScheduleHz is [[epoch_SECONDS, hz], ...] derived from GroupHistory at decode time. Across the
    recordings of one channel we merge all change-points (different sessions stamp different windows
    of the same underlying history), dedup, snap Hz to the Percept bin, and collapse consecutive
    same-Hz points. Returns [[epoch_MS, snapped_hz], ...] sorted by time, or [] if none stamped.
    """
    pts = []
    seen = set()
    for c in ch_list:
        if not isinstance(c, dict):
            continue
        sched = c.get("FreqScheduleHz")
        if not isinstance(sched, (list, tuple)):
            continue
        for item in sched:
            try:
                ts, hz = float(item[0]), _snap_freq(item[1])
            except (TypeError, ValueError, IndexError):
                continue
            if hz is None:
                continue
            ms = int(ts * 1000)
            key = (ms, hz)
            if key in seen:
                continue
            seen.add(key)
            pts.append([ms, hz])
    if not pts:
        return []
    pts.sort(key=lambda p: p[0])
    collapsed = []
    for ms, hz in pts:
        if not collapsed or collapsed[-1][1] != hz:
            collapsed.append([ms, hz])
    return collapsed


def _collect_contact_schedule_ms(ch_list):
    """Union of every recording's stamped ContactSchedule into one sorted change-point list.

    ContactSchedule is [[epoch_SECONDS, "0-3"], ...] derived from GroupHistory at decode time —
    parallel to FreqScheduleHz but for the bipolar recording contact, which is reprogrammed over time
    just like the frequency. Merge change-points across the channel's recordings, dedup, collapse
    consecutive same-contact points. Returns [[epoch_MS, contact], ...] sorted by time, or [].
    """
    pts = []
    seen = set()
    for c in ch_list:
        if not isinstance(c, dict):
            continue
        sched = c.get("ContactSchedule")
        if not isinstance(sched, (list, tuple)):
            continue
        for item in sched:
            try:
                ts, contact = float(item[0]), str(item[1])
            except (TypeError, ValueError, IndexError):
                continue
            if not contact:
                continue
            ms = int(ts * 1000)
            key = (ms, contact)
            if key in seen:
                continue
            seen.add(key)
            pts.append([ms, contact])
    if not pts:
        return []
    pts.sort(key=lambda p: p[0])
    collapsed = []
    for ms, contact in pts:
        if not collapsed or collapsed[-1][1] != contact:
            collapsed.append([ms, contact])
    return collapsed


def _available_frequencies(cv_ch):
    """Per-frequency data availability for one channel's decoding frame (cv_ch).

    For each unique sensing frequency present in the channel's samples (the `frequency_hz` column),
    report how much decodable data exists AT THAT BAND: total samples, distinct calendar days, and
    how many samples / days carry a usable pain label (pain_level in {0,1}) split by class. This is
    what the frequency sub-selector lists and what the per-(channel,frequency) binarization preview
    needs to state data sufficiency. Combines chronic + streaming implicitly — cv_ch already merges
    both sources, so a frequency's counts pool every sample at that band regardless of modality.

    Returns a list of dicts sorted by frequency (ascending), e.g.
        [{"frequency_hz": 7.8, "n_samples": 412, "n_days": 23, "n_labeled": 388,
          "n_pos": 190, "n_neg": 198, "n_days_labeled": 21}, ...]
    Empty list when the frame has no frequency_hz column (legacy data with no center frequency).
    """
    if cv_ch is None or "frequency_hz" not in getattr(cv_ch, "columns", []):
        return []
    df = cv_ch
    fhz = df["frequency_hz"].to_numpy(dtype=float)
    finite = np.isfinite(fhz)
    if not finite.any():
        return []
    ts = pd.to_datetime(df["timestamp"], errors="coerce")
    day = ts.dt.floor("D")
    pl = df["pain_level"].to_numpy(dtype=float) if "pain_level" in df.columns else np.full(len(df), np.nan)
    out = []
    for hz in sorted(set(np.round(fhz[finite], 1))):
        m = finite & (np.round(fhz, 1) == hz)
        if not m.any():
            continue
        labeled = m & np.isin(pl, (0.0, 1.0))
        days_all = day[m].dropna()
        days_lab = day[labeled].dropna()
        out.append({
            "frequency_hz": float(hz),
            "n_samples": int(m.sum()),
            "n_days": int(days_all.nunique()),
            "n_labeled": int(labeled.sum()),
            "n_pos": int(np.nansum(pl[labeled] == 1.0)),
            "n_neg": int(np.nansum(pl[labeled] == 0.0)),
            "n_days_labeled": int(days_lab.nunique()),
        })
    return out


def _decode_by_frequency(cv_ch, label_metric, *, min_labeled=8):
    """Per-(channel, frequency) decoding payload for one channel's frame.

    The analysis unit is (channel, frequency): a contact sensed at 7.8 Hz and the SAME contact sensed
    at 22.5 Hz are physiologically different biomarkers and must never be pooled. For each sensing
    band present in `cv_ch` (the `frequency_hz` column, which already merges chronic + streaming for
    this contact), we slice the frame to that band and compute, on that slice ALONE:
      * decoding  : ROC (FPR/TPR/AUC) + LFP Otsu histogram on LFP_smoothed vs pain_level
      * binarization: a COMPACT daily pain aggregation [{day, mean, n_samples}] for the band's
        samples, plus the high/low day/sample split — the inputs the top BinarizationPreview shows,
        scoped to this band. Daily (not per-sample) so a chronic band with 10k+ samples stays small.
      * counts    : n_samples / n_days / n_labeled for the band.

    Returns {"<hz>": {...}} keyed by the snapped frequency as a string (e.g. "7.8"). A band with
    fewer than `min_labeled` labeled samples still reports counts + binarization but sets
    decoding.auc = None (too little to fit a stable detector) so the UI can flag insufficiency.
    """
    from .routines import analytics
    if cv_ch is None or "frequency_hz" not in getattr(cv_ch, "columns", []):
        return {}
    fhz = cv_ch["frequency_hz"].to_numpy(dtype=float)
    finite = np.isfinite(fhz)
    if not finite.any():
        return {}
    out = {}
    for hz in sorted(set(np.round(fhz[finite], 1))):
        sub = cv_ch[np.round(fhz, 1) == hz]
        if len(sub) == 0:
            continue
        # Daily pain aggregation for the binarization preview (one row per calendar day at this band).
        ts = pd.to_datetime(sub["timestamp"], errors="coerce")
        day = ts.dt.floor("D")
        pain = sub[label_metric].to_numpy(dtype=float) if label_metric in sub.columns else np.full(len(sub), np.nan)
        pl = sub["pain_level"].to_numpy(dtype=float) if "pain_level" in sub.columns else np.full(len(sub), np.nan)
        daily = []
        dser = pd.Series(pain, index=day)
        for d, grp in dser.groupby(level=0):
            if d is None or (isinstance(d, float) and not np.isfinite(d)):
                continue
            vals = grp.to_numpy(dtype=float)
            vals = vals[np.isfinite(vals)]
            if vals.size == 0:
                continue
            daily.append({"day": pd.Timestamp(d).strftime("%Y-%m-%d"),
                          "mean": float(np.mean(vals)), "n_samples": int(len(grp))})
        labeled_mask = np.isin(pl, (0.0, 1.0))
        n_labeled = int(labeled_mask.sum())
        # Class split on the broadcast per-sample label (pain_level already reflects the active
        # strategy's daily cut). Day counts use the labeled days; sample counts the labeled samples.
        lab_days = day[labeled_mask].dropna()
        pos_days = day[labeled_mask & (pl == 1.0)].dropna()
        neg_days = day[labeled_mask & (pl == 0.0)].dropna()
        binar = {
            "daily": daily,
            "n_pos_samples": int(np.nansum(pl[labeled_mask] == 1.0)),
            "n_neg_samples": int(np.nansum(pl[labeled_mask] == 0.0)),
            "n_pos_days": int(pos_days.nunique()),
            "n_neg_days": int(neg_days.nunique()),
            "n_days_labeled": int(lab_days.nunique()),
        }
        # LFP decoding on this band alone. roc/lfp_distribution are pure functions of the slice.
        if n_labeled >= min_labeled and len(np.unique(pl[labeled_mask])) >= 2:
            roc = analytics.roc_analysis(sub)
            dist = analytics.lfp_distribution(sub)
        else:
            roc = {"fpr": [], "tpr": [], "auc": None}
            dist = {"bin_edges": [], "counts": [], "otsu": None, "n_clipped": 0, "n_total": int(len(sub))}
        out[f"{hz:g}"] = {
            "frequency_hz": float(hz),
            "n_samples": int(len(sub)),
            "n_days": int(day.dropna().nunique()),
            "n_labeled": n_labeled,
            "roc": roc,
            "distribution": dist,
            "binarization": binar,
        }
    return out


def _build_contact_epochs(ch_list):
    """Time-segmented recording-CONTACT epochs for one hemisphere channel.

    Parallel to _build_freq_epochs but for the bipolar contact. Segments the channel's actual data
    extent at each contact change-point from the dated GroupHistory schedule, so a long chronic trend
    yields one epoch per contact the signal was actually recorded from. The contact in force at the
    span start is carried from the last change-point at or before it. Returns
    [{"t0": ms, "t1": ms, "contact": str}, ...] (epoch-ms) or [] when no schedule is available.
    """
    extent = _channel_time_extent_ms(ch_list)
    schedule = _collect_contact_schedule_ms(ch_list)
    if extent is None or not schedule:
        return []
    lo, hi = extent
    bounds = sorted({lo, hi} | {ms for ms, _c in schedule if lo < ms < hi})

    def contact_at(ms):
        cur = None
        for cms, cc in schedule:
            if cms <= ms:
                cur = cc
            else:
                break
        return cur if cur is not None else schedule[0][1]

    epochs = []
    for a, b in zip(bounds[:-1], bounds[1:]):
        contact = contact_at(a)
        if not contact:
            continue
        if epochs and epochs[-1]["contact"] == contact and a <= epochs[-1]["t1"] + 1:
            epochs[-1]["t1"] = max(epochs[-1]["t1"], b)
        else:
            epochs.append({"t0": a, "t1": b, "contact": contact})
    return epochs


def _build_freq_epochs(ch_list):
    """Time-segmented center-frequency epochs for one sensing channel.

    The programmed sensing band changes over time, and a single 24/7 trend recording can span MANY
    such changes — so stamping one CenterFrequencyHz per recording collapses that history to a single
    value. The accurate source is the dated GroupHistory schedule (FreqScheduleHz: when the band
    changed), which we intersect against the channel's actual data extent:

      1. If a frequency SCHEDULE is present, segment the channel's [first, last] sample span at each
         change-point that falls inside it, so one long recording yields multiple epochs reflecting
         the real switches. The frequency in force at the span start is carried from the last
         change-point at or before it.
      2. Otherwise fall back to the legacy per-recording behavior (one snapped CenterFrequencyHz per
         recording's own span, merging consecutive same-frequency spans).

    Returns [{"t0": ms, "t1": ms, "hz": float}, ...] (epoch-ms, JSON-friendly) or [].
    """
    extent = _channel_time_extent_ms(ch_list)
    schedule = _collect_freq_schedule_ms(ch_list)

    if extent is not None and schedule:
        lo, hi = extent
        # Boundaries inside the data extent = change-points strictly within (lo, hi].
        bounds = sorted({lo, hi} | {ms for ms, _hz in schedule if lo < ms < hi})
        # Frequency in force at a given time = the last change-point at or before it.
        def hz_at(ms):
            cur = None
            for cms, chz in schedule:
                if cms <= ms:
                    cur = chz
                else:
                    break
            # If the data starts before the first change-point, use the first known freq.
            return cur if cur is not None else schedule[0][1]
        epochs = []
        for a, b in zip(bounds[:-1], bounds[1:]):
            hz = hz_at(a)
            if hz is None:
                continue
            if epochs and epochs[-1]["hz"] == hz and a <= epochs[-1]["t1"] + 1:
                epochs[-1]["t1"] = max(epochs[-1]["t1"], b)
            else:
                epochs.append({"t0": a, "t1": b, "hz": hz})
        if epochs:
            return epochs

    # Legacy fallback: one frequency per recording span (no dated schedule available).
    spans = []
    for c in ch_list:
        if not isinstance(c, dict):
            continue
        hz = _snap_freq(c.get("CenterFrequencyHz"))
        if hz is None:
            continue
        tarr = _parse_time_ms(c.get("Time"))
        if tarr is None or len(tarr) == 0:
            continue
        t0 = int(tarr.min().value // 1_000_000)  # ns -> ms
        t1 = int(tarr.max().value // 1_000_000)
        spans.append((t0, t1, hz))
    if not spans:
        return []
    spans.sort(key=lambda s: s[0])
    merged = [list(spans[0])]
    for t0, t1, hz in spans[1:]:
        last = merged[-1]
        if hz == last[2] and t0 <= last[1] + 1:  # same freq, contiguous/overlapping -> extend
            last[1] = max(last[1], t1)
        else:
            merged.append([t0, t1, hz])
    return [{"t0": m[0], "t1": m[1], "hz": m[2]} for m in merged]

# Upper frequency bound for biomarker band SELECTION and the permutation family. The Percept RC
# senses physiologically-relevant LFP rhythms (theta ~4–8, alpha ~8–12, beta ~13–30, low-gamma
# ~30–50 Hz); the at-home chronic biomarker is a 5 Hz band picked from those. Bands at/above this
# cut are excluded from selection so a high-frequency artifact can never win the max|R| search.
MAX_BIOMARKER_FREQ_HZ = 50.0
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
    # The r in result['corr'] was computed by pearson_corr_psd_label AFTER MAD>=3 outlier rejection
    # (per channel/freq on the feature AND on the label). The effective-N / df here MUST be computed
    # on the SAME surviving samples, otherwise df reflects more observations than r was estimated
    # from and the t->p mapping is anti-conservative (partly undoing the effective-N adjustment this
    # function exists to make). Mirror the MAD keep-mask on the label once; the feature side is per
    # (c,f) inside the loop.
    label_keep = adapter.mad_outlier_mask(labels)
    from scipy.stats import t as _t
    for c in range(C):
        for f in range(F):
            r = corr[c, f]
            if not np.isfinite(r) or abs(r) >= 1:
                continue
            x = feat[:, c, f]
            v = adapter.mad_outlier_mask(x) & label_keep
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
    # Enforce the biomarker frequency cap: bands at/above MAX_BIOMARKER_FREQ_HZ are never selectable.
    finite[:, f_set >= MAX_BIOMARKER_FREQ_HZ] = False
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
                          transform="log", stim_amplitudes=None,
                          match_tolerance_min=None):
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
        match_tolerance_min=match_tolerance_min,
    )
    label_col = f"{label_metric}_{label_reduce}"
    labels = session_df[label_col].to_numpy(dtype=float)

    # Build the rating grouping BEFORE the correlation so the spectrum's p-value can be
    # cluster-robust on ratings rather than a naive t on epochs. `labels` is session_df[label_col],
    # so the identity carries across one-for-one.
    _rating_group = rating_group_from_identity(session_df, labels)
    result = streaming_psd.compute_psd_pain_correlation(streams, labels, chan_order,
                                                        transform=transform,
                                                        rating_group=_rating_group)
    band = select_biomarker_band(result)

    timeline = pd.DataFrame({
        "time": pd.to_datetime(session_df["session_start"]),
        "date": session_df["session_date"],
    })
    if band is not None:
        c_idx, f_idx, r, p, f_hz, fdr_q, fdr_sig = band
        timeline["td_biomarker_value"] = result["psd"][:, c_idx, f_idx]
        # Numeric contact-pair label (e.g. "R 0⁻2⁺"), never the raw word form ("ZERO_TWO_RIGHT").
        timeline["td_biomarker_channel"] = format_channel(result["chan_order"][c_idx])["short"]
        timeline["td_biomarker_freq_hz"] = f_hz
        timeline["td_biomarker_r"] = r
        timeline["td_biomarker_p"] = p
    else:
        timeline["td_biomarker_value"] = np.nan
    timeline["td_stim_amplitude"] = session_df.get("stim_amplitude", np.nan)
    # Carry the PRO<->PSD match bookkeeping so the analytics step can count matched neural samples
    # (and how far off, in minutes) without re-running the match. Present for both the time-window
    # and the legacy same-day path (matched=True there means the session had a same-day PRO).
    if "matched" in session_df.columns:
        timeline["td_matched"] = session_df["matched"].to_numpy()
    if "match_dt_min" in session_df.columns:
        timeline["td_match_dt_min"] = session_df["match_dt_min"].to_numpy()
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
                                       session_df.get("stim_amplitude"),
                                       rating_group=_rating_group))
        summary.update({"channel": ch["short"], "channel_raw": ch["raw"]})
    
    # Inject rating_group into the detail so deduplication works for TD-only channels.
    # Map each session's matched PRO back to the PRO index in pro_df. Each epoch (session) matches
    # to at most one PRO label; we find its index for the rating-grouped deduplication.
    td_labels = result.get("labels", labels)  # use result labels (should match session_df)
    #
    # GROUP ON THE MATCHED RATING'S IDENTITY, NOT ITS VALUE (fixed 2026-08-30).
    #
    # This block used to reconstruct the grouping by searching pro_df for a report whose VALUE
    # equalled the session's label — `np.where(abs(pro_vals - lbl) < 1e-6)[0][0]` — and taking the
    # first hit. On an integer pain scale that is catastrophic: every session that happens to share
    # a score collapses into ONE "rating group", so the number of groups equals the number of
    # distinct pain VALUES (single digits) rather than the number of matched reports (dozens).
    #
    # Two consequences, both on the panel's *rigorous* statistics:
    #   * `_cluster_robust_logit_p` clustered on a handful of clusters instead of dozens. Sandwich
    #     variance with that few clusters is unreliable, and it is the p-value the plate presents as
    #     the pseudoreplication-corrected headline (the ringed survivors).
    #   * `_cv_logistic_auc`'s StratifiedGroupKFold grouped on those same collapsed groups — i.e.
    #     the CV folds were defined BY THE OUTCOME, so whole pain levels were held out together.
    #     Grouping on the value of the thing you are predicting is not a defensible fold structure.
    #
    # `align_pros` now records `matched_pro_time`, the identity of the report each session was
    # matched to (its timestamp under time-window matching; the calendar date under legacy same-day
    # aggregation, where the day's aggregate genuinely IS one shared rating). `labels` is
    # `session_df[label_col]`, so epoch i corresponds to session_df row i one-for-one and the
    # identity can be carried straight across. Distinct identity -> distinct group; unmatched -> -1.
    # Same array the correlation used above; recomputing it would risk the two drifting apart.
    result["rating_group"] = (_rating_group if len(_rating_group) == len(td_labels)
                              else rating_group_from_identity(session_df, td_labels))
    
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


def _rating_level_perm_matrix(y, rating_group, n_perm, rng, block=None):
    """Circular-block permutation at the RATING level, broadcast back to epochs.

    THE EXCHANGEABLE UNIT IS THE RATING, NOT THE EPOCH (audit F3). Several epochs are matched to one
    pain report, so permuting the epoch-level label vector is not a valid null: it hands different
    permuted labels to epochs that belong to the same report, and it splits one report's epochs
    across permutation blocks. Both destroy the replication structure the real data has, which makes
    the null too variable in the wrong direction and the resulting p too small. Measured on RCS08 at
    the selected cell, the epoch-level null gave p = 0.0729 where the rating-level null gives 0.233.

    Construction: take one value per rating in time order, circular-block permute THAT vector (block
    length from the rating-level autocorrelation, so serial dependence between successive reports is
    preserved), then broadcast each permuted rating value back to every epoch sharing that report.

    Returns ``(Yp, info)`` with ``Yp`` of shape ``(n_perm, n_grouped_epochs)`` and ``info`` recording
    the grouped-row mask, the number of ratings and the block length. Callers MUST compute the
    observed statistic on the same ``info["rows"]`` subset, or the observed value and its null come
    from different data (the same defect F8 flags elsewhere).
    """
    y = np.asarray(y, dtype=float)
    g = np.asarray(rating_group, dtype=int)
    rows = np.isfinite(y) & (g >= 0)
    if rows.sum() < 4:
        return None, {"rows": rows, "n_ratings": 0, "block": None,
                      "reason": "fewer than 4 epochs carry both a finite label and a rating id"}
    gg, yy = g[rows], y[rows]
    # unique ratings in FIRST-APPEARANCE (time) order, since the rows arrive time-ordered
    _, first_idx = np.unique(gg, return_index=True)
    uniq = gg[np.sort(first_idx)]
    pos = {int(v): k for k, v in enumerate(uniq)}
    inv = np.array([pos[int(v)] for v in gg], dtype=int)      # epoch -> rating slot
    G = uniq.size
    if G < 4:
        return None, {"rows": rows, "n_ratings": int(G), "block": None,
                      "reason": f"only {G} distinct ratings; a permutation null needs at least 4"}
    # one value per rating. Constant within a rating by construction; mean is a no-op that also
    # tolerates a frame where it is not exactly constant.
    y_rating = np.array([float(np.nanmean(yy[inv == k])) for k in range(G)])
    if block is None:
        block = stats_utils.block_length_for(y_rating, G)
    perm_g = stats_utils.circular_block_perm_matrix(G, int(block), int(n_perm), rng)   # (P, G)
    Yp = y_rating[perm_g][:, inv]                                                       # (P, n_rows)
    return Yp, {"rows": rows, "n_ratings": int(G), "block": int(block),
                "n_epochs_used": int(rows.sum()), "reason": None}


def _block_perm_maxcorr_pvalue(X, y, n_perm=1000, block=None, seed=0, min_n=4, return_null=False,
                               rating_group=None):
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

    Returns (empirical_p, n_perm_used); with return_null=True returns (p, used, obs, null_stats) so
    the UI can plot the null distribution of the family max|R| against the observed value."""
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    rng = np.random.default_rng(seed)
    perm_info = {"unit": "epoch", "n_ratings": None, "block": None, "n_epochs_used": int(X.shape[0])}

    Yp = None
    if rating_group is not None:
        # RATING-LEVEL null (audit F3). Restrict BOTH the observed statistic and the null to the
        # rows that carry a rating id, so the two come from the same data — computing the observed
        # value on more rows than its null is the defect F8 flags elsewhere.
        Yp, info = _rating_level_perm_matrix(y, rating_group, int(n_perm), rng, block=block)
        if Yp is None:
            _log.warning("Biomarkers: rating-level permutation null unavailable (%s); falling back "
                         "to the epoch-level null, which is anti-conservative because epochs "
                         "sharing one rating are not exchangeable.", info.get("reason"))
        else:
            rows = info["rows"]
            X, y = X[rows], y[rows]
            perm_info = {"unit": "rating", "n_ratings": info["n_ratings"], "block": info["block"],
                         "n_epochs_used": info["n_epochs_used"]}

    N, K = X.shape
    obs = _maxabs_corr(X, y, min_n=min_n)
    if not np.isfinite(obs) or N < 4:
        return ((np.nan, 0, obs, None, perm_info) if return_null else (np.nan, 0))
    if Yp is None:
        if block is None:
            block = stats_utils.block_length_for(y, N)
        perm = stats_utils.circular_block_perm_matrix(N, block, int(n_perm), rng)   # (P, N)
        perm_info["block"] = int(block)

    M = np.isfinite(X).astype(float)                  # (N, K) fixed column masks (y is finite)
    Xm = np.where(M > 0, X, 0.0)                      # (N, K)
    nj = M.sum(axis=0)                                # (K,)
    sx = Xm.sum(axis=0)                               # (K,)
    sxx = (Xm * Xm).sum(axis=0)                       # (K,)
    with np.errstate(invalid="ignore", divide="ignore"):
        vx = sxx - sx * sx / nj                       # (K,)

    if Yp is None:
        Yp = y[perm]                                  # (P, N) epoch-level permuted labels

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
        return ((np.nan, 0, obs, None, perm_info) if return_null else (np.nan, 0))
    null_stats = stat[finite]
    ge = int(np.sum(null_stats >= obs))
    p = (ge + 1) / (used + 1)                          # +1: never report p=0
    # WINNER'S CURSE MAGNITUDE (audit F14). The null distribution of the family max|R| IS the
    # magnitude of the selection effect, and it was already being computed here and shipped as a
    # raw array while the plate said only `selection_biased: True`. Summarising it turns "these
    # numbers are biased" into "this is how much of the winning |r| searching alone would produce".
    perm_info.update({
        "null_max_mean": float(np.mean(null_stats)),
        "null_max_p95": float(np.quantile(null_stats, 0.95)),
        "null_max_median": float(np.median(null_stats)),
        "obs_minus_null_mean": float(obs - np.mean(null_stats)),
        "obs_exceeds_null_p95": bool(obs > np.quantile(null_stats, 0.95)),
        "family_size": int(K),
    })
    return (p, used, float(obs), null_stats, perm_info) if return_null else (p, used)


def _band_inference(result, c_idx, f_idx, r, p, f_hz, fdr_q, fdr_sig, stim, n_perm=1000,
                    rating_group=None):
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
    # Robust MAD outlier rejection (>=3 MADs from the median is dropped) on BOTH the band-power
    # feature and the label, consistent with the correlation spectrum and the chronic detector, so a
    # single artifact session cannot inflate the partial r / effective N / Fisher-z CI for the band.
    valid = adapter.mad_outlier_mask(bandpow) & adapter.mad_outlier_mask(labels)
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
    perm_p, perm_used, perm_obs, perm_null, perm_meta = (np.nan, 0, np.nan, None, {})
    if perm_valid.sum() >= 4:
        # Restrict the family to the SAME ≤ MAX_BIOMARKER_FREQ_HZ band the selector searches, so the
        # family-max null (perm_obs) is over exactly the cells a biomarker could be drawn from.
        f_set_all = np.asarray(result["f_set"], dtype=float)
        keep_f = f_set_all < MAX_BIOMARKER_FREQ_HZ
        feat_capped = feat[:, :, keep_f]
        X = feat_capped.reshape(feat_capped.shape[0], -1)[perm_valid]
        yv = labels[perm_valid]
        # Pass the rating grouping so the null permutes RATINGS, not epochs (audit F3). The
        # observed statistic is recomputed inside on the same grouped rows as the null.
        # Explicit argument, NOT result["rating_group"] — that key is not populated until later in
        # run_timedomain_branch, so reading it here silently selected the epoch-level fallback.
        _rg = rating_group if rating_group is not None else result.get("rating_group")
        perm_p, perm_used, perm_obs, perm_null, perm_meta = _block_perm_maxcorr_pvalue(
            X, yv, n_perm=n_perm, seed=0, return_null=True,
            rating_group=(np.asarray(_rg)[perm_valid] if _rg is not None else None))
    return {
        "freq_hz": f_hz, "r": r, "p": p, "fdr_q": fdr_q, "fdr_significant": bool(fdr_sig),
        "selection_biased": True,   # r/p/fdr_q/r_ci are conditional on the max|R| winner
        "stim_adjusted_r": (None if stim_adj is None or not np.isfinite(stim_adj) else float(stim_adj)),
        "stim_adjusted_note": stim_note,
        "n": n, "n_effective": (round(float(n_eff), 1) if np.isfinite(n_eff) else None),
        "r_ci": [None if not np.isfinite(r_lo) else r_lo, None if not np.isfinite(r_hi) else r_hi],
        "r_ci_note": ci_note,
        "perm_p": (None if not np.isfinite(perm_p) else float(perm_p)), "perm_n": int(perm_used),
        # The null distribution itself (family max|R| under block-permuted labels) + the observed
        # value, so the UI can PLOT the permutation test, not just report its p. Rounded to shrink
        # the payload; this is the strongest |R| over all contacts x freqs per shuffle.
        "perm_obs": (None if not np.isfinite(perm_obs) else round(float(perm_obs), 4)),
        "perm_null": ([round(float(s), 4) for s in perm_null] if perm_null is not None else None),
        # F3 provenance: WHICH unit was permuted. "rating" is the valid null; "epoch" is
        # anti-conservative and only appears as a logged fallback.
        "perm_unit": perm_meta.get("unit"),
        "perm_n_ratings": perm_meta.get("n_ratings"),
        "perm_block": perm_meta.get("block"),
        "perm_n_epochs_used": perm_meta.get("n_epochs_used"),
        # F14: the winner's-curse magnitude, not just the flag. null_max_mean is the |r| that
        # searching this family produces on average when there is NO real effect, so the honest
        # read of the winning |r| is the excess over it.
        "perm_null_max_mean": perm_meta.get("null_max_mean"),
        "perm_null_max_p95": perm_meta.get("null_max_p95"),
        "perm_obs_minus_null_mean": perm_meta.get("obs_minus_null_mean"),
        "perm_obs_exceeds_null_p95": perm_meta.get("obs_exceeds_null_p95"),
        "perm_family_size": perm_meta.get("family_size"),
        "narrow_peak_warning": narrow_peak,
    }


def run_powerdomain_branch(pro_df, *, chronic, label_metric="nrs", pain_cutoff=None,
                           label_strategy="kmeans", kmeans_features=("left_leg_vas", "mpq_sum"),
                           low_pct=33.3333, high_pct=66.6667, daily_broadcast=True,
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
                                            kmeans_features=kmeans_features,
                                            low_pct=low_pct, high_pct=high_pct,
                                            daily_broadcast=daily_broadcast)
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

    # PERMUTATION NULL for the in-sample AUC (rigor review: the bar plot's 0.5 chance line is the
    # ANALYTIC baseline; this adds an EMPIRICAL null that preserves daily pain autocorrelation, so
    # the reader can tell whether the observed separability beats chance for THIS serially-correlated
    # series). Block-permute the labels (block = lag-1 decorrelation timescale) and recompute the
    # undirected max(AUC,1-AUC) each shuffle. Emitted as summary["auc_perm"]; None if degenerate.
    try:
        ap = stats_utils.auc_block_perm_null(lfp_s, pl, n_perm=1000, seed=0)
        summary["auc_perm"] = ap if ap.get("observed") is not None else None
    except Exception:
        summary["auc_perm"] = None

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
    # PER-CHANNEL split (rigor review §7-C: the pooled detector mixes hemispheres and modalities).
    # Group the input chronic-shaped entries by the LFP series label (typically "Left LFP" /
    # "Right LFP" after `bravo_powerdomain_to_chronic_like`) so the user can see the detector run
    # independently on each anatomical target — without re-fetching anything.
    per_channel = {}
    chronic_list = chronic if isinstance(chronic, list) else [chronic]
    chronic_list = [c for c in chronic_list if c is not None]
    if len(chronic_list) >= 2:
        groups = {}
        for c in chronic_list:
            names = c.get("ChannelNames") or []
            key = str(names[0]) if names else "Unknown LFP"
            groups.setdefault(key, []).append(c)
        # Skip degenerate "one group" case (would just duplicate the pooled run).
        if len(groups) >= 2:
            for ch_label, ch_list in groups.items():
                try:
                    cv_ch = adapter.bravo_chronic_to_lfp_df(
                        ch_list, pro_df, label_metric=label_metric, pain_cutoff=pain_cutoff,
                        label_strategy=label_strategy, kmeans_features=kmeans_features,
                        low_pct=low_pct, high_pct=high_pct, daily_broadcast=daily_broadcast)
                    ch_detail = threshold_biomarker.run_chronic_threshold(
                        cv_ch, thresholds=thresholds, train_days=train_days,
                        gap_days=gap_days, test_days=test_days, sliding=sliding)
                    pl_ch = cv_ch["pain_level"].to_numpy(dtype=float)
                    lfp_ch = cv_ch["LFP_smoothed"].to_numpy(dtype=float)
                    n_pos_ch = int(np.nansum(pl_ch == 1)); n_neg_ch = int(np.nansum(pl_ch == 0))
                    sens_ch = ch_detail.get("mean_test_sens_sens", np.nan)
                    spec_ch = ch_detail.get("mean_test_spec_sens", np.nan)
                    # Tag hemisphere + kind so the frontend can group per hemisphere without
                    # fragile name-parsing. "<Side>Hemisphere LFP" keys are the pooled chronic-trend
                    # aggregates (kind="aggregate"); "L …"/"R …" keys are individual bipolar sensing
                    # contacts (kind="contact"). Hemisphere is the leading L/R, or the word in the
                    # aggregate label. The frontend averages ONLY contacts within a hemisphere.
                    lbl = str(ch_label)
                    if "Hemisphere" in lbl:
                        ch_kind = "aggregate"
                        ch_hemi = "Left" if lbl.lower().startswith("left") else (
                            "Right" if lbl.lower().startswith("right") else None)
                    else:
                        ch_kind = "contact"
                        first = lbl.strip()[:1].upper()
                        ch_hemi = "Left" if first == "L" else ("Right" if first == "R" else None)
                    # Source modality of this channel group: "chronic" = the BrainSense Timeline
                    # ~10-min around-the-clock LFP power log; "powerdomain" = per-session BrainSense
                    # streaming band power. Read from the recordings' per-dict Source tag (set in
                    # bravo_service / bravo_powerdomain_to_chronic_like). Lets the frontend plot the
                    # around-the-clock chronic stream on its own row alongside the streaming contacts.
                    srcs = {str(c.get("Source", "chronic")) for c in ch_list if isinstance(c, dict)}
                    ch_source = "chronic" if srcs == {"chronic"} else (
                        "powerdomain" if srcs == {"powerdomain"} else "mixed")
                    # Sensing center frequency for this group (latest non-null), so the frontend can
                    # label the row. Chronic dicts carry CenterFrequencyHz; powerdomain dicts may too.
                    ch_hz = None
                    for c in ch_list:
                        if isinstance(c, dict) and c.get("CenterFrequencyHz") is not None:
                            ch_hz = float(c["CenterFrequencyHz"])
                    # Center-frequency EPOCHS over time: the programmed sensing band can change between
                    # sessions, so the most-recent value alone hides that history. Build time-segmented
                    # epochs [{t0, t1, hz}] by taking each recording's own time span + its
                    # CenterFrequencyHz and merging consecutive same-frequency spans. The frontend
                    # paints these as a colored frequency ribbon under the power row.
                    ch_freq_epochs = _build_freq_epochs(ch_list)
                    # Recording-CONTACT epochs over time (parallel to freq_epochs): the programmed
                    # bipolar contact is reprogrammed between sessions, so this hemisphere channel is
                    # actually a sequence of contacts. The serializer uses these to split the chronic
                    # series into per-contact display rows (the signal belongs in the row of the
                    # contact it was recorded from).
                    ch_contact_epochs = _build_contact_epochs(ch_list)
                    ch_summary = {
                        "channel": ch_label,
                        "hemisphere": ch_hemi,
                        "kind": ch_kind,
                        "source_modality": ch_source,
                        "center_hz": ch_hz,
                        "freq_epochs": ch_freq_epochs,
                        "contact_epochs": ch_contact_epochs,
                        # Per-frequency availability (chronic + streaming pooled at each band): drives
                        # the frequency sub-selector and the per-(channel,frequency) binarization view.
                        "available_frequencies": _available_frequencies(cv_ch),
                        "best_threshold": ch_detail.get("mean_thr_sens", np.nan),
                        "sens": sens_ch, "spec": spec_ch,
                        "acc": ch_detail.get("mean_test_acc_sens", np.nan),
                        "n_windows": ch_detail.get("n_windows", 0),
                        "auc_in_sample": _auc(pl_ch, lfp_ch),
                        "n_samples": int(len(cv_ch)),
                    }
                    ch_summary.update(stats_utils.balanced_metrics(sens_ch, spec_ch, n_pos_ch, n_neg_ch))
                    try:
                        ap_ch = stats_utils.auc_block_perm_null(lfp_ch, pl_ch, n_perm=1000, seed=0)
                        ch_summary["auc_perm"] = ap_ch if ap_ch.get("observed") is not None else None
                    except Exception:
                        ch_summary["auc_perm"] = None
                    per_channel[ch_label] = {"summary": ch_summary, "cv_df": cv_ch}
                except Exception as exc:
                    per_channel[ch_label] = {"summary": {"channel": ch_label, "error": str(exc)},
                                              "cv_df": None}

    return {"source": "powerdomain", "code_version": CHRONIC_CODE_VERSION,
            "timeline": timeline, "detail": detail, "summary": summary,
            "per_channel": per_channel,
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
                  low_pct=33.3333, high_pct=66.6667, daily_broadcast=True,
                  thresholds=None, train_days=7, gap_days=1, test_days=2,
                  stim_amplitudes=None, sliding=True, match_tolerance_min=None):
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
                                     transform=transform, stim_amplitudes=stim_amplitudes,
                                     match_tolerance_min=match_tolerance_min)

    def _power():
        return run_powerdomain_branch(pro_df, chronic=chronic, label_metric=label_metric,
                                      pain_cutoff=pain_cutoff, label_strategy=label_strategy,
                                      kmeans_features=kmeans_features,
                                      low_pct=low_pct, high_pct=high_pct,
                                      daily_broadcast=daily_broadcast, thresholds=thresholds,
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
