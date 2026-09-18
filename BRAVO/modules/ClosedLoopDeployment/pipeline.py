"""One entry point: participant in, DeploymentReport out.

Mirrors the signature style of ``modules/StimOptimizer/pipeline.run`` and
``modules/Biomarkers/pipeline`` so the three modules read alike.

The report is deliberately conjunctive and deliberately pessimistic. ``DeploymentReport.is_licensed``
requires device eligibility AND three resolved edges AND a coherent sign pattern AND no blocker.
Anything unmeasured reads as not licensed, because on a device that actuates, treating absence of
evidence as permission is the specific failure this module exists to prevent.

"Resolved" has meant the POINT SIGN since 2026-09-13 (PI rule: "established means mean only for
flexibility", read as "point sign decides, but flag as provisional"): an edge with a finite,
non-zero estimate has a direction; its interval and p stay on the page as caveats; a report
licensed while any interval spans zero is ``provisional`` and its verdict string says so.
"""
from __future__ import annotations

import numpy as np

from . import adapter, edges as E, consistency as C, authority as A
from .types import DeploymentReport, EdgeEstimate



# Aditya canonical compatibility imports/constants.

import pandas as pd



def _optional(name):
    """Import a sibling that may not exist yet, returning None rather than exploding.

    The module is being built in parts; a pipeline that cannot run until every file lands would be
    untestable for as long as that takes.
    """
    try:
        import importlib
        return importlib.import_module(f".{name}", __package__)
    except Exception:
        return None


def _participant_facts(participant_uid, device_facts=None, constraints_module=None,
                       participant_context=None):
    """Build the PARTICIPANT dict, routing participant-scoped device facts into it.

    A fact one dictionary away from the rule that reads it is invisible, and the symptom is
    indistinguishable from genuinely missing data: the rule reports "input not supplied" and blocks
    the verdict. D04 reads ``n_neurostimulators``, D16 reads ``lead_type`` and D31 reads the
    BrainSense envelope, all from HERE rather than from the candidate — so merging every device
    fact into the candidate left those rules unevaluable while their values were present. Scope is
    taken from the constraint module's own ``PARTICIPANT_KEYS`` rather than a list kept here, so a
    rule that changes which dict it reads cannot silently strand its input again.
    """
    facts = {**(participant_context or {}), "uid": participant_uid}
    scoped = set(getattr(constraints_module, "PARTICIPANT_KEYS", {}) or {})
    for k, v in (device_facts or {}).items():
        if k.startswith("_"):
            continue
        if k in scoped and facts.get(k) is None:
            facts[k] = v
    return facts


def _facts_for(candidate, e1, e2, power_scale, device_facts=None, threshold=None):
    """The candidate dict augmented with the facts this module has actually established.

    ``threshold`` is the ``ThresholdPlan`` placed for this candidate, when one was; its
    ``predicted_recapture_alert`` is what rule D26 reads (review C2, 2026-09-12: the ledger's D26
    row had never once been evaluated, because eligibility ran BEFORE the plan that computes the
    alert existed, and nothing else sets the key).

    Two rules about what may be filled in here, both of which exist to stop a gate being satisfied
    by something that was never measured.

    A SIGN IS SUPPLIED ONLY WHEN ITS EDGE IS RESOLVED. Rule D19 asks which way the band moves. An
    unresolved edge has a point estimate with a sign, but that sign is not established — the
    interval spans zero. Passing it would let D19 be satisfied by a direction the data does not
    support, which is precisely the substitution of a guess for a measurement that this module is
    built to refuse. An absent key is reported as not determinable, and not determinable blocks.
    (SUPERSEDED 2026-09-12 by the PI's decision, kept here because this project keeps a reversed
    rule on the record rather than deleting it. The paragraph below is the rule in force.)

    THE POWER SCALE IS A FACT ABOUT THIS RUN, not an assumption. It is whatever scale the edges were
    actually estimated on, so if a caller asks for the log scale, D11 correctly fails rather than
    silently reporting the linear scale the device requires."""
    f = dict(candidate or {})
    sign_keys = {"power_slope_vs_amplitude_sign", "power_slope_vs_pain_sign"}
    for key in sign_keys:
        f.pop(key, None)
    f.setdefault("intent", "adaptive")
    f["power_scale"] = "linear" if power_scale == "power_linear" else "log"
    # One centre frequency and one threshold mode per report, so no pooling occurs by construction.
    f.setdefault("pooled_across_center_or_mode", False)
    # PI decision 2026-09-12: the point sign is supplied whenever the edge has one, and whether it
    # is statistically established travels beside it rather than deciding whether it is supplied.
    for _edge, _key in ((e1, "power_slope_vs_amplitude"), (e2, "power_slope_vs_pain")):
        if _edge is None or _edge.sign is None:
            continue
        f[f"{_key}_sign"] = int(_edge.sign)
        # Since 2026-09-13 ``resolved`` is the point sign itself (PI: "established means mean
        # only"), so the flag D19 prints beside the sign reads the interval rule by its own name.
        f[f"{_key}_sign_established"] = bool(getattr(_edge, "statistically_established", False))
        if _edge.ci is not None:
            try:
                f[f"{_key}_ci"] = [float(_edge.ci[0]), float(_edge.ci[1])]
            except (TypeError, ValueError, IndexError):
                pass
        if _edge.p is not None:
            try:
                f[f"{_key}_p"] = float(_edge.p)
            except (TypeError, ValueError):
                pass
    # Participant-level device facts are merged LAST and never overwrite a value the candidate
    # already carries: an explicit per-candidate setting is a deliberate override, while these are
    # defaults for the participant. Keys beginning with an underscore are provenance and diagnostics
    # for the interface, not inputs to any predicate, so they are excluded.
    for _k, _v in (device_facts or {}).items():
        if not _k.startswith("_") and _k not in sign_keys and f.get(_k) is None:
            f[_k] = _v
    # D26, from the threshold plan this same run placed. Only a plan that actually carries the
    # alert fills it in: a run with no plan (no thresholds could be placed) leaves the key absent,
    # so D26 reads "not determinable" rather than passing on nothing.
    if threshold is not None:
        _alert = getattr(threshold, "predicted_recapture_alert", None)
        if _alert is not None and f.get("predicted_recapture_alert") is None:
            f["predicted_recapture_alert"] = bool(_alert)
        # Participant-specific provenance and examples are maintained outside source control.
        _why = [str(w) for w in (getattr(threshold, "warnings", None) or []) if w]
        if _why and f.get("predicted_recapture_alert_reason") is None:
            f["predicted_recapture_alert_reason"] = "; ".join(_why)
        f.setdefault("_threshold_plan_placed", True)
    return f


def run(participant_uid, *, psd_frame=None, epochs=None, design_matrix=None, pro_frame=None,
        candidates=(), washin_s=60.0, amp_limit_ma=5.0, power_scale="power_linear",
        hemisphere="Left", strict=True, n_boot=500, seed=0, device_facts=None,
        pooled_e1=None, place_thresholds=None, participant_context=None,
        outcome="nrs", outcome_cluster="report_id", band_width_hz=5.0, include_planning=True):
    """Build the deployment report for one participant.

    ``place_thresholds`` (decision 180): a callable ``(rep, candidates) -> (plan, placement)``
    invoked right after the capture rule has placed ``rep.threshold`` and BEFORE the eligibility
    ledger, the replay and the prescription rows read it, so every one of them describes the pair
    the card recommends. The adapter passes its record-based step
    (`adapter._place_thresholds_from_record`); ``None`` keeps the capture pair. The placement dict
    is kept on ``rep.threshold_placement``.

    ``psd_frame`` and ``epochs`` are what ``StimOptimizer.adapter.evidence_inputs`` returns. They are
    passed in rather than fetched here so this function stays testable without a database, and so
    the caller controls the expensive spectral assembly.
    """
    rep = DeploymentReport(participant=str(participant_uid))
    # If no separate pain frame was supplied but the design matrix already carries one rating per
    # exposure epoch, use it. Without this E2 silently has no outcome to regress on and reports
    # itself unestimable, which reads like a data problem when it is only a wiring one.
    if pro_frame is None and design_matrix is not None and len(design_matrix):
        cols = [c for c in ("epoch", outcome) if c in design_matrix.columns]
        if "epoch" in cols and len(cols) > 1:
            pro_frame = design_matrix[cols].copy()
            pro_frame["report_id"] = pro_frame["epoch"].astype(str)
    # THE SIDE IS THE CANDIDATE'S OWN (review C1, 2026-09-12): its actuated side, else its sensing
    # side, else what the caller passed. ``hemisphere`` decides which current column E1, E3, the
    # capture currents and the prescription read, and which side the manifest names; the page used
    # to send "Left" for every request, so a band on a right contact was read against the LEFT
    # stimulator's current. The caller's value is a fallback for a candidate that names no side.
    _first_side = (candidates[0] if candidates and isinstance(candidates[0], dict) else {}) or {}
    _side = (_first_side.get("actuated_hemisphere") or _first_side.get("sensing_hemisphere")
             or hemisphere)
    hemisphere = {"left": "Left", "right": "Right"}.get(str(_side).strip().lower(), _side)
    # The candidate's own centre joins the default grid, so a committed band outside 10.5 to
    # 27.5 Hz (the sweep offers 8.5 to 29.5) is evaluated rather than silently matching no rows.
    cen = set(float(c) for c in adapter.DEFAULT_BAND_CENTERS_HZ)
    for cd in (candidates or ()):
        try:
            cen.add(float(cd.get("center_hz")))
        except (TypeError, ValueError, AttributeError):
            pass
    T = adapter.joined_table_cached(psd_frame, epochs, pro_frame=pro_frame,
                                    centers=tuple(sorted(cen)), width=band_width_hz)
    if not T.empty:
        T = T[T.setting_epoch >= 0].copy()
        if "t_start" in T.columns:
            starts = pd.to_datetime(T.t_start, utc=True).to_numpy().astype("datetime64[ns]").astype("int64") / 1e9
            T = T[T.t >= starts + float(washin_s)].copy()
    rep.manifest = {
        "n_psd_rows": 0 if psd_frame is None else int(len(psd_frame)),
        "n_epochs": 0 if epochs is None else int(len(epochs)),
        "n_table_rows": int(len(T)),
        "power_scale": power_scale, "washin_s": float(washin_s),
        "amp_limit_ma": float(amp_limit_ma), "hemisphere": hemisphere,
        "outcome": outcome, "outcome_cluster": outcome_cluster,
        "participant_context": dict(participant_context or {}),
        "scale_disagreement": adapter.scale_disagreement(T),
    }
    if T.empty:
        rep.blockers.append("no joined table could be built: the participant has no assembled "
                            "spectra, or none of them fall inside a known setting epoch")
        return rep

    cand = list(candidates) or []
    if not cand:
        rep.blockers.append("no candidate configurations supplied; nothing to evaluate")
        return rep
    first = cand[0]
    ch, fc = first.get("channel"), float(first.get("center_hz", np.nan))
    rep.candidates = cand

    # --- Phase 2 runs BEFORE Phase 1 -------------------------------------------------------------
    # The order looks wrong and is deliberate. Rule D19 — the requirement that band power falls as
    # amplitude rises and rises with pain — is the single most important device gate, and it cannot
    # be evaluated until the edges have been estimated. Checking eligibility first would report D19
    # as "not determinable" on every run, which is the least useful possible answer for the one rule
    # that decides whether the control loop is negative feedback or positive.
    e1 = E.actuation_edge(T, channel=ch, center_hz=fc, hemisphere=hemisphere, scale=power_scale, n_boot=n_boot, seed=seed)
    # E1 FROM THE POOLED TITRATION SLOPE when the stored row exists (redesign decision 9, decision
    # 124 in the log, the PI's choice on 2026-09-11): the same row the three-source panel draws, so
    # the triangle and the panel cannot disagree. The historical setting-epoch estimate is kept
    # on the report beside it rather than thrown away. A row with no assessed slope leaves the
    # historical estimate in place -- absence of a pooled answer is not a reason to lose an edge.
    # `pooled_edge` is what the two D26 capture verdicts read (PI decision 2026-09-12, "b and c");
    # it stays None when no slope is stored so those verdicts say "not assessed" rather than
    # quietly reading the historical setting-epoch edge, which is a different quantity.
    pooled_edge = None
    # Use the shared edge boundary: strings, booleans and nonfinite values are absent
    # evidence, even when a persisted row can be coerced to a float.
    if isinstance(pooled_e1, dict) and EdgeEstimate(
            "E1", pooled_e1.get("pooled_slope_per_mA"), None, None, 0, "", 0).sign is not None:
        rep.edges_historical = {"E1": e1}
        e1 = E.pooled_actuation_edge(pooled_e1, scale=power_scale)
        pooled_edge = e1
    e2 = E.state_edge(T, channel=ch, center_hz=fc, scale=power_scale,
                      outcome=outcome, cluster=outcome_cluster, n_boot=n_boot, seed=seed)
    # E3 ON THE ACTUATED SIDE'S CURRENT (review C1). ``therapy_edge`` defaults to the left column;
    # the design matrix carries one amplitude column per side, and the side the loop would drive
    # is the one whose current is regressed on pain.
    _e3_col = adapter.canonical_amp_col(hemisphere)
    if design_matrix is not None and hasattr(design_matrix, "columns"):
        _e3_col = (adapter.resolve_setting_column(design_matrix.columns, "amp", hemisphere)
                   or adapter.canonical_amp_col(hemisphere))
    e3 = (E.therapy_edge(design_matrix, amp_col=_e3_col, outcome=outcome, n_boot=n_boot, seed=seed) if _e3_col
          else E.therapy_edge(design_matrix, outcome=outcome, n_boot=n_boot, seed=seed))
    rep.edges = {"E1": e1, "E2": e2, "E3": e3}
    rep.coherence = C.coherence_report(e1, e2, e3)

    # --- control authority and threshold placement ----------------------------------------------
    d = T[(T.channel == ch) & (np.isclose(T.center_hz, fc))].dropna(subset=[power_scale])
    # THE COLUMN NAME COMES FROM THE ADAPTER, NOT FROM AN f-STRING HERE. Fixed 2026-09-04.
    #
    # This read `f"amp_{hemisphere}"` while the joined table spells the column `amp_mA_Left`, with
    # the unit in the name. The membership test therefore failed on every real report, the whole
    # threshold-placement block was skipped, and `rep.threshold` came back None — with no error and
    # no blocker, because a skipped block raises nothing. Downstream that made the prescription
    # absent too, and the payload looked exactly as it would if the participant genuinely had no
    # amplitude on record. `adapter.canonical_amp_col` is the single definition of this name and is
    # used here so the two cannot drift apart again.
    if include_planning:
        amp_col = adapter.canonical_amp_col(hemisphere)
        if amp_col not in d.columns:
            # Fall back to the tolerant resolver before giving up, since older frames in the artifact
            # store predate the canonical spelling, then say plainly which name was missing.
            try:
                amp_col = adapter.resolve_setting_column(d.columns, "amp", hemisphere) or amp_col
            except Exception:
                pass
        if amp_col not in d.columns and len(d):
            rep.blockers.append(
                f"no {hemisphere} amplitude column in the joined table (looked for "
                f"{adapter.canonical_amp_col(hemisphere)!r}; the table has "
                f"{sorted(c for c in d.columns if 'amp' in c.lower())!r}), so no thresholds were "
                f"placed and no prescription was generated")
        if amp_col in d.columns and len(d):
            amps = d[amp_col].astype(float)
            # Participant-specific provenance and examples are maintained outside source control.
            therapeutic = amps[amps > 0]
            if not len(therapeutic):
                rep.blockers.append(
                    f"no nonzero {hemisphere} amplitude on record for this cell, so the two capture "
                    f"amplitudes cannot both be therapeutic (D07, D28) and no thresholds were placed")
                lo_a = hi_a = float("nan")
            else:
                lo_a, hi_a = therapeutic.min(), therapeutic.max()
            if np.isfinite(lo_a) and np.isfinite(hi_a) and hi_a > lo_a:
                rep.threshold = A.threshold_placement(
                    d.loc[(amps > 0) & (amps <= lo_a), power_scale].to_numpy(),
                    d.loc[(amps > 0) & (amps >= hi_a), power_scale].to_numpy(),
                    amp_low=float(lo_a), amp_high=float(hi_a),
                    expected_sign=-1, observed_series=d[power_scale].to_numpy(),
                    pooled_slope=pooled_edge)
                # THE PAIR FROM THE RECORD (decision 180): re-placed here, so the ledger, the replay
                # and the rows below all read the pair the card recommends, with the capture pair
                # kept beside it on the plan.
                if place_thresholds is not None:
                    try:
                        rep.threshold, rep.threshold_placement = place_thresholds(rep, list(candidates))
                    except Exception as _pex:              # noqa: BLE001 - the capture pair stands
                        rep.threshold_placement = {"available": False,
                                                   "reason": f"placement failed: {_pex!r}"}
            elif np.isfinite(lo_a) and np.isfinite(hi_a):
                # ONE therapeutic current on record (review C12, 2026-09-12). The two capture
                # amplitudes must differ (D24: the thresholds are read at a low and a high current),
                # so no plan can be placed -- and until this line nothing said so: the block was
                # skipped, ``rep.threshold`` stayed None, and ``is_licensed`` does not require a plan,
                # so with a stored pooled slope such a report could have read "supported" with no
                # prescription behind it.
                rep.blockers.append(
                    f"only one therapeutic {hemisphere} amplitude on record for this cell "
                    f"({float(lo_a):g} mA), so no low and high capture amplitudes exist (D24) and no "
                    f"thresholds were placed")

    # --- Phase 1: device eligibility, with every fact this module can legitimately supply ---------
    # RUNS AFTER THRESHOLD PLACEMENT, NOT BEFORE (review C2, 2026-09-12). Rule D26 reads the
    # predicted RECAPTURE THRESHOLDS alert, and the only place that value is computed is the
    # threshold plan above; with eligibility checked first the D26 row read "could not be
    # determined from the inputs given" on every report ever made, while the same request computed
    # the alert a few lines later and serialised it where the page does not show it. Nothing in
    # threshold placement reads the eligibility report, and D19 still sees the edges because they
    # are estimated first, so the move changes only which facts D26 is handed.
    con = _optional("constraints")
    if con is not None and hasattr(con, "check_eligibility"):
        # Device facts must be routed to the dict the rule actually READS. Several rules take
        # their input from the PARTICIPANT dict rather than the candidate — D04 reads
        # n_neurostimulators, D16 reads lead_type, D31 reads the BrainSense envelope — so merging
        # everything into the candidate left those rules unevaluable while the values sat one
        # dictionary away. That failure is silent: the rule reports "input not supplied" and the
        # verdict stays blocked, which looks identical to genuinely missing data.
        rep.eligibility = con.check_eligibility(
            _facts_for(first, e1, e2, power_scale, device_facts=device_facts,
                       threshold=rep.threshold),
            _participant_facts(participant_uid, device_facts, con, participant_context))
    else:
        rep.blockers.append("constraints.py not available: device eligibility was NOT checked, so "
                            "no candidate may be licensed")

    # --- controller replay -----------------------------------------------------------------------
    # Run BEFORE the prescription because the prescription's amplitude-side duty figures come from
    # it. Without this the module reported time spent past a threshold but nothing about time spent
    # at an amplitude limit, and those are different quantities: the amplitude ramps slowly, so a
    # brief excursion past a threshold moves it only part of the way. The replay needs a strictly
    # increasing time base and the joined table has duplicate timestamps, so the series is collapsed
    # to one power value per timestamp first rather than letting the replay refuse it.
    if include_planning:
        rpl = _optional("replay")
        if rpl is not None and rep.threshold is not None and len(d) and "t" in d.columns:
            try:
                g = (d[["t", power_scale]].dropna().groupby("t", as_index=False)[power_scale].mean()
                     .sort_values("t"))
                if len(g) >= 3:
                    t0 = float(g["t"].iloc[0])
                    # Segment-wise, because a chronic record is streaming bursts separated by days and
                    # the single-shot replay correctly refuses a non-uniform interval rather than
                    # attributing a month-long gap to the controller's ramp.
                    rep.replay = rpl.dual_threshold_segments(
                        (g["t"].astype(float) - t0).to_numpy(),
                        g[power_scale].astype(float).to_numpy(), rep.threshold)
            except Exception as ex:
                rep.blockers.append(f"controller replay failed: {ex}")

        # --- the programmable prescription ----------------------------------------------------------
        # Built LAST among the analytic steps because it consumes their outputs: the thresholds place
        # the LFP fields, the timing plan sets the averaging and ramp, and the replay supplies the
        # amplitude-side duty cycle. It is deliberately built even when the verdict is blocked, because
        # a clinician reviewing a blocked configuration still needs to see what would be programmed —
        # that is often how the blocker becomes intelligible. Whether it may be ENTERED is the
        # verdict's business, not this file's, and the interface must not present a prescription from a
        # blocked report as though it were authorised.
        presc = _optional("prescription")
        if presc is not None and rep.threshold is not None:
            try:
                from modules.StimOptimizer.routines import percept_adaptive as _PA
                _mode = (first or {}).get("threshold_mode") or _PA.DUAL
                _t = d["t"].to_numpy() if "t" in d.columns else None
                # Participant-specific provenance and examples are maintained outside source control.
                _tr = _optional("timing_recommendation")
                _record_timing = _tr.for_participant(participant_uid) if _tr is not None else {}
                _prog_all = (device_facts or {}).get("active_sensing_group_timing") or {}
                _programmed = _prog_all.get(hemisphere) if isinstance(_prog_all, dict) else None
                _all = presc.prescribe_all_modes(
                    threshold_plan=rep.threshold, candidate=first,
                    power_series=d[power_scale].to_numpy() if len(d) else None,
                    t_s=_t, replay_result=rep.replay,
                    validated_hemispheres=(hemisphere,) if rep.threshold is not None else (),
                    configuring_both_hemispheres=False,
                    record_timing=_record_timing, programmed_timing=_programmed or {})
                rep.prescriptions = _all
                # `rep.prescription` stays as the mode the CANDIDATE asked for, so callers that predate
                # the toggle keep the behaviour they had. The recommendation is separate from the
                # selection on purpose: a clinician exploring Single Threshold must not have the page
                # silently switch back to what the module prefers.
                rep.prescription = (_all["modes"].get(_mode)
                                    or _all["modes"].get(_all["recommended"]))
            except Exception as ex:
                rep.blockers.append(f"prescription generation failed: {ex}")

        # --- optional pieces ------------------------------------------------------------------------
        prot = _optional("protocol")
        if prot is not None and hasattr(prot, "titration_plan"):
            try:
                # The titration session varies AMPLITUDE, so each candidate must carry the amplitude to
                # be tested; the screen's candidates describe a sensing configuration and do not. The
                # two capture amplitudes are the right ladder ends: they are the amplitudes the
                # thresholds were captured at (D24) and the ones the adaptive limits inherit (D28), so
                # testing between them is testing the range the loop will actually operate over.
                _cand = list(cand or [])
                if rep.threshold is not None:
                    _lo = getattr(rep.threshold, "capture_amp_low", None)
                    _hi = getattr(rep.threshold, "capture_amp_high", None)
                    if _lo is not None and _hi is not None:
                        # Each arm needs its OWN label. The protocol groups differences by label and
                        # refuses duplicates, correctly: two arms sharing a label would be pooled into
                        # one comparison, which is exactly the amplitude contrast the session exists
                        # to measure. So the label carries the amplitude that distinguishes them.
                        _cand = [dict(c, test_amp_mA=a,
                                      label=f"{c.get('channel', 'candidate')} @ {a:g} mA")
                                 for c in _cand for a in (float(_lo), float(_hi))]
                rep.protocol = prot.titration_plan(_cand, seed=seed)
            except Exception as ex:
                rep.blockers.append(f"protocol generation failed: {ex}")

    if strict and rep.threshold is not None and rep.threshold.problems:
        rep.blockers.extend(rep.threshold.problems)
    # THE TWO D26 CAPTURE VERDICTS WARN AND DO NOT BLOCK. PI decision 2026-09-12, "b and c". They
    # used to travel in `threshold.problems` and land in `blockers` on the line above; they now
    # travel in `threshold.warnings` and land in `rep.warnings`, which `is_licensed` does not
    # read. Copied whether or not the run is strict, because a sentence that gates nothing has no
    # strictness to respect.
    if rep.threshold is not None and getattr(rep.threshold, "warnings", None):
        rep.warnings.extend(rep.threshold.warnings)
    return rep


# Retained active Aditya interfaces.
