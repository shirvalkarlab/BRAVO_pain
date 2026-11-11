"""The timeline's detail panel (item P-18; the PI's go-ahead, 2026-10-06): what the device recorded
for ONE clicked mark on the Biomarkers top timeline.

A click names a contact pair, the kind of mark and its start time (the fields every record of the
acquisition timeline already carries: `channel`, `dtype`, `product`, `t_start`). This returns, for
that pair only:

  * `trace`      the voltage trace of the recording (µV), when the recording has one;
  * `psd`        the device's own PSD of it (montage and survey: µVp; patient event: µV), when the
                 device made one;
  * `band_power` the device's own sensed band power (LSB) on this pair within `window_s` of the
                 clicked time (chronic record and BrainSense streaming; never the modelled values).

Device values at face value, never rescaled; no log; no pain rating (decision 216: the acquisition
timeline reads no pain report); no other contact pair's values. A piece the mark does not have is
named in `missing` instead of being left blank. Django-free.
"""
import numpy as np

#: How far apart a clicked mark's time and a recording's start may be and still be the same
#: recording (the timeline sends the start time it was given, so this only absorbs rounding).
MATCH_TOLERANCE_S = 1.0
#: The band-power window either side of the clicked time.
BAND_POWER_WINDOW_S = 12 * 3600.0
#: Above this many samples a trace is sent as the minimum and maximum of each run of samples, so a
#: spike or a dropout stays visible (an average or a stride could hide it).
MAX_TRACE_POINTS = 60_000
MAX_BAND_POWER_POINTS = 8_000

_PAIR_WORDS = ("ZERO", "ONE", "TWO", "THREE")


def canon_pair(name):
    """`ZERO_AND_THREE_LEFT_RING` and `ZERO_THREE_LEFT` -> `ZERO_THREE_LEFT`; the timeline's own
    lane rule (`normalizeChannel`): a two-contact pair on one side, lower contact first. Anything
    else (a segment, an electrode-identifier channel) is returned upper-cased, unchanged."""
    up = str(name).upper()
    if "SEGMENT" in up:
        return up
    side = "LEFT" if "LEFT" in up else ("RIGHT" if "RIGHT" in up else "")
    toks = [t for t in up.replace("_AND_", "_").split("_") if t in _PAIR_WORDS]
    if len(toks) >= 2 and side and toks[0] != toks[1]:
        a, b = sorted((_PAIR_WORDS.index(toks[0]), _PAIR_WORDS.index(toks[1])))
        return f"{_PAIR_WORDS[a]}_{_PAIR_WORDS[b]}_{side}"
    return up


def _epoch(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if np.isfinite(f) else None


def _find(recs, pair, t_start):
    """(recording, column) of the recording on `pair` starting within MATCH_TOLERANCE_S of
    `t_start`, nearest first; (None, None) when there is none."""
    best = (None, None, None)
    for r in recs or []:
        if not isinstance(r, dict):
            continue
        t0 = _epoch(r.get("StartTime"))
        if t0 is None or abs(t0 - t_start) > MATCH_TOLERANCE_S:
            continue
        names = [canon_pair(n) for n in (r.get("ChannelNames") or [])]
        if pair not in names:
            continue
        d = abs(t0 - t_start)
        if best[2] is None or d < best[2]:
            best = (r, names.index(pair), d)
    return best[0], best[1]


def _trace(rec, col, max_points):
    data = np.asarray(rec.get("Data"), dtype=float)
    if data.ndim != 2 or col >= data.shape[1]:
        return None
    y = data[:, col].copy()
    miss = rec.get("Missing")
    if miss is not None:
        m = np.asarray(miss)
        if m.shape == data.shape:
            y[m[:, col] > 0] = np.nan
    y[~np.isfinite(y)] = np.nan
    n = int(y.size)
    fs = float(rec.get("SamplingRate") or 250.0)
    out = {"unit": "µV", "fs": fs, "t0": float(_epoch(rec.get("StartTime"))), "n": n,
           "dur_s": n / fs, "every_nth": 1, "envelope": False}
    if n <= max_points:
        out["x_s"] = None                      # sample i is at t0 + i / fs
        out["y"] = [None if not np.isfinite(v) else float(v) for v in y]
        return out
    # minimum and maximum of each run of samples, in time order within the run
    runs = max_points // 2
    step = int(np.ceil(n / runs))
    xs, ys = [], []
    for s in range(0, n, step):
        seg = y[s:s + step]
        ok = np.isfinite(seg)
        if not ok.any():
            xs.append((s) / fs); ys.append(None)
            continue
        i_lo = int(np.nanargmin(seg)); i_hi = int(np.nanargmax(seg))
        for i in sorted((i_lo, i_hi)):
            xs.append((s + i) / fs); ys.append(float(seg[i]))
    out.update({"x_s": xs, "y": ys, "every_nth": step, "envelope": True})
    return out


def _montage_psd(rec, col):
    desc = rec.get("Descriptor") if isinstance(rec.get("Descriptor"), dict) else {}
    med = desc.get("MedtronicPSD") if isinstance(desc.get("MedtronicPSD"), list) else []
    if col >= len(med) or not isinstance(med[col], dict):
        return None
    p = med[col]
    f, m = p.get("LFPFrequency"), p.get("LFPMagnitude")
    if not f or not m or len(f) != len(m):
        return None
    return {"unit": "µVp", "freq": [float(v) for v in f], "mag": [float(v) for v in m],
            "peak_hz": _epoch(p.get("PeakFrequencyInHertz")),
            "artifact_status": p.get("ArtifactStatus"), "source": "montage or survey"}


def _event_psd(rows, pair, t_start):
    best, bd = None, None
    for r in rows or []:
        t = _epoch(r.get("t"))
        if t is None or abs(t - t_start) > MATCH_TOLERANCE_S or canon_pair(r.get("channel")) != pair:
            continue
        if bd is None or abs(t - t_start) < bd:
            best, bd = r, abs(t - t_start)
    if best is None or best.get("freq") is None or best.get("power") is None:
        return None
    return {"unit": "µV", "freq": [float(v) for v in best["freq"]],
            "mag": [float(v) for v in best["power"]], "peak_hz": None, "artifact_status": None,
            "source": "patient event"}


def _band_power(native, pair, t_lo, t_hi, max_points):
    t, y, cen, src = [], [], [], []
    for ch, d in (native or {}).items():
        if canon_pair(ch) != pair:
            continue
        tt = np.asarray(d.get("t") or [], dtype=float)
        keep = np.flatnonzero((tt >= t_lo) & (tt <= t_hi))
        if not keep.size:
            continue
        yy, cc, ss = d.get("y") or [], d.get("center_hz") or [], d.get("source") or []
        t.extend(tt[keep].tolist())
        y.extend(float(yy[i]) for i in keep)
        cen.extend(cc[i] if i < len(cc) else None for i in keep)
        src.extend(ss[i] if i < len(ss) else None for i in keep)
    if not t:
        return None
    order = np.argsort(t, kind="stable")
    step = int(np.ceil(len(order) / max_points)) if len(order) > max_points else 1
    order = order[::step]
    return {"unit": "LSB", "t": [t[i] for i in order], "y": [y[i] for i in order],
            "center_hz": [cen[i] for i in order], "source": [src[i] for i in order],
            "n": len(t), "every_nth": step, "window": [t_lo, t_hi]}


def build_detail(sel, *, td_recs, psd_recs, event_rows, native_lsb,
                 window_s=BAND_POWER_WINDOW_S, max_trace_points=MAX_TRACE_POINTS,
                 max_band_power_points=MAX_BAND_POWER_POINTS):
    """The detail of one clicked mark. `sel` is the request: `Channel`, `Dtype` ("timedomain",
    "psd" or "bandpower"), `Product` (the record's own product key) and `TStart` (epoch s)."""
    pair = canon_pair(sel.get("Channel"))
    dtype = str(sel.get("Dtype") or "")
    product = str(sel.get("Product") or "")
    t_start = _epoch(sel.get("TStart"))
    out = {"pair": pair, "dtype": dtype, "product": product, "t_start": t_start,
           "trace": None, "psd": None, "band_power": None, "recording": None, "missing": {}}
    if t_start is None:
        out["missing"]["all"] = "the mark carried no time"
        return out

    rec, col = None, None
    if dtype == "timedomain" and product != "montage_td":
        rec, col = _find(td_recs, pair, t_start)
    elif dtype == "timedomain" or (dtype == "psd" and product != "patient_event"):
        rec, col = _find(psd_recs, pair, t_start)

    if rec is not None:
        out["recording"] = {"type": rec.get("RecordingType"), "t0": _epoch(rec.get("StartTime")),
                            "dur_s": _epoch(rec.get("Duration"))}
        out["trace"] = _trace(rec, col, max_trace_points)
        out["psd"] = _montage_psd(rec, col)
    elif product == "patient_event":
        out["psd"] = _event_psd(event_rows, pair, t_start)

    if dtype in ("timedomain", "psd"):
        if out["trace"] is None:
            out["missing"]["trace"] = ("no voltage trace: the device keeps none for a patient event"
                                       if product == "patient_event" else
                                       "no recording on this contact pair starts at this time")
        if out["psd"] is None:
            out["missing"]["psd"] = "the device made no PSD of this recording"

    end = t_start + float((out["recording"] or {}).get("dur_s") or 0.0)
    out["band_power"] = _band_power(native_lsb, pair, t_start - window_s, end + window_s,
                                    max_band_power_points)
    if out["band_power"] is None:
        out["missing"]["band_power"] = "the device sensed no band power on this pair within 12 h"
    return out
