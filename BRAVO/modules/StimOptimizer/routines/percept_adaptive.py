"""Device constraints for Percept RC/PC Adaptive Therapy (closed-loop DBS).

EVERY NUMBER IN THIS FILE IS QUOTED FROM THE DEVICE WHITE PAPER, NOT INFERRED.
Source: Medtronic, "Percept(TM) RC and PC Neurostimulator with BrainSense(TM) Technology and
Adaptive Therapy", doc id UC202012929dEN, FY25 (in project artifacts as
``Medtronic_PerceptAdaptive_WhitePaper_032025.pdf``). Page numbers below are the printed page
numbers in that document. Nothing here may be changed without a quote from the labelling; a closed-
loop stimulator's timing and range limits are safety-relevant and must not be guessed at.

WHY THIS MODULE EXISTS
----------------------
Everything the optimizer has done so far assumes OPEN-LOOP therapy: choose a fixed (frequency,
amplitude) and leave it. Adaptive Therapy is a different decision problem. The clinician does not
choose an amplitude; they choose a CONTROL POLICY, and the device moves amplitude within limits in
response to a sensed LFP band. The free parameters become:

    * threshold mode (Dual / Single; Single Inverse is Sensing-Only and cannot drive therapy)
    * the sensing channel and the LFP band
    * the LFP threshold(s) - set manually for Dual, or DERIVED for Single by the device
    * the adaptive amplitude limits (min, max) and the paused amplitude
    * transition durations up and down
    * onset duration, detection blanking duration, adaptive startup delay

THE CONSTRAINT THAT REFRAMES THE BIOMARKER WORK
-----------------------------------------------
``ADAPTIVE_LFP_BAND_HZ = (8.0, 30.0)``. Adaptive Therapy can only be driven by an LFP band inside
8-30 Hz; the wider 1-96 Hz range is **Sensing Only**, meaning the signal can be recorded but a change
in it will not change stimulation. A band selected outside 8-30 Hz is therefore not deployable as a
closed-loop control signal on this device, however well it correlates with pain. The band-search cap
used by the exploration scan is an upper bound only and does not express this; a closed-loop
candidate must satisfy BOTH bounds.
"""
from __future__ import annotations

import numpy as np

from dataclasses import dataclass

# ---------------------------------------------------------------------------------------------
# Threshold modes (white paper pp. 14-15)
# ---------------------------------------------------------------------------------------------
# Dual Threshold: "When the LFP passes above the upper threshold, the stimulation amplitude slowly
#   ramps up. When the LFP passes below the lower threshold, the stimulation amplitude slowly ramps
#   down. When the LFP remains between the thresholds, the stimulation is held constant at the value
#   it was when the LFP entered the state between thresholds." Reaction "by default on the order of
#   minutes".
# Single Threshold: reaction "by default on the order of milliseconds", tracking one threshold.
# Single Threshold Inverse: higher LFP -> higher amplitude (e.g. Gamma), and is "only available in a
#   Sensing Only configuration, meaning a change in LFP will not [change stimulation]".
DUAL = "dual"
SINGLE = "single"
SINGLE_INVERSE = "single_inverse"

# ---------------------------------------------------------------------------------------------
# ELIGIBILITY: RCS08 IS PROGRAMMED IN PARKINSON'S MODE, SO THE FULL WORKFLOW IS AVAILABLE
# ---------------------------------------------------------------------------------------------
#: PI decision, 2026-09-03: this participant is programmed in Parkinson's mode, so the workflow
#: restriction below does not bind and Adaptive Therapy can be enabled. The closed-loop deliverable
#: is a PROGRAMMABLE configuration, not a prepared non-executable one.
#:
#: The restriction is retained here, quoted rather than paraphrased, because it still governs what a
#: participant programmed in a non-Parkinson's mode could do, and because a future reader needs to
#: know which of the two situations they are in. White paper (UC202012929dEN) p. 13:
#:
#:   "Non-Parkinson's patients are defaulted to the Dual Threshold mode for chronic sensing
#:    capabilities and are not allowed to continue the workflow past the thresholds capture step."
#:
#: p. 9 adds that such patients "do not have the ability to choose the Threshold mode".
#:
#: Selecting Parkinson's mode is the PI's clinical and regulatory determination under their own
#: protocol. It is recorded here as a configuration fact, not as anything this module validated, and
#: nothing downstream should present it as an engineering conclusion.
ADAPTIVE_ENABLE_REQUIRES_PD_INDICATION = False   # RCS08 is programmed in Parkinson's mode
NON_PD_WORKFLOW_CEILING = "thresholds capture"   # applies only to a non-Parkinson's-mode participant

#: WHAT PARKINSON'S MODE DOES *NOT* CHANGE, checked because it looked like it might.
#: Parkinson's mode also unlocks the CHOICE of threshold mode rather than forcing Dual Threshold,
#: which raised a real question: the deployability screen refuses a band whose power RISES with
#: amplitude, and an "inverse" control law would be exactly what such a band needs. If a selectable
#: inverse mode could drive therapy, the cells refused on sign would come back.
#:
#: It cannot. Of the three modes, the two that can drive therapy (Dual and Single) BOTH declare the
#: same expected direction — the LFP must be suppressed when stimulation is High — and Single
#: Threshold Inverse, the one whose law runs the other way, is "only available in a Sensing Only
#: configuration, meaning a change in LFP will not [change stimulation]". See MODES below, where
#: SINGLE_INVERSE carries can_drive_therapy=False for that reason.
#:
#: So the negative-slope requirement in lfp_evidence.screen_cells is unaffected by the mode change,
#: and the cells refused for a positive confound-adjusted slope stay refused.
SIGN_REQUIREMENT_HOLDS_IN_EVERY_THERAPY_DRIVING_MODE = True

# ---------------------------------------------------------------------------------------------
# WHAT THE DUAL THRESHOLD CONTROL LAW ASSUMES ABOUT THE SIGN
# ---------------------------------------------------------------------------------------------
#: White paper p. 13: "High LFP is associated with lower stimulation and lower LFP is associated
#: with higher stimulation... When the LFP passes above the upper threshold, the stimulation
#: amplitude slowly ramps up. When the LFP passes below the lower threshold, the stimulation
#: amplitude slowly ramps down."
#:
#: So the control law HARD-CODES the assumption that band power falls as amplitude rises. It is not
#: a modelling preference. If a band's power RISES with amplitude, the device's response to high LFP
#: (ramp amplitude up) drives the band further up, which calls for more amplitude again — positive
#: feedback bounded only by the clinician's amplitude limits. That is why the deployability screen
#: requires the sign of the CONFOUND-ADJUSTED slope to be negative and not merely significant.
DUAL_THRESHOLD_ASSUMES_POWER_FALLS_WITH_AMPLITUDE = True

# ---------------------------------------------------------------------------------------------
# TIMING: THE RAMP IS A KNOB, AND THE AVERAGING WINDOW SHOULD MATCH THE BIOMARKER
# ---------------------------------------------------------------------------------------------
#: PI direction, 2026-09-03. The 2.5-minute and 5-minute transition durations are ADJUSTABLE, so
#: they are parameters this module chooses rather than device behaviour it must model. The policy
#: that follows from that: do not try to model what the band does during a ramp — blank the ramp
#: out and rely on the settled state — but choose the ramp and the blanking from the biomarker's own
#: integration window rather than by taste.
#:
#: WHY THE INTEGRATION WINDOW SETS THE FLOOR. After an amplitude step the band-power estimate still
#: contains pre-step signal until the estimator's window has fully turned over. Device averaging is
#: non-overlapping (`D14`), so one averaging duration is the minimum for the estimate to be free of
#: the old state, and the ramp itself must finish first. Blanking for less than
#: ramp + averaging guarantees the controller acts on a mixture of the old and new states.
#: `SETTLE_WINDOWS` is the multiple applied for margin and is a declared choice, not a measurement.
SETTLE_WINDOWS = 2.0

#: The biomarker's FFT integration, from the Biomarkers pipeline: Welch with nperseg <= 1024 at the
#: 250 Hz time-domain rate, so 1024 / 250 = 4.096 s. This is the quantity every validated
#: pain-band association in this project was computed on.
BIOMARKER_WELCH_NPERSEG = 1024
BIOMARKER_INTEGRATION_S = BIOMARKER_WELCH_NPERSEG / 250.0

#: Manufacturer titration ramp interval, adjustable 0.5-10 s (`D50`, A610 p. 45), with 30-45 s of
#: streaming after each step. This is the window inside which an empirically chosen ramp must fall,
#: and the procedure that would measure the biomarker's response latency directly.
TITRATION_RAMP_RANGE_S = (0.5, 10.0)
TITRATION_SETTLE_RANGE_S = (30.0, 45.0)

#: Published adjustable range for the onset duration in Dual Threshold mode, from the ADAPT-PD
#: methodology paper rather than the device labelling (`D21`, Stanslaski et al. 2024). Medtronic
#: prints only the 1200 ms default. Ranges for averaging duration, detection blanking and the two
#: transition durations are NOT published anywhere supplied and must be read off the Advanced
#: Settings screens before any of the recommendations below can be programmed.
ONSET_RANGE_DUAL_MS = (1200.0, 2000.0)
UNPUBLISHED_RANGES = ("averaging duration", "detection blanking duration",
                      "transition up duration", "transition down duration")


def timing_plan(*, mode=None, biomarker_integration_s=BIOMARKER_INTEGRATION_S,
                ramp_s=None, settle_windows=SETTLE_WINDOWS, measured_latency_s=None):
    """Closed-loop timing parameters derived from the biomarker's own integration window.

    Returns the averaging duration the device SHOULD use, the ramp to program, how long to blank
    after a step, and — separately and explicitly reported, because it is the number most easily
    lost — the averaging window the biomarker was actually validated on.

    ``ramp_s`` defaults to the measured biomarker response latency when one has been supplied, and
    otherwise to the integration window clamped into the manufacturer's 0.5-10 s titration range.
    Defaulting to the integration window is the conservative choice: ramping faster than the
    estimator can follow produces a controller acting on stale power, and the honest way to shorten
    it is to MEASURE the latency, not to assume it.

    ``measured_latency_s`` is the empirical quantity — how long the band actually takes to reach its
    new level after a step. Until the titration of `D50` is run it is None, and the returned plan
    says so rather than implying the ramp was chosen from data.
    """
    spec = MODES.get(mode or DUAL)
    if spec is None:
        raise ValueError(f"unknown mode {mode!r}; expected one of {sorted(MODES)}")
    integ = float(biomarker_integration_s)
    if integ <= 0:
        raise ValueError("biomarker_integration_s must be positive")

    lat = None if measured_latency_s is None else float(measured_latency_s)
    chosen_ramp = float(ramp_s) if ramp_s is not None else (lat if lat is not None else integ)
    lo, hi = TITRATION_RAMP_RANGE_S
    ramp_clamped = min(max(chosen_ramp, lo), hi)

    # The device's averaging should match what the biomarker was validated on. It currently does not:
    # Dual Threshold defaults to 1200 ms against a 4096 ms integration window.
    want_avg_ms = integ * 1000.0
    dev_avg_ms = float(spec.averaging_duration_ms)
    settle_s = ramp_clamped + settle_windows * (want_avg_ms / 1000.0)

    notes = []
    if abs(want_avg_ms - dev_avg_ms) > 1.0:
        notes.append(
            f"device averaging duration defaults to {dev_avg_ms:.0f} ms but the biomarker was "
            f"validated on a {want_avg_ms:.0f} ms integration window, a factor of "
            f"{want_avg_ms / dev_avg_ms:.1f}. The adjustable range is not published in any supplied "
            "document, so whether the device can be set this long must be read off the Advanced "
            "Settings screen. If it cannot, the deployed feature is NOT the validated feature and "
            "the band should be revalidated at the achievable averaging duration.")
    if ramp_clamped != chosen_ramp:
        notes.append(f"requested ramp {chosen_ramp:.2f} s clamped into the manufacturer's "
                     f"{lo:g}-{hi:g} s titration range (D50)")
    if lat is None:
        notes.append("ramp is NOT empirically grounded: no biomarker response latency has been "
                     "measured. Run the D50 titration (0 mA for 45-60 s, then 0.1-0.5 mA steps, "
                     "streaming 30-45 s per step) and pass measured_latency_s.")
    onset_lo, onset_hi = ONSET_RANGE_DUAL_MS
    onset_ms = min(max(float(spec.onset_duration_ms or onset_lo), onset_lo), onset_hi)

    return {
        "mode": spec.mode,
        # reported separately and by name, because it is the parameter that silently differs
        "biomarker_averaging_window_s": round(integ, 4),
        "recommended_device_averaging_ms": round(want_avg_ms, 1),
        "device_default_averaging_ms": dev_avg_ms,
        "averaging_matches_biomarker": bool(abs(want_avg_ms - dev_avg_ms) <= 1.0),
        "ramp_s": round(ramp_clamped, 3),
        "ramp_is_empirical": lat is not None,
        "measured_latency_s": lat,
        "blank_after_step_s": round(settle_s, 3),
        "settle_windows": float(settle_windows),
        "onset_duration_ms": onset_ms,
        "onset_range_ms": list(ONSET_RANGE_DUAL_MS),
        "detection_blanking_default_ms": spec.detection_blanking_ms,
        "transition_up_ms": spec.transition_up_ms,
        "transition_down_ms": spec.transition_down_ms,
        "ranges_unpublished": list(UNPUBLISHED_RANGES),
        "notes": notes,
    }


def estimate_response_latency(times_s, band_power, amp_mA, *, step_index=None, frac=0.632):
    """Time for the band to reach `frac` of its total change after an amplitude step.

    This is the measurement that would let `timing_plan` stop guessing. `frac` defaults to 0.632,
    the first-order time constant, so the returned number is tau rather than a time-to-plateau and
    is comparable across steps of different size.

    Returns None when there is no usable step or the band does not move, which is itself the
    finding: a band with no measurable latency after an amplitude step is not being driven by that
    step. Deliberately assumption-light — no model is fitted — because with one titration session
    the honest output is a descriptive latency, not a fitted system.
    """
    t = np.asarray(times_s, dtype=float)
    p = np.asarray(band_power, dtype=float)
    a = np.asarray(amp_mA, dtype=float)
    if t.size < 4 or not (t.size == p.size == a.size):
        return None
    d = np.diff(a)
    idx = int(np.nanargmax(np.abs(d))) if step_index is None else int(step_index)
    if not np.isfinite(d[idx]) or d[idx] == 0:
        return None
    pre = p[:idx + 1][np.isfinite(p[:idx + 1])]
    post = p[idx + 1:][np.isfinite(p[idx + 1:])]
    if pre.size < 2 or post.size < 2:
        return None
    p0, p1 = float(np.median(pre)), float(np.median(post[-max(2, post.size // 3):]))
    if not np.isfinite(p0) or not np.isfinite(p1) or p1 == p0:
        return None
    target = p0 + frac * (p1 - p0)
    t_step = float(t[idx])
    for tt, pp in zip(t[idx + 1:], p[idx + 1:]):
        if not np.isfinite(pp):
            continue
        if (p1 > p0 and pp >= target) or (p1 < p0 and pp <= target):
            return float(tt - t_step)
    return None


#: Adaptive Therapy can be driven by a band in this range only. Outside it, sensing is possible but
#: therapy cannot respond. White paper p. 14 parameter table, "LFP Frequency Range":
#: "8-30Hz (Adaptive) / 1-96Hz (Sensing Only)".
ADAPTIVE_LFP_BAND_HZ = (8.0, 30.0)
#: The wider range available when only recording.
SENSING_ONLY_LFP_BAND_HZ = (1.0, 96.0)

# ---------------------------------------------------------------------------------------------
# STIMULATION RATE FLOOR FOR CLOSED LOOP
# ---------------------------------------------------------------------------------------------
#: Minimum stimulation rate for a group configured with Adaptive Therapy.
#:
#: PROVENANCE, stated precisely because it differs from everything else in this file. The A610
#: Clinician Programming Guide (M066414C001 Rev B) states the CONSTRAINT and its DIRECTION but does
#: not print the number on the pages reviewed:
#:   "For a group configured with Adaptive Therapy, maximum pulse width and maximum rate are lower
#:    than a group without Adaptive Therapy configured. Minimum rate is HIGHER than a group without
#:    Adaptive Therapy." (p. 35; the same statement appears for BrainSense on p. 34)
#: The VALUE of 55 Hz is PI-stated ("when we deploy closed-loop it needs to meet the minimum
#: frequency of 55 Hz; the machine doesn't work below that"), and is consistent with the labelling's
#: stated direction. It is recorded as a PI-supplied number rather than a quoted one; if the exact
#: figure is later found in the labelling, replace this note with the quote.
MIN_ADAPTIVE_RATE_HZ = 55.0

#: Open-loop interleaving caps, recorded for completeness (manual p. 29): interleaving "cannot
#: exceed 125 hertz per program, or 250 hertz per hemisphere". Interleaving is NOT available in a
#: group with BrainSense or Adaptive Therapy and must be removed before configuring them.
INTERLEAVE_MAX_RATE_PER_PROGRAM_HZ = 125.0
INTERLEAVE_MAX_RATE_PER_HEMISPHERE_HZ = 250.0

# ---------------------------------------------------------------------------------------------
# CONFIGURATION LOCKS AND EXCLUSIONS (manual pp. 34-35)
# ---------------------------------------------------------------------------------------------
#: "Pulse width and rate cannot be adjusted once BrainSense has been set up for either hemisphere."
#: To change them, BrainSense must be REMOVED from the group. This is the single most important
#: sequencing fact for this project: the open-loop search over (rate, pulse width, amplitude) must
#: be FINISHED before closed loop is configured, because closed loop then adapts amplitude only and
#: freezes the other two.
RATE_AND_PW_FROZEN_ONCE_BRAINSENSE_CONFIGURED = True

#: Features that cannot coexist with BrainSense / Adaptive Therapy in one group (manual pp. 34-35).
ADAPTIVE_EXCLUSIONS = (
    "interleaving (must be removed before configuring BrainSense)",
    "multiple rates within the group",
    "cycling (not available with Adaptive Therapy)",
    "a hemisphere with a pocket adaptor",
    "patient-adjustable amplitude limits (Adaptive uses its own limits from BrainSense Setup and "
    "they are not patient-adjustable)",
)

#: Conditions under which the device disables BrainSense automatically (manual p. 34): MRI mode,
#: recharging, and during an impedance test. A closed-loop plan must assume these interruptions.
BRAINSENSE_AUTO_DISABLED_DURING = ("MRI mode", "recharging", "impedance test")

# ---------------------------------------------------------------------------------------------
# INDICATION AND HARDWARE ELIGIBILITY (manual p. 35) -- READ BEFORE PLANNING A DEPLOYMENT
# ---------------------------------------------------------------------------------------------
#: "Adaptive Therapy is a therapy option for the Parkinson's disease indication in patients who have
#: a single Percept neurostimulator." Chronic pain is therefore an OFF-LABEL indication for Adaptive
#: Therapy, which is a regulatory and IRB matter, not something this module can resolve.
ADAPTIVE_LABELLED_INDICATION = "Parkinson's disease"

#: "Adaptive Therapy has only been studied in patients with a single Percept neurostimulator.
#: Adaptive Therapy should NOT be configured in patients who have two neurostimulators."
#: A bilateral implant using ONE neurostimulator with two leads ("Dual Lead configuration") is
#: supported; TWO neurostimulators is an explicit contraindication.
ADAPTIVE_REQUIRES_SINGLE_NEUROSTIMULATOR = True

#: The control logic assumes the LFP RESPONDS TO STIMULATION AMPLITUDE. Manual p. 35: "Adaptive
#: Therapy relies on LFP signals that respond to stimulation amplitude changes. If a patient's LFP
#: signal does not respond in this way, Adaptive Therapy may not be optimal." In Parkinson's this is
#: the well-characterised alpha-beta suppression with increasing amplitude. For a pain biomarker it
#: is NOT established, and it is a DIFFERENT question from "does this band correlate with pain":
#: a band can track pain perfectly and still be useless as a control signal if stimulation does not
#: move it. The biomarker module currently tests only the pain correlation.
REQUIRES_LFP_RESPONSE_TO_STIMULATION = True

# ---------------------------------------------------------------------------------------------
# THE DEVICE'S BAND-POWER DEFINITION (manual p. 39)
# ---------------------------------------------------------------------------------------------
#: "Captured LFP power ... calculated as the sum of the squared LFP magnitude at each frequency
#: within the selected band, similar to the Area Under the Curve."
#:
#: This matters for threshold transfer. The device thresholds a LINEAR sum of squared magnitude over
#: the band. The biomarker pipeline's feature is log band power (`bp_log`). A threshold learned in
#: log space is not the number the device wants, and a band-power definition that averages rather
#: than sums differs by the bin count. Any threshold handed to the device must be expressed in the
#: device's own units, which means matching this definition exactly, not approximately.
DEVICE_BAND_POWER = "sum of squared LFP magnitude over the band (linear, AUC-like), not log, not mean"


@dataclass(frozen=True)
class ModeSpec:
    """Device defaults for one threshold mode. Values are the white paper's stated defaults, which
    are configurable on the device; they are recorded here as the reference point, not as limits."""

    mode: str
    can_drive_therapy: bool
    lfp_band_hz: tuple
    fft_size_points: int
    fft_update_rate_hz: float
    averaging_duration_ms: float
    onset_duration_ms: float | None
    detection_blanking_ms: float | None
    transition_up_ms: float | None
    transition_down_ms: float | None
    threshold_algorithm: str
    suggested_capture_med_state: str
    expected_direction: str


# White paper p. 14 parameter table. The "(Adaptive)" column is used for modes that can drive
# therapy; Single Inverse carries its Sensing-Only values because it cannot.
MODES = {
    DUAL: ModeSpec(
        mode=DUAL, can_drive_therapy=True, lfp_band_hz=ADAPTIVE_LFP_BAND_HZ,
        fft_size_points=256, fft_update_rate_hz=5.0, averaging_duration_ms=1200.0,
        onset_duration_ms=1200.0, detection_blanking_ms=2000.0,
        transition_up_ms=2.5 * 60_000.0, transition_down_ms=5.0 * 60_000.0,
        threshold_algorithm="manual setting of upper and lower",
        suggested_capture_med_state="off medication",
        expected_direction="when stimulation is High the LFP must be suppressed relative to Low "
                           "(e.g. alpha-beta)"),
    SINGLE: ModeSpec(
        mode=SINGLE, can_drive_therapy=True, lfp_band_hz=ADAPTIVE_LFP_BAND_HZ,
        fft_size_points=64, fft_update_rate_hz=20.0, averaging_duration_ms=100.0,
        onset_duration_ms=200.0, detection_blanking_ms=550.0,
        transition_up_ms=250.0, transition_down_ms=250.0,
        threshold_algorithm="device-calculated: 0.75 * (upper - lower) + lower",
        suggested_capture_med_state="off medication",
        expected_direction="when stimulation is High the LFP must be suppressed relative to Low "
                           "(e.g. alpha-beta)"),
    SINGLE_INVERSE: ModeSpec(
        mode=SINGLE_INVERSE, can_drive_therapy=False, lfp_band_hz=SENSING_ONLY_LFP_BAND_HZ,
        fft_size_points=256, fft_update_rate_hz=2.0, averaging_duration_ms=3000.0,
        onset_duration_ms=None, detection_blanking_ms=None,
        transition_up_ms=None, transition_down_ms=None,
        threshold_algorithm="device-calculated: 0.75 * (upper - lower) + lower",
        suggested_capture_med_state="on medication",
        expected_direction="when stimulation is Low the LFP must be suppressed relative to High "
                           "(e.g. gamma)"),
}

#: Fraction used by the device to derive a single threshold from two captured LFP values
#: (white paper p. 15): "The generated single threshold value is based on 75% of the difference
#: between the two captured values", i.e. threshold = frac * (upper - lower) + lower.
SINGLE_THRESHOLD_FRACTION = 0.75


def derive_single_threshold(lfp_lower, lfp_upper, frac=SINGLE_THRESHOLD_FRACTION):
    """Reproduce the device's single-threshold calculation: ``frac * (upper - lower) + lower``.

    This is NOT a free parameter of ours — it is what the device will compute from the two captured
    LFP values, so any plan that proposes a single-threshold policy must predict the threshold this
    way rather than choosing one. Raises on inverted captures, which the device also refuses: "it is
    possible that the thresholds gathered by the system are either too close together or are
    inverted. In this case, the A610 application will prompt the user to either ... recapture ... or
    select the manual adjustment option." (p. 15)
    """
    lo, hi = float(lfp_lower), float(lfp_upper)
    if not (hi > lo):
        raise ValueError(
            f"inverted or degenerate LFP captures (lower={lo!r}, upper={hi!r}). The device refuses "
            "this and prompts for recapture or manual adjustment; a derived threshold from an "
            "inverted pair is meaningless.")
    return frac * (hi - lo) + lo


def band_is_adaptive_capable(center_hz, band_width_hz):
    """Can a band at this centre/width drive Adaptive Therapy? Returns ``(ok, reason)``.

    The whole band must lie inside ADAPTIVE_LFP_BAND_HZ, not just its centre: a band centred at
    9 Hz with 5 Hz width reaches down to 6.5 Hz and is not adaptive-capable.
    """
    lo_ok, hi_ok = ADAPTIVE_LFP_BAND_HZ
    lo = float(center_hz) - float(band_width_hz) / 2.0
    hi = float(center_hz) + float(band_width_hz) / 2.0
    if lo < lo_ok or hi > hi_ok:
        return False, (
            f"band {lo:.2f}-{hi:.2f} Hz falls outside the adaptive range "
            f"{lo_ok:g}-{hi_ok:g} Hz. It can be SENSED (sensing-only spans "
            f"{SENSING_ONLY_LFP_BAND_HZ[0]:g}-{SENSING_ONLY_LFP_BAND_HZ[1]:g} Hz) but a change in "
            "it cannot drive stimulation on this device, so it is not a deployable closed-loop "
            "control signal however well it correlates with pain.")
    return True, ""


# ---------------------------------------------------------------------------------------------
# Bilateral configuration (white paper p. 17)
# ---------------------------------------------------------------------------------------------
#: "For Dual Lead configurations ... Select the contralateral hemisphere to use the Sensing data
#: from that hemisphere's lead to drive Adaptive Therapy for the selected [hemisphere]."
#: Directly relevant here: this project's left-leg objective disagrees between the two hemispheres,
#: and contralateral drive is a supported configuration rather than something to be worked around.
CONTRALATERAL_DRIVE_SUPPORTED = True


# ---------------------------------------------------------------------------------------------
# Where these live in the exported JSON (white paper, session-report schema section)
# ---------------------------------------------------------------------------------------------
#: ProgramSettings fields carrying adaptive configuration, per the white paper's description of the
#: session-report structure. The existing adapter reads only the open-loop subset (amplitude, rate,
#: pulse width, electrodes); a closed-loop build must additionally read these. Recorded here so the
#: field names are not re-derived by trial and error against the JSON.
ADAPTIVE_JSON_FIELDS = (
    "Thresholds",                    # captured AND manually adjusted
    "SensingFrequency",
    "AveragingDuration",
    "SenseChannelResult",            # for the active channel
    "SensingStatus",
    "AdaptiveTherapyStatus",
    "AdaptiveTherapyMode",
    "AdaptiveTransitionDurations",
    "OnsetDurations",
    "DetectionBlankingDuration",
    "AdaptiveStartupDelay",
    "StimulationLimits",
    "SuspendAmplitude",              # the "Paused" amplitude
    "SensingHemisphere",
)


def validate_policy(policy):
    """Check a proposed closed-loop policy against the device constraints. Returns a list of
    problems; an empty list means nothing in this module objects.

    ``policy`` is a mapping with keys ``mode``, ``center_hz``, ``band_width_hz``, ``amp_min_mA``,
    ``amp_max_mA`` and optionally ``paused_amp_mA``. This deliberately checks only what the
    labelling states. It is NOT a clinical safety review, and it says nothing about whether the
    amplitude limits are tolerable for a given patient — that is what the delivered-amplitude
    envelope and a side-effect record are for.
    """
    problems = []
    mode = policy.get("mode")
    spec = MODES.get(mode)
    if spec is None:
        return [f"unknown threshold mode {mode!r}; expected one of {sorted(MODES)}"]
    if not spec.can_drive_therapy:
        problems.append(
            f"mode {mode!r} is Sensing Only and cannot drive Adaptive Therapy: a change in LFP "
            "will not change stimulation.")

    # Stimulation rate floor. A group configured for Adaptive Therapy has a HIGHER minimum rate
    # than an open-loop group (manual p. 35); the value is PI-supplied. This is a hard gate: a
    # policy below it is not programmable, so an optimizer proposing it is wasting a session.
    rate = policy.get("rate_hz")
    if rate is None:
        problems.append(
            f"rate_hz is required for a closed-loop policy: the adaptive minimum rate "
            f"({MIN_ADAPTIVE_RATE_HZ:g} Hz) is higher than the open-loop minimum, so a rate that "
            "is fine open-loop may not be programmable with Adaptive Therapy.")
    elif float(rate) < MIN_ADAPTIVE_RATE_HZ:
        problems.append(
            f"rate {float(rate):g} Hz is below the adaptive minimum of {MIN_ADAPTIVE_RATE_HZ:g} Hz "
            "and cannot be programmed with Adaptive Therapy. Note this rate may be perfectly "
            "usable OPEN loop — the floor applies to the adaptive configuration.")

    # Hardware eligibility. Two neurostimulators is an explicit contraindication, not a caution.
    n_ins = policy.get("n_neurostimulators")
    if n_ins is not None and int(n_ins) > 1 and ADAPTIVE_REQUIRES_SINGLE_NEUROSTIMULATOR:
        problems.append(
            "Adaptive Therapy must NOT be configured in a patient with two neurostimulators "
            "(manual p. 35: it has only been studied with a single Percept neurostimulator). A "
            "bilateral implant on ONE neurostimulator with two leads is supported; two separate "
            "neurostimulators is not.")

    # The control signal must actually respond to stimulation. This is a DIFFERENT requirement from
    # correlating with the symptom, and it is the one a pain biomarker is least likely to meet.
    if policy.get("lfp_responds_to_stimulation") is not True:
        problems.append(
            "not established that the proposed LFP band RESPONDS TO STIMULATION AMPLITUDE. Adaptive "
            "Therapy relies on that response (manual p. 35); a band that tracks pain but does not "
            "move with amplitude is not a usable control signal. Pass "
            "lfp_responds_to_stimulation=True only when it has been measured, not assumed.")

    if mode == DUAL and policy.get("sensing_hemisphere") not in (None, policy.get("hemisphere")):
        problems.append(
            "in Dual Threshold Mode stimulation is driven by sensing from the SAME hemisphere "
            "unless a contralateral sensing configuration is explicitly set up (manual p. 38). "
            "Set contralateral=True if that configuration is intended.")

    ok, why = band_is_adaptive_capable(policy.get("center_hz", float("nan")),
                                       policy.get("band_width_hz", 0.0))
    if not ok:
        problems.append(why)

    a_lo, a_hi = policy.get("amp_min_mA"), policy.get("amp_max_mA")
    if a_lo is None or a_hi is None:
        problems.append("adaptive amplitude limits are required: the device moves amplitude "
                        "between them and they become the patient limits when the group is "
                        "switched from Adaptive to Sensing Only.")
    elif not (float(a_hi) > float(a_lo)):
        problems.append(f"adaptive amplitude limits must satisfy max > min (got {a_lo}, {a_hi}).")

    paused = policy.get("paused_amp_mA")
    if paused is not None and a_lo is not None and a_hi is not None:
        if not (float(a_lo) <= float(paused) <= float(a_hi)):
            problems.append(
                f"paused amplitude {paused} mA lies outside the adaptive limits "
                f"[{a_lo}, {a_hi}] mA.")
    return problems
