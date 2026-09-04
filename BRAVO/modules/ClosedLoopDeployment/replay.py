"""Replay the device's Dual Threshold controller over a band-power series we already recorded.

WHAT THIS FILE IS FOR
---------------------
Before a closed-loop configuration is programmed, somebody has to answer a question that the
threshold placement alone does not answer: given the band power this participant actually produced,
what would the controller have DONE with it? A pair of thresholds can look well placed in the power
histogram and still produce a controller that sits pinned at one amplitude limit for the whole
recording, which is a switch rather than a regulator. This file runs the device's control law over
an observed series so that outcome becomes visible before it is programmed rather than after.

THE HONESTY REQUIREMENT, STATED BEFORE ANYTHING ELSE
---------------------------------------------------
This is a simulation of the CONTROLLER, not a prediction of the SYSTEM. It replays the control law
over a power series that was recorded while the amplitude was doing something else, and it therefore
assumes that the same power series would have occurred under closed-loop control. That assumption is
false in general, and it is false for a specific and unavoidable reason: the whole premise of
deploying this band is that amplitude changes band power, so a controller that changes the amplitude
changes the very input this replay is feeding it. The two errors run in opposite directions and
neither can be bounded from retrospective data. If the controller raises amplitude and amplitude
suppresses the band, the true power would have fallen faster than the recording shows, so the real
controller would have retreated from the limit sooner than this replay does and the saturation
reported here is pessimistic. If the band does not in fact respond to amplitude, the recorded series
is the right input and the saturation reported here is real.

What this routine therefore establishes is narrow and worth stating plainly: it establishes what the
control law does to a given input, which is a statement about the controller's arithmetic and about
the placement of the thresholds relative to the observed distribution of power. It does not
establish what the amplitude trajectory would have been in the participant, and no result from this
file should be quoted as a predicted amplitude. Every ``ReplayResult`` carries this caveat in its
``note`` field so that it travels with the numbers instead of being left behind in this docstring.

WHICH WAY THE AMPLITUDE MOVES: A CONFLICT THAT IS RECORDED RATHER THAN RESOLVED HERE
-----------------------------------------------------------------------------------
The direction of the control law is safety-relevant, because getting it backwards converts negative
feedback into positive feedback, so this file does not pick a direction by taste. Every source in
this repository that quotes the device labelling states the same law. From
``StimOptimizer/routines/percept_adaptive.py``, quoting the Percept adaptive white paper
(UC202012929dEN) pp. 13-15:

    "When the LFP passes above the upper threshold, the stimulation amplitude slowly ramps up. When
     the LFP passes below the lower threshold, the stimulation amplitude slowly ramps down. When the
     LFP remains between the thresholds, the stimulation is held constant at the value it was when
     the LFP entered the state between thresholds."

That law is also the only one that closes the loop negatively given the direction of effect the same
document requires of a control band. ``percept_adaptive`` records the requirement as
``DUAL_THRESHOLD_ASSUMES_POWER_FALLS_WITH_AMPLITUDE``, meaning the band's power must fall as
amplitude rises. Combine the two: high power raises amplitude, higher amplitude suppresses power,
and power returns toward the band between the thresholds. Reverse the control law while keeping the
same physiology and the arithmetic runs the other way: high power would lower the amplitude, lower
amplitude would raise the power further, and the controller would drive itself to a limit and stay
there, bounded only by the clinician's amplitude limits.

The specification this file was written against described the opposite direction, stating that
amplitude ramps down toward the lower limit when power rises above the upper threshold. That is not
what any document in this repository says, and it is not a difference that can be split. Rather than
choose silently, the direction is an explicit parameter, ``high_power_action``. It defaults to
``"increase"``, which is the labelled behaviour quoted above; passing ``"decrease"`` simulates the
other convention. Whichever is used is recorded in ``ReplayResult.params`` and named in
``ReplayResult.note``, so a reader can never be left wondering which law produced a trajectory. If
the labelled direction is ever shown to be the other one, the fix is a change of default in one
place and the quote above should be replaced with the passage that supersedes it.

TIMING PARAMETERS
-----------------
The default timings are taken from ``percept_adaptive.MODES["dual"]`` rather than retyped here, so
there is exactly one place in the repository where a device timing number lives and one place to
correct if the labelling is re-read. They are the Dual Threshold defaults of rule ``D20``
(white paper p. 14): averaging duration 1200 ms, onset duration 1200 ms, detection blanking
2000 ms, transition up 2.5 minutes, transition down 5 minutes.

Note what the two transition durations are. They are not delays and they are not time constants.
They are the durations over which the amplitude traverses the whole distance between the two
amplitude limits, so together with those limits they set a RATE in mA per second. A controller with
a 1.0 mA span and a 2.5-minute transition up moves at 1.0 / 150 = 0.0067 mA/s, and a 30-second
excursion above the upper threshold therefore buys about 0.2 mA of amplitude. This is the reason a
replay is informative at all: the ramp is slow enough relative to how fast pain-band power moves
that the controller frequently never reaches the limit it is heading for, and whether it does is an
empirical question about the recorded series rather than something that can be reasoned out.
"""
from __future__ import annotations

import math
import warnings

import numpy as np

from StimOptimizer.routines import percept_adaptive

from . import types

#: The Dual Threshold specification, read once at import so the defaults below cannot drift from the
#: device-constraints file. Importing it also means a future correction to a device timing number is
#: picked up here without anyone having to remember that this file exists.
_DUAL = percept_adaptive.MODES[percept_adaptive.DUAL]

#: The labelled control direction, quoted in the module docstring above (white paper pp. 13-15).
#: Named as a constant rather than written as a string literal in the defaults so that a reader
#: looking for "what does the device do" finds one line with the citation attached to it.
DEVICE_HIGH_POWER_ACTION = "increase"

#: The two conventions this file can simulate. ``"increase"`` is the labelled device behaviour;
#: ``"decrease"`` exists only so the other convention can be simulated deliberately and named on the
#: result, and it should not be used to model this device without a document that supports it.
HIGH_POWER_ACTIONS = ("increase", "decrease")

#: Fraction of time pinned at either amplitude limit above which the controller is reported as
#: saturated. This is a DECLARED JUDGEMENT and not a device number: no document defines saturation.
#: It is set at 0.90 because the failure this flag exists to catch is a controller that is really a
#: two-position switch, and a controller spending nine tenths of the recording hard against a limit
#: has at most a tenth of the record in which its intermediate amplitudes mean anything. It is a
#: parameter so a reader who thinks the line belongs elsewhere can move it and see what changes.
SATURATION_FRAC = 0.90

#: How close to a limit counts as being AT that limit, in mA. The trajectory is clipped to the
#: limits exactly, so the pinned samples land on the limit to the last bit and this tolerance only
#: guards against floating-point drift. It is deliberately far below the 0.1 mA programming
#: resolution: widening it would count samples that are merely near the limit as pinned and would
#: inflate the saturation fraction the flag above depends on.
AMP_AT_LIMIT_TOL_mA = 1e-9

#: Largest fractional departure from the median sample interval that still counts as a uniformly
#: sampled series. Five percent accommodates ordinary timestamp jitter in a device export while
#: still refusing a series with a real gap in it, and the reason gaps are refused is given in
#: ``_coerce_series``.
DT_UNIFORMITY_TOL = 0.05

DEFAULT_PARAMS = {
    "averaging_ms": _DUAL.averaging_duration_ms,
    "onset_ms": _DUAL.onset_duration_ms,
    "detection_blanking_ms": _DUAL.detection_blanking_ms,
    "transition_up_ms": _DUAL.transition_up_ms,
    "transition_down_ms": _DUAL.transition_down_ms,
    "high_power_action": DEVICE_HIGH_POWER_ACTION,
    "saturation_frac": SATURATION_FRAC,
    "amp_at_limit_tol_mA": AMP_AT_LIMIT_TOL_mA,
    # Amplitude limits and starting amplitude. None means "take it from the ThresholdPlan", and the
    # starting amplitude has no device default at all, which is discussed in ``dual_threshold``.
    "amp_low_mA": None,
    "amp_high_mA": None,
    "amp_init_mA": None,
}


# --------------------------------------------------------------------------------------------
# Input handling
# --------------------------------------------------------------------------------------------
def _coerce_series(power_series, dt_s=None):
    """Return ``(t_s, power, dt_s)`` from the several shapes a caller may reasonably have.

    ``t_s`` and ``power`` come back as float arrays and ``dt_s`` is the median sample interval,
    which the caller needs in order to convert the device's millisecond timings into sample counts.

    Accepted, in the order tried: a mapping with ``t_s``/``power`` (or ``time_s``/``band_power``);
    an object carrying those as attributes; a two-column array or a pair of sequences; and a plain
    one-dimensional sequence of powers, which requires ``dt_s`` because a power series with no time
    base cannot be replayed against timing parameters measured in milliseconds.

    A uniform sample interval is REQUIRED, and this is the one place the routine is deliberately
    strict. The controller's onset and blanking behaviour is counted in whole sample intervals and
    its ramp advances by rate times interval, so a series whose interval changes partway through
    would have those quantities silently mean different things in different halves of the recording.
    Worse, a recording with a real gap in it — a disconnected session, a dropped stream — has no
    power samples across the gap, and continuing the simulation across it would manufacture a
    controller trajectory for a period in which the device had no input. The right handling of a
    gap is to split the recording and replay the pieces, which the caller can do and this routine
    cannot do for them, so it raises and says so.
    """
    t = p = None

    if isinstance(power_series, dict):
        for tk in ("t_s", "time_s", "t", "time"):
            if tk in power_series:
                t = power_series[tk]
                break
        for pk in ("power", "band_power", "power_series", "p"):
            if pk in power_series:
                p = power_series[pk]
                break
        if p is None:
            raise ValueError(
                "power_series was a mapping with no power values in it. Expected one of the keys "
                "'power', 'band_power', 'power_series' or 'p', and optionally a time base under "
                f"'t_s' or 'time_s'; got keys {sorted(power_series)}.")
    elif hasattr(power_series, "power") or hasattr(power_series, "band_power"):
        p = getattr(power_series, "power", None)
        if p is None:
            p = getattr(power_series, "band_power")
        t = getattr(power_series, "t_s", None)
        if t is None:
            t = getattr(power_series, "time_s", None)
    else:
        arr = np.asarray(power_series, dtype=float)
        if arr.ndim == 2:
            # Two columns is (time, power); two rows is the same thing transposed. Both are common
            # enough in hand-assembled test data that guessing from the shape is worth it, but a
            # 2x2 is genuinely ambiguous and is refused rather than silently read one way.
            if arr.shape[0] == 2 and arr.shape[1] == 2:
                raise ValueError(
                    "power_series is 2x2, which could be two (time, power) samples or a transposed "
                    "pair of series. Pass a mapping with 't_s' and 'power' keys to say which.")
            if arr.shape[1] == 2:
                t, p = arr[:, 0], arr[:, 1]
            elif arr.shape[0] == 2:
                t, p = arr[0, :], arr[1, :]
            else:
                raise ValueError(
                    f"power_series has shape {arr.shape}; a two-dimensional series must have "
                    "exactly two columns (time, power) or two rows.")
        elif arr.ndim == 1:
            p = arr
        else:
            raise ValueError(f"power_series has {arr.ndim} dimensions; expected one or two.")

    p = np.asarray(p, dtype=float).ravel()
    if p.size == 0:
        raise ValueError("power_series is empty; there is nothing to replay.")

    if t is None:
        if dt_s is None:
            raise ValueError(
                "power_series carries no time base, so dt_s must be given. The controller's "
                "timings are durations in milliseconds (averaging, onset, blanking, the two "
                "transitions), and without a sample interval there is no way to convert them into "
                "sample counts or into a ramp step per sample.")
        dt = float(dt_s)
        if not (dt > 0):
            raise ValueError(f"dt_s must be positive, got {dt_s!r}.")
        t = np.arange(p.size, dtype=float) * dt
    else:
        t = np.asarray(t, dtype=float).ravel()
        if t.size != p.size:
            raise ValueError(f"time base has {t.size} samples but power has {p.size}.")

    if p.size == 1:
        raise ValueError(
            "power_series has a single sample. A controller replay needs at least two samples "
            "because the amplitude moves by rate times sample interval and one sample defines no "
            "interval.")

    d = np.diff(t)
    if np.any(d <= 0):
        raise ValueError("the time base is not strictly increasing; sort the series first.")
    med = float(np.median(d))
    worst = float(np.max(np.abs(d - med)) / med)
    if worst > DT_UNIFORMITY_TOL:
        raise ValueError(
            f"the sample interval is not uniform: the largest departure from the median interval "
            f"of {med:.4g} s is {worst * 100:.1f} percent, above the {DT_UNIFORMITY_TOL * 100:.0f} "
            "percent tolerance. This is refused rather than accommodated because a gap in the "
            "recording is a period in which the device had no power estimate, and replaying "
            "across it would invent a controller trajectory for a time the controller was not "
            "running. Split the recording at its gaps and replay each piece.")
    return t, p, med


def _average_to_device_grid(t, p, dt, averaging_s):
    """Aggregate a power series onto the device's non-overlapping averaging windows.

    The device does not see the series at whatever resolution it was exported at. It forms a band
    power estimate over each averaging window and those windows do not overlap (rule ``D14``), so
    the controller can change its mind at most once per averaging duration. Replaying at a finer
    resolution than that would let the simulated controller react to fluctuations the device would
    have averaged away, and it would make the onset and blanking durations span more samples than
    they really do.

    Returns ``(t_grid, p_grid, dt_grid, n_per_window)``. When the input is already at or coarser
    than the averaging duration there is nothing to aggregate and the input grid is returned
    unchanged; the caller records that case in the note, because an input coarser than the averaging
    duration means the replay cannot reproduce the device's behaviour within a window and is
    reporting a coarser controller than the real one.

    The timestamp of a window is its LAST input sample rather than its centre, because the estimate
    is only complete at the end of the window and the controller cannot act on it before then.
    """
    n_per = int(math.floor(averaging_s / dt + 1e-9))
    if n_per <= 1:
        return t, p, dt, 1

    n_win = int(p.size // n_per)
    if n_win < 2:
        raise ValueError(
            f"the series holds {p.size} samples at {dt:.4g} s, which is fewer than two averaging "
            f"windows of {averaging_s:.4g} s. The controller updates once per averaging window, so "
            "a replay over fewer than two windows has no dynamics to show.")

    keep = n_win * n_per
    # A trailing partial window is dropped rather than averaged over fewer samples, because the
    # device's windows are fixed-length and a short final estimate is not one the device would form.
    block = p[:keep].reshape(n_win, n_per)
    # A window containing only missing samples must stay missing, and that is exactly what nanmean
    # returns for it. The warning it emits is suppressed because the NaN is the wanted answer here
    # rather than a problem: the controller treats a missing estimate as "no crossing" and the count
    # of missing windows is reported on the result so it cannot pass unnoticed.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        p_grid = np.nanmean(block, axis=1)
    t_grid = t[:keep].reshape(n_win, n_per)[:, -1]
    return t_grid, p_grid, dt * n_per, n_per


# --------------------------------------------------------------------------------------------
# The controller
# --------------------------------------------------------------------------------------------
def dual_threshold(power_series, plan, params=None) -> types.ReplayResult:
    """Simulate the Dual Threshold controller over an observed band-power series.

    ``power_series`` is the observed band power, in the same units and on the same scale as the
    thresholds in ``plan``. It may be a mapping with ``t_s`` and ``power``, a two-column array, or a
    bare sequence of powers together with ``params["dt_s"]``.

    ``plan`` is a :class:`types.ThresholdPlan`. Its ``upper`` and ``lower`` are the LFP power
    thresholds. Its ``capture_amp_low`` and ``capture_amp_high`` are used as the adaptive amplitude
    limits unless ``params`` overrides them, which is discussed below.

    ``params`` overrides any of :data:`DEFAULT_PARAMS`, plus ``dt_s`` when the series has no time
    base. The resolved parameters are echoed on the result so a trajectory can always be traced back
    to the numbers that produced it.

    WHAT THIS ROUTINE DOES NOT ESTABLISH. It replays the control law over a power series recorded
    while the amplitude was following the participant's actual programming, and so it assumes the
    same power would have occurred under closed-loop control. That assumption is false whenever the
    band responds to amplitude, which is the reason for deploying the band in the first place, so
    the amplitude trajectory returned here is what the control law does to this input and not a
    prediction of what the device would have delivered. The reasoning is set out at length in the
    module docstring and the caveat is copied onto ``ReplayResult.note``.

    THE AMPLITUDE LIMITS. The device's adaptive amplitude limits are programmed separately from the
    threshold capture, but in the capture workflow the two LFP thresholds are gathered at a low and
    a high stimulation amplitude, and those capture amplitudes are the natural limits for the
    controller to move between: they are the amplitudes at which the band's response was actually
    observed. This routine therefore defaults to ``plan.capture_amp_low`` and
    ``plan.capture_amp_high`` and lets ``params`` override them, so that a plan proposing limits
    wider than the range in which the band was characterised has to say so explicitly.

    THE STARTING AMPLITUDE. No supplied document states what amplitude the device starts adaptive
    therapy at. The default here is the midpoint of the two limits, which is a declared choice made
    because it is the only starting point that does not pre-load the answer to the question the
    replay is asked: starting at a limit would count as pinned time whatever the controller then
    does. On a recording long relative to the transition durations the choice washes out; on a short
    one it does not, and ``params["amp_init_mA"]`` exists so its influence can be tested.

    AMPLITUDE IS NOT QUANTISED HERE. The clinician programs amplitude in 0.1 mA increments, but no
    supplied document states whether the adaptive ramp advances on that same grid or moves
    continuously between the limits. The trajectory returned here is continuous and should be read
    as the amplitude the control law commands, not as a quantised output the device would deliver.
    """
    p_in = dict(DEFAULT_PARAMS)
    if params:
        unknown = set(params) - set(DEFAULT_PARAMS) - {"dt_s"}
        if unknown:
            raise ValueError(
                f"unknown params {sorted(unknown)}. Accepted keys are "
                f"{sorted(set(DEFAULT_PARAMS) | {'dt_s'})}. Unknown keys are refused rather than "
                "ignored because a misspelt timing key would silently leave the device default in "
                "place and the trajectory would look plausible.")
        p_in.update(params)

    # ---- thresholds -------------------------------------------------------------------------
    upper, lower = plan.upper, plan.lower
    if upper is None or lower is None:
        raise ValueError(
            "the ThresholdPlan has no thresholds set (upper="
            f"{upper!r}, lower={lower!r}). There is nothing to replay: a plan that could not place "
            "thresholds has already answered the deployability question in the negative, and "
            "substituting a guess here would convert that refusal into a trajectory.")
    upper, lower = float(upper), float(lower)
    if not (upper > lower):
        raise ValueError(
            f"thresholds are inverted or degenerate (upper={upper!r}, lower={lower!r}). The device "
            "itself refuses this case: when the captured thresholds are 'either too close together "
            "or are inverted' the A610 application prompts for recapture or manual adjustment "
            "(white paper p. 15). With upper not above lower the hold region between the "
            "thresholds is empty and the controller would be a two-state switch by construction.")

    # ---- amplitude limits -------------------------------------------------------------------
    amp_low = p_in["amp_low_mA"]
    amp_high = p_in["amp_high_mA"]
    if amp_low is None:
        amp_low = plan.capture_amp_low
    if amp_high is None:
        amp_high = plan.capture_amp_high
    if amp_low is None or amp_high is None:
        raise ValueError(
            "no adaptive amplitude limits are available: the ThresholdPlan carries "
            f"capture_amp_low={plan.capture_amp_low!r} and "
            f"capture_amp_high={plan.capture_amp_high!r}, and params supplied no override. The "
            "limits set the ramp rate in mA per second, so without them the transition durations "
            "cannot be converted into amplitude at all.")
    amp_low, amp_high = float(amp_low), float(amp_high)
    if not (amp_high > amp_low):
        raise ValueError(
            f"amplitude limits are inverted or degenerate (low={amp_low!r}, high={amp_high!r}). A "
            "controller whose limits coincide has no authority: its output would be a constant, "
            "and a constant amplitude reported alongside a mean and a state series would read as a "
            "regulating controller when nothing was being regulated.")

    action = p_in["high_power_action"]
    if action not in HIGH_POWER_ACTIONS:
        raise ValueError(
            f"high_power_action must be one of {list(HIGH_POWER_ACTIONS)}, got {action!r}.")

    amp_init = p_in["amp_init_mA"]
    if amp_init is None:
        amp_init = 0.5 * (amp_low + amp_high)
    amp_init = float(amp_init)
    if not (amp_low - 1e-12 <= amp_init <= amp_high + 1e-12):
        raise ValueError(
            f"amp_init_mA={amp_init!r} lies outside the amplitude limits "
            f"[{amp_low!r}, {amp_high!r}]; the controller can never return there, so the "
            "trajectory would open with a jump that is an artefact of the initial condition.")
    amp_init = min(max(amp_init, amp_low), amp_high)

    # ---- series, then the device's own averaging grid ---------------------------------------
    t_raw, p_raw, dt_raw = _coerce_series(power_series, p_in.get("dt_s"))
    averaging_s = float(p_in["averaging_ms"]) / 1000.0
    if not (averaging_s > 0):
        raise ValueError(f"averaging_ms must be positive, got {p_in['averaging_ms']!r}.")
    t, p, dt, n_per_window = _average_to_device_grid(t_raw, p_raw, dt_raw, averaging_s)
    input_finer_than_averaging = n_per_window > 1

    # ---- timing converted into whole controller steps ---------------------------------------
    # Onset and blanking are counted in whole controller steps rather than in seconds because the
    # controller only exists at these instants: it cannot notice a crossing halfway through a window
    # it has not finished averaging. The step counts are echoed on the result so the discretisation
    # is visible; with the device defaults (onset 1200 ms, averaging 1200 ms) the onset is exactly
    # one step, meaning a single window past a threshold is enough to confirm the crossing, and
    # blanking of 2000 ms rounds up to two steps.
    onset_s = float(p_in["onset_ms"]) / 1000.0
    blank_s = float(p_in["detection_blanking_ms"]) / 1000.0
    if onset_s < 0 or blank_s < 0:
        raise ValueError("onset_ms and detection_blanking_ms must not be negative.")
    onset_steps = max(1, int(math.ceil(onset_s / dt - 1e-9)))
    blank_steps = max(0, int(math.ceil(blank_s / dt - 1e-9)))

    up_s = float(p_in["transition_up_ms"]) / 1000.0
    down_s = float(p_in["transition_down_ms"]) / 1000.0
    if not (up_s > 0 and down_s > 0):
        raise ValueError(
            "transition_up_ms and transition_down_ms must be positive; they are the durations over "
            "which the amplitude crosses the whole span between the limits, and a zero duration "
            "would mean the amplitude jumps to a limit, which is precisely the behaviour the "
            "labelling says the device does not have ('transitions are gradual and incremental').")
    span = amp_high - amp_low
    rate_up = span / up_s        # mA per second while the amplitude is increasing
    rate_down = span / down_s    # mA per second while the amplitude is decreasing

    # ---- run --------------------------------------------------------------------------------
    n = int(p.size)
    amp_out = np.empty(n, dtype=float)
    state_out = [""] * n

    # The controller starts in the hold state. This is a declared choice: adopting whatever state
    # the first window happens to fall in would skip the onset confirmation for that one crossing
    # and would let a single opening sample commit the controller to a ramp.
    adopted = "between"
    amp = amp_init
    pending = None
    pending_run = 0
    blank_left = 0
    n_transitions = 0
    n_onset_suppressed = 0     # crossings that appeared but did not persist for the onset duration
    n_blank_suppressed = 0     # crossings ready to be adopted but refused during detection blanking
    n_missing = 0

    for i in range(n):
        pi = p[i]

        if math.isnan(pi):
            # A missing estimate is not a crossing. The amplitude is HELD rather than allowed to
            # continue an in-progress ramp, because no document says what the device does with a
            # dropped estimate and holding is the choice that does not invent movement. Missing
            # samples are counted and reported so a series full of them cannot be mistaken for a
            # clean replay.
            n_missing += 1
            pending, pending_run = None, 0
            if blank_left > 0:
                blank_left -= 1
            state_out[i] = adopted
            amp_out[i] = amp
            continue

        raw = "above" if pi > upper else ("below" if pi < lower else "between")

        if raw == adopted:
            pending, pending_run = None, 0
        else:
            if pending == raw:
                pending_run += 1
            else:
                pending, pending_run = raw, 1
            if pending_run >= onset_steps:
                if blank_left > 0:
                    # Detection blanking: the crossing is real and has persisted, but the device is
                    # still blanked from the previous detection, so it is not acted on.
                    n_blank_suppressed += 1
                else:
                    adopted = raw
                    n_transitions += 1
                    blank_left = blank_steps
                    pending, pending_run = None, 0
            else:
                n_onset_suppressed += 1

        if blank_left > 0:
            blank_left -= 1

        # Target amplitude for the adopted state. With the labelled law ("increase"), power above
        # the upper threshold drives the amplitude toward the HIGH limit, because raising amplitude
        # is what suppresses the band; power below the lower threshold drives it toward the LOW
        # limit, because the band is already suppressed and the amplitude is not needed. Between the
        # thresholds the amplitude holds at whatever value it had on entering that state, which is
        # what the labelling describes and is why the target is the current amplitude rather than a
        # midpoint.
        if adopted == "above":
            target = amp_high if action == "increase" else amp_low
        elif adopted == "below":
            target = amp_low if action == "increase" else amp_high
        else:
            target = amp

        if target > amp:
            amp = min(target, amp + rate_up * dt)
        elif target < amp:
            amp = max(target, amp - rate_down * dt)
        amp = min(max(amp, amp_low), amp_high)

        state_out[i] = adopted
        amp_out[i] = amp

    # ---- summary ----------------------------------------------------------------------------
    tol = float(p_in["amp_at_limit_tol_mA"])
    at_high = float(np.mean(np.abs(amp_out - amp_high) <= tol))
    at_low = float(np.mean(np.abs(amp_out - amp_low) <= tol))
    sat_frac = float(p_in["saturation_frac"])
    saturated = bool(at_high + at_low >= sat_frac)

    note = _build_note(
        action=action, saturated=saturated, at_low=at_low, at_high=at_high, sat_frac=sat_frac,
        n_transitions=n_transitions, n=n, dt=dt, span=span, up_s=up_s, down_s=down_s,
        n_missing=n_missing, input_finer=input_finer_than_averaging, n_per_window=n_per_window,
        dt_raw=dt_raw, averaging_s=averaging_s, scale=plan.scale)

    return types.ReplayResult(
        t_s=[float(v) for v in t],
        amplitude_mA=[float(v) for v in amp_out],
        state=state_out,
        frac_time_at_upper=at_high,
        frac_time_at_lower=at_low,
        n_transitions=int(n_transitions),
        saturated=saturated,
        params={
            "upper": upper,
            "lower": lower,
            "scale": plan.scale,
            "amp_low_mA": amp_low,
            "amp_high_mA": amp_high,
            "amp_init_mA": amp_init,
            "high_power_action": action,
            "is_labelled_direction": action == DEVICE_HIGH_POWER_ACTION,
            "averaging_ms": float(p_in["averaging_ms"]),
            "onset_ms": float(p_in["onset_ms"]),
            "detection_blanking_ms": float(p_in["detection_blanking_ms"]),
            "transition_up_ms": float(p_in["transition_up_ms"]),
            "transition_down_ms": float(p_in["transition_down_ms"]),
            "ramp_up_mA_per_s": rate_up,
            "ramp_down_mA_per_s": rate_down,
            "dt_input_s": dt_raw,
            "dt_controller_s": dt,
            "samples_per_averaging_window": int(n_per_window),
            "onset_steps": int(onset_steps),
            "blanking_steps": int(blank_steps),
            "n_input_samples": int(p_raw.size),
            "n_controller_steps": n,
            "n_missing_windows": int(n_missing),
            "n_crossings_suppressed_by_onset": int(n_onset_suppressed),
            "n_crossings_suppressed_by_blanking": int(n_blank_suppressed),
            "frac_time_state_above": float(np.mean([s == "above" for s in state_out])),
            "frac_time_state_between": float(np.mean([s == "between" for s in state_out])),
            "frac_time_state_below": float(np.mean([s == "below" for s in state_out])),
            "mean_amplitude_mA": float(np.mean(amp_out)),
            "saturation_frac_threshold": sat_frac,
            "amplitude_quantised": False,
        },
        note=note,
    )


def _build_note(*, action, saturated, at_low, at_high, sat_frac, n_transitions, n, dt, span,
                up_s, down_s, n_missing, input_finer, n_per_window, dt_raw, averaging_s, scale):
    """Assemble the caveat text that travels with the numbers.

    Written as full sentences and assembled here rather than at the call site so that the wording is
    in one place and so the mandatory caveat cannot be dropped by a caller who constructs a
    ``ReplayResult`` through this routine. The order is deliberate: the assumption that invalidates a
    naive reading comes first, before any reader has reached the amplitudes.
    """
    parts = [
        "This is a replay of the control law over a power series that was recorded while the "
        "amplitude was following the participant's actual programming, so it assumes the same "
        "power would have occurred under closed-loop control. That assumption is false whenever "
        "the band responds to amplitude, which is the premise of deploying the band at all: the "
        "controller changes the amplitude that produced the power it is being fed. Read the "
        "trajectory as what the control law does to this input, and not as a prediction of the "
        "amplitude the device would have delivered."
    ]

    if action == DEVICE_HIGH_POWER_ACTION:
        parts.append(
            "Direction simulated: power above the upper threshold drives the amplitude toward the "
            "HIGH limit and power below the lower threshold drives it toward the LOW limit, which "
            "is the behaviour quoted from the device white paper pp. 13-15 in "
            "StimOptimizer.routines.percept_adaptive.")
    else:
        parts.append(
            "Direction simulated: power above the upper threshold drives the amplitude toward the "
            "LOW limit and power below the lower threshold drives it toward the HIGH limit. This "
            "is NOT the direction the device white paper describes at pp. 13-15, and combined with "
            "the requirement that the band's power fall as amplitude rises it is a positive "
            "feedback law. It was simulated because it was asked for explicitly; do not present "
            "this trajectory as the device's behaviour.")

    parts.append(
        f"Ramp rates follow from the amplitude span of {span:.3g} mA and the transition durations: "
        f"{span / up_s:.4g} mA/s upward over {up_s:.4g} s and {span / down_s:.4g} mA/s downward "
        f"over {down_s:.4g} s.")

    if saturated:
        parts.append(
            f"SATURATED: the amplitude sat at a limit for {(at_low + at_high) * 100:.1f} percent of "
            f"the replay ({at_low * 100:.1f} percent at the low limit, {at_high * 100:.1f} percent "
            f"at the high limit), at or above the {sat_frac * 100:.0f} percent line this module "
            "declares as saturation. A controller in that state is a two-position switch rather "
            "than a regulator, and its mean amplitude will look like a reasonable intermediate "
            "setting while almost none of the record was spent there. Report the pinned fractions "
            "with any mean amplitude taken from this result.")
    else:
        parts.append(
            f"Not saturated by this module's declared line: the amplitude sat at a limit for "
            f"{(at_low + at_high) * 100:.1f} percent of the replay, below the "
            f"{sat_frac * 100:.0f} percent threshold. The controller made {n_transitions} "
            "confirmed state changes.")

    if n_transitions == 0:
        parts.append(
            "The controller never confirmed a threshold crossing, so the amplitude never left its "
            "starting value. That is a statement about the thresholds relative to the observed "
            "power distribution, not about the controller: thresholds outside the range the power "
            "actually visited produce exactly this result.")

    if input_finer:
        parts.append(
            f"The input was averaged onto the device's own grid before the replay: {n_per_window} "
            f"input samples at {dt_raw:.4g} s per non-overlapping {averaging_s:.4g} s averaging "
            "window (rule D14), giving a controller step of "
            f"{dt:.4g} s. The returned series is on that controller grid, because the controller "
            "cannot act more often than once per averaging window.")
    else:
        parts.append(
            f"The input sample interval of {dt_raw:.4g} s is at or coarser than the "
            f"{averaging_s:.4g} s averaging duration, so no averaging was applied and each input "
            "sample is one controller step. The effective averaging of this replay is therefore "
            "the input's own resolution rather than the device's, and behaviour within a window "
            "cannot be reproduced from data that does not resolve it.")

    if n_missing:
        parts.append(
            f"{n_missing} of {n} controller steps had no power estimate. A missing estimate is not "
            "a crossing, and the amplitude was held across it rather than continuing an "
            "in-progress ramp, because no supplied document states what the device does with a "
            "dropped estimate.")

    if scale != "linear":
        parts.append(
            f"The plan's thresholds are on the '{scale}' scale. This routine does not convert "
            "scales; the power series must already be on the same one, and a mismatch would place "
            "every crossing in the wrong place while still producing a plausible-looking "
            "trajectory.")

    parts.append(
        "The amplitude trajectory is continuous. The clinician programs amplitude in 0.1 mA "
        "increments, but no supplied document states whether the adaptive ramp advances on that "
        "grid, so this is the commanded amplitude rather than a quantised delivered one.")

    return " ".join(parts)


# --------------------------------------------------------------------------------------------
# SEGMENT-WISE REPLAY OVER A GAPPY CHRONIC RECORD
# --------------------------------------------------------------------------------------------
#: Minimum controller steps a contiguous segment must contain to be replayed. A segment shorter
#: than this cannot exercise the control law meaningfully — with the device's transition durations
#: measured in minutes, a handful of steps cannot move the amplitude far enough for the resulting
#: time-at-limit fractions to mean anything, and including such segments would let a few noisy
#: fragments dominate an average. Declared by this module, not by Medtronic.
MIN_SEGMENT_STEPS = 3

#: A gap larger than this multiple of the median sample interval starts a new segment.
SEGMENT_GAP_FACTOR = 3.0


def dual_threshold_segments(t_s, power, plan, params=None, *,
                            min_segment_steps=MIN_SEGMENT_STEPS,
                            gap_factor=SEGMENT_GAP_FACTOR):
    """Replay the controller over each CONTIGUOUS stretch of a gappy record, then aggregate.

    WHY THIS EXISTS RATHER THAN A LOOSER TOLERANCE IN ``dual_threshold``. That function refuses a
    non-uniform sample interval, and it is right to: the controller advances its ramp by a rate
    times an interval, so feeding it a series whose interval jumps would silently attribute a
    month-long recording gap to the ramp and march the amplitude to a limit that nothing in the
    data supports. On the real RCS08 record the largest departure from the median interval is over
    a million percent, because a chronic Percept record is a series of short streaming bursts
    separated by days.

    Loosening the tolerance would convert a correct refusal into a wrong number. Splitting the
    record at its gaps keeps the refusal intact and asks a question that is actually answerable:
    what would the control law have done during each stretch when the signal was genuinely being
    observed? The amplitude is treated as re-initialised at the start of each segment, which is
    also what the device does in practice — the adaptive startup delay exists precisely because
    the controller resumes from a known amplitude rather than from wherever it left off days
    earlier.

    WHAT THE AGGREGATE MEANS, AND WHAT IT DOES NOT. The returned fractions are weighted by the
    number of controller steps in each segment, so they describe the time the controller spent at
    each limit DURING OBSERVED STRETCHES. They are not fractions of the patient's day: the
    unobserved gaps are not represented at all, and they are not missing at random, because
    streaming happens when the participant or the clinic starts it. ``coverage_frac`` on the
    result records how little of the elapsed span contributed, so the number cannot be quoted
    without it.

    Returns a ``types.ReplayResult`` whose ``params`` carries the segmentation record.
    """
    t = np.asarray(t_s, float).ravel()
    p = np.asarray(power, float).ravel()
    if t.size != p.size:
        raise ValueError(f"time and power differ in length: {t.size} vs {p.size}")
    ok = np.isfinite(t) & np.isfinite(p)
    t, p = t[ok], p[ok]
    order = np.argsort(t, kind="stable")
    t, p = t[order], p[order]

    # Collapse duplicated timestamps rather than letting them appear as zero-length intervals.
    if t.size and np.any(np.diff(t) == 0):
        uniq, idx = np.unique(t, return_inverse=True)
        summed = np.zeros(uniq.size); counts = np.zeros(uniq.size)
        np.add.at(summed, idx, p); np.add.at(counts, idx, 1.0)
        t, p = uniq, summed / np.maximum(counts, 1.0)

    if t.size < min_segment_steps:
        return types.ReplayResult(
            t_s=None, state=None, frac_time_at_upper=None, frac_time_at_lower=None,
            n_transitions=None, saturated=None,
            params={"n_segments": 0, "reason": "too few samples"},
            note=(f"only {t.size} distinct samples, fewer than the {min_segment_steps} steps a "
                  f"segment must contain to exercise the control law, so no replay was run."))

    gaps = np.diff(t)
    med = float(np.median(gaps[gaps > 0])) if np.any(gaps > 0) else None
    if med is None or not (med > 0):
        return types.ReplayResult(
            t_s=None, state=None, frac_time_at_upper=None, frac_time_at_lower=None,
            n_transitions=None, saturated=None, params={"n_segments": 0},
            note="the time base has no positive interval, so no replay was run.")
    # CAN THIS RECORD REPRESENT THE DEVICE'S RAMP AT ALL? This is checked before any segmentation,
    # because it is a property of the sampling cadence rather than of any individual segment, and
    # because failing it makes every downstream number meaningless in a way that is easy to miss.
    #
    # The device moves the amplitude gradually: the transition-up duration is 2.5 minutes and the
    # transition-down duration 5 minutes by default. A replay advances the ramp by a rate times the
    # sample interval, so if the samples arrive FARTHER APART than the transition duration, one
    # step of the replay traverses the entire amplitude range. The simulated controller then jumps
    # between the two limits instantaneously, which is not the control law the device implements —
    # it is a bang-bang controller with the same thresholds. Every time-at-limit fraction computed
    # that way describes an amplitude trajectory the device would never produce.
    #
    # On the real RCS08 record the chronic snapshots arrive every 230 s while the transition-up
    # duration is 150 s, so this is not a hypothetical: the whole record fails this check, and the
    # honest report is that the ramp is unresolvable at this cadence rather than a set of fractions
    # from a controller that does not exist. Denser data is what fixes it — a streaming session
    # sampled at the device's own averaging rate rather than chronic snapshots minutes apart.
    p_in = dict(DEFAULT_PARAMS)
    if params:
        p_in.update({k: v for k, v in params.items() if k in DEFAULT_PARAMS})
    ramp_up_s = float(p_in["transition_up_ms"]) / 1000.0
    if med >= ramp_up_s:
        return types.ReplayResult(
            t_s=None, state=None, frac_time_at_upper=None, frac_time_at_lower=None,
            n_transitions=None, saturated=None,
            params={"n_segments": None, "n_segments_used": 0, "median_interval_s": med,
                    "transition_up_s": ramp_up_s, "ramp_resolvable": False},
            note=(f"THE RAMP IS NOT RESOLVABLE AT THIS SAMPLING CADENCE, so no replay was run and "
                  f"no time-at-limit fraction is reported. The samples arrive every {med:.0f} s "
                  f"while the transition-up duration is {ramp_up_s:.0f} s, so a single replay step "
                  f"would carry the amplitude across the whole range and the simulated controller "
                  f"would jump between the two limits instantaneously. That is a bang-bang "
                  f"controller, not the gradual ramp the device implements, and its time-at-limit "
                  f"fractions would describe a trajectory the device would never produce. "
                  f"Answering this question needs data sampled at the device's own averaging rate "
                  f"during a streaming session, not chronic snapshots minutes apart."))

    cut = np.flatnonzero(gaps > gap_factor * med) + 1
    bounds = np.concatenate([[0], cut, [t.size]])

    used_steps = 0
    tot_up = tot_lo = 0.0
    n_trans = 0
    n_sat = 0
    n_used = 0
    skipped = 0
    for a, b in zip(bounds[:-1], bounds[1:]):
        if b - a < min_segment_steps:
            skipped += 1
            continue
        seg_t, seg_p = t[a:b] - t[a], p[a:b]
        try:
            r = dual_threshold({"t_s": seg_t, "power": seg_p}, plan, params)
        except Exception:
            # A segment the controller still refuses is skipped and counted rather than allowed to
            # abort the aggregate; the count is reported so the reader knows it happened.
            skipped += 1
            continue
        w = float(b - a)
        if r.frac_time_at_upper is not None:
            tot_up += w * float(r.frac_time_at_upper)
        if r.frac_time_at_lower is not None:
            tot_lo += w * float(r.frac_time_at_lower)
        n_trans += int(r.n_transitions or 0)
        n_sat += 1 if r.saturated else 0
        used_steps += w
        n_used += 1

    if not used_steps:
        return types.ReplayResult(
            t_s=None, state=None, frac_time_at_upper=None, frac_time_at_lower=None,
            n_transitions=None, saturated=None,
            params={"n_segments": int(bounds.size - 1), "n_segments_used": 0,
                    "n_segments_skipped": int(skipped), "median_interval_s": med},
            note=(f"the record splits into {bounds.size - 1} contiguous segments at gaps larger "
                  f"than {gap_factor:g} times the median interval of {med:.1f} s, and none of them "
                  f"contains the {min_segment_steps} steps a replay needs. Nothing was replayed, "
                  f"which is reported rather than substituted with a whole-record replay that "
                  f"would have attributed the gaps to the controller's ramp."))

    span = float(t[-1] - t[0])
    observed = float(used_steps) * med
    return types.ReplayResult(
        t_s=None, state=None,
        frac_time_at_upper=tot_up / used_steps,
        frac_time_at_lower=tot_lo / used_steps,
        n_transitions=int(n_trans),
        saturated=bool(n_sat),
        params={"n_segments": int(bounds.size - 1), "n_segments_used": int(n_used),
                "n_segments_skipped": int(skipped), "steps_used": int(used_steps),
                "median_interval_s": med, "span_s": span,
                "coverage_frac": (observed / span) if span > 0 else None,
                "ramp_resolvable": True, "transition_up_s": ramp_up_s,
                "amp_low_mA": getattr(plan, "capture_amp_low", None),
                "amp_high_mA": getattr(plan, "capture_amp_high", None)},
        note=(f"Aggregated over {n_used} contiguous segments ({skipped} skipped for holding fewer "
              f"than {min_segment_steps} steps), weighted by the number of controller steps in "
              f"each. The record was split at gaps larger than {gap_factor:g} times the median "
              f"interval of {med:.1f} s, because the whole-record replay is correctly REFUSED on "
              f"a series whose interval jumps by six orders of magnitude — feeding it through "
              f"would attribute recording gaps to the controller's ramp. These fractions therefore "
              f"describe observed stretches and are NOT fractions of the patient's day: the gaps "
              f"are unrepresented and are not missing at random, since streaming starts when the "
              f"participant or the clinic starts it. The underlying power was also recorded under "
              f"the participant's actual programming rather than under closed-loop control."))
