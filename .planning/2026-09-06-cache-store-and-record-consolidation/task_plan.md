# Task plan — the cache store as the route between modules, and one consolidated written record

**Plan identifier:** `2026-09-06-cache-store-and-record-consolidation`
**Branch:** `PS_closedloop_deployment`, at `705bdb0`, in sync with `origin`.
**Owner of this file:** the orchestrating session. Any parallel worker reports through its own
file and does not rewrite this one.

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

**The work moves to another tool at the PI's decision, 2026-09-07.** Read
`HANDOFF_2026-09-07_cache_store_to_claude_code.md` §4: re-run both suites, decide whether to push
the six local commits, then the five remaining Track A steps.

## Current Phase

Phase 1 — consolidate the written record. **Complete**, commit `7f1882f`.

Phase 2, Track A — the one store. **Three of eight steps complete and committed** in `fa14edd`:
the single store implementation with both duplicates removed, the provenance chain with its refusal
proved by constructing a real cycle, and the append-only ledger in the database. Tracks B through G
not started. **Six commits sit on this branch and on no remote — `origin` is at `705bdb0`, and
pushing is the PI's call.**

**Measured today, each twice with agreement:** container PASS=455 FAIL=0; host 814 passed, 41
skipped. **Re-run rather than carrying these.**

---

## Phase 1 — Consolidate the written record

**Status:** in_progress

The repository root holds 53 markdown files and 50 of them are handoffs, audits, validation
reports, plans or superseded corrections. The PI's words: *"There are too many Handoffs going on
now."* This phase ports every durable fact into five reference documents, resolves every
contradiction to the newer result, archives the rest, and machine-checks that nothing was lost.

**Status: all nine steps complete.**

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

## Phase 2 — Provenance and the one store

**Status:** pending. **Blocked on the PI's explicit go-ahead**, which is his standing rule: a
clicked plan approval unblocks the tooling only, and Phase 2 code changes wait for a spoken
go-ahead.

Track A from the approved plan, eight steps, and **it must precede every track that writes to
the store.** The four arrows the PI drew make all three modules writers and let one module
consume another's computed output, which means Stim Optimizer would read a ground-truth verdict
computed from recordings Stim Optimizer itself chose to collect. Nothing crashes; the exploration
policy becomes self-confirming and the record looks like converging evidence when it is a loop.

## Phase 3 — Canonical form, Redis, and the closed-loop fixes

**Status:** pending. Three independent tracks: the canonical decoded form and its readers, the
three remaining Redis wins, and the two closed-loop display fixes.

## Phase 4 — The store as the single location, and the gated statistics site

**Status:** pending. The statistics site needs a second sign-off from the PI before anything
changes there, and its two steps concern the same 6,309 files as the deletion step in phase 2,
so the two must be settled together rather than one deleting what the other wires up.

## Phase 5 — Verify, rebuild, and close the record

**Status:** pending.

---

## Decisions Made

| # | Decision | Why | When |
|---|---|---|---|
| 1 | **The ground-truth rule for the three-source comparison is settled**, with four conditions added to the proposal. The device's own band power is ground truth where it exists **and passes a per-channel saturation ceiling check**; the calibrated voltage-trace route where it does not; the device-spectrum route below that and tagged as composed rather than measured; never the uncalibrated integrated-density route. Where both the device reading and the calibrated route exist for one band and setting, **both values and the fold ratio between them are written**. Every row carries its route, its window count, and whether the band sits inside the checked conversion span. | The device's own reading is the exact quantity the control law compares against a switching value typed in those units, so anything else is an estimate of it. The ceiling check is needed because about 1 percent of coincident windows are device-side spikes, and a rule that adopts the unfiltered reading adopts those spikes as truth. The fold ratio is the platform's only continuous check on whether the calibration serving the other 97 bands still holds. | 2026-09-07 |
| 2 | **No suite count is written into any replacement document.** The two authoritative commands are written instead. | Counts in these documents have gone stale within a single session, repeatedly, and one was written into a pushed commit message that cannot be edited. | 2026-09-07 |
| 3 | **The superseded documents are moved with `git mv` into an archive folder, never deleted.** | History follows the move, and nothing that a future reader might need to audit becomes unreachable. | 2026-09-07 |
| 4 | **The aspirational device-writing interface in README §2.6 is not ported in any form.** | `POST /api/deployBiomarker`, `PERCEPT_API_KEY` and `PERCEPT_PATIENT_LOOKUP` return zero matches across every Python and JavaScript file in the repository. Writing an aspiration as a current capability, in a document about deploying stimulation to a patient, is the most consequential error available in this set. | 2026-09-07 |
| 5 | **The port is machine-checked rather than asserted.** Every number, constant name, JSON key, file path and commit hash is extracted from the archived documents and from the replacements, and the difference is read item by item. | The instruction was to make the old documents obsolete. That claim is only safe if the loss is measured. | 2026-09-07 |

## Errors Encountered

| Error | Attempt | Resolution |
|---|---|---|
| `git status` and several `git` reads emit `Operation not permitted` on `.git/config` and on the global ignore file, plus a sandbox notice that git protection is in coarse mode | 1 | Harmless and expected in this sandbox; the commands still return their output. Commit identity must be passed inline on the commit rather than configured. |
| The planning initializer stamped the plan identifier `2026-09-06` while the session date is 2026-09-07 | 1 | The machine's local date is a day behind the session clock. Left as generated, because the identifier is a key and renaming it would break the active-plan pointer. |
