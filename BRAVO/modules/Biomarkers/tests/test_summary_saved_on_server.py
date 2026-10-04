"""The deployment summary is saved on the server (the PI, 2026-10-04, decision 423): worked out once,
then served for the same request and the same recordings, settings files, pain reports and clinic
sheets; a new pain report is worked out again."""
from modules.Biomarkers import bravo_service as B
from modules.CacheStore.tests.test_store import _Sandbox, UID

REQ = {"ParticipantId": UID, "Channel": "ZERO_TWO_LEFT", "CenterHz": 20.5, "LabelMetric": "nrs"}


def _patched(pain):
    calls = []
    real = (B._deployment_summary_build, B.summary_input_fingerprints)
    B._deployment_summary_build = lambda rd: (calls.append(1) or {"available": True, "n": len(calls)})
    B.summary_input_fingerprints = lambda uid, rd: {"request": rd, "pain_reports": pain[0]}

    def undo():
        B._deployment_summary_build, B.summary_input_fingerprints = real
    return calls, undo


def test_worked_out_once_then_served():
    with _Sandbox():
        calls, undo = _patched(["p1"])
        try:
            a = B.deployment_summary(dict(REQ))
            b = B.deployment_summary(dict(REQ))
        finally:
            undo()
    assert len(calls) == 1 and a["n"] == b["n"] == 1
    assert b["saved_answer"]["served"] is True


def test_a_new_pain_report_is_worked_out_again():
    with _Sandbox():
        pain = ["p1"]
        calls, undo = _patched(pain)
        try:
            B.deployment_summary(dict(REQ))
            pain[0] = "p2"
            c = B.deployment_summary(dict(REQ))
        finally:
            undo()
    assert len(calls) == 2 and c["saved_answer"]["served"] is False


def test_nothing_is_saved_for_a_participant_the_database_does_not_hold():
    with _Sandbox() as d:
        calls = []
        real = B._deployment_summary_build
        B._deployment_summary_build = lambda rd: (calls.append(1) or {"available": True})
        try:
            B.deployment_summary({"ParticipantId": "no-such-participant", "Channel": "X",
                                  "CenterHz": 20.5})
            B.deployment_summary({"ParticipantId": "no-such-participant", "Channel": "X",
                                  "CenterHz": 20.5})
        finally:
            B._deployment_summary_build = real
        import os
        assert len(calls) == 2
        assert not os.path.isdir(os.path.join(d, "deployment_summary"))
