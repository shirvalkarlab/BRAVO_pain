# Session handoff — Audit items [5] + [42] (2026-06-28)

**Branch:** `PS_closedloop_deployment` · **Suite: 253/253 PASS** (bridge `run_tests.py`) · frontend rebuilt.

This session: (1) committed + pushed the prior Bug 1–4 changeset (commit `f6849c4`), (2) added a
commit+push rule to the `bravo-session-rules` skill (Rule 4 replaces the old no-commits rule), then
implemented two audit items in the Closed-Loop deployment view.

## [5] — server-side cut-point on the FULL ROC arrays (Bucket C, low)

**Root cause:** `analytics.deployment_roc` computed its Youden `operating_point` on the full arrays
but then **downsampled** `fpr/tpr/thr` to `max_points` for the payload. `DeploymentRocPanel.js`
(`solveCutpoint`) re-solved the operating point LIVE in the browser **on those downsampled arrays**,
so the displayed/propagated cut-point (incl. the deploy-default Youden point lifted to Phases C–E)
could drift slightly from the backend's exact full-array optimum.

**Fix (backend, `analytics.py`):**
- New module-level `_solve_roc_operating_point(fpr, tpr, thr_device, rule, prevalence, cost_ratio=1.0)`
  — the same youden / f1 / cost-tangent selection the frontend ran, but on the full arrays. Skips
  the +inf sentinel; strictly-greater keeps the first maximizer (ties never flip); carries the same
  degeneracy guard as the UI.
- `deployment_roc` now ships `operating_points = {youden, f1, cost:[{log_cost, cost_ratio, ...}]}`
  solved BEFORE the downsample. The `cost` grid spans the UI slider's log2 range (−3..3, step 0.25 →
  25 points). The legacy `operating_point` (Youden) is unchanged and now provably equals
  `operating_points['youden']`.

**Fix (frontend, `DeploymentRocPanel.js`):**
- New `pickServerCutpoint(roc, rule, logCost)` snaps to `roc.operating_points`; for `cost` it picks
  the precomputed point at the slider's nearest `log_cost`.
- `op` now prefers `pickServerCutpoint(...) || solveCutpoint(...)` — the live browser solver is kept
  ONLY as a fallback for older payloads that predate `operating_points`. Same return shape, so
  Phases C–E and the downstream `onCutpoint` lift are unchanged.

**Tests (+4, `test_analytics.py`):** youden full-array argmax; inf-sentinel-skip + tie determinism;
cost-ratio shifts toward specificity; `deployment_roc` ships the table and its full-array Youden
equals the legacy `operating_point` even when `max_points` forces a downsampled curve.

## [42] — operating-point chip on the LSB panel + resulting-LSB on the histogram (Bucket D, med)

**Gap:** PB (ROC) handed a threshold in oriented log-power units; PC (LSB) re-displayed it as
"≥ X LSB" — two numbers connected only by prose, no single place showing both.

**Fix (frontend):**
- `LsbPowerPanel.js`: new `onLsbThreshold` prop. The panel lifts the resolved device-LSB threshold
  `{upperLsb, estimated}` to the parent, and renders an **operating-point chip** at the top: rule +
  sens/spec + the oriented log-power cut + `→ ≥/≈ X LSB`. Amber when the cut-point is degenerate or
  the LSB is estimated (modeled), accent-green when measured.
- `index.js`: new `lsbThreshold` state threads PC's resolved LSB back into PB.
- `DeploymentRocPanel.js`: the feature-histogram cut-line annotation (effect D) now appends the
  resulting `≥/≈ X LSB` beneath `cut ≥ <logpower>`, so the histogram shows BOTH numbers the
  deployment connects. `lsbThreshold` added to effect D's dep array.

No backend change for [42] (pure UI wiring; the LSB number already came from `/queryLsbPower`).

## Files touched
- `BRAVO/modules/Biomarkers/routines/analytics.py` — `_solve_roc_operating_point`, `operating_points`.
- `BRAVO/modules/Biomarkers/tests/test_analytics.py` — +4 tests.
- `Client/src/views/Reports/ClosedLoopSim/DeploymentRocPanel.js` — server cut-point + hist LSB note.
- `Client/src/views/Reports/ClosedLoopSim/LsbPowerPanel.js` — op-point chip + LSB lift.
- `Client/src/views/Reports/ClosedLoopSim/index.js` — `lsbThreshold` state wiring.
- `Client/build/` — rebuilt.

## Still open (MEGA_HANDOFF §4)
- **[14]** clustering-granularity reconciliation — needs PI judgment before coding.
- **[49]** embed Plotly PNG snapshots into the deploy export/print (needs bridge for kaleido).
- Low-polish cluster [0]/[15]/[22]/[28]/[39]/[43]/[48].
- Anchor E2E test (timeline circle == spectral point); `per_pro_lsb_overlay` not yet drawn.
