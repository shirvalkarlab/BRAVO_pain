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
Done (decision 170): both onset grids capped at 30 s (and a one-answer-per-window-count rule the cap exposed), the
sweep ends at one minute; suites green, live proof, rebuilt, pushed. Review ranks 4-23 remain his call.

## Current Phase
Phase 6

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

### Phase 4: Fix the three Criticals, tests first
- [x] S1 backend: defaulted limits above the ceiling -> not assessed, history named (RED then GREEN)
- [x] S1 frontend: the checks panel says "history, not a proposal"
- [x] C1 backend: E1 carries `source` (screening_historical | pooled_titration), serialised
- [x] C1 frontend: the triangle draws a screening E1 distinctly and labels it
- [x] B1 frontend: n, interval, q on hover and the pinned panel, beside the plain statistic
- [x] B4: device timing ranges from one home (DecodeCommon), on the sweep response, rows tiered on the grid
- [x] Suites (host + container), live field-count proof on RCS08, frontend rebuild, decision-log entry, push
- **Status:** complete

### Phase 5: Tablet ranges reconciled with the documents
- [x] device_ranges: onset (tablet, FDA kept), transitions (WP + tablet), detection blanking, sensing blanking, high-pass, hold horizon
- [x] Closed-Loop card and rules read the corrected ranges (D21 title, blanking row, coupling text)
- [x] Robustness note names onsets above the enterable maximum
- [x] Grid tiers: 45 s-60 s held level, 5 min beyond the device; caveat resolved
- [x] Docs corrected (DEVICE_percept_rc.md, synthesis addendum), decision 169, suites, live proof, rebuild, push
- **Status:** complete

### Phase 6: Onset grids capped at 30 s; sweep capped at one minute
- [x] robustness.ONSET_GRID_S and design_rule.ONSET_GRID_S stop at the tablet's 30 s; rule versions bumped
- [x] BAND_TIME_SWEEP_SECONDS ends at 60 s; the "ten lengths" wording follows the count; sweep rule version bumped
- [x] Suites, live proof, frontend rebuild, decision 170, push
- **Status:** complete

## Decisions Made
| Decision | Reason |
|----------|--------|
| Own plan dir, not the audit's | CLAUDE.md §4: a second independent task gets its own directory |
| Four reviewers, not three | The brief's hardest question (time dynamics + limited data) cuts across all three modules |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
