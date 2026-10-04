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
    assert "SAVED_ANSWERS_REFRESH" in loop and "refresh_saved_answers" in loop
