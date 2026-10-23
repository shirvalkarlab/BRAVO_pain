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

THE HOME SWING, A WARNING ONLY (wave 2, C7; the PI, 2026-10-20: "Keep thresholds, warn"). Both pairs
above are set from clinic recordings only, on the calibrated LSB scale: the 3 s pieces of
voltage-trace recording converted to device units through the calibration measured on
simultaneous recordings (TD-derived LSB), or the tablet's capture. The ruling keeps both pairs
exactly as they are: no centring on the home record (chronic log) and no false-crossing rate
simulated along its hourly levels. The chronic log is the streaming power quantity averaged over
10 minutes, on the same scale (decision 503: the Medtronic-authored ADAPT-PD methods paper describes
one control signal, shown live in Streaming and stored as 10-minute averages in Timeline); that is
documented, not measured, and the 10-minute average still differs in spread from the 3 s pieces.

What the pair carries is `home_swing`: how many fold the home record's hourly medians swing across
the day at the band, a ratio within that one product, so no conversion is involved (no home-record
value enters any threshold number), with its hours, readings and days, and a plain warning
appended to the rows' reasons. It moves no
threshold, separation, rate, timing or verdict; nothing that decides reads it. The profile is
C6's (`Biomarkers.routines.daily_swing.hourly_profile`), at the chronic frequency C5's mapping puts
on the band (`chronic_band_choice.grid_centre_for`). Neutral `BRAVO_THRESHOLD_HOME_SWING=0`: the
path is skipped and the pair, its rows and its notes are exactly as before.

A THRESHOLD BELOW ZERO, A WARNING ONLY (open item of decision 495; the PI, 2026-10-22: "Go"). The
record pair is the median minus and plus the design rule's half-separation, so where the median is
smaller than that half-separation the LOWER threshold comes out below zero (RCS08 R 0-3 26.5 Hz:
265.95 / -54.05). Device band power cannot go below zero, so the device would never cross it. The
same check covers the upper threshold and the Single mode's threshold the device computes from the
pair (0.75 x (upper - lower) + lower, D20), each below zero only when the pair is lower still. As
C6-C8: nothing is refused and no number changes; `below_zero` (which thresholds, their values, one
plain warning each) goes on the placement, the plan's copy and the report's design-rule summary,
and the warnings are appended to the placement note and the Upper/Lower/Single rows' reasons.
Neutral `BRAVO_THRESHOLD_BELOW_ZERO=0`: the path is skipped.
"""
from __future__ import annotations

import dataclasses
import os as _os
from typing import Any, Dict, Optional, Sequence

import numpy as np

RULE_VERSION = "v1_record_pair_median_centre_design_rule_separation_tablet_clock"  # tablet clock (2026-09-26): every time from the tablet's clock, TabletClock.py #   # decision 180, 2026-09-15


#: The neutral setting (`BRAVO_THRESHOLD_HOME_SWING=0`): no home-swing block, no appended text.
HOME_SWING = _os.environ.get("BRAVO_THRESHOLD_HOME_SWING", "1").strip() != "0"
#: The neutral setting (`BRAVO_THRESHOLD_BELOW_ZERO=0`): no below-zero block, no appended text.
BELOW_ZERO = _os.environ.get("BRAVO_THRESHOLD_BELOW_ZERO", "1").strip() != "0"
#: The Single mode's threshold as the device computes it from the pair (D20).
SINGLE_FRACTION = 0.75
BELOW_ZERO_WHAT = ("whether any threshold this pair gives is below zero: device band power cannot go "
                   "below zero, so a threshold below zero can never be crossed from above; a warning "
                   "only, it changes no threshold, rate, timing or verdict")
THRESHOLDS_FROM = "clinic recordings only"
HOME_STATUS_UNREADABLE = "home record could not be read"
HOME_SWING_WHAT = ("how many fold the home record's (chronic log's) hourly median band power swings "
                   "across the day at this band and contact pair, California local time, device "
                   "values at face value; a ratio within the home record, so no conversion is "
                   "involved, and never a threshold value; the thresholds are set from clinic "
                   "recordings only; a warning only, it changes no threshold, rate, timing or verdict")


def _daily_swing_module():
    try:
        from Biomarkers.routines import daily_swing as _ds
    except ImportError:                                   # pragma: no cover - the other spelling
        from modules.Biomarkers.routines import daily_swing as _ds
    return _ds


def _grid_centre_for(f, centres):
    try:
        from Biomarkers.routines import chronic_band_choice as _cbc
    except ImportError:                                   # pragma: no cover - the other spelling
        from modules.Biomarkers.routines import chronic_band_choice as _cbc
    return _cbc.grid_centre_for(f, centres)


def home_swing_warning(block: Optional[Dict[str, Any]]) -> Optional[str]:
    """The plain warning for one `home_swing` block: the swing at or above C6's
    `daily_swing.SWING_WARN_RATIO`, no home record, or an unreadable one; None below the ratio."""
    _ds = _daily_swing_module()
    b = block or {}
    status = b.get("status")
    if status == _ds.STATUS_NO_HOME_RECORD:
        return f"No home record at this band; these thresholds were set from {THRESHOLDS_FROM}."
    if status == HOME_STATUS_UNREADABLE:
        return f"The home record could not be read; these thresholds were set from {THRESHOLDS_FROM}."
    ratio = b.get("ratio")
    if ratio is None or not np.isfinite(float(ratio)) or float(ratio) < _ds.SWING_WARN_RATIO:
        return None
    return (f"Home power at this band swings {float(ratio):.1f}-fold across the day (lowest "
            f"{int(b['hour_low']):02d}:00, highest {int(b['hour_high']):02d}:00); these thresholds "
            f"were set from {THRESHOLDS_FROM}, so the device may cross them from the time of day alone.")


def home_swing_block(samples_by_pair, pair, centre_hz, *, reason=None) -> Dict[str, Any]:
    """The `home_swing` block for the band at ``centre_hz`` on contact pair ``pair``.

    ``samples_by_pair`` is `chronic_band_choice.chronic_samples_by_pair`'s answer (``None`` with a
    ``reason`` when the home record could not be read). The chronic frequency is the one C5's mapping
    puts on this centre (under 0.5 Hz away; the nearer, then the one with more readings); its hourly
    profile is C6's. Only the ratio, its hours and the counts are kept, never a home-record value."""
    _ds = _daily_swing_module()
    out: Dict[str, Any] = {"status": None, "pair": None if pair is None else str(pair),
                           "centre_hz": None if centre_hz is None else float(centre_hz),
                           "chronic_freq_hz": None, "ratio": None, "hour_low": None,
                           "hour_high": None, "n_readings": 0, "n_days": 0,
                           "thresholds_from": THRESHOLDS_FROM,
                           "warn_at_ratio": float(_ds.SWING_WARN_RATIO), "warning": None,
                           "what": HOME_SWING_WHAT}
    if samples_by_pair is None:
        out["status"] = HOME_STATUS_UNREADABLE
        out["reason"] = str(reason or "the home record could not be read")
        out["warning"] = home_swing_warning(out)
        return out
    d = (samples_by_pair or {}).get(str(pair)) if pair is not None else None
    best = None
    if d is not None and centre_hz is not None:
        t = np.asarray(d.get("t", []), dtype=float)
        y = np.asarray(d.get("y", []), dtype=float)
        hz = np.asarray(d.get("freq_hz", []), dtype=float)
        for f in sorted({float(v) for v in hz[np.isfinite(hz)]}):
            if _grid_centre_for(f, [float(centre_hz)]) is None:
                continue
            sel = hz == f
            cand = (abs(f - float(centre_hz)), -int(sel.sum()), f, t[sel], y[sel])
            if best is None or cand[:2] < best[:2]:
                best = cand
    if best is None:
        out["status"] = _ds.STATUS_NO_HOME_RECORD
        out["warning"] = home_swing_warning(out)
        return out
    prof = _ds.hourly_profile(best[3], best[4])
    if not prof.get("n_readings"):
        out["status"] = _ds.STATUS_NO_HOME_RECORD
        out["warning"] = home_swing_warning(out)
        return out
    out.update({"status": _ds.STATUS_MEASURED, "chronic_freq_hz": float(best[2]),
                "ratio": prof["ratio"], "hour_low": prof["hour_low"], "hour_high": prof["hour_high"],
                "n_readings": int(prof["n_readings"]), "n_days": int(prof["n_days"])})
    out["warning"] = home_swing_warning(out)
    return out


def with_home_swing(plan, placement: Optional[Dict[str, Any]], block: Dict[str, Any]):
    """``(plan, placement)`` carrying ``block`` as ``home_swing`` (on the placement dict and on the
    plan's own copy of it), its warning appended to the plan's ``placement_note`` the way C6 appends
    to ``why``. Touches no number: upper, lower, the capture pair, the time fractions are the
    plan's own."""
    _ds = _daily_swing_module()
    pl = dict(placement or {})
    pl["home_swing"] = dict(block)
    if plan is None:
        return plan, pl
    plan_pl = dict(getattr(plan, "placement", {}) or {})
    plan_pl["home_swing"] = dict(block)
    note = _ds.append_warning(getattr(plan, "placement_note", "") or "", block.get("warning"))
    return dataclasses.replace(plan, placement=plan_pl, placement_note=note), pl


def _signed(v: float) -> str:
    """A value as the warning prints it: two decimals, a true minus sign."""
    return f"{float(v):.2f}".replace("-", "\u2212")


def single_threshold(upper, lower) -> Optional[float]:
    """The Single mode's threshold the device computes from the pair, 0.75 x (upper - lower) +
    lower (D20; the same arithmetic `prescription.prescribe` prints); None without a pair."""
    try:
        up, lo = float(upper), float(lower)
    except (TypeError, ValueError):
        return None
    if not (np.isfinite(up) and np.isfinite(lo)):
        return None
    return SINGLE_FRACTION * (up - lo) + lo


def below_zero_warning(which: str, value: float) -> str:
    """The plain warning for one threshold below zero. ``which``: "upper", "lower" or "single"."""
    if which == "lower":
        tail = "so the device would never cross it"
    else:
        tail = "so power would always sit above it and the device would never see it crossed from above"
    return (f"The {which} threshold is below zero ({_signed(value)}); band power cannot go below "
            f"zero, {tail}.")


def below_zero_block(upper, lower) -> Dict[str, Any]:
    """The `below_zero` block for a pair: each of the upper, lower and Single thresholds, its value
    and, when it is below zero, its warning. ``warning`` joins the Dual pair's two (upper, lower)
    for the placement note; the Single threshold's stays under ``warnings["single"]``."""
    single = single_threshold(upper, lower)
    vals = {"upper": upper, "lower": lower, "single": single}
    warnings: Dict[str, Optional[str]] = {}
    below = []
    for k in ("upper", "lower", "single"):
        v = vals[k]
        try:
            f = float(v)
        except (TypeError, ValueError):
            f = float("nan")
        if np.isfinite(f) and f < 0.0:
            warnings[k] = below_zero_warning(k, f)
            below.append(k)
        else:
            warnings[k] = None
    pair_w = " ".join(w for w in (warnings["upper"], warnings["lower"]) if w) or None
    return {"status": ("below zero" if below else "none below zero"),
            "below_zero": below,
            "upper": None if upper is None else float(upper),
            "lower": None if lower is None else float(lower),
            "single": single, "single_fraction": SINGLE_FRACTION,
            "warnings": warnings, "warning": pair_w, "what": BELOW_ZERO_WHAT}


def with_below_zero(plan, placement: Optional[Dict[str, Any]]):
    """``(plan, placement)`` carrying `below_zero_block` of the plan's own pair as ``below_zero``
    (on the placement dict and on the plan's copy of it), the pair's warning appended to the plan's
    ``placement_note``. Touches no number."""
    _ds = _daily_swing_module()
    pl = dict(placement or {})
    if plan is None:
        return plan, pl
    block = below_zero_block(getattr(plan, "upper", None), getattr(plan, "lower", None))
    pl["below_zero"] = dict(block)
    plan_pl = dict(getattr(plan, "placement", {}) or {})
    plan_pl["below_zero"] = dict(block)
    note = _ds.append_warning(getattr(plan, "placement_note", "") or "", block.get("warning"))
    return dataclasses.replace(plan, placement=plan_pl, placement_note=note), pl


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
