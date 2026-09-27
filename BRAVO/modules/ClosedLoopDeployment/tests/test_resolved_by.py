"""Who can clear a device-rule refusal, carried on every row the evaluator emits, and the rule
table's one-line summary counting its rows by what they are (review findings, 2026-09-26).

Every refusal used to read "measurement, a property of the recording" on the Closed-Loop page,
because the evaluator gives every blocking rule that fails the same kind ("failed") and the page
mapped that one kind to one actor. D52 (the sensing pair must flank the stimulating contacts) is
cleared at the programmer by a change of contacts, not by measuring anything. Each blocking rule
now says which of four things clears it, in ``constraints.RESOLVED_BY``, and the row carries it.
"""
from __future__ import annotations

from ClosedLoopDeployment import constraints, types

from .test_constraints import passing_candidate, resolved_participant as participant_record

KINDS = {"configuration", "band", "recording", "analysis"}


def test_every_blocking_rule_says_what_clears_it():
    blocking = [r.rule_id for r in constraints.RULES if r.severity == "blocking"]
    missing = [rid for rid in blocking if constraints.RESOLVED_BY.get(rid) not in KINDS]
    assert missing == []


def test_the_map_names_only_real_rules_and_only_the_four_kinds():
    assert set(constraints.RESOLVED_BY) <= set(constraints.RULES_BY_ID)
    assert set(constraints.RESOLVED_BY.values()) <= KINDS


def test_a_sensing_pair_refusal_is_cleared_at_the_programmer_not_by_measurement():
    assert constraints.RESOLVED_BY["D52"] == "configuration"
    assert constraints.RESOLVED_BY["D27"] == "configuration"
    assert constraints.RESOLVED_BY["D16"] == "recording"
    assert constraints.RESOLVED_BY["D17"] == "recording"
    assert constraints.RESOLVED_BY["D19"] == "band"
    assert constraints.RESOLVED_BY["D11"] == "analysis"


def test_every_failed_row_carries_what_clears_it():
    cand = passing_candidate(pulse_width_us=160.0)       # D27 fails: above the 120 us ceiling
    rep = constraints.check_eligibility(cand, participant_record())
    d27 = [r for r in rep.failures if r["rule_id"] == "D27"]
    assert d27 and d27[0]["resolved_by"] == "configuration"
    for row in rep.failures + rep.unknowns + rep.advisories + list(rep.deferred or []):
        assert row["resolved_by"] == constraints.RESOLVED_BY.get(row["rule_id"], "")


def test_the_eligible_summary_does_not_call_a_passed_rule_an_advisory():
    rep = types.EligibilityReport(
        eligible=True, checked=52,
        advisories=[{"rule_id": "D52", "kind": "recorded_value"},
                    {"rule_id": "D03", "kind": "recorded_value"},
                    {"rule_id": "D09", "kind": "advisory_failed"}])
    s = rep.summary()
    assert "3 advisory" not in s
    assert s == "eligible (52 rules checked; 2 passed with their value shown, 1 advisory)"


def test_the_eligible_summary_names_a_zero_count_of_passed_values():
    rep = types.EligibilityReport(eligible=True, checked=52,
                                  advisories=[{"rule_id": "D09", "kind": "advisory_failed"}])
    assert rep.summary() == "eligible (52 rules checked; 0 passed with their value shown, 1 advisory)"
