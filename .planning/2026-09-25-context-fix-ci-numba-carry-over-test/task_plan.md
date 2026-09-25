# Task Plan: Context fix, CI with numba, the carry-over test; then the MATLAB item

## Goal
The participant-context service works for RCS08; CI runs the compiled-filter equality test; the
up-leg/down-leg carry-over test is a saved control analysis; then the PI's pending MATLAB item.

## Next Step
Check the context service's live output, then commit item 1.

## Current Phase
Phase 1

## Phases

### Phase 1: The participant-context service
- [x] Test RED (no `_already_on_tablet`), fix, test GREEN
- [ ] Live: the service returns for RCS08; chronic arrays start at implant (decision 263's unproved part)
- [ ] Suites, record, commit
- **Status:** in_progress

### Phase 2: numba in CI
- [ ] Add numba 0.61.2 / llvmlite 0.44.0 to the host job's install; the equality test runs there
- **Status:** pending

### Phase 3: Carry-over (up-leg against down-leg at matched currents)
- [ ] Routine, tests, saved control analysis on the Stim Optimizer page
- **Status:** pending

### Phase 4: The MATLAB item
- [ ] Find what the PI means; do it
- **Status:** pending

## Decisions Made
| Decision | Rationale |
|----------|-----------|

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
