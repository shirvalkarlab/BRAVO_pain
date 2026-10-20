"""The clinic and at-home testing sheets' pain scores, merged into the Biomarkers analyses behind a
request switch that is OFF by default. The sheet's 0-10 verbal scores are multiplied by 10 for the
VAS (0-100) scores and taken as they are for NRS; every added rating carries a flag.

- the heat-map grid (B5 of the 2026-09-15 review, decision 186): counted per cell like the
  device-spectrum mark;
- the deployment summary, deployment ROC and stability grid, which share one setup
  (`_band_validation_setup`), behind the Closed-Loop page's button (the PI, 2026-09-24);
- the all-band scan (`run_for_participant`, the PI, 2026-09-27): the same sheet rows added as new
  DataFrame rows through the same `sheet_ratings.sheet_ratings_for_metric`, one rule, two shapes;
- the plotted pain scores and the matching index (the PI, 2026-10-04, decision 436).

Merged here 2026-10-05: test_sheet_ratings_in_summary.py, test_sheet_ratings_in_all_band_scan.py,
test_clinic_sheets_in_pain_scores.py.
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

from Biomarkers import bravo_service as bs                 # noqa: E402
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


# ==================================================================================================
# merged from test_sheet_ratings_in_summary.py
# The deployment summary's shared setup (`_band_validation_setup`), behind the Closed-Loop page's button.


def _sheet_steps():
    t0 = pd.Timestamp("2026-03-01 18:00", tz="UTC")
    return pd.DataFrame([
        dict(t_utc=t0 + pd.Timedelta(hours=i), left_leg=float(4 + i), overall=np.nan, back=np.nan,
             setting="clinic") for i in range(3)] + [
        dict(t_utc=t0 + pd.Timedelta(hours=9), left_leg=np.nan, overall=6.0, back=np.nan, setting="clinic")])


def _with(patches, fn):
    old = {k: getattr(bs, k) for k in patches}
    try:
        for k, v in patches.items():
            setattr(bs, k, v)
        return fn()
    finally:
        for k, v in old.items():
            setattr(bs, k, v)


def test_the_helper_merges_only_the_steps_carrying_the_score_and_only_when_switched_on():
    t = np.array([1.0e9, 1.1e9]); v = np.array([50.0, 60.0])
    patches = {"load_clinic_sheet_steps": lambda uid: (_sheet_steps(), None)}
    off = _with(patches, lambda: bs._merge_clinic_sheet_ratings("u", "left_leg_vas", "Left Leg VAS", t, v, {}))
    on = _with(patches, lambda: bs._merge_clinic_sheet_ratings(
        "u", "left_leg_vas", "Left Leg VAS", t, v, {"IncludeClinicSheetRatings": "1"}))
    assert off[0].size == 2 and not off[2].any() and off[3]["included"] is False
    assert on[0].size == 5, "three steps carry a Left Leg score; the NRS-only step is not one"
    assert int(on[2].sum()) == 3 and on[3]["n_added"] == 3 and on[3]["included"] is True
    assert sorted(on[1][on[2]]) == [40.0, 50.0, 60.0], "sheet 0-10 put on the page's 0-100 scale"


def test_the_shared_setup_hands_the_merged_ratings_to_the_matcher_when_switched_on():
    seen = []
    from Biomarkers.routines import streaming_psd as sp

    class _P:
        uid = "u"

    def _pooled(mat, times, values, **kw):
        seen.append(np.asarray(times).size)
        return {"psd": np.zeros((1, 1))}
    t = np.array([1.0e9, 1.1e9]); v = np.array([50.0, 60.0])
    patches = {
        "load_clinic_sheet_steps": lambda uid: (_sheet_steps(), None),
        "_load_pros": lambda rd, P: pd.DataFrame({"x": [1, 2]}),
        "_resolve_biomarker_metric": lambda rd, df: (df, "left_leg_vas", None),
        "_pro_match_arrays": lambda df, m: (t, v),
        "_cached_psd_matrix": lambda uid, **k: {"t": np.array([1.0]), "X": np.ones((1, 1))},
        "_all_pro_times": lambda df: t,
        "_chronic_list_for": lambda uid: [],
    }
    old_find, old_pool = bs.models.Participant.find, sp.build_pooled_detail_from_matrix
    bs.models.Participant.find = staticmethod(lambda uid: _P())
    sp.build_pooled_detail_from_matrix = _pooled
    try:
        off = _with(patches, lambda: bs._band_validation_setup({"ParticipantId": "u"}))
        on = _with(patches, lambda: bs._band_validation_setup({"ParticipantId": "u", "IncludeClinicSheetRatings": "1"}))
    finally:
        bs.models.Participant.find, sp.build_pooled_detail_from_matrix = old_find, old_pool
    assert seen == [2, 5], seen
    assert off["clinic_sheet_ratings"]["included"] is False
    assert on["clinic_sheet_ratings"]["n_added"] == 3


# ==================================================================================================
# merged from test_sheet_ratings_in_all_band_scan.py
# The all-band scan (`_merge_clinic_sheet_ratings_into_pro_df`).


def _pro_df():
    t0 = pd.Timestamp("2026-01-01 12:00")
    return pd.DataFrame({
        bs._PRO_TIME_UTC_COL: [t0, t0 + pd.Timedelta(hours=1)],
        "left_leg_vas": [70.0, 80.0],
        "nrs": [5.0, 6.0],
    })


def _merge_into_pro_df(metric, label, request):
    patches = {"load_clinic_sheet_steps": lambda uid: (_sheet_steps(), None)}
    return _with(patches, lambda: bs._merge_clinic_sheet_ratings_into_pro_df(
        "u", metric, label, _pro_df(), request))


def test_the_all_band_scan_adds_only_the_rows_carrying_the_chosen_score_and_only_when_switched_on():
    df, block = _merge_into_pro_df("left_leg_vas", "Left Leg VAS", {})
    assert len(df) == 2, "switch off: the pain-report table is unchanged"
    assert block["included"] is False and block["n_added"] == 0
    df, block = _merge_into_pro_df("left_leg_vas", "Left Leg VAS", {"IncludeClinicSheetRatings": "1"})
    assert len(df) == 5, "3 sheet steps carry a Left Leg score; the overall-only step is not one"
    assert block["included"] is True and block["n_added"] == 3 and block["n_available"] == 3
    added = df[df["_from_clinic_sheet"] == True]  # noqa: E712
    assert sorted(added["left_leg_vas"].tolist()) == [40.0, 50.0, 60.0], \
        "sheet 0-10 put on the page's 0-100 scale"
    assert added["nrs"].isna().all(), "every other column stays NaN, like an ordinary partial report"
    first_two = df.iloc[:2]                               # the original rows are never touched
    assert first_two["left_leg_vas"].tolist() == [70.0, 80.0]
    assert first_two["nrs"].tolist() == [5.0, 6.0]


def test_a_score_the_sheets_have_no_column_for_gives_a_reason_and_no_rows_added():
    df, block = _merge_into_pro_df("mpq_sum", "McGill", {"IncludeClinicSheetRatings": "1"})
    assert len(df) == 2
    assert block["included"] is True and block["n_added"] == 0
    assert block["reason"], block


# ==================================================================================================
# merged from test_clinic_sheets_in_pain_scores.py
# The plotted pain scores and the matching index (decision 436).

T_RC = pd.Timestamp("2026-09-01 18:00:00")

T_SHEET = pd.Timestamp("2026-09-02 17:30:00")


def _pro():
    return pd.DataFrame({"_pro_time_utc": [T_RC], "date_time_s1_daily": ["2026-09-01 11:00:00"],
                         "nrs": [6.0], "left_leg_vas": [55.0], "mpq_sum": [20.0]})

STEPS = [{"t_utc": T_SHEET, "overall": 4.0, "left_leg": 3.0, "setting": "a"},
         {"t_utc": None, "overall": 2.0, "left_leg": 2.0, "setting": "plan"}]


def _with_stubs(fn):
    saved = (bs.models.Participant.find, bs._load_pros, bs.load_clinic_sheet_steps)
    bs.models.Participant.find = staticmethod(lambda **k: object())
    bs._load_pros = lambda rd, p=None: _pro()
    bs.load_clinic_sheet_steps = lambda uid: (STEPS, None)
    try:
        return fn(bs)
    finally:
        bs.models.Participant.find, bs._load_pros, bs.load_clinic_sheet_steps = saved


def _points(out, key):
    return [(p["v"], bool(p.get("sheet"))) for m in out["metrics"] if m["key"] == key
            for p in m["points"]]


def test_the_pain_scores_gain_the_sheet_ratings_flagged_only_when_switched_on():
    out = _with_stubs(lambda bs: bs.pain_scores_for_participant(
        {"ParticipantId": "u", "IncludeClinicSheetRatings": True}))
    assert _points(out, "left_leg_vas") == [(55.0, False), (30.0, True)]
    assert _points(out, "nrs") == [(6.0, False), (4.0, True)]
    assert _points(out, "mpq_sum") == [(20.0, False)]
    assert out["clinic_sheets"]["n_added"] == {"nrs": 1, "left_leg_vas": 1}
    off = _with_stubs(lambda bs: bs.pain_scores_for_participant({"ParticipantId": "u"}))
    assert _points(off, "left_leg_vas") == [(55.0, False)]
    assert _points(off, "nrs") == [(6.0, False)]


def test_matching_index_counts_the_sheet_ratings():
    def run(bs):
        seen = {}
        saved = {k: getattr(bs, k) for k in ("_availability_recordings_cached", "_load_recordings",
                                             "_build_sensing_config_index",
                                             "_rating_centred_scan_index", "_recording_set_identity")}
        bs._availability_recordings_cached = lambda uid, recording_set=None: ([], [], [])
        bs._load_recordings = lambda uid, types: []
        bs._build_sensing_config_index = lambda recs: {}
        bs._recording_set_identity = lambda uid: "rs"

        def idx(uid, td, psd, pain, sensing):
            seen["pain_t"] = list(pain["t"])
            return []
        bs._rating_centred_scan_index = idx
        try:
            bs._SCAN_INDEX_MEMO.clear()
            on = bs.psd_scan_index_for_participant({"ParticipantId": "u", "LabelMetric": "left_leg_vas",
                                                     "IncludeClinicSheetRatings": True})
            n_on = len(seen["pain_t"])
            off = bs.psd_scan_index_for_participant({"ParticipantId": "u", "LabelMetric": "left_leg_vas"})
            return on, off, n_on, len(seen["pain_t"])
        finally:
            for k, v in saved.items():
                setattr(bs, k, v)
            bs._SCAN_INDEX_MEMO.clear()
    on, off, n_on, n_off = _with_stubs(run)
    assert (on["n_reports"], on["n_clinic_sheet"], n_on) == (2, 1, 2)
    assert (off["n_reports"], off["n_clinic_sheet"], n_off) == (1, 0, 1)
