"""Each chronic-log reading is filed under the contact pair and band in force when it was taken,
by ONE schedule built from every export (decision 487; `MedtronicPercept/chronic_schedule.py`).

Until 2026-10-18 each export's chronic recording carried its own schedule, read off its
`GroupHistory` as if each entry started at its date, and switches of active group between sessions
were ignored; two exports could file one reading under two labels (2,350 on RCS08). Pinned here on
small made-up exports:
- a `GroupHistory` entry is the settings at the START of its session: readings before that
  session keep the earlier settings, readings after its end take its `Groups.Final`;
- an event-log switch of active group between sessions is applied from its time;
- when the two views disagree the start-of-session record wins and the stretch is flagged;
- a session start with no known end voids the view from the earlier end;
- the schedule does not depend on the order the exports arrive;
- every chronic recording of the device gets the same schedule, so the merge files no reading
  under two labels.

Plain `assert`, no arguments: these run in the container.
"""
import random
from datetime import datetime, timezone

import numpy as np

from modules.MedtronicPercept import chronic_schedule as CS
from modules.DecodeCommon import representation as R


def _iso(t):
    return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _group(gid, active, left, right):
    sens = []
    for side, (ch, hz) in (("Left", left), ("Right", right)):
        sens.append({"HemisphereLocation": f"HemisphereLocationDef.{side}",
                     "Channel": f"SensingElectrodeConfigDef.{ch}",
                     "SensingSetup": {"FrequencyInHertz": hz}})
    return {"GroupId": f"GroupIdDef.{gid}", "ActiveGroup": active,
            "ProgramSettings": {"SensingChannel": sens}}


D_ = ("ONE_AND_THREE", 24.41)        # group D: 1-3 at 24.41 Hz both sides
A_L, A_R = ("ZERO_AND_THREE", 26.37), ("ZERO_AND_THREE", 7.81)
H = 3600.0
T0 = 1_780_000_000.0


def _groups(active, a_left=A_L, a_right=A_R, d=D_):
    return [_group("GROUP_A", active == "A", a_left, a_right), _group("GROUP_D", active == "D", d, d)]


def _export(start, end, initial, final, history=(), switches=()):
    return {"SessionDate": _iso(start), "SessionEndDate": _iso(end),
            "Groups": {"Initial": initial, "Final": final},
            "GroupHistory": [{"SessionDate": _iso(t), "Groups": g} for t, g in history],
            "DiagnosticData": {"EventLogs": [{"DateTime": _iso(t), "ParameterTrendId": "ParameterTrendIdDef.ActiveGroup",
                                              "OldGroupId": f"GroupIdDef.GROUP_{o}", "NewGroupId": f"GroupIdDef.GROUP_{n}"}
                                             for t, o, n in switches]}}


def _three_sessions():
    # session 1 (T0) ends with D active. Session 2 (T0 + 24 h) changes D's band to 26.37 Hz on 0-3.
    # Session 3 (T0 + 48 h) is a later export whose GroupHistory holds sessions 1 and 2 at their
    # START settings.
    D2 = ("ZERO_AND_THREE", 26.37)
    s1 = _export(T0, T0 + 300, _groups("D"), _groups("D"))
    s2 = _export(T0 + 24 * H, T0 + 24 * H + 300, _groups("D"), _groups("D", d=D2))
    s3 = _export(T0 + 48 * H, T0 + 48 * H + 300, _groups("D", d=D2), _groups("D", d=D2),
                 history=[(T0 - 30, _groups("D")), (T0 + 24 * H - 30, _groups("D"))])
    return [s1, s2, s3]


def _labels(exports, times, side="Left"):
    U = CS.union([CS.settings_record(e) for e in exports])
    return [CS.label_at(U, t, side) for t in times]


def test_a_history_entry_is_the_start_of_its_session_so_the_change_starts_at_that_sessions_end():
    ex = _three_sessions()
    got = _labels(ex, [T0 + 12 * H, T0 + 24 * H - 600, T0 + 36 * H])
    assert [g[0] for g in got] == [["1-3", 24.41], ["1-3", 24.41], ["0-3", 26.37]], got
    assert not any(g[1] for g in got)


def test_a_switch_of_active_group_between_sessions_applies_from_its_time():
    sw = T0 + 6 * H
    s1 = _export(T0, T0 + 300, _groups("D"), _groups("D"), switches=[(sw, "D", "A")])
    s2 = _export(T0 + 24 * H, T0 + 24 * H + 300, _groups("A"), _groups("A"), switches=[(sw, "D", "A")])
    got = _labels([s1, s2], [sw - 600, sw + 600], side="Right")
    assert got == [(["1-3", 24.41], False), (["0-3", 7.81], False)], got


def test_when_the_views_disagree_the_start_of_session_record_wins_and_is_flagged():
    # session 1 ends with D active; the next session starts with A active, and no switch is logged
    s1 = _export(T0, T0 + 300, _groups("D"), _groups("D"))
    s2 = _export(T0 + 24 * H, T0 + 24 * H + 300, _groups("A"), _groups("A"))
    lab, flagged = _labels([s1, s2], [T0 + 12 * H], side="Right")[0]
    assert lab == ["0-3", 7.81] and flagged
    sched = CS.side_schedules(CS.union([CS.settings_record(e) for e in (s1, s2)]))
    fl = sched["RightHemisphere"]["ScheduleFlagged"]
    assert len(fl) == 1 and fl[0][0] <= T0 + 12 * H < fl[0][1], fl


def test_a_session_start_with_no_known_end_voids_the_view_from_the_earlier_end():
    s1 = _export(T0, T0 + 300, _groups("D"), _groups("D"))
    # an export of a session at T0 + 10 h whose end is unknown (no SessionEndDate), changing D
    lost = _export(T0 + 10 * H, T0 + 10 * H, _groups("D", d=("ZERO_AND_TWO", 13.67)), _groups("D", d=("ZERO_AND_TWO", 13.67)))
    del lost["SessionEndDate"]
    s3 = _export(T0 + 24 * H, T0 + 24 * H + 300, _groups("D", d=("ZERO_AND_TWO", 13.67)), _groups("D", d=("ZERO_AND_TWO", 13.67)))
    U = CS.union([CS.settings_record(e) for e in (s1, lost, s3)])
    left, right = CS.views_at(U, T0 + 12 * H, "Left")
    assert left is None and right == ["0-2", 13.67]


def test_the_schedule_does_not_depend_on_the_order_the_exports_arrive():
    ex = _three_sessions()
    want = CS.side_schedules(CS.union([CS.settings_record(e) for e in ex]))
    rng = random.Random(7)
    for _ in range(6):
        order = ex[:]
        rng.shuffle(order)
        assert CS.side_schedules(CS.union([CS.settings_record(e) for e in order])) == want


class _Row:
    def __init__(self, uid, md):
        self.uid, self.metadata, self.saved = uid, md, 0

    def save(self):
        self.saved += 1


class _SF:
    def __init__(self, uid, rec):
        self.uid, self.metadata = uid, {"SensingSettingsRecord": rec}


def test_every_chronic_recording_gets_the_one_schedule_and_no_reading_has_two_labels():
    ex = _three_sessions()
    sfs = [_SF(f"sf{i}", CS.settings_record(e)) for i, e in enumerate(ex)]
    # each export's own (old) schedule differs; the rows start with it
    rows = {f"sf{i}": [_Row(f"r{i}", {"ChannelNames": ["LeftHemisphere LFP", "LeftHemisphere Amplitude"],
                                       "ContactSchedule": [[T0 + i, "0-2"]], "FreqScheduleHz": [[T0 + i, 10.0 + i]]})]
            for i in range(3)}
    counts = CS.restamp_device_chronic(sfs, rows)
    assert counts["restamped"] == 3 and counts["exports_without_record"] == 0, counts
    mds = [rows[k][0].metadata for k in rows]
    assert all(m["ContactSchedule"] == mds[0]["ContactSchedule"] for m in mds)
    assert all(m["FreqScheduleHz"] == mds[0]["FreqScheduleHz"] for m in mds)
    # two copies of one reading, as two exports carry it, filed once
    t = np.asarray([T0 + 12 * H, T0 + 36 * H])
    recs = [{"ChannelNames": m["ChannelNames"], "Data": np.array([[100.0, 1.0], [200.0, 1.0]]), "Time": t,
             "ContactSchedule": m["ContactSchedule"], "FreqScheduleHz": m["FreqScheduleHz"],
             "RecordingType": "MedtronicChronicBrainSense"} for m in mds[:2]]
    _, c = R.merge_chronic_repeats(recs)
    assert c["readings_under_two_labels"] == 0 and c["repeats_removed"] == 2, c
    assert R.chronic_pair_keys(recs[0], t, "LEFT", "X") == ["ONE_THREE_LEFT", "ZERO_THREE_LEFT"]
    assert [R.snap_freq(x) for x in R.chronic_band_tags(recs[0], t, "LEFT")] == [R.snap_freq(24.41), R.snap_freq(26.37)]
    # a second restamp changes nothing
    assert CS.restamp_device_chronic(sfs, rows)["restamped"] == 0
