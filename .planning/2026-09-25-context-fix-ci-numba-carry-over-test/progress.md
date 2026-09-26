# Progress Log

## Session: 2026-09-25

### Current Status
- **Phase:** 4 - options researched, synthesised, critiqued
- **Started:** 2026-09-25

### Actions Taken
- Decision 270 (`97564b1b`): the participant-context service works for RCS08 again.
- Decision 271 (`a42d4517`): CI installs numba 0.61.2 / llvmlite 0.44.0.
- Decision 272 (`6ffb17cc`): the carry-over test saved as `carry_over_ladder` on the Stim Optimizer page.
  Live RCS08: one visit (2026-09-16) with a current rated on both legs, 8 currents, every fall after
  its rise; left ladder -0.75, right +1.00 (down minus up, overall score); held re-rating -0.06
  (-0.26 to +0.27), 62 times on 13 visits.
- Seven option agents; synthesis (00); three critiques (08-10); revised plan drafted (11).
- /swarm-execute (the PI): handoff scan (44 BRAVO handoffs: 21 pending, 20 need the PI); RCSchronicpain
  pre-merge checks (3 token-shaped values tracked, real dates in 52 CSVs) and plots recoloured, uncommitted.
- 273 (`5f3fd835`): saved Closed-Loop inputs held pain under a recording-only key; latent (0 values
  differed), fixed; 59,169 fields, 3 differing (timing). 274 (`68074101`): numba DEBUG log silenced.
- 275, 276 (`0812eacf`): regression to the mean (the swing is the group's: 84.6% of 75,582 splits);
  the adjusted reading's own shuffle, L 1-3+ p 0.030 / 0.035, about 0.21 over the 12 combinations.
- Wave 2 running: one harmonic check (P-01: Stim Optimizer misses the folded 25 and 30 Hz at 55 Hz),
  speed-ups 1-2, the log-power label and stale documents.

### Test Results
| Test | Expected | Actual | Status |
|------|----------|--------|--------|
| host suite after 272 | 0 failed | 1565 passed / 2 skipped / 0 failed | pass |
| container suite after 272 | 0 failed | 757 passed / 0 failed | pass |
| jest after 272 | 0 failed | 251 of 251, 40 suites | pass |
| host / container after 273-276 | 0 failed | 1587 / 2 / 0; 777 / 0 | pass |
| jest after 275 | 0 failed | 253 of 253, 40 suites | pass |

### Errors
| Error | Resolution |
|-------|------------|
| the bridge queued jobs behind the speed-up agent's probes | waited for each outbox file before relying on it |
| first logging test passed without the fix (pytest logs at WARNING) | set root to DEBUG as the server does; RED, then fix |
- 2026-09-25 night: built, uncommitted (all commits held until the tile fix lands): P-03 (a, b), P-20 re-save + version test, Q4 dagger + pooled-fit checks, Q10 per-file settings history, band detector 5a-c, TD/PSD heat-map line + page vocabulary, protocol revision, calibration figures moved, 18 June mock-ups staged for removal. Found: short shared tile copy (findings.md).
