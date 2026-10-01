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
