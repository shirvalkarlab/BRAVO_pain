"""The Percept device rule table (D01-D51) and the eligibility evaluator that reads it.

WHAT THIS FILE IS FOR
=====================
Every rule below was read out of ``percept_device_constraints.md``, which in turn quotes one of the
Medtronic documents for the Percept neurostimulator family and records the page on which the
sentence appears. Nothing here is inferred from general knowledge of the device. Each rule carries
the document tag and page so that a failed check can name the sentence it violates, which is what a
clinician needs in order to argue with the result rather than merely accept it.

The rules are DATA, not a chain of ``if`` statements, for two reasons that both bit earlier versions
of this work. First, a chain of ifs stops at the first failure, so a clinician who fixes one blocker
has to re-run the whole screen to discover the next one; a table can be evaluated exhaustively.
Second, a chain of ifs has nowhere to record a rule that exists but whose value nobody has read off
the programmer yet, so such rules quietly disappear and the configuration appears to pass. The
``severity`` field exists precisely to keep those rules visible and blocking.

SEVERITY
========
``blocking``
    The rule can be evaluated from the inputs a caller is expected to supply, and a failure
    disqualifies the candidate.
``advisory``
    Worth putting on the face of the report, but it does not disqualify. Two kinds of rule land
    here: statements the documents phrase as a recommendation or a warning rather than a
    prohibition, and statements that constrain a whole GROUP of programs or a whole protocol rather
    than the single candidate configuration this evaluator is handed. The second kind is surfaced
    rather than enforced because this evaluator cannot see the sibling programs; when the caller
    does declare them, the predicate returns a verdict and the advisory carries it.
``unknown``
    The rule exists, the documents state that it exists, and neither document prints its value. It
    BLOCKS. A rule we cannot evaluate must never pass silently, because the failure mode we are
    guarding against is a configuration that looks licensed only because nobody measured the thing
    that would have stopped it. Exactly two rules are in this state today: D04, the number of
    implanted neurostimulators for this participant, and D31, the minimum stimulation rate allowed
    in a group with BrainSense configured. Both are read off the device, not out of a document, and
    section 12 of the constraints file says how.

Note on D03, which is the rule most likely to be misread. D03 is severity ``blocking``, not
``unknown``: the documents are perfectly clear about what it requires, so it is evaluable. For
participant RCS08 it PASSES, because that participant is programmed in Parkinson's mode and the
Adaptive workflow is therefore reachable. It is kept as a blocking rule with a live predicate
because it becomes a failure again the moment the same code is run for a participant programmed in
any other mode, and the report records the observed programming mode as its value so that a reader
can see which regime the rest of the report is written in.

HOW MISSING INPUT IS TREATED
============================
A predicate returns True (the rule is satisfied), False (the rule is violated) or None (not
determinable from the inputs given). Absent keys always produce None, never True. For a blocking or
unknown rule, None lands in ``EligibilityReport.unknowns`` and the candidate is not eligible. This
makes the evaluator deliberately pessimistic in the same way ``types.DeploymentReport.is_licensed``
is deliberately pessimistic, and for the same reason: treating absence of evidence as permission is
the specific error this module exists to prevent. The practical consequence is that a candidate
which passes every rule has to declare rather more than the handful of fields that describe the
band, and ``CANDIDATE_KEYS`` and ``PARTICIPANT_KEYS`` below list every field any predicate reads,
with the rule that reads it, so that a caller can see what is still undeclared.

The report distinguishes the two ways a rule can end up unknown, because they need different
actions. ``kind="value_not_read_off_programmer"`` means the rule's own value is missing from the
documentation and has to be read off the device (D04, D31). ``kind="input_not_supplied"`` means the
rule is fully documented but the caller did not state the fact it needs.
"""
from __future__ import annotations

from . import types

# ------------------------------------------------------------------------------------------------
# Numeric constants, each traceable to a rule. Analysis code should read these rather than repeating
# the numbers, so that a documentation correction changes one line here instead of several files.
# ------------------------------------------------------------------------------------------------

#: D08. Adaptive Therapy is available only for a signal of interest inside the alpha-beta range.
ADAPTIVE_BAND_LOW_HZ = 8.0
ADAPTIVE_BAND_HIGH_HZ = 30.0

#: D08. A sensing-only configuration uses the wider window instead.
SENSING_BAND_LOW_HZ = 1.0
SENSING_BAND_HIGH_HZ = 96.0

#: D13. The frequency-domain content of an LFP snapshot runs from 0 to 96.68 Hz.
SPECTRUM_MAX_HZ = 96.68

#: D09. The deployment gate for threshold capture. The two Medtronic documents disagree here and the
#: conservative of the two numbers is used as the gate; see ``LFP_AUTODETECT_FLOOR_UVP``.
LFP_THRESHOLD_CAPTURE_FLOOR_UVP = 1.2

#: D09. The floor the white paper gives for the signal test's automatic peak selection. It is a
#: DIFFERENT number from the gate above, in a different document, and the difference is recorded
#: rather than resolved because neither document explains it.
LFP_AUTODETECT_FLOOR_UVP = 1.1

#: D09. The discrepancy in words, so that it can be displayed next to both numbers.
LFP_FLOOR_DISCREPANCY = (
    "A610 p. 37 recommends selecting a configuration whose alpha-beta LFP amplitude is greater "
    "than 1.2 uVp and A610 p. 72 calls anything below 1.2 uVp below the system minimum for "
    "auto-detection, while WP p. 8 states that the signal test auto-selects a peak that exceeds "
    "1.1 uVp. The module gates on 1.2 uVp because it is the more conservative of the two, and "
    "reports 1.1 uVp as the auto-detection floor. Which number governs a manually selected band is "
    "not resolved by either document."
)

#: D10. The band width the white paper describes the user as selecting. The tolerance is OURS, not
#: the document's: the document says "approximately 5 Hz" and prints no range, so the tolerance only
#: decides whether an advisory is raised and never disqualifies anything.
BAND_WIDTH_NOMINAL_HZ = 5.0
BAND_WIDTH_TOLERANCE_HZ = 1.0

#: D13. Sampling rate and the two available settings of the second, user-configurable high-pass.
SAMPLE_RATE_HZ = 250.0
HIGHPASS_OPTIONS_HZ = (1.0, 10.0)

#: D16. Sense channels outside this impedance window are excluded by the device itself. The short
#: limit depends on the lead family.
IMPEDANCE_SHORT_OHMS = {"1x4": 250.0, "sensight": 350.0}
IMPEDANCE_OPEN_OHMS = 10_000.0

#: D27. Above either of these the stimulation artefact may inflate the LFP during capture. This is a
#: measurement-validity ceiling, not a safety ceiling, and the two must not be conflated.
CAPTURE_ARTEFACT_AMP_MA = 5.0
CAPTURE_ARTEFACT_PW_US = 120.0

#: D44. The only published rate floor. It is written for movement disorders and its relevance to a
#: pain participant is not established by the document, so it is a soft floor.
LOW_RATE_SOFT_FLOOR_HZ = 30.0

#: D31. The general Percept envelope, from the Movement Disorders appendix. A group with BrainSense
#: configured is NARROWER than this in three specific ways whose values are unpublished, so passing
#: this envelope is necessary and not sufficient.
GENERAL_ENVELOPE = {
    "amp_mA": (0.0, 25.5),
    "amp_mA_fine_step": (0.0, 12.5),
    "pulse_width_us": (20.0, 450.0),
    "rate_hz": (2.0, 250.0),
}

#: D11. One unit of LFP Power is approximately this many microvolts squared. LFP Power is a linear
#: sum of squared magnitude, so this conversion is a scaling and not a log transform.
LFP_POWER_LSB_TO_UV2 = 0.01

#: D46. Snapshot and event capacity, after which the oldest snapshots are overwritten silently.
SNAPSHOT_CAPACITY_TOTAL = 200
SNAPSHOT_CAPACITY_PER_HEMISPHERE = 100
NON_LFP_EVENT_CAPACITY = 800

#: D47, D48. Streaming export ceiling and the data hole a stimulation on/off transition creates.
STREAM_EXPORT_MAX_HOURS = 8.0
STREAM_ON_OFF_HOLE_S = 7.0

#: D41. The charge density above which the literature survey quoted by the programming guide
#: suggests damage may occur. The device warns and allows an override; the module displays the
#: device's own state rather than recomputing, because the per-electrode surface area needed for the
#: calculation is not in the lead specification.
CHARGE_DENSITY_LIMIT_UC_CM2 = 30.0

#: D01. The five approved indications. Chronic pain is not among them, which is why every report
#: this module produces carries an off-label banner.
APPROVED_INDICATIONS = frozenset(
    {"parkinsons_disease", "essential_tremor", "dystonia",
     "obsessive_compulsive_disorder", "epilepsy"}
)

#: D20. The per-mode table, transcribed from WP p. 14 Table 1 and A610 pp. 38 and 42. Durations are
#: milliseconds unless the key says otherwise. ``None`` means the document prints "not applicable"
#: for that cell, which is different from the value being unknown.
THRESHOLD_MODE_TABLE = {
    "dual": {
        "can_drive_therapy": True,
        "available_to_non_pd_patient": True,          # sensing only, under D03
        "adaptive_band_hz": (8.0, 30.0),
        "sensing_band_hz": (1.0, 96.0),
        "fft_points": 256,
        "fft_update_rate_hz_adaptive": 5.0,
        "fft_update_rate_hz_sensing": 2.0,
        "averaging_ms_adaptive": 1200.0,
        "averaging_ms_sensing": 3000.0,
        "onset_ms_adaptive": 1200.0,
        "detection_blanking_ms_adaptive": 2000.0,
        "transition_up_s": 150.0,                     # 2.5 minutes
        "transition_down_s": 300.0,                   # 5 minutes
        "threshold_method": "manual upper and lower",
        "suggested_medication_state": "off medication",
    },
    "single": {
        "can_drive_therapy": True,
        "available_to_non_pd_patient": False,
        "adaptive_band_hz": (8.0, 30.0),
        "sensing_band_hz": (1.0, 96.0),
        "fft_points": 64,
        "fft_update_rate_hz_adaptive": 20.0,
        "fft_update_rate_hz_sensing": 2.0,
        "averaging_ms_adaptive": 100.0,
        "averaging_ms_sensing": 1000.0,
        "onset_ms_adaptive": 200.0,
        "detection_blanking_ms_adaptive": 550.0,
        "transition_up_s": 0.25,
        "transition_down_s": 0.25,
        "threshold_method": "computed as 0.75 x (Upper - Lower) + Lower",
        "suggested_medication_state": "off medication",
    },
    "single_inverse": {
        "can_drive_therapy": False,
        "available_to_non_pd_patient": False,
        "adaptive_band_hz": None,
        "sensing_band_hz": (1.0, 96.0),
        "fft_points": 256,
        "fft_update_rate_hz_adaptive": None,
        "fft_update_rate_hz_sensing": 2.0,
        "averaging_ms_adaptive": None,
        "averaging_ms_sensing": 3000.0,
        "onset_ms_adaptive": None,
        "detection_blanking_ms_adaptive": None,
        "transition_up_s": None,
        "transition_down_s": None,
        "threshold_method": "computed as 0.75 x (Upper - Lower) + Lower",
        "suggested_medication_state": "on medication",
    },
}

#: D21. The adjustable range of the onset duration is not printed in either Medtronic document. The
#: only published ranges come from the ADAPT-PD methodology paper and are labelled as such wherever
#: they are used, because a trial paper is not device labelling.
ONSET_DURATION_RANGE_MS_ADAPT_PD = {"dual": (1200.0, 2000.0), "single": (200.0, 500.0)}

#: Accepted spellings of the three threshold modes, normalised before use so that a caller writing
#: "Dual Threshold" and a caller writing "dual" get the same verdict.
THRESHOLD_MODE_ALIASES = {
    "dual": "dual", "dual_threshold": "dual", "dualthreshold": "dual", "dual threshold": "dual",
    "single": "single", "single_threshold": "single", "single threshold": "single",
    "single_inverse": "single_inverse", "single_threshold_inverse": "single_inverse",
    "single threshold inverse": "single_inverse", "inverse": "single_inverse",
}

#: Accepted spellings of the participant indication.
INDICATION_ALIASES = {
    "parkinsons": "parkinsons_disease", "parkinson": "parkinsons_disease",
    "parkinsons_disease": "parkinsons_disease", "pd": "parkinsons_disease",
    "essential_tremor": "essential_tremor", "et": "essential_tremor",
    "dystonia": "dystonia",
    "ocd": "obsessive_compulsive_disorder",
    "obsessive_compulsive_disorder": "obsessive_compulsive_disorder",
    "epilepsy": "epilepsy",
    "chronic_pain": "chronic_pain", "pain": "chronic_pain",
}

#: Every candidate key any predicate reads, with the rules that read it. This exists so that a
#: caller confronted with an ``input_not_supplied`` unknown can see what to declare, and so that the
#: front end can render the undeclared fields as a form rather than as an error.
CANDIDATE_KEYS = {
    "intent": "D08, D18, D24, D27, D28, D34, D40. Either 'adaptive' or 'sensing_only'. When absent "
              "it defaults to 'adaptive', which is the narrower and therefore safer reading; "
              "defaulting the other way would widen the permitted band from 8-30 Hz to 1-96 Hz on "
              "the strength of a missing key.",
    "channel": "Recorded for the report. Not itself checked.",
    "channel_is_brainsense_setup_channel": "D15. Only the three BrainSense Setup channels per "
                                           "hemisphere can become a control signal.",
    "sensing_hemisphere": "D38, D39.",
    "actuated_hemisphere": "D38, D39.",
    "contralateral_pairing_acknowledged": "D39. A contralateral pairing is the document's stated "
                                          "fallback and must be marked as one.",
    "center_hz": "D08, D12, D13.",
    "band_width_hz": "D08, D10, D13.",
    "rate_hz": "D31, D44.",
    "pulse_width_us": "D27, D31.",
    "amp_mA": "D31.",
    "threshold_mode": "D08, D12, D18, D24, D25, D40.",
    "lfp_amplitude_uvp": "D09.",
    "power_scale": "D11. Must be 'linear'; the device thresholds a linear sum of squared magnitude.",
    "pooled_across_center_or_mode": "D12. Power values from different centre frequencies or "
                                    "different threshold modes are not comparable.",
    "highpass_hz": "D13. Either 1.0 or 10.0. Decides whether the selected band sits inside the "
                   "filter stopband.",
    "impedance_ohms": "D16.",
    "impedance_tested": "D16.",
    "artifact_flags": "D17. A list; an empty list means the device flagged nothing.",
    "power_slope_vs_amplitude_sign": "D19. Must be -1: the LFP must be suppressed when stimulation "
                                     "is high.",
    "power_slope_vs_pain_sign": "D19. Must be +1: the device can only ask for more stimulation when "
                                "band power rises.",
    "capture_amp_low_mA": "D24, D28.",
    "capture_amp_high_mA": "D24, D27, D28.",
    "adaptive_min_mA": "D07, D28.",
    "adaptive_max_mA": "D28.",
    "paused_amplitude_mA": "D34.",
    "vertically_aligned_segments_matched": "D29.",
    "frequency_search_closed": "D30. Rate and pulse width freeze when BrainSense is set up, so the "
                               "open-loop frequency search must be finished first.",
    "has_pocket_adaptor": "D32.",
    "multiple_rates_in_group": "D32.",
    "interleaving_in_group": "D32.",
    "cycling_in_group": "D32.",
    "patient_limits_configured": "D32.",
    "group_threshold_modes": "D23. The threshold modes of the other adaptive programs in the group.",
    "onset_duration_ms": "D21.",
    "predicted_recapture_alert": "D26.",
    "charge_density_state": "D41. The device's own charge-density state, taken rather than "
                            "recomputed.",
    "transitions_through_zero": "D48.",
    "snapshots_stored_per_hemisphere": "D46.",
    "streaming_session_hours": "D47.",
    "declared_mode_timing": "D20. Any timing parameters the caller has declared, checked against "
                            "the documented defaults for the declared mode.",
}

#: Every participant key any predicate reads.
PARTICIPANT_KEYS = {
    "uid": "Recorded for the report. Not itself checked.",
    "indication": "D01, D02. One of the five approved indications, or 'chronic_pain'.",
    "programming_mode": "D03. The mode the device is actually programmed in, which is a different "
                        "fact from the clinical indication.",
    "n_neurostimulators": "D04. Currently unread for RCS08.",
    "brainsense_min_rate_hz": "D31. Read off the A610 rate control after a BrainSense group exists.",
    "brainsense_max_rate_hz": "D31.",
    "brainsense_max_pulse_width_us": "D31.",
    "lead_type": "D16. '1x4' or 'sensight'; decides the short-circuit limit.",
    "dual_lead_implant": "D39. Contralateral sensing is documented for dual lead implants only.",
    "adaptive_configured_both_hemispheres": "D40.",
    "accepts_cross_hemisphere_coupling": "D40.",
    "can_operate_neurostimulator": "D05.",
}


# ------------------------------------------------------------------------------------------------
# Field readers. Every predicate goes through these so that a missing, null or unparseable field
# becomes None (not determinable) at exactly one place in the file.
# ------------------------------------------------------------------------------------------------
def _num(d, key):
    """Return the field as a float, or None when it is absent or not a number.

    Booleans are rejected as numbers on purpose. In Python ``True`` would silently read as 1.0, so a
    caller who wrote ``{"rate_hz": True}`` by mistake would get a numeric comparison against a
    typographical error instead of a not-determinable verdict.
    """
    if not isinstance(d, dict):
        return None
    v = d.get(key)
    if v is None or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _flag(d, key):
    """Return the field as a bool, or None when it is absent or not a bool.

    A string such as "false" is deliberately NOT interpreted, because a caller who serialises flags
    as strings should be told the field is not determinable rather than have this file guess which
    strings are falsy.
    """
    if not isinstance(d, dict):
        return None
    v = d.get(key)
    return v if isinstance(v, bool) else None


def _text(d, key):
    """Return the field as a lowercased, stripped string, or None when absent or not a string."""
    if not isinstance(d, dict):
        return None
    v = d.get(key)
    if not isinstance(v, str) or not v.strip():
        return None
    return v.strip().lower()


def _mode(candidate):
    """Return the normalised threshold mode, or None when it is absent or unrecognised."""
    raw = _text(candidate, "threshold_mode")
    if raw is None:
        return None
    return THRESHOLD_MODE_ALIASES.get(raw.replace("-", "_"))


def _indication(participant):
    """Return the normalised indication, or None when it is absent or unrecognised."""
    raw = _text(participant, "indication")
    if raw is None:
        return None
    return INDICATION_ALIASES.get(raw.replace(" ", "_"))


def _is_adaptive(candidate):
    """True when the candidate is an Adaptive Therapy recommendation rather than sensing only.

    The default is adaptive because that is what this module is for and because it is the stricter
    reading: it narrows the permitted band from 1-96 Hz to 8-30 Hz under D08 and it engages the
    capture and limit rules. Defaulting to sensing only would relax those gates on the strength of
    an absent key.
    """
    raw = _text(candidate, "intent")
    return raw is None or raw in ("adaptive", "adaptive_therapy", "closed_loop")


def band_edges(candidate):
    """Return the (low, high) edges of the candidate band in Hz, or None if either input is absent.

    The edges, not the centre, are what D08 constrains, so this helper is used by every rule that
    talks about where the band sits. A 5 Hz band centred at 10 Hz has a lower edge at 7.5 Hz and is
    outside the adaptive window even though its centre is inside it.
    """
    centre = _num(candidate, "center_hz")
    width = _num(candidate, "band_width_hz")
    if centre is None or width is None:
        return None
    return (centre - width / 2.0, centre + width / 2.0)


def permitted_band_hz(candidate):
    """Return the frequency window this candidate must fit inside, per D08."""
    if _is_adaptive(candidate):
        return (ADAPTIVE_BAND_LOW_HZ, ADAPTIVE_BAND_HIGH_HZ)
    return (SENSING_BAND_LOW_HZ, SENSING_BAND_HIGH_HZ)


# ------------------------------------------------------------------------------------------------
# Predicates. Each takes (candidate, participant) and returns True, False or None, and nothing else,
# because that is the contract ``types.DeviceConstraint.predicate`` documents. The observed values a
# clinician needs in order to act on a verdict are produced separately by the ``_OBSERVED``
# functions further down, which keeps the predicate contract intact.
# ------------------------------------------------------------------------------------------------
def _p_d01(candidate, participant):
    """Off-label banner. True only when the indication is one of the five approved ones."""
    ind = _indication(participant)
    if ind is None:
        return None
    return ind in APPROVED_INDICATIONS


def _p_d02(candidate, participant):
    """Adaptive Therapy is labelled for the Parkinson's disease indication only."""
    ind = _indication(participant)
    if ind is None:
        return None
    if not _is_adaptive(candidate):
        return True
    return ind == "parkinsons_disease"


def _p_d03(candidate, participant):
    """Whether the Adaptive workflow can be finished on shipping software.

    This turns on the mode the device is PROGRAMMED in, which is a separate fact from the clinical
    indication. A participant programmed in Parkinson's mode can choose a threshold mode and can
    advance past threshold capture; a participant programmed otherwise is defaulted to Dual
    Threshold and, per WP p. 13, cannot continue past the capture step, which means the Limits,
    Summary and Start Adaptive Therapy steps are unreachable and any recommendation this module
    makes is prepared rather than executable.
    """
    mode = _text(participant, "programming_mode")
    if mode is None:
        return None
    if not _is_adaptive(candidate):
        return True
    return mode in ("parkinsons", "parkinsons_disease", "pd", "parkinson")


def _p_d04(candidate, participant):
    """One neurostimulator. The value has not been read for RCS08, hence severity 'unknown'.

    The predicate is still live so that the rule resolves the moment the device record supplies the
    count. A bilateral implant delivered as two separate cans falls under the prohibition; a single
    can driving two leads does not, so the field has to be a count and not a laterality.
    """
    n = _num(participant, "n_neurostimulators")
    if n is None:
        return None
    return n == 1


def _p_d07(candidate, participant):
    """The lower adaptive limit must not be zero, because abrupt cessation risks rebound.

    Returning False for a declared zero is the point of the rule: the minimum of the adaptive range
    is not safe merely because it is small, and zero is not the low end of a dose axis but a
    qualitatively different therapeutic state.
    """
    lo = _num(candidate, "adaptive_min_mA")
    if lo is None:
        return None
    return lo > 0.0


def _p_d08(candidate, participant):
    """The band EDGES must fit inside the permitted window, not merely the centre frequency.

    This is the rule that disqualifies the biomarker path's 3.92 Hz selection: a 5 Hz band centred
    at 3.92 Hz runs from 1.42 to 6.42 Hz, entirely below the 8 Hz floor of the adaptive window. It
    also disqualifies a band centred at 10 Hz, whose centre is inside the window and whose lower
    edge is not.
    """
    edges = band_edges(candidate)
    if edges is None:
        return None
    low, high = permitted_band_hz(candidate)
    return edges[0] >= low and edges[1] <= high


def _p_d09(candidate, participant):
    """Alpha-beta band LFP amplitude must reach the 1.2 uVp deployment gate.

    The comparison is greater-than-or-equal because A610 p. 37 recommends an amplitude "greater than
    1.2 uVp" while A610 p. 72 calls a signal "less than 1.2 uVp" below the system minimum, so a
    value of exactly 1.2 is described by neither sentence and is admitted rather than rejected. The
    1.1 uVp auto-detection floor from WP p. 8 is a different number in a different document and is
    reported, not used as the gate; see LFP_FLOOR_DISCREPANCY.
    """
    bins = candidate.get("lfp_bins_uvp")
    if bins:
        # Per-bin form. The rule passes when ANY bin inside the selected band clears the gate,
        # because threshold capture reads one frequency, not the band average — averaging a peak
        # together with its neighbours can hide a perfectly capturable peak, and can equally
        # manufacture one. `lfp_bin_clearance` carries the detail for the interface.
        lo, hi = band_edges(candidate) or (None, None)
        inband = [(f, a) for f, a in bins
                  if lo is None or (lo <= float(f) < hi)]
        if not inband:
            return None
        return any(float(a) >= LFP_THRESHOLD_CAPTURE_FLOOR_UVP for _, a in inband)
    amp = _num(candidate, "lfp_amplitude_uvp")
    if amp is None:
        return None
    return amp >= LFP_THRESHOLD_CAPTURE_FLOOR_UVP


def _p_d10(candidate, participant):
    """Band width close to the nominal 5 Hz. Advisory, because the document prints no range."""
    width = _num(candidate, "band_width_hz")
    if width is None:
        return None
    return abs(width - BAND_WIDTH_NOMINAL_HZ) <= BAND_WIDTH_TOLERANCE_HZ


def _p_d11(candidate, participant):
    """Power must be expressed on the linear scale the device actually thresholds.

    LFP Power is the sum of squared LFP magnitude across the band. A threshold placed on a log
    transform of that quantity is not the threshold the device will apply, so a candidate carrying a
    log-scale power column cannot be deployed even if every statistic computed on it is sound. The
    log-scale versions remain valid as statistical descriptions and must be labelled as such.
    """
    scale = _text(candidate, "power_scale")
    if scale is None:
        return None
    return scale in ("linear", "lsb", "linear_lsb")


def _p_d12(candidate, participant):
    """The power column must carry its centre frequency and threshold mode, and must not be pooled.

    Power values from different centre frequencies are not comparable, and because the FFT size
    differs between Single Threshold and the other two modes, power values from different threshold
    modes are not comparable either. So the identity of a power column is the triple of value,
    centre frequency and threshold mode, and any operation that pools across the last two is
    refused rather than warned about.
    """
    pooled = _flag(candidate, "pooled_across_center_or_mode")
    if pooled is None:
        return None
    if pooled:
        return False
    return _num(candidate, "center_hz") is not None and _mode(candidate) is not None


def _p_d13(candidate, participant):
    """The band must lie in the passband of the configured filters, not in a stopband.

    All data is sampled at 250 Hz and passes a fixed 1 Hz high-pass plus a second, user-configurable
    high-pass at either 1 Hz or 10 Hz. If that second filter is set to 10 Hz then a band centred at
    3.92 Hz sits inside the stopband and the power recorded there is an artefact of the filter
    setting rather than a physiological signal, which would make the D09 amplitude check meaningless
    as well. The filter setting is read from the session JSON and stamped on every analysis.
    """
    edges = band_edges(candidate)
    hp = _num(candidate, "highpass_hz")
    if edges is None or hp is None:
        return None
    if hp not in HIGHPASS_OPTIONS_HZ:
        return False
    return edges[0] >= hp and edges[1] <= SPECTRUM_MAX_HZ


def _p_d15(candidate, participant):
    """Only a BrainSense Setup channel can become a control signal.

    Electrode Survey, Electrode Identifier, Timeline, Events and Streaming all expose channels that
    cannot be configured as the sensing channel for therapy, so a band chosen on one of those is not
    deployable however good it looks. Which contact pairs are Setup channels depends on the lead and
    is not printed in the supplied documents, so the caller declares it rather than this file
    inferring it.
    """
    return _flag(candidate, "channel_is_brainsense_setup_channel")


def _p_d16(candidate, participant):
    """Impedance inside the device's own exclusion window, measured by an impedance test.

    The device excludes sense channels with potential shorts, below 250 ohms on a 1x4 lead or
    350 ohms on a SenSight lead, and potential opens above 10 kilohms. The test itself is a
    precondition of BrainSense setup, so an untested channel is not eligible even if a stored
    impedance value happens to be in range.
    """
    tested = _flag(candidate, "impedance_tested")
    z = _num(candidate, "impedance_ohms")
    lead = _text(participant, "lead_type")
    if z is None or lead is None or tested is None:
        return None
    if not tested:
        return False
    short_limit = IMPEDANCE_SHORT_OHMS.get(lead.replace("-", "").replace("_", ""))
    if short_limit is None:
        return None
    return short_limit <= z <= IMPEDANCE_OPEN_OHMS


def _p_d17(candidate, participant):
    """No cardiac, motion or atypical-signal artefact flagged on the channel.

    The clinician application raises these flags itself and states that using a configuration with
    an artefact detected may interfere with capturing meaningful BrainSense information and may
    affect Adaptive Therapy performance. An empty list is a positive statement that the device
    flagged nothing; an absent field is not.
    """
    flags = candidate.get("artifact_flags") if isinstance(candidate, dict) else None
    if flags is None or not isinstance(flags, (list, tuple, set)):
        return None
    return len(flags) == 0


def _p_d18(candidate, participant):
    """The declared threshold mode must be one that can drive therapy, when therapy is intended.

    Single Threshold Inverse is available only in a Sensing Only configuration, so naming it in an
    adaptive recommendation is a category error rather than a marginal choice.
    """
    mode = _mode(candidate)
    if mode is None:
        return None
    if not _is_adaptive(candidate):
        return True
    return bool(THRESHOLD_MODE_TABLE[mode]["can_drive_therapy"])


def _p_d19(candidate, participant):
    """The sign of the biomarker must match the device's fixed control polarity.

    In both therapy-driving modes the amplitude ramps UP when the LFP passes above threshold, and
    the white paper states the precondition as a requirement on the signal: when stimulation is
    high, the LFP must be suppressed relative to when stimulation is low. The one mode with the
    opposite mapping, Single Threshold Inverse, is the one that cannot deliver therapy. So the band
    power must fall as amplitude rises and must rise as pain rises. A band whose power falls as pain
    rises cannot drive Adaptive Therapy in either direction, and no choice of thresholds repairs it.
    """
    amp_sign = _num(candidate, "power_slope_vs_amplitude_sign")
    pain_sign = _num(candidate, "power_slope_vs_pain_sign")
    if not _is_adaptive(candidate):
        return True
    if amp_sign is None or pain_sign is None:
        return None
    return amp_sign < 0 and pain_sign > 0


def _p_d20(candidate, participant):
    """Any timing parameters the caller declares must match the documented defaults for the mode.

    Advisory rather than blocking: the device supplies these defaults itself, and the adjustable
    ranges are not printed in either document, so a declared value that differs from the default is
    something to look at rather than something this file can call wrong.
    """
    mode = _mode(candidate)
    declared = candidate.get("declared_mode_timing") if isinstance(candidate, dict) else None
    if mode is None or not isinstance(declared, dict) or not declared:
        return None
    row = THRESHOLD_MODE_TABLE[mode]
    for key, value in declared.items():
        if key in row and row[key] is not None and value != row[key]:
            return False
    return True


def _p_d21(candidate, participant):
    """Onset duration inside the only published range, which comes from the trial paper.

    Neither Medtronic document prints the adjustable range, so this check cites Stanslaski et al.
    2024 and is advisory. A value outside the trial range is not thereby unprogrammable; it is
    simply outside what has been published.
    """
    mode = _mode(candidate)
    onset = _num(candidate, "onset_duration_ms")
    if mode is None or onset is None:
        return None
    rng = ONSET_DURATION_RANGE_MS_ADAPT_PD.get(mode)
    if rng is None:
        return None
    return rng[0] <= onset <= rng[1]


def _p_d23(candidate, participant):
    """All adaptive programs in a group share one threshold mode.

    Surfaced rather than enforced because this evaluator is handed one candidate configuration and
    cannot see the group's other programs. When the caller declares them the predicate returns a
    real verdict.
    """
    mode = _mode(candidate)
    others = candidate.get("group_threshold_modes") if isinstance(candidate, dict) else None
    if mode is None or not isinstance(others, (list, tuple, set)) or not others:
        return None
    normalised = {THRESHOLD_MODE_ALIASES.get(str(m).strip().lower().replace("-", "_")) for m in others}
    normalised.discard(None)
    return normalised.issubset({mode})


def _p_d24(candidate, participant):
    """Two therapeutic capture amplitudes, in the order the capture table defines.

    In Dual Threshold the Upper LFP Threshold is captured at the LOWER of the two therapeutic
    amplitudes and the Lower LFP Threshold at the higher one. The naming is crossed deliberately,
    because power is expected to be higher when stimulation is lower, and a caller who swaps them
    produces an inverted capture that the device will refuse. In Single Threshold only the upper
    therapeutic amplitude is captured, because the device supplies the second capture itself at
    0 mA, which is why only the high amplitude is required there.
    """
    if not _is_adaptive(candidate):
        return True
    mode = _mode(candidate)
    hi = _num(candidate, "capture_amp_high_mA")
    lo = _num(candidate, "capture_amp_low_mA")
    if mode is None:
        return None
    if mode == "single":
        return None if hi is None else hi > 0.0
    if hi is None or lo is None:
        return None
    return 0.0 < lo < hi


def _p_d25(candidate, participant):
    """Single Threshold capture forces an exposure at 0 mA.

    Advisory, and it fires whenever Single Threshold is proposed. The device automatically captures
    its second LFP signal with amplitude set to 0 mA, and for a pain participant that is not the low
    end of a dose axis but a qualitatively different therapeutic state, so the capture procedure
    itself changes what the participant experiences.
    """
    mode = _mode(candidate)
    if mode is None:
        return None
    return mode != "single"


def _p_d26(candidate, participant):
    """Predict the RECAPTURE THRESHOLDS alert before the visit rather than discovering it at one.

    The device raises this alert when the LFP is minimally responsive to changes in stimulation
    amplitude, and it refuses captures that are inverted or too close together. Both conditions are
    quantities this module estimates from historical data, so an expected alert is reported here.
    """
    predicted = _flag(candidate, "predicted_recapture_alert")
    if predicted is None:
        return None
    return not predicted


def _p_d27(candidate, participant):
    """Capture amplitude at or below 5 mA and pulse width at or below 120 us.

    Above either value the stimulation artefact may make the LFP appear elevated when the Lower LFP
    Threshold is captured, so the resulting threshold is not a physiological measurement. This is a
    measurement-validity ceiling and it is distinct from any safety ceiling; the fact that it
    coincides with the 5.0 mA per-hemisphere limit this project adopted is a coincidence and not a
    derivation. For this participant the recorded pulse width is asymmetric between hemispheres,
    most commonly 60 us on the left and 160 us on the right, so right-hemisphere captures are
    artefact-suspect by this rule.
    """
    if not _is_adaptive(candidate):
        return True
    pw = _num(candidate, "pulse_width_us")
    hi = _num(candidate, "capture_amp_high_mA")
    if hi is None:
        hi = _num(candidate, "amp_mA")
    if pw is None or hi is None:
        return None
    return hi <= CAPTURE_ARTEFACT_AMP_MA and pw <= CAPTURE_ARTEFACT_PW_US


def _p_d28(candidate, participant):
    """The adaptive amplitude limits must be declared, ordered, and both therapeutic.

    The limits default to the amplitudes used when capturing the thresholds, which makes the choice
    of capture amplitudes simultaneously a measurement decision and a therapeutic-range decision:
    the module cannot recommend one without the other. The lower limit must be above zero for the
    reason D07 gives, and both limits must sit inside the general device envelope.
    """
    if not _is_adaptive(candidate):
        return True
    lo = _num(candidate, "adaptive_min_mA")
    hi = _num(candidate, "adaptive_max_mA")
    if lo is None or hi is None:
        return None
    amp_lo, amp_hi = GENERAL_ENVELOPE["amp_mA"]
    return 0.0 < lo < hi <= amp_hi and lo >= amp_lo


def _p_d29(candidate, participant):
    """Vertically aligned segments must share amplitude and polarity when BrainSense is configured.

    The rest of D29 is a workflow hazard rather than a check: changing the electrode configuration
    resets amplitude to zero and clears the BrainSense configuration, and after the OptiStim step
    the captured thresholds survive while the amplitudes that produced them do not, which silently
    detaches a threshold from its calibration. That hazard is in the human text so that it appears
    on the report next to this check.
    """
    return _flag(candidate, "vertically_aligned_segments_matched")


def _p_d30(candidate, participant):
    """The open-loop frequency search must be closed before BrainSense is configured.

    Pulse width and rate cannot be adjusted once BrainSense has been set up for either hemisphere,
    and re-enabling them requires deleting the group and reprogramming it without BrainSense or
    changing the electrode configuration, which by D29 also clears the captured thresholds. So the
    StimOptimizer's frequency search and the closed-loop configuration are sequential and not
    concurrent, and this rule is where that ordering is enforced rather than assumed.
    """
    return _flag(candidate, "frequency_search_closed")


def _p_d31(candidate, participant):
    """Rate and pulse width inside the BrainSense group envelope, whose values are unpublished.

    A group configured with BrainSense has a lower maximum pulse width, a lower maximum rate and a
    HIGHER minimum rate than a group without it, and neither document prints any of the three
    numbers. Severity is therefore 'unknown' and the rule blocks. The predicate still does the work
    it can: it checks the general Percept envelope, so a rate of 300 Hz fails outright, and it
    returns a real verdict as soon as the values are read off the A610 controls and recorded on the
    participant. This matters concretely for RCS08, whose incumbent rate is 55 Hz: if the BrainSense
    minimum rate exceeds 55 Hz then that configuration cannot be programmed at all.
    """
    rate = _num(candidate, "rate_hz")
    pw = _num(candidate, "pulse_width_us")
    if rate is not None:
        lo, hi = GENERAL_ENVELOPE["rate_hz"]
        if not (lo <= rate <= hi):
            return False
    if pw is not None:
        lo, hi = GENERAL_ENVELOPE["pulse_width_us"]
        if not (lo <= pw <= hi):
            return False
    bs_min = _num(participant, "brainsense_min_rate_hz")
    bs_max = _num(participant, "brainsense_max_rate_hz")
    bs_pw_max = _num(participant, "brainsense_max_pulse_width_us")
    if bs_min is None or rate is None:
        return None
    if rate < bs_min:
        return False
    if bs_max is not None and rate > bs_max:
        return False
    if bs_pw_max is None or pw is None:
        return None
    return pw <= bs_pw_max


def _p_d32(candidate, participant):
    """The feature exclusions that make a BrainSense or Adaptive group impossible.

    BrainSense cannot be configured in a hemisphere containing a pocket adaptor, cannot share a
    group with Multiple Rates, and cannot be interleaved; Adaptive Therapy additionally excludes
    cycling and patient limits. Each of these is phrased as an impossibility, so any one of them
    disqualifies. All five have to be declared, because an undeclared exclusion is exactly the kind
    of thing that is discovered at the programming visit.
    """
    checks = {
        "has_pocket_adaptor": True,
        "multiple_rates_in_group": True,
        "interleaving_in_group": True,
    }
    if _is_adaptive(candidate):
        checks["cycling_in_group"] = True
        checks["patient_limits_configured"] = True
    verdict = True
    for key in checks:
        value = _flag(candidate, key)
        if value:
            # One declared exclusion is enough to disqualify, and saying so immediately is safe
            # here because no later flag could turn a violation back into a pass.
            return False
        if value is None:
            verdict = None
    return verdict


def _p_d34(candidate, participant):
    """A Paused Amplitude must be declared, and it must not be zero.

    The programming guide states that setting it is necessary so that a patient can pause Adaptive
    Therapy because of stimulation-related side effects or a loop that is not performing. It is also
    the amplitude delivered during every automatic pause, including each recharging session, so it
    is the therapy the participant actually receives during scheduled controller outages. Zero is
    rejected for the reason D07 gives.
    """
    if not _is_adaptive(candidate):
        return True
    paused = _num(candidate, "paused_amplitude_mA")
    if paused is None:
        return None
    return paused > 0.0


def _p_d38(candidate, participant):
    """Both the sensing hemisphere and the actuated hemisphere must be declared.

    BrainSense and Adaptive Therapy are hemisphere-specific features, configured and disabled one
    hemisphere at a time, so a configuration that names only one hemisphere is ambiguous about what
    it is asking the device to do.
    """
    sens = _text(candidate, "sensing_hemisphere")
    act = _text(candidate, "actuated_hemisphere")
    if sens is None or act is None:
        return None
    return sens in ("left", "right") and act in ("left", "right")


def _p_d39(candidate, participant):
    """A contralateral sensing pairing must be marked as the documented fallback that it is.

    The programming guide supports driving one hemisphere's Adaptive Therapy from the other
    hemisphere's sensing data, and it states the intent: it is for situations where no configuration
    on the actuated lead is acceptable for sensing setup. It is documented for dual lead implants
    only. Treating such a pairing as equivalent to an ipsilateral one would hide that it is a
    fallback, and the distinction is live on the present data, where two of the four configurations
    the current screen licenses are contralateral.
    """
    sens = _text(candidate, "sensing_hemisphere")
    act = _text(candidate, "actuated_hemisphere")
    if sens is None or act is None:
        return None
    if sens == act:
        return True
    dual = _flag(participant, "dual_lead_implant")
    acknowledged = _flag(candidate, "contralateral_pairing_acknowledged")
    if dual is None or acknowledged is None:
        return None
    return bool(dual and acknowledged)


def _p_d40(candidate, participant):
    """In Single Threshold mode with both hemispheres configured, either hemisphere drives therapy.

    This couples the hemispheres, and it invalidates the one-sensing-channel-drives-one-actuated-
    hemisphere model that the candidate record otherwise expresses. It is not a prohibition, so the
    rule passes when the caller states that the coupling is understood and accepted; it fails when
    the coupling is present and unacknowledged, because then the report would describe a controller
    the device is not going to run. Under D03 this mode is unavailable to a participant not
    programmed in Parkinson's mode, but the rule still has to be encoded, because it becomes live
    the moment the indication question is resolved.
    """
    if not _is_adaptive(candidate):
        return True
    mode = _mode(candidate)
    if mode is None:
        return None
    if mode != "single":
        return True
    both = _flag(participant, "adaptive_configured_both_hemispheres")
    if both is None:
        return None
    if not both:
        return True
    return _flag(participant, "accepts_cross_hemisphere_coupling")


def _p_d41(candidate, participant):
    """Report the device's own charge-density state rather than recomputing it.

    The literature survey the programming guide quotes puts the damage threshold at
    30 microcoulombs per square centimetre per phase, the system can exceed it, and the warning can
    be acknowledged and overridden. Reproducing the calculation would need the per-electrode surface
    area, and the lead specification prints only the lead-level surface area, so the honest check is
    whether the device's own state has been recorded.
    """
    state = _text(candidate, "charge_density_state")
    if state is None:
        return None
    return state in ("within_limit", "ok", "no_warning")


def _p_d44(candidate, participant):
    """Soft rate floor of 30 Hz.

    The sentence is written for movement disorders, where a rate below 30 Hz may drive tremor at the
    programmed frequency. Its relevance to a pain participant is not established by the document,
    and it is the only published rate floor, so it is carried as an advisory with the citation
    attached rather than as a gate.
    """
    rate = _num(candidate, "rate_hz")
    if rate is None:
        return None
    return rate >= LOW_RATE_SOFT_FLOOR_HZ


def _p_d46(candidate, participant):
    """Snapshot buffer headroom.

    The snapshot store is a circular buffer with a hard capacity of 200 snapshots, for example 100
    per hemisphere in a bilateral implant, and the oldest are overwritten once it is full. A study
    that relies on patient-marked events therefore has to schedule downloads against that ceiling or
    lose data with no error anywhere.
    """
    n = _num(candidate, "snapshots_stored_per_hemisphere")
    if n is None:
        return None
    return n < SNAPSHOT_CAPACITY_PER_HEMISPHERE


def _p_d47(candidate, participant):
    """Streaming session inside the 8 hour export ceiling.

    There is no maximum streaming duration on the device, but A610 v5.0 exports files containing up
    to 8 hours, so a longer session is partly unexportable. Long sessions also fill tablet memory,
    lengthen JSON generation and shorten the recharge interval.
    """
    hours = _num(candidate, "streaming_session_hours")
    if hours is None:
        return None
    return hours <= STREAM_EXPORT_MAX_HOURS


def _p_d48(candidate, participant):
    """Prefer transitions between two non-zero amplitudes over transitions through zero.

    Turning stimulation on or off while streaming costs a 7 second initialising period during which
    no data appears in the JSON export. The protocol should move between two non-zero amplitudes
    wherever the science allows, and any analysis must exclude those 7 seconds explicitly rather
    than assuming a wash-in window covers them.
    """
    through_zero = _flag(candidate, "transitions_through_zero")
    if through_zero is None:
        return None
    return not through_zero


def _p_d05(candidate, participant):
    """Whether the participant can operate the neurostimulator, which is a contraindication check.

    Only the operability half of D05 is machine-checkable from a participant record. The
    contraindicated procedures, diathermy, transcranial magnetic stimulation and certain MRI
    procedures using a full body transmit radio-frequency coil, are events rather than fields and
    are carried in the human text for the clinician to confirm.
    """
    return _flag(participant, "can_operate_neurostimulator")


# ------------------------------------------------------------------------------------------------
# Observed-value functions. These exist because ``DeviceConstraint.predicate`` is contracted to
# return only True, False or None, and a clinician reading a failure needs the numbers that produced
# it. Keeping them separate preserves that contract instead of widening the predicate return type.
# ------------------------------------------------------------------------------------------------
def _o_d01(c, p):
    return f"indication recorded as {p.get('indication')!r}"


def _o_d02(c, p):
    return f"indication {p.get('indication')!r}, intent {c.get('intent', 'adaptive')!r}"


def _o_d03(c, p):
    return f"programming mode recorded as {p.get('programming_mode')!r}"


def _o_d04(c, p):
    return f"n_neurostimulators recorded as {p.get('n_neurostimulators')!r}"


def _o_d08(c, p):
    edges = band_edges(c)
    low, high = permitted_band_hz(c)
    if edges is None:
        return (f"centre {c.get('center_hz')!r} Hz and width {c.get('band_width_hz')!r} Hz against "
                f"the {low}-{high} Hz window")
    return (f"band edges {edges[0]:.2f}-{edges[1]:.2f} Hz (centre {c.get('center_hz')} Hz, width "
            f"{c.get('band_width_hz')} Hz) against the {low}-{high} Hz window")


def _o_d09(c, p):
    bins = c.get("lfp_bins_uvp")
    if bins:
        edges = band_edges(c)
        inband = [(float(f), float(a)) for f, a in bins
                  if edges is None or (edges[0] <= float(f) < edges[1])]
        clear = [f for f, a in inband if a >= LFP_THRESHOLD_CAPTURE_FLOOR_UVP]
        peak = max((a for _, a in inband), default=None)
        band_txt = "the selected band" if edges is None else f"{edges[0]:.1f}-{edges[1]:.1f} Hz"
        if not inband:
            return f"no LFP survey bins fall inside {band_txt}"
        if clear:
            return (f"{len(clear)} of {len(inband)} bins in {band_txt} reach the "
                    f"{LFP_THRESHOLD_CAPTURE_FLOOR_UVP} uVp capture gate "
                    f"({', '.join(f'{x:.1f} Hz' for x in clear[:6])}); peak {peak:.2f} uVp")
        return (f"NO bin in {band_txt} reaches the {LFP_THRESHOLD_CAPTURE_FLOOR_UVP} uVp capture "
                f"gate; the largest is {peak:.2f} uVp across {len(inband)} bins. Threshold capture "
                f"is likely to be unreliable at this centre frequency even though the workflow is "
                f"not blocked")
    return (f"LFP amplitude {c.get('lfp_amplitude_uvp')!r} uVp against the "
            f"{LFP_THRESHOLD_CAPTURE_FLOOR_UVP} uVp gate; the auto-detection floor in the other "
            f"document is {LFP_AUTODETECT_FLOOR_UVP} uVp")


def _o_d10(c, p):
    return f"band width {c.get('band_width_hz')!r} Hz against a nominal {BAND_WIDTH_NOMINAL_HZ} Hz"


def _o_d11(c, p):
    return f"power_scale declared as {c.get('power_scale')!r}"


def _o_d12(c, p):
    return (f"centre {c.get('center_hz')!r} Hz, threshold mode {c.get('threshold_mode')!r}, pooled "
            f"across centre or mode: {c.get('pooled_across_center_or_mode')!r}")


def _o_d13(c, p):
    edges = band_edges(c)
    edge_text = "band edges not determinable" if edges is None else \
        f"band edges {edges[0]:.2f}-{edges[1]:.2f} Hz"
    return f"{edge_text} against a second high-pass at {c.get('highpass_hz')!r} Hz"


def _o_d15(c, p):
    return (f"channel {c.get('channel')!r}, declared a BrainSense Setup channel: "
            f"{c.get('channel_is_brainsense_setup_channel')!r}")


def _o_d16(c, p):
    return (f"impedance {c.get('impedance_ohms')!r} ohms on a {p.get('lead_type')!r} lead, "
            f"impedance test performed: {c.get('impedance_tested')!r}")


def _o_d17(c, p):
    return f"artifact_flags {c.get('artifact_flags')!r}"


def _o_d18(c, p):
    return f"threshold mode {c.get('threshold_mode')!r}, intent {c.get('intent', 'adaptive')!r}"


def _o_d19(c, p):
    return (f"power-versus-amplitude slope sign {c.get('power_slope_vs_amplitude_sign')!r} "
            f"(must be negative) and power-versus-pain slope sign "
            f"{c.get('power_slope_vs_pain_sign')!r} (must be positive)")


def _o_d24(c, p):
    return (f"capture amplitudes low {c.get('capture_amp_low_mA')!r} mA and high "
            f"{c.get('capture_amp_high_mA')!r} mA in {c.get('threshold_mode')!r} mode")


def _o_d27(c, p):
    return (f"capture high amplitude {c.get('capture_amp_high_mA', c.get('amp_mA'))!r} mA against "
            f"{CAPTURE_ARTEFACT_AMP_MA} mA and pulse width {c.get('pulse_width_us')!r} us against "
            f"{CAPTURE_ARTEFACT_PW_US} us")


def _o_d28(c, p):
    return (f"adaptive limits {c.get('adaptive_min_mA')!r} to {c.get('adaptive_max_mA')!r} mA")


def _o_d30(c, p):
    return f"frequency search closed: {c.get('frequency_search_closed')!r}"


def _o_d31(c, p):
    return (f"rate {c.get('rate_hz')!r} Hz and pulse width {c.get('pulse_width_us')!r} us against a "
            f"BrainSense minimum rate of {p.get('brainsense_min_rate_hz')!r} Hz, maximum rate of "
            f"{p.get('brainsense_max_rate_hz')!r} Hz and maximum pulse width of "
            f"{p.get('brainsense_max_pulse_width_us')!r} us")


def _o_d32(c, p):
    return (f"pocket adaptor {c.get('has_pocket_adaptor')!r}, multiple rates "
            f"{c.get('multiple_rates_in_group')!r}, interleaving {c.get('interleaving_in_group')!r}, "
            f"cycling {c.get('cycling_in_group')!r}, patient limits "
            f"{c.get('patient_limits_configured')!r}")


def _o_d34(c, p):
    return f"paused amplitude {c.get('paused_amplitude_mA')!r} mA"


def _o_d38(c, p):
    return (f"sensing hemisphere {c.get('sensing_hemisphere')!r}, actuated hemisphere "
            f"{c.get('actuated_hemisphere')!r}")


def _o_d39(c, p):
    return (f"sensing {c.get('sensing_hemisphere')!r} driving actuated "
            f"{c.get('actuated_hemisphere')!r}, dual lead implant {p.get('dual_lead_implant')!r}, "
            f"contralateral pairing acknowledged "
            f"{c.get('contralateral_pairing_acknowledged')!r}")


def _o_d40(c, p):
    return (f"threshold mode {c.get('threshold_mode')!r}, adaptive configured in both hemispheres "
            f"{p.get('adaptive_configured_both_hemispheres')!r}, coupling accepted "
            f"{p.get('accepts_cross_hemisphere_coupling')!r}")


def _o_d44(c, p):
    return f"rate {c.get('rate_hz')!r} Hz against a soft floor of {LOW_RATE_SOFT_FLOOR_HZ} Hz"


#: Rule identifier to observed-value function. A rule absent from this mapping simply has no
#: observed line in the report, which is the right outcome for the narrative rules.
_OBSERVED = {
    "D01": _o_d01, "D02": _o_d02, "D03": _o_d03, "D04": _o_d04, "D08": _o_d08, "D09": _o_d09,
    "D10": _o_d10, "D11": _o_d11, "D12": _o_d12, "D13": _o_d13, "D15": _o_d15, "D16": _o_d16,
    "D17": _o_d17, "D18": _o_d18, "D19": _o_d19, "D24": _o_d24, "D27": _o_d27, "D28": _o_d28,
    "D30": _o_d30, "D31": _o_d31, "D32": _o_d32, "D34": _o_d34, "D38": _o_d38, "D39": _o_d39,
    "D40": _o_d40, "D44": _o_d44,
}

#: Rules whose observed value is recorded on the report even when the rule PASSES.
#:
#: Deliberately small. D03 is here because a reader has to be able to see which programming regime
#: the report is written in: the same PASS means something different for a participant programmed in
#: Parkinson's mode than it would for one who is not. D04 and D31 are here because they are the two
#: rules whose values are unread today, so when a value finally is supplied the report should say
#: what it was rather than merely dropping the unknown. Recording every passing rule's value would
#: bury these three among twenty routine lines.
_RECORD_VALUE_ON_PASS = ("D03", "D04", "D31")


# ------------------------------------------------------------------------------------------------
# The rule table.
# ------------------------------------------------------------------------------------------------
RULES = (
    # -- 1. Indication and eligibility -----------------------------------------------------------
    types.DeviceConstraint(
        rule_id="D01",
        title="Chronic pain is not an approved indication for this device",
        source="WP", page="p. 37",
        severity="advisory",
        human_text=(
            "Medtronic DBS Therapy is approved for Parkinson's disease, essential tremor, dystonia, "
            "obsessive-compulsive disorder and epilepsy. Chronic pain is not among them, so "
            "everything this platform does with this participant is outside the approved "
            "labelling. This is advisory rather than blocking because it is the standing condition "
            "of the research programme rather than a defect in a candidate configuration, and it "
            "belongs on the face of every report rather than in a footnote."
        ),
        predicate=_p_d01,
    ),
    types.DeviceConstraint(
        rule_id="D02",
        title="Adaptive Therapy is labelled for the Parkinson's disease indication only",
        source="WP + A610", page="WP p. 1, WP p. 13, A610 p. 35",
        severity="advisory",
        human_text=(
            "The white paper's cover page and body both restrict BrainSense Adaptive DBS to the "
            "Parkinson's disease indication, and the programming guide describes it as a therapy "
            "option for that indication in patients with a single Percept neurostimulator. Like "
            "D01 this is a labelling statement about the participant rather than a property of a "
            "candidate configuration, so it is surfaced on every report. The operative gate is "
            "D03, which is what the software actually enforces."
        ),
        predicate=_p_d02,
    ),
    types.DeviceConstraint(
        rule_id="D03",
        title="On shipping software a participant not programmed in Parkinson's mode cannot finish "
              "Adaptive Therapy setup",
        source="WP", page="p. 9, p. 13 (workflow steps at A610 pp. 41-42)",
        severity="blocking",
        human_text=(
            "Non-Parkinson's patients are defaulted to Dual Threshold mode, cannot choose the "
            "threshold mode, and are not allowed to continue the workflow past the threshold "
            "capture step. The device will still record LFP power, still let a clinician capture "
            "two thresholds against two stimulation amplitudes, and still display the Timeline and "
            "LFP Chart; it will not automatically move amplitude. A recommendation made for such a "
            "participant is therefore a prepared configuration and not an executable one. For "
            "participant RCS08 this rule PASSES because that participant is programmed in "
            "Parkinson's mode and the Adaptive workflow is reachable, and the observed programming "
            "mode is recorded on the report so that a reader can see which regime it describes. It "
            "is kept blocking because it fails again for a participant programmed otherwise."
        ),
        predicate=_p_d03,
    ),
    types.DeviceConstraint(
        rule_id="D04",
        title="A single neurostimulator is required",
        source="A610", page="pp. 35-36",
        severity="unknown",
        human_text=(
            "Adaptive Therapy has only been studied in patients with a single Percept "
            "neurostimulator and should not be configured in patients who have two, because "
            "stimulation from the other neurostimulator may be misinterpreted as LFP signal and "
            "move the amplitude, bounded only by the Adaptive Amplitude Limits. The count has not "
            "been read for this participant, which is why the severity is 'unknown' and why this "
            "rule blocks: a bilateral implant delivered as two separate cans falls under the "
            "prohibition while a single can driving two leads does not, and the two cases cannot be "
            "distinguished from the records this module has been given."
        ),
        predicate=_p_d04,
    ),
    types.DeviceConstraint(
        rule_id="D05",
        title="General DBS contraindications",
        source="WP", page="p. 37",
        severity="advisory",
        human_text=(
            "DBS Therapy is contraindicated for patients unable to properly operate the "
            "neurostimulator. Diathermy, transcranial magnetic stimulation and certain MRI "
            "procedures using a full body transmit radio-frequency coil are contraindicated "
            "procedures. Only the operability half of this rule is a field on a participant "
            "record; the procedures are events, so they are listed here for a clinician to confirm "
            "rather than checked in code."
        ),
        predicate=_p_d05,
    ),
    types.DeviceConstraint(
        rule_id="D06",
        title="Tissue-damage warning attached to the parameters this module recommends",
        source="WP", page="p. 38",
        severity="advisory",
        human_text=(
            "There is a potential risk of brain tissue damage using stimulation parameter settings "
            "of high amplitudes and wide pulse widths. This module's output is exactly a pair of "
            "amplitudes and a pulse width, so the warning is on its critical path and is reproduced "
            "next to every recommended setting. It carries no predicate because the document states "
            "no numeric limit for it; the numeric ceilings that do exist are D27, D31 and D41."
        ),
        predicate=None,
    ),
    types.DeviceConstraint(
        rule_id="D07",
        title="Rebound on abrupt cessation constrains the lower adaptive limit",
        source="WP + A610-MD", page="WP p. 38, A610-MD p. 115",
        severity="advisory",
        human_text=(
            "Abrupt cessation of stimulation should be avoided because symptoms may return with "
            "intensity greater than before implant. The consequence for this module is that the "
            "minimum of the adaptive amplitude range is not a safe value merely because it is "
            "small, and a lower limit of zero means the controller is licensed to stop therapy "
            "entirely."
        ),
        predicate=_p_d07,
    ),

    # -- 2. What can be sensed, and in what units ------------------------------------------------
    types.DeviceConstraint(
        rule_id="D08",
        title="Adaptive Therapy is confined to the alpha-beta range, 8 to 30 Hz",
        source="A610 + WP", page="A610 p. 37, WP p. 14",
        severity="blocking",
        human_text=(
            "Adaptive Therapy is available only for electrode configurations with a signal of "
            "interest inside the alpha-beta range of 8 to 30 Hz; a sensing-only configuration uses "
            "1 to 96 Hz instead. It is the band EDGES that must fit, not the centre frequency, "
            "because the band is what the device sums power over. A 5 Hz band centred at 3.92 Hz, "
            "which is what the biomarker path selects for this participant, runs from 1.42 to "
            "6.42 Hz and is entirely below the floor, so it cannot drive Adaptive Therapy at all. A "
            "5 Hz band centred at 10 Hz also fails, on its lower edge, which is why checking the "
            "centre alone would let the wrong configurations through."
        ),
        predicate=_p_d08,
    ),
    types.DeviceConstraint(
        rule_id="D09",
        title="Minimum signal amplitude for threshold capture is 1.2 uVp",
        source="A610 (gate) and WP (auto-detection floor)",
        page="A610 p. 37, A610 p. 72; discrepant value at WP p. 8",
        #: PI decision 2026-09-04: ADVISORY, not blocking. The guide recommends rather than
        #: requires this amplitude, and the discrepancy between the two documents (1.2 vs 1.1 uVp)
        #: is unexplained, so refusing a configuration outright on a recommendation the
        #: manufacturer states two ways would be stronger than the evidence supports. The rule now
        #: reports WHICH frequency bins clear the gate and flags the shortfall for review rather
        #: than stopping the workflow. It is the one rule in this table that was deliberately
        #: softened, and the reason is recorded here so it is not silently hardened again.
        severity="advisory",
        human_text=(
            "To capture LFP thresholds and set up Adaptive Therapy the programming guide recommends "
            "an electrode configuration whose alpha-beta band LFP amplitude is greater than "
            "1.2 uVp, and it calls a signal below 1.2 uVp below the system minimum for "
            "auto-detection. The ADAPT-PD methodology paper calls 1.2 uVp the lowest acceptable "
            "power to run adaptive DBS. The white paper gives a different number, 1.1 uVp, as the "
            "floor above which the signal test automatically selects the largest peak. The two "
            "documents disagree and neither explains the difference, so this module gates on the "
            "more conservative 1.2 uVp, records 1.1 uVp as the auto-detection floor, and displays "
            "both. Which number governs a manually selected band is unresolved."
        ),
        predicate=_p_d09,
    ),
    types.DeviceConstraint(
        rule_id="D10",
        title="The band of interest is approximately 5 Hz wide",
        source="WP", page="p. 8",
        severity="advisory",
        human_text=(
            "The user selects a frequency band of interest approximately 5 Hz wide to track "
            "chronically. The document prints no adjustable range, so a width away from 5 Hz is "
            "surfaced and not refused, and the tolerance used to decide when to surface it belongs "
            "to this module rather than to the document. The value is kept in the constraints table "
            "rather than hard-coded in the analysis so that the two cannot drift apart."
        ),
        predicate=_p_d10,
    ),
    types.DeviceConstraint(
        rule_id="D11",
        title="LFP Power is a linear sum of squared magnitude, not a log quantity",
        source="A610 + WP", page="A610 p. 41, WP p. 9",
        severity="blocking",
        human_text=(
            "LFP Power is calculated as the sum of the squared LFP magnitude at each frequency in "
            "the selected band, similar to an area under the curve. It is presented in least "
            "significant bits, where one unit is approximately 0.01 microvolts squared. The "
            "biomarker path in this platform defaults to a log transform of band power, and a "
            "threshold placed on a log scale is NOT the threshold the device will apply, because "
            "the device thresholds the linear sum. Any threshold, separation statistic or receiver "
            "operating characteristic that claims to describe device behaviour has to be computed "
            "on the linear quantity. The log-scale versions remain valid as statistical "
            "descriptions and must be labelled as such."
        ),
        predicate=_p_d11,
    ),
    types.DeviceConstraint(
        rule_id="D12",
        title="Power values are not comparable across centre frequencies or threshold modes",
        source="WP", page="p. 9",
        severity="blocking",
        human_text=(
            "LFP power values from different centre frequencies should not be directly compared, "
            "and because the FFT size differs between Single Threshold and the other two modes, "
            "values collected in different threshold modes should not be compared either. The "
            "identity of a power column is therefore the triple of value, centre frequency and "
            "threshold mode, and an operation that pools across either is refused rather than "
            "warned about, because the pooled number looks like a measurement and is not one."
        ),
        predicate=_p_d12,
    ),
    types.DeviceConstraint(
        rule_id="D13",
        title="Sampling at 250 Hz with a second, user-configurable high-pass at 1 or 10 Hz",
        source="WP", page="p. 19, p. 11",
        severity="blocking",
        human_text=(
            "All recorded data is sampled at 250 Hz and passes two low-pass filters at 100 Hz and "
            "two high-pass filters, one fixed at 1 Hz and a second, user-configurable one at either "
            "1 Hz or 10 Hz set in the BrainSense Setup advanced settings. The frequency-domain "
            "content of a snapshot runs from 0 to 96.68 Hz, and the upper frequency displayed may "
            "be limited further by the stimulation frequency to avoid showing aliased stimulation "
            "artefacts. This blocks rather than advises because a band inside the second filter's "
            "stopband records an attenuated artefact of the filter setting rather than a signal: if "
            "that filter is at 10 Hz, the 3.92 Hz band this participant's biomarker path selects is "
            "in the stopband, and the amplitude that D09 would check is not a physiological "
            "measurement at all."
        ),
        predicate=_p_d13,
    ),
    types.DeviceConstraint(
        rule_id="D14",
        title="Power averaging is a unique, non-overlapping average",
        source="WP", page="p. 12",
        severity="advisory",
        human_text=(
            "The power averaging duration is not a moving average; each average contains a unique, "
            "non-overlapping set of data. Consecutive power samples therefore share no raw data, "
            "which is worth stating because it is the assumption an effective-sample-size "
            "calculation would use. They remain serially correlated through the underlying "
            "physiology, so independence of the raw windows is not independence of the samples."
        ),
        predicate=None,
    ),
    types.DeviceConstraint(
        rule_id="D15",
        title="Only a BrainSense Setup channel can become a control signal",
        source="WP", page="p. 18, Table 1",
        severity="blocking",
        human_text=(
            "BrainSense Setup's signal check offers 3 channels per hemisphere on both 1x4 and "
            "SenSight leads, while Electrode Survey offers 6 or 15, Electrode Identifier 4 or 10, "
            "and Timeline, Events and Streaming one each per hemisphere. Only the Setup channels "
            "can become a control signal, so a band chosen on a survey channel is not deployable "
            "however well it performs. Which contact pairs count as Setup channels depends on the "
            "lead and is not printed in the supplied documents, so the caller declares it rather "
            "than this module inferring it from the channel name."
        ),
        predicate=_p_d15,
    ),
    types.DeviceConstraint(
        rule_id="D16",
        title="Impedance gates the sensing channel, and the test is a precondition",
        source="WP + A610", page="WP p. 8, A610 p. 36, A610 p. 47",
        severity="blocking",
        human_text=(
            "The device excludes sense channels with potential shorts, below 250 ohms for 1x4 leads "
            "or 350 ohms for SenSight leads, and potential opens above 10 kilohms. An impedance "
            "test is required before BrainSense setup can proceed. The test itself runs at 80 "
            "microseconds and 100 Hz at 0.1, 0.4 or 1.0 mA, rising to 450 microseconds if impedance "
            "measures higher than normal. An untested channel fails this rule even when a stored "
            "impedance value happens to be in range, because the stored value may predate the "
            "current lead state."
        ),
        predicate=_p_d16,
    ),
    types.DeviceConstraint(
        rule_id="D17",
        title="Artefact classes the device itself detects",
        source="WP + A610", page="WP pp. 19-20, A610 p. 72",
        severity="blocking",
        human_text=(
            "The clinician application flags cardiac artefact, which appears as a large-amplitude 1 "
            "to 2 Hz signal, and motion artefact, which appears as large non-periodic amplitude "
            "excursions during movement, and it may also flag a signal that is simply unlike a "
            "typical LFP, such as the large low-frequency oscillations seen under anaesthesia. "
            "Using a configuration with an artefact detected may interfere with capturing "
            "meaningful BrainSense information and may affect Adaptive Therapy performance. An "
            "empty flag list is a positive statement that the device flagged nothing; an absent "
            "field is not, and is treated as not determinable."
        ),
        predicate=_p_d17,
    ),

    # -- 3. Threshold modes and what each can drive ----------------------------------------------
    types.DeviceConstraint(
        rule_id="D18",
        title="Three threshold modes exist and only two can drive therapy",
        source="A610 + WP", page="A610 p. 39, WP p. 13, WP p. 14",
        severity="blocking",
        human_text=(
            "Adaptive Therapy can be configured in Dual Threshold or Single Threshold mode. Single "
            "Threshold Inverse is available only in a Sensing Only configuration. Naming Single "
            "Threshold Inverse in an adaptive recommendation is a category error rather than a "
            "marginal choice, so it blocks."
        ),
        predicate=_p_d18,
    ),
    types.DeviceConstraint(
        rule_id="D19",
        title="The control polarity of the two therapy-driving modes is fixed and cannot be inverted",
        source="A610 + WP", page="A610 p. 38, WP p. 14",
        severity="blocking",
        human_text=(
            "In both Dual and Single Threshold the amplitude ramps UP when the LFP passes above "
            "threshold, and the white paper states the precondition as a requirement on the signal: "
            "when stimulation is high, the LFP must be suppressed compared with when stimulation is "
            "low. The one mode with the opposite relationship, Single Threshold Inverse, is the one "
            "that cannot deliver therapy. For a pain biomarker this is a hard sign constraint and it "
            "is separate from the amplitude-response requirement: band power must FALL as amplitude "
            "rises and RISE as pain rises. A band whose power falls as pain rises cannot drive "
            "Adaptive Therapy in either direction, and no choice of thresholds repairs it."
        ),
        predicate=_p_d19,
    ),
    types.DeviceConstraint(
        rule_id="D20",
        title="Per-mode timing parameters and defaults",
        source="WP + A610", page="WP p. 14 Table 1, A610 p. 38, A610 p. 42",
        severity="advisory",
        human_text=(
            "The two therapy-driving modes differ throughout: FFT size 256 against 64 points, "
            "adaptive update rate 5 Hz against 20 Hz, averaging 1200 ms against 100 ms, onset "
            "1200 ms against 200 ms, detection blanking 2000 ms against 550 ms, and transition "
            "durations of 2.5 and 5 minutes against 250 ms in each direction. Dual Threshold sets "
            "its two thresholds manually while both single modes compute one as 0.75 times the "
            "difference between the captures added to the lower capture. The full table is exposed "
            "as THRESHOLD_MODE_TABLE so that downstream code reads it rather than restating it. "
            "This is advisory because the device supplies these defaults itself and the adjustable "
            "ranges are not printed, so a declared value that differs is worth seeing rather than "
            "wrong."
        ),
        predicate=_p_d20,
    ),
    types.DeviceConstraint(
        rule_id="D21",
        title="Programmable range of the onset duration is published only in the trial paper",
        source="ADAPT-PD", page="Stanslaski et al. 2024",
        severity="advisory",
        human_text=(
            "Neither Medtronic document prints the adjustable range of the onset duration; both "
            "give only the default. The ADAPT-PD methodology paper states a range of 1.2 to 2 "
            "seconds in dual threshold mode and 200 to 500 milliseconds in single threshold mode. "
            "These are the only published ranges found and they are labelled as coming from the "
            "trial paper rather than from the device labelling, which is why a value outside them "
            "is surfaced rather than refused."
        ),
        predicate=_p_d21,
    ),
    types.DeviceConstraint(
        rule_id="D22",
        title="Adaptive amplitude behaviour differs between the two therapy-driving modes",
        source="ADAPT-PD + WP", page="Stanslaski et al. 2024, WP p. 13",
        severity="advisory",
        human_text=(
            "In single threshold mode the device adjusted amplitude over 250 ms between the upper "
            "and lower stimulation limits, producing a trapezoidal pattern that reaches the limits. "
            "In dual threshold mode it moved more slowly and each adjustment was incremental rather "
            "than ramping fully between the limits, and while the LFP remains between the two "
            "thresholds the amplitude is held at whatever value it had when the LFP entered that "
            "state. Which mode is chosen therefore changes the dose the participant receives as "
            "much as the thresholds do."
        ),
        predicate=None,
    ),
    types.DeviceConstraint(
        rule_id="D23",
        title="One threshold mode per group",
        source="A610", page="p. 39",
        severity="advisory",
        human_text=(
            "The same threshold mode is used for all adaptive programs in a group. This is surfaced "
            "rather than enforced because this evaluator is handed a single candidate configuration "
            "and cannot see the group's other programs; when the caller declares them in "
            "group_threshold_modes the check returns a real verdict."
        ),
        predicate=_p_d23,
    ),

    # -- 4. Threshold capture --------------------------------------------------------------------
    types.DeviceConstraint(
        rule_id="D24",
        title="Dual Threshold capture requires two therapeutic amplitudes in a defined order",
        source="A610 + WP", page="A610 p. 40 Table 5, WP p. 15",
        severity="blocking",
        human_text=(
            "Set the amplitude to the lower limit of therapeutic benefit and capture the Upper LFP "
            "Threshold there, then increase to the upper limit of therapeutic benefit and capture "
            "the Lower LFP Threshold there. The naming is crossed deliberately: the upper threshold "
            "is recorded at the lower amplitude because power is expected to be higher when "
            "stimulation is lower. A caller who swaps the two produces the inverted capture the "
            "device refuses, so the ordering is checked here rather than discovered at the visit. In "
            "Single Threshold only the upper therapeutic amplitude is supplied by the clinician, "
            "because the device captures the second signal itself at 0 mA."
        ),
        predicate=_p_d24,
    ),
    types.DeviceConstraint(
        rule_id="D25",
        title="Single Threshold capture uses one therapeutic amplitude and a forced zero",
        source="A610 + WP", page="A610 p. 40, WP p. 15",
        severity="advisory",
        human_text=(
            "In Single Threshold mode the clinician increases to the upper limit of therapeutic "
            "benefit and captures, and the application then automatically captures a second LFP "
            "signal with amplitude set to 0 mA and generates one threshold at 75 percent of the "
            "difference added to the lower capture. This mode is unavailable to a participant not "
            "programmed in Parkinson's mode under D03, and for a pain participant it would in any "
            "case force a 0 mA exposure, which the objective specification for this project records "
            "as a qualitatively different therapeutic state rather than the low end of the dose "
            "axis. The advisory fires whenever Single Threshold is proposed."
        ),
        predicate=_p_d25,
    ),
    types.DeviceConstraint(
        rule_id="D26",
        title="Capture failure modes are named by the device and can be predicted in advance",
        source="WP + A610", page="WP p. 15, A610 p. 73",
        severity="advisory",
        human_text=(
            "The thresholds the system gathers can be too close together or inverted, in which case "
            "the application prompts for recapture or manual adjustment, and a RECAPTURE THRESHOLDS "
            "alert appears when the LFP is minimally responsive to changes in stimulation "
            "amplitude. If no electrode configuration produces successfully captured thresholds, "
            "the guide says Adaptive Therapy may not be optimal for the patient. Both failure "
            "conditions are quantities this module already estimates: an inverted capture is the "
            "case where the amplitude-to-power slope has the wrong sign, and a too-close capture is "
            "the case where the separation between the two amplitudes is small relative to the "
            "noise. So the alert is predicted before the visit rather than met at one."
        ),
        predicate=_p_d26,
    ),
    types.DeviceConstraint(
        rule_id="D27",
        title="Stimulation artefact contaminates the capture above 5 mA or 120 us",
        source="A610", page="p. 73",
        severity="blocking",
        human_text=(
            "If the stimulation level is above 5 mA or 120 microseconds, the artefact of "
            "stimulation may make the LFP appear elevated when the Lower LFP Threshold is captured. "
            "This is a measurement-validity ceiling on the capture procedure and it is distinct "
            "from any safety ceiling; the fact that 5 mA coincides with the flat per-hemisphere "
            "amplitude limit this project adopted is a coincidence and not a derivation. A capture "
            "above either value is artefact-suspect and its Lower LFP Threshold must not be treated "
            "as a physiological measurement. For this participant the recorded pulse width is "
            "asymmetric between hemispheres, most commonly 60 microseconds on the left and 160 on "
            "the right, so right-hemisphere captures fail this rule as programmed today."
        ),
        predicate=_p_d27,
    ),
    types.DeviceConstraint(
        rule_id="D28",
        title="Adaptive Amplitude Limits inherit the capture amplitudes",
        source="A610 + WP + ADAPT-PD", page="A610 p. 41, WP p. 15, Stanslaski et al. 2024",
        severity="blocking",
        human_text=(
            "The Adaptive Amplitude Limits default to the stimulation amplitudes used when "
            "capturing the LFP thresholds, and they are adjustable. When BrainSense status changes "
            "from Adaptive to Sensing Only for all adaptive programs in a group, those limits "
            "become patient limits. ADAPT-PD set them as the minimum and maximum safe amplitudes "
            "that provide adequate therapy while staying below the amplitude that causes "
            "stimulation-induced adverse effects. The consequence is that choosing the two capture "
            "amplitudes is simultaneously a measurement decision and a therapeutic-range decision, "
            "so this module cannot recommend one without the other, and the limits are required "
            "here rather than left to the visit."
        ),
        predicate=_p_d28,
    ),
    types.DeviceConstraint(
        rule_id="D29",
        title="Configuration changes destroy calibration, and aligned segments must match",
        source="A610", page="p. 37, p. 39",
        severity="blocking",
        human_text=(
            "Changing the electrode configuration resets amplitude to zero and clears the captured "
            "thresholds and the BrainSense configuration. Later in the workflow, changing it may "
            "clear the patient limits and the amplitudes used to capture the thresholds while the "
            "thresholds themselves are retained, which silently detaches a threshold from the "
            "calibration that produced it and is the most dangerous of the workflow hazards here. "
            "The machine-checkable part is the other sentence on the same page: vertically aligned "
            "segments must have the same amplitude and electrode polarity when BrainSense is "
            "configured."
        ),
        predicate=_p_d29,
    ),

    # -- 5. What freezes once sensing is configured ----------------------------------------------
    types.DeviceConstraint(
        rule_id="D30",
        title="Pulse width and rate become unadjustable once BrainSense is set up",
        source="A610", page="p. 34 footnote a, p. 44",
        severity="blocking",
        human_text=(
            "Pulse width and rate cannot be adjusted once BrainSense has been set up for either "
            "hemisphere. Re-enabling those patient limits requires removing BrainSense from the "
            "group, which means deleting the group and reprogramming it without BrainSense, or "
            "changing the electrode configuration, which by D29 also clears the captured "
            "thresholds. Frequency is a searched dimension in the StimOptimizer grid and it stops "
            "being searchable the moment a BrainSense group is committed, so the open-loop "
            "frequency search and the closed-loop configuration are sequential and not concurrent. "
            "This rule is where that ordering is enforced: a candidate whose frequency search is "
            "not closed is not deployable, because committing it would freeze a rate nobody has "
            "finished choosing."
        ),
        predicate=_p_d30,
    ),
    types.DeviceConstraint(
        rule_id="D31",
        title="A BrainSense group has a narrower parameter envelope whose values are unpublished",
        source="A610", page="p. 34, p. 35; general envelope at A610-MD p. 119",
        severity="unknown",
        human_text=(
            "For a group configured with BrainSense the maximum pulse width and maximum rate are "
            "lower, and the minimum rate is HIGHER, than for a group without BrainSense, and the "
            "same sentence is repeated for Adaptive Therapy specifically. Neither document states "
            "any of the three numbers, and a search of all 124 decoded programming-guide pages and "
            "all 40 white-paper pages returned no such figure. The general Percept envelope is "
            "amplitude 0 to 25.5 mA in 0.1 mA steps or 0 to 12.5 mA in 0.05 mA steps, pulse width "
            "20 to 450 microseconds in 10 microsecond steps, and rate 2 to 250 Hz, so passing that "
            "envelope is necessary and not sufficient. This is decisive for this participant, whose "
            "incumbent rate is 55 Hz and one of whose four licensed configurations is at 55 Hz: if "
            "the BrainSense minimum rate exceeds 55 Hz, that configuration cannot be programmed at "
            "all. The value can be read straight off the rate control once a BrainSense group "
            "exists, and doing so should be the first item on the next programming visit's "
            "checklist."
        ),
        predicate=_p_d31,
    ),
    types.DeviceConstraint(
        rule_id="D32",
        title="Feature exclusions for BrainSense and Adaptive groups",
        source="A610", page="p. 34, p. 35",
        severity="blocking",
        human_text=(
            "BrainSense cannot be configured in a hemisphere that includes a pocket adaptor. "
            "BrainSense and Multiple Rates cannot be used in a single group simultaneously. "
            "Interleaving is not available in groups with BrainSense configured, and neither "
            "interleaving nor cycling is available in groups with Adaptive Therapy. Patient limits, "
            "which let a patient adjust a parameter from their own programmer, are not available "
            "with Adaptive Therapy, which uses its own limits set in the BrainSense Setup workflow "
            "and not adjustable by the patient. Every one of these is phrased as an impossibility, "
            "so any one of them disqualifies, and all of them must be declared, because an "
            "undeclared exclusion is exactly what gets discovered at the programming visit."
        ),
        predicate=_p_d32,
    ),
    types.DeviceConstraint(
        rule_id="D33",
        title="What the patient can still do under Adaptive Therapy",
        source="A610 + WP", page="A610 p. 35, p. 43, WP p. 13",
        severity="advisory",
        human_text=(
            "Under Adaptive Therapy the patient can turn stimulation on and off, pause and resume "
            "Adaptive Therapy, and switch groups. The patient cannot directly increase or decrease "
            "amplitude, and cannot do so even while Adaptive Therapy is paused; adjusting amplitude "
            "requires switching to a group set to Sensing Only or Off. This holds even when only "
            "one hemisphere has BrainSense status set to Adaptive. It is recorded because it changes "
            "what self-management the participant retains during a closed-loop trial, which is a "
            "consent and protocol matter rather than a configuration check."
        ),
        predicate=None,
    ),
    types.DeviceConstraint(
        rule_id="D34",
        title="The Paused Amplitude is a required safety parameter",
        source="A610", page="p. 35, p. 43",
        severity="blocking",
        human_text=(
            "Setting the Paused Amplitude is necessary to ensure that patients can pause Adaptive "
            "Therapy because of stimulation-related side effects or a loop that is not performing. "
            "It is also the amplitude the participant receives during every automatic pause, "
            "including each recharging session, so it is the therapy actually delivered during "
            "scheduled controller outages rather than an edge case. It must be declared and, for "
            "the reason D07 gives, must not be zero."
        ),
        predicate=_p_d34,
    ),

    # -- 6. When the loop is not running ---------------------------------------------------------
    types.DeviceConstraint(
        rule_id="D35",
        title="Automatic suspensions of BrainSense and Adaptive Therapy",
        source="A610 + WP", page="A610 pp. 35-36, WP p. 13",
        severity="advisory",
        human_text=(
            "BrainSense is automatically disabled in MRI mode and during a recharging session, and "
            "re-enabled afterwards. No LFP data is recorded during an impedance test and Adaptive "
            "Therapy is temporarily disabled during one. Adaptive Therapy is automatically paused "
            "during recharging and resumed afterwards, and it is not an eligible stimulation option "
            "in MRI mode, so entering MRI mode requires turning stimulation off for the adaptive "
            "group or switching to a group with a bipolar configuration. The consequence for the "
            "report is that a deployment must state the expected DUTY CYCLE of the loop and not "
            "only its configuration: for a rechargeable device the recharge schedule is a scheduled "
            "outage of the controller, and the Paused Amplitude is the therapy delivered during it."
        ),
        predicate=None,
    ),
    types.DeviceConstraint(
        rule_id="D36",
        title="The recharge interval calculator cannot model Adaptive Therapy",
        source="WP", page="p. 19",
        severity="advisory",
        human_text=(
            "Because Adaptive Therapy cannot be predicted, the recharge interval calculator "
            "requires Adaptive Therapy to be paused in order to be used. Any recharge-interval "
            "estimate this module displays for an adaptive configuration is therefore an estimate "
            "for the PAUSED configuration and has to be labelled that way, or it will be read as an "
            "estimate of something nobody computed."
        ),
        predicate=None,
    ),
    types.DeviceConstraint(
        rule_id="D37",
        title="Electromagnetic interference can move the stimulation amplitude",
        source="A610", page="p. 35",
        severity="advisory",
        human_text=(
            "Electromagnetic interference may be misinterpreted as LFP signal during sensing and "
            "cause an increase or decrease in stimulation amplitude, although the amplitude stays "
            "inside the clinician-defined Adaptive Amplitude Limits. The remedies offered are to "
            "move away from the source, pause Adaptive Therapy, switch groups, or turn stimulation "
            "off. Adaptive Therapy has not been studied in patients with other active implanted "
            "devices. This is one more reason the two amplitude limits are a safety decision and "
            "not merely a range."
        ),
        predicate=None,
    ),

    # -- 7. Hemisphere scope ---------------------------------------------------------------------
    types.DeviceConstraint(
        rule_id="D38",
        title="BrainSense and Adaptive Therapy are hemisphere-specific",
        source="A610", page="p. 44",
        severity="blocking",
        human_text=(
            "Adaptive Therapy is a hemisphere-specific feature, and disabling it for a whole group "
            "means repeating the process for the other hemisphere; the same is true of BrainSense. "
            "A candidate configuration must therefore name both the hemisphere it senses from and "
            "the hemisphere it actuates, because a configuration that names only one is ambiguous "
            "about what it is asking the device to do."
        ),
        predicate=_p_d38,
    ),
    types.DeviceConstraint(
        rule_id="D39",
        title="Contralateral sensing is supported, as a documented fallback",
        source="A610", page="p. 37, p. 39",
        severity="blocking",
        human_text=(
            "For dual lead implants only, when the hemisphere contralateral to the selected one has "
            "been set up for BrainSense it appears on the Signal Test screen as a sensing option, "
            "and selecting it uses that hemisphere's sensing data to drive Adaptive Therapy for the "
            "selected hemisphere. The guide states the intent plainly: it is for situations where "
            "configurations on the currently selected lead are not acceptable for sensing setup, "
            "for example when electrode 0, electrode 3 or bipolar stimulation is desired. In Dual "
            "Threshold mode amplitude is driven from the same hemisphere unless a contralateral "
            "sensing configuration is set up. So a contralateral pairing must be marked as the "
            "fallback it is rather than treated as equivalent to an ipsilateral one, and it "
            "requires a dual lead implant. The distinction is live on the present data: the current "
            "screen holds 25 ipsilateral and 25 contralateral pairings among its 50 usable cells, "
            "and two of the four configurations it licenses are contralateral."
        ),
        predicate=_p_d39,
    ),
    types.DeviceConstraint(
        rule_id="D40",
        title="Single Threshold mode couples the hemispheres",
        source="A610", page="p. 39",
        severity="blocking",
        human_text=(
            "If both hemispheres have an Adaptive Therapy program configured in Single Threshold "
            "mode, sensing LFP data from EITHER hemisphere will drive Adaptive Therapy. That "
            "invalidates the one-sensing-channel-drives-one-actuated-hemisphere model the candidate "
            "record otherwise expresses, and it means a bilateral single-threshold configuration is "
            "one controller with two inputs rather than two independent controllers. It is not a "
            "prohibition, so the rule passes when the coupling is explicitly accepted and fails "
            "when it is present and unacknowledged, because then the report would describe a "
            "controller the device is not going to run. Under D03 this mode is unavailable to a "
            "participant not programmed in Parkinson's mode, but the rule still has to be encoded, "
            "because it becomes live the moment the indication question is resolved."
        ),
        predicate=_p_d40,
    ),

    # -- 8. Amplitude, charge and energy ---------------------------------------------------------
    types.DeviceConstraint(
        rule_id="D41",
        title="Charge density above 30 microcoulombs per square centimetre per phase",
        source="A610 (limit) and SL (lead area)", page="A610 p. 22, SL p. 10",
        severity="advisory",
        human_text=(
            "A survey of the literature on electrical stimulation of neural tissue suggests damage "
            "may occur above 30 microcoulombs per square centimetre per phase, and the Medtronic "
            "DBS system is capable of producing charge densities in excess of that. A warning "
            "appears and can be acknowledged and overridden, and programmed patient limits are "
            "counted when charge density is computed, so an upper limit alone can trigger it. The "
            "calculation cannot be reproduced here: the lead specification gives the lead-level "
            "surface area, 13.55 square centimetres for the 33 cm lead and 17.26 for the 42 cm "
            "lead, not the per-electrode area a charge-density calculation needs. So the module "
            "displays the device's own charge-density state rather than recomputing it, and this "
            "rule checks that the state has been recorded."
        ),
        predicate=_p_d41,
    ),
    types.DeviceConstraint(
        rule_id="D42",
        title="Out-of-range delivery is a silent underdelivery failure mode",
        source="A610", page="p. 22",
        severity="advisory",
        human_text=(
            "Certain combinations of amplitude, pulse width and rate are too high for the system to "
            "provide in its current state, producing an alert that stimulation is not being "
            "provided at the level shown, and on a rechargeable device a low battery can cause "
            "this. It matters here because every analysis in this platform assumes the programmed "
            "amplitude equals the delivered amplitude, and this is the documented mechanism by "
            "which that assumption fails without anyone noticing."
        ),
        predicate=None,
    ),
    types.DeviceConstraint(
        rule_id="D43",
        title="Lead electrical specifications, including a lead-length amplitude ceiling",
        source="SL", page="p. 10",
        severity="advisory",
        human_text=(
            "SenSight models B33005 and B33015 have an expected lifetime of 5 years, a maximum "
            "conductor resistance of 100 ohms at all lengths, lengths of 33 and 42 cm, surface "
            "areas of 13.55 and 17.26 square centimetres, a diameter of 1.36 mm, a straight shape, "
            "8 cylindrical distal electrodes with a 1.0 mm distal tip distance, 8 in-line proximal "
            "contacts at 2.2 mm spacing, and polyurethane and platinum iridium construction. The "
            "footnote states that electrical resistance is proportional to lead length and that "
            "long lengths have higher resistance that may limit the amplitude, which is a "
            "per-participant amplitude ceiling depending on which lead length was implanted."
        ),
        predicate=None,
    ),
    types.DeviceConstraint(
        rule_id="D44",
        title="Rates below 30 Hz should not be programmed",
        source="A610-MD", page="p. 115",
        severity="advisory",
        human_text=(
            "The use of rates below 30 Hz may drive tremor, that is, cause it to occur at the same "
            "frequency as the programmed frequency, and for that reason rates should not be "
            "programmed below 30 Hz. This is written for movement disorders and its relevance to a "
            "pain participant is not established by the document, but it is the only published rate "
            "floor, so it is carried as a soft floor with the citation attached rather than as a "
            "gate."
        ),
        predicate=_p_d44,
    ),
    types.DeviceConstraint(
        rule_id="D45",
        title="Battery cost of the two adaptive modes",
        source="WP", page="p. 19",
        severity="advisory",
        human_text=(
            "In the ADAPT-PD study, using Percept PC devices, Dual Threshold patients showed a "
            "median longevity improvement against conventional DBS of 5 percent per year while "
            "Single Threshold patients showed a median reduction of 4 percent per year. For a "
            "rechargeable device a one hour streaming session results in approximately 6 percent "
            "battery drain, and long telemetry sessions shorten the recharge interval without "
            "affecting overall service life. This is recorded because the choice of threshold mode "
            "has a maintenance cost for the participant as well as a control-theoretic one."
        ),
        predicate=None,
    ),

    # -- 9. Data collection capacity and cadence -------------------------------------------------
    types.DeviceConstraint(
        rule_id="D46",
        title="Snapshot and event capacity, with silent overwrite",
        source="WP", page="p. 11",
        severity="advisory",
        human_text=(
            "Percept RC records up to 200 LFP snapshots, for example 100 per hemisphere if "
            "bilateral, and stores up to 800 non-LFP events, and when the maximum is exceeded the "
            "older snapshots are overwritten. A snapshot is approximately 30 seconds of 250 Hz "
            "time-domain data collected after the patient event is received, converted to the "
            "frequency domain, with only the averaged frequency-domain content stored and the time "
            "domain discarded. The store is a circular buffer with a hard capacity, so a study that "
            "relies on patient-marked events has to schedule downloads against the 100 per "
            "hemisphere ceiling or lose data with no error anywhere."
        ),
        predicate=_p_d46,
    ),
    types.DeviceConstraint(
        rule_id="D47",
        title="Streaming export limits and the tablet's screen timeout",
        source="WP", page="p. 12",
        severity="advisory",
        human_text=(
            "A610 version 5.0 supports exporting files with up to 8 hours of streaming data. There "
            "is no maximum streaming duration, but long sessions fill tablet memory, lengthen JSON "
            "generation and shorten the recharge interval. The tablet screen must be kept awake; "
            "for a Percept RC the clinician application keeps it awake for one additional hour, "
            "after which user interaction at least every 10 minutes is required. A session longer "
            "than the export ceiling is therefore partly unexportable."
        ),
        predicate=_p_d47,
    ),
    types.DeviceConstraint(
        rule_id="D48",
        title="Turning stimulation on or off while streaming creates a seven-second hole",
        source="WP", page="p. 20",
        severity="advisory",
        human_text=(
            "With A610 v5.0, turning stimulation on or off while streaming causes a 7 second "
            "initialising period during which data is not available in the JSON export. The "
            "titration protocol should therefore move between two non-zero amplitudes rather than "
            "through zero wherever the science allows it, and any analysis must exclude those 7 "
            "seconds after each transition explicitly rather than assuming a wash-in window covers "
            "them."
        ),
        predicate=_p_d48,
    ),
    types.DeviceConstraint(
        rule_id="D49",
        title="Home streaming cadence as instructed to this participant",
        source="PTG", page="p. 16",
        severity="advisory",
        human_text=(
            "The patient guide instructs the patient to keep the communicator within three feet, "
            "notes that the screen stays on for 60 minutes and must then be touched, states that "
            "data cannot be recorded when the screen is off, and asks the patient to try to stream "
            "for 30 to 60 minutes once a day. That is the actual sampling cadence available for any "
            "home-collected control signal, and it bounds what a between-visit study can observe, "
            "so a design that assumes continuous home data is assuming something the instructions "
            "do not provide."
        ),
        predicate=None,
    ),

    # -- 10. The device's own amplitude-response procedure ----------------------------------------
    types.DeviceConstraint(
        rule_id="D50",
        title="The manufacturer prescribes a specific titration, and it is short",
        source="A610", page="p. 45, p. 72",
        severity="advisory",
        human_text=(
            "Under the heading for using LFP streaming data to view real-time effects of "
            "stimulation, the guide says to pause Adaptive Therapy if configured, set amplitude to "
            "0.0 mA for 45 to 60 seconds to establish a physiologic baseline, start streaming, "
            "increase stimulation by 0.1 to 0.5 mA per step with a ramp interval adjustable from "
            "0.5 to 10 seconds, stream for 30 to 45 seconds after each adjustment to determine the "
            "effect on LFP power, and then explore the correlation between patient symptoms and LFP "
            "reduction. The troubleshooting table recommends the same procedure when no responsive "
            "signal is found. This is the measurement the deployability screen approximates from "
            "historical data. It takes well under an hour per channel to perform directly and it is "
            "free of the amplitude-versus-time confound by construction, so the retrospective "
            "estimate should be treated as a way of choosing which channels to titrate rather than "
            "as a substitute for titrating them."
        ),
        predicate=None,
    ),
    types.DeviceConstraint(
        rule_id="D51",
        title="The device names its own closed-loop failure modes and their remedies",
        source="A610", page="pp. 73-74 (Timeline observable at p. 39, p. 56)",
        severity="advisory",
        human_text=(
            "The troubleshooting table enumerates four adaptive failure states and what to change "
            "for each. For stimulation chronically too low: raise the maximum amplitude limit if "
            "the Timeline shows it stuck at the upper limit, otherwise lower the upper LFP "
            "threshold, then the lower LFP threshold, then raise the minimum amplitude limit. For "
            "stimulation transiently too low: lengthen Transition Down, shorten Transition Up, "
            "decrease Upper Onset and increase Lower Onset, then raise the minimum amplitude limit, "
            "then decrease Detection Blanking. The two chronically and transiently too high states "
            "are the mirror images. Repeated ramping to the upper limit immediately after reaching "
            "the lower limit in Single Threshold mode is fixed by increasing the Detection Blanking "
            "Duration, and a transient jump to the upper limit immediately after resuming is fixed "
            "by increasing the Adaptive Startup Delay. These are the diagnostic states the "
            "deployment panel should predict and, once the loop runs, report against, and the "
            "observable that discriminates them is the Timeline percentage of time above, between "
            "and below thresholds."
        ),
        predicate=None,
    ),
)


#: Rule identifier to rule, for callers that want one rule rather than the whole table.
RULES_BY_ID = {rule.rule_id: rule for rule in RULES}


# ------------------------------------------------------------------------------------------------
# The evaluator.
# ------------------------------------------------------------------------------------------------
def _observe(rule_id, candidate, participant):
    """Return the observed-values line for a rule, or an empty string when it has none.

    A failure in an observed-value function must not be able to suppress the verdict it is
    describing, so anything raised here is reported in place of the values rather than propagated.
    """
    fn = _OBSERVED.get(rule_id)
    if fn is None:
        return ""
    try:
        return fn(candidate if isinstance(candidate, dict) else {},
                  participant if isinstance(participant, dict) else {})
    except Exception as exc:                                    # noqa: BLE001 - see docstring
        return f"observed values could not be rendered: {exc!r}"


def _entry(rule, kind, why, observed):
    """Build one report row.

    The four keys ``types.EligibilityReport`` documents (rule_id, severity, why, page) are always
    present. The rest are additions a reader needs in practice: the title so the row is legible
    without the table to hand, the source tag so the page number means something, ``kind`` so that
    the two very different reasons a rule can be unknown are distinguishable, and ``observed`` so
    that a clinician sees the numbers that produced the verdict rather than only the rule.
    """
    return {
        "rule_id": rule.rule_id,
        "severity": rule.severity,
        "why": why,
        "page": rule.page,
        "title": rule.title,
        "source": rule.source,
        "kind": kind,
        "observed": observed,
    }


def check_eligibility(candidate, participant, rules=None) -> types.EligibilityReport:
    """Evaluate every device rule against one candidate configuration.

    ALL rules are evaluated and every failure is returned. The evaluator does not stop at the first
    blocker, because a clinician who fixes one blocker should not have to re-run the screen to
    discover the next one; on a device where changing the electrode configuration clears the
    captured thresholds (D29), an iteration of that kind can cost a whole programming visit.

    A candidate is eligible only when there are no failures AND no unknowns. Unknowns block for the
    reason the module docstring gives: a rule that could not be evaluated has not been satisfied,
    and reporting it as anything other than a blocker would let a configuration look licensed
    because nobody measured the thing that would have stopped it. Advisories never affect
    eligibility.

    Parameters
    ----------
    candidate : dict
        One configuration. ``CANDIDATE_KEYS`` lists every key any predicate reads and names the
        rules that read it. Absent keys are not determinable, never passes.
    participant : dict
        The participant record. ``PARTICIPANT_KEYS`` lists the keys read.
    rules : iterable of types.DeviceConstraint, optional
        Defaults to the full table. Present so that a caller can evaluate a subset and so that the
        tests can exercise the evaluator's own behaviour with a synthetic rule.

    Returns
    -------
    types.EligibilityReport
        ``checked`` counts every rule evaluated, so it equals the size of the table whatever the
        outcome, which is how a reader can tell that nothing was skipped.
    """
    table = tuple(RULES if rules is None else rules)
    cand = candidate if isinstance(candidate, dict) else {}
    part = participant if isinstance(participant, dict) else {}

    report = types.EligibilityReport(eligible=True)

    for rule in table:
        report.checked += 1
        observed = _observe(rule.rule_id, cand, part)

        if rule.predicate is None:
            verdict = None
            error = None
        else:
            try:
                verdict = rule.predicate(cand, part)
                error = None
            except Exception as exc:                            # noqa: BLE001
                # A predicate that raises is a defect in this file, not a property of the candidate.
                # It is recorded as a blocking unknown rather than allowed to propagate, so that the
                # rest of the table is still evaluated and the report still lists every other
                # failure, while the defect itself is visible and stops the candidate.
                verdict = None
                error = exc

        if verdict not in (True, False, None):
            # Also a defect in this file rather than in the candidate: the contract in
            # ``types.DeviceConstraint`` is that a predicate returns True, False or None.
            error = TypeError(f"predicate returned {verdict!r}, expected True, False or None")
            verdict = None

        if rule.severity == "advisory":
            if error is not None:
                report.advisories.append(_entry(
                    rule, "predicate_error",
                    f"{rule.title}: the check for this advisory could not be run ({error!r}), so "
                    f"the advisory is reported without a verdict. {rule.human_text}", observed))
            elif verdict is False:
                report.advisories.append(_entry(
                    rule, "advisory_failed",
                    f"{rule.title}: not satisfied. {rule.human_text}", observed))
            elif verdict is None and rule.predicate is None:
                report.advisories.append(_entry(
                    rule, "advisory_no_predicate",
                    f"{rule.title}: reported for the record; this rule has no machine check. "
                    f"{rule.human_text}", observed))
            elif verdict is None:
                report.advisories.append(_entry(
                    rule, "advisory_not_determinable",
                    f"{rule.title}: could not be determined from the inputs given, so it is "
                    f"reported rather than resolved. {rule.human_text}", observed))
            continue

        # Blocking and unknown rules from here down. Both can disqualify; they differ in what a
        # reader has to do about a None verdict.
        if error is not None:
            report.unknowns.append(_entry(
                rule, "predicate_error",
                f"{rule.title}: the check for this rule raised {error!r}. This is a defect in the "
                f"rule table rather than a property of the candidate, and it blocks because an "
                f"unevaluated rule has not been satisfied.", observed))
        elif verdict is False:
            report.failures.append(_entry(
                rule, "failed",
                f"{rule.title}: violated. {rule.human_text}", observed))
        elif verdict is None:
            if rule.severity == "unknown":
                report.unknowns.append(_entry(
                    rule, "value_not_read_off_programmer",
                    f"{rule.title}: the rule exists and its value has not been read off the "
                    f"programmer, so it cannot be evaluated and it blocks. {rule.human_text}",
                    observed))
            else:
                report.unknowns.append(_entry(
                    rule, "input_not_supplied",
                    f"{rule.title}: the inputs needed to evaluate this rule were not supplied, so "
                    f"it blocks rather than passing. See CANDIDATE_KEYS and PARTICIPANT_KEYS for "
                    f"the fields it reads. {rule.human_text}", observed))
        elif rule.rule_id in _RECORD_VALUE_ON_PASS and observed:
            # Passed, and the value is one a reader must be able to see; see _RECORD_VALUE_ON_PASS.
            report.advisories.append(_entry(
                rule, "recorded_value",
                f"{rule.title}: satisfied, and the value is recorded here because the meaning of "
                f"the rest of this report depends on it.", observed))

    report.eligible = not report.failures and not report.unknowns
    return report


def severity_counts(rules=None):
    """Return how many rules carry each severity, for the report header and for the tests."""
    table = tuple(RULES if rules is None else rules)
    counts = {"blocking": 0, "advisory": 0, "unknown": 0}
    for rule in table:
        counts[rule.severity] += 1
    return counts
