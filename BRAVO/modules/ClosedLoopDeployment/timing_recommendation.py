"""The closed-loop timing values the participant's OWN record argues for, per participant.

WHY A TABLE (2026-09-13, decisions 148-150). The parameter card on the Closed-Loop Deployment page
("Full parameter recommendation") derived its onset from the biomarker's 4.096 s integration
window and left the transitions, blanking and startup delay at the white paper's Parkinson's
defaults, because nothing in the platform had measured what this participant's signal does over
time. Phase 10 measured it (decision 148), and a six-method contest then re-derived every value
on one held-out scoring rule (decision 150; the judgement is
``artifacts/contest_2026-09-13_SYNTHESIS.md``, the six reports beside it). The contest's central
correction: the device forms one averaged reading per averaging window and counts the onset in
those readings, so the 30 s averaging with 30 s onset that RCS08 runs today -- and that decision
148 recommended -- is ONE comparison with no confirmation behind it; replayed with the averaging
honoured it switches the current 34-40 times an hour and undoes about 49 of those within one
onset in 3.4 h. The Phase 10 sweep had left the averaging at the replay's default, so its "30 s
onset" was ten confirmations of 3 s. With averaging at 3 s (the nearest device value to the
validated 4.096 s feature window) the same 30 s onset IS ten confirmations: 2.5 switches an hour,
none undone, on the held-out stretches.

These are RCS08's values, derived from RCS08's record; they are not device defaults and they are
not another participant's answer. So they live in one table keyed on the participant, exactly as
the PI-stated safety ceiling does (``StimOptimizer.safety_ceiling``): a participant absent from the
table gets the derivation the card used before (two averaging windows for the onset, the
manufacturer's defaults for the rest), with the provenance saying so. Every value here sits inside
the documented selection range where one exists (``percept_adaptive.DOCUMENTED_RANGES``).

WHAT THE RECORD CANNOT DECIDE, and every entry said so: the two ramp durations and the blanking
(no measurement separates 4 s from 60 s once the onset filters), and the response of the band to
the stimulation current at all -- every replay runs the controller over the recorded power with a
zero response curve. The titration session (open item 30) is what would supply the gain.

WHERE IT REACHES THE PAGE. Closed-Loop Deployment page, the "Full parameter recommendation" card:
the onset, averaging, transition, blanking and startup-delay rows carry these values with the
sentence below as their reason and the confidence beside it.
"""
from __future__ import annotations

#: Bumped whenever a value in `RECORD_DERIVED_TIMING_MS` changes for any participant -- folded into
#: `simulation.simulation_signature` (T2, 2026-09-13) so a table edit invalidates the stored
#: closed-loop simulation rather than serving a replay built under the old recommendation.
TABLE_VERSION = "v1_decision150"

#: THE ONE PLACE TO CHANGE A PARTICIPANT'S RECORD-DERIVED TIMING. Participant uid -> field -> ms.
RECORD_DERIVED_TIMING_MS = {
    # RCS08 -- decision 150, contest judgement section 3, held-out replay through 2026-09-13.
    "2e3c75c00d7f4f37b53a048d195f11da": {
        "onset_upper_ms": 30_000.0,
        "onset_lower_ms": 30_000.0,
        "averaging_ms": 3_000.0,
        "transition_up_ms": 30_000.0,
        "transition_down_ms": 30_000.0,
        "detection_blanking_ms": 30_000.0,
        "adaptive_startup_delay_ms": 15_000.0,
    },
}

#: One sentence of reason and a confidence per field, from the contest judgement, printed on the card.
RECORD_DERIVED_WHY = {
    "onset_upper_ms": (
        "Ten confirmations of the 3 s averaged reading: the shortest onset that holds noise-only "
        "threshold crossings at or below one an hour at the stored separation on this "
        "participant's own signal (a fitted slow-level model's noise simulation), and replayed on "
        "held-out stretches it switches the current 2.5 times an hour with none undone, against "
        "34-40 an hour with about 49 undone for the 30 s averaging / 30 s onset the device runs "
        "today.",
        # The block bootstrap's interval is NOT typed here: it is computed per band and printed by
        # `robustness_note` on the same row. A typed "36-90 s" (one contact's 2026-09-13 value) sat
        # beside a live "27-30 s" until the referent audit of 2026-09-15.
        "High"),
    "onset_lower_ms": (
        "Same measurement as the upper onset; the replay applies one onset to both directions, so "
        "equal timers are the honest choice, and asymmetry is the manufacturer's first lever if "
        "the delivered current turns out transiently too low or too high (D51).", "Medium"),
    "averaging_ms": (
        "The validated feature was computed on a 4.1 s window and 3 s is the nearest the device "
        "offers. CORRECTED 2026-09-13, in answer to a direct question: once the onset is properly "
        "re-tuned at EACH averaging duration (rather than compared at one onset held fixed in "
        "seconds, the confound that inflated some of the contest's own switching-rate numbers), "
        "the switching rate is nearly flat, about 3-4 an hour, from 3 s all the way to 30 s, on "
        "both the calibrated grid's own threshold pair and the device's actual programmed 167/166 "
        "pair. What genuinely differs is how long a confirmation takes: at 3 s averaging the "
        "shortest onset reaching zero undone switches is about 21-24 s; at 30 s averaging the same "
        "stability needs 90-180 s. Short averaging is kept for that reason -- it reaches a "
        "confirmed decision in a quarter to a sixth of the time, at an equal switching rate -- not "
        "because it switches less.", "High"),
    "transition_up_ms": (
        "The record cannot decide this: the band's slow level carries over with a time constant of "
        "hours, so every ramp on the device's grid is fast against it, and 4 s to 60 s replay "
        "identically at any onset that filters. 30 s finishes before the next decision could "
        "arrive (onset plus blanking) and is inside every method's acceptable set.", "Low"),
    "transition_down_ms": (
        "Same evidence as the transition up; nothing in the record distinguishes the two "
        "directions.", "Low"),
    "detection_blanking_ms": (
        "Undetermined by the record: at a filtering onset every blanking value from 3 to 60 s "
        "gives the identical switching rate. Equal to the onset stops a decision being "
        "re-classified while the ramp it triggered is still under way, and is what runs today.",
        "Low"),
    "adaptive_startup_delay_ms": (
        "The measured start-of-recording dips (0.10 to 0.41 of the scatter, three independent "
        "measurements) are gone by 12 s; one method finds none. 15 s is the shortest value above "
        "12 s the device has been seen to accept; the 60-87 s two model-based methods derived are "
        "settling times of their estimators, not of the device.", "Medium"),
}

RECORD_DERIVED_PROVENANCE = ("measured on this participant's own record: six-method contest, "
                             "held-out replay (decision 150, "
                             "artifacts/contest_2026-09-13_SYNTHESIS.md section 3)")


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


#: The fields the record cannot decide (decision 150), kept as the participant's table has them when
#: the onset is worked out per band (decision 417), and labelled as such on the card.
SAME_FOR_EVERY_BAND = ("transition_up_ms", "transition_down_ms", "adaptive_startup_delay_ms")


def for_band(participant_uid, band_timing):
    """The card's timing for one band (decision 417): the band's own onset (`band_timing`), the
    blanking equal to it, 3 s averaging, and the fields the record cannot decide from the
    participant's table, labelled as the same for every band. Without a band answer, the
    participant's table as before (`for_participant`)."""
    base = for_participant(participant_uid)
    if not band_timing or not band_timing.get("available"):
        return base
    from . import band_timing as _bt
    cand = band_timing.get("candidate") or {}
    where = (f"worked out for this band ({cand.get('channel')}, {cand.get('center_hz')} Hz) from "
             f"its own record, decision 417")
    onset_ms = float(band_timing["onset_s"]) * 1000.0
    pick = band_timing.get("pick") or {}
    reached = bool(band_timing.get("zero_undone_reached"))
    onset_why = (
        f"Of the onsets at {_bt.AVERAGING_S:g} s averaging with no switch undone within one onset "
        f"when this band's own recorded power is replayed through the controller (its thresholds "
        f"placed from its record: median +- the separation its noise model needs at that onset), "
        f"the one with the fewest switches" + (
            f": {pick.get('transitions_per_hour'):.1f} an hour over "
            f"{band_timing.get('hours_replayed') or 0:.1f} h of recording."
            if pick.get("transitions_per_hour") is not None else ".")
        if reached else
        f"No onset the tablet accepts reached zero undone switches on this band; this one undid "
        f"the fewest ({pick.get('undone')}).")
    out = {}
    for k in ("onset_upper_ms", "onset_lower_ms"):
        out[k] = {"value_ms": onset_ms, "why": onset_why,
                  "confidence": "Medium" if reached else "Low", "provenance": where}
    out["detection_blanking_ms"] = {
        "value_ms": onset_ms, "provenance": where, "confidence": "Low",
        "why": "Equal to this band's onset (the record cannot decide the blanking; equal to the "
               "onset stops a decision being re-classified while its ramp runs)."}
    out["averaging_ms"] = {
        "value_ms": _bt.AVERAGING_S * 1000.0, "provenance": where,
        "confidence": (base.get("averaging_ms") or {}).get("confidence", "High"),
        "why": "The same for every band: the nearest device value to the validated feature's "
               "4.1 s window, and the averaging this band's onset was worked out at."}
    for k in SAME_FOR_EVERY_BAND:
        if k in base:
            out[k] = dict(base[k], why="The same for every band: " + base[k]["why"])
    return out
