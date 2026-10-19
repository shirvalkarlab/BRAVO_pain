"""Each chronic-log reading is filed under the lead its signal came from (the PI, 2026-10-19:
"File each reading under the lead it actually came from"), and a false switch of active group is
not taken as real (the PI asked for the 2026-09-10 case to be resolved).

RCS08 has one device and two leads, and each export files the chronic log under each lead
(`LFPTrendLogs`, "HemisphereLocationDef.Left" / ".Right"). When a group senses ONE lead's signal
for both leads' entries (adaptive group D: both entries' `SensingSetup.ChannelSignalResult.Channel`
name the same lead, e.g. ONE_THREE_LEFT, and the session-report PDF prints the other lead's name
under SENSING SETUP), the other lead's log is a copy of that signal. Pinned here on made-up
exports:
- the schedule names the lead each side's signal comes from (`SignalLeadSchedule`), from the
  device settings alone, never from equal power;
- the copy is merged with the reading of the lead it came from: counted once, under that lead,
  that lead's current kept and the other lead's current recorded beside it (counted when the two
  differ); a copy whose power differs is kept and counted; a copy with no reading to merge with is
  moved to its lead;
- two leads sensing their own signals with equal values by chance stay two readings;
- the result does not depend on the order the recordings arrive;
- a logged switch of active group whose new group is the group already in force is dropped
  (2026-09-10: a false "A -> D" switch at 22:52, present in one export only, filed 18 right-lead
  readings under group A).

Plain `assert`, no arguments: these run in both suites.
"""
import random
from datetime import datetime, timezone

import numpy as np

from modules.MedtronicPercept import chronic_schedule as CS
from modules.DecodeCommon import representation as R

H = 3600.0
T0 = 1_780_000_000.0
_PAIR_TOKEN = {"ONE_AND_THREE": "ONE_THREE", "ZERO_AND_THREE": "ZERO_THREE"}


def _iso(t):
    return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _entry(side, ch, hz, lead):
    return {"HemisphereLocation": f"HemisphereLocationDef.{side}",
            "Channel": f"SensingElectrodeConfigDef.{ch}",
            "SensingSetup": {"FrequencyInHertz": hz,
                             "ChannelSignalResult": {"Channel": f"SensingChannelDef.{_PAIR_TOKEN[ch]}_{lead.upper()}"}}}


def _group(gid, active, left, right):
    """left / right: (channel config, Hz, the lead its signal result names)."""
    return {"GroupId": f"GroupIdDef.{gid}", "ActiveGroup": active,
            "ProgramSettings": {"SensingChannel": [_entry("Left", *left), _entry("Right", *right)]}}


ONE_LEAD = ("ONE_AND_THREE", 23.44, "Left")                       # group D: L 1-3 senses for both
OWN_L, OWN_R = ("ONE_AND_THREE", 23.44, "Left"), ("ZERO_AND_THREE", 7.81, "Right")   # group A


def _groups(active):
    return [_group("GROUP_A", active == "A", OWN_L, OWN_R), _group("GROUP_D", active == "D", ONE_LEAD, ONE_LEAD)]


def _export(start, end, initial, final, switches=()):
    return {"SessionDate": _iso(start), "SessionEndDate": _iso(end),
            "Groups": {"Initial": initial, "Final": final}, "GroupHistory": [],
            "DiagnosticData": {"EventLogs": [{"DateTime": _iso(t), "ParameterTrendId": "ParameterTrendIdDef.ActiveGroup",
                                              "OldGroupId": f"GroupIdDef.GROUP_{o}", "NewGroupId": f"GroupIdDef.GROUP_{n}"}
                                             for t, o, n in switches]}}


def _sched(exports):
    return CS.side_schedules(CS.union([CS.settings_record(e) for e in exports]))


def _rec(side, t, lfp, amp, s):
    return {"ChannelNames": [f"{side}Hemisphere LFP", f"{side}Hemisphere Amplitude"],
            "Data": np.column_stack([np.asarray(lfp, float), np.asarray(amp, float)]),
            "Time": np.asarray(t, float), "SamplingRate": -1, "RecordingType": "MedtronicChronicBrainSense",
            "ContactSchedule": s["ContactSchedule"], "FreqScheduleHz": s["FreqScheduleHz"],
            "SignalLeadSchedule": s["SignalLeadSchedule"]}


def _filed(recs):
    """Every reading handed on: (side, contact-pair key, time, power, current), sorted."""
    out = []
    for r in recs:
        side = "LEFT" if "Left" in r["ChannelNames"][0] else "RIGHT"
        t = np.asarray(r["Time"], float)
        keys = R.chronic_pair_keys(r, t, side, "X")
        for k, tt, row in zip(keys, t, np.asarray(r["Data"], float)):
            out.append((side, k, float(tt), float(row[0]), float(row[1])))
    return sorted(out)


def test_the_schedule_names_the_lead_each_sides_signal_comes_from():
    s = _sched([_export(T0, T0 + 300, _groups("D"), _groups("D")),
                _export(T0 + 24 * H, T0 + 24 * H + 300, _groups("D"), _groups("D"))])
    assert [x[1] for x in s["RightHemisphere"]["SignalLeadSchedule"]] == ["LEFT"], s["RightHemisphere"]
    assert [x[1] for x in s["LeftHemisphere"]["SignalLeadSchedule"]] == ["LEFT"], s["LeftHemisphere"]
    a = _sched([_export(T0, T0 + 300, _groups("A"), _groups("A"))])
    assert [x[1] for x in a["RightHemisphere"]["SignalLeadSchedule"]] == ["RIGHT"]


def test_both_leads_sensing_one_lead_gives_one_reading_under_that_lead_and_none_under_the_other():
    s = _sched([_export(T0, T0 + 300, _groups("D"), _groups("D")),
                _export(T0 + 24 * H, T0 + 24 * H + 300, _groups("D"), _groups("D"))])
    t = T0 + 3 * H + 600.0 * np.arange(5)
    lfp = 300.0 + np.arange(5)
    left = _rec("Left", t, lfp, np.full(5, 2.0), s["LeftHemisphere"])
    right = _rec("Right", t, lfp, np.full(5, 2.5), s["RightHemisphere"])
    out, c = R.merge_chronic_repeats([left, right])
    got = _filed(out)
    assert len(got) == 5, got
    assert all(g[0] == "LEFT" and g[1] == "ONE_THREE_LEFT" and g[4] == 2.0 for g in got), got
    assert c["other_lead_copies_merged"] == 5 and c["other_lead_current_differs"] == 5, c
    assert c["other_lead_power_differs"] == 0 and c["other_lead_moved_alone"] == 0, c
    assert c["readings_under_two_labels"] == 0, c
    # the other lead's current is kept beside the reading it was merged into
    kept = [r for r in out if "Left" in r["ChannelNames"][0]][0]
    assert list(np.asarray(kept["OtherLeadCurrentMilliAmps"], float)) == [2.5] * 5, kept


def test_two_leads_sensing_their_own_signals_with_equal_values_stay_two_readings():
    s = _sched([_export(T0, T0 + 300, _groups("A"), _groups("A")),
                _export(T0 + 24 * H, T0 + 24 * H + 300, _groups("A"), _groups("A"))])
    t = T0 + 3 * H + 600.0 * np.arange(4)
    lfp, amp = np.full(4, 300.0), np.full(4, 2.0)
    out, c = R.merge_chronic_repeats([_rec("Left", t, lfp, amp, s["LeftHemisphere"]),
                                      _rec("Right", t, lfp, amp, s["RightHemisphere"])])
    got = _filed(out)
    assert len(got) == 8, got
    assert sum(g[0] == "LEFT" for g in got) == 4 and sum(g[0] == "RIGHT" for g in got) == 4, got
    assert c["other_lead_copies_merged"] == 0, c


def test_a_copy_with_different_power_is_kept_and_counted_and_a_lone_copy_moves_to_its_lead():
    s = _sched([_export(T0, T0 + 300, _groups("D"), _groups("D")),
                _export(T0 + 24 * H, T0 + 24 * H + 300, _groups("D"), _groups("D"))])
    t = T0 + 3 * H + 600.0 * np.arange(3)
    left = _rec("Left", t[:2], [300.0, 301.0], [2.0, 2.0], s["LeftHemisphere"])
    right = _rec("Right", t, [300.0, 999.0, 302.0], [2.5, 2.5, 2.5], s["RightHemisphere"])
    out, c = R.merge_chronic_repeats([left, right])
    got = _filed(out)
    assert c["other_lead_copies_merged"] == 1 and c["other_lead_power_differs"] == 1, c
    assert c["other_lead_moved_alone"] == 1, c
    assert all(g[0] == "LEFT" for g in got), got
    assert sorted(g[3] for g in got) == [300.0, 301.0, 302.0, 999.0], got


def test_the_merge_with_copies_does_not_depend_on_the_order_the_recordings_arrive():
    s = _sched([_export(T0, T0 + 300, _groups("D"), _groups("D")),
                _export(T0 + 24 * H, T0 + 24 * H + 300, _groups("D"), _groups("D"))])
    t = T0 + 3 * H + 600.0 * np.arange(6)
    recs = [_rec("Left", t[:4], 300.0 + np.arange(4), np.full(4, 2.0), s["LeftHemisphere"]),
            _rec("Left", t, 300.0 + np.arange(6), np.full(6, 2.0), s["LeftHemisphere"]),
            _rec("Right", t[2:], 300.0 + np.arange(2, 6), np.full(4, 2.5), s["RightHemisphere"]),
            _rec("Right", t, 300.0 + np.arange(6), np.full(6, 2.5), s["RightHemisphere"])]
    want, wc = R.merge_chronic_repeats(recs)
    rng = random.Random(3)
    for _ in range(8):
        order = list(range(len(recs)))
        rng.shuffle(order)
        got, gc = R.merge_chronic_repeats([recs[i] for i in order])
        assert _filed(got) == _filed(want) and gc == wc, (gc, wc)
    assert len(_filed(want)) == 6 and wc["other_lead_copies_merged"] == 6, wc


def test_a_false_switch_into_the_group_already_in_force_is_dropped_2026_09_10():
    # the session ends with D active; the next session starts with D. One export logs a switch
    # "A -> D" in between (22:52 on 2026-09-10); no switch out of D was ever logged. The decision-487
    # rule took the switch's old group (A) as in force before it: the readings in between were filed
    # under A's right-lead sensing (R 0-3 7.81 Hz) and flagged.
    sw = T0 + 8 * H
    s1 = _export(T0, T0 + 300, _groups("D"), _groups("D"))
    s2 = _export(T0 + 24 * H, T0 + 24 * H + 300, _groups("D"), _groups("D"), switches=[(sw, "A", "D")])
    U = CS.union([CS.settings_record(e) for e in (s1, s2)])
    assert U["switches"] == [] and U["switches_dropped"] == 1, U["switches"]
    lab, flagged = CS.label_at(U, T0 + 6 * H, "Right")
    assert lab[:2] == ["1-3", 23.44] and not flagged, (lab, flagged)
    # a real switch out of the group in force is kept
    s3 = _export(T0 + 24 * H, T0 + 24 * H + 300, _groups("A"), _groups("A"), switches=[(sw, "D", "A")])
    U2 = CS.union([CS.settings_record(e) for e in (s1, s3)])
    assert len(U2["switches"]) == 1 and U2["switches_dropped"] == 0
    assert CS.label_at(U2, sw + 600, "Right")[0][:2] == ["0-3", 7.81]


def test_the_ingest_reads_the_signal_lead_before_the_decode_deletes_it():
    """`Percept.processTherapySettings` deletes each sensing entry's `ChannelSignalResult` from the
    export in place. The first scratch re-ingest of 2026-10-19 read the settings record after the
    decode, and none of 15,212 entries carried a lead. Pinned: `Session.decodeMedtronicJSON` takes
    the record before the decode touches the export."""
    from modules.MedtronicPercept import Session, Percept
    ex = _export(T0, T0 + 300, _groups("D"), _groups("D"))
    seen = []

    def mutate(JSON):
        for g in JSON["Groups"]["Initial"] + JSON["Groups"]["Final"]:
            for ch in g["ProgramSettings"]["SensingChannel"]:
                ch["SensingSetup"].pop("ChannelSignalResult", None)
        return None                                  # decode "fails": the record was taken before

    saved = (Percept.extractPerceptJSON, CS.settings_record)
    try:
        Percept.extractPerceptJSON = mutate
        CS.settings_record = lambda J: seen.append(saved[1](J)) or seen[-1]
        try:
            Session.decodeMedtronicJSON(ex)
        except Exception:
            pass
    finally:
        Percept.extractPerceptJSON, CS.settings_record = saved
    assert seen, "the settings record was not taken before the decode"
    leads = {v[2] for x in seen[0]["starts"] for g in x[-1].values() for v in g.values() if len(v) > 2}
    assert leads == {"LEFT", "RIGHT"}, seen[0]


def test_a_ganged_entry_names_the_lead_it_is_ganged_to_without_a_signal_result():
    g = _groups("D")
    for grp in g:
        for ch in grp["ProgramSettings"]["SensingChannel"]:
            ch["SensingSetup"].pop("ChannelSignalResult")
            if grp["GroupId"].endswith("GROUP_D") and "Right" in ch["HemisphereLocation"]:
                ch["GangedToHemisphere"] = "HemisphereLocationDef.Left"
    s = _sched([_export(T0, T0 + 300, g, g), _export(T0 + 24 * H, T0 + 24 * H + 300, g, g)])
    assert [x[1] for x in s["RightHemisphere"]["SignalLeadSchedule"]] == ["LEFT"], s["RightHemisphere"]


def test_readings_before_the_first_labelled_record_take_its_label_and_are_listed_as_having_no_record():
    """RCS08's early log (decision 488): a mis-dated history entry (active A, listing sensing for
    group D only) and an event-log switch "D -> A" just after it. The decision-487 rule took the
    switch's old group, D, as in force before it and filed every earlier reading under D's sensing
    (L 0-2 24.41 Hz on RCS08). The switch is false (A was in force), so no record gives those
    readings a label: they take the first real record's label, and the stretch is listed in
    `ScheduleNoRecord`."""
    d_other = ("ZERO_AND_THREE", 24.41, "Left")
    stray = [{"GroupId": "GroupIdDef.GROUP_A", "ActiveGroup": True, "ProgramSettings": {}},
             _group("GROUP_D", False, d_other, d_other)]
    s0 = _export(T0 - 100 * 24 * H, T0 - 100 * 24 * H, stray, stray)
    s0b = _export(T0 - 80 * 24 * H, T0 - 80 * 24 * H, stray, stray)
    del s0["SessionEndDate"], s0b["SessionEndDate"]
    s1 = _export(T0, T0 + 300, _groups("A"), _groups("A"), switches=[(T0 - 90 * 24 * H, "D", "A")])
    s2 = _export(T0 + 24 * H, T0 + 24 * H + 300, _groups("A"), _groups("A"))
    U = CS.union([CS.settings_record(e) for e in (s0, s0b, s1, s2)])
    assert U["switches_dropped"] == 1
    assert CS.label_at(U, T0 - 95 * 24 * H, "Left")[0] is None
    sched = CS.side_schedules(U)["LeftHemisphere"]
    assert sched["ContactSchedule"][0] == [0.0, "1-3"] and sched["FreqScheduleHz"][0] == [0.0, 23.44], sched
    nr = sched["ScheduleNoRecord"]
    assert nr and nr[0][0] == 0.0 and nr[0][1] <= T0, nr
    t = np.asarray([T0 - 95 * 24 * H, T0 + 12 * H])
    rec = _rec("Left", t, [10.0, 20.0], [1.0, 1.0], sched)
    assert R.chronic_pair_keys(rec, t, "LEFT", "X") == ["ONE_THREE_LEFT", "ONE_THREE_LEFT"]
