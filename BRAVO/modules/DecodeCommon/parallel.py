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
