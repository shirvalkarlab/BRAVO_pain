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
All three of the PI's decisions are answered: item 26 built, item 7 built, item 10 closed as
unnecessary. Nothing is queued. The plan's own goal — every check either reachable from production
or gone — was met at Phase 4.

Superseded next step, kept for the trail: Open item 10 — cross the device-rules screen with a candidate setting, the last of the PI's three.
Items 26 and 7 are done, in the order he asked for.
## Current Phase
Phase 6b — done; nothing queued

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
**Status:** complete

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
- [x] Guard test: the check is reachable, gates nothing, and never pools a truncated build.
      Landed with Phase 2b's nine tests (decision 103), including that a truncated build is
      refused before the table is derived and that a row is matched on contact AND centre
      together — two contacts share a band centre.

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
**Status:** complete

- [x] Established what it uniquely computes: nothing. The harmonic-landing flag is already applied
      in wired code (`three_source_response`, `analytics`), and the slope and separation come from
      `lfp_response` through a caller-supplied function. Only its GROUPING was its own — visit as
      both era and cluster across within-visit amplitude steps.
- [x] **Run live before deciding, at the PI's request.** All 22 band centres aligned on all three
      sensing contacts: ONE_THREE_LEFT (13 steps, 4 visits), ZERO_THREE_RIGHT (12 steps, 6 visits),
      ZERO_TWO_LEFT (5 steps, 1 visit) — 22 scored bands each and **zero responders everywhere**,
      against the pooled table's 194 of 294 assessed. Caveat stated rather than buried: the response
      function defaults to requiring SUPPRESSION, so the zero means "no band that can be turned down
      into", the mode that matters for closed-loop control.
- [x] **Deleted on that evidence**, with the numbers and the caveat written into the file where the
      function was, so the next reader sees why rather than an unexplained gap.
- [x] Removed its three tests and the `within_visit` re-export it alone needed.
- [x] **A real mistake in the deletion, caught by the suite.** Removing the re-export broke three
      tests that read `step_settled_medians` and `amplitude_arm_bins` through `clinic_steps`. Checked
      by grep that NO production code ever did, so the fix is to point those tests at
      `within_visit`, which defines them, rather than restore a re-export nothing uses. The
      behaviour under test is unchanged; only the module they ask by.

### Phase 5: Open item 26 — mark the cells the length axis does not apply to
**Status:** complete

- [x] Read both matchers rather than trusting the item's line numbers. Confirmed: the device's own
      spectrum branch has no quantity cap and writes the SAME value into every length row.
- [x] Measured the size of it before building anything. **It is not a rare edge case on this
      record**: 358 of 451 matched reports on R 0-3+ (79.4%), 83 of 174 on L 1-3+ (47.7%), 3, 5, 0
      and 0 on the rest.
- [x] Measured the consequence, not only the structure: the correlation travels 0.037 across the
      whole length axis on R 0-3+ against 0.160 and 0.253 on the two contacts with none — the
      contact with the most data has the most frozen axis.
- [x] Carried a per-report flag from the matcher to where the cell is computed, so the mark counts
      exactly the reports that cell used. Both matching paths report it.
- [x] Marked BOTH grids from their OWN denominators — the split can drop reports from the curve
      grid that the correlation grid keeps.
- [x] Frontend: a dash on each affected cell sized by share, the exact share on hover, an
      always-visible line naming the count, and a drawer bullet — shown only where there is
      something to show.
- [x] Equality proof, no tolerance: 27,935 fields before, 36,399 after, 0 dropped, 8,464 added,
      and of the 27,935 in common exactly 24 differ — every one a wall-clock timing field.

### Phase 6: Open item 7 — every pain score, precomputed off the request path
**Status:** complete

- [x] Built in the two shapes the stability grid already uses: `manage.py precompute_band_sweeps`,
      started detached once a grid lands for the OTHER five scores at the settings in use, and run
      daily at the defaults from the same pass the stability loop already makes.
- [x] **A fan-out guard, because without it one page load becomes a growing tree of real
      processes**: the command builds a grid by calling the ordinary request function, which ends
      by starting background work. A private flag both launchers read holds them off.
- [x] **THE DEFECT THAT WOULD HAVE MADE THIS A NO-OP REPORTING SUCCESS.** `CacheStore` kept exactly
      one entry per participant per kind, so the six scores evicted each other: six computed, six
      writes saying `stored: true`, **one file on disk**, and the page rebuilding a score it had
      just stored. Fixed in the store, where the rule lives — `KEEP_NEWEST_BY_KIND`, twelve for the
      three sweep kinds, one for everything else so a 245 MB tile entry cannot start keeping twelve.
- [x] Speed claim and equality proof together, alternating rounds: served 2.9 / 5.4 s against fresh
      10.4 / 12.0 s, **36,401 fields compared, 22 differing, all bookkeeping, 0 scientific.**
- [x] The daily pass live, exit 0: six scores `already_current` at 2.5-2.9 s each; a participant
      with no recordings reports "nothing stored" and is correctly not a failure.
- [x] **A hazard in my own test, disclosed**: the control called the launcher without switching the
      feature off and really started jobs for a made-up participant on the container runner,
      leaving markers in the live cache. Cleared; the test now switches the feature off.

### Phase 6b: Open item 10 — closed as unnecessary, no code
**Status:** complete

- [x] **The PI closed it rather than choosing between the two options offered**, and gave a
      boundary as the reason: the Biomarkers module does not deal in what stimulation does to a
      biomarker. That page exists to find which frequency bands track pain; whether a band can be
      programmed, and what the current does to it, belong to Closed-Loop Deployment and Stim
      Optimizer, which already hold the 51 device rules and the dose-response work.
- [x] The neutral sentence Track D shipped on every row is therefore the FINAL answer, not a
      placeholder waiting on this decision.
- [x] Checked before writing it down, rather than assumed: Biomarkers imports nothing from the
      device-rule file, and its one mention of it is a comment about a frequency-range check, which
      is a frequency question and not a stimulation one. Nothing had to be removed.

### Phase 7: Prove and land
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
