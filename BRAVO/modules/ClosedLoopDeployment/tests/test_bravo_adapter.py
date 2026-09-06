"""Regression coverage for canonical input wiring and absent programmer evidence."""
import sys
import types

import numpy as np
import pandas as pd

from ClosedLoopDeployment import adapter, pipeline, bravo_service
from ClosedLoopDeployment.types import EdgeEstimate


def fixtures():
    start = pd.Timestamp("2026-01-01T00:00:00Z")
    epochs = pd.DataFrame({"epoch": [11, 29], "t_start": [start, start + pd.Timedelta(hours=1)],
                           "t_end": [start + pd.Timedelta(hours=1), start + pd.Timedelta(hours=2)],
                           "open_ended": [False, True], "amp_mA_Left": [1., 2.],
                           "amp_mA_Right": [2., 3.]})
    psd = pd.DataFrame({"t": [start.timestamp() + 120, start.timestamp() + 7200 + 120],
                        "channel": ["ONE_THREE_RIGHT"] * 2,
                        "log_psd": [np.zeros(40)] * 2, "freqs": [np.arange(40)] * 2})
    return epochs, psd


def test_join_uses_real_epoch_identity_and_includes_final_open_epoch():
    epochs, psd = fixtures()
    table = adapter.joined_table(psd, epochs, centers=(20.5,),
                                 pro_frame=pd.DataFrame({"epoch": [11, 29], "nrs": [3., 8.]}))
    assert list(table.setting_epoch) == [11, 29]
    assert list(table.nrs) == [3., 8.]
    assert list(table.amp_mA_Right) == [2., 3.]


def test_pipeline_respects_declared_mode_selected_metric_hemisphere_and_band(monkeypatch):
    epochs, psd = fixtures()
    calls = {}
    def edge(name):
        return EdgeEstimate(name, None, None, None, 2, "setting epoch", 2)
    monkeypatch.setattr(pipeline.E, "actuation_edge", lambda table, **kw: edge("E1"))
    def state(table, **kw):
        calls["state"] = kw
        calls["centers"] = list(table.center_hz.unique())
        return edge("E2")
    def therapy(frame, **kw):
        calls["therapy"] = kw
        return edge("E3")
    monkeypatch.setattr(pipeline.E, "state_edge", state)
    monkeypatch.setattr(pipeline.E, "therapy_edge", therapy)
    report = pipeline.run("unknown", psd_frame=psd, epochs=epochs,
                          candidates=[{"channel": "ONE_THREE_RIGHT", "center_hz": 19.,
                                       "threshold_mode": "dual", "band_width_hz": 4.}],
                          hemisphere="Right", outcome="left_leg_vas", outcome_cluster="setting_epoch",
                          band_width_hz=4., participant_context={}, include_planning=False)
    assert calls["state"]["outcome"] == "left_leg_vas"
    assert calls["state"]["cluster"] == "setting_epoch"
    assert calls["therapy"]["amp_col"] == "amp_mA_Right"
    assert calls["centers"] == [19.]
    assert any(row["rule_id"] == "D03" for row in report.eligibility.unknowns)
    assert not report.is_licensed()
    assert report.protocol is None and report.threshold is None


def test_programmer_mode_is_participant_specific_source_declaration(monkeypatch):
    module = types.ModuleType("modules.RCS08DataPolicy")
    module.applies_to = lambda participant: participant == "RCS08"
    monkeypatch.setitem(sys.modules, "modules.RCS08DataPolicy", module)
    assert "programming_mode" not in bravo_service.participant_context("other")
    known = bravo_service.participant_context("RCS08")
    assert known["programming_mode"] == "parkinsons"
    assert "not live" in known["programming_mode_status"]
    assert bravo_service._historical_findings(known)[0]["recomputed_here"] is False
    assert not bravo_service._historical_findings({})


def test_service_uses_approved_pros_and_selected_controls(monkeypatch):
    from modules import RedcapStimulation, RCS08DataPolicy
    epochs, psd = fixtures()
    participant = types.SimpleNamespace(uid="RCS08", name="RCS08")
    pros = pd.DataFrame({"nrs": [3., 8.], "left_leg_vas": [30., 80.]})
    calls = {}
    def attach(ep, frame, times, **kw):
        assert ep is epochs and frame is pros
        calls.update(kw)
        return epochs.assign(left_leg_vas=[30., 80.])
    st_adapter = types.SimpleNamespace(evidence_inputs=lambda p: (psd, epochs), attach_pros=attach)
    for name, attrs in {
        "Server": {"models": types.SimpleNamespace(Participant=types.SimpleNamespace(find=lambda **k: participant))},
        "modules": {"RedcapStimulation": RedcapStimulation, "RCS08DataPolicy": RCS08DataPolicy,
                    "AnalysisData": types.SimpleNamespace(input_manifest=lambda p: {"fingerprint": "approved"}, canonical_pros=lambda p: pros,
                                                          eligible_source_files=lambda p: [])},
        "modules.StimOptimizer": {"adapter": st_adapter},
        "modules.StimOptimizer.bravo_service": {"_jsonable": lambda value: value},
        "modules.Biomarkers": {"bravo_service": types.SimpleNamespace(
            _resolve_biomarker_metric=lambda request, p: (p, request["LabelMetric"], []),
            _pro_times_utc_series=lambda p: [1., 2.], _eligible_recordings=lambda p, **kw: [])},
    }.items():
        module = types.ModuleType(name)
        for key, value in attrs.items():
            setattr(module, key, value)
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setattr(bravo_service, "participant_context", lambda p: {})
    out = bravo_service.run_for_participant({"ParticipantId": "RCS08", "Channel": "ONE_THREE_RIGHT",
                                            "CenterHz": 19., "LabelMetric": "left_leg_vas",
                                            "WashinMin": 2., "ProgrammingMode": "parkinsons"})
    assert out["available"], out["reason"]
    assert calls == {"washin_min": 2., "items": ("left_leg_vas",)}
    assert out["manifest"]["InputManifest"]["fingerprint"] == "approved"
    assert out["manifest"]["outcome"] == "left_leg_vas"
    assert out["manifest"]["outcome_cluster"] == "setting_epoch"
    history = out["manifest"]["historical_configurations"]
    assert history["participant_id"] == participant.uid
    assert history["configurations"] == []
    assert history["unavailable_source_count"] == 0
    assert any(row["rule_id"] == "D31" for row in out["eligibility"]["unknowns"])
    assert not out["readiness"]["ready"]
    assert out["protocol"] is None
    assert any(row["rule_id"] == "D03" for row in out["eligibility"]["unknowns"])


def test_one_band_cannot_claim_global_scale_agreement():
    epochs, psd = fixtures()
    table = adapter.joined_table(psd, epochs, centers=(20.5,))
    assert adapter.scale_disagreement(table)["available"] is False
