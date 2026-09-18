"""Synthetic boundary cases for missing planning products and evidence provenance."""
from types import SimpleNamespace
import pytest
from ClosedLoopDeployment import constraints as CN, pipeline as PL, prescription as PR


@pytest.mark.parametrize("container", [None, {}, {"modes": []}])
def test_absent_prescription_container_cannot_create_attached_findings(container):
    for attach in (PR.attach_occupancy, PR.attach_startup_bias, PR.attach_robustness):
        assert attach(container, {"available": True, "why": "synthetic"}) is container
    assert PR.attach_design_rule(container, {"table": []}, averaging_ms=1000.,
                                 onset_ms=2000.) is container


def test_missing_design_rule_row_does_not_supply_threshold_guidance():
    assert PR.design_rule_note({"table": []}, upper=8., lower=4.,
                               averaging_ms=1000., onset_ms=2000.) is None


@pytest.mark.parametrize("payload", [
    {"d_method": {"available": False}, "e_method": {"available": False}},
    {"d_method": {"available": True, "rows": []},
     "e_method": {"available": True, "rows": [{"bias_in_sd": None}]}},
])
def test_unavailable_startup_estimates_are_not_rendered_as_findings(payload):
    assert PR.startup_bias_note(payload) is None


@pytest.mark.parametrize("alert", [False, True])
def test_threshold_alert_and_explanation_are_carried_without_overriding_candidate(alert):
    threshold = SimpleNamespace(predicted_recapture_alert=alert,
                                warnings=[None, "synthetic uncertainty", "synthetic direction"])
    facts = PL._facts_for({}, None, None, "power_linear", threshold=threshold)
    assert facts["predicted_recapture_alert"] is alert
    assert facts["predicted_recapture_alert_reason"] == "synthetic uncertainty; synthetic direction"
    explicit = {"predicted_recapture_alert": not alert,
                "predicted_recapture_alert_reason": "reviewed explicit evidence"}
    facts = PL._facts_for(explicit, None, None, "power_linear", threshold=threshold)
    assert facts["predicted_recapture_alert"] is (not alert)
    assert facts["predicted_recapture_alert_reason"] == "reviewed explicit evidence"
    absent = PL._facts_for({}, None, None, "power_linear",
                           threshold=SimpleNamespace(predicted_recapture_alert=None, warnings=[]))
    assert "predicted_recapture_alert" not in absent
    assert "predicted_recapture_alert_reason" not in absent


@pytest.mark.parametrize("current,phrase", [(1., "fixed measurement current of 1 mA"),
                                           ("automatic_increase", "automatic low-current mode"),
                                           (None, "measurement current that was not recorded")])
def test_impedance_observation_names_measurement_method_and_both_bounds(current, phrase):
    facts = {"impedance_measurement_current": current, "impedance_measured_at": "synthetic-fixed",
             "impedance_tested": True, "impedance_min_ohms": 500., "impedance_ohms": 3000.,
             "impedance_ohms_automatic_newest": 11000.,
             "impedance_automatic_measured_at": "synthetic-automatic"}
    note = CN._o_d16(facts, {"lead_type": "synthetic"})
    assert phrase in note
    assert "minimum 500.0, maximum 3000.0" in note
    assert "synthetic-automatic" in note and "11000.0" in note
