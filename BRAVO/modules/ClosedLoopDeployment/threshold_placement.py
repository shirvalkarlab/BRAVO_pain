"""Placing the two thresholds from the record (decision 180, the PI's ruling of 2026-09-15).

Until that day the two threshold VALUES on the parameter card were the tablet's own capture rule
(D24, `authority.threshold_placement`): the upper threshold is the mean band power measured at the
LOWER current, the lower threshold the mean at the HIGHER current. The Kalman design rule (T3,
decision 152) and the occupancy check (T4, decision 153) read that pair and annotated it -- and on
the committed band the capture pair failed both of the checks printed under it (+-2.6 where the rule
needs +-5; 2.0% of readings between; centred 12.4 units above the median). Open item 31 put the
choice to him; he chose (b): place the pair from the record.

THE RULE. Centre = the participant's own MEDIAN averaged reading at the averaging duration the card
recommends (`occupancy.averaged_readings`, the same re-averaging T4 uses). Half-separation = the
noise-only design rule's minimum at the recommended averaging and onset
(`design_rule.lookup_min_separation` over the stored table, which is simulated with the level held
at the pair's midpoint -- so the placement step fits it at the median, and the record pair's
midpoint IS the median, one fit). The capture pair is kept on the plan as `capture_upper` and
`capture_lower` and printed in the rows' "why", so the tablet's answer is never silently dropped.

REFUSALS, never a fabricated pair: no averaged readings (no median), no design table or a refused
fit, no recommended timing, or a table that finds no separation up to its grid maximum that keeps
noise-only crossings at or below one an hour. A refused placement leaves the capture pair in
place, labelled "capture", with the reason on the plan.
"""
from __future__ import annotations

import dataclasses
from typing import Any, Dict, Optional, Sequence

import numpy as np

RULE_VERSION = "v1_record_pair_median_centre_design_rule_separation"   # decision 180, 2026-09-15



# Aditya canonical compatibility imports/constants.



def median_level(t, power, *, averaging_s: float) -> Dict[str, Any]:
    """The participant's own median averaged reading at ``averaging_s``, over the same 3 s
    pieces the occupancy check averages, never across a gap between two recordings."""
    from . import occupancy as _occ

    try:
        avg = _occ.averaged_readings(t, power, averaging_s=float(averaging_s))
    except Exception as exc:                          # noqa: BLE001 - a refusal, not an error
        return {"available": False, "median": None, "n_readings": 0,
                "averaging_s": float(averaging_s), "reason": f"the readings could not be averaged: {exc!r}"}
    avg = np.asarray(avg, dtype=float)
    avg = avg[np.isfinite(avg)]
    if avg.size == 0:
        return {"available": False, "median": None, "n_readings": 0,
                "averaging_s": float(averaging_s), "reason": "no averaged readings, so no median level"}
    return {"available": True, "median": float(np.median(avg)), "n_readings": int(avg.size),
            "averaging_s": float(averaging_s)}


def record_pair(*, median: Optional[float], design_rows: Sequence[Dict[str, Any]],
                averaging_ms: Optional[float], onset_ms: Optional[float]) -> Dict[str, Any]:
    """The pair: ``median`` +- the design rule's minimum half-separation at the card's timing."""
    out: Dict[str, Any] = {"available": False, "rule": "record", "rule_version": RULE_VERSION,
                           "upper": None, "lower": None, "centre": None, "half_separation": None,
                           "averaging_s": None, "onset_s": None, "timing_exact": None, "note": None}
    if median is None or not np.isfinite(float(median)):
        out["reason"] = "no median level: the record holds no averaged reading to centre on"
        return out
    if not design_rows:
        out["reason"] = "no design-rule table: the noise-only model was not fitted or was refused"
        return out
    if averaging_ms is None or onset_ms is None:
        out["reason"] = "no recommended averaging or onset duration to evaluate the rule at"
        return out
    from . import design_rule as _dr
    row = _dr.lookup_min_separation(list(design_rows), averaging_ms=float(averaging_ms),
                                    onset_ms=float(onset_ms))
    if row is None:
        out["reason"] = "the design-rule table is empty"
        return out
    out["averaging_s"] = float(row["averaging_s"])
    out["onset_s"] = float(row["onset_s"])
    out["timing_exact"] = bool(row["exact_match"])
    if row.get("min_separation") is None:
        out["reason"] = (f"no separation up to the rule's grid maximum keeps noise-only threshold "
                         f"crossings at or below one an hour at {row['averaging_s']:g} s averaging / "
                         f"{row['onset_s']:g} s onset, so no pair can be placed from the record")
        return out
    half = float(row["min_separation"])
    centre = float(median)
    out.update({"available": True, "centre": centre, "half_separation": half,
                "upper": centre + half, "lower": centre - half})
    out["note"] = (f"centred on the median averaged reading at {row['averaging_s']:g} s "
                   f"({centre:.2f} device units), separated by the design rule's minimum of "
                   f"+-{half:g} at " + ("the timing shown on this card" if row["exact_match"] else
                                       f"the nearest evaluated timing, {row['averaging_s']:g} s "
                                       f"averaging / {row['onset_s']:g} s onset"))
    return out


def apply(plan, placement: Dict[str, Any], *, observed_series=None):
    """A NEW plan carrying the record pair (or the capture pair, labelled, when the placement was
    refused). The capture pair is kept as ``capture_upper``/``capture_lower`` either way; the D26
    verdicts, the capture amplitudes and the warnings are the capture's and are untouched."""
    if getattr(plan, "placement_rule", "capture") == "record":
        # already placed once: the capture pair is the one the plan carries, never the record pair
        cap_up, cap_lo = getattr(plan, "capture_upper", None), getattr(plan, "capture_lower", None)
    else:
        cap_up, cap_lo = getattr(plan, "upper", None), getattr(plan, "lower", None)
    fields = dict(capture_upper=cap_up, capture_lower=cap_lo, placement=dict(placement or {}))
    if not (placement or {}).get("available"):
        fields.update(placement_rule="capture",
                      placement_note=("the pair is the tablet's own capture rule (D24); a pair from "
                                      "the record could not be placed: "
                                      + str((placement or {}).get("reason") or "no placement")))
        return dataclasses.replace(plan, **fields)
    up, lo = float(placement["upper"]), float(placement["lower"])
    fb = fbet = fab = None
    if observed_series is not None:
        s = np.asarray(observed_series, dtype=float)
        s = s[np.isfinite(s)]
        if s.size:
            fb = float(np.mean(s < lo))
            fab = float(np.mean(s > up))
            fbet = float(1.0 - fb - fab)
    fields.update(upper=up, lower=lo, placement_rule="record",
                  frac_time_below=fb, frac_time_between=fbet, frac_time_above=fab,
                  placement_note=("the pair is placed from the record (decision 180): "
                                  + str(placement.get("note") or "")
                                  + (f"; the tablet's own capture would place it at "
                                     f"{cap_up:.2f} / {cap_lo:.2f}" if cap_up is not None and cap_lo is not None
                                     else "")))
    return dataclasses.replace(plan, **fields)


# Retained active Aditya interfaces.
