"""What stimulation current was running at a given moment, per side.

WHY THIS MODULE EXISTS. The heat map correlates a band's power against a pain score. On RCS08's
left lead both of those fall as the stimulation current rises, so a band can read as though it
tracks pain when what it tracks is the current that happened to be programmed at the time: measured
on 2026-09-22, every 21.5-26.5 Hz cell on L 1-3+ that the exploratory search called "supported"
loses its wholly positive interval once the current in force at each rating is taken out of it
(24.5 Hz at 60 s: 0.331, interval 0.165 to 0.494, falls to 0.170, interval -0.049 to 0.385). To
take it out, the grid needs one number per pain report: the milliamps running on that side when the
report was filed. This module supplies it.

WHERE THE NUMBER COMES FROM. The settings stream the device's own exported files carry, one row per
(timestamp, hemisphere), already parsed and filed once under the raw kind ``therapy_settings`` in
the one cache store. It is read here, never re-parsed: a second parser would be a second answer
(decision 30). The parser that writes it lives in Stim Optimizer, which this module does NOT and
MAY NOT import -- the dependency runs the other way -- so the store, whose raw kinds are exempt from
the self-derived refusal (decision 31), is the only path, and Biomarkers names itself as the
consumer when it reads.

WHAT IT IS NOT. It is not a claim that the current caused anything, and it is not the current the
band power was measured under (the matcher chooses a window of recording for each report; this is
the setting at the report itself). It is a covariate: the quantity that has to be held still before
"this band rises with pain" means anything on a record where the current was being changed.
"""
import logging

import numpy as np

_log = logging.getLogger(__name__)

#: The raw kind the device's dated settings are filed under, and this module's name when it reads.
THERAPY_SETTINGS_KIND = "therapy_settings"
CONSUMER = "biomarkers"

#: What the page calls the quantity, wherever it prints it.
CURRENT_LABEL = "the stimulation current in force (mA)"


def hemisphere_of_channel(channel):
    """"Left" or "Right" for a sensing contact pair like ``ONE_THREE_LEFT``; None when unknown.

    A pair names the lead it sits on, and a lead is one side's. The grid judges a band on its own
    side (decision 141), so the covariate is that side's current and never the other's.
    """
    name = str(channel or "").upper()
    if name.endswith("_LEFT") or name.endswith("LEFT"):
        return "Left"
    if name.endswith("_RIGHT") or name.endswith("RIGHT"):
        return "Right"
    return None


def settings_stream_for(participant_uid):
    """The stored settings stream as plain arrays, or None when nothing has been filed yet.

    Returns ``{"t_s": [N epoch seconds], "hemi": [N side names], "amp_mA": [N floats],
    "store_key": str or None, "n_rows": int}``. Never raises: a participant whose files have not
    been parsed yet has no stream, which is an answer ("not available"), not a failure.
    """
    try:
        try:
            from modules.CacheStore import store as _cache_store
        except ImportError:                                  # pragma: no cover - host spelling
            from CacheStore import store as _cache_store
        got = _cache_store.load_newest(THERAPY_SETTINGS_KIND, participant_uid, consumer=CONSUMER)
    except Exception as exc:                                 # noqa: BLE001 - an adjunct input
        _log.warning("Biomarkers: the stored settings stream could not be read for %s (%r)",
                     participant_uid, exc)
        return None
    if got is None:
        return None
    df, stamp = got if isinstance(got, tuple) else (got, None)
    if df is None or not hasattr(df, "columns"):
        return None
    cols = set(getattr(df, "columns", ()))
    if not {"t", "hemi", "amp"} <= cols or not len(df):
        return None
    import pandas as pd                                      # local: the store already needs it

    t = pd.to_datetime(df["t"], utc=True, errors="coerce")
    amp = pd.to_numeric(df["amp"], errors="coerce")
    keep = t.notna() & amp.notna()
    if not bool(keep.any()):
        return None
    t, amp = t[keep], amp[keep]
    hemi = df["hemi"][keep].astype(str)
    order = np.argsort(t.astype("int64").to_numpy())
    out = {
        "t_s": (t.astype("int64").to_numpy(dtype=float) / 1e9)[order],
        "hemi": hemi.to_numpy(dtype=object)[order],
        "amp_mA": amp.to_numpy(dtype=float)[order],
        "store_key": (stamp or {}).get("signature_key") if isinstance(stamp, dict) else None,
        "n_rows": int(keep.sum()),
    }
    try:
        from modules.DecodeCommon import data_start as _ds
    except ImportError:                                      # pragma: no cover - host spelling
        from DecodeCommon import data_start as _ds
    return from_data_start(out, _ds.data_start_s(participant_uid))


def from_data_start(stream, start_s):
    """The stream from the implant date on (the PI, 2026-09-24), per side: changes before it go,
    except the last, which is the setting in force at implant and is moved to it. The stored stream
    already does this from rule v3; this is here too because this module reads the NEWEST stored
    stream of any rule, which can be an older one until it is rebuilt."""
    if stream is None or not start_s or float(start_s) <= 0:
        return stream
    try:
        from modules.DecodeCommon import data_start as _ds
    except ImportError:                                      # pragma: no cover - host spelling
        from DecodeCommon import data_start as _ds
    t = np.asarray(stream["t_s"], dtype=float).copy()
    hemi = np.asarray(stream["hemi"], dtype=object)
    keep = np.ones(t.shape, dtype=bool)
    for h in set(hemi.tolist()):
        idx = np.flatnonzero(hemi == h)
        # rows at the same last pre-start time are all kept (session and history can coincide)
        k, new = _ds.clamp_changes(t[idx], start_s)
        before = t[idx] < float(start_s)
        if before.any():
            last_t = t[idx][before].max()
            k = k | (t[idx] == last_t)
            new = np.where(t[idx] == last_t, float(start_s), new)
        keep[idx] = k
        t[idx] = new
    order = np.argsort(t[keep], kind="stable")
    out = dict(stream)
    out["t_s"] = t[keep][order]
    out["hemi"] = hemi[keep][order]
    out["amp_mA"] = np.asarray(stream["amp_mA"], dtype=float)[keep][order]
    out["n_rows"] = int(keep.sum())
    return out


def current_in_force_at(times_s, stream, *, hemisphere):
    """The milliamps programmed on one side at each of ``times_s`` (epoch seconds).

    The newest setting at or before the moment, which is what "in force" means: a setting holds
    until the next one is filed. **Before the first setting on record the answer is unknown, not
    zero** -- a zero there would read as "stimulation was off", which the record does not say.
    """
    times = np.asarray(times_s, dtype=float)
    out = np.full(times.shape, np.nan, dtype=float)
    if stream is None or times.size == 0:
        return out
    hemi = np.asarray(stream.get("hemi"), dtype=object)
    side = np.asarray([str(h) == str(hemisphere) for h in hemi], dtype=bool)
    if not side.any():
        return out
    t_side = np.asarray(stream["t_s"], dtype=float)[side]
    a_side = np.asarray(stream["amp_mA"], dtype=float)[side]
    order = np.argsort(t_side, kind="stable")
    t_side, a_side = t_side[order], a_side[order]
    idx = np.searchsorted(t_side, times, side="right") - 1
    known = idx >= 0
    out[known] = a_side[idx[known]]
    return out


def current_in_force_for_reports(participant_uid, report_times_s, *, channel):
    """``(values, block)``: one current per pain report on the channel's own side, and what to say.

    ``block`` is what a page needs to state the adjustment honestly without opening the code:
    whether a stream was found, how many reports carry a current, how many distinct currents those
    are, which side, and the stream's own store key so the number can be traced.
    """
    side = hemisphere_of_channel(channel)
    block = {"available": False, "hemisphere": side, "label": CURRENT_LABEL,
             "n_reports": int(np.asarray(report_times_s, dtype=float).size),
             "n_with_current": 0, "n_distinct_values": 0, "store_key": None, "reason": None}
    if side is None:
        block["reason"] = f"the sensing contact pair {channel!r} does not name a side"
        return np.full(np.asarray(report_times_s, dtype=float).shape, np.nan), block
    stream = settings_stream_for(participant_uid)
    if stream is None:
        block["reason"] = ("no dated stimulation settings have been filed for this participant yet, "
                           "so the current in force cannot be looked up")
        return np.full(np.asarray(report_times_s, dtype=float).shape, np.nan), block
    values = current_in_force_at(report_times_s, stream, hemisphere=side)
    finite = np.isfinite(values)
    block.update(available=bool(finite.any()), n_with_current=int(finite.sum()),
                 n_distinct_values=int(np.unique(np.round(values[finite], 3)).size),
                 store_key=stream.get("store_key"))
    if not block["available"]:
        block["reason"] = (f"every pain report predates the first setting on record for the "
                           f"{side} side")
    return values, block
