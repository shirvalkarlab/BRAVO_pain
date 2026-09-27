# Task Plan: Control analyses, saved and shown on the page they belong to

## Goal
A "Control analyses" card with a dropdown on the Biomarkers and Stim Optimizer pages, drawing saved,
dated results of the PI's control analyses; first 1 (0 mA), 2 (current explains), 4 (current with
memory), each with the literature link; then 3 (time of day) and 5 (on/off switches).

## Next Step
None: 264-265 committed and pushed.

## Current Phase
Phase 1

## Phases

### Phase 1: Backend package
- [x] `modules/ControlAnalyses/`: registry (key, page, title, literature links), snapshot save/list/load
- [x] Statistical cores as tested functions (within-stretch Spearman with day resampling, BH, dose history, held-out tau curve)
- [x] Runners for 1, 2, 4 that reuse the modules' own matching and save a snapshot
- [x] Tests on constructed data, RED first; add the package to both runners and CI
- **Status:** complete

### Phase 2: Live runs and endpoint
- [x] Run 1, 2, 4 on RCS08 through the bridge; check the saved numbers against the probes of 2026-09-24
- [x] `/queryControlAnalyses` (list, get) behind the participant-access check
- **Status:** complete

### Phase 3: Page card
- [x] `ControlAnalysesCard.js`: dropdown, stamp, figure per analysis, reading, literature link
- [x] On the Biomarkers and Stim Optimizer pages, at the bottom; jest RED first; bundle rebuilt
- [x] Watched live in the browser pane
- **Status:** complete

### Phase 4: Entries 3 and 5
- [x] Time of day and weekends (decision 246's check) as a saved result
- [x] Pain around each on/off switch as a saved result
- **Status:** complete

### Phase 5: Record
- [x] Decision rows, both suites, jest, commit and push
- **Status:** complete

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Saved results, never recomputed on page load | the PI, 2026-09-24: a result for posterity must not change silently |
| Snapshots are files under the data server path, not the cache store | the store keeps the newest entry and can be switched off; these are records |
| Only aggregates saved (counts, correlations, intervals, date ranges) | no individual rating leaves the record |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| stretch finder split a stretch at clinic visits | 1 | runs under a day take the kind of the run before |
| figures drew black: the inks are a named export | 1 | OKABE_ITO imported; jest requires a colour on every mark |
| a switch printed as an end and a start | 1 | one switch per moment, named by the side that changed |
