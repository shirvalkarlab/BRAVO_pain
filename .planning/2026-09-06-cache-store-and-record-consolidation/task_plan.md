# Task plan — the cache store as the route between modules, and one consolidated written record

**Plan identifier:** `2026-09-06-cache-store-and-record-consolidation`
**Branch:** `PS_closedloop_deployment`. Ahead of `origin`; count the commits with
`git rev-list --count origin/PS_closedloop_deployment..HEAD` rather than reading a number here.
**Owner of this file:** the orchestrating session. Any parallel worker reports through its own
file and does not rewrite this one.

**How this file is read by tooling.** The `planning-with-files` plugin counts every three-hash
phase heading under the Phases section, and every bold status line whose value is one of the three
words complete, in_progress and pending. Keep exactly one status line per phase, keep the phase
headings at three hashes, and do not write the heading form or the bold status form anywhere else in
this file, because the counter matches them as substrings. Whenever a phase status changes, rewrite
the Next Step section so it names the single next action. The 30 step titles below are **verbatim
from the approved plan** (`docs/archive/2026-09-07/PLAN_cache_store_phase2_2026-09-07.md`); do not
rename them, because progress is reported against them.

## Goal

Two goals, in this order, and the second is subordinate to the first.

1. **Above everything else, the stored numbers must be correct and the methods behind them
   sound.** Every step that changes how a number is produced or stored proves the numbers did
   not move — by field count and difference count on live recordings, never by a tolerance — and
   every step that speeds something up reports its timings in alternating rounds so the operating
   system's file cache cannot favour whichever ran second.
2. **Make the cache genuinely useful and fast**, and turn it from a one-way speed-up into the
   route by which the three modules read each other's computed results. That closes a dependency
   cycle, so the provenance chain and its proven refusal come first.

## Next Step

**Track B step 4, "Fix the repeated column resolution and float conversion": the remaining site
is the tile-cache builder `availability.raw_lsb_spectrum_cache`, which resolves the channel
column and converts every recording's samples to float once per channel on a cold build. Route
it through the form's prepared per-channel column, then prove the 245 MB tile entry unchanged
field for field on a cleared tile store and time the cold build in alternating rounds.**

## Current Phase

Phase 3 — Tracks B, D, F, G. Phase 2 is complete and pushed (`9a6e0926`; Track A steps 1 to 3 in
`fa14edd`, 4 in `d47b9a7`, 5 in `7278f15c`, 6 in `4e29af7b`, 7 in `0d619ca`, 8 in `9a6e0926`).
Track B steps 1 (`7e57ce03`), 2, 3 and 5 (the commit carrying this edit) are done; Track F
step 1 was done in `b7036bf`.
The PI authorised the phase and the push on 2026-09-07.

## Phases

### Phase 1: Consolidate the written record

**Status:** complete

The repository root holds 53 markdown files and 50 of them are handoffs, audits, validation
reports, plans or superseded corrections. The PI's words: *"There are too many Handoffs going on
now."* This phase ports every durable fact into five reference documents, resolves every
contradiction to the newer result, archives the rest, and machine-checks that nothing was lost.
All nine steps are complete, commit `7f1882f`.

| Step | Status |
|---|---|
| Initialize the planning directory | complete |
| Write the Percept RC device reference | complete — `DEVICE_percept_rc.md` |
| Write the module and cache architecture reference | complete — `ARCHITECTURE_modules_and_store.md` |
| Draw the module and store architecture | complete — `bravo_architecture.{html,svg,png}` |
| Write the measurement methods and findings reference | complete — `METHODS_measurement_and_findings.md` |
| Write the operations runbook | complete — `OPERATIONS_runbook.md` |
| Write the decisions and open-items ledger | complete — `DECISIONS_and_open_items.md` |
| Archive the superseded documents and write the index | complete — 51 files to `docs/archive/2026-09-07/`, with `INDEX.md` |
| Verify no fact was lost in the port | complete — `findings.md` §5, `port_gap_report.json` |

**Root markdown files went from 53 to 7:** the five replacements, the upstream project README, and
the licence.

**The five replacement documents, and what each one owns:**

1. `DEVICE_percept_rc.md` — every Medtronic Percept RC fact the platform depends on: the three
   threshold modes and their timing, the recording products and their JSON keys, the two
   different quantities both called a device unit, and every calibration constant stated as what
   it converts from and to and whether it was measured or composed.
2. `ARCHITECTURE_modules_and_store.md` — the three modules, the store, the formats, Redis and
   MySQL, the decode census, and the three spectrum builders.
3. `METHODS_measurement_and_findings.md` — the measurement rules, the corrections for having
   chosen, the live results on RCS08 and the limit on each one, and every retraction.
4. `OPERATIONS_runbook.md` — the container, the test runners, the frontend rebuild, and the traps.
5. `DECISIONS_and_open_items.md` — the numbered decision log and the single list of open items.

### Phase 2: Provenance and the one store — Track A, "Two-way bus"

**Status:** complete

The PI's standing rule is that a clicked plan approval unblocks the tooling only and code changes
wait for a spoken go-ahead. **He gave that go-ahead for the cache-store phases on 2026-09-07.**

Track A from the approved plan, eight steps, and **it must precede every track that writes to
the store.** The four arrows the PI drew make all three modules writers and let one module
consume another's computed output, which means Stim Optimizer would read a ground-truth verdict
computed from recordings Stim Optimizer itself chose to collect. Nothing crashes; the exploration
policy becomes self-confirming and the record looks like converging evidence when it is a loop.

- [x] 1. Build the one store implementation as a superset, and delete the duplicate — `fa14edd`.
  **One sub-task of this step is deferred, not done:** the plan also said to delete the
  6,309-file `biomarker_psd_rows` directory once its removal was shown to break nothing; that
  is Track C step 1 and open item 7, and `test_one_store.py` grandfathers it until then
- [x] 2. Give every written-back product a provenance chain, not just a version — `fa14edd`, the
  cycle proved by construction in `CacheStore/tests/test_provenance_cycle.py`
- [x] 3. Put the provenance and version ledger in MySQL — `fa14edd`, table created on first use
- [x] 4. Store the REDCap frame, and keep the freshness fetch anyway — built 2026-09-07 (second
  session): kind `redcap_reports`, Parquet, keyed on the table's own content, history kept rather
  than swept, read by no page; the fresh fetch on every request stays and a test proves a newly
  filed report reaches the next request
- [x] 5. Write the therapy and pain matched table into the store — built 2026-09-07 (second
  session): the settings stream as `therapy_settings` keyed on the source-file rows, the matched
  table as `therapy_pain_matched` keyed on the settings key and the pain-report snapshot key, both
  keys in its provenance; on RCS08 the stored stream equals the fresh parse field for field and
  reads in about 0.01 s against about 33 s to parse
- [x] 6. Write the biomarker results back after computing them — built 2026-09-07 (second
  session): `biomarker_band_correlation`, `biomarker_band_discrimination` and the served
  `biomarker_band_sweep`, keyed on the tile entry, the pain-report snapshot, the pain score and
  every setting; on RCS08 27,311 response values and 1,320 table values per statistic compared
  with 0 differences; served 2.5 to 3.8 s against 5.5 to 6.2 s fresh. Reviewed by six
  perspectives the same day (`artifacts/review_2026-09-07_PS_closedloop_deployment.md`)
- [x] 7. Write the amplitude effect on each band where Stim Optimizer can read it — built
  2026-09-07 (second session): `amplitude_effect_by_band`, one row per device-recorded run of
  rising current and band centre, from every run in the record; on RCS08 1,078 rows for eleven
  runs and 98 bands, 2,156 copied powers with 0 differences against the panels, 39,886 fields
  with 0 differences across three round trips; curvature not assessable on this record's ladders
  (open item 18)
- [x] 8. Have Stim Optimizer read the store and write its outputs back — built 2026-09-07
  (second session): the matched table and the newest `amplitude_effect_by_band` are read as
  `stim_optimizer`; the summary, the chosen ladder (`exploration_ladder`), the batch, the
  manifest and the whole response (`stim_optimizer_response`) are written back with every
  input's chain flattened in; a request whose key matches is served from the store. On RCS08
  after the review fixes, two alternating rounds: 21,381 response values compared between the
  fresh fit and the served copy, 0 differences each round; fresh 50.04 and 50.47 s against served
  1.37 and 1.44 s; a fresh-against-fresh control also gave 0 differences in 21,381. **The first live run wrote
  nothing back while every test passed** (a second `rank` column); fixed, pinned by test.
  Reviewed by five perspectives before the commit, 6 findings confirmed and fixed
  (`artifacts/review_2026-09-07_step8_stim_optimizer_store.md`)

### Phase 3: Canonical form, readers, Redis, and the closed-loop fixes — Tracks B, D, F, G

**Status:** in_progress

Independent tracks: the canonical decoded form and its readers, the three remaining Redis wins,
and the two closed-loop fixes. Track D needs Track B's form.

**Track B — "Canonical form"**

- [x] 1. Promote the prototype to real code — 2026-09-07 (second session): the package was
  tracked but its 32 tests ran on neither runner (container-only import spelling; not in the
  container runner's package list). Both spellings now resolve to one module object, the
  container runner discovers it, the host command names it, and the no-constant test stays.
  One real disagreement found and settled: see decision 14
- [x] 2. Adopt it at the 72-million-call site — 2026-09-07: `availability.per_pro_lsb` reads
  from a `ChannelIndex` the service builds once per request; the scan is kept as
  `_per_pro_lsb_scan`, the reference, behind `USE_CHANNEL_INDEX`
- [x] 3. Adopt it at the identical sibling scan — 2026-09-07: `per_pro_lsb_spectrum` likewise,
  through the new `per_pro_lsb_spectrum_indexed`. The plan's note that this scan is not
  exercised by the default page is stale: the page's spectral scan calls it 30 times on a cold
  memo, and the band-by-length sweep calls neither reader at all (0 calls, measured)
- [ ] 4. Fix the repeated column resolution and float conversion — the remaining site is the
  tile-cache builder, reached only on a cold build
- [x] 5. Prove every number unchanged, then measure — 2026-09-07, RCS08 through the bridge, four
  alternating rounds with the switch on, off, on, off: 8,087,210 page values compared with the
  page captured before the change, 0 differences in every round; 54.11 and 53.47 s with the
  index against 65.69 and 63.88 s without; channel-name canonicalisations 5,132 and 5,102
  against 72,457,293. The sweep as a control: 27,305 measured values, 0 differences (its 18
  wall-clock timing fields differ, as they must)

**Track D — "Readers"**

- [ ] 1. Point the Biomarker reading sites at the form
- [ ] 2. Reduce the three spectrum builders
- [ ] 3. Point the Stim Optimizer and closed-loop reads at the form
- [ ] 4. Confirm both endpoints unchanged and faster

**Track F — "Redis wins"**

- [x] 1. Fix the Redis memory limit and eviction policy first — `b7036bf`, authorised out of order
  as a live hazard
- [ ] 2. Add a build lock so four workers cannot duplicate a build
- [ ] 3. Move the freshness key and last-updated date into Redis
- [ ] 4. Point Django's cache at Redis instead of per-process memory

**Track G — "Closed-loop fixes"**

- [ ] 1. Find out why the evidence triangle stopped displaying
- [ ] 2. Agree a ground-truth rule for the three-source comparison, then write it back — the rule
  is agreed (decision 33 in `DECISIONS_and_open_items.md`); the write-back remains

### Phase 4: The store as the single location, and the gated statistics site — Tracks C, E

**Status:** pending

The statistics site needs a second sign-off from the PI before anything changes there, and its
two steps concern the same 6,309 files as the deletion step in Track A step 1, so the two must be
settled together rather than one deleting what the other wires up. Track C needs Track A's single
store.

**Track C — "Cache and dates"**

- [ ] 1. Move every cache to the single approved location
- [ ] 2. Implement the approved writing policy
- [ ] 3. Stamp every cache with when and why it was written
- [ ] 4. Show the last cache update on all three module pages
- [ ] 5. Verify the pain reports stay out of the cached form and its key

**Track E — "Statistics site" — gated on a second sign-off from the PI**

- [ ] 1. Write the decision record before changing anything
- [ ] 2. Connect the live path to the spectrum cache that already exists

### Phase 5: Verify, rebuild, and close the record

**Status:** pending

- [ ] Both suites green on their own runners, counts read from the runs
- [ ] Frontend bundle rebuilt after any change under `Client/src`, and the chunks committed
- [ ] `DECISIONS_and_open_items.md` and the reference documents updated for everything landed
- [ ] The PI's two open questions answered and recorded: commit identity, and whether to push

---

## Decisions Made

| # | Decision | Why | When |
|---|---|---|---|
| 1 | **The ground-truth rule for the three-source comparison is settled**, with four conditions added to the proposal. The device's own band power is ground truth where it exists **and passes a per-channel saturation ceiling check**; the calibrated voltage-trace route where it does not; the device-spectrum route below that and tagged as composed rather than measured; never the uncalibrated integrated-density route. Where both the device reading and the calibrated route exist for one band and setting, **both values and the fold ratio between them are written**. Every row carries its route, its window count, and whether the band sits inside the checked conversion span. | The device's own reading is the exact quantity the control law compares against a switching value typed in those units, so anything else is an estimate of it. The ceiling check is needed because about 1 percent of coincident windows are device-side spikes, and a rule that adopts the unfiltered reading adopts those spikes as truth. The fold ratio is the platform's only continuous check on whether the calibration serving the other 97 bands still holds. | 2026-09-07 |
| 2 | **No suite count is written into any replacement document.** The two authoritative commands are written instead. | Counts in these documents have gone stale within a single session, repeatedly, and one was written into a pushed commit message that cannot be edited. | 2026-09-07 |
| 3 | **The superseded documents are moved with `git mv` into an archive folder, never deleted.** | History follows the move, and nothing that a future reader might need to audit becomes unreachable. | 2026-09-07 |
| 4 | **The aspirational device-writing interface in README §2.6 is not ported in any form.** | `POST /api/deployBiomarker`, `PERCEPT_API_KEY` and `PERCEPT_PATIENT_LOOKUP` return zero matches across every Python and JavaScript file in the repository. Writing an aspiration as a current capability, in a document about deploying stimulation to a patient, is the most consequential error available in this set. | 2026-09-07 |
| 5 | **The port is machine-checked rather than asserted.** Every number, constant name, JSON key, file path and commit hash is extracted from the archived documents and from the replacements, and the difference is read item by item. | The instruction was to make the old documents obsolete. That claim is only safe if the loss is measured. | 2026-09-07 |
| 6 | **The pain-report snapshot is keyed on the content of the tidy table alone**, not on how it was requested, and the store keeps every superseded snapshot of that kind instead of sweeping it. | The same 760-row table requested with and without a record identifier is one report set; two entries for it tell an audit nothing. A swept snapshot would leave the ledger row and not the table, which is the one thing an audit needs. Each snapshot is about 28 KB and one is written per distinct report set, so growth is bounded by how often reports are filed. | 2026-09-07 |
| 7 | **The snapshot is written after every fresh fetch and read by no page.** Decision 22 stands: the reports are fetched fresh on every request. | The stored copy buys reproducibility and a key for derived products, not speed. A test files a new report between two requests and requires the second request to return it while the earlier snapshot stays on disk. | 2026-09-07 |
| 8 | **This plan is kept in the `planning-with-files` plugin's parseable shape** — three-hash phase headings, one literal status line per phase, `Next Step` rewritten on every status change — in legacy mode with structure-aware injection (`.mode` holds `inject-smart`) and **without attestation**. | The plugin's completion check and status command read nothing from the earlier heading shape. Attestation blocks context injection whenever the plan file changes until it is re-attested, and this file is edited after every phase; an auto-recorded digest is not proof of human review. Autonomous and gated modes are not used because the PI's go-ahead rule is a human gate, not a file gate. | 2026-09-07 |
| 9 | **Track A step 5: the settings stream is stored as the raw kind `therapy_settings`, keyed on the participant's source-file rows — each file's uid, content hash and type, never its name — and the matched table as `therapy_pain_matched`, keyed on the settings key plus the pain-report snapshot key, the wash-in and the item list, with both keys in its provenance.** An empty stream, a stream with unreadable files, and a matched table whose inputs cannot both be named are handed back but never stored. `therapy_pain_matched` is registered as raw-derived. | The stream is the single most expensive thing the module does and the file rows identify it before anything is decoded (decision 24); a file name can carry a patient's name. An unreadable file leaves the key unchanged, so a stored copy would carry the gap until the next upload. The report key in the matched table's key is what makes a newly filed report a new entry, so a stale rating cannot be served. The matched table is a deterministic join of two raw inputs and embodies no exploration choice; refusing it to Stim Optimizer would refuse the table this step exists to give it, while the ladder it chooses (the `exploration_ladder` kind, renamed from `settings_stream` on review because that name collided with the function that reads the device's history) stays a derived kind and is still refused — both pinned in `test_provenance_cycle.py`. | 2026-09-07 |
| 10 | **Track A step 6: the band-by-length sweep writes back two tidy tables — `biomarker_band_correlation` and `biomarker_band_discrimination`, one row per contact pair, band centre and length of signal, every value copied from the response and checkable against it, the best row per centre flagged with its interval, selection-aware p-value and verdict, the no-relationship reference on every row (0 for a correlation, 0.5 for an area under the curve) — plus the response itself as `biomarker_band_sweep`, all three under one key naming the tile entry, the pain-report snapshot, the pain score and every setting, with the tile and snapshot keys in their provenance. A request whose key matches is served from the store and marked `served_from_store`.** Reports handed in through the request body, or a participant with no tile key, are computed and never stored. | The approved plan asks for two tables per band centre and contact pair. Serving the response from the store follows decision 26, the key decides: the thousand shuffles and thousand resamples per cell are not paid again when nothing feeding them changed, and every input that could change the answer is in the key. The tables carry the reference value because an area under the curve is above chance by comparison with 0.5 and never with 0. | 2026-09-07 |
| 11 | **The ledger records writes under the production root only.** A write under a caller's own root or the test override is not recorded, and the 218 rows the test suites had written into the live table (participants `test-participant` and `u`) were deleted on 2026-09-07. | The ledger carries no directory, so nothing else could tell a test write from a real one; 214 of its 227 rows were from the container's tile tests. Deleting rows from an append-only table is justified only because they were never part of the record of what the server holds. | 2026-09-07 |
| 12 | **Track A step 7: the amplitude effect on every band is a table derived from the three-source comparison's voltage-trace panel, one row per run of rising current (visit, side turned up, sensing contact, stimulation rate) and band centre, with the number and range of currents actually tested, the pieces of recording behind them, the straight-line slope of log power on current with its standard error and p-value, the curvature test with the peak current, the fold change from lowest to highest current, and the harmonic-landing and checked-span flags.** It is built from every run the device's record holds, written by the closed-loop request as `amplitude_effect_by_band` with the tile entry in its provenance, and the page keeps drawing its four newest runs. A request whose table is already stored builds only those four. | The ladder of currents is read from the device's own record (constraint 4 of the three-source comparison), which the server holds, rather than the clinic sheet, which it does not. Every power value is copied from the panel, so the table is checkable against it. Rows are never pooled across visits, because a result established on one visit day must say so; the visit and run columns let Stim Optimizer pool with the visit as the blocking factor. The curvature floor of eight points is the routine's own and is not lowered to manufacture a verdict. | 2026-09-07 |
| 13 | **Track A step 8: Stim Optimizer reads the therapy-and-pain matched table and the newest amplitude-effect table as `stim_optimizer`, reports which tile entry that table describes and whether it is the current one, and writes back `stim_optimizer_summary`, `exploration_ladder` (the pipeline's queue with its own `rank` kept), `exploration_batch`, `stim_optimizer_manifest` and the whole response as `stim_optimizer_response`, all under one key naming the matched table, the tile entry, the amplitude table, the sites, the brain sides, the wash-in, the backend and the batch settings, with every input's own chain flattened into theirs. A stored response whose key matches is served and marked; one the store refuses is reported, recomputed, and REPLACED; a write-back that fails is reported in the response. A digest of the module and its routines is in the key, the four tables are keyed without the figure backend, and a response computed without the delivered-settings census is not stored.** The amplitude summary counts — runs, currents tested, the smallest slope p-value, whether any run showed movement at p < 0.05 — inside the adaptive window, and does not judge. | Reading as `stim_optimizer` is the exact edge the refusal exists for: the ladder Stim Optimizer chooses decides which recordings come to exist, so a verdict derived from them must not come back to it as independent evidence, and the chain on every output is what lets the next reader see that. The pipeline's fitted surface is repeatable (fresh against fresh: 0 differences in 20,640 values), which is what makes the served response the same answer. The first version inserted a second `rank` column, pandas refused it, and nothing was written back on the live record while every test passed, because the stubbed queue had no `rank`; the stub now has one, and a failed write-back is reported in the response rather than only logged. | 2026-09-07 |
| 14 | **Track B step 1: the decoded form's start-time parser mirrors the platform's exactly, including the rule that a start time written without a timezone is read in the process's local zone.** The disagreement is recorded here and in `findings.md` rather than corrected in the form alone. | The form exists to give the same answer as `availability.per_pro_lsb`, and step 5 proves that field for field on the live record; a form that silently "fixed" the zone would fail that proof, or worse, pass it in the container (which runs in universal time) and disagree on any other machine. The prototype's version read a naive string as universal time; the two agreed in the container and differed by eight hours on the analysis host, which is where the test first ran under pytest. Whether the platform's own rule should change is a separate question and is logged as an open item. | 2026-09-07 |
| 15 | **Track B steps 2, 3 and 5: `availability.per_pro_lsb` and `per_pro_lsb_spectrum` read from the canonical decoded form, built once per request by `availability.channel_index` and passed in by the service; the two original scans stay as `_per_pro_lsb_scan` and `_per_pro_lsb_spectrum_scan`, the reference implementations, behind the module switch `USE_CHANNEL_INDEX`.** The switch off runs the scans with no deployment. | The scans are the specification the indexed readers are proven equal to on constructed recordings (DecodeCommon/tests, 40 tests on both runners), and flipping the switch inside one process is what makes the alternating rounds of the live proof honest: on, off, on, off, 8,087,210 values against the page captured before the change, 0 differences each round, 54 s against 65 s, 5 thousand canonicalisations against 72 million. Deleting the scans would delete the reference and the off switch together. | 2026-09-07 |

## Errors Encountered

| Error | Attempt | Resolution |
|---|---|---|
| `git status` and several `git` reads emit `Operation not permitted` on `.git/config` and on the global ignore file, plus a sandbox notice that git protection is in coarse mode | 1 | Harmless and expected in this sandbox; the commands still return their output. Commit identity must be passed inline on the commit rather than configured. |
| The planning initializer stamped the plan identifier `2026-09-06` while the session date is 2026-09-07 | 1 | The machine's local date is a day behind the session clock. Left as generated, because the identifier is a key and renaming it would break the active-plan pointer. |
| The host suite command in `CLAUDE.md` failed with `No module named pytest` under the default `python` (pyenv 3.12.9) | 1 | The `bravo_app` environment lives at `~/.claude-science/conda/envs/bravo_app/bin/python` (Python 3.11, pytest 9.1). Recorded in `OPERATIONS_runbook.md`. |
| The first snapshot test found nothing written under a store override: `store_if_absent` read from the production root while writing to the caller's | 1 | Fixed in `store.py`: the read now takes the same `root` as the write. A test pins it. |
| The container suite passed but the existing request-scope tests had written five fake pain-report tables into the server's real cache root | 1 | `_service_env()` in `test_redcap_request_scope.py` now points the store at a temporary directory; the five junk entries were removed; a full container run afterwards left only the real participant's entry. |
| My own snapshot test read its sandbox directory after the context manager had deleted it, and reported "nothing written" | 1 | Assertions moved inside the sandbox block. The code was right; the test was wrong. |
| `zsh` treats `echo =====` as a path expansion and prints `===== not found`, which broke several multi-command probes | 1 | Quote the separator string in shell one-liners. |
| The sweep endpoint built its response as a `return {...}` statement, so the write-back lines added after it were unreachable and the only trace was an empty directory created by the miss path | 1 | Diagnosed by spying on the signature call inside the endpoint (it was fine) and then noticing the directory held no payload; the return became an assignment. The test now counts payload files, not directories. |
| A step 6 test expected three sweep runs and got two: the stub reports had no `vas` column, so `SweepMetric="vas"` returned the endpoint's empty state before the sweep | 1 | Test data corrected; the code was right. |
| The live ledger held 227 rows of which 218 were written by the test suites (214 from the container's tile tests for `test-participant`, 4 from the request-scope tests for `u`) | 1 | `store.store` now records only production-root writes, with a test; the 218 rows were deleted. |
| The host suite reached `_arm_comparison` in `StimOptimizer/bravo_service.py` for the first time (step 8's tests call the whole request) and failed on `from modules.StimOptimizer.routines import resolution`, a container-only spelling | 1 | Changed to the relative import the rest of the file uses. |
| The first live run of step 8 wrote nothing back: `ValueError('cannot insert rank, already exists')`. The pipeline's queue already carries a `rank` column and the test stub did not, so eight tests passed while the live write failed | 1 | The write keeps the pipeline's own `rank` and adds `arm`, `site` and `hemisphere` only when absent; the stub queue now carries `rank`; a failed write-back is reported in the response as `store.write_error` rather than only logged, with a test. Proof re-run: 0 differences in 20,640 values, all five products written. |
| The five-perspective review found that after the store refused a stored response, the recompute wrote "if absent", found the refused entry, wrote nothing, reported it as written, and left every later request to be refused again; and that the response's chain came from the newest matched-table sidecar rather than the entry its key names | 1 | After a refusal the five products are written through the plain write and replace the entry; `store.stamp_for_key` finds the sidecar of exactly the entry a key names. Both pinned by tests. A third defect found while fixing: the served copy carried the store block of the request that wrote it, so a refusal recorded then came back with every served copy; the served block is now rebuilt for the current request. |
| The decoded form's tests failed on the host on `test_start_time_matches_the_platform_rule`: a start time with no timezone parsed as universal time in the form and as local time in the platform, eight hours apart on this machine, equal in the container | 1 | The form now mirrors the platform's rule exactly (decision 14); the disagreement is an open item on the platform's own parser, not hidden. |
| The bridge job running the container suite printed the store's own log lines from tests that corrupt an entry or close the ledger's database on purpose; they read as errors, and the job was stopped from outside before the live proof behind it had printed | 1 | The suite had passed (`PASS=486 FAIL=0`); the proof was re-run on its own. Judge a container run by its `PASS=` line, or by the `.out` file in `_agent_bridge/outbox`, never by the filtered log. |
