"""B5 of the 2026-09-15 review (decision 186): the clinic and at-home testing sheets' pain scores can
be pooled into the Biomarkers heat maps as extra ratings, behind a request switch that is OFF by
default. The sheet's 0-10 verbal scores are multiplied by 10 for the VAS (0-100) scores and taken
as they are for NRS. Every added rating carries a flag, counted per cell like the device-spectrum
mark, so the page can say how many of a cell's ratings came from a sheet.
"""
import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..", "..")))

from Biomarkers.routines import analytics as A            # noqa: E402
from Biomarkers.routines import sheet_ratings as SR        # noqa: E402
from Biomarkers.routines import sweep_settings as SS       # noqa: E402


def _steps():
    return [
        {"t_utc": "2026-03-04T18:00:00Z", "setting": "clinic", "overall": 7.0, "left_leg": 6.5, "back": None},
        {"t_utc": "2026-03-04T18:01:00Z", "setting": "clinic", "overall": None, "left_leg": 4.0, "back": 8.0},
        {"t_utc": "2026-07-07T15:00:00Z", "setting": "home", "overall": 3.0, "left_leg": None, "back": 2.0},
        {"t_utc": None, "setting": "home", "overall": 9.0, "left_leg": 9.0, "back": 9.0},   # no time: never used
    ]


def test_the_sheet_column_and_scale_for_each_page_score():
    assert SR.SHEET_COLUMN_FOR_METRIC["nrs"] == ("overall", 1.0)
    assert SR.SHEET_COLUMN_FOR_METRIC["vas"] == ("overall", 10.0)
    assert SR.SHEET_COLUMN_FOR_METRIC["left_leg_vas"] == ("left_leg", 10.0)
    assert SR.SHEET_COLUMN_FOR_METRIC["back_vas"] == ("back", 10.0)
    assert "mpq_sum" not in SR.SHEET_COLUMN_FOR_METRIC and "relief" not in SR.SHEET_COLUMN_FOR_METRIC


def test_sheet_ratings_are_rescaled_and_timed_and_scores_without_a_time_are_dropped():
    t, v, src = SR.sheet_ratings_for_metric(_steps(), "left_leg_vas")
    assert list(v) == [65.0, 40.0]                       # 6.5 and 4.0, times ten; None and no-time dropped
    assert list(src) == ["clinic", "clinic"]
    assert t[1] - t[0] == 60.0
    t2, v2, _ = SR.sheet_ratings_for_metric(_steps(), "nrs")
    assert list(v2) == [7.0, 3.0]                        # NRS is already 0-10
    t3, v3, _ = SR.sheet_ratings_for_metric(_steps(), "mpq_sum")
    assert t3.size == 0 and v3.size == 0                 # no sheet column for this score


def test_merged_ratings_are_in_time_order_and_flagged():
    pro_t = np.array([1.0e9, 3.0e9]); pro_v = np.array([8.0, 6.0])
    sh_t = np.array([2.0e9]); sh_v = np.array([70.0])
    t, v, flag = SR.merge_ratings(pro_t, pro_v, sh_t, sh_v)
    assert list(t) == [1.0e9, 2.0e9, 3.0e9]
    assert list(v) == [8.0, 70.0, 6.0]
    assert list(flag) == [False, True, False]
    # nothing to add: the originals come back untouched, every flag False
    t0, v0, f0 = SR.merge_ratings(pro_t, pro_v, np.zeros(0), np.zeros(0))
    assert list(t0) == list(pro_t) and list(v0) == list(pro_v) and not any(f0)


def test_the_request_switch_is_off_by_default_and_reaches_the_settings_tag():
    assert SS.include_clinic_sheet_ratings_param({}) is False
    assert SS.include_clinic_sheet_ratings_param({"IncludeClinicSheetRatings": "true"}) is True
    assert SS.include_clinic_sheet_ratings_param({"IncludeClinicSheetRatings": False}) is False
    off = SS.sweep_settings_tag_from_request({})
    on = SS.sweep_settings_tag_from_request({"IncludeClinicSheetRatings": True})
    assert off["include_clinic_sheet_ratings"] is False and on["include_clinic_sheet_ratings"] is True
    assert off != on, "a grid built with the sheet scores must never be served for a request without them"


def test_the_sweep_counts_sheet_ratings_per_cell_like_the_device_mark():
    rng = np.random.default_rng(0)
    n = 60
    pain = rng.integers(0, 11, n).astype(float)
    x = 100 + 10 * pain + rng.normal(0, 5, n)
    power = {1.0: x[:, None], 5.0: x[:, None]}
    flags = [i % 3 == 0 for i in range(n)]              # 20 of 60 from a sheet
    sw = A.band_time_sweep_from_power(power, pain, center_freqs_hz=[12.5], n_perm=20, n_boot=50,
                                      from_clinic_sheet=flags)
    assert sw["n_pain_reports_from_clinic_sheet"] == 20
    assert sw["clinic_sheet_n_grid"][0][0] == 20
    assert sw["best_correlation_rows"][0]["n_pain_reports_from_clinic_sheet"] == 20
    # the AUC grid throws the middle third away, so its count is its own, never copied across
    assert sw["clinic_sheet_n_grid_auc"][0][0] <= 20
    sw0 = A.band_time_sweep_from_power(power, pain, center_freqs_hz=[12.5], n_perm=20, n_boot=50)
    assert sw0["n_pain_reports_from_clinic_sheet"] is None, "'nobody checked' is not 'none of them'"
