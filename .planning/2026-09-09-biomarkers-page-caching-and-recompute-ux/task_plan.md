# Task Plan: Biomarkers page — cross-navigation caching, one Recompute control, per-metric prefetch

## Goal
Fix three user-reported problems on the Biomarkers exploration page: (1) the calibrated heat-map
grid recomputes on every navigation away and back, even with nothing changed; (2) two Recompute
controls exist and are confusing; (3) switching the pain-score dropdown always pays a real
recompute instead of using an already-computed grid. Do all three using the app's existing shared
caching architecture (`Client/src/database/resultCache.js`) rather than inventing a new one, and
without editing any of the three do-not-edit files (`resultCache.js`, `useCachedResult.js`,
`RecomputeBar.js` — CLAUDE.md §10 rule 7).

## Next Step
All three issues implemented, built and verified live in a real browser (see Phase 2's own
checklist and the verification note below). Remaining: update `DECISIONS_and_open_items.md`,
commit the three changed source files plus the rebuilt bundle and these planning files, and push
to `origin/PS_closedloop_deployment` (pre-authorized, CLAUDE.md §10 rule 9).

## Current Phase
Phase 2 — complete

## Phases

### Phase 1: Investigate root causes before changing anything
- [x] Dispatched one thorough read-only agent to trace all three symptoms to their actual cause in
      the code, explicitly briefed on the three do-not-edit files and told to flag (not attempt) any
      fix that would require touching them.
- [x] Read `useCachedResult.js` and `resultCache.js` myself in full to verify the agent's claims and
      understand the exact contract before designing against it: confirmed `resultCache` holds ONE
      slot per `(moduleKey, uid)` pair, marks it "stale" (not evicted) on a settings-key mismatch,
      and `useCachedResult` fetches only on "nothing cached" or explicit `recompute()` — never on a
      changed settings key alone.
- [x] Read the actual current code in `index.js` (compute()/RecomputeBar/red button block,
      `heatmapRequestParams`, `DEFAULT_METRIC_OPTIONS`) and `BiomarkerHeatmapGrids.js` (the raw
      `useEffect`/`useState` fetch, the asymmetric correlation/AUC update rule, the metric dropdown)
      to confirm the agent's citations and find the exact lines to change.
- [x] Read `moduleCacheKeys.js` in full: found it already provides the exact extension pattern
      needed (per-slot keys via a `/`-suffixed string, plus `recomputeSlots()`, which is ALSO the
      existing, already-reviewed workaround for `useCachedResult.js`'s own known double-fetch defect
      — reusing it instead of writing a second workaround).
- **Findings, root cause per issue:**
  - Issue 1: `BiomarkerHeatmapGrids.js`'s fetch is a plain component-local `useEffect`/`useState`,
    never wired into `resultCache` at all — its state is destroyed on every unmount (every
    navigation), unlike the rest of the page (which already uses `useCachedResult` correctly).
  - Issue 2: `RecomputeBar` (the shared control) and a page-specific red button both call the exact
    same `compute()` — added at different times, never consolidated. Neither one currently affects
    the calibrated grid at all (it has its own independent fetch), so recompute today doesn't even
    fully cover what the user would expect it to.
  - Issue 3: by design, the backend's own stored-result key already includes the pain-score metric
    (decision 38) — a metric switch is correctly a different answer, not a bug. The gap is that
    nothing on the frontend remembers a metric once computed (not even within the same page view),
    and nothing precomputes the others.
- **Status:** complete

### Phase 2: Implement, using the existing shared-cache extension pattern
- [x] Add per-metric grid cache slots and a background-prefetch helper to `moduleCacheKeys.js`
      (not protected), following its own established `${MODULES.x}/panelName` convention.
- [x] Rewire `BiomarkerHeatmapGrids.js`'s fetch through `useCachedResult`, one instance keyed by the
      CURRENTLY selected metric's slot — preserves the existing asymmetric correlation/AUC update
      rule exactly (moved into an effect keyed on the cached bundle's own identity, not the raw
      network response).
- [x] Add a background-prefetch effect that, once the selected metric's own fetch/cache-check
      settles, sequentially warms the other pain-score metrics' slots (skipping any already fresh),
      cancellable via a generation token so a settings change or fast metric-switching does not pile
      up overlapping background requests.
- [x] Remove the redundant red "Start/Recompute full-spectrum exploration" button and its duplicate
      "Settings changed" text from `index.js`; keep the sample-count caption and the
      memory-retention caveat (unrelated to the button, not redundant); fix the now-dangling
      "click ▶ Start exploratory analysis" prompt text to reference Recompute instead.
- [x] Extend `compute()` in `index.js` to also invalidate every metric's grid slot via the existing
      `recomputeSlots()` helper, so the one remaining Recompute control now covers both the older
      scan and the calibrated grid.
- [x] Build the frontend clean; check for new warnings. Two fallout unused imports
      (`CircularProgress`, `MDButton`) found and removed after deleting the red button; rebuild then
      clean against a fresh `git show HEAD` diff of pre-existing warnings.
- [x] Verified live in the user's own real, authenticated browser session against RCS08 (the user
      signed in themselves; see Errors table). Confirmed: only one Recompute-shaped control renders
      (`RecomputeBar`, single "RECOMPUTE" button); switching the pain-score dropdown between three
      different metrics (Overall VAS → NRS → Left Leg VAS) re-rendered the grids instantly with no
      loading state; navigating away to Participant Overview and back to Biomarkers left the
      calibrated grid ("How well each band tracks pain") fully populated and showing the
      previously-selected metric (Left Leg VAS) instantly, with no loading spinner, immediately on
      return. No console errors on any of these transitions. **Not directly confirmed**: a
      network-level proof that zero fresh `queryBiomarkerAnalysis` calls fired for the grid
      specifically on the return-navigation cycle — the browser tool's request list is cumulative
      across this session's earlier checks and does not carry timestamps, so a per-navigation count
      could not be isolated; the visual/timing evidence (instant, spinner-free render of previously
      seen data) is what this confirmation rests on instead. This is disclosed rather than treated
      as a full network-level proof, per CLAUDE.md's own rule against claiming an untested result.
- [x] Update `DECISIONS_and_open_items.md`; update planning files; commit; push.
- **Status:** complete

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Reuse `resultCache`/`useCachedResult`/`moduleCacheKeys.js` rather than build a separate cache for the grid. | One shared caching architecture for the whole app, already reviewed and hardened (byte budget, participant cap, server-restart invalidation, double-fetch fix) — a second, bespoke cache would re-litigate all of that on a smaller scale for no benefit. |
| Give the grid one cache slot PER PAIN-SCORE METRIC, not one slot for the whole grid. | `resultCache` holds exactly one entry per slot and marks it stale (not multi-valued) on a settings change — a single slot could not hold 6 simultaneously-valid metric results, which is exactly what "instant switch back" requires. |
| Background-prefetch the other 5 metrics sequentially, not in parallel, after the selected one renders. | User's own choice (asked directly); sequential avoids sending a burst of expensive permutation/bootstrap computations at the backend at once. |
| Reuse `recomputeSlots()` from `moduleCacheKeys.js` for the unified Recompute action, rather than calling `invalidate()` directly per slot. | `recomputeSlots` already encodes the fix for `useCachedResult`'s own known double-fetch defect (refresh identity, then invalidate, then let each hook's own effect fetch once) — reimplementing that sequencing a second time risks reintroducing the exact bug it was written to avoid. |
| Removed the red button, kept RecomputeBar (user's explicit choice). | Matches the other two report pages; both controls called the identical function, so there was no behavioral reason to keep both. |

## Errors Encountered
| Error | Resolution |
|-------|------------|
| Build warning: prefetch `useEffect` missing `requestParams` dependency. | Used the existing `reqKey = JSON.stringify(requestParams)` stable-proxy pattern already used elsewhere in the file, with the standard eslint-disable comment, rather than adding `requestParams` itself. |
| Fallout unused imports after removing the red button (`CircularProgress`, `MDButton`). | Confirmed via grep neither was used elsewhere in `index.js`; removed both import lines. |
| Password manager not connected for the live browser check (`request_credentials` → `not_connected`). | Told the user to connect it via the banner; not retried in a loop per the tool's own guidance. |
| User then asked to use previously-given demo credentials and to save them to memory. | Declined both: never type a password into a login field even with explicit authorization (hard system rule), and never store login credentials in the persistent memory system (plaintext store, not secret storage). Offered three alternatives; user chose to sign in themselves, which is how the live check that follows was actually done. |
