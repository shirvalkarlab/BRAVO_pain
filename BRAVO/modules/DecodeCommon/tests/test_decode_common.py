"""Tests for the canonical decoded form and the one consumer built against it.

The point of these tests is NOT that the prototype works. It is that the prototype cannot
quietly disagree with the code it is being compared against. Every test below either pins a
rule the current path also obeys, or asserts the two produce the identical record on
constructed recordings where the answer is known.

The band-power recipes themselves are NOT re-implemented or re-tested here. They are reached
through the Biomarkers analytics module in both paths, and the two calibrated constants stay
there.
"""
import numpy as np

# Both spellings on purpose: the container's path root makes these packages `modules.X`, the
# host suite's root makes them `X`. See `CacheStore/__init__.py`.
try:
    from modules.DecodeCommon import (build_channel_index, per_pro_lsb_indexed,
                                      per_pro_lsb_spectrum_indexed)
    from modules.DecodeCommon.representation import (
        CHANNEL_INDEX_VERSION, canon_channel, missing_per_sample, to_epoch,
    )
    from modules.Biomarkers.routines import availability
    from modules.Biomarkers.routines import analytics
except ImportError:
    from DecodeCommon import (build_channel_index, per_pro_lsb_indexed,
                              per_pro_lsb_spectrum_indexed)
    from DecodeCommon.representation import (
        CHANNEL_INDEX_VERSION, canon_channel, missing_per_sample, to_epoch,
    )
    from Biomarkers.routines import availability
    from Biomarkers.routines import analytics

# Every test below takes no arguments, so the container's own runner
# (`_agent_bridge/run_tests.py`, which calls each `test_*` with nothing) can execute this
# file as well as pytest can. Cases that would otherwise be a parametrized sweep are
# written as a loop inside one test, with the failing case named in the assertion.

T0 = 1_700_000_000.0          # a start time comfortably past the 1e9 epoch guard
FS = 250.0


# ----------------------------------------------------------------------------------------
# the canonicalisation rule must not drift from the platform's
# ----------------------------------------------------------------------------------------

CHANNEL_NAMES = [
    "ZERO_THREE_LEFT", "ZERO_THREE_RIGHT", "ONE_THREE_LEFT", "ZERO_TWO_RIGHT",
    "ZERO_AND_THREE_LEFT_RING", "ONE_AND_THREE_RIGHT_RING", "ZERO_AND_TWO_LEFT_RING",
    "one_three_left", "ONE_A_ONE_B_LEFT_SEGMENT", "ZERO_AND_THREE_LEFT",
    "", "  ", "TWO_A_TWO_B_RIGHT_SEGMENT_RING",
]


def test_canonical_name_matches_the_platform_rule():
    for name in CHANNEL_NAMES:
        assert canon_channel(name) == availability._canon_channel(name), (
            "the canonical form disagrees with the platform on %r" % (name,))


def test_canonical_name_is_idempotent():
    for name in CHANNEL_NAMES:
        once = canon_channel(name)
        assert canon_channel(once) == once


def test_ring_and_short_spellings_land_on_one_key():
    assert canon_channel("ZERO_AND_THREE_LEFT_RING") == canon_channel("ZERO_THREE_LEFT")


# ----------------------------------------------------------------------------------------
# the timestamp and dropped-packet rules must not drift either
# ----------------------------------------------------------------------------------------

def test_start_time_matches_the_platform_rule():
    for value in (None, "", "   ", "not a time", 0, 1.0, 999_999_999.0, T0,
                  "2023-11-14T22:13:20Z", "2023-11-14T22:13:20+00:00",
                  "2023-11-14T22:13:20", 1_700_000_000):
        assert to_epoch(value) == availability._to_epoch(value), (
            "the canonical form disagrees with the platform on start time %r" % (value,))


def test_a_session_relative_start_time_is_refused_not_read_as_1970():
    # A small number is an offset from the start of a session, not a wall-clock time. Reading
    # it as an epoch would place the recording in 1970 and match it to no pain report at all,
    # silently. Both paths refuse it.
    assert to_epoch(12.5) is None


def test_dropped_packet_flag_matches_the_platform_rule():
    cases = [
        (None, 10),
        (np.zeros(10), 10),
        (np.array([0, 1, 0, 0, 0, 0, 0, 0, 0, 1]), 10),
        (np.zeros((10, 3)), 10),
        (np.array([[0, 1, 0]] * 10), 10),
        (np.array([[0] * 10, [1] + [0] * 9]), 10),
    ]
    for i, (missing, nsamp) in enumerate(cases):
        a = missing_per_sample(missing, nsamp)
        b = availability._missing_per_sample(missing, nsamp)
        if a is None or b is None:
            assert a is None and b is None, "case %d disagrees on None" % i
        else:
            assert np.array_equal(a, b), "case %d disagrees: %r vs %r" % (i, a, b)


# ----------------------------------------------------------------------------------------
# what the built form holds
# ----------------------------------------------------------------------------------------

def _td_recording(channels, *, t0=T0, n=1500, amp=50.0, seed=0):
    rng = np.random.default_rng(seed)
    data = amp * rng.standard_normal((n, len(channels)))
    return {"ChannelNames": list(channels), "Data": data, "SamplingRate": FS,
            "StartTime": t0, "RecordingType": "MedtronicBrainSenseTimeDomain"}


def _psd_record(channel, t, *, peak_hz=12.0, seed=0):
    freq = np.arange(0.0, 100.0, 1.0)
    power = 1.0 / (1.0 + (freq - peak_hz) ** 2) + 0.01
    return {"channel": channel, "t": t, "freq": freq, "power": power, "source": "event"}


def _index(td, psd):
    return build_channel_index(td, psd, step_seconds=analytics.TRANSFORM_STEP_SECONDS)


def test_ring_named_and_short_named_recordings_share_one_key():
    idx = _index([_td_recording(["ZERO_AND_THREE_LEFT_RING"], t0=T0),
                  _td_recording(["ZERO_THREE_LEFT"], t0=T0 + 100)], [])
    assert idx.td("ZERO_THREE_LEFT")["t0"].size == 2
    assert idx.td("ZERO_AND_THREE_LEFT_RING")["t0"].size == 2


def test_traces_are_ordered_earliest_first_so_a_reader_can_bisect():
    idx = _index([_td_recording(["ZERO_THREE_LEFT"], t0=T0 + 500),
                  _td_recording(["ZERO_THREE_LEFT"], t0=T0),
                  _td_recording(["ZERO_THREE_LEFT"], t0=T0 + 250)], [])
    t0s = idx.td("ZERO_THREE_LEFT")["t0"]
    assert np.all(np.diff(t0s) >= 0)
    assert t0s[0] == T0


def test_spectrum_records_keep_their_original_order():
    # The reader breaks a tie between two equidistant records by taking the FIRST, which is
    # only the same choice the current linear scan makes if the order is preserved.
    recs = [_psd_record("ZERO_THREE_LEFT", T0 + 300),
            _psd_record("ZERO_THREE_LEFT", T0 + 100),
            _psd_record("ZERO_THREE_LEFT", T0 + 200)]
    idx = _index([], recs)
    assert list(idx.psd("ZERO_THREE_LEFT")["t"]) == [T0 + 300, T0 + 100, T0 + 200]


def test_a_recording_with_an_unreadable_start_time_is_dropped_and_counted():
    good = _td_recording(["ZERO_THREE_LEFT"], t0=T0)
    bad = _td_recording(["ZERO_THREE_LEFT"], t0=12.5)      # session-relative, refused
    idx = _index([good, bad], [])
    s = idx.summary()
    assert s["n_td_recordings_offered"] == 2
    assert s["n_td_traces_kept"] == 1


def test_a_spectrum_record_with_an_unreadable_time_is_dropped_and_counted():
    idx = _index([], [_psd_record("ZERO_THREE_LEFT", T0),
                      _psd_record("ZERO_THREE_LEFT", None)])
    s = idx.summary()
    assert s["n_psd_records_offered"] == 2
    assert s["n_psd_records_kept"] == 1


def test_one_canonical_channel_listed_twice_in_a_recording_yields_one_trace():
    # The current code resolves a channel to the FIRST matching column, so a second column
    # under the same canonical name is unreachable there. The form must not expose it.
    idx = _index([_td_recording(["ZERO_THREE_LEFT", "ZERO_AND_THREE_LEFT_RING"], t0=T0)], [])
    assert len(idx.td("ZERO_THREE_LEFT")["traces"]) == 1


def test_a_transposed_data_block_is_accepted_in_both_orientations():
    r = _td_recording(["ZERO_THREE_LEFT", "ONE_THREE_LEFT"], n=1500)
    flipped = dict(r)
    flipped["Data"] = np.asarray(r["Data"]).T          # (n_channels, n_samples)
    a = _index([r], []).td("ZERO_THREE_LEFT")["traces"][0]["col"]
    b = _index([flipped], []).td("ZERO_THREE_LEFT")["traces"][0]["col"]
    assert np.array_equal(a, b)


def test_an_unknown_channel_reads_as_empty_rather_than_raising():
    idx = _index([_td_recording(["ZERO_THREE_LEFT"])], [_psd_record("ZERO_THREE_LEFT", T0)])
    assert idx.td("NO_SUCH_CHANNEL")["t0"].size == 0
    assert idx.psd("NO_SUCH_CHANNEL")["t"].size == 0


def test_the_form_stores_no_calibration_constant():
    # A shared decode layer must not become a second home for a unit conversion. The two
    # calibrated constants belong to analytics, and this asserts the module text is free of
    # them rather than trusting a reading of it.
    import inspect
    import sys as _sys
    representation = _sys.modules[canon_channel.__module__]
    src = inspect.getsource(representation)
    body = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
    for token in ("352.62", "73.63", "LSB_PER_UV2_TRANSFORM =", "LSB_PER_DEVICE_PSD ="):
        assert token not in body, "the canonical form must not carry %r" % token


def test_the_version_is_an_integer_a_stored_copy_can_be_keyed_on():
    assert isinstance(CHANNEL_INDEX_VERSION, int) and CHANNEL_INDEX_VERSION >= 1


# ----------------------------------------------------------------------------------------
# the indexed consumer against the current implementation, on constructed recordings
# ----------------------------------------------------------------------------------------

FIELDS = ("t", "lsb", "tier", "center_hz", "used_s", "saturated", "reason")


def _both(pro_times, native, channel, center_hz, td, psd, **kw):
    idx = _index(td, psd)
    a = availability._per_pro_lsb_scan(pro_times, native, channel, center_hz,
                                       td_recordings=td, event_psd_recordings=psd, **kw)
    b = per_pro_lsb_indexed(pro_times, native, channel, center_hz,
                            index=idx, analytics=analytics,
                            saturation_uv=availability.PRO_LSB_SATURATION_UV,
                            tier_native=availability.PRO_LSB_TIER_NATIVE,
                            tier_td=availability.PRO_LSB_TIER_TD,
                            tier_bridge=availability.PRO_LSB_TIER_BRIDGE, **kw)
    return a, b


def _assert_identical(a, b):
    assert len(a) == len(b)
    for ra, rb in zip(a, b):
        for f in FIELDS:
            va, vb = ra.get(f), rb.get(f)
            if isinstance(va, float) and isinstance(vb, float) \
                    and np.isnan(va) and np.isnan(vb):
                continue
            assert va == vb, "field %r differs: %r vs %r" % (f, va, vb)


def test_identical_when_the_device_sensed_the_band():
    native = {"t": [T0 + 10, T0 + 60], "y": [123.0, 456.0],
              "center_hz": [12.7, 12.7], "modeled": [False, False]}
    a, b = _both([T0 + 12.0], native, "ZERO_THREE_LEFT", 12.7, [], [])
    _assert_identical(a, b)
    assert a[0]["tier"] == availability.PRO_LSB_TIER_NATIVE


def test_identical_when_a_modelled_point_must_not_win_the_first_tier():
    native = {"t": [T0 + 10], "y": [123.0], "center_hz": [12.7], "modeled": [True]}
    a, b = _both([T0 + 12.0], native, "ZERO_THREE_LEFT", 12.7, [], [])
    _assert_identical(a, b)
    assert a[0]["tier"] is None


def test_identical_when_the_sensed_flag_is_the_wrong_length_and_both_fail_closed():
    native = {"t": [T0 + 10, T0 + 20], "y": [1.0, 2.0],
              "center_hz": [12.7, 12.7], "modeled": [False]}     # short on purpose
    a, b = _both([T0 + 12.0], native, "ZERO_THREE_LEFT", 12.7, [], [])
    _assert_identical(a, b)
    assert a[0]["tier"] is None


def test_identical_on_the_voltage_trace_route():
    td = [_td_recording(["ZERO_THREE_LEFT"], t0=T0, n=int(FS * 120))]
    a, b = _both([T0 + 60.0], None, "ZERO_THREE_LEFT", 12.7, td, [])
    _assert_identical(a, b)
    assert a[0]["tier"] == availability.PRO_LSB_TIER_TD


def test_identical_on_the_voltage_trace_route_through_a_ring_channel_name():
    td = [_td_recording(["ZERO_AND_THREE_LEFT_RING"], t0=T0, n=int(FS * 120))]
    a, b = _both([T0 + 60.0], None, "ZERO_THREE_LEFT", 12.7, td, [])
    _assert_identical(a, b)
    assert a[0]["tier"] == availability.PRO_LSB_TIER_TD


def test_identical_when_a_pain_report_falls_outside_every_recording():
    td = [_td_recording(["ZERO_THREE_LEFT"], t0=T0, n=int(FS * 30))]
    a, b = _both([T0 + 10_000.0], None, "ZERO_THREE_LEFT", 12.7, td, [])
    _assert_identical(a, b)
    assert a[0]["tier"] is None and a[0]["reason"] == "no source in any tier"


def test_identical_when_the_voltage_window_is_railed_and_both_fall_through():
    n = int(FS * 120)
    r = _td_recording(["ZERO_THREE_LEFT"], t0=T0, n=n)
    r["Data"] = np.asarray(r["Data"], dtype=float)
    r["Data"][:, 0] = 9000.0                              # every sample past the rail
    psd = [_psd_record("ZERO_THREE_LEFT", T0 + 60.0)]
    a, b = _both([T0 + 60.0], None, "ZERO_THREE_LEFT", 12.7, [r], psd)
    _assert_identical(a, b)
    assert a[0]["saturated"] is True
    assert a[0]["tier"] == availability.PRO_LSB_TIER_BRIDGE


def test_identical_on_the_device_spectrum_route():
    psd = [_psd_record("ZERO_THREE_LEFT", T0 + 5.0)]
    a, b = _both([T0], None, "ZERO_THREE_LEFT", 12.7, [], psd)
    _assert_identical(a, b)
    assert a[0]["tier"] == availability.PRO_LSB_TIER_BRIDGE


def test_identical_when_the_band_is_outside_the_checked_conversion_range():
    # Outside 7.8-30 Hz the device-spectrum route is refused by both paths, so the report
    # comes back unmatched rather than bridged from an unchecked conversion.
    psd = [_psd_record("ZERO_THREE_LEFT", T0 + 5.0, peak_hz=60.0)]
    a, b = _both([T0], None, "ZERO_THREE_LEFT", 60.5, [], psd)
    _assert_identical(a, b)
    assert a[0]["tier"] is None


def test_identical_tie_break_between_two_equidistant_spectrum_records():
    # Two records the same distance either side of the report. Both paths must keep the one
    # that appears FIRST in the list, and they must keep the SAME one.
    early = _psd_record("ZERO_THREE_LEFT", T0 - 30.0, peak_hz=10.0, seed=1)
    late = _psd_record("ZERO_THREE_LEFT", T0 + 30.0, peak_hz=25.0, seed=2)
    a, b = _both([T0], None, "ZERO_THREE_LEFT", 12.7, [], [early, late])
    _assert_identical(a, b)
    a2, b2 = _both([T0], None, "ZERO_THREE_LEFT", 12.7, [], [late, early])
    _assert_identical(a2, b2)
    assert a[0]["lsb"] != a2[0]["lsb"], (
        "the order-dependent tie-break is what is being pinned; if these agree the test "
        "no longer proves the two paths break the tie the same way")


def test_identical_when_a_spectrum_record_sits_just_outside_the_tolerance():
    psd = [_psd_record("ZERO_THREE_LEFT", T0 + 121.0)]
    a, b = _both([T0], None, "ZERO_THREE_LEFT", 12.7, [], psd, native_tol_s=120.0)
    _assert_identical(a, b)
    assert a[0]["tier"] is None


def test_identical_when_a_spectrum_record_belongs_to_another_channel():
    psd = [_psd_record("ONE_THREE_RIGHT", T0 + 5.0)]
    a, b = _both([T0], None, "ZERO_THREE_LEFT", 12.7, [], psd)
    _assert_identical(a, b)
    assert a[0]["tier"] is None


def test_identical_across_a_mixed_record_of_many_reports():
    td = [_td_recording(["ZERO_THREE_LEFT"], t0=T0, n=int(FS * 200), seed=3),
          _td_recording(["ONE_THREE_LEFT"], t0=T0 + 400, n=int(FS * 200), seed=4),
          _td_recording(["ZERO_AND_THREE_LEFT_RING"], t0=T0 + 800, n=int(FS * 200), seed=5)]
    psd = [_psd_record("ZERO_THREE_LEFT", T0 + 300 + 7 * i, peak_hz=9.0 + i, seed=i)
           for i in range(12)]
    native = {"t": [T0 + 1500], "y": [777.0], "center_hz": [12.7], "modeled": [False]}
    pro = [T0 + 50 * i for i in range(40)]
    a, b = _both(pro, native, "ZERO_THREE_LEFT", 12.7, td, psd)
    _assert_identical(a, b)
    tiers = {r["tier"] for r in a}
    assert len(tiers) >= 3, (
        "this case exists to exercise more than one tier; it currently reaches %r" % (tiers,))


def test_identical_when_there_are_no_pain_reports_at_all():
    a, b = _both([], None, "ZERO_THREE_LEFT", 12.7,
                 [_td_recording(["ZERO_THREE_LEFT"])], [_psd_record("ZERO_THREE_LEFT", T0)])
    assert a == [] and b == []


def test_the_form_is_not_mutated_by_being_read():
    td = [_td_recording(["ZERO_THREE_LEFT"], t0=T0, n=int(FS * 120))]
    psd = [_psd_record("ZERO_THREE_LEFT", T0 + 60.0)]
    idx = _index(td, psd)
    before_col = idx.td("ZERO_THREE_LEFT")["traces"][0]["col"].copy()
    before_t = idx.psd("ZERO_THREE_LEFT")["t"].copy()
    for _ in range(3):
        per_pro_lsb_indexed([T0 + 60.0], None, "ZERO_THREE_LEFT", 12.7,
                            index=idx, analytics=analytics)
    assert np.array_equal(before_col, idx.td("ZERO_THREE_LEFT")["traces"][0]["col"])
    assert np.array_equal(before_t, idx.psd("ZERO_THREE_LEFT")["t"])


def test_reading_the_same_form_twice_gives_the_same_answer():
    td = [_td_recording(["ZERO_THREE_LEFT"], t0=T0, n=int(FS * 200), seed=7)]
    psd = [_psd_record("ZERO_THREE_LEFT", T0 + 300.0)]
    idx = _index(td, psd)
    pro = [T0 + 20 * i for i in range(20)]
    first = per_pro_lsb_indexed(pro, None, "ZERO_THREE_LEFT", 12.7,
                                index=idx, analytics=analytics)
    second = per_pro_lsb_indexed(pro, None, "ZERO_THREE_LEFT", 12.7,
                                 index=idx, analytics=analytics)
    _assert_identical(first, second)


# ----------------------------------------------------------------------------------------
# the indexed full-spectrum reader against the current implementation
# ----------------------------------------------------------------------------------------

SPECTRUM_FIELDS = ("t", "tier", "lsb", "calibrated", "center_hz", "used_s", "saturated", "reason")
CENTERS = tuple(float(c) for c in np.arange(2.5, 100.0, 1.0))


def _both_spectrum(pro_times, channel, td, psd, centers=CENTERS, **kw):
    idx = _index(td, psd)
    a = availability._per_pro_lsb_spectrum_scan(pro_times, channel, centers,
                                                td_recordings=td, event_psd_recordings=psd, **kw)
    b = per_pro_lsb_spectrum_indexed(pro_times, channel, centers, index=idx, analytics=analytics,
                                     saturation_uv=availability.PRO_LSB_SATURATION_UV,
                                     tier_td=availability.PRO_LSB_TIER_TD,
                                     tier_bridge=availability.PRO_LSB_TIER_BRIDGE, **kw)
    return a, b


def _assert_identical_spectrum(a, b):
    assert len(a) == len(b), "record counts differ: %d vs %d" % (len(a), len(b))
    for i, (ra, rb) in enumerate(zip(a, b)):
        assert tuple(ra) == tuple(rb), "record %d has different fields" % i
        for f in SPECTRUM_FIELDS:
            va, vb = ra[f], rb[f]
            if isinstance(va, list):
                assert len(va) == len(vb), "record %d field %r length" % (i, f)
                for k, (x, y) in enumerate(zip(va, vb)):
                    assert x == y, "record %d field %r centre %d: %r vs %r" % (i, f, k, x, y)
            else:
                assert va == vb, "record %d field %r: %r vs %r" % (i, f, va, vb)


def test_spectrum_identical_on_the_voltage_trace_route():
    td = [_td_recording(["ZERO_THREE_LEFT", "ONE_THREE_LEFT"], t0=T0, n=int(FS * 120), seed=7)]
    a, b = _both_spectrum([T0 + 40.0, T0 + 70.0], "ZERO_THREE_LEFT", td, [])
    _assert_identical_spectrum(a, b)
    assert a[0]["tier"] == availability.PRO_LSB_TIER_TD and any(a[0]["calibrated"])


def test_spectrum_identical_on_the_device_spectrum_route_with_per_band_calibration():
    psd = [_psd_record("ZERO_THREE_LEFT", T0 + 5.0, peak_hz=20.0)]
    a, b = _both_spectrum([T0], "ZERO_THREE_LEFT", [], psd)
    _assert_identical_spectrum(a, b)
    assert a[0]["tier"] == availability.PRO_LSB_TIER_BRIDGE
    cal = dict(zip(a[0]["center_hz"], a[0]["calibrated"]))
    assert cal[2.5] is False and cal[12.5] is True and cal[55.5] is False


def test_spectrum_identical_when_the_voltage_window_is_railed_and_both_fall_through():
    td = [_td_recording(["ZERO_THREE_LEFT"], t0=T0, n=int(FS * 120), amp=5000.0, seed=1)]
    psd = [_psd_record("ZERO_THREE_LEFT", T0 + 60.0)]
    a, b = _both_spectrum([T0 + 60.0], "ZERO_THREE_LEFT", td, psd)
    _assert_identical_spectrum(a, b)
    assert a[0]["tier"] == availability.PRO_LSB_TIER_BRIDGE and a[0]["saturated"] is True


def test_spectrum_identical_when_a_report_has_no_source_at_all():
    a, b = _both_spectrum([T0 + 99999.0], "ZERO_THREE_LEFT",
                          [_td_recording(["ZERO_THREE_LEFT"], t0=T0)], [_psd_record("ZERO_THREE_LEFT", T0)])
    _assert_identical_spectrum(a, b)
    assert a[0]["tier"] is None and a[0]["reason"] == "no TD coverage and no coincident PSD event"


def test_spectrum_identical_tie_break_between_two_equidistant_records():
    psd = [_psd_record("ZERO_THREE_LEFT", T0 + 10.0, peak_hz=9.0, seed=1),
           _psd_record("ZERO_THREE_LEFT", T0 - 10.0, peak_hz=30.0, seed=2)]
    a, b = _both_spectrum([T0], "ZERO_THREE_LEFT", [], psd)
    _assert_identical_spectrum(a, b)
    assert a[0]["tier"] == availability.PRO_LSB_TIER_BRIDGE


def test_spectrum_identical_across_a_mixed_record_of_many_reports():
    td = [_td_recording(["ZERO_THREE_LEFT"], t0=T0, n=int(FS * 200), seed=3),
          _td_recording(["ONE_THREE_LEFT"], t0=T0 + 400, n=int(FS * 200), seed=4),
          _td_recording(["ZERO_AND_THREE_LEFT_RING"], t0=T0 + 800, n=int(FS * 200), seed=5)]
    psd = [_psd_record("ZERO_THREE_LEFT", T0 + 300 + 7 * i, peak_hz=9.0 + i, seed=i)
           for i in range(12)]
    pro = [T0 + 50 * i for i in range(40)]
    a, b = _both_spectrum(pro, "ZERO_THREE_LEFT", td, psd)
    _assert_identical_spectrum(a, b)
    tiers = [r["tier"] for r in a]
    assert availability.PRO_LSB_TIER_TD in tiers and availability.PRO_LSB_TIER_BRIDGE in tiers
    assert None in tiers


def test_the_spectrum_reader_stores_no_calibration_constant_either():
    import inspect
    import sys as _sys
    mod = _sys.modules[per_pro_lsb_spectrum_indexed.__module__]
    body = "\n".join(l for l in inspect.getsource(mod).splitlines() if not l.strip().startswith("#"))
    for token in ("352.62", "73.63", "LSB_PER_UV2_TRANSFORM =", "LSB_PER_DEVICE_PSD ="):
        assert token not in body, "the consumer must not carry %r" % token


# ----------------------------------------------------------------------------------------
# the platform's own entry points, under both settings of the switch
# ----------------------------------------------------------------------------------------

def test_the_platform_entry_points_give_the_scan_answer_under_both_switch_settings():
    td = [_td_recording(["ZERO_THREE_LEFT"], t0=T0, n=int(FS * 200), seed=3),
          _td_recording(["ONE_THREE_LEFT"], t0=T0 + 400, n=int(FS * 200), seed=4)]
    psd = [_psd_record("ZERO_THREE_LEFT", T0 + 300 + 7 * i, peak_hz=9.0 + i, seed=i)
           for i in range(12)]
    native = {"t": [T0 + 1500], "y": [777.0], "center_hz": [12.7], "modeled": [False]}
    pro = [T0 + 50 * i for i in range(40)]
    ref = availability._per_pro_lsb_scan(pro, native, "ZERO_THREE_LEFT", 12.7,
                                         td_recordings=td, event_psd_recordings=psd)
    ref_s = availability._per_pro_lsb_spectrum_scan(pro, "ZERO_THREE_LEFT", CENTERS,
                                                    td_recordings=td, event_psd_recordings=psd)
    prev = availability.USE_CHANNEL_INDEX
    try:
        for flag in (True, False):
            availability.USE_CHANNEL_INDEX = flag
            got = availability.per_pro_lsb(pro, native, "ZERO_THREE_LEFT", 12.7,
                                           td_recordings=td, event_psd_recordings=psd)
            _assert_identical(ref, got)
            got_s = availability.per_pro_lsb_spectrum(pro, "ZERO_THREE_LEFT", CENTERS,
                                                      td_recordings=td, event_psd_recordings=psd)
            _assert_identical_spectrum(ref_s, got_s)
        # and with a caller-supplied index, as the service passes it
        idx = _index(td, psd)
        _assert_identical(ref, availability.per_pro_lsb(pro, native, "ZERO_THREE_LEFT", 12.7,
                                                        index=idx))
        _assert_identical_spectrum(ref_s, availability.per_pro_lsb_spectrum(
            pro, "ZERO_THREE_LEFT", CENTERS, index=idx))
    finally:
        availability.USE_CHANNEL_INDEX = prev
