# Session handoff — 2026-09-05 — wiring the three analysis views onto the shared result cache

## What the PI asked for

That results and plots persist across switching between the three module views, instead of
recomputing from scratch every time a module is clicked in the sidebar; that a Recompute control be
added, turning red when settings change or a new biomarker is identified; and that the modules
retain and show the most recent run unless the reader presses Recompute or the server restarts.

The store, the hook and the control (`Client/src/database/resultCache.js`,
`Client/src/database/useCachedResult.js`, `Client/src/views/Reports/RecomputeBar.js`) were written
by the PI before this session and were NOT modified. This session wired the three views onto them,
fixed the plot-persistence half of the request, reconciled the biomarker view's own heavy cache
away, and added tests.

## What changed, by file

**New**

| File | What it is |
|---|---|
| `Client/src/views/Reports/moduleCacheKeys.js` | The seven cache slots the deployment family occupies, plus `markClosedLoopFamilyStale` and the single-request `recomputeSlots`. |
| `Client/src/views/Reports/ClosedLoopSim/PanelStaleNote.js` | One-line staleness disclosure carried by each analyst panel, with a per-panel recompute. |
| `Client/src/database/resultCache.test.js` | Ten tests covering the five behaviours the PI named, plus module/participant isolation and the discard-refetches-once property the views rely on. |
| `Client/src/views/Reports/ClosedLoopSim/cachedPanels.smoke.test.js` | Six tests: each rewired panel renders with nothing cached, and the per-panel stale notice appears when a cached entry was computed under different settings. |

**Edited**

- `ClosedLoopSim/useDeploymentReport.js`, `useDeploymentSummary.js` — fetch through the cache; the
  external `{data, loading, err}` shape is unchanged, with the cache fields added alongside.
- `ClosedLoopSim/DeploymentRocPanel.js`, `EraRefitPanel.js`, `LsbPowerPanel.js`, `PsdLsbPanel.js`,
  `ConversionModelPanel.js` — same, plus a `PanelStaleNote`.
- `ClosedLoopSim/index.js` — `RecomputeBar` in the decision band; the analyst fold is hidden rather
  than unmounted; a module-scope `VIEW_STATE` retains the fold, the threshold mode, the operating
  point and the device threshold across a route unmount.
- `Biomarkers/index.js` — analysis through the cache; `RecomputeBar` at the top; the Compute button
  reworked so it still forces a rebuild; `markClosedLoopFamilyStale` on band commit.
- `Biomarkers/biomarkerStateStore.js` — the heavy in-memory layer (`HEAP`, `putHeavy`, `getHeavy`,
  `dropHeavy`, and its own `memoryInfo`/`underMemoryPressure` guard) is DELETED. The controls layer
  is untouched. The view now imports the memory helpers from `database/resultCache`.
- `Biomarkers/BiomarkerAnalytics.js` — the generic `Fig` wrapper purged its Plotly node before every
  redraw and carried no `uirevision`, so every figure was rebuilt on every render of its panel and
  lost the reader's zoom, pan and legend state. Purge is now on unmount only, and a constant
  `uirevision` is set.
- `StimOptimizer/index.js` — fetch through the cache; `RecomputeBar` at the top; the request written
  out as `OPTIMIZER_REQUEST` so it can be keyed on; arm selection derived rather than assigned in
  the fetch callback (it would otherwise be null on a cache hit and no surfaces would draw);
  `FigurePanel` purges on unmount only.

## Two defects found in files owned by the PI

Both are described with their evidence in the accompanying report; neither file was modified.

1. **`useCachedResult.recompute()` issues TWO fetches per press.** Measured, not inferred: a probe
   component with a stale cached entry recorded `0` fetches on mount and `2` after one
   `recompute()`. The cause is that `invalidate` publishes a store event, the hook re-reads on every
   event, and on that re-read nothing is cached — so the ordinary first-load path starts a request
   while the deliberate one is still waiting behind the server-identity check. Every view here
   therefore calls `recomputeSlots`, which refreshes the identity and then discards the entries and
   lets the hook's own first-load path issue exactly one request each. That property is asserted in
   `resultCache.test.js`.
2. **`MAX_ENTRIES = 6` is too small, and a count is the wrong unit.** The three views want nine
   slots for one participant. Eviction is least-recently-read and the store touches on read, so in
   practice the small panel payloads fall out rather than the nineteen-megabyte biomarker bundle,
   but that is an access-pattern accident rather than a guarantee.

## Not done

- The container bridge, the server and Docker were not touched, as instructed.
- The backend suite was NOT run, so no suite count is asserted anywhere in this document or in
  MEGA_HANDOFF for this session. No `BRAVO/` file was modified.
- Nothing was committed or pushed.

## Verification actually performed

- `npx react-scripts build` — "Compiled with warnings", the pre-existing `@mediapipe` source-map
  warning only.
- `npx eslint` on every file touched — clean, apart from warnings that were already there before
  this session.
- `CI=true npx react-scripts test --watchAll=false` — 4 suites, 46 tests, all passing.
