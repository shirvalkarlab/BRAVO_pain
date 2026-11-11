"""Robustness of the design rule as an interval (T5, 2026-09-13; robustness.py), ported from the
method contest's `fopdt_lambda` entry (decision 150, `artifacts/contest_2026-09-13_SYNTHESIS.md`
section 4, task 5).

The central claim this file exists to prove is not a scientific one -- it is that the fast,
precompute-and-aggregate bootstrap path (`_stretch_accumulators` / `_choose_from_precompute`)
computes EXACTLY what a literal re-simulation per replicate (`choose_naive`, which calls
`run_many` -> `run_stretch`, doing real per-reading work) would have computed, including when a
resample draws the same stretch more than once. Every test checks a VALUE against either a
known-by-construction answer or the naive path's own answer -- never a shape, never "it returned a
dict", per this project's own rule (CLAUDE.md §7 rule 11).

Merged here 2026-10-05: test_robustness_compiled_replay.py, test_robustness_keeps_each_candidate.py.
"""
import importlib.util

import numpy as np
import pytest

try:
    from modules.ClosedLoopDeployment import robustness as RB
    from modules.ClosedLoopDeployment import prescription as PR, types as TY
except ImportError:                                              # pragma: no cover
    from ClosedLoopDeployment import robustness as RB
    from ClosedLoopDeployment import prescription as PR, types as TY

PA = pytest.importorskip("StimOptimizer.routines.percept_adaptive")


# ------------------------------------------------------------------------------------------------
# fixtures: constructed stretches with a known relationship to a pair of thresholds
# ------------------------------------------------------------------------------------------------
def _stretch(n, level, sigma, seed, dt=3.0, t0=0.0):
    rng = np.random.default_rng(seed)
    p = level + rng.normal(0.0, sigma, n)
    t = t0 + np.arange(n) * dt
    a = np.full(n, 3.0)
    return t, p, a


def _oscillating_stretch(n, mid, amplitude, sigma, seed, dt=3.0, t0=0.0, period=40):
    rng = np.random.default_rng(seed)
    base = mid + amplitude * np.sin(2.0 * np.pi * np.arange(n) / period)
    p = base + rng.normal(0.0, sigma, n)
    t = t0 + np.arange(n) * dt
    a = np.full(n, 3.0)
    return t, p, a


def _some_stretches(kind="flat", n_stretches=6, n=80, mid=100.0, seed0=1):
    """A handful of independent stretches (well separated in time so `regrid_stretches` splits
    them), each with its own seed."""
    out = []
    t0 = 0.0
    for i in range(n_stretches):
        if kind == "flat":
            t, p, a = _stretch(n, mid, 12.0, seed0 + i, t0=t0)
        else:
            t, p, a = _oscillating_stretch(n, mid, 25.0, 6.0, seed0 + i, t0=t0)
        out.append((t, p, a))
        t0 = t[-1] + 3600.0            # a one-hour gap: a new stretch on the next iteration
    return out


def _concat(stretches):
    t = np.concatenate([s[0] for s in stretches])
    p = np.concatenate([s[1] for s in stretches])
    a = np.concatenate([s[2] for s in stretches])
    return t, p, a


# ------------------------------------------------------------------------------------------------
# the config grid: shape and the fixed transition
# ------------------------------------------------------------------------------------------------
def test_default_grid_has_320_configurations_none_with_an_onset_the_tablet_refuses():
    """Was 576 (18 onsets to 120 s). The PI's instruction of 2026-09-15: evaluate onsets only up to
    the tablet's 30 s maximum, so the eight onsets above it are gone: 10 x 8 x 4."""
    cfgs = RB._build_config_grid(100.0, 20.0, RB.ONSET_GRID_S, RB.GAP_SD_GRID, RB.BLANKING_GRID_S)
    assert len(cfgs) == len(RB.ONSET_GRID_S) * len(RB.GAP_SD_GRID) * len(RB.BLANKING_GRID_S)
    assert len(cfgs) == 320


def test_the_onset_grid_stops_at_the_tablets_maximum_read_from_the_one_home():
    from StimOptimizer.routines import percept_adaptive as PA
    assert max(RB.ONSET_GRID_S) == PA.ONSET_RANGE_DUAL_MS[1] / 1000.0 == 30.0
    assert RB.ONSET_GRID_S == (3, 6, 9, 12, 15, 18, 21, 24, 27, 30)
    assert RB.RULE_VERSION != "v1_block_bootstrap_port", "a stored table built on the old grid must not be served"


def test_fixed_transition_is_3000_ms():
    assert RB.FIXED_TRANSITION_MS == 3000.0


def test_config_grid_thresholds_are_centred_on_mid():
    cfgs = RB._build_config_grid(150.0, 40.0, (30.0,), (0.5,), (3.0,))
    c = cfgs[0]
    assert c["upper"] == pytest.approx(150.0 + 0.5 * 0.5 * 40.0)
    assert c["lower"] == pytest.approx(150.0 - 0.5 * 0.5 * 40.0)
    assert c["upper"] - c["lower"] == pytest.approx(0.5 * 40.0)


# ------------------------------------------------------------------------------------------------
# run_stretch: known-by-construction controller behaviour
# ------------------------------------------------------------------------------------------------
def test_run_stretch_stays_at_the_low_limit_when_power_never_leaves_below():
    n = 40
    p = np.full(n, 10.0)                # always below any reasonable threshold
    r = RB.run_stretch(p, 3.0, upper=np.array([100.0]), lower=np.array([50.0]),
                       onset_ms=np.array([3000.0]), blanking_ms=np.array([3000.0]),
                       up_ms=np.array([3000.0]), down_ms=np.array([3000.0]), amp_low=0.0,
                       amp_high=5.0)
    # the controller ramps toward the low limit and, given enough steps at a 3 s/3 s ramp over a
    # 5 mA span (rate 5/3 mA per 3 s step), reaches it well within 40 steps.
    assert r["sum_at_lower"][0] / r["n_steps"] > 0.5
    assert r["sum_above"][0] == 0
    assert r["n_transitions"][0] >= 1


def test_run_stretch_never_transitions_when_power_never_crosses():
    n = 40
    p = np.full(n, 75.0)                # always strictly between 50 and 100
    r = RB.run_stretch(p, 3.0, upper=np.array([100.0]), lower=np.array([50.0]),
                       onset_ms=np.array([3000.0]), blanking_ms=np.array([3000.0]),
                       up_ms=np.array([3000.0]), down_ms=np.array([3000.0]), amp_low=0.0,
                       amp_high=5.0)
    assert r["n_transitions"][0] == 0
    assert r["sum_between"][0] == n


# ------------------------------------------------------------------------------------------------
# frac_between_all / _stretch_gap_counts / _frac_between_from_precompute agree exactly
# ------------------------------------------------------------------------------------------------
def test_frac_between_precompute_matches_the_naive_function_at_weights_of_one():
    stretches = _some_stretches("flat", n_stretches=5, seed0=7)
    mid, sd = 100.0, 15.0
    naive = RB.frac_between_all(stretches, mid=mid, sd=sd, gap_sd_grid=RB.GAP_SD_GRID)
    between, n_finite = RB._stretch_gap_counts(stretches, mid=mid, sd=sd,
                                               gap_sd_grid=RB.GAP_SD_GRID)
    fast = RB._frac_between_from_precompute(between, n_finite, np.ones(len(stretches)),
                                            RB.GAP_SD_GRID)
    for g in RB.GAP_SD_GRID:
        assert fast[g] == pytest.approx(naive[g])


def test_frac_between_precompute_matches_a_duplicated_naive_group():
    """A resample that draws stretch 0 twice and stretch 2 once must equal the weighted-sum
    answer with weights [2, 0, 1, 0, 0]."""
    stretches = _some_stretches("flat", n_stretches=5, seed0=11)
    mid, sd = 100.0, 15.0
    group = [stretches[0], stretches[0], stretches[2]]
    naive = RB.frac_between_all(group, mid=mid, sd=sd, gap_sd_grid=RB.GAP_SD_GRID)
    between, n_finite = RB._stretch_gap_counts(stretches, mid=mid, sd=sd,
                                               gap_sd_grid=RB.GAP_SD_GRID)
    weights = np.array([2.0, 0.0, 1.0, 0.0, 0.0])
    fast = RB._frac_between_from_precompute(between, n_finite, weights, RB.GAP_SD_GRID)
    for g in RB.GAP_SD_GRID:
        assert fast[g] == pytest.approx(naive[g])


# ------------------------------------------------------------------------------------------------
# THE CENTRAL EQUALITY: the fast precompute-and-aggregate path equals the naive, literal
# re-simulation path -- at weights of one, and at weights with real duplicates
# ------------------------------------------------------------------------------------------------
def _small_config_arrays(mid, sd):
    cfgs = RB._build_config_grid(mid, sd, onset_grid=(3.0, 30.0, 90.0),
                                 gap_sd_grid=(0.2, 0.6, 1.0), blanking_grid=(3.0, 30.0))
    up_arr = np.array([c["upper"] for c in cfgs])
    lo_arr = np.array([c["lower"] for c in cfgs])
    on_arr = np.array([c["onset_s"] for c in cfgs]) * 1000.0
    bl_arr = np.array([c["blanking_s"] for c in cfgs]) * 1000.0
    upms_arr = np.full(len(cfgs), RB.FIXED_TRANSITION_MS)
    dnms_arr = np.full(len(cfgs), RB.FIXED_TRANSITION_MS)
    return cfgs, up_arr, lo_arr, on_arr, bl_arr, upms_arr, dnms_arr


def test_fast_path_equals_naive_path_at_weights_of_one():
    stretches = _some_stretches("oscillating", n_stretches=6, n=120, seed0=3)
    mid, sd = 100.0, float(np.nanstd(_concat(stretches)[1]))
    cfgs, up_arr, lo_arr, on_arr, bl_arr, upms_arr, dnms_arr = _small_config_arrays(mid, sd)
    averaging_ms = 1200.0

    naive = RB.choose_naive(stretches, cfgs, up_arr=up_arr, lo_arr=lo_arr, on_arr=on_arr,
                            bl_arr=bl_arr, upms_arr=upms_arr, dnms_arr=dnms_arr,
                            averaging_ms=averaging_ms, amp_low=0.0, amp_high=5.0, mid=mid, sd=sd,
                            gap_sd_grid=(0.2, 0.6, 1.0))

    pre = RB._stretch_accumulators(stretches, averaging_ms, up_arr, lo_arr, on_arr, bl_arr,
                                   upms_arr, dnms_arr, 0.0, 5.0)
    gap_between, gap_n_finite = RB._stretch_gap_counts(stretches, mid=mid, sd=sd,
                                                       gap_sd_grid=(0.2, 0.6, 1.0))
    fast = RB._choose_from_precompute(pre, gap_between, gap_n_finite, np.ones(len(stretches)),
                                      cfgs, (0.2, 0.6, 1.0),
                                      between_min_frac=RB.BETWEEN_MIN_FRAC,
                                      limit_min_frac=RB.LIMIT_MIN_FRAC)

    assert naive is not None
    assert fast is not None
    for key in ("onset_s", "blanking_s", "gap_sd", "gap_units", "upper", "lower",
                "transitions_per_hour", "frac_at_upper", "frac_at_lower", "frac_readings_between"):
        assert fast[key] == pytest.approx(naive[key], rel=1e-9, abs=1e-9), key


def test_fast_path_equals_naive_path_with_a_repeated_stretch():
    """The equality that actually discriminates the two implementations: a resample that draws
    one stretch twice and leaves two out entirely."""
    stretches = _some_stretches("oscillating", n_stretches=6, n=120, seed0=5)
    mid, sd = 100.0, float(np.nanstd(_concat(stretches)[1]))
    cfgs, up_arr, lo_arr, on_arr, bl_arr, upms_arr, dnms_arr = _small_config_arrays(mid, sd)
    averaging_ms = 1200.0

    weights = np.array([2.0, 0.0, 1.0, 3.0, 0.0, 1.0])
    group = []
    for i, w in enumerate(weights):
        group += [stretches[i]] * int(w)

    naive = RB.choose_naive(group, cfgs, up_arr=up_arr, lo_arr=lo_arr, on_arr=on_arr,
                            bl_arr=bl_arr, upms_arr=upms_arr, dnms_arr=dnms_arr,
                            averaging_ms=averaging_ms, amp_low=0.0, amp_high=5.0, mid=mid, sd=sd,
                            gap_sd_grid=(0.2, 0.6, 1.0))

    pre = RB._stretch_accumulators(stretches, averaging_ms, up_arr, lo_arr, on_arr, bl_arr,
                                   upms_arr, dnms_arr, 0.0, 5.0)
    gap_between, gap_n_finite = RB._stretch_gap_counts(stretches, mid=mid, sd=sd,
                                                       gap_sd_grid=(0.2, 0.6, 1.0))
    fast = RB._choose_from_precompute(pre, gap_between, gap_n_finite, weights, cfgs,
                                      (0.2, 0.6, 1.0), between_min_frac=RB.BETWEEN_MIN_FRAC,
                                      limit_min_frac=RB.LIMIT_MIN_FRAC)

    assert naive is not None
    assert fast is not None
    for key in ("onset_s", "blanking_s", "gap_sd", "gap_units", "transitions_per_hour",
                "frac_at_upper", "frac_at_lower", "frac_readings_between"):
        assert fast[key] == pytest.approx(naive[key], rel=1e-9, abs=1e-9), key


def test_fast_path_matches_naive_over_many_random_resamples():
    """200 independently drawn weight vectors, each checked against the naive re-simulation of the
    identical (possibly repeated) group of stretches -- the same property the production bootstrap
    relies on, exercised directly rather than only through one or two hand-picked cases."""
    stretches = _some_stretches("oscillating", n_stretches=5, n=90, seed0=9)
    mid, sd = 100.0, float(np.nanstd(_concat(stretches)[1]))
    cfgs, up_arr, lo_arr, on_arr, bl_arr, upms_arr, dnms_arr = _small_config_arrays(mid, sd)
    averaging_ms = 1200.0
    pre = RB._stretch_accumulators(stretches, averaging_ms, up_arr, lo_arr, on_arr, bl_arr,
                                   upms_arr, dnms_arr, 0.0, 5.0)
    gap_between, gap_n_finite = RB._stretch_gap_counts(stretches, mid=mid, sd=sd,
                                                       gap_sd_grid=(0.2, 0.6, 1.0))
    rng = np.random.default_rng(42)
    n_checked = 0
    for _ in range(15):
        idx = rng.integers(0, len(stretches), len(stretches))
        weights = np.bincount(idx, minlength=len(stretches)).astype(float)
        group = [stretches[i] for i in idx]
        naive = RB.choose_naive(group, cfgs, up_arr=up_arr, lo_arr=lo_arr, on_arr=on_arr,
                                bl_arr=bl_arr, upms_arr=upms_arr, dnms_arr=dnms_arr,
                                averaging_ms=averaging_ms, amp_low=0.0, amp_high=5.0, mid=mid,
                                sd=sd, gap_sd_grid=(0.2, 0.6, 1.0))
        fast = RB._choose_from_precompute(pre, gap_between, gap_n_finite, weights, cfgs,
                                          (0.2, 0.6, 1.0), between_min_frac=RB.BETWEEN_MIN_FRAC,
                                          limit_min_frac=RB.LIMIT_MIN_FRAC)
        assert (naive is None) == (fast is None)
        if naive is not None:
            n_checked += 1
            for key in ("onset_s", "blanking_s", "gap_sd", "transitions_per_hour"):
                assert fast[key] == pytest.approx(naive[key], rel=1e-9, abs=1e-9), (key, idx)
    assert n_checked > 0        # the equality was actually exercised on at least one feasible draw


# ------------------------------------------------------------------------------------------------
# robustness_for_series: refusal paths, by construction
# ------------------------------------------------------------------------------------------------
_SHORT = (np.array([0.0, 3.0]), np.array([100.0, 101.0]), np.array([3.0, 3.0]))


@pytest.mark.parametrize("series,kw,reason", [
    ("stretch", dict(upper=None, lower=80.0, amp_low=0.0, amp_high=5.0), "thresholds"),
    ("stretch", dict(upper=120.0, lower=80.0, amp_low=None, amp_high=5.0), "amplitude limits"),
    ("two_samples", dict(upper=120.0, lower=80.0, amp_low=0.0, amp_high=5.0), "too few"),
], ids=["no_thresholds", "no_amplitude_limits", "too_few_samples"])
def test_refuses_with_a_reason(series, kw, reason):
    t, p, a = _stretch(20, 100.0, 10.0, 1) if series == "stretch" else _SHORT
    out = RB.robustness_for_series(t, p, a, **kw)
    assert out["refused"] is True
    assert reason in out["reason"]


# ------------------------------------------------------------------------------------------------
# robustness_for_series: end to end on constructed data, values checked for internal consistency
# ------------------------------------------------------------------------------------------------
def test_end_to_end_reports_an_interval_drawn_from_the_grid():
    stretches = _some_stretches("oscillating", n_stretches=12, n=150, mid=100.0, seed0=101)
    t, p, a = _concat(stretches)
    out = RB.robustness_for_series(t, p, a, upper=125.0, lower=75.0, amp_low=0.0, amp_high=5.0,
                                   n_boot=40, seed=123,
                                   onset_grid=(3.0, 15.0, 30.0, 60.0, 90.0),
                                   gap_sd_grid=(0.2, 0.5, 0.8, 1.0),
                                   blanking_grid=(3.0, 30.0))
    assert out["refused"] is False
    assert out["n_boot"] == 40
    assert out["n_train_stretches"] + out["n_test_stretches"] == 12
    # enough of the feasible grid should be found for a real interval, given a genuinely
    # oscillating series that visits both sides of the pair.
    assert out["n_feasible"] > 0
    onset_i = out["intervals"]["onset_s"]
    assert onset_i is not None
    assert onset_i["lower"] <= onset_i["median"] <= onset_i["upper"]
    assert onset_i["lower"] in (3.0, 15.0, 30.0, 60.0, 90.0)
    assert onset_i["upper"] in (3.0, 15.0, 30.0, 60.0, 90.0)
    gap_i = out["intervals"]["gap_units"]
    assert gap_i is not None
    assert gap_i["lower"] <= gap_i["upper"]


# ------------------------------------------------------------------------------------------------
# robustness_note / attach_robustness: the prescription-card wiring
# ------------------------------------------------------------------------------------------------
def test_robustness_note_states_the_onset_interval_by_construction():
    payload = {"refused": False, "n_boot": 200, "n_feasible": 150,
              "intervals": {"onset_s": {"lower": 36.0, "upper": 90.0, "median": 45.0},
                            "blanking_s": {"lower": 3.0, "upper": 30.0, "median": 15.0},
                            "gap_units": {"lower": 10.0, "upper": 40.0, "median": 20.0}}}
    note = PR.robustness_note(payload)
    assert note is not None
    assert "36" in note and "90" in note
    assert "36–90 s are one recommendation" in note
    assert "150" in note and "200" in note


def test_attach_robustness_touches_only_onset_duration_fields():
    plan = TY.ThresholdPlan(upper=210.579, lower=161.903, capture_amp_low=1.4, capture_amp_high=4.8)
    cand = {"channel": "ONE_THREE_LEFT", "center_hz": 24.5, "band_width_hz": 5.0}
    prescriptions = PR.prescribe_all_modes(threshold_plan=plan, candidate=cand,
                                           power_series=None, validated_hemispheres=("Left",),
                                           configuring_both_hemispheres=False)
    payload = {"refused": False, "n_boot": 200, "n_feasible": 120,
              "intervals": {"onset_s": {"lower": 36.0, "upper": 90.0, "median": 45.0}}}
    out = PR.attach_robustness(prescriptions, payload)
    dual = out["modes"][PR.PA.DUAL]
    touched = {f.name for f in dual.fields if f.robustness_note is not None}
    assert touched == {"Upper onset duration", "Lower onset duration"}
    for f in dual.fields:
        if f.name not in touched:
            assert f.robustness_note is None
    single = out["modes"][PR.PA.SINGLE]
    single_touched = {f.name for f in single.fields if f.robustness_note is not None}
    assert single_touched == {"Onset duration"}


def test_default_averaging_is_the_device_white_paper_dual_threshold_default():
    stretches = _some_stretches("flat", n_stretches=4, seed0=2)
    t, p, a = _concat(stretches)
    out = RB.robustness_for_series(t, p, a, upper=125.0, lower=75.0, amp_low=0.0, amp_high=5.0,
                                   n_boot=5,
                                   onset_grid=(30.0,), gap_sd_grid=(0.5,), blanking_grid=(3.0,))
    assert out["refused"] is False
    try:
        from modules.ClosedLoopDeployment import replay as R
    except ImportError:                                          # pragma: no cover
        from ClosedLoopDeployment import replay as R
    assert out["averaging_ms"] == pytest.approx(float(R.DEFAULT_PARAMS["averaging_ms"]))


def test_robustness_note_names_the_part_of_the_interval_that_cannot_be_entered():
    """The tablet's Dual onset maximum is 30 s (2026-09-15). The bootstrap grid searches to 120 s,
    so an interval can run past what a clinician can type -- 36-90 s on L 1-3+, 27-60 s on the
    committed band. The note must say so rather than recommend an unenterable value."""
    note = PR.robustness_note({"refused": False, "n_boot": 200, "n_feasible": 159,
                               "intervals": {"onset_s": {"lower": 27.0, "upper": 60.0, "median": 48.0}}})
    assert "30 s" in note and "cannot be entered" in note
    inside = PR.robustness_note({"refused": False, "n_boot": 200, "n_feasible": 200,
                                 "intervals": {"onset_s": {"lower": 9.0, "upper": 27.0, "median": 15.0}}})
    assert "cannot be entered" not in inside

# ------------------------------------------------------------------------------------------------
# The compiled replay (from test_robustness_compiled_replay.py, merged 2026-10-05)
# ------------------------------------------------------------------------------------------------
# DRNUMBA (the PI's numba go-ahead, 2026-09-25; `artifacts/research_2026-09-25_options/
# 06_remaining_speed_ups.md` proposal 7): the robustness bootstrap's one per-reading loop,
# `robustness.run_stretch`, runs as a compiled loop and returns EXACTLY what the numpy loop
# returns.
#
# `run_stretch` replays every one of the K threshold-and-timing configurations over one recorded
# stretch, config-vectorised: unlike `design_rule.py`'s two filters, nothing inside the loop is ever
# summed ACROSS configurations, so the compiled kernel needs no `_pairwise_sum` -- each configuration
# is an independent scalar time series and the per-configuration accumulators it returns do not
# depend on the order the configurations are visited in. This test holds the compiled kernel's
# per-configuration counts and sums equal to the numpy loop's, bit for bit, on constructed series with
# gaps, a missing first reading, an onset short enough to adopt on the very first sample, and both a
# rising and a falling ramp; and holds the fast, precompute-and-aggregate bootstrap path (which calls
# `run_stretch` once per training stretch, never once per replicate) equal to the whole-file entry
# point either way. Skipped where numba is not installed (CI); the container has it (decision 271).
needs_numba = pytest.mark.skipif(importlib.util.find_spec("numba") is None, reason="numba is not installed")


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


@needs_numba
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


@needs_numba
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


@needs_numba
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


# ------------------------------------------------------------------------------------------------
# One saved entry per candidate (from test_robustness_keeps_each_candidate.py, merged 2026-10-05)
# ------------------------------------------------------------------------------------------------
# The Closed-Loop robustness answer keeps one saved entry per candidate (decision 309).
#
# The robustness bootstrap is filed under a key that names the candidate (sensing pair, band centre,
# side) and is read back by the candidate tag on its sidecar, exactly like the CL-DBS simulation and
# the design rule. Those two keep six entries a participant; the robustness kind kept the store's
# default of ONE, so writing the right candidate's answer deleted the left's, and the next report for
# the left rebuilt it (the decision-107 failure, found by decision 306's agent on 2026-09-26). Two
# candidates written in turn must both read back, each as its own.
def test_the_left_and_right_candidates_robustness_answers_both_survive_and_each_is_found(tmp_path):
    try:
        from modules.CacheStore import ledger as _ledger, store as st
        from modules.ClosedLoopDeployment import adapter as AD
    except ImportError:                                          # pragma: no cover - host runner
        from CacheStore import ledger as _ledger, store as st
        from ClosedLoopDeployment import adapter as AD
    assert st.KEEP_NEWEST_BY_KIND.get(RB.KIND, 1) >= 2, "one entry per participant evicts a side"
    uid = "p-robustness-cands"
    prev = st.DIR_OVERRIDE, _ledger.ENABLED, AD._SHARED_CACHE_DIR_OVERRIDE
    st.DIR_OVERRIDE, _ledger.ENABLED, AD._SHARED_CACHE_DIR_OVERRIDE = str(tmp_path), False, str(tmp_path)
    try:
        cands = (("ONE_THREE_LEFT", 24.5, "Left"), ("ZERO_THREE_RIGHT", 24.5, "Right"))
        for ch, fc, side in cands:
            st.store(RB.KIND, uid, (RB.KIND, RB.RULE_VERSION, ch, fc, side), {"for": ch},
                     writer="closed_loop", trigger="deployment_report", provenance=[],
                     extra={"candidate": AD._simulation_candidate_tag(ch, fc, side)})
        got = {ch: AD.robustness_if_stored(uid, {"channel": ch, "center_hz": fc,
                                                 "actuated_hemisphere": side}, hemisphere=side)
               for ch, fc, side in cands}
        assert got == {"ONE_THREE_LEFT": {"for": "ONE_THREE_LEFT"},
                       "ZERO_THREE_RIGHT": {"for": "ZERO_THREE_RIGHT"}}, got
        # a candidate never written is not answered with another candidate's entry
        assert AD.robustness_if_stored(uid, {"channel": "ONE_THREE_LEFT", "center_hz": 12.5,
                                             "actuated_hemisphere": "Left"}) is None
    finally:
        # cleared only while this test's own directory override is in force (decisions 116, 129)
        st.clear()
        st.DIR_OVERRIDE, _ledger.ENABLED, AD._SHARED_CACHE_DIR_OVERRIDE = prev
