"""Read-only Phase 0–3 research review on BRAVO's approved data.

No request may supply observations or programmer settings. The source branch's
historical retirement finding is retained separately from this recomputed review.
"""
from dataclasses import asdict
import logging
import math

from . import pipeline, device_facts, adapter, historical_configurations

log = logging.getLogger(__name__)
SOURCE_COMMIT = "d745360d898647048213c561d18e30e3064ad8e7"
HISTORICAL_SOURCE_COMMIT = "8fbe11ba37e7d3788736af123974a3a754c6f7e0"
MODE_SOURCE = "a59e6a2 (Prasad source declaration, 2026-09-03)"


def participant_context(participant):
    from modules.RCS08DataPolicy import applies_to
    if applies_to(participant):
        return {"programming_mode": "parkinsons",
                "programming_mode_source": MODE_SOURCE,
                "programming_mode_status": "source-declared; not live programmer verification",
                "deployment_intent": {
                    "rate_hz_by_hemisphere": {"Left": 55.0, "Right": 55.0},
                    "stimulation_configuration": "Ring stimulation; verify actual contact configuration in device logs for each candidate",
                    "exploratory_110_hz_protocol": "Unfinished in-clinic proposal; not an adopted protocol",
                    "source": "Aditya confirmation, 2026-09-05; intended deployment, not measured delivery"},
                "has_pocket_adaptor": False,
                "has_pocket_adaptor_source": "Aditya hardware confirmation, 2026-09-05; caller-reviewed declaration"}
    return {"programming_mode_source": "No participant-specific programmer-mode declaration"}


def _historical_findings(context):
    if context.get("programming_mode_source") != MODE_SOURCE:
        return []
    return [{"source_commit": HISTORICAL_SOURCE_COMMIT, "status": "retired",
             "scope": "The two configurations nominated in Prasad's source analysis",
             "reason": "Neither survived the source Phase 2 review; nominally resolved band-cells had too few setting-epoch clusters, and nominated configurations were not supported by the whole-epoch permutation.",
             "recomputed_here": False}]


def run_for_participant(request_data):
    from Server import models
    from modules import AnalysisData
    from modules.StimOptimizer import adapter as evidence
    from modules.StimOptimizer.bravo_service import _jsonable
    from modules.Biomarkers import bravo_service as biomarkers

    request = request_data or {}
    uid = request.get("ParticipantId")
    base = {"available": False, "reason": "", "participant": uid, "manifest": {},
            "readiness": {"ready": False, "status": "research_only",
                          "reason": "Retrospective review does not authorize device programming. Prospective evidence and verified programmer settings are required."}}
    participant = models.Participant.find(uid=uid) if uid else None
    if participant is None:
        return {**base, "reason": "Participant not found"}
    context = participant_context(participant)
    base["historical_findings"] = _historical_findings(context)
    base["manifest"] = {"InputManifest": AnalysisData.input_manifest(participant),
                        "source_commit": SOURCE_COMMIT,
                        "programmer_mode": context,
                        "input_scope": "Approved neural spectra and corrected daily REDCap PROs; Oura is not an input to this model.",
                        "spectral_sampling": "StimOptimizer evidence_inputs uses the shared PSD cache with its first-window sampling variant, rather than the rating-centered Biomarkers classifier variant.",
                        "settings_limitation": "Exposure epochs are estimated from eligible JSON settings snapshots; unsampled between-report changes are not directly observed. The final epoch is open-ended.",
                        "analysis_scope": "Selected continuous PRO metric aggregated by estimated setting epoch; this is not the time-window binary biomarker classifier.",
                        "prospective_phases": "Replay and protocol libraries are installed. No prospective observations or pre-registration are created by this review."}
    channel = request.get("Channel")
    try:
        center = float(request.get("CenterHz"))
        width = float(request.get("BandWidthHz", 5))
        washin = float(request.get("WashinMin", 1))
        if not all(math.isfinite(x) for x in (center, width, washin)) or center <= 0 or width <= 0 or washin < 0:
            raise ValueError()
    except (ValueError, TypeError):
        return {**base, "reason": "Choose a valid band and non-negative wash-in duration"}
    if not isinstance(channel, str) or not channel:
        return {**base, "reason": "Choose a channel"}
    hemis = [h for h in ("Left", "Right") if h.lower() in channel.lower()]
    if len(hemis) != 1:
        return {**base, "reason": "The selected channel does not identify one hemisphere"}
    metric = request.get("LabelMetric") or "nrs"
    try:
        pros = AnalysisData.canonical_pros(participant)
        if pros.empty:
            return {**base, "reason": "No approved daily PRO records"}
        # Reuse the exact biomarker metric derivation (including its composite),
        # then the optimizer's epoch/wash-in join, rather than loading another export.
        pros, resolved_metric, _ = biomarkers._resolve_biomarker_metric(request, pros)
        if resolved_metric != metric or metric not in pros:
            return {**base, "reason": "The selected outcome cannot be derived from the approved PRO records"}
        psd, epochs = evidence.evidence_inputs(participant)
        if psd is None or psd.empty or channel not in set(psd.channel):
            return {**base, "reason": "No approved spectra for the selected channel"}
        if epochs is None or epochs.empty:
            return {**base, "reason": "No usable stimulation setting epochs"}
        design = evidence.attach_pros(epochs, pros, biomarkers._pro_times_utc_series(pros),
                                      washin_min=washin, items=(metric,))
        selected = psd[psd.channel == channel].copy()
        pro_frame = design[["epoch", metric]].copy() if not design.empty else None
        candidate = {"channel": channel, "center_hz": center, "band_width_hz": width,
                     "threshold_mode": "dual", "intent": "adaptive"}
        eligible_sources = list(AnalysisData.eligible_source_files(participant))
        history = historical_configurations.for_participant(participant, eligible_sources)
        impedance = list(biomarkers._eligible_recordings(
            participant, source__in=eligible_sources,
            type="MedtronicDeviceImpedance", original__isnull=True))
        facts = device_facts.facts_for_participant(
            uid, impedance, hemisphere=hemis[0], channel=channel)
        report = pipeline.run(uid, psd_frame=selected, epochs=epochs, design_matrix=design,
                              pro_frame=pro_frame, candidates=[candidate], hemisphere=hemis[0],
                              participant_context=context, outcome=metric,
                              outcome_cluster="setting_epoch", band_width_hz=width,
                              washin_s=washin * 60, include_planning=False, device_facts=facts)
        report.blockers.append("Retrospective associations do not establish prospective closed-loop readiness.")
        if report.edges:
            report.edges["E2"].note += " Outcome is an epoch-aggregated PRO; clustering is at setting epoch, not individual rating. Stimulation/time confounding is not removed by this regression."
        payload = {**asdict(report), **adapter.report_to_dict(report)}
        payload["manifest"] = {**base["manifest"], **payload["manifest"],
                               "n_approved_daily_pros": len(pros), "n_outcome_epochs": len(design),
                               "selected_band_only": True, "hypothetical_threshold_mode": "dual",
                               "source_retirement_recomputed": False,
                               "historical_configurations": history,
                               "device_fact_scope": "Eligible post-implant impedance metadata only. Current programmer settings, capture limits and artifact prevalence are not inferred from historical source snapshots.",
                               "device_fact_provenance": facts.get("_provenance", {}),
                               "device_facts": facts,
                               "selected_band": {**candidate, "hypothetical": True},
                               "inference": "Wild-cluster bootstrap-t below 40 clusters; cluster-robust inference otherwise. Small samples and observational confounding still limit interpretation."}
        has_rows = payload["manifest"]["n_table_rows"] > 0
        payload.update(available=has_rows, reason=("Research review completed; see unresolved evidence and rule checks."
                                                 if has_rows else "No spectra fall inside eligible setting epochs after wash-in."),
                       readiness=base["readiness"], historical_findings=base["historical_findings"])
        # A suggested titration is not meaningful without verified device parameters.
        payload["protocol"] = None
        payload["threshold"] = None
        payload["replay"] = None
        payload["prescription"] = None
        payload["prescriptions"] = None
        payload["planning"] = {
            "available": False, "modes": ["dual", "single", "single_inverse"],
            "reason": "Participant-specific programming plans are unavailable in this research review: current programmer settings and capture limits have not been verified.",
        }
        payload.update(_review_disposition(report))
        for key, edge in payload["edges"].items():
            edge["resolved"] = report.edges[key].resolved
            edge["sign"] = report.edges[key].sign
        return _jsonable(payload)
    except Exception as exc:
        log.exception("Closed-loop research review failed for %s", uid)
        raise RuntimeError("The research review could not be computed; retry the analysis.") from exc


def _review_disposition(report):
    """Missing evidence is unsupported; only an observed rule failure is blocked."""
    eligibility = report.eligibility
    failed = bool(eligibility and eligibility.failures)
    device_eligible = None
    if failed:
        device_eligible = False
    elif eligibility is not None and not eligibility.unknowns:
        device_eligible = bool(eligibility.eligible)
    return {"verdict": "blocked" if failed else "unsupported", "licensed": False,
            "verdict_detail": {"device_eligible": device_eligible,
                               "all_edges_resolved": bool(report.edges) and all(
                                   edge.resolved for edge in report.edges.values()),
                               "coherent": None if report.coherence is None else report.coherence.coherent,
                               "blockers": list(report.blockers)}}
