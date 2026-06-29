# BRAVO_pain — Session Handoff (2026-06-26 → 2026-06-27)

> Hand this to the next session. Pairs with `MEGA_HANDOFF.md` (full project history) and
> `AUDIT_TRIAGE_v3_decisions.md` (the medium/low audit decision sheet, artifact
> `f3f0bf13-4174-4c60-b40c-ea6411e8ad66`).

## 0. TL;DR — where the repo is right now

- **Repo:** `/Users/pshirvalkar/dev/BRAVO_pain` · GitHub `shirvalkarlab/BRAVO_pain`
- **Branch:** `PS_closedloop_deployment` (off default `v3.1.0`)
- **HEAD:** `abe8a23` — in sync with `origin/PS_closedloop_deployment` (pushed)
- **Test suite:** **196/196 PASS** (in-container, via the bridge)
- **Live server:** OrbStack container, gunicorn `min(nproc,4)`=4 workers + 1 master, serving the latest code (workers recycled after every commit)
- **Live participant:** RCS08, uid `2e3c75c00d7f4f37b53a048d195f11da`

## 1. What this session accomplished

This was an **audit-cleanup** session: working through the 12 deferred "judgment call"
findings from `AUDIT_TRIAGE_medium_low.md`. The session split them into buckets A–D and
implemented B fully + four of the C statistical calls. Four commits landed:

| Commit | Item(s) | Summary | Suite |
|---|---|---|---|
| `ff65277` | Bucket B [17][3-disp][8][23] | Additive honesty: no-look-ahead invariant test, small-sample + bootstrap-count advisories, temporal-validity export block. **No existing number/gate changed.** | 184→187 |
| `8509e96` | [16]+[19] | Moving-block bootstrap CI + design-effect (DEFF) discount on the power readout | 187→190 |
| `2ef0408` | [3] | BCa AUC confidence interval + raise valid-replicate floor 20→100 | 190→193 |
| `abe8a23` | [18] | Per-week threshold-drift diagnostic + deploy-path warning | 193→196 |

### Bucket B — `ff65277` (additive, no number/gate change)
- **[17]** no-look-ahead invariant — `test_prior_no_lookahead_invariant_survives_full_pooled_pipeline` in `test_match_to_pro.py`. Runs the full pooled pipeline in `"prior"` mode and asserts every matched neural window precedes its rating (`dt_min >= 0`, `<= tolerance`).
- **[3]-display** — ROC title shows `N bootstrap replicates` / `CI on N replicates — unstable` when `n_boot_ok < 100`. Uses the existing field; no math change.
- **[8]** small-sample advisory — `deployment_roc` + `auc_power` carry `small_sample` (`n_clusters < SMALL_SAMPLE_CLUSTER_FLOOR=10`) + `small_sample_floor`. Label only.
- **[23]** temporal-validity export — `temporal_validity` block on `deployment_summary` (`forward_validation` / `threshold_drift` / `stim_state_portability`, each defaulting `"not_assessed"`). Flows into the deploy export.

### [16]+[19] — `8509e96` (moving-block bootstrap + design effect)
- **`_block_bootstrap_aucs`** (analytics.py ~1665) — vectorized de-folded tie-aware Mann–Whitney AUC for ALL replicates at once (one mergesort + `np.add.reduceat` segment-sum + `np.add.at` cluster multiplicities). `block_len<=1` = i.i.d. cluster bootstrap; `>1` = circular moving blocks.
- **`_auto_block_len`** (~1636) — block length from the per-cluster rating autocorrelation: returns **1** when ACF lag-1 ≤ 0.1 (uncorrelated → exact i.i.d. reproduction); else `max(ACF-decay-length, n^(1/3))`, capped at `K//3`.
- **DEFF** — `deff = min(5.0, max(1.0, var_block/var_iid))`, computed in `deployment_roc` from block vs i.i.d. bootstrap variance. `=1.0` when `block_len==1`.
- **`auc_power(..., design_effect=1.0)`** (~3034) — discounts effective N by DEFF into Hanley–McNeil; **`design_effect=1.0` is a bit-exact no-op**. Displays RAW class counts; effective (discounted) counts exposed separately.
- Frontend: `LsbPowerPanel.js` annotates the discount when `deff>1`.
- Live RCS08 DEFF ≈ 1.08–1.15 (mild week-to-week autocorrelation).

### [3] — `2ef0408` (BCa CI + raised floor)
- **BCa headline CI** — `_bca_ci` (~1735): bias `z0` from the block bootstrap, acceleration from a vectorized delete-one-cluster jackknife (`_jackknife_cluster_aucs` ~1724, reuses `_weighted_auc_matrix` ~1695). Validated vs `scipy.stats.bootstrap(method='BCa')` to within MC error.
- **Floor 20→100** — `BOOT_CI_VALID_FLOOR=100`; CI suppressed below it. Applied to the deployment ROC, the by-era CI, and the forward held-out CI.
- **C1 GUARD (the critical subtlety)** — BCa's bias term `z0` collided with the audit-C1 de-fold invariant: on a true-null band it pushed the lower CI from 0.497 back up to 0.501, re-creating the "manufactured beats-chance floor" C1 removed. **Resolution (Prasad's call): headline CI stays full BCa, but the de-folded percentile lower bound `auc_lo_defold` is kept as a separate field, and the "beats chance" power gate reads IT, not the BCa bound.** Both `auc_power` call sites in bravo_service.py pass `auc_lo=roc.get("auc_lo_defold", roc.get("auc_lo"))`.
- Frontend: `DeploymentRocPanel.js` names the BCa/block CI on the figure.
- Live RCS08: BCa `[0.30, 0.70]`, guard `[0.33, 0.70]`.

### [18] — `abe8a23` (per-week threshold drift)
- **`threshold_drift_by_week`** (analytics.py ~2232) — buckets matched samples by elapsed week (`_elapsed_week_cluster`), computes each qualifying week's Youden cut-point under the POOLED orientation, runs an **OLS trend test** (`scipy.stats.linregress`) of cut-point vs week index. Flags drift when slope p<0.05.
- Gates: `DRIFT_MIN_SAMPLES_PER_WEEK=6` (+ both classes), `DRIFT_MIN_WEEKS=4`, else `"not_assessed"` (fail-closed).
- Replaces the `temporal_validity.threshold_drift` stub; adds a deploy caveat on `drift_detected`.
- Live RCS08: `stable` under nearest-matching (4 weeks, slope +0.14/wk, p=0.64), `not_assessed` under prior-matching (only 2 weeks qualify).

## 2. What remains (audit backlog)

**Bucket C (2 statistical calls left):**
- **[5]** — move displayed cut-point solve server-side onto the full ROC arrays (displayed operating point can shift slightly). *Mechanical.*
- **[14]** — reconcile clustering granularity: per-rating ROC vs weekly glmer use different independence units. **Has a judgment call — changes which sample-size unit is reported. Decide before implementing.**

**Bucket D (2 feature builds):**
- **[42]** — operating-point chip (rule + sens/spec) atop the LSB panel + LSB annotation on the histogram.
- **[49]** — embed Plotly PNG snapshots of the 4 figures into the deploy export / printed sheet. (Needs the bridge for kaleido — see §3.)

**Low-polish cluster:** [0]/[15]/[22]/[28]/[39]/[43]/[48] — labeling/navigation niceties, batchable.

## 3. Operating environment & gotchas (READ before working)

- **Bridge:** run code in-container via `python3 BRAVO/_agent_bridge/bridge_client.py --cwd /usr/src/BRAVO --timeout N --wait N "..."`. Status: `--status`.
- **Bridge stalls** — the watcher (pid 8, agent_runner) periodically stops responding (heartbeat age climbs, jobs time out). Fix = **restart the OrbStack container**; the sandbox can't reach the docker daemon to do it, so ask the user. It happened twice this session.
- **Preview env:** `rocqa` (plotly 6.8) for HTML/PNG previews — plotly is NOT in the container.
- **Local env:** `bravo_app` (py3.11, sklearn 1.9.0) — good for pure-function verification by importing analytics.py standalone (Django-free). Full Django setup locally is blocked (MySQL backend lives in-container).
- **Plotly PNG export:** use the bridge, NOT kaleido/chromium in the sandbox.
- **Worker recycle after a commit:** `kill -HUP 1` in-container (master re-reads code from disk). VirtioFS bind mount needs `--reload-engine poll` (inotify doesn't propagate).
- **Git identity:** commit with `-c user.name="Prasad Shirvalkar" -c user.email="prasad.shirvalkar@ucsf.edu"`.
- **save_artifacts dedup trap:** it dedups by filename and won't re-read changed content — **use a fresh filename when content changes** (bit us this session: a re-save silently kept stale bytes).
- **edit_file + em-dashes:** files with multi-byte em-dashes can break `old_string` matching; use a Python in-place heredoc patch as fallback.

## 4. Key files & line anchors (current HEAD)

`BRAVO/modules/Biomarkers/routines/analytics.py`:
- constants: `SMALL_SAMPLE_CLUSTER_FLOOR`=10 (l25), `BOOT_CI_VALID_FLOOR`=100 (l32), `DRIFT_MIN_SAMPLES_PER_WEEK`=6 / `DRIFT_MIN_WEEKS`=4 (l2228-2229)
- `_band_feature_from_detail` l1600, `_auto_block_len` l1636, `_block_bootstrap_aucs` l1665, `_weighted_auc_matrix` l1695, `_jackknife_cluster_aucs` l1724, `_bca_ci` l1735
- `deployment_roc` l1770, `_elapsed_week_cluster` l1995, `deployment_roc_by_era` l2061, `threshold_drift_by_week` l2232, `deployment_forward_chaining` l2341, `auc_power` l3034

`BRAVO/modules/Biomarkers/bravo_service.py` (exact lines @ HEAD `abe8a23`):
- `deployment_summary`: `by_era` call l3985, `forward` call l3992, **`drift` call l3999**, temporal_validity block l4391-4414 (`threshold_drift` l4399, slope/p/total/n_weeks l4401-4406, `stim_state_portability` l4407, `forward_validation` l4392), caveats list l4236 (drift caveat appended after the per-era fragility caveat), the two power-gate sites `_gate_auc_lo = roc.get("auc_lo_defold", roc.get("auc_lo"))` at **l3877** and **l4103**
- `band_deployment_roc` (per-panel ROC handler) l3926 region — also reads the same roc dict; ROC nested under key `"roc"`

Frontend `Client/src/views/Reports/ClosedLoopSim/`:
- `DeploymentRocPanel.js` (CI label ~153), `LsbPowerPanel.js` (DEFF annotation), `DeploySignoffCard.js`, `DeploymentVerdictStrip.js`

Tests: `BRAVO/modules/Biomarkers/tests/test_analytics.py` (82 test fns), `test_match_to_pro.py`

## 5. Verification recipe (how this session checked rigor)

- **Standalone import** of analytics.py (Django-free) in `bravo_app` for pure-function checks: build a synthetic `td_detail` dict, call the function, assert.
- **In-container suite:** `python3 _agent_bridge/run_tests.py 2>&1 | grep -E 'PASS=|FAIL'`.
- **Live RCS08:** call `bravo_service.deployment_summary(...)` / `band_deployment_roc(...)` in-container with `Channel=ZERO_TWO_LEFT, CenterHz=20.0, BandWidthHz=5.0, MatchDirection=prior`.
- **BCa** validated against `scipy.stats.bootstrap(method='BCa')`; **block bootstrap** validated to reproduce the old sklearn loop EXACTLY at `block_len=1`; **DEFF=1.0** validated bit-exact no-op.

---

# EXPANDED DETAIL (v2 — deeper reference)

## 6. `deployment_roc` return-dict schema (the contract the frontend + gates read)

Keys touched/added this session (analytics.py l1941-1985). All `auc*` are on the
**oriented** scale (point AUC ≥ 0.5 by construction; the CI is de-folded so its lower bound
can fall honestly below 0.5):

| Key | Meaning | Notes |
|---|---|---|
| `auc` | point AUC, oriented ≥0.5 | optimistic near chance by construction |
| `auc_lo` / `auc_hi` | **headline BCa** 95% CI | `None` when `< BOOT_CI_VALID_FLOOR` valid replicates |
| `auc_lo_defold` / `auc_hi_defold` | **de-folded plain percentile** CI | **the power gate reads `auc_lo_defold`, NOT `auc_lo`** (C1 guard) |
| `auc_lo_iid` / `auc_hi_iid` | i.i.d. (block_len=1) percentile CI | retained for DEFF transparency / regression |
| `ci_interval` | `"BCa"` | |
| `bca_z0` / `bca_a` | BCa bias-correction / acceleration | `None` when CI suppressed |
| `ci_valid_floor` | `100` (`BOOT_CI_VALID_FLOOR`) | |
| `n_boot_ok` | count of class-non-degenerate replicates | drives "unstable CI" tag when `< floor` |
| `block_len` | auto block length (1 = uncorrelated) | from `_auto_block_len` |
| `deff` | design effect `var_block/var_iid`, clamped [1,5] | `1.0` when `block_len==1` |
| `ci_method` | human string naming scheme + BCa + block_len | shown on the ROC figure |
| `small_sample` / `small_sample_floor` | advisory, `n_clusters < 10` | label only |
| `operating_point` | Youden-J cut-point `{threshold, sensitivity, specificity, rule:"ge", ...}` | |
| `flip` | whether the score was negated to orient | |

**Why the C1 guard matters (do NOT undo this):** BCa's `z0` re-centers the interval on the
orientation-inflated point AUC. Near chance, the de-fold makes that point estimate
optimistic-by-construction (`max(raw, 1−raw)`), so `z0` reads the orientation selection as
estimator bias and "corrects" it upward — which re-creates exactly the manufactured
beats-chance floor audit C1 was built to remove. The fix is to let the displayed CI be BCa
but make the **safety gate** read the de-folded percentile bound. If you ever change the CI
math, re-verify `test_deployment_roc_bootstrap_defolded_null_ci_drops_below_chance` still
asserts on `auc_lo_defold`.

## 7. `threshold_drift_by_week` return-dict schema (analytics.py l2232)

`{available, status, n_weeks_qualifying, pooled_threshold, slope_per_week, slope_p,
total_drift, week_span, drift_flag, weekly:[{week, threshold, n, prevalence}], note}`

- `status` ∈ `{"stable", "drift_detected", "not_assessed"}`
- `drift_flag = (slope_p < 0.05 and finite)` — `drift_detected` iff flagged
- weekly cut-points are Youden-J on the oriented log-power scale, all under the **pooled**
  orientation (so they share one signed scale)
- gates: `DRIFT_MIN_SAMPLES_PER_WEEK=6` (+ both classes per week) and `DRIFT_MIN_WEEKS=4`;
  below either → `not_assessed` with `weekly` still populated for inspection

`temporal_validity` (bravo_service.py l4391) now carries: `threshold_drift` (the status),
`threshold_drift_slope_per_week`, `threshold_drift_p`, `threshold_drift_total`,
`threshold_drift_n_weeks`, plus the pre-existing `forward_validation` and
`stim_state_portability`. **Note the semantic split:** `stim_state_portability` = robustness
to stim STATE (per-era, audit C3); `threshold_drift` = robustness over CALENDAR time (audit
[18]). They are different failure modes — keep them distinct.

## 8. Tests added this session (12 new functions)

`test_analytics.py`:
- Bucket B: `test_roc_small_sample_advisory_is_label_only` (l1771),
  `test_deployment_summary_carries_temporal_validity_block` (l1824, live-RCS08, skips if absent)
- [16]+[19]: `test_block_bootstrap_block_len_1_reproduces_iid_loop` (l1849),
  `test_auto_block_len_degrades_to_iid_when_uncorrelated` (l1887),
  `test_auc_power_design_effect_1_is_exact_noop_and_discount_is_monotone` (l1899)
- [3]: `test_deployment_roc_bca_fields_and_defold_guard_present` (l1918),
  `test_bca_matches_scipy_on_iid_skewed_statistic` (l1945),
  `test_jackknife_cluster_aucs_matches_manual_delete_one` (l1966)
- [18]: `test_threshold_drift_stationary_is_stable` (l2009),
  `test_threshold_drift_detects_planted_trend` (l2020),
  `test_threshold_drift_sparse_record_not_assessed` (l2031);
  helper `_drift_detail(E, weeks, drift_per_week, seed)` plants a week-trend
- Updated: `test_deployment_roc_bootstrap_defolded_null_ci_drops_below_chance` now asserts the
  C1 property on `auc_lo_defold` (the guard), and `ci_interval == "BCa"`

`test_match_to_pro.py`:
- [17]: `test_prior_no_lookahead_invariant_survives_full_pooled_pipeline` (l122)

Standalone verification scripts written to `/tmp` this session (NOT committed, but the
patterns are reusable): `/tmp/bca_validate.py` (BCa vs scipy), `/tmp/verify_bca.py`
(jackknife + floor), `/tmp/verify_drift.py` (3 drift regimes), `/tmp/verify_deff2.py`
(DEFF no-op + block reproduction), `/tmp/vec_auc_check.py` (weighted AUC vs sklearn,
max err 1.1e-16), `/tmp/block_boot_proto.py` (block bootstrap prototype).

## 9. Decision log — choices Prasad made this session (don't re-litigate without cause)

- **Next-task pick:** do the 12 deferred judgment calls (not design-effect-only).
- **Order:** Bucket B fully first, then C one-by-one. Then "[3] then [18]".
- **[19] approach:** block bootstrap (ties to [16]) rather than a standalone DEFF formula.
- **Block length:** auto from autocorrelation (degrades to 1 when uncorrelated).
- **DEFF coupling:** discount effective-N by DEFF; **display the raw class counts**, expose
  discounted counts separately.
- **[3] BCa conflict:** full BCa as the headline CI, de-folded percentile as the C1 guard the
  gate reads (option 3 of 3 offered).
- **[18] drift metric:** trend test (OLS slope) on weekly cut-points — not spread-vs-tolerance.
- **[18] week gate:** require both classes + ≥6 samples/week; ≥4 qualifying weeks else
  `not_assessed`.

## 10. Prior-session carryover still in force (from MEGA_HANDOFF / earlier this session)

- **PR #8** merged into `v3.1.0` earlier (merge commit `a191b758…`); `v3.1.0` advanced
  `e57a7078..a191b758`. The R thread-safety lock (`_R_GLOBAL_LOCK`, RLock) protects every
  pymer4/lme4 fit — embedded R is single-threaded; concurrent fits corrupt it.
- **Perf:** threshold sweep vectorized (24.8×, `97d4e86`); spectral CV intentionally defaults
  SERIAL (`_spectral_cv_threads()` returns 1 — GIL/BLAS-bound, no wall-clock gain). Recompute
  ~47s end-to-end; user accepted ("leave it").
- **Spectral feature importance:** 8–30 Hz are CENTER frequencies; full 0–100 Hz scan shows
  2.5–97.5 Hz (5 Hz band integral). `adaptive_valid` keys on the CENTER frequency being in
  the validated range. `LSB_VALIDATED_HZ_LO=7.8`, `HI=28.3`.
- **Biomarker state persistence:** `biomarkerStateStore.js` (localStorage controls +
  in-memory LRU heap with memory guard), `2fad81b`.
- **Timeline legend:** right-anchored (x:1.0, xanchor:right), Hz color-key deleted (`3525c0a`).
- **Modeled-LSB fallback:** shared `_modeled_lsb_threshold_estimate`; flagged `estimated=True`
  so the UI never renders a modeled value as measured (audit C8 fail-closed).
- **High-gamma 55.5 Hz: CLOSED (not blocked).** Impedance `c=1.02` term: REJECTED
  (`a9c3a01`, pseudoreplication).

## 11. Conventions / constants worth keeping handy

- **Live RCS08 deployment test params:** `Channel=ZERO_TWO_LEFT, CenterHz=20.0,
  BandWidthHz=5.0, Metric=nrs, Strategy=tertile, MatchDirection=prior`. Note: `prior` yields
  only 2 drift-qualifying weeks; `nearest` yields 4 — use `nearest` to exercise the drift path.
- **PRO-match sign convention:** in `"prior"` mode `dt_min >= 0` (PSD precedes rating).
  `build_pooled_detail_from_matrix` defaults: `tolerance_min=60.0, min_per_group=3,
  match_direction="pro_first", max_per_rating=3, refractory_min=2.0`.
- **LSB constants:** `k=269` (LSB_PER_UV2_VALIDATED), `sigma≈1.26`, `ADC_NV_PER_LSB=146.0`,
  `UV2_PER_LSB_VALIDATED=0.00372`, `CONVERSION_FFT_SIZE=256`.
- **Badge colors:** green `#0a7f3f`, amber `#B17500`, fail `#9A3324`, grey `#6c757d`.
- **Skills used:** `ps-statsmodels` (analysis rigor), `code-review` (audits), `ps-plotly` +
  `ps-scientific-visualization` (frontend figures), `bravo-timeline-layout` (timeline).

## 12. Concrete starting points for the next items

- **[5] server-side cut-point:** the Youden operating point is already computed in
  `deployment_roc` (`operating_point`) and in `threshold_drift_by_week._youden_cut`. The task
  is to make the DISPLAYED cut-point (currently solved client-side in `DeploymentRocPanel.js`
  via the cut-point rule selector, `CUTPOINT_TRACE=2`) read the server's full-ROC-array solve
  instead, so it can't drift from the backend. Mechanical; expect the displayed operating
  point to shift slightly.
- **[14] clustering granularity:** the open question is which independence unit to report —
  the per-rating ROC uses `n_clusters` (post-binarization independent ratings), while the
  offline weekly glmer uses elapsed-week random intercepts (`_elapsed_week_cluster`). These
  give different N. **Decide the reported unit with Prasad before coding.**
- **[42] LSB operating-point chip:** `LsbPowerPanel.js` already has the panel; add a chip
  reading `roc.operating_point` (rule + sens/spec) and annotate the histogram with the LSB
  that the cut-point maps to (use `lsb_from_uv2` / the Phase-C cut-point→percentile→LSB path
  in `deployment_summary`).
- **[49] embed figure PNGs:** export the 4 Plotly figures to PNG **via the bridge** (kaleido
  in-container, NOT sandbox), base64-embed into the deploy export JSON / printed sheet
  (`deployPrint.css` already scopes the print view).
