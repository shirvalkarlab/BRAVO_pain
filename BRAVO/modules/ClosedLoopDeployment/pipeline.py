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


def run(participant_uid, *, psd_frame=None, epochs=None, design_matrix=None, pro_frame=None,
        candidates=(), washin_s=60.0, amp_limit_ma=5.0, power_scale="power_linear",
        hemisphere="Left", strict=True, n_boot=500, seed=0):
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
    T = adapter.joined_table(psd_frame, epochs, pro_frame=pro_frame)
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

    # --- Phase 1: device eligibility, if constraints.py has landed -----------------------------
    con = _optional("constraints")
    if con is not None and hasattr(con, "check_eligibility"):
        rep.eligibility = con.check_eligibility(first, {"uid": participant_uid,
                                                        "programming_mode": "parkinsons"})
    else:
        rep.blockers.append("constraints.py not available: device eligibility was NOT checked, so "
                            "no candidate may be licensed")

    # --- Phase 2: the three edges ---------------------------------------------------------------
    e1 = E.actuation_edge(T, channel=ch, center_hz=fc, hemisphere=hemisphere, scale=power_scale)
    e2 = E.state_edge(T, channel=ch, center_hz=fc, scale=power_scale)
    e3 = E.therapy_edge(design_matrix)
    rep.edges = {"E1": e1, "E2": e2, "E3": e3}
    rep.coherence = C.coherence_report(e1, e2, e3)

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
