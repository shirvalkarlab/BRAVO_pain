"""No recording's start is taken from the device's tick counter.

The PI's ruling of 2026-09-26: no time from the device clock. Each block of a Percept export
carries `FirstPacketDateTime` and the device's millisecond counter `TicksInMses` / `TicksInMs`.
Until this ruling the decoder added the tick counter's fraction of a second to block 0's start and
re-timed every later block of a file as block 0 plus the tick difference (unless that disagreed
with its own `FirstPacketDateTime` by more than 10 s). On RCS08 that moved 182 of 254 stored
time-domain blocks by a median 0.75 s (at most 9.8 s).

What these tests pin: each block's start is exactly its own `FirstPacketDateTime` (to the
millisecond when the field carries milliseconds), for the streamed time-domain blocks, the
streamed power blocks, the indefinite streams and a joined recording. The ticks still place samples
INSIDE a block (the zero-fill of missing packets). The conversion of `FirstPacketDateTime` itself
from the device's clock to the tablet's is pinned in test_tablet_clock.py.

Plain `assert`, no arguments: these run in the container, where the decoder's imports are.
"""
from datetime import datetime, timezone

import numpy as np

from modules.MedtronicPercept import Percept
from modules.MedtronicPercept import BrainSenseStream
from modules.MedtronicPercept import IndefiniteStream


def _epoch(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


def _td_block(first_packet_iso, first_tick_ms, n_packets=12, channel="ZERO_THREE_LEFT"):
    """One streamed time-domain block: 250 Hz, a 250 ms packet of 62 or 63 samples, no gaps."""
    sizes = [62 + (i % 2) for i in range(n_packets)]
    ticks = [first_tick_ms + 250 * i for i in range(n_packets)]
    seqs = list(range(1, n_packets + 1))
    return {
        "FirstPacketDateTime": first_packet_iso,
        "Channel": channel,
        "Pass": "FIRST",
        "Gain": 250,
        "GlobalSequences": ",".join(str(s) for s in seqs),
        "GlobalPacketSizes": ",".join(str(s) for s in sizes),
        "TicksInMses": ",".join(str(t) for t in ticks),
        "TimeDomainData": [float(i % 7) for i in range(sum(sizes))],
        "SampleRateInHz": 250,
    }


def _power_block(first_packet_iso, first_tick_ms, n_packets=20):
    """One streamed power block: two readings a second, both sides, no gaps."""
    return {
        "FirstPacketDateTime": first_packet_iso,
        "Channel": "ZERO_THREE_LEFT,ZERO_THREE_RIGHT",
        "SampleRateInHz": 2,
        "TherapySnapshot": {"Left": {}, "Right": {}},
        "LfpData": [{"Left": {"LFP": 100 + i, "mA": 1.0}, "Right": {"LFP": 200 + i, "mA": 1.5},
                     "Seq": i + 1, "TicksInMs": first_tick_ms + 500 * i} for i in range(n_packets)],
    }


def _indefinite_block(first_packet_iso, first_tick_ms, channel):
    b = _td_block(first_packet_iso, first_tick_ms, channel=channel)
    return b


def test_each_streamed_time_domain_block_starts_at_its_own_first_packet_time_when_ticks_disagree_by_3_s():
    # Block 1's FirstPacketDateTime is 30 s after block 0's; its ticks say 33 s. Each keeps its own.
    t0, t1 = "2026-01-01T10:00:00Z", "2026-01-01T10:00:30Z"
    JSON = {"BrainSenseTimeDomain": [_td_block(t0, 5_000_700), _td_block(t1, 5_000_700 + 33_000)]}
    Data = Percept.extractTimeDomainStreamingData(JSON, dict())
    starts = [s["FirstPacketDateTime"] for s in Data["StreamingTD"]]
    assert starts == [_epoch(t0), _epoch(t1)], starts


def test_a_time_domain_block_whose_first_packet_time_has_milliseconds_keeps_them_exactly():
    t0 = "2026-01-01T10:00:00.250Z"
    JSON = {"BrainSenseTimeDomain": [_td_block(t0, 5_000_700)]}
    Data = Percept.extractTimeDomainStreamingData(JSON, dict())
    assert Data["StreamingTD"][0]["FirstPacketDateTime"] == _epoch(t0) == 1767261600.25


def test_each_streamed_power_block_starts_at_its_own_first_packet_time_when_ticks_disagree_by_3_s():
    t0, t1 = "2026-01-01T10:00:00Z", "2026-01-01T10:00:30Z"
    JSON = {"BrainSenseLfp": [_power_block(t0, 5_000_700), _power_block(t1, 5_000_700 + 33_000)]}
    Data = Percept.extractPowerDomainStreamingData(JSON, dict())
    starts = [s["FirstPacketDateTime"] for s in Data["StreamingPower"]]
    assert starts == [_epoch(t0), _epoch(t1)], starts


def test_a_power_block_whose_first_packet_time_has_milliseconds_keeps_them_exactly():
    t0 = "2026-01-01T10:00:00.250Z"
    JSON = {"BrainSenseLfp": [_power_block(t0, 5_000_700)]}
    Data = Percept.extractPowerDomainStreamingData(JSON, dict())
    assert Data["StreamingPower"][0]["FirstPacketDateTime"] == _epoch(t0)


def test_saved_streaming_recordings_carry_each_blocks_first_packet_time_as_their_start():
    # Through the saver, without the merge of adjacent blocks: the stored StartTime of every
    # time-domain and power recording is its block's own FirstPacketDateTime.
    t0, t1 = "2026-01-01T10:00:00Z", "2026-01-01T10:05:00.500Z"
    JSON = {"BrainSenseTimeDomain": [_td_block(t0, 5_000_700), _td_block(t1, 5_000_700 + 303_100)],
            "BrainSenseLfp": [_power_block(t0, 5_000_700), _power_block(t1, 5_000_700 + 303_100)]}
    Data = dict()
    Percept.extractTimeDomainStreamingData(JSON, Data)
    Percept.extractPowerDomainStreamingData(JSON, Data)
    td, pw = BrainSenseStream.saveBrainSenseStreams(Data["StreamingTD"], Data["StreamingPower"],
                                                    FixBreaking=False)
    assert [r["StartTime"] for r in td] == [_epoch(t0), _epoch(t1)]
    assert [r["StartTime"] for r in pw] == [_epoch(t0), _epoch(t1)]


def test_an_indefinite_stream_starts_at_its_first_packet_time_not_plus_the_tick_fraction():
    t0 = "2026-01-01T10:00:00Z"
    JSON = {"IndefiniteStreaming": [_indefinite_block(t0, 5_000_700, "ZERO_TWO_LEFT"),
                                    _indefinite_block(t0, 5_000_700, "ONE_THREE_LEFT")]}
    Data = Percept.extractIndefiniteStreaming(JSON, dict())
    recs = IndefiniteStream.saveIndefiniteStreams(Data["IndefiniteStream"])
    assert len(recs) == 1
    assert recs[0]["StartTime"] == _epoch(t0)


def test_ticks_still_place_a_missing_packet_inside_a_block_without_moving_its_start():
    # A 250 ms packet missing from the middle of a block is zero-filled from the tick jump; the
    # block's start is still its FirstPacketDateTime.
    t0 = "2026-01-01T10:00:00Z"
    b = _td_block(t0, 5_000_700)
    ticks = [int(x) for x in b["TicksInMses"].split(",")]
    sizes = [int(x) for x in b["GlobalPacketSizes"].split(",")]
    drop = 5
    n_dropped = sizes[drop]
    start_of_drop = sum(sizes[:drop])
    b["TicksInMses"] = ",".join(str(t) for i, t in enumerate(ticks) if i != drop)
    b["GlobalPacketSizes"] = ",".join(str(s) for i, s in enumerate(sizes) if i != drop)
    b["GlobalSequences"] = ",".join(str(i + 1) for i in range(len(ticks)) if i != drop)
    b["TimeDomainData"] = b["TimeDomainData"][:start_of_drop] + b["TimeDomainData"][start_of_drop + n_dropped:]
    Data = Percept.extractTimeDomainStreamingData({"BrainSenseTimeDomain": [b]}, dict())
    s = Data["StreamingTD"][0]
    assert s["FirstPacketDateTime"] == _epoch(t0)
    assert int(np.sum(s["Missing"])) > 0
    assert len(s["Data"]) == len(s["Missing"])


def _left_power_block(first_packet_iso, first_tick_ms, n_packets=6):
    """A one-sided power block (left only) with a fixed therapy, so the saver may join two."""
    return {
        "FirstPacketDateTime": first_packet_iso,
        "Channel": "ZERO_THREE_LEFT",
        "SampleRateInHz": 2,
        "TherapySnapshot": {"Left": {"RateInHertz": 55, "PulseWidthInMicroSecond": 60,
                                     "LowerLimitInMilliAmps": 0.5, "UpperLimitInMilliAmps": 4.5}},
        "LfpData": [{"Left": {"LFP": 100 + i, "mA": 1.0}, "Right": {"LFP": 0, "mA": 0.0},
                     "Seq": i + 1, "TicksInMs": first_tick_ms + 500 * i} for i in range(n_packets)],
    }


def test_a_joined_recording_keeps_the_first_packet_time_of_its_first_block():
    # Handoff item P-10: the repair that joins two recordings less than 30 s apart (same channel,
    # same therapy, same current across the join) must not move the joined recording's start. Block 1
    # starts 10 s after block 0 by FirstPacketDateTime and 13 s after by the ticks; the joined recording
    # starts at block 0's FirstPacketDateTime, and the gap between the blocks is filled from those
    # times (block 0 lasts 3.0 s, so 7.0 s of zeros).
    t0, t1 = "2026-01-01T10:00:00Z", "2026-01-01T10:00:10Z"
    JSON = {"BrainSenseTimeDomain": [_td_block(t0, 5_000_700), _td_block(t1, 5_000_700 + 13_000)],
            "BrainSenseLfp": [_left_power_block(t0, 5_000_700),
                              _left_power_block(t1, 5_000_700 + 13_000)]}
    Data = dict()
    Percept.extractTimeDomainStreamingData(JSON, Data)
    Percept.extractPowerDomainStreamingData(JSON, Data)
    n0 = len(Data["StreamingTD"][0]["Data"])
    n1 = len(Data["StreamingTD"][1]["Data"])
    td, pw = BrainSenseStream.saveBrainSenseStreams(Data["StreamingTD"], Data["StreamingPower"],
                                                    FixBreaking=True)
    assert len(td) == 1 and len(pw) == 1, (len(td), len(pw))
    assert td[0]["StartTime"] == _epoch(t0)
    assert pw[0]["StartTime"] == _epoch(t0)
    gap = int((_epoch(t1) - (_epoch(t0) + n0 / 250.0)) * 250)
    assert td[0]["Data"].shape[0] == n0 + gap + n1, (td[0]["Data"].shape, n0, gap, n1)


def test_the_ticks_give_power_readings_only_their_spacing_inside_the_block():
    # The power readings' times inside a block come from their tick steps, counted from the first
    # reading; the block's start is its FirstPacketDateTime, whatever the ticks read.
    t0 = "2026-01-01T10:00:00Z"
    b = _power_block(t0, 987_654_321, n_packets=6)
    Data = Percept.extractPowerDomainStreamingData({"BrainSenseLfp": [b]}, dict())
    s = Data["StreamingPower"][0]
    assert s["FirstPacketDateTime"] == _epoch(t0)
    assert list(s["Time"]) == [0.0, 0.5, 1.0, 1.5, 2.0, 2.5]
