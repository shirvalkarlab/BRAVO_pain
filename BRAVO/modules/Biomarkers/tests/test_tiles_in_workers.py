"""The 3-second tiles of a cold build are cut in worker processes (2026-10-02, the Jetstream2 BRAVO).

One task per run of neighbouring recordings; the recordings' tile arrays come back in the original
recording order and are turned into rows in the calling process, so the product is the one the
one-after-another build makes. Values, not shapes: every tile time, row value, flag and source label
is compared with the one-after-another build, exactly, on constructed recordings that exercise a gap,
the rail, a trailing partial piece, dropped packets, two sensing pairs and recordings that overlap
in time (the final sort must see them in the same order).

What is held here:
  * the workers' product == the one-after-another product, every field, exactly, and the real pool ran;
  * the call asks the shared pool for exactly what `DecodeCommon.parallel` says (`pool_jobs()` workers,
    `loky_backend()`): any other setting makes joblib throw away the web worker's warm pool;
  * BRAVO_TILE_JOBS=1 forces one-after-another and never asks for a pool; small inputs never ask either;
  * a pool that fails falls back to one-after-another, with the same product.
"""
import os
import sys
import unittest.mock as mock

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from modules.Biomarkers.routines import analytics, availability as AV      # noqa: E402
from modules.DecodeCommon import parallel as PAR                            # noqa: E402

CENTERS = np.arange(2.5, 100.0, 1.0)


def _recording(seed, n, t0, names=("ZERO_TWO_LEFT", "ONE_THREE_RIGHT"), product="td"):
    rng = np.random.default_rng(seed)
    data = rng.normal(0, 8, (n, len(names)))
    data[1000:1400, 0] = np.nan                                  # a gap
    data[5000:5003, 0] = np.nan                                  # a few dropped samples inside one piece
    data[7000, 1] = AV.PRO_LSB_SATURATION_UV + 1.0               # the rail
    miss = np.zeros(n, dtype=int)
    miss[9000:9200] = 1                                          # a dropped-packet span over the limit
    return {"ChannelNames": list(names), "Data": data, "SamplingRate": 250.0,
            "StartTime": t0, "Missing": miss, "product": product}


def _recordings():
    # sizes include a trailing partial piece; the 2nd and 3rd overlap in time with the 1st
    return [_recording(1, 12_345, 1.75e9), _recording(2, 20_001, 1.75e9 + 30.0, product="montage"),
            _recording(3, 15_000, 1.75e9 + 60.0), _recording(4, 9_999, 1.75e9 + 5.0),
            _recording(5, 13_000, 1.75e9 + 400.0), _recording(6, 11_111, 1.75e9 + 12.0)]


def _build(env, recs=None, **patches):
    old = {k: os.environ.get(k) for k in ("BRAVO_TILE_JOBS", "BRAVO_POOL_JOBS")}
    os.environ.update(env)
    try:
        with mock.patch.object(AV, "TILE_MIN_SAMPLES_FOR_WORKERS", 0, create=True):
            return {ch: AV.raw_lsb_spectrum_cache(ch, CENTERS, td_recordings=recs or _recordings())
                    for ch in ("ZERO_TWO_LEFT", "ONE_THREE_RIGHT")}
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class _InProcessParallel:
    """Stands in for joblib.Parallel: records how it was asked, runs the tasks here."""
    calls = []

    def __init__(self, *a, **k):
        type(self).calls.append(k)

    def __call__(self, tasks):
        return [f(*a, **k) for f, a, k in tasks]


def _recorder():
    return type("P", (_InProcessParallel,), {"calls": []})


def test_the_real_pool_gives_the_one_after_another_product_exactly_and_ran():
    serial = _build({"BRAVO_TILE_JOBS": "1"})
    runs_before = AV.TILE_POOL_RUNS["workers"]
    workers = _build({"BRAVO_TILE_JOBS": "", "BRAVO_POOL_JOBS": "3"})
    assert AV.TILE_POOL_RUNS["workers"] > runs_before                    # the pool really ran
    assert any(any(serial[ch]["td"]["saturated"]) for ch in serial)   # the rail is in the data
    for ch in serial:
        s, w = serial[ch], workers[ch]
        assert s["n_td_windows"] > 100 and not all(s["td"]["ok"]) and any(s["td"]["ok"])
        assert len(set(s["td"]["source"])) > 1                         # both products are in
        assert s == w                                                    # every field, exactly
        assert s["td"]["t"] == sorted(s["td"]["t"])


def test_the_call_asks_for_the_shared_pool_settings():
    P = _recorder()
    with mock.patch("joblib.Parallel", P):
        out = _build({"BRAVO_TILE_JOBS": "", "BRAVO_POOL_JOBS": "7"})
    assert P.calls
    want = PAR.loky_backend()
    for asked in P.calls:
        assert asked["n_jobs"] == 7
        assert type(asked["backend"]) is type(want)
        assert asked["backend"].backend_kwargs == want.backend_kwargs
    assert out["ZERO_TWO_LEFT"] == _build({"BRAVO_TILE_JOBS": "1"})["ZERO_TWO_LEFT"]


def test_the_switch_forces_one_after_another_and_never_asks_for_a_pool():
    P = _recorder()
    with mock.patch("joblib.Parallel", P):
        out = _build({"BRAVO_TILE_JOBS": "1", "BRAVO_POOL_JOBS": "7"})
    assert P.calls == [] and out["ZERO_TWO_LEFT"]["n_td_windows"] > 0


def test_a_small_input_never_asks_for_a_pool():
    P = _recorder()
    old = os.environ.pop("BRAVO_TILE_JOBS", None)
    try:
        with mock.patch("joblib.Parallel", P):
            AV.raw_lsb_spectrum_cache("ZERO_TWO_LEFT", CENTERS, td_recordings=_recordings()[:1])
    finally:
        if old is not None:
            os.environ["BRAVO_TILE_JOBS"] = old
    assert P.calls == []


def test_a_pool_that_fails_falls_back_to_one_after_another_with_the_same_product():
    class Broken(_InProcessParallel):
        calls = []

        def __call__(self, tasks):
            raise RuntimeError("the pool died")
    serial = _build({"BRAVO_TILE_JOBS": "1"})
    with mock.patch("joblib.Parallel", Broken):
        fell_back = _build({"BRAVO_TILE_JOBS": "", "BRAVO_POOL_JOBS": "7"})
    assert Broken.calls                                                  # the pool was asked, and died
    assert serial == fell_back
