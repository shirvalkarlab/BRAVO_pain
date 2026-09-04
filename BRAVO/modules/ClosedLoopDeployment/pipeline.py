"""One entry point: participant in, DeploymentReport out.

Mirrors the signature style of ``modules/StimOptimizer/pipeline.run`` and
``modules/Biomarkers/pipeline`` so the three modules read alike.

The report is deliberately conjunctive and deliberately pessimistic. ``DeploymentReport.is_licensed``
requires device eligibility AND three resolved edges AND a coherent sign pattern AND no blocker.
Anything unmeasured reads as not licensed, because on a device that actuates, treating absence of
evidence as permission is the specific failure this module exists to prevent.
"""
from __future__ import annotations

import numpy as np

from . import adapter, edges as E, consistency as C, authority as A
from .types import DeploymentReport


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


def _participant_facts(participant_uid, device_facts=None, constraints_module=None):
    """Build the PARTICIPANT dict, routing participant-scoped device facts into it.

    A fact one dictionary away from the rule that reads it is invisible, and the symptom is
    indistinguishable from genuinely missing data: the rule reports "input not supplied" and blocks
    the verdict. D04 reads ``n_neurostimulators``, D16 reads ``lead_type`` and D31 reads the
    BrainSense envelope, all from HERE rather than from the candidate — so merging every device
    fact into the candidate left those rules unevaluable while their values were present. Scope is
    taken from the constraint module's own ``PARTICIPANT_KEYS`` rather than a list kept here, so a
    rule that changes which dict it reads cannot silently strand its input again.
    """
    facts = {"uid": participant_uid,
             "indication": "chronic_pain",
             # PI decision recorded 2026-09-03. This is a clinical and regulatory determination,
             # not an engineering conclusion of this module.
             "programming_mode": "parkinsons"}
    scoped = set(getattr(constraints_module, "PARTICIPANT_KEYS", {}) or {})
    for k, v in (device_facts or {}).items():
        if k.startswith("_"):
            continue
        if k in scoped and facts.get(k) is None:
            facts[k] = v
    return facts


def _facts_for(candidate, e1, e2, power_scale, device_facts=None):
    """The candidate dict augmented with the facts this module has actually established.

    Two rules about what may be filled in here, both of which exist to stop a gate being satisfied
    by something that was never measured.

    A SIGN IS SUPPLIED ONLY WHEN ITS EDGE IS RESOLVED. Rule D19 asks which way the band moves. An
    unresolved edge has a point estimate with a sign, but that sign is not established — the
    interval spans zero. Passing it would let D19 be satisfied by a direction the data does not
    support, which is precisely the substitution of a guess for a measurement that this module is
    built to refuse. An absent key is reported as not determinable, and not determinable blocks.

    THE POWER SCALE IS A FACT ABOUT THIS RUN, not an assumption. It is whatever scale the edges were
    actually estimated on, so if a caller asks for the log scale, D11 correctly fails rather than
    silently reporting the linear scale the device requires.
    """
    f = dict(candidate or {})
    f.setdefault("intent", "adaptive")
    f["power_scale"] = "linear" if power_scale == "power_linear" else "log"
    # One centre frequency and one threshold mode per report, so no pooling occurs by construction.
    f.setdefault("pooled_across_center_or_mode", False)
    if e1 is not None and e1.resolved and e1.sign is not None:
        f["power_slope_vs_amplitude_sign"] = int(e1.sign)
    if e2 is not None and e2.resolved and e2.sign is not None:
        f["power_slope_vs_pain_sign"] = int(e2.sign)
    # Participant-level device facts are merged LAST and never overwrite a value the candidate
    # already carries: an explicit per-candidate setting is a deliberate override, while these are
    # defaults for the participant. Keys beginning with an underscore are provenance and diagnostics
    # for the interface, not inputs to any predicate, so they are excluded.
    for _k, _v in (device_facts or {}).items():
        if not _k.startswith("_") and f.get(_k) is None:
            f[_k] = _v
    return f


def run(participant_uid, *, psd_frame=None, epochs=None, design_matrix=None, pro_frame=None,
        candidates=(), washin_s=60.0, amp_limit_ma=5.0, power_scale="power_linear",
        hemisphere="Left", strict=True, n_boot=500, seed=0, device_facts=None):
    """Build the deployment report for one participant.

    ``psd_frame`` and ``epochs`` are what ``StimOptimizer.adapter.evidence_inputs`` returns. They are
    passed in rather than fetched here so this function stays testable without a database, and so
    the caller controls the expensive spectral assembly.
    """
    rep = DeploymentReport(participant=str(participant_uid))
    # If no separate pain frame was supplied but the design matrix already carries one rating per
    # exposure epoch, use it. Without this E2 silently has no outcome to regress on and reports
    # itself unestimable, which reads like a data problem when it is only a wiring one.
    if pro_frame is None and design_matrix is not None and len(design_matrix):
        cols = [c for c in ("epoch", "nrs", "vas") if c in design_matrix.columns]
        if "epoch" in cols and len(cols) > 1:
            pro_frame = design_matrix[cols].copy()
            pro_frame["report_id"] = pro_frame["epoch"].astype(str)
    T = adapter.joined_table_cached(psd_frame, epochs, pro_frame=pro_frame)
    rep.manifest = {
        "n_psd_rows": 0 if psd_frame is None else int(len(psd_frame)),
        "n_epochs": 0 if epochs is None else int(len(epochs)),
        "n_table_rows": int(len(T)),
        "power_scale": power_scale, "washin_s": float(washin_s),
        "amp_limit_ma": float(amp_limit_ma), "hemisphere": hemisphere,
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
    e1 = E.actuation_edge(T, channel=ch, center_hz=fc, hemisphere=hemisphere, scale=power_scale)
    e2 = E.state_edge(T, channel=ch, center_hz=fc, scale=power_scale)
    e3 = E.therapy_edge(design_matrix)
    rep.edges = {"E1": e1, "E2": e2, "E3": e3}
    rep.coherence = C.coherence_report(e1, e2, e3)

    # --- Phase 1: device eligibility, with every fact this module can legitimately supply ---------
    con = _optional("constraints")
    if con is not None and hasattr(con, "check_eligibility"):
        # Device facts must be routed to the dict the rule actually READS. Several rules take
        # their input from the PARTICIPANT dict rather than the candidate — D04 reads
        # n_neurostimulators, D16 reads lead_type, D31 reads the BrainSense envelope — so merging
        # everything into the candidate left those rules unevaluable while the values sat one
        # dictionary away. That failure is silent: the rule reports "input not supplied" and the
        # verdict stays blocked, which looks identical to genuinely missing data.
        rep.eligibility = con.check_eligibility(
            _facts_for(first, e1, e2, power_scale, device_facts=device_facts),
            _participant_facts(participant_uid, device_facts, con))
    else:
        rep.blockers.append("constraints.py not available: device eligibility was NOT checked, so "
                            "no candidate may be licensed")

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
        # THE CAPTURE AMPLITUDES MUST BOTH BE THERAPEUTIC, so zero is excluded. Fixed 2026-09-04.
        #
        # This previously used the plain minimum of the observed amplitudes, and on RCS08 that
        # minimum is 0.0 mA, so the "lower capture amplitude" was stimulation switched OFF. Two
        # separate things go wrong with that and both are serious.
        #
        # First, it reintroduces the exact confound the amplitude-response screen was built to
        # eliminate. Comparing band power at 0 mA against band power at 4.8 mA is comparing a
        # recording with no stimulation artefact against one with a large artefact, so any
        # difference in band power is uninterpretable as a physiological response — it is at least
        # partly the artefact appearing and disappearing.
        #
        # Second, it produces a prescription the device will not accept. The adaptive amplitude
        # limits inherit the capture amplitudes (D28) and the lower limit must be strictly above
        # zero (D07), because an adaptive lower limit of zero means therapy switches off entirely
        # whenever the band is quiet, which is a rebound risk rather than a therapeutic floor. A
        # capture at 0 mA therefore yields a lower amplitude limit that fails D07 and D28.
        #
        # The lowest THERAPEUTIC amplitude on record is used instead. When the record contains no
        # nonzero amplitude for this hemisphere there is nothing to capture from and the threshold
        # placement is skipped, which is reported rather than silently substituted.
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
                expected_sign=-1, observed_series=d[power_scale].to_numpy())

    # --- controller replay -----------------------------------------------------------------------
    # Run BEFORE the prescription because the prescription's amplitude-side duty figures come from
    # it. Without this the module reported time spent past a threshold but nothing about time spent
    # at an amplitude limit, and those are different quantities: the amplitude ramps slowly, so a
    # brief excursion past a threshold moves it only part of the way. The replay needs a strictly
    # increasing time base and the joined table has duplicate timestamps, so the series is collapsed
    # to one power value per timestamp first rather than letting the replay refuse it.
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
            from StimOptimizer.routines import percept_adaptive as _PA
            _mode = (first or {}).get("threshold_mode") or _PA.DUAL
            _t = d["t"].to_numpy() if "t" in d.columns else None
            # ALL modes, not just the recommended one. The clinician chooses the mode, so the
            # interface needs a toggle, and a toggle needs every option's field set. Building them
            # here rather than on demand also means the comparison is against one snapshot of the
            # data instead of two fetches that could straddle a change.
            _all = presc.prescribe_all_modes(
                threshold_plan=rep.threshold, candidate=first,
                power_series=d[power_scale].to_numpy() if len(d) else None,
                t_s=_t, replay_result=rep.replay,
                validated_hemispheres=(hemisphere,) if rep.threshold is not None else (),
                configuring_both_hemispheres=False)
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
    return rep
