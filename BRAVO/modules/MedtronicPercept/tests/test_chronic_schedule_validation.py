"""Complete prepared settings metadata is required before any schedule mutation."""
from copy import deepcopy
from types import SimpleNamespace
import json

import pytest

from modules.MedtronicPercept import chronic_schedule as CS


def empty():
    return {"starts": [], "ends": [], "switches": []}


def valid():
    return {"starts": [[10.0, "initial", "GROUP_A", {"GROUP_A": {"Left": ["1-3", 20.0, "LEFT"]}}]],
            "ends": [[20.0, None, {}]], "switches": [[30.0, "GROUP_A", "GROUP_B"]]}


def test_explicit_empty_and_full_records_are_valid_and_unchanged():
    for record in (empty(), valid()):
        assert CS.validate_settings_record(record) is record
        json.dumps(record, allow_nan=False)


@pytest.mark.parametrize("record", [None, [], {}, {"starts": [], "ends": []},
    dict(empty(), extra=[]), dict(empty(), starts=None), dict(empty(), ends={}),
    dict(empty(), starts=[None]), dict(empty(), starts=[[1, "initial"]]),
    dict(empty(), switches=[[True, "A", "B"]]),
    dict(empty(), switches=[[float("nan"), "A", "B"]]),
    dict(empty(), switches=[[float("inf"), "A", "B"]]),
    dict(empty(), switches=[[10 ** 1000, "A", "B"]]),
    dict(empty(), switches=[["1", "A", "B"]]),
    dict(empty(), switches=[[1, "", "B"]]), dict(empty(), switches=[[1, "A", None]]),
    dict(empty(), starts=[[1, "other", "A", {}]]),
    dict(empty(), ends=[[1, 3, {}]]), dict(empty(), ends=[[1, "A", []]]),
    dict(empty(), ends=[[1, "A", {"": {}}]]), dict(empty(), ends=[[1, "A", {"A": []}]]),
    dict(empty(), ends=[[1, "A", {"A": {"Unknown": ["1-3", 20]}}]]),
    dict(empty(), ends=[[1, "A", {"A": {"Left": "1-3"}}]]),
    dict(empty(), ends=[[1, "A", {"A": {"Left": ["1-3"]}}]]),
    dict(empty(), ends=[[1, "A", {"A": {"Left": ["unknown", 20]}}]]),
    *[dict(empty(), ends=[[1, "A", {"A": {"Left": ["1-3", hz]}}]])
      for hz in (True, "20", 0, -1, float("nan"), float("inf"))],
    dict(empty(), ends=[[1, "A", {"A": {"Left": ["1-3", 20, "UNKNOWN"]}}]]),
])
def test_malformed_record_rejected(record):
    with pytest.raises(ValueError):
        CS.validate_settings_record(record)


def test_unknown_frequency_and_unspecified_active_group_are_explicitly_allowed():
    record = dict(empty(), ends=[[1, None, {"A": {"Right": ["0-3", None]}}]])
    assert CS.validate_settings_record(record) is record


def test_union_rejects_missing_records_instead_of_skipping_them():
    with pytest.raises(ValueError):
        CS.union([valid(), None])


def test_extractor_rejects_non_object_and_preserves_empty_export():
    with pytest.raises(ValueError):
        CS.settings_record(None)
    assert CS.settings_record({}) == empty()


class Row:
    def __init__(self, metadata):
        self.metadata, self.saved = metadata, 0

    def save(self):
        self.saved += 1


def sf(uid, record):
    return SimpleNamespace(uid=uid, metadata={"SensingSettingsRecord": record})


def old_metadata():
    return {"ChannelNames": ["LeftHemisphere LFP"], "ContactSchedule": [[0, "0-3"]],
            "FreqScheduleHz": [[0, 10]], "SignalLeadSchedule": [[0, "LEFT"]]}


@pytest.mark.parametrize("metadata", [{}, None, {"SensingSettingsRecord": None},
    {"SensingSettingsRecord": {"starts": [], "ends": []}}])
def test_last_missing_export_prevents_every_row_mutation(metadata):
    row = Row(old_metadata())
    before = deepcopy(row.metadata)
    files = [sf("first", valid()), SimpleNamespace(uid="last", metadata=metadata)]
    with pytest.raises(ValueError):
        CS.restamp_device_chronic(files, {"first": [row]})
    assert row.metadata == before and row.saved == 0


def test_candidate_storage_failure_prevents_earlier_row_mutation():
    first, second = Row(old_metadata()), Row(dict(old_metadata(), unrelated=float("nan")))
    before = deepcopy(first.metadata)
    with pytest.raises(ValueError):
        CS.restamp_device_chronic([sf("source", valid())], {"source": [first, second]})
    assert first.metadata == before and first.saved == second.saved == 0


def test_complete_empty_inventory_marks_old_labels_unverified_without_deleting_them():
    row = Row(old_metadata())
    result = CS.restamp_device_chronic([sf("source", empty())], {"source": [row]})
    assert result["status"] == "complete" and result["exports_without_record"] == 0
    assert row.metadata["ContactSchedule"] == [[0, "0-3"]]
    assert row.metadata["FreqScheduleHz"] == [[0, 10]]
    assert row.metadata["SignalLeadSchedule"] == [[0, "LEFT"]]
    assert row.metadata["ScheduleNoRecord"] == [[0.0, None]]
    assert row.metadata["ScheduleFlagged"] == [] and row.saved == 1
    assert "no verified" in row.metadata["ScheduleSource"]
    assert CS.restamp_device_chronic([sf("source", empty())], {"source": [row]})["restamped"] == 0


def test_dry_run_is_exact_and_does_not_mutate_rows_even_without_metadata():
    row = Row(None)
    files = [sf("source", empty())]
    dry = CS.restamp_device_chronic(iter(files), {"source": [row]}, save=False)
    assert row.metadata is None and row.saved == 0 and dry["restamped"] == 1
    actual = CS.restamp_device_chronic(files, {"source": [row]})
    assert dry == actual and row.saved == 1


def test_extraction_ignores_unrelated_unusable_entries_and_retains_unknown_frequency():
    groups = [None, {}, {"GroupId": "GroupIdDef.GROUP_A", "ActiveGroup": True,
              "ProgramSettings": {"SensingChannel": [None, {},
                {"HemisphereLocation": "HemisphereLocationDef.Left",
                 "Channel": "SensingElectrodeConfigDef.ONE_AND_THREE",
                 "SensingSetup": {"FrequencyInHertz": "unavailable"}}]}}]
    record = CS.settings_record({"GroupHistory": [None, {},
        {"SessionDate": "2001-01-01T00:00:00Z", "Groups": {"Final": groups}}],
        "DiagnosticData": {"EventLogs": [None, {"ParameterTrendId": "unrelated"},
                                         {"ParameterTrendId": "ActiveGroup", "DateTime": "invalid"}]}})
    assert len(record["starts"]) == 1 and record["ends"] == record["switches"] == []
    assert record["starts"][0][-1] == {"GROUP_A": {"Left": ["1-3", None]}}
    schedule = CS.side_schedules(CS.union([record]))
    assert schedule["LeftHemisphere"]["FreqScheduleHz"] == []


def test_adjacent_disagreement_intervals_coalesce_into_one_flagged_interval():
    # A right-lead-only switch changes a boundary but not the left lead's conflict.
    left_a = {"Left": ["1-3", 20.0], "Right": ["0-3", 8.0]}
    left_b = {"Left": ["0-3", 30.0], "Right": ["0-3", 8.0]}
    record = {"starts": [[1000, "initial", "B", {"A": left_b, "B": left_b}]],
              "ends": [[100, "A", {"A": left_a, "B": left_a}]],
              "switches": [[500, "A", "B"]]}
    result = CS.side_schedules(CS.union([record]))
    assert result["LeftHemisphere"]["ScheduleFlagged"] == [[100.0, 1000.0]]


def test_fractional_timestamps_with_same_rounded_duplicate_identity_are_order_independent():
    import itertools
    groups = {"A": {"Left": ["1-3", 20.0]}, "B": {"Left": ["0-3", 30.0]}}
    records = [{"starts": [[10 + off, "initial", "A", groups]],
                "ends": [[20 + off, "A", groups]], "switches": [[30 + off, "A", "B"]]}
               for off in (0.1, 0.2, 0.3)]
    before = deepcopy(records)
    expected = CS.union(records)
    assert expected["starts"][0][0] == 10.1
    assert expected["ends"][0][0] == 20.1
    assert expected["switches"][0][0] == 30.1
    for order in itertools.permutations(records):
        got = CS.union(order)
        assert got == expected
        assert CS.side_schedules(got) == CS.side_schedules(expected)
    assert records == before
