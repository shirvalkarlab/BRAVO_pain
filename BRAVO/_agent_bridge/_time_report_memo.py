"""Alternating rounds (decision 476): 8 Closed-Loop reports built fresh in one process, with the shared
recording reads off or on (MEMO=0/1), 2 pool workers as in a 16-worker pass."""
import os, sys, time, json, warnings, logging
sys.path.insert(0, "/usr/src/BRAVO"); os.environ.setdefault("DJANGO_SETTINGS_MODULE", "BRAVO.settings")
import django; django.setup()
warnings.filterwarnings("ignore"); logging.disable(logging.WARNING)
from modules.CacheStore import request_memory as rm, saved_answers
from modules.ClosedLoopDeployment import bravo_service as cl
from modules.Biomarkers import bravo_service as bs
os.environ[saved_answers.REBUILD_ENV] = "1"; os.environ[rm.OFF_ENV] = "0"
os.environ["BRAVO_POOL_JOBS"] = "2"
if os.environ.get("MEMO") == "1": os.environ[bs.BAND_SETUP_MEMO_ENV] = "1"
else: os.environ.pop(bs.BAND_SETUP_MEMO_ENV, None)
calls = {"n": 0}; real = bs._load_recordings_uncached
def counted(*a, **k): calls["n"] += 1; return real(*a, **k)
bs._load_recordings_uncached = counted
rows = [r for r in rm.recent("2e3c75c00d7f4f37b53a048d195f11da") if r["kind"] == "closed_loop_report"][:8]
t = []
for r in rows:
    t0 = time.perf_counter(); cl.run_for_participant(dict(r["body"])); t.append(round(time.perf_counter() - t0, 2))
print(json.dumps({"memo": os.environ.get("MEMO"), "total_s": round(sum(t), 1), "each": t, "recording_decodes": calls["n"]}))
