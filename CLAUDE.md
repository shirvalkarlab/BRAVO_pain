# BRAVO_pain — Claude Agentic Framework, tailored to this repository

Django backend, React frontend. Ingests exported files from the **Medtronic Percept RC**
neurostimulator and patient-reported pain scores from REDCap, and produces a stimulation
configuration a clinician programs by hand. **There is no interface that writes to the device.**

**This file merges the generic Claude Agentic Framework with the rules this project already
established.** Where the two disagree, the disagreement is written out rather than silently
resolved — see **§10, which overrides anything above it.** Three of the seven core principles
conflict with something here that was decided for a measured reason.

**Framework tree status, checked rather than assumed (re-checked 2026-09-07, second session):**
`.claude/` now holds `rules/`, `skills/`, `hooks/`, `agents/`, `templates/` and `settings.json`, and
**the whole tree is gitignored by `.gitignore` line 336**, so it exists on this machine and in no
clone. `.claude/commands/` and `./scratchpad/` still do not exist; `./artifacts/` exists and is
empty. Check `ls .claude` before relying on any of it, and **do not report a rule as loaded because
this file names it.** The project's plan is tracked with the `planning-with-files` plugin, which is a
user-scope install and not part of this tree — see §4.

---

## 1. Quick Reference

```bash
# --- the two test suites. THEY RUN IN DIFFERENT PLACES AND A GREEN RUN OF ONE IS NOT A GREEN
# --- RUN OF THE PLATFORM. Never quote a count without a run behind it.

# container: Biomarkers (22 files) + CacheStore (4) + DecodeCommon (1). No pytest in there, so tests use plain assert.
python3 BRAVO/_agent_bridge/bridge_client.py --cwd /usr/src/BRAVO --timeout 900 --wait 900 \
  "python3 _agent_bridge/run_tests.py"

# host: ClosedLoopDeployment (11) + StimOptimizer (20) + CacheStore (4) + DecodeCommon (1). These use pytest;
# CacheStore and DecodeCommon run on BOTH runners on purpose, so their tests take no arguments.
cd BRAVO/modules && PYTHONPATH=. python -B -m pytest \
  ClosedLoopDeployment/tests StimOptimizer/tests CacheStore/tests DecodeCommon/tests -q -W ignore

# --- run anything inside the live server container
python3 BRAVO/_agent_bridge/bridge_client.py --cwd /usr/src/BRAVO --timeout N --wait M "<cmd>"
python3 BRAVO/_agent_bridge/bridge_client.py --status      # heartbeat; a stall needs a restart

# --- frontend. REQUIRED after any change under Client/src, and the rebuilt chunks are committed.
cd Client && export PATH="/usr/local/bin:$PATH" && export npm_config_cache=/tmp/npmcache \
  && env CI=false GENERATE_SOURCEMAP=false npm run build
```

**There is no linter, no type checker, no formatter and no continuous integration in this
repository** — no `pyproject.toml`, no `setup.cfg`, no `ruff`, no standalone eslint configuration,
no `.pre-commit-config.yaml`, no `.github/workflows`. `Client/package.json` carries only
`start`, `build`, `test` and `eject`, with the default React eslint settings inline. **So "run the
quality gates" here means exactly three things: the two test suites, and the frontend build.**
Claiming a linter or type check passed would be claiming something that cannot have run.

---

## 2. Core Principles

The framework's seven, each with what it means in this repository. **Read the annotations — three
of them invert the generic advice.**

### 1. Understand First
Read before writing; grep before creating; verify an interface against the code rather than
recollection.

**Here this is stronger than usual, for a measured reason: every code line number in every
archived document has moved.** Fifty-one superseded documents sit in `docs/archive/2026-09-07/`
and their citations were all correct once. Search for the name, never trust the number. **And
before changing something that looks obviously improvable, read
`DECISIONS_and_open_items.md`** — several obvious-looking changes in this project are reversals of
a decision made for a measured reason.

### 2. Prove It Works
Tests before code, the gates before every commit, a regression test for every fix.

**Two additions, both load-bearing.**

- **A test whose name asserts something untrue is worse than no test.** When you remove a
  calculation, split the test rather than relabelling its assertion. One test in this repository
  had been creating its condition by breaking a helper the code no longer called, so it passed
  while checking nothing.
- **Check the values, never the shape.** A right-shaped answer is the most dangerous wrong answer:
  it passes every test and looks normal on every page. Count the files, print the numbers, read the
  value back out of the thing that stored it. "It returned a table", "the keys are all there" and
  "nothing raised" are not verification. **§10 rule 11 is the full rule, with the three times this
  project has been caught by it.**
- **Software tests are only half of "it works" here. The other half is proving the numbers did not
  move.** Any change to how a value is produced or stored must report a field count and a
  difference count on live data — **never a tolerance**, because "within 1e-9" hides a real change
  in a value that happens to be small. Any speed claim must report timings in **alternating
  rounds**, because the operating system's file cache favours whichever ran second. **A speed claim
  and its equality proof appear in the same report.** Procedure:
  `ARCHITECTURE_cache_store.md` §7.

### 3. Keep It Safe
No secrets in code, validate input, least privilege, flag vulnerabilities immediately.

**The specific exposure here is patient information, not credentials.** The device export file
names on the shared drive **carry real patient names** — keep that folder out of the repository.
`RCS08` is the de-identified code and repository exports are derived spectral features only.
`secrets/redcap.env` is excluded from version control and must stay so.

### 4. Keep It Simple
Single responsibility, no premature abstraction, delete dead code, fix warnings before committing.

**"Delete dead code" is the one that will do damage here, so read this before acting on it.** This
repository deliberately keeps things that look dead:

- **`LSB_RULE_OF_THUMB` and `LFP_POWER_LSB_TO_UV2`** are unused constants whose comments record
  that nothing multiplies by them. **Misreading one of them as a working conversion is what left
  the closed-loop page's numbers unscaled**, so the warning travels with them. Deleting them
  deletes the warning.
- **Superseded rows in the decision log are kept struck rather than removed**, because in those
  cases the mistake is the lesson.
- **`test_one_store.py` grandfathers exactly two constructs** and asserts the count is one, so
  that when the pending migration lands the test fails and says to delete the exemption. That
  assertion looks redundant and is not.

**"Avoid `any` types" does not apply** — this is Python and plain JavaScript, with no TypeScript
anywhere.

### 5. Don't Repeat Yourself
Check the skills directory before generating an ad-hoc solution; one source of truth per rule.

**This principle is the reason the newest work exists.** Two implementations of the same cache
lived in two modules, drifted apart, and disagreed by a factor of four about how large an entry may
be. They are now one module, `BRAVO/modules/CacheStore/`, and `test_one_store.py` reads the other
modules' source and fails on the constructs that make a private store. **A comment asking a future
reader not to write a third copy would not have prevented the second one.**

### 6. Ship It
*Framework text: work on a branch, commit iteratively, push to remote — work isn't done until
`git push` succeeds.*

**THIS DOES NOT HOLD HERE only in part.** Pushing without being asked was never the principal
investigator's default, but he gave that go-ahead on 2026-09-07 for this branch's work
("Push everything") and every commit since has gone to `origin`. **Whose name goes on the
commits was asked three times and is now answered, on 2026-09-07: his own** — Prasad Shirvalkar,
`prasad.shirvalkar@ucsf.edu`. The commits made before that date carry a machine identity and are
not rewritten. The git configuration file is not writable in the sandbox this work was done in,
so identity is still passed inline on every commit:

```bash
git -c user.name="Prasad Shirvalkar" -c user.email="prasad.shirvalkar@ucsf.edu" commit -m "..."
```

**Commit iteratively: yes. Push without being asked: no — but he has already said yes for this
branch's ongoing work, so continue pushing what he already authorized rather than asking again
each time.**

### 7. Leave a Trail
Artifacts in a durable directory, work tracked, decisions in architecture decision records, clear
names.

**The principle holds; the location does not.** `./artifacts/` does not exist here. This project's
durable trail predates the framework and is what every commit message, the archive index and 545
rows of one tool's stored memory point at. **See §4 for which location to use for what.**

---

## 3. Tech Stack

| Layer | What |
|---|---|
| backend | Django, served by gunicorn behind nginx in the `bravo-server` OrbStack container |
| container runtime | Python 3.12.3, rpy2 3.5.15, pymer4 0.8.2, pandas 2.2.3, scikit-learn 1.5.2 |
| frontend | React via react-scripts; `Client/build` is a **committed** compiled bundle |
| database | MySQL 8.0.46, `BRAVOServer`, 44 tables |
| shared memory store | Redis 5.0.14 — **construct every client with protocol version 2**, since this predates version 6 and rejects the newer handshake |
| cache on disk | Parquet with zstd for tables, compressed array files for spectra, pickle otherwise |
| statistics | statsmodels, and mixed models through rpy2 and pymer4 |

Once `.claude/rules/tech-strategy.md` exists it should point back at `DEVICE_percept_rc.md` and
`ARCHITECTURE_modules_and_store.md` rather than restate them.

---

## 4. Workflow

### Branching — corrected against this repository

*The framework's default is trunk-based development off `main`.* **There is no `main` branch
here.** The default branch is **`v3.1.0`**, and the working branch **`PS_closedloop_deployment`**
is long-lived rather than short-lived: 61 commits of it were merged into `v3.1.0` as pull request
#9, and work continued on it afterwards. Other remote branches are `development` and the release
line `v2.0-alpha` through `v2.2.1`.

**So: keep working on `PS_closedloop_deployment`, never commit to `v3.1.0` directly, and treat
"short-lived branches off `main`" as not describing this repository.** If trunk-based development
is wanted here, that is a change to propose to the principal investigator, not a default to assume.

### Planning flow — the `planning-with-files` skill

The framework's ladder — vision, requirements, architecture decision, design specification, plan,
tasks — with ceremony scaled to scope. **The live plan already exists and is kept in the shape of
the `planning-with-files` plugin** (OthmanAdi, version 3.16.1, installed at user scope under
`~/.claude/plugins/cache/planning-with-files/`; adopted for this project on 2026-09-07). The plugin
keeps three markdown files on disk as working memory and injects the plan's head into every turn
and every matched tool call, so the plan survives compaction and a new session.

**The active plan** is named in `.planning/.active_plan` and lives at
`.planning/2026-09-06-cache-store-and-record-consolidation/`. The directory name says `2026-09-06`
because this machine's local date runs a day behind the session day; it is a key, so leave it.

| File | What it holds | Update it |
|---|---|---|
| `task_plan.md` | the goal, the single next step, the current phase, five phases with **all 30 step titles verbatim from the approved plan** (`docs/archive/2026-09-07/PLAN_cache_store_phase2_2026-09-07.md`) as checkboxes, the decision table, the error table | tick a step when it lands; change a phase's status when it changes; **rewrite Next Step whenever a status changes**; add a row to Decisions for every design choice and to Errors for every error, with the attempt number |
| `findings.md` | observations only, never instructions: §1 the 30 resolved contradictions, §5 the machine-checked port, §6 the code map for the remaining steps and the state of the tooling | after any discovery, and after every two read or search operations whose result matters |
| `progress.md` | the chronological session log: what was read, what was run with the counts beside the run that produced them, what was built, the errors, the reboot check | throughout the session, and before stopping |

**The format the plugin parses, which is why it matters.** Its completion check and its status
command count every three-hash `Phase` heading under the `Phases` section and every bold status
line whose value is one of `complete`, `in_progress` and `pending`; both are matched as substrings,
so neither form may appear anywhere else in the file. One status line per phase, five phases, and
step titles as checkboxes beneath them. Verify after editing:

```bash
sh ~/.claude/plugins/cache/planning-with-files/planning-with-files/3.16.1/scripts/check-complete.sh
```

**The rules the skill imposes, all of which this project already wanted:** create or re-read the
plan before starting; re-read it before any decision; log every error to the plan and never repeat
a failed action unchanged; after three failed attempts stop and ask; update the files after acting
rather than at the end. Commands: `/plan` or `/pwf` to initialise a plan, `/status` for a phase
summary, `/plan-doctor` when the hooks seem silent, `/plan-attest`, `/plan-loop` and `/plan-goal`
for the optional attestation and loop modes.

**Choices made for this project, decision 8 in `task_plan.md`.** The planning files are
**committed** (the plugin's default is gitignored). The plan runs in the plugin's legacy mode with
structure-aware injection only — `.planning/<plan-id>/.mode` holds the single token `inject-smart`,
so each injection carries the goal, the next step, the phase in progress and the last three
decisions rather than the file's first lines. **No attestation and no autonomous or gated mode**:
attestation blocks injection whenever the plan file changes until it is re-attested, and this file
changes after every phase; the gate can refuse a stop, and in this project the principal
investigator decides when work stops.

**Keep using these three files for the cache-store work rather than opening a parallel plan.** A
second, independent task gets its own plan directory through `/pwf "<name>"` and its own
`.active_plan` entry; do not put it in this one.

---

## 5. Artifacts and working directories

| Location | Use it for | Lifecycle |
|---|---|---|
| repository root, `*.md` | the ten reference documents — **already established, referenced by name in commit messages and the archive index; do not move them into `./artifacts/`** | committed |
| `.planning/<plan-id>/` | the live plan, findings and progress for the cache-store work, in the `planning-with-files` shape (§4), plus the `.mode` marker | committed |
| `./artifacts/` | **new** framework-shaped documents: `adr_*.md`, `prd_*.md`, `design_spec_*.md`, `postmortem_*.md`, following the framework's naming table | exists, empty; committed once something is in it |
| `docs/archive/2026-09-07/` | 51 superseded documents plus `INDEX.md` naming what replaced each. **Everything in there is superseded and every line number in it has moved** | committed, read-only in practice |
| `docs/exported_artifacts/` | 11 files pulled out of a cloud store so they are on disk: both cache inventory drawings, the architecture drawing in three formats, the four-lens audit of record, the port gap list | committed |
| `./scratchpad/` | ephemeral notes | gitignored; **does not exist**, and `BRAVO/_agent_bridge/_*` is the scratch area in use |
| `BRAVO/_agent_bridge/_*` | **the existing scratch area**, and the only path the container can see. Probe scripts written here are gitignored and disposable | gitignored — see warning 3, which is what that word did not cover until 2026-09-10 |

**Three warnings about this tree.**

1. **`BRAVO/_agent_bridge/_*` holds stale copies of real module files**, including old
   `bravo_service.py`. A search for a function name returns most of its hits there. **Do not edit
   or grep them expecting live code.**
2. **`.gitignore` carries blanket rules `HANDOFF_*.md` and `AUDIT_TRIAGE_*.md`** from when the root
   was filling with per-session handoffs. They were excluding the opposite of what was intended —
   the one handoff a new session must read, and three archived audits — and negations were appended
   to restore them. **If you add a file whose name matches those patterns, check `git status`
   actually sees it.** A file that exists locally but is untracked survives only until someone runs
   `git clean`.
3. **The row above called this whole folder gitignored, and until 2026-09-10 that was true only of
   the `.py` files sitting directly inside it.** The rule was `BRAVO/_agent_bridge/*.py`, and that
   wildcard does not reach into a folder below it — so a stale
   `_bm_sync/Biomarkers/bravo_service.py`, **the exact hazard warning 1 names**, was untracked but
   not ignored. It showed in `git status`, and one `git add -A` would have put a second, stale copy
   of real module source into the repository where a later grep finds it as live code. Every
   non-`.py` scratch file leaked the same way, and `cl_docs/` was covered by nothing at all.
   Measured that day: **265 files on this macOS checkout, 273 matched case-sensitively the way the
   Linux container does**, 240 of them `.py`. Fixed with `BRAVO/_agent_bridge/_*` and `/cl_docs/`,
   which match at every depth. **Nothing was untracked by it** — an ignore rule never removes a file
   already in the index, proven before and after: 23 tracked files, identical list. One side effect:
   staging one of those 23 by its own explicit path now needs `git add -f`, as it already did for
   `bridge_client.py`; `git add -u`, `git add -A`, `git add .` and `git commit -a` are unaffected.

---

## 6. Task tracking

1. **Durable record** — this project has no issue tracker in use. The durable list is
   **`DECISIONS_and_open_items.md`**: 34 decisions and the single open-items list. Add to it rather
   than starting an `ISSUES.md`.
2. **In-flight work** — the checkboxes and status lines of `task_plan.md` (§4), which survive the
   session, plus the native task list within a session, owned by the orchestrator.
3. **Handoffs** — `HANDOFF_2026-09-07_cache_store_to_claude_code.md` is the current one. Its §0
   lists every file, its §4 says what to do first.

---

## 7. Commands

The framework's roles. **`.claude/commands/` does not exist here; the roles are installed as skills
under `.claude/skills/` instead, gitignored with the rest of the tree.**

| Command | Role | Where it fits here |
|---|---|---|
| `/architect` | Principal Architect | the remaining store design; write decisions into `DECISIONS_and_open_items.md` |
| `/builder` | Software Engineer | the five remaining Track A steps |
| `/qa-engineer` | QA Engineer | **the equality proofs, not only the test suites** |
| `/security-auditor` | Security Auditor | patient information exposure and the REDCap credential |
| `/ui-ux-designer` | UI/UX Designer | the three module pages |
| `/code-check` | Codebase Auditor | **read §2 principle 4 first** — several things that look like dead code here are deliberate |
| `/land-the-plane` | Finish-Line Protocol | **its push step does not apply — see §2 principle 6** |
| `/tailor` | Configuration Tailor | it will find no linter, no type checker and no continuous integration; that is accurate, not a gap to fill silently |
| `/swarm-plan` `/swarm-execute` `/swarm-review` `/swarm-research` | Orchestrators | the remaining tracks are largely independent and suit parallel work |

---

## 8. MCP tools

The framework lists Sequential Thinking, Chrome DevTools, Context7 and Filesystem. **None of them
is verified as connected in this repository. Check what is actually available rather than assuming
this list.**

If browser tooling is used against this platform: nginx serves the compiled bundle from
`Client/build`, and **the timeline and closed-loop views are code-split into numbered chunks rather
than `main.<hash>.js`** — so to prove a panel reached the served bundle, search the chunks for a
string literal that panel owns, not for the component name.

---

## 9. Skills

Claude Code loads each skill's name and description at startup and pulls in the body when it
matches. `.claude/skills/` now holds the framework's seventeen skills, gitignored. **The
`planning-with-files` skill this project's plan depends on is not among them: it is a user-scope
plugin** at `~/.claude/plugins/cache/planning-with-files/`, and §4 says how it is used here.

**Three project-specific skills exist outside this repository and their substance is only partly
written down.** The session obligations are in this file. **The figure conventions for the
optimiser and closed-loop plots, and the timeline's left-label geometry, are not** — they matter
only when touching `StimOptimizer/routines/plots.py` or `BiomarkerDataTimeline.js`. **If you touch
either, ask for those conventions rather than inventing them**; the figure ones include a rule that
has cost this project whole figure sets.

---

## 10. Project rules that override everything above

**These come from the principal investigator and from failures already paid for. Where they and the
framework disagree, these win.**

1. **`/usr/src/BRAVO` IS a live mount** of the `BRAVO/` subtree — write on the host and run. Only
   repository-**root** files and `Client/` are absent from it. An earlier claim that it is not a
   mount was wrong and reached two pushed commit messages that cannot be edited.
2. **A frontend change without a bundle rebuild produces a component that exists in source and in
   no served bundle.** It can neither render nor report a failure. This has cost this project a
   whole panel.
3. **Never quote a test-suite count, a timing, or a code line number from a document — including
   this one.** Re-run, re-measure, re-grep.
4. **A speed claim and its equality proof appear together.** Field count and difference count on
   live data, never a tolerance; timings in alternating rounds.
5. **The store's key decides whether to write, not the caller**, and **no pain rating may enter the
   key or the payload of any recording-derived product.** A rating in the key would discard a
   37-second build every time a report was filed; a rating in the payload would let a file serve a
   stale rating, **which is the one failure in this system with no visible symptom.**
   `CacheStore/tests` pins both.
6. **Anything written back into the store carries its provenance chain and its writer.** Without
   them the self-derived refusal cannot fire. **Stim Optimizer decides which settings need
   exploring, which decides which recordings exist** — so if it reads a verdict computed from those
   recordings as independent evidence, its own policy confirms itself, nothing crashes, and the
   record looks like converging evidence when it is a loop.
7. **Do not edit `Client/src/database/resultCache.js`, `useCachedResult.js` or `RecomputeBar.js`.**
   They are the principal investigator's, and two defects in them are open on him.
8. **Plan approval is not execution authority.** He gives an explicit go-ahead before
   implementation. He gave it for the cache-store phases on 2026-09-07.
9. **Pushing and the commit identity are both answered, 2026-09-07.** Push: yes, for this
   branch's ongoing work — see §2 principle 6. Identity: Prasad Shirvalkar,
   `prasad.shirvalkar@ucsf.edu`, passed inline on every commit since the git configuration file
   cannot be written in the sandbox. Commits made before this date keep the machine identity they
   were made with.
10. **Write in plain language with no jargon**, and **only make a claim about a result if the same
    reply contains the result.** The full rules, the replacement table, and the eight things that
    must never be claimed are in `HOUSE_RULES_writing_and_claims.md`. **Read it before writing any
    reply, report, commit message or document.**

11. **NEVER CHECK THAT SOMETHING WORKED BY LOOKING AT THE SHAPE OF THE ANSWER. OPEN IT AND READ THE
    ACTUAL VALUES.** Given by the principal investigator on 2026-09-10, in his words: *"never verify
    results or changes based on the shape of a variable but always measure the actual variable
    values bit for bit or byte for byte."*

    A right-shaped answer is the most dangerous kind of wrong answer, because it passes every test
    and looks normal on every page. **These are not hypothetical — each one happened in this
    project and each one reported success while being wrong:**

    - The reliable-change check was handed a table with no pain ratings in it. Every item came back
      "no ratings were matched", **which is exactly what a correct answer looks like when the data
      have not arrived yet.** It would have said that forever, including after the ratings arrived.
      Caught only by reading the six values and noticing all six were identical when one was known
      to be different (decision 104).
    - Six grids were computed and stored, six writes each reported success, and **one file was on
      disk.** Caught only by counting the files (decision 107).
    - A background job asked for one key and the run it started wrote a different one. Nothing
      raised, the run succeeded, and the page would have started a whole-machine job on every load
      forever. **Every test passed, because each built its key by hand** (decision 96).

    **So: count the files. Print the values. Compare field by field and report how many were
    compared and how many differed, never a tolerance and never a percentage on its own. Read the
    number back out of the thing that stored it, not out of the variable you just set.** "The
    payload has the right keys", "it returned a dict", "the length is 6", "no exception was raised"
    and "the tests pass" are **not** verification. This rule sits alongside rule 4's equality proof
    and is the general form of it.

12. **HE HAS TO BE ABLE TO READ IT WITHOUT HAVING READ THE CODE.** Said again on 2026-09-10, of a
    reply that was mostly unreadable to him: *"you're starting to use weird jargon again and I can't
    understand half of what you just previously said."* Rule 10 already says this and it keeps
    slipping, so the test is now written down: **before sending, take each sentence and ask whether
    somebody who has never opened this repository would know what it means. If the answer is no,
    the sentence is wrong, however accurate it is.**

    The words that failed on 2026-09-10 are listed with their plain replacements in
    `HOUSE_RULES_writing_and_claims.md` §2a. **Function names, file names, field names and internal
    switch names are the worst offenders** — say what the thing does, and put the name in brackets
    afterwards only if he would need it to find the code himself.

---

## 11. Read these first

@HOUSE_RULES_writing_and_claims.md
@HANDOFF_2026-09-07_cache_store_to_claude_code.md

## 12. Reference, by subject

@ARCHITECTURE_cache_store.md
@DECISIONS_and_open_items.md

Four more are large and are **not** imported, so they stay out of context until needed. Open the
one that matches what you are touching:

- `DEVICE_percept_rc.md` — the three threshold modes and their fixed timing, the recording products
  with their exact export keys, the two different quantities both written LSB, and every
  calibration constant stated as what it converts from and to and **whether it was measured on
  simultaneous recordings or composed by chaining**.
- `ARCHITECTURE_modules_and_store.md` — the three modules, where request time actually goes, the
  named routines and response keys, the file map. **Its cache sections describe the state before
  the store was unified; `ARCHITECTURE_cache_store.md` is newer where they disagree.**
- `METHODS_measurement_and_findings.md` — how a band power is defined, the two multiple-comparison
  corrections, the live results with the limit on each, **and the eight things that must never be
  claimed**.
- `OPERATIONS_runbook.md` — the container, the bridge, the two test runners, the traps already paid
  for.
- `DESIGN_biomarker_pipeline_v2.md` — the 890-line design ledger, including the band-candidate
  contract between the two modules.
- `docs/archive/2026-09-07/INDEX.md` — which document replaced each archived one.

---

## 13. Live participant

**RCS08**, live identifier `2e3c75c00d7f4f37b53a048d195f11da`. Device exported files are on the
shared drive at `…/PNL/RCS008 jsons`; **those file names carry real patient names, so keep that
folder out of the repository.** Cached pain-report table at
`BRAVO/_pro_dump/RCS08_chronic_pro_df.csv`.
