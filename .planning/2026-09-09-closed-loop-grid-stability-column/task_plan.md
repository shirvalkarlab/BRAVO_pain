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
Phase 7: land it. Nothing under `Client/src` changed in any phase, so no frontend rebuild applies;
what is left is the decision rows and the push.

## Current Phase
Phase 7 — landing

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
**Status:** complete

- [x] `AsyncJobScheduler` checked and ruled out: it is a Slurm cluster scheduler for recording
      processing, not a general off-request-path runner. Built a Django management command,
      `compute_stability_grid`, instead — which is also what gives Phase 5 its scheduled entry point,
      so there is one implementation rather than two.
- [x] `compute_and_store_stability_grid` writes the finished grid as kind
      `biomarker_band_stability_grid` with `writer="biomarkers"` and the sweep's own provenance
      chain (the tile entry and the pain-report snapshot).
- [x] Proven live on RCS08: 132 of 132 points stored in 23.6 s; a second run does no fitting at all
      (`already_current`, 4.5 s), so the key decides the work as decision 26 requires; the stored
      grid reads back with ONE_THREE_LEFT at 12.5 Hz carrying `lrt_p` 0.032285156521398184,
      byte-identical to the value measured before it was ever stored.
- [x] `adapter.band_sweep_grid_for_closed_loop` now falls back to the stored grid when a row carries
      no inline result, and reports `cross_setting_stability_from_store` so a reader can tell a
      background answer from an inline one. The row's own field still wins when present.
- [x] **The blocker is cleared** (findings §14, §15): one appended `sys.path` entry for `modules/` in
      `BRAVO/settings.py`, the PI's own choice between two fix shapes. Commit `c6b8690b`.
- [x] The sweep starts the command once its own grid lands, on BOTH return paths — freshly built and
      served from the store — because the reader is looking at a grid either way
      (`launch_stability_grid_in_background`). Detached with `start_new_session`, so a worker being
      recycled does not take a half-finished run down with it. The response carries
      `stability_background`, saying what happened, so a live check needs no log file.
- [x] Started only when there is something to do: skipped when the answer under this exact key is
      already stored, when another run for the same key is inside the 600 s cooldown (a FILE, because
      four gunicorn workers are four independent memories), when the request carries its own pain
      reports (a separate process cannot reproduce them), when the caller asked for the inline
      column, and when the switch `STABILITY_GRID_BACKGROUND` is off.
- [x] Only the sweep's own settings travel, by whitelist (`STABILITY_GRID_SETTING_KEYS`), through a
      new `--request-json` argument the command filters again on arrival. A command line is visible
      in the process list, so pain-report rows and the REDCap field map must never reach it.
- [x] **A real defect found by the live proof and fixed** (findings §16): the computation rebuilt the
      sweep's key from the response's echoed `settings_applied` block, which is NOT the block the
      sweep keys itself on. Measured on RCS08: the page asked for `dc6cec1b...`, the run it had just
      started wrote `c02e9aca...`. Fixed by carrying the sweep's own key in the response; the
      re-derivation is deleted outright. Re-proven: asked for and written are now the same key,
      `a2954bda...`.
- [x] **A second real defect, found by the container suite**: the launcher was reachable from the
      unit tests, which really did start `manage.py compute_stability_grid` for a made-up
      participant. A background run is now refused while the store is pointed at a caller's own root
      (`STABILITY_GRID_LAUNCH_UNDER_OVERRIDE_ROOT`), the same rule the ledger already applies to its
      own writes.
- [x] Proven live on RCS08, twice, the whole loop: page request 11.3 s fresh / 3.2-3.8 s served, the
      run finishing 10.8-12.7 s later with 132 of 132 points, the known case ONE_THREE_LEFT at
      12.5 Hz reading `lrt_p` 0.032285156521398184 exactly as before it was ever stored, the second
      request reporting "already stored" and starting nothing, and the Closed-Loop reader returning
      264 rows all carrying a stored answer.
- [x] Suites: container 590 -> **605 passed, 0 failed** (+15 new tests); host **993 passed, 42
      skipped, 1 failed** — the known environment mismatch of decisions 84/85, unchanged.

### Phase 5: Scheduled precompute, off the request path
**Status:** complete

- [x] `BRAVO/_agent_bridge/stability_precompute_loop.sh` runs `compute_stability_grid --all --json`
      every 86,400 s, started by `boot.sh` the same best-effort way the agent bridge itself is, so a
      failure there never blocks the app starting. **The PI chose the dev compose override**, so the
      shared `docker-compose.yml` and the production image are untouched.
- [x] Every knob is an environment variable, so nothing needs editing to change it:
      `STABILITY_PRECOMPUTE=0` turns it off, `STABILITY_PRECOMPUTE_INTERVAL_SECONDS` sets the gap,
      `STABILITY_PRECOMPUTE_FIRST_DELAY_SECONDS` (default 600) keeps the first pass out of the way of
      container start, migrations and the first page loads.
- [x] One loop, not several: a pid lock that is ignored when that process is gone, so a hard
      container kill cannot wedge it. Proven — a second loop refused with "another loop is already
      running (pid 2050348)".
- [x] The key decides whether any work happens, so a daily pass over every participant is cheap:
      measured 2.9-3.4 s for RCS08 when nothing had moved, against 10.8-12.7 s for a real rebuild.
- [x] **A half-finished run leaves the previous answer in place.** The batch policy stops after three
      points in a row raise, and the store keeps ONE current entry per participant per kind replaced
      whole — so writing a stopped-early grid would have destroyed the previous answer, not narrowed
      it, and rows that had a real answer an hour ago would read "not yet computed". Now refused and
      reported, with a test that also proves a COMPLETE run still replaces it (a guard that froze the
      answer forever would be worse than the bug).
- [x] The failure is visible where a person looks: the command writes it to standard error and exits
      non-zero, the loop logs "PASS FINISHED WITH FAILURES", and a participant with no recordings is
      correctly NOT counted as a failure.
- [x] Proven live: a full pass over both participants — one correctly "the calibrated grid has no
      points for this participant", RCS08 `already_current` in 3.425 s — exit status 0.
- [x] Suites: container **606 passed, 0 failed**; host **993 passed, 42 skipped, 1 failed** (known).

### Phase 6: Prove it on live data before claiming anything
**Status:** complete

- [x] **The two routes give the same answers.** The inline column (the only route before this work)
      against the background-computed stored grid, on RCS08: 132 points each, **5,148 fields
      compared, 0 differing**, 0 present in only one. Never a tolerance — values compared exactly.
- [x] **Turning the column on ADDS fields and moves no existing scientific value.** The Closed-Loop
      response with the stored grid absent against present: 27,889 fields to 34,225. **6,336 fields
      added, every one under `cross_setting_stability`; 0 dropped; of the 27,889 in common, 2
      moved** — `cross_setting_stability_from_store` (0 to 264) and `cross_setting_stability_
      included`, which are the column's own bookkeeping. **Zero scientific values moved.**
- [x] **Timings in alternating rounds**, old, new, old, new: the inline route 292.70 s and 289.87 s;
      the new route's page request 10.60 s and 10.64 s, its background run 15.93 s and 13.56 s.
      **The page went from about 291 s to about 10.6 s (~27x), and the complete answer from about
      291 s to about 25 s (~11.6x).** The Phase 1 hypothesis of ~297 s to ~86 s is superseded by
      this measured pair; the real gain is larger, because Phase 3 also dropped pymer4 and forked
      across cores. The page's own background launch was switched off for these measurements so a
      run it started could not overlap the run being timed — stated rather than hidden.
- [x] The ONE_THREE_LEFT 12.5 Hz spot-check reproduces `lrt_p` 0.032285156521398184 through the new
      path — but it is NOT the "cannot tell" case the code comments claimed, and that is resolved
      separately in findings §19 rather than noted and left.
- [x] Suites re-run fresh: container **606 passed, 0 failed**; host **993 passed, 42 skipped, 1
      failed** (the known environment mismatch of decisions 84, 85).

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
| 11 | The documented disagreement example is re-anchored on ONE_THREE_LEFT at 17.5 Hz, with the old 12.5 Hz numbers kept as dated history rather than deleted. | The comment presented p = 0.290 and "cannot tell" as current fact and neither is true today. Deleting the old pair would hide that a documented scientific example moved; keeping it undated would keep the falsehood. The superseded-row convention this project already uses for decisions applies to examples too. | 2026-09-09 |
| 12 | Every quoted p-value for one of these points now carries its band width and binarisation. | Measured: the same electrode and centre gives p = 0.286 at a 1 Hz band and 0.032 at 5 Hz. A p-value quoted without its band width is not a reproducible claim, which is what made the old example impossible to check. | 2026-09-09 |
| 9 | The daily pass is started from `boot.sh` in the dev compose override, not from the shared compose file or a cron entry in the image. | The PI's own choice. It touches nothing in `docker-compose.yml` or the production image, mirrors the best-effort pattern the agent bridge already uses in the same file, and is one block to remove. It takes effect on the next container start. | 2026-09-09 |
| 10 | A run that stopped early never replaces a stored answer, and that is a failure a scheduler can alert on. | The store keeps one current entry per participant per kind, replaced whole, so a partial write destroys the previous answer rather than narrowing it — and nothing on any page would show it, because the page would simply go back to "not yet computed". | 2026-09-09 |
| 6 | The background run is started by `subprocess.Popen` on the management command, detached, rather than by a thread. | A thread inside a gunicorn worker cannot fork safely once that worker has answered a single-candidate request, so it would silently take the serial path — the same answers, several times slower. A separate process is what makes the fast path reachable at all. | 2026-09-09 |
| 7 | Anything derived from the calibrated grid takes the sweep's OWN key out of the response and never re-derives one. | The re-derivation was wrong in a way nothing could see: the echoed settings block is not the settings block the sweep keys itself on, so the page and the background run named different keys for one grid, every page load started a fresh whole-machine job, and none of them ever satisfied the page. Proven live before the fix (`dc6cec1b` asked for, `c02e9aca` written) and after (`a2954bda` both). | 2026-09-09 |
| 8 | A background run is refused while the store is pointed at a caller's own root, and the default is the refusing one. | The container suite really was starting `manage.py compute_stability_grid --participant u` for the test bench's made-up participant. A unit suite must not start whole-machine jobs, and an answer written into a temporary directory is read by nothing. Mirrors the ledger's own production-root rule. | 2026-09-09 |
| 5 | The shared setup is extracted into one helper both paths call, never copied into a second implementation. | Two implementations of one thing drifting apart is the exact failure this repository already paid for with its two cache stores (decision 30), and a stability answer that differed between the grid and the single-candidate panel would be worse than no answer. | 2026-09-09 |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| The page asked for stability key `dc6cec1b...` while the run it had just started wrote `c02e9aca...`, so the answer could never satisfy the page and every load would start another job. | 1 | The computation rebuilt the sweep's key from the response's echoed `settings_applied` block, which carries three fields the real key does not and lacks two it does, and resolved the pain score without the sweep's own `SweepMetric` override. The response now carries the sweep's own key; the second derivation is deleted. |
| Container suite 603 passed 1 failed: a served response no longer matched a freshly built one. | 1 | The symptom, not the cause. The cause was that the launcher was reachable from the unit tests and was starting real background processes for the bench's made-up participant. Guarded on the production store root rather than papering over the comparison. |
| My own new assertion `"STABILITY_GRID_RULE_VERSION," not in src` was a false positive. | 1 | The computation's stored payload legitimately carries that constant as one of its fields. Tightened the check to the tuple's actual opening, `"(STABILITY_GRID_KIND, STABILITY_GRID_RULE_VERSION"`. |
| The Closed-Loop reader came back empty. | 1 | My probe's error, not the code's: `band_sweep_grid_for_closed_loop` takes the participant uid, and I passed it a request dict. Called correctly it returns 264 rows. |
| Probe raised `ImproperlyConfigured: settings are not configured`. | 1 | The bridge does not set `DJANGO_SETTINGS_MODULE`. Copied the bootstrap the existing `_3way_*.py` probes already use: `os.environ.setdefault("DJANGO_SETTINGS_MODULE", "BRAVO.settings")` before `django.setup()`. |
