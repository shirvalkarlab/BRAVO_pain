# Plan: Biomarkers backend efficiency and redundancy fixes (review findings 1-6)

**Written 2026-09-08.** Source: `.planning/2026-09-08-biomarkers-module-efficiency-and-redunda/findings.md`,
Agent A's backend review, findings 1 through 6 (finding 7, `SlidingWindow`, is a parked behavior
decision and stays out of scope here — the PI asked for "items one through six" specifically).

**Status: PLAN ONLY. No code has been changed.** Per CLAUDE.md §10 rule 8, plan approval is not
execution authority — implementation starts only after an explicit go-ahead in chat.

## Branching note (overrides swarm-plan's generic default)

`swarm-plan`'s own template assumes trunk-based development with one branch and one PR per task,
merged to `main`. **This repository has no `main` branch** and CLAUDE.md §4 explicitly says so:
the working branch is the long-lived `PS_closedloop_deployment`, and every decision in
`DECISIONS_and_open_items.md` (37 through 78) landed as a direct, sequential commit on it — no
feature branches, no PRs. This plan follows that established pattern: six commits, in the merge
order below, straight onto `PS_closedloop_deployment`, each with its own equality proof, each
independently revertable with `git revert` (the two-way-door property swarm-plan's own framework
cares about is satisfied by clean, single-purpose commits, not by branch isolation).

## Decision classification

All six items are **Two-Way Door** decisions: internal implementation/performance changes with no
external contract, each independently revertible, each protected by an equality proof against live
RCS08 data before it's considered done. No ADR is needed — this `plan_*.md` is the only artifact
this work needs, per the Small-Feature tier (this is well under a day of focused work across six
small, independently-mergeable commits).

## Recommended merge order and why

Tasks 1, 2, 3 and 5 all touch `bravo_service.py`'s `run_for_participant`/`_build_availability`
region (confirmed by fresh reads: recordings loads at lines ~4006-4023 and ~4114-4123, the dead
spectrum calls at 3780-3787/4139-4145, `_build_availability`'s signature at line 3674). Sequencing
them avoids one task's diff shifting another's line numbers mid-flight. Tasks 4 and 6 touch
different files (`adapter.py`, `routines/analytics.py`) and can land in any order relative to the
others.

**Order: 1 → 2 → 6 → 4 → 3 → 5** (smallest/safest first; 3 and 5 last because they're the two
most structurally invasive and benefit from the smaller cleanups landing first).

---

## Task 1 — Stop shipping the unread `pro_lsb_spectrum` field

**Files:** `BRAVO/modules/Biomarkers/bravo_service.py`
**Size:** ~10 lines removed. ~15 minutes.

`_build_availability` (lines 3780-3787) calls `_pro_lsb_spectrum_cached(...)` and writes the result
into the response dict as `"pro_lsb_spectrum"` (line 3865). A fresh grep of `Client/src/` confirms,
again, zero reads of this key anywhere in the frontend. `_pro_lsb_spectrum_cached` (line 936) is a
pure memoized computation with no side effect anything else depends on — safe to delete outright.

**Acceptance criteria:**
- Lines 3780-3787 and the `"pro_lsb_spectrum"` dict entry at line 3865 removed.
- Equality proof on live RCS08 (`ARCHITECTURE_cache_store.md` §7 procedure): full
  `_build_availability` response captured before and after. Expect the `pro_lsb_spectrum` subtree's
  fields to disappear and **zero** other fields to change value. Report the exact field count
  removed and the difference count on every remaining common field (must be 0).
- Container and host suites re-run fresh and both green (never quote a stale count — CLAUDE.md
  §10 rule 3).

## Task 2 — Skip building the discarded spectrum in the Recompute path

**Files:** `BRAVO/modules/Biomarkers/bravo_service.py`, `BRAVO/modules/Biomarkers/routines/availability.py`
**Size:** ~30-40 lines changed across two functions. ~30 minutes.

`_live_pro_lsb_spectrum` (bravo_service.py:1573) returns `(spectra, stats)`; `run_for_participant`
(line 4139) uses only `stats` (as `live_match_stats`, feeding a live matching-controls caption) and
discards `spectra`. But `availability.live_lsb_spectrum_match` (routines/availability.py:1837-2062)
still does the real per-report Python-loop work to build `spectra` (the per-channel dict/list
construction around lines 2000-2008 and 2041-2048).

**Change:** add an optional keyword argument (`return_spectra=False`, or equivalent) to both
`_live_pro_lsb_spectrum` and `availability.live_lsb_spectrum_match`, defaulting to `False` so every
existing caller's behavior is unchanged unless it opts in. When `False`, skip the per-channel dict
accumulation in the loop. Call sites confirmed by fresh grep, all of which must keep passing
unmodified: `bravo_service.py:4139` (`run_for_participant`, pass `return_spectra=False`),
`bravo_service.py:1596` (internal, unaffected), tests `test_band_time_sweep.py`,
`test_shared_raw_lsb_cache.py`, `test_live_match_vectorised.py`, `test_per_pro_lsb.py`,
`test_match_direction.py` (must all pass with the new default; none of them need updating unless
they explicitly want the old always-build behavior, in which case they pass `return_spectra=True`
explicitly).

**Acceptance criteria:**
- New keyword argument, default preserves current behavior for every caller that doesn't pass it.
- `run_for_participant` passes `return_spectra=False` (it never used the value anyway).
- Equality proof on live RCS08: `live_match_stats` and every other field in `run_for_participant`'s
  response identical before/after — field count + difference count, 0 differences.
- Timing in alternating rounds (CLAUDE.md §10 rule 4): report `run_for_participant`'s wall-clock
  before and after, at least two rounds each, in alternating order.
- All five named test files pass unchanged; container/host suites green.

## Task 6 — Remove the now-fully-dead `spectral_feature_importance` function

**Files:** `BRAVO/modules/Biomarkers/routines/analytics.py`, `BRAVO/modules/Biomarkers/tests/test_analytics.py`, docstring cleanup in `bravo_service.py` and `routines/streaming_psd.py`
**Size:** ~750 lines removed from analytics.py (function body lines 1259-1993, plus its sole-use
helper `_spectral_cv_threads` lines 1134-1155), an unknown but nontrivial number of lines removed
from `test_analytics.py` (confirmed ~18 reference lines: 468,470,490,499,517,527,572,588,624,679,
744,753-754,769,865,1244,2679-2680,2904), plus 6 stale-comment edits. ~45 minutes given the test
file surgery.

**Verified this is safe to delete, not one of CLAUDE.md's deliberate-dead-code exceptions:**
decision 77's exact text (`DECISIONS_and_open_items.md` line 102) reads: *"Backend:
`spectral_feature_importance` dropped from `bravo_service.py`'s `td_tasks`; its
`pro_lsb_spectrum_by_channel` parameter removed from `_compute_analytics` too; `_live_pro_lsb_spectrum`'s
own call is kept because its second return value, `live_match_stats`, still feeds a live
matching-controls caption."* This describes removing the **call site**, not preserving the
**function**. No decision-log entry states a reason to keep `spectral_feature_importance` itself
around (unlike `LSB_RULE_OF_THUMB`/`LFP_POWER_LSB_TO_UV2`, which carry an explicit documented
reason in CLAUDE.md §2 principle 4). `_spectral_cv_threads` (analytics.py:1134-1155) has exactly
one call site, inside `spectral_feature_importance` itself (line 1613) — confirmed dead the moment
the function it serves is gone.

**The test file needs real surgery, not a skip.** `test_analytics.py` directly unit-tests
`spectral_feature_importance` as a pure function, independent of any production caller — per
CLAUDE.md §2 principle 2, "a test whose name asserts something untrue is worse than no test."
Since the function will no longer exist, these tests must be **deleted**, not marked `xfail` or
silently skipped.

**Acceptance criteria:**
- `spectral_feature_importance` (analytics.py:1259-1993) and `_spectral_cv_threads`
  (analytics.py:1134-1155) deleted.
- All ~18 `test_analytics.py` lines/blocks that test `spectral_feature_importance` deleted outright.
- Fresh `grep -rn "spectral_feature_importance\|_spectral_cv_threads"` across the repo (excluding
  `docs/archive/`) returns zero hits in live code or tests.
- The 6 stale docstring references cleaned up: `bravo_service.py:3274-3279` (6-line block),
  `bravo_service.py:4106`, `streaming_psd.py:730,821,1030,1041` — reworded to describe only what
  actually still happens, not what the removed function used to do.
- Container and host suites re-run fresh; report the exact new pass count (it will be LOWER than
  before by however many tests were removed — state the before/after numbers, never assume).

## Task 4 — Vectorize `adapter.align_pros(target="chronic")`

**Files:** `BRAVO/modules/Biomarkers/adapter.py`
**Size:** ~20 lines changed (lines 264-287). ~30 minutes.

Current code (adapter.py:264-283) loops over every chronic sample and, per sample, does a dict
lookup plus a `.mean()` call per metric (up to 3 metrics) on a pre-grouped sub-frame. Replace with
one vectorized aggregation: `df.groupby("_date")[metrics].mean()` computed once, then joined onto
the chronic timestamps by date (via `.reindex()`/`.map()`), instead of one `.mean()` call per row
per metric. Confirmed callers: `pipeline.py:610` (`target="session"`, unaffected — different
branch), `adapter.py:604` (`target="chronic"`, the one being changed), and `test_adapter.py`
(lines 166, 183, 819, 839, 857, 915).

**Acceptance criteria:**
- The per-row loop replaced with a groupby-based join; output DataFrame has the identical column
  set, row count, and dtypes as before (`["time", "lfp", "stim_amplitude"] + metrics`).
- Equality proof on live RCS08: `align_pros(target="chronic")`'s full output DataFrame compared
  before/after, every field, 0 differences (never a tolerance — a metric mean that's "close" but
  not identical is a real bug here, not noise).
- Timing in alternating rounds; report the actual speedup honestly, including if it turns out to be
  small on this participant's current chronic-sample count — don't assume the vectorization pays
  off by a specific factor before measuring.
- `test_adapter.py`'s existing `align_pros` tests pass unchanged.

## Task 3 — Eliminate the duplicate recordings load in one request

**Files:** `BRAVO/modules/Biomarkers/bravo_service.py`
**Size:** ~40-60 lines changed (a new optional-parameter signature plus the call-site wiring).
~45 minutes — the most structurally invasive of the six.

`run_for_participant` (line 4114) loads `AVAILABILITY_PSD_TYPES` recordings and derives
`_scan_sensing_idx`/`_scan_event_blocks`/`_scan_montage_blocks` from them (lines 4116-4123). It
then calls `_build_availability` (line 4222), whose current signature
(`_build_availability(participant_uid, *, chronic_list, powerdomain_list, td_list, pro_df,
label_metric, region_map, warm=False, native_lsb_tolerance_s=120.0)`, line 3674) has no way to
receive what was already loaded — so it reloads everything from scratch internally
(`_load_recordings` again at 3695, `_build_sensing_config_index` again at 3709,
`_event_psd_lsb_blocks` again at 3754).

**Change:** add optional keyword parameters to `_build_availability`
(`psd_list=None, sensing_index=None, event_psd_blocks=None, montage_psd_blocks=None`); when
provided, skip the three internal reload steps and use them directly. `run_for_participant` passes
through what it already has. The other two confirmed callers of `_build_availability`
(`availability_for_participant`'s two call sites, lines 3903 and 3931) omit the new parameters and
keep their current reload-every-time behavior unchanged — this is purely additive.

**Acceptance criteria:**
- `_build_availability`'s new parameters are optional and default to `None`/current behavior; the
  two `availability_for_participant` call sites are untouched and their tests
  (`test_availability.py`) still pass exactly as before.
- `run_for_participant` passes its already-loaded `psd_list`/`sensing_index`/blocks through instead
  of letting `_build_availability` reload them.
- Equality proof on live RCS08: `run_for_participant`'s full response before/after, field count +
  difference count, 0 differences except timing fields.
- Timing in alternating rounds: report the wall-clock saved by skipping one full recordings
  reload+decode cycle.
- `test_availability.py`, `test_per_pro_lsb.py`, `test_band_time_sweep.py`,
  `test_live_match_vectorised.py` all pass; container/host suites green.

## Task 5 — No-expiry cache for the chronic/powerdomain branch

**Files:** `BRAVO/modules/Biomarkers/bravo_service.py`
**Size:** ~30-50 lines (a new memo mirroring the existing pattern, plus its call-site wiring).
~30-40 minutes.

Chronic and powerdomain recordings are loaded at `bravo_service.py:4006-4007`
(`_load_recordings(participant_uid, CHRONIC_TYPES)`,
`_load_recordings(participant_uid, POWERDOMAIN_TYPES)`), concatenated at line 4013, then run
through `pipeline.run_powerdomain_branch` → `adapter.bravo_chronic_to_lfp_df` → `align_pros` +
KMeans — fully fresh on every full-compute request, with no cache. Decision 22 (as amended by 78)
explicitly permits a no-expiry cache here: recordings are immutable once exported.

**Recommended approach (from the research agent's comparison):** an in-process memo, the same
shape as the existing `_RECORDINGS_SETUP_MEMO` (bravo_service.py:791-902 — keyed on
`participant_uid`, no expiry, a bounded FIFO of 8 entries, a lock around writes, holding ONLY
recordings-derived data), rather than the full `CacheStore` module. Reasoning: this computation
runs entirely within one gunicorn worker process with no cross-module handoff, so `CacheStore`'s
`writer=`/`provenance=` machinery (built for cross-module provenance tracking, per
`ARCHITECTURE_cache_store.md`) would be unnecessary weight for a same-process, same-request-shape
memo. Either extend `_RECORDINGS_SETUP_MEMO` to also hold the concatenated `power_list` if its key
shape already fits, or add a sibling `_CHRONIC_POWER_LIST_MEMO` with the identical lock/size/no-expiry
pattern if it doesn't — the implementer should re-verify which fits at the time, since this is the
one place in this plan where the exact mechanism (extend vs. new memo) is a judgment call to make
against the code as it stands when this task starts, not a decision to lock in now.

**Acceptance criteria:**
- New or extended memo holds only recording-derived data (the concatenated `power_list`), never any
  pain-report/PRO data (decision 22's hard rule).
- No expiry, keyed on participant identity (and whatever the recordings' own content signature is,
  matching decision 24's "the key decides whether to write" convention used elsewhere in this repo
  — not on file names, which can carry patient information).
- Equality proof: cold call vs. warm call on live RCS08, full response, field count + difference
  count, 0 differences.
- Timing in alternating rounds: cold vs. warm wall-clock, at least two of each.
- Container and host suites green.

---

## Cross-cutting requirements for every task (from CLAUDE.md §2 principle 2 and §10)

- **A speed claim and its equality proof appear in the same report** — never one without the other.
- **Field count and difference count, never a tolerance.** A value that's "close" is a bug here,
  not noise.
- **Timings in alternating rounds** (before, after, before, after) — the OS file cache favors
  whichever ran second, so a single before/after pair proves nothing.
- **Re-run both test suites fresh before claiming a count** — container (`BRAVO/_agent_bridge/
  bridge_client.py ... _agent_bridge/run_tests.py`) and host (`pytest ClosedLoopDeployment/tests
  StimOptimizer/tests CacheStore/tests DecodeCommon/tests`, though Biomarkers itself has no host-suite
  membership per the prior session's own note — container is the suite that actually exercises this
  module).
- **Frontend rebuild is not needed for any of these six tasks** — all six are backend-only, no
  `Client/src` changes.
- **Commit identity:** `git -c user.name="Prasad Shirvalkar" -c user.email="prasad.shirvalkar@ucsf.edu" commit -m "..."`, one commit per task, in the merge order above, directly onto `PS_closedloop_deployment`.
- **Push:** already authorized for this branch's ongoing work (CLAUDE.md §10 rule 9) — push after
  each commit or in one batch at the end, either is fine, but don't skip it (Ship It, §2 principle 6).
- **Update `DECISIONS_and_open_items.md`** with one new decision row per task (or one combined row
  if they land together), each carrying its own proof numbers, following the exact style of
  decisions 71-78.

## What this plan deliberately leaves out

- Finding 7 (`SlidingWindow`) — parked, a behavior decision, not requested for this batch.
- The frontend findings (dead code, color/threshold duplication, Plotly boilerplate) and the
  Plotly hover-mode/render-manager findings — separate review sections, not part of "items one
  through six" as the PI specified, which refers to Agent A's backend-only numbered list.

## Handoff to implementation

This plan is ready for `/swarm-execute` or direct sequential implementation. **Do not begin any
task without an explicit go-ahead in chat** — CLAUDE.md §10 rule 8. This session's harness has no
`TaskCreate`/`TaskUpdate` tool, so the six tasks above are tracked as checklist items in this
artifact and mirrored as a new phase in
`.planning/2026-09-08-biomarkers-module-efficiency-and-redunda/task_plan.md`, rather than in a
native task list.

| # | Task | Depends on (merge order) | Size |
|---|------|---------------------------|------|
| 1 | Remove unread `pro_lsb_spectrum` field | — | ~15 min |
| 2 | Skip building discarded spectrum in Recompute | after 1 | ~30 min |
| 6 | Delete dead `spectral_feature_importance` + helper + tests + docstrings | after 2 | ~45 min |
| 4 | Vectorize `align_pros(target="chronic")` | independent (different file) | ~30 min |
| 3 | Eliminate duplicate recordings load | after 6 | ~45 min |
| 5 | No-expiry cache for chronic/powerdomain branch | after 3 | ~30-40 min |
