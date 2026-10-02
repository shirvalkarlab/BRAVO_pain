"""Every BRAVO worker pool is asked for through one helper, so a pool started ahead of time is the
one requests reuse, and it can be kept alive longer than joblib's five idle minutes (the PI,
2026-10-02: keep the pool warm, with reasonable memory limits).

joblib reuses a web worker's pool only when a call asks with the same settings as the call that
started it; a call asking for any other idle time replaces it (watched on the Jetstream2 BRAVO,
2026-10-02: a plain `backend="loky"` call after one with a set idle time started a new pool). So:
  * the idle time is BRAVO_POOL_IDLE_SECONDS, else joblib's own 300 s;
  * no BRAVO module asks for a pool any other way than `parallel.loky_backend()`;
  * two calls through the helper share one pool, which carries the idle time asked for.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

try:
    from modules.DecodeCommon import parallel as P
except ImportError:                                              # the host runner's spelling
    from DecodeCommon import parallel as P

MODULES_ROOT = Path(__file__).resolve().parents[2]
BRAVO_ROOT = MODULES_ROOT.parent


def _idle_with(value):
    old = os.environ.get(P.POOL_IDLE_ENV)
    try:
        if value is None:
            os.environ.pop(P.POOL_IDLE_ENV, None)
        else:
            os.environ[P.POOL_IDLE_ENV] = value
        return P.pool_idle_seconds()
    finally:
        if old is None:
            os.environ.pop(P.POOL_IDLE_ENV, None)
        else:
            os.environ[P.POOL_IDLE_ENV] = old


def test_the_idle_time_defaults_to_joblibs_five_minutes_and_follows_its_variable():
    got = {"unset": _idle_with(None), "3600": _idle_with("3600"), "junk": _idle_with("junk"),
           "zero": _idle_with("0")}
    assert got == {"unset": 300, "3600": 3600, "junk": 300, "zero": 300}, got


def test_the_helper_carries_the_idle_time():
    old = os.environ.get(P.POOL_IDLE_ENV)
    os.environ[P.POOL_IDLE_ENV] = "4321"
    try:
        assert P.loky_backend().backend_kwargs == {"idle_worker_timeout": 4321}
    finally:
        if old is None:
            os.environ.pop(P.POOL_IDLE_ENV, None)
        else:
            os.environ[P.POOL_IDLE_ENV] = old


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
