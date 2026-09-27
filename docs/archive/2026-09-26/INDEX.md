# Archive 2026-09-26: the planning and design clean-up

The PI asked on 2026-09-26 for every planning and design document to be checked and cleaned up.
Every plan under `.planning/` was complete, and every step in them is recorded in the decision
log, so all ten were moved here by `git mv` and no plan is live. The design working papers that a
later specification or ruling replaced were moved here too. Line numbers in these files have moved.

## Plans (`planning/`)

Each was complete (every phase's status line reads complete). The decision log carries what each
one built; nothing in them is an open item.

| Archived here | Recorded in |
|---|---|
| `planning/2026-09-21-drill-down-merges-clinic-sheet-ratings/` | decision 228 |
| `planning/2026-09-21-exploratory-ladder-left-c1-2/` | decisions 230, 236 (its 125 Hz rate was overruled to 55 Hz) and 244 |
| `planning/2026-09-23-closed-loop-page-step-7/` | decision 242 |
| `planning/2026-09-23-stim-optimizer-page-step-8/` | decision 243 |
| `planning/2026-09-23-housekeeping-step-9/` | decision 246; its `progress.md` is cited by `artifacts/research_2026-09-25_options/05_small_rulings_and_stale_numbers.md` as a withdrawn claim (the R 1-3+ daily cycle, corrected in decision 265) |
| `planning/2026-09-23-outstanding-items/` | decisions 248-258 |
| `planning/2026-09-24-implant-date-cutoff-and-off-period-analy/` | decisions 260-262 |
| `planning/2026-09-24-control-analyses-card/` | decisions 264-265 |
| `planning/2026-09-25-speed-up-slow-builds/` | decisions 266-269 |
| `planning/2026-09-25-context-fix-ci-numba-carry-over-test/` | decisions 270-301 and 310-314; the switch it left waiting on the PI was built as decision 315 (it was the last active plan) |

## Design papers (`design/`)

| Archived here | Replaced by |
|---|---|
| `design/design_2026-09-26_minimalist_redesign/proposal_1.md` | `artifacts/design_2026-09-26_minimalist_redesign/SPEC.md`, which takes it as its base (decision 320) |
| `design/design_2026-09-26_minimalist_redesign/proposal_2.md` | the same `SPEC.md`, which takes seven of its ideas (listed at the top of SPEC.md) |
| `design/design_2026-09-26_minimalist_redesign/evaluations.json` | the same `SPEC.md`; these were the five read-only evaluations of the pages as they were before decision 320 |
| `design/design_2026-09-12_stim_optimizer_page_redesign.md` and its folder (mock-ups and phase patch files) | the Stim Optimizer page as rebuilt in decisions 243, 303 and 320-325; its current layout is in `SPEC.md` §5.3 |

**Kept in place, not archived:** `artifacts/design_2026-09-26_minimalist_redesign/SPEC.md` (the
one current design specification, amended in place with dated notes) and `TASTE_AUDIT.md` beside
it (page code cites its item numbers by that path); `artifacts/design_review_2026-09-26_stim_optimizer_and_biomarkers.md`
(page code and tests cite it; a status note added); `DESIGN_biomarker_pipeline_v2.md` (still
listed in CLAUDE.md §10 for the band-candidate contract; a note added at its top naming the
superseded sections); `artifacts/design_2026-09-08_*` and `artifacts/design_2026-09-11_*` (dated
designs cited by code or other records); `artifacts/spec_2026-09-25_P18_timeline_detail_panel.md`
(an unbuilt draft for an open item, P-18).
