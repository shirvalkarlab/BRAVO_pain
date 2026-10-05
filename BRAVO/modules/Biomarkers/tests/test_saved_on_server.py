"""The Biomarkers answers saved on the server (the one store, CacheStore).

- The deployment summary (the PI, 2026-10-04, decision 423) and the Closed-Loop page's ROC,
  month-by-month and band-power panels (decision 428; measured 3.9, 4.2 and 11-13 s on every
  request): worked out once, then served for the same request and the same recordings, settings
  files, pain reports and clinic sheets (`summary_input_fingerprints`); a new pain report is worked
  out again; an unknown participant is never saved.
- They remember the requests they answer (decision 435), so the server can work them out again when
  the data change; a request whose label cannot be built is not remembered.
- The device's programmed adaptive thresholds, saved per participant (decision 429): about 2.3 s of
  every band-power request walked all 10,421 therapy groups. The answer depends only on the therapy
  history, so it is saved under the participant's source files and the therapy rows' count and
  highest id; any change there works it out again. An empty answer is not saved.

Merged here 2026-10-05: test_panels_saved_on_server.py, test_summary_saved_on_server.py,
test_saved_band_answer_remembered.py, test_programmed_thresholds_saved.py.
"""
import os

from modules.Biomarkers import bravo_service as B
from modules.CacheStore import locks, request_memory as rm, saved_answers
from modules.CacheStore.tests.test_request_memory import FakeRedis
from modules.CacheStore.tests.test_store import _Sandbox, UID

REQ = {"ParticipantId": UID, "Channel": "ZERO_TWO_LEFT", "CenterHz": 20.5, "BandWidthHz": 5.0,
       "MatchDirection": "prior", "LabelMetric": "nrs"}
ENDPOINTS = (("deployment_summary", "_deployment_summary_build"),
             ("band_deployment_roc", "_band_deployment_roc_build"),
             ("band_deployment_roc_by_era", "_band_deployment_roc_by_era_build"),
             ("band_lsb_and_power", "_band_lsb_and_power_build"))


def _patched(build_name, pain):
    calls = []
    real = (getattr(B, build_name), B.summary_input_fingerprints)
    setattr(B, build_name, lambda rd: (calls.append(1) or {"available": True, "n": len(calls)}))
    B.summary_input_fingerprints = lambda uid, rd: {"request": rd, "pain_reports": pain[0]}

    def undo():
        setattr(B, build_name, real[0])
        B.summary_input_fingerprints = real[1]
    return calls, undo


def test_each_answer_is_worked_out_once_then_served_and_again_after_a_new_pain_report():
    for endpoint, build in ENDPOINTS:
        with _Sandbox():
            pain = ["p1"]
            calls, undo = _patched(build, pain)
            try:
                a = getattr(B, endpoint)(dict(REQ))
                b = getattr(B, endpoint)(dict(REQ))
                pain[0] = "p2"
                c = getattr(B, endpoint)(dict(REQ))
            finally:
                undo()
        assert len(calls) == 2, endpoint
        assert b["saved_answer"]["served"] is True and a["n"] == b["n"] == 1, endpoint
        assert c["saved_answer"]["served"] is False, endpoint


def test_nothing_is_saved_for_a_participant_the_database_does_not_hold():
    for endpoint, build in ENDPOINTS:
        kind = B.PANEL_KINDS.get(endpoint, "deployment_summary")
        with _Sandbox() as d:
            calls = []
            real = getattr(B, build)
            setattr(B, build, lambda rd: (calls.append(1) or {"available": True}))
            try:
                for _ in range(2):
                    getattr(B, endpoint)({"ParticipantId": "no-such-participant", "Channel": "X",
                                          "CenterHz": 20.5})
            finally:
                setattr(B, build, real)
            assert len(calls) == 2, endpoint
            assert not os.path.isdir(os.path.join(d, kind)), endpoint


def test_the_three_panels_are_saved_under_their_own_kinds():
    assert {B.PANEL_KINDS[e] for e, _ in ENDPOINTS[1:]} == {"deployment_roc", "deployment_roc_by_era",
                                                             "band_lsb_power"}


def _run_remembered(fingerprints):
    fake = FakeRedis()
    saved = (locks.CLIENT_FACTORY, os.environ.get(rm.OFF_ENV), B.summary_input_fingerprints,
             saved_answers.serve_or_build)
    locks.CLIENT_FACTORY, os.environ[rm.OFF_ENV] = (lambda: fake), "1"
    B.summary_input_fingerprints = fingerprints
    saved_answers.serve_or_build = lambda kind, uid, inputs, build, **k: build()
    try:
        out = B._serve_saved_band_answer("deployment_summary", {"ParticipantId": "u1", "CenterHz": 23.5},
                                         lambda rd: {"available": True, "rd": rd})
        return out, rm.recent("u1")
    finally:
        locks.CLIENT_FACTORY, env, B.summary_input_fingerprints, saved_answers.serve_or_build = saved
        if env is None:
            os.environ.pop(rm.OFF_ENV, None)
        else:
            os.environ[rm.OFF_ENV] = env


def test_an_answered_request_is_remembered_and_one_without_a_label_is_not():
    out, got = _run_remembered(lambda uid, rd: {"x": 1})
    assert out["available"] is True
    assert [(g["kind"], g["body"]) for g in got] == [
        ("deployment_summary", {"ParticipantId": "u1", "CenterHz": 23.5})]

    def no_label(uid, rd):
        raise LookupError("no participant")
    out, got = _run_remembered(no_label)
    assert out["available"] is True and got == [], "a request without a label is not remembered"


THRESHOLDS = {"Left": {"lower": 192.0, "upper": 242.0, "status": "RUNNING", "date": 1.0}}


def _patched_thresholds(label, answer):
    calls = []
    real = (B._programmed_adaptive_thresholds_build, B._therapy_history_label)
    B._programmed_adaptive_thresholds_build = lambda p: (calls.append(1) or dict(answer))
    B._therapy_history_label = lambda p: label[0]

    def undo():
        B._programmed_adaptive_thresholds_build, B._therapy_history_label = real
    return calls, undo


def test_programmed_thresholds_worked_out_once_read_back_again_on_a_new_history_and_empty_never_saved():
    with _Sandbox():
        label = [("files-1", 10421, 99)]
        calls, undo = _patched_thresholds(label, THRESHOLDS)
        try:
            a = B._programmed_adaptive_thresholds("P")
            b = B._programmed_adaptive_thresholds("P")
            label[0] = ("files-1", 10422, 100)
            c = B._programmed_adaptive_thresholds("P")
        finally:
            undo()
    assert a == b == c == THRESHOLDS and len(calls) == 2
    with _Sandbox():
        calls, undo = _patched_thresholds([("files-1", 1, 1)], {})
        try:
            B._programmed_adaptive_thresholds("P")
            B._programmed_adaptive_thresholds("P")
        finally:
            undo()
    assert len(calls) == 2, "an empty answer is not saved"
