"""Threshold occupancy check (T4, 2026-09-13; contest decision 150,
``artifacts/contest_2026-09-13_SYNTHESIS.md`` section 4).

WHAT THIS ANSWERS. The device decides its state by comparing one averaged band-power reading
against two fixed numbers. If almost none of the participant's own readings ever land between the
two thresholds, the device is not really working as a Dual Threshold controller: it is a single
threshold with a second number typed in for show, and the amplitude will sit at one end or the
other almost all the time. A second, separate way the same thing happens: the pair can be placed
well off the level the signal actually sits at, so the signal spends nearly all its time on one
side of the whole pair even though the pair itself is wide enough. The contest found real,
measured examples of both: the device's own programmed pair (167 / 166) leaves 0.3% of readings
between the two numbers, and the stored pair on the L 1-3+ contact is placed about sixty device
units below the level the signal actually sits at
(``artifacts/contest_2026-09-13_fopdt_lambda.md``, "the stored pair today is centred 61 units
below the level the signal actually sits at"). This file checks both, plainly, for whichever pair
is on the card.

WHAT IT DELIBERATELY DOES NOT DO. It does not run the controller: no onset, no persistence rule,
no transitions. It counts where the raw averaged readings land relative to the two numbers.
``design_rule.py``'s own noise simulation and ``simulation.py``'s replay are the places a
persistence rule is applied to a hypothetical trajectory. This check answers a simpler, prior
question: is there anywhere for a Dual Threshold controller to hold "between" at all, on this
participant's own recorded signal?

THE AVERAGING DURATION USED IS THE ONE IN FORCE ON THE CARD (``timing_recommendation``'s own
value), not the device's native 3 s tile clock, because the averaged reading is the quantity the
device actually compares against the thresholds. Readings are averaged onto that duration inside
each unbroken stretch of recording, using the same device-clock grid ``design_rule.py`` and
``simulation.py`` already build (``simulation.regrid_stretches``), so a gap between two recordings
is never averaged across; an averaging window with no finite reading anywhere inside it is
dropped, never counted as a reading of zero or credited as "between" by default.
"""
from __future__ import annotations

from typing import Any, Dict

import numpy as np

#: Below this fraction of averaged readings landing between the two thresholds, the pair is
#: judged a single threshold in all but name (synthesis section 4, T4's own wording).
MIN_BETWEEN_FRAC = 0.10


def _windowed_average(grid_power: np.ndarray, *, dt_s: float, averaging_s: float) -> np.ndarray:
    """One stretch's device-clock (``dt_s``-spaced) readings, re-averaged onto non-overlapping
    ``averaging_s`` windows. A window with no finite reading anywhere inside it is dropped."""
    p = np.asarray(grid_power, dtype=float)
    if p.size == 0 or not (dt_s and dt_s > 0):
        return p[np.isfinite(p)]
    n_per = max(1, int(round(float(averaging_s) / float(dt_s))))
    if n_per <= 1:
        return p[np.isfinite(p)]
    out = []
    for i in range(0, p.size, n_per):
        seg = p[i:i + n_per]
        seg = seg[np.isfinite(seg)]
        if seg.size:
            out.append(float(seg.mean()))
    return np.asarray(out, dtype=float)


def averaged_readings(t, power, *, averaging_s: float) -> np.ndarray:
    """Every stretch of ``t``/``power`` (the same shape ``simulation_inputs_for_participant``
    returns), put on the device's own clock and re-averaged onto ``averaging_s`` windows,
    concatenated across stretches. A gap between two recordings is never averaged across -- see
    the module docstring.
    """
    from . import simulation as _sim

    t = np.asarray(t, dtype=float)
    p = np.asarray(power, dtype=float)
    ok = np.isfinite(t) & np.isfinite(p)
    t, p = t[ok], p[ok]
    if t.size < 2:
        return p
    order = np.argsort(t, kind="stable")
    t, p = t[order], p[order]
    if np.any(np.diff(t) == 0):                     # duplicated timestamps are collapsed by mean
        uniq, idx = np.unique(t, return_inverse=True)
        s_ = np.zeros(uniq.size)
        c = np.zeros(uniq.size)
        np.add.at(s_, idx, p)
        np.add.at(c, idx, 1.0)
        p = np.where(c > 0, s_ / np.maximum(c, 1.0), np.nan)
        t = uniq
    gaps = np.diff(t)
    pos = gaps[gaps > 0]
    if pos.size == 0:
        return p[np.isfinite(p)]
    dt_s = float(np.median(pos))
    a = np.zeros(t.size, dtype=float)                # amplitude is not used by this check
    stretches, _n_empty, _n_merged, _bounds = _sim.regrid_stretches(t, p, a, dt_s)
    out = [_windowed_average(grid_p, dt_s=dt_s, averaging_s=averaging_s)
           for _grid_t, grid_p, _grid_a in stretches]
    return np.concatenate(out) if out else np.empty(0)


def threshold_occupancy(t, power, *, upper, lower, averaging_s,
                        min_between_frac: float = MIN_BETWEEN_FRAC) -> Dict[str, Any]:
    """Where the participant's own averaged readings sit relative to one threshold pair.

    Returns a plain dict, never raising. ``available`` is ``False`` with a ``reason`` when there
    is nothing to report (no thresholds, no averaging duration, or too few averaged readings). On
    success: ``frac_above``, ``frac_between``, ``frac_below`` (fractions of the averaged readings,
    summing to 1.0), ``n_readings``, ``median_level`` (the participant's own median of that same
    averaged series), ``centre`` (``(upper + lower) / 2``), ``half_width``
    (``(upper - lower) / 2``, using the pair's own order), ``distance_from_median``
    (``centre - median_level``), ``warning`` (``True`` when ``frac_between`` is below
    ``min_between_frac`` OR the centre sits more than one half-width from the median), and
    ``why``, one plain-language sentence stating the actual numbers.
    """
    if upper is None or lower is None:
        return {"available": False, "reason": "no thresholds are placed for this candidate"}
    upper, lower = float(upper), float(lower)
    if averaging_s is None or not (float(averaging_s) > 0):
        return {"available": False,
                "reason": "no averaging duration is in force to average the readings onto"}
    readings = averaged_readings(t, power, averaging_s=float(averaging_s))
    readings = readings[np.isfinite(readings)]
    n = int(readings.size)
    if n < 3:
        return {"available": False, "n_readings": n,
                "reason": f"only {n} averaged reading(s), too few to report an occupancy fraction"}
    hi, lo = max(upper, lower), min(upper, lower)
    above = float((readings > hi).sum()) / n
    below = float((readings < lo).sum()) / n
    between = 1.0 - above - below
    median = float(np.median(readings))
    centre = 0.5 * (upper + lower)
    half_width = 0.5 * abs(upper - lower)
    distance = centre - median
    too_narrow = between < float(min_between_frac)
    off_centre = half_width > 0 and abs(distance) > half_width
    warning = bool(too_narrow or off_centre)

    parts = [
        f"At the {float(averaging_s):.0f} s averaging duration in force, {n} averaged readings: "
        f"{100 * above:.1f}% above the upper threshold, {100 * between:.1f}% between the two, "
        f"{100 * below:.1f}% below the lower threshold."
    ]
    if too_narrow:
        parts.append(
            f"Only {100 * between:.1f}% of readings land between the two thresholds, below the "
            f"{100 * float(min_between_frac):.0f}% this check treats as enough to behave as two "
            "thresholds rather than one: this pair is a single threshold in all but name."
        )
    if off_centre:
        # distance = centre - median: a POSITIVE distance means the centre sits ABOVE the median
        # (centre > median), a negative one means it sits BELOW it.
        side = "above" if distance > 0 else "below"
        parts.append(
            f"The pair's centre ({centre:.2f}) sits {abs(distance):.1f} device units {side} the "
            f"participant's own median reading ({median:.2f}), which is more than the pair's own "
            f"half-width (+-{half_width:.1f})."
        )
    return {
        "available": True, "n_readings": n, "averaging_s": float(averaging_s),
        "frac_above": above, "frac_between": between, "frac_below": below,
        "median_level": median, "centre": centre, "half_width": half_width,
        "distance_from_median": distance, "warning": warning,
        "min_between_frac": float(min_between_frac), "why": " ".join(parts),
    }
