"""The segments of a gappy record are simulated in worker processes (2026-10-02: the Closed-Loop
request ran its ~700 segment simulations one after another on one core of the Jetstream2 BRAVO's
64). Each segment's simulation depends on that segment alone, and the per-segment results are
combined in segment order exactly as before, so the answer is the same to the last bit.

Values, not shapes: every number and array of the result compared element for element.
"""
import numpy as np

try:
    from modules.ClosedLoopDeployment import simulation as S
    from modules.StimOptimizer.routines import amplitude_response as AR
    from modules.ClosedLoopDeployment.tests.test_simulation import _plan, _series
except ImportError:                                              # pragma: no cover
    from ClosedLoopDeployment import simulation as S
    from StimOptimizer.routines import amplitude_response as AR
    from ClosedLoopDeployment.tests.test_simulation import _plan, _series


def _record(n_segments=12):
    t, p, a = _series(n=300)
    ts, ps, as_ = [], [], []
    for k in range(n_segments):                 # stretches a day apart, as in a chronic record
        ts.append(t + 86400.0 * k); ps.append(p if k % 2 else p[::-1]); as_.append(a)
    return np.concatenate(ts), np.concatenate(ps), np.concatenate(as_)


def _flat(o, pre=""):
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
    fa, fb = _flat(a), _flat(b)
    assert fa.keys() == fb.keys()
    n = 0
    for k in fa:
        x, y = np.asarray(fa[k]), np.asarray(fb[k])
        n += int(x.shape != y.shape or not np.array_equal(x, y, equal_nan=x.dtype.kind == "f"))
    return len(fa), n


def _run(monkeypatch, jobs):
    monkeypatch.setenv(S.SEGMENT_JOBS_ENV, str(jobs))
    t, p, a = _record()
    curves = [AR.ResponseCurve.zero(), AR.ResponseCurve.zero()]
    return S.simulate_segments(t, p, a, _plan(), curves, tau_s=30.0, keep_longest=2)


def test_segments_simulated_in_worker_processes_give_the_same_result_to_the_last_bit(monkeypatch):
    one = _run(monkeypatch, 1)
    many = _run(monkeypatch, 4)
    assert one["refused"] is False and one["n_segments_used"] == 12
    n, differing = _differences(one, many)
    assert n > 50 and differing == 0, (n, differing)


def test_when_no_worker_process_can_start_the_segments_run_here_with_the_same_result(monkeypatch):
    import joblib

    one = _run(monkeypatch, 1)

    def no_pool(*a, **k):
        raise OSError("no process pool in this sandbox")

    monkeypatch.setattr(joblib, "Parallel", no_pool)
    fallback = _run(monkeypatch, 4)
    n, differing = _differences(one, fallback)
    assert differing == 0, (n, differing)
