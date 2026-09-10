# Task Plan: Closed-Loop grid stability column

## Goal
Make the calibrated grid on the Closed-Loop Deployment page carry its cross-setting stability
answer, instead of showing "stability: not yet computed" on every row forever, and make the
computation fast enough that carrying it is not a burden. Track D built both halves — the raw
answer per (sensing contact, band centre) point on the Biomarkers side, the honest four-valued
translation on the Closed-Loop side — and nothing has ever turned them on, because a full grid cost
over five minutes.

Measured this session (findings §8): **63% of every point is setup that does not depend on the
point at all**, and a further 8% is a mixed-model fit the grid path computes and throws away. Only
0.645 s of a 2.25 s point is the fit actually wanted. So the cost is mostly an artefact of calling
a single-candidate function in a loop, not an irreducible price.

The PI's answer on how the remaining cost is paid: **compute in the background after the grid
lands, so the page is usable first, AND precompute off the request path on a schedule, at least
daily.** Both, not either.

Constraint that shapes every option: `stability.py` may import from Biomarkers, never the reverse
(its own docstring makes that a hard rule and an earlier Track D draft broke it).

## Next Step
Phase 4: run the finished grid in the background after the page's own grid lands, and write the
result into the shared store with `writer=` and `provenance=`. The hard constraint discovered while
proving Phase 3: it must run in its OWN process, because a process that has already fitted anything
cannot fork (findings §13c).

## Current Phase
Phase 4 — background computation

## Phases

### Phase 1: Establish the real cost and the real call sites
**Status:** complete

- [x] Confirmed by grep that no client code sets `IncludeCrossSettingStability`: the only hits are
      the one read in `bravo_service.py`, a comment and a tooltip in `BandSweepGridPanel.js`, and
      documentation.
- [x] Read `_validate_band_core` in full and established which of its steps depend on the band
      centre. Four of the six do not, and none of the four takes a `channel` argument either, so the
      setup is participant-level and is currently redone for all 132 points.
- [x] Found that the grid path discards the `glmer` fit it pays for: `raw_stability_result_for_point`
      returns `core["stim"]` alone, while `_validate_band_core` runs
      `analytics.band_mixedmodel_inference` unconditionally first.
- [x] Measured the split live on RCS08 (`_probe_stability_cost.py`, three centres on
      ONE_THREE_LEFT): setup 1.451 s, discarded glmer 0.189 s, wanted fit 0.645 s, of a 2.25 s
      steady-state point. Full table in findings §8.
- [x] Established that `band_stim_stability` fits two R mixed models per point through pymer4/rpy2,
      so the fit itself cannot be vectorized — findings §8d records what can and cannot be done.

### Phase 2: The cost decision
**Status:** complete

- [x] Answered directly by the PI: background after the grid lands, AND a scheduled precompute off
      the request path at least daily. Both.
- [x] Recorded that the honest "not yet computed" chip stays as the state a reader sees while the
      background answer is still coming, rather than a blank or an optimistic default.

### Phase 3: Build the fast path
**Status:** complete

- [x] Added `stability_grid_for_participant` to `bravo_service.py`: participant-level setup once,
      then only `analytics.band_stim_stability` per point. Never runs `band_mixedmodel_inference`.
- [x] Extracted the shared setup into `_band_validation_setup`, called by BOTH `_validate_band_core`
      and the new function — one copy, not two.
- [x] Vectorizing the band-power extraction was NOT done, and the reason is measured: 93-98% of a
      call is inside R's two model fits and only 0.011 s is Python, so the whole available gain is
      about 1.5 s across a 132-point grid (findings §9a). Skipped deliberately, not overlooked.
- [x] Replaced pymer4 with a direct `lme4::glmer` call (`_binomial_glmer_loglik_pair`), keeping
      pymer4 as the reference implementation behind `USE_DIRECT_GLMER`. **5,148 fields compared,
      0 differing**; 77.8/77.0 s to 37.0/34.9 s.
- [x] Parallelised across the machine's usable core count via `sched_getaffinity`, never hardcoded.
      Parallel against serial: **5,148 fields compared, 0 differing, 0 points missing**.
- [x] Batch failure policy: carry on, stop after 3 consecutive RAISED points. Proven by forcing
      every fit to raise — 3 attempted, 129 never attempted, all three carrying the real reason.
- [x] Suites: container 590 passed 0 failed; host 992 passed, 42 skipped, 1 failed (the known
      environment mismatch of decisions 84/85, unrelated and unchanged).

### Phase 4: Background computation after the grid lands
**Status:** pending

- [ ] Return the grid immediately, then fill the stability column behind it. Find how this project
      already runs work off the response path — `AsyncJobScheduler` exists as a module and is the
      first place to look — rather than inventing a threading approach next to rpy2, which holds a
      single embedded R process.
- [ ] Write the finished column into the shared store as its own kind, with `writer=` and
      `provenance=` naming the tile entry and the pain-report snapshot, or the self-derived refusal
      cannot fire (CLAUDE.md §10 rule 6).
- [ ] The Closed-Loop panel reads the stored column when it exists and keeps showing the honest
      "not yet computed" chip when it does not. A reader must never see a blank cell that could be
      read as "stable".

### Phase 5: Scheduled precompute, off the request path
**Status:** pending

- [ ] Run it at least daily per participant, independent of whether anyone opened a page.
- [ ] Key it so a run whose inputs have not changed does no work: the store's own rule is that the
      key decides whether to write, not the caller (decision 26).
- [ ] Make a failed or half-finished run leave the previous answer in place rather than a partial
      grid, and make the failure visible somewhere a person will actually look.

### Phase 6: Prove it on live data before claiming anything
**Status:** pending

- [ ] Field count and difference count on RCS08, never a tolerance. The specific claim to prove:
      turning the column on ADDS fields and moves no existing scientific value.
- [ ] Timings in alternating rounds (old path, new path, old, new), reported in the same message as
      the equality proof. The hypothesis from findings §8c is ~297 s to ~86 s; the real pair
      replaces it.
- [ ] Spot-check ONE_THREE_LEFT at 12.5 Hz against the single-candidate path the deployment page
      already runs: the known disagreement case, where the retired flag reads "stable" and the
      honest answer reads "cannot tell". The probe already returned `lrt_p` = 0.0323 for that point,
      which is the number to reproduce through the new path.
- [ ] Both suites re-run fresh, not carried forward: container via the bridge, host via pytest.
      The host suite carries one known environment failure (decisions 84, 85).

### Phase 7: Land it
**Status:** pending

- [ ] Rebuild the frontend if anything under `Client/src` changed, and commit the rebuilt
      `Client/build` chunks in the SAME commit as the source (CLAUDE.md §10 rule 2).
- [ ] Verify by string search that any changed panel text reached the served chunk (CLAUDE.md §8).
- [ ] Add a decision row to `DECISIONS_and_open_items.md` carrying the real numbers.
- [ ] Commit with the PI's identity inline and push to `origin/PS_closedloop_deployment`.

## Decisions Made
| # | Decision | Why | When |
|---|----------|-----|------|
| 1 | This gets its own plan directory rather than joining the finished caching plan. | CLAUDE.md §4: a second, independent task gets its own directory and its own active-plan entry. | 2026-09-09 |
| 2 | Background after the grid lands, AND a scheduled precompute at least daily. Both. | The PI's direct answer to Phase 2. Background keeps the page usable for whoever opens it; the schedule means the answer is usually already there before anyone opens anything. | 2026-09-09 |
| 3 | The setup is hoisted out of the per-point loop and the discarded glmer fit is skipped, before any concurrency is considered. | Measured: 63% of a point is point-invariant setup and 8% is a fit whose result is thrown away. Both are deterministic wins with no concurrency risk, and together they predict ~297 s to ~86 s. Parallelism across rpy2's single embedded R process is the risky lever and is not taken first. | 2026-09-09 |
| 4 | "Vectorize the stability analysis" is answered honestly rather than claimed: the fit cannot be vectorized. | `band_stim_stability` fits two R mixed models per point through pymer4/rpy2 and takes the likelihood-ratio test between them. There is no numpy formulation and no way to batch it through rpy2. The band-power extraction feeding it is vectorizable and is worth about 0.02 s against a 0.645 s fit. Recorded in findings §8d so this is not re-litigated. | 2026-09-09 |
| 5 | The shared setup is extracted into one helper both paths call, never copied into a second implementation. | Two implementations of one thing drifting apart is the exact failure this repository already paid for with its two cache stores (decision 30), and a stability answer that differed between the grid and the single-candidate panel would be worse than no answer. | 2026-09-09 |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| Probe raised `ImproperlyConfigured: settings are not configured`. | 1 | The bridge does not set `DJANGO_SETTINGS_MODULE`. Copied the bootstrap the existing `_3way_*.py` probes already use: `os.environ.setdefault("DJANGO_SETTINGS_MODULE", "BRAVO.settings")` before `django.setup()`. |
