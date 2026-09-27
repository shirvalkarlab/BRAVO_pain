"""The clinic-sheet ratings reach the all-band scan too (the PI, 2026-09-27: "if clinic readings
were activated by clicking the buttons they should be used ... same as the heat maps inherit").

The switch that adds the sheet ratings to the heat-map grid (decision 186) used to stop there: the
all-band scan (`run_for_participant`, which feeds `pipeline.run_biomarker`) took a tidy pain-report
DataFrame and never merged the sheets into it, so the scan read the home surveys only whatever the
switch said (decision 331's page-only fix made this NOT stale, rather than making it correct). Now
`_merge_clinic_sheet_ratings_into_pro_df` adds the same sheet rows, as new DataFrame rows carrying
only the chosen score, through the SAME `sheet_ratings.sheet_ratings_for_metric` the array-based
helper calls -- one rule, two shapes.

Runs in the container (Django): python3 Biomarkers/tests/test_sheet_ratings_in_all_band_scan.py
"""
import os
import sys

import numpy as np
import pandas as pd

_BRAVO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, _BRAVO_ROOT)
sys.path.insert(0, os.path.join(_BRAVO_ROOT, "modules"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "BRAVO.settings")
try:
    import django  # noqa: E402
    django.setup()
except Exception:
    pass
from Biomarkers import bravo_service as bs  # noqa: E402


def _sheet_steps():
    t0 = pd.Timestamp("2026-03-01 18:00", tz="UTC")
    return pd.DataFrame([
        dict(t_utc=t0 + pd.Timedelta(hours=i), left_leg=float(4 + i), overall=np.nan, back=np.nan,
             setting="clinic") for i in range(3)] + [
        dict(t_utc=t0 + pd.Timedelta(hours=9), left_leg=np.nan, overall=6.0, back=np.nan, setting="clinic")])


def _pro_df():
    t0 = pd.Timestamp("2026-01-01 12:00")
    return pd.DataFrame({
        bs._PRO_TIME_UTC_COL: [t0, t0 + pd.Timedelta(hours=1)],
        "left_leg_vas": [70.0, 80.0],
        "nrs": [5.0, 6.0],
    })


def _with(patches, fn):
    old = {k: getattr(bs, k) for k in patches}
    try:
        for k, v in patches.items():
            setattr(bs, k, v)
        return fn()
    finally:
        for k, v in old.items():
            setattr(bs, k, v)


def test_the_switch_off_leaves_pro_df_unchanged():
    patches = {"load_clinic_sheet_steps": lambda uid: (_sheet_steps(), None)}
    df, block = _with(patches, lambda: bs._merge_clinic_sheet_ratings_into_pro_df(
        "u", "left_leg_vas", "Left Leg VAS", _pro_df(), {}))
    assert len(df) == 2
    assert block["included"] is False and block["n_added"] == 0


def test_the_switch_on_adds_only_the_rows_carrying_the_chosen_score():
    patches = {"load_clinic_sheet_steps": lambda uid: (_sheet_steps(), None)}
    df, block = _with(patches, lambda: bs._merge_clinic_sheet_ratings_into_pro_df(
        "u", "left_leg_vas", "Left Leg VAS", _pro_df(),
        {"IncludeClinicSheetRatings": "1"}))
    assert len(df) == 5, "3 sheet steps carry a Left Leg score; the overall-only step is not one"
    assert block["included"] is True and block["n_added"] == 3 and block["n_available"] == 3
    added = df[df["_from_clinic_sheet"] == True]  # noqa: E712
    assert sorted(added["left_leg_vas"].tolist()) == [40.0, 50.0, 60.0], \
        "sheet 0-10 put on the page's 0-100 scale"
    assert added["nrs"].isna().all(), "every other column stays NaN, like an ordinary partial report"


def test_the_original_rows_are_never_touched():
    patches = {"load_clinic_sheet_steps": lambda uid: (_sheet_steps(), None)}
    original = _pro_df()
    df, _ = _with(patches, lambda: bs._merge_clinic_sheet_ratings_into_pro_df(
        "u", "left_leg_vas", "Left Leg VAS", original,
        {"IncludeClinicSheetRatings": "1"}))
    first_two = df.iloc[:2]
    assert first_two["left_leg_vas"].tolist() == [70.0, 80.0]
    assert first_two["nrs"].tolist() == [5.0, 6.0]


def test_a_score_the_sheets_have_no_column_for_gives_a_reason_and_no_rows_added():
    patches = {"load_clinic_sheet_steps": lambda uid: (_sheet_steps(), None)}
    df, block = _with(patches, lambda: bs._merge_clinic_sheet_ratings_into_pro_df(
        "u", "mpq_sum", "McGill", _pro_df(), {"IncludeClinicSheetRatings": "1"}))
    assert len(df) == 2
    assert block["included"] is True and block["n_added"] == 0
    assert block["reason"], block


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
