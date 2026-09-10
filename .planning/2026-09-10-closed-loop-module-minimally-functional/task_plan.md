# Task Plan: Closed-Loop module minimally functional

## Goal
Make the ClosedLoopDeployment module minimally functional: **every check that was built is either
reachable from production or gone.** The module carried seven functions with zero production
callers — checks that were written, tested, proven on live data, and then reached by nothing. A
check nobody calls is not a safeguard; it is a comment that costs maintenance.

Two constraints shape every decision here. `ClosedLoopDeployment` may import `Biomarkers`, never
the reverse. And CLAUDE.md §2 principle 4 warns that things that look dead in this repository are
often deliberate — decisions 74 and 75 record several of these as built-ahead on purpose, to be
wired in later. **A decision that says "wire later" is not permission to delete.**

The line I do not cross alone: anything that changes what a clinician reads as a verdict is the
PI's call. Adding a reported caveat is not that; changing `verdict` or `licensed` is.

## Next Step
Phase 4 needs the PI's call: `clinic_steps.within_visit_band_scores` is a thin orchestrator whose
ingredients all exist in wired code, but whose grouping (visit as both era and cluster, across
within-visit amplitude steps) is reproduced by neither wired path. Wire, delete, or leave. Then the
PI's three other decisions — open items 26, 10 and 7.

Superseded next step, kept for the trail: Phase 3, `reliable_change`. Decision 75 measured that RCS08 has no epoch with two or more ratings
under one unchanged setting, so both functions answer "not assessed" today — decide whether to wire
them as a caveat that populates when the data arrive, or say plainly in the module that they wait
on data rather than on code.

## Current Phase
Phase 2 — the consistency check chain

## Phases

### Phase 1: Audit the module against its two siblings
**Status:** complete

- [x] Compared file-for-file against Biomarkers and StimOptimizer. Decisions 100 and 101 carry the
      findings and the fixes: `cache_status` missing from the two empty-state returns, a
      ground-truth failure reported under the amplitude-effect key, and **zero logger calls in the
      whole module** against Biomarkers' 43.
- [x] Gave the module the `bravo_service.py` entry point both siblings had, and made the view's
      catch-all log — the handler that answered HTTP 200 while the package was unimportable for
      five days.
- [x] Put those fixes to adversarial review, which found a real defect in one of them: the
      explanation was returned under `reason` where the page renders `note`.
- [x] Proven live end to end: a real candidate returns `available: true`, 26 keys, verdict
      `blocked`, both write-backs written.

### Phase 2: The consistency check chain — 4 of the 7 functions
**Status:** in_progress

- [x] Read the chain. `direction_consistency.for_band` is the entry; it calls
      `correlation_row_for_band`, `implied_control_direction`, and
      `amplitude_effect.pooled_shape_for_band`. Four functions, one decision.
- [x] Established that **both inputs are already in hand** inside `report_for_participant` at the
      same moment: `_3build` (the three-source comparison) and `_grid_export` (the calibrated
      grid). The check fits no new model — it reads two results that already exist and reports the
      sign combination.
- [x] Wired `for_band` into `report_for_participant` as `implied_control_direction`, carrying
      `gates_nothing: True`, with "not assessed" on every missing input rather than a manufactured
      pass. Decision 74 named this destination ("as a caveat") when it shipped the check unwired.
- [x] Proven live on RCS08, four points across two contacts: the check is reachable, returns a real
      payload, carries `gates_nothing: true`, and the verdict did not move (`blocked`/`false` on
      every point, unchanged).
- [x] **A real defect found by that proof, and fixed.** Every point answered "not assessed", and
      the reason was the within-visit link. `report_for_participant` truncates the three-source
      comparison to 4 runs for display whenever the amplitude-effect and ground-truth entries are
      already stored — the steady state. Pooling over that slice defeats decision 55/56, whose whole
      point is pooling across every visit. Measured on the SAME band on the SAME day:
      **cold cache, every run → 13 points across 4 visits; warm cache, 4 runs → 6 points across 1
      visit.** The 13 across 4 is exactly what decision 56 measured for this contact. An answer that
      depends on what happened to be cached is not a finding, so the check now refuses to pool a
      truncated build and says why.
- [ ] Guard test: the check is reachable, gates nothing, and never pools a truncated build.

### Phase 2b: The stored pooled table (the PI's choice)
**Status:** complete

- [x] `amplitude_effect.pooled_table_from_build` derives one row per (sensing contact, band centre)
      from a full-run comparison; `adapter.write_pooled_shape` stores it as the derived kind
      `within_visit_pooled_shape` with `writer=` and the tile entry in its provenance;
      `pooled_shape_if_stored` reads it back by `load_newest`, the no-writer's-key pattern decision
      41 established.
- [x] **The writer REFUSES a truncated build** rather than trusting its caller: a stored wrong
      answer is worse than no stored answer, because everything downstream then trusts it. A test
      proves the table is not even derived in that case.
- [x] The check reads the stored row on EVERY request and never re-pools, so cold and warm give the
      same answer. `for_band` gained a `pooled=` argument; the build path is kept for a caller that
      genuinely holds every run.
- [x] **Proven live on RCS08 — the property that matters:** cold, warm, and warm again all give
      **13 points across 4 visits**, where before the fix cold gave 13/4 and warm gave 6/1. The
      table itself holds **294 rows across 3 contacts and 98 band centres, 194 of them assessed.**
- [x] Page cost: 32.5 s on the cold request that builds and stores the table, **11.2 s and 8.8 s
      warm** against about 8.3 s before — the warm page pays one store read.
- [x] Nine guard tests. Suites: container **608 passed, 0 failed**; host **1019 passed**, 42
      skipped, 1 failed (the known environment mismatch).

### Phase 3: reliable_change — 2 functions
**Status:** complete

- [x] The PI's instruction: wire it as a WARNING, never a blocker; let it populate when the data
      arrive; do not let it hold up any other analysis.
- [x] Wired as `reliable_change` on the report, carrying `gates_nothing: True`, a per-item noise
      floor, the Farrar population bar alongside it, and a plain sentence saying a change smaller
      than the floor is not "no change".
- [x] **A defect in the first draft, caught by reading the live result rather than the shape.** It
      passed `eps`, the settings-epoch frame, which carries no pain ratings at all — so every item
      reported "no ratings were matched to any epoch". That looks exactly like the expected "not
      enough history yet" and **would have stayed that way forever, including after the ratings this
      check waits for arrived**, defeating the whole instruction. Caught by noticing every item said
      the same thing when decision 75 had measured that one of them did have ratings. The right
      frame is `dm`, `attach_pros`'s output, one row per epoch with a mean, an SD and a count per
      item.
- [x] **It populated itself, and this supersedes decision 75's measurement.** All six pain scores
      now have a floor where on 2026-09-08 none did: nrs 0.93 points over 78 epochs, mpq_sum 4.84,
      vas 13.39, back_vas 13.42 over 62, left_leg_vas 14.38 over 62, relief 17.29. The data grew.
- [x] Proven not to block: the report still returns `available: true` with all eight other analyses
      present and the verdict unmoved at `blocked`/`licensed` false.

### Phase 4: clinic_steps.within_visit_band_scores — 1 function
**Status:** pending

- [ ] Read it and find what it computes that nothing else does.
- [ ] Wire or delete. This one is named in no decision, so it has no built-ahead defence.

### Phase 5: Prove and land
**Status:** pending

- [ ] Field count and difference count on RCS08: wiring a caveat must ADD fields and move no
      existing value, the same claim proven for the stability column.
- [ ] Both suites green, re-run fresh.
- [ ] Decision row carrying the real numbers; commit and push.

## Decisions Made
| # | Decision | Why | When |
|---|----------|-----|------|
| 1 | This work gets its own plan directory rather than joining the stability-column plan. | CLAUDE.md §4: a second, independent task gets its own directory and its own active-plan entry. | 2026-09-10 |
| 2 | Wire the consistency check as a reported caveat, never as a gate. | Its own docstring says it is not a pass/fail gate, and decision 74 named "as a caveat" as the destination. Adding a reported field is mine to do; changing `verdict` or `licensed` is the PI's. | 2026-09-10 |
| 4 | **The consistency check gets a stored pooled table**, computed off the request path, rather than always building every run on the page or leaving the check unable to answer. | The PI's choice, 2026-09-10, from four options. Measured cost of the alternative: always building every run is 23.7 s against 8.3 s warm, about +15 s on every page load. A stored table keeps the page cost and lets the check answer from all 4 visits rather than 1. | 2026-09-10 |
| 5 | **Open item 26: mark the affected cells.** Cells computed from the device's own spectrum are to be marked on the grid, not merely described in the drawer. | The PI's choice. A reader comparing down a column currently reads a constant as a trend, and a sentence in a drawer does not reach the reader who is looking at the grid. Needs a per-cell flag threaded through the sweep response. | 2026-09-10 |
| 6 | **Open item 10: cross the grid with a candidate setting.** The reader supplies an amplitude, rate and pulse width, and the real 51-rule device screen runs against the grid for that setting. | The PI's choice, resolving decision 65's requirement that could not be built as written (47 of 51 rules need fields a grid point does not carry). Accepts that the check becomes live-computed per setting rather than pre-computed, which supersedes the ADR's own performance argument for pre-computing it. | 2026-09-10 |
| 7 | **Open item 7: sweep every pain score, precomputed off the request path.** | The PI's choice. Roughly six times the compute, moved off the page — the same shape as the stability grid's daily pass — so switching score is instant and one outcome can be compared against another. | 2026-09-10 |
| 3 | Nothing in this module is deleted on the grounds of having no caller, without checking the decision log first. | Decisions 74 and 75 record several of these as deliberately built ahead of their wiring, and CLAUDE.md §2 principle 4 exists because this repository has already paid for deleting something that looked dead. | 2026-09-10 |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| Returned the cache-status explanation under `reason`; the page renders `note` and has no `reason` field, so the cause would have been invisible on screen. | 1 | Found by adversarial review before it reached anyone. Verified against `CacheStatusLine.js` directly, then returned the full sibling shape. |
| The logging guards walked one function, and `ast.walk` does not descend into a function it merely calls — so the helper with the unlogged handler passed both guards. | 1 | Widened to a named five-function surface, which immediately found two more unlogged handlers. |
