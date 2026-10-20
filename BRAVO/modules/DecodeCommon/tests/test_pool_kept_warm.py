"""Every BRAVO worker pool: one size, asked for through one helper, kept warm, and stopped with
its worker (DecodeCommon.parallel).

Merged here 2026-10-05: test_one_pool_size.py, test_pool_stops_with_its_worker.py (their notes are
at the head of their sections below).

KEPT WARM. Every pool is asked for through one helper, so a pool started ahead of time is the one
requests reuse, and it can be kept alive longer than joblib's five idle minutes (the PI,
2026-10-02: keep the pool warm, with reasonable memory limits). joblib reuses a web worker's pool
only when a call asks with the same settings as the call that started it; a call asking for any
other idle time replaces it (watched on the Jetstream2 BRAVO, 2026-10-02: a plain
`backend="loky"` call after one with a set idle time started a new pool). So:
  * the idle time is BRAVO_POOL_IDLE_SECONDS, else joblib's own 300 s;
  * no BRAVO module asks for a pool any other way than `parallel.loky_backend()`;
  * two calls through the helper share one pool, which carries the idle time asked for.
"""
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

try:
    from modules.DecodeCommon import parallel as P
    from modules.StimOptimizer.routines import surrogate as SUR, band_checks as BC
    from modules.ClosedLoopDeployment import simulation as SIM
except ImportError:                                              # the host runner's spelling
    from DecodeCommon import parallel as P
    from StimOptimizer.routines import surrogate as SUR, band_checks as BC
    from ClosedLoopDeployment import simulation as SIM

from ._helpers import alive as _alive

MODULES_ROOT = Path(__file__).resolve().parents[2]
BRAVO_ROOT = MODULES_ROOT.parent


def _idle_with(value):
    old = os.environ.get(P.POOL_IDLE_ENV)
    try:
        if value is None:
            os.environ.pop(P.POOL_IDLE_ENV, None)
        else:
            os.environ[P.POOL_IDLE_ENV] = value
        return P.pool_idle_seconds(), P.loky_backend().backend_kwargs
    finally:
        if old is None:
            os.environ.pop(P.POOL_IDLE_ENV, None)
        else:
            os.environ[P.POOL_IDLE_ENV] = old


def test_the_idle_time_defaults_to_joblibs_five_minutes_follows_its_variable_and_rides_on_the_helper():
    """(Merged 2026-10-05 with `test_the_helper_carries_the_idle_time`.)"""
    got = {v: _idle_with(v)[0] for v in (None, "3600", "junk", "0")}
    assert got == {None: 300, "3600": 3600, "junk": 300, "0": 300}, got
    assert _idle_with("4321")[1] == {"idle_worker_timeout": 4321}


POOL_USERS = ("ClosedLoopDeployment/simulation.py", "StimOptimizer/routines/band_checks.py",
              "StimOptimizer/routines/surrogate.py")


def test_no_bravo_module_asks_for_a_pool_except_through_the_helper():
    plain = []
    for path in list(MODULES_ROOT.rglob("*.py")) + [BRAVO_ROOT / "BRAVO" / "warmup.py"]:
        rel = str(path.relative_to(BRAVO_ROOT))
        if "/tests/" in rel or "_agent_bridge" in rel:
            continue
        text = path.read_text()
        if re.search(r"""backend\s*=\s*["']loky["']""", text):
            plain.append(rel)
    assert plain == []
    missing = [u for u in POOL_USERS + ("../BRAVO/warmup.py",)
               if "loky_backend()" not in (MODULES_ROOT / u).read_text()]
    assert missing == []


SHARED = r"""
import json, os, sys
sys.path.insert(0, %r)
from DecodeCommon import parallel as P
import joblib
from joblib.externals.loky import reusable_executor as RE
from math import sqrt
joblib.Parallel(n_jobs=2, backend=P.loky_backend())(joblib.delayed(sqrt)(i) for i in range(4))
first = RE._executor
joblib.Parallel(n_jobs=2, backend=P.loky_backend())(joblib.delayed(sqrt)(i) for i in range(4))
print(json.dumps({"same": RE._executor is first, "idle": first._timeout}))
""" % (str(MODULES_ROOT),)


def test_two_calls_through_the_helper_share_one_pool_that_keeps_the_idle_time_asked_for():
    env = dict(os.environ, **{P.POOL_IDLE_ENV: "4321"})
    out = subprocess.run([sys.executable, "-c", SHARED], env=env, capture_output=True, text=True,
                         timeout=120)
    assert out.returncode == 0, out.stderr[-2000:]
    got = json.loads(out.stdout.strip().splitlines()[-1])
    assert got == {"same": True, "idle": 4321}, got


# --------------------------------------------------------------------------------------------
# one pool size (was test_one_pool_size.py)
#
# Every BRAVO worker pool asks for ONE size (2026-10-02, the Jetstream2 BRAVO): joblib keeps a
# single process pool per web worker and shuts it down and rebuilds it whenever a call asks for a
# different size, which cost 1.3-1.5 s per switch there (the Closed-Loop simulation asked for 64,
# the Stim Optimizer's held-out folds and band checks for 15). The size is the core count less one
# (BRAVO_POOL_JOBS overrides it); each use keeps its own variable to set it apart.
#
# Values, not shapes: with no variable set, the three uses report the same number, and it is the
# core count less one; the shared variable moves all three; a use's own variable moves only it.
# --------------------------------------------------------------------------------------------

_VARS = (P.POOL_JOBS_ENV, SUR.LOO_JOBS_ENV, BC.JOBS_ENV, SIM.SEGMENT_JOBS_ENV)


def _with_env(env, fn):
    old = {k: os.environ.get(k) for k in _VARS}
    for k in _VARS:
        os.environ.pop(k, None)
    os.environ.update(env)
    try:
        return fn()
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _three():
    return (SUR._loo_n_jobs(), BC.n_jobs(), SIM._segment_n_jobs())


def test_the_three_pools_default_to_one_size_the_cores_less_one_and_the_variables_move_them():
    """(Merged 2026-10-05 with `test_the_shared_variable_moves_all_three_and_a_use_s_own_moves_only_it`.)"""
    # Both read inside the cleared environment: a BRAVO_POOL_JOBS set on the machine (31 on the
    # Jetstream2 BRAVO, decision 369) must not leak into the default this test pins.
    got, shared = _with_env({}, lambda: (_three(), P.pool_jobs()))
    assert got == (shared,) * 3 == (max(1, (os.cpu_count() or 2) - 1),) * 3
    assert _with_env({P.POOL_JOBS_ENV: "7"}, _three) == (7, 7, 7)
    assert _with_env({P.POOL_JOBS_ENV: "7", SIM.SEGMENT_JOBS_ENV: "1"}, _three) == (7, 7, 1)


# --------------------------------------------------------------------------------------------
# the pool stops with its worker (was test_pool_stops_with_its_worker.py)
#
# A web worker's pool stops when the worker does (2026-10-03).
#
# Reloading gunicorn (`kill -HUP 1`) replaced the workers but left each one's joblib pool running with
# no parent: on 2026-10-02, 850 processes holding 84 GB on the Jetstream2 BRAVO, which pushed the host
# to 240 of 245 GB and the kernel killed part of the desktop. Reproduced on a separate test gunicorn in
# the container (1 worker, a 2-process pool): one HUP left 2 processes with no parent. The pool is
# kept for a day on purpose (`BRAVO_POOL_IDLE_SECONDS`), so nothing else ends it; `shutdown_pool()`
# does, and gunicorn's `worker_exit` hook calls it.
# --------------------------------------------------------------------------------------------

def test_shutdown_pool_stops_the_reusable_pools_processes_and_with_no_pool_is_quiet():
    """(Merged 2026-10-05 with `test_shutdown_pool_with_no_pool_is_quiet`.)"""
    from joblib.externals.loky import get_reusable_executor
    ex = get_reusable_executor(max_workers=2, timeout=600)
    assert sum(ex.map(abs, [-1, -2, -3])) == 6
    pids = list(ex._processes.keys())
    assert len(pids) >= 1
    assert P.shutdown_pool() is True
    deadline = time.time() + 15
    while _alive(pids) and time.time() < deadline:
        time.sleep(0.2)
    assert _alive(pids) == []
    assert P.shutdown_pool() in (True, False)          # no pool left: quiet, never an exception


def test_gunicorn_stops_the_pool_when_a_worker_exits():
    conf = Path(__file__).resolve().parents[3] / "gunicorn.conf.py"
    src = conf.read_text()
    assert "def worker_exit(server, worker):" in src
    assert "shutdown_pool()" in src.split("def worker_exit(server, worker):", 1)[1]
    # the path a reload actually takes: the worker is ended by SIGTERM (see the test below)
    assert "stop_pool_on_signals()" in src.split("def post_worker_init(worker):", 1)[1]


_CHILD = r'''
import os, signal, sys, time
sys.path[:0] = [sys.argv[1]]
try:
    from modules.DecodeCommon import parallel as P
except ImportError:
    from DecodeCommon import parallel as P
from joblib.externals.loky import get_reusable_executor
ex = get_reusable_executor(max_workers=2, timeout=600)
assert sum(ex.map(abs, [-1, -2])) == 3
print(" ".join(str(p) for p in ex._processes), flush=True)
P.stop_pool_on_signals()
signal.signal(signal.SIGTERM, signal.getsignal(signal.SIGTERM))
os.kill(os.getpid(), signal.SIGTERM)
time.sleep(30)
'''


def test_a_worker_killed_by_sigterm_stops_its_pool_first():
    """The live worker dies by SIGTERM: uvicorn shuts its server down, then re-raises the signal with
    the default action, so gunicorn's `worker_exit` and Python's exit routines never run. The handler
    `stop_pool_on_signals` installs stops the pool, then lets the signal end the process as before."""
    root = str(Path(__file__).resolve().parents[3])
    p = subprocess.Popen([sys.executable, "-c", _CHILD, root], stdout=subprocess.PIPE, text=True)
    pids = [int(x) for x in p.stdout.readline().split()]
    assert pids
    assert p.wait(timeout=30) == -signal.SIGTERM        # still ended by the signal, as before
    deadline = time.time() + 15
    while _alive(pids) and time.time() < deadline:
        time.sleep(0.2)
    assert _alive(pids) == []
