# Task Plan: Context fix, CI with numba, the carry-over test; then the pending work by swarm

## Goal
Items 1-3 done (270-272). Now: every pending and ongoing item worked by agents (the PI, 2026-09-25,
/swarm-execute), RCSchronicpain's open items included, handoff leftovers turned into a to-do list.

## Next Step
Wait for the PI's answers (revised plan section 5; Lane 0 items 0.1-0.3). Open: P-03 two parts, P-20 pickles, P-07 count.

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
- [x] Synthesis across the seven (00_SYNTHESIS.md)
- [x] Adversarial critique: science, feasibility, rulings and language (08-10)
- [x] Revised plan with likely problems named (11_REVISED_PLAN.md, committed)
- **Status:** complete

### Phase 5: Swarm wave 1 (no PI ruling needed)
- [x] Handoff scan: pending items from every earlier handoff, checked against the record, as a to-do list
- [x] RCSchronicpain: pre-merge checks (3 token-shaped values tracked; real dates) and the two plots recoloured, uncommitted
- [x] Regression-to-the-mean check saved (275); the adjusted reading's own shuffle (276)
- [x] Stale pain ratings in the Closed-Loop saved inputs: latent, fixed (273); numba log noise (274)
- [x] Suites, bundle, record, commit and push (5f3fd835, 68074101, 0812eacf)
- **Status:** complete

### Phase 6: Swarm wave 2
- [x] Stale numbers and stale open items corrected (280)
- [x] Harmonic one home, speed-ups, sheet parser (277-281)
- [x] Revised plan run by workflow, verified, committed (282-288)
- **Status:** complete

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
