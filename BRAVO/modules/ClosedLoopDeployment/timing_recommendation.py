"""The closed-loop timing values the participant's OWN record argues for, per participant.

WHY A TABLE (2026-09-13, decision 148 and its wiring). The parameter card on the Closed-Loop
Deployment page ("Full parameter recommendation") derived its onset from the biomarker's 4.096 s
integration window and left the transitions, blanking and startup delay at the white paper's
Parkinson's defaults, because nothing in the platform had measured what this participant's signal
does over time. Phase 10 of the "Make Closed-Loop Work" session measured it: on RCS08's own
calibrated band power (31.6 h on L 1-3+, 27.4 h on L 0-2+, at 24.5 Hz), the 3-second readings are
near-independent draws, excursions past a threshold last one or two readings, a 1.2 s onset
switches the current about 440 times an hour with a third of the switches undone within one onset,
and 30 s cuts that to about 2.5 an hour with none undone. The whole analysis, every number's
source, and what the record CANNOT decide are in
``artifacts/research_2026-09-13_percept_adaptive_timing_SYNTHESIS.md`` (section 4 is the table
this file transcribes).

These are RCS08's values, derived from RCS08's record; they are not device defaults and they are
not another participant's answer. So they live in one table keyed on the participant, exactly as
the PI-stated safety ceiling does (``StimOptimizer.safety_ceiling``): a participant absent from the
table gets the derivation the card used before (the biomarker window for the onset, the
manufacturer's defaults for the rest), with the provenance saying so. Every value here sits inside
the documented selection range where one exists (``percept_adaptive.DOCUMENTED_RANGES``).

A method contest (six modelling approaches over the same held-out stretches, 2026-09-13) is
re-deriving these values; when it lands, this table is the one place to change.

WHERE IT REACHES THE PAGE. Closed-Loop Deployment page, the "Full parameter recommendation" card:
the onset, averaging, transition, blanking and startup-delay rows carry these values with the
sentence below as their reason and the confidence beside it.
"""
from __future__ import annotations

#: THE ONE PLACE TO CHANGE A PARTICIPANT'S RECORD-DERIVED TIMING. Participant uid -> field -> ms.
RECORD_DERIVED_TIMING_MS = {
    # RCS08 -- decision 148, synthesis section 4, measured on the record through 2026-09-13.
    "2e3c75c00d7f4f37b53a048d195f11da": {
        "onset_upper_ms": 30_000.0,
        "onset_lower_ms": 30_000.0,
        "averaging_ms": 30_000.0,
        "transition_up_ms": 30_000.0,
        "transition_down_ms": 30_000.0,
        "detection_blanking_ms": 30_000.0,
        "adaptive_startup_delay_ms": 15_000.0,
    },
}

#: One sentence of reason and a confidence per field, from the synthesis table, printed on the card.
RECORD_DERIVED_WHY = {
    "onset_upper_ms": (
        "Measured on this participant's own band power: the 3-second readings are near-independent "
        "draws whose excursions past a threshold last one or two readings, so 30 s is the shortest "
        "onset that switches the current about 2.5 times an hour with no switch undone within one "
        "onset, on both candidate bands; 1.2 s would switch about 440 times an hour.", "High"),
    "onset_lower_ms": (
        "Same measurement as the upper onset; nothing in the record argues for the two timers to "
        "differ, and asymmetry is the manufacturer's first lever if the delivered current turns out "
        "transiently too low or too high (D51).", "High"),
    "averaging_ms": (
        "More than half of a reading's variance is faster than 10 s and is noise to a loop that "
        "should follow the slow part; 30 s is the documented maximum and the device already runs "
        "it on this participant.", "High"),
    "transition_up_ms": (
        "Replaying the controller over the record, outcomes are indistinguishable from 4 s up to "
        "60 s once the onset is 30 s, so the choice is about ramp comfort; 30 s smooths a 1 mA "
        "change over 100 steps of 0.01 mA and stays well below the 2.5 min at which the loop stops "
        "reaching its limits. Keeping today's 4 s is equally defensible on the data.", "Medium"),
    "transition_down_ms": (
        "Same evidence as the transition up; the record gives no reason for down to differ from "
        "up. The white paper's 2.5 and 5 min defaults are Parkinson's defaults and would leave "
        "this loop mid-ramp most of the time.", "Medium"),
    "detection_blanking_ms": (
        "With a 30 s onset, blanking shorter than the onset would let a decision be re-classified "
        "while the ramp it triggered is still under way; equal to the onset is the consistent "
        "choice and is what runs today. No direct measurement is possible from this record.",
        "Low"),
    "adaptive_startup_delay_ms": (
        "The first 12 s of sensing after a stretch starts read 0.24 to 0.41 of the scatter low on "
        "this record (85 and 71 stretches), so a delay shorter than that lets a startup artefact "
        "drive the first decision; today's 0 is the one value the record argues against. 15 s if "
        "the tablet offers it, else 30 s.", "Medium"),
}

RECORD_DERIVED_PROVENANCE = ("measured on this participant's own record (decision 148, "
                             "artifacts/research_2026-09-13_percept_adaptive_timing_SYNTHESIS.md "
                             "section 4)")


def for_participant(participant_uid):
    """The record-derived timing for one participant, or ``{}`` when none has been measured.

    Returns a dict of field -> {"value_ms", "why", "confidence", "provenance"}; the caller decides
    what to do with an absent participant (the card falls back to its older derivation and says
    so). Nothing is invented for a participant not in the table.
    """
    table = RECORD_DERIVED_TIMING_MS.get(str(participant_uid) if participant_uid is not None else "")
    if not table:
        return {}
    out = {}
    for k, v in table.items():
        why, conf = RECORD_DERIVED_WHY.get(k, ("", "Low"))
        out[k] = {"value_ms": float(v), "why": why, "confidence": conf,
                  "provenance": RECORD_DERIVED_PROVENANCE}
    return out
