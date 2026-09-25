"""Speed-up item 4 (`artifacts/research_2026-09-25_options/06_remaining_speed_ups.md` #4; decision
269's pattern applied to the CL-DBS simulation's controller loop): the compiled loop returns
EXACTLY what the numpy loop returns.

Unlike the design rule's two-component filter, nothing in this loop sums across the K replicates a
call runs at once, so no pairwise-summation kernel is needed here to match a numpy reduction inside
the loop: every step is elementwise (add, subtract, multiply, divide, comparison, clip), and the
reductions over time that follow the loop (the fractions of time at a limit, the mean amplitude,
and the rest) run in plain numpy on the arrays the loop filled, in both the numpy and the compiled
case, so they inherit numpy's own reduction order automatically.

This test holds the compiled loop's output arrays and running counts equal to the numpy loop's on
constructed series exercising every curve kind (none, a straight line either sign, the quadratic on
both sides of an established peak, and a quadratic with no established peak), gaps in both the
power and the amplitude, and every controller branch (onset suppression, detection blanking, both
transition directions, saturation at a limit); and holds the whole `simulate_series` answer equal
too. Skipped where numba is not installed (CI); the container has it (decision 271).
"""
import numpy as np
import pytest

pytest.importorskip("numba")

try:
    from modules.ClosedLoopDeployment import simulation as S, types as T
    from modules.StimOptimizer.routines import amplitude_response as AR
except ImportError:                                              # pragma: no cover
    from ClosedLoopDeployment import simulation as S, types as T
    from StimOptimizer.routines import amplitude_response as AR


# --------------------------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------------------------
def _plan(upper=120.0, lower=80.0, lo=1.0, hi=3.0):
    return T.ThresholdPlan(upper=upper, lower=lower, scale="linear",
                           capture_amp_low=lo, capture_amp_high=hi)


def _series(n, seed, amp_lo, amp_hi, dt=1.2, gap_frac=0.1):
    """A band-power series crossing both thresholds repeatedly, an amplitude series stepping
    between the plan's own limits, and gaps of missing estimates in both -- a missing power sample
    must hold the controller's state, a missing amplitude sample must fall back to the amplitude
    the controller itself is commanding."""
    rng = np.random.default_rng(seed)
    p = 100.0 + 35.0 * np.sin(np.linspace(0, 6 * np.pi, n)) + rng.normal(0, 6.0, n)
    a = amp_lo + (amp_hi - amp_lo) * (0.5 + 0.5 * np.sin(np.linspace(0, 4 * np.pi, n) + 1.0))
    t = np.arange(n) * dt
    p = p.copy()
    a = a.copy()
    p[rng.random(n) < gap_frac] = np.nan
    a[rng.random(n) < gap_frac] = np.nan
    return t, p, a


def _curve_bank():
    """One of each curve kind the controller loop has to evaluate: no response, a rising and a
    falling straight line, a peaked quadratic (the post-peak break falls inside the capture range,
    so `has_post` is True) and a quadratic with no established peak (`peak_mA` is NaN, so
    `has_post` stays False throughout)."""
    return [
        AR.ResponseCurve.zero(),
        AR.ResponseCurve.linear(+55.0),
        AR.ResponseCurve.linear(-40.0),
        AR.ResponseCurve(kind=AR.QUADRATIC, quad_per_mA2=-30.0, quad_lin_per_mA=90.0,
                         peak_mA=2.0, post_peak_slope_per_mA=-25.0),
        AR.ResponseCurve(kind=AR.QUADRATIC, quad_per_mA2=8.0, quad_lin_per_mA=-5.0,
                         peak_mA=float("nan"), post_peak_slope_per_mA=float("nan")),
    ]


def _compare(a, b):
    """Field count and difference count, recursively: dicts and lists by key/index, arrays
    element for element (NaN equal to NaN), everything else by equality (project convention:
    check the values, never the shape -- CLAUDE.md §8 rule 11)."""
    if isinstance(a, dict):
        compared = differing = 0
        for key in a:
            c, d = _compare(a[key], b[key])
            compared += c
            differing += d
        return compared, differing
    if isinstance(a, (list, tuple)):
        compared = differing = 0
        for x, y in zip(a, b):
            c, d = _compare(x, y)
            compared += c
            differing += d
        return compared, differing
    if isinstance(a, np.ndarray):
        b = np.asarray(b)
        if a.dtype.kind in "fc":
            bf = b.astype(float)
            same = (a == bf) | (np.isnan(a) & np.isnan(bf))
        else:
            same = (a == b)
        return int(a.size), int(a.size - int(np.count_nonzero(same)))
    if isinstance(a, float) and isinstance(b, float) and np.isnan(a) and np.isnan(b):
        return 1, 0
    return 1, int(a != b)


# --------------------------------------------------------------------------------------------
# 1. the compiled loop's own arrays and running counts, many constructed series
# --------------------------------------------------------------------------------------------
def test_the_compiled_loop_returns_exactly_the_numpy_loops_arrays_and_counts():
    curves = _curve_bank()
    bank = S._bank(curves)
    plan = _plan()
    upper, lower = float(plan.upper), float(plan.lower)
    amp_low, amp_high = float(plan.capture_amp_low), float(plan.capture_amp_high)
    onset_steps, blank_steps = 4, 3
    rate_up, rate_down = 2.0, 1.5
    target_hi, target_lo = amp_high, amp_low
    dt = 1.2
    amp_init = 0.5 * (amp_low + amp_high)

    assert S.COMPILED_CONTROLLER, "numba is installed, so the compiled loop must be the one reachable"

    compared = differing = 0
    # Nine constructed recordings, not eight: with 8 (n = 350 + 17*seed, K = 5 replicates), the
    # loop's own arrays and counts give exactly 49,308 compared values by construction (3*K*n summed
    # over the 8 series, plus 4*K + 1 running counts each) -- true and correct, but short of the
    # 50,000-value floor this test originally asserted, which an adversarial review caught failing
    # under the container's pinned numba (0.61.2) with `compared: 49308`. The ninth series restores
    # the margin honestly rather than lowering the floor to match the smaller number.
    for seed in range(9):
        n = 350 + 17 * seed
        _, p, a_obs = _series(n, seed, amp_low, amp_high)
        rng = np.random.default_rng(1000 + seed)
        alpha = rng.uniform(0.05, 1.0, bank["K"])
        got_np = S._run_controller_loop_numpy(bank, p, a_obs, alpha, dt, upper, lower, amp_low,
                                              amp_high, amp_init, rate_up, rate_down, onset_steps,
                                              blank_steps, target_hi, target_lo)
        got_kernel = S._run_controller_loop(bank, p, a_obs, alpha, dt, upper, lower, amp_low,
                                            amp_high, amp_init, rate_up, rate_down, onset_steps,
                                            blank_steps, target_hi, target_lo)
        c, d = _compare(list(got_np), list(got_kernel))
        compared += c
        differing += d
    assert compared > 50_000, compared
    assert differing == 0, (compared, differing)


# --------------------------------------------------------------------------------------------
# 2. the whole `simulate_series` answer, forced compiled against forced numpy
# --------------------------------------------------------------------------------------------
def test_the_whole_simulate_series_answer_is_the_same_with_the_compiled_loop():
    curves = _curve_bank()
    plan = _plan()
    t, p, a_obs = _series(700, seed=3, amp_lo=float(plan.capture_amp_low),
                          amp_hi=float(plan.capture_amp_high))
    saved = S.COMPILED_CONTROLLER
    try:
        S.COMPILED_CONTROLLER = True
        fast = S.simulate_series(t, p, a_obs, plan, curves, tau_s=8.0)
        S.COMPILED_CONTROLLER = False
        slow = S.simulate_series(t, p, a_obs, plan, curves, tau_s=8.0)
    finally:
        S.COMPILED_CONTROLLER = saved
    assert fast["n_missing"] > 0, "the fixture must exercise the missing-estimate hold"
    compared, differing = _compare(fast, slow)
    assert compared > 5_000, compared
    assert differing == 0, (compared, differing)


def test_the_whole_simulate_segments_answer_is_the_same_with_the_compiled_loop():
    """`simulate_segments` re-enters `simulate_series` once per contiguous stretch (decision 269's
    equality proof needs the whole path a report actually takes, not only the innermost loop)."""
    curves = _curve_bank()
    plan = _plan()
    t1, p1, a1 = _series(400, seed=11, amp_lo=float(plan.capture_amp_low),
                         amp_hi=float(plan.capture_amp_high))
    t2, p2, a2 = _series(500, seed=12, amp_lo=float(plan.capture_amp_low),
                         amp_hi=float(plan.capture_amp_high))
    t = np.concatenate([t1, t2 + t1[-1] + 3600.0])
    p = np.concatenate([p1, p2])
    a = np.concatenate([a1, a2])
    saved = S.COMPILED_CONTROLLER
    try:
        S.COMPILED_CONTROLLER = True
        fast = S.simulate_segments(t, p, a, plan, curves, tau_s=8.0)
        S.COMPILED_CONTROLLER = False
        slow = S.simulate_segments(t, p, a, plan, curves, tau_s=8.0)
    finally:
        S.COMPILED_CONTROLLER = saved
    assert fast["refused"] is False and fast["n_segments_used"] == 2
    compared, differing = _compare(fast, slow)
    assert compared > 500, compared
    assert differing == 0, (compared, differing)


# --------------------------------------------------------------------------------------------
# 3. numba's own DEBUG logging is quiet (decision 269: 38,760 lines on the first fit)
# --------------------------------------------------------------------------------------------
def test_compiling_the_loop_logs_nothing_below_a_warning():
    import logging
    root = logging.getLogger()
    before = root.level
    root.setLevel(logging.DEBUG)                 # what the server's logging configuration does
    try:
        assert logging.getLogger("numba").getEffectiveLevel() >= logging.WARNING
    finally:
        root.setLevel(before)
