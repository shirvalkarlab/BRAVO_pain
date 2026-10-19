"""A streaming band-power block's first two readings are dropped as repeats only when they are
bit-for-bit copies of the next two (the PI, 2026-10-19, decision 491; CLAUDE.md section 11: "Drop
only a bit-for-bit duplicate of an ingested recording; one value off means ingest").

`Percept.extractPowerDomainStreamingData` dropped the first two readings whenever their sequence
numbers repeated the next two, without comparing time, power or current, so two real readings
that happened to share sequence numbers would have been lost. On RCS08 it dropped none (all
266,819 export readings are stored, decision 490); these tests pin the rule on made-up blocks.

Plain `assert`, no arguments: these run in the container, where the decoder's imports are.
"""
import numpy as np

from modules.MedtronicPercept import Percept

T0 = "2026-01-01T10:00:00Z"
START_TICK = 5_000_000


def _reading(seq, off_ms, left, right, left_ma=1.0, right_ma=2.0):
    return {"Left": {"LFP": left, "mA": left_ma}, "Right": {"LFP": right, "mA": right_ma},
            "Seq": seq, "TicksInMs": START_TICK + off_ms}


def _decode_all(readings):
    block = {"FirstPacketDateTime": T0, "Channel": "ZERO_THREE_LEFT,ZERO_THREE_RIGHT", "SampleRateInHz": 2,
             "TherapySnapshot": {"Left": {}, "Right": {}}, "LfpData": readings}
    return Percept.extractPowerDomainStreamingData({"BrainSenseLfp": [block]}, dict())


def _decode(readings):
    return _decode_all(readings)["StreamingPower"][0]


def _present(s):
    k = np.where(s["Missing"][:, 0] == 0)[0]
    return sorted((s["Power"][i, 0], s["Power"][i, 1]) for i in k)


def test_two_readings_that_copy_the_next_two_exactly_are_dropped_once():
    first = [_reading(1, 0, 100, 200), _reading(2, 500, 110, 210)]
    rest = [_reading(1, 0, 100, 200), _reading(2, 500, 110, 210)] + \
           [_reading(3 + i, 1000 + 500 * i, 120 + i, 220 + i) for i in range(4)]
    s = _decode(first + rest)
    assert _present(s) == sorted((r["Left"]["LFP"], r["Right"]["LFP"]) for r in rest), _present(s)


def test_two_readings_sharing_sequence_numbers_but_not_values_are_all_kept():
    # sequence numbers 1, 2, 1, 2 (a counter restart), but different times and powers: real readings
    readings = [_reading(1, 0, 100, 200), _reading(2, 500, 110, 210),
                _reading(1, 1000, 300, 400), _reading(2, 1500, 310, 410)] + \
               [_reading(3 + i, 2000 + 500 * i, 120 + i, 220 + i) for i in range(3)]
    s = _decode(readings)
    assert len(_present(s)) == len(readings), _present(s)
    assert _present(s) == sorted((r["Left"]["LFP"], r["Right"]["LFP"]) for r in readings)


def test_a_repeat_with_one_current_off_is_dropped_but_recorded_on_the_export():
    """Same sequence numbers and ticks, one current different. Kept, the ticks would run backwards and
    the whole stream would be set aside; so the pair is dropped and its values recorded."""
    readings = [_reading(1, 0, 100, 200, right_ma=2.5), _reading(2, 500, 110, 210),
                _reading(1, 0, 100, 200, right_ma=2.0), _reading(2, 500, 110, 210)] + \
               [_reading(3 + i, 1000 + 500 * i, 120 + i, 220 + i) for i in range(3)]
    out = _decode_all(readings)
    assert len(_present(out["StreamingPower"][0])) == len(readings) - 2
    aside = [a for a in out["StreamingPowerSetAside"] if "repeat" in a["reason"]]
    assert len(aside) == 1, out["StreamingPowerSetAside"]
    assert aside[0]["Stimulation"][0][1] == 2.5 and aside[0]["Power"][1] == [110.0, 210.0], aside


def test_an_exact_repeat_is_not_recorded_as_set_aside():
    first = [_reading(1, 0, 100, 200), _reading(2, 500, 110, 210)]
    rest = [_reading(1, 0, 100, 200), _reading(2, 500, 110, 210)] + \
           [_reading(3 + i, 1000 + 500 * i, 120 + i, 220 + i) for i in range(3)]
    assert _decode_all(first + rest)["StreamingPowerSetAside"] == []
