"""Scope and evidential limits of historical configuration review."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from ClosedLoopDeployment import historical_configurations as history
from ClosedLoopDeployment import constraints


def source(**changes):
    return SimpleNamespace(**{**dict(uid="source-1", owner_id="participant-1", hashed="hash-1",
                                   type="MedtronicJSON", metadata={"Device": "device-1"}), **changes})


def event(**changes):
    fields = [{"label": label, "value": value} for label, value in (
        ("Frequency", "55 Hz"), ("Pulse width", "60 µs"), ("Sensing", "On"),
        ("Stimulation contacts", "2a, 2b, 2c"), ("Sensing contacts", "1 and 3"))]
    return {**dict(time=100., kind="settings_observed", phase="Final", settings={
        "group": [{"label": "Group", "value": "Group A"},
                  {"label": "Stimulation status", "value": "On"}],
        "left": fields, "right": []}), **changes}


def collect(sources=None, events=None, **kwargs):
    return history.collect("participant-1", [source()] if sources is None else sources,
                           lambda item: {"excluded": None, "events": [event()] if events is None else events},
                           now=200., **kwargs)


@pytest.mark.parametrize("value", [None, 55, "55 mA", "unknown Hz", "nan Hz", "inf Hz", "0 Hz", "-1 Hz"])
def test_unknown_invalid_or_wrong_unit_is_not_a_configuration(value):
    assert history._quantity(value, "Hz") is None


def test_owner_device_and_source_exclusions_are_checked_before_loading():
    loaded = []
    sources = [source(owner_id="participant-2"), source(metadata={}), source(type="Other"),
               source(metadata={"Device": "device-1", "AnalysisExclusion": "quarantined"}), source()]
    result = history.collect("participant-1", sources,
                             lambda s: loaded.append(s.uid) or {"excluded": "wrong implant", "events": []}, now=200.)
    assert loaded == ["source-1"]
    assert result["excluded_source_count"] == 5
    assert result["configurations"] == []
    unavailable = history.collect("participant-1", [source()], lambda s: None, now=200.)
    assert unavailable["unavailable_source_count"] == 1
    assert unavailable["excluded_source_count"] == 0


def test_active_snapshot_carries_provenance_without_claiming_delivery_or_clearing_limits():
    result = collect()
    row = result["configurations"][0]
    assert row["participant_id"] == "participant-1" and row["device_id"] == "device-1"
    assert row["hemisphere"] == "Left" and row["rate_hz"] == 55. and row["pulse_width_us"] == 60.
    assert row["active_group_observed"] is True
    assert row["stimulation_status"] == row["sensing_status"] == "On"
    assert row["delivery_verified"] is None
    assert row["observations"] == [{"source_id": "source-1", "source_hash": "hash-1", "time": 100., "phase": "Final"}]
    candidate = {"rate_hz": 55., "pulse_width_us": 60., "historical_configurations": result}
    # Even matching ON/active history cannot manufacture missing programmer limits.
    assert constraints._p_d31(candidate, {"historical_configurations": result}) is None
    assert constraints._p_d31(candidate, {"brainsense_min_rate_hz": 60.,
                                         "historical_configurations": result}) is False


def test_full_configuration_device_and_side_are_distinct_and_repeated_snapshots_are_deduplicated():
    changed = deepcopy(event())
    changed["settings"]["left"][-1]["value"] = "0 and 2"
    both = deepcopy(event())
    both["settings"]["right"] = deepcopy(both["settings"]["left"])
    result = collect(sources=[source(), source(uid="source-2"),
                              source(uid="source-3", metadata={"Device": "device-2"})],
                     events=[event(), event(), changed, both])
    rows = result["configurations"]
    assert len(rows) == 6, "Separate sensing settings, device and hemisphere; never rate/PW-only grouping"
    original = next(r for r in rows if r["device_id"] == "device-1" and r["hemisphere"] == "Left"
                    and r["side_settings"][-1]["value"] == "1 and 3")
    assert len(original["observations"]) == 2, "One record per distinct source snapshot, not duplicate events"


def test_invalid_dates_non_settings_missing_side_values_and_unknown_statuses():
    valid = deepcopy(event())
    valid["settings"]["group"] = []
    valid["settings"]["left"] = valid["settings"]["left"][:2]
    missing_pw = deepcopy(valid)
    missing_pw["settings"]["left"] = missing_pw["settings"]["left"][:1]
    result = collect(events=[event(time=1.), event(time=201.), event(time=float("nan")),
                             event(kind="group_change"), missing_pw, valid], earliest=50.)
    assert len(result["configurations"]) == 1
    row = result["configurations"][0]
    assert len(row["observations"]) == 1
    assert row["stimulation_status"] == row["sensing_status"] == "Unknown"


def test_wrapper_uses_shared_review_policy_and_no_model_or_device_operations(monkeypatch):
    from modules import RedcapStimulation, RCS08DataPolicy
    person = SimpleNamespace(uid="participant-1")
    seen = []
    monkeypatch.setattr(RCS08DataPolicy, "applies_to", lambda participant: True)
    monkeypatch.setattr(history.time, "time", lambda: RCS08DataPolicy.IMPLANT_DAY + 2)
    monkeypatch.setattr(RedcapStimulation, "source_context", lambda *args, **kwargs:
                        seen.append((args, kwargs)) or ({"excluded": None, "events": [
                            event(time=RCS08DataPolicy.IMPLANT_DAY - 1),
                            event(time=RCS08DataPolicy.IMPLANT_DAY + 1)]}, True))
    result = history.for_participant(person, [source()])
    assert len(result["configurations"][0]["observations"]) == 1
    assert seen[0][0][1] is person and seen[0][0][2] is True
    assert seen[0][1] == {"cached_only": True}
    monkeypatch.setattr(RCS08DataPolicy, "applies_to", lambda participant: False)
    result = history.for_participant(person, [source()], now=RCS08DataPolicy.IMPLANT_DAY + 2)
    assert len(result["configurations"][0]["observations"]) == 2


@pytest.mark.parametrize("active", [False, None, "true"])
def test_saved_inactive_or_unknown_group_cannot_become_active_configuration_evidence(active):
    from modules import RedcapStimulation
    report = {"SessionDate": "2026-08-01T10:00:00Z", "SessionEndDate": "2026-08-01T11:00:00Z",
              "Groups": {"Initial": [{"ActiveGroup": active}], "Final": [{"ActiveGroup": active}]}}
    result = RedcapStimulation.extract(report)
    assert result["events"] == []
    observed = history.collect("participant-1", [source()], lambda s: result, now=2e9)
    assert observed["configurations"] == []
    report["Groups"]["Final"] = [{"ActiveGroup": True}, {"ActiveGroup": True}]
    assert RedcapStimulation.extract(report)["events"] == []
