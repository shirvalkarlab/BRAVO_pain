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
    base = dict(mode=PA.SINGLE, center_hz=20.0, band_width_hz=5.0,
                amp_min_mA=1.0, amp_max_mA=3.0, paused_amp_mA=2.0)
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
