"""Whole answers saved on the server under everything that can change them (the PI, 2026-10-04,
decision 423: "save report and summary on the server").

The Closed-Loop report (about 22 s) and the deployment summary (about 9 s) were worked out on every
request. They are now saved under a label built from the request, the data fingerprints the caller
supplies (recordings, settings files, pain reports, clinic sheets, the stored tables read) and a
fingerprint of the analysis code itself, so a new pain report, a new recording, a changed setting
or a code change each makes the saved copy miss. Values: built once then served; another input is
built again; an answer that is not available is never saved; the code fingerprint changes when any
analysis file changes and not otherwise; fields named as volatile are left out and re-attached.
"""
import os
import pathlib
import tempfile

from modules.CacheStore import saved_answers as SA
from modules.CacheStore.tests.test_store import _Sandbox, UID

KIND = "closed_loop_report"


def test_built_once_then_served_and_another_input_builds_again():
    with _Sandbox():
        calls = []

        def build():
            calls.append(1)
            return {"available": True, "value": 41 + len(calls)}
        a = SA.serve_or_build(KIND, UID, {"request": {"band": 1}, "pain": "p1"}, build,
                              writer="closed_loop")
        b = SA.serve_or_build(KIND, UID, {"request": {"band": 1}, "pain": "p1"}, build,
                              writer="closed_loop")
        c = SA.serve_or_build(KIND, UID, {"request": {"band": 1}, "pain": "p2"}, build,
                              writer="closed_loop")
        assert len(calls) == 2
        assert a["value"] == b["value"] == 42 and c["value"] == 43
        assert a["saved_answer"]["served"] is False and b["saved_answer"]["served"] is True
        assert b["saved_answer"]["written_utc"]


def test_an_unavailable_answer_is_never_saved():
    with _Sandbox():
        calls = []

        def build():
            calls.append(1)
            return {"available": False, "reason": "nothing"}
        SA.serve_or_build(KIND, UID, {"x": 1}, build, writer="closed_loop")
        SA.serve_or_build(KIND, UID, {"x": 1}, build, writer="closed_loop")
        assert len(calls) == 2


def test_volatile_fields_are_not_saved_and_are_attached_fresh():
    with _Sandbox():
        n = []

        def build():
            n.append(1)
            return {"available": True, "value": 1, "grid": {"live": len(n)}}
        fresh = lambda: {"grid": {"live": "now"}}                   # noqa: E731
        SA.serve_or_build(KIND, UID, {"x": 1}, build, writer="closed_loop", volatile=("grid",),
                          refresh=fresh)
        b = SA.serve_or_build(KIND, UID, {"x": 1}, build, writer="closed_loop", volatile=("grid",),
                              refresh=fresh)
        assert b["grid"] == {"live": "now"} and b["value"] == 1


def test_the_code_fingerprint_follows_the_analysis_files():
    with tempfile.TemporaryDirectory() as d:
        root = pathlib.Path(d)
        (root / "Mod").mkdir()
        (root / "Mod" / "a.py").write_text("x = 1\n")
        (root / "Mod" / "tests").mkdir()
        (root / "Mod" / "tests" / "test_a.py").write_text("y = 1\n")
        one = SA.code_digest(root, cache=False)
        (root / "Mod" / "tests" / "test_a.py").write_text("y = 2\n")   # a test: no change
        assert SA.code_digest(root, cache=False) == one
        (root / "Mod" / "a.py").write_text("x = 2\n")                    # analysis code: change
        assert SA.code_digest(root, cache=False) != one


def test_the_label_carries_the_code_fingerprint():
    with _Sandbox():
        calls = []

        def build():
            calls.append(1)
            return {"available": True}
        real = SA.code_digest
        SA.serve_or_build(KIND, UID, {"x": 1}, build, writer="closed_loop")
        SA.code_digest = lambda *a, **k: "another version of the code"
        try:
            SA.serve_or_build(KIND, UID, {"x": 1}, build, writer="closed_loop")
        finally:
            SA.code_digest = real
        assert len(calls) == 2
