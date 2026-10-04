"""gunicorn settings shared by both BRAVOs (the Mac and the Jetstream2 server).

gunicorn reads `./gunicorn.conf.py` from the folder it is started in when no `-c` is given. Both
container commands start it in /usr/src/BRAVO (this folder, mounted live), so both pick this file up
at the next start of gunicorn's main process (`kill -HUP 1` in the container, or a restart); no
compose file changes. Options on the command line (`-w`, `--timeout`, `--reload` ...) still win.

Each new web worker is warmed (`BRAVO/warmup.py`: R started, the numba
loops compiled, the libraries a request imports loaded) after Django is set up and before the worker
accepts a request (speed-up item B9, 2026-10-02). `BRAVO_WARMUP=0` in the environment turns it off.
And when gunicorn starts, the loop that rebuilds saved band answers after data change is launched
(`when_ready`, decision 435; `SAVED_ANSWERS_REFRESH=0` turns it off).
Keep this file free of imports at the top: gunicorn's main process reads it too.
"""


def when_ready(server):
    """Runs once in gunicorn's main process when it starts (not on a reload). Starts the loop that
    works saved band answers out again when a participant's data change (decision 435). The
    Jetstream2 server starts gunicorn directly, not through `_agent_bridge/boot.sh`, so this is
    where the loop starts there; the loop's own pid lock stops a second copy where both run.
    `SAVED_ANSWERS_REFRESH=0` turns it off. Never stops gunicorn starting."""
    import os
    import subprocess
    if os.environ.get("SAVED_ANSWERS_REFRESH", "1") == "0":
        return
    here = os.path.dirname(os.path.abspath(__file__))
    loop = os.path.join(here, "_agent_bridge", "saved_answers_refresh_loop.sh")
    logs = os.path.join(here, "_agent_bridge", "logs")
    try:
        if not os.path.isfile(loop):
            return
        os.makedirs(logs, exist_ok=True)
        with open(os.path.join(logs, "saved_answers_refresh.boot.log"), "ab") as out:
            proc = subprocess.Popen(["bash", loop], stdout=out, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL, start_new_session=True)
        server.log.info("BRAVO saved-answer refresh loop launched (pid %s)", proc.pid)
    except Exception as exc:                                   # noqa: BLE001
        try:
            server.log.warning("BRAVO saved-answer refresh loop not started: %s: %s",
                               type(exc).__name__, exc)
        except Exception:                                      # noqa: BLE001
            pass


def post_worker_init(worker):
    """Runs in each new web worker, once, before it serves anything. Never stops a worker starting."""
    # The worker's pool must stop before a reload's SIGTERM ends the worker (2026-10-03): that path
    # skips worker_exit below (see `DecodeCommon.parallel.stop_pool_on_signals`).
    try:
        try:
            from DecodeCommon.parallel import stop_pool_on_signals
        except ImportError:
            from modules.DecodeCommon.parallel import stop_pool_on_signals
        stop_pool_on_signals()
    except Exception as exc:                                   # noqa: BLE001
        try:
            worker.log.warning("BRAVO pool signal handler not installed: %s: %s", type(exc).__name__, exc)
        except Exception:                                      # noqa: BLE001
            pass
    try:
        from BRAVO.warmup import warm_up
        report = warm_up()
        worker.log.info("BRAVO warm-up: %s s, %s", report.get("seconds"),
                        {k: (v.get("seconds"), v.get("ok")) for k, v in report.get("steps", {}).items()})
    except Exception as exc:                                   # noqa: BLE001
        try:
            worker.log.warning("BRAVO warm-up skipped: %s: %s", type(exc).__name__, exc)
        except Exception:                                      # noqa: BLE001
            pass


def worker_exit(server, worker):
    """Runs in each web worker as it exits (a reload, a timeout, a stop): stops the worker's process
    pool, which is kept for a day and would otherwise outlive the worker with no parent (2026-10-02:
    one reload left 850 such processes, 84 GB). Never stops the exit."""
    try:
        try:
            from DecodeCommon.parallel import shutdown_pool
        except ImportError:
            from modules.DecodeCommon.parallel import shutdown_pool
        stopped = shutdown_pool()
        worker.log.info("BRAVO pool at worker exit: %s", "stopped" if stopped else "none running")
    except Exception as exc:                                   # noqa: BLE001
        try:
            worker.log.warning("BRAVO pool at worker exit not stopped: %s: %s", type(exc).__name__, exc)
        except Exception:                                      # noqa: BLE001
            pass
