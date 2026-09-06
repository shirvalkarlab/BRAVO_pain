"""Synthetic orchestration checks: absent evidence must remain absent in planning."""
from types import SimpleNamespace

import pandas as pd
import pytest

from ClosedLoopDeployment import adapter, pipeline as PL
from ClosedLoopDeployment.types import EdgeEstimate, ThresholdPlan
from StimOptimizer import adapter as optimizer_adapter


@pytest.fixture
def planning(monkeypatch):
    table = pd.DataFrame({"t": [1., 2., 3.], "setting_epoch": [0, 1, 2],
                          "channel": ["CH"] * 3, "center_hz": [20.5] * 3,
                          "power_linear": [3., 2., 1.], "amp_mA_Left": [1., 2., 3.]})
    monkeypatch.setattr(PL.adapter, "joined_table_cached", lambda *a, **kw: table.copy())
    monkeypatch.setattr(PL.adapter, "scale_disagreement", lambda t: {})
    for name in ("actuation_edge", "state_edge", "therapy_edge"):
        monkeypatch.setattr(PL.E, name, lambda *a, **kw: EdgeEstimate("synthetic", None, None, None, 3, "epoch", 3))
    plan = ThresholdPlan(upper=3., lower=1., capture_amp_low=1., capture_amp_high=3.)
    monkeypatch.setattr(PL.A, "threshold_placement", lambda *a, **kw: plan)
    calls = {}
    def replay(*args):
        calls["replay"] = args
        return SimpleNamespace(note="synthetic replay")
    def prescription(**kwargs):
        calls["prescription"] = kwargs
        return {"recommended": "dual", "modes": {"dual": "synthetic prescription"}}
    def protocol(candidates, **kwargs):
        calls["protocol"] = candidates
        return candidates
    modules = {"replay": SimpleNamespace(dual_threshold_segments=replay),
               "prescription": SimpleNamespace(prescribe_all_modes=prescription),
               "protocol": SimpleNamespace(titration_plan=protocol)}
    monkeypatch.setattr(PL, "_optional", lambda name: modules.get(name))
    def run(**kwargs):
        return PL.run("synthetic", candidates=[{"channel": "CH", "center_hz": 20.5}], **kwargs)
    return table, plan, modules, calls, run


def test_planning_wires_replay_into_all_modes_and_distinct_amplitude_arms(planning):
    table, plan, modules, calls, run = planning
    report = run()
    assert calls["prescription"]["replay_result"] is report.replay
    assert report.prescription == "synthetic prescription"
    assert [c["test_amp_mA"] for c in calls["protocol"]] == [1., 3.]
    assert len({c["label"] for c in calls["protocol"]}) == 2
    table.drop(columns="t", inplace=True)
    calls.clear()
    report = run()
    assert "replay" not in calls
    assert calls["prescription"]["t_s"] is None


@pytest.mark.parametrize("resolver_fails", [False, True])
def test_missing_amplitude_cannot_silently_create_thresholds(planning, monkeypatch, resolver_fails):
    table, _, modules, calls, run = planning
    table.drop(columns="amp_mA_Left", inplace=True)
    def resolve(*a):
        if resolver_fails:
            raise ValueError("synthetic unresolved legacy column")
        return None
    monkeypatch.setattr(PL.adapter, "resolve_setting_column", resolve)
    report = run()
    assert report.threshold is None and report.prescription is None
    assert any("no Left amplitude column" in text for text in report.blockers)
    assert "prescription" not in calls


def test_zero_amplitudes_cannot_be_therapeutic_capture_endpoints(planning):
    table, _, _, _, run = planning
    table["amp_mA_Left"] = 0.
    report = run()
    assert report.threshold is None
    assert any("no nonzero Left amplitude" in text for text in report.blockers)


def test_cell_without_matching_power_cannot_generate_a_plan(planning):
    table, _, _, _, run = planning
    table["channel"] = "OTHER"
    report = run()
    assert report.threshold is None and report.replay is None and report.prescription is None


def test_two_timepoints_withhold_replay_but_keep_the_distinction_from_missing_module(planning):
    table, _, modules, calls, run = planning
    table.drop(index=2, inplace=True)
    report = run()
    assert "replay" not in calls and report.replay is None
    assert report.prescription == "synthetic prescription"
    modules.pop("protocol")
    report = run()
    assert report.protocol is None


def test_unknown_capture_limit_does_not_invent_a_titration_amplitude(planning):
    _, plan, _, calls, run = planning
    plan.capture_amp_low = None
    run()
    assert all("test_amp_mA" not in candidate for candidate in calls["protocol"])


def test_input_memo_respects_refresh_changed_signature_and_bounded_eviction(monkeypatch):
    adapter.clear_inputs_cache()
    monkeypatch.setattr(adapter, "_INPUTS_MEMO_MAX", 1)
    monkeypatch.setattr(adapter, "recording_set_signature", lambda participant: participant)
    calls = []
    def evidence(participant):
        calls.append(participant)
        return pd.DataFrame({"value": [len(calls)]}), pd.DataFrame()
    monkeypatch.setattr(optimizer_adapter, "evidence_inputs", evidence)
    monkeypatch.setattr(optimizer_adapter, "build_design_matrix", lambda p: pd.DataFrame())
    try:
        original = adapter.evidence_inputs_cached("first")
        assert adapter.evidence_inputs_cached("first") is original
        refreshed = adapter.evidence_inputs_cached("first", force_refresh=True)
        assert refreshed is not original
        adapter.evidence_inputs_cached("second")
        assert adapter.inputs_cache_stats()["entries"] == 1
        assert adapter.evidence_inputs_cached("first") is not refreshed
        assert calls == ["first", "first", "second", "first"]
    finally:
        adapter.clear_inputs_cache()
