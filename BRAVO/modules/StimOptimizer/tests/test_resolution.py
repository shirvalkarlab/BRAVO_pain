"""One resolution rule, and the figure headline must not contradict the verdict.

The defect these pin was live for five days. `plots._incumbent_verdict` compared the predicted gain
against `opt_posterior_sd` — the CANDIDATE's posterior standard deviation at the grid minimum —
while the gate in `pipeline.ArmResult.surface_can_resolve_its_optimum` had been corrected on
2026-08-30 to compare against the propagated standard deviation of the DIFFERENCE. So the headline
could print the strong claim on an arm whose optimum the module itself reported as unresolved.

Merged here 2026-10-05: test_resolution_exposure.py (each under its own heading below).
"""
import numpy as np
import pytest

from StimOptimizer import pipeline
from StimOptimizer.routines import plots as PLT
from StimOptimizer.routines import resolution as RES
import math

from StimOptimizer import stage1_openloop as S1
from StimOptimizer.tests.test_stage1 import _matrix


# The arm that motivated the original gate correction, with its real numbers.
GAIN, SD_CANDIDATE, SD_INCUMBENT = 1.117, 0.989, 0.923


def test_the_propagated_sd_is_what_the_worked_example_says():
    sd = RES.sd_of_difference(SD_CANDIDATE, SD_INCUMBENT)
    assert sd == pytest.approx(1.353, abs=5e-4)
    # the criterion the figure headline used to apply, kept here so the difference is explicit
    assert GAIN > SD_CANDIDATE, "the candidate-SD-only criterion passed, which is why it was wrong"
    assert GAIN < sd, "the propagated criterion does not pass"
    assert RES.is_resolved(GAIN, SD_CANDIDATE, SD_INCUMBENT) is False


def test_is_resolved_keeps_three_states_apart():
    assert RES.is_resolved(5.0, 0.1, 0.1) is True
    assert RES.is_resolved(0.01, 1.0, 1.0) is False
    # a difference that cannot be FORMED is not a difference that is too small to call
    assert RES.is_resolved(1.0, 0.0, 0.0) is None
    assert RES.is_resolved(1.0, float("nan"), 0.5) is None
    assert RES.is_resolved(float("nan"), 0.5, 0.5) is None


def _ctx_with(mu_min, sd_opt, sd_inc):
    """A stand-in carrying only the meta keys the headline reads."""
    class _Ctx:
        meta = {"mu_min": mu_min, "opt_posterior_sd": sd_opt, "incumbent_sd": sd_inc}
    return _Ctx()


def test_the_figure_headline_does_not_contradict_the_gate():
    """The load-bearing test. Same numbers into both, and they must reach the same conclusion."""
    ctx = _ctx_with(-GAIN, SD_CANDIDATE, SD_INCUMBENT)
    headline = PLT._incumbent_verdict(ctx)

    gate = pipeline.ArmResult(
        site="left_leg", hemisphere="Right", ctx=None, batch=None, queue=None, stopping=None,
        meta={"mu_star": -GAIN, "sd_star": SD_CANDIDATE,
              "incumbent_mu": 0.0, "incumbent_sd": SD_INCUMBENT},
    ).surface_can_resolve_its_optimum()

    assert gate is False, "the gate must still find this unresolved"
    assert "NOT resolved" in headline, f"the headline no longer agrees with the gate: {headline!r}"
    # and it must name the quantity it actually used, so a reader can check the arithmetic
    assert "SD of the difference" in headline
    assert "1.35" in headline, f"the propagated SD is not reported: {headline!r}"


def test_the_headline_reports_the_degenerate_case_as_its_own_answer():
    ctx = _ctx_with(-1.0, 0.0, 0.0)
    headline = PLT._incumbent_verdict(ctx)
    assert "could not be formed" in headline
    assert "NOT resolved" not in headline, "a difference that cannot be formed is a third answer"


def test_a_non_negative_minimum_still_supports_the_strong_negative_claim():
    assert PLT._incumbent_verdict(_ctx_with(0.4, 0.5, 0.5)) == \
        "Nothing on the grid is predicted better than the incumbent"


def test_no_call_site_still_spells_the_propagation_out_for_itself():
    """A grep-style guard. The point of the leaf module is that the arithmetic appears once; a
    future edit that re-inlines `sqrt(sd_star**2 + ...)` anywhere would reintroduce the drift this
    file exists to prevent."""
    import pathlib

    root = pathlib.Path(pipeline.__file__).parent
    offenders = []
    for path in list(root.glob("*.py")) + list((root / "routines").glob("*.py")):
        if path.name == "resolution.py":
            continue                                  # the one place it is allowed to live
        src = path.read_text()
        for marker in ('sd_star"]) ** 2 + sd_inc ** 2', 'sd_star")) ** 2 + float('):
            if marker in src:
                offenders.append(f"{path.name}: {marker}")
    assert not offenders, f"the propagation is spelled out again in: {offenders}"


# ================================================================================================
# From test_resolution_exposure.py (merged here 2026-10-05).
# How many times the "proven better than today's setting" test ran, and what that exposes.
#
# WHY (panel C item 4, 2026-09-22). A current is recommended at a rate only when its gain over the
# setting in force clears ONE standard deviation of that difference (`RESOLUTION_K = 1.0`). One
# standard deviation is a declared, modest bar, not a significance threshold: on a comparison where
# nothing is truly better, the gain alone clears it about one time in six (the upper tail of a normal
# curve beyond one standard deviation, 0.1587). The page runs that comparison once per rate per
# pulse-width pairing it can fit, and nothing on it said how many that was. Visibility only: nothing
# here changes the rule, refuses anything or corrects anything.
#
# Pinned on the values, never the shape.
# ================================================================================================


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


# Stage 1 runs here without its calibration check (`calibration_check=False`, 2026-10-02): a
# warning that changes no recommendation (decision 233, ruling 6), read by no test in this file,
# and held by `test_stratum_calibration.py`; its leave-one-out refits were most of each fit's time.
def test_stage1_reports_the_exposure_counting_only_comparisons_that_could_be_formed():
    res = S1.run_stage1(_matrix(), hemispheres=("Left", "Right"), primary_item="left_leg_vas",
                        data_horizon="2026-12-31", calibration_check=False)
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
                        data_horizon="2026-12-31", calibration_check=False)
    fl = res.audit.get("frequency_length_scale")
    assert fl is not None
    assert fl["pinned"] is True
    assert fl["value"] == S1.JOINT_FIXED_LENGTH_SCALE[0] == 0.823
    assert "assumption" in fl["why"] and "bimodal" in fl["why"]
    assert "per-rate current surfaces" in fl["acts_on"]
