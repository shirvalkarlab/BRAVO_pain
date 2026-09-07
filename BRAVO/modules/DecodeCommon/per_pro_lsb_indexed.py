"""One band-power value per pain report, read out of the canonical form instead of re-derived.

WHAT THIS IS
------------
The readers behind `availability.per_pro_lsb` and `availability.per_pro_lsb_spectrum` since
Track B steps 2 and 3. The original per-call scans are kept in `availability` as
`_per_pro_lsb_scan` and `_per_pro_lsb_spectrum_scan`: they are the specification these readers
are proven equal to (`tests/test_decode_common.py`, on constructed recordings where the answer
is known) and the path `availability.USE_CHANNEL_INDEX = False` falls back to.

WHAT IS IDENTICAL, AND WHY THAT MATTERS
---------------------------------------
The three-tier precedence, both tolerance windows, the dropped-packet rejection, the
saturation rule, the fall-through from a saturated voltage window to the device spectrum, the
inclusive band edges, the tie-break that keeps the FIRST of two equidistant spectrum records,
and every string written into `reason` are all reproduced exactly. The two calibrated
constants are reached through the same `analytics.td_to_lsb` and `analytics.device_psd_to_lsb`
calls, so no conversion is re-derived here and no new constant is introduced.

WHAT CHANGES, AND IT IS ONLY ONE THING
--------------------------------------
Where the scans walk the whole spectrum-record list for every pain report -- re-canonicalising
each record's channel name and re-parsing its timestamp on every pass -- these read the records
for the one channel out of the prepared index and find the nearest by one array operation. Same
records, same choice among them, same value; the grouping and the parsing simply already
happened, once per request rather than once per channel and per report.

Measured on the live record for participant 2e3c75c0 before the change, the scan made
72,332,380 channel-name canonicalisations from that one line in a single page request. The
count after the change is in the progress log beside the run that produced it.
"""
import numpy as np


def per_pro_lsb_indexed(pro_times, native_lsb_series, channel, center_hz, *,
                        index,
                        analytics,
                        band_half_hz=2.5,
                        native_tol_s=120.0,
                        extent_s=None,
                        max_missing_frac=0.10,
                        saturation_uv=4000.0,
                        tier_native="native",
                        tier_td="td_transform",
                        tier_bridge="psd_bridge"):
    """Return one record per pain report, in report order.

    `index` is a `ChannelIndex` from `representation.build_channel_index`. `analytics` is the
    Biomarkers analytics module, passed in rather than imported so this file has no upward
    dependency on the Biomarkers package and can be tested with a stand-in.

    The tier names and the saturation rail are arguments with the platform's current values as
    defaults, so the caller can pass the platform's own constants and a drift between the two
    shows up as a failing comparison rather than as a silent disagreement.
    """
    from .representation import canon_channel

    if extent_s is None:
        extent_s = analytics.TRANSFORM_CENTERED_EXTENT_SECONDS
    half = float(band_half_hz)
    lo_hz = float(analytics.LSB_VALIDATED_HZ_LO)
    hi_hz = float(analytics.LSB_DEPLOYABLE_HZ_HI)
    channel = canon_channel(channel)
    center_hz = float(center_hz)

    # ---- tier 1: the device actually sensed this band near the report -------------------
    # Unchanged from the current code, including the fail-closed rule: if the flag marking
    # which points are device-sensed rather than modelled is missing or the wrong length,
    # every point is treated as modelled so this tier can win nothing and the lower tiers
    # serve the report instead.
    nat_t = np.empty(0)
    nat_y = np.empty(0)
    if native_lsb_series is not None:
        y = np.asarray(native_lsb_series.get("y"), dtype=float)
        hz = np.asarray(native_lsb_series.get("center_hz"), dtype=float)
        modeled = native_lsb_series.get("modeled") or []
        is_modeled = (np.array([bool(m) for m in modeled], dtype=bool)
                      if len(modeled) == y.size else np.ones(y.size, bool))
        t = np.asarray(native_lsb_series.get("t"), dtype=float)
        band = (np.isfinite(y) & np.isfinite(hz) & ~is_modeled
                & (hz >= center_hz - half) & (hz <= center_hz + half))
        nat_t = t[band]
        nat_y = y[band]

    # ---- tier 2 and tier 3 inputs: read, not rebuilt ------------------------------------
    td_bucket = index.td(channel)
    td_prepped = td_bucket["traces"]
    td_t0 = td_bucket["t0"]

    psd_bucket = index.psd(channel)
    psd_t = psd_bucket["t"]
    psd_records = psd_bucket["records"]
    bridge_in_range = lo_hz <= center_hz <= hi_hz

    out = []
    for tp in np.asarray(pro_times, dtype=float):
        rec = {"t": float(tp), "lsb": None, "tier": None, "center_hz": center_hz,
               "used_s": 0.0, "saturated": False, "reason": ""}

        # (1) device-sensed in band
        if nat_t.size:
            d = np.abs(nat_t - tp)
            j = int(np.argmin(d))
            if d[j] <= native_tol_s:
                rec.update(lsb=float(nat_y[j]), tier=tier_native,
                           reason="device-sensed in band")
                out.append(rec)
                continue

        # (2) the voltage trace, transformed. Only a trace that STARTED at or before the
        # report can cover it, so bisecting the start times skips the rest.
        matched_td = False
        hi = int(np.searchsorted(td_t0, tp, side="right")) if td_t0.size else 0
        for pr in td_prepped[:hi]:
            if not (pr["t0"] <= tp <= pr["t1"]):
                continue
            fs = pr["fs"]
            slice_uv, used_s = analytics.transform_centered_window(
                pr["col"], fs, tp - pr["t0"], extent_s=extent_s, missing=pr["miss"],
                max_missing_frac=max_missing_frac)
            if slice_uv is None:
                continue
            if np.nanmax(np.abs(slice_uv)) >= saturation_uv:
                rec["saturated"] = True
                rec["reason"] = "TD window saturated (ADC rail)"
                continue
            lsb = analytics.td_to_lsb(slice_uv, fs, center_hz, half_hz=half,
                                      step_samples=pr["step"])
            if lsb is None or not np.isfinite(lsb) or lsb <= 0:
                continue
            rec.update(lsb=float(lsb), tier=tier_td, used_s=float(used_s), saturated=False,
                       reason="direct TD->LSB transform (k=%.2f)"
                              % analytics.LSB_PER_UV2_TRANSFORM)
            matched_td = True
            break
        if matched_td:
            out.append(rec)
            continue

        # (3) the device's own spectrum, bridged. Reached also when tier 2 found a trace but
        # every overlapping window was saturated -- a clean spectrum reading beats a clipped
        # voltage window, and the saturated flag stays set so the reader still sees it.
        if bridge_in_range and psd_t.size:
            d = np.abs(psd_t - tp)
            # `argmin` returns the FIRST smallest, which is the same record the current
            # linear scan keeps: it only replaces its running best on a STRICTLY smaller
            # distance, so the earliest of two equidistant records wins there too.
            j = int(np.argmin(d))
            if d[j] <= native_tol_s:
                ev = psd_records[j]
                lsb = analytics.device_psd_to_lsb(ev.get("freq"), ev.get("power"), center_hz,
                                                  half_hz=half)
                if lsb is not None and np.isfinite(lsb) and lsb > 0:
                    rec.update(lsb=float(lsb), tier=tier_bridge,
                               reason="PSD-only event bridge (k=%.2f)"
                                      % analytics.LSB_PER_DEVICE_PSD)
                    out.append(rec)
                    continue

        rec["reason"] = rec["reason"] or "no source in any tier"
        out.append(rec)
    return out


def per_pro_lsb_spectrum_indexed(pro_times, channel, centers_hz, *,
                                 index,
                                 analytics,
                                 band_half_hz=2.5,
                                 native_tol_s=120.0,
                                 extent_s=None,
                                 max_missing_frac=0.10,
                                 saturation_uv=4000.0,
                                 tier_td="td_transform",
                                 tier_bridge="psd_bridge"):
    """One full-spectrum record per pain report, read out of the canonical form.

    The indexed twin of `availability.per_pro_lsb_spectrum`, reproduced rule for rule: the
    voltage-trace route first, over every centre at once, calibrated wherever the band has
    signal; else the nearest device-spectrum record within the tolerance, over the full grid,
    calibrated only inside the checked conversion range; the railed-window flag that stays set
    when the bridge serves the report; the same `reason` strings. What changes is only where the
    prepared traces and the grouped spectrum records come from.
    """
    from .representation import canon_channel

    if extent_s is None:
        extent_s = analytics.TRANSFORM_CENTERED_EXTENT_SECONDS
    half = float(band_half_hz)
    lo_hz = float(analytics.LSB_VALIDATED_HZ_LO)
    hi_hz = float(analytics.LSB_DEPLOYABLE_HZ_HI)
    channel = canon_channel(channel)
    centers = np.atleast_1d(np.asarray(centers_hz, dtype=float))
    nC = centers.size
    cal_band = (centers >= lo_hz - 1e-9) & (centers <= hi_hz + 1e-9)

    td_bucket = index.td(channel)
    td_prepped = td_bucket["traces"]
    td_t0 = td_bucket["t0"]
    psd_bucket = index.psd(channel)
    psd_t = psd_bucket["t"]
    psd_records = psd_bucket["records"]

    none_vec = [None] * nC
    out = []
    for tp in np.asarray(pro_times, dtype=float):
        rec = {"t": float(tp), "tier": None, "lsb": list(none_vec),
               "calibrated": [False] * nC, "center_hz": [float(c) for c in centers],
               "used_s": 0.0, "saturated": False, "reason": ""}

        matched_td = False
        hi = int(np.searchsorted(td_t0, tp, side="right")) if td_t0.size else 0
        for pr in td_prepped[:hi]:
            if not (pr["t0"] <= tp <= pr["t1"]):
                continue
            fs = pr["fs"]
            slice_uv, used_s = analytics.transform_centered_window(
                pr["col"], fs, tp - pr["t0"], extent_s=extent_s, missing=pr["miss"],
                max_missing_frac=max_missing_frac)
            if slice_uv is None:
                continue
            if np.nanmax(np.abs(slice_uv)) >= saturation_uv:
                rec["saturated"] = True
                rec["reason"] = "TD window saturated (ADC rail)"
                continue
            bp = np.atleast_1d(analytics.td_transform_band_power(
                slice_uv, fs, centers, half_hz=half, step_samples=pr["step"]))
            lsb = np.where(np.isfinite(bp) & (bp > 0),
                           analytics.LSB_PER_UV2_TRANSFORM * bp, np.nan)
            rec["tier"] = tier_td
            rec["lsb"] = [float(v) if np.isfinite(v) else None for v in lsb]
            rec["calibrated"] = [bool(np.isfinite(v)) for v in lsb]
            rec["used_s"] = float(used_s)
            rec["saturated"] = False
            rec["reason"] = "direct TD->LSB transform (k=%.2f)" % analytics.LSB_PER_UV2_TRANSFORM
            matched_td = True
            break
        if matched_td:
            out.append(rec)
            continue

        if psd_t.size:
            d = np.abs(psd_t - tp)
            j = int(np.argmin(d))            # FIRST smallest, as the linear scan's strict "<" keeps
            if d[j] <= native_tol_s:
                ev = psd_records[j]
                bp = np.atleast_1d(analytics.device_psd_band_power(
                    ev.get("freq"), ev.get("power"), centers, half_hz=half))
                lsb = np.where(np.isfinite(bp) & (bp > 0),
                               analytics.LSB_PER_DEVICE_PSD * bp, np.nan)
                rec["tier"] = tier_bridge
                rec["lsb"] = [float(v) if np.isfinite(v) else None for v in lsb]
                rec["calibrated"] = [bool(np.isfinite(v) and cal_band[i]) for i, v in enumerate(lsb)]
                rec["reason"] = ("PSD-only event bridge (k=%.2f); calibrated only in [%.1f,%.1f] Hz"
                                 % (analytics.LSB_PER_DEVICE_PSD, lo_hz, hi_hz))
                out.append(rec)
                continue

        rec["reason"] = "no TD coverage and no coincident PSD event"
        out.append(rec)
    return out
