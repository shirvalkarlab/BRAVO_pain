"""Does the "behaves the same under every stimulation setting" answer survive the trip to the
closed-loop report?

Most of these tests are about ONE failure this project keeps repeating: the answer "we could not
tell" being written onto a page as either a pass or as "behaves differently". Both readings are
wrong and both are dangerous, because the thing being decided is whether a value gets programmed
into a stimulator that delivers current to somebody's brain. So the tests below are less interested
in whether the arithmetic is right -- that lives in the Biomarkers module and is tested there -- and
much more interested in whether the three-way answer can be flattened by a caller.

None of these tests needs R. The statistical fits live in Biomarkers and are exercised there; here
we feed the translation the shapes that test produces, including the shapes it produces when it
fails, so the report's handling of a failure is tested rather than assumed.
"""
import dataclasses

import numpy as np
import pytest

from ClosedLoopDeployment import stability as ST


def _slopes(diff, se, n=40):
    """Two stimulation states whose slopes differ by `diff`, each measured to `se`."""
    return {"OFF": {"slope_log_or": 0.0, "se": se, "n": n},
            "HIGH": {"slope_log_or": float(diff), "se": se, "n": n}}


def _result(verdict=None, *, slopes=None, lrt_p=0.4, margin=None, rate=None, n=120):
    """A stand-in for what Biomarkers.band_stim_stability returns when it succeeds.

    The equivalence block is built by calling the REAL stability_equivalence rather than being
    hand-written, so these tests cannot drift away from what the module actually emits.
    """
    slopes = _slopes(0.1, 0.1) if slopes is None else slopes
    m = ST.STABILITY_EQUIVALENCE_MARGIN_LOG_OR if margin is None else margin
    equivalence = ST.stability_equivalence(slopes, lrt_p, margin=m)
    if verdict is not None:
        equivalence = dict(equivalence, verdict=verdict)
    return {"available": True, "lrt_p": lrt_p, "slope_by_era": slopes,
            "equivalence": equivalence, "stability_verdict": equivalence.get("verdict"),
            "n": n, "n_clusters": 5,
            "era_counts": {"OFF": 40, "LOW": 30, "HIGH": 50},
            "rate": rate or {"available": False, "reason": "no rate series supplied"}}


# ------------------------------------------------------------------------------------------------
# The answer stays three-valued, and "cannot tell" is neither of the other two
# ------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("upstream,expected", [
    ("stable", "behaves the same"),
    ("stim-dependent", "behaves differently"),
    ("inconclusive", "cannot tell"),
])
def test_each_biomarkers_verdict_keeps_its_own_meaning(upstream, expected):
    f = ST.finding_from_stability_result(_result(upstream), "ZERO_THREE_RIGHT", 24.5)
    assert f.answer == expected
    assert f.test_ran is True


def test_cannot_tell_is_not_a_pass_and_is_not_behaves_differently():
    """The whole reason this file exists. "cannot tell" has to answer no to BOTH of the other two
    questions; a reader or a page that asks either one must not be told yes."""
    f = ST.finding_from_stability_result(_result("inconclusive"), "ZERO_THREE_RIGHT", 24.5)
    assert f.answer_is("cannot tell")
    assert not f.answer_is("behaves the same")
    assert not f.answer_is("behaves differently")
    assert "cannot tell" in f.headline()


def test_the_finding_offers_no_true_or_false_summary_of_the_answer():
    """A boolean field is the mechanism by which "cannot tell" gets flattened: the moment one
    exists, somebody writes `if finding.stable:` and every "cannot tell" in the study becomes a
    failure. So no such field may exist, under any of the names it would plausibly be given."""
    f = ST.finding_from_stability_result(_result("inconclusive"), "ZERO_THREE_RIGHT", 24.5)
    for name in ("stable", "stim_stable", "ok", "passed", "passes", "is_stable", "eligible",
                 "blocks", "blocking", "failed", "valid"):
        assert not hasattr(f, name), f"{name!r} must not exist: it invites a two-way reading"
    # Nothing in the payload is a true-or-false verdict either. test_ran is allowed, because it
    # says whether the test ran, not what it concluded.
    booleans = [k for k, v in f.as_payload().items() if isinstance(v, bool)]
    assert booleans == ["test_ran"], f"unexpected true-or-false keys in the payload: {booleans}"


def test_asking_about_a_word_that_is_not_an_answer_is_an_error_not_a_no():
    """`answer_is("stable")` returning False would look exactly like a band that is not stable,
    which is the same flattening by another route. It has to raise instead."""
    f = ST.finding_from_stability_result(_result("stable"), "ZERO_THREE_RIGHT", 24.5)
    assert f.answer_is("behaves the same")
    for wrong in ("stable", "inconclusive", "pass", "yes", ""):
        with pytest.raises(ValueError):
            f.answer_is(wrong)


def test_an_answer_outside_the_four_cannot_be_constructed():
    with pytest.raises(ValueError):
        ST.BandStabilityFinding(electrode="ZERO_THREE_RIGHT", band_center_hz=24.5,
                                band_width_hz=5.0, answer="probably fine", reason="",
                                test_ran=True, declared_margin=0.69)


def test_not_tested_and_test_ran_cannot_disagree():
    """A finding claiming the test ran while reporting "not tested" (or the reverse) would let a
    page show a verdict that nothing produced."""
    common = dict(electrode="ZERO_THREE_RIGHT", band_center_hz=24.5, band_width_hz=5.0,
                  reason="", declared_margin=0.69)
    with pytest.raises(ValueError):
        ST.BandStabilityFinding(answer="not tested", test_ran=True, **common)
    with pytest.raises(ValueError):
        ST.BandStabilityFinding(answer="cannot tell", test_ran=False, **common)


# ------------------------------------------------------------------------------------------------
# When the test could not run at all
# ------------------------------------------------------------------------------------------------
def test_a_test_that_could_not_run_says_so_rather_than_borrowing_an_answer():
    f = ST.finding_from_stability_result(
        {"available": False, "reason": "no stim series"}, "ONE_THREE_LEFT", 12.5)
    assert f.answer == "not tested"
    assert f.test_ran is False
    assert "no stim series" in f.reason
    assert not f.answer_is("behaves the same")
    assert not f.answer_is("behaves differently")


@pytest.mark.parametrize("junk", [None, {}, [], "no", {"available": True}])
def test_anything_unusable_from_upstream_becomes_not_tested(junk):
    f = ST.finding_from_stability_result(junk, "ONE_THREE_LEFT", 12.5)
    assert f.answer == "not tested"


def test_a_verdict_word_we_do_not_recognise_is_not_guessed_at():
    """If Biomarkers grows a fourth verdict, treating it as one of the three we know would put a
    conclusion on the page that nobody drew. Saying "not tested" is the only honest option."""
    f = ST.finding_from_stability_result(_result("mostly-stable"), "ZERO_THREE_RIGHT", 24.5)
    assert f.answer == "not tested"
    assert "does not recognise" in f.reason and "mostly-stable" in f.reason


def test_a_test_that_raises_is_reported_not_propagated():
    """A report listing every other check is more use to a clinician than a page that will not
    load, so an exception inside the statistics becomes a "not tested" row."""
    f = ST.assess_band_stability({"anything": 1}, "ZERO_THREE_RIGHT", 24.5,
                                 stim_series={"t": [0.0], "y": [1.0]})
    assert f.answer == "not tested"
    assert f.test_ran is False


# ------------------------------------------------------------------------------------------------
# The declared margin is part of the claim, and re-deciding against a different one is honest
# ------------------------------------------------------------------------------------------------
def test_widening_the_declared_margin_can_turn_cannot_tell_into_behaves_the_same():
    """"Behaves the same" means the remaining difference is smaller than a difference we declared
    in advance would matter. Change that declaration and the answer can legitimately change, which
    is exactly why the declared margin is carried on the finding rather than hidden."""
    slopes = _slopes(0.5, 0.2)
    at_default = ST.finding_from_stability_result(
        _result(slopes=slopes, lrt_p=0.40), "ZERO_THREE_RIGHT", 24.5)
    assert at_default.answer == "cannot tell"
    wider = ST.finding_from_stability_result(
        _result(slopes=slopes, lrt_p=0.40), "ZERO_THREE_RIGHT", 24.5, margin=2.0)
    assert wider.answer == "behaves the same"
    assert wider.declared_margin == pytest.approx(2.0)


def test_narrowing_the_declared_margin_can_take_a_pass_away():
    slopes = _slopes(0.1, 0.1)
    assert ST.finding_from_stability_result(
        _result(slopes=slopes, lrt_p=0.40), "ZERO_THREE_RIGHT", 24.5).answer == "behaves the same"
    strict = ST.finding_from_stability_result(
        _result(slopes=slopes, lrt_p=0.40), "ZERO_THREE_RIGHT", 24.5, margin=0.05)
    assert strict.answer == "cannot tell"


def test_no_margin_makes_behaves_differently_into_a_pass():
    """"Behaves differently" comes from the test finding a real difference, not from the size of
    the declared margin, so no choice of margin may talk it round into a pass."""
    slopes = _slopes(1.4, 0.2)
    for margin in (0.01, 0.69, 5.0, 100.0):
        f = ST.finding_from_stability_result(
            _result(slopes=slopes, lrt_p=0.001), "ZERO_THREE_RIGHT", 24.5, margin=margin)
        assert f.answer == "behaves differently", margin


def test_fewer_than_two_comparable_states_is_cannot_tell_not_a_pass():
    """With only one stimulation state there is nothing to compare, and the equivalence test says
    so. That must arrive as "cannot tell" and never as agreement by default."""
    f = ST.finding_from_stability_result(
        _result(slopes={"OFF": {"slope_log_or": 0.2, "se": 0.1, "n": 40}, "HIGH": None},
                lrt_p=0.9), "ZERO_THREE_RIGHT", 24.5)
    assert f.answer == "cannot tell"
    assert f.n_states_compared == 1


# ------------------------------------------------------------------------------------------------
# What the report carries alongside the answer
# ------------------------------------------------------------------------------------------------
def test_the_payload_carries_the_evidence_and_all_four_possible_answers():
    f = ST.finding_from_stability_result(_result("inconclusive"), "ZERO_THREE_RIGHT", 24.5)
    p = f.as_payload()
    assert p["answer"] == "cannot tell"
    assert p["answers_possible"] == list(ST.ANSWERS) and len(p["answers_possible"]) == 4
    assert p["n_measurements"] == 120 and p["n_time_blocks"] == 5
    assert p["measurements_per_state"] == {"stimulation off": 40, "low current": 30,
                                           "high current": 50}
    assert p["band_center_hz"] == 24.5 and p["band_width_hz"] == 5.0
    assert len(p["difference_interval"]) == 2
    assert p["reason"]
    # Every key must be plain data, so serialising the payload cannot fail on the page.
    import json
    json.loads(json.dumps(p))


def test_the_blocking_decision_is_recorded_as_undecided_and_is_not_a_boolean():
    """Reporting this as "does not block" would read on the page as "this was checked and it was
    fine". It has not been ruled on, and the phrase has to say that."""
    f = ST.finding_from_stability_result(_result("stim-dependent"), "ZERO_THREE_RIGHT", 24.5)
    assert f.blocking_status == ST.BLOCKING_STATUS
    assert not isinstance(f.blocking_status, bool)
    assert "not decided" in f.blocking_status
    assert f.as_payload()["blocking_status"] == ST.BLOCKING_STATUS


def test_the_rate_warnings_come_through_and_are_absent_rather_than_false_when_unknown():
    """Whether the stimulation rate was changing at the same moments as the current decides how
    much the answer is worth. When no rate information was supplied that has to be missing, not
    False -- False would say the confusion was checked for and ruled out."""
    without = ST.finding_from_stability_result(_result("stable"), "ZERO_THREE_RIGHT", 24.5)
    assert without.rate_moved_with_current is None
    assert without.distance_to_nearest_artifact_hz is None

    with_rate = ST.finding_from_stability_result(
        _result("stable", rate={"available": True, "rate_confounded_with_era": True,
                                "band_near_harmonic_hz": 0.5}), "ZERO_THREE_RIGHT", 24.5)
    assert with_rate.rate_moved_with_current is True
    assert with_rate.distance_to_nearest_artifact_hz == 0.5


def test_the_finding_cannot_be_edited_after_it_is_made():
    """A verdict a page could rewrite in passing is not a finding."""
    f = ST.finding_from_stability_result(_result("inconclusive"), "ZERO_THREE_RIGHT", 24.5)
    assert dataclasses.is_dataclass(f)
    with pytest.raises(dataclasses.FrozenInstanceError):
        f.answer = "behaves the same"


# ------------------------------------------------------------------------------------------------
# Several bands at once
# ------------------------------------------------------------------------------------------------
def test_the_summary_always_shows_all_four_answers_including_the_zeros():
    """A page that shows three categories for one participant and four for another invites the
    reader to think "cannot tell" was not among the options."""
    findings = [
        ST.finding_from_stability_result(_result("stable"), "ZERO_THREE_RIGHT", 24.5),
        ST.finding_from_stability_result(_result("inconclusive"), "ZERO_THREE_RIGHT", 25.5),
        ST.finding_from_stability_result(_result("inconclusive"), "ONE_THREE_LEFT", 12.5),
        ST.finding_from_stability_result({"available": False, "reason": "no R"},
                                         "ONE_THREE_LEFT", 13.5),
    ]
    s = ST.summarise(findings)
    assert s["n_assessed"] == 4
    assert s["counts_by_answer"] == {"behaves the same": 1, "behaves differently": 0,
                                     "cannot tell": 2, "not tested": 1}
    assert set(s["counts_by_answer"]) == set(ST.ANSWERS)
    assert "neither a pass nor a failure" in s["note"]


def test_an_empty_summary_still_names_every_answer():
    s = ST.summarise([])
    assert s["n_assessed"] == 0
    assert s["counts_by_answer"] == {a: 0 for a in ST.ANSWERS}


def test_nothing_here_imports_the_closed_loop_side_back_into_biomarkers():
    """The dependency runs one way only. If Biomarkers ever imported this module the pair would
    stop loading, and the failure would appear far from its cause.

    Read the import statements rather than searching the text: Biomarkers names this module in its
    comments in several places, quite properly, to explain which side of the boundary a calculation
    belongs on. Only a real import is a problem, so only real imports are checked.
    """
    import ast

    import Biomarkers.routines.analytics as A
    tree = ast.parse(open(A.__file__, encoding="utf-8").read())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    offenders = sorted(m for m in imported if m.split(".")[0] == "ClosedLoopDeployment")
    assert offenders == [], f"Biomarkers must not import the closed-loop side: {offenders}"
