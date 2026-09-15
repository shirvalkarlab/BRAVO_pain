# Task Plan: Clinician adversarial review of the three modules

## Goal
An adversarial review, written from the seat of a clinician who will program a Percept RC by hand
for closed-loop DBS in chronic pain, of (1) the Biomarkers module -- is its analysis rigorous and
actionable for in-clinic and at-home sessions; (2) the Stim Optimizer -- does it collect the data
that resolves the questions closed-loop deployment needs answered; (3) Closed-Loop Deployment --
are its recommendations complete against the device's real capabilities and honest about the
patient's time dynamics and thin, fluctuating data. Name the main shortcomings with concrete fixes
(backend, frontend, or documentation), each tied to a file:line, a test, or a live number.

## Next Step
Done: report written, page published (https://claude.ai/artifact/2B71nChGmAnXaxyYe1NMiQ), decision 167
logged, committed and pushed. Nothing queued; every fix is his call (rule 8).

## Current Phase
Phase 3

### Phase 1: Parallel review
- [x] Biomarkers reviewer dispatched and returned
- [x] Stim Optimizer reviewer dispatched and returned
- [x] Closed-Loop Deployment reviewer dispatched and returned
- [x] Cross-cutting (time dynamics, data sufficiency, Percept limits) reviewer dispatched and returned
- **Status:** complete

### Phase 2: Interrogate and root-cause
- [x] Verify every Critical/High finding against the code or a live number before keeping it
- [x] Adversarial questions on the four reports; drop anything not evidenced
- [x] Five Whys on the systemic issues that recur across modules
- **Status:** complete

### Phase 3: Report
- [x] `artifacts/review_2026-09-15_clinician_three_modules.md` in house style, with ranked fixes
- [x] Published artifact page; decision-log entry; commit + push per bravo-session-rules Rule 4
- **Status:** complete

## Decisions Made
| Decision | Reason |
|----------|--------|
| Own plan dir, not the audit's | CLAUDE.md §4: a second independent task gets its own directory |
| Four reviewers, not three | The brief's hardest question (time dynamics + limited data) cuts across all three modules |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
