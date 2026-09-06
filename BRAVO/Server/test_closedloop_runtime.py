"""Runtime tests of the installed research service, with synthetic data boundaries.

These import and execute the production adapter and pipeline. Only database/input
loading, the epoch PRO join, and statistical estimators are replaced; the selected
band, temporal filtering, manifest, and research-only result handling execute.
"""
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest

from Server import models
from modules import AnalysisData, RCS08DataPolicy
from modules.ClosedLoopDeployment import bravo_service as service, pipeline
from modules.ClosedLoopDeployment.types import EdgeEstimate, EligibilityReport, CoherenceReport
from modules.StimOptimizer import adapter as evidence


def test_fresh_django_worker_imports_service_without_test_package_aliases():
    """The API imports modules.ClosedLoopDeployment, without conftest's path edits."""
    import os
    from pathlib import Path
    import subprocess
    import sys
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    result = subprocess.run([sys.executable, "-c", """
import django
import importlib
import sys
from django.conf import settings
settings.LOGGING_CONFIG = None
settings.DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
django.setup()
assert 'StimOptimizer' not in sys.modules
service = importlib.import_module('modules.ClosedLoopDeployment.bravo_service')
assert callable(service.run_for_participant)
from modules.ClosedLoopDeployment import authority
from modules.StimOptimizer.routines.lfp_response import MIN_CAPTURE_SEPARATION_D
assert authority.MIN_CAPTURE_SEPARATION_D == MIN_CAPTURE_SEPARATION_D
assert 'StimOptimizer' not in sys.modules
"""], cwd=Path(__file__).resolve().parents[1], env=environment,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


@pytest.fixture
def review(monkeypatch):
    person = SimpleNamespace(uid="synthetic-patient")
    find = Mock(return_value=person)
    monkeypatch.setattr(models.Participant, "find", find)
    monkeypatch.setattr(RCS08DataPolicy, "applies_to", lambda participant: False)
    start = pd.Timestamp("2026-01-01T00:00:00Z")
    pros = pd.DataFrame({"nrs": [3., 8.], "left_leg_vas": [30., 80.],
                         "_pro_time_utc": [start.tz_localize(None) + pd.Timedelta(minutes=3),
                                           start.tz_localize(None) + pd.Timedelta(hours=1, minutes=3)]})
    epochs = pd.DataFrame({"epoch": [11, 29], "t_start": [start, start + pd.Timedelta(hours=1)],
                           "t_end": [start + pd.Timedelta(hours=1), start + pd.Timedelta(hours=2)],
                           "open_ended": [False, True], "amp_mA_Left": [1., 2.],
                           "amp_mA_Right": [2., 3.]})
    psd = pd.DataFrame({"t": [start.timestamp() + 120, start.timestamp() + 3720],
                        "channel": ["ONE_THREE_RIGHT"] * 2,
                        "log_psd": [np.zeros(40)] * 2, "freqs": [np.arange(40)] * 2})
    canonical = Mock(return_value=pros)
    sources = []
    eligible_sources = Mock(return_value=sources)
    recordings = Mock(return_value=[])
    inputs = Mock(return_value=(psd, epochs))
    attach = Mock(return_value=epochs.assign(nrs=[3., 8.], left_leg_vas=[30., 80.]))
    monkeypatch.setattr(AnalysisData, "canonical_pros", canonical)
    monkeypatch.setattr(AnalysisData, "eligible_source_files", eligible_sources)
    monkeypatch.setattr(models.Recording, "find_all", recordings)
    monkeypatch.setattr(AnalysisData, "input_manifest", lambda participant: {"fingerprint": "approved-synthetic"})
    monkeypatch.setattr(evidence, "evidence_inputs", inputs)
    monkeypatch.setattr(evidence, "attach_pros", attach)
    for name, edge in (("actuation_edge", "E1"), ("state_edge", "E2"), ("therapy_edge", "E3")):
        monkeypatch.setattr(pipeline.E, name, Mock(return_value=EdgeEstimate(
            edge, None, None, None, 2, "setting epoch", 2)))
    return SimpleNamespace(person=person, find=find, start=start, pros=pros, epochs=epochs,
                           psd=psd, canonical=canonical, inputs=inputs, attach=attach,
                           sources=sources, eligible_sources=eligible_sources, recordings=recordings,
                           request={"ParticipantId": person.uid, "Channel": "ONE_THREE_RIGHT",
                                    "CenterHz": 19., "LabelMetric": "nrs"})


@pytest.mark.parametrize("body", [None, {}, {"ParticipantId": "missing"}])
def test_missing_participant_never_loads_research_inputs(review, body):
    review.find.return_value = None
    result = service.run_for_participant(body)
    assert result["available"] is False
    assert result["reason"] == "Participant not found"
    assert result["readiness"]["ready"] is False
    review.canonical.assert_not_called()


@pytest.mark.parametrize("control,value", [
    ("CenterHz", None), ("CenterHz", "invalid"), ("CenterHz", float("nan")),
    ("CenterHz", 0), ("CenterHz", -1), ("BandWidthHz", float("inf")),
    ("BandWidthHz", 0), ("BandWidthHz", -2), ("WashinMin", -1), ("WashinMin", {}),
])
def test_invalid_band_or_washin_rejected_before_data_load(review, control, value):
    result = service.run_for_participant({**review.request, control: value})
    assert result["available"] is False
    assert "valid band and non-negative wash-in" in result["reason"]
    review.canonical.assert_not_called()
    review.inputs.assert_not_called()


@pytest.mark.parametrize("channel,reason", [
    (None, "Choose a channel"), ([], "Choose a channel"), ("", "Choose a channel"),
    ("ONE_THREE", "one hemisphere"), ("LEFT_RIGHT", "one hemisphere"),
])
def test_unidentified_or_ambiguous_hemisphere_is_not_guessed(review, channel, reason):
    result = service.run_for_participant({**review.request, "Channel": channel})
    assert result["available"] is False
    assert reason in result["reason"]
    review.canonical.assert_not_called()


def test_empty_approved_pros_is_distinct_from_processing_failure(review):
    review.canonical.return_value = pd.DataFrame()
    result = service.run_for_participant(review.request)
    assert result["reason"] == "No approved daily PRO records"
    assert result["available"] is False
    review.inputs.assert_not_called()


@pytest.mark.parametrize("metric,drop", [("unrecognized_metric", False), ("nrs", True)])
def test_metric_fallback_or_missing_column_cannot_silently_change_outcome(review, metric, drop):
    if drop:
        review.canonical.return_value = review.pros.drop(columns="nrs")
    result = service.run_for_participant({**review.request, "LabelMetric": metric})
    assert result["available"] is False
    assert "cannot be derived" in result["reason"]
    review.inputs.assert_not_called()


@pytest.mark.parametrize("kind", ["none", "empty", "other_channel"])
def test_missing_selected_spectra_returns_specific_unavailability(review, kind):
    psd = {"none": None, "empty": pd.DataFrame(),
           "other_channel": review.psd.assign(channel="ONE_THREE_LEFT")}[kind]
    review.inputs.return_value = psd, review.epochs
    result = service.run_for_participant(review.request)
    assert result["available"] is False
    assert result["reason"] == "No approved spectra for the selected channel"
    review.attach.assert_not_called()


@pytest.mark.parametrize("epochs", [None, pd.DataFrame()])
def test_missing_setting_epochs_is_not_assumed_no_stimulation(review, epochs):
    review.inputs.return_value = review.psd, epochs
    result = service.run_for_participant(review.request)
    assert result["available"] is False
    assert result["reason"] == "No usable stimulation setting epochs"
    review.attach.assert_not_called()


def test_pipeline_error_propagates_as_retryable_failure_not_no_data(review, monkeypatch):
    failure = ValueError("synthetic corrupt estimator input")
    monkeypatch.setattr(pipeline, "run", Mock(side_effect=failure))
    with pytest.raises(RuntimeError, match="could not be computed") as raised:
        service.run_for_participant(review.request)
    assert raised.value.__cause__ is failure


def test_selected_metric_band_washin_and_canonical_manifest_reach_real_pipeline(review):
    result = service.run_for_participant({**review.request, "LabelMetric": "left_leg_vas",
                                          "BandWidthHz": 4, "WashinMin": 0,
                                          "ProgrammingMode": "parkinsons"})
    assert result["available"] is True
    assert result["manifest"]["n_table_rows"] == 2
    assert result["manifest"]["outcome"] == "left_leg_vas"
    assert result["manifest"]["washin_s"] == 0
    assert result["manifest"]["InputManifest"] == {"fingerprint": "approved-synthetic"}
    assert result["candidates"][0]["center_hz"] == 19
    assert result["candidates"][0]["band_width_hz"] == 4
    assert review.attach.call_args.kwargs == {"washin_min": 0., "items": ("left_leg_vas",)}
    pd.testing.assert_series_equal(review.attach.call_args.args[2], review.pros._pro_time_utc)
    assert result["readiness"]["ready"] is False
    assert result["readiness"]["status"] == "research_only"
    assert all(result[key] is None for key in ("protocol", "threshold", "replay"))
    assert "programming_mode" not in result["manifest"]["programmer_mode"]
    assert result["historical_findings"] == []
    assert any(rule["rule_id"] == "D03" for rule in result["eligibility"]["unknowns"])
    assert "not individual rating" in result["edges"]["E2"]["note"]


def test_washin_excludes_real_joined_spectra_without_claiming_completed_review(review):
    result = service.run_for_participant({**review.request, "WashinMin": 3})
    assert result["manifest"]["n_psd_rows"] == 2
    assert result["manifest"]["n_table_rows"] == 0
    assert result["available"] is False
    assert "after wash-in" in result["reason"]
    assert result["edges"] == {}
    assert result["readiness"]["ready"] is False


def test_empty_outcome_join_preserves_missingness_and_unresolved_evidence(review):
    review.attach.return_value = pd.DataFrame()
    result = service.run_for_participant(review.request)
    assert result["manifest"]["n_outcome_epochs"] == 0
    assert result["manifest"]["n_table_rows"] == 2
    assert result["edges"]["E2"]["resolved"] is False
    assert result["readiness"]["ready"] is False


@pytest.mark.parametrize("estimate,interval,clusters,resolved", [
    (1., None, 40, False), (1., (1., 2.), 39, True),
    (-1., (-2., -1.), 40, True), (1., (-1., 1.), 41, False),
    (1., (0., 1.), 2, False), (-1., (-1., 0.), 2, False),
    (None, (1., 2.), 40, False),
])
def test_edge_resolution_preserves_bootstrap_results_without_authorizing_programming(
        review, monkeypatch, estimate, interval, clusters, resolved):
    for name, edge in (("actuation_edge", "E1"), ("state_edge", "E2"), ("therapy_edge", "E3")):
        monkeypatch.setattr(pipeline.E, name, Mock(return_value=EdgeEstimate(
            edge, estimate, interval, .01, 100, "setting epoch", clusters)))
    result = service.run_for_participant(review.request)
    assert result["available"] is True
    for edge in result["edges"].values():
        assert edge["resolved"] is resolved
        assert "inference_reliable" not in edge
        assert edge["sign"] == (None if estimate is None else (1 if estimate > 0 else -1))
    assert "bootstrap-t below 40 clusters" in result["manifest"]["inference"]
    assert result["readiness"]["ready"] is False
    assert any("do not establish prospective" in blocker for blocker in result["blockers"])


def test_source_declared_mode_keeps_historical_retirement_separate_from_recomputation(review, monkeypatch):
    monkeypatch.setattr(RCS08DataPolicy, "applies_to", lambda participant: participant is review.person)
    result = service.run_for_participant(review.request)
    mode = result["manifest"]["programmer_mode"]
    assert mode["programming_mode"] == "parkinsons"
    assert "not live programmer verification" in mode["programming_mode_status"]
    assert mode["deployment_intent"]["rate_hz_by_hemisphere"] == {"Left": 55., "Right": 55.}
    assert "not an adopted protocol" in mode["deployment_intent"]["exploratory_110_hz_protocol"]
    assert mode["has_pocket_adaptor"] is False
    assert "segmental_steering_in_use" not in mode
    assert result["historical_findings"][0]["status"] == "retired"
    assert result["historical_findings"][0]["recomputed_here"] is False
    assert result["manifest"]["source_retirement_recomputed"] is False
    assert result["historical_findings"][0]["source_commit"] == service.HISTORICAL_SOURCE_COMMIT
    assert result["historical_findings"][0]["source_commit"] != result["manifest"]["source_commit"]
    assert result["manifest"]["source_commit"] == service.SOURCE_COMMIT
    assert result["readiness"]["ready"] is False


def test_impedance_loader_obeys_canonical_sources_implant_cutoff_and_original_recordings(review, monkeypatch):
    monkeypatch.setattr(RCS08DataPolicy, "applies_to", lambda participant: participant is review.person)
    service.run_for_participant(review.request)
    review.eligible_sources.assert_called_once_with(review.person)
    review.recordings.assert_called_once_with(
        source__in=review.sources, type="MedtronicDeviceImpedance", original__isnull=True,
        date__gte=RCS08DataPolicy.IMPLANT_DAY)


def test_live_impedance_and_provenance_reach_rule_checks_without_importing_historical_facts(review):
    review.recordings.return_value = [SimpleNamespace(date=review.start.timestamp(), metadata={
        "Status": "GOOD", "Left": {"LeadModel": "LEAD_B33015", "Bipolar": [[0, 2500], [2500, 0]]},
        "Right": {"LeadModel": "LEAD_B33015", "Bipolar": [[0, 3200], [3200, 0]]}})]
    result = service.run_for_participant(review.request)
    assert result["available"] is True
    assert not any(row["rule_id"] == "D16" for bucket in ("failures", "unknowns")
                   for row in result["eligibility"][bucket])
    provenance = result["manifest"]["device_fact_provenance"]
    assert "NEWEST" in provenance["impedance_ohms"]
    assert "Right" in provenance["impedance_ohms"]
    assert "impedance" in result["manifest"]["device_fact_scope"].lower()
    assert "capture_amp_low_mA" not in provenance
    assert result["verdict"] == "unsupported"
    assert result["verdict_detail"]
    assert "deferred" in result["eligibility"]


def test_right_lead_model_is_not_inferred_from_known_left_model(review):
    review.recordings.return_value = [SimpleNamespace(date=review.start.timestamp(), metadata={
        "Status": "GOOD", "Left": {"LeadModel": "LEAD_B33015", "Bipolar": [[0, 2500], [2500, 0]]},
        "Right": {"Bipolar": [[0, 3200], [3200, 0]]}})]
    result = service.run_for_participant(review.request)
    facts = result["manifest"]["device_facts"]
    assert facts["impedance_ohms"] == 3200
    assert "lead_type" not in facts
    assert any(row["rule_id"] == "D16" for row in result["eligibility"]["unknowns"])


def test_absent_impedance_leaves_hardware_unknown_and_never_loads_private_snapshot(review):
    result = service.run_for_participant(review.request)
    assert any(row["rule_id"] == "D16" for row in result["eligibility"]["unknowns"])
    assert result["manifest"]["device_fact_provenance"] == {}
    assert result["verdict"] == "unsupported"
    assert result["manifest"]["historical_configurations"]["configurations"] == []
    assert "deployment_intent" not in result["manifest"]["programmer_mode"]


def test_scoped_history_reaches_manifest_but_does_not_supply_rule_limits(review, monkeypatch):
    from modules import RedcapStimulation
    review.sources.extend([
        SimpleNamespace(uid="approved-source", owner_id=review.person.uid, type="MedtronicJSON",
                        hashed="approved-hash", metadata={"Device": "participant-device"}),
        SimpleNamespace(uid="foreign-source", owner_id="someone-else", type="MedtronicJSON",
                        hashed="foreign-hash", metadata={"Device": "foreign-device"})])
    cache = Mock(return_value=({"excluded": None, "events": [{
        "time": review.start.timestamp(), "kind": "settings_observed", "phase": "Final",
        "settings": {"group": [{"label": "Stimulation status", "value": "On"}], "left": [],
                     "right": [{"label": "Frequency", "value": "55 Hz"},
                               {"label": "Pulse width", "value": "160 µs"},
                               {"label": "Sensing", "value": "Enabled"}]}}]}, True))
    monkeypatch.setattr(RedcapStimulation, "source_context", cache)
    result = service.run_for_participant({**review.request,
                                          "historical_configurations": {"brainsense_min_rate_hz": 1.}})
    history = result["manifest"]["historical_configurations"]
    assert history["excluded_source_count"] == 1
    assert len(history["configurations"]) == 1
    row = history["configurations"][0]
    assert row["participant_id"] == review.person.uid and row["device_id"] == "participant-device"
    assert row["observations"][0]["source_id"] == "approved-source"
    assert row["delivery_verified"] is None
    cache.assert_called_once()
    assert cache.call_args.kwargs == {"cached_only": True}
    assert "brainsense_min_rate_hz" not in result["manifest"]["device_facts"]
    assert any(item["rule_id"] == "D31" for item in result["eligibility"]["unknowns"])


def test_impedance_loading_failure_does_not_masquerade_as_unknown_evidence(review):
    review.recordings.side_effect = ValueError("synthetic unreadable recording")
    with pytest.raises(RuntimeError, match="could not be computed") as raised:
        service.run_for_participant(review.request)
    assert isinstance(raised.value.__cause__, ValueError)


@pytest.mark.parametrize("eligibility,device_eligible,verdict", [
    (None, None, "unsupported"),
    (EligibilityReport(False, unknowns=[{"rule_id": "D16"}]), None, "unsupported"),
    (EligibilityReport(False, failures=[{"rule_id": "D19"}], unknowns=[{"rule_id": "D16"}]),
     False, "blocked"),
    (EligibilityReport(True), True, "unsupported"),
    (EligibilityReport(False), False, "unsupported"),
])
@pytest.mark.parametrize("has_edges,coherent", [(False, None), (True, True), (True, False)])
def test_review_disposition_distinguishes_missing_evidence_from_observed_failure(
        eligibility, device_eligible, verdict, has_edges, coherent):
    edge = EdgeEstimate("E1", 1., (0.5, 1.5), .01, 100, "setting epoch", 12)
    report = SimpleNamespace(
        eligibility=eligibility, edges={"E1": edge} if has_edges else {},
        coherence=None if coherent is None else CoherenceReport(coherent, None),
        blockers=["Prospective validation remains absent"])
    result = service._review_disposition(report)
    assert result["verdict"] == verdict
    assert result["licensed"] is False
    assert result["verdict_detail"] == {
        "device_eligible": device_eligible, "all_edges_resolved": has_edges,
        "coherent": coherent, "blockers": report.blockers}
