'See the implementation and synthetic regression tests for this contract.'
import numpy as np

from modules.MedtronicPercept import Percept, Session

T0 = "2026-03-19T18:00:00Z"


def _lfp(n, start_tick=1000, step=100, backwards=False):
    ticks = [start_tick + (-1 if backwards and i == n - 1 else 1) * step * i for i in range(n)]
    return [{"Left": {"LFP": 10 + i, "mA": 1.0}, "Right": {"LFP": 20 + i, "mA": 1.0},
             "Seq": i, "TicksInMs": t} for i, t in enumerate(ticks)]


def _power_stream(n, **kw):
    return {"FirstPacketDateTime": T0, "SampleRateInHz": "2", "Channel": "ZERO_THREE_LEFT,ZERO_THREE_RIGHT",
            "TherapySnapshot": {"Left": {}, "Right": {}}, "LfpData": _lfp(n, **kw)}


def _td_stream(packets, channel="ZERO_THREE_LEFT"):
    sizes = [62 + (i % 2) for i in range(packets)]
    return {"FirstPacketDateTime": T0, "SampleRateInHz": "250", "Channel": channel,
            "GlobalSequences": ",".join(str(i + 1) for i in range(packets)),
            "GlobalPacketSizes": ",".join(str(s) for s in sizes),
            "TicksInMses": ",".join(str(1000 + 250 * i) for i in range(packets)),
            "TimeDomainData": list(np.arange(sum(sizes), dtype=float))}


def test_a_single_reading_band_power_recording_does_not_stop_the_others():
    data = {}
    Percept.extractPowerDomainStreamingData({"BrainSenseLfp": [_power_stream(1), _power_stream(20)]}, data)
    assert len(data["StreamingPower"]) == 2
    assert [len(s["Power"]) for s in data["StreamingPower"]] == [1, 20]


def test_backwards_ticks_set_aside_one_recording_only():
    data = {}
    Percept.extractPowerDomainStreamingData(
        {"BrainSenseLfp": [_power_stream(20, backwards=True), _power_stream(20)]}, data)
    assert len(data["StreamingPower"]) == 1
    assert len(data["StreamingPowerSetAside"]) == 1


def test_a_one_packet_time_domain_stream_is_kept():
    data = {}
    Percept.extractTimeDomainStreamingData({"BrainSenseTimeDomain": [_td_stream(1), _td_stream(10)]}, data)
    assert sorted(len(s["Data"]) for s in data["StreamingTD"]) == [62, 62 * 5 + 63 * 5]


def test_time_domain_is_built_without_any_band_power():
    data = {}
    Percept.extractTimeDomainStreamingData({"BrainSenseTimeDomain": [_td_stream(10)]}, data)
    td, power = Session.brainSenseStreamRecordings(data, fix_breaking=False)
    assert len(td) == 1 and power == []
    assert td[0]["type"] == "MedtronicBrainSenseTimeDomain"
