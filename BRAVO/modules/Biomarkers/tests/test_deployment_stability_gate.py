"""Portable regressions for the existing deployment summary's stability evidence.

Execute actual production bodies at their original source locations. Expensive scientific
and recording boundaries return synthetic fixtures; no Django or private data is accessed.
"""
import ast
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

SOURCE = Path(__file__).parents[1] / "bravo_service.py"
FUNCTIONS = {"_deployment_stim_gate", "_ramp_guidance", "deployment_summary"}


@pytest.fixture
def service(monkeypatch):
    import modules.Biomarkers.routines as routines

    native = {"LEFT": {"y": list(range(10, 30)), "center_hz": [20.] * 20,
                       "source": ["chronic"] * 20, "modeled": [False] * 20}}
    availability = SimpleNamespace(
        lsb_series=Mock(return_value=native),
        modeled_lsb_at_center=Mock(return_value=np.empty(0)),
    )
    monkeypatch.setattr(routines, "availability", availability, raising=False)
    monkeypatch.setitem(sys.modules, "modules.Biomarkers.routines.availability", availability)
    unavailable = {"available": False, "reason": "synthetic unavailable evidence"}
    analytics = SimpleNamespace(
        deployment_roc=Mock(return_value=unavailable),
        deployment_roc_by_era=Mock(return_value=unavailable),
        deployment_forward_chaining=Mock(return_value=unavailable),
        threshold_drift_by_week=Mock(return_value=unavailable),
        _band_feature_from_detail=Mock(return_value=(np.array([0., 1.]),)),
        power_center_freqs=Mock(return_value={}),
        format_channel=Mock(return_value={"short": "LEFT", "hemisphere": "Left",
                                          "label": "Synthetic left contact", "region": "test"}),
    )
    core = {"available": True, "pooled": {}, "channel": "LEFT", "center_hz": 20.,
            "band_width_hz": 5., "label_strategy": "tertile", "low_pct": 33.,
            "high_pct": 67., "label_metric": "nrs", "participant_uid": "synthetic",
            "match_direction": "prior", "verdict": "VALIDATED (synthetic fixture)",
            "glmer": {"available": True, "odds_ratio": 2., "or_lo": 1.2, "or_hi": 2.8,
                      "p": .001, "n": 40}, "stim": {}}
    ns = {"np": np, "analytics": analytics, "_validate_band_core": Mock(return_value=core),
          "_int_param": lambda data, key, **kw: data.get(key, kw.get("default")),
          "_float_param": lambda data, key, **kw: data.get(key, kw.get("default")),
          "_load_recordings": Mock(return_value=[]),
          "_modeled_lsb_threshold_estimate": Mock(return_value=None),
          "_suggested_percept_mode": Mock(return_value=("Dual", "synthetic mapping")),
          "_band_credible_ci": Mock(return_value=(True, 1.6)),
          "_threshold_mode_block": Mock(return_value={"mode": "synthetic"}),
          "ADAPTIVE_LO_HZ": 8., "ADAPTIVE_HI_HZ": 30.,
          "CHRONIC_TYPES": ("chronic",), "POWERDOMAIN_TYPES": ("power",),
          "AVAILABILITY_PSD_TYPES": ("psd",), "TIMEDOMAIN_TYPES": ("td",)}
    tree = ast.parse(SOURCE.read_text())
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef)
             and node.name in FUNCTIONS]
    assert {node.name for node in nodes} == FUNCTIONS
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), "exec"), ns)
    return ns, core, availability


@pytest.mark.parametrize("evidence", [None, [], "unknown", {},
    {"available": False, "stability_verdict": "stable", "stim_stable": True}])
def test_unavailable_or_malformed_assessment_never_passes(service, evidence):
    ns, _, _ = service
    state, detail, confirmed = ns["_deployment_stim_gate"](evidence)
    assert state == "indeterminate"
    assert confirmed is None
    assert "unavailable" in detail.lower()


@pytest.mark.parametrize("legacy", [True, False, None])
@pytest.mark.parametrize("verdict", [None, "", "not_tested", "unknown", "inconclusive", "equivalent"])
def test_missing_or_unrecognized_equivalence_never_uses_legacy_pass(service, legacy, verdict):
    ns, _, _ = service
    state, detail, confirmed = ns["_deployment_stim_gate"](
        {"available": True, "stability_verdict": verdict, "stim_stable": legacy})
    assert state == "indeterminate"
    assert confirmed is None
    assert "equivalence" in detail.lower()


@pytest.mark.parametrize("legacy", [True, False, None])
def test_explicit_dependence_remains_failed(service, legacy):
    ns, _, _ = service
    state, detail, confirmed = ns["_deployment_stim_gate"](
        {"available": True, "stability_verdict": "stim-dependent", "stim_stable": legacy})
    assert state == "fail"
    assert confirmed is False
    assert "stim-dependent" in detail.lower()


@pytest.mark.parametrize("legacy", [False, None, 1, "true"])
def test_conflicting_or_incomplete_stability_does_not_gain_a_pass(service, legacy):
    ns, _, _ = service
    state, detail, confirmed = ns["_deployment_stim_gate"](
        {"available": True, "stability_verdict": "stable", "stim_stable": legacy})
    assert state == "indeterminate"
    assert confirmed is None
    assert "conflict" in detail.lower() or "incomplete" in detail.lower()


def test_confirmed_equivalence_is_a_pass(service):
    ns, _, _ = service
    state, detail, confirmed = ns["_deployment_stim_gate"](
        {"available": True, "stability_verdict": "stable", "stim_stable": True})
    assert state == "pass"
    assert confirmed is True
    assert "margin" in detail.lower()


@pytest.mark.parametrize("verdict,legacy,state,posture", [
    ("stable", True, "pass", "moderate"),
    ("stim-dependent", False, "fail", "conservative"),
    ("inconclusive", True, "indeterminate", "conservative"),
    ("stable", False, "indeterminate", "conservative"),
    (None, True, "indeterminate", "conservative"),
])
def test_real_summary_wires_gate_and_ramp_without_programming_authority(service, verdict, legacy, state, posture):
    ns, core, _ = service
    core["stim"] = {"available": True, "stability_verdict": verdict, "stim_stable": legacy}
    out = ns["deployment_summary"]({"Cutpoint": .5})
    gate = next(item for item in out["gates"] if item["key"] == "stim_stable")
    assert gate["state"] == state
    assert gate["pass"] is (state == "pass")
    assert gate["necessary"] is False
    assert gate["label"] == "Stim-stability (equivalence)"
    assert out["device_control"]["ramp"]["posture"] == posture
    if state == "indeterminate":
        note = out["device_control"]["ramp"]["transition_note"].lower()
        assert "unconfirmed" in note
        assert "did not converge" not in note  # Inconclusive does not imply a failed model fit.
    assert {item["key"] for item in out["gates"] if item["necessary"]} == {
        "validated", "adaptive_band", "deployable_threshold"}
    assert out["n_necessary"] == 3
    assert out["n_necessary_passed"] == 3
    assert out["research_gates_passed"] is True
    assert out["ready_to_program"] is False
    assert out["recommendation_eligible"] is False
    assert out["threshold"]["upper_lsb"] == 19.5
    assert out["device_control"]["suggested_mode"] == "Dual"
    assert out["n_gates_passed"] == (5 if state == "pass" else 4)
    assert out["n_gates_indeterminate"] == (2 if state == "indeterminate" else 1)
    ns["_validate_band_core"].assert_called_once_with({"Cutpoint": .5, "MatchDirection": "prior"})


def test_missing_native_threshold_remains_a_failed_research_prerequisite(service):
    ns, core, availability = service
    core["stim"] = {"available": True, "stability_verdict": "stable", "stim_stable": True}
    availability.lsb_series.return_value = {}
    out = ns["deployment_summary"]({"Cutpoint": .5})
    assert out["n_necessary_passed"] == 2
    assert out["research_gates_passed"] is False
    assert out["ready_to_program"] is False
    assert out["recommendation_eligible"] is False


def test_unavailable_core_never_builds_a_summary_or_loads_recordings(service):
    ns, core, _ = service
    core.update(available=False, reason="synthetic unavailable core")
    assert ns["deployment_summary"]({}) is core
    ns["_load_recordings"].assert_not_called()
