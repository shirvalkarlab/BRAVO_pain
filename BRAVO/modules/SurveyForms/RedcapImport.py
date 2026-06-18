""""""
"""
=========================================================
* UF BRAVO Platform  (Pain fork)
=========================================================

* Copyright 2025 by Jackson Cagle, Fixel Institute
* The source code is made available under Open Source GPL-3.0 License

 =========================================================

* The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
"""
"""
Offline REDCap CSV / DataFrame ingest for the SurveyForms module.
===================================================================

PURPOSE
-------
The stock SurveyForms module can only obtain REDCap records by pulling them LIVE from the
REDCap API on every request (`RedcapForm.queryRedcapFormRecords`), which requires a project API
token to be stored on the server for each form. This module adds an OFFLINE path: take a tidy
REDCap export (the CSV produced by the current BRAVO biomarker pipeline,
`redcap_client.process_redcap(pull_redcap(), field_map)` -> `_pro_dump/<pt>_chronic_pro_df.csv`,
or any tidy export) -- or a pandas DataFrame passed directly -- and turn it into the SAME native
data shapes the platform already renders and analyses:

    * a `ScaleForms.record` FieldMapping (one typed "score" question per metric + a "Time" marker)
    * one `ScaleRecord.record` Result matrix (pages x questions) per report, with the report
      timestamp as the record date.

The persistence (creating the Django `ScaleForms` / `ScaleRecord` / `ParticipantLinkRel` rows) is
done in `bravo_service`; THIS file is deliberately pure pandas/stdlib (no Django, no network) so it
is unit-testable and reusable from library mode.

DATA SHAPES PRODUCED (must match what the frontend expects)
-----------------------------------------------------------
`RecordScoreTimeline.js` reads, for each plotted question of type "score"/"redcapForm":

    dataToRender[j].Date                                 # epoch seconds
    dataToRender[j].Result[question.page][question.index]  # the numeric value

and builds its score selector from `form` = the FieldMapping list of pages, each page
`{header, questions:[{text, type, activeView, ...}]}`. We therefore emit a single page whose
questions are the metrics (plus a hidden "Time" marker that mirrors the Redcap-linked convention),
and per-record a Result matrix indexed `Result[0][questionIndex]`.

WIDE vs LONG
------------
* WIDE  (primary): the pipeline's `chronic_pro_df` -- one row per report, one column per metric,
  plus a timestamp column (`date_time_s1_daily`). Each metric column -> one instrument's questions;
  the whole wide table is treated as ONE instrument (the daily PRO survey).
* LONG  (general): a tidy-long export with an instrument column, a metric/column name, a numeric
  value, and a timestamp. Grouped by instrument; each instrument pivoted to wide and ingested the
  same way. Supports multi-instrument exports in a single file.
"""

import math
import datetime

import pandas as pd
import numpy as np


# Canonical metric -> (display label, [y-min, y-max]) for the daily-PRO columns the BRAVO pipeline
# emits. Mirrors dbs_stage2_percept / redcap_pull.py and bravo_service's pain-score axis ranges.
# Unknown columns fall back to a 0..100 score range with a title-cased label.
CANONICAL_METRICS = {
    "nrs":           ("NRS (0-10)", [0, 10]),
    "vas":           ("VAS Pain Intensity (0-100)", [0, 100]),
    "left_leg_vas":  ("Left Leg VAS (0-100)", [0, 100]),
    "back_vas":      ("Back VAS (0-100)", [0, 100]),
    "relief":        ("Pain Relief VAS (0-100)", [0, 100]),
    "mpq_sum":       ("MPQ Sum", [0, 45]),
    "mpq_sen":       ("MPQ Sensory", [0, 33]),
    "mpq_aff":       ("MPQ Affective", [0, 12]),
    "electrocuting": ("Electrocuting (0-10)", [0, 10]),
    "tingly":        ("Tingly (0-10)", [0, 10]),
}

# Timestamp column names we recognise, in priority order. `date_time_s1_daily` is the canonical
# tidy timestamp emitted by `redcap_client.process_redcap`.
TIMESTAMP_CANDIDATES = ("date_time_s1_daily", "timestamp", "datetime", "date_time", "date")

# Metrics shown by default on the record timeline (activeView=True) when present.
DEFAULT_ACTIVE = ("nrs", "vas", "mpq_sum")

# The marker form record_type this ingest produces (distinct from "Normal Survey" and
# "Redcap Linked Survey"; recognised by bravo_service / DataAnalysis).
RECORD_TYPE = "Redcap CSV Import"


# --------------------------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------------------------- #

def _to_epoch(value):
    """Parse a timestamp (str / pandas Timestamp / epoch number) to epoch SECONDS (float), or None."""
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(value, float) and math.isnan(value):
            return None
        # Heuristic: treat very large numbers as ms, otherwise seconds.
        return float(value) / 1000.0 if value > 1e11 else float(value)
    try:
        ts = pd.to_datetime(value)
    except (ValueError, TypeError):
        return None
    if pd.isna(ts):
        return None
    return ts.timestamp()


def _metric_label(col):
    if col in CANONICAL_METRICS:
        return CANONICAL_METRICS[col][0]
    return str(col).replace("_", " ").strip().title()


def _metric_range(col, series=None):
    if col in CANONICAL_METRICS:
        return list(CANONICAL_METRICS[col][1])
    # Infer a sane range from the data for unknown columns.
    if series is not None:
        vals = pd.to_numeric(series, errors="coerce").dropna()
        if len(vals):
            lo = min(0, float(np.floor(vals.min())))
            hi = float(np.ceil(vals.max()))
            return [lo, hi if hi > lo else lo + 1]
    return [0, 100]


def _clean_value(v):
    """JSON-safe numeric value: float for finite numbers, None for NaN/missing."""
    if v is None:
        return None
    try:
        f = float(v)
    except (ValueError, TypeError):
        # Non-numeric categorical answer -> keep the string as-is.
        s = str(v).strip()
        return s if s else None
    return None if math.isnan(f) else f


# --------------------------------------------------------------------------------------------- #
# core parse
# --------------------------------------------------------------------------------------------- #

def build_instrument(df, instrument_name, metric_cols, timestamp_col, display_labels=None):
    """Turn a WIDE per-report table into (FieldMapping, records) for one instrument.

    Parameters
    ----------
    df : DataFrame
        One row per report. Must contain `timestamp_col` and the `metric_cols`.
    instrument_name : str
        Human label for the instrument / form (e.g. "Daily PRO Survey (RCS08)").
    metric_cols : list[str]
        Columns to expose as score questions, in display order.
    timestamp_col : str
        Column holding the report timestamp.
    display_labels : dict | None
        Optional {col: label} overrides.

    Returns
    -------
    dict with:
        FieldMapping : list[page]  -- a single page; questions = one per metric + a hidden "Time".
        records      : list[{Name, Date, Result}]  -- one per report, Result = [[v0, v1, ...]].
        skipped      : int  -- rows dropped for an unparseable / missing timestamp.
        metrics      : list[str]  -- the metric cols actually emitted (order matches Result).
    """
    display_labels = display_labels or {}

    # Build the page's questions: one "score" per metric, then a trailing hidden "Time" marker
    # (mirrors the Redcap-linked FieldMapping convention; not plotted, but keeps the shape uniform
    # and lets the customized-analysis path find the timestamp column if needed).
    questions = []
    for col in metric_cols:
        rng = _metric_range(col, df[col] if col in df.columns else None)
        # The range is only a display/axis hint; never let a canonical hint understate the actual
        # data (e.g. MPQ-SF sums can exceed the nominal 45). Values are stored verbatim regardless.
        if col in df.columns:
            obs = pd.to_numeric(df[col], errors="coerce").dropna()
            if len(obs):
                rng = [min(rng[0], float(np.floor(obs.min()))), max(rng[1], float(np.ceil(obs.max())))]
        questions.append({
            "variableName": str(col),
            "text": display_labels.get(col, _metric_label(col)),
            "type": "score",
            "min": rng[0],
            "max": rng[1],
            "step": 1,
            "value": 0,
            "default": 0,
            "activeView": col in DEFAULT_ACTIVE,
            "show": True,
        })
    time_index = len(questions)
    questions.append({
        "variableName": str(timestamp_col),
        "text": "Time",
        "type": "redcapForm",
        "value": str(timestamp_col),
        "default": "",
        "validation": "variable",
        "activeView": False,
        "show": False,
    })

    field_mapping = [{"header": instrument_name, "questions": questions}]

    records = []
    skipped = 0
    for _, row in df.iterrows():
        epoch = _to_epoch(row.get(timestamp_col))
        if epoch is None:
            skipped += 1
            continue
        page_result = [_clean_value(row.get(col)) for col in metric_cols]
        # Time question slot carries the ISO timestamp string (matches Redcap-linked Result shape).
        try:
            iso = pd.to_datetime(row.get(timestamp_col)).isoformat()
        except (ValueError, TypeError):
            iso = None
        page_result.append(iso)
        records.append({
            "Name": instrument_name,
            "Date": epoch,
            "Result": [page_result],
        })

    records.sort(key=lambda r: r["Date"])
    return {
        "FieldMapping": field_mapping,
        "records": records,
        "skipped": skipped,
        "metrics": list(metric_cols),
        "time_index": time_index,
    }


def parse_wide(df, instrument_name, timestamp_col=None, metric_cols=None, display_labels=None):
    """Parse a WIDE export (the pipeline's chronic_pro_df) as a SINGLE instrument.

    Auto-detects the timestamp column (TIMESTAMP_CANDIDATES) and the metric columns (every other
    column that is numeric, or a known canonical metric) when not given explicitly.
    """
    df = df.copy()
    # drop a stray pandas index column if present
    if df.columns.size and str(df.columns[0]).lower() in ("unnamed: 0", "index"):
        df = df.drop(columns=[df.columns[0]])

    if timestamp_col is None:
        for cand in TIMESTAMP_CANDIDATES:
            if cand in df.columns:
                timestamp_col = cand
                break
    if timestamp_col is None:
        raise ValueError(
            "Could not find a timestamp column. Expected one of "
            f"{TIMESTAMP_CANDIDATES} or pass timestamp_col explicitly."
        )

    if metric_cols is None:
        metric_cols = []
        for col in df.columns:
            if col == timestamp_col:
                continue
            if col in CANONICAL_METRICS:
                metric_cols.append(col)
                continue
            # include numeric columns; coerce check
            coerced = pd.to_numeric(df[col], errors="coerce")
            if coerced.notna().any():
                metric_cols.append(col)
    if not metric_cols:
        raise ValueError("No metric columns found to import.")

    return [build_instrument(df, instrument_name, metric_cols, timestamp_col,
                             display_labels=display_labels)]


def parse_long(df, instrument_col, metric_col, value_col, timestamp_col,
               instance_col=None, name_prefix=""):
    """Parse a tidy-LONG export into one instrument per `instrument_col` value.

    Each (instrument, report-instance/timestamp) group is pivoted to a wide row keyed by
    `metric_col`, then ingested via `build_instrument`. `instance_col` (if given) disambiguates
    repeats sharing a timestamp; otherwise the timestamp itself groups a report.
    """
    df = df.copy()
    out = []
    for inst, g in df.groupby(instrument_col):
        key_cols = [timestamp_col] + ([instance_col] if instance_col else [])
        # pivot: index = report key, columns = metric, value = value
        g2 = g.dropna(subset=[timestamp_col])
        if g2.empty:
            continue
        wide = (g2.pivot_table(index=key_cols, columns=metric_col, values=value_col,
                               aggfunc="first")
                  .reset_index())
        # restore a clean timestamp column name
        metric_cols = [c for c in wide.columns if c not in key_cols]
        name = (name_prefix + str(inst)).strip()
        parsed = parse_wide(wide, name, timestamp_col=timestamp_col, metric_cols=metric_cols)
        out.extend(parsed)
    return out


def parse_export(source, instrument_name=None, layout="auto", **kwargs):
    """Top-level entry: read a CSV path / DataFrame and return a list of parsed instruments.

    Parameters
    ----------
    source : str | pandas.DataFrame
        A path to a tidy REDCap CSV, or a DataFrame already in memory (e.g. the pipeline's
        chronic_pro_df passed directly).
    instrument_name : str | None
        Name for the (wide) instrument. Defaults to "Imported REDCap Survey".
    layout : {"auto", "wide", "long"}
        "auto" picks long when the standard long columns are present, else wide.
    **kwargs : passed to parse_wide / parse_long (timestamp_col, metric_cols, instrument_col, ...).

    Returns
    -------
    list[dict]  -- each dict as produced by build_instrument.
    """
    if isinstance(source, str):
        df = pd.read_csv(source, low_memory=False)
    elif isinstance(source, pd.DataFrame):
        df = source.copy()
    else:
        raise TypeError("source must be a CSV path or a pandas DataFrame.")

    if layout == "auto":
        long_cols = {"instrument_canonical", "value_num", "timestamp"}
        layout = "long" if long_cols.issubset(set(df.columns)) else "wide"

    if layout == "long":
        return parse_long(
            df,
            instrument_col=kwargs.get("instrument_col", "instrument_canonical"),
            metric_col=kwargs.get("metric_col", "column"),
            value_col=kwargs.get("value_col", "value_num"),
            timestamp_col=kwargs.get("timestamp_col", "timestamp"),
            instance_col=kwargs.get("instance_col"),
            name_prefix=kwargs.get("name_prefix", ""),
        )

    return parse_wide(
        df,
        instrument_name or "Imported REDCap Survey",
        timestamp_col=kwargs.get("timestamp_col"),
        metric_cols=kwargs.get("metric_cols"),
        display_labels=kwargs.get("display_labels"),
    )
