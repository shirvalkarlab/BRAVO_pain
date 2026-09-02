"""Tests for the gate between the open-loop and closed-loop stages.

The gate's job is to be able to say NO and to name the reason. So almost every test below constructs
a configuration that SHOULD be refused and checks two things: that it was refused, and that the
refusal identifies the specific condition responsible. A gate that refused everything with one
opaque message would pass a naive "did it refuse" test and be useless in a clinic.
"""
import numpy as np
import pytest

from StimOptimizer import stage1_openloop as S1
from StimOptimizer.routines import percept_adaptive as PA
from StimOptimizer.routines import stage_gate as GATE


# ---------------------------------------------------------------------------------------------
# Fixtures: frozen configurations built directly, so a gate test does not depend on a GP fit
# ---------------------------------------------------------------------------------------------
def _setting(hemisphere="Left", rate_hz=130.0, pw_us=60.0, amp_star=2.0,
             amp_lo=1.0, amp_hi=3.0, rate_resolved=True, pw_resolved=True):
    return S1.HemisphereSetting(
        hemisphere=hemisphere, rate_hz=rate_hz, pw_us=pw_us, amp_star_mA=amp_star,
        amp_delivered_min_mA=amp_lo, amp_delivered_max_mA=amp_hi, n_epochs_fitted=20,
        rate_resolved=rate_resolved, pw_resolved=pw_resolved, reasons=("fixture",))


def _frozen(*settings, override=None):
    return S1.FrozenConfiguration(
        settings=tuple(settings or (_setting(),)), primary_item="left_leg",
        incumbent_epoch=1.0, incumbent_rate_hz=55.0, incumbent_pw_us=60.0,
        data_horizon="test", washin_min=1.0, n_epochs_total=40, override=override)


def _responding_lfp(n=120, low=1.0, high=3.0, suppression=0.9, band=(13.0, 17.0), seed=0):
    """LFP magnitude that IS suppressed by amplitude inside ``band``, so the response test passes."""
    rng = np.random.default_rng(seed)
    amp = np.repeat([low, high], n // 2)
    freqs = np.arange(4.0, 40.0, 0.5)
    mag = np.abs(rng.normal(1.0, 0.05, (n, freqs.size)))
    sel = (freqs >= band[0]) & (freqs <= band[1])
    mag[:, sel] *= (np.exp(-suppression * amp)[:, None] * 3.0)
    return GATE.LfpEvidence(amplitude_mA=amp, magnitude=mag, freqs=freqs,
                            era=np.tile(["a", "b"], n // 2), cluster=np.arange(n))


def _flat_lfp(n=120, seed=1):
    """LFP that does NOT respond to amplitude: pure noise, no amplitude-dependent structure."""
    rng = np.random.default_rng(seed)
    amp = np.repeat([1.0, 3.0], n // 2)
    freqs = np.arange(4.0, 40.0, 0.5)
    mag = np.abs(rng.normal(1.0, 0.05, (n, freqs.size)))
    return GATE.LfpEvidence(amplitude_mA=amp, magnitude=mag, freqs=freqs,
                            era=np.tile(["a", "b"], n // 2), cluster=np.arange(n))


# ---------------------------------------------------------------------------------------------
# Condition 1: the adaptive rate floor
# ---------------------------------------------------------------------------------------------
def test_the_gate_refuses_a_sub_55_hz_rate_and_names_the_rate_condition():
    """A group configured for Adaptive Therapy has a higher minimum rate (A610 manual p. 35).

    55 Hz is the PI-supplied value in percept_adaptive.MIN_ADAPTIVE_RATE_HZ. Below it the policy is
    not programmable at all, so this is the cheapest condition to check and to fail.
    """
    g = GATE.evaluate_gate(_frozen(_setting(rate_hz=40.0)), lfp=_responding_lfp())
    assert g.passed is False
    assert "rate_at_or_above_adaptive_minimum" in g.failed_names()
    c = g.condition("rate_at_or_above_adaptive_minimum")
    assert c.passed is False
    assert "40" in c.detail and "55" in c.detail
    # the refusal must be attributable, not a single opaque verdict
    assert ("rate_at_or_above_adaptive_minimum", c.detail) in g.refusals()


def test_a_rate_exactly_at_the_floor_passes():
    """The constraint is "at or above", so 55 Hz itself must not be refused."""
    g = GATE.evaluate_gate(_frozen(_setting(rate_hz=PA.MIN_ADAPTIVE_RATE_HZ)),
                           lfp=_responding_lfp())
    assert g.condition("rate_at_or_above_adaptive_minimum").passed is True


def test_one_hemisphere_below_the_floor_blocks_the_whole_gate():
    """Rate freezes per group, so a sub-floor rate on either side blocks the configuration."""
    g = GATE.evaluate_gate(_frozen(_setting("Left", rate_hz=40.0),
                                   _setting("Right", rate_hz=165.0)), lfp=_responding_lfp())
    c = g.condition("rate_at_or_above_adaptive_minimum")
    assert c.passed is False
    assert "Left" in c.detail
    assert g.passed is False


# ---------------------------------------------------------------------------------------------
# Condition 2: the open-loop choice must be resolved, or overridden with a reason
# ---------------------------------------------------------------------------------------------
def test_the_gate_refuses_an_unresolved_open_loop_choice():
    g = GATE.evaluate_gate(_frozen(_setting(rate_resolved=False)), lfp=_responding_lfp())
    c = g.condition("openloop_choice_resolved")
    assert c.passed is False
    assert c.overridden is False
    assert "NOT resolved" in c.detail
    assert g.passed is False


def test_a_not_assessed_component_is_reported_as_never_asked_not_as_refused():
    """"Not assessed" and "refused" both block, but they tell the clinician different things.

    One says go and measure it; the other says the measurement came back negative. Collapsing them
    would lose the only piece of information that determines what to do next.
    """
    g = GATE.evaluate_gate(_frozen(_setting(pw_resolved=None)), lfp=_responding_lfp())
    c = g.condition("openloop_choice_resolved")
    assert c.passed is False
    assert "NOT ASSESSED" in c.detail


def test_a_recorded_override_licenses_the_resolution_condition_but_is_reported_as_an_override():
    cfg = S1.clinician_override(_frozen(_setting(rate_resolved=False, pw_resolved=False)),
                                reason="tolerated for two years at this rate", by="PI")
    g = GATE.evaluate_gate(cfg, lfp=_responding_lfp())
    c = g.condition("openloop_choice_resolved")
    assert c.passed is True
    assert c.overridden is True
    assert c.verdict == "OVERRIDDEN"
    assert "tolerated for two years" in c.detail
    assert "not a pass" in c.detail


def test_an_override_does_not_license_any_other_condition():
    """The override covers the resolution requirement only. It is not a master key.

    A clinician can have reasons to freeze an unresolved rate; nobody can override the fact that the
    device will not accept 40 Hz with Adaptive Therapy configured.
    """
    cfg = S1.clinician_override(_frozen(_setting(rate_hz=40.0, rate_resolved=False)),
                                reason="clinical judgement")
    g = GATE.evaluate_gate(cfg, lfp=_responding_lfp())
    assert g.condition("openloop_choice_resolved").passed is True
    assert g.condition("rate_at_or_above_adaptive_minimum").passed is False
    assert g.passed is False


# ---------------------------------------------------------------------------------------------
# Condition 3: a band inside 8-30 Hz that responds to stimulation amplitude
# ---------------------------------------------------------------------------------------------
def test_the_gate_refuses_when_no_band_inside_8_to_30_hz_passes_the_response_test():
    """The band range and the response requirement are independent, and both are necessary.

    Here every candidate band is inside the adaptive range, so the range half passes; the LFP simply
    does not move with amplitude, so the response half fails and the gate must refuse.
    """
    g = GATE.evaluate_gate(_frozen(), lfp=_flat_lfp())
    c = g.condition("adaptive_band_passes_lfp_response")
    assert c.passed is not True
    assert g.passed is False
    assert "adaptive_band_passes_lfp_response" in [n for n, _ in g.refusals()]


def test_a_band_outside_the_adaptive_range_is_refused_on_the_range_alone():
    """Adaptive Therapy can only be driven inside 8-30 Hz; wider is Sensing Only.

    A band that correlates with pain perfectly but sits at 60 Hz can be recorded and cannot drive
    stimulation, so it is refused before any response test is attempted.
    """
    g = GATE.evaluate_gate(_frozen(), lfp=_responding_lfp(), band_centers=(60.0, 70.0),
                           band_width_hz=5.0)
    c = g.condition("adaptive_band_passes_lfp_response")
    assert c.passed is False
    assert "adaptive range" in c.detail
    assert c.evidence["n_inside_adaptive_range"] == 0


def test_the_whole_band_must_be_inside_the_range_not_just_its_centre():
    """A band centred at 9 Hz with 5 Hz width reaches to 6.5 Hz and is not adaptive-capable."""
    g = GATE.evaluate_gate(_frozen(), lfp=_responding_lfp(), band_centers=(9.0,),
                           band_width_hz=5.0)
    assert g.condition("adaptive_band_passes_lfp_response").passed is False
    ok, _ = PA.band_is_adaptive_capable(9.0, 5.0)
    assert ok is False


def test_missing_lfp_evidence_is_not_assessed_and_still_blocks():
    """This is the state the project's real design matrix is in: settings and pain, no spectra.

    Treating an unasked question as satisfied would license closed-loop configuration on evidence
    nobody collected, so the condition must be None and the gate must still refuse.
    """
    g = GATE.evaluate_gate(_frozen(), lfp=None)
    c = g.condition("adaptive_band_passes_lfp_response")
    assert c.passed is None
    assert c.verdict == "NOT ASSESSED"
    assert c.blocking is True
    assert g.passed is False
    assert "adaptive_band_passes_lfp_response" in g.not_assessed_names()


def test_a_responding_band_passes_and_reports_its_separation():
    g = GATE.evaluate_gate(_frozen(), lfp=_responding_lfp())
    c = g.condition("adaptive_band_passes_lfp_response")
    assert c.passed is True
    assert c.evidence["n_passing"] >= 1
    assert "separation" in c.detail or "separated" in c.detail
    for centre in c.evidence["passing_centers"]:
        ok, _ = PA.band_is_adaptive_capable(centre, GATE.DEFAULT_BAND_WIDTH_HZ)
        assert ok, f"a passing centre {centre} must lie inside the adaptive range"


def test_default_band_centres_all_lie_inside_the_adaptive_range():
    for c in GATE.DEFAULT_BAND_CENTERS_HZ:
        ok, why = PA.band_is_adaptive_capable(c, GATE.DEFAULT_BAND_WIDTH_HZ)
        assert ok, why


# ---------------------------------------------------------------------------------------------
# Condition 4: amplitude limits
# ---------------------------------------------------------------------------------------------
def test_limits_above_the_declared_ceiling_are_refused():
    g = GATE.evaluate_gate(_frozen(_setting(amp_lo=1.0, amp_hi=6.0)), lfp=_responding_lfp(),
                           amp_limits={"Left": (1.0, 5.5)})
    c = g.condition("amplitude_limits_inside_envelope_and_under_ceiling")
    assert c.passed is False
    assert "ceiling" in c.detail


def test_limits_above_the_delivered_envelope_are_refused_with_the_severity_evidence():
    """Above the delivered maximum is UNKNOWN, not safe.

    Amplitude does not predict side-effect severity in this record, and only a handful of coded
    steps sit above 4 mA, so an adaptive ceiling above what was ever delivered would hand the device
    authority to go somewhere nobody has observed.
    """
    g = GATE.evaluate_gate(_frozen(_setting(amp_lo=1.0, amp_hi=3.0)), lfp=_responding_lfp(),
                           amp_limits={"Left": (1.0, 4.5)})
    c = g.condition("amplitude_limits_inside_envelope_and_under_ceiling")
    assert c.passed is False
    assert "delivered" in c.detail
    assert "UNKNOWN rather than safe" in c.detail


def test_inverted_limits_are_refused():
    g = GATE.evaluate_gate(_frozen(), lfp=_responding_lfp(), amp_limits={"Left": (2.5, 1.5)})
    c = g.condition("amplitude_limits_inside_envelope_and_under_ceiling")
    assert c.passed is False
    assert "max > min" in c.detail


def test_defaulted_limits_say_so_rather_than_looking_checked():
    """A reader must not mistake a default for a verified proposal."""
    g = GATE.evaluate_gate(_frozen(), lfp=_responding_lfp(), amp_limits=None)
    c = g.condition("amplitude_limits_inside_envelope_and_under_ceiling")
    assert c.passed is True
    assert "DEFAULTED" in c.detail
    assert "by construction" in c.detail


def test_limits_inside_the_envelope_and_under_the_ceiling_pass():
    g = GATE.evaluate_gate(_frozen(_setting(amp_lo=1.0, amp_hi=4.0)), lfp=_responding_lfp(),
                           amp_limits={"Left": (1.5, 3.0)})
    assert g.condition("amplitude_limits_inside_envelope_and_under_ceiling").passed is True


# ---------------------------------------------------------------------------------------------
# The gate as a whole
# ---------------------------------------------------------------------------------------------
def test_all_four_conditions_are_always_evaluated_and_reported():
    """Evaluation must not short-circuit on the first failure.

    The conditions fail for unrelated reasons, so fixing the first does not predict the second, and
    a clinician needs the whole picture in one pass.
    """
    g = GATE.evaluate_gate(_frozen(_setting(rate_hz=40.0, rate_resolved=False,
                                            amp_lo=1.0, amp_hi=3.0)),
                           lfp=None, amp_limits={"Left": (1.0, 9.0)})
    names = [c.name for c in g.conditions]
    assert names == ["rate_at_or_above_adaptive_minimum", "openloop_choice_resolved",
                     "adaptive_band_passes_lfp_response",
                     "amplitude_limits_inside_envelope_and_under_ceiling"]
    assert len(g.refusals()) == 4
    assert g.passed is False


# ---------------------------------------------------------------------------------------------
# Selected biomarker bands: the DEVICE question and the STATISTICAL question, kept apart
# ---------------------------------------------------------------------------------------------
def test_supplying_selected_bands_adds_two_separately_reported_conditions():
    """The device-window question and the statistical-support question are different questions.

    A band can fail either one alone, so they must be reported separately or a reader cannot tell
    which one binds.
    """
    g = GATE.evaluate_gate(_frozen(_setting(rate_hz=130.0)),
                           selected_bands=GATE.RCS08_SELECTED_BANDS,
                           response_summary=GATE.RCS08_RESPONSE_SUMMARY)
    names = [c.name for c in g.conditions]
    assert names == ["rate_at_or_above_adaptive_minimum", "openloop_choice_resolved",
                     "selected_band_inside_adaptive_window",
                     "selected_band_statistically_supported",
                     "adaptive_band_passes_lfp_response",
                     "amplitude_limits_inside_envelope_and_under_ceiling"]
    assert len(g.conditions) == 6


def test_omitting_selected_bands_leaves_the_original_four_condition_shape():
    g = GATE.evaluate_gate(_frozen(), lfp=_responding_lfp())
    assert len(g.conditions) == 4
    assert "selected_band_inside_adaptive_window" not in [c.name for c in g.conditions]


def test_the_out_of_window_band_is_excluded_by_the_device_not_by_its_statistics():
    """The 3.92 Hz band spans roughly 1.4-6.4 Hz at 5 Hz width, outside the 8-30 Hz window.

    That exclusion holds whatever its p-value had turned out to be, and the gate must say so
    rather than folding it in with the statistical refusal. Conflating the two would overstate the
    case: the two RCS08 bands fail for genuinely different reasons.
    """
    nrs = [b for b in GATE.RCS08_SELECTED_BANDS if b.outcome == "nrs"][0]
    lo, hi = nrs.band_hz
    assert lo == pytest.approx(1.4215, abs=1e-3)
    assert hi == pytest.approx(6.4215, abs=1e-3)
    ok, why = nrs.adaptive_capable()
    assert ok is False
    assert "outside the adaptive range" in why
    c = GATE.check_selected_band_in_adaptive_window(GATE.RCS08_SELECTED_BANDS)
    assert "DEVICE constraint" in c.detail or "DEVICE window" in c.detail
    assert "3.921" in c.detail
    # and it is NOT counted among the candidates whose statistics are assessed
    s = GATE.check_selected_band_statistical_support(GATE.RCS08_SELECTED_BANDS)
    assert [r["outcome"] for r in s.evidence["candidates"]] == ["left_leg_vas"]


def test_a_band_outside_the_window_would_be_excluded_even_with_a_significant_p_value():
    """Independence of the two reasons, stated as a test rather than as a comment."""
    hypothetical = GATE.SelectedBand(outcome="nrs", center_hz=3.9215, band_width_hz=5.0,
                                     r=-0.5303, perm_p=0.0001, fdr_q=0.0001)
    assert hypothetical.statistically_supported() is True
    assert hypothetical.adaptive_capable()[0] is False
    c = GATE.check_selected_band_in_adaptive_window([hypothetical])
    assert c.passed is False


def test_the_only_adaptive_capable_band_is_not_statistically_supported():
    """The 14.817 Hz band IS inside the window and fails on its selection-corrected statistics.

    Reconciled by the biomarker track (audit F8 part 2, commit 6001e00): perm_p moved from 0.6074
    to 0.4166 and FDR q = 0.5055, so it does not survive multiplicity correction at all, and the
    observed correlation does not exceed its own null 95th percentile.
    """
    llv = [b for b in GATE.RCS08_SELECTED_BANDS if b.outcome == "left_leg_vas"][0]
    assert llv.adaptive_capable()[0] is True
    assert llv.perm_p == pytest.approx(0.4166)
    assert llv.fdr_q == pytest.approx(0.5055)
    assert llv.exceeds_null_95th is False
    assert llv.statistically_supported() is False
    c = GATE.check_selected_band_statistical_support(GATE.RCS08_SELECTED_BANDS)
    assert c.passed is False
    assert "0.4166" in c.detail and "0.5055" in c.detail
    assert "separate refusal" in c.detail


def test_the_nrs_band_lost_its_nominal_significance_under_selection_correction():
    nrs = [b for b in GATE.RCS08_SELECTED_BANDS if b.outcome == "nrs"][0]
    assert nrs.perm_p == pytest.approx(0.0809)
    assert nrs.perm_p >= GATE.SELECTION_ALPHA      # no longer nominally significant
    assert nrs.statistically_supported() is False
    assert nrs.exceeds_null_95th is False


def test_a_band_surviving_permutation_but_not_fdr_is_refused():
    """Selection correction and multiplicity correction are both required."""
    b = GATE.SelectedBand(outcome="x", center_hz=15.0, band_width_hz=5.0, r=-0.6,
                          perm_p=0.01, fdr_q=0.40)
    assert b.statistically_supported() is False
    assert GATE.check_selected_band_statistical_support([b]).passed is False


def test_a_band_with_no_permutation_p_is_not_assessed_rather_than_passed():
    b = GATE.SelectedBand(outcome="x", center_hz=15.0, band_width_hz=5.0, r=-0.6)
    assert b.statistically_supported() is None
    c = GATE.check_selected_band_statistical_support([b])
    assert c.passed is None
    assert c.blocking is True


def test_a_supported_adaptive_capable_band_passes():
    """The condition must be capable of a yes, or its refusal carries no information."""
    b = GATE.SelectedBand(outcome="x", center_hz=15.0, band_width_hz=5.0, r=-0.7,
                          perm_p=0.004, fdr_q=0.02, exceeds_null_95th=True)
    c = GATE.check_selected_band_statistical_support([b])
    assert c.passed is True
    assert GATE.check_selected_band_in_adaptive_window([b]).passed is True


def test_the_selection_thresholds_are_the_conventional_values_and_are_not_relaxed():
    """A threshold adjusted until the answer changes is not a threshold."""
    assert GATE.SELECTION_ALPHA == 0.05
    assert GATE.SELECTION_FDR_Q == 0.05


# ---------------------------------------------------------------------------------------------
# A supplied LFP-response verdict
# ---------------------------------------------------------------------------------------------
def test_a_supplied_failing_response_summary_is_reported_with_its_source():
    """3 of 15 channel-by-rate cells suppress, one-sided binomial p = 0.996.

    This verdict was computed elsewhere over the whole historical record, which is a larger
    computation than assess_response performs on one band, so it is reported with attribution
    rather than recomputed and presented as the same claim.
    """
    c = GATE.check_adaptive_band(_frozen(), response_summary=GATE.RCS08_RESPONSE_SUMMARY)
    assert c.passed is False
    assert "3 of 15" in c.detail
    assert "0.996" in c.detail
    assert "165 Hz" in c.detail
    assert "established outside this module" in c.detail
    assert "supplied by" in c.detail


def test_a_supplied_summary_takes_precedence_over_row_level_evidence():
    """When both are given, the externally established verdict is the one reported."""
    c = GATE.check_adaptive_band(_frozen(), lfp=_responding_lfp(),
                                 response_summary=GATE.RCS08_RESPONSE_SUMMARY)
    assert c.passed is False
    assert c.evidence["source"] == "supplied"


def test_a_supplied_summary_with_no_verdict_is_not_assessed():
    s = GATE.ResponseSummary(responds=None, source="a run that did not conclude")
    c = GATE.check_adaptive_band(_frozen(), response_summary=s)
    assert c.passed is None
    assert c.blocking is True


def test_a_supplied_passing_summary_passes():
    s = GATE.ResponseSummary(responds=True, n_cells_suppressing=12, n_cells_total=15,
                             one_sided_p=0.002, source="a later record")
    c = GATE.check_adaptive_band(_frozen(), response_summary=s)
    assert c.passed is True
    assert "12 of 15" in c.detail


def test_the_reconciled_plate_carries_its_provenance():
    """Three successive corrections have moved this statistic, so each band must name its source.

    The values are the selection-corrected ones, and the provenance records which commit reconciled
    the permutation family with the family the band was actually selected from.
    """
    assert len(GATE.RCS08_SELECTED_BANDS) == 2
    for b in GATE.RCS08_SELECTED_BANDS:
        assert "6001e00" in b.provenance
        assert "selection-corrected from perm_p" in b.provenance
        assert b.exceeds_null_95th is False, "neither band exceeds its own null 95th percentile"
        assert b.statistically_supported() is False
    assert GATE.RCS08_RESPONSE_SUMMARY.responds is False
    assert GATE.RCS08_RESPONSE_SUMMARY.source


def test_the_gate_can_pass_when_every_condition_is_met():
    """The gate must be capable of a yes, or a refusal carries no information."""
    cfg = S1.clinician_override(_frozen(_setting(rate_hz=130.0, amp_lo=1.0, amp_hi=4.0)),
                                reason="not needed here but harmless")
    g = GATE.evaluate_gate(cfg, lfp=_responding_lfp(), amp_limits={"Left": (1.5, 3.0)})
    assert g.passed is True, g.describe()
    assert g.refusals() == []
    assert "MAY START" in g.describe()


def test_passing_requires_strictly_true_never_none():
    g = GATE.evaluate_gate(_frozen(_setting(rate_hz=130.0)), lfp=None)
    assert all(c.passed is not False for c in g.conditions)   # nothing outright failed
    assert g.passed is False                                  # yet the gate does not pass
    assert g.not_assessed_names() == ["adaptive_band_passes_lfp_response"]


def test_a_configuration_with_no_settings_is_not_assessed_rather_than_passed():
    empty = S1.FrozenConfiguration(
        settings=(), primary_item="left_leg", incumbent_epoch=1.0, incumbent_rate_hz=55.0,
        incumbent_pw_us=60.0, data_horizon="test", washin_min=1.0, n_epochs_total=0)
    g = GATE.evaluate_gate(empty, lfp=_responding_lfp())
    assert g.passed is False
    assert g.condition("rate_at_or_above_adaptive_minimum").passed is None
    assert g.condition("amplitude_limits_inside_envelope_and_under_ceiling").passed is None


def test_describe_names_every_blocking_condition():
    g = GATE.evaluate_gate(_frozen(_setting(rate_hz=40.0)), lfp=None)
    text = g.describe()
    assert "MUST NOT START" in text
    for name, _ in g.refusals():
        assert name in text


def test_an_unknown_condition_name_raises_rather_than_returning_a_default():
    g = GATE.evaluate_gate(_frozen(), lfp=None)
    with pytest.raises(KeyError, match="no gate condition named"):
        g.condition("does_not_exist")


# ---------------------------------------------------------------------------------------------
# LfpEvidence
# ---------------------------------------------------------------------------------------------
def test_band_power_uses_the_device_definition_of_a_sum_of_squares():
    """The device thresholds a linear SUM of squared magnitude over the band, not a mean or a log.

    A mean would differ from the sum by the bin count, and the threshold handed to the device has to
    be in the units the device uses.
    """
    freqs = np.array([9.0, 10.0, 11.0, 12.0, 13.0])
    mag = np.array([[1.0, 2.0, 3.0, 4.0, 5.0]])
    ev = GATE.LfpEvidence(amplitude_mA=np.array([1.0]), magnitude=mag, freqs=freqs)
    got = ev.power_for(11.0, 2.0)                # selects 10, 11, 12 Hz
    assert got[0] == pytest.approx(2.0 ** 2 + 3.0 ** 2 + 4.0 ** 2)


def test_precomputed_band_power_is_used_when_supplied():
    ev = GATE.LfpEvidence(amplitude_mA=np.array([1.0, 3.0]),
                          band_power={(15.0, 5.0): np.array([10.0, 2.0])})
    assert list(ev.power_for(15.0, 5.0)) == [10.0, 2.0]
    assert ev.power_for(20.0, 5.0) is None       # no magnitude to fall back on
