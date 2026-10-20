"""A fresh web worker is warmed before its first request (speed-up item B9, 2026-10-02).

`BRAVO/warmup.py` runs once in each new web worker, from gunicorn's `post_worker_init` hook in
`BRAVO/gunicorn.conf.py`, before the worker accepts a request. On the Jetstream2 BRAVO a fresh
worker spent the first Closed-Loop request starting R (about 6 s) and compiling the numba loops
(3.3 s), work every later request skips.

These tests hold that:
  1. after the warm-up, every numba loop a request uses is compiled for the argument types a real
     call passes, so the request itself compiles nothing;
  2. the controller loop and the robustness replay load from numba's on-disk cache in a second
     process, with results identical to the bit (the design rule's filters are cached on disk too
     since 2026-10-02, when their summation stopped calling itself; that is tested in
     test_design_rule_compiled_filter.py);
  3. asked for, the worker pool is started and the next joblib call reuses it rather than
     replacing it;
  4. R is started under the lock every R fit holds;
  5. nothing in the warm-up can stop a worker from starting: a failing step is reported, never
     raised, and the gunicorn hook swallows even a failed import.

Each check that depends on what a process has already compiled runs in a fresh interpreter.
Skipped where numba is not installed (CI installs it, decision 271).
"""
import importlib.util
import json
import logging
import os
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("numba")

BRAVO_ROOT = Path(__file__).resolve().parents[3]          # .../BRAVO (holds BRAVO/warmup.py)
MODULES_ROOT = BRAVO_ROOT / "modules"
WARMUP_FILE = BRAVO_ROOT / "BRAVO" / "warmup.py"
GUNICORN_CONF = BRAVO_ROOT / "gunicorn.conf.py"

# The path set-up of a web worker: BRAVO's root first (the views import `modules.X`), `modules/`
# appended (settings.py does the same), so both spellings are importable and one object.
PRELUDE = (
    "import json, os, sys\n"
    "sys.path.insert(0, %r)\n"
    "sys.path.append(%r)\n"
    "import BRAVO.warmup as W\n"
) % (str(BRAVO_ROOT), str(MODULES_ROOT))


def _run(code, extra_env=None, timeout=300):
    env = dict(os.environ)
    env.pop("BRAVO_WARMUP", None)
    env.pop("BRAVO_WARMUP_POOL", None)
    env["BRAVO_WARMUP_PARTICIPANTS"] = "0"      # these subprocesses have no database; the step has its own tests
    env.update(extra_env or {})
    out = subprocess.run([sys.executable, "-c", PRELUDE + code], env=env, capture_output=True,
                         text=True, timeout=timeout, cwd=str(BRAVO_ROOT))
    assert out.returncode == 0, (out.stdout[-3000:], out.stderr[-3000:])
    return json.loads(out.stdout.strip().splitlines()[-1])


def _load_warmup_in_process():
    spec = importlib.util.spec_from_file_location("bravo_warmup_test_copy", WARMUP_FILE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------------------------------
# 1. every numba loop a request uses is compiled, for the argument types a real call passes
# --------------------------------------------------------------------------------------------
REAL_CALLS = r"""
import numpy as np
from modules.ClosedLoopDeployment import design_rule as DR, simulation as SIM, robustness as RB
# The two-component loop a request runs (decision 361); `_filter_2comp_kernel` is only its reference.
kernels = {"design_rule._filter_2comp_active_kernel": DR._filter_2comp_active_kernel,
           "design_rule._filter_1state_kernel": DR._filter_1state_kernel,
           "design_rule._pairwise_sum": DR._pairwise_sum,
           "simulation._run_controller_loop_kernel": SIM._run_controller_loop_kernel,
           "robustness._run_stretch_kernel": RB._run_stretch_kernel}
before_warm = {k: len(d.signatures) for k, d in kernels.items()}
report = W.warm_up(imports=False, r=False, pool=0)
after_warm = {k: len(d.signatures) for k, d in kernels.items()}

# Calls shaped as the request makes them: a stretch panel wider than 128 (the pairwise sum's
# split), gaps, a missing first reading; the controller over curves of every kind; the replay
# over a prepared stretch with configuration arrays built by the module's own grid.
rng = np.random.default_rng(7)
Y = rng.normal(size=(300, 40)); Y[rng.random(Y.shape) < 0.1] = np.nan; Y[0, 0] = np.nan
DR.filter_2comp(Y, phi_s=0.97, phi_f=0.4, q_s=0.02, q_f=0.3, m=0.1, r0=0.8)
DR.filter_1state(Y, phi=1.0, m=0.0, q=0.05, r0=0.9)
bank = {"K": 4, "kind": np.array([0, 1, 2, 2]), "slope": np.array([0.0, 0.3, 0.0, 0.0]),
        "a": np.array([0.0, 0.0, -0.2, 0.1]), "b": np.array([0.0, 0.0, 0.9, -0.3]),
        "peak": np.array([np.nan, np.nan, 2.2, np.nan]), "post": np.array([np.nan, np.nan, -0.1, np.nan])}
p = rng.normal(1.0, 0.6, 500); p[rng.random(500) < 0.05] = np.nan
a_obs = rng.uniform(0.5, 3.0, 500); a_obs[::50] = np.nan
SIM._run_controller_loop(bank, p, a_obs, np.full(4, 0.3), 0.5, 1.4, 0.6, 0.5, 3.0, 1.5, 0.4, 0.6,
                         3, 2, 3.0, 0.5)
gt = np.arange(400) * 0.5; gp = rng.normal(1.0, 0.5, 400); ga = rng.uniform(0.5, 3.0, 400)
_t, pp, _a, dt, _n = RB.prepare(gt, gp, ga, 1000.0)
K = 6
RB.run_stretch(pp, dt, np.linspace(1.1, 1.6, K), np.linspace(0.4, 0.9, K), np.full(K, 2000.0),
               np.full(K, 1000.0), np.full(K, 4000.0), np.full(K, 6000.0), 0.5, 3.0)
after_real = {k: len(d.signatures) for k, d in kernels.items()}
print(json.dumps({"report": report, "before_warm": before_warm, "after_warm": after_warm,
                  "after_real": after_real}, default=str))
"""


def test_the_warm_up_compiles_every_numba_loop_for_the_argument_types_a_request_passes(tmp_path):
    got = _run(REAL_CALLS, {"NUMBA_CACHE_DIR": str(tmp_path)})
    assert got["report"]["enabled"] is True
    assert got["report"]["steps"]["numba"]["ok"] is True, got["report"]
    for name, n in got["before_warm"].items():
        assert n == 0, f"{name} was compiled before the warm-up ran ({n}); the check proves nothing"
    for name, n in got["after_warm"].items():
        assert n >= 1, f"the warm-up did not compile {name}"
    # The request-shaped calls added no specialisation: the warm-up compiled the very one they use.
    assert got["after_real"] == got["after_warm"], (got["after_warm"], got["after_real"])


# --------------------------------------------------------------------------------------------
# 2. the controller loop and the robustness replay come from the disk cache, identical to the bit
# --------------------------------------------------------------------------------------------
CACHED_RUN = r"""
import hashlib
import numpy as np
from modules.ClosedLoopDeployment import simulation as SIM, robustness as RB
rng = np.random.default_rng(11)
bank = {"K": 5, "kind": np.array([0, 1, 2, 2, 1]), "slope": np.array([0.0, 0.3, 0.0, 0.0, -0.4]),
        "a": np.array([0.0, 0.0, -0.2, 0.1, 0.0]), "b": np.array([0.0, 0.0, 0.9, -0.3, 0.0]),
        "peak": np.array([np.nan, np.nan, 2.2, np.nan, np.nan]),
        "post": np.array([np.nan, np.nan, -0.1, np.nan, np.nan])}
p = rng.normal(1.0, 0.6, 3000); p[rng.random(3000) < 0.05] = np.nan
a_obs = rng.uniform(0.5, 3.0, 3000); a_obs[::70] = np.nan
args = (bank, p, a_obs, np.array([0.3, 0.5, 1.0, 0.2, 0.7]), 0.5, 1.4, 0.6, 0.5, 3.0, 1.5, 0.4, 0.6, 3, 2, 3.0, 0.5)
h = hashlib.sha256()
for a in SIM._run_controller_loop(*args):
    h.update(np.ascontiguousarray(a).tobytes())
ref = hashlib.sha256()
for a in SIM._run_controller_loop_numpy(*args):
    ref.update(np.ascontiguousarray(a).tobytes())
gt = np.arange(2000) * 0.5; gp = rng.normal(1.0, 0.5, 2000); gp[rng.random(2000) < 0.03] = np.nan
_t, pp, _a, dt, _n = RB.prepare(gt, gp, rng.uniform(0.5, 3.0, 2000), 1000.0)
K = 9
r = RB.run_stretch(pp, dt, np.linspace(1.1, 1.6, K), np.linspace(0.4, 0.9, K), np.full(K, 2000.0),
                   np.full(K, 1000.0), np.full(K, 4000.0), np.full(K, 6000.0), 0.5, 3.0)
hr = hashlib.sha256()
for k in sorted(r):
    hr.update(k.encode()); hr.update(np.ascontiguousarray(r[k]).tobytes())
st_sim, st_rb = SIM._run_controller_loop_kernel.stats, RB._run_stretch_kernel.stats
print(json.dumps({"sim": h.hexdigest(), "sim_numpy": ref.hexdigest(), "rb": hr.hexdigest(),
                  "sim_hits": sum(st_sim.cache_hits.values()), "sim_misses": sum(st_sim.cache_misses.values()),
                  "rb_hits": sum(st_rb.cache_hits.values()), "rb_misses": sum(st_rb.cache_misses.values())}))
"""


def test_the_controller_loop_and_the_replay_load_from_the_disk_cache_with_identical_results(tmp_path):
    first = _run(CACHED_RUN, {"NUMBA_CACHE_DIR": str(tmp_path)})
    second = _run(CACHED_RUN, {"NUMBA_CACHE_DIR": str(tmp_path)})
    assert first["sim_misses"] >= 1 and first["rb_misses"] >= 1, first        # compiled and saved
    assert second["sim_hits"] >= 1 and second["sim_misses"] == 0, second       # loaded, not compiled
    assert second["rb_hits"] >= 1 and second["rb_misses"] == 0, second
    assert second["sim"] == first["sim"] == first["sim_numpy"]
    assert second["rb"] == first["rb"]


# --------------------------------------------------------------------------------------------
# 3. the worker pool, when asked for, is started and then reused by the next joblib call
# --------------------------------------------------------------------------------------------
POOL_REUSE = r"""
import joblib
from joblib.externals.loky import reusable_executor as RE
report = W.warm_up(imports=False, r=False, numba=False, pool=2)
ex = RE._executor
warm_pids = sorted(ex._processes) if ex is not None else []
from DecodeCommon import parallel as PAR          # the way every request asks for the pool
pids = joblib.Parallel(n_jobs=2, backend=PAR.loky_backend())(joblib.delayed(os.getpid)() for _ in range(6))
print(json.dumps({"report": report, "warm_pids": warm_pids, "same_executor": RE._executor is ex,
                  "pids": sorted(set(pids))}, default=str))
"""


def test_the_pool_step_starts_the_worker_pool_that_the_next_joblib_call_reuses(tmp_path):
    got = _run(POOL_REUSE, {"NUMBA_CACHE_DIR": str(tmp_path)})
    step = got["report"]["steps"]["pool"]
    assert step["ok"] is True, step
    assert len(got["warm_pids"]) == 2, got
    assert got["same_executor"] is True, "the next joblib call replaced the warmed pool"
    assert set(got["pids"]) <= set(got["warm_pids"]), got


def test_no_pool_is_started_unless_asked_for(tmp_path):
    got = _run("from joblib.externals.loky import reusable_executor as RE\n"
               "report = W.warm_up(imports=False, r=False, numba=False)\n"
               "print(json.dumps({'report': report, 'executor': RE._executor is not None}, default=str))\n",
               {"NUMBA_CACHE_DIR": str(tmp_path)})
    assert got["executor"] is False
    assert got["report"]["steps"]["pool"]["workers"] == 0


# --------------------------------------------------------------------------------------------
# 4. R is started, under the lock every R fit holds
# --------------------------------------------------------------------------------------------
R_STEP = r"""
from modules.Biomarkers.routines import analytics as A
held = []
class _Spy:
    def __init__(self, lock): self.lock = lock
    def acquire(self, *a, **k):
        held.append(True); return self.lock.acquire(*a, **k)
    def release(self): return self.lock.release()
    def __enter__(self): self.acquire(); return self
    def __exit__(self, *exc): self.release()
A._R_GLOBAL_LOCK = _Spy(A._R_GLOBAL_LOCK)
report = W.warm_up(imports=False, numba=False, pool=0)
print(json.dumps({"report": report, "lock_taken": bool(held),
                  "r_started": "rpy2.robjects" in sys.modules and "pymer4.models" in sys.modules}, default=str))
"""


def test_the_r_step_starts_r_under_the_lock_every_r_fit_holds(tmp_path):
    if importlib.util.find_spec("pymer4") is None:
        pytest.skip("pymer4 and R are not installed here (the container has them)")
    got = _run(R_STEP, {"NUMBA_CACHE_DIR": str(tmp_path)})
    assert got["report"]["steps"]["r"]["ok"] is True, got["report"]
    assert got["r_started"] is True
    assert got["lock_taken"] is True


# --------------------------------------------------------------------------------------------
# 5. nothing here can stop a worker from starting
# --------------------------------------------------------------------------------------------
def test_a_failing_step_is_reported_and_never_raised(monkeypatch, caplog):
    W = _load_warmup_in_process()

    def boom(*a, **k):
        raise RuntimeError("synthetic failure")
    for name in ("_import_step", "_r_step", "_numba_step", "_pool_step"):
        monkeypatch.setattr(W, name, boom)
    with caplog.at_level(logging.WARNING):
        report = W.warm_up(pool=2)
    assert report["enabled"] is True
    for name in ("imports", "r", "numba", "pool"):
        assert report["steps"][name]["ok"] is False
        assert "synthetic failure" in report["steps"][name]["error"]
    assert "synthetic failure" in caplog.text


def test_bravo_warmup_0_turns_it_off(monkeypatch):
    W = _load_warmup_in_process()
    monkeypatch.setenv("BRAVO_WARMUP", "0")
    called = []
    monkeypatch.setattr(W, "_numba_step", lambda *a, **k: called.append(1))
    assert W.warm_up() == {"enabled": False, "steps": {}, "seconds": 0.0}
    assert called == []


def test_the_pool_size_is_read_from_bravo_warmup_pool(monkeypatch):
    W = _load_warmup_in_process()
    for raw, want in (("", 0), ("0", 0), ("off", 0), ("3", 3), ("nonsense", 0), ("-4", 0)):
        monkeypatch.setenv("BRAVO_WARMUP_POOL", raw)
        assert W._pool_size_from_env() == want, raw
    monkeypatch.setenv("BRAVO_WARMUP_POOL", "auto")
    assert W._pool_size_from_env() >= 1


def test_the_gunicorn_hook_warms_the_worker_and_swallows_any_failure(monkeypatch):
    conf = runpy.run_path(str(GUNICORN_CONF))
    assert callable(conf.get("post_worker_init")), "gunicorn.conf.py defines no post_worker_init"

    class _Log:
        def __init__(self): self.lines = []
        def info(self, msg, *a): self.lines.append(msg % a)
        def warning(self, msg, *a): self.lines.append(msg % a)

    class _Worker:
        log = _Log()

    # the warm-up module cannot be imported at all: the hook logs it and returns
    monkeypatch.setitem(sys.modules, "BRAVO.warmup", None)
    conf["post_worker_init"](_Worker())
    assert any("warm-up" in l for l in _Worker.log.lines), _Worker.log.lines

    # the warm-up runs and its report is logged
    import types
    fake = types.ModuleType("BRAVO.warmup")
    fake.warm_up = lambda: {"enabled": True, "steps": {}, "seconds": 0.0}
    monkeypatch.setitem(sys.modules, "BRAVO.warmup", fake)
    _Worker.log.lines.clear()
    conf["post_worker_init"](_Worker())
    assert any("warm-up" in l for l in _Worker.log.lines), _Worker.log.lines


# --------------------------------------------------------------------------------------------
# 6. the participants' data, loaded into each web worker before it takes a request (2026-10-02)
# --------------------------------------------------------------------------------------------
# The first heat-map cell click that reached a web worker loaded the REDCap ratings and decoded every
# recording (6 s on the Mac, 12 s on the 16-worker Jetstream2 BRAVO); later clicks in the same
# worker took 0.03-0.13 s. With 16 workers, most early clicks were that first one. The step makes the
# two Biomarkers requests the page makes (the grid, then one cell of it) for each participant, so
# the worker is warm for the page's first click.
def _fake_service(calls, grid_response=None):
    import types
    svc = types.ModuleType("fake_bm_service")
    def run_for_participant(req):
        calls.append(dict(req))
        if req.get("BandTimeSweepCell"):
            return {"band_time_sweep_cell": {"points": []}}
        return grid_response if grid_response is not None else {
            "integration_seconds": [1.0, 5.0],
            "band_time_sweep": {"CH_A": {"center_freqs_hz": [8.5, 9.5]}}}
    svc.run_for_participant = run_for_participant
    return svc


def test_the_participants_step_makes_the_pages_grid_request_then_one_cell_request(monkeypatch):
    W = _load_warmup_in_process()
    calls = []
    monkeypatch.setattr(W, "_participant_uids", lambda: ["P1"])
    monkeypatch.setattr(W, "_biomarkers_service", lambda: _fake_service(calls))
    out = W._participants_step()
    assert out == {"participants": 1, "warmed": ["P1"], "failed": {}}, out
    assert calls[0].get("BandTimeSweep") == "1" and calls[0]["ParticipantId"] == "P1", calls
    assert calls[1] == {"ParticipantId": "P1", "SweepMetric": "nrs", "BandTimeSweepCell": "1",
                        "Channel": "CH_A", "BandCenterHz": 8.5, "IntegrationSeconds": 1.0}, calls
    assert len(calls) == 2


def test_one_participant_failing_does_not_stop_the_others(monkeypatch):
    W = _load_warmup_in_process()
    calls = []
    svc = _fake_service(calls)
    real = svc.run_for_participant
    def flaky(req):
        if req["ParticipantId"] == "BAD":
            raise RuntimeError("no data")
        return real(req)
    svc.run_for_participant = flaky
    monkeypatch.setattr(W, "_participant_uids", lambda: ["BAD", "P2"])
    monkeypatch.setattr(W, "_biomarkers_service", lambda: svc)
    out = W._participants_step()
    assert out["warmed"] == ["P2"] and "BAD" in out["failed"] and "no data" in out["failed"]["BAD"], out


def test_a_grid_with_no_channels_warms_only_the_grid(monkeypatch):
    W = _load_warmup_in_process()
    calls = []
    monkeypatch.setattr(W, "_participant_uids", lambda: ["P1"])
    monkeypatch.setattr(W, "_biomarkers_service",
                        lambda: _fake_service(calls, grid_response={"band_time_sweep": {}}))
    out = W._participants_step()
    assert out["warmed"] == ["P1"] and len(calls) == 1, (out, calls)


def test_the_participants_step_is_off_when_asked(monkeypatch):
    W = _load_warmup_in_process()
    for raw in ("0", "off", "false"):
        monkeypatch.setenv("BRAVO_WARMUP_PARTICIPANTS", raw)
        assert W._participant_limit() == 0, raw
    monkeypatch.setenv("BRAVO_WARMUP_PARTICIPANTS", "2")
    assert W._participant_limit() == 2
    monkeypatch.delenv("BRAVO_WARMUP_PARTICIPANTS", raising=False)
    assert W._participant_limit() == 3                      # the default: the three newest participants


def test_warm_up_runs_the_participants_step_last_and_reports_it(monkeypatch):
    W = _load_warmup_in_process()
    order = []
    for name in ("_import_step", "_r_step", "_numba_step", "_pool_step", "_participants_step"):
        monkeypatch.setattr(W, name, (lambda n: (lambda *a, **k: order.append(n) or {}))(name))
    report = W.warm_up(pool=0)
    assert order == ["_import_step", "_r_step", "_numba_step", "_pool_step", "_participants_step"], order
    assert "participants" in report["steps"]


def test_a_source_file_with_no_owner_is_not_warmed(monkeypatch):
    W = _load_warmup_in_process()
    import types
    class _Q:
        def values_list(self, *a, **k):
            return iter([None, "", "P1", "P1", "P2"])
    fake_models = types.SimpleNamespace(SourceFile=types.SimpleNamespace(objects=_Q()))
    server = types.ModuleType("Server"); server.models = fake_models
    monkeypatch.setitem(sys.modules, "Server", server)
    monkeypatch.delenv("BRAVO_WARMUP_PARTICIPANTS", raising=False)
    assert W._participant_uids() == ["P1", "P2"]
