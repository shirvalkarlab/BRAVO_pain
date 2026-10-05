"""The heat-map grid's per-pair statistics (shuffles, resamples, fits) run in worker processes
(2026-10-02, the Jetstream2 BRAVO). Matching recordings to pain reports stays in threads; the
arithmetic on each contact pair's power matrices goes to the shared pool, one pair per task, and
comes back in the pairs' own order. Values, not shapes: the answer from the workers is compared
with the one-after-another answer, field by field, on constructed data with the real statistics.

What is held here:
  * workers' answer == one-after-another answer, every field but the computing-time ones, and the
    pairs come back in their own order (the draws are seeded inside each pair's own call);
  * the call asks the shared pool for exactly what `DecodeCommon.parallel` says: `pool_jobs()` workers
    and `loky_backend()` (any other setting makes joblib throw away the web worker's warm pool);
  * BIOMARKER_SWEEP_PROCESSES=1 forces one-after-another and never asks for a pool;
  * a pool that fails falls back to one-after-another, with the same answer;
  * one pair's statistics failing blanks that pair only.

Merged here 2026-10-05: test_sweep_pairs_threads.py.
"""
import json
import os
import sys
import unittest.mock as mock
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from modules.Biomarkers import bravo_service as B          # noqa: E402
from modules.Biomarkers.routines import analytics as A    # noqa: E402
from modules.DecodeCommon import parallel as PAR          # noqa: E402
PAIRS = {"ZERO_TWO_LEFT": 11, "ONE_THREE_LEFT": 12, "ZERO_TWO_RIGHT": 13, "ONE_THREE_RIGHT": 14}
CENTERS = A.sweep_center_freqs(np.arange(2.5, 100.0, 1.0))
N_REPORTS = 40
PAIN = list(np.random.default_rng(5).integers(0, 11, N_REPORTS).astype(float))


def _fake_power(pro_times, raw_cache, _x, **kw):
    """Constructed band power for one pair: noise, with one band tracking the pain score."""
    rng = np.random.default_rng(raw_cache["seed"])
    power = {}
    for s in A.BAND_TIME_SWEEP_SECONDS:
        m = np.exp(rng.normal(0, 1, (N_REPORTS, CENTERS.size)))
        m[:, 5] += 0.8 * np.asarray(PAIN)
        power[float(s)] = m
    stats = {str(float(s)): {"n_pro": N_REPORTS} for s in A.BAND_TIME_SWEEP_SECONDS}
    return power, stats, CENTERS, None, None, [False] * N_REPORTS


def _canon(o):
    if isinstance(o, dict):
        return {str(k): _canon(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_canon(v) for v in o]
    if isinstance(o, np.ndarray):
        return _canon(o.tolist())
    if isinstance(o, np.generic):
        return o.item()
    return o


def _timeless(out):
    """One string per pair: every field but the computing-time ones, floats at full precision."""
    res = {}
    for ch, sw in out.items():
        sw = dict(sw)
        sw.pop("matched_seconds", None)
        sw.pop("total_seconds", None)
        if isinstance(sw.get("logistic_fit_crosscheck"), dict):
            sw["logistic_fit_crosscheck"] = {k: v for k, v in sw["logistic_fit_crosscheck"].items()
                                             if k != "seconds"}
        res[ch] = json.dumps(_canon(sw), sort_keys=True, default=str)
    return res


def _real_grids(out, except_for=()):
    """Every pair (bar those named) came back as a computed grid, not as the blank 'could not be completed'."""
    return [ch for ch, sw in out.items() if ch not in except_for and not sw.get("correlation_grid")]


def _run(env):
    old = {k: os.environ.get(k) for k in ("BIOMARKER_SWEEP_PROCESSES", "BRAVO_POOL_JOBS")}
    os.environ.update(env)
    try:
        with mock.patch.object(B, "_band_time_sweep_power_by_seconds", _fake_power):
            return B._band_time_sweep_channels(
                {ch: {"seed": s} for ch, s in PAIRS.items()}, list(np.arange(N_REPORTS, dtype=float)),
                tol_s=60, allow_window_reuse=False, pain_values=PAIN, label_strategy="median",
                low_pct=33, high_pct=67, outlier_n_mad=5, outlier_scale="raw",
                metric_key="m", metric_label="m", n_perm=60, n_boot=60)
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
    cls = type("P", (_InProcessParallel,), {"calls": []})
    return cls


def test_workers_give_the_one_after_another_answer_field_for_field_in_order():
    warned = []
    with mock.patch.object(B._log, "warning", lambda *a, **k: warned.append(a)):
        serial = _run({"BIOMARKER_SWEEP_PROCESSES": "1"})
        workers = _run({"BIOMARKER_SWEEP_PROCESSES": "", "BRAVO_POOL_JOBS": "3"})
    assert list(serial) == list(workers) == list(PAIRS)
    assert _real_grids(serial) == _real_grids(workers) == []
    s, w = _timeless(serial), _timeless(workers)
    assert all(len(v) > 5000 for v in s.values())                    # a real grid per pair
    assert [k for k in s if s[k] != w[k]] == []
    assert len({s[k] for k in s}) == len(PAIRS)                       # the pairs differ from each other
    assert warned == []                                               # no pool failure was swallowed


def test_the_call_asks_for_the_shared_pool_settings():
    P = _recorder()
    with mock.patch("joblib.Parallel", P):
        out = _run({"BIOMARKER_SWEEP_PROCESSES": "", "BRAVO_POOL_JOBS": "7"})
    assert len(P.calls) == 1
    asked = P.calls[0]
    with mock.patch.dict(os.environ, {"BRAVO_POOL_JOBS": "7"}):
        assert asked["n_jobs"] == PAR.pool_jobs() == 7
    want = PAR.loky_backend()
    assert type(asked["backend"]) is type(want)
    assert asked["backend"].backend_kwargs == want.backend_kwargs
    assert list(out) == list(PAIRS) and _real_grids(out) == []


def test_the_switch_forces_one_after_another_and_never_asks_for_a_pool():
    P = _recorder()
    with mock.patch("joblib.Parallel", P):
        out = _run({"BIOMARKER_SWEEP_PROCESSES": "1", "BRAVO_POOL_JOBS": "7"})
    assert P.calls == [] and list(out) == list(PAIRS) and _real_grids(out) == []


def test_a_pool_that_fails_falls_back_to_one_after_another_with_the_same_answer():
    class Broken(_InProcessParallel):
        calls = []

        def __call__(self, tasks):
            raise RuntimeError("the pool died")
    serial = _run({"BIOMARKER_SWEEP_PROCESSES": "1"})
    with mock.patch("joblib.Parallel", Broken):
        fell_back = _run({"BIOMARKER_SWEEP_PROCESSES": "", "BRAVO_POOL_JOBS": "7"})
    assert len(Broken.calls) == 1                                       # the pool was asked, and died
    assert _real_grids(fell_back) == []
    assert _timeless(serial) == _timeless(fell_back)


def test_one_pair_failing_blanks_that_pair_only_and_the_others_keep_their_answers():
    real = A.band_time_sweep_from_power

    def flaky(power, pain, **kw):
        if kw.get("channel") == "ONE_THREE_LEFT":
            raise ValueError("this pair broke")
        return real(power, pain, **kw)

    ok_out = _run({"BIOMARKER_SWEEP_PROCESSES": "1"})
    ok = _timeless(ok_out)
    P = _recorder()
    with mock.patch.object(A, "band_time_sweep_from_power", flaky), mock.patch("joblib.Parallel", P):
        got = _run({"BIOMARKER_SWEEP_PROCESSES": "", "BRAVO_POOL_JOBS": "7"})
    assert len(P.calls) == 1                                            # the pairs went through the pool
    t = _timeless(got)
    assert "this pair broke" in json.dumps(_canon(got["ONE_THREE_LEFT"]), default=str)
    assert [k for k in ok if k != "ONE_THREE_LEFT" and ok[k] != t[k]] == []
    assert list(got) == list(PAIRS)
    assert _real_grids(got, except_for=("ONE_THREE_LEFT",)) == [] and _real_grids(ok_out) == []
    assert not got["ONE_THREE_LEFT"].get("correlation_grid")


# --------------------------------------------------------------------------------------------------
# merged from test_sweep_pairs_threads.py
# The heat-map grid's contact pairs are swept side by side in threads (2026-10-02, the Jetstream2
# BRAVO). Each pair reads only its own cache; the answers come back in the pairs' own order and equal
# the one-after-another answers. Values, not shapes: each pair's entry compared with the serial run,
# the order of the pairs, and that more than one thread did the work.


import threading
from modules.Biomarkers.routines import analytics


def _run_pairs(threads):
    seen = set()
    old_power, old_sweep, old_env = (B._band_time_sweep_power_by_seconds,
                                     analytics.band_time_sweep_from_power,
                                     os.environ.get("BIOMARKER_SWEEP_THREADS"))
    old_proc = os.environ.get("BIOMARKER_SWEEP_PROCESSES")
    os.environ["BIOMARKER_SWEEP_PROCESSES"] = "1"      # this test stands in for the statistics; they stay in-process

    def power(pro_times, raw_cache, _x, **kw):
        seen.add(threading.get_ident())
        import time; time.sleep(0.05)
        return ([raw_cache["v"] * 2], {"10": {"n_pro": 3}}, [1.0], None, None, False)

    def sweep(power, pain_values, **kw):
        return {"grid": list(power), "channel": kw["channel"]}

    B._band_time_sweep_power_by_seconds = power
    analytics.band_time_sweep_from_power = sweep
    os.environ["BIOMARKER_SWEEP_THREADS"] = str(threads)
    try:
        out = B._band_time_sweep_channels(
            {"ZERO_TWO_LEFT": {"v": 1}, "ONE_THREE_LEFT": {"v": 2}, "EMPTY": {},
             "ZERO_TWO_RIGHT": {"v": 3}},
            [1.0, 2.0], tol_s=60, allow_window_reuse=False, pain_values=[1, 2],
            label_strategy="median", low_pct=33, high_pct=67, outlier_n_mad=5,
            outlier_scale=1.0, metric_key="m", metric_label="m")
    finally:
        B._band_time_sweep_power_by_seconds = old_power
        analytics.band_time_sweep_from_power = old_sweep
        if old_proc is None:
            os.environ.pop("BIOMARKER_SWEEP_PROCESSES", None)
        else:
            os.environ["BIOMARKER_SWEEP_PROCESSES"] = old_proc
        if old_env is None:
            os.environ.pop("BIOMARKER_SWEEP_THREADS", None)
        else:
            os.environ["BIOMARKER_SWEEP_THREADS"] = old_env
    for v in out.values():
        v.pop("matched_seconds", None); v.pop("total_seconds", None)
    return out, seen


def test_pairs_swept_in_threads_equal_the_one_after_another_answers_in_the_same_order():
    serial, seen1 = _run_pairs(1)
    threaded, seen4 = _run_pairs(4)
    assert list(serial) == list(threaded) == ["ZERO_TWO_LEFT", "ONE_THREE_LEFT", "ZERO_TWO_RIGHT"]
    assert serial == threaded
    assert [serial[k]["grid"] for k in serial] == [[2], [4], [6]]
    assert len(seen1) == 1 and len(seen4) == 3
