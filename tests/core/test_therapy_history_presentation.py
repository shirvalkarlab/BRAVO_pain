"""Compact therapy payload must change representation only, never the shared source."""
import copy
import importlib.util
from pathlib import Path
import pytest
MODULE = Path(__file__).resolve().parents[2] / "BRAVO/modules/therapy_history_presentation.py"
spec = importlib.util.spec_from_file_location("therapy_history_presentation", MODULE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def history():
    return {
        "TherapyModification": [{"Device": {"Id": "synthetic"}, "History": [
            {"Date": 1, "Previous": "A", "New": "B", "Therapy": {"Repeated": [1, 2]}},
            {"Date": 2, "Previous": "B", "New": "A"}]}],
        "TherapyTimeline": [{"Date": 1, "Therapies": [{"Repeated": [1, 2]}], "DefinedTherapies": [{"GroupId": "A", "Current": 0}]},
                            {"Date": 2, "DefinedTherapies": []}],
        "TherapyDevices": [{"Id": "synthetic"}],
        "TherapyConfiguration": [{"History": [{"Current": 0, "Unknown": None}]}],
        "DeviceImpedance": [1, 2],
        "FutureField": {"Unmodified": True},
    }

@pytest.mark.parametrize("compact", [False, None, "true", 1, 0])
def test_legacy_default_is_exact_original_without_opt_in(compact):
    source = history()
    assert module.therapy_history_response(source, compact) is source
    assert module.therapy_history_response(source) is source

def test_opt_in_omits_only_two_unused_nested_fields_without_mutating_source():
    source = history(); before = copy.deepcopy(source)
    result = module.therapy_history_response(source, True)
    expected = copy.deepcopy(before)
    for device in expected["TherapyModification"]:
        for row in device["History"]: row.pop("Therapy", None)
    for row in expected["TherapyTimeline"]: row.pop("Therapies", None)
    assert result == expected
    assert source == before
    assert result is not source
    assert result["TherapyModification"][0]["History"][0] is not source["TherapyModification"][0]["History"][0]
    assert result["TherapyTimeline"][0] is not source["TherapyTimeline"][0]

def test_empty_histories_stay_empty():
    assert module.therapy_history_response({"TherapyModification": [], "TherapyTimeline": []}, True) == {"TherapyModification": [], "TherapyTimeline": []}
