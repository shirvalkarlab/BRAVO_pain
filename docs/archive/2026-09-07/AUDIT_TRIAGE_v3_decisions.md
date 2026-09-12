# Audit medium/low — re-triage of the 12 deferred judgment calls (2026-06-26)

Re-checked the 12 "Bucket B" judgment calls from `AUDIT_TRIAGE_medium_low.md` against the
CURRENT tree (HEAD `ae3538e`). Several were resolved by fixes that landed AFTER the triage was
written. The genuinely-open set is now smaller and splits three ways.

## A. Already resolved since the triage (no action — verified at file:line)

| ID | Was | Now resolved by | Verified |
|---|---|---|---|
| [9]  | verdict on raw auc_spread | `portable_by_ci` (CI-overlap + no confident reversal + band×era LRT); spread now descriptive only | analytics.py:1979-1988 |
| [21] | verdict on raw cutpoint_spread | same C3 fix — descriptive only | analytics.py:1948,1985 |
| [10] | per-era n_boot_ok not reported | exposed per era | analytics.py:1931 |
| [20] | no genuine temporal split | `deployment_forward_chaining` = expanding-window weekly folds (C2) | analytics.py:2003,2049 |
| [51] | no print stylesheet | `deployPrint.css` shipped this session | ClosedLoopSim/deployPrint.css |

## B. Safe additive — increase honesty, change NO existing number or gate (recommend: implement)

| ID | Sev | Change | Why safe |
|---|---|---|---|
| [17] | med | Unit-test invariant: with MatchDirection="prior" every matched neural window END < rating time (no look-ahead / no leakage) | Test only; pins a deploy-critical property; no runtime change |
| [3]-disp | med | Annotate the ROC CI with its valid-replicate count and tag "wide/unstable CI" when n_boot_ok is low | Label only; does NOT change the CI math or the floor |
| [8] | low | Tag power/AUC readouts "small-sample, approximate" below a cluster floor (~10) | Label only; no gate change |
| [23] | low | Add temporal-validity fields to the deploy export schema (forward_validation / threshold_drift, "not assessed" default) | Additive fields; carries existing forward-chaining status |

## C. Changes a reported number / uncertainty / gate — NEEDS PRASAD'S CALL

| ID | Sev | Proposed change | Effect on a clinician number |
|---|---|---|---|
| [3]-floor | med | Raise valid-replicate floor 20→100 and/or switch percentile-CI → BCa | CI widths change; some CIs suppressed |
| [16] | med | Block (≈1-week) bootstrap instead of rating-cluster bootstrap | CIs widen (honestly) — serial autocorrelation |
| [19] | med | Discount effective-N by a design-effect factor in the power-vs-N curve | "ratings needed" rises; power falls |
| [18] | med | Per-week LSB threshold-drift diagnostic + tolerance warning | New warning can appear on the deploy path |
| [5]  | low | Move displayed cut-point solve server-side on full ROC arrays | Displayed operating point can shift slightly |
| [14] | med | Reconcile clustering granularity (per-rating ROC vs weekly glmer) | Changes which independence unit is reported |

## D. Larger feature builds — priority call (medium effort each)

| ID | Sev | Build |
|---|---|---|
| [42] | med | Echo operating point (rule + sens/spec) as a chip atop the LSB panel + annotate histogram with resulting LSB |
| [49] | med | Embed Plotly PNG snapshots of the 4 figures into the deploy export / printed sheet |

Plus the low-value polish cluster [0]/[15]/[22]/[28]/[39]/[43]/[48] — labeling/navigation niceties, batch later.


---

## STATUS UPDATE 2026-06-26 — Bucket B COMPLETE (commit ff65277, 187/187 tests)

- **[17]** no-look-ahead invariant — `test_prior_no_lookahead_invariant_survives_full_pooled_pipeline` (test only).
- **[3]-display** — ROC title now shows `N bootstrap replicates` / `CI on N replicates — unstable` when <100 (uses existing `n_boot_ok`; no math change).
- **[8]** — `small_sample` + `small_sample_floor` advisory on `deployment_roc` and `auc_power` (floor=`SMALL_SAMPLE_CLUSTER_FLOOR`=10); ROC title tags `small sample — approximate`. Label only; equivalence-tested.
- **[23]** — `temporal_validity` block on `deployment_summary` (forward_validation / threshold_drift='not_assessed' / stim_state_portability), each defaulting to 'not_assessed'. Flows into the deploy export. Verified live on RCS08.

**Remaining: Bucket C (6 statistical calls) + Bucket D (2 feature builds).** Next: walk Bucket C one-by-one, starting with [19] design-effect discount.


---

## STATUS UPDATE 2026-06-27 — Bucket C: [16]+[19], [3], [18] COMPLETE

- **[16]+[19]** (commit `8509e96`, 190/190) — **moving-block bootstrap + design-effect.** Vectorized de-folded tie-aware AUC engine (`_block_bootstrap_aucs`) replaces the per-replicate sklearn loop; auto block length (`_auto_block_len`, =1 when ratings uncorrelated → exact i.i.d. reproduction); `DEFF = var_block/var_iid` (clamped [1,5]) discounts effective-N in `auc_power` (`design_effect=1.0` is a bit-exact no-op). LsbPowerPanel annotates the discount. Live RCS08 DEFF≈1.08–1.15.
- **[3]** (commit `2ef0408`, 193/193) — **BCa CI + raised valid-replicate floor.** Headline ROC CI is now bias-corrected & accelerated (z0 from the block bootstrap, acceleration from a vectorized delete-one-cluster jackknife; validated vs `scipy.stats.bootstrap` BCa to within MC error). Floor raised 20→100 (`BOOT_CI_VALID_FLOOR`), applied to the ROC, by-era, and forward held-out CIs; below it the CI is suppressed. **C1 guard:** the de-folded percentile lower bound (`auc_lo_defold`) is kept separate and the "beats chance" power gate reads IT, not the BCa bound — BCa's bias term would otherwise re-floor a true-null band at ~0.5. ROC figure names the BCa/block CI.
- **[18]** (commit `abe8a23`, 196/196) — **per-week threshold-drift diagnostic.** New `threshold_drift_by_week`: buckets matched samples by elapsed week, computes each qualifying week's Youden cut-point under the pooled orientation, OLS trend test of cut-point vs week index; flags drift when the slope is significantly non-zero. Gate: ≥6 samples/week + both classes, ≥4 weeks else `not_assessed`. Replaces the `temporal_validity.threshold_drift` stub + adds a deploy caveat. Live RCS08: `stable` (nearest, 4 weeks) / `not_assessed` (prior, 2 weeks).

**Remaining: Bucket C [5] (server-side cut-point) + [14] (clustering-granularity reconciliation); Bucket D [42]/[49]; low-polish cluster [0,15,22,28,39,43,48].**
