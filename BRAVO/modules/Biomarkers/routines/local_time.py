"""Calendar dates for already-normalized instants and legacy local PRO wall times.

This helper changes grouping dates only. It never replaces an input timestamp,
clock recovery coordinate, or the absolute-time identity used to match a report.
"""
import numpy as np
import pandas as pd

PRO_LOCAL_TZ = "America/Los_Angeles"


def local_calendar_day(when, *, naive_is_local=False):
    """Return Pacific date(s), keeping missing values missing.

    Canonical PRO and decoded device timestamps use naive UTC or aware instants.
    Only the raw PRO library fallback sets ``naive_is_local=True``: its naive
    dates retain their original local wall-date meaning. Aware values always
    convert from their explicit zone. Series preserve their index; sequences
    return an Index. Input timestamps are never changed.
    """
    if isinstance(when, pd.Series):
        if naive_is_local:
            return when.map(lambda value: local_calendar_day(value, naive_is_local=True))
        return pd.to_datetime(when, errors="coerce", utc=True).dt.tz_convert(PRO_LOCAL_TZ).dt.date
    if isinstance(when, (pd.Index, list, tuple, np.ndarray)):
        if naive_is_local:
            return pd.Index([local_calendar_day(value, naive_is_local=True) for value in when],
                            dtype=object)
        days = pd.DatetimeIndex(pd.to_datetime(when, errors="coerce", utc=True)).tz_convert(PRO_LOCAL_TZ).date
        return pd.Index([None if pd.isna(day) else day for day in days], dtype=object)
    ts = pd.to_datetime(when, errors="coerce")
    if ts is None or pd.isna(ts):
        return None
    if ts.tzinfo is None:
        if naive_is_local:
            return ts.date()
        ts = ts.tz_localize("UTC")
    return ts.tz_convert(PRO_LOCAL_TZ).date()
