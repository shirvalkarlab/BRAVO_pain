# Task Plan: Closed-Loop grid stability column

## Goal
Make the calibrated grid on the Closed-Loop Deployment page carry its cross-setting stability
answer, instead of showing "stability: not yet computed" on every row forever. Track D already
built both halves of this — `Biomarkers.bravo_service.raw_stability_result_for_point` computes the
untranslated answer per (sensing contact, band centre) point, and
`ClosedLoopDeployment.stability.finding_from_stability_result` turns it into the honest four-valued
finding on the reader's side — but the switch that turns it on, `IncludeCrossSettingStability`, is
set by no client code anywhere, so neither half has ever run for a real page view.

The obstacle is cost, and it is real and already measured (decision 68): a full grid build with the
flag off took 5.85 s; with it on, 326.7 s. That is why it was left off by default rather than
forgotten. So this task is not "flip a boolean" — it is deciding how that cost gets paid without
making a page anyone loads wait five and a half minutes, then building whichever answer the PI
picks and proving on live RCS08 data that no scientific value moved.

Constraint that shapes every option: `stability.py` may import from Biomarkers, never the reverse
(its own docstring makes that a hard rule and an earlier Track D draft broke it). Constraint on
process: CLAUDE.md §10 rule 8 — plan approval is not execution authority, so Phase 2 is a real stop.

## Next Step
Phase 1: measure the current cost again rather than trusting decision 68's numbers (CLAUDE.md §10
rule 3 forbids quoting a timing from a document), and find every code path that would have to set
the flag. Nothing is built until Phase 2's decision is answered by the PI.

## Current Phase
Phase 1 — in_progress

## Phases

### Phase 1: Establish the real cost and the real call sites
**Status:** in_progress

- [ ] Re-measure the flag-off and flag-on full grid build on RCS08 through the bridge, in
      alternating rounds (off, on, off, on), because the operating system's file cache favours
      whichever ran second. Decision 68's 5.85 s / 326.7 s pair is a document number and must not
      be quoted forward.
- [ ] Confirm by grep that no client code sets `IncludeCrossSettingStability` today, and list every
      place that would have to: `useBandSweepGrid.js`'s request body, and any other caller of
      `/api/queryClosedLoopDeployment` or `/api/queryBiomarkerAnalysis` that reaches the sweep.
- [ ] Read `_attach_grid_export_columns` and `raw_stability_result_for_point` in full and record
      what dominates the 300-plus seconds: how many (contact, centre) points are computed, how many
      distinct calls that is after the existing per-centre cache, and what each call costs.
      A per-point cost times a point count is what makes the options below concrete.
- [ ] Check whether the cost is per-participant-once or per-settings-change: the flag is folded into
      the sweep's own cache key, so establish whether changing an unrelated setting (a percentile
      cut, the pain score) throws the whole 300 s away.

### Phase 2: Put the cost question to the PI and get an answer
**Status:** pending

- [ ] Write the options up with the Phase 1 numbers attached to each, not in the abstract. The
      candidates, in the order they seem worth considering:
      (a) compute it in the background after the grid lands, so the page is fast and the column
          fills in a moment later;
      (b) compute it on demand for the one row a reader opens, rather than all of them;
      (c) compute it for every point but only when a reader explicitly asks, behind a button on the
          Closed-Loop panel that says what it will cost;
      (d) precompute for every participant on a schedule, off the request path entirely.
- [ ] State plainly for each option what a reader sees while the answer is missing, since this
      project's standing rule (decision 9, §2 principle 2) is that an absent finding is shown and
      labelled, never silently hidden.
- [ ] Get the PI's explicit go-ahead for one option. **This phase is a stop, not a formality** —
      CLAUDE.md §10 rule 8. Nothing in Phase 3 starts without it.

### Phase 3: Build the chosen option
**Status:** pending

- [ ] Build only what the chosen option needs, honouring the one-way import rule: the raw result is
      computed on the Biomarkers side, the four-valued translation happens on the Closed-Loop side,
      and `Biomarkers` never imports `ClosedLoopDeployment.stability`.
- [ ] Use the double-import spelling for any new module-level import, since the container resolves
      `modules.CacheStore` and the host suite resolves `CacheStore` — a single spelling breaks one
      runner at import time.
- [ ] If the sweep's stored response changes shape, bump `_BAND_SWEEP_RULE_VERSION` so an entry
      built under the old shape is never served as if it carried the new one.
- [ ] Keep `BandSweepGridPanel.js`'s existing "not yet computed" chip as the honest state for a row
      whose answer genuinely has not been computed, rather than replacing it with a blank.

### Phase 4: Prove it on live data before claiming anything
**Status:** pending

- [ ] Field count and difference count on RCS08, never a tolerance (`ARCHITECTURE_cache_store.md`
      §7). The specific thing to prove: turning the column on ADDS fields and moves no existing
      scientific value, the same shape decision 68 proved (0 dropped, 10,560 new, 22 differing and
      every one of those a timing field or the store key).
- [ ] Timings in alternating rounds, reported in the same message as the equality proof.
- [ ] Spot-check at least two real points against the single-candidate path the deployment page
      already runs today, which is the equality proof that matters: the grid's answer for a point
      must equal what that page reports for the same point. ONE_THREE_LEFT at 12.5 Hz is the known
      disagreement case (the retired flag reads "stable", the honest answer reads "cannot tell")
      and is the best single test.
- [ ] Both suites, re-run fresh and not carried forward from any document: container via the bridge,
      host via pytest. Note that the host suite carries one known environment failure
      (`test_no_directory_means_memory_only_and_not_a_failure`, decisions 84 and 85).

### Phase 5: Land it
**Status:** pending

- [ ] Rebuild the frontend if anything under `Client/src` changed, and commit the rebuilt
      `Client/build` chunks in the SAME commit as the source (CLAUDE.md §10 rule 2).
- [ ] Verify by string search that the changed panel text reached the served chunk, searching for a
      literal the panel owns rather than the component name (CLAUDE.md §8).
- [ ] Add a decision row to `DECISIONS_and_open_items.md` carrying the numbers, and close or amend
      the open item this resolves.
- [ ] Commit with the PI's identity inline and push to `origin/PS_closedloop_deployment`.

## Decisions Made
| # | Decision | Why | When |
|---|----------|-----|------|
| 1 | This gets its own plan directory rather than joining the finished caching plan. | CLAUDE.md §4 says a second, independent task gets its own directory and its own active-plan entry. The caching plan reached its end state and its commit and push already landed. | 2026-09-09 |
| 2 | Phase 2 is a hard stop for the PI's decision, not a checkbox to tick past. | The four options differ in what a clinician sees and in what the page costs, which is his call, not an implementation detail. CLAUDE.md §10 rule 8. | 2026-09-09 |
| 3 | Decision 68's timing pair is treated as a starting hypothesis, not a fact to quote. | CLAUDE.md §10 rule 3: never quote a timing from a document, including this project's own. Re-measure. | 2026-09-09 |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| (none yet) | — | — |
