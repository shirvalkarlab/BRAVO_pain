"""Tests for the device rule table and the eligibility evaluator.

The tests are written around the failure modes this module exists to prevent rather than around
line coverage. In order of importance those are: a rule that cannot be evaluated passing silently,
a check that reads the centre frequency when the document constrains the band edges, an evaluator
that stops at the first blocker and so hides the second one, and a threshold placed on a log scale
that the device is never going to apply.

Every candidate here is built by mutating ``passing_candidate()``, so a test named after one rule
fails only on that rule and the assertion can say so exactly.
"""
from __future__ import annotations

import pytest

from ClosedLoopDeployment import constraints, types


# ------------------------------------------------------------------------------------------------
# Fixtures. These are functions rather than pytest fixtures so that a test can build two variants
# in one body without asking for the fixture twice.
# ------------------------------------------------------------------------------------------------
def passing_candidate(**overrides):
    """A configuration that satisfies every blocking rule and resolves both unknowns.

    It declares considerably more than the band description, because the evaluator treats an
    undeclared fact as not determinable and therefore blocking. The values are the ones this
    project has actually adopted where such a value exists: a 5 Hz band inside the alpha-beta
    window, 60 microsecond pulse width (the left hemisphere's programmed value), capture amplitudes
    inside the 5 mA artefact ceiling, and a right-sensing, left-actuating contralateral pairing of
    the kind the current deployability screen produces.
    """
    candidate = {
        # Band and channel.
        "channel": "ZERO_THREE_RIGHT",
        "channel_is_brainsense_setup_channel": True,
        "sensing_hemisphere": "Right",
        "actuated_hemisphere": "Left",
        "contralateral_pairing_acknowledged": True,
        "center_hz": 20.0,
        "band_width_hz": 5.0,
        "highpass_hz": 1.0,
        "impedance_ohms": 1200.0,
        "impedance_tested": True,
        "artifact_flags": [],
        # Stimulation parameters.
        "rate_hz": 110.0,
        "pulse_width_us": 60.0,
        "amp_mA": 3.0,
        # Sensing and control.
        "threshold_mode": "dual",
        "intent": "adaptive",
        "lfp_amplitude_uvp": 1.6,
        "power_scale": "linear",
        "pooled_across_center_or_mode": False,
        "power_slope_vs_amplitude_sign": -1,
        "power_slope_vs_pain_sign": 1,
        # Capture and limits.
        "capture_amp_low_mA": 2.0,
        "capture_amp_high_mA": 3.5,
        "adaptive_min_mA": 2.0,
        "adaptive_max_mA": 3.5,
        "paused_amplitude_mA": 2.0,
        "vertically_aligned_segments_matched": True,
        # Ordering and group state.
        "frequency_search_closed": True,
        "has_pocket_adaptor": False,
        "multiple_rates_in_group": False,
        "interleaving_in_group": False,
        "cycling_in_group": False,
        "patient_limits_configured": False,
    }
    candidate.update(overrides)
    return candidate


def resolved_participant(**overrides):
    """A participant record in which D04 and D31 have been read off the device.

    The BrainSense rate and pulse-width figures here are PLACEHOLDERS chosen to be permissive, not
    measurements: neither Medtronic document prints them, and section 12 of the constraints file
    says they have to be read off the A610 controls once a BrainSense group exists. They are used
    only to show that the rule resolves once the values arrive.
    """
    participant = {
        "uid": "TEST08",
        "indication": "chronic_pain",
        "programming_mode": "parkinsons",
        "n_neurostimulators": 1,
        "brainsense_min_rate_hz": 50.0,
        "brainsense_max_rate_hz": 250.0,
        "brainsense_max_pulse_width_us": 120.0,
        "lead_type": "sensight",
        "dual_lead_implant": True,
        "adaptive_configured_both_hemispheres": False,
        "can_operate_neurostimulator": True,
    }
    participant.update(overrides)
    return participant


def rcs08_participant(**overrides):
    """The participant record as it actually stands today: D04 and D31 unread.

    This is the record the module has to behave correctly on right now, and the correct behaviour is
    to refuse to license anything.
    """
    participant = resolved_participant(**overrides)
    participant["n_neurostimulators"] = None
    participant["brainsense_min_rate_hz"] = None
    participant["brainsense_max_rate_hz"] = None
    participant["brainsense_max_pulse_width_us"] = None
    return participant


def ids(rows):
    """Rule identifiers from a list of report rows, as a set."""
    return {row["rule_id"] for row in rows}


# ------------------------------------------------------------------------------------------------
# The table itself.
# ------------------------------------------------------------------------------------------------
def test_table_encodes_all_fifty_one_rules_exactly_once():
    """D01 to D51 with no gaps and no duplicates, because a skipped rule is an invisible rule."""
    got = [rule.rule_id for rule in constraints.RULES]
    assert got == [f"D{n:02d}" for n in range(1, 52)]
    assert len(set(got)) == 51


def test_every_rule_carries_its_citation_and_a_plain_english_reason():
    for rule in constraints.RULES:
        assert rule.title.strip(), rule.rule_id
        assert rule.source.strip(), rule.rule_id
        assert rule.page.strip(), rule.rule_id
        # The house rule is that the text explains what goes wrong, which does not fit in a slogan.
        assert len(rule.human_text) > 120, rule.rule_id
        assert rule.predicate is None or callable(rule.predicate), rule.rule_id


def test_severity_counts_are_the_documented_split():
    """20 blocking, 29 advisory, 2 unknown. The two unknowns are the point of the split.

    Was 21/28/2 until 2026-09-04, when D09 was moved from blocking to advisory on PI decision. The
    guide RECOMMENDS the 1.2 uVp amplitude and states it two ways (1.2 against 1.1) without
    explaining the difference, so refusing a configuration outright on it was stronger than the
    evidence supports. D09 is the only rule that has been softened; if this count moves again,
    check that the change was deliberate and recorded.
    """
    counts = constraints.severity_counts()
    assert counts == {"blocking": 20, "advisory": 29, "unknown": 2}
    unknown_ids = {rule.rule_id for rule in constraints.RULES if rule.severity == "unknown"}
    assert unknown_ids == {"D04", "D31"}


def test_d03_is_blocking_and_not_unknown():
    """The documents state D03 clearly, so it is evaluable; it is unknown for nobody."""
    assert constraints.RULES_BY_ID["D03"].severity == "blocking"
    assert constraints.RULES_BY_ID["D03"].predicate is not None


def test_every_observed_value_function_names_a_real_rule():
    assert set(constraints._OBSERVED).issubset(set(constraints.RULES_BY_ID))
    assert set(constraints._RECORD_VALUE_ON_PASS).issubset(set(constraints._OBSERVED))


# ------------------------------------------------------------------------------------------------
# The passing case.
# ------------------------------------------------------------------------------------------------
def test_fully_declared_candidate_is_eligible():
    report = check(passing_candidate(), resolved_participant())
    assert report.failures == [], [r["rule_id"] for r in report.failures]
    assert report.unknowns == [], [r["rule_id"] for r in report.unknowns]
    assert report.eligible is True
    assert report.checked == 51
    assert isinstance(report, types.EligibilityReport)


def test_passing_report_records_the_programming_regime_it_was_written_in():
    """D03 passes, and the report still says which regime that pass was obtained in.

    Without this a reader cannot tell whether the report describes a participant for whom the
    Adaptive workflow is reachable at all.
    """
    report = check(passing_candidate(), resolved_participant())
    recorded = [row for row in report.advisories if row["kind"] == "recorded_value"]
    assert ids(recorded) == {"D03", "D04", "D31"}
    d03 = next(row for row in recorded if row["rule_id"] == "D03")
    assert "parkinsons" in d03["observed"]


def test_off_label_indication_is_surfaced_without_disqualifying():
    """D01 and D02 are labelling statements about the participant, not configuration defects.

    UPDATED 2026-09-04. Both rules read `indication` and both fail on an off-label one, so one fact
    was producing two advisory entries. D02 asks the narrower question (is Adaptive specifically
    labelled for this indication) and now OWNS the finding; D01 defers to it and moves to the
    `deferred` bucket. The observation is still in the report — the assertion below checks that it
    is present and names its owner — and eligibility is unchanged, which is the property that makes
    the collapse safe.
    """
    report = check(passing_candidate(), resolved_participant())
    assert "D02" in ids(report.advisories), "the narrower rule keeps the finding"
    assert "D01" not in ids(report.advisories), "the broader rule must not charge it a second time"
    d01 = next(row for row in report.deferred if row["rule_id"] == "D01")
    assert d01["deferred_to"] == "D02"
    assert "indication" in d01["deferral_reason"]
    assert report.eligible is True


def test_an_advisory_failure_does_not_disqualify():
    """A 7 Hz band width breaches the nominal 5 Hz of D10, whose document prints no range."""
    report = check(passing_candidate(band_width_hz=7.0), resolved_participant())
    d10 = next(row for row in report.advisories if row["rule_id"] == "D10")
    assert d10["kind"] == "advisory_failed"
    assert report.eligible is True


# ------------------------------------------------------------------------------------------------
# D08, the rule that disqualifies the biomarker path.
# ------------------------------------------------------------------------------------------------
def test_d08_rejects_the_biomarker_paths_3_92_hz_selection():
    """A 5 Hz band centred at 3.92 Hz spans 1.42 to 6.42 Hz, entirely below the 8 Hz floor."""
    report = check(passing_candidate(center_hz=3.92), resolved_participant())
    assert "D08" in ids(report.failures)
    d08 = next(row for row in report.failures if row["rule_id"] == "D08")
    assert "1.42" in d08["observed"] and "6.42" in d08["observed"]
    assert report.eligible is False


def test_d08_checks_the_band_edges_and_not_the_centre_frequency():
    """A 5 Hz band centred at 10 Hz has its centre inside the window and its lower edge outside.

    This is the case that separates an edge check from a centre check, and it is the reason the
    rule is written against band_edges().
    """
    inside_centre_outside_edge = passing_candidate(center_hz=10.0)
    assert constraints.band_edges(inside_centre_outside_edge) == (7.5, 12.5)
    report = check(inside_centre_outside_edge, resolved_participant())
    assert "D08" in ids(report.failures)

    # The upper edge behaves the same way at the other end of the window.
    upper = check(passing_candidate(center_hz=29.0), resolved_participant())
    assert "D08" in ids(upper.failures)

    # And a band that fits at both edges passes.
    ok = check(passing_candidate(center_hz=20.0), resolved_participant())
    assert "D08" not in ids(ok.failures)


def test_d08_window_widens_for_a_sensing_only_candidate():
    """The 8 to 30 Hz confinement is the ADAPTIVE window; sensing only uses 1 to 96 Hz.

    The same 3.92 Hz band that cannot drive Adaptive Therapy can still be sensed chronically, and
    conflating the two windows would either forbid legitimate chronic sensing or license an
    unprogrammable adaptive configuration.
    """
    sensing = passing_candidate(center_hz=3.92, intent="sensing_only")
    assert constraints.permitted_band_hz(sensing) == (1.0, 96.0)
    assert constraints._p_d08(sensing, resolved_participant()) is True


# ------------------------------------------------------------------------------------------------
# D09 and its documented discrepancy.
# ------------------------------------------------------------------------------------------------
def test_d09_reports_a_shortfall_without_blocking():
    """D09 is ADVISORY as of 2026-09-04. A signal below the capture gate is surfaced for review,
    and it does NOT make the configuration ineligible.

    The distinction is the point: on RCS08 no bin in the 22-27 Hz candidate band reaches 1.2 uVp on
    any of the twelve channels, while bins at 8.8-11.7 Hz do. That is a strong argument for moving
    the centre frequency, and a weak argument for refusing to let anyone proceed — which is why it
    now informs rather than stops.
    """
    below = check(passing_candidate(lfp_amplitude_uvp=0.9), resolved_participant())
    assert "D09" not in ids(below.failures), "D09 must no longer block"
    assert "D09" in ids(below.advisories), "but the shortfall must still be reported"
    assert below.eligible is True, "a sub-gate amplitude alone must not make it ineligible"

    at_gate = check(passing_candidate(lfp_amplitude_uvp=1.2), resolved_participant())
    assert "D09" not in ids(at_gate.failures)


def test_d09_uses_the_conservative_of_the_two_documented_floors():
    """1.15 uVp clears the white paper's 1.1 auto-detection floor and fails the 1.2 gate.

    The two Medtronic documents disagree here. The module gates on the conservative number and
    reports the other one rather than resolving a disagreement the documents do not resolve.
    """
    assert constraints.LFP_THRESHOLD_CAPTURE_FLOOR_UVP == 1.2
    assert constraints.LFP_AUTODETECT_FLOOR_UVP == 1.1
    assert "1.2" in constraints.LFP_FLOOR_DISCREPANCY
    assert "1.1" in constraints.LFP_FLOOR_DISCREPANCY

    # D09 became ADVISORY on 2026-09-04, so the row moved out of failures. Both documented floors
    # must still appear in what the reader sees, which was always the point of this test: the
    # module reports a disagreement the manufacturer's own documents do not resolve.
    report = check(passing_candidate(lfp_amplitude_uvp=1.15), resolved_participant())
    d09 = next(row for row in report.advisories if row["rule_id"] == "D09")
    assert "1.2" in d09["observed"] and "1.1" in d09["observed"]
    assert "D09" not in ids(report.failures)


# ------------------------------------------------------------------------------------------------
# The two unknowns.
# ------------------------------------------------------------------------------------------------
def test_the_two_unknown_rules_block_on_the_record_as_it_stands():
    """With D04 and D31 unread, a candidate that satisfies every other rule is still not eligible.

    This is the situation today, and the required behaviour is refusal. The two unknowns are also
    the ONLY blockers on this candidate, which is what makes the report actionable: read two values
    off the device and the configuration is licensable.
    """
    report = check(passing_candidate(), rcs08_participant())
    assert report.failures == [], [r["rule_id"] for r in report.failures]
    assert ids(report.unknowns) == {"D04", "D31"}
    assert all(row["kind"] == "value_not_read_off_programmer" for row in report.unknowns)
    assert report.eligible is False
    assert report.checked == 51


def test_the_two_unknowns_are_distinguishable_from_an_undeclared_input():
    """A missing candidate field and an unread device value both block, for different reasons.

    They need different actions, so the report labels them differently rather than pooling them.
    """
    report = check(passing_candidate(paused_amplitude_mA=None), rcs08_participant())
    by_kind = {row["rule_id"]: row["kind"] for row in report.unknowns}
    assert by_kind["D04"] == "value_not_read_off_programmer"
    assert by_kind["D31"] == "value_not_read_off_programmer"
    assert by_kind["D34"] == "input_not_supplied"


def test_d31_still_fails_outright_when_the_general_envelope_is_breached():
    """The BrainSense envelope is unpublished; the general Percept envelope is not.

    A rate of 300 Hz is outside the general envelope, so D31 can return a real failure even while
    its own narrowing figures remain unread.
    """
    report = check(passing_candidate(rate_hz=300.0), rcs08_participant())
    assert "D31" in ids(report.failures)
    assert "D31" not in ids(report.unknowns)


def test_d31_bites_on_the_incumbent_55_hz_rate_if_the_minimum_turns_out_higher():
    """The concrete question for this participant, encoded so the answer is mechanical.

    One of the four configurations the current screen licenses runs at 55 Hz. If the BrainSense
    minimum rate is read off the device as 60 Hz, that configuration cannot be programmed at all.
    """
    participant = resolved_participant(brainsense_min_rate_hz=60.0)
    report = check(passing_candidate(rate_hz=55.0), participant)
    assert "D31" in ids(report.failures)

    permissive = resolved_participant(brainsense_min_rate_hz=50.0)
    assert "D31" not in ids(check(passing_candidate(rate_hz=55.0), permissive).failures)


# ------------------------------------------------------------------------------------------------
# Missing input must never read as a pass.
# ------------------------------------------------------------------------------------------------
def test_empty_inputs_produce_no_passes_at_all():
    """Two empty dicts: every blocking and unknown rule lands in unknowns, none in failures.

    This is the single most important behaviour in the file. If an absent field read as a pass, an
    empty candidate would be reported as eligible.
    """
    report = check({}, {})
    assert report.failures == []
    assert len(report.unknowns) == 22          # 20 blocking + 2 unknown (D09 now advisory)
    assert len(report.advisories) == 29        # 28 + D09, softened 2026-09-04
    assert report.checked == 51
    assert report.eligible is False


def test_a_boolean_in_a_numeric_field_is_not_determinable_rather_than_one():
    """True would silently read as 1.0 in a numeric comparison, which would hide a typo."""
    assert constraints._num({"rate_hz": True}, "rate_hz") is None
    assert constraints._num({"rate_hz": "not a number"}, "rate_hz") is None
    assert constraints._num({"rate_hz": 110}, "rate_hz") == 110.0


def test_an_empty_artefact_list_passes_but_an_absent_field_does_not():
    """An empty list is a positive statement that the device flagged nothing. Absence is not."""
    participant = resolved_participant()
    assert constraints._p_d17(passing_candidate(artifact_flags=[]), participant) is True
    assert constraints._p_d17(passing_candidate(artifact_flags=["cardiac"]), participant) is False
    absent = passing_candidate()
    del absent["artifact_flags"]
    assert constraints._p_d17(absent, participant) is None


# ------------------------------------------------------------------------------------------------
# Every failure, not just the first.
# ------------------------------------------------------------------------------------------------
def test_check_eligibility_returns_every_failure_rather_than_the_first():
    """A clinician fixing one blocker must not have to re-run the screen to find the next.

    On this device that iteration is expensive: changing the electrode configuration to fix one
    problem clears the captured thresholds (D29), so a discover-one-at-a-time loop can cost a whole
    programming visit.
    """
    broken = passing_candidate(
        center_hz=3.92,                        # D08: band edges below 8 Hz
        lfp_amplitude_uvp=0.9,                 # D09: below the 1.2 uVp gate
        power_scale="log10",                   # D11: the device thresholds a linear sum
        pooled_across_center_or_mode=True,     # D12: pooled across centre frequency or mode
        highpass_hz=10.0,                      # D13: the band sits in the filter stopband
        channel_is_brainsense_setup_channel=False,   # D15: not a channel that can drive therapy
        impedance_ohms=100.0,                  # D16: below the SenSight short-circuit limit
        artifact_flags=["cardiac"],            # D17: artefact flagged by the device
        power_slope_vs_amplitude_sign=1,       # D19: wrong sign for the fixed control polarity
        pulse_width_us=160.0,                  # D27: above the 120 us artefact ceiling
        frequency_search_closed=False,         # D30: rate would freeze mid-search
        has_pocket_adaptor=True,               # D32: BrainSense cannot be configured there
        paused_amplitude_mA=0.0,               # D34: a pause must not mean cessation
    )
    report = check(broken, resolved_participant())

    # D09 is deliberately absent: it was softened to advisory on 2026-09-04, so a sub-gate
    # amplitude is reported rather than counted as a failure.
    expected = {"D08", "D11", "D12", "D13", "D15", "D16", "D17",
                "D19", "D27", "D30", "D32", "D34"}
    assert expected.issubset(ids(report.failures))
    assert len(report.failures) >= len(expected)
    assert report.checked == 51                # nothing was skipped on the way past the failures
    assert report.eligible is False
    assert "NOT eligible" in report.summary()


def test_every_failure_row_carries_the_page_that_forbids_it():
    """A verdict a clinician cannot trace to a sentence is a verdict they cannot argue with."""
    report = check(passing_candidate(center_hz=3.92, lfp_amplitude_uvp=0.9), resolved_participant())
    for row in report.failures + report.unknowns + report.advisories:
        assert row["page"].strip(), row["rule_id"]
        assert row["source"].strip(), row["rule_id"]
        assert row["why"].strip(), row["rule_id"]


# ------------------------------------------------------------------------------------------------
# The rules the task singles out as the ones that actually bite.
# ------------------------------------------------------------------------------------------------
def test_d30_makes_the_frequency_search_and_the_closed_loop_sequential():
    """Rate and pulse width freeze when BrainSense is set up, so the search must close first."""
    open_search = check(passing_candidate(frequency_search_closed=False), resolved_participant())
    assert ids(open_search.failures) == {"D30"}
    assert open_search.eligible is False

    closed = check(passing_candidate(frequency_search_closed=True), resolved_participant())
    assert "D30" not in ids(closed.failures)


def test_d40_couples_the_hemispheres_in_single_threshold_mode():
    """Bilateral Single Threshold is one controller with two inputs, not two controllers.

    The rule passes only when that coupling is explicitly accepted, because otherwise the report
    would describe a per-hemisphere controller the device is not going to run.
    """
    single = passing_candidate(threshold_mode="single", capture_amp_high_mA=3.5)
    coupled = resolved_participant(adaptive_configured_both_hemispheres=True)

    # The coupling is present and nobody has said whether it is understood. That is not
    # determinable rather than violated, so it blocks as an unknown and the report row names the
    # field to declare.
    unacknowledged = check(single, coupled)
    assert "D40" in ids(unacknowledged.unknowns)
    assert unacknowledged.eligible is False

    # Declining the coupling outright is a violation, because the configuration then describes a
    # per-hemisphere controller the device is not going to run.
    refused = resolved_participant(adaptive_configured_both_hemispheres=True,
                                   accepts_cross_hemisphere_coupling=False)
    assert "D40" in ids(check(single, refused).failures)

    accepted = resolved_participant(adaptive_configured_both_hemispheres=True,
                                    accepts_cross_hemisphere_coupling=True)
    assert "D40" not in ids(check(single, accepted).failures)

    # One hemisphere only: the coupling does not arise.
    one_side = resolved_participant(adaptive_configured_both_hemispheres=False)
    assert "D40" not in ids(check(single, one_side).failures)

    # Dual Threshold: the rule is not engaged at all, whatever the other hemisphere is doing.
    assert "D40" not in ids(check(passing_candidate(), coupled).failures)


def test_single_threshold_mode_raises_the_forced_zero_advisory():
    """D25: the device captures its second signal at 0 mA, which is a therapeutic state change."""
    report = check(passing_candidate(threshold_mode="single", capture_amp_high_mA=3.5),
                   resolved_participant(accepts_cross_hemisphere_coupling=True))
    d25 = next(row for row in report.advisories if row["rule_id"] == "D25")
    assert d25["kind"] == "advisory_failed"


def test_d03_blocks_a_participant_not_programmed_in_parkinsons_mode():
    """The same code that passes for RCS08 must fail for a participant defaulted to Dual Threshold.

    This is why D03 is kept as a live blocking rule rather than compiled away into a note.
    """
    report = check(passing_candidate(), resolved_participant(programming_mode="dual_default"))
    assert "D03" in ids(report.failures)
    assert report.eligible is False
    assert "D03" not in ids(report.advisories)      # a failure is not also a recorded value


def test_d27_flags_the_right_hemispheres_160_us_pulse_width():
    """This participant's right hemisphere is programmed at 160 us, above the 120 us ceiling.

    The consequence is specific: the Lower LFP Threshold captured there is artefact-suspect and must
    not be read as a physiological measurement.
    """
    report = check(passing_candidate(pulse_width_us=160.0), resolved_participant())
    assert "D27" in ids(report.failures)
    assert "160" in next(row for row in report.failures if row["rule_id"] == "D27")["observed"]

    over_amplitude = check(passing_candidate(capture_amp_high_mA=5.5, adaptive_max_mA=5.5),
                           resolved_participant())
    assert "D27" in ids(over_amplitude.failures)


def test_d19_rejects_a_biomarker_whose_power_falls_as_pain_rises():
    """The device can only ask for more stimulation when band power rises.

    The mode that would invert the mapping, Single Threshold Inverse, is sensing-only, so no choice
    of thresholds repairs a band with the wrong sign.
    """
    wrong_pain_sign = check(passing_candidate(power_slope_vs_pain_sign=-1), resolved_participant())
    assert "D19" in ids(wrong_pain_sign.failures)

    no_suppression = check(passing_candidate(power_slope_vs_amplitude_sign=1),
                           resolved_participant())
    assert "D19" in ids(no_suppression.failures)


def test_d18_refuses_single_threshold_inverse_for_an_adaptive_recommendation():
    report = check(passing_candidate(threshold_mode="single_inverse"), resolved_participant())
    assert "D18" in ids(report.failures)
    assert constraints.THRESHOLD_MODE_TABLE["single_inverse"]["can_drive_therapy"] is False


def test_d39_marks_a_contralateral_pairing_as_the_documented_fallback():
    """25 of the 50 usable cells on the current screen are contralateral, so this is live."""
    unmarked = passing_candidate()
    del unmarked["contralateral_pairing_acknowledged"]
    assert "D39" in ids(check(unmarked, resolved_participant()).unknowns)

    not_dual_lead = check(passing_candidate(),
                          resolved_participant(dual_lead_implant=False))
    assert "D39" in ids(not_dual_lead.failures)

    ipsilateral = passing_candidate(sensing_hemisphere="Left", actuated_hemisphere="Left")
    del ipsilateral["contralateral_pairing_acknowledged"]
    assert constraints._p_d39(ipsilateral, resolved_participant()) is True


def test_d11_refuses_a_threshold_expressed_on_a_log_scale():
    """A threshold on log power is not the threshold the device will apply to a linear sum."""
    for scale in ("log", "log10", "db"):
        report = check(passing_candidate(power_scale=scale), resolved_participant())
        assert "D11" in ids(report.failures), scale
    assert constraints.LFP_POWER_LSB_TO_UV2 == 0.01


def test_d12_refuses_power_pooled_across_centre_frequency_or_threshold_mode():
    report = check(passing_candidate(pooled_across_center_or_mode=True), resolved_participant())
    assert "D12" in ids(report.failures)


def test_d13_refuses_a_band_inside_the_configured_filter_stopband():
    """With the second high-pass at 10 Hz, a 3.92 Hz band records a filter artefact, not a signal."""
    report = check(passing_candidate(center_hz=3.92, highpass_hz=10.0), resolved_participant())
    assert {"D08", "D13"}.issubset(ids(report.failures))

    # A band inside the adaptive window is unaffected by either high-pass setting.
    assert constraints._p_d13(passing_candidate(highpass_hz=10.0), resolved_participant()) is True


def test_d16_uses_the_lead_specific_short_circuit_limit():
    """250 ohms on a 1x4 lead, 350 on a SenSight lead, opens above 10 kilohms, and a test required."""
    sensight = resolved_participant(lead_type="sensight")
    one_by_four = resolved_participant(lead_type="1x4")
    assert constraints._p_d16(passing_candidate(impedance_ohms=300.0), sensight) is False
    assert constraints._p_d16(passing_candidate(impedance_ohms=300.0), one_by_four) is True
    assert constraints._p_d16(passing_candidate(impedance_ohms=20000.0), sensight) is False
    assert constraints._p_d16(passing_candidate(impedance_tested=False), sensight) is False


def test_d24_enforces_the_crossed_capture_order():
    """The Upper LFP Threshold is captured at the LOWER amplitude; swapping them inverts the capture."""
    swapped = check(passing_candidate(capture_amp_low_mA=3.5, capture_amp_high_mA=2.0),
                    resolved_participant())
    assert "D24" in ids(swapped.failures)


def test_d28_owns_the_ordering_and_envelope_but_not_the_zero_lower_limit():
    """UPDATED 2026-09-04, and the update is the point.

    D28's predicate used to read `0.0 < lo < hi <= amp_hi and lo >= amp_lo`, folding D07's
    zero-lower-limit condition into its own compound test, so a declared zero failed both rules and
    one consideration was charged twice. D07 owns that condition now.

    Crucially D28 must still catch everything else it tests. The duplicate was removed from the
    CONDITION rather than by deferring the whole rule, because D28 tests three separate things and
    setting it aside would have discarded the ordering and envelope checks too.
    """
    # the zero lower limit is now D07's finding alone
    zero = check(passing_candidate(adaptive_min_mA=0.0), resolved_participant())
    assert "D07" in ids(zero.advisories), "D07 still reports the rebound risk"
    assert "D28" not in ids(zero.failures), "and D28 no longer charges it a second time"

    # but D28's OWN checks are untouched: wrong order still fails
    swapped = check(passing_candidate(adaptive_min_mA=4.0, adaptive_max_mA=3.5),
                    resolved_participant())
    assert "D28" in ids(swapped.failures), "the ordering check must survive the deduplication"

    # and so does the envelope check
    over = check(passing_candidate(adaptive_min_mA=1.0, adaptive_max_mA=99.0),
                 resolved_participant())
    assert "D28" in ids(over.failures), "the envelope check must survive too"


# ------------------------------------------------------------------------------------------------
# The evaluator's own failure handling.
# ------------------------------------------------------------------------------------------------
def test_a_predicate_that_raises_blocks_and_does_not_stop_the_rest_of_the_table():
    """A defect in this file must be visible and must not license anything.

    It also must not abort the run, or one broken rule would hide the verdicts of the other fifty.
    """
    def explodes(candidate, participant):
        raise RuntimeError("device document unreadable")

    broken_rule = types.DeviceConstraint(
        rule_id="D08", title="synthetic", source="test", page="n/a",
        severity="blocking", human_text="x" * 200, predicate=explodes,
    )
    good_rule = types.DeviceConstraint(
        rule_id="D09", title="synthetic", source="test", page="n/a",
        severity="blocking", human_text="x" * 200, predicate=lambda c, p: False,
    )
    report = check(passing_candidate(), resolved_participant(), rules=[broken_rule, good_rule])
    assert report.checked == 2
    assert ids(report.unknowns) == {"D08"}
    assert report.unknowns[0]["kind"] == "predicate_error"
    assert ids(report.failures) == {"D09"}
    assert report.eligible is False


def test_a_predicate_returning_a_non_verdict_is_treated_as_a_defect():
    """The contract is True, False or None. Anything else is a bug, not a pass."""
    sloppy = types.DeviceConstraint(
        rule_id="D08", title="synthetic", source="test", page="n/a",
        severity="blocking", human_text="x" * 200, predicate=lambda c, p: "yes",
    )
    report = check(passing_candidate(), resolved_participant(), rules=[sloppy])
    assert report.unknowns[0]["kind"] == "predicate_error"
    assert report.eligible is False


def test_severity_must_be_one_of_the_three_declared_values():
    with pytest.raises(ValueError):
        types.DeviceConstraint(rule_id="X", title="t", source="s", page="p",
                               severity="warning", human_text="h")


# ------------------------------------------------------------------------------------------------
def check(candidate, participant, rules=None):
    """Thin wrapper so that every test reads the same way."""
    return constraints.check_eligibility(candidate, participant, rules=rules)



# --- rule deferral: one fact must not be charged twice (2026-09-04) ----------------------------
def test_every_kind_the_evaluator_emits_is_classified_for_deferral():
    """The bug this pins cost a silent mechanism failure.

    `apply_deferrals` first tested for the kind "fail" while the evaluator emits "failed", so every
    deferral involving a BLOCKING rule never fired, and the mechanism appeared to work only because
    the one advisory pair happened to match. Any kind string the evaluator can produce must fall in
    exactly one of the three sets, so a rename cannot quietly disable deferral again.
    """
    import re
    from ClosedLoopDeployment import constraints as CN
    src = open(CN.__file__).read()
    emitted = set(re.findall(r'_entry\(\s*rule,\s*"([a-z_]+)"', src))
    assert emitted, "could not find the kinds the evaluator emits"
    unclassified = emitted - CN.ALL_KINDS
    assert not unclassified, f"kinds emitted but not classified: {sorted(unclassified)}"
    assert not (CN.KIND_ADVERSE & CN.KIND_UNEVALUABLE)
    assert not (CN.KIND_ADVERSE & CN.KIND_BENIGN)


def test_a_blocking_rule_deferral_would_fire_if_one_were_declared():
    """Pins the "fail" versus "failed" bug independently of which pairs are declared today.

    `apply_deferrals` first tested for the kind "fail" while the evaluator emits "failed", so any
    deferral involving a BLOCKING rule silently never fired. The one pair declared at the time was
    advisory and happened to match, so the mechanism looked as though it worked. The declared pairs
    change; this behaviour must not.
    """
    from ClosedLoopDeployment import constraints as CN
    rid, owner = "D01", CN.RULE_DEFERS_TO["D01"][0]
    out = CN.apply_deferrals({rid: {"rule_id": rid, "kind": "failed"},
                              owner: {"rule_id": owner, "kind": "failed"}})
    assert out[rid]["kind"] == "deferred_duplicate", "a BLOCKING kind must be recognised"
    assert out[rid]["counts_toward_verdict"] is False


def test_deferral_can_never_make_a_blocked_candidate_eligible():
    """The safety property. A row is set aside only when its OWNER reached the same adverse
    verdict, so the owner is still failing and the verdict cannot move. Asserted directly rather
    than argued, because this is the property that makes collapsing duplicates safe on a module
    whose output authorises programming a neurostimulator."""
    from ClosedLoopDeployment import constraints as CN
    for rid, (owner, _why) in CN.RULE_DEFERS_TO.items():
        rows = {rid: {"rule_id": rid, "kind": "failed"},
                owner: {"rule_id": owner, "kind": "failed"}}
        out = CN.apply_deferrals(rows)
        assert out[rid]["kind"] == "deferred_duplicate"
        # the OWNER is untouched and still adverse, so whatever bucket logic runs, it still blocks
        assert out[owner]["kind"] == "failed"
        assert out[owner].get("counts_toward_verdict") is not False


def test_deferral_surfaces_a_disagreement_instead_of_hiding_it():
    """If the owner passed while the deferring rule failed, two rules reading one input disagree.
    That is more interesting than either verdict alone, so the row is kept and annotated."""
    from ClosedLoopDeployment import constraints as CN
    rid, (owner, _) = "D01", CN.RULE_DEFERS_TO["D01"]
    out = CN.apply_deferrals({rid: {"rule_id": rid, "kind": "advisory_failed"},
                              owner: {"rule_id": owner, "kind": "recorded_value"}})
    assert out[rid]["kind"] == "advisory_failed", "never suppressed"
    assert "DISAGREEMENT" in out[rid]["deferral_note"]
    assert out[rid]["counts_toward_verdict"] is True


def test_deferral_stands_alone_when_the_owner_could_not_be_evaluated():
    """No second charge to collapse into, so suppressing the row would drop a real finding."""
    from ClosedLoopDeployment import constraints as CN
    rid, (owner, _) = "D01", CN.RULE_DEFERS_TO["D01"]
    out = CN.apply_deferrals({rid: {"rule_id": rid, "kind": "advisory_failed"},
                              owner: {"rule_id": owner, "kind": "input_not_supplied"}})
    assert out[rid]["kind"] == "advisory_failed"
    assert "could not be evaluated" in out[rid]["deferral_note"]
    assert out[rid]["counts_toward_verdict"] is True


def test_the_deferral_graph_is_acyclic_and_points_at_real_rules():
    """Validated at import; re-asserted here so the guard itself is covered."""
    from ClosedLoopDeployment import constraints as CN
    ids_present = {r.rule_id for r in CN.RULES}
    for deferring, (owner, why) in CN.RULE_DEFERS_TO.items():
        assert deferring in ids_present and owner in ids_present
        assert deferring != owner
        assert len(why) > 80, "a deferral must carry its reasoning, not just a pointer"
    CN._validate_deferral_graph()
