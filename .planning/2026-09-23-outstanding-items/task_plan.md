# Task Plan: The outstanding items after the panels' build order

## Goal
Build what the 2026-09-23 audit found outstanding, in the order agreed with the PI ("go in your
order"): stability column, ruling 8 with the sign-off identity, the parameter-card heading and the
two stale page tests, the next-visit list on the titration card, then the two diagnostics.

## Next Step
None: every item of the 2026-09-23 audit is built; what comes next is the PI's to choose.

## Phases

### Phase 1: The stability column
- [x] Store keeps one answer per grid; the Closed-Loop card reads its own grid's answer and the clinic-sheet switch (decision 248, 760f1966)
- **Status:** complete

### Phase 2: Ruling 8 and the sign-off identity (D-8)
- [x] Server record of the chosen band: table, read/choose/clear, endpoint (10 tests RED first; live, rolled back)
- [x] The page reads the server record on open and writes it on every choice and clear (7 jest RED first)
- [x] The sign-off card prints the band, who chose it, where it is held, and its grid (5 jest RED first)
- [x] Bundle rebuilt (732.8eb74a0b), live in the pane, decision 249
- **Status:** complete

### Phase 3: Page wording and test debt
- [x] D-7: one heading per row, counting that row's notes (no row carries four) (decision 250)
- [x] The two stale Closed-Loop page tests updated; jest 226 / 226 (decision 250)
- **Status:** complete

### Phase 4: What the next visit must deliver, on the page
- [x] `coverage_gap` on every failing per-rate row and on the current-map card (decision 251)
- **Status:** complete

### Phase 5: The two diagnostics
- [x] B-3: level shifts in the chronic log at held left-side changes; 4 of 21 readable (decision 252)
- [x] C-3: the main 55 Hz surface moves between blocks of time; the rest thin data; no kernel (decision 253)
- **Status:** complete

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| The chosen band lives in its own append-only table, created on first use, like the store's ledger | a migration is a manual deployment step here; a history answers "what was chosen when, by whom" |
| Unlike the ledger, a failed save is reported to the page | the page must say when a choice lives in this browser only |
| A grid-chosen band's empty label is left alone (the summary's defaults) | it changes what the deployment summary computes; the PI's to rule on, reported in 249 |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
