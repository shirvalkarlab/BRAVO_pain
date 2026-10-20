"""The stimulation program a user defines on the Closed-Loop page (decision 467): its checks, the
device facts it replaces for the sensing side's rules, and the parameter table's program rows.
No database."""
import pytest

from ClosedLoopDeployment import stim_program as SP, prescription as PR, types as TY

PA = pytest.importorskip("StimOptimizer.routines.percept_adaptive")

from ClosedLoopDeployment import safe_current as SAFE
from DecodeCommon.tests.synthetic_clinical_config import install

SYNTHETIC_UID = "synthetic-prescription-participant"


@pytest.fixture(autouse=True)
def synthetic_configuration(monkeypatch, tmp_path):
    install(monkeypatch, tmp_path / "clinical.json", [SYNTHETIC_UID])


# Independently chosen test-only settings; the contacts exercise the flanking rule.
SYNTHETIC_PROGRAM = {"rate_hz": 100,
         "Left": {"contacts": {"2a": -1, "2b": -1, "2c": -1, "case": 1}, "amp_mA": 2.0, "pw_us": 90,
                  "lower_limit_mA": 1.0, "upper_limit_mA": 3.0, "target": "Synthetic left target"},
         "Right": {"contacts": {"1a": -1, "1b": -1, "1c": -1, "2a": -1, "2b": -1, "2c": -1, "case": 1},
                   "amp_mA": 1.5, "pw_us": 120, "lower_limit_mA": 0.5, "upper_limit_mA": 2.5}}


def test_the_flanking_rule_d52_on_synthetic_program():
    p = SP.normalise(SYNTHETIC_PROGRAM)
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
    f = SP.device_facts_from_program(SYNTHETIC_PROGRAM, "Right")
    assert (f["rate_hz"], f["pulse_width_us"], f["stim_rings_on_sensing_lead"]) == (100.0, 120.0, [1, 2])
    assert f["stim_contacts_on_sensing_lead"] == "1a-1b-1c-2a-2b-2c"
    assert "your stimulation program" in f["_provenance"]
    assert SP.device_facts_from_program(SYNTHETIC_PROGRAM, "Nowhere") == {}


def test_contacts_text_writes_positives_first_as_the_programmer_does():
    assert SP.contacts_text({"2b": -1, "2a": -1, "case": 1}) == "C+ 2a- 2b-"


def _rows(cand):
    plan = TY.ThresholdPlan(upper=0.5, lower=0.2, capture_amp_low=1.0, capture_amp_high=3.0)
    plan = SAFE.apply_to_plan(plan, SYNTHETIC_UID, "Left")
    pr = PR.prescribe(mode=PA.DUAL, threshold_plan=plan, candidate=cand, timing=PA.timing_plan(mode=PA.DUAL))
    return {r["parameter"]: r for r in pr.as_rows()}


def test_with_a_program_the_table_carries_its_rows_and_its_limits():
    cand = {"channel": "ZERO_THREE_LEFT", "center_hz": 25.5, "band_width_hz": 5.0,
            "actuated_hemisphere": "Left", "paused_amplitude_mA": 3.0, "stim_program": SP.normalise(SYNTHETIC_PROGRAM)}
    r = _rows(cand)
    assert r["Stimulation contacts"]["value"] == "C+ 2a- 2b- 2c-"
    assert (r["Rate"]["value"], r["Pulse width"]["value"]) == (100.0, 90.0)
    assert r["Adaptive amplitude limit, lower"]["value"] == 1.0
    assert r["Adaptive amplitude limit, lower"]["status"] == "your_program"
    assert r["Paused amplitude"]["value"] == 3.0 and r["Paused amplitude"]["origin"] == "clinician"


def test_without_a_program_the_table_is_as_before():
    r = _rows({"channel": "ZERO_THREE_LEFT", "center_hz": 25.5, "band_width_hz": 5.0})
    assert "Stimulation contacts" not in r and "Rate" not in r
    assert r["Adaptive amplitude limit, lower"]["status"] == "derived"
    assert r["Paused amplitude"]["value"] is None
