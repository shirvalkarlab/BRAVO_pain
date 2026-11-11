"""Equality proof for decision 476: build a fixed sample of remembered answers fresh, in one process,
and write every one to a JSON file. Run once as the pages run (no pass switches) and once as a
32-worker pass's process runs (shared recordings memo, 1 pool helper, 1 BLAS thread); then compare."""
import os, sys, json, time, warnings, logging
warnings.filterwarnings("ignore"); logging.disable(logging.WARNING)
OUT = os.environ["PROOF_OUT"]
from modules.CacheStore import request_memory as rm, saved_answers
from modules.ClosedLoopDeployment import refresh_saved_answers as job
P = "2e3c75c00d7f4f37b53a048d195f11da"
os.environ[saved_answers.REBUILD_ENV] = "1"; os.environ[rm.OFF_ENV] = "0"
rows = rm.recent(P)
want = {"closed_loop_report": 12, "deployment_summary": 4, "deployment_roc": 4,
        "deployment_roc_by_era": 4, "band_lsb_power": 4}
pick = []
for r in rows:
    if want.get(r["kind"], 0) > 0:
        want[r["kind"]] -= 1; pick.append(r)
res = []
t0 = time.perf_counter()
for r in pick:
    fn = job._function_for(r["kind"])
    t = time.perf_counter(); out = fn(dict(r["body"]))
    res.append({"kind": r["kind"], "body": r["body"], "seconds": round(time.perf_counter() - t, 2),
                "out": json.loads(json.dumps(out, sort_keys=True, default=str))})
    print(r["kind"], res[-1]["seconds"], flush=True)
json.dump(res, open(OUT, "w"), sort_keys=True)
print("total", round(time.perf_counter() - t0, 1), "answers", len(res))
