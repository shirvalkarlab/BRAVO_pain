"""Tests for the joint current-titration schedule (2026-09-14), `current_map_schedule.py`.

This module is pure arithmetic on values a caller already holds (no Django, no store, no
recordings), so every test here constructs its own small frames directly, the same discipline
`test_titration_plan.py` (if any) or the module's own docstring establishes.

Merged here 2026-10-05: test_surface_serialization.py (each under its own heading below).
"""
import numpy as np
import pandas as pd
import pytest

from StimOptimizer import current_map_schedule as CMS

from StimOptimizer import bravo_service as BS
from StimOptimizer import stage1_openloop as S1


# ---------------------------------------------------------------------------------------------
# design_points: the ceiling caps the grid, and an unsafe cell is excluded and named
# ---------------------------------------------------------------------------------------------
def test_the_ceiling_caps_the_design_grid():
    dp = CMS.design_points(ceiling_left_mA=2.0, ceiling_right_mA=5.0)
    assert dp["levels_left_mA"] == [1.0]              # only 1.0 clears a 2.0 mA ceiling of (1,2.5,4)
    assert dp["levels_right_mA"] == [1.0, 2.5, 4.0]
    assert all(p["amp_left_mA"] <= 2.0 + 1e-9 for p in dp["points"])
    assert all(p["amp_right_mA"] <= 5.0 + 1e-9 for p in dp["points"])


def test_an_unsafe_point_is_excluded_and_named():
    def is_safe(l, r):
        return not (l >= 4.0 and r >= 4.0)            # the top corner alone is unsafe
    dp = CMS.design_points(ceiling_left_mA=5.0, ceiling_right_mA=5.0, is_safe=is_safe)
    excluded_pairs = {(p["amp_left_mA"], p["amp_right_mA"]) for p in dp["excluded"]}
    assert (4.0, 4.0) in excluded_pairs
    assert (4.0, 4.0) not in {(p["amp_left_mA"], p["amp_right_mA"]) for p in dp["points"]}
    hit = [p for p in dp["excluded"] if (p["amp_left_mA"], p["amp_right_mA"]) == (4.0, 4.0)][0]
    assert "reason" in hit and "safe set" in hit["reason"]


def test_the_anchor_is_included_and_its_key_is_reported():
    dp = CMS.design_points(ceiling_left_mA=5.0, ceiling_right_mA=5.0,
                           in_force_left_mA=3.0, in_force_right_mA=2.5)
    assert dp["anchor_key"] == (3.0, 2.5)
    assert any(p["amp_left_mA"] == 3.0 and p["amp_right_mA"] == 2.5 for p in dp["points"])


# ---------------------------------------------------------------------------------------------
# the setting in force above today's ceiling: kept as history, never offered as a target
# (2026-09-26). Before, `add` refused the pair silently and the schedule lost its anchor with
# nothing on the page saying why.
# ---------------------------------------------------------------------------------------------
def test_an_in_force_setting_above_the_ceiling_is_kept_as_history_not_as_a_target():
    dp = CMS.design_points(ceiling_left_mA=4.5, ceiling_right_mA=4.5,
                           in_force_left_mA=4.8, in_force_right_mA=3.0)
    inf = dp["in_force"]
    assert inf["amp_left_mA"] == 4.8 and inf["amp_right_mA"] == 3.0
    assert inf["above_ceiling"] is True
    assert inf["sides_above_ceiling"] == ["Left"]
    assert inf["offered_as_target"] is False
    assert inf["label"] == "in force, above today's ceiling"
    # never a target: not among the points, and no anchor for the order to repeat
    assert (4.8, 3.0) not in {(p["amp_left_mA"], p["amp_right_mA"]) for p in dp["points"]}
    assert dp["anchor_key"] is None


def test_an_in_force_setting_under_the_ceiling_is_the_anchor_and_says_so():
    dp = CMS.design_points(ceiling_left_mA=4.5, ceiling_right_mA=4.5,
                           in_force_left_mA=3.0, in_force_right_mA=2.5)
    inf = dp["in_force"]
    assert inf["above_ceiling"] is False and inf["sides_above_ceiling"] == []
    assert inf["offered_as_target"] is True
    assert dp["anchor_key"] == (3.0, 2.5)


def test_the_schedule_carries_the_in_force_point_above_the_ceiling_and_no_step_above_it():
    block = CMS.build_schedule(
        rate_hz=55.0, pw_us_left=100.0, pw_us_right=150.0,
        ceiling_left_mA=4.5, ceiling_right_mA=4.5,
        in_force_left_mA=3.0, in_force_right_mA=4.8,
        existing_epochs_at_stratum=pd.DataFrame(columns=["amp_mA_Left", "amp_mA_Right", "n", "t0"]),
        epochs_for_reporting_rate=pd.DataFrame(columns=["t0", "n"]))
    inf = block["in_force"]
    assert inf["sides_above_ceiling"] == ["Right"] and inf["offered_as_target"] is False
    assert "history" in inf["why"]
    assert all(st["amp_right_mA"] <= 4.5 + 1e-9 for st in block["steps"])
    assert not any("setting in force" in st["why"] for st in block["steps"])


# ---------------------------------------------------------------------------------------------
# drop_already_covered
# ---------------------------------------------------------------------------------------------
def test_a_point_with_at_least_the_target_reports_already_is_dropped():
    points = [dict(amp_left_mA=1.0, amp_right_mA=1.0, why="grid"),
             dict(amp_left_mA=4.0, amp_right_mA=4.0, why="grid")]
    existing = pd.DataFrame({"amp_mA_Left": [1.0, 1.0, 1.0], "amp_mA_Right": [1.0, 1.0, 1.0],
                             "n": [4.0, 4.0, 4.0]})    # 12 reports total, above the 10 floor
    dc = CMS.drop_already_covered(points, existing)
    dropped_keys = {(p["amp_left_mA"], p["amp_right_mA"]) for p in dc["dropped"]}
    kept_keys = {(p["amp_left_mA"], p["amp_right_mA"]) for p in dc["points"]}
    assert (1.0, 1.0) in dropped_keys
    assert (4.0, 4.0) in kept_keys
    assert dc["dropped"][0]["existing_reports"] == pytest.approx(12.0)


def test_a_point_below_the_report_threshold_is_kept():
    points = [dict(amp_left_mA=1.0, amp_right_mA=1.0, why="grid")]
    existing = pd.DataFrame({"amp_mA_Left": [1.0], "amp_mA_Right": [1.0], "n": [3.0]})
    dc = CMS.drop_already_covered(points, existing)
    assert len(dc["points"]) == 1
    assert dc["dropped"] == []


def test_no_existing_epochs_drops_nothing():
    points = [dict(amp_left_mA=1.0, amp_right_mA=1.0, why="grid")]
    dc = CMS.drop_already_covered(points, None)
    assert len(dc["points"]) == 1
    assert dc["dropped"] == []


# ---------------------------------------------------------------------------------------------
# reports_per_day / hold_days_for_point
# ---------------------------------------------------------------------------------------------
def test_reports_per_day_reads_a_median_over_the_lookback_window():
    t0 = pd.date_range("2026-06-01", periods=10, freq="D", tz="UTC")
    epochs = pd.DataFrame({"t0": t0, "n": [2.0] * 10})
    rpd = CMS.reports_per_day(epochs, lookback_days=9, reference=t0[-1])
    assert rpd["median_per_day"] == pytest.approx(2.0)
    assert rpd["n_days"] == 10


def test_reports_per_day_handles_no_data():
    rpd = CMS.reports_per_day(None)
    assert rpd["median_per_day"] is None
    assert "no epochs" in rpd["note"]


def test_hold_days_clamps_to_three_and_seven():
    # A fast reporter (20 reports/day) needing only 5 reports would round to under 3 days --
    # clamped up.
    fast = CMS.hold_days_for_point(20.0, target_reports=5, min_days=3, max_days=7)
    assert fast["hold_days"] == 3
    # A slow reporter (0.2 reports/day) needing 5 reports would take 25 days -- clamped down.
    slow = CMS.hold_days_for_point(0.2, target_reports=5, min_days=3, max_days=7)
    assert slow["hold_days"] == 7
    # A moderate reporter lands inside the window with no clamping.
    mid = CMS.hold_days_for_point(1.0, target_reports=5, min_days=3, max_days=7)
    assert mid["hold_days"] == 5
    # No measured rate defaults to the maximum, not a guess.
    none_ = CMS.hold_days_for_point(None, min_days=3, max_days=7)
    assert none_["hold_days"] == 7


# ---------------------------------------------------------------------------------------------
# order_points: never three consecutive strictly-increasing left-current steps; the anchor
# appears at least three times
# ---------------------------------------------------------------------------------------------
def _grid_points(anchor=(2.5, 2.5)):
    levels = (1.0, 2.5, 4.0)
    pts = [dict(amp_left_mA=l, amp_right_mA=r, why="grid") for l in levels for r in levels]
    return pts, anchor


def test_the_order_never_ramps_three_consecutive_increasing_left_steps():
    pts, anchor = _grid_points()
    ordered = CMS.order_points(pts, anchor_key=anchor, seed=1)
    lefts = [s["amp_left_mA"] for s in ordered["steps"]]
    for i in range(len(lefts) - 2):
        a, b, c = lefts[i], lefts[i + 1], lefts[i + 2]
        assert not (a < b < c), f"three consecutive increasing left-current steps at {i}: {lefts}"


def test_the_anchor_is_repeated_at_least_three_times():
    pts, anchor = _grid_points()
    ordered = CMS.order_points(pts, anchor_key=anchor, seed=1)
    hits = sum(1 for s in ordered["steps"]
              if (round(s["amp_left_mA"], 3), round(s["amp_right_mA"], 3)) == anchor)
    assert hits >= 3


def test_with_no_anchor_every_point_appears_exactly_once():
    pts, _ = _grid_points()
    ordered = CMS.order_points(pts, anchor_key=None, seed=1)
    assert ordered["n_steps"] == len(pts)
    assert {(s["amp_left_mA"], s["amp_right_mA"]) for s in ordered["steps"]} == \
        {(p["amp_left_mA"], p["amp_right_mA"]) for p in pts}


# ---------------------------------------------------------------------------------------------
# what_this_buys
# ---------------------------------------------------------------------------------------------
def test_what_this_buys_reports_whether_the_completed_schedule_would_clear_coverage():
    steps = [dict(amp_left_mA=l, amp_right_mA=r, planned_days=5) for l in (0.0, 1.0, 2.5, 4.0)
            for r in (0.0, 1.0, 2.5, 4.0)]                      # decision 184: days, not only reports
    wtb = CMS.what_this_buys(None, steps, target_reports=5)
    assert wtb["resolution_coverage_would_pass"] is True
    assert wtb["coverage_after_schedule"]["n_pairs"] == 16


def test_what_this_buys_says_no_when_the_schedule_alone_is_not_enough():
    steps = [dict(amp_left_mA=1.0, amp_right_mA=1.0)]     # a single point, no span at all
    wtb = CMS.what_this_buys(None, steps, target_reports=5)
    assert wtb["resolution_coverage_would_pass"] is False


# ---------------------------------------------------------------------------------------------
# build_schedule end to end
# ---------------------------------------------------------------------------------------------
def test_build_schedule_end_to_end_on_a_record_with_nothing_yet():
    block = CMS.build_schedule(
        rate_hz=55.0, pw_us_left=100.0, pw_us_right=150.0,
        ceiling_left_mA=5.0, ceiling_right_mA=5.0,
        in_force_left_mA=3.0, in_force_right_mA=2.5,
        existing_epochs_at_stratum=pd.DataFrame(columns=["amp_mA_Left", "amp_mA_Right", "n", "t0"]),
        epochs_for_reporting_rate=pd.DataFrame(columns=["t0", "n"]))
    assert block["available"] is True
    assert block["rate_hz"] == pytest.approx(55.0)
    assert block["n_steps"] > 0
    assert block["total_days"] == block["hold"]["hold_days"] * block["n_steps"]
    assert block["record_today"]["n_existing_epochs_at_this_stratum"] == 0
    # no reporting-rate data means the maximum hold, per hold_days_for_point's own default
    assert block["hold"]["hold_days"] == CMS.MAX_HOLD_DAYS


def test_unavailable_schedule_carries_a_plain_reason():
    block = CMS.unavailable_schedule("no rate on record")
    assert block["available"] is False
    assert block["reason"] == "no rate on record"


# ================================================================================================
# From test_surface_serialization.py (merged here 2026-10-05).
# Tests for the (left current, right current) surface `bravo_service.py` attaches to every
# FITTED row of `two_stage.stage1.rate_strata`, and the pooled 3-input reference slices it attaches
# once per joint stratum (2026-09-14, alongside decision 158's honest-current rule) -- the data the
# Stim Optimizer page's new `CurrentMapCard` draws.
#
# Built self-contained, with its own thin-and-fat rate mix at ONE pulse-width pair, rather than
# reusing `test_stage1.py`'s `rcs08_like` fixture: that fixture aliases pulse width to rate one-to-
# one, so every joint stratum it fits has exactly one rate and never exercises the "some rates in a
# stratum fit, some do not" case this file's own second test needs.
# ================================================================================================


def _matrix_two_rates_one_pw():
    """One (pulse-width-Left, pulse-width-Right) pair, two rates inside it: 55 Hz with 12 epochs
    (clears ``RATE_STRATUM_MIN_EPOCHS`` = 8) and 10 Hz with 3 (does not)."""
    rng = np.random.default_rng(0)
    rows = []
    ep = 0
    for rate, n in ((55.0, 12), (10.0, 3)):
        for k in range(n):
            ep += 1
            amp_left = 1.0 + 0.25 * (k % 6)
            amp_right = 1.2 + 0.25 * (k % 5)
            rows.append(dict(
                epoch=float(ep), freq_hz=float(rate), pw_us_Left=100.0, pw_us_Right=150.0,
                amp_mA_Left=float(amp_left), amp_mA_Right=float(amp_right), n=6.0, dur_h=180.0,
                left_leg_vas=float(50.0 + 3.0 * rng.standard_normal()), left_leg_vas_sd=7.5))
    d = pd.DataFrame(rows)
    d["t0"] = pd.date_range("2025-07-01", periods=len(d), freq="3D", tz="UTC")
    return d


# Stage 1 runs here without its calibration check (`calibration_check=False`, 2026-10-02): a
# warning that changes no recommendation (decision 233, ruling 6), read by no test in this file,
# and held by `test_stratum_calibration.py`; its leave-one-out refits were most of each fit's time.
@pytest.fixture(scope="module")
def stage1_two_rates():
    d = _matrix_two_rates_one_pw()
    return S1.run_stage1(d, data_horizon="test", washin_min=1.0, calibration_check=False)


def _rate_strata_records(s1):
    records = BS._frame_records(s1.rate_summary)
    return BS._attach_rate_stratum_surfaces(records, s1)


def test_a_fitted_rows_surface_matches_the_raw_rate_stratum_value_for_value(stage1_two_rates):
    records = _rate_strata_records(stage1_two_rates)
    fitted = [r for r in records if r["fitted"]]
    assert fitted, "the 55 Hz stratum should have fitted"
    row = fitted[0]
    assert "surface" in row
    surface = row["surface"]

    # The raw object the response was built from.
    key = (round(float(row["pw_us_left"]), 6), round(float(row["pw_us_right"]), 6),
          row.get("left_contact"), round(float(row["rate_hz"]), 6))
    rs = BS._rate_stratum_lookup(stage1_two_rates)[key]

    assert len(surface["amps_mA"]) == 21
    assert len(surface["mu"]) == 21
    assert len(surface["mu"][0]) == 21
    assert len(surface["sd"]) == 21
    assert len(surface["safe"]) == 21

    # Every finite cell of the serialised grid equals the raw RateStratum's own surface, to the
    # rounding the response applies (4 decimals) -- never a tolerance beyond that stated rounding.
    raw_mu = np.asarray(rs.mu, float)
    raw_sd = np.asarray(rs.sd, float)
    raw_safe = np.asarray(rs.safe, bool)
    n_compared, n_differing = 0, 0
    for i in range(21):
        for j in range(21):
            n_compared += 1
            expect_mu = None if not np.isfinite(raw_mu[i, j]) else round(float(raw_mu[i, j]), 4)
            expect_sd = None if not np.isfinite(raw_sd[i, j]) else round(float(raw_sd[i, j]), 4)
            if surface["mu"][i][j] != expect_mu:
                n_differing += 1
            if surface["sd"][i][j] != expect_sd:
                n_differing += 1
            if surface["safe"][i][j] != bool(raw_safe[i, j]):
                n_differing += 1
    assert n_compared == 441
    assert n_differing == 0

    # amps_mA is the grid's own amplitude axis (identical for left and right: both sides share
    # stage1_openloop.JOINT_AMP_GRID).
    assert surface["amps_mA"] == [round(float(v), 4) for v in np.asarray(rs.grid.amps_left, float)]
    assert surface["amps_mA"][0] == 0.0
    assert surface["amps_mA"][-1] == pytest.approx(5.0)

    # The observed points are the individual epochs the fit regressed, not a grid cell.
    assert len(surface["points"]) == int(row["n_epochs"]) == 12
    for p in surface["points"]:
        for k in ("amp_left_mA", "amp_right_mA", "n_reports", "J", "epoch"):
            assert k in p


def test_b_an_unfitted_row_carries_no_surface_key(stage1_two_rates):
    records = _rate_strata_records(stage1_two_rates)
    unfitted = [r for r in records if not r["fitted"]]
    assert unfitted, "the 3-epoch 10 Hz stratum should not have fitted"
    row = unfitted[0]
    assert row["rate_hz"] == 10.0
    assert "surface" not in row
    assert row["reason"]


def test_c_pooled_surfaces_carry_every_delivered_rate_once_per_stratum(stage1_two_rates):
    pooled = BS._joint_pooled_surfaces(stage1_two_rates)
    assert len(pooled) == 1
    key = "100_150"
    assert key in pooled
    strat = pooled[key]
    assert strat["pw_us_left"] == 100.0
    assert strat["pw_us_right"] == 150.0
    rates = strat["surface_at_rate"]
    # Both rates the stratum delivered are present, fitted or not -- the pooled surface has an
    # opinion at every rate it was ever asked about, which is exactly why it is reference-only.
    assert set(rates.keys()) == {"55", "10"}
    for rate_key, surf in rates.items():
        assert len(surf["amps_mA"]) == 21
        assert len(surf["mu"]) == 21
        assert len(surf["mu"][0]) == 21
        assert len(surf["safe"]) == 21


def test_d_the_full_two_stage_payload_carries_both_new_fields(stage1_two_rates):
    """`_two_stage_payload` (the function that actually serves the response) attaches `surface` to
    the fitted rate-strata row and a `pooled_surfaces` block, reached through the real code path
    rather than only through the two helpers tested directly above."""
    class _FakeReport:
        pass

    # `_two_stage_payload` needs a `pipeline.TwoStageReport`-shaped object; build the minimum it
    # reads (`.stage1`, `.gate`, `.stage2`, `.manifest`, `.can_deploy_closed_loop()`, `.describe()`)
    # rather than importing the whole gate/Stage 2 machinery, which is exercised by other tests.
    class _FakeGate:
        conditions = []
        passed = False
        headline = "Stage 2 MUST NOT START: 0 of 0 conditions block"   # GateResult.headline, 2026-09-15

        @staticmethod
        def refusals():
            return []

        @staticmethod
        def failed_names():
            return []

        @staticmethod
        def not_assessed_names():
            return []

        @staticmethod
        def describe():
            return ""

    class _FakeStage2:
        started = False
        notes = []
        refusal_reasons = []

        @staticmethod
        def describe():
            return ""

    rep = _FakeReport()
    rep.stage1 = stage1_two_rates
    rep.gate = _FakeGate()
    rep.stage2 = _FakeStage2()
    rep.manifest = {}
    rep.can_deploy_closed_loop = lambda: False
    rep.describe = lambda: ""

    out = BS._two_stage_payload(rep, inputs={}, seconds=0.0)
    rate_strata = out["stage1"]["rate_strata"]
    fitted = [r for r in rate_strata if r["fitted"]]
    assert fitted and "surface" in fitted[0]
    assert "pooled_surfaces" in out["stage1"]
    assert out["stage1"]["pooled_surfaces"]


# ---- the PI, 2026-09-17: absolute numbers on the current map, colour centred on today ----------
def test_e_every_surface_carries_the_pain_rating_at_the_setting_in_force_so_the_page_can_print_absolute_values(stage1_two_rates):
    """`mu` is the score RELATIVE to the setting in force (J = rating - rating at the incumbent +
    side-effect cost). The page adds `pain_reference` back to print the predicted rating in the
    participant's own 0-10 units and centres its colour scale on it; the fit itself is unchanged."""
    s1 = stage1_two_rates
    records = _rate_strata_records(s1)
    fitted = [r for r in records if r["fitted"]]
    surface = fitted[0]["surface"]
    assert "pain_reference" in surface and "pain_item" in surface
    D = s1.D
    item = str(D["primary_item"].iloc[0])
    inc = D.loc[D["epoch"].astype(float) == float(s1.frozen.incumbent_epoch)]
    assert len(inc) == 1
    assert surface["pain_item"] == item
    assert surface["pain_reference"] == float(inc[item].iloc[0])
    # and J_pain is exactly the rating minus that reference on every row
    assert np.allclose(D[item].astype(float) - D["J_pain"].astype(float), surface["pain_reference"])
    # the pooled reference surfaces carry the same number
    pooled = BS._joint_pooled_surfaces(s1)
    for stratum in pooled.values():
        for rate_surface in stratum["surface_at_rate"].values():
            assert rate_surface["pain_reference"] == surface["pain_reference"]
