"""Two requests that need R at the same moment must both get the right answer (item C7's prerequisite).

The server's R (the program behind the mixed-model fits) runs inside the web worker and can do one
thing at a time. The Closed-Loop page's four deployment requests (ROC, device units, month-by-month
check, sign-off) all fit the same two models, and under the async worker they arrive together. A
lock (`analytics._R_GLOBAL_LOCK`) is meant to make them queue.

Three things are checked, on a constructed record (nothing here is a real recording):
  1. every call into R that the two fits make is made while the lock is held (by the thread that
     makes it); R is touched by three kinds of call here, each watched;
  2. eight threads started together, two kinds of fit, give exactly the answers the one-at-a-time
     run gave (every field equal, no tolerance);
  3. the control: with the lock taken away, check 1 fails, so the check can fail.
Plain asserts. When R or pymer4 is missing (the host machine) each test returns without checking.
"""
import copy
import importlib.util
import os
import sys
import threading
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from Biomarkers.routines import analytics  # noqa: E402
from Biomarkers.tests.test_one_block_per_report import _constructed  # noqa: E402

_HAS_R = importlib.util.find_spec("pymer4") is not None and importlib.util.find_spec("rpy2") is not None


def _fits(detail, stim):
    """The two R-using fits a deployment request makes, as plain values."""
    mixed = analytics.band_mixedmodel_inference(detail, "ZERO_TWO_LEFT", 20.0, strategy="median",
                                                exclude_first_weeks=0)
    stab = analytics.band_stim_stability(detail, "ZERO_TWO_LEFT", 20.0, stim_series=stim,
                                         strategy="median")
    return {"mixed": mixed, "stab": stab}


def _flat(o, p="", out=None):
    out = {} if out is None else out
    if isinstance(o, dict):
        for k, v in o.items():
            _flat(v, f"{p}.{k}", out)
    elif isinstance(o, (list, tuple)):
        for i, v in enumerate(o):
            _flat(v, f"{p}[{i}]", out)
    else:
        out[p] = repr(o)
    return out


class _Watch:
    """Records every R call made while the lock is NOT held by the calling thread."""

    def __init__(self):
        self.outside = []
        self.inside = 0
        self._undo = []

    def _wrap(self, owner, name, label):
        orig = getattr(owner, name)
        watch = self

        def wrapped(*a, **k):
            if analytics._R_GLOBAL_LOCK._is_owned():
                watch.inside += 1
            else:
                watch.outside.append(label)
            return orig(*a, **k)
        setattr(owner, name, wrapped)
        self._undo.append((owner, name, orig))

    def install(self):
        import rpy2.robjects as ro
        from pymer4.models import Lmer
        self._wrap(type(ro.r), "__call__", "R code run")
        self._wrap(type(ro.globalenv), "__setitem__", "R global variable set")
        self._wrap(Lmer, "fit", "pymer4 model fit")
        return self

    def remove(self):
        for owner, name, orig in reversed(self._undo):
            setattr(owner, name, orig)
        self._undo = []


def _skip_without_r():
    if not _HAS_R:
        return True
    try:
        import pymer4.models  # noqa: F401
        import rpy2.robjects  # noqa: F401
    except Exception:
        return True
    return False


def test_every_call_into_r_by_the_two_fits_holds_the_lock():
    if _skip_without_r():
        return
    detail, stim, _, _ = _constructed()
    w = _Watch().install()
    try:
        got = _fits(detail, stim)
    finally:
        w.remove()
    assert got["mixed"].get("available") and got["stab"].get("available"), (got["mixed"], got["stab"])
    assert w.inside > 0, "the watch saw no call into R at all, so it proves nothing"
    assert w.outside == [], w.outside


def test_the_watch_fails_when_the_lock_is_taken_away():
    """The control for the test above: swap in a lock nobody holds and the watch must report calls."""
    if _skip_without_r():
        return
    detail, stim, _, _ = _constructed()

    class _NoLock:
        def acquire(self, *a, **k):
            return True

        def release(self):
            return None

        def _is_owned(self):
            return False

    real = analytics._R_GLOBAL_LOCK
    w = _Watch()
    analytics._R_GLOBAL_LOCK = _NoLock()
    try:
        w.install()
        _fits(detail, stim)
    finally:
        w.remove()
        analytics._R_GLOBAL_LOCK = real
    assert len(w.outside) > 0, "with no lock the watch saw nothing outside it, so it cannot fail"


def test_eight_simultaneous_fits_give_the_one_at_a_time_answers():
    if _skip_without_r():
        return
    detail, stim, _, _ = _constructed()
    serial = _flat(_fits(copy.deepcopy(detail), copy.deepcopy(stim)))
    assert serial, "empty serial answer"
    assert any(k.startswith(".mixed.odds_ratio") for k in serial), sorted(serial)[:5]

    results, errors = [None] * 8, []
    start = threading.Barrier(8)

    def work(i):
        try:
            d, s = copy.deepcopy(detail), copy.deepcopy(stim)
            start.wait(timeout=60)
            # half the threads ask for the mixed model first, half for the stability test first, so
            # the two kinds of fit really do overlap in time
            if i % 2:
                out = _fits(d, s)
            else:
                stab = analytics.band_stim_stability(d, "ZERO_TWO_LEFT", 20.0, stim_series=s,
                                                     strategy="median")
                mixed = analytics.band_mixedmodel_inference(d, "ZERO_TWO_LEFT", 20.0,
                                                            strategy="median", exclude_first_weeks=0)
                out = {"mixed": mixed, "stab": stab}
            results[i] = _flat(out)
        except BaseException as e:      # noqa: BLE001
            errors.append((i, repr(e)))

    threads = [threading.Thread(target=work, args=(i,)) for i in range(8)]
    t0 = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=600)
    assert not errors, errors
    assert all(not t.is_alive() for t in threads), "a thread never finished (a stuck lock)"
    n_diff = 0
    for i, r in enumerate(results):
        assert r is not None, f"thread {i} gave no answer"
        assert r.keys() == serial.keys(), (i, sorted(r.keys() ^ serial.keys())[:5])
        n_diff += sum(1 for k in serial if r[k] != serial[k])
    assert n_diff == 0, f"{n_diff} fields differ between simultaneous and one-at-a-time answers"
    assert time.perf_counter() - t0 < 600
