# Findings & Decisions

## Requirements
-

## Research Findings
-

## Technical Decisions
| Decision | Rationale |
|----------|-----------|

## Issues Encountered
| Issue | Resolution |
|-------|------------|

## Resources
-

## 2026-10-01: Stim Optimizer "3.5 s of sleeping" (item B2) is not waste
_prof_so2.pstats callers of time.sleep: threading.wait (151 calls, 1.44 s), selectors.select (1.16 s), multiprocessing _send, joblib parallel _retrieve. The main thread blocks while the loky leave-one-out workers compute (surrogate.loo_predict_many). Nothing to remove; B2 dropped.

## Jetstream2 worker threads after A2 (2026-10-01)
- Each Jetstream2 web worker has 59 threads, the main process 5. Not maths threads: threadpoolctl shows both OpenBLAS copies at 1 thread.
- 56 are started by blosc2 at import (modules.Database imports it; pool sized to the 64 cores), 1 by pyarrow (jemalloc), via pandas.
- blosc2 is used only to uncompress stored recordings (Database.py, DataCurator.py) and one compress (not byte-repeatable, per Database.py's comment). Idle between requests.
- Relevant to B4 (decode in processes): N processes x 56 blosc2 threads. Consider BLOSC_NTHREADS there, with its own proof. Not changed now.

## Phase 9 sizing, Jetstream2, 2026-10-02 (measured)
- Idle web worker: 204 MB (17 gunicorn processes, 3.2 GB in all).
- One two-stage request: 32 loky pool workers at a median 174 MB; request + pool peak 10.8 GB.
- Each web worker keeps its own loky pool alive 5 idle minutes: a web worker with 64 pool workers holds ~11 GB; 16 recently busy web workers could hold ~178 GB of idle pool workers, plus the recording cache (decision 359, up to 6 GB each = 96 GB). Worst case exceeds 245 GB -> cap pool size per web worker and/or the recording budget once the agents' changes are in (they add pools).

## Held-out pool size, Jetstream2, 2026-10-02
- Two-stage request warm, side by side: STIM_OPTIMIZER_LOO_JOBS=48 35.2 s vs 15 35.8 s; 64,212 values, 0 analysis values differ. Each fit's held-out folds wait on the slowest fold and the fits run in sequence, so more workers stay idle. Keep 15.
- Warm, all changes so far + recording cache: two-stage ~35 s (52.4 at start of 2026-10-02), Closed-Loop ~27-29 s (42.4), heat-map grid 7.8 s (9.4). Remaining two-stage time is mostly GP refits (12 seeded restarts each); faster only with a different fitting method, which would change numbers.
