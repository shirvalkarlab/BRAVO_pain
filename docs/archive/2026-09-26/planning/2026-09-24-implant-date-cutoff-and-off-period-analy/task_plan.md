# Task Plan: Implant-date cutoff, the 0 mA within-stretch test, the dose-history model

## Goal
Nothing dated before the device's implant date reaches any view or product; the PI's two analyses
run from 2025-07-16 on the page's own matching, with the 0 mA sample counted correctly.

## Next Step
None: 260-262 committed and pushed; the PI to read the results.

## Current Phase
Phase 3

## Phases

### Phase 1: Analyses 2 and 3 (read-only probes)
- [x] Probe: band vs pain within each both-off stretch, 60-minute match, NRS and VAS
- [x] Probe: dose-history model and the calibration diagnosis with dose
- [x] Read both outputs and write the counts beside the run
- [x] Re-run decision 240's diagnostic at the page's 60-minute match window
- **Status:** complete

### Phase 2: Implant-date cutoff (code)
- [x] Map every read site of chronic log, therapy history, controller events
- [x] One helper for a participant's first valid time (the implant date)
- [x] Tests first, watched RED
- [x] Filter at the choke points; bump rule versions or keys the change touches
- **Status:** complete

### Phase 3: Proof and record
- [x] Live before/after: field count and difference count on each touched response
- [x] Both suites, jest if page text changes, bundle if Client changes (host 1533 / 2 / 0, container 721 / 0; no Client change)
- [x] Decision row, synthesis corrected (19 reports), commit and push
- **Status:** complete

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Filter at read time, never delete rows | deleting patient data is irreversible; the PI asked for it gone from views and products |
| Implant date from the device record (2025-07-16 18:06 UTC) | the PI confirmed July 16 2025 |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| within-stretch probe crashed: empty bootstrap list in the pooled case | 1 | return NaN when fewer than 100 finite draws |
| before-captures from the copied tree loaded no ratings (pt_config looked up beside the copy) | 1 | BRAVO_PT_CONFIG_DIR pointed at the live folder; so2, clL, bm re-captured |
| cutoff proof moved Stim Optimizer coverage days | 1 | not the cutoff: a stored table's day arrays were miscounted (decision 261); proved with the table rebuilt on both sides |
