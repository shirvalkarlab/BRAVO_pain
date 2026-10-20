"""Synthetic chronic repeats, conflicts and upstream analysis exclusions."""
import sys
import pathlib

import numpy as np

_BRAVO_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(_BRAVO_ROOT) not in sys.path:
    sys.path.insert(0, str(_BRAVO_ROOT))

from DecodeCommon import representation as R

T0 = 1_760_000_000.0


def _rec(t, lfp, amp, side="Left", sched=None, contacts=None, center=None):
    t = np.asarray(t, dtype=float)
    rec = {"ChannelNames": [f"{side}Hemisphere LFP", f"{side}Hemisphere Amplitude"],
           "Data": np.column_stack([np.asarray(lfp, float), np.asarray(amp, float)]),
           "Time": t, "SamplingRate": -1, "RecordingType": "MedtronicChronicBrainSense"}
    if sched is not None:
        rec["FreqScheduleHz"] = sched
    if contacts is not None:
        rec["ContactSchedule"] = contacts
    if center is not None:
        rec["CenterFrequencyHz"] = center
    return rec


def _samples(recs):
    """Every (side, time, band power, current) handed on, as a sorted list (NaN as a string)."""
    out = []
    for r in recs:
        side = "L" if "Left" in r["ChannelNames"][0] else "R"
        for t, row in zip(np.asarray(r["Time"]), np.asarray(r["Data"])):
            out.append((side, float(t)) + tuple("nan" if not np.isfinite(v) else float(v) for v in row))
    return sorted(out)


def test_a_reading_held_by_three_exports_is_handed_on_once():
    t = T0 + 600.0 * np.arange(10)
    lfp = 100.0 + np.arange(10); amp = np.full(10, 2.0)
    a = _rec(t[:6], lfp[:6], amp[:6], center=23.44)
    b = _rec(t[:8], lfp[:8], amp[:8], center=23.44)
    c = _rec(t, lfp, amp, center=23.44)
    out, counts = R.merge_chronic_repeats([a, b, c])
    got = _samples(out)
    assert len(got) == 10, len(got)
    assert got == _samples([c]), got
    assert counts["repeats_removed"] == 6 + 8, counts
    assert counts["conflicting_kept"] == 0, counts
    assert len(out) == 3                                 # every recording kept, with its settings


def test_the_two_sides_at_one_time_are_two_readings():
    t = T0 + 600.0 * np.arange(4)
    left = _rec(t, [5, 6, 7, 8], [1, 1, 1, 1], side="Left", center=23.44)
    right = _rec(t, [5, 6, 7, 8], [1, 1, 1, 1], side="Right", center=23.44)
    out, counts = R.merge_chronic_repeats([left, right])
    assert len(_samples(out)) == 8 and counts["repeats_removed"] == 0, counts


def test_copies_that_differ_in_value_are_both_kept_and_counted():
    t = T0 + 600.0 * np.arange(3)
    a = _rec(t, [10, 20, 30], [1, 1, 1], center=23.44)
    b = _rec(t, [10, 21, 30], [1, 1, 1], center=23.44)
    out, counts = R.merge_chronic_repeats([a, b])
    got = _samples(out)
    assert len(got) == 4, got                            # 10, 20, 21, 30
    assert ("L", T0 + 600.0, 20.0, 1.0) in got and ("L", T0 + 600.0, 21.0, 1.0) in got
    assert counts["conflicting_kept"] == 1 and counts["repeats_removed"] == 2, counts


def test_copies_filed_under_different_bands_or_pairs_are_not_merged():
    """Two exports whose own settings history put one reading on different bands (or contact
    pairs) are not collapsed: which one is right is not decided here, and both are counted."""
    t = T0 + 600.0 * np.arange(3)
    a = _rec(t, [10, 20, 30], [1, 1, 1], sched=[[T0 - 1, 24.41]], contacts=[[T0 - 1, "1-3"]])
    b = _rec(t, [10, 20, 30], [1, 1, 1], sched=[[T0 - 1, 26.37]], contacts=[[T0 - 1, "0-3"]])
    out, counts = R.merge_chronic_repeats([a, b])
    assert len(_samples(out)) == 6 and counts["repeats_removed"] == 0, counts
    assert counts["readings_under_two_labels"] == 3, counts


def test_the_answer_does_not_depend_on_the_order_the_exports_arrive():
    rng = np.random.default_rng(3)
    recs = []
    base = T0 + 600.0 * np.arange(40)
    lfp = rng.uniform(50, 900, 40); amp = rng.choice([0.0, 1.5, 3.0], 40)
    for lo, hi in [(0, 20), (5, 30), (10, 40), (0, 40), (25, 40)]:
        recs.append(_rec(base[lo:hi], lfp[lo:hi], amp[lo:hi], sched=[[T0 - 1, 23.44], [T0 + 9000, 24.41]],
                         contacts=[[T0 - 1, "1-3"]]))
    want, wc = R.merge_chronic_repeats(recs)
    for seed in range(6):
        order = np.random.default_rng(seed).permutation(len(recs))
        got, gc = R.merge_chronic_repeats([recs[i] for i in order])
        assert _samples(got) == _samples(want), seed
        assert gc == wc, (gc, wc)
        # the same recording holds the same samples, whatever the order (content, not position)
        held = sorted((float(np.asarray(r["Time"])[0]) if len(r["Time"]) else -1.0, len(r["Time"])) for r in got)
        assert held == sorted((float(np.asarray(r["Time"])[0]) if len(r["Time"]) else -1.0, len(r["Time"]))
                              for r in want)


def test_the_invalid_code_averaged_into_a_reading_is_blanked_and_its_current_kept():
    # Synthetic values straddle the upstream threshold; no participant samples.
    t = T0 + 600.0 * np.arange(4)
    rec = _rec(t, [120.0, R.CHRONIC_INVALID_LSB + 50, 30000.0, R.CHRONIC_INVALID_LSB + 500], [2.0, 2.5, 3.0, 3.5], center=23.44)
    out, counts = R.merge_chronic_repeats([rec])
    d = np.asarray(out[0]["Data"])
    assert np.isnan(d[1, 0]) and np.isnan(d[3, 0]), d
    assert d[0, 0] == 120.0 and d[2, 0] == 30000.0, d
    assert list(d[:, 1]) == [2.0, 2.5, 3.0, 3.5]          # the current at that time is real
    assert counts["invalid_code_values"] == 2, counts
    assert R.CHRONIC_INVALID_LSB == (2 ** 32 - 1) / 60.0
    # and the device's own band-power series no longer carries them
    nat = R.native_lsb_by_channel(out, [])
    ys = [y for v in nat.values() for y in v["y"]]
    assert sorted(ys) == [120.0, 30000.0], ys


def test_exact_zero_readings_are_not_readings_and_their_current_is_kept():
    """Exact zero exclusion is the upstream policy; raw current remains measured."""
    t = T0 + 600.0 * np.arange(3)
    out, counts = R.merge_chronic_repeats([_rec(t, [0.0, 0.0, 5.0], [1, 1.5, 2], center=23.44)])
    d = np.asarray(out[0]["Data"])
    assert np.isnan(d[0, 0]) and np.isnan(d[1, 0]) and d[2, 0] == 5.0, d
    assert list(d[:, 1]) == [1.0, 1.5, 2.0]
    assert counts["zero_values"] == 2 and counts["invalid_code_values"] == 0, counts
    ys = [y for v in R.native_lsb_by_channel(out, []).values() for y in v["y"]]
    assert ys == [5.0], ys


def test_a_zero_repeated_in_two_exports_is_counted_once():
    t = T0 + 600.0 * np.arange(2)
    a = _rec(t, [0.0, 7.0], [1, 1], center=23.44)
    b = _rec(t, [0.0, 7.0], [1, 1], center=23.44)
    out, counts = R.merge_chronic_repeats([a, b])
    assert counts["zero_values"] == 1 and counts["repeats_removed"] == 2, counts


def test_inputs_are_not_changed_and_a_second_merge_changes_nothing():
    t = T0 + 600.0 * np.arange(5)
    a = _rec(t, [1, 2, 3, R.CHRONIC_INVALID_LSB + 20, 5], [1] * 5, center=23.44)
    b = _rec(t, [1, 2, 3, R.CHRONIC_INVALID_LSB + 20, 5], [1] * 5, center=23.44)
    before = (np.array(a["Data"]).copy(), np.array(a["Time"]).copy())
    once, c1 = R.merge_chronic_repeats([a, b])
    assert np.array_equal(a["Data"], before[0]) and np.array_equal(a["Time"], before[1])
    twice, c2 = R.merge_chronic_repeats(once)
    assert _samples(twice) == _samples(once)
    assert c2["repeats_removed"] == 0 and c2["invalid_code_values"] == 0, c2
    assert c1["repeats_removed"] == 5 and c1["invalid_code_values"] == 1, c1


def test_every_per_sample_array_is_cut_with_the_samples():
    t = T0 + 600.0 * np.arange(4)
    a = _rec(t, [1, 2, 3, 4], [1] * 4, center=23.44)
    b = _rec(t, [1, 2, 3, 4], [1] * 4, center=23.44)
    b["Extra"] = np.arange(4.0)
    out, _ = R.merge_chronic_repeats([a, b])
    for r in out:
        n = len(r["Time"])
        assert np.asarray(r["Data"]).shape[0] == n
        if "Extra" in r:
            assert len(r["Extra"]) == n
        assert r["ChannelNames"] == a["ChannelNames"]


def test_schedule_lists_are_not_sample_arrays_when_lengths_coincide():
    a = _rec([10, 20], [5, 6], [1, 1])
    b = _rec([10, 20], [5, 6], [1, 1])
    for r in (a, b):
        r['ScheduleNoRecord'] = [[0, 1], [15, None]]
        r['ScheduleFlagged'] = [[2, 3], [4, 5]]
        r['ContactSchedule'] = [[0, '1-3'], [15, '1-3']]
        r['FreqScheduleHz'] = [[0, 20], [15, 20]]
        r['SignalLeadSchedule'] = [[0, 'LEFT'], [15, 'LEFT']]
    out, _ = R.merge_chronic_repeats([a,b])
    for r in out:
        for key in ('ScheduleNoRecord', 'ScheduleFlagged', 'ContactSchedule', 'FreqScheduleHz', 'SignalLeadSchedule'):
            assert r[key] == a[key]


def test_same_power_distinct_other_lead_currents_preserve_ambiguity():
    own = _rec([10], [20], [1], side='Left', center=20)
    copies = [_rec([10], [20], [current], side='Right', center=20) for current in (2, 3, 2)]
    for r in copies: r['SignalLeadSchedule'] = [[0, 'LEFT']]
    for recs in ([own, *copies], [*reversed(copies), own]):
        out, counts = R.merge_chronic_repeats(recs)
        active = [r for r in out if len(r['Time'])]
        assert len(active) == 1
        assert active[0]['OtherLeadCurrentValuesMilliAmps'] == [[2,3]]
        assert active[0]['OtherLeadCurrentAmbiguous'].tolist() == [True]
        assert np.isnan(active[0]['OtherLeadCurrentMilliAmps'][0])
        assert active[0]['Data'].tolist() == [[20,1]]
        assert counts['other_lead_copies_merged'] == 2
        twice, _ = R.merge_chronic_repeats(out)
        assert [r for r in twice if len(r['Time'])][0]['OtherLeadCurrentValuesMilliAmps'] == [[2,3]]


def test_moved_only_power_preserves_all_logged_currents_but_no_target_current():
    recs = [_rec([10], [20], [current], side='Right', center=20) for current in (2,3,2)]
    for r in recs: r['SignalLeadSchedule'] = [[0, 'LEFT']]
    for inputs in (recs, list(reversed(recs))):
        out, _ = R.merge_chronic_repeats(inputs)
        active = [r for r in out if len(r['Time'])]
        assert len(active) == 1
        r = active[0]
        assert r['Data'][0,0] == 20 and np.isnan(r['Data'][0,1])
        assert r['MovedFromLead'] == 'RIGHT'
        assert r['OtherLeadCurrentValuesMilliAmps'] == [[2,3]]
        assert r['OtherLeadCurrentAmbiguous'].tolist() == [True]
        second, _ = R.merge_chronic_repeats(out)
        reread = [r for r in second if len(r['Time'])]
        assert len(reread) == 1
        assert reread[0]['OtherLeadCurrentValuesMilliAmps'] == [[2,3]]
        assert np.isnan(reread[0]['Data'][0,1])


def test_malformed_records_do_not_abort_other_valid_readings():
    invalid = [None, {}, {'Time': [1]}, {'Time': [1], 'Data': [1]},
               {'Time':[1,2], 'Data':[[1,2]]}, {'Time':[1], 'Data':[[]]},
               {'Time': 1, 'Data': [[1,2]]}]
    out, counts = R.merge_chronic_repeats(invalid)
    assert out == invalid and counts['repeats_removed'] == 0
    assert R.merge_chronic_repeats(None)[0] == []


def test_band_and_lead_schedule_fallbacks():
    assert R.chronic_band_tags({'FreqScheduleHz': [None, [], ['bad', 10], [0,None]]}, [1], 'LEFT') == [None]
    for hemi in ('LEFT','RIGHT'):
        assert R.chronic_band_tags({'Descriptor': {'Therapy': {}}}, [1], hemi) == [None]
    assert R.chronic_band_tags({}, [1], '') == [None]
    assert R.chronic_signal_leads({'SignalLeadSchedule': [None, [], ['bad','LEFT'], [0,'UNKNOWN']]}, [1], 'LEFT') == ['LEFT']
    assert R.chronic_signal_leads(None, [1], '') == ['']
    assert R.chronic_signal_leads({'SignalLeadSchedule': [[0,'LEFT']]}, [1], 'unknown') == ['unknown']


def test_no_current_column_and_equal_currents():
    own = _rec([10], [20], [1], side='Left')
    copy = _rec([10], [20], [1], side='Right')
    copy['SignalLeadSchedule'] = [[0,'LEFT']]
    out, counts = R.merge_chronic_repeats([own,copy])
    assert counts['other_lead_current_differs'] == 0
    for r in (own,copy): r['Data'] = r['Data'][:,:1]
    out, _ = R.merge_chronic_repeats([own,copy])
    assert sum(len(r['Time']) for r in out) == 1
    out, _ = R.merge_chronic_repeats([copy])
    assert sum(len(r['Time']) for r in out) == 1
    assert out[-1]['Data'].shape == (1,1)


def test_existing_other_current_evidence_and_nan_duplicates():
    own = _rec([10], [20], [1], side='Left')
    own['OtherLeadCurrentValuesMilliAmps'] = [[2]]
    copy = _rec([10], [20], [2], side='Right')
    copy['SignalLeadSchedule'] = [[0,'LEFT']]
    out, _ = R.merge_chronic_repeats([own,copy])
    assert out[0]['OtherLeadCurrentValuesMilliAmps'] == [[2]]
    a = _rec([10], [20], [np.nan], side='Left')
    b = _rec([10], [20], [np.nan], side='Left')
    out, counts = R.merge_chronic_repeats([a,b])
    assert sum(len(r['Time']) for r in out) == 1 and counts['repeats_removed'] == 1
    # Distinct ancillary columns retain provenance without duplicating one current.
    own = _rec([10], [20], [1], side='Left')
    copies = [_rec([10], [20], [2], side='Right') for _ in range(2)]
    for i,r in enumerate(copies):
        r['SignalLeadSchedule'] = [[0,'LEFT']]
        r['Data'] = np.column_stack((r['Data'], [i]))
    out, _ = R.merge_chronic_repeats([own,*copies])
    assert out[0]['OtherLeadCurrentValuesMilliAmps'] == [[2]]
