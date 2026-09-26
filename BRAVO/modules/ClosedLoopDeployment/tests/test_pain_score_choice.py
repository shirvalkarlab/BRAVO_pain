"""Nothing on the Closed-Loop page is computed on NRS alone (the PI, 2026-09-25 night).

The report hard-coded the pain score: the band-to-pain reading (E2) and the current-to-pain reading
(E3) read the `nrs` column, and the stability card's per-state odds ratios asked the Biomarkers
test for its default score, NRS. The page now sends the pain score chosen in a dropdown beside the
band selection (`PainScore`, one of the Biomarkers heat maps' own choices), and every band-to-pain
reading on the report follows it. What is saved under the recording set stays free of every pain
rating (decision 273; CLAUDE.md section 8 rule 5): the ratings are joined per request.
"""
import ast
import inspect
import textwrap

import numpy as np
import pandas as pd

from ClosedLoopDeployment import adapter as AD
from ClosedLoopDeployment import pipeline as PL
from ClosedLoopDeployment.tests.test_adapter_caching import (  # noqa: F401  (fixtures)
    _epoch_frame, _isolate_caches, _psd_frame, live_inputs)
from ClosedLoopDeployment.tests.test_calibrated_join import _cal_frame

try:
    from Biomarkers.routines import sweep_settings as SS
except ImportError:                                                  # pragma: no cover
    from modules.Biomarkers.routines import sweep_settings as SS

T0 = 1_750_000_000.0


def test_the_pain_scores_offered_are_the_biomarkers_heat_maps_own_list():
    assert AD.PAIN_SCORE_KEYS == tuple(m["key"] for m in SS.BIOMARKER_METRICS)
    assert AD.PAIN_SCORE_KEYS[0] == "nrs" and "left_leg_vas" in AD.PAIN_SCORE_KEYS


def test_the_requested_pain_score_is_named_on_the_answer_and_a_bad_one_is_refused_by_name():
    got = AD.pain_score_from_request({"PainScore": "left_leg_vas"})
    assert got["key"] == "left_leg_vas" and got["label"] == "Left Leg VAS", got
    assert got["requested"] == "left_leg_vas" and got["fell_back_to_nrs"] is False, got
    none = AD.pain_score_from_request({})
    assert none["key"] == "nrs" and none["fell_back_to_nrs"] is True
    assert "no pain score" in none["reason"], none
    bad = AD.pain_score_from_request({"PainScore": "worst_pain"})
    assert bad["key"] == "nrs" and bad["fell_back_to_nrs"] is True
    assert "worst_pain" in bad["reason"], bad


def _epochs6():
    t0 = pd.Timestamp(T0, unit="s", tz="UTC")
    starts = [t0 + pd.Timedelta(seconds=60 * k) for k in range(6)]
    return pd.DataFrame({"t_start": starts, "t_end": [s + pd.Timedelta(seconds=60) for s in starts],
                         "amp_mA_Left": [0.5, 1.0, 1.5, 2.0, 2.5, 3.0],
                         "amp_mA_Right": [np.nan] * 6, "freq_hz": [55.0] * 6,
                         "pw_us_Left": [60.0] * 6, "dur_h": [1 / 60] * 6,
                         "epoch": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]})


def _design_matrix():
    return pd.DataFrame({"epoch": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
                         "amp_mA_Left": [0.5, 1.0, 1.5, 2.0, 2.5, 3.0],
                         "nrs": [5.0, 5.0, 5.0, 5.0, 5.0, 5.1],
                         "vas": [50.0] * 6,
                         "left_leg_vas": [80.0, 70.0, 60.0, 40.0, 30.0, 20.0]})


def _run_capturing(monkeypatch, **kw):
    seen = {}
    real_state, real_therapy = PL.E.state_edge, PL.E.therapy_edge

    def state_spy(T, **k):
        seen["e2_outcome"] = k.get("outcome", "nrs")
        seen["T_columns"] = set(T.columns)
        seen["T"] = T
        return real_state(T, **k)

    def therapy_spy(dm, **k):
        seen["e3_outcome"] = k.get("outcome", "nrs")
        return real_therapy(dm, **k)
    monkeypatch.setattr(PL.E, "state_edge", state_spy)
    monkeypatch.setattr(PL.E, "therapy_edge", therapy_spy)
    rep = PL.run("P", psd_frame=_cal_frame(n=120, channels=("ZERO_TWO_LEFT",)), epochs=_epochs6(),
                 design_matrix=_design_matrix(),
                 candidates=[{"channel": "ZERO_TWO_LEFT", "center_hz": 20.5, "band_width_hz": 5.0}],
                 hemisphere="Left", power_scale="power_linear", n_boot=50, **kw)
    return rep, seen


def test_e2_and_e3_read_the_chosen_pain_score(monkeypatch):
    rep, seen = _run_capturing(monkeypatch, pain_score="left_leg_vas")
    assert seen["e2_outcome"] == "left_leg_vas" and seen["e3_outcome"] == "left_leg_vas", seen
    assert "left_leg_vas" in seen["T_columns"], "the joined table dropped the chosen score"
    by_epoch = seen["T"].dropna(subset=["left_leg_vas"]).groupby("setting_epoch")["left_leg_vas"].first()
    assert set(by_epoch.to_numpy()) <= set(_design_matrix()["left_leg_vas"]), by_epoch
    assert rep.manifest["pain_score"] == "left_leg_vas"
    # E3 on the leg score: pain falls 60 points over 2.5 mA, which NRS (flat) could not show
    assert rep.edges["E3"].estimate is not None and rep.edges["E3"].estimate < -10, rep.edges["E3"]


def test_without_a_pain_score_the_pipeline_reads_nrs_as_before(monkeypatch):
    rep, seen = _run_capturing(monkeypatch)
    assert seen["e2_outcome"] == "nrs" and seen["e3_outcome"] == "nrs"
    assert rep.manifest["pain_score"] == "nrs"


def test_the_joined_table_memo_tells_two_leg_scores_apart():
    psd, eps = _psd_frame(), _epoch_frame()
    p1 = pd.DataFrame({"epoch": [1.0], "report_id": ["1"], "nrs": [7.0], "vas": [70.0],
                       "left_leg_vas": [40.0]})
    p2 = p1.assign(left_leg_vas=[90.0])
    t1 = AD.joined_table_cached(psd, eps, pro_frame=p1)
    t2 = AD.joined_table_cached(psd, eps, pro_frame=p2)
    assert t1 is not t2, "a memo hit handed back the other request's leg ratings"
    assert set(t2["left_leg_vas"].dropna()) == {90.0}


def test_the_composite_is_blended_per_report_by_biomarkers_then_averaged_per_setting(live_inputs,
                                                                                      monkeypatch):
    import sys
    bs = sys.modules["modules.Biomarkers.bravo_service"]
    t0 = pd.Timestamp("2026-01-01T00:00:00Z")
    pros = pd.DataFrame([{"t_utc": t0 + pd.Timedelta(hours=h), "nrs": 5.0, "vas": 50.0,
                          "mpq_sum": m, "left_leg_vas": v}
                         for h, m, v in ((1.0, 10.0, 60.0), (2.0, 20.0, 80.0), (7.0, 5.0, 20.0),
                                         (8.0, 5.0, 30.0), (13.0, 1.0, 10.0), (14.0, 3.0, 10.0))])
    monkeypatch.setattr(bs, "_load_pros", lambda request_data, participant: pros, raising=False)

    def resolve(request_data, df):                # stands in for Biomarkers' own blend
        out = df.copy()
        out["composite_mpq_leftleg"] = out["mpq_sum"] + out["left_leg_vas"] / 10.0
        return out, "composite_mpq_leftleg", ("mpq_sum", "left_leg_vas")
    monkeypatch.setattr(bs, "_resolve_biomarker_metric", resolve, raising=False)
    _psd, eps, dm = AD.evidence_inputs_cached("PARTICIPANT")
    assert "composite_mpq_leftleg" not in dm.columns
    dm2, note = AD.design_matrix_with_pain_score("PARTICIPANT", dm, eps, "composite_mpq_leftleg")
    assert note is None, note
    per_report = pros["mpq_sum"] + pros["left_leg_vas"] / 10.0
    want = {1.0: per_report[:2].mean(), 2.0: per_report[2:4].mean(), 3.0: per_report[4:].mean()}
    got = dict(zip(dm2["epoch"], dm2["composite_mpq_leftleg"]))
    for e, v in want.items():
        assert abs(got[e] - v) < 1e-12, (e, got, want)
    # a score the design matrix already carries is handed back untouched
    same, note2 = AD.design_matrix_with_pain_score("PARTICIPANT", dm, eps, "nrs")
    assert same is dm and note2 is None


def test_the_saved_inputs_hold_no_pain_rating_and_their_key_takes_no_pain_score(live_inputs,
                                                                                monkeypatch):
    assert list(inspect.signature(AD.inputs_signature).parameters) == ["participant"]
    seen = {}
    real = AD._shared_store

    def spy(kind, sig, payload, **kw):
        seen[kind] = (sig, payload)
        return real(kind, sig, payload, **kw)
    monkeypatch.setattr(AD, "_shared_store", spy)
    AD.evidence_inputs_cached("PARTICIPANT", force_refresh=True)
    sig, saved = seen["inputs"]
    assert not any(k in repr(sig) for k in AD.PAIN_SCORE_KEYS), sig
    for f in saved:
        cols = set(getattr(f, "columns", []))
        assert not cols & set(AD.PAIN_SCORE_KEYS), sorted(cols)


def _report_source():
    return textwrap.dedent(inspect.getsource(AD.report_for_participant))


def test_the_report_hands_the_chosen_score_to_the_pipeline_and_to_the_stability_test():
    tree = ast.parse(_report_source())
    calls = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            name = getattr(n.func, "attr", getattr(n.func, "id", None))
            calls.setdefault(name, []).append({k.arg for k in n.keywords})
    assert any("pain_score" in kws for kws in calls.get("run", [])), \
        "the pipeline is not handed the chosen pain score"
    assert any("pain_score" in kws for kws in calls.get("stability_request_body", [])), \
        "the stability test is not asked on the chosen pain score"


def test_the_stability_request_carries_the_chosen_score_as_the_biomarkers_label_metric():
    body = AD.stability_request_body("UID", "ONE_THREE_LEFT", 24.5, 5.0, pain_score="left_leg_vas")
    assert body == {"ParticipantId": "UID", "Channel": "ONE_THREE_LEFT", "CenterHz": 24.5,
                    "BandWidthHz": 5.0, "LabelMetric": "left_leg_vas"}, body


def test_each_state_names_how_many_pain_reports_its_interval_rests_on():
    from ClosedLoopDeployment import stability as ST
    slopes = {"OFF": {"slope_log_or": 0.2, "se": 0.3, "n": 60, "n_reports": 14},
              "LOW": {"slope_log_or": -0.1, "se": 0.25, "n": 80, "n_reports": 21}, "HIGH": None}
    eq = ST.stability_equivalence(slopes, 0.4)
    raw = {"available": True, "lrt_p": 0.4, "slope_by_era": slopes, "equivalence": eq,
           "stability_verdict": eq["verdict"], "n": 140, "n_clusters": 9,
           "era_counts": {"OFF": 60, "LOW": 80, "HIGH": 0}, "rate": {"available": False},
           "or_by_era": {"OFF": 1.2214, "LOW": 0.9048, "HIGH": None},
           "or_by_era_ci": {"OFF": [0.6, 2.4], "LOW": [0.5, 1.6], "HIGH": None},
           "or_by_era_n_reports": {"OFF": 14, "LOW": 21, "HIGH": None}}
    per = ST.finding_from_stability_result(raw, "ONE_THREE_LEFT", 24.5).as_payload()["odds_ratio_per_state"]
    assert per["stimulation off"]["n_reports"] == 14 and per["low current"]["n_reports"] == 21
    assert per["high current"]["n_reports"] is None
