# Task Plan: PI rulings of 2026-09-21 on the open items

## Goal
Six rulings from the PI (2026-09-21), each built test-first with a live proof and one commit: delete the frozen
June log-log model; pool across pulse widths behind a toggle (option A, default separate); the harmonic rule as a
warning on the readiness screen, never blocking; the matcher's report cap stays out and becomes a warning; delete
the chronic-detector routines with no caller; the full-spectrum matrix keeps rebuilding on a new report (no change).

## Next Step
All six rulings built and recorded (218-222). Nothing queued. For the PI: the audit code leftovers, and the two chronic-detector helpers with no caller.

## Current Phase
Phase 3

### Phase 1: The four small items, cheapest first
- [x] 1. Frozen June log-log model deleted: `psd_lsb_model.py`, its asset, its tests, `load_model`/`estimate_lsb` callers; container suite; live endpoint unchanged
- [x] 2. Chronic-detector routines with zero callers deleted (`sliding_window_analytics`, `power_pain_scatter`, `cluster_scatter`, `pain_binarization`; callers re-grepped first); response 0 differing
- [x] 3. Harmonic rule on the readiness screen: a warning on the row and the table, never a refusal; jest + host tests; live proof
- [x] 4. Matcher report cap (`max_per_rating`) stays off; the shared-report count becomes a warning on the response and the page; live count on RCS08
- **Status:** complete

### Phase 2: Pooling across pulse widths (decision 189's option A)
- [x] Read the current-map fit; design the pooled model (pulse widths as two inputs); tests first
- [x] Toggle on the Stim Optimizer current-map card, default separate; both fits compared on RCS08 with the three checks' numbers
- **Status:** complete

### Phase 3: Record
- [x] Decisions 218+ appended to the digest and the full log; the 217 clinic implication kept verbatim; suites; push
- **Status:** complete

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| The matrix keeps rebuilding on a new report | the PI: the data will be different (audit B item A2 closed, design 53 stands) |
| Audit code leftovers wait | the PI: handle them afterwards |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
