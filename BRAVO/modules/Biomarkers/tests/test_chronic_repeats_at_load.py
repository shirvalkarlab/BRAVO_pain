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
    assert BS._ACQ_TIMELINE_RULE_VERSION.startswith("v6_chronic_readings_once")
