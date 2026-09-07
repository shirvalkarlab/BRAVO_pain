# BRAVO_pain

Django backend, React frontend. Ingests exported files from the **Medtronic Percept RC**
neurostimulator and patient-reported pain scores from REDCap, and produces a stimulation
configuration a clinician programs by hand. **There is no interface that writes to the device.**

Working branch `PS_closedloop_deployment`; default branch `v3.1.0`.

## Read these before writing anything

@HOUSE_RULES_writing_and_claims.md
@HANDOFF_2026-09-07_cache_store_to_claude_code.md

## Reference, by subject

@DEVICE_percept_rc.md
@ARCHITECTURE_cache_store.md
@DECISIONS_and_open_items.md

Three more are large and are **not** imported here, so they do not sit in context on every session.
Open the one that matches what you are touching:

- `ARCHITECTURE_modules_and_store.md` — the three modules, where request time goes, the named
  routines and response keys, the file map. **Its cache sections describe the state before the
  store was unified; `ARCHITECTURE_cache_store.md` is newer where they disagree.**
- `METHODS_measurement_and_findings.md` — how a band power is defined, the two
  multiple-comparison corrections, the live results with the limit on each, **and the eight things
  that must never be claimed**.
- `OPERATIONS_runbook.md` — the container, the bridge, the traps already paid for.
- `DESIGN_biomarker_pipeline_v2.md` — the 890-line design ledger, including the band-candidate
  contract.
- `docs/archive/2026-09-07/INDEX.md` — 51 superseded handoffs, and which document replaced each.
  **Everything in that folder is superseded; every code line number in it has moved.**

## Commands

**The two test suites run in different places, and a green run of one is not a green run of the
platform. Never quote a count without a run behind it.**

```bash
# container: Biomarkers + CacheStore. No pytest in there, so tests use plain assert.
python3 BRAVO/_agent_bridge/bridge_client.py --cwd /usr/src/BRAVO --timeout 900 --wait 900 \
  "python3 _agent_bridge/run_tests.py"

# host: ClosedLoopDeployment + StimOptimizer + CacheStore. These use pytest.
cd BRAVO/modules && PYTHONPATH=. python -B -m pytest \
  ClosedLoopDeployment/tests StimOptimizer/tests CacheStore/tests -q -W ignore

# run anything inside the live server container
python3 BRAVO/_agent_bridge/bridge_client.py --cwd /usr/src/BRAVO --timeout N --wait M "<cmd>"
python3 BRAVO/_agent_bridge/bridge_client.py --status      # heartbeat; stalls need a container restart

# frontend — REQUIRED after any change under Client/src, and the rebuilt chunks are committed
cd Client && export PATH="/usr/local/bin:$PATH" && export npm_config_cache=/tmp/npmcache \
  && env CI=false GENERATE_SOURCEMAP=false npm run build
```

## Rules that are not negotiable

1. **`/usr/src/BRAVO` IS a live mount** of the `BRAVO/` subtree. Write on the host and run. Only
   repository-**root** files and `Client/` are absent from it. An earlier claim that it is not a
   mount was wrong and reached two pushed commit messages.
2. **A frontend change without a rebuild produces a component that exists in source and in no
   served bundle** — it can neither render nor report a failure. This has cost this project a whole
   panel. The timeline and closed-loop views are code-split into numbered chunks, not
   `main.<hash>.js`, so search the chunks for a string literal the panel owns.
3. **Never quote a test-suite count, a timing, or a code line number from a document.** Re-run,
   re-measure, re-grep. Every line citation in the archived documents has moved.
4. **A speed claim and its equality proof appear together**: field count and difference count on
   live data, never a tolerance; timings in alternating rounds. See
   `ARCHITECTURE_cache_store.md` §7.
5. **The store's key decides whether to write, not the caller**, and **no pain rating may enter the
   key or payload of a recording-derived product**. `CacheStore/tests` pins both.
6. **Anything written back into the store carries its provenance chain and its writer.** Without
   them the self-derived refusal cannot fire, and the failure it prevents has no symptom.
7. **Do not edit `Client/src/database/resultCache.js`, `useCachedResult.js` or `RecomputeBar.js`.**
   They are the principal investigator's, and two defects in them are open on him.
8. **Plan approval is not execution authority.** He gives an explicit go-ahead before
   implementation. He gave it for the cache-store phases on 2026-09-07.
9. **The git configuration file is not writable in the sandbox this work was done in**, so commit
   identity is passed inline: `git -c user.name=... -c user.email=... commit`. **Whose name should
   be on these commits is an open question for him — ask once, then be consistent.**

## Live participant

**RCS08**, live identifier `2e3c75c00d7f4f37b53a048d195f11da`. Device exported files are on the
shared drive at `…/PNL/RCS008 jsons`; **those file names carry real patient names, so keep that
folder out of the repository.** Cached pain-report table at
`BRAVO/_pro_dump/RCS08_chronic_pro_df.csv`.
