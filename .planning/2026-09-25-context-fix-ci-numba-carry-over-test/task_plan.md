# Task Plan: Context fix, CI with numba, the carry-over test; then the MATLAB item

## Goal
The participant-context service works for RCS08; CI runs the compiled-filter equality test; the
up-leg/down-leg carry-over test is a saved control analysis; then the options researched and critiqued.

## Next Step
Synthesis across the seven option reports, then the critique agents.

## Current Phase
Phase 4

## Phases

### Phase 1: The participant-context service
- [x] Test RED (no `_already_on_tablet`), fix, test GREEN
- [x] Live: the service returns for RCS08; chronic arrays start at implant
- [x] Suites, record, commit (decision 270)
- **Status:** complete

### Phase 2: numba in CI
- [x] numba 0.61.2 / llvmlite 0.44.0 in the host job's install (decision 271)
- **Status:** complete

### Phase 3: Carry-over (up-leg against down-leg at matched currents)
- [x] Routine, tests, saved control analysis on the Stim Optimizer page
- [x] Live run on RCS08, decision row (272), commit
- **Status:** complete

### Phase 4: Options researched, synthesised, critiqued (the PI's pasted instructions)
- [x] Seven option agents launched (1 regression to the mean, 2 next visit, 3 time rule, 4 band detector, 5 small rulings, 6 speed-ups, 7 MATLAB HamD6)
- [ ] Synthesis across the seven
- [ ] Adversarial critique (1-3 agents)
- [ ] Revised plan with likely problems named; published
- **Status:** in_progress

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| MATLAB work read-only and headless | the PI: no desktop; the other repository is not ours to change |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
