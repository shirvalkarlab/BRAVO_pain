"""The device's own band-power samples carry their OWN run's band and their OWN contact pair (the
PI's go-ahead, 2026-10-06; decision 461).

Until now every BrainSense streaming sample on a pair was tagged with ONE band, the last run's
(`power_center_freqs`, "last writer wins"), though RCS08's runs on R 0-3 used 9 bands; and every
chronic sample of one side was filed under ONE pair, the first streaming pair met on that side,
though the chronic record's own contact schedule moved between 0-3, 1-3 and 0-2. The Closed-Loop
sign-off picks samples by that band tag to set the threshold to program; on the committed band
(L 1-3, 24.5 Hz) it found none and fell back to a modelled value. Pinned here for all three
copies of the rule: the fast one, its per-sample reference, and the timeline's reference scan.
"""
import sys
import pathlib

import numpy as np

_BRAVO_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(_BRAVO_ROOT) not in sys.path:
    sys.path.insert(0, str(_BRAVO_ROOT))

from DecodeCommon import representation as R
from modules.Biomarkers.routines import availability as av

T0 = 1_760_000_000.0


def _run(hz, start, contact="ZERO_THREE_RIGHT", n=10):
    side = "Right" if "RIGHT" in contact else "Left"
    return {"ChannelNames": [f"{contact} Power"], "Data": np.full((n, 1), 100.0 + hz),
            "Missing": np.zeros((n, 1)), "SamplingRate": 2.0, "StartTime": start,
            "Descriptor": {"Therapy": {side: {"SensingSetup": {"FrequencyInHertz": hz}}}}}


def _chronic(side="Left", schedule=True):
    t = T0 + 600.0 * np.arange(6)
    rec = {"ChannelNames": [f"{side}Hemisphere LFP", f"{side}Hemisphere Amplitude"],
           "Data": np.column_stack([np.arange(6) * 10.0 + 1, np.full(6, 2.0)]), "Time": t,
           "SamplingRate": -1, "FreqScheduleHz": [[T0 - 10, 22.46], [T0 + 1500, 11.72]]}
    if schedule:
        rec["ContactSchedule"] = [[T0 - 10, "1-3"], [T0 + 1500, "0-3"]]
    return rec


def _all_three(chronic, pd):
    fast = R.native_lsb_by_channel(chronic, pd)
    loop = R._native_lsb_by_channel_loop(chronic, pd)
    scan = av._lsb_series_scan(chronic, pd)
    return fast, loop, scan


def test_each_streaming_run_keeps_its_own_band():
    pd = [_run(9.77, T0), _run(26.37, T0 + 3600)]
    for out in _all_three([], pd):
        d = out["ZERO_THREE_RIGHT"]
        bands = {round(t - T0): hz for t, hz in zip(d["t"], d["center_hz"])}
        assert bands[0] == R.snap_freq(9.77) and bands[3600] == R.snap_freq(26.37)


def test_a_run_without_its_own_band_falls_back_to_the_pairs():
    bare = _run(9.77, T0)
    bare["Descriptor"] = {}
    pd = [bare, _run(26.37, T0 + 3600)]
    for out in _all_three([], pd):
        d = out["ZERO_THREE_RIGHT"]
        assert d["center_hz"][0] == R.snap_freq(26.37)


def test_chronic_samples_are_filed_under_the_pair_in_force_then():
    pd = [_run(9.77, T0 - 7200, contact="ZERO_TWO_LEFT")]     # the first left streaming pair
    for out in _all_three([_chronic()], pd):
        a = [(round(t - T0), hz) for t, hz, s in zip(out["ONE_THREE_LEFT"]["t"], out["ONE_THREE_LEFT"]["center_hz"],
                                                     out["ONE_THREE_LEFT"]["source"]) if s == "chronic"]
        b = [(round(t - T0), hz) for t, hz, s in zip(out["ZERO_THREE_LEFT"]["t"], out["ZERO_THREE_LEFT"]["center_hz"],
                                                     out["ZERO_THREE_LEFT"]["source"]) if s == "chronic"]
        assert a == [(0, R.snap_freq(22.46)), (600, R.snap_freq(22.46)), (1200, R.snap_freq(22.46))]
        assert b == [(1800, R.snap_freq(11.72)), (2400, R.snap_freq(11.72)), (3000, R.snap_freq(11.72))]
        assert "chronic" not in out["ZERO_TWO_LEFT"]["source"]


def test_chronic_without_a_contact_schedule_keeps_the_old_filing():
    pd = [_run(9.77, T0 - 7200, contact="ZERO_TWO_LEFT")]
    for out in _all_three([_chronic(schedule=False)], pd):
        assert out["ZERO_TWO_LEFT"]["source"].count("chronic") == 6


def test_the_index_version_moved():
    assert R.CHANNEL_INDEX_VERSION >= 4


# ---- A streaming run that reads 0 throughout is not a reading (the PI, 2026-10-06; decision 462) ----
def _zero_run(hz, start, contact="ZERO_THREE_LEFT"):
    r = _run(hz, start, contact=contact)
    r["Data"] = np.zeros_like(r["Data"])
    return r


def test_a_run_reading_zero_throughout_is_left_out_by_all_three():
    pd = [_zero_run(26.37, T0), _run(26.37, T0 + 3600, contact="ZERO_THREE_LEFT")]
    for out in _all_three([], pd):
        d = out["ZERO_THREE_LEFT"]
        assert len(d["t"]) == 10 and all(t >= T0 + 3600 for t in d["t"])
        assert 0.0 not in d["y"]


def test_a_run_with_some_zeros_is_kept_whole():
    r = _run(26.37, T0, contact="ZERO_THREE_LEFT")
    r["Data"][:5] = 0.0
    for out in _all_three([], [r]):
        assert out["ZERO_THREE_LEFT"]["y"].count(0.0) == 5


def test_the_left_out_runs_are_counted_with_their_pair_and_band():
    pd = [_zero_run(26.37, T0), _zero_run(9.77, T0 + 10, contact="ZERO_TWO_LEFT"),
          _run(26.37, T0 + 3600, contact="ZERO_THREE_LEFT")]
    z = R.zero_runs(pd)
    assert [(x["pair"], x["center_hz"], x["n"]) for x in z] == [
        ("ZERO_THREE_LEFT", R.snap_freq(26.37), 10), ("ZERO_TWO_LEFT", R.snap_freq(9.77), 10)]
