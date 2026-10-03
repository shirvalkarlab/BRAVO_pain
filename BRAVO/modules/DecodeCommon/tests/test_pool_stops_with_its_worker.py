"""A web worker's pool stops when the worker does (2026-10-03).

Reloading gunicorn (`kill -HUP 1`) replaced the workers but left each one's joblib pool running with
no parent: on 2026-10-02, 850 processes holding 84 GB on the Jetstream2 BRAVO, which pushed the host
to 240 of 245 GB and the kernel killed part of the desktop. Reproduced on a separate test gunicorn in
the container (1 worker, a 2-process pool): one HUP left 2 processes with no parent. The pool is
kept for a day on purpose (`BRAVO_POOL_IDLE_SECONDS`), so nothing else ends it; `shutdown_pool()`
does, and gunicorn's `worker_exit` hook calls it.
"""
import time
from pathlib import Path

try:
    from modules.DecodeCommon import parallel as P
except ImportError:                                        # pragma: no cover - flat path layout
    from DecodeCommon import parallel as P


def _alive(pids):
    try:
        import psutil
    except ImportError:                                    # a host without psutil (the Mac may lack it)
        import os
        out = []
        for p in pids:
            try:
                os.kill(p, 0)
                out.append(p)
            except OSError:
                pass
        return out
    out = []
    for p in pids:
        try:
            if psutil.Process(p).status() != psutil.STATUS_ZOMBIE:
                out.append(p)
        except psutil.NoSuchProcess:
            pass
    return out


def test_shutdown_pool_stops_the_reusable_pools_processes():
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


def test_shutdown_pool_with_no_pool_is_quiet():
    P.shutdown_pool()
    assert P.shutdown_pool() in (True, False)


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
    import signal
    import subprocess
    import sys
    root = str(Path(__file__).resolve().parents[3])
    p = subprocess.Popen([sys.executable, "-c", _CHILD, root], stdout=subprocess.PIPE, text=True)
    pids = [int(x) for x in p.stdout.readline().split()]
    assert pids
    assert p.wait(timeout=30) == -signal.SIGTERM        # still ended by the signal, as before
    deadline = time.time() + 15
    while _alive(pids) and time.time() < deadline:
        time.sleep(0.2)
    assert _alive(pids) == []
