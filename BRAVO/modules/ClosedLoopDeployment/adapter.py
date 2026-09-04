"""Phase 0: one joined epoch-level table that every downstream estimator reads.

This is plumbing, and the module plan calls it the highest-value item precisely because it is
plumbing: before it existed each estimator built its own near-miss of the same join, so two panels
could disagree about what the brain was doing at a given moment and neither was obviously wrong.

The table is keyed on (session, channel, setting epoch) and carries, for every scanned band, BOTH
power scales, the delivered stimulation settings per hemisphere, the stimulation era, and the
matched pain report.

THE ONE SUBTLETY WORTH READING BEFORE USING THIS. The stored spectral matrix holds LOG power per
frequency bin. Band power on the linear scale is the ARITHMETIC mean of the linear bin powers, and
the arithmetic mean of linear values is not the exponentiated mean of their logarithms — that is the
GEOMETRIC mean, which is systematically smaller and differently weighted whenever the bins are
unequal. This is not a pedantic distinction here: rule D11 records that the device computes LFP
Power as a linear sum of squared magnitude rather than a log quantity, so the linear scale is the
device-relevant one, while the biomarker pipeline validated its bands on the log scale. Both are
therefore computed and carried side by side under names that say which is which, so a downstream
estimator can never silently take the wrong one, and so the question of whether the scale changes
the winner can actually be answered rather than assumed.
"""
from __future__ import annotations

import hashlib as _hashlib
import threading as _threading

import numpy as np
import pandas as pd

from ClosedLoopDeployment import edges as _edges

#: The scanned band centres and width used throughout this project.
DEFAULT_BAND_CENTERS_HZ = tuple(float(x) for x in np.arange(10.5, 28.0, 1.0))
DEFAULT_BAND_WIDTH_HZ = 5.0

#: Stimulation era boundaries in mA, shared with the Biomarkers stability test so the two modules
#: cut the amplitude axis in the same place.
ERA_OFF_MAX_MA = 0.1
ERA_LOW_MAX_MA = 1.5


#: The settings columns have been spelled two ways in this codebase: ``amp_Left`` in the raw pivot
#: and ``amp_mA_Left`` in the exposure-epoch frame that callers actually receive. Accepting only one
#: of them is how the Phase 0 table silently came back with no amplitude at all — the join succeeded,
#: every downstream edge reported "no estimable band", and nothing raised. The canonical spelling
#: emitted by this module is the one with units, matching StimOptimizer.
_AMP_NAMES = ("amp_mA_{h}", "amp_{h}")
_PW_NAMES = ("pw_us_{h}", "pw_{h}")


def resolve_setting_column(columns, kind, hemisphere):
    """First matching spelling of a settings column, or None. ``kind`` is 'amp' or 'pw'."""
    names = _AMP_NAMES if kind == "amp" else _PW_NAMES
    for pat in names:
        c = pat.format(h=hemisphere)
        if c in columns:
            return c
    return None


def canonical_amp_col(hemisphere):
    return f"amp_mA_{hemisphere}"


def _era(amp):
    if amp is None or not np.isfinite(amp):
        return None
    if amp < ERA_OFF_MAX_MA:
        return "OFF"
    return "LOW" if amp <= ERA_LOW_MAX_MA else "HIGH"


def band_powers(log_psd, freqs, centers=DEFAULT_BAND_CENTERS_HZ, width=DEFAULT_BAND_WIDTH_HZ):
    """Per-band power on both scales from one row's log spectrum.

    Returns (linear, log_of_linear, mean_of_log), each a dict keyed by band centre.

    ``linear`` is the arithmetic mean of the linear bin powers and is the device-comparable
    quantity (D11). ``log_of_linear`` is its decibel expression, which is a monotone relabelling of
    the same ordering. ``mean_of_log`` is the quantity the biomarker pipeline used; it is the
    geometric mean in disguise and can rank bands differently, which is why it is returned rather
    than quietly replaced.
    """
    lp = np.asarray(log_psd, dtype=float)
    f = np.asarray(freqs, dtype=float)
    if lp.shape[0] != f.shape[0]:
        raise ValueError(f"log_psd has {lp.shape[0]} bins but freqs has {f.shape[0]}")
    lin_bins = np.power(10.0, lp / 10.0)
    out_lin, out_log, out_mol = {}, {}, {}
    half = float(width) / 2.0
    for c in centers:
        m = (f >= c - half) & (f < c + half)
        if not m.any():
            out_lin[c] = out_log[c] = out_mol[c] = np.nan
            continue
        with np.errstate(invalid="ignore", divide="ignore"):
            lin = float(np.nanmean(lin_bins[m]))
            out_lin[c] = lin
            out_log[c] = 10.0 * np.log10(lin) if lin > 0 else np.nan
            out_mol[c] = float(np.nanmean(lp[m]))
    return out_lin, out_log, out_mol


def _assign_epoch(t_epoch_s, epochs):
    """Setting-epoch index for each PSD timestamp, or -1 when it falls in no epoch.

    Half-open intervals on purpose: a sample landing exactly on a settings change belongs to the NEW
    epoch, because the change had already been programmed when it was recorded.
    """
    t = np.asarray(t_epoch_s, dtype=float)
    out = np.full(t.shape[0], -1, dtype=int)
    if epochs is None or len(epochs) == 0:
        return out
    # Cast explicitly to nanosecond resolution BEFORE taking the integer view. Under pandas 3 a
    # datetime column may carry microsecond resolution, and `.astype("int64")` returns the raw
    # integer in whatever unit the dtype happens to have — so dividing by 1e9 silently produced
    # timestamps a thousand times too small, every sample fell outside every epoch, and the joined
    # table came back empty with no error anywhere. The same resolution-independent idiom is used in
    # Biomarkers/routines/analytics.py for exactly this reason.
    starts = (pd.to_datetime(epochs["t_start"], utc=True).to_numpy()
              .astype("datetime64[ns]").astype("int64") / 1e9)
    ends = (pd.to_datetime(epochs["t_end"], utc=True).to_numpy()
            .astype("datetime64[ns]").astype("int64") / 1e9)
    for i, (a, b) in enumerate(zip(starts, ends)):
        m = (t >= a) & (t < b) if np.isfinite(b) else (t >= a)
        out[m] = i
    return out


# ---------------------------------------------------------------------------------------------
# PHASE 0 CACHE
# ---------------------------------------------------------------------------------------------
#: The joined table costs ~70 s to build for RCS08 (109,296 rows from 6,072 spectra against 120
#: exposure epochs), and the deployment endpoint rebuilt it on EVERY request — so the live page sat
#: on a spinner for over a minute each time a clinician changed a candidate. Every consumer wants
#: the same table for the same inputs, so it is memoised.
#:
#: WHY THE SIGNATURE IS A CONTENT HASH AND NOT A SHAPE. A cache keyed on row counts would serve a
#: stale table whenever the data changed without changing its size — a corrected amplitude, a
#: re-decoded spectrum, an epoch boundary moving. On a module whose output authorises programming a
#: neurostimulator, serving a stale table is far worse than rebuilding one, so the key folds in the
#: actual VALUES of the columns the join depends on. Hashing 109k rows costs well under a second
#: against the 70 s it saves, which is why the safe choice is also the affordable one.
_JOINED_MEMO = {}
_JOINED_MEMO_LOCK = _threading.Lock()

#: Entries are large (a 109k-row frame), so the memo holds few. Two is enough for the access
#: pattern that matters: a clinician toggling between two candidate configurations on one page.
_JOINED_MEMO_MAX = 2


def _frame_fingerprint(df, columns):
    """A content hash of the columns a join depends on, plus the frame's shape.

    THE ARRAY-VALUED COLUMN IS THE WHOLE DIFFICULTY, and getting it wrong is silent. The PSD frame
    is one row per (sample, channel) with the entire spectrum held as a numpy array in ``log_psd``
    and the frequency axis in ``freqs``. ``pandas.util.hash_pandas_object`` cannot hash a column of
    arrays, and a first version of this function listed column names that did not exist on the real
    frame — so it hashed only ``t`` and ``channel``, reported its mode as "hashed", and did not
    change when the spectra changed. A re-decoded recording with unchanged timestamps would have
    been served a stale table by a cache that looked verified. Array columns are therefore hashed
    over their BYTES, and a column that cannot be hashed at all marks the whole fingerprint
    "shape_only" so the degradation is visible in the key rather than hidden inside it.

    Columns absent from the frame are skipped, which is intended: an annotation added downstream
    must not invalidate a table whose join inputs are unchanged. But because absence is silent, the
    names of the columns actually used are part of the returned tuple.
    """
    if df is None:
        return ("none",)
    present = [c for c in columns if c in getattr(df, "columns", [])]
    if not present:
        return ("no_columns", int(getattr(df, "shape", (0, 0))[0]))
    parts, degraded = [], False
    for c in present:
        col = df[c]
        first = next((v for v in col.to_numpy()[:1]), None)
        if isinstance(first, (np.ndarray, list, tuple)):
            try:
                buf = bytearray()
                for v in col.to_numpy():
                    buf += np.ascontiguousarray(np.asarray(v, dtype=float)).tobytes()
                parts.append((c, _hashlib.blake2b(bytes(buf), digest_size=16).hexdigest()))
            except Exception:
                degraded = True
        else:
            try:
                parts.append((c, int(pd.util.hash_pandas_object(col, index=True).sum())))
            except Exception:
                degraded = True
    # Row count is kept as a cheap guard, but the column COUNT deliberately is NOT: naming an
    # explicit subset is what lets a downstream annotation column leave the table valid, and
    # folding df.shape[1] in would silently undo that.
    if degraded or not parts:
        return ("shape_only", int(df.shape[0]), tuple(present))
    return ("hashed", int(df.shape[0]), tuple(parts))


def _joined_signature(psd_frame, epochs, centers, width):
    # These are the columns lfp_evidence.frame_from_matrix actually emits. Naming a column that
    # does not exist is not a harmless typo here: the fingerprint silently narrows to whatever DOES
    # exist and stops tracking the data that matters.
    return (_frame_fingerprint(psd_frame, ("t", "channel", "source", "log_psd", "freqs")),
            _frame_fingerprint(epochs, ("t_start", "t_end", "amp_mA_Left", "amp_mA_Right",
                                        "amp_Left", "amp_Right", "freq_hz", "pw_us_Left")),
            tuple(float(c) for c in (centers or ())), float(width))


#: THE ACTUAL BOTTLENECK, measured 2026-09-04 rather than assumed. A stage profile of one
#: deployment report on RCS08 came out as:
#:
#:     StimOptimizer.evidence_inputs          32.96 s
#:     StimOptimizer.build_design_matrix      33.99 s
#:     joined_table (cold)                     2.62 s
#:     edges.actuation_edge                    0.09 s
#:     pipeline.run                            0.05 s
#:
#: so 67 of the 70 seconds are the two input fetches, and the joined table — which I had assumed
#: was the problem and cached first — is 4% of the request. Both fetches re-read and re-decode the
#: same recordings from the database on every request, and both are pure functions of the recording
#: set, so both are memoised here.
#:
#: THE KEY IS THE RECORDING SET, NOT A TIMER. An expiry-based cache would serve a stale plot for
#: however long the window lasts, and this project has already lost a session to exactly that class
#: of confusion — a frozen Biomarkers plot whose cause was un-ingested files rather than a bad
#: cache. Keying on the identity of every recording means a new ingest invalidates immediately and
#: nothing else does.
_INPUTS_MEMO = {}
_INPUTS_MEMO_LOCK = _threading.Lock()
_INPUTS_MEMO_MAX = 2


def recording_set_signature(participant):
    """Identity of every recording that feeds the inputs, so a new ingest invalidates the cache.

    Folds in each recording's own uid and content hash rather than a count or a max date: a
    re-decode that replaces a recording in place changes neither of those, and a count alone would
    also miss a deletion balanced by an insertion.
    """
    from Server import models as _m
    sfs = list(_m.SourceFile.find_all(owner=participant))
    recs = list(_m.Recording.find_all(source__in=sfs))
    ident = sorted((str(getattr(r, "uid", "")), str(getattr(r, "hashed", "")),
                    str(getattr(r, "type", ""))) for r in recs)
    blob = "|".join("~".join(t) for t in ident).encode("utf8")
    return (str(getattr(participant, "uid", participant)), len(sfs), len(recs),
            _hashlib.blake2b(blob, digest_size=16).hexdigest())


def evidence_inputs_cached(participant, *, force_refresh=False):
    """``StimOptimizer.evidence_inputs`` and ``build_design_matrix``, memoised together.

    Returns ``(psd_frame, epochs, design_matrix)``. The two calls are cached as one entry because
    every consumer needs all three and they share the same invalidation condition, so splitting
    them would double the signature cost for no benefit.

    Callers must treat the returned frames as READ-ONLY, or copy before mutating: they are the same
    objects handed to every other caller. That is the same contract the Biomarkers assembled-matrix
    cache imposes.
    """
    from StimOptimizer import adapter as _sa
    sig = recording_set_signature(participant)
    if not force_refresh:
        with _INPUTS_MEMO_LOCK:
            hit = _INPUTS_MEMO.get(sig)
        if hit is not None:
            return hit
    psd, eps = _sa.evidence_inputs(participant)
    dm = _sa.build_design_matrix(participant)
    out = (psd, eps, dm)
    with _INPUTS_MEMO_LOCK:
        if sig not in _INPUTS_MEMO and len(_INPUTS_MEMO) >= _INPUTS_MEMO_MAX:
            _INPUTS_MEMO.pop(next(iter(_INPUTS_MEMO)), None)
        _INPUTS_MEMO[sig] = out
    return out


def inputs_cache_stats():
    with _INPUTS_MEMO_LOCK:
        return {"entries": len(_INPUTS_MEMO), "max": _INPUTS_MEMO_MAX,
                "psd_rows": [0 if v[0] is None else int(v[0].shape[0])
                             for v in _INPUTS_MEMO.values()]}


def clear_inputs_cache():
    with _INPUTS_MEMO_LOCK:
        _INPUTS_MEMO.clear()


def joined_table_cached(psd_frame, epochs, *, centers=None, width=DEFAULT_BAND_WIDTH_HZ,
                        force_refresh=False, **kwargs):
    """``joined_table`` with a content-keyed memo. Returns the SAME object to every caller.

    Callers must therefore treat the result as read-only, or copy it before mutating. That is the
    price of not rebuilding a 70-second table per request, and it is the same contract the
    Biomarkers assembled-matrix cache already imposes.
    """
    cen = tuple(DEFAULT_BAND_CENTERS_HZ if centers is None else centers)
    sig = _joined_signature(psd_frame, epochs, cen, width)
    if not force_refresh:
        with _JOINED_MEMO_LOCK:
            hit = _JOINED_MEMO.get(sig)
        if hit is not None:
            return hit
    out = joined_table(psd_frame, epochs, centers=cen, width=width, **kwargs)
    with _JOINED_MEMO_LOCK:
        if sig not in _JOINED_MEMO and len(_JOINED_MEMO) >= _JOINED_MEMO_MAX:
            _JOINED_MEMO.pop(next(iter(_JOINED_MEMO)), None)
        _JOINED_MEMO[sig] = out
    return out


def joined_cache_stats():
    """Entries and their row counts, for the interface and for tests."""
    with _JOINED_MEMO_LOCK:
        return {"entries": len(_JOINED_MEMO), "max": _JOINED_MEMO_MAX,
                "rows": [int(getattr(v, "shape", (0,))[0]) for v in _JOINED_MEMO.values()]}


def clear_joined_cache():
    with _JOINED_MEMO_LOCK:
        _JOINED_MEMO.clear()


def joined_table(psd_frame, epochs, *, centers=DEFAULT_BAND_CENTERS_HZ,
                 width=DEFAULT_BAND_WIDTH_HZ, pro_frame=None):
    """The Phase 0 table: one row per (PSD sample, band).

    Long rather than wide in the band dimension. Wide would mean 18 columns per power scale and a
    reshape inside every estimator; long lets an estimator filter to its band and keeps the three
    power scales as three columns rather than fifty-four.

    ``pro_frame``, when supplied, must carry ``epoch`` and a report identifier; the matched pain
    report is joined on the setting epoch rather than on time, because the epoch is the unit the
    exposure model already assigns reports to and re-deriving it here would let the two drift.
    """
    if psd_frame is None or len(psd_frame) == 0:
        return pd.DataFrame()
    ep_idx = _assign_epoch(psd_frame["t"].to_numpy(), epochs)

    rows = []
    have_epochs = epochs is not None and len(epochs) > 0
    for i, (_, r) in enumerate(psd_frame.iterrows()):
        lin, logl, mol = band_powers(r["log_psd"], r["freqs"], centers, width)
        e = int(ep_idx[i])
        ctx = {}
        if have_epochs and e >= 0:
            row = epochs.iloc[e]
            ctx = {c: row.get(c) for c in
                   ("freq_hz", "cathode_Left", "cathode_Right", "t_start", "t_end", "dur_h",
                    "epoch", "open_ended")
                   if c in epochs.columns}
            # Normalise the settings columns to the canonical spelling regardless of which one the
            # incoming frame used, so downstream estimators need to know only one name.
            for h in ("Left", "Right"):
                ac = resolve_setting_column(epochs.columns, "amp", h)
                pc = resolve_setting_column(epochs.columns, "pw", h)
                if ac:
                    ctx[canonical_amp_col(h)] = row.get(ac)
                if pc:
                    ctx[f"pw_us_{h}"] = row.get(pc)
        for c in centers:
            rows.append({
                "t": float(r["t"]), "channel": r["channel"], "source": r.get("source"),
                "setting_epoch": e, "center_hz": float(c), "band_width_hz": float(width),
                "power_linear": lin[c], "power_log_of_linear": logl[c],
                "power_mean_of_log": mol[c],
                **ctx,
            })
    T = pd.DataFrame(rows)
    if T.empty:
        return T
    for h in ("Left", "Right"):
        c = canonical_amp_col(h)
        if c in T.columns:
            T[f"era_{h}"] = [_era(x) for x in pd.to_numeric(T[c], errors="coerce")]
    if pro_frame is not None and len(pro_frame) and "epoch" in pro_frame.columns:
        keep = [c for c in ("epoch", "report_id", "nrs", "vas") if c in pro_frame.columns]
        T = T.merge(pro_frame[keep].rename(columns={"epoch": "setting_epoch"}),
                    on="setting_epoch", how="left")
    return T


def scale_disagreement(T):
    """How often the two power scales would pick a different winning band.

    This answers hypothesis H4 of the module plan directly. It is a diagnostic, not a verdict: a
    high disagreement rate does not say which scale is right, only that the choice is consequential
    and must therefore be made deliberately rather than inherited from whichever pipeline ran first.
    """
    if T is None or T.empty:
        return {"available": False, "reason": "empty table"}
    g = T.dropna(subset=["power_linear", "power_mean_of_log"])
    if g.empty:
        return {"available": False, "reason": "no rows with both scales"}
    win_lin = g.loc[g.groupby(["t", "channel"])["power_linear"].idxmax(), ["t", "channel", "center_hz"]]
    win_mol = g.loc[g.groupby(["t", "channel"])["power_mean_of_log"].idxmax(), ["t", "channel", "center_hz"]]
    m = win_lin.merge(win_mol, on=["t", "channel"], suffixes=("_lin", "_mol"))
    if m.empty:
        return {"available": False, "reason": "no comparable samples"}
    disagree = float((m.center_hz_lin != m.center_hz_mol).mean())
    return {"available": True, "n_samples": int(len(m)),
            "disagreement_rate": disagree,
            "median_abs_shift_hz": float((m.center_hz_lin - m.center_hz_mol).abs().median()),
            "note": ("fraction of (time, channel) samples where the linear and mean-of-log scales "
                     "pick a different peak band. The device uses the linear scale (D11); the "
                     "biomarker pipeline validated on mean-of-log.")}


# ---------------------------------------------------------------------------------------------
# Phase 7 seam: live platform data -> a JSON-serialisable DeploymentReport for the interface
# ---------------------------------------------------------------------------------------------
def _num(x):
    """JSON-safe number. NaN and infinity are not valid JSON and silently become nulls or crash
    the serialiser depending on the encoder, so they are converted explicitly here rather than
    being discovered by the browser."""
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return f if np.isfinite(f) else None


def report_to_dict(rep):
    """Flatten a DeploymentReport for the interface.

    The verdict is expressed as THREE states rather than a boolean, because the interface has to
    distinguish "the device forbids this" from "the evidence does not support it". Those call for
    different actions by the reader — the first is a configuration problem, the second is a
    measurement problem — and collapsing them into one "not ready" was the specific complaint the
    panel disposition raised.
    """
    el = rep.eligibility
    device_ok = bool(el.eligible) if el is not None else None
    edges_ok = bool(rep.edges) and all(e.resolved for e in rep.edges.values())
    # PRESERVE THE THREE STATES. `CoherenceReport.coherent` is None when at least one contributing
    # edge is unresolved, meaning "not established", which is a different finding from False,
    # meaning "the signs contradict each other". Wrapping it in bool() collapsed None to False and
    # made the interface report a contradiction that the data had not shown — the exact failure this
    # panel was rebuilt to prevent.
    coherent = None if rep.coherence is None else rep.coherence.coherent

    if device_ok is False:
        verdict = "blocked"
    elif rep.is_licensed():
        verdict = "supported"
    else:
        verdict = "unsupported"

    return {
        "available": True,
        "participant": rep.participant,
        "verdict": verdict,
        "licensed": rep.is_licensed(),
        "verdict_detail": {
            "device_eligible": device_ok,
            "all_edges_resolved": edges_ok,
            "coherent": coherent,
            "blockers": list(rep.blockers),
        },
        "eligibility": None if el is None else {
            "eligible": el.eligible, "checked": el.checked, "summary": el.summary(),
            "failures": el.failures, "unknowns": el.unknowns, "advisories": el.advisories,
            # The fourth bucket. Rows land here when another rule already charged the SAME
            # consideration from the SAME input, so the observation is kept and only the duplicate
            # charge against the verdict is dropped. Omitting it made the four bucket lengths fail
            # to account for the rules checked, which is the arithmetic a reader uses to satisfy
            # themselves that nothing was quietly discarded.
            "deferred": getattr(el, "deferred", []) or [],
        },
        "edges": {k: {
            "name": e.name, "estimate": _num(e.estimate),
            "ci": None if e.ci is None else [_num(e.ci[0]), _num(e.ci[1])],
            "p": _num(e.p), "n": int(e.n), "cluster_unit": e.cluster_unit,
            "n_clusters": int(e.n_clusters), "scale": e.scale, "sign": e.sign,
            "resolved": e.resolved, "note": e.note, "confounded_by": list(e.confounded_by),
            # WHICH ESTIMATOR produced the interval and the p-value, read from edges.py so the
            # switch has exactly one definition. The deployment panel used to hardcode the cluster
            # threshold in JavaScript with a comment claiming to mirror edges.py, and by then the
            # comment was wrong twice over: the constant had stopped being a disqualification floor
            # and become a choice between two estimators.
            "inference": _edges.estimator_for(e.n_clusters),
        } for k, e in (rep.edges or {}).items()},
        "coherence": None if rep.coherence is None else {
            "coherent": rep.coherence.coherent, "p_coherent": _num(rep.coherence.p_coherent),
            "expected_pattern": rep.coherence.expected_pattern,
            "observed_pattern": rep.coherence.observed_pattern,
            "n_boot": rep.coherence.n_boot, "note": rep.coherence.note,
        },
        # The programmable prescription. Every field carries its provenance because the interface
        # must be able to distinguish a value derived from this participant's data from a
        # manufacturer default and from a field whose adjustable range is unpublished — a clinician
        # transcribing these into a programmer is entitled to know which is which, and rendering
        # them identically would invite a default to be entered as though it were a measurement.
        # The controller replay. Not serialised at all until 2026-09-04, so the panel could not
        # show the counterfactual trajectory even when the pipeline had computed it. The amplitude
        # TRAJECTORY itself is deliberately omitted: it is one value per controller step over
        # months of recording, far too large for a payload, and the fractions plus the transition
        # count are what a reader acts on. Its caveat is carried through verbatim because the
        # trajectory is what the control law would have done to a power series recorded under the
        # participant's actual programming, which is not a forecast of what the device would
        # deliver once the loop is closed.
        # The titration protocol. Also unserialised until 2026-09-04, so a session plan the
        # pipeline had generated could not be shown. The power figures are carried because a plan
        # whose detectable effect size is implausibly large is a plan not worth running, and the
        # clinician is the person who can judge that; the seed is carried so a plan can be
        # regenerated identically, which is what makes the randomised order auditable rather than
        # merely random.
        "protocol": None if rep.protocol is None else {
            "steps": list(rep.protocol.steps or []),
            "n_steps": len(rep.protocol.steps or []),
            "n_pairs": rep.protocol.n_pairs,
            "alpha": rep.protocol.alpha,
            "power": rep.protocol.power,
            "detectable_d": rep.protocol.detectable_d,
            "duration_min": rep.protocol.duration_min,
            "seed": rep.protocol.seed,
            "note": rep.protocol.note,
        },
        "replay": None if rep.replay is None else {
            "frac_time_at_upper": rep.replay.frac_time_at_upper,
            "frac_time_at_lower": rep.replay.frac_time_at_lower,
            "n_transitions": rep.replay.n_transitions,
            "saturated": rep.replay.saturated,
            "params": {k: v for k, v in (rep.replay.params or {}).items()},
            "note": rep.replay.note,
        },
        # EVERY MODE, plus which one this module recommends and why. The interface renders a
        # toggle from this, so the clinician can look at what Single Threshold would require
        # instead of taking the module's word that Dual is better. `selected` is what the candidate
        # asked for and `recommended` is what this module would choose; they are deliberately
        # separate keys so a page showing the non-recommended mode still displays the advice.
        "prescriptions": None if getattr(rep, "prescriptions", None) is None else {
            "recommended": rep.prescriptions.get("recommended"),
            "selected": getattr(getattr(rep, "prescription", None), "mode", None),
            "recommendation": {k: v for k, v in (rep.prescriptions.get("recommendation") or {}).items()
                               if not k.startswith("_")},
            "modes": {m: {
                "mode": pr.mode,
                "fields": pr.as_rows(),
                "not_applicable": [{"parameter": f.name, "units": f.units, "why": f.why,
                                    "status": f.status, "origin": f.origin, "confirm": f.confirm}
                                   for f in (pr.not_applicable or [])],
                "couplings": list(pr.couplings or []),
                "unknowns": list(pr.unknowns or []),
                "note": pr.note,
                "duty": None if pr.duty is None else {
                    k: getattr(pr.duty, k) for k in (
                        "lfp_frac_above", "lfp_frac_between", "lfp_frac_below",
                        "stim_frac_at_upper", "stim_frac_at_lower", "stim_frac_mid",
                        "mean_amplitude_mA", "amplitude_duty", "transitions_per_hour",
                        "qualified_transitions", "unqualified_excursions", "hours_observed",
                        "hours_of_signal", "coverage_frac", "fractions_are_of_observed_samples",
                        "onset_windows_upper", "onset_windows_lower", "onset_inoperative",
                        "predicted_failure_mode")} | {
                    "caveats": list(pr.duty.caveats or [])},
            } for m, pr in (rep.prescriptions.get("modes") or {}).items()},
        },
        "prescription": None if getattr(rep, "prescription", None) is None else {
            "mode": rep.prescription.mode,
            "fields": rep.prescription.as_rows(),
            "not_applicable": [{"parameter": f.name, "units": f.units, "why": f.why,
                                "status": f.status, "origin": f.origin, "confirm": f.confirm}
                               for f in (rep.prescription.not_applicable or [])],
            "couplings": list(rep.prescription.couplings or []),
            "unknowns": list(rep.prescription.unknowns or []),
            "note": rep.prescription.note,
            "duty": None if rep.prescription.duty is None else {
                k: getattr(rep.prescription.duty, k) for k in (
                    "lfp_frac_above", "lfp_frac_between", "lfp_frac_below",
                    "stim_frac_at_upper", "stim_frac_at_lower", "stim_frac_mid",
                    "mean_amplitude_mA", "amplitude_duty", "transitions_per_hour",
                    "qualified_transitions", "unqualified_excursions", "hours_observed",
                    # Coverage travels with the fractions or they will be misread. Omitting these
                    # three from this tuple already happened once: the caveat text carried the
                    # numbers while the fields serialised as null, so an interface reading the
                    # fields alone could have printed "49.6% of the day" for a record with 0.012%
                    # coverage. Any field added to DutyCycle must be added here too.
                    "hours_of_signal", "coverage_frac", "fractions_are_of_observed_samples",
                    "onset_windows_upper", "onset_windows_lower", "onset_inoperative",
                    "predicted_failure_mode")} | {
                "caveats": list(rep.prescription.duty.caveats or [])},
        },
        "threshold": None if rep.threshold is None else {
            "upper": _num(rep.threshold.upper), "lower": _num(rep.threshold.lower),
            "control_authority": _num(rep.threshold.control_authority),
            "capture_amp_low": _num(rep.threshold.capture_amp_low),
            "capture_amp_high": _num(rep.threshold.capture_amp_high),
            "frac_time_below": _num(rep.threshold.frac_time_below),
            "frac_time_between": _num(rep.threshold.frac_time_between),
            "frac_time_above": _num(rep.threshold.frac_time_above),
            "predicted_recapture_alert": rep.threshold.predicted_recapture_alert,
            "problems": list(rep.threshold.problems), "note": rep.threshold.note,
        },
        "manifest": rep.manifest,
        "candidates": rep.candidates,
    }


def report_for_participant(participant, request_data=None, *, candidates=None, hemisphere="Left",
                           power_scale="power_linear", force_refresh=None):
    """Fetch this participant's data from the platform and build the report.

    Imports of the sibling modules are deferred to call time for the same reason
    ``StimOptimizer.adapter`` defers its Biomarkers import: at module import time the Django app
    registry may not be populated, and a module-level import would also create a cycle between the
    three analysis modules.
    """
    from modules.StimOptimizer import adapter as _sa
    from . import pipeline as _pl

    rd = request_data or {}
    # Both fetches go through the memo: measured at 32.96 s and 33.99 s respectively on RCS08, i.e.
    # 67 of the 70 s this endpoint used to take. build_design_matrix ACCEPTS request_data and never
    # references it, so it is a pure function of the participant and safe to key on the recording
    # set; it is called with default washin_min and items, and a caller varying those would need
    # them in the key.
    psd, eps, dm = evidence_inputs_cached(participant, force_refresh=bool(force_refresh))
    if psd is None:
        return {"available": False,
                "reason": "this participant has no assembled spectra, so no control signal can be "
                          "evaluated. Sensing recordings must be ingested first."}

    cands = candidates or rd.get("Candidates") or []
    if not cands:
        return {"available": False,
                "reason": "no candidate configuration was supplied. Choose a channel and centre "
                          "frequency on the Biomarker Exploration page first; deployability is "
                          "evaluated for a specific configuration, not for a participant."}
    # Device facts the rules need but the analysis tables cannot supply. Fetched here rather than
    # inside pipeline.run so the pipeline stays free of ORM imports and remains testable on frames.
    dev = {}
    try:
        from ClosedLoopDeployment import device_facts as _df
        from Server import models as _m
        _p = participant if hasattr(participant, "uid") else _m.Participant.find(uid=participant)
        _sfs = _m.SourceFile.find_all(owner=_p)
        _imp = list(_m.Recording.find_all(source__in=_sfs, type="MedtronicDeviceImpedance"))
        _hemi = (cands[0] or {}).get("actuated_hemisphere") or (cands[0] or {}).get(
            "sensing_hemisphere") or hemisphere
        dev = _df.facts_for_participant(getattr(_p, "uid", participant), _imp,
                                        hemisphere=_hemi,
                                        channel=(cands[0] or {}).get("channel"))
    except Exception as exc:                      # never let a fact lookup take down the report
        dev = {"_provenance": {}, "_error": f"device facts unavailable: {exc!r}"}

    rep = _pl.run(getattr(participant, "uid", participant), psd_frame=psd, epochs=eps,
                  design_matrix=dm, candidates=cands, hemisphere=hemisphere,
                  power_scale=power_scale, device_facts=dev)
    out = report_to_dict(rep)
    out["device_facts"] = {k: v for k, v in dev.items() if not k.startswith("_")}
    out["device_facts_provenance"] = dev.get("_provenance", {})
    out["impedance_status"] = dev.get("_impedance_status")
    out["impedance_status_counts"] = dev.get("_impedance_status_counts")
    return out
