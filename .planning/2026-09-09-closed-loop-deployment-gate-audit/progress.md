# Progress Log

## Session: 2026-09-09

### Current Status
- **Phase:** 3 - complete

### Actions Taken
- User asked to run an ops agent on the deployment module against the DBS criteria. Dispatched one
  thorough read-only audit agent; independently re-verified its headline finding by reading
  `bravo_service.py:6063` and `analytics.py:5436` directly before reporting it as confirmed.
  Reported 13 criteria, 10 enforced, 1 confirmed defect, 2 unwired checks. Decision 82 logged.
- User approved fixing the stim-stability defect and asked to wire overlapping checks to the
  pipeline "wherever possible," preferring the pipeline's implementation and deleting redundant
  older code. Given the safety stakes, dispatched a second scoping agent before writing any code,
  which found the premise needed correction: the two verdict systems already stopped
  independently-computing the headline on 2026-09-04; only one gate (`stim_stable`) and one
  partial gate (`adaptive_band`, centre-vs-edge) were real duplicates.
- Put three judgment calls to the user via AskUserQuestion rather than deciding unilaterally: fix
  `adaptive_band` now (edge-based, matches D08) or later; add device-rule detail to the sign-off
  card's own gate list or leave the pipeline driving the headline as today; delete the two
  confirmed-dead frontend files. All three answered with the recommended option.
- Implemented both fixes in `bravo_service.py` as new pure functions
  (`_deployment_summary_stim_stable_gate`, `_deployment_summary_adaptive_band_gate`), mirroring the
  file's own `_band_decide_verdict` precedent. Added 2 regression tests to `test_band_candidate.py`.
  Deleted `DeploymentEvidencePanel.js` and `DeploymentVerdictStrip.js` after a fresh, whole-frontend
  grep confirmed zero live importers.
- Container suite: 582 -> 584 passed (+2 new tests), 0 failed.
- Live proof on RCS08: temporarily swapped the pre-fix `bravo_service.py` back into the live-mounted
  container (backed up first, restored after — no `git checkout` used), ran the documented
  ONE_THREE_LEFT/12.5Hz disagreement case and a second edge-vs-centre case at 9.5Hz on the same
  channel, then restored the fix and re-ran the full container suite (584/0 again, confirming exact
  restoration).
- Frontend rebuilt clean (`npm run build`); grepped the fresh bundle chunks for the two deleted
  files' distinctive strings (absent everywhere) and for `DeploySignoffCard.js`'s own string
  (present, confirming the live component still reaches the bundle).
- Attempted the host suite (pytest-based) — unavailable both on this sandbox's Python and inside
  the live container. Ran a substitute cross-module import check instead (clean) and disclosed the
  gap to the user honestly.
- Committed and pushed. Decision 83 logged with both live-proof numbers.

### Test Results
| Test | Expected | Actual | Status |
|------|----------|--------|--------|
| `test_deployment_summary_stim_stable_gate_reads_three_way_verdict` (new) | pins the exact bug: an "inconclusive" verdict must render "indeterminate", never "pass" | Pass | Pass |
| `test_deployment_summary_adaptive_band_gate_checks_edges_not_centre` (new) | edges checked against 8-30Hz, matching D08's own documented examples (3.92Hz and 10Hz cases) | Pass | Pass |
| Container suite (`_agent_bridge/run_tests.py`) | 0 failed | 584/0 (was 582, +2 new) | Pass |
| Container suite, re-run after restoring the fixed file post live-swap | Byte-identical to the pre-swap run | 584/0 again | Pass |
| Live RCS08: ONE_THREE_LEFT@12.5Hz, `stim_stable` | pass (buggy, before) -> indeterminate (fixed, after) | Confirmed: "pass"/"(stable)" before, "indeterminate"/"cannot tell" after, p=0.0586 both times | Pass |
| Live RCS08: ONE_THREE_LEFT@9.5Hz, `adaptive_band` | pass (centre-only, before) -> fail (edge-based, after) | Confirmed: "pass" before, "fail" (edges 7.0-12.0Hz, below 8Hz floor) after | Pass |
| Cross-module import check (host-suite substitute) | `ClosedLoopDeployment.adapter`/`stability` and edited `Biomarkers.bravo_service` import together | Confirmed clean | Pass (substitute only, not the real pytest suite) |
| `npm run build` | Compiles clean, no ClosedLoopSim warnings from the deletion | Clean | Pass |
| Bundle grep: deleted files' distinctive strings | Absent everywhere | 0 matches | Pass |
| Bundle grep: `DeploySignoffCard.js`'s own string (`deploy_signoff_v1`) | Present (component still live) | Found in `85.1ee8578f.chunk.js` | Pass |

### Errors
| Error | Resolution |
|-------|------------|
| Host suite (ClosedLoopDeployment/tests, StimOptimizer/tests) could not be run: no `pytest` module on any of this sandbox's Python interpreters, nor inside the live container. | Ran a substitute cross-module import check instead; disclosed the gap explicitly to the user rather than claiming the suite ran. |

## Session: 2026-09-09 (continued) — actually running the host suite

### Current Status
- **Phase:** 4 - complete

### Actions Taken
- User asked to install pytest on their local machine or the OrbStack server and actually run the
  host suite, rather than leaving it as an acknowledged gap.
- `python3-venv` is not installed in the container, so an isolated virtual environment (the safer
  route, avoiding any system-Python change) was not available; installed pytest directly with
  `pip install --break-system-packages pytest` instead, as the user's own instruction authorized
  installing it on the server.
- Ran `PYTHONPATH=. python3 -B -m pytest ClosedLoopDeployment/tests StimOptimizer/tests
  CacheStore/tests DecodeCommon/tests -q -W ignore` inside the container against the live-mounted
  source (the same source tree `git status` shows, not a copy). Result: 990 passed, 42 skipped,
  1 failed.
- Investigated the failure rather than reporting the raw number: re-ran the single failing test in
  isolation (still failed, ruling out test-order pollution), then read `CacheStore/store.py`'s
  `root_dir()` directly and found it falls through to the real, Django-configured production cache
  root whenever the test's monkeypatched override is `None` -- the test's own premise ("no directory
  configured means nowhere to write") only holds in the bare host environment this suite was
  designed for, which has no `DATASERVER_PATH` set; the live container does have one. Confirmed
  neither `CacheStore/store.py` nor `ClosedLoopDeployment/adapter.py` was touched by this session's
  own edits (decision 83 only touched `Biomarkers/bravo_service.py` and two frontend files).
- Investigated whether the test's own write (which this discovery showed lands in the REAL cache
  root) had a real side effect: read `_sweep_superseded` and found its eviction marker never
  actually varies by participant for the `_shared_store` call path (`participant_uid` is always
  passed as `None`), even though the participant identity is already inside the signature. Confirmed
  the `"inputs"`-kind cache directory was empty immediately after the test run, consistent with the
  throwaway test write evicting whatever real entry was resident. Assessed this as self-healing (a
  cache miss the store's own design already treats as routine, not a correctness issue) and recorded
  the underlying scoping gap as a new, separate, flagged-not-fixed finding (open item 25) rather than
  silently fixing infrastructure outside what was asked.
- Cleaned up the three scratch probe scripts used for this investigation (gitignored, `_agent_bridge/_*`).
- `DECISIONS_and_open_items.md` decision 84 and open item 25 added. Committed and pushed (docs only;
  no source files changed by this phase).

### Test Results
| Test | Expected | Actual | Status |
|------|----------|--------|--------|
| Host suite (real `pytest`, run inside the container against the live-mounted source) | Reflects any real regression from decision 83's edits | 990 passed, 42 skipped, 1 failed -- the 1 failure traced to a pre-existing environment mismatch unrelated to decision 83's edited files | Pass (no regression found) |
| Failing test re-run in isolation | Rules out test-order pollution | Failed the same way standalone | Confirms genuine, reproducible mismatch, not flakiness |

### Errors
| Error | Resolution |
|-------|------------|
| `pip install pytest` refused by PEP 668 (externally-managed environment); `python3 -m venv` failed (`ensurepip` unavailable, needs `python3.12-venv` via apt). | Used `pip install --break-system-packages pytest`, the user's own explicitly-authorized path ("install pytest ... on the OrbStack server"), since no venv tooling was available as the safer alternative. |
| `test_no_directory_means_memory_only_and_not_a_failure` failed inside the container. | Root-caused (not assumed) to `store.root_dir()` falling through to the real, Django-configured cache root when the container has a live `DATASERVER_PATH` -- a mismatch between the test's bare-host assumption and the live container it actually ran in, not a regression from this session's edits. |
| The failing test's own write triggered a real cache eviction (`_sweep_superseded`) against the live production cache directory. | Confirmed self-healing (next real request rebuilds and re-caches); the underlying participant-scoping gap that made this possible is recorded as open item 25 for the PI, not fixed in this pass. |

## Session: 2026-09-09 (continued) — fixing open item 25

### Current Status
- **Phase:** 5 - complete

### Actions Taken
- User asked directly to fix the cross-participant cache-eviction bug just identified (open item 25).
- Read `CacheStore/store.py`'s `_stem`/`kind_dir`/`root_dir`/`_sweep_superseded` in full before
  editing anything: confirmed the signature already makes each participant's file name unique (via
  `recording_set_signature`'s own embedded participant field), but `_sweep_superseded`'s CLEANUP
  step groups only by the `participant_uid` argument, which every `ClosedLoopDeployment.adapter`
  call site passed as `None` regardless of which participant it was for.
- Added an optional `participant_uid=None` keyword to `_shared_store`/`_shared_load`/`_shared_path`
  in `ClosedLoopDeployment/adapter.py`, forwarded to the store instead of a hardcoded `None`.
  `evidence_inputs_cached` (the only live production caller of the "inputs" kind) now passes the
  real participant identity on both its load and store calls, derived the same way
  `recording_set_signature` already does. `cache_status_for_page` (the cache-status line shown on
  the page, decision 48) was also hardcoding `None` and would have looked in the wrong place once
  the storage side was fixed -- corrected to match.
- Investigated `amplitude_response_cached` ("response" kind) before deciding what to do with it:
  grepped the whole module tree and found zero production callers anywhere, only its own test file;
  neither of its two inputs (`steps`, `tiles_by_channel`) carries a participant identity to derive
  one from. Left it passing `participant_uid=None` deliberately, with a comment explaining why and
  pointing a future real caller at the fix `evidence_inputs_cached` got, rather than inventing a
  participant identity that doesn't exist at that call site.
- Ran the full host suite before writing any test of my own, to see the actual state: found a SECOND
  failure beyond decision 84's already-known one -- `test_ground_truth.py::test_the_report_page_
  status_names_the_inputs_entry_or_its_absence`. Investigated rather than assumed: its own setup
  line hardcoded the OLD, buggy convention (`st.store("inputs", None, ...)`) to simulate an existing
  cache entry, so once `cache_status_for_page` started looking under the real participant_uid, the
  test's own simulated entry (written under the old `None`/"shared" convention) no longer matched.
  Fixed the test's setup to write under the real participant_uid, matching what the real writer now
  does, without touching the test's own assertion about what the status page should report.
- Grepped the whole test directory for any OTHER test hardcoding the same old convention for the
  "inputs" kind -- confirmed this was the only one.
- Added two new regression tests to `test_adapter_caching.py`: one proves, directly at the
  `_shared_store`/`_shared_load` level, that two participants' entries survive each other's writes
  and rebuilds; one proves `evidence_inputs_cached` itself now stores under the real participant id,
  not "shared".
- Re-ran the full host suite: 992 passed (990 -> 992, +2 new), 42 skipped, 1 failed -- confirmed by
  name that the one remaining failure is exactly decision 84's own already-explained, unrelated
  environment mismatch, not a new regression from this fix.
- Ran the container suite as a sanity check (this fix touches no Biomarkers or CacheStore/store.py
  code): 584/0, unchanged.
- Live-proven on RCS08: cleared the shared cache for this module's two kinds (a controlled version
  of the same benign, self-healing eviction already observed once today), rebuilt
  `evidence_inputs_cached` fresh, and confirmed (a) the resulting file name carries the real
  participant uid (`2e3c75c00d7f4f37b53a048d195f11da`), not "shared", (b) `cache_status_for_page`
  finds the entry, and (c) the rebuilt values -- 123 exposure epochs, 92 design-matrix rows --
  exactly match this same function's own comment, which already documents those row counts from the
  2026-09-06 measurement, confirming the fix changed only the cache's own bookkeeping, not any
  computed number.
- Cleaned up the scratch verification script (gitignored, `_agent_bridge/_*`).
- `DECISIONS_and_open_items.md` decision 85 added; open item 25 marked resolved. Committed and
  pushed.

### Test Results
| Test | Expected | Actual | Status |
|------|----------|--------|--------|
| `test_writing_one_participants_entry_does_not_evict_another_participants` (new) | participant A's entry, and A's own rebuild, never delete participant B's entry | Pass | Pass |
| `test_evidence_inputs_cached_stores_under_the_real_participant_not_shared` (new) | the stored file name carries the real participant id, never ".shared." | Pass | Pass |
| Host suite, full re-run | Only decision 84's known, unrelated failure remains | 992 passed, 42 skipped, 1 failed (the known one, confirmed by name) | Pass |
| Container suite, sanity re-run | Unaffected (no Biomarkers/CacheStore/store.py code touched) | 584/0, unchanged | Pass |
| Live RCS08: rebuilt "inputs" cache file name | Carries the real participant uid | `inputs.v1.2e3c75c00d7f4f37b53a048d195f11da.<hash>.pkl` | Pass |
| Live RCS08: rebuilt row counts | Match the 2026-09-06-documented values (123 epochs, 92 design-matrix rows) | Exact match | Pass -- confirms no computed number moved |

### Errors
| Error | Resolution |
|-------|------------|
| After the `cache_status_for_page` fix, a second, previously-passing test failed: `test_the_report_page_status_names_the_inputs_entry_or_its_absence`. | Traced to the test's own setup hardcoding the old `participant_uid=None` convention to simulate an entry; updated the setup to the real writer's real behavior (the fix, not a workaround), leaving the test's actual assertion unchanged. |
