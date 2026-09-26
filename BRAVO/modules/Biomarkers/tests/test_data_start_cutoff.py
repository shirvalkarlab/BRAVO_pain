"""Nothing dated before the implant date reaches a Biomarkers product (the PI, 2026-09-24).

RCS08's device record gives 2025-07-16 18:06 UTC; the database also held a chronic log and
patient events from 2025-06-18 (both leads reading the same power, about a tenth of the level after
implant) and a settings stream opening with four January-April 2025 snapshots. Plain asserts: this
file runs in the container suite.
"""
import numpy as np

from modules.Biomarkers import bravo_service as BS
from modules.Biomarkers.routines import stim_current as SC

IMPLANT = 1752689160.0
DAY = 86400.0


def test_chronic_samples_before_implant_are_cut_and_a_file_spanning_it_keeps_its_later_part():
    t = IMPLANT + DAY * np.array([-28.0, -1.0, 0.5, 3.0])
    spanning = {"RecordingType": "MedtronicChronicBrainSense", "Time": t.copy(),
                "Data": np.arange(8.0).reshape(4, 2), "ChannelNames": ["L", "R"]}
    before_only = {"RecordingType": "MedtronicChronicBrainSense", "Time": t[:2].copy(),
                   "Data": np.zeros((2, 2)), "ChannelNames": ["L", "R"]}
    stream = {"RecordingType": "MedtronicBrainSenseTimeDomain", "Time": t.copy()}
    out = BS._trim_chronic_before([spanning, before_only, stream], IMPLANT)
    assert len(out) == 2                                     # the all-bench file is gone
    assert list(out[0]["Time"]) == list(t[2:])
    assert out[0]["Data"].tolist() == [[4.0, 5.0], [6.0, 7.0]]
    assert out[0]["ChannelNames"] == ["L", "R"]
    assert list(out[1]["Time"]) == list(t)                   # not a chronic log: untouched


def test_no_implant_date_trims_nothing():
    d = {"RecordingType": "MedtronicChronicBrainSense", "Time": np.array([1.0, 2.0]),
         "Data": np.zeros((2, 2))}
    assert BS._trim_chronic_before([d], 0.0)[0]["Time"].tolist() == [1.0, 2.0]


def test_the_recording_set_label_moves_with_the_start_so_every_memo_rebuilds():
    ident = [("a", "h1", "MedtronicChronicBrainSense")]
    assert BS._identity_digest(ident, IMPLANT) != BS._identity_digest(ident, 0.0)
    assert BS._identity_digest(ident, IMPLANT) == BS._identity_digest(list(ident), IMPLANT)


def test_the_current_reader_starts_at_implant_with_the_setting_then_in_force():
    s = {"t_s": np.array([IMPLANT - 179 * DAY, IMPLANT - 89 * DAY, IMPLANT - 89 * DAY, IMPLANT + 2 * DAY,
                          IMPLANT - 89 * DAY, IMPLANT + 2 * DAY]),
         "hemi": np.array(["Left", "Left", "Left", "Left", "Right", "Right"], dtype=object),
         "amp_mA": np.array([2.9, 2.9, 2.9, 0.0, 3.1, 0.0]), "store_key": None, "n_rows": 6}
    out = SC.from_data_start(s, IMPLANT)
    left = out["hemi"] == "Left"
    assert out["t_s"][left].tolist() == [IMPLANT, IMPLANT, IMPLANT + 2 * DAY]
    assert out["amp_mA"][left].tolist() == [2.9, 2.9, 0.0]
    right = out["hemi"] == "Right"
    assert out["t_s"][right].tolist() == [IMPLANT, IMPLANT + 2 * DAY]
    # between implant and the first change, the current is the setting then in force, not unknown
    assert SC.current_in_force_at([IMPLANT + DAY], out, hemisphere="Left").tolist() == [2.9]
    assert SC.current_in_force_at([IMPLANT - DAY], out, hemisphere="Left")[0] != SC.current_in_force_at(
        [IMPLANT - DAY], out, hemisphere="Left")[0]          # NaN: before implant is unknown


def test_a_chronic_file_spanning_the_implant_is_dated_from_the_implant_not_its_own_start():
    """Decision 313. The trim cut the samples but left the file's own start and length, so the
    acquisition timeline (which dates a chronic record by `StartTime` and `Duration`) drew RCS08's
    two spanning chronic files from 2025-06-18 and opened its subtitle there. A spanning file is
    dated from the implant date, as the recordings list does (decision 263); its end is unchanged."""
    start = IMPLANT - 28 * DAY
    t = IMPLANT + DAY * np.array([-28.0, -1.0, 0.5, 3.0])
    spanning = {"RecordingType": "MedtronicChronicBrainSense", "Time": t.copy(),
                "Data": np.arange(8.0).reshape(4, 2), "ChannelNames": ["L", "R"],
                "StartTime": start, "Duration": 3.0 * DAY + 28 * DAY}
    after = {"RecordingType": "MedtronicChronicBrainSense", "Time": t[2:].copy(),
             "Data": np.zeros((2, 2)), "ChannelNames": ["L", "R"],
             "StartTime": IMPLANT + 0.5 * DAY, "Duration": 2.5 * DAY}
    out = BS._trim_chronic_before([spanning, after], IMPLANT)
    assert out[0]["StartTime"] == IMPLANT
    assert out[0]["StartTime"] + out[0]["Duration"] == start + 31.0 * DAY   # the end is where it was
    assert out[1]["StartTime"] == IMPLANT + 0.5 * DAY and out[1]["Duration"] == 2.5 * DAY
    from modules.Biomarkers.routines import availability as AV
    recs = AV.extract_availability({"MedtronicChronicBrainSense": out})
    assert recs and min(r["t_start"] for r in recs) >= IMPLANT
