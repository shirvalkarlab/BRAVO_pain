"""BrainSense streaming is kept whole (the PI, 2026-10-05: ingest ALL data, decision 440). On RCS08
one band-power recording with a single reading stopped the band-power step for its export
(2026-03-19), and because time-domain was stored only when band power also decoded, all 20
time-domain recordings of that export (about 34 min) were lost; and 18 short time-domain fragments
were dropped for having one packet after the first-packet repair.

Values: a single-reading band-power recording decodes beside a normal one; a recording whose ticks
run backwards is set aside and named, the others kept; a one-packet time-domain stream is kept;
time-domain recordings are built when no band power decoded at all."""
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
