# Findings & Decisions

## Requirements
-

## Research Findings

### Agent B — Frontend visual & structural redundancy (COMPLETE, verbatim findings below)

Scope: `Client/src/views/Reports/Biomarkers/` (9 files, ~7,067 lines). All findings verified by
direct file reading or targeted grep.

1. **`BandTimeSweepPanel.js` (410 lines) is fully orphaned dead code — confirmed.** Zero import
   sites anywhere in `Client/src` other than a comment in `index.js:24-27` noting it was
   deliberately superseded by `BiomarkerHeatmapGrids.js` and kept as a file rather than deleted
   (CLAUDE.md's don't-delete-working-code principle). Ships in the bundle with no reachable render
   path. Fix direction: confirm it's excluded from the main chunk (code-split) or moved to an
   explicit archive location — not a silent deletion, since a prior decision deliberately kept it.
2. **~250 lines of dead code in `BiomarkerAnalytics.js`: `ValidationReadout` and its support
   cluster — confirmed.** Lines 272-519 define `ValidationReadout`, never instantiated as JSX
   anywhere in the file; makes `STABILITY_CELLS` (165-197), `resolveStability` (202-217),
   `stabilityNumbers` (223-246), `StabilityTrack` (251-270) unreachable too, plus 3 imports that
   exist solely for this dead component (`SessionController` line 18; `commitBandCandidate`/
   `downloadBandCandidate` line 19; `ToggleButton`/`ToggleButtonGroup` line 13, unused anywhere in
   the file). Fix: delete the block and its dedicated imports (or archive, matching #1).
3. **Cross-file color-constant duplication instead of importing from `binarizationModel.js` —
   confirmed, real drift risk.** `binarizationModel.js` exports `BIN_HI`/`BIN_LO`/`BIN_MID` as the
   documented single source of truth; independently re-typed in `BiomarkerAnalytics.js:546`,
   `BiomarkerHeatmapGrids.js:54-55,292-293` (RGB triplets + hex fallbacks), `BiomarkerTimeline.js:
   17-20`. (`BiomarkerDataTimeline.js:31`'s darkened excluded-middle shade is a documented
   deliberate legibility divergence, not duplication.) Fix: import the shared constants everywhere
   instead of re-deriving; add an RGB-tuple export for the SVG gradient math.
4. **Threshold/percentile-cut math reimplemented independently in `BinarizationPreview.js` —
   confirmed.** Lines 36-74 (`percentile`, `computeCuts`, including a from-scratch Lloyd's-algorithm
   k-means loop) duplicate `binarizationModel.js:26-33,71-92` almost line-for-line, feeding only the
   "daily fallback" path (the matched-scan path correctly reuses `scanModel.cuts`). Fix: export and
   reuse `computeCuts`/`percentile` for the daily-fallback case too.
5. **Duplicated raw Plotly lifecycle boilerplate across 4 files, no shared wrapper — confirmed.**
   `BinarizationPreview.js`, `BiomarkerAnalytics.js`, `BiomarkerDataTimeline.js`,
   `BiomarkerTimeline.js` each import `Plotly` directly and hand-roll mount/update/purge
   `useEffect` + near-identical config. `BiomarkerAnalytics.js` abstracted its own file-local `Fig`
   component (lines 82-112, used 7x) but it was never adopted by the other three files. Fix
   direction: a shared `usePlotly(ref, traces, layout, config)` hook, or promote `Fig` out —
   mechanical, low-risk. (Hover-template content itself is Agent C's scope.)
6. **`BiomarkerTimeline.js` reintroduces a Plotly purge/zoom-reset bug already fixed next door —
   confirmed, low current impact (rare fallback path).** `BiomarkerAnalytics.js:56-112` documents a
   previously-fixed bug (purging on every effect re-run destroys zoom/pan; fix was purge-on-unmount-
   only + stable `uirevision`). `BiomarkerTimeline.js:154-675`'s effect (deps `[data, height,
   linked]`) unconditionally purges in cleanup (669-674) with no `uirevision` in its layout
   (367-375) — toggling "LINK AXES" or any parent re-render resets zoom/pan. Confined to the rare
   legacy-fallback timeline (renders only when the live availability payload has zero records AND
   the older `data.timeline` field is non-empty — confirmed via `index.js:563-583`).
7. **`BiomarkerHeatmapGrids.js`: cell/label arrays rebuilt on every parent re-render, not scoped to
   grid-relevant state — confirmed.** Only `bestByCol` (line 95) is memoized; `cells`, `xLabels`,
   `yLabels` (120-156) recompute on every render of `Heatmap`, including unrelated UI state (e.g.
   the "How to read this" collapse toggle at 590), because `Heatmap` isn't `React.memo`-wrapped.
   Separate from the already-fixed hover-latency work — this is about unrelated state forcing a
   full ~220-cell SVG array rebuild. Fix: `React.memo` on `Heatmap`; hoist `xLabels`/`yLabels` into
   `useMemo([sw])`.
8. **Cross-file visual/comment inconsistency: "programmed" marker color — confirmed.**
   `BiomarkerAnalytics.js:727` sets `PROG_COLOR = "#6E0F8A"` with comment "(matches timeline)", but
   `BiomarkerTimeline.js:22` defines `programmed: "#1A1A1A"` for the same semantic marker — the
   parity comment is false. User-visible (a clinician moving between panels sees two different
   colors for the same concept) and the comment will mislead the next editor.
9. Minor/cosmetic: unused prop `matchDirty` destructured but not referenced in
   `BiomarkerAnalytics.js:591` (only `onBandCommitted` from that destructure is used) — worth a
   final visual confirmation before removing.

**Checked and downgraded (not an issue):** `scanModel` fed into `BinarizationPreview.js`/
`BiomarkerDataTimeline.js` IS properly memoized in `index.js:480-489` via `useMemo` keyed on
debounced inputs.

**Checked and confirmed clean (no action needed):** `BiomarkerDataTimeline.js`/
`BandTimeSweepPanel.js` correctly consume `computeMatchedScanModel`'s output rather than
reimplementing; `biomarkerStateStore.js`/`binarizationModel.js` are well-scoped and don't reinvent
a more general Reports-view pattern (`ClosedLoopSim/bandCandidateStore.js` is an analogous but
distinct-domain store, not duplication).

### Agent A — Backend data-handling & redundancy (COMPLETE, verbatim findings below)

Scope: `bravo_service.py` (7,167 lines), `pipeline.py`, `routines/analytics.py`,
`routines/streaming_psd.py`, `routines/availability.py`, `adapter.py`,
`routines/band_results_tables.py`. Stray worktree copy ignored. No live timing harness was
available for this module (no `_agent_bridge` dir found under it) — findings below are call-graph
and code-shape confirmed (loop bounds, vectorization/cache presence or absence), not measured
wall-clock, flagged per-item.

1. **CONFIRMED, HIGH IMPACT — two full `pro_lsb_spectrum` computations are orphaned by the
   `spectral_feature_importance` removal: one shipped-but-unread, one computed-and-discarded.**
   `bravo_service.py:3780-3787` (`_build_availability`) calls `_pro_lsb_spectrum_cached(...)` and
   ships the result as `"pro_lsb_spectrum"` in every timeline/availability response (line 3865) —
   grepped all of `Client/src/` for `pro_lsb_spectrum`/`proLsbSpectrum`: zero matches, read by
   nothing. Separately, `bravo_service.py:4139-4145` (`run_for_participant`, the Recompute handler)
   calls `_live_pro_lsb_spectrum(...)`, keeps only its `stats` half (`live_match_stats`, still used)
   and discards the `spectra` half entirely — but `availability.live_lsb_spectrum_match`
   (`routines/availability.py:1837-2062`) still does real per-PRO Python-loop dict construction
   (97-length lists per matched PRO, lines 2000-2008/2041-2048) to produce it. Stale docstrings at
   `bravo_service.py:938-940` and `streaming_psd.py:730,821,1030,1041` still describe this as
   feeding "the spectral feature-importance panel." Fix direction: drop `pro_lsb_spectrum` from
   `_build_availability`'s response; split `live_lsb_spectrum_match` so a stats-only path can skip
   the per-PRO dict-building loop.
2. **CONFIRMED, HIGH IMPACT — `run_for_participant` and `_build_availability` redundantly reload
   the same montage/survey PSD recordings within one request.** `run_for_participant`
   (`bravo_service.py:4114`) calls `_load_recordings(..., AVAILABILITY_PSD_TYPES)` and derives
   `_scan_sensing_idx`/`_scan_event_blocks`/`_scan_montage_blocks` from it (4116-4123); later in the
   SAME request, `_build_availability` (~4219, no `psd_list` param in its signature) repeats all of
   it from scratch (`_load_recordings` again at 3695, `_build_sensing_config_index` again at 3709,
   `_event_psd_lsb_blocks` again at 3754). `_load_recordings` has no caching — each call is a fresh
   DB query plus, per file, disk read + full-file HMAC-SHA256 + blosc2 decompress + `pickle.loads`
   (`Database.loadSourceFile`). The fix already exists in the codebase and just isn't wired here:
   `_recordings_setup_cached` (`bravo_service.py:875-902`) memoizes exactly this tuple with no
   expiry (decision-22-compliant) but today only the hover-cell endpoint uses it. Route
   `run_for_participant`/`_build_availability` through the same memo, or give `_build_availability`
   an optional `psd_list`/`event_blocks` param the way it already accepts `td_list`.
3. **CONFIRMED PATTERN, MEDIUM-HIGH IMPACT, size unconfirmed live — `adapter.align_pros
   (target="chronic")` joins with a per-row Python loop instead of a vectorized groupby.**
   `adapter.py:264-283`: for every chronic sample (10-min cadence — tens of thousands of rows over
   a multi-year history), a dict lookup plus, per metric (up to 3), a pandas `.mean()` call on a
   sub-frame, per row. Runs fresh on every `source in ("powerdomain","both")` request — `"both"` is
   the default (`bravo_service.py:3984`). Fix direction: one `df.groupby("_date")[metrics].mean()`,
   then join by date via `.map()`/`merge`.
4. **SUSPECTED, MEDIUM IMPACT — no recordings-derived cache for the powerdomain/chronic branch,**
   unlike the timedomain branch's `_cached_psd_matrix`. `_load_recordings(CHRONIC_TYPES)`/
   `(POWERDOMAIN_TYPES)` and the subsequent KMeans+smoothing join run fully fresh every full-compute
   request. Chronic recordings are immutable once exported, so decision 22 permits a no-expiry
   cache here; none exists. Lower urgency than #1/#2 since it duplicates work across requests, not
   within one.
5. **Confirmed: `analytics.spectral_feature_importance` itself (routines/analytics.py:1259) is
   unreachable from production** — zero live call sites in `bravo_service.py`/`pipeline.py` (only
   comments and its own test file). The prior session's removal is real and clean at the call-site
   level; the function itself, its worker-count helper, and the two `pro_lsb_spectrum` producers
   (finding #1) are what it left behind.
6. **Refinement, not a new bug, on the already-parked `compute_psd_pain_correlation` finding:**
   `run_timedomain_branch`'s full grid is NOT purely wasted — it's stored as `detail` and feeds
   `_compute_analytics`'s `corr_spectrum`/`psd_spectra` tasks, which drive real, currently-rendered
   panels. Only the narrower `select_biomarker_band`/`_band_inference` single-band summary feeds the
   dead legacy-fallback row. That slice's permutation cost (`_block_perm_maxcorr_pvalue`) is already
   fully vectorized matmul (not a per-permutation Python loop) — sub-100ms class, not a real waste
   source, contrary to what one might assume from the name.
7. **`SlidingWindow` backend branch location, reported per instructions, not re-litigated:**
   `sliding = request_data.get("SlidingWindow", True)` at `bravo_service.py:3450`; since the
   frontend always sends `false` (`index.js:175,224,511`), the `if sliding:` gate at
   `bravo_service.py:3289-3291` and the `analytics.sliding_window_analytics` calls at 3313/3333
   never fire in practice.

### Agent C — Plotly hover template + render manager (COMPLETE, the PI's explicit ask, verbatim below)

**Q1, hover template/mode — mixed answer, real gap is `customdata`, not the declarative mechanism.**
Zero `plotly_hover`/`plotly_unhover` JS listeners exist anywhere in `Client/src` — confirmed by
grep — so no group does expensive per-event work on hover today; the hover-preview network caller
(`BiomarkerHeatmapGrids.js:447-461`, SVG-based, out of Plotly scope) is already well-engineered:
220ms debounce, a per-cell result cache, a stale-response guard. The Biomarkers module builds rich
`customdata` arrays once per render and feeds them into declarative `hovertemplate` strings
(`BiomarkerDataTimeline.js:483-958`, `BiomarkerAnalytics.js:866-1563`) — the efficient pattern.
**0 of the 59 `PlotlyRenderManager`-based files use `customdata` at all** — per-point hover detail
beyond x/y is baked into one hovertemplate string per whole trace instead, which only works because
that string happens to be constant across the trace. `PlotlyRenderManager`'s own `plot()`/
`scatter()`/`bar()`/`box()` already pass unrecognized option keys straight onto the trace object
(`index.js:401-413`), so `customdata` would work today if any caller passed it — it's simply never
used by convention. Hovermode: Biomarkers picks `"closest"` vs `"x unified"` per chart need
sensibly; the render manager defaults to `hovermode:"x"` but **5 files
(`AdaptivePowerTrend.js:62`, `PowerBandBoxplot.js:58`, `AnalysisBuilderOverview.js:48`,
`CircadianRhythm.js:53`, `PatientEventCount.js:48`) set `hovermode:"xy"`, which is not a valid
Plotly enum value** (confirmed against `Client/node_modules/plotly.js/src/components/fx/
layout_attributes.js:62-65` — valid values are `'x'/'y'/'closest'/false/'x unified'/'y unified'`,
default `'closest'`). Plotly silently discards it and falls back to its OWN default (`'closest'`),
not the manager's `"x"` and not the intended `"xy"` — so these 5 charts land on a third, unintended
hovermode, defeating the consistency the override was meant to buy.

**Q2, "the layout is not set" — confirmed meaning: (b), not (a) or (c).**
`defaultLayoutOptions` (`index.js:77-119`) is NOT empty — deep-cloned into `this.layout` in the
constructor, real styling present (gridcolor, linecolor, `hovermode:"x"`, `autosize:true`), and
`responsive:true` is correctly wired in the render config too — so hypotheses (a) and (c) are both
false. **Hypothesis (b) is the real story:** the class exposes `setLayoutProps`/`setAxisProps`/
`setTitle`/`setXlabel`, but only 6 of the 59 caller files actually call them — the other ~53 accept
the single generic default untouched, so the "manager" supplies one fallback most consumers never
engage with; it isn't actually enforcing or curating per-chart-type layout consistency. **Decision
5 (the closed-loop flash-to-loading bug, `255e0ef`) is confirmed UNRELATED** — that was a React
object-identity/re-fetch issue (`requestParamsFromCandidate` recreated inline in JSX), not a
render-manager layout defect. A related but DIFFERENT perf issue was found instead: sampled callers
(`AdaptivePowerTrend.js:31`, `PatientEventCount.js:31`, `TimeFrequencyAnalysis.js:46`) construct
`new PlotlyRenderManager(...)` directly in the component body (not `useRef`), minting a fresh
instance with `fresh=true` on every React re-render; only `CircadianRhythm.js:120` persists it via
`useRef`. Since `fresh` gates `Plotly.newPlot` (full rebuild) vs `Plotly.react` (incremental patch)
(`index.js:1381-1394`), most callers never get the incremental path the flag exists for — flagged as
suspected, not confirmed to visibly flash like decision 5. **Biomarkers bypassing the manager is
unrelated to this defect** — its charts already own their layout/hovermode/customdata per-chart and
would gain little from adopting a manager that isn't delivering enforced consistency today.

**Ranked findings:**
1. Confirmed — `hovermode:"xy"` (invalid enum) in 5 files, silently reverts to Plotly's own
   `'closest'` default instead of the intended value. Fix: use a valid value.
2. Confirmed — 0/59 render-manager consumers use `customdata`; per-point hover detail beyond x/y is
   unavailable to them without it. Fix direction: adopt the Biomarkers `customdata` pattern.
3. Confirmed — only 6/59 files call `setLayoutProps`/`setAxisProps`; the shared default is not
   enforced per-chart-type consistency. Fix direction: enrich `defaultLayoutOptions` per common
   chart archetype, or require explicit layout intent by convention.
4. Suspected — most render-manager callers instantiate fresh per React render (no `useRef`),
   forfeiting the `fresh`/`Plotly.react` incremental-update path that `CircadianRhythm.js:120`
   already demonstrates correctly.
-

## Technical Decisions
| Decision | Rationale |
|----------|-----------|

## Issues Encountered
| Issue | Resolution |
|-------|------------|

## Resources
-
