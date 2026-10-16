"""The Closed-Loop report is saved on the server (the PI, 2026-10-04, decision 423).

A report for a band is worked out once and then served to every request with the same inputs: the
same request, and the same recordings, settings files, pain reports, clinic sheets and stored
tables (`adapter.report_input_fingerprints`). A new pain report changes the label, so the report is
worked out again. The band grid and the stored-results line are read fresh on every request. A
request with no band (the grid alone) is never saved.
"""
from modules.ClosedLoopDeployment import adapter as AD, bravo_service as BS
from modules.CacheStore.tests.test_store import _Sandbox, UID

REQ = {"ParticipantId": UID, "Candidates": [{"channel": "ZERO_TWO_LEFT", "center_hz": 20.5}],
       "PainScore": "nrs"}


def _patched(pain):
    calls = []
    saved = {k: getattr(AD, k) for k in ("report_for_participant", "report_input_fingerprints",
                                        "band_sweep_grid_for_closed_loop", "_cache_status_or_reason")}
    real_part = BS._participant_or_none

    def report(participant, rd, **kw):
        calls.append(1)
        return {"available": True, "verdict": "x", "n": len(calls), "band_sweep_grid": {"g": 0},
                "cache_status": {"c": 0}}
    AD.report_for_participant = report
    AD.report_input_fingerprints = lambda participant, rd: {"request": rd, "pain_reports": pain[0]}
    AD.band_sweep_grid_for_closed_loop = lambda uid, rd=None, **k: {"g": "fresh"}
    AD._cache_status_or_reason = lambda participant: {"c": "fresh"}
    BS._participant_or_none = lambda uid: object()

    def undo():
        for k, v in saved.items():
            setattr(AD, k, v)
        BS._participant_or_none = real_part
    return calls, undo


def test_worked_out_once_then_served_without_the_grid():
    with _Sandbox():
        pain = ["p1"]
        calls, undo = _patched(pain)
        try:
            a = BS._run_for_participant(dict(REQ))
            b = BS._run_for_participant(dict(REQ))
        finally:
            undo()
    assert len(calls) == 1
    assert a["n"] == b["n"] == 1
    assert b["saved_answer"]["served"] is True
    # the band grid leaves a band's report (decision 431: the page reads the grid from its own
    # request, never from here), so a served report re-reads only the stored-results line
    assert "band_sweep_grid" not in a and "band_sweep_grid" not in b
    assert b["cache_status"] == {"c": "fresh"}


def test_a_new_pain_report_is_worked_out_again():
    with _Sandbox():
        pain = ["p1"]
        calls, undo = _patched(pain)
        try:
            BS._run_for_participant(dict(REQ))
            pain[0] = "p2"
            c = BS._run_for_participant(dict(REQ))
        finally:
            undo()
    assert len(calls) == 2 and c["saved_answer"]["served"] is False


def test_the_grid_alone_is_never_saved():
    with _Sandbox():
        pain = ["p1"]
        calls, undo = _patched(pain)
        try:
            BS._run_for_participant({"ParticipantId": UID, "Candidates": []})
            BS._run_for_participant({"ParticipantId": UID, "Candidates": []})
        finally:
            undo()
    assert len(calls) == 2


def test_the_grid_alone_still_carries_the_grid():
    with _Sandbox():
        calls, undo = _patched(["p1"])
        try:
            out = BS._run_for_participant({"ParticipantId": UID, "Candidates": []})
        finally:
            undo()
    assert out["band_sweep_grid"] == {"g": 0}


def test_a_band_report_request_is_remembered_and_the_grid_alone_is_not():
    """Decision 435: the server replays remembered band requests when the data change."""
    import os
    from modules.CacheStore import locks, request_memory as rm
    from modules.CacheStore.tests.test_request_memory import FakeRedis
    fake = FakeRedis()
    saved, saved_env = locks.CLIENT_FACTORY, os.environ.get(rm.OFF_ENV)
    locks.CLIENT_FACTORY, os.environ[rm.OFF_ENV] = (lambda: fake), "1"
    try:
        with _Sandbox():
            calls, undo = _patched(["p1"])
            try:
                BS._run_for_participant(dict(REQ))
                BS._run_for_participant({"ParticipantId": UID, "Candidates": []})
            finally:
                undo()
        got = rm.recent(UID)
    finally:
        locks.CLIENT_FACTORY = saved
        if saved_env is None:
            os.environ.pop(rm.OFF_ENV, None)
        else:
            os.environ[rm.OFF_ENV] = saved_env
    assert [(g["kind"], g["body"]) for g in got] == [(BS.REPORT_KIND, REQ)]
