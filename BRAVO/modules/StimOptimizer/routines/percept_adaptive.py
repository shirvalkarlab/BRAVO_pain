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
