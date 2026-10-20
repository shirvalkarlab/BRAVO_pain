'Warm a fresh web worker before it serves its first request (speed-up item B9, 2026-10-02).'
import importlib
import logging
import os
import time

_log = logging.getLogger("BRAVO.warmup")

ENABLE_ENV = "BRAVO_WARMUP"
POOL_ENV = "BRAVO_WARMUP_POOL"

#: Imported in this order. The services first (each pulls in its own routines), then the libraries
#: the 2026-10-02 profile saw imported inside a request, with what each cost there.
IMPORTS = (
    "modules.Biomarkers.bravo_service",
    "modules.StimOptimizer.bravo_service",
    "modules.ClosedLoopDeployment.bravo_service",
    "modules.ClosedLoopDeployment.simulation",
    "modules.ClosedLoopDeployment.design_rule",
    "modules.ClosedLoopDeployment.robustness",
    "statsmodels.api",                 # 0.3-0.7 s, all three requests
    "statsmodels.formula.api",
    "sklearn.metrics",
    "sklearn.linear_model",
    "matplotlib.pyplot",               # 0.5 s, Closed-Loop
    "seaborn",                         # 0.1 s, Closed-Loop
)


def _import(name):
    """`modules.X` as the views spell it (so it stays the canonical name, decision 143), and the
    bare `X` where only `modules/` is on the path (the test suites)."""
    try:
        return importlib.import_module(name)
    except ImportError:
        if name.startswith("modules."):
            return importlib.import_module(name[len("modules."):])
        raise


def _import_step():
    failed = {}
    for name in IMPORTS:
        try:
            _import(name)
        except Exception as exc:                      # noqa: BLE001 -- one missing library is not fatal
            failed[name] = f"{type(exc).__name__}: {exc}"
    return {"imported": len(IMPORTS) - len(failed), "failed": failed}


def _r_step():
    """Start R and load lme4 the way the first mixed-model fit does (`from pymer4.models import
    Lmer`), holding the lock every R fit holds, so R is never touched by two threads at once."""
    try:
        analytics = _import("modules.Biomarkers.routines.analytics")
        lock = analytics._R_GLOBAL_LOCK
    except Exception:                                  # noqa: BLE001 -- no lock to take: no R fits either
        lock = None
    if lock is not None:
        lock.acquire()
    try:
        from pymer4.models import Lmer  # noqa: F401
    finally:
        if lock is not None:
            lock.release()
    return {"r": True}


def _numba_step():
    """Each compiled loop through its own public function, on a few numbers. The public function
    converts the arguments (contiguous float64 arrays, Python floats and ints), so the loop is
    compiled for exactly the types a request passes."""
    import numpy as np
    dr = _import("modules.ClosedLoopDeployment.design_rule")
    sim = _import("modules.ClosedLoopDeployment.simulation")
    rb = _import("modules.ClosedLoopDeployment.robustness")
    done = {}

    Y = np.array([[np.nan, 1.0, 1.2, np.nan, 0.9, 1.1, 1.3, 1.0, 0.8, 1.2],
                  [0.5, 0.7, np.nan, 0.6, 0.8, 0.4, 0.9, 1.0, 0.7, 0.6],
                  [1.5, 1.4, 1.6, 1.2, np.nan, 1.3, 1.1, 1.0, 1.4, 1.5]])
    if getattr(dr, "COMPILED_FILTER", False):
        dr.filter_2comp(Y, phi_s=0.95, phi_f=0.5, q_s=0.01, q_f=0.1, m=1.0, r0=0.5)
        dr.filter_1state(Y, phi=1.0, m=1.0, q=0.05, r0=0.5)
        done["design_rule"] = True

    if getattr(sim, "COMPILED_CONTROLLER", False):
        _controller_loop_once(sim)
        done["simulation"] = True

    if getattr(rb, "COMPILED_REPLAY", False):
        p = np.array([1.0, 1.6, np.nan, 0.4, 1.8, 1.2, 0.3, 1.7, 1.1, 0.2])
        K = 2
        rb.run_stretch(p, 1.0, np.array([1.5, 1.4]), np.array([0.5, 0.6]), np.full(K, 2000.0),
                       np.full(K, 1000.0), np.full(K, 3000.0), np.full(K, 3000.0), 0.5, 3.0)
        done["robustness"] = True
    return {"compiled": done}


def _controller_loop_once(sim):
    """The simulation's controller loop on a few numbers."""
    import numpy as np
    bank = {"K": 3, "kind": np.array([0, 1, 2]), "slope": np.array([0.0, 0.2, 0.0]),
            "a": np.array([0.0, 0.0, -0.1]), "b": np.array([0.0, 0.0, 0.5]),
            "peak": np.array([np.nan, np.nan, 2.5]), "post": np.array([np.nan, np.nan, 0.0])}
    p = np.array([1.0, 2.2, np.nan, 0.5, 2.6, 1.5, 0.2, 2.5])
    a_obs = np.array([1.0, 1.2, 1.4, np.nan, 1.6, 1.8, 2.0, 2.2])
    sim._run_controller_loop(bank, p, a_obs, np.full(3, 0.5), 1.0, 2.0, 1.0, 0.5, 3.0, 1.5, 1.0,
                             1.0, 2, 1, 3.0, 0.5)


def _pool_size_from_env():
    raw = os.environ.get(POOL_ENV, "").strip().lower()
    if raw in ("", "0", "off", "no", "false"):
        return 0
    if raw == "auto":                                  # the size every BRAVO pool asks for (decision 364)
        try:
            return int(_import("modules.DecodeCommon.parallel").pool_jobs())
        except Exception:                              # noqa: BLE001
            return max(1, (os.cpu_count() or 2) - 1)
    try:
        return max(0, int(raw))
    except ValueError:
        return 0


def _pool_step(n):
    """joblib's reusable worker pool, started the way the simulation starts it (same backend, so
    the next joblib call of the same size reuses it rather than replacing it). Each task is the
    controller loop itself, so a worker that runs one imports the simulation module by the name the
    request uses and compiles the loop (or loads it from numba's disk cache). Twice as many tasks
    as workers, so a worker still starting when the first tasks are taken still gets one."""
    if n <= 0:
        return {"workers": 0}
    import joblib
    import numpy as np
    sim = _import("modules.ClosedLoopDeployment.simulation")
    bank = {"K": 2, "kind": np.array([1, 2]), "slope": np.array([0.2, 0.0]),
            "a": np.array([0.0, -0.1]), "b": np.array([0.0, 0.5]),
            "peak": np.array([np.nan, 2.5]), "post": np.array([np.nan, 0.0])}
    p = np.array([1.0, 2.2, np.nan, 0.5, 2.6, 1.5])
    a_obs = np.array([1.0, 1.2, 1.4, np.nan, 1.6, 1.8])
    joblib.Parallel(n_jobs=n, backend=_import("modules.DecodeCommon.parallel").loky_backend())(
        joblib.delayed(sim._run_controller_loop)(bank, p, a_obs, np.full(2, 0.5), 1.0, 2.0, 1.0,
                                                 0.5, 3.0, 1.5, 1.0, 1.0, 2, 1, 3.0, 0.5)
        for _ in range(2 * n))
    return {"workers": n, "tasks": 2 * n}


PARTICIPANTS_ENV = "BRAVO_WARMUP_PARTICIPANTS"
DEFAULT_PARTICIPANTS = 3


def _participant_limit():
    raw = os.environ.get(PARTICIPANTS_ENV, "").strip().lower()
    if raw == "":
        return DEFAULT_PARTICIPANTS
    if raw in ("off", "no", "false"):
        return 0
    try:
        return max(0, int(raw))
    except ValueError:
        return DEFAULT_PARTICIPANTS


def _participant_uids():
    """The participants that have recordings (the first few), by uid."""
    limit = _participant_limit()
    if limit <= 0:
        return []
    from Server import models
    seen = []
    for uid in models.SourceFile.objects.values_list("owner_id", flat=True):
        if uid and uid not in seen:              # a source file with no owner is not a participant
            seen.append(uid)
        if len(seen) >= limit:
            break
    return seen


def _biomarkers_service():
    return _import("modules.Biomarkers.bravo_service")


def _participants_step():
    """Make the Biomarkers page's grid request and then one cell request for each participant, so
    this worker holds the ratings and the decoded recordings before its first click."""
    uids = _participant_uids()
    svc = _biomarkers_service() if uids else None
    warmed, failed = [], {}
    for uid in uids:
        try:
            grid = svc.run_for_participant({"ParticipantId": uid, "BandTimeSweep": "1",
                                            "SweepMetric": "nrs"})
            data = (grid or {}).get("data", grid) or {}
            sweeps = data.get("band_time_sweep") or {}
            seconds = data.get("integration_seconds") or []
            channel = next(iter(sorted(sweeps)), None)
            centres = (sweeps.get(channel) or {}).get("center_freqs_hz") or [] if channel else []
            if channel and centres and seconds:
                svc.run_for_participant({"ParticipantId": uid, "SweepMetric": "nrs",
                                         "BandTimeSweepCell": "1", "Channel": channel,
                                         "BandCenterHz": centres[0], "IntegrationSeconds": seconds[0]})
            warmed.append(uid)
        except Exception as exc:                      # noqa: BLE001 -- one participant never stops the rest
            failed[uid] = f"{type(exc).__name__}: {exc}"
    return {"participants": len(uids), "warmed": warmed, "failed": failed}


def _timed(name, fn, *args):
    t0 = time.perf_counter()
    try:
        out = dict(fn(*args) or {})
        out.update(ok=True, error=None)
    except Exception as exc:                          # noqa: BLE001 -- reported, never raised
        out = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        _log.warning("warm-up step %s failed: %s", name, out["error"])
    out["seconds"] = round(time.perf_counter() - t0, 3)
    return out


def warm_up(*, imports=True, r=True, numba=True, pool=None):
    """Warm this process. Never raises. Returns what each step did and how long it took.

    `pool` is the number of worker processes to start (None: read `BRAVO_WARMUP_POOL`, default 0).
    """
    t0 = time.perf_counter()
    try:
        if os.environ.get(ENABLE_ENV, "1").strip().lower() in ("0", "off", "no", "false"):
            return {"enabled": False, "steps": {}, "seconds": 0.0}
        steps = {}
        if imports:
            steps["imports"] = _timed("imports", _import_step)
        if r:
            steps["r"] = _timed("r", _r_step)
        if numba:
            steps["numba"] = _timed("numba", _numba_step)
        n = _pool_size_from_env() if pool is None else max(0, int(pool))
        steps["pool"] = _timed("pool", _pool_step, n)
        if n == 0 and steps["pool"].get("ok"):
            steps["pool"]["workers"] = 0
        steps["participants"] = _timed("participants", _participants_step)
        report = {"enabled": True, "steps": steps, "seconds": round(time.perf_counter() - t0, 3)}
        _log.info("warm-up done in %.1f s: %s", report["seconds"],
                  ", ".join(f"{k} {v['seconds']:.1f} s{'' if v['ok'] else ' FAILED'}"
                            for k, v in steps.items()))
        return report
    except Exception as exc:                          # noqa: BLE001 -- the last line of defence
        _log.warning("warm-up failed: %s: %s", type(exc).__name__, exc)
        return {"enabled": True, "steps": {}, "seconds": round(time.perf_counter() - t0, 3),
                "error": f"{type(exc).__name__}: {exc}"}
