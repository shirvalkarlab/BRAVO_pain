"""The stimulation program a user defines on the Closed-Loop page (decision 467): its checks, the
device facts it replaces for the sensing side's rules, and the parameter table's program rows.
No database."""
import pytest

from ClosedLoopDeployment import stim_program as SP, prescription as PR, types as TY

PA = pytest.importorskip("StimOptimizer.routines.percept_adaptive")

RCS08 = {"rate_hz": 55,
         "Left": {"contacts": {"2a": -1, "2b": -1, "2c": -1, "case": 1}, "amp_mA": 3.0, "pw_us": 100,
                  "lower_limit_mA": 1.4, "upper_limit_mA": 4.0, "target": "Left GPe"},
         "Right": {"contacts": {"1a": -1, "1b": -1, "1c": -1, "2a": -1, "2b": -1, "2c": -1, "case": 1},
                   "amp_mA": 2.5, "pw_us": 150, "lower_limit_mA": 1.2, "upper_limit_mA": 3.0}}


def test_the_flanking_rule_d52_on_rcs08s_program_today():
    p = SP.normalise(RCS08)
    # left stimulates on 2 only: the device senses on 1-3, not on the chosen band's 0-3
    assert SP.blocking_problems(p["Left"], (0, 3)) == ["Sensing on 0-3 needs stimulation on 1 and 2: the device cannot sense"]
    assert SP.blocking_problems(p["Left"], (1, 3)) == []
    # right stimulates on 1 and 2: 0-3 (shown 8-11) is the flanking pair
    assert SP.blocking_problems(p["Right"], (0, 3), side="Right") == []
    assert SP.blocking_problems(p["Right"], (1, 3), side="Right") == [
        "Sensing on 9-11 needs stimulation on 10: the device cannot sense"]


def test_each_blocking_problem_is_said_and_nothing_else():
    assert SP.blocking_problems({"contacts": {"case": 1}}) == ["No negative contact: no stimulation on this side"]
    assert SP.blocking_problems({"contacts": {"2a": -1}}) == ["No positive contact: make the case or a contact positive"]
    assert SP.blocking_problems({"contacts": {"3": -1, "case": 1}}, (0, 3)) == [
        "Sensing on 0-3 needs stimulation on 1 and 2: the device cannot sense"]
    assert SP.blocking_problems({"contacts": {"2a": -1, "case": 1}, "amp_mA": 5.0,
                                 "lower_limit_mA": 1.0, "upper_limit_mA": 4.0}) == [
        "Amp is outside the lowest and highest current"]


def test_normalise_drops_unknown_contacts_and_signs():
    p = SP.normalise({"rate_hz": "55", "Left": {"contacts": {"2A": -1, "9a": -1, "3": 0, "case": 1}}})
    assert p["rate_hz"] == 55.0 and p["Left"]["contacts"] == {"2a": -1, "case": 1}
    assert SP.normalise("x") is None


def test_the_program_replaces_the_sensing_sides_rate_pulse_width_and_rings():
    f = SP.device_facts_from_program(RCS08, "Right")
    assert (f["rate_hz"], f["pulse_width_us"], f["stim_rings_on_sensing_lead"]) == (55.0, 150.0, [1, 2])
    assert f["stim_contacts_on_sensing_lead"] == "1a-1b-1c-2a-2b-2c"
    assert "your stimulation program" in f["_provenance"]
    assert SP.device_facts_from_program(RCS08, "Nowhere") == {}


def test_contacts_text_writes_positives_first_as_the_programmer_does():
    assert SP.contacts_text({"2b": -1, "2a": -1, "case": 1}) == "C+ 2a- 2b-"


def _rows(cand):
    plan = TY.ThresholdPlan(upper=0.3956, lower=0.182, capture_amp_low=1.4, capture_amp_high=4.8)
    pr = PR.prescribe(mode=PA.DUAL, threshold_plan=plan, candidate=cand, timing=PA.timing_plan(mode=PA.DUAL))
    return {r["parameter"]: r for r in pr.as_rows()}


def test_with_a_program_the_table_carries_its_rows_and_its_limits():
    cand = {"channel": "ZERO_THREE_LEFT", "center_hz": 25.5, "band_width_hz": 5.0,
            "actuated_hemisphere": "Left", "paused_amplitude_mA": 3.0, "stim_program": SP.normalise(RCS08)}
    r = _rows(cand)
    assert r["Stimulation contacts"]["value"] == "C+ 2a- 2b- 2c-"
    assert (r["Rate"]["value"], r["Pulse width"]["value"]) == (55.0, 100.0)
    assert r["Adaptive amplitude limit, lower"]["value"] == 1.4
    assert r["Adaptive amplitude limit, lower"]["status"] == "your_program"
    assert r["Paused amplitude"]["value"] == 3.0 and r["Paused amplitude"]["origin"] == "clinician"


def test_without_a_program_the_table_is_as_before():
    r = _rows({"channel": "ZERO_THREE_LEFT", "center_hz": 25.5, "band_width_hz": 5.0})
    assert "Stimulation contacts" not in r and "Rate" not in r
    assert r["Adaptive amplitude limit, lower"]["status"] == "derived"
    assert r["Paused amplitude"]["value"] is None
