"""One resolution rule, and the figure headline must not contradict the verdict.

The defect these pin was live for five days. `plots._incumbent_verdict` compared the predicted gain
against `opt_posterior_sd` — the CANDIDATE's posterior standard deviation at the grid minimum —
while the gate in `pipeline.ArmResult.surface_can_resolve_its_optimum` had been corrected on
2026-08-30 to compare against the propagated standard deviation of the DIFFERENCE. So the headline
could print the strong claim on an arm whose optimum the module itself reported as unresolved.
"""
import numpy as np
import pytest

from StimOptimizer import pipeline, stage1_openloop
from StimOptimizer.routines import plots as PLT
from StimOptimizer.routines import resolution as RES


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


def test_the_constant_has_exactly_one_definition():
    """`stage1_openloop.RESOLUTION_K` is a re-export, so a change cannot apply to only some
    callers. Existing importers read it from either place and must agree."""
    assert stage1_openloop.RESOLUTION_K is RES.RESOLUTION_K


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
