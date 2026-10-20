"""Synthetic checks for the native chronic-to-timeline display boundary."""
import importlib.util
from pathlib import Path
MODULE = Path(__file__).resolve().parents[2] / "BRAVO/modules/chronic_timeline_contract.py"
spec = importlib.util.spec_from_file_location("chronic_timeline_contract", MODULE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
def activity(times):
    return {"Time": times, "ChannelNames": ["power", "stim"], "ChannelUnits": ["", "mA"],
            "Data": [[0, None, 3][:len(times)], [0, 2, 4][:len(times)]]}
def test_durations_end_at_observed_next_time_without_final_extrapolation():
    source = activity([10, 20, 45]); result = module.chronic_timeline_activity(source)
    assert result["Duration"] == [10, 25, None]
    assert result["AnalysisType"] == "CustomizedTimelineData"
    for field in ("Time", "ChannelNames", "ChannelUnits", "Data"):
        assert result[field] is source[field]
    assert "Duration" not in source
def test_single_observation_is_a_point_with_known_units():
    result = module.chronic_timeline_activity(activity([10]))
    assert result["Duration"] == [None]
    assert result["ChannelUnits"] == ["", "mA"]
    assert result["Data"] == [[0], [0]]
def test_empty_chronic_series_has_no_invented_interval():
    result = module.chronic_timeline_activity(activity([]))
    assert result["Duration"] == []
    assert result["Time"] == []
