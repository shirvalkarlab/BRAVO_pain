# BRAVO_pain — project instructions

Django backend, React frontend. Ingests exported files from the **Medtronic Percept RC**
neurostimulator and patient-reported pain scores from REDCap, and produces a stimulation
configuration a clinician programs by hand. **Nothing here writes to the device.**

This file merges the generic Claude Agentic Framework with this project's own rules. Where they
disagree, **§8 wins over everything above it.** Compacted 2026-09-19 (the previous version is at
`docs/archive/2026-09-19/CLAUDE.md`).

**Framework tree, checked 2026-09-19:** `.claude/` holds `skills/` (17), `hooks/`, `agents/`,
`templates/`, `settings.json` and one path-scoped rules file (`rules/hooks-conventions.md`; the six
generic framework rules were deleted on 2026-09-19 as inapplicable, and this file carries what
mattered from them). **The whole tree is gitignored** (`.gitignore` line 336): it exists on this
machine and in no clone. `.claude/commands/` and `./scratchpad/` do not exist. Run `ls .claude`
before relying on any of it. The plan is tracked with the `planning-with-files` plugin (§4).

---

## 1. Quick reference

```bash
# THE TWO TEST SUITES RUN IN DIFFERENT PLACES. A GREEN RUN OF ONE IS NOT A GREEN PLATFORM.
# Never quote a count without a run behind it. Preferred: both at once in one bridge job:
bash BRAVO/_agent_bridge/run_both_suites.sh          # see memory: run-both-suites-in-parallel

# container: Biomarkers + CacheStore + DecodeCommon + ControlAnalyses. No pytest there; plain assert.
python3 BRAVO/_agent_bridge/bridge_client.py --cwd /usr/src/BRAVO --timeout 900 --wait 900 \
  "python3 _agent_bridge/run_tests.py"

# host: ClosedLoopDeployment + StimOptimizer + CacheStore + DecodeCommon + ControlAnalyses, pytest.
# CacheStore, DecodeCommon and ControlAnalyses run on BOTH runners, so their tests take no arguments.
cd BRAVO/modules && PYTHONPATH=. python -B -m pytest \
  ClosedLoopDeployment/tests StimOptimizer/tests CacheStore/tests DecodeCommon/tests \
  ControlAnalyses/tests -q -W ignore

# anything inside the live server container; --status is the heartbeat (a stall needs a restart)
python3 BRAVO/_agent_bridge/bridge_client.py --cwd /usr/src/BRAVO --timeout N --wait M "<cmd>"
python3 BRAVO/_agent_bridge/bridge_client.py --status

# frontend. REQUIRED after any change under Client/src; the rebuilt chunks are committed.
cd Client && export PATH="/usr/local/bin:$PATH" && export npm_config_cache=/tmp/npmcache \
  && env CI=false GENERATE_SOURCEMAP=false npm run build

# gunicorn workers do not always pick up a Python edit: reload them after backend changes
python3 BRAVO/_agent_bridge/bridge_client.py --cwd /usr/src/BRAVO --timeout 30 --wait 30 "kill -HUP 1"
```

**No linter, type checker or formatter exists in this repository.** "Run the quality gates" means
exactly: the two suites, the frontend build, and (for page text) jest under `Client/src`. Claiming a
lint or type check passed would be claiming something that cannot have run.

**CI** (`.github/workflows/ci.yml`) runs on every push to `PS_closedloop_deployment`, `v3.1.0` or
`development` and on every pull request: the host suite (without the `store` and `live` markers),
the frontend build, the page tests (jest, since 2026-09-23: the two known-failing page tests were
repaired in decision 250) and a `gitleaks` secret scan (known false positives are fingerprinted in
`.gitleaksignore`; add a fingerprint rather than loosen the scan). **CI does not run the container
suite** (needs MySQL, Redis, R, rpy2).

---

## 2. Core principles, annotated for this repository

1. **Understand first.** Read before writing; grep before creating. Every code line number in
   every archived document has moved: search for the name, never trust the number. **Before
   changing anything that looks obviously improvable, read `DECISIONS_and_open_items.md`**: several
   obvious changes here are reversals of a decision made for a measured reason.
2. **Prove it works.** Tests before code; a regression test for every fix. Two additions:
   a test whose name asserts something untrue is worse than no test (split it, never relabel it);
   and **check the values, never the shape** (§8 rule 11). Any change to how a value is produced
   or stored reports a field count and a difference count on live data, never a tolerance; any
   speed claim reports alternating-round timings beside its equality proof
   (`ARCHITECTURE_cache_store.md` §5).
3. **Keep it safe.** The exposure here is patient information, not credentials. Device export file
   names on the shared drive carry real patient names; keep that folder out of the repository.
   `RCS08` is the de-identified code; `secrets/` stays out of version control.
4. **Keep it simple, but "delete dead code" will do damage here.** Kept on purpose:
   `LSB_RULE_OF_THUMB` and `LFP_POWER_LSB_TO_UV2` (unused constants whose comments warn that
   misreading them as conversions once left a page unscaled); struck rows in the decision log
   (the mistake is the lesson); `test_one_store.py`'s grandfathered-count assertion (it fails when
   the pending migration lands, on purpose). Python and plain JavaScript only; no TypeScript.
   Two hats: never mix a refactor (structure, tests unchanged) and an optimisation (behaviour
   unchanged, timings required) in one commit. Before a fix, name three falsifiable causes and
   check the cheapest first; after three failed attempts, stop and ask.
5. **Don't repeat yourself.** Two copies of one cache drifted by a factor of four; now one module,
   `BRAVO/modules/CacheStore/`, and a test that fails on a second copy. A comment would not have
   prevented it.
6. **Ship it, as the PI has authorised it.** Commit iteratively; push to `origin` on this branch
   (his standing go-ahead of 2026-09-07); identity inline on every commit (§8 rule 9). Only commit
   meaningful changes (memory: commit-only-meaningful-changes).
7. **Leave a trail.** The ten root reference documents, `DECISIONS_and_open_items.md`,
   `./artifacts/` for ADRs, PRDs, reviews and analyses, `.planning/` for the live plan (§5).

---

## 3. Tech stack

| Layer | What |
|---|---|
| backend | Django, gunicorn behind nginx in the `bravo-server` OrbStack container |
| container runtime | Python 3.12.3, rpy2 3.5.15, pymer4 0.8.2, pandas 2.2.3, scikit-learn 1.5.2; no GPU |
| frontend | React via react-scripts; `Client/build` is a **committed** compiled bundle |
| database | MySQL 8.0.46, `BRAVOServer`, 44 tables |
| shared memory | Redis 5.0.14 — **construct every client with protocol version 2**; bounded 512 MB, allkeys-lru |
| cache on disk | Parquet+zstd tables, compressed array files for spectra, pickle otherwise |
| statistics | statsmodels; mixed models through rpy2 and pymer4 |

---

## 4. Workflow

**Branching.** `PS_closedloop_deployment` is the default branch (decision 177). Work lands on it
directly; CI runs on every push; `v3.1.0` is a version label to tag from, not a branch to merge into.
Use a short-lived branch only for something you might throw away. **No worktrees**: the container
mounts only the main checkout, so code in a worktree runs against nothing
(`.claude/agents/README_no_worktrees.md`).

**Planning: the `planning-with-files` plugin** (user scope, `~/.claude/plugins/cache/planning-with-files/`,
adopted 2026-09-07). It keeps three files per plan and injects the plan's Goal, Next Step, current
phase and last decisions into every turn and every matched tool call. **That injection is paid on
every tool call, so keep Goal and Next Step short.** The active plan is named in
`.planning/.active_plan`.

| File | Holds | Update |
|---|---|---|
| `task_plan.md` | goal, single next step, phases with step checkboxes, decision and error tables | tick steps as they land; rewrite Next Step whenever a status changes; log every error with its attempt number |
| `findings.md` | observations only, never instructions | after any discovery |
| `progress.md` | the session log, counts beside the run that produced them | throughout, and before stopping |

**Format the plugin parses:** three-hash `Phase` headings under `Phases`; one bold status line per
phase whose value is `complete`, `in_progress` or `pending` (substring-matched, so those words
appear nowhere else in the file). Verify after editing:
`sh ~/.claude/plugins/cache/planning-with-files/planning-with-files/3.16.1/scripts/check-complete.sh`.

**Choices for this project (decision 36):** planning files committed; legacy mode with
`inject-smart` in `.planning/<plan-id>/.mode`; autonomous mode with attestation is allowed per plan
(decision 223); never gated (the PI decides when work stops). After any edit to `task_plan.md` in an
autonomous plan, run `attest-plan.sh` again or the hooks stop injecting it. A new independent task
gets its own plan via `/pwf "<name>"`. Rules the
skill imposes and this project wanted anyway: re-read the plan before any decision; log every
error; never repeat a failed action unchanged; after three failed attempts stop and ask.

---

## 5. Where things live

| Location | Use | Lifecycle |
|---|---|---|
| repository root `*.md` | the reference documents, named in commit messages; do not move them | committed |
| `.planning/<plan-id>/` | the one live plan (completed plans were deleted 2026-09-19; the cache-store plan, cited by four documents, is under `docs/archive/2026-09-19/planning/`) | committed |
| `./artifacts/` | ADRs, PRDs, design specs, reviews, analyses, contest reports | committed |
| `docs/archive/<date>/` | superseded documents with an `INDEX.md` naming the replacement; every line number in them has moved | committed, read-only |
| `docs/decision_log_full_2026-09-19.md` | the full decision rows behind the digest | committed |
| `docs/exported_artifacts/` | cache drawings, architecture drawing, the four-lens audit, the port gap list | committed |
| `BRAVO/_agent_bridge/_*` | **the scratch area, and the only path the container sees**; probe scripts here are disposable | gitignored at every depth |

**Three warnings.** (1) `BRAVO/_agent_bridge/_*` holds stale copies of real module files, including
old `bravo_service.py`; a grep for a function name lands there first. Never edit or grep them
expecting live code. (2) `.gitignore` has blanket `HANDOFF_*.md` and `AUDIT_TRIAGE_*.md` rules with
negations appended; if you add a file matching them, check `git status` sees it. (3) The scratch
rule is `BRAVO/_agent_bridge/_*` and `/cl_docs/` (fixed 2026-09-10; the old top-level-only rule
left 265 files untracked but unignored). Staging one of the 23 tracked files under it by explicit
path needs `git add -f`.

---

## 6. Task tracking

1. **Durable record:** `DECISIONS_and_open_items.md` (digest) and the full log in `docs/`. No issue
   tracker; add there rather than start an `ISSUES.md`. Only code changes are open items.
2. **In flight:** the checkboxes and status lines of the active `task_plan.md`, plus the session's
   native task list.
3. **Handoffs:** none. The dated handoffs were deleted on 2026-09-19; the decision log carries
   everything they described. Do not start a new one.

---

## 7. Commands and skills

`.claude/commands/` does not exist; the framework's roles are skills under `.claude/skills/`
(gitignored): `/architect`, `/builder`, `/qa-engineer` (the equality proofs, not only the suites),
`/security-auditor` (patient information and the REDCap credential), `/ui-ux-designer`,
`/code-check` (read §2 principle 4 first), `/land-the-plane` (its push step is already answered),
`/tailor` (it will find no linter and a three-job CI; that is accurate), `/swarm-*` orchestrators.
**Switched off 2026-09-20** in `.claude/settings.local.json` (`skillOverrides`), unused in 36 sessions: architect,
builder, code-check, qa-engineer, security-auditor, tailor, ui-ux-designer and the nine nested groups
(architecture, core-engineering, operations, product, security); delete the override line to bring one back.

**Project-specific plugin skills exist and load by name:** `bravo-session-rules` (its description
still tells sessions to update `MEGA_HANDOFF.md`, archived since 2026-09-07 — ignore that line),
`bravo-stimoptimizer-figures` (figure conventions for `StimOptimizer/routines/plots.py` and the
decision plots; a rule there has cost whole figure sets) and `bravo-timeline-layout` (the
timeline's left-label geometry, `BiomarkerDataTimeline.js`). **Load the matching one before touching
either file; if it does not load, ask for the conventions rather than inventing them.**

**MCP tools:** none of the framework's list is verified as connected; check what is available. To
prove a panel reached the served bundle, search the code-split chunks for a string literal that
panel owns, not for the component name.

---

## 8. Project rules that override everything above

From the PI and from failures already paid for.

1. **`/usr/src/BRAVO` IS a live mount** of `BRAVO/`: write on the host and run. Root files and
   `Client/` are absent from it. Two pushed commit messages say otherwise and are wrong.
2. **A frontend change without a bundle rebuild is a component in no served bundle.** It can
   neither render nor report a failure. This has cost a whole panel.
3. **Never quote a suite count, a timing or a line number from a document, including this one.**
   Re-run, re-measure, re-grep.
4. **A speed claim and its equality proof appear together.** Field count and difference count on
   live data, never a tolerance; timings in alternating rounds.
5. **The store's key decides whether to write**, and **no pain rating enters the key or payload of
   any recording-derived product**: in the key it discards a 37 s build on every report; in the
   payload it lets a file serve a stale rating, the one failure with no visible symptom.
6. **Every write-back carries its provenance chain and writer.** Without them the self-derived
   refusal cannot fire, and Stim Optimizer would confirm its own exploration policy while the
   record looks like converging evidence.
7. **Do not edit `Client/src/database/resultCache.js`, `useCachedResult.js` or `RecomputeBar.js`**
   (the PI's; lifted once each for decisions 54 and 259, the latter only to enlarge the recompute bar's text).
8. **Plan approval is not execution authority.** He gives an explicit go-ahead before implementation.
9. **Push and identity are answered (2026-09-07):** push this branch's work; identity
   `git -c user.name="Prasad Shirvalkar" -c user.email="prasad.shirvalkar@ucsf.edu"` on every commit
   (the sandbox cannot write git config). Older commits keep their machine identity.
10. **Plain language, no jargon, and a claim only beside its result.** Read
    `HOUSE_RULES_writing_and_claims.md` before writing any reply, report, commit message or document.
11. **Never verify by the shape of an answer; open it and read the values** (PI, 2026-09-10:
    measure the actual values bit for bit). Three times a right-shaped answer reported success while
    wrong: a check handed a table with no ratings said "no ratings matched" forever (104); six grids
    stored, six successes, one file on disk (107); a job asked for one key and wrote another, and
    every test passed because each built its key by hand (96). So: count the files, print the
    values, compare field by field, read the number back out of the thing that stored it.
12. **He must be able to read it without having read the code** (PI, 2026-09-10, after a reply he
    could not follow). Before sending, ask of each sentence whether someone who has never opened
    this repository would understand it; if not, the sentence is wrong however accurate. Function,
    file and field names are the worst offenders: say what the thing does, name it in brackets only
    if he would need it to find the code.
13. **Every explanation says which module, where on the page, and whether it is on screen today**
    (PI, 2026-09-10). This project keeps much that is built, tested and reached by nothing. If it is
    on no page, say that first.
14. **Log power enters no calculation anywhere** (PI, 2026-09-19, decision 202). **Time is modelled
    nowhere**: drift is a current effect (decision 196). **Device thresholds sit on raw power**: never
    log-scale a power plot or statistic, never pool across electrodes (memory: no-log10).

---

## 9. Read these first

@HOUSE_RULES_writing_and_claims.md
@ARCHITECTURE_cache_store.md
@DECISIONS_and_open_items.md

## 10. Reference, by subject (not imported; open the one that matches)

- `DEVICE_percept_rc.md` — threshold modes, timing ranges, recording products and export keys, the
  two quantities both written LSB, every calibration constant and whether measured or composed.
- `ARCHITECTURE_modules_and_store.md` — the three modules, where request time goes, routines and
  response keys, file map. Its cache sections predate the one store; `ARCHITECTURE_cache_store.md` wins.
- `METHODS_measurement_and_findings.md` — band power definition, the two corrections, live results
  with their limits, the eight things never to claim.
- `OPERATIONS_runbook.md` — container, bridge, the two runners, traps already paid for.
- `DESIGN_biomarker_pipeline_v2.md` — the design ledger and the band-candidate contract.
- `AUDIT_2026-09-15_side_effect_penalty_and_pain_scale.md` — dated audit, superseded by decisions 164-166.
- Module-level documents, cited by decisions: `BRAVO/modules/StimOptimizer/{OBJECTIVE_SPEC,TWO_STAGE_DESIGN,BOTORCH_REFACTOR,FIGURES,README}.md`,
  `Biomarkers/{README,RECONCILIATION_F8}.md`, `ClosedLoopDeployment/WIRING_stability_into_the_report.md`,
  `_agent_bridge/HANDOFF_agent_bridge.md`.
- `docs/archive/2026-09-07/INDEX.md` and `docs/archive/2026-09-19/INDEX.md` — which document replaced each archived one.

## 11. Live participant

**RCS08**, uid `2e3c75c00d7f4f37b53a048d195f11da`. Device exports on the shared drive at
`…/PNL/RCS008 jsons` (file names carry real patient names; keep the folder out of the repository).
Cached pain-report table: `BRAVO/_pro_dump/RCS08_chronic_pro_df.csv`. Clinic sheets sync from the
Drive folder "Clinic Testing" daily (decision 182).
