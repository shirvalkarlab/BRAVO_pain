# Audit triage — 28 medium + 24 low findings (ClosedLoopSim deployment module)

**Date:** 2026-06-25 · **Branch:** `PS_audit_cleanup` (off `PS_closedloop_deployment` HEAD 22b1e97)
**Source:** `closedloop_audit_report.md` (artifact e3a12136), four-lens expert audit.
**Method:** code-review skill (React + Python guides). Every "already resolved" claim was VERIFIED
against current code at file:line — not assumed. The 4 HIGH (C1/C2/C3/C8) + C4 are resolved on the
base branch; the audit was written against an EARLIER tree, and a subsequent **"Phase-2 viz pass"**
(visible in `palette.js`, the panels, and `bravo_service.py`) already resolved most VIZ/PLOTLY
mechanicals. This triage reflects the CURRENT state, so the open set is far smaller than 52.

## Headline

Of the 52 medium+low findings, **38 are already resolved** in the current base (verified at
file:line), **2 mechanical items were open and are now fixed on this branch**, and **12 are genuine
judgment calls** (statistical methodology / larger-scope features) deferred to Prasad. No finding was
left unclassified, and no statistic/gate/clinician-facing number was changed by a mechanical fix.

---

## Bucket A — mechanical fixes IMPLEMENTED this session (on PS_audit_cleanup)

| ID | Panel | Sev | File:line | Change |
|---|---|---|---|---|
| **[25]** | P0 identity | low | `index.js` ~99 | Adaptive-band chip escaped the PAL palette (MUI framework-green `color="success"` + hardcoded `#f1d9b5` off-band fill). Routed through PAL: valid → `PAL.pass` fill / white text; off-band → `PAL.warn` fill / `PAL.onWarn` dark text. Now obeys the module's CVD discipline. Text labels unchanged → encoding stays redundant. |
| **[1]** | P0 identity | low | `index.js` ~127 | "· credible" / "· narrow CI" badge carried no rule. Added `title` tooltips surfacing the `_band_credible_ci` criterion (OR-space 95% CI width > 0.10, NOT "excludes 1") and noting the same flag gates the PE credible-CI gate. Pure interpretability fix; no logic change. |

Both are presentation-only, change no computed value, and are scoped to `index.js`.

---

## Bucket C — VERIFIED already resolved in current base (no action needed)

Each confirmed at the cited file:line in the CURRENT tree.

### Resolved by the C-series HIGH fixes (C1/C2/C3/C8/C4) propagating
| ID | Sev | Resolved by | Verified at |
|---|---|---|---|
| [2] PB oriented-AUC optimism note | med | C1/C4 | `bravo_service.py` roc `note` carries point-AUC optimism + class-collapse clauses |
| [4] class-collapse CI narrowing note | low | C1 | same `note` documents dropped class-collapsed replicates |
| [6] power on optimistic point AUC | med | C4 | `auc_power(..., auc_lo=roc.get("auc_lo"))` l.3693, 3903 — powers off CI lower bound |
| [12] PE powered gate + AUC-CI honesty | med | C4 | powered gate fail-closes on conservative end l.3978–3984 (`_powered_detail` power band) |
| [11] PE stim_stable fails OPEN | med | C8 | gates carry tri-state `state` pass/fail/**indeterminate** l.3919–3927; non-convergence ≠ pass |
| [13] necessary vs supportive gate tally | low | C8 | `necessary` flag on `_gate(...)`; ready blocks on necessary-gate failure l.3925–3932 |

### Resolved by the Phase-2 viz pass (palette + panels)
| ID | Sev | What current code does | Verified at |
|---|---|---|---|
| [24] P0 verdict badge white-on-orange | med | `onWarn` dark text when fill is warn | `index.js` l.66; `palette.js` onWarn=#1A1A1A (7.7:1) |
| [26] PB overlay histogram muddy blend | med | pain-low filled + pain-high step OUTLINE | `palette.js` painHighOutline; comment "Audit C7" |
| [27] PB AUC CI "clustered" provenance | med | title says "95% clustered-bootstrap CI" | `DeploymentRocPanel.js` l.154 |
| [29] PB degenerate marker white-on-orange | low | dark annotation text on warn | palette onWarn / cutpointDegenerate |
| [30] PC now/need markers unlabeled | med | static "now:"/"need:" annotations drawn once | `LsbPowerPanel.js` l.109–151 |
| [31] PC confidence color misleading | med | high→pass, medium→warn, low→fail | `LsbPowerPanel.js` l.409–410 |
| [32] PC y-axis "power" jargon collision | low | axis disambiguated (statistical power) | LsbPowerPanel power-curve layout |
| [33]/[46] incomplete `1px solid ` border | low | `PAL.warnBorder` token used; zero bare-border matches | grep returns none |
| [34] PD non-estimable era at x=0.5 | med | faint "n/a (insufficient)" row, no point on AUC scale | `EraRefitPanel.js` l.7, 93, 119 |
| [35] PD pooled-CI band unlabeled | med | "shaded = pooled 95% CI" static annotation | `EraRefitPanel.js` l.132 |
| [36] PD CI label not "clustered" | low | "AUC (95% clustered-bootstrap CI)" | `EraRefitPanel.js` l.188 |
| [37] PE headline warn text contrast | med | `PAL.warnText` (#8A6100, 5.5:1) not raw orange | `DeploySignoffCard.js` l.166 |
| [38] PE evidence-table CI methods | low | "in-sample (95% clustered-bootstrap CI)" labeled | `DeploySignoffCard.js` l.256 |
| [40] PB hardcoded restyle trace `[2]` | med | `const CUTPOINT_TRACE = 2;` single-sourced | `DeploymentRocPanel.js` l.31, 191, 209 |
| [41]/[47] modebar hidden (no export) | med/low | minimal modebar (toImage+reset, displaylogo:false) | `palette.js` l.91–109 + panels |
| [44] PC needed-N marker off-curve | med | marker placed at curve's interpolated power at nNeed | `LsbPowerPanel.js` l.150 |
| [45] PC no current-programmed anchor | med | recommended-vs-programmed Δ box (C10) | `LsbPowerPanel.js` l.65, 343–369 |
| [50] PE no ramp guidance | med | `_ramp_guidance(...)` emits onset/offset posture | `bravo_service.py` l.2902–2939 |

---

## Bucket B — JUDGMENT CALLS for Prasad (statistics / larger scope; NOT touched)

These change a statistic, a gate, a verdict rule, or are a feature larger than a fix. Each needs a
decision before implementation. Grouped by theme.

### B1 — Bootstrap / CI estimand (changes reported uncertainty)
- **[3] PB (med):** percentile-CI valid-replicate floor is only ≥20; 2.5/97.5 percentiles of 20 are
  near min/max and very noisy. *Question:* raise floor to ≥100 and/or switch to BCa, and gate the CI
  display on `n_boot_ok`? (Changes reported CI widths.)
- **[16] TIME-PB (med):** clustered bootstrap treats rating clusters as exchangeable, ignoring
  serial autocorrelation; a moving-block / weekly-unit bootstrap would widen the CI honestly.
  *Question:* adopt block bootstrap (block ≈ 1 week) — and accept the wider, more honest CIs?
- **[5] PB (low):** browser re-solves the cut-point on the DOWNSAMPLED ROC while the backend uses
  the full arrays; the two Youden points can differ slightly and the browser one propagates to C–E.
  *Question:* solve the displayed cut-point server-side on full arrays and pass the index?
- **[10] PD (low):** per-era bootstraps reuse seed=0 and the ≥20 floor; per-era CIs rest on far
  fewer valid replicates. *Question:* report `n_boot_ok` per era and de-emphasize thin eras?

### B2 — Verdict rules keyed on point spread, not inference
- **[9] PD (med):** portability verdict uses `auc_spread > 0.10` of POINT AUCs, ignoring per-era CIs.
  *Question:* base fragile/portable on CI overlap (or the band×era LRT p), keep spread as descriptive?
- **[21] PD (med):** verdict also keys on `cutpoint_spread` of RE-OPTIMIZED per-era Youden cuts,
  inflated by small strata. *Question:* put a bootstrap CI on the cut-point spread and gate on that?

### B3 — Temporal validity (the panel measures stim-state, not time)
- **[18] PC (med):** feature & device-LSB percentiles computed GLOBALLY → assumes stationarity; a
  drifting LSB baseline silently mis-scales the deployable threshold. *Question:* add a per-week
  threshold-drift diagnostic + tolerance warning (reuses weekly-cluster machinery)?
- **[20] PD (med):** stim eras are interleaved in calendar time, so PD measures robustness to stim
  STATE, not temporal generalization. *Question:* add a genuine per-week / first-half-vs-second-half
  temporal split and re-scope the verdict wording?
- **[19] PC (med):** power-vs-N curve assumes iid future ratings; autocorrelation overcounts
  effective N. *Question:* discount effective N by a design-effect factor, or relabel x-axis
  "effective independent ratings"?
- **[17] PB (med):** prior/forecasting match (neural window strictly BEFORE rating, no look-ahead)
  cannot be verified from this bundle. *Recommendation:* add a unit-test invariant asserting every
  matched window end < rating time + expose match tolerance. (Deploy-critical; needs the upstream
  matching code, not in this module — flag for the matching module owner.)
- **[14] TIME-P0 (med):** header independence unit ("weekly eras", glmer) is COARSER than the ROC
  bootstrap's per-rating clusters. *Question:* reconcile granularity (label PB as per-rating, or
  cluster ROC on the weekly unit)?

### B4 — Larger-scope features (beyond a fix)
- **[42] PLOTLY-PB (med):** PB hands a threshold in "oriented log-power units"; PC re-displays it as
  "≥ X LSB" — two numbers connected only by prose. *Question:* echo the operating point (rule +
  sens/spec) as a chip atop PC and annotate the histogram line with the resulting LSB? (GENUINELY
  OPEN — grep found no such chip.) Medium build.
- **[49] PLOTLY-PE (med):** exported `deploy_signoff_v1` JSON + printed sheet contain only numbers,
  none of the 4 figures that justify the decision. *Question:* embed `Plotly.toImage` PNG data-URIs
  into the export / print? (GENUINELY OPEN.) Medium build.
- **[51] PLOTLY-PE (low):** `window.print()` has no `@media print` stylesheet → screen layout
  (dark JSON inspector, shadows) prints poorly. *Question:* add a print stylesheet? (GENUINELY OPEN.)
  Low effort, materially improves the audit artifact.
- **[23] TIME-PE (low):** export schema has no `forward_validation` / `threshold_drift` fields, so
  the device record can't state temporal-validity status. *Question:* add fields (even "not
  assessed")? Pairs naturally with [18]/[20] if those land.

### B5 — Small-sample honesty (low)
- **[8] PC (low):** `n_clu ≥ 4` is permissive for asymptotic-normal AUC variance / Gaussian power.
  *Question:* raise floor to ≥8–10 or tag the readout "small-sample, approximate" below ~10?
- **[0]/[15]/[22]/[28]/[39]/[43]/[48] (low):** descriptive/labeling/navigation niceties (per-era OR
  CIs or relabel; stim-stability tooltip; single-era cluster assignment; unify feature-axis phrasing;
  scroll-link chips; Plotly resize-on-reveal comment; co-locate verdict with forest). Low-value
  polish — batch later if desired, none blocking.

---

## Validation note

The two bucket-A fixes are JS-only (`index.js`), presentation-only, and do not touch the Python
backend that the container test suite (`_agent_bridge`, baseline 166/166) exercises — so they cannot
regress the suite. They should still be eyeballed in the running client. The parent agent validates
the backend suite at merge.
