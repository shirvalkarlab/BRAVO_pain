# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

BRAVO_pain: Django backend, React frontend. It reads exported files from the **Medtronic Percept RC**
neurostimulator and pain scores from REDCap, and produces a stimulation configuration a clinician
programs by hand. **Nothing here writes to the device.** §7 overrides everything above it. Rewritten
2026-09-27 (older versions: `docs/archive/<date>/CLAUDE.md` and git history).

## 1. Commands

Both test suites run **inside the `bravo-server` container**, through the bridge. The container
mounts `BRAVO/` live at `/usr/src/BRAVO`. **No Python on this Mac has pytest.**

```bash
# Both suites at once (routine run); then poll BRAVO/_agent_bridge/outbox/<job>.out
python3 BRAVO/_agent_bridge/bridge_client.py --cwd /usr/src/BRAVO --timeout 900 --wait 5 \
  "sh _agent_bridge/run_both_suites.sh"                    # --live: only the live-record tests
# One test, in the container (works for either suite's files)
python3 BRAVO/_agent_bridge/bridge_client.py --cwd /usr/src/BRAVO/modules --timeout 120 --wait 120 \
  "PYTHONPATH=/usr/src/BRAVO:. DJANGO_SETTINGS_MODULE=BRAVO.settings python3 -B -m pytest \
   <Package>/tests/test_x.py::test_name -q -W ignore -p no:cacheprovider"
# Any command in the container; --status is the heartbeat (a stall needs a restart)
python3 BRAVO/_agent_bridge/bridge_client.py --cwd /usr/src/BRAVO --timeout N --wait M "<cmd>"
python3 BRAVO/_agent_bridge/bridge_client.py --status
# Reload gunicorn after a Python edit (workers do not always pick it up)
python3 BRAVO/_agent_bridge/bridge_client.py --cwd /usr/src/BRAVO --timeout 30 --wait 30 "kill -HUP 1"
# Frontend build: REQUIRED after any change under Client/src; the rebuilt chunks are committed
cd Client && export PATH="/usr/local/bin:$PATH" npm_config_cache=/tmp/npmcache \
  && env CI=false GENERATE_SOURCEMAP=false npm run build
# Page tests (jest): one file, or drop the path for all
cd Client && CI=true npx react-scripts test --watchAll=false src/views/Reports/figureStyle.test.js
```

- **Two suites; a green run of one is not a green platform.** `run_tests.py` (plain `assert`):
  Biomarkers, CacheStore, DecodeCommon, ControlAnalyses, MedtronicPercept. pytest:
  ClosedLoopDeployment, StimOptimizer, CacheStore, DecodeCommon, ControlAnalyses (the shared three
  take no test arguments). Markers in `modules/pytest.ini`: `store` runs serially, `live` daily.
- **No linter, type checker or formatter exists;** the gates are the two suites, the build and the
  page tests. **CI** (`.github/workflows/ci.yml`, every push and pull request): pytest without
  `store`/`live`, page tests, build, `gitleaks` (add a fingerprint to `.gitleaksignore`, never loosen
  it). CI cannot run the container suite (needs MySQL, Redis, R, rpy2).

## 2. Architecture

- **Ingest:** `BRAVO/modules/MedtronicPercept/` parses device exports; every time is put on the
  tablet clock (`TabletClock.py`), never the device clock. `modules/DataCurator.py` writes to MySQL.
- **Requests:** `BRAVO/Server/APIs/urls.py` → `Server/APIs/DataAnalysis.py` (`queryBiomarkerAnalysis`,
  `queryStimOptimizer`, `queryClosedLoopDeployment`, ...) → each module's `bravo_service.py`.
- **Three analysis modules = three pages.** `modules/Biomarkers/` (band power against pain, the
  heat-map grids), `modules/StimOptimizer/` (which settings to explore next),
  `modules/ClosedLoopDeployment/` (whether a chosen band can drive closed loop); pages in
  `Client/src/views/Reports/{Biomarkers,StimOptimizer,ClosedLoopSim}/`, one browser-side result
  cache (`Client/src/database/resultCache.js`), served from the committed `Client/build/`.
- **Shared code:** `modules/DecodeCommon/` (one home for matching, the implant-date cut, device
  ranges, the sensing-pair rule); `modules/CacheStore/` (the one saved-results store, with provenance
  and a Redis build lock; a second store is a test failure; Redis here is version 5, so
  **construct every Redis client with `protocol=2`**); `modules/ControlAnalyses/` (offline only).
- Detail: `ARCHITECTURE_modules_and_store.md` (file map, timings); `ARCHITECTURE_cache_store.md`.

## 3. Workflow

- **Branch:** `PS_closedloop_deployment` is the default; work lands on it directly. `v3.1.0` is a
  tag label. **No worktrees:** the container mounts only the main checkout.
- **Plans:** `planning-with-files` (`/pwf "<name>"`), committed under `.planning/`, `inject-smart`,
  autonomous with attestation allowed, never gated; none is live today. Keep Goal and Next Step short.
- **Record:** `DECISIONS_and_open_items.md` is the digest and the only open-items list (no issue
  tracker, no handoffs). A new decision: one line in its Part 3 plus a full row in
  `docs/decision_log_full_2026-09-19.md`.

## 4. Where things live

- Root `*.md`: reference documents (§8), do not move them. `artifacts/`: specs, reviews, analyses
  (current design spec: `artifacts/design_2026-09-26_minimalist_redesign/SPEC.md`).
  `docs/archive/<date>/`: superseded documents with an `INDEX.md`; their line numbers are stale.
- `BRAVO/_agent_bridge/_*`: **the scratch area, the only path the container sees**, gitignored. It
  holds stale copies of real modules: never edit them or search them expecting live code.
- `.gitignore` has blanket `HANDOFF_*.md` and `AUDIT_TRIAGE_*.md` rules: check `git status` sees a
  new file matching them. `.claude/` is gitignored (this machine only).

## 5. Skills

Load the matching one before touching its files; if it will not load, ask for the conventions:
`bravo-stimoptimizer-figures` (`StimOptimizer/routines/plots.py` and the decision plots),
`bravo-timeline-layout` (`BiomarkerDataTimeline.js`'s left labels), `bravo-session-rules` (ignore
its line about `MEGA_HANDOFF.md`, archived), `jevgrep` (rule 14).

## 6. Principles, as this repository needs them

- **Before changing anything that looks obviously improvable, search `DECISIONS_and_open_items.md`:**
  several obvious changes here reverse a decision made for a measured reason.
- Tests before code; a regression test for every fix; a test named for something untrue is worse
  than none (split it, never relabel it). Never mix a refactor and a speed-up in one commit. Before
  a fix, name three testable causes, cheapest first; after three failed attempts, stop and ask.
- **"Delete dead code" does damage here.** Kept on purpose: `LSB_RULE_OF_THUMB`,
  `LFP_POWER_LSB_TO_UV2` (their comments prevent a units error), struck decision rows,
  `test_one_store.py`'s grandfathered count. Python and plain JavaScript; no TypeScript.

## 7. Project rules that override everything above (from the PI and failures already paid for)

1. **`/usr/src/BRAVO` IS a live mount** of `BRAVO/`: write on the host and run. Root files and
   `Client/` are absent from it. Two pushed commit messages say otherwise and are wrong.
2. **A frontend change without a rebuild is in no served bundle**: it can neither render nor
   report a failure. To prove a panel is served, search the built chunks for a text string it owns.
3. **Never quote a suite count, timing or line number from a document, this one included.** Re-run.
4. **Any change to how a value is produced or stored, and any speed claim, comes with its equality
   proof:** field count and difference count on live data, never a tolerance; timings in
   alternating rounds (`ARCHITECTURE_cache_store.md` §5).
5. **The store's key decides whether to write; no pain rating in the key or payload of any
   recording-derived product** (in the payload it serves a stale rating with no visible symptom).
6. **Every write-back carries its provenance chain and writer**, or Stim Optimizer can confirm its
   own exploration policy.
7. **`resultCache.js`, `useCachedResult.js` and `RecomputeBar.js` are ours to edit** (the PI lifted the
   old no-edit rule, 2026-10-02: "these are our files, edit as needed"). They serve all three pages,
   so a change to them comes with a cache test and the full page-test run.
8. **Plan approval is not execution authority.** He gives an explicit go-ahead before implementation.
9. **Push this branch's work** (standing go-ahead, 2026-09-07), identity inline on every commit:
   `git -c user.name="Prasad Shirvalkar" -c user.email="prasad.shirvalkar@ucsf.edu"`. Commit only
   meaningful changes; record edits ride in the next code commit.
10. **Plain language, no jargon, a claim only beside its result:** the house rules, imported below.
11. **Never verify by the shape of an answer; read the values** (three right-shaped successes were
    wrong: decisions 96, 104, 107). Count the files, print the values, compare field by field.
12. **He must be able to read it without having read the code.** Say what a thing does; name the
    code in brackets only if he needs it. Say which module, where on the page, and whether it is
    on screen today; if it is on no page, say that first.
13. **Log power enters no calculation anywhere; time is modelled nowhere; device thresholds sit on
    raw power; never pool across electrodes** (decisions 196, 202).
14. **Search with jevgrep, not grep** (PI, 2026-09-27; skill `jevgrep`, OpenJev via Codiv). For
    finding, classifying, routing, ranking, retrieving or verifying code by meaning, run
    `jg "<question>" <narrowest folder>`. Grep only for exact text: a literal string, a count,
    proving something is absent (rules 2, 3, 11). Every `jg` sends the folder's code to Codiv: never
    `--no-ignore`, never a folder holding patient data.

## 8. Read first, and on demand

@HOUSE_RULES_writing_and_claims.md

Open when the work touches the subject: `DECISIONS_and_open_items.md` (before changing earlier
work), `ARCHITECTURE_cache_store.md` (the store), `DEVICE_percept_rc.md` (device settings, export
keys, calibration constants), `METHODS_measurement_and_findings.md` (band power, live results, what
never to claim), `OPERATIONS_runbook.md` (container, bridge, traps), `DESIGN_biomarker_pipeline_v2.md`,
and the module documents (`StimOptimizer/*.md`, `Biomarkers/*.md`, `ClosedLoopDeployment/*.md`).

## 9. Live participant and patient data

**RCS08** (the de-identified code), uid `2e3c75c00d7f4f37b53a048d195f11da`, implanted 2025-07-16.
Device exports on the shared drive at `…/PNL/RCS008 jsons` carry **real patient names in file
names: keep that folder out of the repository.** `secrets/` stays untracked. Cached pain reports:
`BRAVO/_pro_dump/RCS08_chronic_pro_df.csv` (gitignored). Clinic sheets sync daily from the Drive
folder "Clinic Testing".

## 10. Visit sheets (in-clinic and at-home) and the chronic home record

Full rules, notations and edge cases: `docs/clinic_sheets_parsing.yaml` (machine-readable).
- **Sync before reading** (`manage.py sync_clinic_sheets`); check the newest local sheet against the
  newest visit (on 2026-10-01 the copy had stopped at 2026-09-17).
- **Ratings live in more than the Stim Testing tab**: the Notes tab holds timed verbal scores; a
  rating belongs to the step in force when given (within its duration + 60 s); then REDCap fills
  what is left, by filing time (VAS / 10). `rating_source` records which.
- **Unrated steps are exposure, never pain data**; an unrated step with no time is a plan, not a
  delivery (the 09_24_26 sheet is an exported ladder never filled in).
- **Clinic and home streams are never merged**: clinic ratings choose, home ratings confirm.
- Traps: "8/10" stored by Excel as 10 August; Left lead 0-3 and Right 8-11; text after "/" in old
  notation is sEEG; bipolar "1+2-"; the device record cannot tell bipolar from monopolar.
