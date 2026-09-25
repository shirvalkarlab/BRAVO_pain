"""Speed-up item 3 (the PI, 2026-09-25: "add numba and do option 1"): the design rule's two-component
filter runs as a compiled loop and returns EXACTLY what the numpy loop returns.

The numpy loop does about 30 small array operations per time step over 349 stretches x 1,499 steps
on RCS08, and the fit calls it about 1,600 times: 29 ms a call, the time spent in dispatch rather
than arithmetic. The compiled loop mirrors every operation in the same order, sums each step's terms
in numpy's own pairwise order, and takes the log from the same library; this test holds its
log-likelihood and count equal to the numpy loop's on constructed panels with gaps, short and long
stretches and a missing first reading, over many parameter draws, and the whole fit equal too.
Skipped where numba is not installed (CI); the container has it.
"""
import numpy as np
import pytest

pytest.importorskip("numba")

from ClosedLoopDeployment import design_rule as DR


def _panel(seed, s=60, l=300):
    rng = np.random.default_rng(seed)
    Y = np.full((s, l), np.nan)
    for i in range(s):
        n = int(rng.choice([3, 7, 12, 40, l]))
        y = 100 + np.cumsum(rng.normal(0, 3, n)) + rng.normal(0, 5, n)
        Y[i, :n] = y
        gaps = rng.random(n) < 0.15
        Y[i, :n][gaps] = np.nan
    Y[0, 0] = np.nan                                           # a stretch whose first reading is missing
    return Y


def test_the_compiled_filter_returns_exactly_the_numpy_filters_answer():
    for seed in range(4):
        Y = _panel(seed)
        sc = DR._scales(Y)
        rng = np.random.default_rng(100 + seed)
        for _ in range(40):
            kw = dict(phi_s=rng.uniform(0.3, 0.999), phi_f=rng.uniform(0.0, 0.95),
                      q_s=rng.uniform(0.01, 3) * sc["var_rob"], q_f=rng.uniform(0.01, 3) * sc["var_rob"],
                      m=sc["mbar"] + rng.normal(0, 3), r0=rng.uniform(0.05, 3) * sc["var_rob"])
            a = DR._filter_2comp_numpy(Y, **kw)
            b = DR.filter_2comp(Y, **kw)
            assert DR.COMPILED_FILTER, "numba is installed, so the compiled loop must be the one used"
            assert (a["loglik"] == b["loglik"] or (np.isnan(a["loglik"]) and np.isnan(b["loglik"]))) and a["n"] == b["n"], (kw, a, b)


def test_the_whole_fit_is_the_same_with_the_compiled_filter():
    Y = _panel(7, s=30, l=120)
    fast = DR.fit_two_component(Y, maxfev=300, restarts=1)
    saved = DR.COMPILED_FILTER
    try:
        DR.COMPILED_FILTER = False
        slow = DR.fit_two_component(Y, maxfev=300, restarts=1)
    finally:
        DR.COMPILED_FILTER = saved
    assert repr(fast) == repr(slow)


def test_compiling_the_filter_logs_nothing_below_a_warning():
    """numba logs its own type checking at DEBUG (38,760 lines on the first fit, 2026-09-25), and the
    server logs at DEBUG, so every worker's first design-rule fit flooded its log."""
    import logging
    root = logging.getLogger()
    before = root.level
    root.setLevel(logging.DEBUG)                 # what the server's logging configuration does
    try:
        assert logging.getLogger("numba").getEffectiveLevel() >= logging.WARNING
    finally:
        root.setLevel(before)
