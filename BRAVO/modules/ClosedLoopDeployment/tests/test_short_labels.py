"""The short labels the Closed-Loop decision card prints as its red and yellow bullets (decision 302).

The PI, 2026-09-26: when the device refuses a configuration the card lists why in red bullets of
five words or less, and evidence that should have been evaluated and was not in yellow bullets of
the same form. The words live beside the rules and checks they describe, on the server, so the page
prints them and cannot drift from them:

* every one of the 52 device rules carries a ``short_label`` of at most four words, carried on
  every row the evaluator emits, so "Unmet: <label>" or "Unchecked: <label>" is at most five;
* the report carries ``evidence_not_evaluated``: each evidence check that should have run and did
  not, with its own label of at most four words ("Untested: <label>" is at most five).
"""
from __future__ import annotations

import copy

import pytest

from ClosedLoopDeployment import adapter, constraints, types

from .test_constraints import passing_candidate, resolved_participant as participant_record


def _words(s):
    return len(str(s).split())


def test_every_device_rule_has_a_short_label_of_at_most_four_words():
    missing = [r.rule_id for r in constraints.RULES if not (r.short_label or "").strip()]
    assert missing == []
    too_long = [(r.rule_id, r.short_label) for r in constraints.RULES if _words(r.short_label) > 4]
    assert too_long == []
    assert len(constraints.RULES) == 52


def test_short_labels_are_distinct_so_two_bullets_never_read_the_same():
    labels = [r.short_label.lower() for r in constraints.RULES]
    assert len(set(labels)) == len(labels)


def test_every_row_the_evaluator_emits_carries_its_rules_short_label():
    cand = passing_candidate(pulse_width_us=160.0)       # D27 fails: above the 120 us ceiling
    part = participant_record()
    part.pop("brainsense_max_pulse_width_us", None)      # and a rule made not determinable
    rep = constraints.check_eligibility(cand, part)
    assert rep.unknowns, "the participant without its pulse-width ceiling should leave an unknown"
    rows = rep.failures + rep.unknowns + rep.advisories + list(rep.deferred or [])
    assert rows, "the mutated candidate should produce rows"
    for row in rows:
        assert row["short_label"] == constraints.RULES_BY_ID[row["rule_id"]].short_label
    assert any(r["rule_id"] == "D27" for r in rep.failures)


def test_a_rule_built_without_a_label_still_constructs():
    # Tests elsewhere build synthetic rules; the field has a default so they keep working.
    r = types.DeviceConstraint(rule_id="DX", title="t", source="s", page="p", severity="advisory",
                               human_text="h")
    assert r.short_label == ""


# ------------------------------------------------------------------------------------------------
# Evidence that should have been evaluated and was not
# ------------------------------------------------------------------------------------------------
def _payload():
    edge = lambda name, est: {"name": name, "estimate": est, "ci": [est - 1, est + 1], "p": 0.5,
                              "resolved": est is not None, "sign": None if est is None else -1}
    return {
        "available": True,
        "verdict_detail": {"device_eligible": True, "all_edges_resolved": True},
        "edges": {"E1": edge("E1", -1.0), "E2": edge("E2", 0.1), "E3": edge("E3", -0.2)},
        "coherence": {"coherent": True},
        "band_stability": {"answer": "cannot tell"},
    }


def test_nothing_is_listed_when_every_check_ran():
    assert adapter.evidence_not_evaluated(_payload()) == []


def test_an_edge_with_no_point_estimate_is_listed_by_its_own_label():
    p = _payload()
    p["edges"]["E1"] = {"name": "E1", "estimate": None, "resolved": False}
    out = adapter.evidence_not_evaluated(p)
    assert [r["key"] for r in out] == ["E1"]
    assert out[0]["label"] == adapter.EVIDENCE_CHECK_LABELS["E1"]
    assert out[0]["card"] and out[0]["why"]


def test_an_unrun_sign_test_and_an_unrun_stability_test_are_listed():
    p = _payload()
    p["coherence"] = {"coherent": None}
    p["band_stability"] = {"answer": "not tested", "reason": "one stimulation state only"}
    out = adapter.evidence_not_evaluated(p)
    assert [r["key"] for r in out] == ["coherence", "stability"]
    assert out[1]["why"] == "one stimulation state only"


def test_a_missing_edge_and_a_missing_stability_answer_are_listed():
    p = _payload()
    del p["edges"]["E3"]
    p.pop("band_stability")
    assert [r["key"] for r in adapter.evidence_not_evaluated(p)] == ["E3", "stability"]


def test_cannot_tell_is_an_answer_not_an_absence():
    # "cannot tell" means the test ran and could not settle it: that is on the stability card, not
    # a yellow "not evaluated" bullet.
    p = _payload()
    p["band_stability"] = {"answer": "cannot tell"}
    assert adapter.evidence_not_evaluated(p) == []


def test_sign_agreement_is_not_listed_twice_when_an_edge_is_missing():
    # With an edge missing the sign test cannot run by construction; the missing edge is the
    # finding, and a second bullet for the same absence would say one thing twice.
    p = _payload()
    p["edges"]["E2"] = {"name": "E2", "estimate": None, "resolved": False}
    p["coherence"] = {"coherent": None}
    assert [r["key"] for r in adapter.evidence_not_evaluated(p)] == ["E2"]


def test_evidence_labels_are_at_most_four_words():
    assert all(_words(v) <= 4 for v in adapter.EVIDENCE_CHECK_LABELS.values())
    assert set(adapter.EVIDENCE_CHECK_LABELS) == {"E1", "E2", "E3", "coherence", "stability"}


def test_an_unavailable_report_lists_nothing():
    assert adapter.evidence_not_evaluated({"available": False}) == []
    assert adapter.evidence_not_evaluated(None) == []


# ------------------------------------------------------------------------------------------------
# A refused configuration's record prints no switching value (decision 302)
# ------------------------------------------------------------------------------------------------
def _thr_payload(eligible):
    return {"available": True,
            "verdict_detail": {"device_eligible": eligible, "warnings": []},
            "threshold": {"lower": 75.24469939878163, "upper": 213.48343672013655}}


def test_the_switching_values_caveat_names_the_values_when_the_device_allows_them():
    rows = adapter.caveats_for_report(_thr_payload(True))
    text = " ".join(r["text"] for r in rows)
    assert "75.2447 and 213.4834" in text


def test_the_switching_values_caveat_withholds_the_values_when_the_device_refuses():
    # The parameter table withholds every value while the device refuses, because a number on screen
    # during a programming visit gets typed; the caveat on the same card printed both thresholds to
    # four places (found building decision 302 on R 0-3+). Same caveat, no number.
    for eligible in (False, None):
        rows = adapter.caveats_for_report(_thr_payload(eligible))
        text = " ".join(r["text"] for r in rows)
        assert "75.2447" not in text and "213.4834" not in text
        assert any("switching values" in r["text"] and "withheld" in r["text"] for r in rows)
