"""Track A step 6: the band-by-length sweep's results as two tidy tables, one row per contact pair,
band centre and length of signal.

WHY TWO TABLES AND NOT THE RESPONSE. The sweep answers the page with one nested dictionary per
contact pair: grids of the correlation and of the discrimination value over lengths of signal and
band centres, and one "best" row per band centre with its interval, its selection-aware p-value and
its verdict. That shape draws a heat map well and joins to nothing. The approved plan asks for
"two new tables, per band centre and per contact pair: the correlation results and the
discrimination results", so that Stim Optimizer, or an audit, can read them by column. Every grid
cell becomes a row; the best cell for each centre is flagged and carries the evidence the sweep
attached to it; every other row leaves those columns empty. Nothing is recomputed here: every
number is copied from the sweep, so the table can be checked against the response value for value.

THE NO-RELATIONSHIP REFERENCE IS A COLUMN. An area under the curve is above chance by comparison
with 0.5, never with 0; a correlation by comparison with 0. Each table carries its reference so a
reader of the file alone cannot get that wrong.

Pure pandas and numpy, no Django, so it is testable on either runner.
"""
import numpy as np
import pandas as pd

#: The kinds the two tables are stored under, and the rule version bumped when a column's meaning
#: changes. The columns themselves are part of the table, so a new column does not need a bump.
CORRELATION_KIND = "biomarker_band_correlation"
DISCRIMINATION_KIND = "biomarker_band_discrimination"
RULE_VERSION = "v1_grid_rows"

#: Columns copied from the best row for each centre. Anything not in this list stays with the
#: response (the sentences, the row's own wording), because a table is for numbers.
_BEST_CORRELATION_COLUMNS = (
    "pearson_r_low", "pearson_r_high", "n_resamples_used", "answer",
    "chosen_as_best_of_n_windows", "shuffled_best_of_windows_p95",
    "shuffled_best_of_windows_p99", "p_selection_aware", "beats_shuffled_best_of_windows_p95",
)
_BEST_DISCRIMINATION_COLUMNS = (
    "auc_low", "auc_high", "n_resamples_used", "answer", "interval_spans_no_discrimination",
    "chosen_as_best_of_n_windows", "shuffled_best_of_windows_p95",
    "shuffled_best_of_windows_p99", "p_selection_aware", "beats_shuffled_best_of_windows_p95",
)


def _f(v):
    """A float, with None and non-finite values as NaN, so a column is never object-typed."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return np.nan
    return x if np.isfinite(x) else np.nan


def _grid(sweep, name):
    g = sweep.get(name) or []
    return [list(row) for row in g]


def _best_by_centre(rows):
    """The best row for each band centre, keyed on the centre as the sweep reports it."""
    out = {}
    for r in rows or []:
        c = r.get("band_center_hz", r.get("center_hz"))
        if c is None:
            continue
        out[round(float(c), 6)] = r
    return out


def _rows(sweep, channel, value_grid, value_name, best_rows, best_columns, extra_grids):
    centres = [float(c) for c in (sweep.get("center_freqs_hz") or [])]
    requested = [float(s) for s in (sweep.get("integration_seconds_requested") or [])]
    delivered = list(sweep.get("integration_seconds_delivered") or [])
    tiles = list(sweep.get("integration_tiles") or [])
    inside = list(sweep.get("band_fully_inside_8_to_30_hz") or [])
    n_grid = _grid(sweep, "n_grid")
    width = _f(sweep.get("band_width_hz"))
    best = _best_by_centre(best_rows)
    out = []
    for t, seconds in enumerate(requested):
        if t >= len(value_grid):
            break
        for c, centre in enumerate(centres):
            if c >= len(value_grid[t]):
                break
            b = best.get(round(centre, 6))
            # The same rounding as the centre lookup, so a length printed or rounded upstream
            # cannot silently leave a centre with no best row.
            is_best = bool(b is not None
                           and round(_f(b.get("integration_seconds_requested")), 6)
                           == round(seconds, 6))
            row = {
                "channel": str(channel),
                "brain_side": (b or {}).get("brain_side"),
                "contacts": (b or {}).get("contacts"),
                "band_center_hz": centre,
                "band_low_hz": centre - width / 2.0 if np.isfinite(width) else np.nan,
                "band_high_hz": centre + width / 2.0 if np.isfinite(width) else np.nan,
                "band_width_hz": width,
                "band_fully_inside_8_to_30_hz": bool(inside[c]) if c < len(inside) else None,
                "integration_seconds_requested": seconds,
                "integration_seconds_delivered": _f(delivered[t]) if t < len(delivered) else np.nan,
                "integration_tiles": int(tiles[t]) if t < len(tiles) else -1,
                value_name: _f(value_grid[t][c]),
                "n_pain_reports": (int(n_grid[t][c]) if t < len(n_grid) and c < len(n_grid[t])
                                   else -1),
            }
            for name, g in extra_grids.items():
                row[name] = (_f(g[t][c]) if t < len(g) and c < len(g[t]) else np.nan)
            row["is_best_for_centre"] = is_best
            for col in best_columns:
                v = b.get(col) if is_best else None
                if col in ("answer",):
                    row[col] = (str(v) if v is not None else None)
                elif col in ("beats_shuffled_best_of_windows_p95",
                             "interval_spans_no_discrimination"):
                    row[col] = (bool(v) if v is not None else None)
                elif col in ("n_resamples_used", "chosen_as_best_of_n_windows"):
                    row[col] = (int(v) if v is not None else -1)
                else:
                    row[col] = _f(v)
            out.append(row)
    return out


def _finish(rows, sweeps, extra):
    df = pd.DataFrame(rows)
    for k, v in extra.items():
        df[k] = v
    return df.reset_index(drop=True)


def correlation_table(sweeps_by_channel, *, metric_key=None):
    """One row per contact pair, band centre and length of signal: the correlation between band
    power and the pain score, the number of reports behind it, and on the best row for each centre
    the interval, the selection-aware p-value and the verdict."""
    rows = []
    for channel, sweep in (sweeps_by_channel or {}).items():
        if not sweep or not sweep.get("center_freqs_hz"):
            continue
        rows += _rows(sweep, channel, _grid(sweep, "correlation_grid"), "pearson_r",
                      sweep.get("best_correlation_rows"), _BEST_CORRELATION_COLUMNS, {})
    return _finish(rows, sweeps_by_channel, {
        "no_relationship_value": 0.0,
        "metric_key": (str(metric_key) if metric_key is not None else None),
    })


def discrimination_table(sweeps_by_channel, *, metric_key=None):
    """One row per contact pair, band centre and length of signal: the area under the curve of the
    band power against high-versus-low pain, keeping its direction, the folded value, the counts
    of high and low reports, and on the best row for each centre the interval and the verdict."""
    rows = []
    first = None
    for channel, sweep in (sweeps_by_channel or {}).items():
        if not sweep or not sweep.get("center_freqs_hz"):
            continue
        first = first or sweep
        rows += _rows(sweep, channel, _grid(sweep, "auc_grid"), "auc",
                      sweep.get("best_auc_rows"), _BEST_DISCRIMINATION_COLUMNS,
                      {"auc_direction_folded": _grid(sweep, "auc_direction_folded_grid"),
                       "n_high_pain_reports": _grid(sweep, "auc_n_high_grid"),
                       "n_low_pain_reports": _grid(sweep, "auc_n_low_grid")})
    first = first or {}
    return _finish(rows, sweeps_by_channel, {
        "no_relationship_value": 0.5,
        "metric_key": (str(metric_key) if metric_key is not None else None),
        "pain_split_rule": first.get("pain_split_rule"),
        "pain_low_cut": _f(first.get("pain_low_cut")),
        "pain_high_cut": _f(first.get("pain_high_cut")),
    })


def count_matches(table, sweeps_by_channel, value_name, grid_name):
    """(fields compared, fields differing) between a table's value column and the response grid it
    was copied from. Exact equality, NaN equal to NaN; never a tolerance."""
    compared = differ = 0
    for channel, sweep in (sweeps_by_channel or {}).items():
        grid = _grid(sweep, grid_name)
        centres = [float(c) for c in (sweep.get("center_freqs_hz") or [])]
        requested = [float(s) for s in (sweep.get("integration_seconds_requested") or [])]
        sub = table[table["channel"] == str(channel)]
        for t, s in enumerate(requested):
            for c, centre in enumerate(centres):
                got = sub[(sub["integration_seconds_requested"] == s)
                          & (sub["band_center_hz"] == centre)][value_name]
                if len(got) != 1:
                    differ += 1
                    compared += 1
                    continue
                a, b = _f(grid[t][c]), _f(got.iloc[0])
                compared += 1
                if not ((a == b) or (np.isnan(a) and np.isnan(b))):
                    differ += 1
    return compared, differ
