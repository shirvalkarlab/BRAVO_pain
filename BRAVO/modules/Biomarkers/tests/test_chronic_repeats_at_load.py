"""The chronic log reaches every Biomarkers reader with each reading once (the PI, 2026-10-18,
item 6a/6b). The loader every chronic reader goes through (`_load_recordings_uncached`: the
sign-off threshold, the stimulation series, the band-power timeline, the all-band scan's power
source) merges the repeated copies each export carries, after the implant-date cut. Plain
asserts: this file runs in the container suite.
"""
import types

import numpy as np

from modules.Biomarkers import bravo_service as BS
from modules.Biomarkers import adapter as AD

T0 = 1_760_000_000.0
CH = "MedtronicChronicBrainSense"


def _chronic(t, lfp, side="Left"):
    t = np.asarray(t, dtype=float)
    return {"RecordingType": CH, "Time": t, "SamplingRate": -1, "CenterFrequencyHz": 23.44,
            "ChannelNames": [f"{side}Hemisphere LFP", f"{side}Hemisphere Amplitude"],
            "Data": np.column_stack([np.asarray(lfp, float), np.full(t.size, 2.0)])}


def test_the_loader_merges_chronic_repeats_and_leaves_other_recordings_alone():
    t = T0 + 600.0 * np.arange(5)
    a = _chronic(t[:3], [1, 2, 3]); b = _chronic(t, [1, 2, 3, 4, 71583000.0])
    stream = {"RecordingType": "MedtronicBrainSenseTimeDomain", "Time": t.copy(), "Data": np.zeros((5, 1))}
    out = BS._merge_chronic_repeats([a, stream, b])
    assert len(out) == 3 and out[1] is stream
    total = sum(len(r["Time"]) for r in out if r.get("RecordingType") == CH)
    assert total == 5, total
    vals = sorted(v for r in out if r.get("RecordingType") == CH for v in np.asarray(r["Data"])[:, 0])
    assert vals[:4] == [1.0, 2.0, 3.0, 4.0] and np.isnan(vals[4]), vals


def test_load_recordings_uncached_applies_the_merge_after_the_implant_cut():
    t = T0 + 600.0 * np.arange(4)
    decoded = [_chronic(t, [5, 6, 7, 8]), _chronic(t, [5, 6, 7, 8]), _chronic(t, [5, 6, 7, 8], side="Right")]
    fake = types.SimpleNamespace(
        Participant=types.SimpleNamespace(find=lambda **k: object()),
        SourceFile=types.SimpleNamespace(find_all=lambda **k: ["src"]),
        Recording=types.SimpleNamespace(find_all=lambda **k: ["r1", "r2", "r3"]))
    saved = (BS.models, BS._decoded_with_row_labels, BS._data_start.data_start_s)
    try:
        BS.models = fake
        BS._decoded_with_row_labels = lambda uid, recs: [dict(d) for d in decoded]
        BS._data_start.data_start_s = lambda uid: T0 + 1.0       # the first reading is before it
        out = BS._load_recordings_uncached("uid", BS.CHRONIC_TYPES)
    finally:
        BS.models, BS._decoded_with_row_labels, BS._data_start.data_start_s = saved
    left = sorted(float(x) for r in out if "Left" in r["ChannelNames"][0] for x in r["Time"])
    right = sorted(float(x) for r in out if "Right" in r["ChannelNames"][0] for x in r["Time"])
    assert left == list(t[1:]) and right == list(t[1:]), (left, right)


def test_concat_chronic_hands_each_chronic_reading_on_once():
    """The all-band scan's power source joins the chronic recordings in `_concat_chronic`; a
    caller that hands it unmerged copies (the command-line pipeline) gets each reading once too.
    Streaming band power converted to the same shape is not touched."""
    t = T0 + 600.0 * np.arange(6)
    a = _chronic(t[:4], [10, 20, 30, 40]); b = _chronic(t, [10, 20, 30, 40, 50, 60])
    a["Source"] = b["Source"] = "chronic"
    pd_like = {"Source": "powerdomain", "SamplingRate": -1, "ChannelNames": ["L 0⁻3⁺", "L Stim"],
               "Time": t[:2].copy(), "Data": np.array([[10.0, 2.0], [20.0, 2.0]])}
    out = AD._concat_chronic([a, b, pd_like], mad_k=0)
    assert len(out["Time"]) == 6 + 2, len(out["Time"])
    assert sorted(out["Data"][out["Source"] == "chronic", 0].tolist()) == [10, 20, 30, 40, 50, 60]


def test_the_saved_timeline_is_filed_under_the_new_rule():
    """The saved acquisition timeline (its stimulation row and band-power lines read the chronic
    log) is filed under the recording set, which the merge does not change; the rule version
    moves so the old timeline, every repeat counted, is not served."""
    # v6 was this change's own version; any later rule (v7, 2026-10-27: the band labeller's table to
    # 125 Hz) keeps the timeline that counted every repeat out of reach as well
    assert int(BS._ACQ_TIMELINE_RULE_VERSION[1:].split("_")[0]) >= 6


def test_the_loader_carries_the_signal_lead_and_files_a_copy_under_its_lead():
    """Decision 488: the lead each chronic reading's signal came from is written on the database
    row (`SignalLeadSchedule`, chronic_schedule.py); the loader must put it on the decoded
    recording, or the merge never sees it and the copy stays under the wrong lead (it did, on the
    first scratch run of 2026-10-19: 0 copies merged)."""
    t = T0 + 600.0 * np.arange(3)
    left, right = _chronic(t, [300, 301, 302]), _chronic(t, [300, 301, 302], side="Right")
    sched = [[0.0, "1-3"]]
    rows = [types.SimpleNamespace(uid="L", type=CH, metadata={"ContactSchedule": sched, "SignalLeadSchedule": [[0.0, "LEFT"]]}),
            types.SimpleNamespace(uid="R", type=CH, metadata={"ContactSchedule": sched, "SignalLeadSchedule": [[0.0, "LEFT"]]})]
    saved = BS._decoded_payloads
    try:
        BS._decoded_payloads = lambda uid, recs: {"L": [dict(left)], "R": [dict(right)]}
        got = BS._decoded_with_row_labels("P", rows)
    finally:
        BS._decoded_payloads = saved
    assert all(d.get("SignalLeadSchedule") == [[0.0, "LEFT"]] for d in got), got
    out = BS._merge_chronic_repeats(got)
    sides = sorted(r["ChannelNames"][0].split(" ")[0] for r in out for _ in r["Time"])
    assert sides == ["LeftHemisphere"] * 3, sides


def test_each_lead_keeps_its_own_current_after_a_copy_is_merged():
    """Decision 488, the PI's ruling that each side's current stays its own: after the merge files
    the right lead's copy of the left lead's signal under the left lead, the right lead's
    stimulation current at those times must still be in the right lead's series (read from
    `OtherLeadCurrentMilliAmps`), and the left lead's series must hold only its own. The pooled
    series holds both, as before the merge."""
    from modules.Biomarkers.routines import availability as AV
    t = T0 + 600.0 * np.arange(4)
    left, right = _chronic(t, [300, 301, 302, 303]), _chronic(t, [300, 301, 302, 303], side="Right")
    right["Data"][:, 1] = 2.5                                   # the right lead's own current
    for r in (left, right):
        r["ContactSchedule"] = [[0.0, "1-3"]]
        r["SignalLeadSchedule"] = [[0.0, "LEFT"]]
    before = {s: AV.stim_series([left, right], hemisphere=s) for s in ("Left", "Right")}
    before[None] = AV.stim_series([left, right])
    out = BS._merge_chronic_repeats([left, right])
    assert sum(len(r["Time"]) for r in out) == 4                # one reading per time, under the left lead
    for s in ("Left", "Right", None):
        got = AV.stim_series(out, hemisphere=s)
        assert got["t"] == before[s]["t"] and sorted(got["y"]) == sorted(before[s]["y"]), (s, got, before[s])
    assert AV.stim_series(out, hemisphere="Right")["y"] == [2.5] * 4
    # a reading moved to its signal's lead keeps its current on the lead whose log held it
    moved = dict(_chronic(t[:1], [400]), MovedFromLead="RIGHT")
    moved["Data"][:, 1] = 2.5
    assert AV.stim_series([moved], hemisphere="Right")["y"] == [2.5]
    assert AV.stim_series([moved], hemisphere="Left")["y"] == []
