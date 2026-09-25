# Task Plan: Context fix, CI with numba, the carry-over test; then the pending work by swarm

## Goal
Items 1-3 done (270-272). Now: every pending and ongoing item worked by agents (the PI, 2026-09-25,
/swarm-execute), RCSchronicpain's open items included, handoff leftovers turned into a to-do list.

## Next Step
Wave 1 running (handoff scan, RCS items, regression-to-the-mean + reproducible p); then critique.

## Current Phase
Phase 5

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
- [x] Seven option agents launched; six reports in, the MATLAB one sent to the PI outside the repo
- [ ] Synthesis across the seven (agent running)
- [ ] Adversarial critique (1-3 agents)
- [ ] Revised plan with likely problems named; published
- **Status:** in_progress

### Phase 5: Swarm wave 1 (no PI ruling needed)
- [ ] Handoff scan: pending items from every earlier handoff, checked against the record, as a to-do list
- [ ] RCSchronicpain: pre-merge checks (no merge, no push), the two plots coloured by condition
- [ ] Regression-to-the-mean check as a saved control analysis (report 1's specification)
- [ ] Decision 262's "p 0.04" made reproducible by the saved analysis
- [ ] Suites, bundle, record, commit and push for each BRAVO change
- **Status:** in_progress

### Phase 6: Swarm wave 2
- [ ] Stale numbers and stale open items in the record corrected (report 5, the handoff scan)
- [ ] Speed-ups from report 6 that keep every value identical, each with its proof
- **Status:** pending

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| MATLAB headless only; nothing merged or pushed in RCSchronicpain without the PI's yes | outward-facing, another repository |
| The other study's figures and report kept out of this repository | they describe that study's patients |
| Agents do not commit; the orchestrator runs suites, commits, pushes | one checkout, one staging area (no worktrees) |
| Items that need a PI ruling become questions, not builds | CLAUDE.md section 8 rule 8 |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
