"""The band checks of the readiness screen run in worker processes (2026-10-02: a two-stage Stim
Optimizer request made its 1,080 band checks -- `lfp_response.assess_response`, two regression
fits each -- one after another, 12.6 s on one core of the Jetstream2 BRAVO's 64).

Each check depends on its own band's power and its cell's current, visit labels and repeat units
alone, so whole cells are handed out in chunks and the results put back in the cells' order; the
rest of the screen runs in the calling process as before. The answer must be the same to the last
bit: every field of every band check and every value of the screen frame compared element for
element, a difference count of 0, never a tolerance.
"""
import dataclasses
import logging
import os

import numpy as np
import pytest

from StimOptimizer.routines import band_checks as BC
from StimOptimizer.routines import lfp_evidence as EV
from StimOptimizer.routines import lfp_response as LR
from StimOptimizer.routines import stage_gate as GATE
from StimOptimizer.routines import surrogate as SUR

CENTRES = [float(c) for c in range(10, 28)]          # eighteen bands per cell, as on RCS08
PAIN = {"ZERO_TWO_LEFT": set(CENTRES), "ONE_THREE_RIGHT": {12.0, 20.0}}


def _cell(seed, *, n_per_step=12, amps=(1.0, 1.5, 2.0, 2.5), visits=4, slope=-0.6):
    """One cell: every visit walks the current steps, band power has a current effect (falling
    for some bands, rising for others), a visit offset and right-skewed scatter."""
    rng = np.random.default_rng(seed)
    amp, era = [], []
    for v in range(visits):
        for a in amps:
            amp += [a] * n_per_step
            era += [f"2026-0{v + 1}-01"] * n_per_step
    amp = np.asarray(amp, float)
    era = np.asarray(era)
    offset = np.repeat(rng.normal(0.0, 1.0, visits), len(amps) * n_per_step)
    bp = {}
    for i, c in enumerate(CENTRES):
        s = slope if i % 3 else -slope
        bp[(c, 5.0)] = np.exp(rng.normal(0.0, 0.4, amp.size)) * (20.0 + s * amp + offset + 0.1 * i)
    return GATE.LfpEvidence(amplitude_mA=amp, band_power=bp, era=era, cluster=era,
                            hemisphere="Left")


def _evidence():
    """Eight cells that fit, plus one too small to assess (its checks are NOT ASSESSED)."""
    ev = {}
    for k, (ch, hemi, rate) in enumerate([(ch, h, r) for ch in ("ZERO_TWO_LEFT", "ONE_THREE_RIGHT")
                                          for h in ("Left", "Right") for r in (55.0, 130.0)]):
        ev[(ch, hemi, rate)] = _cell(k)
    ev[("ZERO_TWO_LEFT", "Left", 165.0)] = _cell(99, n_per_step=1, amps=(1.0, 2.0), visits=3)
    return ev


def _flat(o, pre=""):
    if dataclasses.is_dataclass(o) and not isinstance(o, type):
        o = dataclasses.asdict(o)
    if isinstance(o, dict):
        out = {}
        for k, v in o.items():
            out.update(_flat(v, f"{pre}.{k}"))
        return out
    if isinstance(o, (list, tuple)):
        out = {}
        for i, v in enumerate(o):
            out.update(_flat(v, f"{pre}[{i}]"))
        return out
    return {pre: o}


def _differences(a, b):
    """(fields compared, fields differing): same keys, same type, same value, NaN equal to NaN."""
    fa, fb = _flat(a), _flat(b)
    assert fa.keys() == fb.keys()
    n = 0
    for k in fa:
        x, y = fa[k], fb[k]
        if type(x) is not type(y):
            n += 1
            continue
        xa, ya = np.asarray(x), np.asarray(y)
        n += int(xa.shape != ya.shape
                 or not np.array_equal(xa, ya, equal_nan=xa.dtype.kind == "f"))
    return len(fa), n


def _screen(monkeypatch, ev, jobs):
    monkeypatch.setenv(BC.JOBS_ENV, str(jobs))
    checks = BC.check_all(ev, LR.assess_response)
    screen, best = EV.screen_cells(ev, response_fn=LR.assess_response, amp_ceiling=5.0,
                                   pain_positive_by_channel=PAIN)
    return {"checks": {str(k): {c: r for c, r in v.items()} for k, v in checks.items()},
            "screen": screen.to_dict("list"), "best": best}


def test_band_checks_in_worker_processes_give_the_one_process_answer_to_the_last_bit(
        monkeypatch, caplog):
    ev = _evidence()
    one = _screen(monkeypatch, ev, 1)
    with caplog.at_level(logging.WARNING):
        many = _screen(monkeypatch, ev, 3)
    assert not [r for r in caplog.records if "one at a time" in r.getMessage()], caplog.text
    results = [r for cell in one["checks"].values() for r in cell.values()]
    assert len(results) == 9 * 18
    assert sum(np.isfinite(r.slope_p) for r in results) == 8 * 18      # the small cell: none
    assert sum(r.responds is None for r in results) == 18
    assert len({r.slope_per_mA for r in results if np.isfinite(r.slope_p)}) == 8 * 18
    n, differing = _differences(one, many)
    assert n > 3000 and differing == 0, (n, differing)


def _where(power, amp, era=None, cluster=None):
    """A stand-in band check reporting the process it ran in and its linear-algebra threads."""
    from threadpoolctl import threadpool_info
    return os.getpid(), sorted({d["num_threads"] for d in threadpool_info()
                                if d.get("user_api") == "blas"})


@pytest.mark.parametrize("threads", [1, 2])
def test_the_checks_run_in_other_processes_at_the_callers_linear_algebra_thread_count(
        monkeypatch, threads):
    threadpoolctl = pytest.importorskip("threadpoolctl")
    if not [d for d in threadpoolctl.threadpool_info() if d.get("user_api") == "blas"]:
        pytest.skip("no linear-algebra library whose thread count can be read")
    monkeypatch.setenv(BC.JOBS_ENV, "3")
    with threadpoolctl.threadpool_limits(limits=threads, user_api="blas"):
        got = BC.check_all(_evidence(), _where)
    seen = [r for cell in got.values() for r in cell.values()]
    assert len(seen) == 9 * 18
    assert os.getpid() not in {pid for pid, _ in seen}
    assert {tuple(t) for _, t in seen} == {(threads,)}


def test_when_no_worker_process_can_start_the_checks_run_here_with_the_same_answer(monkeypatch):
    import joblib

    ev = _evidence()
    one = _screen(monkeypatch, ev, 1)

    def no_pool(*a, **k):
        raise OSError("no process pool in this sandbox")

    monkeypatch.setattr(joblib, "Parallel", no_pool)
    fallback = _screen(monkeypatch, ev, 3)
    n, differing = _differences(one, fallback)
    assert n > 3000 and differing == 0, (n, differing)


def _asked(monkeypatch):
    import joblib
    asked = []                         # recorded, not raised: a raise would be caught by the fallback
    monkeypatch.setattr(joblib, "Parallel", lambda *a, **k: asked.append(1))
    return asked


def test_with_the_setting_at_one_no_worker_process_is_asked_for(monkeypatch):
    """"1" is the before-this-change path: every check in the calling process."""
    asked = _asked(monkeypatch)
    monkeypatch.setenv(BC.JOBS_ENV, "1")
    got = BC.check_all(_evidence(), LR.assess_response)
    assert asked == [] and sum(len(v) for v in got.values()) == 9 * 18


def test_a_screen_too_small_to_be_worth_handing_out_runs_here(monkeypatch):
    asked = _asked(monkeypatch)
    monkeypatch.setenv(BC.JOBS_ENV, "3")
    ev = dict(list(_evidence().items())[:2])                     # 36 checks
    assert 2 * 18 < BC.MIN_CHECKS_FOR_WORKERS
    got = BC.check_all(ev, LR.assess_response)
    assert asked == [] and sum(len(v) for v in got.values()) == 36


def test_worker_count_setting(monkeypatch):
    """Unset, the band checks ask for the held-out folds' worker count: joblib keeps ONE pool and
    rebuilds it whenever a different count is asked for."""
    monkeypatch.delenv(SUR.LOO_JOBS_ENV, raising=False)
    for raw, want in (("1", 1), ("0", 1), ("4", 4), ("not a number", SUR._loo_n_jobs())):
        monkeypatch.setenv(BC.JOBS_ENV, raw)
        assert BC.n_jobs() == want, raw
    monkeypatch.delenv(BC.JOBS_ENV)
    assert BC.n_jobs() == SUR._loo_n_jobs() == SUR.LOO_DEFAULT_JOBS
    monkeypatch.setenv(SUR.LOO_JOBS_ENV, "6")
    assert BC.n_jobs() == 6
