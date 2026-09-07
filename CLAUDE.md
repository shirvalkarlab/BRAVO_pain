# BRAVO_pain — Claude Agentic Framework, tailored to this repository

Django backend, React frontend. Ingests exported files from the **Medtronic Percept RC**
neurostimulator and patient-reported pain scores from REDCap, and produces a stimulation
configuration a clinician programs by hand. **There is no interface that writes to the device.**

**This file merges the generic Claude Agentic Framework with the rules this project already
established.** Where the two disagree, the disagreement is written out rather than silently
resolved — see **§10, which overrides anything above it.** Three of the seven core principles
conflict with something here that was decided for a measured reason.

**Framework tree status, checked rather than assumed:** `.claude/` exists but holds only an
untracked `settings.local.json` from June. **`.claude/rules/`, `.claude/skills/` and
`.claude/commands/` do not exist yet**, and neither do `./artifacts/` or `./scratchpad/`. So every
reference below to an auto-loaded rule file or a skill directory describes where those things go
once installed, not where they are. **Install the framework tree before relying on any of it, and
do not report a rule as loaded because this file names it.**

---

## 1. Quick Reference

```bash
# --- the two test suites. THEY RUN IN DIFFERENT PLACES AND A GREEN RUN OF ONE IS NOT A GREEN
# --- RUN OF THE PLATFORM. Never quote a count without a run behind it.

# container: Biomarkers (19 files) + CacheStore (3). No pytest in there, so tests use plain assert.
python3 BRAVO/_agent_bridge/bridge_client.py --cwd /usr/src/BRAVO --timeout 900 --wait 900 \
  "python3 _agent_bridge/run_tests.py"

# host: ClosedLoopDeployment (10) + StimOptimizer (18) + CacheStore (3). These use pytest.
cd BRAVO/modules && PYTHONPATH=. python -B -m pytest \
  ClosedLoopDeployment/tests StimOptimizer/tests CacheStore/tests -q -W ignore

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

**THIS DOES NOT HOLD HERE, and acting on it would take a decision that is not yours.** Six commits
sit on `PS_closedloop_deployment` and on no remote; `origin` is at `705bdb0`. **Whether to push is
the principal investigator's call, and so is whose name goes on the commits** — that question has
been asked three times and is still open, which is why the existing ones carry a machine identity.
The git configuration file is not writable in the sandbox this work was done in, so identity is
passed inline:

```bash
git -c user.name="..." -c user.email="..." commit -m "..."
```

**Commit iteratively: yes. Push without being asked: no.**

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

### Planning flow

The framework's ladder — vision, requirements, architecture decision, design specification, plan,
tasks — with ceremony scaled to scope. **The live plan already exists and is not in that shape:**

`.planning/2026-09-06-cache-store-and-record-consolidation/`

| File | What it holds |
|---|---|
| `task_plan.md` | the 30 step titles, **verbatim from the approved plan** — do not rename them, progress is reported against them |
| `findings.md` | **§1 the 30 resolved contradictions** across the source documents; **§5 the machine-checked port** |
| `progress.md` | what was read, verified, decided and built, in order |

**Keep using these three for the cache-store work rather than opening a parallel plan.** The
directory name says `2026-09-06` because this machine's local date runs a day behind the session
day; it is a key, so leave it.

---

## 5. Artifacts and working directories

| Location | Use it for | Lifecycle |
|---|---|---|
| repository root, `*.md` | the ten reference documents — **already established, referenced by name in commit messages and the archive index; do not move them into `./artifacts/`** | committed |
| `.planning/<plan-id>/` | the live plan, findings and progress for the cache-store work | committed |
| `./artifacts/` | **new** framework-shaped documents, once the framework is installed: `adr_*.md`, `prd_*.md`, `design_spec_*.md`, `postmortem_*.md`, following the framework's naming table | committed; **does not exist yet** |
| `docs/archive/2026-09-07/` | 51 superseded documents plus `INDEX.md` naming what replaced each. **Everything in there is superseded and every line number in it has moved** | committed, read-only in practice |
| `docs/exported_artifacts/` | 11 files pulled out of a cloud store so they are on disk: both cache inventory drawings, the architecture drawing in three formats, the four-lens audit of record, the port gap list | committed |
| `./scratchpad/` | ephemeral notes | gitignored; **does not exist yet** |
| `BRAVO/_agent_bridge/_*` | **the existing scratch area**, and the only path the container can see. Probe scripts written here are gitignored and disposable | gitignored |

**Two warnings about this tree.**

1. **`BRAVO/_agent_bridge/_*` holds stale copies of real module files**, including old
   `bravo_service.py`. A search for a function name returns most of its hits there. **Do not edit
   or grep them expecting live code.**
2. **`.gitignore` carries blanket rules `HANDOFF_*.md` and `AUDIT_TRIAGE_*.md`** from when the root
   was filling with per-session handoffs. They were excluding the opposite of what was intended —
   the one handoff a new session must read, and three archived audits — and negations were appended
   to restore them. **If you add a file whose name matches those patterns, check `git status`
   actually sees it.** A file that exists locally but is untracked survives only until someone runs
   `git clean`.

---

## 6. Task tracking

1. **Durable record** — this project has no issue tracker in use. The durable list is
   **`DECISIONS_and_open_items.md`**: 34 decisions and the single open-items list. Add to it rather
   than starting an `ISSUES.md`.
2. **In-flight work** — the native task list, owned by the orchestrator.
3. **Handoffs** — `HANDOFF_2026-09-07_cache_store_to_claude_code.md` is the current one. Its §0
   lists every file, its §4 says what to do first.

---

## 7. Commands

The framework's roles. **They require `.claude/commands/`, which is not installed here yet.**

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
matches. **`.claude/skills/` does not exist here yet**, so there is nothing to check until the
framework tree is installed.

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
9. **Do not push, and do not choose a commit identity.** See §2 principle 6.
10. **Write in plain language with no jargon**, and **only make a claim about a result if the same
    reply contains the result.** The full rules, the replacement table, and the eight things that
    must never be claimed are in `HOUSE_RULES_writing_and_claims.md`. **Read it before writing any
    reply, report, commit message or document.**

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
