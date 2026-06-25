# Session handoff — next session (two parallel tracks)

**Date written:** 2026-06-25
**Repo:** `/Users/pshirvalkar/dev/BRAVO_pain`, branch `PS_closedloop_deployment`, remote
`shirvalkarlab/BRAVO_pain`. **HEAD `90fd5c3`**, in sync with origin (0 ahead / 0 behind).
**Backend suite:** 166/166 PASS via the `_agent_bridge` runner (`python3 _agent_bridge/run_tests.py`).
**Full prior context:** `MEGA_HANDOFF.md` (7 sessions synthesized + all closures).

## State at handoff — what just closed

- **Item #4 (impedance gain term `c=1.02`):** REJECTED & documented (`3207c29`→`a9c3a01`). Cluster-
  robust SE n.s.; collinear with calendar time; deployable effect 1.07× (below the model's own
  1.26× σ). Frozen fit untouched.
- **High-gamma 55.5 Hz:** action item CLOSED (`90fd5c3`). Not actionable for closed-loop — the
  Percept RC adaptive modes are firmware-limited to 8–30 Hz, so a 55.5 Hz sensing-only band cannot
  drive a controller. The extrapolation GUARD shipped earlier (`dac25ac`, `9de1aeb`) STAYS:
  `estimate_lsb` flags `freq_extrapolated` outside 7.8–28.3 Hz. No 55.5 Hz streaming calibration
  needed. Evidence: `rcs08_highgamma_extrapolation.png`.
- **Audit C4 (power on optimistic AUC):** RESOLVED (`7fcee95`). `auc_power(..., auc_lo=)` reports a
  power band and the "powered" gate fail-closes on the CI-lower-bound end. Test:
  `test_auc_power_conservative_band_gates_on_ci_lower_bound`.

## Operational gotchas (carry forward — these WILL bite otherwise)

- **Container is the only test runner.** Docker socket is permission-denied from the sandbox; use
  the `_agent_bridge` mailbox watcher (running INSIDE the `bravo-server` OrbStack container on the
  `./BRAVO ↔ /usr/src/BRAVO` bind mount). Submit: `cd BRAVO/_agent_bridge && python3 bridge_client.py
  --cwd /usr/src/BRAVO --wait <min> --timeout <s> "<cmd>"`. Runner: `python3
  _agent_bridge/run_tests.py` (no pytest in container). `--status` reads the heartbeat.
- **Git config is unwritable in the sandbox.** Commit with identity via env vars:
  `GIT_AUTHOR_NAME/EMAIL` + `GIT_COMMITTER_NAME/EMAIL` = `Prasad Shirvalkar
  <prasad.shirvalkar@ucsf.edu>`. The `/Users/pshirvalkar/.config/git/ignore` "Operation not
  permitted" and keychain `failed to store: -50` warnings are BENIGN — pushes succeed.
- **`save_artifacts` only resolves WORKSPACE-relative paths**, not the repo path. Copy the file into
  `/Users/pshirvalkar/.operon/orgs/e1a4e614-cfd2-4f53-ae46-1203303ddbf1/workspaces/e2117876-0f1f-48e9-ab78-b121ebbf6edf/`
  first, then save.
- **Frozen model is sacred:** `b=0.8545`, `r²=0.841`, 8.8 Hz `a=1.7695`. Do not refit.

---

# TRACK 1 (delegate to a separate reviewer agent) — code-review audit of the 27 medium + 24 low findings

**Goal:** clear the remaining backlog from the four-lens closed-loop deployment audit. The 4 HIGH
(C1, C2, C3, C8) and C4 are all resolved; **27 medium + 24 low** remain.

**Source of the findings:** the original audit report is the artifact `closedloop_audit_report.md`,
version_id `e3a12136-e0e1-4fff-b95f-baa42d0a0a46` (56 findings: 4 high · 28 medium · 24 low; C4 now
closed → 27 medium remain). Read it in full first. Companion artifacts: `ClosedLoopSim_review.md`
(`83f7dea0-ff85-4dc1-9ae7-f07ea7f62ea6`), `closedloop_audit_summary.png`
(`1019772b-7697-4089-b4db-c37bc9b57c80`). The `FIXHANDOUT_MASTER_biomarker_fixes.md` in the repo
root carries the priority-ordered backend+frontend fix list.

**Engineering code-review plugin:** Prasad wants this done with the engineering plugin's code-review
skill. **CAVEAT — verify it is attached first:** as of this writing, `search_skills` for
code-review terms did NOT surface a named engineering code-review skill in the catalog, and the
configured agent profiles are `BOOKMARKER, ONBOARDING, OPERON, REVIEWER, DATAML_COPY,
MATLAB_PROGRAMMER` — `REVIEWER` is a *transcript* reviewer (fabrication / plan-deviation), not a
code-quality reviewer. **First action: run `search_skills` for the engineering plugin and check
`operon.agents.list()`/`operon.skills.list()`.** If the engineering code-review skill is present,
load it and drive the audit through it. If it is not attached, tell Prasad it needs attaching
(Customize → Connectors / Skills) before this track can use it — do not silently substitute a
generic review.

**How to run it:** spawn this as a **separate reviewer sub-agent** (`operon.delegate`, its own
context). Give it: the audit report artifact, the repo path, the 166/166 baseline, and the gotchas
above. Ask it to triage the 27+24 into (a) quick mechanical fixes it can batch, (b) findings that
need a judgment call from Prasad, (c) anything already silently resolved by C1/C2/C3/C8/C4 (the
audit noted several "resolve automatically once Cx lands" dependencies — verify, don't assume).
Output: a ranked fix plan + PRs, each validated against the container suite.

---

# TRACK 2 (do this yourself, in parallel) — percept-spectral-repro comparison → timeline + deployment LSB

**This analysis is already DONE** — see `ANALYSIS_percept_spectral_repro_comparison.md` in the repo
root (committed this session). It read the repro repo's `HANDOFF.md` + `spectral.py` +
head-to-head benchmark and compared to our frozen model. **Read that file first**; the punchlines
and plan below are its summary.

**Repo:** `shirvalkarlab/percept-spectral-repro` (HANDOFF.md is the entry point).

### Punchline 1 — how they compare
- Our `269 LSB/µV²` Welch256 band-integral constant is **independently vindicated**: the repro repo
  re-fit it on RCS08 and got 270.2 / 266.2 (all / stim-off rows) — within ~0.4%.
- Their RC+S-Hann transform reaches lower RMSE (60.6 vs 208.9 LSB) on direct block-level
  `BrainSenseLfp` reproduction, but ONLY after fitting a **transform-specific, drifting** scale
  (`k≈353–357`, swings to 461–577 at `ZERO_THREE_RIGHT` 26.37 Hz). Median fold-error is the SAME as
  our `269` route (≈1.09×) — the difference is outlier RMSE, not typical error.
- Our frozen log-log model scores r=0.515 on THIS surface — **not a defect**: it was fit for
  percentile-anchored deployment thresholds, not direct block-level power. The repro authors say
  explicitly not to use that number to dismiss the model.

### Punchline 2 — optimal approach
A tiered fall-through, native-preferred: (1) native device LSB when the band was sensed — both
codebases agree this is best, and our `band_lsb_and_power` ALREADY does it; (2) a modeled conversion
for PSD-only bands — **Welch256 × `269` is the default candidate, but the exploratory-timeline method
is chosen empirically in Step 0** (it may instead be the repro transform + report-CV k if that wins
in-window on accuracy AND stability); (3) frozen per-band model for its intended deployment-threshold
job, with the existing extrapolation guard; (4) never the white-paper `100` (under-scaled 3.5×) and
never the repro fitted-k as a single fixed constant (it drifts by channel/frequency/session — only
the report-held-out CV form is defensible, and even then per the Step-0 verdict).

### Implementation plan (build this)
See `ANALYSIS_percept_spectral_repro_comparison.md` §"Proposed implementation plan" for the detailed
version. **The method choice for the timeline is NOT pre-decided — Step 0 decides it empirically.**

- **Step 0 — RUN THE REPRO CODEBASE AND PICK THE METHOD (do this FIRST; it gates A/B/C).**
  Prasad's instruction: independently run `shirvalkarlab/percept-spectral-repro` and verify the
  **"repro transform + report-held-out CV k"** route — the one with the low RMSE (r=0.993, RMSE
  62.1 LSB, median fold 1.10× on n=131; its key property is that k is fit with the SAME report held
  out, so it is honest out-of-sample, not a same-report refit). Then **decide which method drives the
  biomarker timeline / exploratory plotting + calculations.** Concretely:
  1. Clone the repo, `uv --cache-dir .cache/uv run pytest` + `ruff check .` to confirm it runs, then
     re-run `scripts/benchmark_brainsense_power.py --jobs 16 --out-dir results/...`. Reproduce the
     head-to-head table (their numbers: transform+CV-k RMSE 62.1 vs Welch256+269 RMSE 208.9, both
     r≥0.92, both median fold ≈1.09–1.10×).
  2. **Restrict the comparison to the 8–30 Hz window** — that is the band that matters for the
     biomarker exploration workflow and is the only range the adaptive controller can use. Re-score
     each method on 8–30 Hz paired rows only (the full-corpus numbers include out-of-range bands).
     Report per-method r / RMSE / median-fold **within 8–30 Hz**, since that is the decision-relevant
     metric, not the all-band number.
  3. **Decision criteria for the timeline method** (state the verdict explicitly with the numbers):
     - *Accuracy in 8–30 Hz* — does transform+CV-k actually beat Welch256+269 on TYPICAL error
       (median fold), or only on outlier RMSE? (At the corpus level the median fold was identical;
       check whether that holds in-window.)
     - *Stability* — the transform's k drifts 10–16% early→late and up to ~1.5× at ZERO_THREE_RIGHT
       26.37 Hz. For an exploratory timeline that must read consistently week-to-week, a drifting
       scale is a real cost. Quantify the in-window drift before choosing.
     - *Interpretability / single source of truth* — Welch256+269 is the same physical constant the
       deployment module already uses; using a different transform for the timeline means two
       conversions in one product. Weigh that.
     - *Native-first is non-negotiable either way* — whichever modeled method wins is the FALLBACK;
       native device LSB is still preferred when the band was sensed.
  4. **Write the verdict** into `ANALYSIS_percept_spectral_repro_comparison.md` (new "Timeline method
     decision" section) with the in-window numbers and the chosen method. THEN proceed to A/B/C using
     the chosen method — do not hardcode 269 in Step A until Step 0 confirms it (or swaps in the
     transform+CV-k route).
  Note: their benchmark needs paired TD/`BrainSenseLfp` rows; the repo's are RCS08 Stage-1. If those
  data are not reachable from this environment, say so and fall back to a code-level review of
  `spectral.py` + the committed `results/.../brainsense_power_head_to_head_summary.json` — do NOT
  fabricate benchmark numbers.

- **A.** Shared `analytics.psd_band_to_lsb(...)` helper implementing the **method chosen in Step 0**
  (Welch256 × 269 *or* the report-CV-k transform), reusing the existing `freq_extrapolated`
  (7.8–28.3 Hz) guard. The target conversion window is **8–30 Hz** — convert PSDs (and, where TD is
  present, time-domain windows) to LSB across that band for the exploratory workflow. One conversion
  path, one chosen constant/transform.
- **B. Timeline (Biomarker view):** extend `availability.lsb_series` with a `source="psd_modeled"`
  tier so survey/montage PSD bands (which have a PSD but no native LSB) get a calibrated LSB trace
  over 8–30 Hz; render it with a distinct hollow marker + a legend naming the chosen method (e.g.
  "modeled from PSD (×269)" or "modeled (repro transform, CV-k)") so it is never confused with native
  LSB. This is the user's *"drive LSB for all the band powers from the PSD"* ask.
- **C. Closed-loop deployment module:** `band_lsb_and_power` already prefers native LSB and only
  models when the band was unsensed — VERIFY its fallback routes through the new shared helper, and
  add an FYI native-vs-modeled agreement cross-check on the sign-off card. **Deployment-threshold
  conversion stays on the physically-interpretable Welch256+269 / frozen-model path regardless of
  what Step 0 picks for the timeline** — if Step 0 chooses the transform for exploratory display, the
  timeline and the deployment threshold may legitimately use different methods (exploratory fidelity
  vs deployment stability are different objectives); document that split clearly. Do NOT change the
  frozen model.
- **D.** Validate via `_agent_bridge` (baseline 166/166); the Step-0 benchmark doubles as the
  confirmation that our chosen conversion reproduces the expected fold-error.

**Why these are two separate tracks:** Track 1 is a context-heavy review backlog best handled by a
dedicated sub-agent; Track 2 is hands-on feature work on the timeline + deployment module. They touch
different files (Track 1 ranges across the audit surface; Track 2 is `analytics.py` +
`availability.py` + `bravo_service.py` + `BiomarkerDataTimeline.js`) and can run concurrently.
