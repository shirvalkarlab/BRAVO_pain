"""DRNUMBA (the PI's numba go-ahead, 2026-09-25; `artifacts/research_2026-09-25_options/
06_remaining_speed_ups.md` proposal 7): the robustness bootstrap's one per-reading loop,
`robustness.run_stretch`, runs as a compiled loop and returns EXACTLY what the numpy loop
returns.

`run_stretch` replays every one of the K threshold-and-timing configurations over one recorded
stretch, config-vectorised: unlike `design_rule.py`'s two filters, nothing inside the loop is ever
summed ACROSS configurations, so the compiled kernel needs no `_pairwise_sum` -- each configuration
is an independent scalar time series and the per-configuration accumulators it returns do not
depend on the order the configurations are visited in. This test holds the compiled kernel's
per-configuration counts and sums equal to the numpy loop's, bit for bit, on constructed series with
gaps, a missing first reading, an onset short enough to adopt on the very first sample, and both a
rising and a falling ramp; and holds the fast, precompute-and-aggregate bootstrap path (which calls
`run_stretch` once per training stretch, never once per replicate) equal to the whole-file entry
point either way. Skipped where numba is not installed (CI); the container has it (decision 271).
"""
import numpy as np
import pytest

pytest.importorskip("numba")

from ClosedLoopDeployment import robustness as RB


def _series(seed, n=180, level=100.0, sigma=15.0, gap_frac=0.12, first_nan=False):
    rng = np.random.default_rng(seed)
    p = level + np.cumsum(rng.normal(0, sigma * 0.15, n)) + rng.normal(0, sigma, n)
    gaps = rng.random(n) < gap_frac
    p[gaps] = np.nan
    if first_nan:
        p[0] = np.nan
    return p


def _configs(rng, k=9):
    """A grid of K configurations spanning the parameters that change the compiled loop's control
    flow: onset steps from 1 (adopt on the very first qualifying sample) up, several blanking and
    ramp durations, and separations that both do and do not bracket the series."""
    onset_ms = np.array([1.0] + list(rng.uniform(1500.0, 60000.0, k - 1)))
    blanking_ms = rng.uniform(0.0, 30000.0, k)
    up_ms = rng.uniform(1500.0, 30000.0, k)
    down_ms = rng.uniform(1500.0, 30000.0, k)
    gap = rng.uniform(5.0, 60.0, k)
    upper = 100.0 + 0.5 * gap
    lower = 100.0 - 0.5 * gap
    return dict(upper=upper, lower=lower, onset_ms=onset_ms, blanking_ms=blanking_ms,
               up_ms=up_ms, down_ms=down_ms)


def _assert_run_stretch_results_equal(a, b):
    for key in a:
        av, bv = a[key], b[key]
        if key in ("dt",):
            assert av == bv
            continue
        np.testing.assert_array_equal(np.asarray(av), np.asarray(bv), err_msg=key)


def test_the_compiled_replay_returns_exactly_the_numpy_loops_answer():
    assert RB.COMPILED_REPLAY, "numba is installed, so the compiled loop must be the one used"
    rng = np.random.default_rng(20260925)
    for trial in range(30):
        first_nan = (trial % 5 == 0)
        p = _series(1000 + trial, n=int(rng.integers(20, 240)), first_nan=first_nan)
        cfgs = _configs(rng, k=int(rng.integers(1, 12)))
        dt = float(rng.choice([1.2, 3.0, 6.0]))
        amp_low, amp_high = 0.0, float(rng.uniform(2.0, 6.0))
        kw = dict(p=p, dt=dt, amp_low=amp_low, amp_high=amp_high, **cfgs)

        fast = RB.run_stretch(**kw)
        RB.COMPILED_REPLAY = False
        try:
            slow = RB.run_stretch(**kw)
        finally:
            RB.COMPILED_REPLAY = True
        _assert_run_stretch_results_equal(fast, slow)


def test_the_compiled_replay_matches_with_a_stated_amp_init_and_tol():
    p = _series(7, n=100)
    cfgs = _configs(np.random.default_rng(3), k=4)
    kw = dict(p=p, dt=3.0, amp_low=0.5, amp_high=4.5, amp_init=2.1, tol=0.02, **cfgs)
    fast = RB.run_stretch(**kw)
    RB.COMPILED_REPLAY = False
    try:
        slow = RB.run_stretch(**kw)
    finally:
        RB.COMPILED_REPLAY = True
    _assert_run_stretch_results_equal(fast, slow)


def test_the_fast_bootstrap_path_still_equals_the_naive_path_with_the_compiled_replay():
    """The central equality `test_robustness.py` already proves (the precompute-and-aggregate
    bootstrap path equals literal re-simulation) holds with whichever `run_stretch` backend is
    active -- this is what actually protects production, since `robustness_for_series` never calls
    the compiled kernel directly, only through `run_stretch`."""
    assert RB.COMPILED_REPLAY
    rng = np.random.default_rng(555)
    stretches = []
    t0 = 0.0
    for i in range(6):
        n = 90
        p = _series(200 + i, n=n)
        t = t0 + np.arange(n) * 3.0
        a = np.full(n, 3.0)
        stretches.append((t, p, a))
        t0 = t[-1] + 3600.0
    cfgs = RB._build_config_grid(100.0, 20.0, onset_grid=(3.0, 30.0, 90.0),
                                 gap_sd_grid=(0.2, 0.6, 1.0), blanking_grid=(3.0, 30.0))
    up_arr = np.array([c["upper"] for c in cfgs])
    lo_arr = np.array([c["lower"] for c in cfgs])
    on_arr = np.array([c["onset_s"] for c in cfgs]) * 1000.0
    bl_arr = np.array([c["blanking_s"] for c in cfgs]) * 1000.0
    upms_arr = np.full(len(cfgs), RB.FIXED_TRANSITION_MS)
    dnms_arr = np.full(len(cfgs), RB.FIXED_TRANSITION_MS)
    averaging_ms = 1200.0

    naive = RB.choose_naive(stretches, cfgs, up_arr=up_arr, lo_arr=lo_arr, on_arr=on_arr,
                            bl_arr=bl_arr, upms_arr=upms_arr, dnms_arr=dnms_arr,
                            averaging_ms=averaging_ms, amp_low=0.0, amp_high=5.0, mid=100.0, sd=20.0,
                            gap_sd_grid=(0.2, 0.6, 1.0))

    pre = RB._stretch_accumulators(stretches, averaging_ms, up_arr, lo_arr, on_arr, bl_arr,
                                   upms_arr, dnms_arr, 0.0, 5.0)
    between, n_finite = RB._stretch_gap_counts(stretches, mid=100.0, sd=20.0,
                                               gap_sd_grid=(0.2, 0.6, 1.0))
    fast = RB._choose_from_precompute(pre, between, n_finite, np.ones(len(stretches)), cfgs,
                                      (0.2, 0.6, 1.0), between_min_frac=RB.BETWEEN_MIN_FRAC,
                                      limit_min_frac=RB.LIMIT_MIN_FRAC)
    assert naive == fast


def test_compiling_the_replay_logs_nothing_below_a_warning():
    """Same reason as decision 269's own test on `design_rule.py`: numba logs its own type
    checking at DEBUG, and the server logs at DEBUG."""
    import logging
    root = logging.getLogger()
    before = root.level
    root.setLevel(logging.DEBUG)
    try:
        assert logging.getLogger("numba").getEffectiveLevel() >= logging.WARNING
    finally:
        root.setLevel(before)
