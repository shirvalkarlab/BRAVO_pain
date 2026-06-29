# Session Handoff — Audit C2: forward-chaining / out-of-sample validation

**Branch:** `PS_biomarker_actionability` (not yet committed this session)
**Participant tested:** RCS08 (uid `2e3c75c00d7f4f37b53a048d195f11da`)
**Prior handoff:** `SESSION_HANDOFF_20260625T011910Z.md` (frozen PSD→LSB model)

---

## What this session did

Closed **Audit C2 (HIGH)** — the last unaddressed HIGH finding from the four-lens
closed-loop deployment audit. Until now every deployment AUC / sens / spec was
**in-sample**: fit AND evaluated on one contiguous record. For a controller that
runs forward in time the decision-relevant number is next-week held-out
performance. This session adds expanding-window, blocked-by-week forward-chaining
and surfaces the held-out number beside the in-sample one, with a new gate.

### Backend — the estimator
`routines/analytics.py` :: **`deployment_forward_chaining(td_detail, channel_raw,
center_hz, *, band_width_hz, strategy, low_pct, high_pct, pain_cutoff,
min_train_clusters=8, test_block_weeks=1, max_test_expand_weeks=4, n_boot=500, seed=0)`**

Anti-look-ahead discipline (the whole point of the finding):
- **Rating CLUSTERS** are the unit, each assigned to ONE elapsed-week by its
  earliest sample, so a cluster's near-duplicate PSDs never straddle the
  train/test boundary. Weekly buckets reuse `_elapsed_week_cluster` (same unit as
  the glmer's weekly random intercept).
- Per fold: band **sign (flip)** and the **Youden threshold** are fit on the TRAIN
  clusters ALONE; the held-out future clusters are scored with that fixed sign +
  threshold. No future information touches the threshold.
- Test folds are **non-overlapping** and strictly after their train window → every
  held-out cluster is scored exactly once by a model that never saw it (OOF).
- The held-out AUC is **NOT re-folded** (no `max(auc,1-auc)`): it can honestly fall
  below 0.5 when the train sign doesn't generalize — same de-fold discipline as C1.
- Held-out-AUC CI = bootstrap over independent held-out clusters. `beats_chance_forward`
  ⇔ CI lower bound > 0.5.

Returns `{available, n_folds, reliable, in_sample_auc, held_out_auc,
held_out_auc_lo/hi, held_out_auc_mean_fold, beats_chance_forward, held_out_sens,
held_out_spec, optimism (= in_sample − held_out), n_test_clusters, n_test_samples,
folds:[{test_week_start, n_train_clusters, n_test_clusters, train_auc, test_auc,
sens, spec}], note}` or `{available:False, reason}`.

### Backend — service wiring (`bravo_service.py`)
- `deployment_summary` and `band_deployment_roc` both call the estimator and return
  a **`forward`** block (in-sample vs held-out AUC+CI, optimism, per-fold trace).
- New PE gate **`forward_validated`** (SUPPORTIVE, not necessary):
  - `pass`  — held-out CI clears chance.
  - `fail` (collapse) — held-out AUC ≤ 0.55: "band did NOT generalize forward".
  - `fail` (underpowered) — held-out POINT holds near in-sample but CI dips below
    0.5: "UNDERPOWERED forward; more weeks of ratings needed". (Distinguished by
    optimism so a perfectly-generalizing-but-thin band isn't mislabeled a failure.)
  - `indeterminate` — no forward split / unstable CI (absence of evidence, non-pass).
- Caveats mirror the three forward outcomes. The export record (`deploy_signoff_v1`)
  already serializes the whole `summary`, so `forward` + the gate travel into the JSON
  with no schema change.

### Frontend (`Client/src/views/Reports/ClosedLoopSim/DeploySignoffCard.js`)
- EVIDENCE block now shows **"Deployment AUC — in-sample"** and a new
  **"Deployment AUC — forward held-out (N weekly folds)"** row, colored green when it
  clears chance / warn-amber when not, with a ✓/✗ tag. The `forward_validated` gate
  renders automatically through the existing `data.gates.map` (tri-state GateRow).
- eslint clean; full production build (`Client/build/`) recompiled, exit 0.

### Tests (+4, all green)
`tests/test_analytics.py`: `test_forward_chaining_validates_stationary_band` (real
stationary signal → held-out clears chance, optimism≈0), `..._null_band_does_not_beat_chance_forward`
(in-sample optimistic >0.5 but held-out CI drops below 0.5), `..._catches_sign_reversal_over_time`
(late folds score below chance, fails forward), `..._guards_single_week`.

## Verification (LIVE DB, REDCap-backed container)
Full `modules/Biomarkers/tests/` via `_agent_bridge/run_tests.py`: **PASS=161 FAIL=0**
(includes the model-dependent files that can't run in the local standalone runner).

Forward-chaining on three committed RCS08 bands (prior, NBoot=400) — see
`c2_forward_validation_RCS08.csv`:
| band | in-sample | held-out (CI) | optimism | gate |
|---|---|---|---|---|
| nrs 0-3R 26.4 Hz | 0.55 | **0.24** (0.14–0.37) | +0.31 | fail (collapse) |
| nrs 0-3R 8.8 Hz | 0.52 | 0.37 (0.25–0.51) | +0.16 | fail (collapse) |
| mpq 0-3R 83.5 Hz | 0.67 | **0.67** (0.50–0.78) | ≈0 | fail (underpowered) |

The nrs bands' in-sample AUC was masking a forward *reversal* — exactly the
closed-loop failure C2 exists to catch. The mpq band generalizes perfectly forward
(optimism 0) but is one rating short of a CI that excludes chance.

## NOT done / open
- **Not committed**; no PR. Suggest committing this branch and (with the now-green
  full suite) opening the PR to `v3.1.0`.
- C2 is the **last HIGH** audit finding — with it closed, all four HIGH findings
  (C1, C2, C3, C8) are resolved.
- 8.8 Hz temporal regime shift still unexplained (separate thread); note the forward
  result independently flags 8.8 Hz as non-generalizing.
- Forward panel is currently text-only in the sign-off EVIDENCE block + gate. A
  dedicated per-fold forward-AUC trace plot in DeploymentRocPanel was not built
  (the `forward.folds` array is already returned for it).
- RCS08-only frozen PSD→LSB model unchanged; forward-chaining itself is
  participant-agnostic (no frozen asset needed).

## Key files changed
- `BRAVO/modules/Biomarkers/routines/analytics.py` (+`deployment_forward_chaining`)
- `BRAVO/modules/Biomarkers/bravo_service.py` (forward block + gate + caveats in
  `deployment_summary`, forward block in `band_deployment_roc`)
- `BRAVO/modules/Biomarkers/tests/test_analytics.py` (+4 tests, registered in runner)
- `Client/src/views/Reports/ClosedLoopSim/DeploySignoffCard.js` (forward evidence row)
- `Client/build/` regenerated
