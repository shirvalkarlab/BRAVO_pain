"""The clinic and at-home testing sheets' pain scores as extra ratings for the Biomarkers heat maps
(B5 of the 2026-09-15 review, decision 186), Django-free.

THE SCALE. The sheet's scores are 0-10 verbal ratings at half-point resolution. The page's NRS is
0-10 too, so "overall" goes in as it is; the three VAS scores are 0-100, so the sheet's "overall",
"left_leg" and "back" columns go in multiplied by ten (the PI, 2026-09-16: "rescale ... by
multiplying the NRS clinic or at-home verbal ratings by 10"). MPQ and relief have no sheet column
and get nothing.

WHY THIS IS A CAVEAT AND NOT JUST MORE DATA. Every sheet step was taken while current was being
stepped on purpose, so band power and pain both move with the ladder; and the steps come one a
minute inside a session, so 200 of them are perhaps 20 sessions' worth of near-duplicate ratings.
The p-value's block shuffle and the interval's block bootstrap (decision 183) size their blocks on
the rating series' own autocorrelation, which these steps raise -- the corrections adapt, the
effective sample size grows far less than the count. That is why the switch is off by default and
the count is on the page."""
from __future__ import annotations

import numpy as np

#: The page's pain score -> (the sheet column, the factor that puts the sheet's 0-10 on the page's
#: scale). A score not named here takes nothing from the sheets.
SHEET_COLUMN_FOR_METRIC = {
    "nrs": ("overall", 1.0),
    "vas": ("overall", 10.0),
    "left_leg_vas": ("left_leg", 10.0),
    "back_vas": ("back", 10.0),
}



# Aditya canonical compatibility imports/constants.

def _epoch_s(value):
    """UTC epoch seconds for a sheet step's `t_utc` (a Timestamp, a datetime, an ISO string), or
    None when there is none."""
    if value is None:
        return None
    try:
        import pandas as pd
        ts = pd.Timestamp(value)
        if pd.isna(ts):
            return None
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        return float(ts.timestamp())
    except (TypeError, ValueError):
        return None


def sheet_ratings_for_metric(steps, metric):
    """``(times_epoch_s, values_on_the_page_scale, setting)`` for the sheet steps that carry the
    page's score, in time order; a step with no time or no score is left out. ``steps`` is the
    ingested clinic-step table (a DataFrame or a list of row dicts, as `clinic_pain_steps` stores
    it). A score with no sheet column gives three empty arrays."""
    col_scale = SHEET_COLUMN_FOR_METRIC.get(str(metric))
    if col_scale is None or steps is None:
        return np.zeros(0), np.zeros(0), np.zeros(0, dtype=object)
    col, scale = col_scale
    rows = steps.to_dict("records") if hasattr(steps, "to_dict") else list(steps)
    t, v, s = [], [], []
    for r in rows:
        when = _epoch_s(r.get("t_utc"))
        raw = r.get(col)
        try:
            val = float(raw) if raw is not None else float("nan")
        except (TypeError, ValueError):
            val = float("nan")
        if when is None or not np.isfinite(val):
            continue
        t.append(when); v.append(val * float(scale)); s.append(str(r.get("setting") or ""))
    order = np.argsort(np.asarray(t, dtype=float), kind="stable") if t else np.zeros(0, int)
    return (np.asarray(t, dtype=float)[order], np.asarray(v, dtype=float)[order],
            np.asarray(s, dtype=object)[order])


def merge_ratings(pro_times, pro_values, sheet_times, sheet_values):
    """The page's ratings and the sheet's, as one series in time order, with a flag per rating
    that is True where it came from a sheet. With nothing to add the originals come back in their
    own order, every flag False."""
    pt = np.asarray(pro_times, dtype=float); pv = np.asarray(pro_values, dtype=float)
    st = np.asarray(sheet_times, dtype=float); sv = np.asarray(sheet_values, dtype=float)
    if st.size == 0:
        return pt, pv, np.zeros(pt.size, dtype=bool)
    t = np.concatenate([pt, st]); v = np.concatenate([pv, sv])
    flag = np.concatenate([np.zeros(pt.size, dtype=bool), np.ones(st.size, dtype=bool)])
    order = np.argsort(t, kind="stable")
    return t[order], v[order], flag[order]


# Retained active Aditya interfaces.
