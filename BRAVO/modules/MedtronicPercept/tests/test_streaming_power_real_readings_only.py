"""Synthetic contracts for actual streaming readings (decision 480).
    Preserve measured power/current and exact reading times. Empty grid positions
    are NaN and missing, never interpolation or a measured zero."""
import numpy as np
import pytest

from modules.MedtronicPercept import Percept, BrainSenseStream

T0 = "2026-01-01T10:00:00Z"
T1 = "2026-01-01T10:00:20Z"
START_TICK = 5_000_700
# tick offsets (ms) of the real readings: on the grid for 3, one late packet (+600 ms), then
# 100 ms off the grid; a gap of two readings (1,500 ms step); a gap of four (2,500 ms step)
OFFSETS_MS = [0, 500, 1000, 1600, 2100, 2600, 4100, 4600, 7100, 7600, 8100]


def _readings(offsets=OFFSETS_MS, left_ma=None):
    out = []
    for i, off in enumerate(offsets):
        out.append({"Left": {"LFP": 1000 + 7 * i + (i % 3), "mA": (left_ma[i] if left_ma else 0.5 + 0.1 * i)},
                    "Right": {"LFP": 2000 + 11 * i, "mA": 2.0 - 0.1 * i},
                    "Seq": i + 1, "TicksInMs": START_TICK + off})
    return out


def _block(offsets=OFFSETS_MS, first=T0, channel="ZERO_THREE_LEFT,ZERO_THREE_RIGHT", therapy=None, left_ma=None):
    return {"FirstPacketDateTime": first, "Channel": channel, "SampleRateInHz": 2,
            "TherapySnapshot": therapy or {"Left": {}, "Right": {}},
            "LfpData": _readings(offsets, left_ma)}


def _real(block):
    return [((p["TicksInMs"] - START_TICK) / 1000.0, p["Left"]["LFP"], p["Left"]["mA"],
             p["Right"]["LFP"], p["Right"]["mA"]) for p in block["LfpData"]]


def _decode(blocks):
    return Percept.extractPowerDomainStreamingData({"BrainSenseLfp": blocks}, dict())["StreamingPower"]


def test_every_stored_present_reading_is_a_real_one_with_its_own_value_current_and_time():
    b = _block()
    s = _decode([b])[0]
    present = np.where(s["Missing"][:, 0] == 0)[0]
    stored = [(float(s["Time"][k]), s["Power"][k, 0], s["Stimulation"][k, 0], s["Power"][k, 1], s["Stimulation"][k, 1])
              for k in present]
    assert sorted(stored) == sorted(_real(b)), (stored, _real(b))
    # none invented: exactly as many present rows as real readings, on both sides
    assert len(present) == len(OFFSETS_MS)
    assert np.array_equal(s["Missing"][:, 0], s["Missing"][:, 1])


def test_an_empty_place_on_the_grid_holds_no_number_and_is_marked_missing():
    s = _decode([_block()])[0]
    empty = s["Missing"][:, 0] == 1
    # gap of two readings (2 places) and of four (4 places)
    assert int(empty.sum()) == 2 + 4, int(empty.sum())
    assert np.all(np.isnan(s["Power"][empty])) and np.all(np.isnan(s["Stimulation"][empty]))
    assert np.all(np.isnan(s["Time"][empty]))
    assert not np.any(np.isnan(s["Power"][~empty])) and not np.any(np.isnan(s["Stimulation"][~empty]))


def test_the_grid_place_is_within_half_a_spacing_of_the_readings_own_time_and_ends_at_the_last_reading():
    s = _decode([_block()])[0]
    rate = s["SamplingRate"]
    k = np.where(s["Missing"][:, 0] == 0)[0]
    err = np.abs(s["Time"][k] - k / rate)
    assert err.max() <= 0.5 / rate + 1e-9, err
    assert abs(err.max() - 0.1) < 1e-9          # the late packet: 100 ms off the grid after it
    assert s["Missing"][-1, 0] == 0              # nothing stored past the last real reading
    assert len(s["Power"]) == int(np.floor(OFFSETS_MS[-1] / 1000.0 * rate + 0.5)) + 1


def test_a_block_with_no_gap_is_stored_as_recorded():
    offs = [500 * i for i in range(8)]
    b = _block(offs)
    s = _decode([b])[0]
    assert s["Missing"].sum() == 0
    assert list(s["Time"]) == [o / 1000.0 for o in offs]
    assert [tuple(r) for r in s["Power"]] == [(p["Left"]["LFP"], p["Right"]["LFP"]) for p in b["LfpData"]]


def test_readings_closer_than_one_spacing_are_all_kept_back_to_back():
    # at a stated 2 readings a second, readings 100 ms apart cannot each have their own grid place:
    # none is dropped or averaged; they are stored as recorded and the block says so
    offs = [100 * i for i in range(6)] + [1500, 1600]
    b = _block(offs)
    s = _decode([b])[0]
    assert s["Missing"].sum() == 0
    assert s.get("SlotLayout") == "as recorded"
    assert list(s["Time"]) == [o / 1000.0 for o in offs]
    assert [tuple(r) for r in s["Stimulation"]] == [(p["Left"]["mA"], p["Right"]["mA"]) for p in b["LfpData"]]


def test_the_saved_recording_carries_only_real_values_currents_and_their_own_times():
    b = _block()
    pw = BrainSenseStream.saveBrainSenseStreams([], _decode([b]), FixBreaking=False)[1]
    assert len(pw) == 1
    R = pw[0]
    assert R["ChannelNames"] == ["ZERO_THREE_LEFT Power", "ZERO_THREE_RIGHT Power",
                                 "ZERO_THREE_LEFT Stimulation", "ZERO_THREE_RIGHT Stimulation"]
    k = np.where(R["Missing"][:, 0] == 0)[0]
    assert np.all(R["Missing"][k] == 0) and np.all(np.delete(R["Missing"], k, axis=0) == 1)
    stored = [(float(R["ReadingTime"][i]), R["Data"][i, 0], R["Data"][i, 2], R["Data"][i, 1], R["Data"][i, 3]) for i in k]
    assert sorted(stored) == sorted(_real(b))
    assert np.all(np.isnan(np.delete(R["Data"], k, axis=0)))
    assert R["Duration"] == R["Data"].shape[0] / R["SamplingRate"]
    # not `Time`: the raw-series handler and the analysis builder take a stored `Time` as their axis
    assert "Time" not in R


def test_one_side_channel_choice_ignores_the_empty_places():
    # a one-side block whose other side reads 0 throughout: the side read is the one with readings,
    # whatever the empty (NaN) places hold
    b = _block(channel="ZERO_THREE_LEFT", therapy={"Left": {}})
    for p in b["LfpData"]:
        p["Right"] = {"LFP": 0, "mA": 0.0}
    R = BrainSenseStream.saveBrainSenseStreams([], _decode([b]), FixBreaking=False)[1][0]
    assert R["ChannelNames"] == ["ZERO_THREE_LEFT Power", "ZERO_THREE_LEFT Stimulation"]
    k = np.where(R["Missing"][:, 0] == 0)[0]
    assert sorted(R["Data"][k, 0].tolist()) == sorted(p["Left"]["LFP"] for p in b["LfpData"])


@pytest.mark.parametrize("amplitude", [0.0, 1.0])
def test_a_joined_recording_keeps_every_reading_at_its_own_time_and_fills_no_number(amplitude):
    therapy = {"Left": {"RateInHertz": 55, "PulseWidthInMicroSecond": 60,
                        "LowerLimitInMilliAmps": 0.5, "UpperLimitInMilliAmps": 4.5}}
    ma = [amplitude] * len(OFFSETS_MS)
    b0 = _block(first=T0, channel="ZERO_THREE_LEFT", therapy=therapy, left_ma=ma)
    b1 = _block(first=T1, channel="ZERO_THREE_LEFT", therapy=therapy, left_ma=ma)
    for blk in (b0, b1):
        for p in blk["LfpData"]:
            p["Right"] = {"LFP": 0, "mA": 0.0}
    td0 = _td(T0)
    td1 = _td(T1)
    D = dict()
    Percept.extractTimeDomainStreamingData({"BrainSenseTimeDomain": [td0, td1]}, D)
    pw = BrainSenseStream.saveBrainSenseStreams(D["StreamingTD"], _decode([b0, b1]), FixBreaking=True)[1]
    assert len(pw) == 1
    R = pw[0]
    k = np.where(R["Missing"][:, 0] == 0)[0]
    assert len(k) == 2 * len(OFFSETS_MS)
    assert np.all(np.isnan(np.delete(R["Data"], k, axis=0)))
    t = R["ReadingTime"][k]
    own = [o / 1000.0 for o in OFFSETS_MS] + [20.0 + o / 1000.0 for o in OFFSETS_MS]
    assert np.allclose(sorted(t), own), (t, own)
    assert np.abs(t - k / R["SamplingRate"]).max() <= 0.5 / R["SamplingRate"] + 1e-9


def _td(first, n_packets=20):
    sizes = [62 + (i % 2) for i in range(n_packets)]
    return {"FirstPacketDateTime": first, "Channel": "ZERO_THREE_LEFT", "Pass": "FIRST", "Gain": 250,
            "GlobalSequences": ",".join(str(i + 1) for i in range(n_packets)),
            "GlobalPacketSizes": ",".join(str(s) for s in sizes),
            "TicksInMses": ",".join(str(START_TICK + 250 * i) for i in range(n_packets)),
            "TimeDomainData": [float(i % 7) for i in range(sum(sizes))], "SampleRateInHz": 250}


def _stored_with_gap():
    # a saved one-side recording: 12 places at 2 a second, places 4-7 empty (NaN, marked missing);
    # the current steps 1.0 -> 2.0 mA across the gap
    n = 12
    real = np.ones(n, bool)
    real[4:8] = False
    data = np.column_stack([100.0 + np.arange(n), np.where(np.arange(n) < 8, 1.0, 2.0)])
    data[~real] = np.nan
    missing = np.zeros((n, 2))
    missing[~real] = 1
    therapy = {"Left": {"RateInHertz": 55, "PulseWidthInMicroSecond": 60,
                        "SensingChannel": "SensingChannelDef.ZERO_THREE_LEFT"}}
    return {"ChannelNames": ["ZERO_THREE_LEFT Power", "ZERO_THREE_LEFT Stimulation"], "Data": data,
            "Missing": missing, "SamplingRate": 2.0, "StartTime": 1_760_000_000.0,
            "Descriptor": {"Therapy": therapy}}, real


def test_the_therapy_labels_see_the_change_of_current_across_a_gap_and_no_empty_place():
    rec, real = _stored_with_gap()
    device = {"GenericName": "Percept", "Electrodes": [{"Target": "Left GPi", "CustomName": "Left"}]}
    series, graph = BrainSenseStream.processTherapyInformation(rec, device)
    amps = [v["Amplitude"] for s in series for v in s["TherapyOverview"].values()]
    assert all(np.isfinite(amps)), amps
    assert amps[0] == 1.0 and 2.0 in amps, amps
    series = BrainSenseStream.extractPowerBands(rec, series)
    for s in series[:-1]:
        v = np.asarray(s.get("ZERO_THREE_LEFT Power", []), dtype=float)
        assert np.all(np.isfinite(v))


def test_saved_close_readings_preserve_slot_layout_and_actual_offsets():
    b = _block([100 * i for i in range(8)])
    R = BrainSenseStream.saveBrainSenseStreams([], _decode([b]), FixBreaking=False)[1][0]
    assert R["SlotLayout"] == "as recorded"
    assert np.allclose(R["ReadingTime"], np.arange(8) / 10)


def test_native_therapy_and_power_views_use_reading_times_instead_of_grid_positions():
    rec, _ = _stored_with_gap()
    rec["ReadingTime"] = np.array([0.0, 0.1, 0.2, 0.3, np.nan, np.nan, np.nan, np.nan,
                                  10.0, 11.0, 12.0, 13.0])
    device = {"GenericName": "Percept", "Electrodes": [{"Target": "Left GPi", "CustomName": "Left"}]}
    series, _ = BrainSenseStream.processTherapyInformation(rec, device)
    assert series[1]["Time"] == rec["StartTime"] + 10.0
    windows = [{"Time": rec["StartTime"] + 6.0}, {"Time": rec["StartTime"] + 17.0}]
    got = BrainSenseStream.extractPowerBands(rec, windows)
    assert list(got[0]["ZERO_THREE_LEFT Power"]) == [108.0, 109.0, 110.0, 111.0]


def test_present_reading_time_missing_position_is_not_replaced_by_legacy_grid():
    rec, _ = _stored_with_gap()
    rec["ReadingTime"] = np.full(len(rec["Data"]), np.nan)
    device = {"GenericName": "Percept", "Electrodes": [{"Target": "Left GPi", "CustomName": "Left"}]}
    series, _ = BrainSenseStream.processTherapyInformation(rec, device)
    assert series == []


def test_missing_row_mask_is_optional_but_nonfinite_values_still_excluded():
    record = {"Data": np.array([[1.0], [np.nan], [2.0]])}
    assert list(BrainSenseStream._real_rows(record, 0)) == [True, False, True]
    record["Missing"] = np.zeros(1)
    with pytest.raises(ValueError):
        BrainSenseStream._real_rows(record, 0)


def test_invalid_measured_times_are_never_silently_replaced_by_grid():
    import pytest
    rec, _ = _stored_with_gap()
    for invalid in ([0], np.full(12, np.inf), np.arange(12)[::-1], "malformed"):
        rec["ReadingTime"] = invalid
        with pytest.raises(ValueError):
            BrainSenseStream._reading_times(rec)


@pytest.mark.parametrize("bad_mask", [None, [0], "malformed", [["not numeric"]] * 12,
    np.full((12, 2), np.nan), np.full((12, 2), 2)])
def test_native_readers_reject_present_malformed_missing_masks(bad_mask):
    rec, _ = _stored_with_gap()
    rec["Missing"] = bad_mask
    device = {"GenericName": "Percept", "Electrodes": [{"Target": "Left GPi", "CustomName": "Left"}]}
    with pytest.raises(ValueError):
        BrainSenseStream.processTherapyInformation(rec, device)
    with pytest.raises(ValueError):
        BrainSenseStream.extractPowerBands(rec, [{"Time": 0}, {"Time": 1}])
