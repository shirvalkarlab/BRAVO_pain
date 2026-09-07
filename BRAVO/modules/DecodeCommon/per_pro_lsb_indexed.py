"""One band-power value per pain report, read out of the canonical form instead of re-derived.

WHAT THIS IS
------------
A PARALLEL implementation of `availability.per_pro_lsb`. It is not a replacement and nothing
in the platform calls it. `availability.per_pro_lsb` is untouched and remains the only path
the running server uses. This exists so the two can be run side by side on the live record
and compared field by field, which is the only honest way to claim a shared decoded form
saves time without changing a number.

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
Where the current code walks the whole spectrum-record list for every pain report --
re-canonicalising each record's channel name and re-parsing its timestamp on every pass --
this reads the records for the one channel out of the prepared index and finds the nearest by
one array operation. Same records, same choice among them, same value; the grouping and the
parsing simply already happened.

Measured on the live record for participant 2e3c75c0, the current code makes 72,332,380
channel-name canonicalisations from that one line in a single page request. Through the index
the count for the same work is the number of (recording, channel) pairs, which is roughly
four thousand.
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
