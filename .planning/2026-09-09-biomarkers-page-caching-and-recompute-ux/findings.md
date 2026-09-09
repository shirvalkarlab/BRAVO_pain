# Findings & Decisions

## Requirements
- Three user-reported problems on the Biomarkers page, in the user's own words: recompute-on-every-
  navigation for the calibrated grid; two Recompute controls; pain-score dropdown switch always
  costs a real recompute instead of using an already-computed result.

## Research Findings
See task_plan.md Phase 1 for the full root-cause writeup per issue, confirmed by direct reading of
`Client/src/database/resultCache.js`, `Client/src/database/useCachedResult.js` (both do-not-edit,
read only), `Client/src/views/Reports/moduleCacheKeys.js`, `Client/src/views/Reports/Biomarkers/
index.js`, and `Client/src/views/Reports/Biomarkers/BiomarkerHeatmapGrids.js`.

Key facts that shaped the design:
- `resultCache` holds exactly ONE entry per `(moduleKey, uid)` slot; a settings-key mismatch marks
  it stale, it does not create a second entry. To hold 6 simultaneously-valid pain-score results,
  each metric needs its OWN moduleKey/slot, not one shared slot.
- `moduleCacheKeys.js` already exists specifically to extend `resultCache` with multiple named slots
  per page (the Closed-Loop Deployment family), and already provides `recomputeSlots()`, a
  documented workaround for a known double-fetch defect in `useCachedResult.js` itself (its own
  header names the defect and says calling code should use `recomputeSlots` until the hook's owner
  fixes it). This project's own precedent is to build on that helper, not re-derive the same fix.
- `BiomarkerHeatmapGrids.js`'s fetch effect already implements a real, deliberate asymmetric update
  rule (PRD §3): a change to matching settings replaces both grids; a change to only binarization
  settings replaces the AUC grid alone (correlation's object identity is kept so its frame does not
  redraw). This logic must survive the caching rewrite unchanged.

## Technical Decisions
See task_plan.md's Decisions Made table.

## Issues Encountered
| Issue | Resolution |
|-------|------------|

## Resources
- `DECISIONS_and_open_items.md` decisions 62, 66 (the calibrated grid's own design and the
  correlation/binarization asymmetry it must preserve).
