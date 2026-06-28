# Session handoff — ClosedLoopSim "CL fixes" (four-lens audit, Wave 1 + Wave 2)

## What shipped
**PR #5 — MERGED** into `v3.1.0` as squash commit `c50be37`
(https://github.com/shirvalkarlab/BRAVO_pain/pull/5). Branch `PS_biomarker_clfixes`
created from the merged base `52010ec`; deleted after merge.
origin/v3.1.0 HEAD is now `c50be37` (previously `52010ec`).

Git identity reused via env vars: `Prasad Shirvalkar <prasad.shirvalkar@ucsf.edu>`
(`.git/config` is unwritable — the "Operation not permitted" + keychain `-50`
warnings on every git op are documented-harmless; do not chase them).

## Scope implemented (user chose "Wave 1 + Wave 2")
Convergent findings C1, C3, C5, C6, C7, C8 from the four-lens audit
(`closedloop_audit_report.md`, artifact version `e3a12136-e0e1-4fff-b95f-baa42d0a0a46`).
**Deferred (NOT done): C2** (forward-chaining / out-of-sample validation) and
**C10** (recommended-vs-programmed delta, ramp guidance, figure embedding, modebar).
**C9** (hardcoded cut-point trace index `[2]` in DeploymentRocPanel) is Wave-3, NOT done.

### Backend (BRAVO/modules/Biomarkers/)
- **C1** `analytics.deployment_roc`: bootstrap appends `float(ab)` (fixed orientation),
  not `max(ab,1-ab)`. De-folds the CI so the lower bound can fall below 0.5 on a null
  band. Added `ci_method` key + disclosure note.
- **C3** `analytics.deployment_roc_by_era`: `_roc_for(mask, fixed_flip=None)` — pooled
  computed FIRST (fixed_flip=None, orients to own data), eras reuse `pooled_flip`. Era
  AUC is signed (`metrics.roc_auc_score(y, use)`, no fold) + `reversed` flag. Per-era
  bootstrap also de-folded. New return keys: `any_reversed`, `ci_overlaps_pooled`,
  `portable_by_ci` (>=2 estimable eras, all CIs overlap pooled, no reversal), `n_boot_ok`.
- **C3 wiring** `bravo_service.band_deployment_roc_by_era`: attaches
  `by_era["stim_lrt"] = {available, lrt_p, stim_stable}` from `core["stim"]`.
- **C8** `bravo_service.deployment_summary`: `_gate(key,label,state,detail,necessary)`
  helper; tri-state `state` in {pass,fail,indeterminate}; `pass` bool == state=="pass".
  Stim-stable gate ABSTAINS (indeterminate) when LRT unavailable (was fail-open green).
  Necessary gates: validated, adaptive_band, deployable_threshold. New return keys:
  `ready_to_program` (all necessary pass), `n_gates_indeterminate`, `n_necessary`,
  `n_necessary_passed`.

### Frontend (Client/src/views/Reports/ClosedLoopSim/)
- **palette.js**: added `warnText` (#8A6100, 5.5:1 on white), `onWarn` (#1A1A1A, 7.7:1
  on orange), `indeterminate` (gray), `painHighOutline`. Rule: orange `warn` for
  FILLS/AREA only; `warnText` for warn TEXT; `onWarn` for text ON an orange fill.
- **EraRefitPanel.js**: verdict keys on `any_reversed` / band×era LRT / `portable_by_ci`
  (not raw auc_spread). Reversed eras = X marker in `fail`. Non-estimable glyph moved
  OFF the chance line to a left-margin "n/a (insufficient samples)" annotation. Pooled-CI
  band labeled + dotted edges. x-range floored at min era CI (shows sub-0.5).
- **LsbPowerPanel.js**: needed-N marker linearly interpolated onto the curve at
  n_ratings_needed (was y=tgt*100). Static now/need annotations. Fixed incomplete
  `border:'1px solid '` -> warnBorder. µV²/LSB confidence tri-state colored. warn text
  -> warnText.
- **DeploymentRocPanel.js**: ROC title CI label -> "95% clustered-bootstrap CI".
  pain-high histogram is a transparent-fill 1.6px OUTLINE (was 0.62-opacity fill);
  pain-low 0.55 fill. Degenerate-marker annotation uses onWarn dark text. Degenerate
  warn box text -> warnText.
- **DeploySignoffCard.js**: GateRow tri-state (pass=check_circle/pass, fail=cancel/fail,
  indeterminate=help/gray-neutral); REQUIRED + NOT TESTED inline tags. Headline driven
  by `ready_to_program` (falls back to passed-count for old payloads), warnText. AUC CI
  labeled clustered-bootstrap; power line guarded when sufficient.
- **index.js**: `verdictTextColor()` -> onWarn on the stim-dependent (orange) badge,
  white otherwise. suggested-mode warn text -> warnText.

### Tests (BRAVO/modules/Biomarkers/tests/test_analytics.py)
4 new, registered in the `__main__` runner:
- `test_deployment_roc_bootstrap_defolded_null_ci_drops_below_chance`
- `test_deployment_roc_by_era_pooled_orientation_surfaces_reversal`
  (helper `_era_split_detail(E,beta,high_sign,seed)` plants a reversal with high_sign=-1)
- `test_deployment_roc_by_era_portable_when_eras_agree`
- `test_deployment_summary_gate_states_and_necessary_blocking` (pure gate-arithmetic)
All 4 pass + existing deployment ROC/by-era/power suite green.

## Validation done
- Local run: 43/47 pass. The 4 failures are PRE-EXISTING and OUT OF SCOPE (confirmed
  outside my diff): `numpy.trapz` removed in the env's numpy; 3 PRO-timezone tests need
  Django settings (`test_normalize_pro_times_idempotent_and_safe`,
  `test_pain_scores_emit_utc_t_epoch`, `test_pain_series_epochs_match_pro_match_arrays`).
- CRA production build compiles clean (exit 0). Build command:
  `cd Client && export npm_config_cache=/tmp/npmcache && GENERATE_SOURCEMAP=false
  NODE_OPTIONS=--openssl-legacy-provider CI=false npx --no-install react-scripts build`.
  Repo COMMITS `Client/build/` alongside source (precedent: e32828f, 52010ec) — the
  regenerated bundle was committed in PR #5.
- Figures verified by rendering the corrected backend on the real device bundle
  (`phase0_bundle.npz`, 4722x6x101). Real nrs@10Hz on ZERO_TWO_LEFT: pooled AUC 0.779
  CI (0.599,0.921), all eras agree -> portable_by_ci=True. Synthetic reversal: HIGH era
  AUC 0.000 reversed=True -> any_reversed=True portable_by_ci=False (old code folded -> 1.00).

## Environment gotchas (carry forward)
- **bravo_app has pandas 3.0.3 which DROPPED `pd.Series.view`** -> the untouched
  `_assign_stim_eras` (analytics.py:1655) and `_elapsed_week_cluster` use `t_dt.view("int64")`
  and raise AttributeError locally. The LIVE CONTAINER still has older pandas where `.view`
  works, so SOURCE IS CORRECT — do not "fix" it without checking the container's pandas.
  For LOCAL testing only, monkeypatch (source untouched), and it MUST be ns-resolution to
  match the container (pandas 3.0 datetime64 is [us], so a naive astype('int64') gives
  microseconds and mis-assigns eras):
    pd.Series.view = lambda self, dtype=None: (
        pd.Series(self.values.astype('datetime64[ns]').astype('int64'), index=self.index)
        if np.issubdtype(self.dtype, np.datetime64) else self.astype('int64'))
- Run backend tests from `BRAVO/` with `sys.path.insert(0, os.path.abspath('modules'))`
  AND `os.path.abspath('.')` (some tests import `modules.Biomarkers...`, others `Biomarkers...`).
- Envs: `bravo_app` (py3.11.15, has requests, matches container libs), `rocqa` (py3.13.14,
  plotly 6.8 + kaleido 1.3 — kaleido Chrome export BROKEN, use write_html or matplotlib),
  `python` (read-only). No conda/gh/PyGithub on bash PATH; GitHub via urllib + GITHUB_TOKEN
  (Bearer, API version 2022-11-28). Self-approval blocked -> post issue comment then
  PUT /pulls/{n}/merge (squash).

## Hard constraint (still in force)
ClosedLoopSim Plotly panels draw ONCE via `Plotly.react` and mutate via
`Plotly.restyle(...,[traceIndex])` / `Plotly.relayout` — NEVER rebuild a figure on
interaction (commit 255e0ef fixed the reset bug). All Wave-2 edits preserved this.

## Preview artifacts (this session)
- `clfix_montage.png` version `1d21b75f-71c6-462d-a5b2-69d61d7d2f3e` — 4-panel before/after.
- `clfix_preview.html` version `c73fd676-6b03-4498-bddc-f9f59bc2bed0` — interactive Plotly,
  mirrors the panels from the corrected backend.

## Suggested next steps
- C9: single-source the cut-point trace index in DeploymentRocPanel (`const CUTPOINT_TRACE=2`).
- C10 actionability: recommended-vs-programmed delta, ramp guidance.
- C2: forward-chaining / out-of-sample validation (the one HIGH finding still open).
- Optional: properly fix the pandas `.view` -> `.astype` at analytics.py ~1655 and
  `_elapsed_week_cluster`, but ONLY after confirming the live container's pandas version.
