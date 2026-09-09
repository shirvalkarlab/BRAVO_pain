# Task Plan: Closed-Loop Deployment module — DBS gate audit and fix

## Goal
Audit the ClosedLoopDeployment module against the DBS deployment gates/criteria documented across
`DECISIONS_and_open_items.md` (decision 9's three-state gate discipline, the 51-rule device screen,
the stim-stability equivalence test, etc.), report any gap between what should gate deployability
and what the code actually enforces, and — if the PI approves — fix confirmed defects.

## Next Step
Complete. Both confirmed defects found in the audit (decision 82) are fixed (decision 83), tested
(2 new pure-function unit tests, container suite 582->584/0), live-proven on RCS08 for the exact
documented disagreement case (ONE_THREE_LEFT at 12.5 Hz), and two confirmed-dead frontend files
deleted. Committed and pushed. **The host suite WAS subsequently run** (decision 84), at the user's
follow-up request, by installing pytest inside the live container (`--break-system-packages`, no
venv tooling available): 990 passed, 42 skipped, 1 failed. The one failure is a pre-existing
environment-assumption mismatch in the test itself (it assumes no `DATASERVER_PATH` is configured,
true only in the bare host env this suite was designed for, not inside the live container), not a
regression from anything this session changed — confirmed by reading `store.py`'s `root_dir()`
directly. Running it also surfaced a real, self-healing cache-eviction side effect and a genuine,
separate, flagged-not-fixed scoping gap in `_sweep_superseded` (open item 25). Nothing left queued.

## Current Phase
Phase 4 (final)

## Phases

### Phase 1: Audit the deployment module against the documented DBS gates
- [x] Dispatched one thorough read-only audit agent, briefed with the relevant decision-log entries
      (9, 33, 40, 45, 47, 52, 55, 56, 65, 67, 68, 70, 74, 75) and house-rules claim restrictions, to
      map every gate in `ClosedLoopDeployment/` and `Biomarkers.bravo_service.deployment_summary()`
      and check each against the code directly rather than trusting any prior document's summary.
- [x] Independently re-verified the agent's headline finding myself by reading the exact lines
      cited (`bravo_service.py:6063`, `analytics.py:5436`) before reporting it as confirmed.
- [x] Reported to the user: 13 criteria found, 10 fully enforced, 1 confirmed live defect
      (`deployment_summary`'s `stim_stable` gate reads the retired boolean instead of the three-way
      `stability_verdict`), 2 correctly-built checks with zero production callers
      (`direction_consistency`, `reliable_change`).
- [x] `DECISIONS_and_open_items.md` decision 82 added, recording the audit.
- **Status:** complete

### Phase 2: Scope the fix before touching a clinician-facing safety page
- [x] Dispatched a second read-only agent specifically to map the actual call contexts, inputs, and
      real overlap between `deployment_summary()` and `pipeline.run()` before any edit — found the
      two verdict systems already stopped fighting on 2026-09-04 (the card's headline already comes
      from the pipeline; only `stim_stable` is a genuine duplicate with an existing correct
      translation to redirect to; `adaptive_band` duplicates D08's INTENT but with a weaker
      centre-only check; the other five card gates are exploration-time statistics with no
      pipeline equivalent and must not be merged).
- [x] Verified independently: grepped for importers of the two components the scoping agent found
      dead (`DeploymentEvidencePanel.js`, `DeploymentVerdictStrip.js`) across the whole frontend,
      not just the one file the agent checked — confirmed zero live imports either way.
- [x] Put the three resulting judgment calls to the user rather than deciding unilaterally (fix
      `adaptive_band` now or later; add device-rule detail into the sign-off card or leave the
      pipeline driving the headline as today; delete the two dead files or leave them) — all three
      answered with the recommended option.
- **Status:** complete

### Phase 3: Implement, test, and prove the two fixes
- [x] `stim_stable` gate: extracted `_deployment_summary_stim_stable_gate(st)`, a pure function
      mirroring the existing `_band_decide_verdict` pattern, reading `stability_verdict` instead of
      the retired boolean. Not imported from `ClosedLoopDeployment.stability` (which already has
      the identical mapping) because `Biomarkers` may not import `ClosedLoopDeployment` — the
      mapping is inlined against the same source field instead.
- [x] `adaptive_band` gate: extracted `_deployment_summary_adaptive_band_gate(center_hz,
      band_width_hz)`, checking band EDGES against 8-30 Hz (matching
      `ClosedLoopDeployment/constraints.py`'s D08 rule) instead of the bare centre.
- [x] Two new regression tests added to `test_band_candidate.py`, mirroring its existing
      `_band_decide_verdict` test style (pure, no DB): both pass, plus the full file's other 6
      pre-existing tests still pass.
- [x] Full container suite re-run: 582 -> 584 (+2), 0 failed.
- [x] Live proof on RCS08: temporarily swapped the pre-fix file into the live-mounted container
      (via a saved backup, never `git checkout`), ran the exact documented disagreement case
      (ONE_THREE_LEFT at 12.5 Hz) and a second edge-vs-centre case (9.5 Hz), then restored the fix
      and re-ran the full container suite to confirm the restoration was byte-exact (584/0 again).
      Both behavior changes matched the fix's intent exactly (see progress.md for the numbers).
- [x] Deleted the two confirmed-dead frontend files. Frontend rebuilt clean; grepped the fresh
      bundle chunks and confirmed both deleted files' distinctive strings are absent everywhere,
      and the still-live `DeploySignoffCard.js` (which renders the fixed gate) still reaches its
      own chunk.
- [x] Attempted the host suite (ClosedLoopDeployment/StimOptimizer, pytest-based) — pytest is not
      installed on this sandbox's Python nor inside the live container, and the `bravo_app` host
      environment CLAUDE.md documents is not reachable from this session. Could not run it; ran a
      substitute check instead (confirmed `ClosedLoopDeployment.adapter`, `ClosedLoopDeployment.
      stability` and the edited `Biomarkers.bravo_service` still import together cleanly, which is
      the one-way-import edge this fix depends on not inverting) and disclosed the gap honestly
      rather than claiming a suite run that didn't happen.
- [x] `DECISIONS_and_open_items.md` decision 83 added, with both live proof numbers.
- **Status:** complete

### Phase 4: Actually run the host suite, at the user's follow-up request
- [x] Installed pytest inside the live container (`pip install --break-system-packages pytest`) —
      `python3-venv` is not installed, so a proper isolated virtual environment (the safer route)
      was not available; installed directly into the container's system Python instead, as the user
      explicitly authorized ("install pytest ... on the OrbStack server").
- [x] Ran `PYTHONPATH=. python3 -B -m pytest ClosedLoopDeployment/tests StimOptimizer/tests
      CacheStore/tests DecodeCommon/tests -q -W ignore` against the live-mounted source. Result:
      990 passed, 42 skipped, 1 failed.
- [x] Investigated the one failure by reading the code, not assuming: confirmed it reproduces in
      isolation (not test-order pollution), then traced it to `CacheStore/store.py`'s `root_dir()`
      falling through to the real `DATASERVER_PATH`-derived production root when the test's
      monkeypatched override is `None` — a mismatch between the test's assumption (no directory
      configured means "nowhere to write") and the live container's actual, fully-configured Django
      settings. None of decision 83's edited files are involved.
- [x] Investigated the real side effect of the test's own write inside the live container: read
      `_sweep_superseded` directly and found it keys eviction on `participant_uid is None`, which
      `ClosedLoopDeployment.adapter._shared_store` always passes regardless of the real participant
      — confirmed the `"inputs"`-kind cache directory was empty immediately after, consistent with
      the test's throwaway write evicting whatever real entry was resident. Confirmed this is
      self-healing (next real request rebuilds and re-caches, per the already-documented cold/warm
      timings) and recorded the underlying scoping gap as new open item 25, flagged not fixed.
- [x] `DECISIONS_and_open_items.md` decision 84 added with the real suite numbers, the root-cause
      analysis, and open item 25.
- **Status:** complete

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| New plan directory rather than folding into the Biomarkers efficiency plan. | Different module (ClosedLoopDeployment, not Biomarkers), different goal (a safety-critical gate defect, not efficiency/redundancy) — CLAUDE.md §4's own rule for when a second, independent task gets its own plan. |
| Scoped the fix with a dedicated research agent before writing any code, given this is a clinician-facing DBS-programming page. | The user's request ("wire overlapping checks... use the pipeline for device rules") did not map cleanly onto the actual code once read closely — the two verdict systems had already been reconciled at the frontend layer on 2026-09-04, so a literal reading of the request risked reintroducing the exact two-verdicts problem that rebuild fixed. Surfaced this to the user rather than guessing. |
| Extracted both fixes into their own pure, testable functions rather than fixing inline. | Mirrors this file's own established `_band_decide_verdict` precedent, and is the only way to pin the exact bug (an "inconclusive" verdict rendering as "pass") with a fast, DB-free regression test rather than only a live RCS08 check. |
| Did not add device-rule duplication into `deployment_summary()`'s own payload. | The pipeline's eligibility verdict already drives the sign-off card's headline (fixed 2026-09-04); duplicating it inside the card's own response would recreate the two-independently-computed-verdicts problem, confirmed with the user before skipping this. |

## Errors Encountered
| Error | Resolution |
|-------|------------|
| Host suite (`ClosedLoopDeployment/tests`, `StimOptimizer/tests`) could not be run: no `pytest` on this sandbox's Python interpreters, and none inside the live container either. | Ran a substitute cross-module import check instead (confirmed clean) and disclosed the gap explicitly rather than claiming the suite ran. |
