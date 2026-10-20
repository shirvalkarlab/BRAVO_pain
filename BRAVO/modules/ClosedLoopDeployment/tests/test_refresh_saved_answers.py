"""The server works the remembered band answers out again when a participant's data change (the PI,
2026-10-04: "yes do 3b", decision 435): after an ingest, a new or corrected pain report, new clinic
sheets, new settings files or new code. Every 10 minutes it compares each participant's data
fingerprint with the one it last worked under; if it moved, it replays the remembered requests
(`CacheStore.request_memory`), newest first, at most 32 at once.

Values: unchanged data replays nothing; changed data replays every remembered request once, newest
first, and then counts as current; one failing request does not stop the rest; the replays are
not themselves remembered; each kind is answered by its page's own function."""
import os
from pathlib import Path

import pytest

from modules.CacheStore import locks, request_memory as rm
from modules.CacheStore.tests.test_request_memory import FakeRedis
from modules.ClosedLoopDeployment import refresh_saved_answers as job


def stand_in_biomarkers(monkeypatch, **attrs):
    """A stand-in for the Biomarkers page module, under both of its import names, for this test only.
    The real one needs the server's Django settings, MySQL driver and data folder, which the CI runner
    has none of (decision 476); these tests check the rebuild's wiring and replace the Biomarkers
    functions they reach anyway. Returns the stand-in."""
    import importlib
    import sys
    import types
    stub = types.ModuleType("modules.Biomarkers.bravo_service")
    for k, v in attrs.items():
        setattr(stub, k, v)
    for pkg in ("modules.Biomarkers", "Biomarkers"):
        monkeypatch.setitem(sys.modules, pkg + ".bravo_service", stub)
        monkeypatch.setattr(importlib.import_module(pkg), "bravo_service", stub, raising=False)
    return stub


@pytest.fixture
def fake(monkeypatch):
    f = FakeRedis()
    # main() sets this default; restore it after each orchestration test.
    monkeypatch.setenv("BRAVO_POOL_JOBS", os.environ.get("BRAVO_POOL_JOBS", "3"))
    monkeypatch.setattr(locks, "CLIENT_FACTORY", lambda: f)
    monkeypatch.setenv(rm.OFF_ENV, "1")              # the test runners turn remembering off
    monkeypatch.setattr(job, "_heat_maps", lambda uid: {"built": 0, "current": 0, "failed": 0})   # no real rebuild
    monkeypatch.setattr(job, "_run_command", lambda name, uid, limit: {"built": 0, "current": 0, "failed": 0})
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
    """Each remembered kind is replayed through the function the page itself calls. Read from the
    two modules' source, so it needs no server settings (decision 476)."""
    import ast
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    def defined(module):
        path = os.path.join(here, *module.split(".")[1:]) + ".py"
        return {n.name for n in ast.parse(open(path).read()).body if isinstance(n, ast.FunctionDef)}

    assert job.KINDS == {
        "deployment_summary": ("modules.Biomarkers.bravo_service", "deployment_summary"),
        "deployment_roc": ("modules.Biomarkers.bravo_service", "band_deployment_roc"),
        "deployment_roc_by_era": ("modules.Biomarkers.bravo_service", "band_deployment_roc_by_era"),
        "band_lsb_power": ("modules.Biomarkers.bravo_service", "band_lsb_and_power"),
        "closed_loop_report": ("modules.ClosedLoopDeployment.bravo_service", "run_for_participant"),
    }
    for module, name in job.KINDS.values():
        assert name in defined(module), (module, name)
    cl_src = open(os.path.join(here, "ClosedLoopDeployment", "bravo_service.py")).read()
    assert 'REPORT_KIND = "closed_loop_report"' in cl_src


def test_workers_are_capped_at_32_and_by_the_memory_left_under_nine_tenths():
    """Decision 476: one per core at most (the PI, 2026-10-16: 32 workers); a replay process peaks
    at about 5.4 GB in a full pass with its share of the cores as pool workers (measured 2026-10-16:
    16 at once reached 94 %), budgeted 6. The PI, 2026-10-14: 75 % is an alarm with room
    above it, not a ceiling; use the machine."""
    assert job.MAX_WORKERS == 32 and job.GB_PER_WORKER == 6.0
    assert job.worker_count(40, headroom_gb=300) == 32
    assert job.worker_count(32, headroom_gb=80) == 13
    assert job.worker_count(32, headroom_gb=1) == 1
    assert job.worker_count(32, headroom_gb=-5) == 1
    assert job._headroom_gb({"MemTotal": 122 * 2**20, "MemAvailable": 60 * 2**20}) == 60 - (1 - 0.9) * 122


def test_the_deployment_does_not_automatically_start_refresh():
    import runpy
    root = Path(__file__).resolve().parents[4]
    conf = runpy.run_path(str(root / "deploy" / "gunicorn.conf.py"))
    assert "when_ready" not in conf
    assert 'SAVED_ANSWERS_REFRESH: "0"' in (root / "docker-compose.yml").read_text()


def test_gunicorn_keeps_pool_cleanup_without_startup_analysis():
    import runpy
    root = Path(__file__).resolve().parents[4]
    conf = runpy.run_path(str(root / "deploy" / "gunicorn.conf.py"))
    assert callable(conf["post_worker_init"])
    assert callable(conf["worker_exit"])
    assert "warm_up" not in (root / "deploy" / "gunicorn.conf.py").read_text()


def test_startup_leaves_ingestion_and_scheduling_explicit():
    root = Path(__file__).resolve().parents[4]
    entry = (root / "deploy" / "entrypoint.sh").read_text()
    assert "collectstatic" in entry and "exec gunicorn" in entry
    for command in ("daily_ingest", "ingest_new_exports", "sync_clinic_sheets", "crontab", "refresh_saved_answers"):
        assert command not in entry


def test_the_spare_cores_are_shared_out_as_pool_workers_and_set_outright():
    """Decision 476: the container sets BRAVO_POOL_JOBS=16, which a setdefault left in force (up to
    16 helpers in each replay process); the pass now sets cores // replays outright."""
    assert job.pool_jobs_per_replay(11, cores=32) == 2
    assert job.pool_jobs_per_replay(32, cores=32) == 1
    assert job.pool_jobs_per_replay(40, cores=32) == 1
    assert job.pool_jobs_per_replay(1, cores=32) == 32
    import inspect
    src = inspect.getsource(job.workers_now)
    assert 'os.environ["BRAVO_POOL_JOBS"] = str(pool_jobs_per_replay(n))' in src
    assert 'setdefault("BRAVO_POOL_JOBS"' not in inspect.getsource(job)


def test_workers_are_counted_after_the_heat_maps_just_before_the_replays(fake, monkeypatch):
    """Decision 476: the 07:23 UTC pass of 2026-10-16 counted the free memory when it started, while
    memory was briefly high, and ran on 8 replays where 13 fitted a minute later."""
    events = []
    monkeypatch.setenv("BRAVO_POOL_JOBS", os.environ.get("BRAVO_POOL_JOBS", "1"))
    monkeypatch.setattr(job, "worker_count", lambda req: events.append(("count", req)) or 5)
    monkeypatch.setattr(job, "_heat_maps", lambda uid: events.append("heat") or {})
    monkeypatch.setattr(job, "_other_products", lambda uid: events.append("others") or {})
    monkeypatch.setattr(job, "_run_in_pool", lambda rows, w: events.append(("replays", w)) or [])
    rm.remember("deployment_summary", "u1", {"ParticipantId": "u1", "CenterHz": 24.5})
    out = job.refresh_participant("u1", workers=32, stamp=_stamp())
    assert events == ["heat", "others", ("count", 32), ("replays", 5)], events
    assert out["workers"] == 5 and os.environ["BRAVO_POOL_JOBS"] == str(job.pool_jobs_per_replay(5))
    src = __import__("inspect").getsource(job.main)
    assert "worker_count(" not in src and "refresh_participant(uid, workers=n" in src




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
    from modules.ClosedLoopDeployment import all_band_requests as A
    bs = stand_in_biomarkers(monkeypatch, band_deployment_roc=None, band_lsb_and_power=None)
    got = {}
    monkeypatch.setattr(bs, "band_deployment_roc", lambda rd: {"available": True, "roc": {
        "available": True, "operating_points": {"youden": {"threshold": 0.25}}}})
    monkeypatch.setattr(bs, "band_lsb_and_power", lambda rd: got.setdefault("body", rd) and {"available": True})
    A.replay_lsb_from_roc({"roc": {"CenterHz": 24.5}, "lsb_template": {"CenterHz": 24.5, "Cutpoint": None}})
    assert got["body"]["Cutpoint"] == 0.25
    monkeypatch.setattr(bs, "band_deployment_roc", lambda rd: {"available": False})
    out = A.replay_lsb_from_roc({"roc": {"CenterHz": 24.5}, "lsb_template": {"CenterHz": 24.5}})
    assert out["available"] is False and "no cut-point" in out["reason"]


def test_an_explicit_refresh_pass_has_a_one_hour_default_limit():
    root = Path(__file__).resolve().parents[4]
    script = (root / "deploy" / "refresh-saved-answers.sh").read_text()
    assert "SAVED_ANSWERS_REFRESH_PASS_LIMIT_SECONDS:-3600" in script
    assert "--signal=TERM" in script and "--kill-after=10s" in script
    assert "-m modules.ClosedLoopDeployment.refresh_saved_answers" in script


def test_memory_fraction_uses_available_bytes_on_every_platform(monkeypatch):
    import psutil
    from types import SimpleNamespace
    monkeypatch.setattr(psutil, "virtual_memory", lambda: SimpleNamespace(total=10 * 2**30, available=4 * 2**30))
    assert job._used_fraction() == pytest.approx(0.6)
    assert job._headroom_gb() == pytest.approx(3.0)


def test_group_cleanup_never_targets_kernel_self_or_other_groups(monkeypatch):
    import psutil
    import signal
    handlers, killed, exits = [], [], []
    monkeypatch.setattr(os, "setpgrp", lambda: None)
    monkeypatch.setattr(os, "getpid", lambda: 100)
    monkeypatch.setattr(os, "getpgrp", lambda: 42)
    monkeypatch.setattr(psutil, "pids", lambda: [0, 100, 101, 102, 103])
    def group(pid):
        if pid == 103:
            raise ProcessLookupError()
        return 42 if pid == 101 else 99
    monkeypatch.setattr(os, "getpgid", group)
    monkeypatch.setattr(os, "kill", lambda pid, sig: killed.append((pid, sig)))
    monkeypatch.setattr(os, "_exit", lambda status: exits.append(status))
    monkeypatch.setattr(signal, "signal", lambda sig, handler: handlers.append(handler))
    job._own_process_group()
    handlers[0](signal.SIGTERM, None)
    assert killed == [(101, signal.SIGKILL)]
    assert exits == [143]
    assert handlers[1] == signal.SIG_IGN


def test_unavailable_process_group_does_not_install_a_signal_handler(monkeypatch):
    import signal
    def unavailable():
        raise OSError("synthetic unsupported group")
    monkeypatch.setattr(os, "setpgrp", unavailable)
    monkeypatch.setattr(signal, "signal", lambda *args: pytest.fail("no group was established"))
    assert job._own_process_group() is None


def test_replay_pool_recycles_between_completed_chunks_and_keeps_order(monkeypatch):
    from concurrent.futures import Future
    import concurrent.futures
    from collections import Counter
    generations, sent = [], []
    class Executor:
        def __init__(self, **kwargs):
            assert "max_tasks_per_child" not in kwargs
            self.index = len(generations)
            self.workers = kwargs["max_workers"]
            self.count = 0
            self.closed = False
            generations.append(self)
        def submit(self, wrapper, replay, kind, body):
            assert not self.closed
            pid = 1000 + 10 * self.index + self.count % self.workers
            self.count += 1
            sent.append((pid, body["value"]))
            future = Future()
            future.set_result((pid, replay(kind, body)))
            return future
        def shutdown(self, **kwargs):
            self.closed = True
    monkeypatch.setattr(concurrent.futures, "ProcessPoolExecutor", Executor)
    monkeypatch.setattr(job, "_used_fraction", lambda: 0.2)
    monkeypatch.setattr(job, "REPLAYS_PER_PROCESS", 5)
    job._close_pass_pool()
    rows = [{"kind": "synthetic", "body": {"value": i}} for i in range(17)]
    try:
        got = job._run_in_pool(rows, 2, replay=lambda kind, body: body["value"] * 2)
        assert got == [i * 2 for i in range(17)]
        assert [value for pid, value in sent] == list(range(17))
        assert max(Counter(pid for pid, value in sent).values()) <= 5
        assert len(generations) >= 2
        previous = generations[-1]
        job._pass_pool(1)
        assert previous.closed
    finally:
        job._close_pass_pool()
        job._close_pass_pool()
    assert all(g.closed for g in generations)
    monkeypatch.setattr(os, "getpid", lambda: 123)
    assert job._counted_replay(lambda kind, body: body["value"], "k", {"value": 7}) == (123, 7)


# ---- decision 464: committed band first, a memory check before every batch, one REDCap download ----
def test_the_committed_band_and_its_neighbours_go_first():
    from modules.ClosedLoopDeployment import all_band_requests as A
    bands = [{"channel": ch, "centre": c} for ch in ("ZERO_THREE_LEFT", "ONE_THREE_LEFT") for c in (20.5, 21.5, 22.5, 23.5, 24.5, 25.5, 26.5)]
    got = [(b["channel"], b["centre"]) for b in A.order_committed_first(bands, {"channel": "ONE_THREE_LEFT", "centre": 24.5})]
    assert got[:5] == [("ONE_THREE_LEFT", 24.5), ("ONE_THREE_LEFT", 23.5), ("ONE_THREE_LEFT", 25.5),
                       ("ONE_THREE_LEFT", 22.5), ("ONE_THREE_LEFT", 26.5)]
    assert sorted(got) == sorted((b["channel"], b["centre"]) for b in bands)
    assert A.order_committed_first(bands, None) == bands


def test_memory_is_checked_before_every_batch_and_waits_above_nine_tenths():
    seen, waits = [], []
    mem = iter([0.5, 0.92, 0.95, 0.85, 0.5])
    out = job._run_in_batches([{"kind": "k", "body": {"i": i}} for i in range(5)], 2,
                              run=lambda rows, w: seen.append([r["body"]["i"] for r in rows]) or [{"ok": True}] * len(rows),
                              used_fraction=lambda: next(mem), sleep=lambda s: waits.append(s), batch=2)
    assert seen == [[0, 1], [2, 3], [4]]
    assert len(out) == 5 and len(waits) == 2               # waited while 92% and then 95% was used; 85% goes on


def test_above_nine_tenths_the_pass_closes_its_processes_before_it_waits():
    """Decision 474 (2026-10-14, 101 of 122 GB): with one set of processes for the whole pass,
    waiting freed nothing, because the processes kept their memory; they are closed first."""
    events = []
    mem = iter([0.5, 0.92, 0.6, 0.5])
    job._run_in_batches([{"kind": "k", "body": {"i": i}} for i in range(3)], 1,
                        run=lambda rows, w: events.append("batch") or [{"ok": True}] * len(rows),
                        used_fraction=lambda: next(mem), sleep=lambda s: events.append("wait"), batch=1,
                        before_wait=lambda: events.append("close"))
    assert events == ["batch", "close", "wait", "batch", "batch"]


def test_a_replay_process_is_replaced_often_and_keeps_few_preparations():
    """How few preparations each keeps is checked beside the memo, in the Biomarkers tests."""
    assert job.REPLAYS_PER_PROCESS <= 20
    import inspect
    assert "before_wait=_close_pass_pool" in inspect.getsource(job._run_in_pool)


def test_a_pass_shares_one_redcap_download_and_cleans_up(fake, monkeypatch):
    from modules.Biomarkers.routines import redcap_client as rc
    _remember_three()
    dirs = []

    def run(rows, workers):
        d = os.environ.get(rc.PASS_DIR_ENV)
        dirs.append(d and os.path.isdir(d))
        return [{"kind": r["kind"], "ok": True} for r in rows]
    job.refresh_participant("u1", stamp={"d": 1}, run=run)
    assert dirs == [True] and not os.environ.get(rc.PASS_DIR_ENV)


def test_a_silent_redcap_skips_the_pass(fake, monkeypatch):
    from modules.Biomarkers.routines import redcap_client as rc

    def boom(uid):
        raise rc.RedcapUnavailable("REDCap did not answer within 20 s")
    monkeypatch.setattr(job, "data_stamp", boom)
    out = job.refresh_participant("u1")
    assert out["skipped"].startswith("REDCap not answering")


def test_heat_maps_are_rebuilt_first_when_the_data_changed_and_not_otherwise(fake):
    _remember_three()
    order = []
    run = lambda rows, w: order.append("replays") or [{"kind": r["kind"], "ok": True} for r in rows]
    heat = lambda uid: order.append("heat maps") or {"built": 6, "current": 0, "failed": 0}
    first = job.refresh_participant("u1", stamp={"d": 1}, run=run, heat_maps=heat)
    again = job.refresh_participant("u1", stamp={"d": 1}, run=run, heat_maps=heat)
    assert order == ["heat maps", "replays"]
    assert first["heat_maps"]["built"] == 6 and "heat_maps" not in again


def test_stability_and_session_summary_follow_the_heat_maps_before_the_replays(fake, monkeypatch):
    """Decision 473: the daily pass's two other products are rebuilt in the same pass, when the data
    changed: the stability column reads the heat maps' grids, and the Closed-Loop report (a replay)
    reads the session-report summary."""
    _remember_three()
    order = []
    monkeypatch.setattr(job, "_run_command", lambda name, uid, limit: order.append(name)
                        or {"built": 1, "current": 0, "failed": 0, "seconds": 0.0})
    monkeypatch.setattr(job, "_heat_maps", lambda uid: job._run_command("precompute_band_sweeps", uid, 1))
    run = lambda rows, w: order.append("replays") or [{"kind": r["kind"], "ok": True} for r in rows]
    first = job.refresh_participant("u1", stamp={"d": 1}, run=run, heat_maps=None)
    job.refresh_participant("u1", stamp={"d": 1}, run=run, heat_maps=None)
    assert order == ["precompute_band_sweeps", "compute_stability_grid",
                     "rebuild_session_report_summary", "replays"]
    assert first["stability"]["built"] == 1 and first["session_summary"]["built"] == 1


def test_a_pass_waits_while_an_ingest_is_writing(fake, monkeypatch, tmp_path, capsys):
    """The daily ingest (`_agent_bridge/daily_ingest.sh`) leaves a note while it writes; a pass that
    started then would rebuild on half the new exports and again on all of them 10 minutes later."""
    note = tmp_path / ".ingest_running"
    monkeypatch.setattr(job, "INGEST_NOTE", str(note))
    # main() sets these two for the replay processes it starts; put back after this test (decision
    # 476: left set, the pool size leaked into the Stim Optimizer tests run after it)
    monkeypatch.setenv("BRAVO_POOL_JOBS", os.environ.get("BRAVO_POOL_JOBS", "1"))
    monkeypatch.setenv(rm.OFF_ENV, os.environ.get(rm.OFF_ENV, "0"))
    seen = []
    monkeypatch.setattr(job, "refresh_participant", lambda uid, **k: seen.append(uid) or {"participant": uid})
    note.write_text("")
    assert job.main(["--participant", "u1"]) == 0
    assert seen == [] and '"skipped": "ingest running"' in capsys.readouterr().out
    os.utime(note, (0, 0))                                   # a note left by a crashed ingest is ignored
    assert job.main(["--participant", "u1"]) == 0 and seen == ["u1"]
    note.unlink()
    assert job.main(["--participant", "u1"]) == 0 and seen == ["u1", "u1"]


# ---- decision 474: a new pain rating rebuilds what the pages asked for, not every band ----
def _stamp(**over):
    s = {"recordings": "r1", "settings_files": "f1", "pain_reports": "p1", "clinic_sheets": "c1", "code": "k1"}
    s.update(over)
    return s


def _band_run(seen):
    def run(rows, workers):
        seen.extend(r["kind"] for r in rows)
        return [{"kind": r["kind"], "ok": True, "served": False} for r in rows]
    return run


def test_only_new_ratings_rebuild_the_pages_answers_but_not_every_band(fake, monkeypatch):
    from modules.ClosedLoopDeployment import all_band_requests as A
    rm.remember("deployment_summary", "u1", {"ParticipantId": "u1", "CenterHz": 24.5})
    A.register("u1")
    clock = {"t": 1000.0}
    monkeypatch.setattr(job, "_now", lambda: clock["t"])
    seen = []
    job.refresh_participant("u1", stamp=_stamp(), run=_band_run(seen), plan=lambda uid: _plan())
    assert seen.count(A.LSB_FROM_ROC_KIND) == 2                       # first pass: every band
    for change in ({"pain_reports": "p2"}, {"clinic_sheets": "c2"}):
        seen.clear()
        clock["t"] += 600
        out = job.refresh_participant("u1", stamp=_stamp(**change), run=_band_run(seen), plan=lambda uid: _plan())
        assert seen == ["deployment_summary"], change                 # the page's answer only
        assert out["all_bands"]["skipped"].startswith("only pain ratings or clinic sheets changed")
    for change in ({"recordings": "r2"}, {"settings_files": "f2"}, {"code": "k2"}):
        seen.clear()
        clock["t"] += 600
        job.refresh_participant("u1", stamp=_stamp(**change), run=_band_run(seen), plan=lambda uid: _plan())
        assert seen.count(A.LSB_FROM_ROC_KIND) == 2, change          # new recordings, settings, code


def test_every_band_catches_up_within_a_day_even_with_no_further_change(fake, monkeypatch):
    from modules.ClosedLoopDeployment import all_band_requests as A
    A.register("u1")
    clock = {"t": 1000.0}
    monkeypatch.setattr(job, "_now", lambda: clock["t"])
    seen = []
    job.refresh_participant("u1", stamp=_stamp(), run=_band_run(seen), plan=lambda uid: _plan())
    clock["t"] += 600
    job.refresh_participant("u1", stamp=_stamp(pain_reports="p2"), run=_band_run(seen), plan=lambda uid: _plan())
    seen.clear()
    clock["t"] += 3600                                                 # same data, under a day: nothing
    out = job.refresh_participant("u1", stamp=_stamp(pain_reports="p2"), run=_band_run(seen), plan=lambda uid: _plan())
    assert seen == [] and out["skipped"] == "data unchanged"
    clock["t"] = 1000.0 + job.BAND_CATCH_UP_SECONDS + 1                 # a day after the last every-band run
    out = job.refresh_participant("u1", stamp=_stamp(pain_reports="p2"), run=_band_run(seen), plan=lambda uid: _plan())
    assert seen.count(A.LSB_FROM_ROC_KIND) == 2 and out["all_bands"]["bands"] == 2
    seen.clear()
    clock["t"] += 600                                                  # caught up: quiet again
    assert job.refresh_participant("u1", stamp=_stamp(pain_reports="p2"), run=_band_run(seen),
                                   plan=lambda uid: _plan())["skipped"] == "data unchanged" and seen == []


def test_one_set_of_replay_processes_serves_the_whole_pass_and_ends_with_it():
    """Decision 474: the same processes across batches (a fresh set per batch of 24 restarted R and
    emptied every in-process store about 40 times a pass), replaced after REPLAYS_PER_PROCESS, and
    closed when the pass ends, helper processes included (the 6.5-hour hang of 2026-10-05)."""
    import subprocess
    import sys
    import tempfile
    import textwrap
    modules_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    script = os.path.join(tempfile.mkdtemp(), "pass_pool.py")
    with open(script, "w") as fh:
        fh.write(textwrap.dedent(f"""
            import os, sys, importlib
            sys.path.insert(0, {os.path.dirname(modules_dir)!r})
            sys.path.insert(1, {modules_dir!r})
            from modules.ClosedLoopDeployment import refresh_saved_answers as job

            def pid_and_helper(kind, body):
                SP = importlib.import_module("modules.DecodeCommon.side_process")
                return {{"ok": True, "pid": os.getpid(), "value": SP.submit(sorted, [2, 1]).result(timeout=60)}}

            if __name__ == "__main__":
                job.REPLAYS_PER_PROCESS = 5
                rows = [{{"kind": "k", "body": {{"i": i}}}} for i in range(14)]     # 3 batches of 6
                out = job._run_in_pool(rows, 2, replay=pid_and_helper)
                job._close_pass_pool()
                from collections import Counter
                counts = Counter(r["pid"] for r in out)
                print("values", sum(r["value"] == [1, 2] for r in out), "pids", len(counts), "max_tasks", max(counts.values()))
        """))
    out = subprocess.run([sys.executable, "-B", script], capture_output=True, text=True, timeout=180)
    # 14 replays, 5 per process at most. Whole pool generations retire only
    # with no pending futures, avoiding Python 3.12 worker-recycling deadlock.
    line = [l for l in out.stdout.splitlines() if l.startswith("values")]
    assert line, out.stderr[-2000:]
    _, n_ok, _, n_pids, _, max_tasks = line[0].split()
    assert int(n_ok) == 14 and 3 <= int(n_pids) <= 6, line
    assert int(max_tasks) <= 5, line


def test_many_quick_replays_never_leave_the_pass_waiting_on_no_processes():
    """2026-10-16, twice: a full pass waited 12 minutes with no replay process alive. Python 3.12.3's
    pool, told to replace each process after a number of tasks (`max_tasks_per_child`), skips the
    replacement while it counts a process as idle that has already taken the next task; once every
    process has gone, the queued replays wait for ever (CPython gh-115634, fixed in later 3.12).
    The pass now starts a fresh set itself after workers x REPLAYS_PER_PROCESS replays."""
    import subprocess
    import sys
    import tempfile
    import textwrap
    modules_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    script = os.path.join(tempfile.mkdtemp(), "many_replays.py")
    with open(script, "w") as fh:
        fh.write(textwrap.dedent(f"""
            import os, sys
            sys.path.insert(0, {os.path.dirname(modules_dir)!r})
            sys.path.insert(1, {modules_dir!r})
            from modules.ClosedLoopDeployment import refresh_saved_answers as job

            def quick(kind, body):
                return {{"ok": True, "pid": os.getpid()}}

            if __name__ == "__main__":
                job.REPLAYS_PER_PROCESS = 2
                rows = [{{"kind": "k", "body": {{"i": i}}}} for i in range(60)]
                out = job._run_in_pool(rows, 4, replay=quick)
                job._close_pass_pool()
                print("done", sum(r["ok"] for r in out), "pids", len({{r["pid"] for r in out}}))
        """))
    try:
        out = subprocess.run([sys.executable, "-B", script], capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        raise AssertionError("60 quick replays did not finish in 120 s: the pool was left with no processes")
    line = [l for l in out.stdout.splitlines() if l.startswith("done")]
    assert line, out.stderr[-2000:]
    _, n_ok, _, n_pids = line[0].split()
    assert int(n_ok) == 60, line
    # each batch of 12 (3 per worker) is more than 4 x 2, so every batch gets a fresh set: 5 sets.
    # Quick replays can all land on a set's first process, so at least 5 processes, not 4 x 5.
    assert int(n_pids) >= 5, line


def test_a_stopped_pass_takes_every_process_it_started_with_it():
    """2026-10-14: a pass stopped by hand left 119 calculation-pool processes behind (their parents,
    the replay processes, were gone); they held the loop's output pipe open and the loop froze. The
    job leads its own process group and, on the stop signal its time limit sends, ends the group."""
    import signal
    import subprocess
    import sys
    import tempfile
    import textwrap
    import time
    modules_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    d = tempfile.mkdtemp()
    script = os.path.join(d, "stopped_pass.py")
    with open(script, "w") as fh:
        fh.write(textwrap.dedent(f"""
            import subprocess, sys, time
            sys.path.insert(0, {os.path.dirname(modules_dir)!r})
            sys.path.insert(1, {modules_dir!r})
            from modules.ClosedLoopDeployment import refresh_saved_answers as job
            job._own_process_group()
            # a grandchild that outlives its parent, as an orphaned pool process does
            subprocess.Popen([sys.executable, "-c",
                "import subprocess, sys; p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)']);"
                " open({os.path.join(d, 'gc.pid')!r}, 'w').write(str(p.pid))"])
            time.sleep(120)
        """))
    p = subprocess.Popen([sys.executable, "-B", script])
    pid_file = os.path.join(d, "gc.pid")
    for _ in range(100):
        if os.path.exists(pid_file) and open(pid_file).read():
            break
        time.sleep(0.1)
    gc = int(open(pid_file).read())
    os.kill(p.pid, signal.SIGTERM)
    # 143 (stopped), not 137: the loop reads 137 as its own time limit and logged a 5-minute pass as
    # "still running after the 3600s limit" (2026-10-14)
    assert p.wait(timeout=30) == 143
    for _ in range(50):
        try:
            os.kill(gc, 0)
        except ProcessLookupError:
            break
        import psutil
        try:                                             # unreaped zombies are no longer running
            if psutil.Process(gc).status() == psutil.STATUS_ZOMBIE:
                break
        except psutil.NoSuchProcess:
            break
        time.sleep(0.1)
    else:
        os.kill(gc, signal.SIGKILL)
        raise AssertionError("the orphaned grandchild outlived the stopped pass")
