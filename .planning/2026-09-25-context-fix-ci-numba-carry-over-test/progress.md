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
- Seven option agents launched; reports in `artifacts/research_2026-09-25_options/`. Done: 1, 2, 3, 4, 5.

### Test Results
| Test | Expected | Actual | Status |
|------|----------|--------|--------|
| host suite after 272 | 0 failed | 1565 passed / 2 skipped / 0 failed | pass |
| container suite after 272 | 0 failed | 757 passed / 0 failed | pass |
| jest after 272 | 0 failed | 251 of 251, 40 suites | pass |

### Errors
| Error | Resolution |
|-------|------------|
| the bridge queued jobs behind the speed-up agent's probes | waited for each outbox file before relying on it |
