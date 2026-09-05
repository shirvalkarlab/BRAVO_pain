"""Can a threshold actually be placed on this signal, and what will the device do with it?

Control authority is the question the deployability screen does not answer. A band can respond to
amplitude with a statistically clear slope and still be useless, because the slope is small relative
to how much the band wanders on its own. What a threshold controller needs is SEPARATION: the power
at the two capture amplitudes must be far apart compared with the moment-to-moment spread within
each, or the device will cross the threshold constantly on noise.

This is also where the device's own failure modes become predictable before the visit. Rule D26
records that the programmer raises a RECAPTURE THRESHOLDS alert when "the LFP signal is minimally
responsive to changes in stimulation amplitude", and that captures can fail by being "too close
together or inverted". The document's own encoding note observes that both are quantities this
module already estimates: an inverted capture is an amplitude-to-power slope with the wrong sign,
and a too-close capture is a separation that is small relative to the noise. Predicting the alert is
therefore not speculation, it is arithmetic on numbers we have.
"""
from __future__ import annotations

import numpy as np

from .types import ThresholdPlan

#: Separation below which the two captured thresholds should be treated as too close. Expressed in
#: within-state standard deviations, so it is a Cohen's-d-style quantity. This is a DECLARED
#: threshold, not a device-published one: Medtronic documents the alert's existence and its trigger
#: in words ("minimally responsive") but not a numeric criterion, so the module states its own and
#: labels it rather than implying the number came from the manufacturer.
#:
#: IMPORTED RATHER THAN RESTATED, 2026-09-05. This constant was declared here as 1.0 while
#: StimOptimizer's response test declared the SAME criterion as 0.5, and nothing linked them — two
#: independent literals encoding one unpublished manufacturer rule, drifted to a factor of two
#: apart. The consequence was a band that clears the screen and is then called too-close
#: downstream: any cell with d between 0.5 and 1.0 passed `assess_response` and failed
#: `threshold_placement`. That was not hypothetical — on RCS08 at 55 Hz with the five-era window,
#: every band clearing separation sits between 0.51 and 0.93, so all of them fell in the gap.
#:
#: PI decision: use the LOOSER criterion for both. Rather than write 0.5 in two places and invite
#: the same drift again, this module now imports the one definition. If the floor is ever revisited,
#: it moves in a single file.
from StimOptimizer.routines.lfp_response import (        # noqa: E402  (constant, not a cycle)
    MIN_CAPTURE_SEPARATION_D,
)

#: Rule D27 (A610 p. 73): above these values the stimulation artefact "may cause the LFP to appear
#: elevated when capturing the Lower LFP Threshold". This is a measurement-validity ceiling on the
#: CAPTURE procedure specifically, distinct from any therapeutic amplitude limit.
CAPTURE_ARTEFACT_AMP_MA = 5.0
CAPTURE_ARTEFACT_PW_US = 120.0


def control_authority(power_low, power_high):
    """Separation between the power distributions at the two capture amplitudes, in pooled SD.

    Returns None when either sample is too small to have a spread, rather than a large number
    computed from one observation — the most dangerous failure here would be reporting excellent
    authority because a distribution had no measured variance.
    """
    a = np.asarray(power_low, float); a = a[np.isfinite(a)]
    b = np.asarray(power_high, float); b = b[np.isfinite(b)]
    if a.size < 2 or b.size < 2:
        return None
    va, vb = np.var(a, ddof=1), np.var(b, ddof=1)
    pooled = np.sqrt(((a.size - 1) * va + (b.size - 1) * vb) / (a.size + b.size - 2))
    if not np.isfinite(pooled) or pooled == 0:
        return None
    return float((np.mean(b) - np.mean(a)) / pooled)


def threshold_placement(power_low, power_high, *, amp_low, amp_high, expected_sign=-1,
                        pulse_width_us=None, observed_series=None):
    """Place the two thresholds and predict what the device will report.

    The thresholds are placed at the two capture means, which is what the device does when it
    captures at two amplitudes. The value added here is the set of predictions that come with them:
    whether the capture will be flagged as inverted, whether it will be flagged as too close, how
    much of the time the signal will sit in each of the three control states, and whether the
    capture amplitudes themselves violate the artefact ceiling of D27.
    """
    problems = []
    d = control_authority(power_low, power_high)
    a = np.asarray(power_low, float); a = a[np.isfinite(a)]
    b = np.asarray(power_high, float); b = b[np.isfinite(b)]
    lo_mean = float(np.mean(a)) if a.size else None
    hi_mean = float(np.mean(b)) if b.size else None

    # D27: the capture itself is only valid below the artefact ceiling.
    for label, amp in (("lower", amp_low), ("upper", amp_high)):
        if amp is not None and amp > CAPTURE_ARTEFACT_AMP_MA:
            problems.append(
                f"D27: the {label} capture amplitude of {amp:.2f} mA exceeds {CAPTURE_ARTEFACT_AMP_MA} mA, "
                "above which stimulation artefact may make the LFP appear elevated during capture. "
                "The captured threshold would partly measure the stimulator.")
    if pulse_width_us is not None and pulse_width_us > CAPTURE_ARTEFACT_PW_US:
        problems.append(
            f"D27: pulse width {pulse_width_us:.0f} us exceeds {CAPTURE_ARTEFACT_PW_US:.0f} us, with "
            "the same artefact consequence for the capture.")

    inverted = None
    if lo_mean is not None and hi_mean is not None:
        observed_sign = 1 if hi_mean > lo_mean else (-1 if hi_mean < lo_mean else 0)
        inverted = (observed_sign != expected_sign) and observed_sign != 0
        if inverted:
            problems.append(
                "D26 inverted capture: power moves with amplitude in the opposite direction to the "
                "one the control law assumes, so the device would drive the loop the wrong way. "
                "This is the condition the programmer reports as an inverted capture.")
    too_close = (d is not None and abs(d) < MIN_CAPTURE_SEPARATION_D)
    if too_close:
        problems.append(
            f"D26 thresholds too close: separation is {abs(d):.2f} within-state standard deviations, "
            f"below the declared minimum of {MIN_CAPTURE_SEPARATION_D}. The signal is minimally "
            "responsive to amplitude at these settings and the device is likely to raise RECAPTURE "
            "THRESHOLDS.")
    if d is None:
        problems.append("control authority is not estimable: at least one capture has fewer than "
                        "two usable samples, so its spread is unknown.")

    fb = fbet = fab = None
    if observed_series is not None and lo_mean is not None and hi_mean is not None:
        s = np.asarray(observed_series, float); s = s[np.isfinite(s)]
        if s.size:
            up, dn = max(lo_mean, hi_mean), min(lo_mean, hi_mean)
            fb = float(np.mean(s < dn)); fab = float(np.mean(s > up))
            fbet = float(1.0 - fb - fab)

    return ThresholdPlan(
        upper=max(lo_mean, hi_mean) if None not in (lo_mean, hi_mean) else None,
        lower=min(lo_mean, hi_mean) if None not in (lo_mean, hi_mean) else None,
        capture_amp_low=amp_low, capture_amp_high=amp_high,
        frac_time_below=fb, frac_time_between=fbet, frac_time_above=fab,
        predicted_recapture_alert=(bool(inverted) or bool(too_close)) if d is not None else None,
        control_authority=d, problems=problems,
        note=("Thresholds are placed at the two capture means, as the device does. The separation "
              "criterion is declared by this module, not published by the manufacturer, who "
              "describes the alert qualitatively as the signal being minimally responsive."))
