# Task Plan: Biomarkers module — efficiency, redundancy, and Plotly review

## Goal
Produce a thorough, cited review of the Biomarkers exploration module (frontend + backend) covering
data-handling efficiency/speed, front-end visual redundancy, back-end redundancy, and a dedicated
look at the Plotly hover template and the unused/half-configured "render manager" that ~50 files
render through — as input to the session's larger goal (optimize speed, clean up visualization, make
the closed-loop module deployable). This task is REVIEW ONLY: no code changes until the user picks
which findings to act on.

## Context carried in from the prior (complete) plan
`.planning/2026-09-08-biomarkers-heatmap-plotting-redesign/` closed out 2026-09-08, committed as
38371d6b + 6af29244, pushed, 0 commits ahead of origin/PS_closedloop_deployment. Established facts
this review must not contradict or re-derive:
- The two main correlation/AUC grids (`BiomarkerHeatmapGrids.js`) are hand-rolled SVG, NOT Plotly —
  decision 66, deliberate, for per-cell hover/click. ~220 SVG rects, sub-millisecond draw.
- `spectral_feature_importance` panel (old scatter+violin in `BiomarkerAnalytics.js`) was REMOVED
  entirely (backend + frontend) this session already — do not re-flag its removal, do not assume it
  still exists.
- `streaming_psd.compute_psd_pain_correlation`: computed on every request via
  `pipeline.run_timedomain_branch`, but its only frontend consumer is `BiomarkerTimeline.js`'s
  legacy fallback path, which never renders when the modern availability payload is present (always,
  in normal operation). Flagged as wasted compute, parked, NOT fixed. Fair game for this review to
  size/confirm, but the fix decision is the user's.
- `SlidingWindow`: hardcoded `const slidingWindow = false`, no setter, still gates real backend
  branching. Parked, not touched. Fair game to review, not to change.
- Decision 22 (as amended by decision 78): recordings/PSD-derived data may be cached with no expiry
  (immutable once exported); pain-report tables must NOT be cached with a clock — the only allowed
  invalidation is "a build replaces it" (`_PRO_BUILD_CACHE` / `_remember_pain_reports` /
  `_pain_reports_for_drilldown`). Any new caching recommendation must respect this rule explicitly.
- Decision 5: this project already paid for Plotly's re-render lifecycle once (closed-loop figures
  flashing back to loading state) — relevant context for the render-manager investigation.
- Existing fast caches to be aware of (don't recommend re-inventing): `_RAW_LSB_CACHE_MEMO`,
  `_RECORDINGS_SETUP_MEMO` (`_hover_cell_recordings_setup`), `_PRO_BUILD_CACHE`.

## Next Step
All three legs of the original review (backend, frontend, Plotly) are now closed out. Backend:
6 fixes, decision 79, pushed. Frontend: 9 findings implemented, decision 80, pushed (57c65d1b,
cc73a5fa). Plotly: all 4 findings evaluated by dedicated research agents at the user's request and
found not worth fixing (small mechanical-looking changes with a blast radius of up to 58 files
outside this module, for benefits that direct verification found speculative or already
nonexistent) — decision 81, no code changed. Nothing left queued from this review; a new task would
need a fresh trigger (a specific reported problem, or a new review).

## Current Phase
Phase 8 (final)

## Phases

### Phase 1: Scope the Biomarkers module
- [x] Enumerated frontend files: `Client/src/views/Reports/Biomarkers/{index.js, BiomarkerAnalytics.js,
      BiomarkerHeatmapGrids.js, BiomarkerTimeline.js, BiomarkerDataTimeline.js, BandTimeSweepPanel.js,
      BinarizationPreview.js, binarizationModel.js, biomarkerStateStore.js}`.
- [x] Enumerated backend files: canonical module is `BRAVO/modules/Biomarkers/{bravo_service.py,
      pipeline.py, routines/analytics.py, routines/streaming_psd.py}`. (NOTE: `.claude/worktrees/
      agent-a995da316079930ca/BRAVO/modules/Biomarkers/` is a stray other-agent worktree with a
      duplicate copy — out of scope, do not review or edit it.)
- [x] Located the Plotly render manager: `PlotlyRenderManager` class in
      `Client/src/graphing-utility/Plotly/index.js` (~line 197), used by 59 files — almost all under
      `Client/src/views/Experimental/**`. KEY FINDING: the Biomarkers module does NOT use it at all.
      Five Biomarkers files import raw `Plotly` directly from `"plotly.js-dist"` instead
      (`BandTimeSweepPanel.js`, `BinarizationPreview.js`, `BiomarkerDataTimeline.js`,
      `BiomarkerAnalytics.js`, `BiomarkerTimeline.js`), each hand-rolling its own layout/hovertemplate/
      resize handling rather than going through the shared manager. This is the starting point for
      Agent C, not a full explanation — Agent C still needs to confirm the "layout is not set" claim
      inside `PlotlyRenderManager` itself and trace consequences on both sides (the 59 files that use
      it, and the 5 Biomarkers files that don't).
- **Status:** complete

### Phase 2: Parallel review agents
- [x] Agent A — Backend data-handling & redundancy: 7 findings, file:line cited, confidence-tagged.
- [x] Agent B — Frontend visual & structural redundancy: 9 findings + 2 checked-clean notes.
- [x] Agent C — Plotly hover template + render manager: both PI questions answered directly with
      code citations, 4 ranked findings.
- **Status:** complete

### Phase 3: Synthesis
- [x] Cross-checked each agent's findings against the "Context carried in" facts — no
      contradictions found; no agent re-flagged an already-removed/already-parked item as new.
- [x] Merged into findings.md, cited to file:line, ranked by impact/confidence, tagged
      backend/frontend/plotly.
- **Status:** complete

### Phase 4: Delivery
- [x] Reported the prioritized findings to the user in chat; asked which items to act on next
      rather than implementing unprompted.
- **Status:** complete

### Phase 5: Plan the fixes for backend findings 1-6 (via /swarm-plan, at the user's direction)
- [x] Ran three targeted research agents to pin exact current line numbers and implementation
      shapes for all six backend findings (dead-spectrum removal, duplicate-load elimination,
      align_pros vectorization, chronic/powerdomain cache, dead-code removal safety check).
- [x] Wrote `artifacts/plan_2026-09-08_biomarkers_backend_efficiency_fixes.md`: six tasks, each
      sized ~15-45 minutes, with acceptance criteria (equality proof + alternating-round timing per
      CLAUDE.md §10 rules 3-4), a merge order (1→2→6→4→3→5), and an explicit note that this
      repository's own branching rule (CLAUDE.md §4) overrides swarm-plan's generic
      one-PR-per-task/trunk-based template — these land as sequential commits on
      `PS_closedloop_deployment`, not separate branches.
- [x] Classified all six as Two-Way Door (reversible, no external contract) — no ADR needed, the
      plan artifact alone is sufficient per the Small-Feature tier.
- [x] No `TaskCreate` tool is available in this harness; tasks are tracked in the plan artifact's
      table and mirrored here instead of a native task list.
- **Status:** complete

### Phase 6: Implement the six backend fixes
- [x] Task 1: remove unread `pro_lsb_spectrum` field — commit 5cc0d832
- [x] Task 2: skip building discarded spectrum in Recompute path — commit 03b45c3e
- [x] Task 6: delete dead `spectral_feature_importance` + helper + tests + docstrings — commit 0316abad
- [x] Task 4: vectorize `align_pros(target="chronic")` — commit fca229c9
- [x] Task 3: eliminate duplicate recordings load — commit 4d480e8a
- [x] Task 5: no-expiry cache for chronic/powerdomain branch — commit 8f8c0fad
- [x] `DECISIONS_and_open_items.md` decision 79 added, summarizing all six with their proof numbers
- **Status:** complete

### Phase 7: Implement the frontend dead-code/duplication findings (Agent B, via /swarm-execute)
- [x] Deleted the dead `STABILITY_CELLS`/`resolveStability`/`stabilityNumbers`/`StabilityTrack`/
      `ValidationReadout` cluster from `BiomarkerAnalytics.js` (~395 lines), confirmed via grep that
      `<ValidationReadout>` was never rendered; removed its now-orphaned imports and the `matchDirty`
      prop (only that dead cluster read it) from both `BiomarkerAnalytics.js` and its `index.js` call
      site, leaving `BinarizationPreview.js`'s own genuine use of `matchDirty` untouched.
- [x] Investigated finding #1 (`BandTimeSweepPanel.js`): already documented in `index.js` as
      deliberately kept (CLAUDE.md §2 principle 4); never imported anywhere so zero bundle cost.
      No code change made or needed.
- [x] Deduplicated colors: `binarizationModel.js` exports `BIN_HI_RGB`/`BIN_LO_RGB`;
      `BiomarkerHeatmapGrids.js`, `BiomarkerTimeline.js`, `BiomarkerAnalytics.js` import the shared
      HI/LO constants instead of redeclaring matching hex literals. Deliberately did NOT alias
      `BiomarkerTimeline.js`'s `td`/`threshold` colors or `BiomarkerHeatmapGrids.js`'s
      `PAL.accentBorder` chip — different semantic concepts that only coincidentally share hex values.
- [x] Deduplicated `computeCuts`: exported `binarizationModel.js`'s version;
      `BinarizationPreview.js`'s locally-duplicated implementation (verified mathematically
      equivalent — nearest-centroid assignment and midpoint-threshold splitting are identical for
      1-D two-centroid k-means) replaced with a thin wrapper, mirroring the file's own existing
      `matchedCuts` pattern.
- [x] Fixed the Plotly zoom-reset bug in `BiomarkerTimeline.js` (Plotly.purge was running in the
      main effect's cleanup on every `[data, height, linked]` change instead of unmount-only) —
      moved to a dedicated unmount-only effect, added `uirevision`, mirroring `BiomarkerAnalytics.js`'s
      already-correct `Fig` component.
- [x] Memoized `xLabels`/`yLabels` in `BiomarkerHeatmapGrids.js`'s `Heatmap` (moved before the early
      return to satisfy rules-of-hooks) and `centers`/`seconds` (an eslint exhaustive-deps warning
      caught that `sw.x || []` allocated a fresh array every render, defeating the memoization just
      added).
- [x] Assessed and deliberately deferred the other half of finding #7: did NOT wrap `Heatmap` in
      `React.memo`, since the parent passes `onHover`/`onClick` as fresh inline closures every
      render (would need `useCallback` too, risking the hardened hover/click interaction logic) for
      near-zero benefit (cell rendering already sub-millisecond per decision 66).
- [x] Fixed a false code comment on `PROG_COLOR` in `BiomarkerAnalytics.js` that incorrectly claimed
      it matched `BiomarkerTimeline.js`'s legacy-view color (it doesn't — left as two colors
      deliberately, not a drive-by fix).
- [x] `npm run build` clean; cross-checked every remaining warning against `git show HEAD` to
      confirm all are pre-existing, none introduced by this session's edits.
- [x] Bundle-verified: grepped `build/static/js/*.chunk.js` for distinctive new strings
      (`uirevision: "biomarker-timeline"`, "KMeans midpoint", `[213, 94, 0]`) — all reached chunk
      806; confirmed the deleted cluster's strings ("Not determinable", "declared equivalence
      margin") appear nowhere in the bundle.
- [x] Committed 57c65d1b (source + rebuilt `Client/build/`); `DECISIONS_and_open_items.md` decision
      80 added.
- [x] Pushed to origin/PS_closedloop_deployment (57c65d1b, cc73a5fa).
- [x] Reported to user: findings fixed, findings requiring no change, the one deliberately deferred
      item, and that no live browser check was performed.
- **Status:** complete

### Phase 8: Evaluate Agent C's Plotly render-manager findings (via 4 parallel research agents)
- [x] Dispatched 4 independent, read-only research agents, one per Agent C ranked finding, each
      told to verify the finding directly against current code (not trust the prior summary) and
      weigh cost vs. benefit against the user's bar ("only proceed if the pro is more than 30%
      better").
- [x] All four returned SKIP, each after directly disproving or substantially narrowing the
      original finding's premise: the `hovermode:"xy"` typo is in 10 files not 5, and `"closest"`
      (its accidental fallback) is a value this codebase deliberately picks elsewhere; the
      `customdata` gap causes no actual lost hover info in a 14-file sample; "6/59 customize
      layout" was undercounted — a full-method grep found 57/58 do; the `useRef` persistence gap is
      real (55/58) but its DOM-mutating call is effect-gated on real data props everywhere sampled,
      so the practical harm is wasted allocation, not the visible flash bug decision 5 fixed.
- [x] `DECISIONS_and_open_items.md` decision 81 added, recording all four findings and why none
      qualified. No code changed — this phase was evaluation only, at the user's explicit
      instruction not to implement without first weighing pros/cons.
- **Status:** complete

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Keep this implementation plan in the SAME plan directory as the review, as new phases 5-6, rather than opening a new `.planning/` directory. | This is a direct continuation of the review's own output at the user's request ("tackle the backend items 1-6"), not an independent task — matches planning-with-files rule 7 ("Continue After Completion: add new phases"). |
| Sequenced commits directly on `PS_closedloop_deployment`, no per-task branches/PRs, overriding swarm-plan's generic trunk-based template. | CLAUDE.md §4 explicitly states there is no `main` branch here and this project's actual workflow (decisions 37-78) is sequential commits on this one long-lived branch. |
| Task 6 (dead-code removal) is safe — no CLAUDE.md-style deliberate-keep reason found for `spectral_feature_importance` itself, only for its removed call site. | Verified directly against decision 77's exact text and a fresh grep; unlike `LSB_RULE_OF_THUMB`, no decision log entry protects this function. |

## Errors Encountered
| Error | Resolution |
|-------|------------|
| Rules-of-hooks violation: `BiomarkerHeatmapGrids.js`'s `Heatmap` called two new `useMemo` hooks after the component's conditional early return (`if (!rows \|\| !cols) return ...`), which `npm run build` refused to compile (`react-hooks/rules-of-hooks`). | Moved the padding/geometry computation and both `useMemo` calls to before the early return, guarding potential division-by-zero with `(cols \|\| 1)`/`(rows \|\| 1)` — safe because those values are never rendered on the early-return path. Also found and removed a leftover duplicate copy of the old post-early-return `xLabels`/`yLabels` block the edit had left behind. |
| Memo-defeating bug (self-introduced): after fixing the rules-of-hooks violation, `centers`/`seconds` were still computed inline as `sw.x \|\| []`, which allocates a fresh array reference every render — used as a `useMemo` dependency, this silently defeated the memoization just added. Caught by a NEW `react-hooks/exhaustive-deps` warning in the next build, not by manual review. | Wrapped both in their own `useMemo(() => sw.x \|\| [], [sw])`. |
