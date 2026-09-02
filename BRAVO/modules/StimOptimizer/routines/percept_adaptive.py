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
