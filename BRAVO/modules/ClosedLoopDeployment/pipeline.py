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
    amp_col = f"amp_{hemisphere}"
    if amp_col in d.columns and len(d):
        amps = d[amp_col].astype(float)
        lo_a, hi_a = amps.min(), amps.max()
        if np.isfinite(lo_a) and np.isfinite(hi_a) and hi_a > lo_a:
            rep.threshold = A.threshold_placement(
                d.loc[amps <= lo_a, power_scale].to_numpy(),
                d.loc[amps >= hi_a, power_scale].to_numpy(),
                amp_low=float(lo_a), amp_high=float(hi_a),
                expected_sign=-1, observed_series=d[power_scale].to_numpy())

    # --- optional pieces ------------------------------------------------------------------------
    prot = _optional("protocol")
    if prot is not None and hasattr(prot, "titration_plan"):
        try:
            rep.protocol = prot.titration_plan(cand, seed=seed)
        except Exception as ex:
            rep.blockers.append(f"protocol generation failed: {ex}")

    if strict and rep.threshold is not None and rep.threshold.problems:
        rep.blockers.extend(rep.threshold.problems)
    return rep
