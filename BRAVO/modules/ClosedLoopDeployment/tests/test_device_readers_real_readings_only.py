"""The Closed-Loop page's readers of the device's streamed band power and current take only the
readings the device made (the PI, 2026-10-18; decision 480 (e)).

From that day the stored streaming band-power recording keeps each real reading at its place on
the stated-rate grid, and a place with no reading holds NaN and is marked missing. Before it, those
places held straight-line interpolated power and current, and these readers used them as samples
(they never read the missing marks). Pinned here, on a recording with a gap:
- the band-power reader returns only the real readings, with their power, current and grid times;
- the current reader returns only the real readings, so a gap is not a change of current;
- the run finder sees one change of current, not one at every empty place;
- a stored recording from before the change (interpolated values marked missing) gives the same
  real readings.
"""
import numpy as np

from ClosedLoopDeployment import three_source_response as TSR

T0 = 1_760_000_000.0
FS = 2.0


def _recording(old_style=False):
    # 12 places at 2 a second; places 4-7 hold no reading. Left steps 1.0 -> 2.0 mA after the gap;
    # right stays at 0.
    n = 12
    real = np.ones(n, bool)
    real[4:8] = False
    lp = 100.0 + np.arange(n)
    la = np.where(np.arange(n) < 8, 1.0, 2.0)
    rp = 50.0 + np.arange(n)
    ra = np.zeros(n)
    data = np.column_stack([lp, rp, la, ra])
    missing = np.zeros((n, 4))
    missing[~real] = 1
    if old_style:
        # the pre-2026-10-18 store: the empty places held interpolated values, marked missing
        for c in range(4):
            data[~real, c] = np.interp(np.where(~real)[0], np.where(real)[0], data[real, c])
    else:
        data[~real] = np.nan
    return {"ChannelNames": ["ZERO_THREE_LEFT Power", "ZERO_THREE_RIGHT Power",
                             "ZERO_THREE_LEFT Stimulation", "ZERO_THREE_RIGHT Stimulation"],
            "Data": data, "Missing": missing, "SamplingRate": FS, "StartTime": T0,
            "Duration": n / FS, "Descriptor": {"Therapy": {"Left": {"FrequencyInHertz": 24.5},
                                                          "Right": {"FrequencyInHertz": 10.5}}}}, real


def test_band_power_reader_returns_only_the_real_readings_with_their_current_and_time():
    rec, real = _recording()
    out = TSR.read_device_band_power([rec])
    left = out["ZERO_THREE_LEFT"]
    k = np.where(real)[0]
    assert left["n_samples"] == len(k) == 8
    assert np.array_equal(left["t"], T0 + k / FS)
    assert np.array_equal(left["power"], rec["Data"][k, 0])
    assert np.array_equal(left["mA"], rec["Data"][k, 2])
    assert np.all(np.isfinite(left["power"])) and np.all(np.isfinite(left["mA"]))
    assert left["centre_hz"].shape == (8,) and np.all(left["centre_hz"] == 24.5)


def test_current_reader_returns_only_the_real_readings():
    rec, real = _recording()
    cur = TSR.read_device_current([rec])
    b = cur["blocks"][0]
    k = np.where(real)[0]
    assert np.array_equal(b["t"], T0 + k / FS)
    assert np.array_equal(b["mA"]["ZERO_THREE_LEFT"], rec["Data"][k, 2])
    assert np.all(np.isfinite(b["mA"]["ZERO_THREE_RIGHT"]))


def test_a_gap_is_not_a_change_of_current():
    rec, _ = _recording()
    b = TSR.read_device_current([rec])["blocks"][0]
    aL = b["mA"]["ZERO_THREE_LEFT"]
    changed = np.where(np.diff(aL) != 0)[0] + 1
    assert len(changed) == 1 and aL[changed[0]] == 2.0 and aL[changed[0] - 1] == 1.0


def test_a_recording_stored_before_the_change_gives_the_same_real_readings():
    new, _ = _recording()
    old, _ = _recording(old_style=True)
    a, b = TSR.read_device_band_power([new]), TSR.read_device_band_power([old])
    for c in a:
        for key in ("t", "power", "mA"):
            assert np.array_equal(a[c][key], b[c][key]), (c, key)
    ca, cb = TSR.read_device_current([new])["blocks"][0], TSR.read_device_current([old])["blocks"][0]
    assert np.array_equal(ca["t"], cb["t"])
    assert all(np.array_equal(ca["mA"][c], cb["mA"][c]) for c in ca["mA"])


def test_exact_device_offsets_survive_and_missing_clocks_do_not_become_grid_times():
    rec, real = _recording()
    offsets = np.arange(12) / FS + .031
    offsets[~real] = np.nan
    rec['ReadingTime'] = offsets
    p = TSR.read_device_band_power([rec])['ZERO_THREE_LEFT']
    cur = TSR.read_device_current([rec])['blocks'][0]
    assert np.array_equal(p['t'], T0 + offsets[real])
    assert np.array_equal(cur['t'], p['t'])
    for broken in ([1], 'broken', None):
        rec['ReadingTime'] = broken
        assert TSR.read_device_band_power([rec])['ZERO_THREE_LEFT']['n_samples'] == 0
        assert len(TSR.read_device_current([rec])['blocks'][0]['t']) == 0


def test_missing_metadata_orientation_and_malformed_marks_preserve_unknown():
    rec, real = _recording()
    rec['Missing'] = rec['Missing'].T
    assert TSR.read_device_band_power([rec])['ZERO_THREE_LEFT']['n_samples'] == 8
    del rec['Missing']
    assert TSR.read_device_band_power([rec])['ZERO_THREE_LEFT']['n_samples'] == 8
    for broken in ([1], 'bad'):
        rec['Missing'] = broken
        assert TSR.read_device_band_power([rec])['ZERO_THREE_LEFT']['n_samples'] == 0
        assert len(TSR.read_device_current([rec])['blocks'][0]['t']) == 0


def test_malformed_recording_shapes_and_columns_cannot_silently_create_readings():
    import copy
    rec, _ = _recording()
    variants = [None, {}, dict(rec, Data=[1,2]), dict(rec, SamplingRate='bad'),
                dict(rec, SamplingRate=float('nan')), dict(rec, SamplingRate=0),
                dict(rec, StartTime=float('nan')), dict(rec, StartTime='bad')]
    for bad in variants:
        assert TSR.read_device_band_power([bad]) == {}
        assert TSR.read_device_current([bad])['blocks'] == []
    # Transposed device arrays retain the identical measured rows.
    transposed = dict(rec, Data=rec['Data'].T)
    assert TSR.read_device_band_power([transposed])['ZERO_THREE_LEFT']['n_samples'] == 8
    assert len(TSR.read_device_current([transposed])['blocks'][0]['t']) == 8
    assert TSR.read_device_band_power([dict(rec, ChannelNames=['X Power'])]) == {}
    assert TSR.read_device_current([dict(rec, ChannelNames=['X Power'])])['blocks'] == []
    assert TSR.read_device_band_power([dict(rec, ChannelNames=['X Power','unused','unused','unused','X Stimulation'])]) == {}
