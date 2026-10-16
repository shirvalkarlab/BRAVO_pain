"""Time the part of a rating-only pass that is not measured elsewhere: every answer the pages asked
for, worked out afresh through the pass's own machinery (one process set, shared band preparation,
memory-checked batches), as a new pain rating forces. Decision 474."""
import os, sys, time, json
sys.path.insert(0, "/usr/src/BRAVO")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "BRAVO.settings")
import django; django.setup()
from modules.CacheStore import request_memory, saved_answers
from modules.ClosedLoopDeployment import refresh_saved_answers as job
P = "2e3c75c00d7f4f37b53a048d195f11da"
rows = [r for r in request_memory.recent(P) if r.get("kind") in job.KINDS]
os.environ[saved_answers.REBUILD_ENV] = "1"           # the replay processes inherit it
os.environ[request_memory.OFF_ENV] = "0"                 # as the pass does: replays are not remembered
n = int(os.environ.get("MEASURE_WORKERS") or job.worker_count(job.MAX_WORKERS))
os.environ["BRAVO_POOL_JOBS"] = str(job.pool_jobs_per_replay(n))   # as main() does
print("workers", n, "pool jobs", os.environ["BRAVO_POOL_JOBS"], flush=True)
t = time.perf_counter()
try:
    res = job._run_in_pool(rows, n)
finally:
    job._close_pass_pool()
    os.environ.pop(saved_answers.REBUILD_ENV, None)
dt = time.perf_counter() - t
c = job._count(res)
by = {}
for r, x in zip(rows, res):
    by.setdefault(r["kind"], [0, 0.0]); by[r["kind"]][0] += 1; by[r["kind"]][1] += float(x.get("seconds") or 0)
print(json.dumps({"answers": len(rows), "workers": n, "seconds": round(dt, 1), **{k: c[k] for k in ("built", "served", "failed")},
                  "errors": c["errors"][:3],
                  "by_kind": {k: {"n": v[0], "mean_s": round(v[1] / v[0], 1)} for k, v in by.items()}}))
