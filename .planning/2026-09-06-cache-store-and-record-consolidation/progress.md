# Progress log

## Session 2026-09-07 — takeover, and consolidation of the written record

**Took over from** `SESSION_HANDOFF_2026-09-07_cache_store_takeover.md`. Read the eight documents
in the order the PI set, plus the repository READMEs, the full project memory, and the Percept RC
document folder on the shared drive.

### What was read, in the order set

1. `SESSION_HANDOFF_2026-09-07_cache_store_takeover.md` — the reading order, the cache design, the
   format measurements, the last ten parallel lanes, the ten traps.
2. `PLAN_cache_store_phase2_2026-09-07.md` — 30 steps in seven tracks, with the two settled items.
3. The design ledger, retrieved from the artifact store as
   `f9b3d791-7e95-44bb-bd81-8aebcf9e1b3b` version `c7bf4b85-4867-4e3a-b8de-2ba900d1fd9b`, whose
   own title line reads revision 13. **It is not a file in the repository.**
4. `HANDOFF_TD_LSB_calibration_2026-06-27.md` — the calibration, the recipe, the per-recipe
   constant catalogue, and the seven catalogued errors.
5. `SESSION_HANDOFF_2026-09-06_sweep_ramp_and_matcher.md` — the previous session.
6. `README_CORRECTIONS_RECONCILED_2026-09-06.md`.
7. `README_BIOMARKERS_AND_DEPLOYMENT.md`.
8. `MEGA_HANDOFF.md` — header, the newest entry in §0, and reference sections §1 through §9 in
   full. **The older narrative in §0 was not read line by line**: it is 4,000 lines of
   session-by-session history whose durable content is what §1 through §9 exist to hold, and the
   two most recent sessions are covered by items 1 and 5 above. Stated rather than implied,
   because it is the one gap in the reading.

### Verified against the code rather than carried from the documents

Twenty-two constants and nineteen function definitions were read from the working tree at
`705bdb0`. **Every line citation in all eight documents has moved.** The current values and
locations are tabulated in `findings.md` §2, and they are what the replacement documents cite.

Two claims in the README describe machinery that **does not exist anywhere in the repository**:
the device-writing endpoint with its two environment variables, and a firmware version and value
range for the threshold. Both were confirmed absent by searching every Python and JavaScript file.

### Decided this session

**The ground-truth rule for the three-source comparison**, which the PI left open because it is a
scientific choice. Recorded in `task_plan.md` under Decisions Made, with the four conditions the
proposal needed. The proposal's precedence is accepted; what it lacked was a saturation ceiling
check on the stream it names as truth, the fold ratio between the two routes where both exist, a
rule that one-band coverage never reads as coverage, and the checked conversion span stated on
every row.

### Completed

- **Planning directory created** at `.planning/2026-09-06-cache-store-and-record-consolidation/`.
- **The supersession register is written** — 30 contradictions found across the eight documents,
  each resolved to the newer result, in `findings.md` §1. Four are marked as corrections to keep,
  because in those the mistake itself is the lesson.
- **Fourteen facts that appear in exactly one document** were identified as the items most at risk
  of being dropped in the port, and each is assigned to a replacement document. `findings.md` §3.

### Phase 1 delivered

**Five replacement documents at the repository root**, written against the supersession register
rather than by copying:

1. `DEVICE_percept_rc.md` — the three threshold modes and their fixed timing, the five recording
   products with their exact JSON keys, the two different quantities both written LSB, every
   calibration constant stated as what it converts from and to and **whether it was measured on
   simultaneous recordings or composed by chaining**, the transform recipe step by step, the
   harmonic landings by stimulation rate, the ramp measured across all 326 amplitude steps, the
   frozen per-participant model with its numbers kept verbatim, and the parsing traps.
2. `ARCHITECTURE_modules_and_store.md` — the three modules, the store as measured, the two
   duplicated implementations and their mismatched limits, the approved layout, the format
   comparison with its honest caveat, the Redis and MySQL facts, where a request actually spends
   its time, the three spectrum builders, and the named routines and response keys.
3. `METHODS_measurement_and_findings.md` — the measurement rules, the **two** different
   multiple-comparison corrections for the two different questions, the live results on RCS08 each
   with its limit, the ground-truth rule, and eight things that must never be claimed.
4. `OPERATIONS_runbook.md` — the container and the mount, the two test runners, how to make a
   backend and a frontend change actually take effect, and every trap already paid for.
5. `DECISIONS_and_open_items.md` — 34 numbered decisions with decision 20 marked superseded by 21
   rather than deleted, the single list of open items, and the commit lineage read from `git log`.

**One architecture drawing** — `bravo_architecture.html`, `.svg` and `.png`: the three modules, the
one store, the four arrows, the cycle they close, and where the provenance refusal sits.

**51 superseded documents archived** to `docs/archive/2026-09-07/` with `git mv` where tracked, so
history follows them, and an `INDEX.md` naming which replacement carries each one's content.
**Nothing was deleted.** Root markdown files went from 53 to 7.

**The port was machine-checked**, not asserted — `findings.md` §5 and `port_gap_report.json`. Four
groups of real omissions were found and ported: the response keys and routine names, the frontend
component files, the device JSON key spellings, and the commit lineage. Thirty-five flagged
identifiers were checked against the current source, all 35 are live, and all were ported. Seven
named scripts were confirmed session-only scratch and are labelled as such.

### The one honest gap in the port, stated rather than implied

**The mega handoff's §0 — about 4,000 lines of session-by-session narrative — was not ported line by
line.** Its reference sections §1 to §9 were ported in full, the two most recent sessions are
covered by their own handoffs, and the narrative remains in the archive. A future session that
needs the reasoning behind an older change should open the dated handoff rather than expect it in
the five replacements.

### Phase 2, Track A — three steps built, and the work then moved tools

**The PI gave the go-ahead on 2026-09-07** and later decided to continue the mechanical half in
another tool. Built before that decision and committed as `fa14edd`, with the decoded-form
prototype tracked in `14ad802`:

- **One cache store**, `BRAVO/modules/CacheStore/`, 1,771 lines in 8 files. Both duplicate
  implementations are gone; the two modules keep their function names as delegations of a few lines
  each, and their event counters are now bound by reference to the store's own, so a count read in
  either module is the count the store actually made. Net on the two module files: 225 lines added,
  342 removed.
- **The provenance chain and its refusal**, with the cycle **proved by construction** — three real
  products written through the real store to close a genuine loop, and each such test paired with a
  control showing that a product built only from device recordings is released.
- **The append-only ledger**, created on first use so there is no migration to run by hand, and
  swallowing its own exceptions so bookkeeping can never be the reason an analysis is refused.
- **A guard test**, `test_one_store.py`, which reads the other modules' source and fails on the
  constructs that make a private store. It grandfathers exactly the two constructs belonging to the
  per-recording spectrum directories, and **asserts the count is exactly one, so when that
  migration lands the test fails and says to delete the exemption.**

**Two defects of my own, found and fixed rather than left:**

1. The container suite failed on my own "nowhere to write" test, because on a configured server
   Django supplies the storage path and clearing an environment variable does not create the
   condition. That exposed a real gap — there was no way to tell the store not to use a file at
   all — so the store gained an explicit off switch, which is also an operational kill switch if a
   stored product is ever suspected of being wrong.
2. **My comments claimed the smaller of the two per-entry limits "would have refused" the 245.90 MB
   tile entry. That was wrong arithmetic: 268,435,456 bytes is 256 MiB and the entry fits, with 4
   to 9 percent to spare.** The defensible argument is headroom — single-digit headroom on the one
   entry the cache exists to hold, where crossing a limit is silent. Corrected in five places, and
   the test assertion was replaced with one that actually discriminates between the two limits.

**Three existing tests were updated and none was weakened.** One of them had been creating its
condition by breaking a helper the new code does not call, so it would have passed while checking
nothing.

### Written down for the move to another tool

Three bodies of knowledge existed only in this tool's session state, and each is now a file in the
repository: `ARCHITECTURE_cache_store.md` (the store had **no** documentation — the string
"CacheStore" appeared in zero markdown files), `HOUSE_RULES_writing_and_claims.md` (the PI's
language and claim rules, previously only in stored memory), and
`DESIGN_biomarker_pipeline_v2.md` (which existed only as an artifact, so a session that searched
the working tree for it found nothing). Eleven further artifacts were exported to
`docs/exported_artifacts/`, and `CLAUDE.md` is the entry point with the commands and the
non-negotiable rules.

### Not done, and why

**No code has been changed and none will be until the PI gives an explicit go-ahead.** His
standing rule: a clicked plan approval unblocks the tooling only, and the second phase waits for
a spoken go-ahead. The one exception he authorised himself was the Redis memory bound, already
landed in `b7036bf`.

### Test and build state

**Not run this session.** No count is quoted anywhere in this session's output, and the
replacement documents carry the commands rather than a number.

---

## Session 2026-09-07, second session — Claude Code, the `planning-with-files` plugin adopted

The machine's local date reads 2026-09-06 throughout; the session day is 2026-09-07.

### What was read, in the order set

`CLAUDE.md`, `AGENTS.md` (its override box first), `HOUSE_RULES_writing_and_claims.md`,
`HANDOFF_2026-09-07_cache_store_to_claude_code.md`, `ARCHITECTURE_cache_store.md`,
`DECISIONS_and_open_items.md`; then `CacheStore/store.py`, `provenance.py`, `ledger.py` and the
three store test files; the REDCap loader and the within-request scope in
`Biomarkers/bravo_service.py`; the settings stream, the epoch collapse and the pain-report matcher
in `StimOptimizer/adapter.py`; the store delegations and `recording_set_signature` in
`ClosedLoopDeployment/adapter.py`; `METHODS_measurement_and_findings.md` §5 and §6; the band-candidate
contract in `DESIGN_biomarker_pipeline_v2.md` §6.

### Inventory and state, checked rather than assumed

- 13 root markdown files; 75 tracked files across the archive, the exported artifacts, the planning
  directory and the store; 8 commits ahead of `origin/PS_closedloop_deployment`; last commit author
  `Claude | noreply@anthropic.com`.
- The framework tree under `.claude/` (rules, skills, hooks, agents, templates, `settings.json`)
  now exists and is gitignored by `.gitignore` line 336. `.claude/commands/` and `./scratchpad/` do
  not exist; `./artifacts/` exists and is empty.
- The `planning-with-files` plugin, version 3.16.1, is installed at user scope. Its `plan-doctor`
  resolves this plan and injects context. Its completion check read nothing from this plan until
  the headings were restructured below.

### Test results

| Run | Runner | Result |
|---|---|---|
| Before any change | container, `run_tests.py` via the bridge | PASS=455 FAIL=0 |
| Before any change | host, `bravo_app` pytest | 814 passed, 41 skipped |
| After Track A step 4 | container | PASS=464 FAIL=0 (nine new tests: seven snapshot, two store) |
| After Track A step 4 | host | 816 passed, 41 skipped (two new store tests) |

The host runs used `~/.claude-science/conda/envs/bravo_app/bin/python`; the default `python` on
this machine (pyenv 3.12.9) has no pytest.

### Track A step 4 — "Store the REDCap frame, and keep the freshness fetch anyway" — built

- **Status:** complete in the working tree, committed with this session's planning-file update.
- Files changed: `BRAVO/modules/CacheStore/store.py` (`KEEP_HISTORY_KINDS`; `store_if_absent` reads
  from the root it writes to), `BRAVO/modules/Biomarkers/bravo_service.py`
  (`_snapshot_pain_reports`, `_pro_table_digest`, `PRO_STORE_KEY_ATTR`, called from `_load_pros`
  after every fresh fetch), `BRAVO/modules/CacheStore/tests/test_store.py` (two tests),
  `BRAVO/modules/Biomarkers/tests/test_redcap_request_scope.py` (store sandboxed),
  `BRAVO/modules/Biomarkers/tests/test_redcap_snapshot.py` (new, seven tests).
- Live check on RCS08 through the bridge (`_agent_bridge/_snap_live.py`, disposable): the snapshot
  landed as Parquet, 760 rows, 12 columns, 28,315 bytes; the stored table against the fetched one:
  **9,120 fields compared, 0 differences**, same column types, same index; a second fetch left the
  directory byte-identical and five further calls likewise; the snapshot step costs 2.3 to 4.0 ms
  per call when the key already matches, of which the content digest is 0.5 to 0.7 ms. The fetch
  itself took 0.73 to 0.90 s per round, unchanged by the snapshot.
- Two defects found in passing and fixed, and one of my own, are in the Errors table of
  `task_plan.md`.

### Adopted the planning-with-files skill

- `task_plan.md` restructured: three-hash phase headings, one literal status line per phase
  (Phase 1 complete, Phase 2 in progress, 3 to 5 pending), all 30 step titles verbatim from
  `docs/archive/2026-09-07/PLAN_cache_store_phase2_2026-09-07.md` as checkboxes under Phases 2 to 4,
  `Next Step` and `Current Phase` made true, decisions 6 to 8 and four error rows added. No existing
  sentence was dropped.
- `.mode` added with `inject-smart`. No attestation.
- `CLAUDE.md` §4, §5, §6, §9 and the framework-tree paragraph, `AGENTS.md`'s override box,
  `HANDOFF_2026-09-07_cache_store_to_claude_code.md`, `ARCHITECTURE_cache_store.md` §6 and
  `OPERATIONS_runbook.md` updated to describe the skill and to correct the stale claims listed in
  `findings.md` §6.

### 5-question reboot check

| Question | Answer |
|---|---|
| Where am I? | Phase 2, Track A, step 4 committed, step 5 next |
| Where am I going? | Track A steps 5 to 8, then Phases 3 to 5 |
| What's the goal? | Correct stored numbers first; the store as the route between modules second |
| What have I learned? | `findings.md` §6 |
| What have I done? | This entry |

### Track A step 5 — "Write the therapy and pain matched table into the store" — built

- **Status:** complete in the working tree, committed with this entry.
- Files changed: `BRAVO/modules/StimOptimizer/adapter.py` (`source_file_signature`,
  `settings_stream` now store-backed with the parser moved to `_build_settings_stream`,
  `build_design_matrix` stores the matched table when both inputs carry a key; `STORE_KEY_ATTR`,
  `UNREADABLE_ATTR`), `BRAVO/modules/CacheStore/provenance.py` (`therapy_pain_matched` raw-derived;
  both new kinds mapped to `stim_optimizer`), tests: `StimOptimizer/tests/test_settings_store.py`
  (new, twelve tests), `CacheStore/tests/test_provenance_cycle.py` (one test: the matched table is
  released to every module while the chosen ladder is still refused).
- Live proof on RCS08 through the bridge (`_agent_bridge/_step5_live.py`, disposable), three
  alternating rounds, each round a cold parse followed by a stored read:

| Product | Fresh (s) | Stored (s) | Fields compared | Differences |
|---|---|---|---|---|
| settings stream, 6,629 rows, 46,530-byte Parquet | 33.61, 32.56, 32.89 | 0.013, 0.009, 0.009 | 59,661 each round | 0 each round |
| matched table, 92 rows, stream given | 0.932, 0.027, 0.024 | 0.019, 0.012, 0.012 | 3,036 each round | 0 each round |
| matched table from an unstored stream vs stored | — | — | 3,036 | 0 |

  Column types and index equal in every comparison. The first matched-table round includes the
  REDCap fetch. The stored stream's sidecar: writer `stim_optimizer`, no provenance (raw); the
  matched table's: writer `stim_optimizer`, provenance `therapy_settings` and `redcap_reports`.
- Not changed: the closed-loop module's `inputs` and `response` entries are still written with no
  provenance; that is Track A step 8 and Track G work, recorded in `findings.md` §6.

### Track A step 6 — "Write the biomarker results back after computing them" — built and reviewed

- **Status:** complete in the working tree, committed with this entry together with the review
  fixes.
- Files changed: `BRAVO/modules/Biomarkers/routines/band_results_tables.py` (new: the two tidy
  tables and the exact-count checker), `BRAVO/modules/Biomarkers/bravo_service.py` (the sweep
  endpoint asks the store before loading spectra, event blocks and tiles; writes the two tables and
  the response; `_band_sweep_signature`, `_load_stored_sweep`, `_store_sweep_results`,
  `store_written`; the tile cache lookup accepts a precomputed tile signature),
  `BRAVO/modules/CacheStore/provenance.py` (three kinds registered; `exploration_ladder` replaces
  `settings_stream`; `check()` deleted), `BRAVO/modules/CacheStore/store.py` (`STORE_KEY_ATTR`;
  refuses a derived kind with no writer; counts a derived kind with no chain; sidecar compared
  before the payload is opened; a payload whose file type disagrees with its sidecar is unreadable;
  ledger for production-root writes only; warning level on unexpected failures),
  `BRAVO/modules/CacheStore/__init__.py` (both import spellings resolve to one module object),
  `BRAVO/modules/CacheStore/ledger.py` (`CONNECTION_FACTORY` for tests),
  `BRAVO/modules/ClosedLoopDeployment/adapter.py` (`inputs` cites its inputs; both reads pass a
  consumer), `BRAVO/modules/StimOptimizer/adapter.py` (the shared attribute name). Tests: new
  `Biomarkers/tests/test_band_results_tables.py` (5), `Biomarkers/tests/test_band_sweep_store.py`
  (7), `CacheStore/tests/test_ledger.py` (4); added to `CacheStore/tests/test_store.py` (3),
  `CacheStore/tests/test_one_store.py` (1), `StimOptimizer/tests/test_settings_store.py` (2).
- Review: six perspectives in parallel, report at
  `artifacts/review_2026-09-07_PS_closedloop_deployment.md`; sixteen findings fixed in this
  session, four left open by decision (`DECISIONS_and_open_items.md` decisions 38 and 39, open
  items 16 and 17).

| Run | Runner | Result |
|---|---|---|
| Final step 6 code | container, `run_tests.py` via the bridge | PASS=485 FAIL=0 |
| Final step 6 code | host, `bravo_app` pytest, documented order | 839 passed, 41 skipped |
| Final step 6 code | host, the three suites in reverse order | 839 passed, 41 skipped |

- Live proof on RCS08 through the bridge (`_agent_bridge/_step6_live.py`, disposable), after the
  store check was moved ahead of the recording loads, three alternating rounds of a fresh sweep
  followed by a served one:

| Round | Fresh (s) | Served (s) | Response values compared | Differences |
|---|---|---|---|---|
| 1 | 6.17 (sweep itself 2.36) | 2.59 | 27,311 | 0 |
| 2 | 5.65 (2.37) | 3.80 | 27,311 | 0 |
| 3 | 5.52 (2.33) | 2.50 | 27,311 | 0 |

  The two tables: 1,320 rows each (six contact pairs, 22 centres from 8.5 to 29.5 Hz, ten
  lengths); the correlation column against the response grid 1,320 fields, 0 differences; the
  area-under-curve column and its folded column likewise 1,320 and 0 each. Sidecars: writer
  `biomarkers`, provenance the tile entry and the pain-report snapshot. What a served request
  still pays is the report fetch and the time-domain recording load, about 2.5 s together.
  Before the reorder the served path took 3.41 to 3.50 s against 5.76 to 6.81 s fresh (two
  rounds, 27,311 values, 0 differences each).
- A REDCap connection error appeared once during the proof ("remote end closed connection
  without response"); the narrowed request fell back to the full export and the run completed.
- The same proof re-run on the finished code (after the review fixes), three alternating rounds:
  fresh 7.25, 5.90 and 8.16 s against served 2.71, 2.57 and 2.64 s; 27,314 response values
  compared each round (three more than before: the `store_written` flags), 0 differences each
  round; both tables 1,320 rows, 0 differences against the response grids.

### Track A step 7 — "Write the amplitude effect on each band where Stim Optimizer can read it" — built

- **Status:** complete in the working tree, committed with this entry.
- Files changed: `BRAVO/modules/ClosedLoopDeployment/amplitude_effect.py` (new: the table, one
  row per device-recorded run of rising current and band centre, and an exact-count checker),
  `BRAVO/modules/ClosedLoopDeployment/adapter.py` (`amplitude_effect_signature`,
  `amplitude_effect_if_stored`, `write_amplitude_effect`; the report builds every run for the
  table when it is not yet stored and keeps drawing its four newest), `CacheStore/provenance.py`
  (the kind's writer is the closed-loop module). Tests: new
  `ClosedLoopDeployment/tests/test_amplitude_effect.py` (9).

| Run | Runner | Result |
|---|---|---|
| Final step 7 code | container, `run_tests.py` via the bridge | PASS=485 FAIL=0 |
| Final step 7 code | host, documented order | 848 passed, 41 skipped |
| Final step 7 code | host, reverse order | 848 passed, 41 skipped |

- Live proof on RCS08 through the bridge (`_agent_bridge/_step7_live.py`, disposable): the
  device's current record holds eleven runs; the table has 1,078 rows (eleven runs, 98 bands).
  Every copied power against the comparison panels: 2,156 fields, 0 differences. Three rounds of
  derive, write, and read back as Stim Optimizer: 39,886 fields compared each round, 0
  differences, same shape and column types; derive 0.16, 0.14 and 0.15 s; write 1.09, 1.09 and
  1.16 s; read 8, 3 and 3 ms; payload 84,366 bytes; sidecar writer `closed_loop`, provenance the
  tile entry. A later request finds the stored summary (1,078 rows, eleven runs, 98 bands) without
  building every run again.
- **What the table says on this record, stated plainly.** Settled settings per run under the
  thirty-second window: 0 to 6. Curvature is assessed on 0 of 1,078 rows because no run reaches
  the routine's floor of eight points. On the 2026-08-18 left run at 55 Hz, six currents from 1.0
  to 3.5 mA, the straight-line slope across 22.5 to 28.5 Hz has p between 0.19 and 0.90 and the
  fold change from lowest to highest current is between 0.92 and 1.07: no movement was detectable
  across the currents the device recorded. The documented rise-then-fall at 25 to 28 Hz rests on
  the clinic sheet's fifteen steps, which the server does not hold (open item 18).
