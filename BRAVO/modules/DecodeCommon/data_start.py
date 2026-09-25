"""The moment a participant's record begins: the device's implant date (the PI, 2026-09-24).

WHY THIS EXISTS. A Percept carries its own history into its first clinic session. On RCS08 the
device record gives an implant date of 2025-07-16 18:06 UTC, yet the database also held:

- four "Past Therapy" snapshots dated 2025-01-18, 02-17, 03-19 and 04-18, exactly 30 days apart,
  read off the device at the 2025-07-17 session, which the settings stream turned into six months
  of "stimulation on at 2.9 / 3.1 mA" that never reached the patient;
- a chronic band-power log and patient-controller events from 2025-06-18, whose power was the same
  on both leads (median 40, 10th-90th 26-58) and about a tenth of the level after 07-19.

These are the device before it went in -- testing, most likely. Nothing dated before the implant
date is the patient, so every view and every product starts there. The rows stay in the database;
they are filtered where they are read, and a filter that cannot find a date filters nothing.

TWO RULES, BECAUSE THE DATA ARE TWO KINDS.
- A MEASUREMENT (a band-power sample, a patient event, a therapy snapshot) dated before the start
  is dropped.
- A SETTING is a state that holds until the next change. The setting in force at the moment of
  implant is post-implant information even though the change that set it was filed earlier, so
  the last change before the start is kept and moved to the start (`clamp_changes`). Dropping it
  would leave the current unknown until the first clinic change after implant.
"""
import logging

import numpy as np

_log = logging.getLogger(__name__)

#: A participant with no implant date on any device row: nothing is filtered.
NO_START = 0.0


def earliest_implant_s(dates):
    """The earliest positive, finite implant date (epoch seconds) among a participant's device
    rows, or ``NO_START``. A device row with no date carries 0, which is "unknown", not 1970."""
    vals = [float(d) for d in (dates or []) if d is not None]
    vals = [d for d in vals if np.isfinite(d) and d > 0]
    return min(vals) if vals else NO_START


def data_start_s(participant):
    """The participant's first valid time in epoch seconds, from the database's device rows.

    ``participant`` is a Participant row or its uid. Returns ``NO_START`` when the database cannot
    be read (the host test runner has no Django) or no device carries a date, and logs the first.
    """
    try:
        from Server import models
    except Exception:                                    # noqa: BLE001 -- host runner, no Django
        return NO_START
    try:
        uid = getattr(participant, "uid", participant)
        dates = models.DBSDevice.objects.filter(owner_id=str(uid)).values_list(
            "implanted_date", flat=True)
        return earliest_implant_s(list(dates))
    except Exception:                                    # noqa: BLE001 -- a read, never a failure
        _log.warning("data_start: could not read the implant date for %r; filtering nothing",
                     participant, exc_info=True)
        return NO_START


def keep_from(times_s, start_s):
    """Boolean mask: True where a measurement is at or after the start (all True with no start).
    A time that is not a number is kept: dropping it would be a claim about when it was taken."""
    t = np.asarray(times_s, dtype=float)
    if not start_s or start_s <= 0:
        return np.ones(t.shape, dtype=bool)
    return ~(t < float(start_s))


def clamp_changes(times_s, start_s):
    """For a sorted list of setting-change times: which changes to keep and at what time.

    Returns ``(keep, new_times)``. Changes at or after the start are kept as they are; of those
    before it, only the LAST is kept (it is the setting in force at implant), moved to the start.
    """
    t = np.asarray(times_s, dtype=float)
    keep = np.ones(t.shape, dtype=bool)
    new = t.copy()
    if not start_s or start_s <= 0 or t.size == 0:
        return keep, new
    before = np.flatnonzero(t < float(start_s))
    if before.size:
        keep[before] = False
        last = before[np.argmax(t[before])]
        keep[last] = True
        new[last] = float(start_s)
    return keep, new


def trim_segment(time_s, data, start_s, *, time_axis):
    """One recording's samples from the start on: ``(time, data)`` with every sample before the
    start removed along ``time_axis`` of ``data``, or ``None`` when nothing is left. With no start
    both come back unchanged. For the chronic log's files (time on axis 0) and the chronic view's
    segments (time on axis 1) alike."""
    t = np.asarray(time_s, dtype=float)
    keep = keep_from(t, start_s)
    if keep.all():
        return time_s, data
    if not keep.any():
        return None
    d = np.asarray(data)
    return t[keep], np.compress(keep, d, axis=time_axis)


def listed_date(date_s, start_s, *, spans_start=False):
    """How a row dated ``date_s`` is listed: its own date when on or after the start, the start
    when it began before and runs past it (a chronic file spanning the implant), None (not listed)
    when it lies wholly before it."""
    if not start_s or start_s <= 0 or date_s is None or not float(date_s) < float(start_s):
        return date_s
    return float(start_s) if spans_start else None
