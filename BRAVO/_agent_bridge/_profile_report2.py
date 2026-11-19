"""Callee breakdown of one Closed-Loop report build (the second in the process)."""
import cProfile, pstats, io, time, os, warnings
warnings.filterwarnings("ignore")
import logging; logging.disable(logging.WARNING)
from modules.CacheStore import request_memory as rm, saved_answers
from modules.ClosedLoopDeployment import bravo_service as cl
P = "2e3c75c00d7f4f37b53a048d195f11da"
os.environ[saved_answers.REBUILD_ENV] = "1"; os.environ[rm.OFF_ENV] = "0"
rows = [r for r in rm.recent(P) if r["kind"] == "closed_loop_report"][:2]
cl.run_for_participant(dict(rows[0]["body"]))
pr = cProfile.Profile(); t = time.perf_counter()
pr.enable(); cl.run_for_participant(dict(rows[1]["body"])); pr.disable()
print(f"report: {time.perf_counter()-t:.1f} s"); pr.dump_stats("/usr/src/BRAVO/_agent_bridge/_report2.prof"); raise SystemExit
st = pstats.Stats(pr)
for fn in ("report_for_participant", "write_simulation", "run_models", "_place_thresholds_from_record", "report_input_fingerprints", "simulation_inputs_for_participant", "run", "build_for_participant", "pooled_view_payload"):
    s = io.StringIO(); st.stream = s; st.sort_stats("cumulative").print_callees(fn)
    lines = [l[:200] for l in s.getvalue().splitlines() if l.strip()]
    print("\n".join(lines[:40])); print("-----")
