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

**Nothing queued in this plan's own scope.** Phase 6 (the Biomarkers heat-map headline redesign,
built entirely under a separate `/swarm-plan` brief between the last update to this file and
2026-09-08) is complete, reviewed, and every finding from that review is closed — see Phase 6
below and `DECISIONS_and_open_items.md` decisions 62-70. What remains open, genuinely, in THIS
plan's original scope: Track D steps 1-2 (§Phase 3), unblocked since Track E resolved
(decisions 51-53) but never picked up — whether to build them is the PI's call, not yet asked.
Waiting for further direction.

## Current Phase

**Phases 1, 2, 4, 5 and 6 are complete. Phase 3 is the one still in_progress**, and only because
Track D steps 1-2 within it are unbuilt — unblocked since 2026-09-08 (Track E resolved,
decisions 51-53) but never picked up; whether they are still worth building is the PI's call.
Phase 2 is complete and pushed (`9a6e0926`; Track A steps 1 to 3 in
`fa14edd`, 4 in `d47b9a7`, 5 in `7278f15c`, 6 in `4e29af7b`, 7 in `0d619ca`, 8 in `9a6e0926`).
Track B is complete (`7e57ce03`, `a86e9c09`, `b6a8d1a4`); Track D steps 3 and 4, Track G step 1
and Track F step 2 in `f01a0320`; Track F steps 3 and 4 assessed and Track G step 2 built in the
commit carrying this edit; Track F step 1 was `b7036bf`; Track C step 1 and Track E step 2
resolved together 2026-09-08 (decisions 51-53). **Phase 6, a separate plan's worth of work
(the Biomarkers heat-map headline redesign, four tracks, a full swarm-review, and two follow-up
fix rounds) landed in this same window and is recorded below rather than in a second plan
directory, since it continues the identical branch and the identical "prove the numbers didn't
move" discipline.**
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
- [x] 4. Fix the repeated column resolution and float conversion — 2026-09-07: the tile-cache
  builder `raw_lsb_spectrum_cache` takes the form's prepared traces (walked in the recording
  list's own order, so the tile arrays keep their order) and the service prepares every trace
  once for all channels; proven on RCS08 in four alternating rounds, 31,868,643 tile values
  compared with the build without the form, 0 differences each round. **It buys little**: the
  cold build is 38.59 and 35.67 s with the form against 39.22 and 36.27 s without, because the
  band-power arithmetic, not the column resolution, is the build
- [x] 5. Prove every number unchanged, then measure — 2026-09-07, RCS08 through the bridge, four
  alternating rounds with the switch on, off, on, off: 8,087,210 page values compared with the
  page captured before the change, 0 differences in every round; 54.11 and 53.47 s with the
  index against 65.69 and 63.88 s without; channel-name canonicalisations 5,132 and 5,102
  against 72,457,293. The sweep as a control: 27,305 measured values, 0 differences (its 18
  wall-clock timing fields differ, as they must)

**Track D — "Readers"**

- [ ] 1. Point the Biomarker reading sites at the form — **unblocked 2026-09-08**: this step's
  own note said it stayed open "behind Track E's gate"; Track E is now resolved (decisions
  51-53), so the gate is lifted. Not picked up. Whether it is still worth building, now that
  the sites in question have not caused a measured problem since, is the PI's call
- [ ] 2. Reduce the three spectrum builders — same gate, same state: unblocked, not built
- [x] 3. Point the Stim Optimizer and closed-loop reads at the form — resolved by measurement on
  2026-09-07, no code change: the 65.71 s settings-stream consumer this step names was removed
  by Track A step 5 (the stream is read from the store); the closed-loop report costs 4.77 s
  cold and 0.38 s warm, the Stim Optimizer request 1.37 and 1.27 s served from the store, and
  neither builds the stream (0 builds counted in two runs each)
- [x] 4. Confirm both endpoints unchanged and faster — the same measurement; "unchanged" was
  proven when each endpoint's store path landed (Track A steps 5 and 8)

**Track F — "Redis wins"**

- [x] 1. Fix the Redis memory limit and eviction policy first — `b7036bf`, authorised out of order
  as a live hazard
- [x] 2. Add a build lock so four workers cannot duplicate a build — 2026-09-07:
  `CacheStore/locks.py`, a Redis lock keyed on the tile file's own key, held during the build,
  expiring on its own; a waiter reads the file when it appears, builds anyway after its patience
  runs out, and Redis being unreachable means building as before. Proven on RCS08: four
  concurrent cold requests ran one build and served three, wall 40.85 s; with the lock off, four
  builds, wall 368.03 s
- [x] 3. Move the freshness key and last-updated date into Redis — resolved by measurement on
  2026-09-07, no code change: the step's premise, answering the last-update question without
  opening the 245 MB file, is already met by the 350-byte sidecar the store writes beside every
  entry. Reading it costs 0.012 to 0.013 ms per call against 0.017 ms for a Redis read of the
  same value, in three alternating rounds of 1,000 calls; a Redis mirror would be slower and
  would add a way for the date to be wrong
- [x] 4. Point Django's cache at Redis instead of per-process memory — not done, and recorded as
  such on 2026-09-07: no code in the platform reads Django's cache (no import of
  `django.core.cache` anywhere under `BRAVO/`), and `CACHES` is not set, so the default
  per-process memory cache holds nothing. A setting with no reader cannot be proven, and the
  cold-worker penalty the step names is what the shared tile file and the build lock address

**Track G — "Closed-loop fixes"**

- [x] 1. Find out why the evidence triangle stopped displaying — found and fixed 2026-09-07: the
  literal was in the served bundle, so it was not a missed rebuild this time; the deployment
  report raised on every candidate because `evidence_inputs` has returned the calibrated frame
  (one row per tile, one column per band) since `90eb109`, while the join and its fingerprint
  still required the older one-spectrum-per-row columns, and the web handler turned the raise
  into "the three edges have not been estimated". The join and the fingerprint now accept the
  calibrated frame (decision 17); on RCS08 all four candidates tried return three edges
- [x] 2. Agree a ground-truth rule for the three-source comparison, then write it back — the rule
  is decision 33; written back 2026-09-07 as `ground_truth_verdict` by the closed-loop request,
  one row per run, band and stimulation setting, with the device route's saturation ceiling
  check added to the comparison (a provisional constant, open item 20), and read by Stim
  Optimizer as itself. On RCS08: 2,958 rows over 11 runs, 31 on the device, 2,881 on the
  voltage trace, 46 on nothing; 29 rows with both, fold 0.807 to 1.785, median 0.987; 12 device
  spikes excluded; the ceiling changed 3 of 12,068 comparison values, all pieces counts or
  reasons, no settled power

### Phase 4: The store as the single location, and the gated statistics site — Tracks C, E

**Status:** complete

The statistics site needs a second sign-off from the PI before anything changes there, and its
two steps concern the same 6,309 files as the deletion step in Track A step 1, so the two must be
settled together rather than one deleting what the other wires up. Track C needs Track A's single
store.

**Track C — "Cache and dates"**

- [x] 1. Move every cache to the single approved location — **resolved 2026-09-08, decisions
  51 and 53, jointly with Track E step 2 below.** The two directories were not settled the same
  way: `biomarker_psd` (97 files, 500 MB) moved into the one store as raw kind
  `biomarker_psd_matrix` (decision 53) — both writers and both readers go through it now, proven
  by a byte-identical round trip, 0 of 654,146 fields differing. `biomarker_psd_rows` (6,309
  files) did NOT move in — decision 51 found that moving it would force a full rewrite on every
  new recording (the store keeps one current snapshot per kind, while this cache wants one file
  per recording), so it stays exactly where it is, sped up in front instead with a stamp that
  skips the per-recording loop when nothing moved. `test_one_store.py`'s exemption for
  `biomarker_psd`'s own directory-construction is removed; only `biomarker_psd_rows`'s
  exemption remains, and it is a decision, not an oversight
- [x] 2. Implement the approved writing policy — delivered by Track A step 1 (`fa14edd`): the
  key decides (`store_if_absent`), reads are read-only by construction, and
  `test_a_matching_key_leaves_the_directory_byte_identical` proves a page whose key matches
  leaves the directory byte for byte unchanged
- [x] 3. Stamp every cache with when and why it was written — delivered by Track A step 1: the
  `.meta.json` sidecar beside every entry carries the write time, the trigger, the writer, the
  recording count and the flattened provenance, is moved into place last as the commit marker,
  and is what a page reads (Track F step 3's measurement: 0.012 ms)
- [x] 4. Show the last cache update on all three module pages — 2026-09-07: every module's
  response carries `cache_status` (`store.status_for_page`: whether an entry exists under the
  current key, its build date from the entry's own sidecar, the trigger, and a sentence saying
  what the date means on that page, or the plain fact that there is none yet), and one
  `CacheStatusLine` component under each page's recompute control shows it; bundle rebuilt and
  the line's literal found in one served chunk. On RCS08: tiles built 07:01, the closed-loop
  inputs assembled 06:43, the optimizer response stored 07:22 (all 2026-09-07 universal time)
- [x] 5. Verify the pain reports stay out of the cached form and its key — delivered by Track A
  (decision 23, proven both ways on the live record: changing the report set changes 19,464 of
  27,305 answer values and causes zero writes; `CacheStore/tests` pins it) and by the decoded
  form (Track B), which holds no pain report or REDCap column by construction and whose test
  file says so

**Track E — "Statistics site" — gated on a second sign-off from the PI**

- [x] 1. Write the decision record before changing anything — 2026-09-07,
  `artifacts/adr_2026-09-07_track_e_spectrum_directories.md`: who reads which directory
  (measured: the assembled matrix once per page, report and validation; the per-recording
  files by no page request), the stored spectra against a fresh computation (547,118 values,
  0 differences), what connecting would save (about 2.5 s of a 52 s page, measured, smaller
  than the 4.05 s projected), and three options with a recommendation. Nothing changed
- [x] 2. Connect the live path to the spectrum cache that already exists — **done 2026-09-08
  (decisions 51, 52, 53).** The assembled matrix moved into the one store as `biomarker_psd_matrix`
  (both writers, both readers, decision 53); the per-recording directory stays in place, sped up
  by the stamp-and-manifest shortcut instead (decision 51).

### Phase 5: Verify, rebuild, and close the record

**Status:** complete

- [x] Both suites green on their own runners, counts read from the runs — after the last code
  change (Track C step 4): container PASS=537 FAIL=0; host 934 passed, 41 skipped, both orders.
  **Superseded by later runs, never carried forward as a claim** — see Phase 6 for the counts
  after that phase's own last change (container 578, host 949)
- [x] Frontend bundle rebuilt after any change under `Client/src`, and the chunks committed —
  `f70b270d`, the status line's literal found in one served chunk
- [x] `DECISIONS_and_open_items.md` and the reference documents updated for everything landed —
  decisions 35 to 48, open items 16 to 20, the handoff, the architecture note, the methods note
- [x] The PI's two open questions answered and recorded: commit identity, and whether to push —
  **both answered 2026-09-07. Push: "Push everything," every commit since is pushed. Commit
  identity: Prasad Shirvalkar, `prasad.shirvalkar@ucsf.edu` (decision 49); every commit from
  that date carries it, passed inline since the git config file is not writable in this
  sandbox. This checkbox itself was stale — the answer had already landed in
  `DECISIONS_and_open_items.md` Part 2 item 1 and was never carried back into this file until
  now.**

### Phase 6: Biomarkers heat-map headline redesign — a separate `/swarm-plan`, folded in here

**Status:** complete

Not part of the original 30-step plan above. Requested directly by the PI after Phase 5 closed:
make the calibrated correlation/AUC heat maps the headline visualization on the Biomarkers page,
wire the page's match-direction control into the calibrated sweep, add a family-wise correction
across the grid's own 22 band centres, and export the full grid to Closed-Loop Deployment. Scoped
and executed under its own `/swarm-plan` brief (PR-FAQ, PRD with three page-layout options, two
ADRs, a four-track task breakdown — `artifacts/prd_2026-09-08_biomarkers_heatmap_headline.md` and
siblings), then followed by a full `/swarm-review` and two rounds of fixing what it found. Kept in
this plan's own files rather than a second `.planning/` directory because it continues the
identical branch and the identical proof discipline this plan already established, not because it
shares this plan's own goal statement above.

- [x] **Track A — page layout and interaction (Option 2, "search-first, minimal chrome",
  decision 62).** New component `BiomarkerHeatmapGrids.js`: hover-preview, click-to-pin,
  small-multiples contact-pair strip, no auto-selected cell on load. The correlation/binarization
  asymmetry (PRD §3) enforced structurally, not just visually. New endpoint
  `band_time_sweep_cell_for_participant` for the click-through drill-down. A real bug caught live:
  the drill-down's raw correlation didn't match the grid's own stored value because it skipped the
  grid's own outlier rule; fixed and reproduced to 11 significant figures. Decision 66
- [x] **Track B — match-direction wiring.** `availability.live_lsb_spectrum_match` gained a
  `match_direction` argument threaded through both search paths; the sweep's own request-layer
  parsing (`_sweep_match_direction`, later extracted) reads the page's control. Proven live on
  RCS08: default vs "nearest" differ only in timing/label fields (0 scientific values moved),
  default vs "prior" differs in 20,229 real fields. Decision 64
- [x] **Track C — the 8-30 Hz family-wise correction (decision 63: Benjamini-Hochberg, no
  autocorrelation adjustment).** `analytics._apply_family_wise_correction`, corrected
  independently per grid (correlation, AUC), never pooled with the older full-spectrum routine's
  own correction (decision 61: the two routines answer different questions and were not folded).
  A real caching bug found and fixed along the way: the sweep's version constant wasn't bumped, so
  the first live check silently replayed a stale pre-change response. Decision 64
- [x] **Track D — export the full grid to Closed-Loop Deployment (decision 65's go-ahead).**
  `band_sweep_grid_for_closed_loop` reads the stored grid via the existing no-writer's-key
  pattern; the cross-setting stability column is off by default, folded into the cache key when
  on. D2(a) (a device-rule pass/fail column) deliberately NOT built — checked against the real
  51-rule table first and found only 4 of 51 rules are evaluable from a band centre alone.
  A real, pre-existing production bug found and fixed: `stability.py`'s import was spelled only
  the host-only way, so the already-shipped single-candidate stability field had likely never
  returned its real answer inside the production container — confirmed directly through Django's
  own `manage.py shell` (the exact process gunicorn's workers use) before and after the fix, then
  proven end to end with a real four-valued answer on live RCS08 data. Decisions 67-68
- [x] **The full-grid live proof (D4), left incomplete when the container's bridge stalled, was
  finished after a restart.** Field-count/difference-count proof for `IncludeCrossSettingStability`
  off vs on: 27,865 fields common, 0 dropped, 10,560 new fields, and of the common fields only 22
  differ — all timing fields or the store key, which correctly changes because the flag is folded
  into the cache key. Decision 68
- [x] **A full `/swarm-review` of the branch (scoped to this session's 10 commits, `10b9e8bb^..HEAD`)
  found one HIGH, three Medium and three Low findings. All eight are closed:** the HIGH (zero
  test coverage for the sweep's own request-level MatchDirection parsing) and one Low (the
  same class of gap in the OLDER, pre-existing MatchDirection parse used by
  `run_for_participant`) were both fixed by extracting the parsing into named, directly-testable
  helpers (`_sweep_match_direction`, `_forecast_match_direction`) with tests pinning both their
  defaults and that the two deliberately disagree on what an unrecognised value falls back to.
  The three Mediums: an all-NaN-family test for the family-wise correction, a test rename
  reflecting what it actually proves, and a cross-check of `bh_fdr` against
  `statsmodels.stats.multitest.multipletests`. The other two Lows: a terse local variable renamed
  (`_prior` to `_prior_mode`), and a past commit's message wording left alone on purpose — it is
  already-pushed history, and this project's own rule is to never rewrite that
- [x] **Two PI-requested follow-ups, resolved after the review.** The device-rules status note's
  wording ("not assessable from a band alone" to "more stimulation settings needed", the PI's own
  direction). And the missing populated-grid screenshot (open item 24): the real cause was that
  RCS08 carried zero `StudyDataRel` rows in this database, so no browser session — not a login
  problem — could see it; fixed via the app's own Join Study flow plus one `StudyDataRel` row,
  confirmed the calibrated grid renders live and populated on RCS08's real page, then the grant
  was revoked so no standing access to a real participant remains on the throwaway account

Container suite after this phase's last change: **578 passed, 0 failed** (was 537 at the end of
Phase 5). Host suite: **949 passed, 41 skipped**, both orders (was 934 at the end of Phase 5).
Full detail: `DECISIONS_and_open_items.md` decisions 62 through 70.

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
| 16 | **Track B step 4: the tile-cache builder reads the form's prepared traces, in the recording list's own order, and the service prepares every trace once for all channels; the per-recording preparation stays as the path without a form.** The form's traces carry `seq` and `product` for it (form version 2). | Proven equal on RCS08, 31,868,643 values and 0 differences in each of four alternating rounds. The saving is under a second of a 37 s cold build (38.59 and 35.67 s against 39.22 and 36.27 s), so this is recorded as the completion of the form's adoption and not as a speed-up; the build's cost is the band-power arithmetic on 304,309 tiles. | 2026-09-07 |
| 17 | **Track G step 1: the deployment report's joined table and its content fingerprint accept the calibrated frame — one row per three-second tile, one `band_lsb_<centre>` column per band, already on the device's scale — reading each band's linear power from its own column, its decibel expression from that, and leaving the mean-of-log scale empty because no per-bin spectrum exists to take it from; tiles the cache marked unusable or railed are left out; the fingerprint hashes every band column and the tile flags; the pipeline adds the candidate's own centre to the join's grid.** | Since `90eb109` (2026-09-05) the frame the report is built on has been the calibrated one, and since `8e31342` the fingerprint raises on a missing column rather than skipping it; between them the report raised on every candidate and the page's evidence triangle read "not estimated". The fix follows decision 33: the device's own scale is the one a switching value is typed in, so the join reads it rather than falling back to the uncalibrated spectrum. The tile gate is the same one the other panels apply. On RCS08 with the left 0-2 contact at 26.5 Hz the table has 5,427,936 rows from 304,309 tiles and the report returns in 19.2 s cold, 7.2 s warm; the amplitude-to-pain edge resolves (estimate −0.159 pain points per mA, interval −0.275 to −0.042, 90 clusters) and the other two do not at that band. | 2026-09-07 |
| 18 | **Track F step 2: a short-lived Redis lock (`CacheStore/locks.py`) keyed on the tile file's own key is held while the tiles are built; it expires on its own (300 s against a 36 to 39 s build), a waiter reads the file when its sidecar appears and builds anyway after 150 s, and Redis being unreachable, the client absent or the lock switched off all mean building as before with no error.** Redis is reached with protocol version 2. | Four workers missing the same file used to start four builds. Proven on RCS08 through the bridge with four concurrent cold requests in one process: one build, three served, every request answered in 40.4 to 40.8 s; the control with the lock off ran four builds contending for the machine and every request took 367 to 368 s. Seven tests on a stand-in for Redis pin the three requirements and that eight concurrent callers yield exactly one builder. | 2026-09-07 |
| 19 | **Track G step 2: the device route in the three-source comparison excludes and counts samples above a saturation ceiling, a fold of the settled window's own median (`DEVICE_SPIKE_FOLD = 10`, provisional, open item 20); the ground-truth verdict of decision 33 is applied to every run, band and setting, pairing the device's band with the single nearest stored centre the comparison itself uses, and written as `ground_truth_verdict` by the closed-loop request with the tile entry in its provenance; Stim Optimizer reads the newest verdict as `stim_optimizer`, reports it, keys its response on it and cites it.** | The rule was decided and not written back; the ceiling it requires did not exist in the code, and the number is a scientific choice the PI has not made, so it is one named constant with a fold against the window's own median rather than an absolute level. On RCS08 the ceiling changed 3 of 12,068 comparison values (two pieces counts, one reason), excluded 12 spikes, and no settled power moved. The verdict's first version keyed the device's band on the programmed centre and so never met the converted routes: 0 rows with both; pairing at the comparison's own nearest centre gives 29, fold 0.807 to 1.785, median 0.987. | 2026-09-07 |
| 20 | **Track C step 4: every module response carries `cache_status` — whether a stored entry exists under the request's current key, its build date read from the entry's own sidecar, the trigger, and a plain sentence saying what the date means on that page — and one shared line component under each page's recompute control shows it, including "no stored results yet".** The biomarker page names its tile entry, the closed-loop page its assembled inputs, the optimizer page its stored response. | The plan asks for the date on all three pages including the no-cache case, worded so a stale page is distinguishable from a current one at a glance; three pages mean three different dates, so the sentence beside each says which. The date comes from the sidecar (Track F step 3), never a file timestamp. On RCS08 all three answer, the biomarker status costs 0.48 s (the key from database rows) and the closed-loop one 0.40 s. | 2026-09-07 |
| 21 | **This file is reconciled against `DECISIONS_and_open_items.md`, which had continued to be the record of everything landed since decision 61 while this file and `progress.md` stopped there.** Phase 6 is added to hold the Biomarkers heat-map headline redesign (Tracks A-D, decisions 62-70) rather than opening a second plan directory for it. Track C step 1 and Track D steps 1-2 are corrected against decisions 51-53 (Track E's resolution settled Track C step 1 and lifted the gate on Track D steps 1-2, neither of which had been carried back into this file). Phase 5's commit-identity checkbox is corrected — it read "still open" though the answer (decision 49) had been on record since 2026-09-07. | Asked directly: check what's open here. `DECISIONS_and_open_items.md` had been kept current throughout; this file and `progress.md` had not, so a reader of only these files would have missed nine decisions' worth of real, tested, pushed work and would have acted on two stale open questions that were already answered. One genuine, still-open documentation conflict was found in the course of this and left unresolved rather than picked one way: `DECISIONS_and_open_items.md`'s own open item 7 still reads as unsettled while `ARCHITECTURE_cache_store.md` §3 states plainly that decisions 51-53 settled it — that reconciliation needs the PI's read, not an agent's guess at which document is right. | 2026-09-08 |

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
| Commit `7aa161ad`'s message quotes the host suite as 929 passed; the run said 931. The number was written from the previous run plus an expectation rather than read from the run that had just finished | 1 | Documents corrected; the commit message stands as a record of the mistake. Read the count from the run's output after it finishes, never before. |
| The bridge job running the container suite printed the store's own log lines from tests that corrupt an entry or close the ledger's database on purpose; they read as errors, and the job was stopped from outside before the live proof behind it had printed | 1 | The suite had passed (`PASS=486 FAIL=0`); the proof was re-run on its own. Judge a container run by its `PASS=` line, or by the `.out` file in `_agent_bridge/outbox`, never by the filtered log. |
