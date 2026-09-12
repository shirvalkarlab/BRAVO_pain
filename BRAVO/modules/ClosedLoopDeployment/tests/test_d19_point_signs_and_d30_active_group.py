"""Two decisions by the principal investigator, 2026-09-12, pinned by value.

D19 (control polarity) passes on the POINT signs of the two edges, whether or not each edge's
interval excludes zero; the established-or-not distinction travels beside each sign and the
ledger row names any sign that is not established, with its interval and p-value.

D30 (the chosen rate is committed for this attempt) is DERIVED from the device: the candidate's
rate counts as committed when it equals the rate frozen in the device's newest ACTIVE sensing
group, read live from the newest ingested session report rather than from the stale committed
summary.

No database anywhere in this file: the report parser is pure, the derivation is pure, and the
memo's miss-on-new-file rule is exercised through the key alone.
"""
from __future__ import annotations

from ClosedLoopDeployment import adapter as AD, constraints, device_facts as DF
from ClosedLoopDeployment import pipeline as PL
from ClosedLoopDeployment.types import EdgeEstimate

RCS08_UID = "2e3c75c00d7f4f37b53a048d195f11da"


def _participant():
    return {"uid": RCS08_UID, "indication": "chronic_pain", "programming_mode": "parkinsons"}


def _d19(cand):
    return constraints.RULES_BY_ID["D19"].predicate(cand, _participant())


def _d30(cand):
    return constraints.RULES_BY_ID["D30"].predicate(cand, _participant())


# ------------------------------------------------------------------------------------------------
# D19
# ------------------------------------------------------------------------------------------------
def test_d19_passes_on_the_expected_point_signs_even_when_neither_edge_is_resolved():
    """RCS08 at the committed band on 2026-09-12: E1 −4.45 with interval −18.6 to +9.7 (p 0.54),
    E2 an AUC of 0.588 with interval 0.477 to 0.695 -- both unresolved, both with the right point
    sign. Under the old rule D19 was not determinable; under the PI's decision it passes."""
    e1 = EdgeEstimate("E1", -4.45, (-18.6, 9.7), 0.54, 13, "run", 4)
    e2 = EdgeEstimate("E2", 0.088, (-0.023, 0.195), 0.12, 400, "rating", 60)
    assert e1.resolved is False and e2.resolved is False
    facts = PL._facts_for({"channel": "ZERO_TWO_LEFT", "center_hz": 24.5}, e1, e2, "power_linear")
    assert facts["power_slope_vs_amplitude_sign"] == -1
    assert facts["power_slope_vs_pain_sign"] == 1
    assert _d19(facts) is True


def test_d19_established_flags_are_false_for_an_unresolved_edge_and_true_for_a_resolved_one():
    unresolved = EdgeEstimate("E1", -4.45, (-18.6, 9.7), 0.54, 13, "run", 4)
    resolved = EdgeEstimate("E2", 0.9, (0.5, 1.3), 0.001, 400, "rating", 60)
    facts = PL._facts_for({}, unresolved, resolved, "power_linear")
    assert facts["power_slope_vs_amplitude_sign_established"] is False
    assert facts["power_slope_vs_pain_sign_established"] is True
    assert facts["power_slope_vs_amplitude_ci"] == [-18.6, 9.7]
    assert facts["power_slope_vs_amplitude_p"] == 0.54
    assert facts["power_slope_vs_pain_ci"] == [0.5, 1.3]
    assert facts["power_slope_vs_pain_p"] == 0.001


def test_d19_still_fails_on_a_wrong_point_sign_whether_or_not_it_is_established():
    """The decision changes WHICH sign is read, not what the rule requires of it."""
    wrong_e1 = EdgeEstimate("E1", 2.0, (-1.0, 5.0), 0.3, 13, "run", 4)      # unresolved, positive
    right_e2 = EdgeEstimate("E2", 0.9, (0.5, 1.3), 0.001, 400, "rating", 60)
    assert _d19(PL._facts_for({}, wrong_e1, right_e2, "power_linear")) is False


def test_d19_observer_names_the_unestablished_edge_with_its_interval_and_p_value():
    e1 = EdgeEstimate("E1", -4.45, (-18.6, 9.7), 0.54, 13, "run", 4)
    e2 = EdgeEstimate("E2", 0.9, (0.5, 1.3), 0.001, 400, "rating", 60)
    facts = PL._facts_for({}, e1, e2, "power_linear")
    observed = constraints._o_d19(facts, _participant())
    assert "power-versus-amplitude slope sign -1" in observed
    assert "NOT statistically established" in observed
    assert "interval -18.6 to 9.7" in observed
    assert "p 0.54" in observed
    # The established edge is stated plainly and is NOT flagged.
    pain_part = observed.split(" and ")[-1]
    assert "power-versus-pain slope sign 1" in pain_part
    assert "NOT statistically established" not in pain_part


def test_d19_observer_flags_nothing_when_both_signs_are_established():
    e1 = EdgeEstimate("E1", -1.0, (-1.5, -0.5), 0.01, 50, "setting epoch", 60)
    e2 = EdgeEstimate("E2", 0.9, (0.5, 1.3), 0.001, 400, "rating", 60)
    observed = constraints._o_d19(PL._facts_for({}, e1, e2, "power_linear"), _participant())
    assert "NOT statistically established" not in observed


def test_d19_is_not_determinable_when_a_candidate_carries_no_edge_at_all():
    facts = PL._facts_for({"channel": "ZERO_TWO_LEFT"}, None, None, "power_linear")
    assert "power_slope_vs_amplitude_sign" not in facts
    assert "power_slope_vs_pain_sign" not in facts
    assert _d19(facts) is None


def test_d19_is_not_determinable_when_an_edge_exists_but_has_no_estimate():
    """An edge that could not be estimated has no sign to supply, established or not."""
    no_est = EdgeEstimate("E1", None, None, None, 0, "run", 0)
    e2 = EdgeEstimate("E2", 0.9, (0.5, 1.3), 0.001, 400, "rating", 60)
    facts = PL._facts_for({}, no_est, e2, "power_linear")
    assert "power_slope_vs_amplitude_sign" not in facts
    assert _d19(facts) is None


def test_d19_pass_is_recorded_on_the_ledger_with_its_observed_signs():
    """A pass on a point sign must not vanish from the ledger, or the caveat is unreadable."""
    e1 = EdgeEstimate("E1", -4.45, (-18.6, 9.7), 0.54, 13, "run", 4)
    e2 = EdgeEstimate("E2", 0.9, (0.5, 1.3), 0.001, 400, "rating", 60)
    facts = PL._facts_for({}, e1, e2, "power_linear")
    report = constraints.check_eligibility(facts, _participant(),
                                         rules=[constraints.RULES_BY_ID["D19"]])
    rows = [r for r in report.advisories if r["rule_id"] == "D19"]
    assert len(rows) == 1 and rows[0]["kind"] == "recorded_value"
    assert "NOT statistically established" in rows[0]["observed"]


def test_d19_human_text_records_the_pi_decision_and_its_date():
    text = constraints.RULES_BY_ID["D19"].human_text
    assert "2026-09-12" in text and "POINT signs" in text
    assert "not statistically established" in text


# ------------------------------------------------------------------------------------------------
# D30 -- the derivation
# ------------------------------------------------------------------------------------------------
_ACTIVE_55 = {"active_sensing_group": "GROUP_D", "active_sensing_group_rate_hz": 55.0,
              "active_sensing_group_pulse_widths_us": [100, 150],
              "active_sensing_group_adaptive_status": ["RUNNING", "RUNNING"],
              "session_report_date": "2026-09-11T15:30:00Z"}


def test_d30_equal_rates_give_true_with_the_group_named_in_the_provenance():
    out = AD.rate_commitment_from_active_group(55.0, _ACTIVE_55)
    assert out["rate_committed_for_this_attempt"] is True
    assert "GROUP_D" in out["_provenance"]
    assert "55 Hz" in out["_provenance"] and "2026-09-12" in out["_provenance"]
    assert _d30({"rate_hz": 55.0, "rate_committed_for_this_attempt": True}) is True


def test_d30_unequal_rates_give_false_and_say_a_new_group_and_capture_would_be_needed():
    out = AD.rate_commitment_from_active_group(110.0, _ACTIVE_55)
    assert out["rate_committed_for_this_attempt"] is False
    assert "110 Hz" in out["_provenance"] and "55 Hz" in out["_provenance"]
    assert "new group" in out["_provenance"] and "threshold capture" in out["_provenance"]
    assert _d30({"rate_hz": 110.0, "rate_committed_for_this_attempt": False}) is False


def test_d30_an_unknown_rate_on_either_side_supplies_nothing_and_leaves_d30_not_determinable():
    assert AD.rate_commitment_from_active_group(None, _ACTIVE_55) == {}
    assert AD.rate_commitment_from_active_group(55.0, {}) == {}
    assert AD.rate_commitment_from_active_group(55.0, {"active_sensing_group_rate_hz": None}) == {}
    assert AD.rate_commitment_from_active_group("not a number", _ACTIVE_55) == {}
    assert _d30({"rate_hz": 55.0}) is None


def test_d30_observer_states_the_candidate_rate_the_active_groups_rate_and_the_group():
    cand = {"rate_hz": 55.0, "rate_committed_for_this_attempt": True, **_ACTIVE_55}
    observed = constraints._o_d30(cand, _participant())
    assert "candidate rate 55.0 Hz" in observed
    assert "GROUP_D" in observed
    assert "55.0 Hz" in observed
    assert "committed for this attempt: True" in observed


def test_d30_human_text_records_the_pi_decision_and_its_date():
    text = constraints.RULES_BY_ID["D30"].human_text
    assert "2026-09-12" in text and "option a" in text and "ACTIVE sensing group" in text


def test_every_new_d19_and_d30_key_is_declared_in_candidate_keys():
    for key in ("power_slope_vs_amplitude_sign_established", "power_slope_vs_pain_sign_established",
                "power_slope_vs_amplitude_ci", "power_slope_vs_amplitude_p",
                "power_slope_vs_pain_ci", "power_slope_vs_pain_p",
                "rate_committed_for_this_attempt", "active_sensing_group",
                "active_sensing_group_rate_hz", "active_sensing_group_pulse_widths_us",
                "active_sensing_group_adaptive_status", "session_report_date"):
        assert key in constraints.CANDIDATE_KEYS, key
    assert constraints.CANDIDATE_KEYS["rate_committed_for_this_attempt"].startswith("D30")


# ------------------------------------------------------------------------------------------------
# D30 -- reading the active sensing group off a session report, and the memo
# ------------------------------------------------------------------------------------------------
def _group(gid, active, sensing, rate=55.0, pw=(100, 150), status="RUNNING"):
    ps = {"RateInHertz": rate}
    if sensing:
        ps["SensingChannel"] = [{"PulseWidthInMicroSecond": w, "AdaptiveTherapyStatus": status,
                                 "RateInHertz": rate} for w in pw]
    return {"GroupId": gid, "ActiveGroup": active, "ProgramSettings": ps}


def test_active_sensing_group_from_report_reads_the_active_group_that_has_sensing():
    report = {"SessionDate": "2026-09-11T15:30:00Z",
              "Groups": {"Final": [
                  _group("GroupIdDef.GROUP_A", active=False, sensing=True, rate=110.0),
                  _group("GroupIdDef.GROUP_B", active=True, sensing=False, rate=145.0),
                  _group("GroupIdDef.GROUP_D", active=True, sensing=True, rate=55.0)]}}
    facts = DF.active_sensing_group_from_report(report)
    assert facts == {"active_sensing_group": "GROUP_D",
                     "active_sensing_group_rate_hz": 55.0,
                     "active_sensing_group_pulse_widths_us": [100, 150],
                     "active_sensing_group_adaptive_status": ["RUNNING", "RUNNING"],
                     "session_report_date": "2026-09-11T15:30:00Z"}


def test_active_sensing_group_from_report_is_empty_when_no_active_group_has_sensing():
    report = {"SessionDate": "2026-09-11T15:30:00Z",
              "Groups": {"Final": [
                  _group("GroupIdDef.GROUP_A", active=False, sensing=True),
                  _group("GroupIdDef.GROUP_B", active=True, sensing=False)]}}
    assert DF.active_sensing_group_from_report(report) == {}
    assert DF.active_sensing_group_from_report({}) == {}
    assert DF.active_sensing_group_from_report(None) == {}
    assert DF.active_sensing_group_from_report({"Groups": {"Initial": [
        _group("GroupIdDef.GROUP_D", active=True, sensing=True)]}}) == {}


def test_active_sensing_group_from_report_reads_the_final_groups_not_the_initial_ones():
    """Final is what the device left the clinic running; Initial is what it arrived with."""
    report = {"Groups": {"Initial": [_group("GroupIdDef.GROUP_A", True, True, rate=110.0)],
                         "Final": [_group("GroupIdDef.GROUP_D", True, True, rate=55.0)]}}
    assert DF.active_sensing_group_from_report(report)["active_sensing_group_rate_hz"] == 55.0


def test_active_group_memo_serves_a_repeat_of_the_same_file_and_misses_when_the_file_changes():
    DF._ACTIVE_GROUP_MEMO.clear()
    calls = []

    def build_55():
        calls.append("55")
        return {"active_sensing_group": "GroupIdDef.GROUP_D", "active_sensing_group_rate_hz": 55.0}

    def build_110():
        calls.append("110")
        return {"active_sensing_group": "GroupIdDef.GROUP_A",
                "active_sensing_group_rate_hz": 110.0}

    key_old = (RCS08_UID, "file-uid-1", "hash-1")
    key_new = (RCS08_UID, "file-uid-2", "hash-2")        # the daily ingest's new report
    a = DF._memoised_active_group_facts(key_old, build_55)
    b = DF._memoised_active_group_facts(key_old, build_55)
    assert a == b and a["active_sensing_group_rate_hz"] == 55.0
    assert calls == ["55"], "a repeat of the same file must not rebuild"
    c = DF._memoised_active_group_facts(key_new, build_110)
    assert c["active_sensing_group_rate_hz"] == 110.0
    assert calls == ["55", "110"], "a new file identity must be a miss"
    # The served copy is a copy: mutating it cannot poison the memo for the next reader.
    a["active_sensing_group_rate_hz"] = 999.0
    assert DF._memoised_active_group_facts(key_old, build_55)["active_sensing_group_rate_hz"] == 55.0
    DF._ACTIVE_GROUP_MEMO.clear()


def test_active_group_memo_key_changes_when_the_same_file_uid_is_rewritten_with_a_new_hash():
    DF._ACTIVE_GROUP_MEMO.clear()
    calls = []
    build = lambda: (calls.append(1), {"active_sensing_group_rate_hz": 55.0})[1]
    DF._memoised_active_group_facts((RCS08_UID, "file-uid-1", "hash-1"), build)
    DF._memoised_active_group_facts((RCS08_UID, "file-uid-1", "hash-2"), build)
    assert len(calls) == 2
    DF._ACTIVE_GROUP_MEMO.clear()
