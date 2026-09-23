"""How many times the "proven better than today's setting" test ran, and what that exposes.

WHY (panel C item 4, 2026-09-22). A current is recommended at a rate only when its gain over the
setting in force clears ONE standard deviation of that difference (`RESOLUTION_K = 1.0`). One
standard deviation is a declared, modest bar, not a significance threshold: on a comparison where
nothing is truly better, the gain alone clears it about one time in six (the upper tail of a normal
curve beyond one standard deviation, 0.1587). The page runs that comparison once per rate per
pulse-width pairing it can fit, and nothing on it said how many that was. Visibility only: nothing
here changes the rule, refuses anything or corrects anything.

Pinned on the values, never the shape.
"""
import math

from StimOptimizer import stage1_openloop as S1
from StimOptimizer.routines import resolution as RES
from StimOptimizer.tests.test_stage1 import _matrix


def test_one_test_at_one_standard_deviation_passes_by_luck_about_one_time_in_six():
    ex = RES.exposure(n_tests=1, k=1.0)
    assert abs(ex["false_pass_rate_per_test"] - 0.158655) < 1e-6
    assert abs(ex["chance_of_at_least_one_false_pass"] - 0.158655) < 1e-6


def test_the_chance_of_at_least_one_false_pass_grows_with_the_number_of_tests():
    ex = RES.exposure(n_tests=6, k=1.0)
    p = 0.15865525393145707
    assert abs(ex["chance_of_at_least_one_false_pass"] - (1 - (1 - p) ** 6)) < 1e-12
    assert ex["chance_of_at_least_one_false_pass"] > 0.6
    assert ex["n_tests"] == 6 and ex["k"] == 1.0


def test_no_tests_is_said_as_no_tests_not_as_zero_risk_from_a_computation():
    ex = RES.exposure(n_tests=0, k=1.0)
    assert ex["n_tests"] == 0
    assert ex["chance_of_at_least_one_false_pass"] is None
    assert "no comparison" in ex["sentence"].lower()


def test_the_sentence_says_it_is_an_upper_bound_and_changes_nothing():
    s = RES.exposure(n_tests=4, k=1.0)["sentence"].lower()
    assert "4 " in s
    assert "upper bound" in s
    assert "changes nothing" in s


def test_stage1_reports_the_exposure_counting_only_comparisons_that_could_be_formed():
    res = S1.run_stage1(_matrix(), hemispheres=("Left", "Right"), primary_item="left_leg_vas",
                        data_horizon="2026-12-31")
    ex = res.audit.get("resolution_exposure")
    assert ex is not None, "Stage 1 carries the exposure on its audit, which the page receives"
    formed = 0
    for _k, sl in res.slices.items():
        for _r, rs in (sl.rate_strata or {}).items():
            g = ((rs.resolution or {}).get("gain") or {}) if rs.fitted else {}
            if g.get("passes") is not None:
                formed += 1
    for rs in (res.pooled_rate_strata or {}).values():
        g = ((rs.resolution or {}).get("gain") or {}) if rs.fitted else {}
        if g.get("passes") is not None:
            formed += 1
    assert ex["n_tests"] == formed
    assert ex["k"] == S1.RESOLUTION_K
    if formed:
        assert math.isclose(ex["chance_of_at_least_one_false_pass"],
                            1 - (1 - ex["false_pass_rate_per_test"]) ** formed)


def test_stage1_names_the_rate_length_scale_as_a_pinned_assumption():
    """Panel C item 7: the one-octave pin is reported on the response, with the value this run
    actually used, as an assumption and not an estimate."""
    res = S1.run_stage1(_matrix(), hemispheres=("Left", "Right"), primary_item="left_leg_vas",
                        data_horizon="2026-12-31")
    fl = res.audit.get("frequency_length_scale")
    assert fl is not None
    assert fl["pinned"] is True
    assert fl["value"] == S1.JOINT_FIXED_LENGTH_SCALE[0] == 0.823
    assert "assumption" in fl["why"] and "bimodal" in fl["why"]
    assert "per-rate current surfaces" in fl["acts_on"]
