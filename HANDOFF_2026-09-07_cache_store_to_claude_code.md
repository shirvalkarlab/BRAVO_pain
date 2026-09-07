# Handoff — the cache store work, moving to another tool

**Written 2026-09-07.** Branch `PS_closedloop_deployment`. This replaces
`SESSION_HANDOFF_2026-09-07_cache_store_takeover.md`, which is now in `docs/archive/2026-09-07/`.

---

## 0. EVERY FILE NAMED IN THIS DOCUMENT IS ON THIS MACHINE. NOTHING NEEDS DOWNLOADING.

The repository is at **`/Users/pshirvalkar/dev/BRAVO_pain`**. Every path below is relative to that
directory, every file is committed to branch `PS_closedloop_deployment`, and **there is nothing
held in a cloud store, an attachment, or a conversation that you need and cannot read from disk.**

**Confirm it in one command before doing anything else:**

```bash
cd /Users/pshirvalkar/dev/BRAVO_pain
ls *.md | wc -l                                    # expect 13
git ls-files docs/archive/2026-09-07 docs/exported_artifacts \
            .planning BRAVO/modules/CacheStore | wc -l   # expect 75
git log --oneline -5                               # expect the five subjects listed below
```

The five newest commits, oldest first, are the record consolidation, the one cache store, tracking
the decoded-form prototype, the `.gitignore` fix, and a correction to this inventory check.
**They are timestamped 2026-09-06 even though the work was done on the 2026-09-07 session day**,
because this machine's local date runs a day behind; the same lag put `2026-09-06` in the planning
directory's name.

**Name those four directories explicitly rather than matching `docs/` as a whole** — `docs/` also
holds 113 files that were already in this repository, including 77 images and the Sphinx
documentation, and a pattern over the whole directory counts those too.

The 75 breaks down as 52 files in the archive (51 superseded documents plus its index), 11 exported
from the cloud store, 4 planning files, and 8 in the store itself. **Commit identifiers advance
with every commit, so check the dates rather than matching the four short identifiers you see
today.**

**The twelve root markdown files, and what each is for:**

| File | Read it when |
|---|---|
| `CLAUDE.md` | **first, always** — read automatically at session start; merges the Claude Agentic Framework with this project's rules, and its §10 overrides everything else |
| `AGENTS.md` | the framework's tool-agnostic instructions, **with an override box at the top** — its Mode B would have you push and target a `main` branch that does not exist |
| `HOUSE_RULES_writing_and_claims.md` | before writing any reply, report, commit message or document |
| **this file** | to know where the work stands and what to do next |
| `ARCHITECTURE_cache_store.md` | touching anything under `BRAVO/modules/CacheStore/` or the cache |
| `DECISIONS_and_open_items.md` | before changing something that looks obviously improvable |
| `DEVICE_percept_rc.md` | touching band power, units, calibration, or a device export key |
| `METHODS_measurement_and_findings.md` | making or reporting any measurement or statistic |
| `ARCHITECTURE_modules_and_store.md` | finding a routine, a response key, or where request time goes |
| `OPERATIONS_runbook.md` | running the container, the bridge, or the test suites |
| `DESIGN_biomarker_pipeline_v2.md` | the band-candidate contract between the two modules |
| `README.md` | the upstream project's own readme, unchanged |
| `LICENSE.md` | — |

**Three directories carry the rest:**

- **`BRAVO/modules/CacheStore/`** — the store, 8 files, 1,771 lines. Documented in
  `ARCHITECTURE_cache_store.md`.
- **`.planning/2026-09-06-cache-store-and-record-consolidation/`** — the `planning-with-files`
  plugin's three files, kept in its parseable shape since 2026-09-07 (`CLAUDE.md` §4):
  `task_plan.md` (five phases with the 30 step titles, verbatim, as checkboxes, so progress reports
  still line up), `findings.md` (**the 30 resolved contradictions, §1, the machine-checked port, §5,
  and the code map for the remaining steps, §6**), `progress.md`.
- **`docs/archive/2026-09-07/`** — 51 superseded documents plus `INDEX.md` naming which document
  replaced each one. **Everything in there is superseded and every code line number in it has
  moved.** `docs/exported_artifacts/` holds 11 files pulled out of a cloud store so they are on
  disk too: both cache inventory drawings, the architecture drawing in three formats, the four-lens
  audit of record, and the port gap list.

**Two facts about git state you need before your first commit.**

1. **THIS BRANCH IS AHEAD OF EVERY REMOTE AND NOTHING HERE IS ON GITHUB.**
   `origin/PS_closedloop_deployment` is at `705bdb0`; everything described in this document was
   committed after it. **Count it rather than trusting a number in a document** — an earlier
   version of this line said "three" and was already stale by the time it was committed:

   ```bash
   git rev-list --count origin/PS_closedloop_deployment..HEAD
   git log --oneline origin/PS_closedloop_deployment..HEAD
   ```

   **Pushing is the principal investigator's call, and so is whose name goes on the commits.**
2. **`.gitignore` contained blanket rules `HANDOFF_*.md` and `AUDIT_TRIAGE_*.md`**, written when
   the root was filling up with per-session handoffs. They were excluding the opposite of what was
   intended — this file, and three archived audits. Negations were appended to restore them.
   **If you add a document whose name starts with `HANDOFF_`, check `git status` actually sees
   it**; a file that exists locally but is untracked survives only until someone runs `git clean`.

**Everything described here is on disk in this repository.** Nothing needed to continue is held
only in a conversation. The three things that *were* only in a conversation have been written out,
and they are named in §5 so you can check they arrived.

---

## 1. Where the work stands

**Phase 1, consolidating the written record: complete**, commit `7f1882f`. 53 markdown files at the
repository root became 7; the other 51 are in `docs/archive/2026-09-07/` with an index naming which
document replaced each one. 30 contradictions across the source documents were resolved to the
newer result, and the resolution record is
`.planning/2026-09-06-cache-store-and-record-consolidation/findings.md` §1.

**Phase 2, Track A, the one store: all eight steps are complete and committed.** Steps 1 to 3
in `fa14edd` (the store, the provenance chain, the ledger, both duplicates removed) and `14ad802`
(the decoded-form prototype tracked); step 4 in `d47b9a7`; step 5 in `7278f15c`; step 6 with the
six-perspective review fixes in `4e29af7b`; step 7 in `0d619ca`; step 8 in the newest commit.
Each of steps 4 to 8 was proved on the live record before it was committed, and the counts are in
`.planning/2026-09-06-cache-store-and-record-consolidation/progress.md` beside the runs.

| Step | State |
|---|---|
| Build the one store implementation as a superset, and delete the duplicate | **done** |
| Give every written-back product a provenance chain, not just a version | **done, with the cycle proved by construction** |
| Put the provenance and version ledger in MySQL | **done** — table created on first use, no migration to run |
| Store the REDCap frame, and keep the freshness fetch anyway | **done, 2026-09-07 second session** — the pain-report table as `redcap_reports`, read by no page |
| Write the therapy and pain matched table into the store | **done, 2026-09-07 second session** — `therapy_settings` and `therapy_pain_matched` |
| Write the biomarker results back after computing them | **done, 2026-09-07 second session** — two tidy tables and the served response |
| Write the amplitude effect on each band where Stim Optimizer can read it | **done, 2026-09-07 second session** — `amplitude_effect_by_band`, one row per device-recorded run and band |
| Have Stim Optimizer read the store and write its outputs back | **done, 2026-09-07 second session** — the matched table and the amplitude table read as `stim_optimizer`; five products written back; the response served when the key matches |

Tracks B through G — the canonical decoded form, the re-derivation speedups, the Redis build lock,
moving the remaining caches into one location, the two closed-loop display fixes, the gated
statistics site — **all not started.** The 30 step titles are in
`.planning/2026-09-06-cache-store-and-record-consolidation/task_plan.md` as checkboxes, verbatim
from `docs/archive/2026-09-07/PLAN_cache_store_phase2_2026-09-07.md`, so progress reports against
them still line up. (Two of them had been reworded in this table — "in the database" for "in
MySQL", and "pain-report snapshot" for "REDCap frame" — and were restored on 2026-09-07.)

**Test state, each read from a run today, and each obtained twice with agreement:**

- container, Biomarkers plus CacheStore plus DecodeCommon: **PASS=536 FAIL=0** (2026-09-07, after Track G step 1 and Track F step 2)
- host, ClosedLoopDeployment plus StimOptimizer plus CacheStore plus DecodeCommon: **921 passed,
  41 skipped**, in both orders (2026-09-07, after Track G step 1 and Track F step 2)

**Re-run both before trusting either.** The commands are in `CLAUDE.md`.

---

## 2. What landed, and in which commit

**The working tree is clean for all real source.** Nothing described here is waiting to be
committed.

| Change | Commit |
|---|---|
| `BRAVO/modules/CacheStore/` — the store, 8 files, 1,771 lines | `fa14edd` |
| `Biomarkers/bravo_service.py` — store block replaced by delegations, 271 lines changed | `fa14edd` |
| `ClosedLoopDeployment/adapter.py` — same, 210 lines changed | `fa14edd` |
| `Biomarkers/tests/test_shared_raw_lsb_cache.py` — three tests updated, 45 lines | `fa14edd` |
| `_agent_bridge/run_tests.py` — discovers `CacheStore` too, 32 lines | `fa14edd` |
| `requirements.txt` — `pyarrow` pinned with its reasoning, 9 lines | `fa14edd` |
| `BRAVO/modules/DecodeCommon/` — the decoded-form prototype, 823 lines, **imported by nothing** | `14ad802` |
| `.gitignore` negations, and this section 0 | `bdfed97`, `0f8cb79`, `57400a8` |

Net on the two module files: **225 lines added, 342 removed.** The store is a superset of what was
deleted, so the modules got shorter.

`BRAVO/_agent_bridge/_*` directories are scratch copies from earlier sessions. **They contain stale
duplicates of `bravo_service.py` — do not edit or grep them expecting real code.** A search for the
old store internals returns most of its hits there.

---

## 3. The four changes that are easy to misread

**1. `run_tests.py` now discovers two packages, and deliberately not the other two.** It imports
each test module and calls every top-level `test_*` function itself, because there is no pytest in
the container. `ClosedLoopDeployment` and `StimOptimizer` are excluded: their files (31 today) use
pytest fixtures or `pytest.raises`, so importing them there raises and would report one spurious
failure per file. The reasoning is written into the file.

**2. The store import is spelled twice on purpose.** The container's path root makes the package
`modules.CacheStore`; the host suite's root makes it `CacheStore`. A single spelling breaks one
runner at import time.

**3. Three existing tests were changed, and none was weakened.** All three had assumptions that the
unified store falsified:

- `test_no_directory_means_memory_only_and_is_not_an_error` created its condition by breaking
  `_psd_cache_dir`, a helper the delegation no longer calls — **so it would have passed while
  checking nothing.** It now uses the store's explicit off switch, which also works on a configured
  server where Django supplies the path.
- `_Bench.files()` listed the override root; the store keeps a subdirectory per kind, so it now
  asks `shared_cache_dir()` where the files are, and skips the `.meta.json` sidecars, which are
  part of an entry rather than separate entries.
- Three corruption tests joined a file name onto the override root, which no longer exists as a
  path; a `file_path()` helper asks the store instead.

**4. One claim in my own comments was wrong and has been corrected in five places.** I wrote that
the smaller of the two per-entry limits "would have refused" the 245.90 MB tile entry.
**268,435,456 bytes is 256 MiB, so it would not have** — it fits with 4 to 9 percent to spare. The
real argument for the larger limit is that single-digit headroom on the one entry the cache exists
to hold is a silent failure waiting to happen. The corrected reasoning, and a test assertion that
actually discriminates between the two limits, are in `ARCHITECTURE_cache_store.md` §1.

---

## 4. What to do first, in order

1. **Re-run both suites** and confirm the two counts above. Nothing else should be trusted until
   they agree.
2. **Decide whether to push.** This branch is ahead of every remote; `origin` is at `705bdb0`.
   **Count the commits with the command in §0 rather than reading a number here.** **That is the principal investigator's call, and so is whose name goes on future
   commits** — see `HOUSE_RULES_writing_and_claims.md` §7. The six already made carry a machine
   identity because the git configuration file is not writable in the sandbox they were made in.
3. **Then the remaining Track A steps**, in the order of the checkboxes in `task_plan.md`; §6 of
   `ARCHITECTURE_cache_store.md` describes what each one writes. Each one writes a new table and
   each **must** pass `writer=` and `provenance=`; without them the self-derived refusal cannot fire.
4. **Before any step that changes a stored number, read the equality-proof procedure** in
   `ARCHITECTURE_cache_store.md` §7. Field count and difference count on live data, never a
   tolerance; timings in alternating rounds.

---

## 5. What was written down for this handover, so you can check it arrived

Three bodies of knowledge existed only inside one tool's session state. Each is now a file:

1. **The store itself had no documentation at all** — 1,771 lines of new code and the string
   "CacheStore" appeared in **zero** markdown files. Now `ARCHITECTURE_cache_store.md`, which
   carries the reason the provenance refusal exists, the format measurements, the exemptions in the
   guard test, and the equality-proof procedure.
2. **The writing and claim rules** came from the principal investigator over several sessions and
   lived in stored memory. Now `HOUSE_RULES_writing_and_claims.md`: the jargon replacement table,
   the reserved meaning of "threshold", the rule that a claim and its result appear together, the
   prose constructions he rejects, and the eight things that must never be claimed.
3. **The design ledger existed only as an artifact and not as a repository file.** A session that
   ran `cat DESIGN_biomarker_pipeline_v2.md` found nothing and could have concluded the design
   record did not exist. Now exported to the repository root, revision 13, 62,151 bytes, including
   the band-candidate contract that is the interface between the two modules.

---

## 6. What genuinely cannot come along, and what to do about it

**Be aware of these rather than surprised by them.**

1. **545 rows of stored project memory.** The load-bearing parts are now in
   `HOUSE_RULES_writing_and_claims.md`, `DECISIONS_and_open_items.md` and
   `METHODS_measurement_and_findings.md`. What is *not* transferred is the long tail: individual
   corrections, dead ends, and the reasoning behind decisions that were reversed. **When something
   looks like an obvious improvement, check `DECISIONS_and_open_items.md` first** — several
   obvious-looking changes in this project are reversals of a decision made for a measured reason.
2. **The remaining artifacts.** The cache inventory drawings (`CACHE_MAP.md`, `cache_map.png`,
   `cache_map.excalidraw`, `build_cache_map.py`), the architecture drawing
   (`bravo_architecture.html`, `.svg`, `.png`), and the four-lens audit of record
   (`closedloop_audit_report.md`) are in the artifact store, not the repository. The audit is the
   source for the remaining backlog in `DECISIONS_and_open_items.md` open item 15. **Export any of
   these you need before relying on them.**
3. **Three project-specific skills**, whose substance is now distributed into these documents: the
   session obligations are in `CLAUDE.md`; the figure conventions for the optimiser and closed-loop
   plots, and the timeline's left-label geometry, are **not** — they matter only when touching
   `StimOptimizer/routines/plots.py` or `BiomarkerDataTimeline.js`. **If you touch either, ask for
   those conventions rather than inventing them**; the figure ones include a rule that has cost
   this project whole figure sets.
4. **The statistics for the two tables that are actual science** — biomarker results per band, and
   the amplitude effect with slope and curvature — were planned to be done where a statistics
   reference and the pre-registration reasoning are at hand. They can be done anywhere, but
   **curvature is not optional** and the reason is in `DECISIONS_and_open_items.md`: a
   rise-then-fall response exists in this record, and a straight-line fit reads it as no response.

---

## 7. The two things most likely to be silently lost

1. **The reason the provenance refusal exists.** It is easy to read as ordinary cache-key
   bookkeeping and simplify away — the code still works, the tests still pass if the chain is
   dropped from a write, and nothing crashes. What is lost is the guarantee that Stim Optimizer is
   not reading a verdict computed from the recordings its own exploration policy chose to collect.
   **That failure produces no error and no visible symptom; it makes the record look like
   converging evidence when it is a loop.** Every write-back call site must pass `writer=` and
   `provenance=`, and `tests/test_provenance_cycle.py` is what proves the refusal still fires.
2. **That a green container run is not a green platform.** The container runs 26 test files and the
   host runs 35, of which 31 are its own. Reporting one number as "the suite" is how a stale count reached a pushed
   commit message in this project once already.
