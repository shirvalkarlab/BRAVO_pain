"""The server works the remembered band answers out again when a participant's data change (the PI,
2026-10-04: "yes do 3b", decision 435): after an ingest, a new or corrected pain report, new clinic
sheets, new settings files or new code. Every 10 minutes it compares each participant's data
fingerprint with the one it last worked under; if it moved, it replays the remembered requests
(`CacheStore.request_memory`), newest first, at most 8 at once.

Values: unchanged data replays nothing; changed data replays every remembered request once, newest
first, and then counts as current; one failing request does not stop the rest; the replays are
not themselves remembered; each kind is answered by its page's own function."""
import os

import pytest

from modules.CacheStore import locks, request_memory as rm
from modules.CacheStore.tests.test_request_memory import FakeRedis
from modules.ClosedLoopDeployment import refresh_saved_answers as job


@pytest.fixture
def fake(monkeypatch):
    f = FakeRedis()
    monkeypatch.setattr(locks, "CLIENT_FACTORY", lambda: f)
    monkeypatch.setenv(rm.OFF_ENV, "1")              # the test runners turn remembering off
    yield f


def _remember_three():
    import time
    clock = {"t": time.time() - 100.0}
    real = rm._now
    try:
        for c in (20.5, 21.5, 22.5):
            clock["t"] += 1
            rm._now = (lambda v=clock["t"]: v)
            rm.remember("deployment_summary", "u1", {"ParticipantId": "u1", "CenterHz": c})
    finally:
        rm._now = real


def test_unchanged_data_replays_nothing_changed_data_replays_each_once_newest_first(fake):
    _remember_three()
    ran = []

    def run(rows, workers):
        ran.append([r["body"]["CenterHz"] for r in rows])
        return [{"kind": r["kind"], "ok": True} for r in rows]
    first = job.refresh_participant("u1", stamp={"d": 1}, run=run)
    again = job.refresh_participant("u1", stamp={"d": 1}, run=run)
    moved = job.refresh_participant("u1", stamp={"d": 2}, run=run)
    assert ran == [[22.5, 21.5, 20.5], [22.5, 21.5, 20.5]]
    assert (first["replayed"], again["replayed"], moved["replayed"]) == (3, 0, 3)
    assert again["skipped"] == "data unchanged"


def test_one_failure_does_not_stop_the_rest(fake, monkeypatch):
    _remember_three()
    seen = []

    def fn(body):
        seen.append(body["CenterHz"])
        if body["CenterHz"] == 21.5:
            raise RuntimeError("boom")
        return {"available": True, "saved_answer": {"served": False}}
    monkeypatch.setattr(job, "_function_for", lambda kind: fn)
    out = job.refresh_participant("u1", stamp={"d": 1}, run=job._run_here)
    assert seen == [22.5, 21.5, 20.5]
    assert out["replayed"] == 3 and out["failed"] == 1 and out["built"] == 2


def test_replays_are_not_remembered(fake, monkeypatch):
    monkeypatch.setenv(rm.OFF_ENV, "0")
    assert rm.remember("deployment_summary", "u1", {"ParticipantId": "u1"}) is False
    assert rm.recent("u1") == []


def test_each_kind_is_answered_by_its_pages_function():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "BRAVO.settings")
    import django
    django.setup()
    from modules.Biomarkers import bravo_service as bs
    from modules.ClosedLoopDeployment import bravo_service as cs
    assert job._function_for("deployment_summary") is bs.deployment_summary
    assert job._function_for("deployment_roc") is bs.band_deployment_roc
    assert job._function_for("deployment_roc_by_era") is bs.band_deployment_roc_by_era
    assert job._function_for("band_lsb_power") is bs.band_lsb_and_power
    assert job._function_for(cs.REPORT_KIND) is cs.run_for_participant
    assert set(job.KINDS) == {"deployment_summary", "deployment_roc", "deployment_roc_by_era",
                              "band_lsb_power", cs.REPORT_KIND}


def test_workers_are_capped_at_eight_and_by_free_memory():
    assert job.worker_count(20, available_gb=200) == 8
    assert job.worker_count(8, available_gb=13) == 2
    assert job.worker_count(8, available_gb=1) == 1


def test_the_server_starts_the_loop():
    here = os.path.dirname(os.path.abspath(__file__))
    bridge = os.path.join(here, "..", "..", "..", "_agent_bridge")
    boot = open(os.path.join(bridge, "boot.sh")).read()
    assert "saved_answers_refresh_loop.sh" in boot
    # Jetstream2 starts gunicorn directly (its compose command, not boot.sh): gunicorn's start-up
    # hook launches the loop there; the loop's pid lock keeps it to one where both run
    conf = open(os.path.join(bridge, "..", "gunicorn.conf.py")).read()
    hook = conf.split("def when_ready(server):", 1)[1]
    assert "saved_answers_refresh_loop.sh" in hook and "SAVED_ANSWERS_REFRESH" in hook
    loop = open(os.path.join(bridge, "saved_answers_refresh_loop.sh")).read()
    assert "SAVED_ANSWERS_REFRESH" in loop
    # as a module from the code root: run by its path, the job's folder comes first on Python's
    # path and its `types.py` hides the standard library's (every pass failed at import, 2026-10-04)
    assert "-m modules.ClosedLoopDeployment.refresh_saved_answers" in loop
    assert "modules/ClosedLoopDeployment/refresh_saved_answers.py" not in loop


def test_gunicorn_also_starts_the_daily_loop():
    """The daily pass (every pain score's heat maps, the stability column, the clinic-sheet sync)
    was started only by boot.sh, which Jetstream2 never runs (the PI, 2026-10-04: "yes")."""
    here = os.path.dirname(os.path.abspath(__file__))
    conf = open(os.path.join(here, "..", "..", "..", "gunicorn.conf.py")).read()
    hook = conf.split("def when_ready(server):", 1)[1].split("\ndef ", 1)[0]
    assert "stability_precompute_loop.sh" in hook and "STABILITY_PRECOMPUTE" in hook


def test_a_replay_that_starts_the_helper_process_still_ends():
    """A replay whose work starts the stability model's helper process (decision 427) must end.
    Python waits for a replay process's children before it runs the code that stops them, so an
    unstopped helper held the replay, and the whole pass, for 6.5 hours (2026-10-05, 15:10 UTC on)."""
    import subprocess
    import sys
    import tempfile
    import textwrap
    modules_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    script = os.path.join(tempfile.mkdtemp(), "replay_with_helper.py")
    with open(script, "w") as fh:
        fh.write(textwrap.dedent(f"""
            import sys
            sys.path.insert(0, {os.path.dirname(modules_dir)!r})
            sys.path.insert(1, {modules_dir!r})
            from modules.ClosedLoopDeployment import refresh_saved_answers as job
            import importlib

            def uses_helper(kind, body):          # the helper module, under the name in `kind`
                SP = importlib.import_module(kind)
                return {{"kind": kind, "ok": True, "value": SP.submit(sorted, [2, 1]).result(timeout=60)}}

            if __name__ == "__main__":
                rows = [{{"kind": n, "body": {{}}}} for n in ("modules.DecodeCommon.side_process",
                                                          "DecodeCommon.side_process")]
                print(job._run_in_processes(rows, 1, replay=uses_helper))
        """))
    out = subprocess.run([sys.executable, "-B", script], capture_output=True, text=True, timeout=120)
    assert out.stdout.count("'value': [1, 2]") == 2, out.stderr[-2000:]


# ---- every band, registered with the job (the PI, 2026-10-06; decision 463) ----
def _plan():
    bands = []
    for c in (23.5, 24.5):
        bands.append({"channel": "ONE_THREE_LEFT", "centre": c,
                      "report": {"ParticipantId": "u1", "Candidates": [{"center_hz": c}]},
                      "summary": {"ParticipantId": "u1", "CenterHz": c},
                      "roc": {"ParticipantId": "u1", "CenterHz": c, "MatchDirection": "prior"},
                      "era": {"ParticipantId": "u1", "CenterHz": c, "Era": 1},
                      "lsb_template": {"ParticipantId": "u1", "CenterHz": c, "Cutpoint": None}})
    return {"bands": bands, "settings_source": "page"}


def test_a_registered_participant_gets_every_band_replayed_after_its_remembered_requests(fake):
    from modules.ClosedLoopDeployment import all_band_requests as A
    rm.remember("deployment_summary", "u1", {"ParticipantId": "u1", "CenterHz": 24.5})   # already sent by a page
    A.register("u1")
    batches = []

    def run(rows, workers):
        batches.append([(r["kind"], r["body"].get("CenterHz") or r["body"].get("roc", {}).get("CenterHz")
                         or r["body"]["Candidates"][0]["center_hz"]) for r in rows])
        return [{"kind": r["kind"], "ok": True, "served": False} for r in rows]
    out = job.refresh_participant("u1", stamp={"d": 1}, run=run, plan=lambda uid: _plan())
    assert batches[0] == [("deployment_summary", 24.5)]
    assert sorted(batches[1]) == sorted([("closed_loop_report", 23.5), ("deployment_summary", 23.5),
                                         ("deployment_roc", 23.5), ("deployment_roc_by_era", 23.5),
                                         ("closed_loop_report", 24.5),
                                         ("deployment_roc", 24.5), ("deployment_roc_by_era", 24.5)])
    assert batches[2] == [(A.LSB_FROM_ROC_KIND, 23.5), (A.LSB_FROM_ROC_KIND, 24.5)]
    assert out["all_bands"]["bands"] == 2 and out["all_bands"]["settings_source"] == "page"


def test_an_unregistered_participant_gets_no_band_beyond_what_its_pages_sent(fake):
    _remember_three()
    asked = []
    job.refresh_participant("u1", stamp={"d": 1}, run=lambda rows, w: [{"ok": True} for r in rows],
                            plan=lambda uid: asked.append(uid) or _plan())
    assert asked == []


def test_registration_is_kept_and_can_be_undone(fake):
    from modules.ClosedLoopDeployment import all_band_requests as A
    assert not A.registered("u2")
    A.register("u2")
    assert A.registered("u2") and "u2" in A.registered_participants()
    A.unregister("u2")
    assert not A.registered("u2")


def test_band_power_is_asked_at_the_bands_own_roc_cut_point(monkeypatch):
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "BRAVO.settings")
    import django
    django.setup()
    from modules.ClosedLoopDeployment import all_band_requests as A
    from modules.Biomarkers import bravo_service as bs
    got = {}
    monkeypatch.setattr(bs, "band_deployment_roc", lambda rd: {"available": True, "roc": {
        "available": True, "operating_points": {"youden": {"threshold": 0.25}}}})
    monkeypatch.setattr(bs, "band_lsb_and_power", lambda rd: got.setdefault("body", rd) and {"available": True})
    A.replay_lsb_from_roc({"roc": {"CenterHz": 24.5}, "lsb_template": {"CenterHz": 24.5, "Cutpoint": None}})
    assert got["body"]["Cutpoint"] == 0.25
    monkeypatch.setattr(bs, "band_deployment_roc", lambda rd: {"available": False})
    out = A.replay_lsb_from_roc({"roc": {"CenterHz": 24.5}, "lsb_template": {"CenterHz": 24.5}})
    assert out["available"] is False and "no cut-point" in out["reason"]


def test_a_pass_may_run_an_hour():
    src = open(os.path.join(os.path.dirname(job.__file__), "..", "..", "_agent_bridge",
                            "saved_answers_refresh_loop.sh")).read()
    assert 'PASS_LIMIT="${SAVED_ANSWERS_REFRESH_PASS_LIMIT_SECONDS:-3600}"' in src
