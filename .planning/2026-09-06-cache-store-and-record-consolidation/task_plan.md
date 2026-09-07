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

**Commit Track A step 4 together with the planning-file and document updates of 2026-09-07's second
session; then build Track A step 5, "Write the therapy and pain matched table into the store".**

## Current Phase

Phase 2 — Track A, the one store. Steps 1 to 3 are committed in `fa14edd`; step 4 is built, tested
on both runners and checked on the live record, and is being committed. Tracks B through G are not
started, except Track F step 1 (`b7036bf`).

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

**Status:** in_progress

The PI's standing rule is that a clicked plan approval unblocks the tooling only and code changes
wait for a spoken go-ahead. **He gave that go-ahead for the cache-store phases on 2026-09-07.**

Track A from the approved plan, eight steps, and **it must precede every track that writes to
the store.** The four arrows the PI drew make all three modules writers and let one module
consume another's computed output, which means Stim Optimizer would read a ground-truth verdict
computed from recordings Stim Optimizer itself chose to collect. Nothing crashes; the exploration
policy becomes self-confirming and the record looks like converging evidence when it is a loop.

- [x] 1. Build the one store implementation as a superset, and delete the duplicate — `fa14edd`
- [x] 2. Give every written-back product a provenance chain, not just a version — `fa14edd`, the
  cycle proved by construction in `CacheStore/tests/test_provenance_cycle.py`
- [x] 3. Put the provenance and version ledger in MySQL — `fa14edd`, table created on first use
- [x] 4. Store the REDCap frame, and keep the freshness fetch anyway — built 2026-09-07 (second
  session): kind `redcap_reports`, Parquet, keyed on the table's own content, history kept rather
  than swept, read by no page; the fresh fetch on every request stays and a test proves a newly
  filed report reaches the next request
- [ ] 5. Write the therapy and pain matched table into the store
- [ ] 6. Write the biomarker results back after computing them
- [ ] 7. Write the amplitude effect on each band where Stim Optimizer can read it
- [ ] 8. Have Stim Optimizer read the store and write its outputs back

### Phase 3: Canonical form, readers, Redis, and the closed-loop fixes — Tracks B, D, F, G

**Status:** pending

Independent tracks: the canonical decoded form and its readers, the three remaining Redis wins,
and the two closed-loop fixes. Track D needs Track B's form.

**Track B — "Canonical form"**

- [ ] 1. Promote the prototype to real code
- [ ] 2. Adopt it at the 72-million-call site
- [ ] 3. Adopt it at the identical sibling scan
- [ ] 4. Fix the repeated column resolution and float conversion
- [ ] 5. Prove every number unchanged, then measure

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
