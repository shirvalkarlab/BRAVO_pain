"""The settings stream says whether each programmed upper limit is a patient limit (decision 136's
rule, imported from the Closed-Loop module): a sensing group's limit is not one while its adaptive
therapy is running. Written for review S8 of 2026-09-12; the anchor builder that read the column
(`plots.limit_anchors_from_stream`) was deleted on 2026-09-12 when the PI replaced the safety
model's limit anchors with a stated ceiling (`safety_ceiling.py`), and its tests went with it.
The column itself is a fact about the record and stays on the stream.
"""
import pytest

from StimOptimizer import adapter as AD


# ---------------------------------------------------------------------------------------------
# the stream carries whether each limit is a patient limit
# ---------------------------------------------------------------------------------------------
def _sensing_channel(side, upper, status):
    return {"HemisphereLocation": f"HemisphereLocationDef.{side}", "SuspendAmplitudeInMilliAmps": 2.0,
            "PulseWidthInMicroSecond": 100, "RateInHertz": 55, "UpperLimitInMilliAmps": upper,
            "LowerLimitInMilliAmps": 1.0, "AdaptiveTherapyStatus": status,
            "ElectrodeState": [{"Electrode": "ElectrodeDef.SenSight_1", "ElectrodeStateResult": "Negative"}]}


def test_a_sensing_limit_under_running_adaptive_therapy_is_not_a_patient_limit():
    g = {"ProgramSettings": {"SensingChannel": [
        _sensing_channel("Left", 3.0, "AdaptiveTherapyStatusDef.RUNNING"),
        _sensing_channel("Right", 4.0, "AdaptiveTherapyStatusDef.NOT_CONFIGURED")]}}
    out = AD.group_settings(g)
    assert out["Left"]["upper"] == 3.0 and out["Left"]["upper_is_patient_limit"] is False
    assert out["Right"]["upper"] == 4.0 and out["Right"]["upper_is_patient_limit"] is True
    assert out["Left"]["schema"] == "sensing"


def test_a_legacy_program_limit_is_a_patient_limit_and_no_limit_is_none():
    g = {"ProgramSettings": {"RateInHertz": 110, "LeftHemisphere": {"Programs": [
        {"AmplitudeInMilliAmps": 2.0, "PulseWidthInMicroSecond": 60, "UpperLimitInMilliAmps": 3.2,
         "ElectrodeState": []}]}, "RightHemisphere": {"Programs": [
        {"AmplitudeInMilliAmps": 2.0, "PulseWidthInMicroSecond": 60, "ElectrodeState": []}]}}}
    out = AD.group_settings(g)
    assert out["Left"]["upper_is_patient_limit"] is True and out["Left"]["schema"] == "hemisphere"
    assert out["Right"]["upper"] is None and out["Right"]["upper_is_patient_limit"] is None


def test_the_rule_is_the_closed_loop_modules_not_a_copy():
    import inspect
    src = inspect.getsource(AD._sensing_upper_is_patient_limit)
    assert "session_report_facts" in src and "_patient_limits_configured" in src
    # the comparison itself lives in the imported rule; only the docstring names the status here
    assert '== "RUNNING"' not in src and "AdaptiveTherapyStatus" not in src.split('"""')[2]


def test_the_stream_rule_version_was_bumped_for_the_new_column():
    # v2 added the column; any later version (v3 starts the stream at implant, 2026-09-24) keeps it
    assert not AD._THERAPY_SETTINGS_RULE_VERSION.startswith("v1")
    import inspect
    assert '"upper_is_patient_limit"' in inspect.getsource(AD._build_settings_stream)
