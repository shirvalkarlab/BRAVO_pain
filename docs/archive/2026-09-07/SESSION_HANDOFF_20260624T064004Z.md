# Session handoff — ClosedLoopSim figure-reset fix + PR merge to v3.1.0

**Written:** 2026-06-24T06:40:04Z · **Repo:** `/Users/pshirvalkar/dev/BRAVO_pain`
**Prior handoff:** `SESSION_HANDOFF_20260624T053839Z.md` (the biomarker-engine work that this session reviewed).

---

## TL;DR — everything the user asked for this session is DONE and SHIPPED

1. **Reset bug fixed** — the ClosedLoopSim module no longer collapses/resets every figure on slider move / toggle / figure click.
2. **Four-reviewer critique done** — viz, statistical rigor, interaction design, and hands-on interactive QA (built Plotly prototypes, exercised every control). Findings acted on + saved.
3. **Pushed, PR'd, reviewed, merged** — `PS_biomarker_module` → **`v3.1.0`** (the repo's default branch = the "main channel"). **PR #3 is MERGED and CLOSED.**

There are **no open work threads**. The only forward-looking items are the optional Phase-2 visualization upgrades listed at the bottom (not started; they need backend changes).

---

## Git state (verified at handoff)

- Local branch `PS_biomarker_module`, **HEAD = `255e0ef`**, tree **clean**, in sync with `origin/PS_biomarker_module`.
- `origin/v3.1.0` **HEAD = `52337f5`** = "Merge PR #3: Pain Biomarkers + Closed-Loop Deployment module into v3.1.0".
- The `255e0ef` commit (the ClosedLoopSim fix) is the most recent on the branch; the 109 commits before it are the prior biomarker-engine work.
- Remote: `https://github.com/shirvalkarlab/BRAVO_pain.git`. **Default branch is `v3.1.0`** (HEAD moved here from the now-deleted `v3.0.0-alpha`). Other live branches: `development`, `v2.x`. There is NO `3.1-beta`/`3.1-alpha` — it's just `v3.1.0`.
- Git author identity to reuse: `Prasad Shirvalkar <prasad.shirvalkar@ucsf.edu>` (set via `GIT_AUTHOR_*`/`GIT_COMMITTER_*` env vars per commit; `.git/config` is unwritable in this sandbox → the `could not write config file` / keychain `-50` warnings on push are HARMLESS, the push/merge still succeed).
- **PR #3:** https://github.com/shirvalkarlab/BRAVO_pain/pull/3 — merged 2026-06-24T06:35:00Z, merge commit `52337f51c77ce82abd10acc46f74f36b8e6ba8a3`, 110 commits, 127 files, +26797/-735, 0 conflicts. My review is posted as an issue comment (GitHub blocks "approving" your own PR).

---

## What the commit `255e0ef` changed (frontend only — no backend/API or stats-engine changes)

All files under `Client/src/views/Reports/ClosedLoopSim/`. The production bundle `Client/build` was rebuilt: chunk **`431.afb86956` → `431.d554f4a8`**, main **`main.4fedca57` → `main.4fb8bc8b`**. ClosedLoopSim lives in **chunk 431** (code-split), NOT chunk 768 (that's the timeline). `asset-manifest.json` + `index.html` both reference the rebuilt bundles. Build command: `cd Client && GENERATE_SOURCEMAP=false NODE_OPTIONS=--openssl-legacy-provider npx react-scripts build` (exits 0; node v24.13.0, npm 11.6.2, node_modules present ~1.2G).

### Reset bug — three mechanisms, all fixed
1. **`index.js`** — `requestParamsFromCandidate(bc)` was called inline in JSX → new object identity every render → all 4 panels list `requestParams` in their fetch `useEffect` deps → any child state change (ROC cost slider lifting a cut-point) re-created it → every panel refetched → every figure unmounted to loading state. **Fix:** `const requestParams = useMemo(() => requestParamsFromCandidate(bc), [bc])`; all 4 panels rewired to `requestParams={requestParams}`.
2. **`DeploymentRocPanel.js`** — the Plotly `<div ref>` was inside the `loading ? … : success` ternary, so any refetch unmounted the graph DOM (lost zoom). **Fix:** the `<div ref>` is now permanently mounted with `display: roc ? "block" : "none"`; loading/error became a banner ABOVE it; controls wrapped in `{roc && !loading && !err ? … : null}`.
3. **`DeploymentRocPanel.js`** — draw effect cleanup purged the graph on every `[roc,opThr,opRule]` change. **Fix:** split into effect (A) draw ROC base once per `[roc]` with cut-point marker as a fixed empty trace at index [2]; effect (B) move ONLY the marker+annotation via `Plotly.restyle(gd,...,[2])`+`Plotly.relayout` on operating-point change; purge moved to an unmount-only effect. The cut-point lift to the parent is debounced 250 ms so slider drags don't thrash the LSB/era fetches.

### Cut-point correctness / UX (from the reviewer audit)
- **Removed the `net benefit` rule** — its objective is exactly `prevalence × the cost objective` (`u_nb = p·u_cost`), so it always selected the IDENTICAL operating point as `cost`. Two device-threshold buttons that can never disagree, with float ties occasionally flipping = looks like a bug. Kept one `cost` rule; deterministic first-maximizer tie-break (strict `>`). True Vickers net benefit is a decision CURVE, noted as a Phase-2 panel.
- **Degenerate operating-point guard** — `solveCutpoint` now returns a `degenerate` flag (spec<0.10, sens<0.30, or corner pins fpr>0.95 / (fpr<0.02 & sens<0.5)). The ROC summary box warns (amber) + marker turns amber; the flag is threaded through the cut-point lift so `LsbPowerPanel` shows a warning banner and refuses to present a confident "THRESHOLD TO PROGRAM"; `DeploySignoffCard` shows it too.
- **Adaptive annotation offset** — the "power ≥ X" label flips toward the plot interior near top/right corners (where F1 and low cost ratios land) so it no longer clips off-panel.
- **Plain-language relabeling** — matchDir toggle `prior`/`pro_first` → "Forecasting (deploy default)" / "Concurrent (exploratory)" with tooltip; cut-point rules carry clinical descriptors ("Balanced (Youden)", "Favor detection (F1)", "Cost-weighted"); cost slider gains "← fewer false triggers / catch more pain →" end labels. Sensitivity/specificity privileged in the cut-point box with an explicit in-sample-optimism caveat.
- **`DeploySignoffCard`** — records operating-point provenance (which rule chose the cut-point + achieved sens/spec + degenerate flag) on the card and in the exported JSON (`operating_point` key, schema `deploy_signoff_v1`).

**Validation done:** babel parse OK on all 5 files; build EXIT=0; new chunk 431 contains all new strings and zero `net benefit` / `pro_first (discovery)`.

---

## Artifacts saved this session

- `ClosedLoopSim_review.md` (artifact `29f8efc6-1f58-4c29-bf73-2b9c6c6c76f9`, version `83f7dea0-ff85-4dc1-9ae7-f07ea7f62ea6`) — full four-reviewer critique: findings tables + the interactive QA test log (every control exercised, verdicts).
- `ClosedLoopSim_source.txt` (artifact `0d4444e7-4bc9-433c-bc64-6a19b3d6f292`) — the concatenated module source bundle handed to the reviewers (hidden).
- The interactive QA reviewer saved Plotly prototypes as artifacts: `roc_cost_slider.html` (`d5b08e59-...`), `roc_rule_toggle.html` (`58948907-...`), `roc_matchdir_toggle.html` (`2b936e5f-...`), plus PNG snapshots `roc_rule_grid.png` (`8521cd3d-...`), `roc_matchdir.png` (`11d57c4a-...`).
- The viz reviewer saved `recommended_encodings.png` (`0384ee9b-d6cb-437c-9178-74d43a7321c2`) — the Phase-2 encoding mockups.

---

## OPEN / FUTURE — Phase 2 visualization upgrades (NOT started; optional; need backend changes)

All four reviewers converged on these. They are visual-encoding upgrades, deferred because each needs the `/api/queryDeployment*` endpoints to return new data arrays:
1. **Feature-distribution histogram** (pain-high vs pain-low) with the threshold line drawn on it, beneath the ROC in `DeploymentRocPanel`. Needs the API to return the per-sample oriented log-power feature values. (Reviewers' single highest-impact change.)
2. **AUC forest/dot plot across stim eras** (OFF/LOW/HIGH/Pooled) with a pooled-CI band, replacing the 4 text EraCards in `EraRefitPanel`. Needs per-era AUC+CI arrays (already computed server-side; just surface them).
3. **Power-vs-N sufficiency curve** replacing the 3-number StatBox row in `LsbPowerPanel`. Needs a power curve array.
4. **Shared colorblind-safe palette** (Okabe–Ito) hoisted out of the 4 files into one module — replaces the red/green pass-fail pairing on the deploy-decision axis (current hardcoded hexes duplicated across files: #1A73E8, #0a7f3f, #B17500, #9A3324, #6c757d) and the era palette reusing the accent blue for HIGH.

The `recommended_encodings.png` mockup illustrates #1–#3.

### ps-plotly vs plotly.js note (from the QA reviewer)
The module uses **browser plotly.js 2.x imperatively** (`Plotly.react` + `Plotly.restyle(…,[traceIndex])` + `Plotly.relayout`), NOT the Python ps-plotly figure-rebuild / `add_annotation` / kaleido pattern. A maintainer following the ps-plotly skill verbatim would be steered toward rebuilding figures (which re-introduces the reset bug). Keep the restyle-by-trace-index pattern for any Phase-2 work in this module.

---

## Environment / mechanics reminders
- Conda env `bravo_app` (Python 3.11.15) for local decode; needs a dummy Fernet key before importing HelperFunctions. Live container `bravo-server` runs the code via `BRAVO/_agent_bridge/` (Python 3.12.3, rpy2 3.5.15, pymer4 0.8.2).
- `cd` is inside granted rw host folder `/Users/pshirvalkar/dev`; relative paths act on the user's real files. Edit via `edit_file`; delete only via `delete_host_files` (never `rm`).
- Subject de-identified as RCS08.
