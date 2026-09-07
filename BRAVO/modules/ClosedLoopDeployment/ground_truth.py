"""The ground-truth verdict for the three-source comparison, written where Stim Optimizer reads it.

THE RULE (decision 33, `METHODS_measurement_and_findings.md` section 6), applied to every band and
stimulation setting of every run of rising current the device's own record holds:

1. the device's own band power is ground truth wherever it exists and passed its ceiling check;
2. the calibrated voltage-trace route where the device's own reading does not exist;
3. the device's own spectrum route below that, tagged composed rather than measured;
4. never the uncalibrated integrated-density route (it is not in the comparison at all).

Every row carries the route chosen, the value on every route that had one, the fold ratio between
the device reading and the voltage-trace value where both exist (the platform's only continuous
check on the calibration serving the other bands), the pieces of recording behind each route, the
device spikes excluded by the ceiling, and whether the band sits inside the checked conversion span.
Nothing here converts a unit or fits anything: it is a choice among numbers the comparison already
made, and every number is copied from the comparison rows and checkable against them.
"""
import numpy as np
import pandas as pd

from . import three_source_response as _3src

KIND = "ground_truth_verdict"
RULE_VERSION = "v2_decision_33_device_band_paired"

ROUTE_DEVICE = "device"
ROUTE_VOLTAGE_TRACE = "voltage_trace_calibrated"
ROUTE_DEVICE_SPECTRUM = "device_spectrum_composed"
ROUTE_NONE = "none"

_SOURCE_TO_ROUTE = {
    _3src.SOURCE_DEVICE_BAND_POWER: ROUTE_DEVICE,
    _3src.SOURCE_TIME_DOMAIN: ROUTE_VOLTAGE_TRACE,
    _3src.SOURCE_DEVICE_SPECTRUM: ROUTE_DEVICE_SPECTRUM,
}

COLUMNS = ("run_label", "visit_date", "ramped_side", "sensing_contact", "stimulation_rate_hz",
           "band_center_hz", "device_band_center_hz", "current_mA", "ground_truth_route",
           "ground_truth_power",
           "ground_truth_is_measured_not_composed", "device_power", "device_n_pieces",
           "device_spikes_excluded", "device_refused_reason", "voltage_trace_power",
           "voltage_trace_n_pieces", "voltage_trace_refused_reason", "device_spectrum_power",
           "device_spectrum_n_pieces", "device_spectrum_refused_reason",
           "fold_device_over_voltage_trace", "band_inside_checked_conversion_range",
           "band_is_measuring_the_stimulator", "why_no_ground_truth")


def _key(r):
    return (r["run"], float(r["band_centre_hz"]), float(r["current_mA"]))


def verdict_rows(rows, device_band_alias=None):
    """Apply the rule to the flat comparison rows of one or more runs.

    `rows` is what `three_source_response.comparison_rows` returns. Rows with no stimulation
    setting (a route absent for the whole run) contribute their reason and nothing else.

    `device_band_alias` maps `(run, programmed centre)` to the stored centre the comparison
    made at: the device senses one band at its programmed centre (7.81 Hz, say) and the two
    converted routes hold bands on the stored grid (8.5 Hz), and the comparison itself pairs the
    device's band with the single nearest stored centre. The verdict pairs them the same way, and
    the row keeps the device's own centre in `device_band_center_hz` so nothing is hidden.
    """
    alias = device_band_alias or {}
    by_cell = {}
    absent = {}
    for r in rows:
        route = _SOURCE_TO_ROUTE.get(r.get("source"))
        if route is None:
            continue
        if r.get("current_mA") is None or r.get("band_centre_hz") is None:
            absent.setdefault((r["run"], route),
                              r.get("route_absent_reason") or r.get("why_not_used") or "")
            continue
        k = _key(r)
        if route == ROUTE_DEVICE:
            k = (k[0], float(alias.get((k[0], k[1]), k[1])), k[2])
        cell = by_cell.setdefault(k, {"meta": r, "routes": {}})
        cell["routes"][route] = r
    out = []
    for (run, centre, current), cell in sorted(by_cell.items()):
        m = cell["meta"]
        routes = cell["routes"]

        def val(route):
            r = routes.get(route)
            if r is None:
                return None, 0, absent.get((run, route), "this route had no row for this setting")
            v = r.get("settled_band_power_device_units")
            v = float(v) if v is not None and np.isfinite(float(v)) else None
            return v, int(r.get("n_pieces_averaged") or 0), (r.get("why_not_used") or "")

        dev_v, dev_n, dev_why = val(ROUTE_DEVICE)
        td_v, td_n, td_why = val(ROUTE_VOLTAGE_TRACE)
        sp_v, sp_n, sp_why = val(ROUTE_DEVICE_SPECTRUM)
        spikes = int((routes.get(ROUTE_DEVICE) or {}).get("n_spikes_excluded") or 0)
        if dev_v is not None:
            route, power, measured, why = ROUTE_DEVICE, dev_v, True, ""
        elif td_v is not None:
            route, power, measured, why = ROUTE_VOLTAGE_TRACE, td_v, True, ""
        elif sp_v is not None:
            route, power, measured, why = ROUTE_DEVICE_SPECTRUM, sp_v, False, ""
        else:
            route, power, measured = ROUTE_NONE, None, None
            why = "; ".join(x for x in (f"device: {dev_why}" if dev_why else "",
                                        f"voltage trace: {td_why}" if td_why else "",
                                        f"device spectrum: {sp_why}" if sp_why else "") if x)
        fold = (dev_v / td_v) if (dev_v is not None and td_v is not None and td_v > 0) else None
        checked = None
        for rr in routes.values():
            if rr.get("band_inside_checked_conversion_range") is not None:
                checked = bool(rr["band_inside_checked_conversion_range"])
                break
        stim = m.get("band_is_measuring_the_stimulator")
        dev_row = routes.get(ROUTE_DEVICE)
        out.append({
            "run_label": run, "visit_date": m.get("visit_date"), "ramped_side": m.get("ramped_side"),
            "sensing_contact": m.get("sensing_contact"),
            "stimulation_rate_hz": m.get("stimulation_rate_hz"),
            "band_center_hz": float(centre),
            "device_band_center_hz": (float(dev_row["band_centre_hz"]) if dev_row is not None
                                      and dev_row.get("band_centre_hz") is not None else None),
            "current_mA": float(current),
            "ground_truth_route": route, "ground_truth_power": power,
            "ground_truth_is_measured_not_composed": measured,
            "device_power": dev_v, "device_n_pieces": dev_n, "device_spikes_excluded": spikes,
            "device_refused_reason": dev_why if dev_v is None else "",
            "voltage_trace_power": td_v, "voltage_trace_n_pieces": td_n,
            "voltage_trace_refused_reason": td_why if td_v is None else "",
            "device_spectrum_power": sp_v, "device_spectrum_n_pieces": sp_n,
            "device_spectrum_refused_reason": sp_why if sp_v is None else "",
            "fold_device_over_voltage_trace": fold,
            "band_inside_checked_conversion_range": checked,
            "band_is_measuring_the_stimulator": bool(stim) if stim is not None else None,
            "why_no_ground_truth": why,
        })
    return out


def table_from_build(build):
    """One tidy table over every run in a `build_for_participant` result."""
    comps = (build or {}).get("comparisons") or []
    rows = []
    for c in comps:
        rows.extend(verdict_rows(_3src.comparison_rows(c), device_band_alias=device_band_alias(c)))
    return pd.DataFrame(rows, columns=list(COLUMNS))


def device_band_alias(comparison):
    """`{(run, programmed centre): comparison centre}` for one comparison, from its own panels:
    the converted routes' band centre is the single nearest stored centre to what the device
    sensed, and that is where the device's own band is compared."""
    prog = getattr(comparison, "programmed_centre_hz", None)
    if prog is None:
        return {}
    for panel in getattr(comparison, "panels", ()):
        if panel.source != _3src.SOURCE_DEVICE_BAND_POWER and panel.band_centre_hz is not None:
            return {(comparison.label, float(prog)): float(panel.band_centre_hz)}
    return {}


def count_matches(table, rows):
    """How many verdict values equal the comparison row they were copied from, and how many not.

    Checks every `ground_truth_power` against the settled value of its chosen route in `rows`.
    Returns (n_compared, n_differences).
    """
    lookup = {}
    for r in rows:
        route = _SOURCE_TO_ROUTE.get(r.get("source"))
        if route is None or r.get("current_mA") is None or r.get("band_centre_hz") is None:
            continue
        lookup[(r["run"], float(r["band_centre_hz"]), float(r["current_mA"]), route)] = \
            r.get("settled_band_power_device_units")
    n = d = 0
    for _, t in table.iterrows():
        if t["ground_truth_route"] == ROUTE_NONE:
            continue
        n += 1
        centre = (t["device_band_center_hz"] if t["ground_truth_route"] == ROUTE_DEVICE
                  and t["device_band_center_hz"] is not None
                  and not (isinstance(t["device_band_center_hz"], float) and np.isnan(t["device_band_center_hz"]))
                  else t["band_center_hz"])
        src = lookup.get((t["run_label"], float(centre), float(t["current_mA"]),
                          t["ground_truth_route"]))
        if src is None or float(src) != float(t["ground_truth_power"]):
            d += 1
    return n, d
