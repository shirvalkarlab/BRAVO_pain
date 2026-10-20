"""How much a band's power swings across the day, as a WARNING beside the band's link with pain
(wave 2, C6; the PI, 2026-10-19: "Drop blocks, warn").

WHY A WARNING AND NOT A CORRECTION. Preserve Prasad's approved descriptive
warning approach: no hour blocks, centring or within-block shuffling. No answer,
supported status, verdict, gate or p-value may depend on it. Participant-derived
measurements motivating this choice remain in private provenance.

WHAT IT MEASURES.
  * From the chronic log (the device's own band power, one reading per 10 minutes, at home) on the
    row's own contact pair, at the chronic sensing frequency that the chronic log's own mapping puts
    on the band's centre (`chronic_band_choice.grid_centre_for`): the median reading in each hour of
    the day, on raw power (device units at face value, never log power, decision 202); the
    whole-day ratio of the highest hourly median to the lowest; the hours of the highest and the
    lowest; how many readings and how many days went in.
  * From the reports the row's own answer used: the hour of day each was filed (earliest, median,
    latest, and the count in each hour).

WHICH CLOCK. Hours of the day are the participant's own: California local time
(`local_time.PRO_LOCAL_TZ`, America/Los_Angeles, daylight saving applied for each instant), from
times stored as seconds since 1970 UTC (every device time is already on the tablet clock and every
pain-report time already converted from California wall-clock to UTC, `bravo_service.
_pro_timestamps_utc`). Local time and not UTC because the swing follows the participant's day
(sleep, waking, activity), whose hours are local, and an hour in UTC moves by one against them at
each daylight-saving change.

No Django.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .local_time import PRO_LOCAL_TZ

#: Source warning threshold, retained as a descriptive convention rather than
#: an independently validated clinical cutoff.
SWING_WARN_RATIO = 1.25

STATUS_MEASURED = "measured"
STATUS_NO_HOME_RECORD = "no home record at this band"

WHAT = ("the daily swing of this band's power in the home record (chronic log): the median reading "
        "in each hour of the day (California local time), on the device's values at face value, and "
        "the hours of day the pain reports were filed; a warning only, it changes no answer")


def local_hours(times_s):
    """The hour of day (0-23, California local time, daylight saving applied) of each UTC time in
    seconds since 1970, as an int array (NaN times are left out)."""
    t = np.asarray(times_s, dtype=float)
    t = t[np.isfinite(t)]
    if t.size == 0:
        return np.zeros(0, dtype=int)
    idx = pd.to_datetime(t, unit="s", utc=True).tz_convert(PRO_LOCAL_TZ)
    return np.asarray(idx.hour, dtype=int)


def _local_decimal_hours(times_s):
    t = np.asarray(times_s, dtype=float)
    t = t[np.isfinite(t)]
    if t.size == 0:
        return np.zeros(0, dtype=float)
    idx = pd.to_datetime(t, unit="s", utc=True).tz_convert(PRO_LOCAL_TZ)
    return (np.asarray(idx.hour, dtype=float) + np.asarray(idx.minute, dtype=float) / 60.0
            + np.asarray(idx.second, dtype=float) / 3600.0)


def _clock(h):
    """A decimal hour of day as "HH:MM"."""
    if h is None:
        return None
    m = int(round(float(h) * 60.0))
    m = min(m, 24 * 60 - 1)
    return "%02d:%02d" % (m // 60, m % 60)


def report_hours(times_s):
    """When in the day a set of pain reports was filed (California local time): ``n_reports``,
    ``earliest_hour`` / ``median_hour`` / ``latest_hour`` (decimal hours, with "HH:MM" beside each),
    ``counts_by_hour`` (24 counts, hour 0 first)."""
    h = _local_decimal_hours(times_s)
    out = {"n_reports": int(h.size), "earliest_hour": None, "median_hour": None,
           "latest_hour": None, "earliest": None, "median": None, "latest": None,
           "counts_by_hour": [0] * 24}
    if h.size == 0:
        return out
    lo, med, hi = float(h.min()), float(np.median(h)), float(h.max())
    out.update({"earliest_hour": round(lo, 4), "median_hour": round(med, 4),
                "latest_hour": round(hi, 4), "earliest": _clock(lo), "median": _clock(med),
                "latest": _clock(hi),
                "counts_by_hour": [int(v) for v in np.bincount(np.floor(h).astype(int).clip(0, 23),
                                                               minlength=24)]})
    return out


def hourly_profile(times_s, values):
    """The chronic log's daily profile on one contact pair and frequency: ``hourly_median`` (24
    values, hour 0 first; None for an hour with no reading), ``n_readings_by_hour``, ``ratio`` (the
    highest hourly median over the lowest, None when fewer than two hours have readings or the
    lowest is not above zero), ``hour_high`` / ``hour_low`` (the hour each starts), ``n_readings``,
    ``n_days`` (distinct California calendar days with a reading)."""
    t = np.asarray(times_s, dtype=float)
    y = np.asarray(values, dtype=float)
    ok = np.isfinite(t) & np.isfinite(y)
    t, y = t[ok], y[ok]
    out = {"hourly_median": [None] * 24, "n_readings_by_hour": [0] * 24, "ratio": None,
           "hour_high": None, "hour_low": None, "n_readings": int(t.size), "n_days": 0}
    if t.size == 0:
        return out
    idx = pd.to_datetime(t, unit="s", utc=True).tz_convert(PRO_LOCAL_TZ)
    hh = np.asarray(idx.hour, dtype=int)
    out["n_days"] = int(pd.Index(idx.date).nunique())
    med = np.full(24, np.nan)
    cnt = np.bincount(hh, minlength=24)
    for h in range(24):
        if cnt[h]:
            med[h] = float(np.median(y[hh == h]))
    out["hourly_median"] = [None if not np.isfinite(v) else float(v) for v in med]
    out["n_readings_by_hour"] = [int(v) for v in cnt]
    fin = np.isfinite(med)
    if int(fin.sum()) >= 2:
        hi_h = int(np.nanargmax(med)); lo_h = int(np.nanargmin(med))
        out["hour_high"], out["hour_low"] = hi_h, lo_h
        if med[lo_h] > 0:
            out["ratio"] = float(med[hi_h] / med[lo_h])
    return out


def warning_sentence(profile, hours):
    """The plain warning, or None when the swing is under `SWING_WARN_RATIO` or not measured."""
    ratio = (profile or {}).get("ratio")
    if ratio is None or not np.isfinite(ratio) or float(ratio) < SWING_WARN_RATIO:
        return None
    s = (f"Band power at this band swings {float(ratio):.1f}-fold across the day (lowest "
         f"{int(profile['hour_low']):02d}:00, highest {int(profile['hour_high']):02d}:00)")
    if (hours or {}).get("n_reports"):
        first = int(np.floor(hours["earliest_hour"]))
        last = int(np.floor(hours["latest_hour"])) + 1
        s += (f"; its pain reports were filed {first:02d}:00-{last:02d}:00, so part of a link with "
              "pain may be the time of day")
    else:
        s += "; part of any link with pain may be the time of day"
    return s


def swing_block(profile, hours, *, freq_hz=None):
    """The `daily_swing` block one row or one chronic answer carries. ``profile`` is
    `hourly_profile`'s answer for the chronic frequency on the band (None: no home record at this
    band, and the profile and ratio are None); ``hours`` is `report_hours` for the reports the
    answer used."""
    hours = hours if hours is not None else report_hours([])
    if profile is None:
        return {"status": STATUS_NO_HOME_RECORD, "chronic_freq_hz": None, "hourly_median": None,
                "n_readings_by_hour": None, "ratio": None, "hour_high": None, "hour_low": None,
                "n_readings": 0, "n_days": 0, "report_hours": hours, "warning": None,
                "warn_at_ratio": SWING_WARN_RATIO, "what": WHAT}
    w = warning_sentence(profile, hours)
    return {"status": STATUS_MEASURED, "chronic_freq_hz": (None if freq_hz is None else float(freq_hz)),
            "hourly_median": profile["hourly_median"],
            "n_readings_by_hour": profile["n_readings_by_hour"], "ratio": profile["ratio"],
            "hour_high": profile["hour_high"], "hour_low": profile["hour_low"],
            "n_readings": profile["n_readings"], "n_days": profile["n_days"],
            "report_hours": hours, "warning": w, "warn_at_ratio": SWING_WARN_RATIO, "what": WHAT}


def append_warning(why, warning):
    """``why`` with the warning appended the way C5's override warning is (". " between), or ``why``
    unchanged when there is no warning."""
    if not warning:
        return why
    if not why:
        return warning
    return str(why) + ". " + warning
