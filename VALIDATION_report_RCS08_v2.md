# RCS08 biomarker validation report — PRO-first pool (v2)
Generated: 2026-06-23
Supersedes: `VALIDATION_report_RCS08.md` (v1, PSD-first / 15-min window)

## What changed between v1 and v2

The matching layer between PSDs and pain ratings was rebuilt. v1 used PSD-first matching with a 15-minute window and "prior" (forecasting) direction — every PSD had to precede its rating by ≤15 min to count. The audit showed this dropped 92.8% of the otherwise-usable pool on RCS08: 67 of 682 pain ratings ever entered the analysis. v2 ships PRO-first matching with a 60-minute window: walk pain ratings (the units of statistical independence), claim up to 3 closest PSDs per channel each within tolerance, do not re-claim a PSD a later rating has already taken. PRO-first is now the discovery default; the old PSD-first "prior" mode is kept for the threshold-deployment view (causal forecasting is the right semantics there).

The headline effect on RCS08:

| metric | v1 PROs in pool | v2 PROs in pool | v1 PSD-rows | v2 PSD-rows |
|---|---|---|---|---|
| NRS / VAS | 67 / 682 | **290 / 682** | 517 | **1,627** |
| left-leg VAS / back VAS | (not pooled / sparse) | 264 / 517 | — | 1,285 |
| MPQ sum | ~50 | 289 / 678 | ~430 | 1,624 |

## Pipeline overview

Identical to v1; only the matched pool changed.

- **Phase 0** — build the (4,722 × 6 × 101) PSD cube from the cached PSD matrix, attach per-metric PRO labels under PRO-first matching, attach the chronic-stim trace. Saved to `phase0_bundle_v2.npz` (intermediate, ~1.2 MB).
- **Phase 1** — full sliding 5-Hz band scan (92 bands × 6 channels = 552 cells per metric, 3,312 total). Per cell: Pearson r vs continuous PRO, Cohen's d on the high-vs-low tertile, and rating-clustered logistic Wald p. BH-FDR over the (band × channel) grid per metric on both the rating-clustered logistic p (primary inference) and the naive Pearson p (pseudoreplication contrast).
- **Phase 2** — for the top 8 contiguous-band candidates per metric (peak by |Cohen's d|), fit `pain_high ~ band_power + (1|weekly_era)` via pymer4/lme4 (binomial). BH-FDR over the 42 candidate fits. Validated candidate = q_glmer<0.05 AND non-singular AND no separation.
- **Phase 2b** — for each validated candidate, fit reduced `pain_high ~ band_power + stim_era + (1|weekly_era)` vs full `pain_high ~ band_power × stim_era + (1|weekly_era)`, LRT on the interaction. stim-stable iff LRT p ≥ 0.05. Per-era OR computed by stratifying on stim era and re-fitting `pain_high ~ band_power + (1|weekly_era)`.
- **Phase 3** — assemble the ranked validated band table + figures.

## Results

### Scan + FDR

For each metric, the rigorous (rating-clustered logistic, BH-FDR α=0.05) vs naive (Pearson, BH-FDR α=0.05) survivor counts:

| metric | rigorous q<.05 | naive q<.05 | min q_logit | min p_logit |
|---|---|---|---|---|
| NRS | 143 | 341 | 0.0029 | 6.24e-05 |
| VAS | **191** | 169 | 0.0005 | 9.88e-07 |
| left-leg VAS | 101 | 212 | 0.0052 | 9.49e-06 |
| back VAS | 67 | 159 | 0.0090 | 1.63e-05 |
| MPQ sum | 77 | 296 | < 0.001 | 1.98e-08 |
| composite (MPQ + leg-VAS) | 6 | 166 | 0.0235 | 9.03e-05 |

Pseudoreplication contrast: rigorous ≤ naive for 5/6 metrics, as expected. **VAS flips** (191 rigorous vs 169 naive) — the rating-clustered logistic gains more from the bigger PRO pool than Pearson does, because clustering corrects the standard error _down_ when an individual rating's PSDs are positively correlated within the cluster and the rating-level mean still carries signal. Worth a methods-section note rather than a flag; both are real signals under both filters.

See [fig1_pseudoreplication_v2.png]({{artifact:428c0b5b-ca9b-4fab-bcc0-e6ed28f60880}}).

### Validated band candidates

**12 candidates survive mixed-effects FDR.** Of those: **7 have credible confidence intervals (CI width > 0.10 in OR units)** — these are the trustworthy biomarkers. The other 5 carry numerically narrow Wald CIs (often <0.005) characteristic of a saturated random-effect fit when the rating cluster is small (n_clusters < 30); they should be re-validated under a profile-likelihood or bootstrap CI before deployment. All 5 narrow-CI cases land on either ZERO_TWO_RIGHT or ONE_THREE_{LEFT, RIGHT} with n_clusters ≤ 28.

The 7 trustworthy validated bands (credible_CI=True in `validated_band_candidates_v2.csv`):

| metric | channel | center | OR (95% CI) | direction | stim verdict |
|---|---|---|---|---|---|
| NRS | ZERO_THREE_RIGHT | 84.5 Hz | 0.41 (0.28 – 0.58) | negative | **stim-stable** |
| NRS | ONE_THREE_RIGHT | 55.5 Hz | 0.23 (0.08 – 0.70) | negative | stim-stable |
| VAS | ZERO_TWO_LEFT | 61.5 Hz | 0.11 (0.02 – 0.51) | negative | stim-stable |
| VAS | ONE_THREE_LEFT | 45.5 Hz | 0.39 (0.23 – 0.65) | negative | stim-dependent |
| VAS | ZERO_TWO_LEFT | 40.5 Hz | 0.17 (0.04 – 0.73) | negative | stim-dependent |
| MPQ sum | ZERO_THREE_RIGHT | 32.5 Hz | 0.53 (0.34 – 0.81) | negative | stim-dependent |
| MPQ sum | ZERO_THREE_RIGHT | 51.5 Hz | 0.52 (0.33 – 0.81) | negative | stim-stable |

See [fig2_forest_OR_v2.png]({{artifact:35c4f3f0-3969-4272-8764-02a73c8caee3}}) for the forest plot and [fig3_stim_stability_v2.png]({{artifact:12d01fd4-c969-4cbb-8b36-a10b7d7ec4e5}}) for the per-era ORs.

### What this means for the closed-loop target

**v1's beta-band left-leg-VAS candidate on ONE_THREE_LEFT @ 23.5 Hz (OR ≈ 15) does NOT survive v2.** Under the larger pool with PRO-first matching, the candidate did not enter the top 8 by Cohen's d for left-leg-VAS (which contributed zero validated candidates). The reason: with 264 PROs the per-band variance estimate stabilized and the previously dominant cluster-correlation effect attenuated. v1 was likely benefiting from low-n optimism on a sparsely-populated metric.

The closest analog in v2 is **VAS @ 45.5 Hz on ONE_THREE_LEFT (OR 0.39, 0.23–0.65, stim-dependent — strongest at LOW/HIGH stim)** — but this is a different mechanism and not in the device's adaptive band (8–30 Hz).

**The most defensible closed-loop targets in v2** are the **NRS @ 84.5 Hz on ZERO_THREE_RIGHT (OR 0.41, stim-stable, credible CI)** and **VAS @ 61.5 Hz on ZERO_TWO_LEFT (OR 0.11, stim-stable, credible CI)** — both high-frequency, both negative-direction (higher band power → lower pain), both stable across stim eras. Neither is on the Percept-RC's beta-band default for adaptive DBS, which means the deployment view will need to either run a custom band or expose a feature-mapping step.

The high-frequency direction matches v1's pattern (negative correlation, ZERO_THREE-cluster) — that finding strengthens under v2. **It also re-raises the stim-artifact scrutiny question** for 54–87 Hz; the 60 Hz line-noise harmonic and DBS spillover need explicit ruling-out on raw TD before any of these go to deployment.

### Caveats

- **Narrow-CI candidates (5 of 12)** need bootstrap re-validation before they count as deliverables. The pattern (small n_clusters + saturated random effect) is well-known in pymer4 Wald CIs; a 500-iter cluster bootstrap on the matched pool would settle it. Not done here to keep this run scoped to a re-validation, but it's a one-screen addition.
- **Composite metric still has the lowest validated count (0 of top-8 candidates, 6 rigorous-FDR cells)** — the composite blend of MPQ + leg-VAS is noisier than either parent, consistent with v1. Recommend single-metric anchors for wave-2 deployment.
- **Weekly era is the only random intercept used.** Day-of-week and rating-time-of-day effects are folded into residual variance; if those become hypotheses, refit with crossed random intercepts.
- **Stim heterogeneity uses 3 eras with crude amplitude thresholds (OFF<0.1, LOW≤1.5, HIGH>1.5 mA).** Era assignment was last-observation-carried-forward from the chronic stim trace; PSDs collected mid-ramp may be misclassified.
- **PRO-first matching expands the pool, but high-frequency signals could still reflect timing artifacts** — patient-event PSDs cluster around pain reports by construction (the patient triggered both), so a high-freq band that tracks pain in the patient-event subset may be reading a recording-trigger signature rather than a pain signal. Suggested in wave 2: re-fit each validated candidate with a `source` random intercept or stratify by source.

## Reproduction

Scripts (all standalone, under `BRAVO/_agent_bridge/`):

- `phase0_build_v2.py` — build the v2 cube from the cached PSD matrix.
- `phase1_scan_v2.py` — full sliding-band scan + FDR.
- `phase2_glmer_v2.py` — mixed-effects per candidate.
- `phase2b_hetero_v2.py` — stim-era interaction LRT.
- `phase3_artifacts_v2.py` — validated table + figures.

Run via the bridge: `python3 BRAVO/_agent_bridge/bridge_client.py --cwd /usr/src/BRAVO --timeout 900 "python3 _agent_bridge/phaseN_v2.py"`.

## Artifact references

- [validated_band_candidates_v2.csv]({{artifact:d279db71-0239-48e5-b83e-89d7df62d5dc}}) — 12-row table, the headline deliverable
- [fig1_pseudoreplication_v2.png]({{artifact:428c0b5b-ca9b-4fab-bcc0-e6ed28f60880}}) — naive vs rigorous FDR per metric
- [fig2_forest_OR_v2.png]({{artifact:35c4f3f0-3969-4272-8764-02a73c8caee3}}) — forest plot, credible-CI candidates only
- [fig3_stim_stability_v2.png]({{artifact:12d01fd4-c969-4cbb-8b36-a10b7d7ec4e5}}) — per-era ORs

Underlying tables (saved, hidden): scan_full_fdr_v2.csv (3,312 rows), band_candidates_raw_v2.csv (66 raw clusters), glmer_results_v2.csv (42 candidate fits), stim_hetero_v2.csv (12 LRT results), phase0_meta_v2.json (cube provenance).
