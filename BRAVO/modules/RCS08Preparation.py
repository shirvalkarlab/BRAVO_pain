"""Supervise one sync/report worker within the available maintenance window.

Imports are transactional per neural file and survey batch; Oura publishes a new
snapshot before swapping its pointer. Forced termination therefore retains prior
complete data or committed streams. A final revision invalidation covers the narrow
commit-before-cache-invalidation interval. Orphaned unpublished files can remain.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from threading import Timer
from uuid import uuid4
from filelock import FileLock, Timeout


class PreparationTimeout(RuntimeError):
    pass


def _stop_group(process, *, grace_seconds=4):
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=max(0, grace_seconds))
    except subprocess.TimeoutExpired:
        pass
    # The parent may exit on TERM while a child ignores it. Kill the entire
    # remaining group in either case, so no maintenance calculation outlives it.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def _run_preparation(*, deadline, mode):
    """Run in a child process; cap nightly work at 4h and explicit manual work at 2h.

    No automatic catch-up policy lives here: the scheduler admits scheduled work
    only during 03:00–07:00 Pacific. Explicit manual work gets its own deadline.
    """
    from modules import ReportCache
    now = time.time()
    maximum_seconds = 14400 if mode == "Nightly" else 7200
    deadline = min(float(deadline), now + maximum_seconds)
    if deadline - now <= 5:
        raise PreparationTimeout("No time remains in the preparation window; no worker started.")
    directory = Path(os.environ["DATASERVER_PATH"]) / "sync-state"
    directory.mkdir(parents=True, exist_ok=True)
    token = uuid4().hex
    result_path = directory / f"preparation-{token}.json"
    log_path = directory / f"preparation-{token}.log"
    command = [sys.executable, "manage.py", "prepare_rcs08_cycle", "--deadline", str(deadline),
               "--result", str(result_path)]
    process = None
    try:
        with log_path.open("w") as log:
            log_path.chmod(0o600)
            process = subprocess.Popen(command, cwd=Path(__file__).resolve().parents[1],
                                       stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                process.wait(timeout=max(0, deadline - time.time() - 5))
            except subprocess.TimeoutExpired:
                # Reserve five seconds for shutdown so CPU work stops by the deadline.
                _stop_group(process, grace_seconds=min(4, max(0, deadline - time.time())))
                ReportCache.invalidate(neural=True)
                raise PreparationTimeout(f"{mode} preparation reached its time limit; the worker stopped. Completed streams are retained; remaining work can be retried.")
        if process.returncode != 0:
            ReportCache.invalidate(neural=True)
            raise RuntimeError(f"{mode} preparation failed. See the private preparation log {log_path.name}.")
        result = json.loads(result_path.read_text())
        if not isinstance(result, dict):
            raise RuntimeError("Preparation did not return a valid result.")
        return result
    finally:
        if process is not None and process.poll() is None:
            _stop_group(process)
            ReportCache.invalidate(neural=True)


def preparation_lock():
    path = Path(os.environ["DATASERVER_PATH"]) / "sync-state" / "rcs08-preparation.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    return FileLock(str(path), timeout=0)


def is_preparing():
    lock = preparation_lock()
    try:
        lock.acquire()
    except Timeout:
        return True
    lock.release()
    return False


def run_preparation(*, deadline, mode):
    """Share one lock between the manual worker and the single nightly runner."""
    try:
        with preparation_lock():
            return _run_preparation(deadline=deadline, mode=mode)
    except Timeout as error:
        raise RuntimeError("RCS08 preparation is already running; retry within the maintenance window.") from error


def start_deadline_watchdog(deadline):
    """Keep the child cutoff even if its invoking supervisor is interrupted.

    The process must own its group so this cannot target the caller's shell or
    the persistent manual daemon. The daemon timer lives for the process lifetime,
    including Python's wait for analysis executor threads during shutdown.
    """
    if os.getpgrp() != os.getpid():
        raise RuntimeError("Preparation worker must run in its own supervised process group.")
    group = os.getpgrp()
    timer = Timer(max(0, float(deadline) - time.time()),
                  lambda: os.killpg(group, signal.SIGKILL))
    timer.daemon = True
    timer.start()
    return timer
