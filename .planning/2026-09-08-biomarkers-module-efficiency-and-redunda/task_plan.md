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
All six backend fixes are implemented, proven on RCS08, and committed (5cc0d832, 03b45c3e,
0316abad, fca229c9, 4d480e8a, 8f8c0fad), plus DECISIONS_and_open_items.md decision 79. Not yet
pushed. Next: push, then report the completed work to the user. The frontend and Plotly findings
from the same review remain open for a future session if the user wants them tackled too.

## Current Phase
Phase 6

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

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Keep this implementation plan in the SAME plan directory as the review, as new phases 5-6, rather than opening a new `.planning/` directory. | This is a direct continuation of the review's own output at the user's request ("tackle the backend items 1-6"), not an independent task — matches planning-with-files rule 7 ("Continue After Completion: add new phases"). |
| Sequenced commits directly on `PS_closedloop_deployment`, no per-task branches/PRs, overriding swarm-plan's generic trunk-based template. | CLAUDE.md §4 explicitly states there is no `main` branch here and this project's actual workflow (decisions 37-78) is sequential commits on this one long-lived branch. |
| Task 6 (dead-code removal) is safe — no CLAUDE.md-style deliberate-keep reason found for `spectral_feature_importance` itself, only for its removed call site. | Verified directly against decision 77's exact text and a fresh grep; unlike `LSB_RULE_OF_THUMB`, no decision log entry protects this function. |

## Errors Encountered
| Error | Resolution |
|-------|------------|
