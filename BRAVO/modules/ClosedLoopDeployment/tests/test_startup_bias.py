"""Synthetic regression fixtures adapted from Prasad8146f069 for startup_bias."""
import numpy as np
import pytest

try:
    from modules.ClosedLoopDeployment import startup_bias as SB
    from modules.ClosedLoopDeployment import prescription as PR, types as TY
except ImportError:                                              # pragma: no cover
    from ClosedLoopDeployment import startup_bias as SB
    from ClosedLoopDeployment import prescription as PR, types as TY

PA = pytest.importorskip("StimOptimizer.routines.percept_adaptive")


def _stretch(power_values, t0=0.0, dt=3.0):
    """One ``(t_grid, power, amp)`` tuple, `simulation.regrid_stretches`'s own shape, built
    directly rather than through regridding so each test controls exactly which cells are
    missing."""
    p = np.asarray(power_values, dtype=float)
    t = t0 + np.arange(p.size) * dt
    a = np.full(p.size, np.nan)
    return (t, p, a)


# ------------------------------------------------------------------------------------------------
# split_stretches_by_time: the one split both contestants used
# ------------------------------------------------------------------------------------------------
def test_split_by_time_orders_by_start_time_before_splitting():
    s_a = _stretch([1.0], t0=300.0)
    s_b = _stretch([1.0], t0=0.0)
    s_c = _stretch([1.0], t0=100.0)
    s_d = _stretch([1.0], t0=200.0)
    train, test = SB.split_stretches_by_time([s_a, s_b, s_c, s_d], frac=0.5)
    assert [s[0][0] for s in train] == [0.0, 100.0]
    assert [s[0][0] for s in test] == [200.0, 300.0]


def test_split_by_time_rounds_the_train_count_by_the_contests_own_rule():
    stretches = [_stretch([1.0], t0=float(i)) for i in range(10)]
    train, test = SB.split_stretches_by_time(stretches, frac=0.7)
    assert len(train) == 7
    assert len(test) == 3
    # round-half-to-even/away is irrelevant here since 0.7*10 = 7.0 exactly; check a case where
    # rounding actually matters (round(), Python's own banker's rounding, matches both scripts).
    stretches15 = [_stretch([1.0], t0=float(i)) for i in range(15)]
    train15, _test15 = SB.split_stretches_by_time(stretches15, frac=0.7)
    assert len(train15) == round(0.7 * 15)


def test_split_by_time_with_no_stretches_returns_two_empty_lists():
    train, test = SB.split_stretches_by_time([], frac=0.7)
    assert train == []
    assert test == []


# ------------------------------------------------------------------------------------------------
# startup_bias_d_method: contestant D's own arithmetic, verified by independent computation
# ------------------------------------------------------------------------------------------------
def test_d_method_reproduces_a_hand_computed_bias_and_t_statistic():
    """Three stretches whose first reading is 10, 20 and 30 units below their own median of 100;
    the bias and t-statistic are computed independently here, by direct numpy arithmetic on the
    same construction, and must match `startup_bias_d_method`'s own answer exactly."""
    stretches = [
        _stretch([90.0, 100.0, 100.0, 100.0, 100.0]),
        _stretch([80.0, 100.0, 100.0, 100.0, 100.0]),
        _stretch([70.0, 100.0, 100.0, 100.0, 100.0]),
    ]
    out = SB.startup_bias_d_method(stretches, min_finite=2, max_index=1)
    assert out["available"] is True
    assert out["n_qualifying_stretches"] == 3

    pooled = np.array([90, 100, 100, 100, 100, 80, 100, 100, 100, 100, 70, 100, 100, 100, 100],
                      dtype=float)
    expected_sd = float(np.std(pooled))                    # population sd, D's own `np.std`
    assert out["sd_of_series"] == pytest.approx(expected_sd)

    row = out["rows"][0]
    assert row["reading_index"] == 0
    assert row["n_stretches"] == 3
    d = np.array([90.0, 80.0, 70.0]) - 100.0                # every stretch's own median is 100
    expected_bias = float(d.mean() / expected_sd)
    expected_t = float(d.mean() / (d.std(ddof=1) / np.sqrt(3)))
    assert row["bias_in_sd"] == pytest.approx(expected_bias)
    assert row["t_stat"] == pytest.approx(expected_t)
    # by construction the first reading runs low relative to the rest of the stretch
    assert row["bias_in_sd"] < 0
    assert row["t_stat"] < 0


def test_d_method_floor_is_strictly_greater_than_not_at_least():
    """D's own source reads `f.size > 20`, a strict inequality; a stretch with exactly
    `min_finite` finite readings does not qualify, one with one more does."""
    exactly_at_floor = _stretch([50.0, 100.0])              # 2 finite readings
    one_more = _stretch([50.0, 100.0, 100.0])               # 3 finite readings
    out = SB.startup_bias_d_method([exactly_at_floor, one_more], min_finite=2, max_index=1)
    assert out["available"] is True
    assert out["n_qualifying_stretches"] == 1
    assert out["rows"][0]["n_stretches"] == 1
    assert out["rows"][0]["mean_value"] == pytest.approx(50.0)     # the one_more stretch's f[0]


def test_d_method_unavailable_when_no_stretch_qualifies():
    out = SB.startup_bias_d_method([_stretch([50.0, 100.0])], min_finite=20, max_index=1)
    assert out["available"] is False
    assert "20" in out["reason"]


def test_d_method_unavailable_with_fewer_than_two_finite_readings():
    out = SB.startup_bias_d_method([_stretch([np.nan])], min_finite=0, max_index=1)
    assert out["available"] is False


def test_d_method_sd_pools_every_training_stretch_not_only_the_qualifying_ones():
    """D's own `sd` line concatenates every TRAINING stretch's finite readings, including
    stretches too short to contribute a `vals`/`base` pair -- the short stretch changes the
    standard deviation even though it contributes no reading-0 value."""
    long_enough = _stretch([90.0, 100.0, 100.0, 100.0])     # 4 finite readings, qualifies at >2
    too_short = _stretch([500.0, 500.0])                    # 2 finite readings, does not qualify
    with_short = SB.startup_bias_d_method([long_enough, too_short], min_finite=2, max_index=1)
    without_short = SB.startup_bias_d_method([long_enough], min_finite=2, max_index=1)
    assert with_short["rows"][0]["n_stretches"] == without_short["rows"][0]["n_stretches"] == 1
    assert with_short["sd_of_series"] != pytest.approx(without_short["sd_of_series"])
    pooled = np.array([90.0, 100.0, 100.0, 100.0, 500.0, 500.0])
    assert with_short["sd_of_series"] == pytest.approx(float(np.std(pooled)))


# ------------------------------------------------------------------------------------------------
# startup_bias_e_method: contestant E's own arithmetic, and the mechanism that makes it disagree
# with D even on baselines both call "the stretch's own median"
# ------------------------------------------------------------------------------------------------
def test_e_method_reproduces_a_hand_computed_bias_and_z():
    stretches = [
        _stretch([90.0, 100.0, 100.0]),
        _stretch([95.0, 105.0, 100.0]),
    ]
    out = SB.startup_bias_e_method(stretches, dt_s=3.0, max_index=1)
    assert out["available"] is True
    allv = np.array([90.0, 100.0, 100.0, 95.0, 105.0, 100.0])
    expected_sd = float(np.std(allv))
    assert out["sd_of_series"] == pytest.approx(expected_sd)

    row = out["rows"][0]
    assert row["reading_index"] == 0
    assert row["time_s"] == pytest.approx(0.0)
    assert row["n_stretches"] == 2
    vals = np.array([90.0, 95.0])
    base = np.array([float(np.median([90.0, 100.0, 100.0])),
                     float(np.median([95.0, 105.0, 100.0]))])
    d = (vals - base) / expected_sd
    expected_bias = float(d.mean())
    expected_se = float(d.std(ddof=1) / np.sqrt(2))
    expected_z = expected_bias / expected_se
    assert row["bias_in_sd"] == pytest.approx(expected_bias)
    assert row["stderr_in_sd"] == pytest.approx(expected_se)
    assert row["z"] == pytest.approx(expected_z)


def test_e_method_a_missing_cell_excludes_that_stretch_from_that_reading_index_only():
    """The mechanism the module docstring names as the reason D and E disagree: a stretch with a
    missing SECOND cell contributes nothing to reading index 1 in E's method -- it is not shifted
    to the next real value, unlike D's compacted index."""
    with_gap = _stretch([90.0, np.nan, 100.0])
    complete = _stretch([95.0, 105.0, 100.0])
    out = SB.startup_bias_e_method([with_gap, complete], dt_s=3.0, max_index=2)
    row0, row1 = out["rows"]
    assert row0["n_stretches"] == 2                        # both stretches have a finite cell 0
    assert row1["n_stretches"] == 1                        # only `complete` has a finite cell 1
    # with only one contributing stretch there is no standard error to report -- correctly None,
    # never a fabricated number; the exclusion itself is what this test is about (n_stretches).
    assert row1["bias_in_sd"] is None


def test_d_and_e_methods_disagree_by_construction_on_the_same_stretches():
    """The same two stretches as above, run through BOTH methods at reading index 1: D compacts
    `with_gap` to its two real readings [90, 100] and uses the second one (100) as reading 1; E
    excludes `with_gap` from reading 1 entirely because its raw grid position 1 is missing. Same
    input, same nominal "reading index", genuinely different sets of numbers -- the mechanism the
    module and `startup_bias_note` both describe in words, demonstrated here by construction."""
    with_gap = _stretch([90.0, np.nan, 100.0])
    complete = _stretch([95.0, 105.0, 100.0])

    d_out = SB.startup_bias_d_method([with_gap, complete], min_finite=1, max_index=2)
    e_out = SB.startup_bias_e_method([with_gap, complete], dt_s=3.0, max_index=2)

    d_row1 = d_out["rows"][1]
    e_row1 = e_out["rows"][1]
    assert d_row1["n_stretches"] == 2                       # D: both stretches qualify and
                                                            # contribute their 2nd REAL reading
    assert e_row1["n_stretches"] == 1                       # E: only the complete stretch reaches
                                                            # raw grid position 1 with data there
    assert d_row1["n_stretches"] != e_row1["n_stretches"]


# ------------------------------------------------------------------------------------------------
# startup_bias_for_series: the one entry point, built from a raw t/power/amp series
# ------------------------------------------------------------------------------------------------
def test_for_series_refuses_with_too_few_samples():
    out = SB.startup_bias_for_series(np.array([0.0, 3.0]), np.array([1.0, 2.0]),
                                     np.array([1.0, 1.0]))
    assert out["refused"] is True
    assert "too few" in out["reason"]


def test_for_series_refuses_when_every_power_reading_is_missing():
    t = np.arange(10) * 3.0
    p = np.full(10, np.nan)
    a = np.full(10, 1.0)
    out = SB.startup_bias_for_series(t, p, a)
    assert out["refused"] is True


def test_for_series_builds_stretches_and_runs_both_methods_on_a_constructed_dip():
    """A constructed series with a real, repeatable dip at the very first reading of every
    stretch: both methods should find it at reading 0 (they cannot disagree there, because the
    first grid cell of a stretch is always the first real sample by construction of
    `simulation.regrid_stretches`, so D's compacted index 0 and E's raw index 0 are identical)."""
    rng = np.random.default_rng(2026_09_13)
    t_parts, p_parts = [], []
    t0 = 0.0
    for _ in range(40):
        n = 25
        vals = 100.0 + rng.normal(0.0, 3.0, n)
        vals[0] -= 15.0                                     # a real dip at the first reading
        t_parts.append(t0 + np.arange(n) * 3.0)
        p_parts.append(vals)
        t0 += n * 3.0 + 3600.0                              # a real gap between recordings
    t = np.concatenate(t_parts)
    p = np.concatenate(p_parts)
    a = np.full(t.size, np.nan)
    out = SB.startup_bias_for_series(t, p, a)
    assert out["refused"] is False
    assert out["device_clock_s"] == pytest.approx(3.0)
    assert out["n_stretches_total"] == 40

    d0 = out["d_method"]["rows"][0]
    e0 = out["e_method"]["rows"][0]
    assert d0["n_stretches"] == e0["n_stretches"]           # identical at reading 0, as reasoned
    assert d0["bias_in_sd"] < 0
    assert e0["bias_in_sd"] < 0
    assert d0["t_stat"] < -2.0                              # a real, detectable dip
    assert e0["z"] < -2.0


# ------------------------------------------------------------------------------------------------
# startup_bias_note / attach_startup_bias: the prescription-card wiring, mirroring
# design_rule_note / occupancy_note
# ------------------------------------------------------------------------------------------------
def test_startup_bias_note_is_none_when_refused():
    assert PR.startup_bias_note({"refused": True, "reason": "x"}) is None
    assert PR.startup_bias_note(None) is None


def test_startup_bias_note_states_both_methods_numbers():
    stretches = [
        _stretch([90.0, 100.0, 100.0, 100.0, 100.0]),
        _stretch([80.0, 100.0, 100.0, 100.0, 100.0]),
        _stretch([70.0, 100.0, 100.0, 100.0, 100.0]),
    ]
    d_result = SB.startup_bias_d_method(stretches, min_finite=2, max_index=1)
    e_result = SB.startup_bias_e_method(stretches, dt_s=3.0, max_index=1)
    payload = {"refused": False, "d_method": d_result, "e_method": e_result}
    note = PR.startup_bias_note(payload)
    assert note is not None
    assert "Method D" in note
    assert "Method E" in note
    assert f"{d_result['rows'][0]['t_stat']:.2f}" in note
    assert f"{e_result['rows'][0]['z']:.2f}" in note


def test_attach_startup_bias_only_touches_the_startup_delay_field():
    plan = TY.ThresholdPlan(upper=210.579, lower=161.903, capture_amp_low=1.4, capture_amp_high=4.8)
    cand = {"channel": "ONE_THREE_LEFT", "center_hz": 24.5, "band_width_hz": 5.0}
    prescriptions = PR.prescribe_all_modes(threshold_plan=plan, candidate=cand,
                                           power_series=None, validated_hemispheres=("Left",),
                                           configuring_both_hemispheres=False)
    stretches = [
        _stretch([90.0, 100.0, 100.0, 100.0, 100.0]),
        _stretch([80.0, 100.0, 100.0, 100.0, 100.0]),
        _stretch([70.0, 100.0, 100.0, 100.0, 100.0]),
    ]
    d_result = SB.startup_bias_d_method(stretches, min_finite=2, max_index=1)
    e_result = SB.startup_bias_e_method(stretches, dt_s=3.0, max_index=1)
    payload = {"refused": False, "d_method": d_result, "e_method": e_result}
    out = PR.attach_startup_bias(prescriptions, payload)
    dual = out["modes"][PR.PA.DUAL]
    touched = {f.name for f in dual.fields if f.startup_bias_note is not None}
    assert touched == {"Adaptive startup delay"}
    for f in dual.fields:
        if f.name not in touched:
            assert f.startup_bias_note is None


def test_attach_startup_bias_is_a_no_op_when_refused():
    plan = TY.ThresholdPlan(upper=210.579, lower=161.903, capture_amp_low=1.4, capture_amp_high=4.8)
    cand = {"channel": "ONE_THREE_LEFT", "center_hz": 24.5, "band_width_hz": 5.0}
    prescriptions = PR.prescribe_all_modes(threshold_plan=plan, candidate=cand,
                                           power_series=None, validated_hemispheres=("Left",),
                                           configuring_both_hemispheres=False)
    out = PR.attach_startup_bias(prescriptions, {"refused": True, "reason": "x"})
    dual = out["modes"][PR.PA.DUAL]
    assert all(f.startup_bias_note is None for f in dual.fields)


def test_as_rows_carries_the_startup_bias_note_key():
    plan = TY.ThresholdPlan(upper=210.579, lower=161.903, capture_amp_low=1.4, capture_amp_high=4.8)
    cand = {"channel": "ONE_THREE_LEFT", "center_hz": 24.5, "band_width_hz": 5.0}
    prescriptions = PR.prescribe_all_modes(threshold_plan=plan, candidate=cand,
                                           power_series=None, validated_hemispheres=("Left",),
                                           configuring_both_hemispheres=False)
    dual = prescriptions["modes"][PR.PA.DUAL]
    rows = dual.as_rows()
    assert all("startup_bias_note" in r for r in rows)
    assert all(r["startup_bias_note"] is None for r in rows)   # nothing attached yet
