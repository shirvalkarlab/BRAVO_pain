"""Frozen PSD->device-LSB conversion model: load + apply with an explicit fallback hierarchy.

The Percept reports band power in device "LSB" units; an offline Welch PSD reports physical uV^2.
When a committed band has its OWN device-LSB Timeline recordings, the deployable threshold is read
straight off those (percentile-anchored, the trustworthy path). When it does NOT -- the device never
sensed that exact (channel, frequency) long enough -- we fall back to a per-participant conversion
MODEL to *estimate* the LSB threshold from the physical uV^2 cut-point, and flag it ESTIMATED.

Why a frozen asset and not an on-request refit:
    The model embeds reviewed human judgment that must not silently recompute per request --
    Iglewicz-Hoaglin outlier omission per band, a hard n>=6-per-band reliability floor, the
    ZERO_THREE_RIGHT 8.8 Hz current-config restriction (>= 2026-03-01), and the 23.4 Hz
    exclusion. The reviewed fit is frozen to data/psd_lsb_models/<PARTICIPANT>.json and loaded here.

    The 8.8 Hz cut deserves a note because it is easy to mistake for the sensing-config
    change date (2025-12-05) and "correct" it there -- which would be wrong. Chronic 0-3R
    sensing was reassigned off the 8.8 Hz band on 2025-12-05, but the 8.8 Hz gain then falls
    through a multi-week settling transient (the chronic config bounced 28/24.4/26.4 Hz before
    settling), with a significant downward within-regime trend over Dec-Feb (-0.078 log10/month,
    p=0.039). Stationarity is only reached from ~2026-02-15 (trend p 0.72 -> 0.91 by 03-01). The
    >= 2026-03-01 cut isolates the stable current-config regime; moving it back to the config-
    change date would inject the higher-gain declining transient and bias the deployable threshold.

Model form (per channel):  log10(LSB) = a_f + b * log10(uV2),  b = per-channel common slope,
a_f = per-frequency intercept (= log10 of the device LSB at 1 uV^2 for that band). The frequency
dependence -- the device's on-board power gain falling as sensing frequency rises -- lives entirely
in a_f; a single slope b is shared across a channel's bands (the per-frequency slope difference is
not statistically supported -- LR n.s., adjusted-R^2 does not improve).

No electrode-impedance gain term. An impedance covariate (+ c*log10(Z_0-3R), Z from the 487
device DeviceImpedance logs joined nearest-in-time onto the ZERO_THREE_RIGHT pairing epochs) was
evaluated and REJECTED. It is significant under naive OLS (c=0.53, p=8e-8), which treats the
2985 epochs as independent when they share just 230 distinct session-level impedance
measurements -- pseudoreplication. With impedance-cluster-robust SE the term is n.s. (p=0.26).
It is also significant when forced in alongside a collinear calendar-time covariate (c=0.90,
p=0.016) -- but log10(Z) is collinear with calendar time (r=0.36), so that reflects shared slow
drift, not an impedance effect; the coefficient is unstable across specifications
(0.53 / 0.90 / 0.17 / the originally claimed 1.02); and in the deployable
>= 2026-03-01 regime -- with the full 2326-4712 ohm range present -- it is c=0.17, p=0.38. Even
the most generous estimate moves the deployable LSB threshold only 1.22x across the observed Z
range, smaller than the model's own residual scatter (1.83x, 1 sigma) and the validated k
uncertainty (1.26x). The term's original motivation (8.8 Hz drift) was itself retracted; it is a
slow-time proxy, not a physical gain correction, and is not adopted.

Fallback tiers (every non-measured result carries tier + estimated=True):
    tier 1  measured   : caller had device-LSB Timeline samples -- not this module's job.
    tier 2  band       : exact (channel, frequency) intercept from the model.
    tier 3  channel_freq: same channel, nearest fitted frequency intercept (gain extrapolated in Hz).
    tier 4  channel_pooled: channel's pooled robust gain k (proportional LSB = k*uV2), no freq model.
    none               : channel not in model and no pooled k -- cannot estimate.
"""
import json
import os

import numpy as np

_MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "data", "psd_lsb_models")
_CACHE = {}


def _canon(participant):
    """RCS08 / rcs08 / 'RCS08 ' -> 'RCS08'. Participant code, not the uid."""
    return str(participant or "").strip().upper()


def load_model(participant):
    """Return the frozen conversion model dict for a participant, or None. Cached per process."""
    code = _canon(participant)
    if code in _CACHE:
        return _CACHE[code]
    path = os.path.join(_MODEL_DIR, f"{code}.json")
    model = None
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                model = json.load(f)
        except (OSError, ValueError):
            model = None
    _CACHE[code] = model
    return model


def has_model(participant, channel=None):
    """True if a participant model exists (and, if channel given, covers that channel at all)."""
    m = load_model(participant)
    if m is None:
        return False
    if channel is None:
        return True
    return channel in (m.get("channels") or {})


def estimate_lsb(participant, channel, center_hz, psd_uv2):
    """Estimate device LSB from a physical PSD band power (uV^2) via the frozen model.

    Returns a dict ALWAYS carrying `estimated` and `tier`:
        {available, estimated=True, tier, lsb, k_effective, slope_b, center_hz,
         model_center_hz, r2, note}
    or {available: False, reason, estimated: True, tier: "none"} when no estimate is possible.

    psd_uv2 may be a scalar or array; `lsb` mirrors the input shape.
    """
    out = {"available": False, "estimated": True, "tier": "none", "channel": channel,
           "center_hz": (None if center_hz is None else float(center_hz))}
    m = load_model(participant)
    if m is None:
        out["reason"] = f"no conversion model for participant {participant}"
        return out
    ch = (m.get("channels") or {}).get(channel)
    if ch is None:
        out["reason"] = f"channel {channel} not in conversion model"
        return out

    P = np.asarray(psd_uv2, dtype=float)
    scalar = (P.ndim == 0)
    Pc = np.clip(P, 1e-12, None)

    bands = ch.get("bands") or []
    b = ch.get("common_slope_b")

    # ---- tier 2: exact band, or tier 3: nearest fitted frequency on the same channel ----
    if bands and b is not None and center_hz is not None:
        centers = np.array([bd["center_hz"] for bd in bands], dtype=float)
        j = int(np.argmin(np.abs(centers - float(center_hz))))
        bd = bands[j]
        a_f = float(bd["intercept_a"])
        lsb = np.power(10.0, a_f + float(b) * np.log10(Pc))
        exact = abs(float(bd["center_hz"]) - float(center_hz)) < 1e-6
        k_eff = lsb / Pc                                  # effective LSB/uV^2 at this power (b!=1 => power-dependent)
        out.update({
            "available": True, "tier": "band" if exact else "channel_freq",
            "lsb": (float(lsb) if scalar else [float(x) for x in lsb]),
            "k_effective": (float(k_eff) if scalar else [float(x) for x in k_eff]),
            "slope_b": float(b), "model_center_hz": float(bd["center_hz"]),
            "intercept_a": a_f, "r2": ch.get("r2"),
            "note": ("exact band match" if exact else
                     f"nearest fitted band {bd['center_hz']:.1f} Hz (requested {float(center_hz):.1f} Hz)"),
        })
        return out

    # ---- tier 4: channel pooled robust gain (proportional) ----
    k = ch.get("channel_pooled_k")
    if k is not None and np.isfinite(k):
        lsb = float(k) * Pc
        out.update({
            "available": True, "tier": "channel_pooled",
            "lsb": (float(lsb) if scalar else [float(x) for x in lsb]),
            "k_effective": float(k), "slope_b": 1.0, "model_center_hz": None,
            "r2": None,
            "note": f"channel pooled gain k={float(k):.1f} LSB/uV^2 (no per-frequency model; proportional)",
        })
        return out

    out["reason"] = f"channel {channel} has no fitted band and no pooled gain"
    return out


def model_plot_payload(participant):
    """Compact payload for the deployment-panel plots: per-channel common slope + per-band
    intercept (gain anchor) + pooled k. Returns {available, participant, channels:[...]} so the
    frontend can draw (1) gain-anchor-vs-frequency per channel and (2) the per-channel fit lines.
    """
    m = load_model(participant)
    if m is None:
        return {"available": False, "reason": f"no conversion model for {participant}"}
    chans = []
    for ch_key, ch in (m.get("channels") or {}).items():
        bands = [{"center_hz": bd["center_hz"], "lsb_at_1uv2": bd["LSB_at_1uV2"],
                  "intercept_a": bd["intercept_a"], "intercept_ci": bd.get("intercept_ci"),
                  "n": bd.get("n")} for bd in (ch.get("bands") or [])]
        chans.append({"channel": ch_key, "fittable": bool(ch.get("fittable")),
                      "common_slope_b": ch.get("common_slope_b"), "r2": ch.get("r2"),
                      "channel_pooled_k": ch.get("channel_pooled_k"),
                      "n_clusters": ch.get("n_clusters"), "bands": bands,
                      "scatter": ch.get("scatter") or []})
    return {"available": True, "participant": _canon(participant),
            "schema": m.get("schema"), "pipeline": m.get("pipeline"),
            "special": (m.get("pipeline") or {}).get("special") if isinstance(m.get("pipeline"), dict) else None,
            "channels": chans}
