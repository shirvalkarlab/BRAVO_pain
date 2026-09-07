"""Track A step 7: how stimulation current moves band power, on every band, as a table Stim
Optimizer can read.

WHERE THE NUMBERS COME FROM. The three-source comparison already finds every run of rising current
on one side in the device's own current record, cuts the voltage trace into three second pieces,
and averages the settled pieces before each next increase into one band power per setting, at
every band centre on the tile grid (`three_source_response.build_for_participant`). That panel is
the input here. Nothing is re-derived from recordings: every power value in this table is copied
from that panel, so the table can be checked against the comparison value for value.

WHAT IS COMPUTED PER RUN AND BAND, and why each column is there.

* The number and range of currents actually tested, and how many pieces of recording stood
  behind each. The approved plan asks for these because the eight things that must never be
  claimed begin with concluding that a band does not respond from a narrow range of currents.
* A straight-line slope of the logarithm of band power on current, with its standard error and
  p-value from that one run's settings. The standard error is the honest statement of the smallest
  slope this run could have shown; a slope of about twice it would have been visible.
* Curvature, from `within_visit.amplitude_response_shape`: whether the relationship rises and then
  falls, where the peak sits, and how much more a curve explains than a straight line. This is not
  optional. A rise-then-fall response exists in this record (25 to 28 Hz on 2026-08-18, peaking
  near 2.1 mA) and a straight-line fit reads it as no response.
* The fold change from the lowest to the highest current, so a reader sees the size of the
  movement in the device's own units, not only whether a line through it is significant.
* Whether the band sits on a folded stimulation harmonic, reported and not acted on, and whether
  it lies inside the span over which the conversion into device units was checked.

ONE RUN IS ONE ROW PER BAND. A run is one visit, one side turned up, one sensing contact, one
stimulation rate. Rows are never pooled across visits here, because a result established on one
visit day must say so; pooling with the visit as the blocking factor is the reader's step, and the
`visit_date` and `run_label` columns are what make it possible.

Pure numpy, pandas and scipy, no Django, so it is testable on either runner.
"""
import json
import math

import numpy as np
import pandas as pd

#: The kind this table is stored under, and the rule version bumped when a column's meaning
#: changes. The columns themselves are part of the table.
KIND = "amplitude_effect_by_band"
RULE_VERSION = "v1_per_run"

#: The source panel that feeds the table: the calibrated voltage-trace route, which covers every
#: band. The device's own band power covers one band and its own spectrum is empty during ladders.
ROUTE = "time domain voltage trace"

#: Fewer currents than this and no straight line is fitted; fewer than the curvature routine's own
#: minimum (eight points) and no curve is fitted. Both are reported as "not assessed" rows that
#: still carry the currents tested, because an absent row would read as "no data" rather than
#: "too few currents".
MIN_POINTS_SLOPE = 3
MIN_POINTS_CURVATURE = 8


def _f(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return np.nan
    return x if np.isfinite(x) else np.nan


def _slope(x, y_log):
    """Straight line of log power on current: slope, intercept, standard error, p, r squared."""
    from scipy import stats
    if x.size < MIN_POINTS_SLOPE or np.unique(x).size < 2:
        return dict(slope_log_per_mA=np.nan, slope_intercept=np.nan, slope_stderr=np.nan,
                    slope_p=np.nan, r2_linear=np.nan, log_power_residual_sd=np.nan)
    r = stats.linregress(x, y_log)
    resid = y_log - (r.intercept + r.slope * x)
    dof = x.size - 2
    return dict(slope_log_per_mA=float(r.slope), slope_intercept=float(r.intercept),
                slope_stderr=float(r.stderr), slope_p=float(r.pvalue),
                r2_linear=float(r.rvalue ** 2),
                log_power_residual_sd=(float(np.sqrt(np.sum(resid ** 2) / dof)) if dof > 0
                                       else np.nan))


def _direction(slope, p):
    if not np.isfinite(slope) or not np.isfinite(p):
        return "not assessed"
    if p > 0.05:
        return "no straight-line movement detected across the currents tested"
    return ("band power rises as current rises" if slope > 0
            else "band power falls as current rises")


def rows_for_comparison(comparison, *, checked_lo_hz, checked_hi_hz, band_half_hz,
                        min_points_curvature=MIN_POINTS_CURVATURE):
    """One row per band centre for one run. Empty when the voltage-trace panel has nothing."""
    from StimOptimizer.routines import within_visit
    panel = next((p for p in comparison.panels if p.source == ROUTE), None)
    if panel is None or panel.absent_reason or not panel.spectrum_power:
        return []
    centres = np.asarray(panel.spectrum_centres_hz, dtype=float)
    currents = np.asarray(panel.current_mA, dtype=float)
    pieces = np.asarray(panel.n_pieces, dtype=float)
    P = np.asarray([[_f(v) for v in row] for row in panel.spectrum_power], dtype=float)
    if P.ndim != 2 or P.shape[0] != currents.size or P.shape[1] != centres.size:
        return []
    on_stim = list(panel.spectrum_band_is_measuring_the_stimulator or [])
    rows = []
    for j, centre in enumerate(centres):
        y = P[:, j]
        ok = np.isfinite(currents) & np.isfinite(y) & (y > 0)
        x, yy, pc = currents[ok], y[ok], pieces[ok]
        n = int(x.size)
        levels = np.unique(x)
        row = {
            "run_label": str(comparison.label),
            "visit_date": str(comparison.visit_date),
            "ramped_side": str(comparison.ramped_side),
            "sensing_contact": str(comparison.sensing_contact),
            "stimulation_rate_hz": _f(comparison.stimulation_rate_hz),
            "route": ROUTE,
            "band_center_hz": float(centre),
            "band_low_hz": float(centre) - float(band_half_hz),
            "band_high_hz": float(centre) + float(band_half_hz),
            "band_is_measuring_the_stimulator": (bool(on_stim[j]) if j < len(on_stim) else None),
            "band_inside_checked_conversion_range": bool(
                float(checked_lo_hz) - 1e-9 <= centre <= float(checked_hi_hz) + 1e-9),
            "n_settings_offered": int(panel.n_settings_offered),
            "n_currents_tested": int(levels.size),
            "current_min_mA": (float(levels.min()) if levels.size else np.nan),
            "current_max_mA": (float(levels.max()) if levels.size else np.nan),
            "currents_mA": json.dumps([float(v) for v in x]),
            "n_pieces_total": int(np.nansum(pc)) if n else 0,
            "n_pieces_min_per_setting": (int(np.nanmin(pc)) if n else 0),
            "power_at_min_current": (float(yy[np.argmin(x)]) if n else np.nan),
            "power_at_max_current": (float(yy[np.argmax(x)]) if n else np.nan),
        }
        row["fold_max_over_min"] = (row["power_at_max_current"] / row["power_at_min_current"]
                                    if n and row["power_at_min_current"] > 0 else np.nan)
        row.update(_slope(x, np.log(yy)) if n else _slope(np.empty(0), np.empty(0)))
        row["smallest_detectable_slope_log_per_mA"] = (
            2.0 * row["slope_stderr"] if np.isfinite(row["slope_stderr"]) else np.nan)
        row["direction"] = _direction(row["slope_log_per_mA"], row["slope_p"])
        # curvature, on the settled powers themselves, as the routine defines it
        if n >= 3:
            shape = within_visit.amplitude_response_shape(x, yy, min_points=min_points_curvature)
        else:
            shape = dict(curves=False, peaks_inside=False, peak_mA=np.nan, p_curvature=np.nan,
                         r2_linear=np.nan, r2_quadratic=np.nan, n=n,
                         verdict=f"not assessed: {n} usable points")
        row["curves"] = bool(shape.get("curves", False))
        row["peaks_inside"] = bool(shape.get("peaks_inside", False))
        row["peak_mA"] = _f(shape.get("peak_mA"))
        row["p_curvature"] = _f(shape.get("p_curvature"))
        row["r2_quadratic"] = _f(shape.get("r2_quadratic"))
        row["quadratic_coefficient"] = (float(np.polyfit(x, yy, 2)[0])
                                        if n >= 3 and levels.size >= 3 else np.nan)
        row["n_points"] = n
        row["curvature_verdict"] = str(shape.get("verdict", "not assessed"))
        rows.append(row)
    return rows


def table_from_build(build, *, checked_lo_hz, checked_hi_hz, band_half_hz,
                     min_points_curvature=MIN_POINTS_CURVATURE):
    """The table for every comparison in what `build_for_participant` returned."""
    rows = []
    for comp in (build or {}).get("comparisons", []) or []:
        rows += rows_for_comparison(comp, checked_lo_hz=checked_lo_hz, checked_hi_hz=checked_hi_hz,
                                    band_half_hz=band_half_hz,
                                    min_points_curvature=min_points_curvature)
    return pd.DataFrame(rows).reset_index(drop=True)


def count_matches(table, build):
    """(fields compared, fields differing) between the table's copied power values and the panels
    they came from. Exact equality, NaN equal to NaN; never a tolerance."""
    compared = differ = 0
    for comp in (build or {}).get("comparisons", []) or []:
        panel = next((p for p in comp.panels if p.source == ROUTE), None)
        if panel is None or not panel.spectrum_power:
            continue
        sub = table[(table["run_label"] == comp.label)]
        currents = np.asarray(panel.current_mA, dtype=float)
        for j, centre in enumerate(panel.spectrum_centres_hz):
            got = sub[sub["band_center_hz"] == float(centre)]
            if len(got) != 1:
                compared += 2; differ += 2; continue
            col = np.asarray([_f(row[j]) for row in panel.spectrum_power], dtype=float)
            ok = np.isfinite(currents) & np.isfinite(col) & (col > 0)
            for name, pick in (("power_at_min_current", np.argmin), ("power_at_max_current", np.argmax)):
                expect = float(col[ok][pick(currents[ok])]) if ok.any() else np.nan
                have = _f(got.iloc[0][name])
                compared += 1
                if not ((expect == have) or (math.isnan(expect) and math.isnan(have))):
                    differ += 1
    return compared, differ
