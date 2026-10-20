"""Participant-bound timing recommendations from private evidence or live band analysis.

Historical empirical tables are deployment inputs, never application defaults.
Missing source evidence makes timing recommendations explicitly unavailable.
"""
from __future__ import annotations

import math

try:
    from modules.DecodeCommon.private_clinical_config import (
        ClinicalConfigurationUnavailable, participant_section, config_digest)
except ImportError:
    from DecodeCommon.private_clinical_config import (
        ClinicalConfigurationUnavailable, participant_section, config_digest)

TABLE_VERSION = "private_config_v1"
RECORD_DERIVED_PROVENANCE = "participant-specific private timing evidence"
TIMING_FIELDS = ("onset_upper_ms", "onset_lower_ms", "averaging_ms", "transition_up_ms",
                 "transition_down_ms", "detection_blanking_ms", "adaptive_startup_delay_ms")


def for_participant(participant_uid):
    """Return a complete provenance-bound timing table, or explicitly refuse it."""
    record = participant_section(participant_uid, "timing")
    fields = record.get("fields")
    if not isinstance(fields, dict) or set(fields) != set(TIMING_FIELDS):
        raise ClinicalConfigurationUnavailable("The participant timing evidence is incomplete.")
    out = {}
    for key in TIMING_FIELDS:
        entry = fields[key]
        if not isinstance(entry, dict):
            raise ClinicalConfigurationUnavailable("Invalid participant timing entry.")
        try:
            value = float(entry["value_ms"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ClinicalConfigurationUnavailable("Invalid participant timing value.") from exc
        if (isinstance(entry["value_ms"], bool) or not math.isfinite(value) or value < 0
                or (key == "averaging_ms" and value == 0)):
            raise ClinicalConfigurationUnavailable("Timing values must be finite nonnegative milliseconds with positive averaging.")
        if (entry.get("confidence") not in ("Low", "Medium", "High")
                or not isinstance(entry.get("why"), str) or not entry["why"].strip()):
            raise ClinicalConfigurationUnavailable("Timing evidence must state its reason and confidence.")
        out[key] = {"value_ms": value, "why": entry["why"],
                    "confidence": entry["confidence"], "provenance": record["provenance"],
                    "participant_uid": str(participant_uid),
                    "config_digest": record["configuration_digest"]}
    return out


#: Fields retained from participant evidence when the onset is recomputed per band.
SAME_FOR_EVERY_BAND = ("transition_up_ms", "transition_down_ms", "adaptive_startup_delay_ms")


def for_band(participant_uid, band_timing):
    """The card's timing for one band (the PI, 2026-10-18, item 3; decision 417 for the onset): the
    band's own averaging and onset (`band_timing`), the blanking equal to the onset, and the fields
    the record cannot decide from the participant's table, labelled as the same for every band.
    Without a band answer, the participant's table as before (`for_participant`). An answer saved
    before the averaging was chosen carries no ``averaging_s`` and reads as 3 s, which is what it
    was worked out at."""
    base = for_participant(participant_uid)
    if not band_timing or not band_timing.get("available"):
        return base
    from . import band_timing as _bt
    cand = band_timing.get("candidate") or {}
    where = (f"worked out for this band ({cand.get('channel')}, {cand.get('center_hz')} Hz) from "
             f"its own record, decision 417 and the averaging rule of 2026-10-18")
    try:
        onset_s = band_timing["onset_s"]
        avg_raw = band_timing.get("averaging_s", _bt.AVERAGING_S)
        onset_ms = float(onset_s) * 1000.0
        avg_s = float(avg_raw)
    except (KeyError, TypeError, ValueError) as exc:
        raise ClinicalConfigurationUnavailable("The band timing result has no valid onset or averaging.") from exc
    if (isinstance(onset_s, bool) or isinstance(avg_raw, bool)
            or not math.isfinite(onset_ms) or onset_ms <= 0
            or not math.isfinite(avg_s) or avg_s <= 0):
        raise ClinicalConfigurationUnavailable("The band timing result has no finite positive onset or averaging.")
    pick = band_timing.get("pick") or {}
    reached = bool(band_timing.get("zero_undone_reached"))
    onset_why = (
        f"Of the averaging and onset pairs with no switch undone within one onset when this "
        f"band's own recorded power is replayed through the controller (its thresholds placed "
        f"from its record at each averaging: median +- the separation its noise model needs at "
        f"that pair), the one with the fewest switches" + (
            f": {pick.get('transitions_per_hour'):.1f} an hour over "
            f"{band_timing.get('hours_replayed') or 0:.1f} h of recording."
            if pick.get("transitions_per_hour") is not None else ".")
        if reached else
        f"No averaging and onset pair the tablet accepts reached zero undone switches on this "
        f"band; this one undid the fewest ({pick.get('undone')}).")
    out = {}
    for k in ("onset_upper_ms", "onset_lower_ms"):
        out[k] = {"value_ms": onset_ms, "why": onset_why,
                  "confidence": "Medium" if reached else "Low", "provenance": where}
    out["detection_blanking_ms"] = {
        "value_ms": onset_ms, "provenance": where, "confidence": "Low",
        "why": "Equal to this band's onset (the record cannot decide the blanking; equal to the "
               "onset stops a decision being re-classified while its ramp runs)."}
    out["averaging_ms"] = {
        "value_ms": avg_s * 1000.0, "provenance": where,
        "confidence": "Medium" if reached else "Low",
        "why": (f"Chosen with the onset, from 3 to 30 s in 3 s steps, by the same rule: "
                f"{avg_s:g} s averaging with a {onset_ms / 1000.0:g} s onset switched least with "
                f"none undone on this band's own record.") if reached else (
                f"Chosen with the onset, from 3 to 30 s in 3 s steps: {avg_s:g} s averaging "
                f"with a {onset_ms / 1000.0:g} s onset undid the fewest switches on this band's "
                f"own record.")}
    for k in SAME_FOR_EVERY_BAND:
        out[k] = dict(base[k], why="The same for every band: " + base[k]["why"])
    for entry in out.values():
        entry.update(participant_uid=str(participant_uid),
                     config_digest=base["averaging_ms"]["config_digest"])
    return out
