"""The device's own band-power samples grouped by channel, a column at a time (the PI, 2026-10-04,
decision 429; plan item 2). The band-power panel spent about 4.7 s here, one Python step and one
band-centre lookup per sample (about 421,000 on RCS08). Pinned: the output equals the per-sample
loop, kept as `_native_lsb_by_channel_loop`, field for field and in order, on constructed
streaming and chronic recordings with gaps, sentinels, negatives, NaNs, a frequency schedule with
ties and times before its first change, a scalar centre, and a therapy-only fallback."""
import numpy as np

from DecodeCommon import representation as R


def _recordings(seed=0):
    rng = np.random.default_rng(seed)
    pd_recs = []
    for k in range(3):
        n = 200
        data = rng.uniform(0, 5000, (n, 4))
        data[rng.random((n, 4)) < 0.05] = R._POWER_SENTINEL
        data[rng.random((n, 4)) < 0.03] = -1.0
        data[rng.random((n, 4)) < 0.02] = np.nan
        missing = (rng.random((n, 4)) < 0.04).astype(float)
        pd_recs.append({"ChannelNames": ["ZERO_TWO_LEFT POWER", "ZERO_TWO_LEFT LFP",
                                         "ONE_THREE_RIGHT POWER", "X"],
                        "Data": data, "Missing": missing, "SamplingRate": 2.0,
                        "StartTime": f"2026-0{k + 1}-01T00:00:00Z",
                        "Descriptor": {"Therapy": {"Left": {"SensingSetup": {"FrequencyInHertz": 20.0}}}}})
    chronic = []
    base = 1.75e9
    for k, (sched, scalar) in enumerate([
            ([[base + 100, 22.1], [base + 100, 18.3], [base + 400, 27.0]], None),
            (None, 25.2),
            (None, None),
            ([["bad", 1], [base + 900, 9.9]], 23.4)]):
        n = 150
        t = base + 10.0 * np.arange(n) + 1000.0 * k
        col = rng.uniform(0, 3000, n)
        col[rng.random(n) < 0.05] = R._POWER_SENTINEL
        col[rng.random(n) < 0.05] = -2.0
        rec = {"ChannelNames": ["LFP LEFT" if k % 2 == 0 else "LFP RIGHT"], "Data": col[:, None],
               "Time": t, "Descriptor": {"Therapy": {"Left": {"SensingSetup": {"FrequencyInHertz": 20.0}},
                                                     "Right": {"SensingSetup": {"FrequencyInHertz": 31.0}}}}}
        if sched is not None:
            rec["FreqScheduleHz"] = sched
        if scalar is not None:
            rec["CenterFrequencyHz"] = scalar
        chronic.append(rec)
    return chronic, pd_recs


def test_the_column_version_equals_the_per_sample_loop():
    for seed in range(5):
        chronic, pd_recs = _recordings(seed)
        want = R._native_lsb_by_channel_loop(chronic, pd_recs)
        got = R.native_lsb_by_channel(chronic, pd_recs)
        assert list(got) == list(want), seed
        for ch in want:
            for k in ("t", "y", "center_hz", "source"):
                a, b = got[ch][k], want[ch][k]
                assert len(a) == len(b), (seed, ch, k)
                assert all((x == y) or (x != x and y != y) for x, y in zip(a, b)), (seed, ch, k)
                assert [type(x) for x in a] == [type(y) for y in b], (seed, ch, k)


def test_no_recordings_gives_nothing():
    assert R.native_lsb_by_channel(None, None) == {} == R._native_lsb_by_channel_loop(None, None)


def test_a_column_with_no_usable_sample_makes_no_entry():
    chronic, pd_recs = _recordings(0)
    pd_recs[0]["Data"][:, 2] = R._POWER_SENTINEL          # ONE_THREE_RIGHT POWER: nothing usable
    for r in pd_recs[1:]:
        r["Data"][:, 2] = -1.0
    chronic[1]["Data"][:, 0] = np.nan
    want = R._native_lsb_by_channel_loop(chronic, pd_recs)
    got = R.native_lsb_by_channel(chronic, pd_recs)
    assert list(got) == list(want)
