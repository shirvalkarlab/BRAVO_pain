"""Every device-clock time of a Percept export is converted to the tablet's clock (the PI, 2026-09-26).

The rule (MedtronicPercept/TabletClock.py): tablet time = the entry's own OffsetInSeconds + its
family's fixed difference (-600 s for the chronic log) + (SessionEndDate - Final
DeviceDateTimeOffsetInSeconds) of the export the entry was derived from: the first export of its
clock block that carries it. These
tests build exports whose device clock runs 7,494 s ahead of the tablet (as RCS08's did on
2026-09-16) and 35 s behind it (as on 2026-09-17), and check every family the export carries.
Plain `assert`, no arguments: container runner.
"""
import copy
from datetime import datetime, timezone

from modules.MedtronicPercept import TabletClock as TC


def iso(t, ms=False):
    d = datetime.fromtimestamp(t, tz=timezone.utc)
    return d.strftime("%Y-%m-%dT%H:%M:%S") + (".000Z" if ms else "Z")


def ep(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


BLOCK = 43


def stamp(t_dev, off, ms=False, key="DateTime"):
    return {key: iso(t_dev, ms), key + "BlockId": BLOCK, key + "OffsetInSeconds": off}


def make_export(session_tablet_iso, device_offset, gap_s, entries_offsets):
    """An export whose device clock reads `gap_s` ahead of the tablet. `entries_offsets`: the device
    offsets (seconds counter) of the entries each family carries."""
    sd = ep(session_tablet_iso)
    a_dev = sd + gap_s - device_offset            # the device's anchor in this export
    dev = lambda off, k=0.0: a_dev + off + k
    o = entries_offsets
    J = {
        "SessionDate": session_tablet_iso,
        "SessionEndDate": iso(sd + 600),
        "DeviceInformation": {"Initial": {**stamp(dev(device_offset), device_offset, key="DeviceDateTime")},
                              "Final": {**stamp(dev(device_offset + 600), device_offset + 600, key="DeviceDateTime")}},
        "BrainSenseTimeDomain": [{**stamp(dev(o["stream"]), o["stream"], True, "FirstPacketDateTime"), "Channel": "ZERO_THREE_LEFT"}],
        "BrainSenseLfp": [{**stamp(dev(o["stream"]), o["stream"], True, "FirstPacketDateTime")}],
        "IndefiniteStreaming": [{**stamp(dev(o["stream"] + 60), o["stream"] + 60, True, "FirstPacketDateTime")}],
        "LfpMontageTimeDomain": [{**stamp(dev(o["stream"] + 120), o["stream"] + 120, True, "FirstPacketDateTime")}],
        "BrainSenseSurveysTimeDomain": [{
            "ElectrodeSurvey": [{**stamp(dev(o["stream"] + 180), o["stream"] + 180, True, "FirstPacketDateTime")}],
            "ElectrodeIdentifier": [{"FirstPacketDateTime": "", "FirstPacketDateTimeBlockId": BLOCK,
                                     "FirstPacketDateTimeOffsetInSeconds": 0}]}],
        "CalibrationTests": [{**stamp(dev(o["stream"] + 240), o["stream"] + 240, True, "FirstPacketDateTime")}],
        "SenseChannelTests": [{**stamp(dev(o["stream"] + 300), o["stream"] + 300, True, "FirstPacketDateTime")}],
        "Thresholds": [{**stamp(dev(o["stream"] + 360), o["stream"] + 360, True, "FirstPacketDateTime")}],
        "DiagnosticData": {
            "LFPTrendLogs": {"HemisphereLocationDef.Left": {"2026-09-16T00:00:00Z": [
                {**stamp(dev(o["chronic"], -600.0), o["chronic"]), "LFP": 100, "AmplitudeInMilliAmps": 3.0}]}},
            "LfpFrequencySnapshotEvents": [{**stamp(dev(o["event"]), o["event"]), "EventName": "Pain",
                                            "LfpFrequencySnapshotEvents": {"HemisphereLocationDef.Left":
                                                                           {**stamp(dev(o["event"]), o["event"])}}}],
            "EventLogs": [{**stamp(dev(o["eventlog"]), o["eventlog"]), "NewGroupId": "GroupIdDef.GROUP_B"}],
        },
        "GroupHistory": [{**stamp(dev(o["group"]), o["group"], key="SessionDate"), "Groups": []}],
        "RechargeCount": [{**stamp(dev(o["recharge"]), o["recharge"], key="SessionStartDate")}],
        "EventSummary": {**stamp(dev(o["eventlog"]), o["eventlog"], key="SessionStartDate"),
                         **stamp(dev(device_offset), device_offset, key="SessionEndDate")},
        "Annotations": [{**stamp(dev(o["eventlog"]), o["eventlog"], key="Date")}],
    }
    return J


A_OFF = 36_000_000.0                        # export A's device reading (its seconds counter)
A_TABLET = "2026-09-16T17:00:00Z"
OFFS = {"stream": A_OFF + 300, "chronic": A_OFF - 3 * 3600, "event": A_OFF - 5000,
        "eventlog": A_OFF - 7000, "group": A_OFF - 86_400, "recharge": A_OFF - 20_000}


def expected(off, k=0.0, anchor=None):
    anchor = ep(A_TABLET) - A_OFF if anchor is None else anchor
    return off + k + anchor


def test_every_device_clock_family_converts_to_offset_plus_family_difference_plus_the_tablet_anchor():
    J = make_export(A_TABLET, A_OFF, 7494.0, OFFS)
    TC.convert_export(J, [])
    got = {
        "TD": J["BrainSenseTimeDomain"][0]["FirstPacketDateTime"],
        "power": J["BrainSenseLfp"][0]["FirstPacketDateTime"],
        "indefinite": J["IndefiniteStreaming"][0]["FirstPacketDateTime"],
        "montage": J["LfpMontageTimeDomain"][0]["FirstPacketDateTime"],
        "survey": J["BrainSenseSurveysTimeDomain"][0]["ElectrodeSurvey"][0]["FirstPacketDateTime"],
        "calibration": J["CalibrationTests"][0]["FirstPacketDateTime"],
        "sense channel": J["SenseChannelTests"][0]["FirstPacketDateTime"],
        "thresholds": J["Thresholds"][0]["FirstPacketDateTime"],
        "chronic": J["DiagnosticData"]["LFPTrendLogs"]["HemisphereLocationDef.Left"]["2026-09-16T00:00:00Z"][0]["DateTime"],
        "event": J["DiagnosticData"]["LfpFrequencySnapshotEvents"][0]["DateTime"],
        "event side": J["DiagnosticData"]["LfpFrequencySnapshotEvents"][0]["LfpFrequencySnapshotEvents"]["HemisphereLocationDef.Left"]["DateTime"],
        "event log": J["DiagnosticData"]["EventLogs"][0]["DateTime"],
        "group history": J["GroupHistory"][0]["SessionDate"],
        "recharge": J["RechargeCount"][0]["SessionStartDate"],
        "summary start": J["EventSummary"]["SessionStartDate"],
        "summary end": J["EventSummary"]["SessionEndDate"],
        "annotation": J["Annotations"][0]["Date"],
        "device reading": J["DeviceInformation"]["Initial"]["DeviceDateTime"],
    }
    want = {
        "TD": iso(expected(OFFS["stream"]), True), "power": iso(expected(OFFS["stream"]), True),
        "indefinite": iso(expected(OFFS["stream"] + 60), True), "montage": iso(expected(OFFS["stream"] + 120), True),
        "survey": iso(expected(OFFS["stream"] + 180), True), "calibration": iso(expected(OFFS["stream"] + 240), True),
        "sense channel": iso(expected(OFFS["stream"] + 300), True), "thresholds": iso(expected(OFFS["stream"] + 360), True),
        "chronic": iso(expected(OFFS["chronic"], -600.0)), "event": iso(expected(OFFS["event"])),
        "event side": iso(expected(OFFS["event"])), "event log": iso(expected(OFFS["eventlog"])),
        "group history": iso(expected(OFFS["group"])), "recharge": iso(expected(OFFS["recharge"])),
        "summary start": iso(expected(OFFS["eventlog"])), "summary end": A_TABLET,
        "annotation": iso(expected(OFFS["eventlog"])), "device reading": A_TABLET,
    }
    wrong = {k: (got[k], want[k]) for k in want if got[k] != want[k]}
    assert not wrong, wrong
    # the tablet's own fields and an empty time are untouched
    assert J["SessionDate"] == A_TABLET
    assert J["BrainSenseSurveysTimeDomain"][0]["ElectrodeIdentifier"][0]["FirstPacketDateTime"] == ""


def test_the_stream_moves_back_by_the_device_clocks_lead():
    J = make_export(A_TABLET, A_OFF, 7494.0, OFFS)
    before = ep(J["BrainSenseTimeDomain"][0]["FirstPacketDateTime"])
    TC.convert_export(J, [])
    after = ep(J["BrainSenseTimeDomain"][0]["FirstPacketDateTime"])
    assert before - after == 7494.0


def _stored(J, anchors):
    """What the ingest records for an export: its anchor and the entries it carried first."""
    counts = TC.convert_export(copy.deepcopy(J), anchors)
    return dict(TC.export_anchor(J), first_carried=counts["first_carried"])


def _chronic(J):
    return J["DiagnosticData"]["LFPTrendLogs"]["HemisphereLocationDef.Left"]["2026-09-16T00:00:00Z"][0]["DateTime"]


B_OFF = A_OFF + 86_000.0
B_TABLET = iso(ep(A_TABLET) + 86_000.0 + 3.0)       # the tablet anchor moves by a few seconds
A_ANCHOR, B_ANCHOR = ep(A_TABLET) - A_OFF, ep(B_TABLET) - B_OFF


def test_an_entry_re_sent_in_a_later_export_keeps_the_anchor_of_the_first_export_that_carried_it():
    # 2026-09-16 (device ahead by 7,494 s) and 2026-09-17 (device 35 s behind). A chronic reading
    # logged before A is carried by A and re-sent by B: it was derived from A, so B's copy converts
    # with A's anchor and both copies read one time. B's own stream takes B's anchor.
    A = make_export(A_TABLET, A_OFF, 7494.0, OFFS)
    B = make_export(B_TABLET, B_OFF, -35.0, dict(OFFS, stream=B_OFF + 200))
    stored = [_stored(A, [])]
    A2, B2 = copy.deepcopy(A), copy.deepcopy(B)
    TC.convert_export(A2, stored); TC.convert_export(B2, stored)
    assert A_ANCHOR != B_ANCHOR
    assert _chronic(A2) == _chronic(B2) == iso(OFFS["chronic"] - 600 + A_ANCHOR)
    assert B2["BrainSenseTimeDomain"][0]["FirstPacketDateTime"] == iso(B_OFF + 200 + B_ANCHOR, True)


def test_an_entry_first_carried_by_a_later_export_takes_that_exports_anchor_even_if_logged_before_an_earlier_one():
    # A reading logged BEFORE A's session that A did not carry (an export not fully read carries no
    # logs) was derived from B, the first export that carries it.
    A = make_export(A_TABLET, A_OFF, 7494.0, OFFS)
    del A["DiagnosticData"]["LFPTrendLogs"]
    B = make_export(B_TABLET, B_OFF, -35.0, dict(OFFS, stream=B_OFF + 200))
    stored = [_stored(A, [])]
    TC.convert_export(B, stored)
    assert _chronic(B) == iso(OFFS["chronic"] - 600 + B_ANCHOR)


def test_the_export_records_the_entries_it_carried_first_and_not_those_an_earlier_export_carried():
    A = make_export(A_TABLET, A_OFF, 7494.0, OFFS)
    B = make_export(B_TABLET, B_OFF, -35.0, dict(OFFS, stream=B_OFF + 200))
    counts = TC.convert_export(copy.deepcopy(B), [_stored(A, [])])
    fc = counts["first_carried"]
    chronic_key = ".DiagnosticData.LFPTrendLogs.HemisphereLocationDef.Left.<date>[].DateTime"
    assert chronic_key not in fc                                  # A carried it first
    assert fc[".BrainSenseTimeDomain[].FirstPacketDateTime"] == {str(BLOCK): [B_OFF + 200]}


def test_the_anchor_pairs_the_tablets_save_time_with_the_devices_final_reading():
    # SessionEndDate pairs with the Final reading; SessionDate (stamped about 34 s after the Initial
    # reading on RCS08) is not used where an end time exists.
    J = make_export(A_TABLET, A_OFF, 7494.0, OFFS)
    J["SessionDate"] = iso(ep(A_TABLET) + 34.0)
    a = TC.export_anchor(J)
    assert a["rule"] == "SessionEndDate-Final"
    assert a["anchor_s"] == ep(J["SessionEndDate"]) - (A_OFF + 600)
    TC.convert_export(J, [])
    assert J["BrainSenseTimeDomain"][0]["FirstPacketDateTime"] == iso(expected(OFFS["stream"]), True)


def test_an_export_with_no_save_time_falls_back_to_its_start_and_initial_reading_and_says_so():
    J = make_export(A_TABLET, A_OFF, 7494.0, OFFS)
    J["SessionEndDate"] = ""
    a = TC.export_anchor(J)
    assert a["rule"].startswith("SessionDate-Initial")
    assert a["anchor_s"] == ep(A_TABLET) - A_OFF


def test_an_entry_in_a_clock_block_with_no_export_is_left_out_and_counted():
    J = make_export(A_TABLET, A_OFF, 7494.0, OFFS)
    old = {**stamp(1.7e9, 5000.0), "NewGroupId": "x"}
    old["DateTimeBlockId"] = 17
    J["DiagnosticData"]["EventLogs"].append(old)
    counts = TC.convert_export(J, [])
    assert len(J["DiagnosticData"]["EventLogs"]) == 1
    assert counts["left_out"] == {".DiagnosticData.EventLogs[]": 1}


def test_converting_twice_changes_nothing():
    J = make_export(A_TABLET, A_OFF, 7494.0, OFFS)
    TC.convert_export(J, [])
    once = copy.deepcopy(J)
    TC.convert_export(J, [])
    once.pop("_TabletClock"); J.pop("_TabletClock")
    assert J == once


def test_the_export_anchor_is_the_save_time_minus_the_final_reading():
    J = make_export(A_TABLET, A_OFF, 7494.0, OFFS)
    a = TC.export_anchor(J)
    assert a == {"block": BLOCK, "final_offset_s": A_OFF + 600, "session_date_s": ep(A_TABLET),
                 "anchor_s": ep(A_TABLET) + 600 - (A_OFF + 600), "rule": "SessionEndDate-Final"}
