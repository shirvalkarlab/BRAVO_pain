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

WHICH NUMBERS, since 2026-09-12 (PI decision, "b and c"): the two D26 verdicts are judged on the
POOLED TITRATION SLOPE -- band power on current across every run of rising current on the contact,
one baseline per run (decisions 55, 124, 126) -- and they WARN rather than block. The between-visit
separation described in the first paragraph is still computed and reported, labelled as the
comparison decision 124 distrusts, but it no longer decides either verdict. See
``d26_capture_verdicts``.
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
#: IMPORTED, NOT RESTATED (review C10, 2026-09-12), for the same reason as the separation floor
#: above: the two numbers were written here, in ``constraints`` and in ``session_report_facts``,
#: three literals for one rule. Their one home is ``session_report_facts``; ``constraints``
#: re-exports them under these names.
from .constraints import CAPTURE_ARTEFACT_AMP_MA, CAPTURE_ARTEFACT_PW_US   # noqa: E402


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


#: What the two D26 verdicts are judged on since 2026-09-12. Named once so the sentences, the
#: structured field and the tests read one string.
D26_JUDGED_ON = "pooled titration slope (E1, decision 124)"

#: The label the between-visit comparison carries wherever its number is still reported.
D26_HISTORICAL_LABEL = ("between-visit comparison decision 124 distrusts: every band-power sample "
                        "recorded at the lowest therapeutic current on record pooled against every "
                        "sample at the highest, across every visit and month. Reported beside the "
                        "verdicts as a number; it is not the verdict.")


def _fmt_ci_p(edge):
    """'interval -18.6 to +9.7, p 0.54', or what is missing, for a D26 sentence."""
    parts = []
    ci = getattr(edge, "ci", None)
    if ci is not None:
        try:
            parts.append(f"interval {float(ci[0]):+.1f} to {float(ci[1]):+.1f}")
        except (TypeError, ValueError, IndexError):
            parts.append("no interval is available")
    else:
        parts.append("no interval is available")
    p = getattr(edge, "p", None)
    if p is not None and np.isfinite(float(p)):
        parts.append(f"p {float(p):.2f}")
    return ", ".join(parts)


def d26_capture_verdicts(pooled_slope, *, expected_sign=-1, historical_d=None,
                         historical_low_mean=None, historical_high_mean=None):
    """The two D26 verdicts -- "inverted capture" and "thresholds too close" -- judged on the
    POOLED TITRATION SLOPE, and reported as warnings that gate nothing.

    PI decision 2026-09-12, his words "b and c". Until then both verdicts were judged on the
    between-visit comparison this function still receives as ``historical_*``: the mean of every
    sample recorded at the lowest therapeutic current on record against the mean at the highest,
    pooled over every visit and month. Decisions 124 and 126 had already ruled that comparison
    confounded by time and replaced it, as the report's current-to-power edge, with the pooled
    slope across runs of rising current, one baseline per run (``edges.pooled_actuation_edge``).
    On RCS08 at the committed band the two disagreed in sign: the between-visit means read power
    HIGHER at 4.8 mA than at 1.4 mA (196.1 against 190.9, an "inverted capture") while the pooled
    slope reads −4.45 device units per mA, the direction the control law needs. The verdicts now
    read the number the project trusts.

    THE RULE, SINCE 2026-09-13 (PI: "Established means mean only for flexibility", read as "point
    sign decides, but flag as provisional"). BOTH verdicts are judged on the SIGN OF THE POINT
    ESTIMATE. "Inverted" is the pooled slope's sign being wrong for the control law. "Too close"
    is the slope being exactly zero -- no separation between the two captures at all. Whether the
    slope is STATISTICALLY ESTABLISHED (its interval excludes zero) is a CAVEAT: it is printed on
    both sentences with the interval and p, it is carried as ``established`` beside each status,
    and it changes neither status nor the predicted alert. Until that date "too close" was the
    slope not being established, and an unestablished slope raised the predicted alert; that rule
    is kept here on the record. When no pooled slope is stored for the band, both verdicts say
    NOT ASSESSED rather than falling back to the historical comparison silently; the historical
    separation is still reported beside them, labelled as the comparison decision 124 distrusts.

    WHAT COMES BACK. ``(verdicts, warnings, predicted_recapture_alert)``. ``verdicts`` is the
    structured form for the page; ``warnings`` carries the sentence of every verdict that is
    adverse or not assessed, PLUS the caveat sentence of every verdict whose slope is not
    statistically established (a caveat gates nothing, and warnings gate nothing, which is where
    a caveat belongs on the page); it is EMPTY when the slope is established with the right sign.
    ``predicted_recapture_alert`` is True when either verdict is adverse on the point sign, False
    when both are clear, and None when nothing could be assessed -- the same None the field
    carried before when the historical spread could not be measured, because a prediction made
    from no number would be a fabrication.
    """
    hist_inverted = None
    if historical_low_mean is not None and historical_high_mean is not None:
        s = (1 if historical_high_mean > historical_low_mean
             else (-1 if historical_high_mean < historical_low_mean else 0))
        hist_inverted = bool(s != 0 and s != expected_sign)
    historical = {
        "label": D26_HISTORICAL_LABEL,
        "mean_power_at_low_capture": historical_low_mean,
        "mean_power_at_high_capture": historical_high_mean,
        "separation_pooled_sd": historical_d,
        "inverted_by_means": hist_inverted,
        "below_declared_minimum": (None if historical_d is None
                                   else bool(abs(historical_d) < MIN_CAPTURE_SEPARATION_D)),
        "declared_minimum": MIN_CAPTURE_SEPARATION_D,
    }
    est = getattr(pooled_slope, "estimate", None)
    have_slope = est is not None and np.isfinite(float(est))

    if not have_slope:
        tail = ""
        if historical_d is not None:
            tail = (f" For the record only, the between-visit comparison decision 124 distrusts "
                    f"gives a separation of {abs(historical_d):.2f} pooled standard deviations"
                    + (" with power higher at the higher current" if hist_inverted else "")
                    + "; it is not the verdict.")
        inv = ("D26 inverted capture: not assessed -- no pooled titration slope is stored for this "
               "band, so whether power falls as current rises cannot be judged from the runs of "
               "rising current." + tail)
        close = ("D26 thresholds too close: not assessed -- no pooled titration slope is stored for "
                 "this band, so whether the signal's response to current can be told from no "
                 "response is unknown; the device may raise RECAPTURE THRESHOLDS." + tail)
        verdicts = {
            "judged_on": None, "assessed": False,
            "pooled_slope_per_mA": None, "pooled_slope_ci": None, "pooled_slope_p": None,
            "pooled_slope_established": None,
            "inverted": {"status": "not assessed", "established": None, "sentence": inv},
            "too_close": {"status": "not assessed", "established": None, "sentence": close},
            "historical": historical,
        }
        return verdicts, [inv, close], None

    b = float(est)
    sign = getattr(pooled_slope, "sign", None)
    # The CAVEAT flag, not the verdict (PI rule 2026-09-13): does the interval exclude zero?
    established = bool(getattr(pooled_slope, "statistically_established", False))
    unit = ("device units per mA" if str(getattr(pooled_slope, "scale", "linear")).endswith("linear")
            else "units of log power per mA")
    ci_p = _fmt_ci_p(pooled_slope)
    if sign is not None and sign < 0:
        direction = "power falls as current rises"
    elif sign is not None and sign > 0:
        direction = "power rises as current rises"
    else:
        direction = "power does not change with current"
    inverted = bool(sign is not None and sign != 0 and sign != expected_sign)
    # "Too close" on the point estimate: a slope of exactly zero separates nothing.
    too_close = bool(sign == 0)
    needs = ("as the control law needs" if not inverted and sign != 0
             else "the opposite of what the control law assumes")
    caveat = ("" if established else
              f" CAVEAT: the interval spans zero ({ci_p}), so this rests on the point estimate "
              "alone; the sign is not statistically established.")
    if inverted:
        inv = (f"D26 inverted capture: INDICATED -- the pooled titration slope is {b:+.2f} {unit} "
               f"({direction}, {needs}; {ci_p}), so the device would drive the loop the wrong way. "
               f"This is the condition the programmer reports as an inverted capture.{caveat}")
    else:
        inv = (f"D26 inverted capture: NOT indicated -- the pooled titration slope is {b:+.2f} {unit} "
               f"({direction}, {needs}; {ci_p}).{caveat}")
    if too_close:
        close = (f"D26 thresholds too close: INDICATED -- the pooled titration slope is exactly zero "
                 f"({ci_p}), so the two captures do not separate and the device may raise RECAPTURE "
                 f"THRESHOLDS.{caveat}")
    else:
        close = (f"D26 thresholds too close: NOT indicated -- the pooled titration slope is "
                 f"{b:+.2f} {unit} ({ci_p}), so on the point estimate the two captures separate."
                 + ("" if established else
                    f" CAVEAT: the interval spans zero ({ci_p}), so the signal's response to current "
                    "is not statistically established and the device may still raise RECAPTURE "
                    "THRESHOLDS at the visit; that is a caveat, not the verdict."))
    ci = getattr(pooled_slope, "ci", None)
    verdicts = {
        "judged_on": D26_JUDGED_ON, "assessed": True,
        "pooled_slope_per_mA": b,
        "pooled_slope_ci": None if ci is None else [float(ci[0]), float(ci[1])],
        "pooled_slope_p": getattr(pooled_slope, "p", None),
        "pooled_slope_established": established,
        "inverted": {"status": "indicated" if inverted else "not indicated",
                     "established": established, "sentence": inv},
        "too_close": {"status": "indicated" if too_close else "not indicated",
                      "established": established, "sentence": close},
        "historical": historical,
    }
    warnings = []
    # Adverse verdicts and unestablished caveats both go on the page as warnings (which gate
    # nothing); an established slope with the right sign leaves the list empty.
    if inverted or not established:
        warnings.append(inv)
    if too_close or not established:
        warnings.append(close)
    return verdicts, warnings, bool(inverted or too_close)


def threshold_placement(power_low, power_high, *, amp_low, amp_high, expected_sign=-1,
                        pulse_width_us=None, observed_series=None, pooled_slope=None):
    """Place the two thresholds and predict what the device will report.

    The thresholds are placed at the two capture means, which is what the device does when it
    captures at two amplitudes. The value added here is the set of predictions that come with them:
    whether the capture will be flagged as inverted, whether it will be flagged as too close, how
    much of the time the signal will sit in each of the three control states, and whether the
    capture amplitudes themselves violate the artefact ceiling of D27.

    ``pooled_slope`` is the report's E1 when it is the pooled titration slope (an ``EdgeEstimate``
    from ``edges.pooled_actuation_edge``), or None when no slope is stored. Since 2026-09-12 the
    two D26 verdicts are judged on it and land in ``ThresholdPlan.warnings`` rather than
    ``problems`` -- see ``d26_capture_verdicts``. The two threshold VALUES and the two capture
    amplitudes are computed exactly as before, from the two capture means; only what the two
    verdict sentences are judged on, and where they land, changed.
    """
    problems = []
    d = control_authority(power_low, power_high)
    a = np.asarray(power_low, float); a = a[np.isfinite(a)]
    b = np.asarray(power_high, float); b = b[np.isfinite(b)]
    lo_mean = float(np.mean(a)) if a.size else None
    hi_mean = float(np.mean(b)) if b.size else None

    # The capture THIS MODULE PROPOSES is only valid below the artefact ceiling. This is the same
    # ceiling rule D27 applies, but to a DIFFERENT amplitude: the ledger's D27 row judges the
    # device's own newest capture (3.0 mA on RCS08, decision 136), while the amplitudes here are
    # the lowest and highest therapeutic currents on record for the cell (1.0 and 4.8 mA, decision
    # 139), which are where the thresholds below are read. The sentence therefore names the
    # proposed amplitude and no longer cites "D27" as if it were the ledger row (review C10,
    # 2026-09-12): at 5.5 mA delivered this would have blocked "on D27" while the ledger's D27 row
    # passed on the device's 3.0 mA capture.
    for label, amp in (("lower", amp_low), ("upper", amp_high)):
        if amp is not None and amp > CAPTURE_ARTEFACT_AMP_MA:
            _which = {"lower": "lowest", "upper": "highest"}[label]
            problems.append(
                f"the proposed {label} capture amplitude of {amp:.2f} mA (the {_which} therapeutic "
                f"current on record for this cell) exceeds the {CAPTURE_ARTEFACT_AMP_MA} mA artefact "
                "ceiling, above which stimulation artefact may make the LFP appear elevated during "
                "capture; a threshold read there would partly measure the stimulator. The ledger's "
                "D27 row judges the device's own newest capture, which is a different amplitude.")
    if pulse_width_us is not None and pulse_width_us > CAPTURE_ARTEFACT_PW_US:
        problems.append(
            f"the proposed capture's pulse width {pulse_width_us:.0f} us exceeds the "
            f"{CAPTURE_ARTEFACT_PW_US:.0f} us artefact ceiling, with the same consequence for the capture.")

    # THE TWO D26 VERDICTS READ THE POOLED TITRATION SLOPE AND WARN, since 2026-09-12 (PI: "b and
    # c"). Until then they were judged here on `lo_mean` against `hi_mean` and on `d`, the
    # between-visit comparison decision 124 distrusts, and appended to `problems`, which blocks.
    # Those numbers are still computed above -- the thresholds ARE the two means, and `d` is still
    # reported as `control_authority` -- but they judge nothing now; they travel in the structured
    # verdicts as the historical comparison, labelled as such.
    verdicts, warnings, alert = d26_capture_verdicts(
        pooled_slope, expected_sign=expected_sign, historical_d=d,
        historical_low_mean=lo_mean, historical_high_mean=hi_mean)
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
        predicted_recapture_alert=alert,
        control_authority=d, problems=problems, warnings=warnings, capture_verdicts=verdicts,
        note=("Thresholds are placed at the two capture means, as the device does. Since 2026-09-12 "
              "the two D26 verdicts (inverted capture, thresholds too close) are judged on the "
              "pooled titration slope across runs of rising current, not on the between-visit "
              "comparison of the two capture means, and they warn rather than block. The "
              "separation criterion on that comparison is declared by this module, not published "
              "by the manufacturer, who describes the alert qualitatively as the signal being "
              "minimally responsive."))
