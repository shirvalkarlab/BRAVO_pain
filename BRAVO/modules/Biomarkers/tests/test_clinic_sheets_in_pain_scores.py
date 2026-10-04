"""With the clinic-sheet switch on, the Biomarkers page's pain scores and its matching index carry
the clinic and at-home sheets' ratings as well as REDCap's (the PI, 2026-10-04: "update the pain
reports matching, text reports ... to use clinic sheets when toggled on", decision 436). The heat
maps and the band checks already did (decision 186); the plotted pain row, the coverage sentence and
the binarization card read these two requests, which did not.

Values: on, Left leg VAS gains the sheet's left-leg score x 10 and NRS the overall score as is,
each flagged as from a sheet; MPQ (no sheet column) is unchanged; off, nothing is added. The
matching index counts the sheet ratings among its reports."""
import pandas as pd

T_RC = pd.Timestamp("2026-09-01 18:00:00")
T_SHEET = pd.Timestamp("2026-09-02 17:30:00")


def _pro():
    return pd.DataFrame({"_pro_time_utc": [T_RC], "date_time_s1_daily": ["2026-09-01 11:00:00"],
                         "nrs": [6.0], "left_leg_vas": [55.0], "mpq_sum": [20.0]})


STEPS = [{"t_utc": T_SHEET, "overall": 4.0, "left_leg": 3.0, "setting": "a"},
         {"t_utc": None, "overall": 2.0, "left_leg": 2.0, "setting": "plan"}]


def _with_stubs(fn):
    from modules.Biomarkers import bravo_service as bs
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


def test_switch_on_adds_each_scores_sheet_ratings_flagged():
    out = _with_stubs(lambda bs: bs.pain_scores_for_participant(
        {"ParticipantId": "u", "IncludeClinicSheetRatings": True}))
    assert _points(out, "left_leg_vas") == [(55.0, False), (30.0, True)]
    assert _points(out, "nrs") == [(6.0, False), (4.0, True)]
    assert _points(out, "mpq_sum") == [(20.0, False)]
    assert out["clinic_sheets"]["n_added"] == {"nrs": 1, "left_leg_vas": 1}


def test_switch_off_adds_nothing():
    out = _with_stubs(lambda bs: bs.pain_scores_for_participant({"ParticipantId": "u"}))
    assert _points(out, "left_leg_vas") == [(55.0, False)]
    assert _points(out, "nrs") == [(6.0, False)]


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
