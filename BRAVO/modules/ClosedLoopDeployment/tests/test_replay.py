"""Tests for the Dual Threshold replay.

The cases that matter here are not the arithmetic ones. They are the three qualitatively different
things a controller can do to a recorded series — hold between the thresholds, regulate between them,
or sit pinned at a limit and act as a switch — because the third is the outcome the replay exists to
expose and the one that a mean amplitude would hide.
"""
import math

import numpy as np
import pytest

from ClosedLoopDeployment import replay, types
from StimOptimizer.routines import percept_adaptive


DT = 1.2   # the device's own averaging duration, so one input sample is one controller step


def plan(upper=10.0, lower=2.0, amp_low=1.0, amp_high=3.0, scale="linear"):
    return types.ThresholdPlan(upper=upper, lower=lower, scale=scale,
                               capture_amp_low=amp_low, capture_amp_high=amp_high)


def series(values, dt=DT):
    n = len(values)
    return {"t_s": np.arange(n, dtype=float) * dt, "power": np.asarray(values, dtype=float)}


# --------------------------------------------------------------------------------------------
# The defaults are the device's, taken from one place
# --------------------------------------------------------------------------------------------
def test_defaults_are_read_from_percept_adaptive_and_not_retyped():
    """Rule D20 (white paper p. 14). Retyping these numbers is how the two modules would drift; the
    test asserts identity with the constraints file rather than the literal values, so a correction
    there cannot leave this module simulating a superseded device."""
    d = percept_adaptive.MODES[percept_adaptive.DUAL]
    p = replay.DEFAULT_PARAMS
    assert p["averaging_ms"] == d.averaging_duration_ms == 1200.0
    assert p["onset_ms"] == d.onset_duration_ms == 1200.0
    assert p["detection_blanking_ms"] == d.detection_blanking_ms == 2000.0
    assert p["transition_up_ms"] == d.transition_up_ms == 150_000.0
    assert p["transition_down_ms"] == d.transition_down_ms == 300_000.0


def test_default_direction_is_the_labelled_one():
    """The white paper (pp. 13-15, quoted in percept_adaptive) has the amplitude ramp UP above the
    upper threshold. The direction is safety-relevant, so the default is asserted explicitly."""
    assert replay.DEVICE_HIGH_POWER_ACTION == "increase"
    assert replay.DEFAULT_PARAMS["high_power_action"] == "increase"


def test_ramp_rates_follow_from_the_span_and_the_transition_durations():
    """The transition durations are the time to cross the WHOLE amplitude span, so they set a rate.
    With a 2 mA span this is 2/150 mA/s up and 2/300 mA/s down."""
    r = replay.dual_threshold(series([5.0] * 20), plan())
    assert r.params["ramp_up_mA_per_s"] == pytest.approx(2.0 / 150.0)
    assert r.params["ramp_down_mA_per_s"] == pytest.approx(2.0 / 300.0)


# --------------------------------------------------------------------------------------------
# Hold, regulate, saturate
# --------------------------------------------------------------------------------------------
def test_power_between_the_thresholds_holds_the_amplitude_constant():
    """"When the LFP remains between the thresholds, the stimulation is held constant at the value
    it was when the LFP entered the state between thresholds" (white paper p. 14). With no crossing
    there is also no transition to count and no time at either limit."""
    r = replay.dual_threshold(series([5.0] * 200), plan())
    assert set(r.state) == {"between"}
    assert r.amplitude_mA == [2.0] * 200          # the midpoint default, held
    assert r.n_transitions == 0
    assert r.frac_time_at_upper == 0.0 and r.frac_time_at_lower == 0.0
    assert r.saturated is False
    assert r.params["frac_time_state_between"] == 1.0
    assert "never confirmed a threshold crossing" in r.note


def test_sustained_high_power_pins_the_amplitude_and_is_reported_as_saturated():
    """The case the replay exists for. Power held above the upper threshold for twenty minutes
    ramps the amplitude to the high limit in 75 s (1 mA of headroom at 2/150 mA/s) and leaves it
    there, so the mean amplitude is close to the limit and the controller is not regulating."""
    n = 1000                                       # 1000 x 1.2 s = 1200 s
    r = replay.dual_threshold(series([100.0] * n), plan())
    assert r.n_transitions == 1                    # one confirmed crossing into "above"
    assert set(r.state) == {"above"}
    assert r.amplitude_mA[-1] == pytest.approx(3.0)
    # 1 mA at 0.016 mA per 1.2 s step is 62.5 steps, so index 62 is the first pinned sample.
    assert r.frac_time_at_upper == pytest.approx((n - 62) / n)
    assert r.frac_time_at_lower == 0.0
    assert r.saturated is True
    assert "SATURATED" in r.note
    assert r.params["mean_amplitude_mA"] > 2.9


def test_a_two_position_switch_saturates_at_both_limits():
    """A long excursion above followed by a long excursion below spends most of the record pinned,
    once at each limit. Reporting only the mean amplitude here would give 2 mA — the exact midpoint
    the controller almost never occupies."""
    n_half = 2000
    r = replay.dual_threshold(series([100.0] * n_half + [0.5] * n_half), plan())
    assert r.n_transitions == 2
    assert r.frac_time_at_upper > 0.4 and r.frac_time_at_lower > 0.4
    assert r.saturated is True
    assert r.amplitude_mA[-1] == pytest.approx(1.0)


def test_a_regulating_controller_never_reaches_a_limit_and_is_not_saturated():
    """Excursions short relative to the transition durations move the amplitude a little and are
    reversed before it arrives anywhere. Ten steps above buys 0.16 mA and twenty steps below gives
    it back, so the trajectory oscillates inside the limits: this is the behaviour a deployable
    configuration should show, and it is what saturation is being distinguished from."""
    cycle = [100.0] * 10 + [0.5] * 20
    r = replay.dual_threshold(series(cycle * 30), plan())
    assert r.saturated is False
    assert r.frac_time_at_upper == 0.0 and r.frac_time_at_lower == 0.0
    assert min(r.amplitude_mA) > 1.0 and max(r.amplitude_mA) < 3.0
    assert r.n_transitions > 50
    assert "Not saturated" in r.note


def test_the_saturation_line_is_a_parameter_and_moving_it_changes_the_verdict():
    """SATURATION_FRAC is a declared judgement rather than a device number, so a reader must be able
    to move it and see the verdict change instead of having to trust 0.90."""
    # 1 mA of headroom at 0.016 mA per step needs 62.5 steps, so the 63rd step (index 62) is the
    # first one clipped to the limit and 38 of the 100 steps are pinned.
    s = series([100.0] * 100)
    r = replay.dual_threshold(s, plan())
    assert r.frac_time_at_upper == pytest.approx(0.38)
    assert r.saturated is False
    assert replay.dual_threshold(s, plan(), {"saturation_frac": 0.3}).saturated is True


# --------------------------------------------------------------------------------------------
# Direction
# --------------------------------------------------------------------------------------------
def test_the_two_directions_move_the_amplitude_opposite_ways_and_both_are_named_on_the_result():
    """The specification this file was written against described the opposite direction from the one
    the repository's device-constraints file quotes. Rather than choose silently, both are
    simulable, the labelled one is the default, and the result records which was used."""
    s = series([100.0] * 200)
    up = replay.dual_threshold(s, plan())
    down = replay.dual_threshold(s, plan(), {"high_power_action": "decrease"})

    assert up.amplitude_mA[-1] == pytest.approx(3.0)
    assert down.amplitude_mA[-1] == pytest.approx(1.0)
    assert up.params["is_labelled_direction"] is True
    assert down.params["is_labelled_direction"] is False
    assert "toward the HIGH limit" in up.note
    assert "NOT the direction the device white paper describes" in down.note
    assert "positive feedback" in down.note


def test_an_unrecognised_direction_is_refused():
    with pytest.raises(ValueError, match="high_power_action"):
        replay.dual_threshold(series([5.0] * 10), plan(), {"high_power_action": "inverse"})


# --------------------------------------------------------------------------------------------
# Onset confirmation and detection blanking
# --------------------------------------------------------------------------------------------
def test_a_crossing_shorter_than_the_onset_duration_is_not_acted_on():
    """The onset duration is the device's debounce. With it set to three controller steps, a two-step
    excursion above the upper threshold is seen and discarded, and the amplitude never moves."""
    s = series([5.0] * 10 + [100.0] * 2 + [5.0] * 10)
    r = replay.dual_threshold(s, plan(), {"onset_ms": 3 * 1200.0})
    assert r.params["onset_steps"] == 3
    assert r.n_transitions == 0
    assert set(r.amplitude_mA) == {2.0}
    assert r.params["n_crossings_suppressed_by_onset"] == 2


def test_the_default_onset_confirms_a_crossing_within_a_single_averaging_window():
    """With the device defaults the onset duration equals the averaging duration, so one window past
    a threshold is enough. This is worth pinning: it means the debounce contributes nothing at the
    default settings, and a reader who assumes otherwise would misattribute the ramp's slowness."""
    r = replay.dual_threshold(series([100.0] * 20), plan())
    assert r.params["onset_steps"] == 1
    assert r.n_transitions == 1


def test_detection_blanking_suppresses_crossings_that_arrive_too_soon_after_one():
    """Blanking of 2000 ms spans two 1.2 s controller steps, so a series that crosses on every step
    has some of its crossings refused. The count is reported because a series whose crossings are
    mostly blanked is one the controller is not tracking, whatever the state series suggests."""
    r = replay.dual_threshold(series([100.0, 5.0] * 60), plan())
    assert r.params["blanking_steps"] == 2
    assert r.params["n_crossings_suppressed_by_blanking"] > 0


# --------------------------------------------------------------------------------------------
# The device's averaging grid
# --------------------------------------------------------------------------------------------
def test_a_finer_input_is_averaged_onto_the_devices_non_overlapping_windows():
    """Rule D14: the averaging windows do not overlap, so the controller cannot change its mind more
    often than once per averaging duration. A 0.1 s input therefore becomes a 1.2 s controller grid,
    and the returned series is on the controller's grid because that is where it exists."""
    n = 1200
    s = {"t_s": np.arange(n) * 0.1, "power": np.full(n, 5.0)}
    r = replay.dual_threshold(s, plan())
    assert r.params["samples_per_averaging_window"] == 12
    assert r.params["n_input_samples"] == 1200 and r.params["n_controller_steps"] == 100
    assert len(r.t_s) == 100 and len(r.amplitude_mA) == 100
    assert r.params["dt_controller_s"] == pytest.approx(1.2)
    assert "averaged onto the device's own grid" in r.note


def test_an_input_coarser_than_the_averaging_duration_is_flagged_rather_than_upsampled():
    """A 10 s input cannot show what the device did inside a 1.2 s window. The replay runs on the
    coarse grid and says so, because inventing intermediate samples would be inventing data."""
    r = replay.dual_threshold(series([5.0] * 20, dt=10.0), plan())
    assert r.params["samples_per_averaging_window"] == 1
    assert r.params["dt_controller_s"] == pytest.approx(10.0)
    assert "no averaging was applied" in r.note


def test_a_bare_sequence_needs_a_sample_interval():
    with pytest.raises(ValueError, match="dt_s must be given"):
        replay.dual_threshold([5.0] * 10, plan())
    r = replay.dual_threshold([5.0] * 10, plan(), {"dt_s": DT})
    assert r.t_s[1] == pytest.approx(DT)


# --------------------------------------------------------------------------------------------
# Missing samples
# --------------------------------------------------------------------------------------------
def test_a_missing_estimate_holds_the_amplitude_rather_than_continuing_the_ramp():
    """No supplied document says what the device does with a dropped estimate, so the amplitude is
    held across it and the count is reported. Continuing the ramp would be a guess presented as a
    trajectory."""
    s = series([100.0] * 10 + [float("nan")] * 10 + [100.0] * 10)
    r = replay.dual_threshold(s, plan())
    assert r.params["n_missing_windows"] == 10
    assert r.amplitude_mA[19] == pytest.approx(r.amplitude_mA[9])
    assert r.amplitude_mA[29] > r.amplitude_mA[19]
    assert r.state[15] == "above"                  # the adopted state carries across the gap
    assert "no power estimate" in r.note


# --------------------------------------------------------------------------------------------
# The honesty requirement
# --------------------------------------------------------------------------------------------
def test_every_result_carries_the_open_loop_confound_caveat():
    """The replay assumes the observed power would have occurred under closed-loop control, which is
    false whenever the band responds to amplitude. The caveat has to travel with the numbers, so it
    is asserted on the result and not merely present in the docstring."""
    r = replay.dual_threshold(series([5.0] * 20), plan())
    assert "assumes the same power would have occurred under closed-loop control" in r.note
    assert "not as a prediction" in r.note
    assert "controller changes the amplitude that produced the power" in r.note
    assert replay.dual_threshold.__doc__ is not None
    assert "does not establish" in replay.dual_threshold.__doc__.lower()


def test_a_non_linear_threshold_scale_is_reported_because_the_routine_does_not_convert():
    """A plan on a log scale with a linear power series would put every crossing in the wrong place
    while still producing a plausible trajectory, so the mismatch has to be visible."""
    r = replay.dual_threshold(series([5.0] * 20), plan(scale="log10"))
    assert r.params["scale"] == "log10"
    assert "does not convert" in r.note


def test_the_trajectory_is_not_claimed_to_be_quantised():
    r = replay.dual_threshold(series([5.0] * 20), plan())
    assert r.params["amplitude_quantised"] is False
    assert "commanded amplitude" in r.note


# --------------------------------------------------------------------------------------------
# Refusals
# --------------------------------------------------------------------------------------------
def test_a_plan_without_thresholds_is_refused():
    """A plan that could not place thresholds has already answered the deployability question; a
    replay that substituted a guess would turn that refusal into a trajectory."""
    with pytest.raises(ValueError, match="no thresholds set"):
        replay.dual_threshold(series([5.0] * 10), types.ThresholdPlan(upper=None, lower=None,
                                                                      capture_amp_low=1.0,
                                                                      capture_amp_high=3.0))


def test_inverted_or_touching_thresholds_are_refused_as_the_device_refuses_them():
    """White paper p. 15: thresholds "too close together or ... inverted" prompt for recapture."""
    with pytest.raises(ValueError, match="inverted or degenerate"):
        replay.dual_threshold(series([5.0] * 10), plan(upper=2.0, lower=10.0))
    with pytest.raises(ValueError, match="inverted or degenerate"):
        replay.dual_threshold(series([5.0] * 10), plan(upper=5.0, lower=5.0))


def test_missing_or_degenerate_amplitude_limits_are_refused():
    """Without limits there is no ramp rate at all; with coincident limits the output is a constant
    that would read as a regulating controller."""
    with pytest.raises(ValueError, match="no adaptive amplitude limits"):
        replay.dual_threshold(series([5.0] * 10), plan(amp_low=None, amp_high=None))
    with pytest.raises(ValueError, match="inverted or degenerate"):
        replay.dual_threshold(series([5.0] * 10), plan(amp_low=2.0, amp_high=2.0))


def test_amplitude_limits_can_be_overridden_but_the_starting_amplitude_must_be_inside_them():
    r = replay.dual_threshold(series([5.0] * 10), plan(), {"amp_low_mA": 0.0, "amp_high_mA": 4.0})
    assert r.params["amp_init_mA"] == pytest.approx(2.0)
    assert r.params["amp_low_mA"] == 0.0 and r.params["amp_high_mA"] == 4.0
    with pytest.raises(ValueError, match="outside the amplitude limits"):
        replay.dual_threshold(series([5.0] * 10), plan(), {"amp_init_mA": 9.0})


def test_a_non_uniform_time_base_is_refused_rather_than_replayed_across_the_gap():
    """A gap is a period in which the device had no power estimate. Simulating across it would
    manufacture a controller trajectory for a time the controller was not running."""
    t = np.arange(20, dtype=float) * DT
    t[10:] += 600.0                                # a ten-minute dropout
    with pytest.raises(ValueError, match="not uniform"):
        replay.dual_threshold({"t_s": t, "power": np.full(20, 5.0)}, plan())


def test_degenerate_series_are_refused():
    with pytest.raises(ValueError, match="empty"):
        replay.dual_threshold([], plan(), {"dt_s": DT})
    with pytest.raises(ValueError, match="single sample"):
        replay.dual_threshold([5.0], plan(), {"dt_s": DT})


def test_an_unknown_parameter_key_is_refused_rather_than_ignored():
    """A misspelt timing key would silently leave the device default in place, and the resulting
    trajectory would look entirely plausible."""
    with pytest.raises(ValueError, match="unknown params"):
        replay.dual_threshold(series([5.0] * 10), plan(), {"transition_up_s": 150.0})


def test_zero_transition_durations_are_refused():
    """The labelling describes gradual, incremental transitions; a zero duration would jump the
    amplitude straight to a limit."""
    with pytest.raises(ValueError, match="must be positive"):
        replay.dual_threshold(series([5.0] * 10), plan(), {"transition_up_ms": 0.0})


# --------------------------------------------------------------------------------------------
# Internal consistency of the returned record
# --------------------------------------------------------------------------------------------
def test_the_returned_record_is_internally_consistent():
    r = replay.dual_threshold(series([100.0] * 50 + [5.0] * 50 + [0.5] * 50), plan())
    n = len(r.t_s)
    assert len(r.amplitude_mA) == n == len(r.state) == r.params["n_controller_steps"]
    assert set(r.state) <= {"below", "between", "above"}
    frac_sum = (r.params["frac_time_state_above"] + r.params["frac_time_state_between"]
                + r.params["frac_time_state_below"])
    assert frac_sum == pytest.approx(1.0)
    assert all(1.0 - 1e-12 <= a <= 3.0 + 1e-12 for a in r.amplitude_mA)
    assert r.params["mean_amplitude_mA"] == pytest.approx(float(np.mean(r.amplitude_mA)))
    assert math.isclose(r.t_s[1] - r.t_s[0], r.params["dt_controller_s"])
