"""Tests for the canonical decoded form and the one consumer built against it.

The point of these tests is NOT that the prototype works. It is that the prototype cannot
quietly disagree with the code it is being compared against. Every test below either pins a
rule the current path also obeys, or asserts the two produce the identical record on
constructed recordings where the answer is known.

The band-power recipes themselves are NOT re-implemented or re-tested here. They are reached
through the Biomarkers analytics module in both paths, and the two calibrated constants stay
there.
"""
import datetime

import numpy as np

# Both spellings on purpose: the container's path root makes these packages `modules.X`, the
# host suite's root makes them `X`. See `CacheStore/__init__.py`.
try:
    from modules.DecodeCommon import build_channel_index
    from modules.DecodeCommon.representation import (
        CHANNEL_INDEX_VERSION, canon_channel, missing_per_sample, to_epoch,
    )
    from modules.Biomarkers.routines import availability
    from modules.Biomarkers.routines import analytics
except ImportError:
    from DecodeCommon import build_channel_index
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
                  "2023-11-14T22:13:20", 1_700_000_000,
                  "2023-11-14T14:13:20-08:00",
                  datetime.datetime(2023, 11, 14, 22, 13, 20),
                  datetime.datetime(2023, 11, 14, 22, 13, 20, tzinfo=datetime.timezone.utc)):
        assert to_epoch(value) == availability._to_epoch(value), (
            "the canonical form disagrees with the platform on start time %r" % (value,))


def test_a_session_relative_start_time_is_refused_not_read_as_1970():
    # A small number is an offset from the start of a session, not a wall-clock time. Reading
    # it as an epoch would place the recording in 1970 and match it to no pain report at all,
    # silently. Both paths refuse it.
    assert to_epoch(12.5) is None


def test_a_naive_start_time_is_read_as_utc_on_every_host():
    """Open item 19, DECISIONS_and_open_items.md: a start time with no timezone attached names a
    moment in Universal Time (UTC), never the process's own local zone. `expected` is built with
    an explicit UTC offset rather than borrowed from either function under test, so this would
    have failed under the old rule on any host that does not itself run in Universal Time --
    unlike `test_start_time_matches_the_platform_rule`, which only proves the two functions agree
    with EACH OTHER and would have passed even under the old, host-dependent rule.
    """
    expected = datetime.datetime(2023, 11, 14, 22, 13, 20, tzinfo=datetime.timezone.utc).timestamp()
    naive_string = "2023-11-14T22:13:20"
    naive_datetime = datetime.datetime(2023, 11, 14, 22, 13, 20)
    for value in (naive_string, naive_datetime):
        assert to_epoch(value) == expected, "the canonical form read %r as local time" % (value,)
        assert availability._to_epoch(value) == expected, (
            "the platform read %r as local time" % (value,))


def test_a_timezone_aware_start_time_is_unchanged_by_the_naive_utc_rule():
    """An explicit offset is already unambiguous; naive-means-UTC must not touch it. The Z suffix,
    an explicit +00:00, and a genuinely non-UTC offset (-08:00, the same instant restated) must
    all still resolve to the same moment as their naive counterpart above."""
    expected = datetime.datetime(2023, 11, 14, 22, 13, 20, tzinfo=datetime.timezone.utc).timestamp()
    for value in ("2023-11-14T22:13:20Z", "2023-11-14T22:13:20+00:00",
                  "2023-11-14T14:13:20-08:00",
                  datetime.datetime(2023, 11, 14, 22, 13, 20, tzinfo=datetime.timezone.utc)):
        assert to_epoch(value) == expected, "the canonical form mis-read an explicit offset %r" % (value,)
        assert availability._to_epoch(value) == expected, (
            "the platform mis-read an explicit offset %r" % (value,))


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
    for token in ("345.59", "349.10", "352.62", "72.16", "72.90", "73.63", "LSB_PER_UV2_TRANSFORM =", "LSB_PER_DEVICE_PSD ="):
        assert token not in body, "the canonical form must not carry %r" % token


def test_the_version_is_an_integer_a_stored_copy_can_be_keyed_on():
    assert isinstance(CHANNEL_INDEX_VERSION, int) and CHANNEL_INDEX_VERSION >= 1


# The per-report reader (`per_pro_lsb_indexed`, one band-power value per pain report by the
# three-tier source rule; its reference scan and platform entry point in `availability`) and its
# 17 tests here were deleted on 2026-09-21 at the PI's direction: nothing on any page had read its
# answer since the timeline's per-report circles went (decision 216), and the Compute response's
# unread copy of it went on the same day (decision 224). The many-centre reader went on 2026-09-10
# (decision 115).


def test_the_per_report_reader_is_gone_from_both_packages():
    try:
        import modules.DecodeCommon as dc
    except ImportError:
        import DecodeCommon as dc
    assert not hasattr(dc, "per_pro_lsb_indexed")
    assert "per_pro_lsb_indexed" not in dc.__all__
    assert not hasattr(availability, "per_pro_lsb")
    assert not hasattr(availability, "_per_pro_lsb_scan")


# ----------------------------------------------------------------------------------------
# the tile-cache builder through the form (Track B step 4)
# ----------------------------------------------------------------------------------------

# The 0-100 Hz half-integer centre grid the tile cache is built on (the same grid the service uses).
CENTERS = tuple(float(c) for c in np.arange(2.5, 100.0, 1.0))

def _assert_tiles_identical(a, b):
    assert set(a) == set(b), "top-level keys differ"
    for fam in ("td", "psd"):
        assert set(a[fam]) == set(b[fam]), fam
        for k in a[fam]:
            x, y = np.asarray(a[fam][k]), np.asarray(b[fam][k])
            assert x.shape == y.shape, "%s/%s shape %s vs %s" % (fam, k, x.shape, y.shape)
            if x.dtype.kind in "fc":
                assert np.array_equal(x, y, equal_nan=True), "%s/%s values" % (fam, k)
            else:
                assert np.array_equal(x, y), "%s/%s values" % (fam, k)
    for k in ("channel", "centers_hz", "window_s", "band_half_hz", "n_td_windows", "n_psd_windows"):
        assert np.array_equal(np.asarray(a[k]), np.asarray(b[k])), k


def test_tiles_identical_through_the_form_and_in_the_recording_lists_order():
    # recordings deliberately NOT in start-time order, with a ring-named one and a railed one
    td = [_td_recording(["ZERO_THREE_LEFT", "ONE_THREE_LEFT"], t0=T0 + 900, n=int(FS * 30), seed=1),
          _td_recording(["ZERO_AND_THREE_LEFT_RING"], t0=T0, n=int(FS * 45), seed=2),
          _td_recording(["ZERO_THREE_LEFT"], t0=T0 + 300, n=int(FS * 20), amp=5000.0, seed=3)]
    for i, r in enumerate(td):
        r["product"] = ("streaming_td", "montage_td", "indefinite")[i]
    psd = [_psd_record("ZERO_THREE_LEFT", T0 + 100 + 50 * i, peak_hz=10.0 + i, seed=i) for i in range(4)]
    a = availability.raw_lsb_spectrum_cache("ZERO_THREE_LEFT", CENTERS, td_recordings=td,
                                            event_psd_recordings=psd)
    b = availability.raw_lsb_spectrum_cache("ZERO_THREE_LEFT", CENTERS, td_recordings=td,
                                            event_psd_recordings=psd, index=_index(td, []))
    _assert_tiles_identical(a, b)
    assert a["n_td_windows"] > 0 and a["n_psd_windows"] == 4
    assert {"BrainSense streaming", "Montage", "Indefinite stream"} <= set(a["td"]["source"])
