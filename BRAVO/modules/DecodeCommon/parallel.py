"""ONE worker-pool size for every BRAVO process pool (2026-10-02, the Jetstream2 BRAVO).

joblib keeps a single process pool per process (here: per web worker) and shuts it down and
rebuilds it whenever a call asks for a different size; on the Jetstream2 BRAVO a rebuild cost
1.3-1.5 s, against 0.02 s to reuse a pool of the same size. The Closed-Loop simulation asked for
the core count (64) and the Stim Optimizer's held-out folds and band checks for 15, so a web worker
serving both pages paid a rebuild on every switch. Every pool now asks for `pool_jobs()`: the
core count less one (63 there, 15 on the 16-core Mac, where nothing changes), or BRAVO_POOL_JOBS.
Each use keeps its own variable (STIM_OPTIMIZER_LOO_JOBS, STIM_OPTIMIZER_SCREEN_JOBS,
CLOSED_LOOP_SEGMENT_JOBS) to set it apart. The pool's size never changes an answer: every use
combines its workers' results in the original order (each use's own tests prove it).
"""
import os

POOL_JOBS_ENV = "BRAVO_POOL_JOBS"


def pool_jobs() -> int:
    """The shared worker-pool size: BRAVO_POOL_JOBS, else the core count less one (at least 1)."""
    raw = os.environ.get(POOL_JOBS_ENV, "").strip()
    try:
        n = int(raw) if raw else (os.cpu_count() or 2) - 1
    except ValueError:
        n = (os.cpu_count() or 2) - 1
    return max(1, n)


# HOW LONG AN IDLE POOL STAYS ALIVE, and the one way every pool is asked for (the PI, 2026-10-02:
# keep the pool warm, with reasonable memory limits). joblib closes a pool after 300 idle seconds, so
# a pool started ahead of time (`BRAVO/warmup.py`) was gone five minutes later. BRAVO_POOL_IDLE_SECONDS
# keeps it longer. joblib reuses a pool only when a call asks with the same settings as the call that
# started it (a call naming the loky backend by its name alone after one with a set idle time started a new pool, watched
# on the Jetstream2 BRAVO), so every BRAVO pool asks through `loky_backend()`. The memory a kept pool
# holds is bounded by its size: BRAVO_POOL_JOBS workers per web worker (OPERATIONS_runbook.md).
POOL_IDLE_ENV = "BRAVO_POOL_IDLE_SECONDS"
DEFAULT_IDLE_SECONDS = 300                       # joblib's own


def pool_idle_seconds() -> int:
    """Seconds an idle pool stays alive: BRAVO_POOL_IDLE_SECONDS (a positive whole number), else 300."""
    try:
        n = int(os.environ.get(POOL_IDLE_ENV, "").strip())
    except ValueError:
        return DEFAULT_IDLE_SECONDS
    return n if n > 0 else DEFAULT_IDLE_SECONDS


def loky_backend():
    """joblib's process-pool backend with BRAVO's idle time: pass as `backend=` to every pool call."""
    from joblib.parallel import LokyBackend
    return LokyBackend(idle_worker_timeout=pool_idle_seconds())
