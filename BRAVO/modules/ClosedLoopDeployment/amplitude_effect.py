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


def _raw_pairs(currents, column):
    """(x, yy, ok): currents and one band's power values restricted to indices where both are
    finite and the power is positive -- the exact filter every per-band row already applies, and
    the mask so a caller can restrict any other same-length array (such as piece counts) the same
    way."""
    ok = np.isfinite(currents) & np.isfinite(column) & (column > 0)
    return currents[ok], column[ok], ok


def _panel_grid(comparison):
    """(panel, centres, currents, P) for one comparison's voltage-trace panel, or (None, ...)
    when the panel is absent or its shapes disagree. Shared by `rows_for_comparison` and
    `_raw_pairs_for_band` so the two never read the panel two different ways."""
    panel = next((p for p in comparison.panels if p.source == ROUTE), None)
    if panel is None or panel.absent_reason or not panel.spectrum_power:
        return None, None, None, None
    centres = np.asarray(panel.spectrum_centres_hz, dtype=float)
    currents = np.asarray(panel.current_mA, dtype=float)
    P = np.asarray([[_f(v) for v in row] for row in panel.spectrum_power], dtype=float)
    if P.ndim != 2 or P.shape[0] != currents.size or P.shape[1] != centres.size:
        return None, None, None, None
    return panel, centres, currents, P


def _raw_pairs_for_band(comparison, band_center_hz):
    """(x, yy): the current and settled band-power values `rows_for_comparison` computes for one
    band centre in one comparison's voltage-trace panel, via the identical `_raw_pairs` filter.
    Empty arrays when the panel is absent or the centre is not on its grid -- built for
    `pooled_shape_for_band`, which needs the raw pairs for one band across every comparison in a
    build rather than the full per-band row `rows_for_comparison` returns.
    """
    panel, centres, currents, P = _panel_grid(comparison)
    if panel is None:
        return np.empty(0), np.empty(0)
    matches = np.where(np.isclose(centres, float(band_center_hz), atol=1e-6))[0]
    if matches.size == 0:
        return np.empty(0), np.empty(0)
    x, yy, _ = _raw_pairs(currents, P[:, int(matches[0])])
    return x, yy


def rows_for_comparison(comparison, *, checked_lo_hz, checked_hi_hz, band_half_hz,
                        min_points_curvature=MIN_POINTS_CURVATURE):
    """One row per band centre for one run. Empty when the voltage-trace panel has nothing."""
    from StimOptimizer.routines import within_visit
    panel, centres, currents, P = _panel_grid(comparison)
    if panel is None:
        return []
    pieces = np.asarray(panel.n_pieces, dtype=float)
    on_stim = list(panel.spectrum_band_is_measuring_the_stimulator or [])
    rows = []
    for j, centre in enumerate(centres):
        y = P[:, j]
        x, yy, ok = _raw_pairs(currents, y)
        pc = pieces[ok]
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


def pooled_shape_for_band(build, band_center_hz, sensing_contact, *, min_points=8):
    """The pooled, cluster-robust within-visit dose-response direction for one band centre **on
    one sensing contact**, across every run on that contact in what `build_for_participant`
    returned -- built for the closed-loop consistency check (`direction_consistency.py`), which
    needs a single answer to "does this band's power rise or fall as current rises, on this
    electrode" rather than one run's own slope (this project's own rule against calling a result
    established on one visit day).

    ``sensing_contact`` is required, not optional: different sensing contacts are different
    physical electrodes, and pooling their runs together would average dose-response curves from
    channels with no reason to share one, exactly the kind of silent conflation this project's own
    rules exist to catch. Only comparisons whose own `comparison.sensing_contact` matches are
    pooled.

    Pools the raw (current, settled power) pairs `_raw_pairs_for_band` reads from every matching
    comparison's panel, labels each run's points with the run's own label so
    `within_visit.amplitude_response_shape_pooled` gives each run its own baseline intercept --
    two runs on the same calendar day but a different side or rate are different ladders and must
    not share one intercept, so the grouping key is the run label, not the visit date. Returns the
    same dict shape as `amplitude_response_shape_pooled`, with a "not assessed" verdict and NaN
    fields when no matching comparison has a usable panel for this centre.
    """
    from StimOptimizer.routines import within_visit
    contact = str(sensing_contact)
    xs, ys, vs = [], [], []
    for comp in (build or {}).get("comparisons", []) or []:
        if str(getattr(comp, "sensing_contact", None)) != contact:
            continue
        x, y = _raw_pairs_for_band(comp, band_center_hz)
        if x.size:
            xs.append(x)
            ys.append(y)
            vs.append(np.full(x.size, str(comp.label)))
    if not xs:
        return within_visit.amplitude_response_shape_pooled(
            np.empty(0), np.empty(0), np.empty(0), min_points=min_points)
    return within_visit.amplitude_response_shape_pooled(
        np.concatenate(xs), np.concatenate(ys), np.concatenate(vs), min_points=min_points)


def table_from_build(build, *, checked_lo_hz, checked_hi_hz, band_half_hz,
                     min_points_curvature=MIN_POINTS_CURVATURE):
    """The table for every comparison in what `build_for_participant` returned."""
    rows = []
    for comp in (build or {}).get("comparisons", []) or []:
        rows += rows_for_comparison(comp, checked_lo_hz=checked_lo_hz, checked_hi_hz=checked_hi_hz,
                                    band_half_hz=band_half_hz,
                                    min_points_curvature=min_points_curvature)
    return pd.DataFrame(rows).reset_index(drop=True)


#: The pooled within-visit table: ONE row per (sensing contact, band centre), holding the
#: dose-response direction pooled across every stimulation-current ladder this participant has.
#: A DERIVED kind — it must be written with `writer=` and `provenance=` (CLAUDE.md §10 rule 6).
#:
#: WHY IT IS STORED RATHER THAN COMPUTED ON THE PAGE. `pooled_shape_for_band` needs EVERY run, and
#: `adapter.report_for_participant` builds only the runs the page draws once the amplitude-effect
#: and ground-truth entries exist — which is the steady state. Pooling over that slice defeats
#: decision 55/56, whose whole point is pooling across visits. Measured on RCS08, ONE_THREE_LEFT at
#: 17.5 Hz, same band on the same day: a full build gives 13 points across 4 visits, the page's
#: 4-run slice gives 6 across 1. Storing the table computed from the full build means the answer is
#: the same on every request instead of depending on what happened to be cached.
POOLED_KIND = "within_visit_pooled_shape"
POOLED_RULE_VERSION = "v2_pooled_shape_curve_coefficients"

#: The fields carried per row. `post_peak` is deliberately absent: it is a nested structure rather
#: than a scalar, no consumer reads it, and a table is the wrong shape to carry it in.
POOLED_FIELDS = ("pooled_direction", "pooled_slope_per_mA", "pooled_slope_stderr",
                 "pooled_slope_p", "n", "n_visits", "verdict", "curves", "peaks_inside",
                 "peak_mA", "p_curvature", "r2_linear", "r2_quadratic",
                 # Since v2 (2026-09-11): the quadratic's coefficients and the post-peak line, so
                 # the closed-loop simulation can rebuild the fitted CURVE from the stored row
                 # (redesign decision 21) rather than only read where its peak is.
                 "quad_coef_per_mA2", "quad_lin_coef_per_mA", "quad_coef_stderr",
                 "post_peak_slope_per_mA", "post_peak_intercept", "post_peak_n_points")


def pooled_table_from_build(build, *, checked_lo_hz, checked_hi_hz, band_half_hz,
                            min_points=MIN_POINTS_CURVATURE):
    """One pooled within-visit answer per (sensing contact, band centre) in `build`.

    `build` MUST hold every run the record supports. Passing the page's truncated build produces a
    table that looks complete and answers from a fraction of the visits — the exact failure this
    table exists to prevent — so the caller is responsible for building with `max_runs=_ALL_RUNS`
    and `adapter.write_pooled_shape` refuses to store one built any other way.

    The contacts and centres are taken from `table_from_build`'s own output rather than from a
    separate list, so this table covers exactly the (contact, band) pairs the per-run amplitude
    table already covers and the two cannot disagree about which points exist.
    """
    per_run = table_from_build(build, checked_lo_hz=checked_lo_hz, checked_hi_hz=checked_hi_hz,
                               band_half_hz=band_half_hz)
    if not len(per_run):
        return pd.DataFrame(columns=("sensing_contact", "band_center_hz") + POOLED_FIELDS)

    rows = []
    for contact in sorted(per_run["sensing_contact"].dropna().astype(str).unique()):
        centres = per_run.loc[per_run["sensing_contact"].astype(str) == contact, "band_center_hz"]
        for centre in sorted(float(c) for c in centres.dropna().unique()):
            pooled = pooled_shape_for_band(build, centre, contact, min_points=min_points) or {}
            pp = pooled.get("post_peak") or {}
            pooled = dict(pooled, post_peak_slope_per_mA=pp.get("slope_per_mA", float("nan")),
                          post_peak_intercept=pp.get("intercept", float("nan")),
                          post_peak_n_points=pp.get("n_points", 0))
            row = {"sensing_contact": contact, "band_center_hz": float(centre)}
            row.update({k: pooled.get(k) for k in POOLED_FIELDS})
            rows.append(row)
    return pd.DataFrame(rows).reset_index(drop=True)


def pooled_row(table, sensing_contact, band_center_hz, *, atol=1e-6):
    """The stored pooled row for one point, as the dict `direction_consistency` expects, or None.

    Returns a plain dict rather than a pandas row so the consistency check never has to know the
    table was stored — it takes the same shape whether it came from a live pool or from disk.
    """
    if table is None or not len(table):
        return None
    want = str(sensing_contact)
    target = float(band_center_hz)
    for _i, r in table.iterrows():
        if str(r.get("sensing_contact")) != want:
            continue
        centre = r.get("band_center_hz")
        try:
            if abs(float(centre) - target) <= atol:
                return {k: r.get(k) for k in POOLED_FIELDS}
        except (TypeError, ValueError):
            continue
    return None


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
