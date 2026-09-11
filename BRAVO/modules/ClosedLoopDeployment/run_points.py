"""The stored per-run points behind the three-source comparison, and the pooled-by-side view the
Closed-Loop page draws from them (redesign plan decisions 5 and 10, 2026-09-11).

WHY A STORED TABLE. The page's three-source panel used to draw one tab per run, and the build behind
it is truncated to the newest four runs once the write-back entries exist (adapter.py,
`THREE_SOURCE_RUNS_ON_PAGE`). The PI wants two tabs -- right stimulator turned up, left stimulator
turned up -- each pooling EVERY visit. Rebuilding every run on each page load measured 3.7 s with
the tile cache warm; he chose instead to store each run's points once, beside the pooled table of
decision 103, and read them back (his words: "keep option b").

WHAT IS STORED. `three_source_response.comparison_rows` already flattens a run into one row per
route, band and stimulation setting -- the compared band's settled values, the reasons a setting
was refused, and every other band of the routes that cover the whole range. This module writes
exactly that, for every run, plus the run's programmed centre and its start time, as one long
table (kind `three_source_run_points`). Nothing is computed here that the comparison did not
already compute; the table is a copy a page can group, never a second implementation.

A TABLE FROM A TRUNCATED BUILD IS REFUSED, in `adapter.write_run_points`, for the reason decision
103 gives: a stored partial answer looks complete and everything downstream trusts it.

THE VIEW. `pooled_view_payload` groups the stored rows by the side that was turned up, then by the
sensing contact on that side (never across contacts -- decision 74: two electrodes have no reason
to share one dose-response), then by run, and attaches the stored pooled row per band centre so
the page can draw the pooled straight-line slope (decision 9 of the plan) without pooling anything
itself. It gates nothing and says so.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

KIND = "three_source_run_points"
RULE_VERSION = "v2_run_points_window_end"

# The three routes, by the names the comparison uses (three_source_response.SOURCE_*). Spelled here
# rather than imported so a reader of a stored table can match them without the module.
ROUTE_TIME_DOMAIN = "time domain voltage trace"
ROUTE_DEVICE_SPECTRUM = "device's own spectrum"
ROUTE_DEVICE_BAND_POWER = "device's own band power"
ROUTE_KEYS = {ROUTE_TIME_DOMAIN: "time_domain", ROUTE_DEVICE_SPECTRUM: "psd",
              ROUTE_DEVICE_BAND_POWER: "direct"}

#: Fields copied from the stored pooled table (amplitude_effect.POOLED_FIELDS) into the view, with
#: `verdict` carried as `curvature_note` so the word never appears in a payload that gates nothing.
POOLED_VIEW_FIELDS = ("pooled_direction", "pooled_slope_per_mA", "pooled_slope_stderr",
                      "pooled_slope_p", "n", "n_visits", "curves", "peaks_inside", "peak_mA",
                      "p_curvature", "r2_linear", "r2_quadratic",
                      "quad_coef_per_mA2", "quad_lin_coef_per_mA", "quad_coef_stderr",
                      "post_peak_slope_per_mA", "post_peak_intercept", "post_peak_n_points")


def _f(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if np.isfinite(x) else None


def run_points_table_from_build(build) -> pd.DataFrame:
    """One long table of every route, band and setting of every run in `build`.

    `build` MUST hold every run the record supports; `adapter.write_run_points` refuses to store
    one built any other way. The rows are `comparison_rows`' own, with the run's programmed centre
    and start time added so a reader can group them without the comparison objects.
    """
    from . import three_source_response as TSR
    rows: List[Dict[str, Any]] = []
    for comp in (build or {}).get("comparisons", []) or []:
        extra = {"programmed_centre_hz": _f(getattr(comp, "programmed_centre_hz", None)),
                 "window_start_local": str(getattr(comp, "window_start_local", "") or ""),
                 # since v2: the run's end too, so the simulation's settling-time measurement can
                 # read every run's window from this table whatever the page's own build held
                 "window_end_local": str(getattr(comp, "window_end_local", "") or "")}
        for r in TSR.comparison_rows(comp):
            rows.append({**r, **extra})
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    # Parquet needs one type per column; the reasons and labels are strings, the rest numeric or
    # boolean, and a None in a numeric column becomes NaN on the way through.
    for c in ("why_not_used", "route_absent_reason", "run", "visit_date", "ramped_side",
              "sensing_contact", "source", "window_start_local", "window_end_local"):
        if c in df:
            df[c] = df[c].astype(str)
    return df.reset_index(drop=True)


def _route_block(g: pd.DataFrame) -> Dict[str, Any]:
    """One route's points for one run: the settings that produced a value, and every band the
    route covers, as a currents-by-centres matrix (None where a band has no value)."""
    used = g[g["settled_band_power_device_units"].notna()]
    absent = ""
    if "route_absent_reason" in g and len(g):
        absent = str(g["route_absent_reason"].iloc[0] or "")
    if used.empty:
        return {"currents_mA": [], "centres_hz": [], "power": [], "n_pieces": [],
                "absent_reason": absent or "no settled value from this recording"}
    currents = sorted(set(float(v) for v in used["current_mA"]))
    centres = sorted(set(float(v) for v in used["band_centre_hz"]))
    ci = {c: i for i, c in enumerate(currents)}
    fi = {f: j for j, f in enumerate(centres)}
    P = [[None] * len(centres) for _ in currents]
    pieces = [None] * len(currents)
    for _, r in used.iterrows():
        i, j = ci[float(r["current_mA"])], fi[float(r["band_centre_hz"])]
        P[i][j] = _f(r["settled_band_power_device_units"])
        if pieces[i] is None:
            pieces[i] = int(r.get("n_pieces_averaged") or 0)
    striped = []
    if "band_is_measuring_the_stimulator" in used:
        for f in centres:
            flags = used.loc[np.isclose(used["band_centre_hz"].astype(float), f),
                             "band_is_measuring_the_stimulator"]
            striped.append(bool(flags.fillna(False).astype(bool).any()))
    return {"currents_mA": currents, "centres_hz": centres, "power": P, "n_pieces": pieces,
            "striped": striped, "absent_reason": absent}


def _pooled_rows_for_contact(pooled: Optional[pd.DataFrame], contact: str) -> List[Dict[str, Any]]:
    if pooled is None or not len(pooled) or "sensing_contact" not in pooled:
        return []
    sub = pooled[pooled["sensing_contact"].astype(str) == str(contact)]
    out = []
    for _, r in sub.sort_values("band_center_hz").iterrows():
        row = {"band_centre_hz": _f(r.get("band_center_hz"))}
        for k in POOLED_VIEW_FIELDS:
            v = r.get(k)
            if isinstance(v, (bool, np.bool_)):
                row[k] = bool(v)
            elif isinstance(v, str):
                row[k] = v
            else:
                row[k] = _f(v)
        row["curvature_note"] = str(r.get("verdict", "") or "")
        out.append(row)
    return out


def pooled_line_anchor(points_x: List[float], points_y: List[float],
                       run_labels: List[str]) -> Optional[Dict[str, float]]:
    """Where the pooled straight line is drawn through, for one contact at one band centre.

    The pooled model (decision 55, `within_visit.amplitude_response_shape_pooled`) fits settled
    band power in the device's own LINEAR units on current, one baseline per run and ONE shared
    slope (`pooled_slope_per_mA`, device units per mA), so it has no single intercept to draw. The
    page passes that slope through the point returned here.

    THE CHOICE (redesign decision 12, 2026-09-11): the mean of the per-run centroids -- every run
    counts once, whatever its number of settings, which is the pooled model's own grouping. The
    centroid of all points would let a six-setting visit outweigh a two-setting one; the newest
    run's centroid would move the line every time a run lands.
    """
    if not points_x:
        return None
    x = np.asarray(points_x, dtype=float)
    y = np.asarray(points_y, dtype=float)
    labels = np.asarray([str(r) for r in run_labels])
    runs = sorted(set(labels.tolist()))
    cx = [float(np.mean(x[labels == r])) for r in runs]
    cy = [float(np.mean(y[labels == r])) for r in runs]
    return {"x": float(np.mean(cx)), "y": float(np.mean(cy)), "n_runs": len(runs)}


def _anchors_by_centre(cd: pd.DataFrame) -> Dict[float, Optional[Dict[str, float]]]:
    """For one contact: the anchor per band centre from the time-domain route's settled points."""
    td = cd[(cd["source"].astype(str) == ROUTE_TIME_DOMAIN)
            & cd["settled_band_power_device_units"].notna()
            & (cd["settled_band_power_device_units"].astype(float) > 0)]
    out: Dict[float, Optional[Dict[str, float]]] = {}
    for centre, g in td.groupby("band_centre_hz"):
        out[float(centre)] = pooled_line_anchor(
            g["current_mA"].astype(float).tolist(),
            g["settled_band_power_device_units"].astype(float).tolist(),
            g["run"].astype(str).tolist())
    return out


def pooled_view_payload(points: Optional[pd.DataFrame], pooled: Optional[pd.DataFrame],
                        *, absent_reason: Optional[str] = None) -> Dict[str, Any]:
    """The two-tab view: side -> sensing contact -> runs, with the pooled row per band centre."""
    out: Dict[str, Any] = {"gates_nothing": True, "sides": []}
    if points is None or not len(points):
        out["absent_reason"] = absent_reason or (
            "no stored per-run points yet; they are written the next time the comparison is built "
            "from every run")
        return out
    out["from"] = "stored per-run points, every run of rising current on one side"
    df = points.copy()
    for side in ("Right", "Left"):
        sd = df[df["ramped_side"].astype(str).str.lower() == side.lower()]
        if sd.empty:
            continue
        contacts = []
        for contact, cd in sd.groupby("sensing_contact", sort=True):
            runs = []
            for run_label, rd in cd.groupby("run", sort=False):
                first = rd.iloc[0]
                routes = {}
                for source, key in ROUTE_KEYS.items():
                    g = rd[rd["source"].astype(str) == source]
                    routes[key] = _route_block(g) if len(g) else {
                        "currents_mA": [], "centres_hz": [], "power": [], "n_pieces": [],
                        "absent_reason": "this route has no rows for this run"}
                runs.append({
                    "run": str(run_label),
                    "visit_date": str(first.get("visit_date", "")),
                    "window_start_local": str(first.get("window_start_local", "")),
                    "stimulation_rate_hz": _f(first.get("stimulation_rate_hz")),
                    "programmed_centre_hz": _f(first.get("programmed_centre_hz")),
                    "routes": routes,
                })
            runs.sort(key=lambda r: r["window_start_local"], reverse=True)
            rates = sorted(set(r["stimulation_rate_hz"] for r in runs
                               if r["stimulation_rate_hz"] is not None))
            pooled_rows = _pooled_rows_for_contact(pooled, str(contact))
            anchors = _anchors_by_centre(cd)
            for row in pooled_rows:
                c = row.get("band_centre_hz")
                row["anchor"] = (anchors.get(float(c)) if c is not None else None)
            contacts.append({
                "sensing_contact": str(contact),
                "n_runs": len(runs),
                "n_visits": len(set(r["visit_date"] for r in runs)),
                "stimulation_rates_hz": rates,
                "runs": runs,
                "pooled_by_centre": pooled_rows,
            })
        contacts.sort(key=lambda c: (-c["n_runs"], c["sensing_contact"]))
        out["sides"].append({"ramped_side": side, "contacts": contacts})
    out["n_runs"] = int(df["run"].nunique())
    out["n_rows"] = int(len(df))
    return out
