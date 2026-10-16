"""Where a Closed-Loop report's build time goes: two different bands' reports in one process, the
second with the shared band preparation available (decision 474 follow-up)."""
import cProfile, pstats, io, time, os, sys
from modules.CacheStore import request_memory as rm, saved_answers
from modules.ClosedLoopDeployment import bravo_service as cl
P = "2e3c75c00d7f4f37b53a048d195f11da"
os.environ[saved_answers.REBUILD_ENV] = "1"
os.environ[rm.OFF_ENV] = "0"
if len(sys.argv) > 1: os.environ["BRAVO_BAND_SETUP_MEMO"] = sys.argv[1]
rows = [r for r in rm.recent(P) if r["kind"] == "closed_loop_report"][:3]
for i, r in enumerate(rows):
    pr = cProfile.Profile(); t = time.perf_counter()
    pr.enable(); out = cl.run_for_participant(dict(r["body"])); pr.disable()
    print(f"=== report {i}: {time.perf_counter()-t:.1f} s available={out.get('available')}", flush=True)
    s = io.StringIO(); pstats.Stats(pr, stream=s).sort_stats("cumulative").print_stats(45)
    print("\n".join(l[:180] for l in s.getvalue().splitlines() if "/modules/" in l or "ncalls" in l))
