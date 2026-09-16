"""Tests for the joint current-titration schedule (2026-09-14), `current_map_schedule.py`.

This module is pure arithmetic on values a caller already holds (no Django, no store, no
recordings), so every test here constructs its own small frames directly, the same discipline
`test_titration_plan.py` (if any) or the module's own docstring establishes.
"""
import numpy as np
import pandas as pd
import pytest

from StimOptimizer import current_map_schedule as CMS


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
    steps = [dict(amp_left_mA=l, amp_right_mA=r) for l in (0.0, 1.0, 2.5, 4.0)
            for r in (0.0, 1.0, 2.5, 4.0)]
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
