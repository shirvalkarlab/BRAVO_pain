"""Device-constraint tests. Values are quoted from the Percept adaptive white paper (UC202012929dEN)."""
import pytest

from StimOptimizer.routines import percept_adaptive as PA


def test_adaptive_band_is_8_to_30_hz_and_sensing_only_is_wider():
    assert PA.ADAPTIVE_LFP_BAND_HZ == (8.0, 30.0)
    assert PA.SENSING_ONLY_LFP_BAND_HZ == (1.0, 96.0)


def test_single_inverse_cannot_drive_therapy():
    """'only available in a Sensing Only configuration, meaning a change in LFP will not' change
    stimulation. Proposing it as a control policy is a category error, not a tuning choice."""
    assert PA.MODES[PA.SINGLE_INVERSE].can_drive_therapy is False
    assert PA.MODES[PA.DUAL].can_drive_therapy is True
    assert PA.MODES[PA.SINGLE].can_drive_therapy is True


def test_dual_is_minutes_and_single_is_milliseconds():
    """The two modes differ by four orders of magnitude in reaction speed, which is the whole basis
    for choosing between them."""
    d, s = PA.MODES[PA.DUAL], PA.MODES[PA.SINGLE]
    assert d.transition_up_ms == 150_000.0 and d.transition_down_ms == 300_000.0
    assert s.transition_up_ms == 250.0 and s.transition_down_ms == 250.0
    assert d.onset_duration_ms == 1200.0 and s.onset_duration_ms == 200.0
    assert d.detection_blanking_ms == 2000.0 and s.detection_blanking_ms == 550.0
    assert d.fft_size_points == 256 and s.fft_size_points == 64
    assert d.fft_update_rate_hz == 5.0 and s.fft_update_rate_hz == 20.0


def test_single_threshold_derivation_matches_the_device_formula():
    """threshold = 0.75*(upper - lower) + lower. Not our free parameter — it is what the device
    computes, so a single-threshold plan must PREDICT it, not choose it."""
    assert PA.SINGLE_THRESHOLD_FRACTION == 0.75
    assert PA.derive_single_threshold(0.0, 4.0) == pytest.approx(3.0)
    assert PA.derive_single_threshold(2.0, 6.0) == pytest.approx(5.0)
    assert PA.derive_single_threshold(1.0, 1.5) == pytest.approx(1.375)


def test_inverted_captures_are_refused():
    """The device refuses these and prompts for recapture; a derived threshold from an inverted
    pair is meaningless."""
    with pytest.raises(ValueError, match="inverted or degenerate"):
        PA.derive_single_threshold(5.0, 2.0)
    with pytest.raises(ValueError, match="inverted or degenerate"):
        PA.derive_single_threshold(3.0, 3.0)


def test_whole_band_must_be_inside_the_adaptive_range_not_just_the_centre():
    """A 5 Hz-wide band centred at 9 Hz reaches 6.5 Hz and is not adaptive-capable, even though its
    centre is inside the range."""
    ok, why = PA.band_is_adaptive_capable(9.0, 5.0)
    assert not ok and "6.50" in why
    ok, _ = PA.band_is_adaptive_capable(20.0, 5.0)
    assert ok
    ok, why = PA.band_is_adaptive_capable(29.0, 5.0)
    assert not ok and "31.50" in why


def test_the_selected_biomarker_bands_against_the_device_constraint():
    """THE CONSEQUENCE FOR THIS PROJECT. The nrs band selected by the exploration scan sits at
    3.92 Hz and is NOT deployable as a closed-loop control signal; the left_leg_vas band at
    14.82 Hz is. This is a device fact, independent of how well either correlates with pain."""
    ok_nrs, why_nrs = PA.band_is_adaptive_capable(3.9215, 5.0)
    assert not ok_nrs and "outside the adaptive range" in why_nrs
    ok_leg, _ = PA.band_is_adaptive_capable(14.817, 5.0)
    assert ok_leg


def test_policy_validation_flags_limits_and_paused_amplitude():
    # Base updated 2026-09-02: rate_hz, n_neurostimulators and lfp_responds_to_stimulation became
    # required when the manual's rate floor, single-neurostimulator contraindication and
    # LFP-must-respond requirement were encoded. A policy without them is now legitimately
    # incomplete, so the old base was a stale premise rather than this test finding a bug.
    base = dict(mode=PA.SINGLE, center_hz=20.0, band_width_hz=5.0,
                amp_min_mA=1.0, amp_max_mA=3.0, paused_amp_mA=2.0,
                rate_hz=130.0, n_neurostimulators=1, lfp_responds_to_stimulation=True)
    assert PA.validate_policy(base) == []
    assert any("max > min" in p for p in
               PA.validate_policy({**base, "amp_min_mA": 3.0, "amp_max_mA": 1.0}))
    assert any("paused amplitude" in p for p in PA.validate_policy({**base, "paused_amp_mA": 9.0}))
    assert any("limits are required" in p for p in PA.validate_policy({**base, "amp_max_mA": None}))
    assert any("Sensing Only" in p for p in
               PA.validate_policy({**base, "mode": PA.SINGLE_INVERSE}))
    assert any("unknown threshold mode" in p for p in PA.validate_policy({**base, "mode": "zzz"}))


def test_contralateral_drive_is_a_supported_configuration():
    """Relevant because this project's left-leg objective disagrees between hemispheres: sensing
    from the contralateral lead to drive the selected side is supported, not a workaround."""
    assert PA.CONTRALATERAL_DRIVE_SUPPORTED is True


def test_adaptive_json_field_names_are_recorded():
    """So a closed-loop adapter does not rediscover them by trial and error against the JSON."""
    for f in ("AdaptiveTherapyMode", "Thresholds", "StimulationLimits", "SuspendAmplitude",
              "SensingHemisphere", "DetectionBlankingDuration"):
        assert f in PA.ADAPTIVE_JSON_FIELDS


# --- rate floor and eligibility (2026-09-02, from the A610 manual + PI) ------------------------
def _ok_policy(**kw):
    base = dict(mode=PA.SINGLE, center_hz=20.0, band_width_hz=5.0, amp_min_mA=1.0,
                amp_max_mA=3.0, paused_amp_mA=2.0, rate_hz=130.0,
                n_neurostimulators=1, lfp_responds_to_stimulation=True)
    base.update(kw)
    return base


def test_a_fully_specified_policy_passes():
    assert PA.validate_policy(_ok_policy()) == []


def test_rate_below_the_adaptive_floor_is_refused():
    """The manual states a group with Adaptive Therapy has a HIGHER minimum rate than an open-loop
    group; the value is PI-supplied at 55 Hz."""
    assert PA.MIN_ADAPTIVE_RATE_HZ == 55.0
    probs = PA.validate_policy(_ok_policy(rate_hz=40.0))
    assert any("below the adaptive minimum" in p for p in probs)
    assert PA.validate_policy(_ok_policy(rate_hz=55.0)) == []
    assert PA.validate_policy(_ok_policy(rate_hz=54.9)) != []


def test_missing_rate_is_refused_rather_than_defaulted():
    """Silently assuming a rate would let a sub-floor policy through."""
    assert any("rate_hz is required" in p for p in PA.validate_policy(_ok_policy(rate_hz=None)))


def test_open_loop_rates_that_fail_closed_loop_are_named_as_such():
    """40 Hz appeared on the open-loop clinic list and is legitimate there. The message must not
    imply the rate is unusable in general."""
    p = [x for x in PA.validate_policy(_ok_policy(rate_hz=40.0)) if "adaptive minimum" in x][0]
    assert "OPEN loop" in p


def test_two_neurostimulators_is_a_contraindication():
    probs = PA.validate_policy(_ok_policy(n_neurostimulators=2))
    assert any("must NOT be configured" in p for p in probs)
    assert PA.ADAPTIVE_REQUIRES_SINGLE_NEUROSTIMULATOR is True


def test_lfp_must_be_shown_to_respond_to_stimulation():
    """A band that tracks pain but does not move with amplitude is not a control signal. Absence of
    evidence must fail, so the default (unset) is a problem, not a pass."""
    assert any("RESPONDS TO STIMULATION" in p
               for p in PA.validate_policy(_ok_policy(lfp_responds_to_stimulation=None)))
    assert any("RESPONDS TO STIMULATION" in p
               for p in PA.validate_policy(_ok_policy(lfp_responds_to_stimulation=False)))
    pol = _ok_policy(); pol.pop("lfp_responds_to_stimulation")
    assert any("RESPONDS TO STIMULATION" in p for p in PA.validate_policy(pol))


def test_indication_and_config_locks_are_recorded():
    """These are the facts that decide whether a deployment is even attemptable."""
    assert PA.ADAPTIVE_LABELLED_INDICATION == "Parkinson's disease"
    assert PA.RATE_AND_PW_FROZEN_ONCE_BRAINSENSE_CONFIGURED is True
    assert any("interleaving" in e for e in PA.ADAPTIVE_EXCLUSIONS)
    assert any("cycling" in e for e in PA.ADAPTIVE_EXCLUSIONS)
    assert set(PA.BRAINSENSE_AUTO_DISABLED_DURING) >= {"MRI mode", "recharging"}


def test_device_band_power_definition_is_recorded_as_linear_sum_of_squares():
    """The device thresholds a linear sum of squared magnitude; the pipeline's feature is log band
    power. A threshold learned in log space is not the number the device wants."""
    d = PA.DEVICE_BAND_POWER.lower()
    assert "sum of squared" in d and "not log" in d


def test_the_55_hz_floor_interacts_with_the_selected_biomarker_bands():
    """Both gates must pass together: the BAND must be inside 8-30 Hz and the stimulation RATE must
    be at or above 55 Hz. They are independent constraints on different quantities and it is easy
    to conflate them, since both are frequencies in Hz."""
    pol = _ok_policy(center_hz=14.817, band_width_hz=5.0, rate_hz=130.0)
    assert PA.validate_policy(pol) == []
    # right band, unprogrammable rate
    assert PA.validate_policy(_ok_policy(center_hz=14.817, rate_hz=40.0)) != []
    # programmable rate, undeployable band (the nrs winner at 3.92 Hz)
    assert PA.validate_policy(_ok_policy(center_hz=3.9215, rate_hz=130.0)) != []
