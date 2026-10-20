"""Work the remembered band answers out again when a participant's data change (the PI, 2026-10-04:
"yes do 3b", decision 435). Run every 10 minutes by `_agent_bridge/saved_answers_refresh_loop.sh`.

WHAT IT DOES. For each participant with remembered requests (`CacheStore.request_memory`: the
summary, the three Closed-Loop panels and the Closed-Loop report, as the pages sent them, including
the requests sent ahead for neighbouring and strongest bands), it builds the participant's data
fingerprint: the recording set, the stimulation-settings files, the pain reports (fetched fresh
from REDCap), the newest clinic sheets and the analysis code. If that differs from the fingerprint
of its last pass, it replays every remembered request, newest first, through the page's own
function, so each answer is saved under its new label before anyone asks. Unchanged data costs one
pain-report download per participant.

LIMITS. At most 32 replays at once, one per core (the PI, 2026-10-16), fewer when memory is short
(one per GB_PER_WORKER left under MEMORY_LIMIT_FRACTION; depending on available memory), and the cores
left shared out as pool workers: each replay process gets cores // replays of them, set outright
(the container's own BRAVO_POOL_JOBS=16 used to win over the 3 meant here, decision 476). The replay
processes
are fresh interpreters that exit if this process dies. A failed replay is logged and the rest go
on; the fingerprint is then recorded, so a request that always fails is retried at the next data
change, not every 10 minutes.

    python3 -m modules.ClosedLoopDeployment.refresh_saved_answers --all [--workers 32] [--force]
"""
import argparse
import json
import os
import sys
import time

KINDS = {
    "deployment_summary": ("modules.Biomarkers.bravo_service", "deployment_summary"),
    "deployment_roc": ("modules.Biomarkers.bravo_service", "band_deployment_roc"),
    "deployment_roc_by_era": ("modules.Biomarkers.bravo_service", "band_deployment_roc_by_era"),
    "band_lsb_power": ("modules.Biomarkers.bravo_service", "band_lsb_and_power"),
    "closed_loop_report": ("modules.ClosedLoopDeployment.bravo_service", "run_for_participant"),
}
#: Kinds only the every-band step sends (decision 463); never in a page's remembered requests.
ALL_BAND_KINDS = {
    "band_lsb_power_from_roc": ("modules.ClosedLoopDeployment.all_band_requests", "replay_lsb_from_roc"),
    "all_band_plan": ("modules.ClosedLoopDeployment.all_band_requests", "plan_for"),
}
MAX_WORKERS = 32
#: A replay process's peak with its share of the cores as pool workers, measured 2026-10-16: 5.4 GB
#: in a full pass (16 at once, 2 pool workers each: 114.7 GB in use, 94 %, so the pass was stopped),
#: 4.4 GB when only the pages' answers are rebuilt (11 at once: 78 GB). With the container's 16
#: pool workers each it was 6.5 GB (13 at once: 112 GB, 92 %). Decision 476.
GB_PER_WORKER = 6.0
STAMP_PREFIX = "bravo:saved_answer_refresh:"
#: Left by `_agent_bridge/daily_ingest.sh` while it writes; a pass then waits for the next one, so an
#: ingest is rebuilt once, on all its exports. A note older than INGEST_NOTE_MAX_SECONDS is ignored.
INGEST_NOTE = "/usr/src/BRAVO/_agent_bridge/.ingest_running"
INGEST_NOTE_MAX_SECONDS = 6 * 3600


def ingest_running():
    try:
        return time.time() - os.path.getmtime(INGEST_NOTE) < INGEST_NOTE_MAX_SECONDS
    except OSError:
        return False


def _function_for(kind):
    import importlib
    mod, name = KINDS[kind] if kind in KINDS else ALL_BAND_KINDS[kind]
    return getattr(importlib.import_module(mod), name)


def workers_now(requested):
    """The replays' worker count from the memory free just before they start, and each replay
    process's share of the cores as pool workers, set outright (the container sets 16). Counted
    here rather than when the pass starts: the 2026-10-16 07:23 UTC pass counted while memory was
    briefly 60 GB in use and ran on 8 where 13 fitted once the heat maps were done (decision 476)."""
    n = worker_count(requested)
    os.environ["BRAVO_POOL_JOBS"] = str(pool_jobs_per_replay(n))
    return n


def pool_jobs_per_replay(workers, cores=None):
    """The pool workers each replay process may start: the cores shared out among the replays."""
    return max(1, int(cores or os.cpu_count() or 2) // max(1, int(workers)))


def _headroom_gb(meminfo_kb=None):
    """Memory left before MEMORY_LIMIT_FRACTION of the machine is in use, in GB."""
    if meminfo_kb is None:
        import psutil
        memory = psutil.virtual_memory()
        meminfo_kb = {"MemTotal": memory.total / 1024, "MemAvailable": memory.available / 1024}
    total = meminfo_kb["MemTotal"] / 1024.0 / 1024.0
    return meminfo_kb["MemAvailable"] / 1024.0 / 1024.0 - (1.0 - MEMORY_LIMIT_FRACTION) * total


def worker_count(requested, headroom_gb=None):
    """At most `MAX_WORKERS`, and one per `GB_PER_WORKER` of the memory left under MEMORY_LIMIT_FRACTION
    of the machine (at least one): a replay process peaks at about 5.4 GB in a full pass (decision 476)."""
    if headroom_gb is None:
        try:
            headroom_gb = _headroom_gb()
        except Exception:                                      # noqa: BLE001
            headroom_gb = GB_PER_WORKER * MAX_WORKERS
    return max(1, min(int(requested), MAX_WORKERS, int(max(0.0, headroom_gb) // GB_PER_WORKER)))


def data_stamp(participant_uid):
    """Everything besides the request that can change a saved band answer, for one participant."""
    from modules.Biomarkers import bravo_service as bs
    from modules.CacheStore import saved_answers
    from modules.StimOptimizer import adapter as so
    from Server import models
    participant = models.Participant.find(uid=participant_uid)
    if not participant:
        return None
    with bs.pro_request_scope():
        pro = bs._load_pros({}, participant)
    sheets = bs._cache_store.newest_stamp(bs.CLINIC_SHEET_STEPS_KIND, str(participant_uid),
                                          root=bs._SHARED_CACHE_DIR_OVERRIDE) or {}
    return {"recordings": repr(bs._recording_set_identity(participant_uid)),
            "settings_files": repr(so.source_file_signature(participant)),
            "pain_reports": bs._pro_table_digest(pro) if pro is not None and len(pro) else "none",
            "clinic_sheets": sheets.get("signature_key"),
            "code": saved_answers.code_digest()}


def _last_stamp(participant_uid):
    from modules.CacheStore import locks
    try:
        client = locks._client()
        raw = client.get(STAMP_PREFIX + str(participant_uid)) if client is not None else None
        return json.loads(raw.decode() if isinstance(raw, bytes) else raw) if raw else None
    except Exception:                                          # noqa: BLE001
        return None


def _save_stamp(participant_uid, stamp):
    from modules.CacheStore import locks
    try:
        client = locks._client()
        if client is not None:
            client.set(STAMP_PREFIX + str(participant_uid), json.dumps(stamp, sort_keys=True))
    except Exception:                                          # noqa: BLE001
        pass


def _replay_one(kind, body):
    t = time.perf_counter()
    try:
        out = _function_for(kind)(dict(body)) or {}
        saved = out.get("saved_answer") or {}
        return {"kind": kind, "ok": True, "available": out.get("available"),
                "served": bool(saved.get("served")), "seconds": round(time.perf_counter() - t, 2)}
    except Exception as exc:                                   # noqa: BLE001 -- the rest go on
        return {"kind": kind, "ok": False, "error": f"{type(exc).__name__}: {exc}"[:300],
                "seconds": round(time.perf_counter() - t, 2)}


def _run_here(rows, workers):
    return [_replay_one(r["kind"], r["body"]) for r in rows]


def _replay_process_init(parent_pid, sys_path):
    """Set up one replay process. At its exit Python waits for the process's children BEFORE it runs
    the code that stops them, so a helper (decision 427) or calculation pool left running holds the
    replay, and the whole pass, for ever (6.5 hours on 2026-10-05). Stop them first: a step
    registered here runs ahead of that wait."""
    from multiprocessing import util
    from modules.DecodeCommon import side_process
    side_process._child_init(parent_pid, sys_path)
    os.environ[BAND_SETUP_MEMO_ENV] = "1"                    # this worker keeps the band preparation (decision 474)
    util.Finalize(None, _stop_helpers, exitpriority=100)


def _stop_helpers():
    """Stop the calculation pool and the helper, under each name the helper module was loaded as
    ("DecodeCommon..." and "modules.DecodeCommon..." are two copies, each with its own helper)."""
    from modules.DecodeCommon import parallel
    parallel.shutdown_pool()
    for name, mod in list(sys.modules.items()):
        if name.endswith("DecodeCommon.side_process") and hasattr(mod, "shutdown"):
            mod.shutdown()


#: `Biomarkers.bravo_service.BAND_SETUP_MEMO_ENV`, by name: importing that module here would load
#: the server's Django settings in every replay process before it ran anything, which a process with
#: no server settings (the CI runner) cannot do (decision 476). The Biomarkers tests check the name.
BAND_SETUP_MEMO_ENV = "BRAVO_BAND_SETUP_MEMO"

#: A fresh set of replay processes after at most this many replays per process, so what they
#: keep cannot grow without end. Counted by the pass itself, never Python's `max_tasks_per_child`:
#: Python 3.12.3 then skips replacing a process while it counts one as idle that has already taken
#: the next task, and once every process has gone the queued replays wait for ever (CPython
#: gh-115634; two full passes on 2026-10-16 sat 12 minutes with no process alive). Decision 476.
REPLAYS_PER_PROCESS = 20
_PASS_POOL = {}


def _pass_pool(workers):
    'Reuse replay worker processes for one refresh pass. Participant preparation and in-process stores can be reused across batches. refresh_participant closes the pool at the end of the pass.'
    import multiprocessing
    from concurrent.futures import ProcessPoolExecutor
    if _PASS_POOL.get("workers") != workers:
        _close_pass_pool()
        _PASS_POOL["pool"] = ProcessPoolExecutor(
            max_workers=workers, mp_context=multiprocessing.get_context("spawn"),
            initializer=_replay_process_init, initargs=(os.getpid(), list(sys.path)))
        _PASS_POOL["workers"] = workers
        _PASS_POOL["completed"] = {}
    return _PASS_POOL["pool"]


def _close_pass_pool():
    pool = _PASS_POOL.pop("pool", None)
    _PASS_POOL.pop("workers", None)
    _PASS_POOL.pop("completed", None)
    if pool is not None:
        pool.shutdown(wait=True, cancel_futures=True)


def _counted_replay(replay, kind, body):
    return os.getpid(), replay(kind, body)


def _run_in_pool(rows, workers, replay=_replay_one):
    """`_run_in_batches` over the pass's one set of processes (memory checked before each batch)."""
    def run(batch, w):
        # CPython 3.12's max_tasks_per_child can deadlock while replacing a
        # worker with queued work (python/cpython#115634). Recycle only after
        # all submitted work has completed. A chunk cannot exceed the busiest
        # worker's remaining budget, even if that worker takes the whole chunk.
        pending, results = list(batch), []
        while pending:
            pool = _pass_pool(w)
            counts = _PASS_POOL["completed"]
            remaining = max(1, REPLAYS_PER_PROCESS) - max(counts.values(), default=0)
            if remaining <= 0:
                _close_pass_pool()
                continue
            chunk, pending = pending[:remaining], pending[remaining:]
            futures = [pool.submit(_counted_replay, replay, r["kind"], r["body"]) for r in chunk]
            for future in futures:
                pid, result = future.result()
                counts[pid] = counts.get(pid, 0) + 1
                results.append(result)
        return results
    return _run_in_batches(rows, workers, run, before_wait=_close_pass_pool)


def _run_in_processes(rows, workers, replay=_replay_one):
    import multiprocessing
    from concurrent.futures import ProcessPoolExecutor
    with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn"),
                             initializer=_replay_process_init,
                             initargs=(os.getpid(), list(sys.path))) as ex:
        futures = [ex.submit(replay, r["kind"], r["body"]) for r in rows]
        return [f.result() for f in futures]


def _plan_in_process(participant_uid):
    """`all_band_requests.plan_for` in one replay process (it decodes the recordings), so this loop
    process stays small."""
    import multiprocessing
    from concurrent.futures import ProcessPoolExecutor
    with ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context("spawn"),
                             initializer=_replay_process_init,
                             initargs=(os.getpid(), list(sys.path))) as ex:
        return ex.submit(_plan_call, participant_uid).result()


def _plan_call(participant_uid):
    return _function_for("all_band_plan")(participant_uid)


def _count(results):
    return {"built": sum(1 for r in results if r.get("ok") and not r.get("served")),
            "served": sum(1 for r in results if r.get("ok") and r.get("served")),
            "failed": sum(1 for r in results if not r.get("ok")),
            "errors": [r["error"] for r in results if not r.get("ok")][:5]}


def _all_bands(participant_uid, done_rows, workers, run, plan):
    """EVERY BAND (decision 463): for a registered participant, every band on the band grid as the
    page would ask for it (`all_band_requests`): report, summary, ROC and month-by-month first (those
    this pass already replayed skipped), then band power at each band's own fresh ROC cut-point."""
    p = (plan or _plan_in_process)(participant_uid) or {}
    bands = p.get("bands") or []
    done = {json.dumps([r["kind"], r["body"]], sort_keys=True) for r in done_rows}
    first = []
    for b in bands:
        for kind, field in (("closed_loop_report", "report"), ("deployment_summary", "summary"),
                            ("deployment_roc", "roc"), ("deployment_roc_by_era", "era")):
            row = {"kind": kind, "body": b[field]}
            if json.dumps([kind, b[field]], sort_keys=True) not in done:
                first.append(row)
    lsb = [{"kind": "band_lsb_power_from_roc", "body": {"roc": b["roc"], "lsb_template": b["lsb_template"]}}
           for b in bands]
    r1 = run(first, workers) if first else []
    r2 = run(lsb, workers) if lsb else []
    return {"bands": len(bands), "settings_source": p.get("settings_source"),
            "grid_available": p.get("grid_available", True), **_count(list(r1) + list(r2))}


#: Above this share of memory in use a pass closes its processes and waits before its next batch
#: (decision 464). 90 %, not 75 %: the PI, 2026-10-14, "dont [worry] about staying under the 75%
#: threshold thats why its a threshold ... max out the resources" (decision 474).
MEMORY_LIMIT_FRACTION = 0.90


def _used_fraction():
    import psutil
    memory = psutil.virtual_memory()
    return 1.0 - memory.available / float(memory.total)


def _run_in_batches(rows, workers, run, *, used_fraction=None, sleep=None, batch=None, before_wait=None):
    """`run` over `rows` a batch at a time (3 rows per worker), checking memory before each batch and
    waiting (30 s at a time) while more than `MEMORY_LIMIT_FRACTION` is in use (decision 464). The
    pass's own time limit (the loop's `timeout`) bounds the waiting. `before_wait` runs once before
    a wait: the pass closes its replay processes there, or waiting would free nothing (decision 474)."""
    used_fraction = used_fraction or _used_fraction
    sleep = sleep or time.sleep
    size = max(1, int(batch or workers * 3))
    out = []
    for i in range(0, len(rows), size):
        closed = False
        while used_fraction() > MEMORY_LIMIT_FRACTION:
            if before_wait is not None and not closed:
                before_wait()
                closed = True
            sleep(30)
        out.extend(run(rows[i:i + size], workers))
    return out


#: The heat-map rebuild may evaluate multiple pain scores in one pass.
HEAT_MAP_LIMIT_SECONDS = 1200
#: The two products the daily pass used to build (decision 473), each this long at most.
PRODUCT_LIMIT_SECONDS = 900


def _run_command(name, participant_uid, limit):
    """One of the daily loop's own commands for one participant, in its own process so this one
    stays small; it reads this pass's one REDCap download (the folder is in its environment).
    Counts its JSON lines: stored, already current, failed (a reason and nothing stored)."""
    import subprocess
    manage = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "manage.py")
    try:
        p = subprocess.run([sys.executable, manage, name, "--participant", str(participant_uid), "--json"],
                           capture_output=True, text=True, timeout=limit, cwd=os.path.dirname(manage))
    except subprocess.TimeoutExpired:
        return {"built": 0, "current": 0, "failed": 0, "error": f"stopped after {limit} s"}
    rows = []
    for line in (p.stdout or "").splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return {"built": sum(1 for r in rows if r.get("stored")),
            "current": sum(1 for r in rows if r.get("already_current")),
            "failed": sum(1 for r in rows if not r.get("stored") and not r.get("already_current") and r.get("reason")),
            "seconds": round(sum(float(r.get("wall_seconds") or 0) for r in rows), 1)}


def _heat_maps(participant_uid):
    """THE BIOMARKERS HEAT MAPS, rebuilt when the data changed (decision 464): every pain score's
    grid. The Closed-Loop band grid and the stability column read these saved grids, so they go first."""
    return _run_command("precompute_band_sweeps", participant_uid, HEAT_MAP_LIMIT_SECONDS)


def _other_products(participant_uid):
    """THE STABILITY COLUMN AND THE SESSION-REPORT SUMMARY (decision 473; until then the daily pass's):
    after the heat maps (the stability column reads their grids), before the replays (the Closed-Loop
    report's device rules read the summary)."""
    return {"stability": _run_command("compute_stability_grid", participant_uid, PRODUCT_LIMIT_SECONDS),
            "session_summary": _run_command("rebuild_session_report_summary", participant_uid,
                                            PRODUCT_LIMIT_SECONDS)}


def refresh_participant(participant_uid, *, workers=MAX_WORKERS, force=False, stamp=None, run=None,
                        plan=None, heat_maps=None):
    """Replay the participant's remembered requests if its data changed since the last pass; for a
    registered participant, then every band (`_all_bands`, decision 463)."""
    import shutil
    import tempfile
    from modules.Biomarkers.routines import redcap_client
    from modules.CacheStore import request_memory
    # ONE REDCap DOWNLOAD FOR THE WHOLE PASS (decision 464): the fingerprint's download writes the
    # table into this folder and every replay of the pass reads it; deleted when the pass ends.
    pass_dir = tempfile.mkdtemp(prefix=f"redcap_pass_{participant_uid}_")
    os.environ[redcap_client.PASS_DIR_ENV] = pass_dir
    try:
        return _refresh_participant(participant_uid, workers=workers, force=force, stamp=stamp,
                                    run=run, plan=plan, heat_maps=heat_maps)
    except redcap_client.RedcapUnavailable as exc:
        return {"participant": participant_uid, "skipped": f"REDCap not answering: {exc}", "replayed": 0}
    finally:
        _close_pass_pool()
        os.environ.pop(redcap_client.PASS_DIR_ENV, None)
        shutil.rmtree(pass_dir, ignore_errors=True)


#: The parts of the data stamp that change band power or what a band's answers are built from:
#: a change in any of them rebuilds every band at once (decision 474). A change in the pain ratings or
#: clinic sheets alone rebuilds only what the pages asked for; every band follows within a day.
BAND_STRUCTURAL_KEYS = ("recordings", "settings_files", "code")
BAND_CATCH_UP_SECONDS = 20 * 3600
BAND_STAMP_PREFIX = STAMP_PREFIX + "every_band:"


def _now():
    return time.time()


def _last_band_stamp(participant_uid):
    from modules.CacheStore import locks
    try:
        client = locks._client()
        raw = client.get(BAND_STAMP_PREFIX + str(participant_uid)) if client is not None else None
        return json.loads(raw.decode() if isinstance(raw, bytes) else raw) if raw else None
    except Exception:                                          # noqa: BLE001
        return None


def _save_band_stamp(participant_uid, stamp):
    from modules.CacheStore import locks
    try:
        client = locks._client()
        if client is not None:
            client.set(BAND_STAMP_PREFIX + str(participant_uid),
                       json.dumps({"stamp": stamp, "t": _now()}, sort_keys=True))
    except Exception:                                          # noqa: BLE001
        pass


def bands_due(participant_uid, stamp, force=False):
    """Whether every band is rebuilt in this pass (decision 474): on the first pass, when the
    recordings, settings files or code changed since the last every-band run, or when anything else
    changed and that run is BAND_CATCH_UP_SECONDS old."""
    if force:
        return True
    last = _last_band_stamp(participant_uid)
    if not last:
        return True
    prev = last.get("stamp") or {}
    if any(prev.get(k) != stamp.get(k) for k in BAND_STRUCTURAL_KEYS):
        return True
    return prev != stamp and _now() - float(last.get("t") or 0) >= BAND_CATCH_UP_SECONDS


def _refresh_participant(participant_uid, *, workers, force, stamp, run, plan, heat_maps):
    from modules.CacheStore import request_memory
    from modules.ClosedLoopDeployment import all_band_requests as _abr
    stamp = data_stamp(participant_uid) if stamp is None else stamp
    if stamp is None:
        return {"participant": participant_uid, "skipped": "no such participant", "replayed": 0}
    registered = _abr.registered(participant_uid)
    due = registered and bands_due(participant_uid, stamp, force)
    runner = (lambda rs, w: _run_in_batches(rs, w, run)) if run else \
        (lambda rs, w: _run_in_pool(rs, w))
    if not force and _last_stamp(participant_uid) == stamp:
        if not due:
            return {"participant": participant_uid, "skipped": "data unchanged", "replayed": 0}
        # THE DAILY CATCH-UP: the pages' answers are current, every band is a day behind the ratings
        t = time.perf_counter()
        workers = workers_now(workers) if run is None else workers
        every = _all_bands(participant_uid, [], workers, runner, plan)
        _save_band_stamp(participant_uid, stamp)
        return {"participant": participant_uid, "replayed": 0, "built": 0, "served": 0, "failed": 0,
                "errors": [], "all_bands": every, "seconds": round(time.perf_counter() - t, 1),
                "every_band_catch_up": True, "workers": workers}
    heat = (heat_maps or _heat_maps)(participant_uid)        # first: the band grid reads these
    others = _other_products(participant_uid)
    rows = [r for r in request_memory.recent(participant_uid) if r.get("kind") in KINDS]
    if not rows and not registered:
        _save_stamp(participant_uid, stamp)
        return {"participant": participant_uid, "replayed": 0, "built": 0, "served": 0, "failed": 0,
                "errors": [], "seconds": 0.0, "heat_maps": heat, **others}
    t = time.perf_counter()
    workers = workers_now(workers) if run is None else workers   # after the heat maps, before the replays
    results = runner(rows, workers) if rows else []
    every = None
    if due:
        every = _all_bands(participant_uid, rows, workers, runner, plan)
        _save_band_stamp(participant_uid, stamp)
    elif registered:
        every = {"skipped": "only pain ratings or clinic sheets changed; every band follows within "
                            f"{BAND_CATCH_UP_SECONDS // 3600} h"}
    _save_stamp(participant_uid, stamp)
    out = {"participant": participant_uid, "replayed": len(results), **_count(results), "workers": workers,
           "seconds": round(time.perf_counter() - t, 1)}
    if every is not None:
        out["all_bands"] = every
    out["heat_maps"] = heat
    out.update(others)
    return out


def _own_process_group():
    """Lead a process group and end all of it on SIGTERM (the stop signal the loop's time limit
    sends). 2026-10-14: a stopped pass left 119 calculation-pool processes behind, children of its
    killed replay processes; they held the loop's output pipe and the loop froze, as on 2026-10-05.
    Every process the pass starts inherits the group, so one signal ends them all."""
    import signal
    try:
        os.setpgrp()
    except OSError:
        return

    def stop(signum, frame):
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        me, group = os.getpid(), os.getpgrp()
        import psutil
        for pid in psutil.pids():
            # macOS includes PID 0 (the kernel). kill(0) targets the caller's
            # entire group, including this leader, so it must never be used.
            if pid <= 0 or pid == me:
                continue
            try:
                if os.getpgid(pid) == group:
                    os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
        # 143, "stopped": the loop reads 137 as its own time limit (2026-10-14, a 5-minute pass logged
        # as "still running after the 3600s limit"); its real limit comes back as 124 from `timeout`
        os._exit(143)
    signal.signal(signal.SIGTERM, stop)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--participant", action="append", default=[])
    ap.add_argument("--workers", type=int, default=MAX_WORKERS)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    if ingest_running():
        print(json.dumps({"skipped": "ingest running",
                          "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}), flush=True)
        return 0
    from modules.CacheStore import request_memory
    os.environ[request_memory.OFF_ENV] = "0"                   # the replays are not remembered
    from modules.ClosedLoopDeployment import all_band_requests
    uids = list(a.participant) + (request_memory.participants() + all_band_requests.registered_participants()
                                  if a.all else [])
    n = max(1, min(int(a.workers), MAX_WORKERS))      # the cap; each pass counts the memory itself
    for uid in dict.fromkeys(uids):
        try:
            out = refresh_participant(uid, workers=n, force=a.force)
        except Exception as exc:                               # noqa: BLE001 -- next participant
            out = {"participant": uid, "error": f"{type(exc).__name__}: {exc}"[:300]}
        out["utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        print(json.dumps(out, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    _own_process_group()
    sys.path.insert(0, "/usr/src/BRAVO")
    sys.path.insert(1, "/usr/src/BRAVO/modules")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "BRAVO.settings")
    import django
    django.setup()
    sys.exit(main())
