"""Span-aware separation diagnostics: distinguishing a narrow ladder from a flat band."""
from types import SimpleNamespace as NS

import numpy as np
import pytest

from StimOptimizer.routines import lfp_response as LR
from StimOptimizer.routines import objective as OBJ


def _res(d, lo, hi, slope, a_lo, a_hi):
    return NS(separation_d=d, power_low=lo, power_high=hi, slope_log_per_mA=slope,
              amp_low_mA=a_lo, amp_high_mA=a_hi)


def test_expected_separation_is_slope_times_span_over_scatter():
    assert LR.expected_separation_d(-0.13, 1.0, 0.25) == pytest.approx(0.52)
    assert LR.expected_separation_d(-0.13, 3.5, 0.25) == pytest.approx(1.82)
    # sign of the slope does not matter to a separation
    assert LR.expected_separation_d(0.13, 2.0, 0.25) == LR.expected_separation_d(-0.13, 2.0, 0.25)
    for bad in (LR.expected_separation_d(np.nan, 1.0, 0.25),
                LR.expected_separation_d(-0.1, 1.0, 0.0),
                LR.expected_separation_d(-0.1, 1.0, -1.0)):
        assert not np.isfinite(bad)


def test_the_within_arm_scatter_is_recovered_from_the_gates_own_numbers():
    """Recovered from `separation_d` and the two capture values rather than refitted, so it cannot
    disagree with the separation the gate actually applied.
    """
    r = _res(d=2.0, lo=1.0, hi=2.0, slope=-0.2, a_lo=1.0, a_hi=4.0)
    assert LR.within_arm_sd_from_result(r) == pytest.approx(0.5)   # |2-1| / 2.0
    assert not np.isfinite(LR.within_arm_sd_from_result(_res(0.0, 1.0, 2.0, -0.2, 1.0, 4.0)))
    assert not np.isfinite(LR.within_arm_sd_from_result(_res(np.nan, 1.0, 2.0, -0.2, 1.0, 4.0)))


def test_a_narrow_ladder_is_named_as_a_protocol_shortfall_not_a_flat_band():
    """The distinction the screen previously conflated: these two refusals have opposite remedies."""
    r = _res(d=0.30, lo=2.0, hi=2.15, slope=-0.13, a_lo=1.0, a_hi=2.0)
    o = LR.span_needed_for_separation(r)
    assert o["verdict"] == "widen_the_ladder", o
    assert o["span_needed_mA"] > o["observed_span_mA"]
    assert o["span_needed_mA"] < OBJ.AMP_HARD_LIMIT_MA
    assert "PROTOCOL shortfall" in o["note"]


def test_a_flat_band_is_not_reported_as_a_ladder_instruction():
    """The branch that could never fire in my first version, because the amplitude ceiling was
    probed from globals() where the constant does not live, so it silently defaulted to infinity.
    A 62 mA ladder is not an instruction; it means the band does not respond.
    """
    r = _res(d=0.05, lo=2.0, hi=2.005, slope=-0.0008, a_lo=1.0, a_hi=2.0)
    o = LR.span_needed_for_separation(r)
    assert o["verdict"] == "slope_indistinguishable_from_zero", o
    assert o["span_needed_mA"] > OBJ.AMP_HARD_LIMIT_MA
    assert "beyond" in o["note"]


def test_a_cell_that_already_clears_is_left_alone():
    r = _res(d=1.30, lo=2.0, hi=2.9, slope=-0.20, a_lo=1.0, a_hi=4.5)
    o = LR.span_needed_for_separation(r)
    assert o["verdict"] == "clears" and o["span_needed_mA"] is None


def test_an_inestimable_slope_says_nothing_rather_than_guessing():
    r = _res(d=0.30, lo=2.0, hi=2.15, slope=np.nan, a_lo=1.0, a_hi=2.0)
    o = LR.span_needed_for_separation(r)
    assert o["verdict"] == "slope_not_estimable" and o["span_needed_mA"] is None


def test_the_ceiling_is_explicit_and_never_silently_infinite():
    """Pins the fix. With a deliberately tiny ceiling the same narrow-ladder cell must flip to
    unreachable -- which proves the ceiling is consulted rather than defaulted away.
    """
    r = _res(d=0.30, lo=2.0, hi=2.15, slope=-0.13, a_lo=1.0, a_hi=2.0)
    assert LR.span_needed_for_separation(r, amp_ceiling_mA=1.5)["verdict"] == \
        "slope_indistinguishable_from_zero"
    assert LR.span_needed_for_separation(r, amp_ceiling_mA=10.0)["verdict"] == "widen_the_ladder"


def test_the_floor_itself_is_not_scaled_by_the_span():
    """The conclusion of the open question, asserted so it cannot be quietly reversed. The device
    places its threshold BETWEEN the two captures, so placeability depends on the ABSOLUTE overlap
    of the two distributions and does not become easier because a narrow ladder was chosen.
    """
    narrow = _res(d=0.30, lo=2.0, hi=2.15, slope=-0.13, a_lo=1.0, a_hi=2.0)
    wide = _res(d=0.30, lo=2.0, hi=2.15, slope=-0.13, a_lo=1.0, a_hi=4.5)
    assert LR.span_needed_for_separation(narrow)["floor"] == \
        LR.span_needed_for_separation(wide)["floor"] == LR.MIN_CAPTURE_SEPARATION_D
    # and the same observed d is refused in both, regardless of the span used
    assert LR.span_needed_for_separation(narrow)["verdict"] != "clears"
    assert LR.span_needed_for_separation(wide)["verdict"] != "clears"


def test_a_span_already_wider_than_needed_is_named_as_an_inconsistency_not_a_shortfall():
    """Found on real data: one band returned "widen the ladder" while needing 1.78 mA against the
    2.0 mA already used, which is incoherent -- the ladder is already wide enough on the slope's own
    account. The cause is that the slope is era-BLOCKED while the capture arms are RAW, so when era
    adjustment carries the relationship the adjusted slope implies a contrast the arms do not hold.
    Naming it separately matters because the remedy is different: not a wider ladder, but distrust
    of the adjusted slope.
    """
    # slope -0.30, sd 0.10 -> needs only 0.5*0.10/0.30 = 0.167 mA, yet 2.0 mA was used and the
    # observed separation is still below the floor
    r = _res(d=0.20, lo=2.0, hi=2.02, slope=-0.30, a_lo=1.0, a_hi=3.0)
    o = LR.span_needed_for_separation(r)
    assert o["verdict"] == "arms_inconsistent_with_slope", o
    assert o["span_needed_mA"] <= o["observed_span_mA"]
    assert o["expected_d_at_observed_span"] > o["floor"] > o["observed_d"]
    assert "disagree" in o["note"]


def test_widen_the_ladder_only_fires_when_the_span_really_is_too_narrow():
    """Guards the boundary between the two verdicts, which is the whole point of the new branch."""
    # needs MORE than used -> genuine shortfall
    wide_needed = _res(d=0.30, lo=2.0, hi=2.15, slope=-0.13, a_lo=1.0, a_hi=2.0)
    o1 = LR.span_needed_for_separation(wide_needed)
    assert o1["verdict"] == "widen_the_ladder"
    assert o1["span_needed_mA"] > o1["observed_span_mA"]
    # needs LESS than used -> inconsistency
    o2 = LR.span_needed_for_separation(_res(d=0.20, lo=2.0, hi=2.02, slope=-0.30,
                                            a_lo=1.0, a_hi=3.0))
    assert o2["verdict"] == "arms_inconsistent_with_slope"
