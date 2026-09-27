# Task Plan: The cell drill-down matches the same ratings as the grid

## Goal
The heat-map cell's scatter and violin come from the same pain ratings the grid correlated: the drill-down merges the clinic-sheet ratings when the switch is on, tags each point by source, and a test proves its n and Pearson r equal the grid's cell.

## Next Step
None: closed (decision 228).

## Current Phase
Phase 1

### Phase 1: Build
- [x] Container test: grid cell n and r equal the drill-down's point count and Pearson r with the switch on (RED first)
- [x] `band_time_sweep_cell_for_participant` reads the switch, merges the sheet ratings as the grid does, tags points `from_clinic_sheet`
- [x] Scatter marks sheet points; live before/after on the PI's cell; suites; bundle; decision row; push
- **Status:** complete

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Fix on the backend, not by shipping the grid's slope | the drill-down's contract is "the pairs behind that cell"; the violin's labels need the same pairs too |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
