"""The one place the participant's clock is named, and the one rule for "which calendar day".

WHY THIS IS ITS OWN FILE, 2026-09-12 (review B1). The pain-report timestamps are California
wall-clock time (decision 2), and `bravo_service` has always converted them to UTC through the
zone named here. But "the same calendar day" -- the join the chronic pain detector makes between
each 10-minute brain-signal sample and that day's pain ratings, and the daily series the pain cut
is computed on -- was taken from the UTC instant, whose day boundary falls at 4-5 pm in
California. Every rating filed in the late afternoon or evening was therefore averaged into the
NEXT day's samples: on RCS08, 201 of 766 timed ratings (26 %), all filed 16:00-19:59 local.

`bravo_service` imports Django's models at import time, so `adapter.py` and `pipeline.py` (which
the host suite imports without Django) cannot take the zone from there. Both take it from here,
and `bravo_service` binds it under the name it always used (`_PRO_LOCAL_TZ`), so there is one
definition and no import from the service into the adapter.

`local_calendar_day` is the rule. Every "calendar day" the Biomarkers page derives from a UTC
instant -- the chronic join, the legacy same-day session join, the daily series behind the pain
cut, the per-day binarization preview and day counts, the timeline's date column -- goes through
it, so reversing the rule (should the PI want the UTC day back) is a change to this one function.
"""
from __future__ import annotations

import datetime as _dt

import pandas as pd

#: The participant's clock. REDCap records the survey time as local wall-clock with no offset; the
#: study is entirely in California, so this is the zone the naive strings are localized to before
#: they are converted to UTC, and the zone the calendar day is read in.
PRO_LOCAL_TZ = "America/Los_Angeles"


def local_calendar_day(when):
    """The California calendar date of a UTC instant (or of each instant in a Series / Index /
    list). A tz-naive input is read as UTC, which is what every instant in this module is once
    `_pro_timestamps_utc` and `adapter._to_datetime` have done their work; a tz-aware input is
    converted from its own zone. NaT stays NaT (a scalar NaT comes back as `None`, so it can be
    compared against a date the way the old `ts.date() if not pd.isna(ts) else None` was).

    Returns `datetime.date` objects: a Series of them for a Series, a plain Index of them for an
    Index or list, one for a scalar.
    """
    if isinstance(when, pd.Series):
        ts = pd.to_datetime(when, errors="coerce")
        aware = ts.dt.tz_localize("UTC") if ts.dt.tz is None else ts
        return aware.dt.tz_convert(PRO_LOCAL_TZ).dt.date
    if isinstance(when, (pd.Index, list, tuple)):
        idx = pd.DatetimeIndex(pd.to_datetime(list(when), errors="coerce"))
        aware = idx.tz_localize("UTC") if idx.tz is None else idx
        days = aware.tz_convert(PRO_LOCAL_TZ).date
        return pd.Index([None if pd.isna(d) else d for d in days], dtype=object)
    ts = pd.to_datetime(when, errors="coerce")
    if ts is None or pd.isna(ts):
        return None
    ts = pd.Timestamp(ts)
    aware = ts.tz_localize("UTC") if ts.tzinfo is None else ts
    return aware.tz_convert(PRO_LOCAL_TZ).date()


def is_calendar_date(value):
    """True for a plain `datetime.date` (not a datetime), the type `local_calendar_day` returns."""
    return isinstance(value, _dt.date) and not isinstance(value, _dt.datetime)
