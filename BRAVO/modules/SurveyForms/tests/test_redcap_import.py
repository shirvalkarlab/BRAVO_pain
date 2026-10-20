"""Pure-pandas REDCap parser tests using independent synthetic tables.

Run through scripts/run_portable_tests.py or a deliberately isolated test environment.
No private deployment export is read by this public test module.
"""
import os

import numpy as np
import pandas as pd
import pytest

from modules.SurveyForms import RedcapImport as R


# --------------------------------------------------------------------------------------------- #
# synthetic wide
# --------------------------------------------------------------------------------------------- #

def _wide_df():
    return pd.DataFrame({
        "nrs":        [5, 7, np.nan],
        "vas":        [50, 70, 60],
        "mpq_sum":    [10, np.nan, 12],
        "date_time_s1_daily": ["2025-07-20 10:00:00", "2025-07-21 11:30:00", "2025-07-22 09:15:00"],
    })


def test_wide_basic_shapes():
    parsed = R.parse_export(_wide_df(), instrument_name="Daily")[0]
    assert parsed["metrics"] == ["nrs", "vas", "mpq_sum"]
    assert len(parsed["records"]) == 3
    # 3 score questions + the Time marker
    qs = parsed["FieldMapping"][0]["questions"]
    assert len(qs) == 4
    assert qs[-1]["text"] == "Time"
    assert [q["type"] for q in qs[:3]] == ["score", "score", "score"]


def test_wide_nan_becomes_none():
    parsed = R.parse_export(_wide_df(), instrument_name="Daily")[0]
    # records are date-sorted; the nrs NaN row (2025-07-22) is last.
    last = parsed["records"][-1]
    assert last["Result"][0][0] is None  # nrs NaN -> None
    assert last["Result"][0][1] == 60.0  # vas present


def test_wide_records_sorted_by_date():
    parsed = R.parse_export(_wide_df(), instrument_name="Daily")[0]
    dates = [r["Date"] for r in parsed["records"]]
    assert dates == sorted(dates)


def test_canonical_ranges_and_labels():
    parsed = R.parse_export(_wide_df(), instrument_name="Daily")[0]
    qs = {q["variableName"]: q for q in parsed["FieldMapping"][0]["questions"]}
    assert qs["nrs"]["text"] == "NRS (0-10)"
    assert qs["nrs"]["min"] == 0 and qs["nrs"]["max"] == 10
    assert qs["nrs"]["activeView"] is True   # nrs is a DEFAULT_ACTIVE metric
    assert qs["mpq_sum"]["max"] == 45


def test_unknown_metric_inferred_range():
    df = pd.DataFrame({
        "custom_metric": [1, 9, 4],
        "timestamp": ["2025-01-01", "2025-01-02", "2025-01-03"],
    })
    parsed = R.parse_export(df, instrument_name="X")[0]
    q = parsed["FieldMapping"][0]["questions"][0]
    assert q["text"] == "Custom Metric"
    assert q["min"] == 0 and q["max"] == 9


def test_missing_timestamp_raises():
    df = pd.DataFrame({"nrs": [1, 2], "vas": [3, 4]})
    with pytest.raises(ValueError):
        R.parse_export(df, instrument_name="X")


def test_unparseable_timestamp_row_skipped():
    df = pd.DataFrame({
        "nrs": [1, 2, 3],
        "date_time_s1_daily": ["2025-07-20 10:00:00", "not-a-date", "2025-07-22 09:15:00"],
    })
    parsed = R.parse_export(df, instrument_name="X")[0]
    assert len(parsed["records"]) == 2
    assert parsed["skipped"] == 1


# --------------------------------------------------------------------------------------------- #
# synthetic long
# --------------------------------------------------------------------------------------------- #

def test_long_layout_splits_instruments():
    df = pd.DataFrame({
        "instrument_canonical": ["nrs_daily", "nrs_daily", "mpq", "mpq"],
        "column":              ["nrs", "nrs", "mpq_sum", "mpq_sum"],
        "value_num":           [5, 6, 10, 12],
        "timestamp":           ["2025-07-20", "2025-07-21", "2025-07-20", "2025-07-21"],
    })
    parsed = R.parse_export(df)  # auto -> long
    names = sorted(p["FieldMapping"][0]["header"] for p in parsed)
    assert names == ["mpq", "nrs_daily"]
    for p in parsed:
        assert len(p["records"]) == 2



def test_range_never_understates_data():
    # Canonical mpq_sum hint is [0,45] but MPQ-SF sums can exceed it; the saved range must cover
    # the observed max so the axis hint never contradicts the stored value.
    df = pd.DataFrame({
        "mpq_sum": [10, 48, 30],
        "date_time_s1_daily": ["2025-07-20", "2025-07-21", "2025-07-22"],
    })
    parsed = R.parse_export(df, instrument_name="X")[0]
    q = parsed["FieldMapping"][0]["questions"][0]
    assert q["max"] >= 48
    # value preserved verbatim
    assert any(r["Result"][0][0] == 48.0 for r in parsed["records"])
