"""Synthetic controller-screening boundaries; no participant inputs or programming advice."""
from types import SimpleNamespace

import numpy as np
import pytest

from ClosedLoopDeployment import prescription as PR, types as TY
from StimOptimizer.routines import percept_adaptive as PA


def test_known_manual_field_still_requires_programmer_confirmation():
    field = PR.Field_("Checked limit", 1., "mA", "read_off_programmer")
    assert field.confirm == "check_on_device"
    assert field.origin == "clinician"


def test_failed_mode_is_explicit_and_does_not_remove_other_modes(monkeypatch):
    real = PR.prescribe
    def fail_single(**kwargs):
        if kwargs["mode"] == PA.SINGLE:
            raise ValueError("synthetic mode failure")
        return real(**kwargs)
    monkeypatch.setattr(PR, "prescribe", fail_single)
    result = PR.prescribe_all_modes(threshold_plan=None)
    assert set(result["modes"]) == set(PA.MODES)
    assert result["modes"][PA.DUAL].fields
    assert not result["modes"][PA.SINGLE].fields
    assert "could not be built" in result["modes"][PA.SINGLE].note.lower()


def test_insufficient_finite_power_cannot_be_a_zero_duty_estimate():
    result = PR.duty_cycle([np.nan, 1., 2.], upper=3., lower=1.)
    assert result.lfp_frac_above is None
    assert result.hours_observed is None
    assert "only 2 finite" in result.caveats[-1]


@pytest.mark.parametrize("times", [None, [0.], [0., 0., 0.]])
def test_interval_without_elapsed_span_cannot_produce_hourly_rate(times):
    result = PR.duty_cycle([0., 5., 10.], upper=8., lower=2., dt_s=1.2, t_s=times)
    assert result.hours_observed is None
    assert result.transitions_per_hour is None
    assert result.coverage_frac is None
    assert result.hours_of_signal > 0


def test_dense_samples_use_averaged_windows_and_short_series_discloses_limit():
    dense = PR.duty_cycle(np.repeat([0., 5., 10.], 12), upper=8., lower=2.,
                          t_s=np.arange(36) * .1)
    assert dense.lfp_frac_above == pytest.approx(1/3)
    assert dense.hours_of_signal == pytest.approx(3 * 1.2 / 3600)
    short = PR.duty_cycle([0., 5., 10.], upper=8., lower=2., dt_s=.1)
    assert any("NOT re-averaged" in note for note in short.caveats)


def test_operative_onsets_reject_short_excursion_and_single_has_no_between_state():
    result = PR.duty_cycle([5., 10., 5., 0., 0., 5.], upper=8., lower=2.,
                           upper_onset_ms=2400, lower_onset_ms=2400)
    assert not result.onset_inoperative
    assert result.unqualified_excursions >= 1
    single = PR.duty_cycle([0., 5., 10.], upper=8., lower=2., is_dual=False)
    assert single.lfp_frac_between is None
    assert single.lfp_frac_above == pytest.approx(1/3)
    assert any("Single Threshold" in note for note in single.caveats)


@pytest.mark.parametrize("state,params,mean,duty", [
    ([2., 3., 4.], {"amp_low_mA": 2., "amp_high_mA": 4.}, 3., .5),
    ([2., 3., 4.], {}, 3., .5),
    ([2., 2., 2.], {}, 2., None),
    ([np.nan], {}, None, None),
    (None, {}, None, None),
])
def test_replay_amplitude_duty_distinguishes_limits_missing_and_constant(state, params, mean, duty):
    replay = SimpleNamespace(state=["below", "between", "above"], amplitude_mA=state, params=params,
                             frac_time_at_upper=.2, frac_time_at_lower=.3)
    result = PR.duty_cycle([0., 5., 10.], upper=8., lower=2., replay_result=replay)
    assert result.stim_frac_mid == pytest.approx(.5)
    assert result.mean_amplitude_mA == mean
    assert result.amplitude_duty == duty
    absent = PR.duty_cycle([0., 5., 10.], upper=8., lower=2., replay_result=SimpleNamespace())
    assert absent.stim_frac_mid is None


@pytest.mark.parametrize("above,below,upper,lower,label", [
    (.1, .1, .81, 0., "chronically too high"),
    (.1, .1, 0., .81, "chronically too low"),
    (.5, .5, None, None, "transiently unstable"),
])
def test_failure_description_requires_corresponding_measured_fraction(above, below, upper, lower, label):
    assert label in PR._failure_mode(above, below, upper, lower)


def test_prescription_attaches_screening_duty_when_input_power_is_supplied():
    plan = TY.ThresholdPlan(upper=8., lower=2., capture_amp_low=1., capture_amp_high=3.)
    result = PR.prescribe(mode=PA.DUAL, threshold_plan=plan,
                          power_series=[0., 5., 10.], timing=PA.timing_plan(mode=PA.DUAL))
    assert result.duty.lfp_frac_above == pytest.approx(1/3)
    assert result.duty.mean_amplitude_mA is None
    assert any("ACTUAL programming" in text for text in result.duty.caveats)


def test_unrecognized_mode_is_rejected_instead_of_assigning_a_control_law():
    with pytest.raises(ValueError, match="unknown threshold mode"):
        PR.prescribe(mode="unrecognized")
