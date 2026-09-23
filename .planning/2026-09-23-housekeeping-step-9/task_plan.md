# Task Plan: Housekeeping, step 9 of the panels' build order

## Goal
The last six items of the panels' build order: the effective count on the grid, the grid null's
own reconciliation check, the time-of-day diagnostic, the whole-search paragraph, the coverage
wording, and the Closed-Loop response's unread fields (A-4, A-3, A-9, A-2, B-6, D-10).

## Next Step
None: the panels' build order is finished; what comes next is the PI's to choose.

### Phase 1: Backend
- [x] D-10: `protocol`, `edges_historical` and three duty-cycle fields leave the Closed-Loop response (3 tests, RED first)
- [x] A-4: `n_pain_reports_effective` on each circled cell, rule v22 (3 tests, RED first)
- [x] A-3: `null_family_reconciliation` on each grid, the null unchanged (4 tests, RED first; 4,281 values, 0 differing)
- **Status:** complete

### Phase 2: Page and record
- [x] A-4 on the hover and panel line (3 jest, RED first)
- [x] A-2 line in the drawer (referent test extended, RED first)
- [x] B-6 in report B, both occurrences, citations corrected to §8
- [x] A-9 script with a self-test, force-added under the bridge folder
- [x] Bundle rebuilt (63.257cb08b)
- **Status:** complete

### Phase 3: Proof and record
- [x] Host suite; Biomarkers tests runnable here (same 28 environment failures before and after); jest
- [x] The live proof on the PI's machine: Closed-Loop 1,299 fields removed per side, all in the
      three named groups; grid 216 added, 0 correlation values moved, the stability column
      awaiting its rebuild under the new key; the time-of-day table recorded in decision 246;
      container 709 / 0, host 1475 / 2 / 0
- **Status:** complete

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| The unread fields leave the served response only; `rep.protocol` is still built | it can add a blocker if it fails, and removing that path is a behaviour change nobody asked for |
| The effective count prints inside the ratings phrase of the hover | the PI's hover ruling of 2026-09-16 ("X ratings, q = Y") is kept, only X gains its qualifier |
| The null's arithmetic is one function run on the shuffles and on the unshuffled scores | the check must compare the grid with the family the shuffles actually ran on, not a second copy |
| The time-of-day check is a script, not a routine | panel A: nothing ships and nothing reads it; a routine reached by nothing is what this project removes |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| Report B cited the coverage table as §6 and §4 of the device document; it is §8 | 1 | both citations corrected with the wording |
