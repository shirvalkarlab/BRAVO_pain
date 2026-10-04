"""One helper process per web worker, for work that can run beside a request (the PI, 2026-10-04,
decision 427: run the stability model in a second process).

Pinned: the helper returns what the call returns in-process; a helper whose parent dies -- even
killed outright, which no exit hook sees -- exits by itself within a few seconds (the 2026-10-02
reload left 850 orphaned pool processes holding 84 GB); `shutdown_pool`, which every existing exit
path already calls, stops the helper too; switched off, nothing is started and the caller computes
in-process.
"""
import os
import signal
import subprocess
import sys
import textwrap
import time

from DecodeCommon import side_process as SP
from DecodeCommon import parallel as PAR


def test_the_helper_returns_what_the_call_returns_here():
    fut = SP.submit(sorted, [3, 1, 2])
    assert fut is not None and fut.result(timeout=60) == [1, 2, 3]
    assert SP.helper_pid() not in (None, os.getpid())


def test_shutdown_pool_stops_the_helper():
    SP.submit(sorted, [1]).result(timeout=60)
    pid = SP.helper_pid()
    assert pid is not None
    PAR.shutdown_pool()
    for _ in range(50):
        if not _alive(pid):
            break
        time.sleep(0.1)
    assert not _alive(pid)
    assert SP.helper_pid() is None


def test_switched_off_nothing_is_started():
    SP.shutdown()
    old = SP.ENABLED
    SP.ENABLED = False
    try:
        assert SP.submit(sorted, [2, 1]) is None
        assert SP.helper_pid() is None
    finally:
        SP.ENABLED = old


def _alive(pid):
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    try:                                          # a zombie is not alive
        with open(f"/proc/{pid}/stat") as fh:
            return fh.read().split()[2] != "Z"
    except OSError:
        return False


def test_a_helper_whose_parent_is_killed_outright_exits_by_itself():
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    code = textwrap.dedent(f"""
        import sys, time
        sys.path.insert(0, {here!r})
        from DecodeCommon import side_process as SP
        SP.submit(sorted, [1]).result(timeout=60)
        print(SP.helper_pid(), flush=True)
        time.sleep(600)
    """)
    p = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)
    helper = int(p.stdout.readline().strip())
    assert _alive(helper)
    os.kill(p.pid, signal.SIGKILL)
    p.wait()
    for _ in range(100):
        if not _alive(helper):
            break
        time.sleep(0.1)
    assert not _alive(helper), "the helper outlived its parent"


def test_the_helper_does_not_rerun_an_unguarded_main_script():
    """A main script with work at its top level (the plain-assert runner is one) must not be run
    again in the helper: it ran the whole suite there and broke the pool (2026-10-04)."""
    import tempfile
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    d = tempfile.mkdtemp()
    log = os.path.join(d, "imports.txt")
    script = os.path.join(d, "unguarded.py")
    with open(script, "w") as fh:
        fh.write(textwrap.dedent(f"""
            import sys
            sys.path.insert(0, {here!r})
            open({log!r}, "a").write("imported\\n")
            from DecodeCommon import side_process as SP
            print(SP.submit(sorted, [2, 1]).result(timeout=60))
            SP.shutdown()
        """))
    out = subprocess.run([sys.executable, script], capture_output=True, text=True, timeout=120)
    assert "[1, 2]" in out.stdout, out.stderr[-2000:]
    with open(log) as fh:
        assert fh.read().count("imported") == 1
