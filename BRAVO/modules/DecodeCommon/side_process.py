"""ONE HELPER PROCESS PER WEB WORKER, for work that can run beside a request (the PI, 2026-10-04,
decision 427: run the Closed-Loop report's stability model in a second process).

Python runs one calculation at a time per process, and the stability model's R calls hold that
lock too, so a thread would not overlap it with the rest of the report. A helper process does. It
is started the first time it is asked for (one per web worker, kept for the worker's life, so its
imports are paid once) and is a fresh interpreter ("spawn"), never a fork of a worker holding
database connections and threads.

NO ORPHANS. On 2026-10-02 one reload left 850 pool processes with no parent, holding 84 GB. Two
guards: `DecodeCommon.parallel.shutdown_pool`, which every exit path of a worker already calls
(gunicorn's `worker_exit`, and the reload signals), stops this helper too; and the helper checks
once a second that its parent is still the process that started it and exits if not, which also
covers a parent killed outright, which no exit hook sees.

`submit` returns a future, or None when the helper is switched off (`ENABLED`) or cannot be
started; the caller then computes in-process, as before.
"""
import os
import threading

ENABLED = True
_EXEC = None
_LOCK = threading.Lock()
_LOCK_START = threading.Lock()      # one submit at a time while the main script is hidden


def _watch_parent(parent_pid):
    import time
    while True:
        if os.getppid() != parent_pid:
            os._exit(0)
        time.sleep(1.0)


def _child_init(parent_pid, sys_path):
    import sys
    for p in reversed(sys_path):
        if p not in sys.path:
            sys.path.insert(0, p)
    threading.Thread(target=_watch_parent, args=(parent_pid,), daemon=True).start()
    if os.environ.get("DJANGO_SETTINGS_MODULE"):
        try:
            import django
            django.setup()
        except Exception:                                      # noqa: BLE001 -- not a Django task
            pass


def _executor():
    global _EXEC
    with _LOCK:
        if _EXEC is None:
            import multiprocessing
            import sys
            from concurrent.futures import ProcessPoolExecutor
            _EXEC = ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context("spawn"),
                                        initializer=_child_init,
                                        initargs=(os.getpid(), list(sys.path)))
        return _EXEC


class _MainHidden:
    """While the helper starts, hide the parent's main script from Python's "spawn": it imports
    that script again in the new process to restore its functions, and a script with work at its
    top level (the plain-assert test runner) then ran that work in the helper and broke it
    (2026-10-04). The helper's tasks live in importable modules and never need the main script.
    The helper is started inside `submit`, which is where the hiding is applied."""

    def __enter__(self):
        import sys
        self.main = sys.modules.get("__main__")
        self.saved = {}
        for name in ("__file__", "__spec__"):
            if self.main is not None and hasattr(self.main, name):
                self.saved[name] = getattr(self.main, name)
        if self.main is not None:
            if "__file__" in self.saved:
                delattr(self.main, "__file__")
            self.main.__spec__ = None
        return self

    def __exit__(self, *exc):
        if self.main is not None:
            for name, value in self.saved.items():
                setattr(self.main, name, value)
            if "__spec__" not in self.saved and hasattr(self.main, "__spec__"):
                try:
                    delattr(self.main, "__spec__")
                except AttributeError:
                    pass
        return False


def submit(fn, *args, **kwargs):
    """``fn(*args, **kwargs)`` in this worker's helper: a future, or None (compute in-process)."""
    if not ENABLED:
        return None
    try:
        with _LOCK_START, _MainHidden():
            return _executor().submit(fn, *args, **kwargs)
    except Exception:                                          # noqa: BLE001 -- the caller computes
        shutdown()
        return None


def helper_pid():
    """The helper's process id, or None when none is running."""
    ex = _EXEC
    if ex is None:
        return None
    procs = getattr(ex, "_processes", None) or {}
    return next(iter(procs), None)


def shutdown():
    """Stop the helper, if one is running. Never raises."""
    global _EXEC
    with _LOCK:
        ex, _EXEC = _EXEC, None
    if ex is None:
        return False
    try:
        procs = list((getattr(ex, "_processes", None) or {}).values())
        ex.shutdown(wait=False, cancel_futures=True)
        for p in procs:
            try:
                p.terminate()
                p.join(timeout=5)
            except Exception:                                  # noqa: BLE001
                pass
        return True
    except Exception:                                          # noqa: BLE001
        return False
