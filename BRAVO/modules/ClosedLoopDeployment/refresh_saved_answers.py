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

LIMITS. At most 8 replays at once, fewer when memory is short (one per 6 GB available), each
replay process limited to 3 pool workers (8 x 3 + 8 stays within 32 cores). The replay processes
are fresh interpreters that exit if this process dies. A failed replay is logged and the rest go
on; the fingerprint is then recorded, so a request that always fails is retried at the next data
change, not every 10 minutes.

    python3 -m modules.ClosedLoopDeployment.refresh_saved_answers --all [--workers 8] [--force]
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
MAX_WORKERS = 8
GB_PER_WORKER = 6.0
POOL_JOBS_PER_REPLAY = "3"
STAMP_PREFIX = "bravo:saved_answer_refresh:"


def _function_for(kind):
    import importlib
    mod, name = KINDS[kind] if kind in KINDS else ALL_BAND_KINDS[kind]
    return getattr(importlib.import_module(mod), name)


def worker_count(requested, available_gb=None):
    """At most `MAX_WORKERS`, and one per `GB_PER_WORKER` of memory available (at least one)."""
    if available_gb is None:
        try:
            with open("/proc/meminfo") as fh:
                kb = next(int(l.split()[1]) for l in fh if l.startswith("MemAvailable:"))
            available_gb = kb / 1024.0 / 1024.0
        except Exception:                                      # noqa: BLE001
            available_gb = GB_PER_WORKER * MAX_WORKERS
    return max(1, min(int(requested), MAX_WORKERS, int(available_gb // GB_PER_WORKER)))


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
    util.Finalize(None, _stop_helpers, exitpriority=100)


def _stop_helpers():
    """Stop the calculation pool and the helper, under each name the helper module was loaded as
    ("DecodeCommon..." and "modules.DecodeCommon..." are two copies, each with its own helper)."""
    from modules.DecodeCommon import parallel
    parallel.shutdown_pool()
    for name, mod in list(sys.modules.items()):
        if name.endswith("DecodeCommon.side_process") and hasattr(mod, "shutdown"):
            mod.shutdown()


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


#: Above this share of memory in use a pass waits before its next batch (decision 464; the PI's
#: standing rule: relieve memory above 75 %).
MEMORY_LIMIT_FRACTION = 0.75


def _used_fraction():
    with open("/proc/meminfo") as fh:
        m = {l.split(":")[0]: int(l.split()[1]) for l in fh if ":" in l}
    return 1.0 - m["MemAvailable"] / float(m["MemTotal"])


def _run_in_batches(rows, workers, run, *, used_fraction=None, sleep=None, batch=None):
    """`run` over `rows` a batch at a time (3 rows per worker), checking memory before each batch and
    waiting (30 s at a time) while more than `MEMORY_LIMIT_FRACTION` is in use (decision 464). The
    pass's own time limit (the loop's `timeout`) bounds the waiting."""
    used_fraction = used_fraction or _used_fraction
    sleep = sleep or time.sleep
    size = max(1, int(batch or workers * 3))
    out = []
    for i in range(0, len(rows), size):
        while used_fraction() > MEMORY_LIMIT_FRACTION:
            sleep(30)
        out.extend(run(rows[i:i + size], workers))
    return out


#: The heat maps' rebuild may run this long in one pass (six pain scores, about 9 s each on RCS08).
HEAT_MAP_LIMIT_SECONDS = 1200


def _heat_maps(participant_uid):
    """THE BIOMARKERS HEAT MAPS, rebuilt when the data changed (decision 464; until now once a day by
    the daily loop): every pain score's grid, by the daily loop's own command, in its own process so
    this one stays small. It reads this pass's one REDCap download (the folder is in its environment).
    The Closed-Loop band grid reads these same saved grids, so they go first."""
    import subprocess
    manage = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "manage.py")
    try:
        p = subprocess.run([sys.executable, manage, "precompute_band_sweeps", "--participant",
                            str(participant_uid), "--json"], capture_output=True, text=True,
                           timeout=HEAT_MAP_LIMIT_SECONDS, cwd=os.path.dirname(manage))
    except subprocess.TimeoutExpired:
        return {"built": 0, "current": 0, "failed": 0, "error": f"stopped after {HEAT_MAP_LIMIT_SECONDS} s"}
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
        os.environ.pop(redcap_client.PASS_DIR_ENV, None)
        shutil.rmtree(pass_dir, ignore_errors=True)


def _refresh_participant(participant_uid, *, workers, force, stamp, run, plan, heat_maps):
    from modules.CacheStore import request_memory
    stamp = data_stamp(participant_uid) if stamp is None else stamp
    if stamp is None:
        return {"participant": participant_uid, "skipped": "no such participant", "replayed": 0}
    if not force and _last_stamp(participant_uid) == stamp:
        return {"participant": participant_uid, "skipped": "data unchanged", "replayed": 0}
    heat = (heat_maps or _heat_maps)(participant_uid)        # first: the band grid reads these
    rows = [r for r in request_memory.recent(participant_uid) if r.get("kind") in KINDS]
    from modules.ClosedLoopDeployment import all_band_requests as _abr
    if not rows and not _abr.registered(participant_uid):
        _save_stamp(participant_uid, stamp)
        return {"participant": participant_uid, "replayed": 0, "built": 0, "served": 0, "failed": 0,
                "errors": [], "seconds": 0.0, "heat_maps": heat}
    t = time.perf_counter()
    runner = (lambda rs, w: _run_in_batches(rs, w, run)) if run else \
        (lambda rs, w: _run_in_batches(rs, w, _run_in_processes))
    results = runner(rows, workers) if rows else []
    from modules.ClosedLoopDeployment import all_band_requests
    every = (_all_bands(participant_uid, rows, workers, runner, plan)
             if all_band_requests.registered(participant_uid) else None)
    _save_stamp(participant_uid, stamp)
    out = {"participant": participant_uid, "replayed": len(results), **_count(results),
           "seconds": round(time.perf_counter() - t, 1)}
    if every is not None:
        out["all_bands"] = every
    out["heat_maps"] = heat
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--participant", action="append", default=[])
    ap.add_argument("--workers", type=int, default=MAX_WORKERS)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    from modules.CacheStore import request_memory
    os.environ[request_memory.OFF_ENV] = "0"                   # the replays are not remembered
    os.environ.setdefault("BRAVO_POOL_JOBS", POOL_JOBS_PER_REPLAY)
    from modules.ClosedLoopDeployment import all_band_requests
    uids = list(a.participant) + (request_memory.participants() + all_band_requests.registered_participants()
                                  if a.all else [])
    n = worker_count(a.workers)
    for uid in dict.fromkeys(uids):
        try:
            out = refresh_participant(uid, workers=n, force=a.force)
        except Exception as exc:                               # noqa: BLE001 -- next participant
            out = {"participant": uid, "error": f"{type(exc).__name__}: {exc}"[:300]}
        out["utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        out["workers"] = n
        print(json.dumps(out, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    sys.path.insert(0, "/usr/src/BRAVO")
    sys.path.insert(1, "/usr/src/BRAVO/modules")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "BRAVO.settings")
    import django
    django.setup()
    sys.exit(main())
