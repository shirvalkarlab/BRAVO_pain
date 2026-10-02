"""gunicorn settings shared by both BRAVOs (the Mac and the Jetstream2 server).

gunicorn reads `./gunicorn.conf.py` from the folder it is started in when no `-c` is given. Both
container commands start it in /usr/src/BRAVO (this folder, mounted live), so both pick this file up
at the next start of gunicorn's main process (`kill -HUP 1` in the container, or a restart); no
compose file changes. Options on the command line (`-w`, `--timeout`, `--reload` ...) still win.

Only one thing is set here: each new web worker is warmed (`BRAVO/warmup.py`: R started, the numba
loops compiled, the libraries a request imports loaded) after Django is set up and before the worker
accepts a request (speed-up item B9, 2026-10-02). `BRAVO_WARMUP=0` in the environment turns it off.
Keep this file free of imports at the top: gunicorn's main process reads it too.
"""


def post_worker_init(worker):
    """Runs in each new web worker, once, before it serves anything. Never stops a worker starting."""
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
