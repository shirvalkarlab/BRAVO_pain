# PSD→LSB: percept-spectral-repro vs. our frozen model — comparison & optimal approach

**Date:** 2026-06-25
**Sources read:** `shirvalkarlab/percept-spectral-repro` — `HANDOFF.md` (537 lines), `README.md`,
`PLAN.md`, `src/percept_spectral_repro/spectral.py`, `docs/brainsense_power_validation.md`,
`results/brainsense_power_head_to_head/brainsense_power_head_to_head_summary.json`. Compared against
our `BRAVO/modules/Biomarkers/routines/{analytics,psd_lsb_model,availability}.py` +
`bravo_service.py`.

---

## Punchline 1 — how the two approaches compare

The repro repo benchmarked **four** TD→LSB routes against `n=131` timestamp-paired RCS08 Stage-1
`BrainSenseLfp` selected-band-power blocks (the device's own selected-band LFP Power, in LSB). The
head-to-head (all positive targets):

| Method | r | RMSE (LSB) | Median fold | What it is |
|---|---:|---:|---:|---|
| repro transform + **fitted** k (≈353) | 0.993 | 60.6 | 1.09× | RC+S-Hann magnitude², transform-specific scale |
| repro transform + report-CV k | 0.993 | 62.1 | 1.10× | same, held-out k |
| **our Welch256 + fixed `269`** | 0.921 | 208.9 | **1.09×** | **our deployment default** |
| repro transform + white-paper `100` | 0.993 | 429.4 | 3.53× | under-scaled doc baseline |
| **our frozen log-log model on Welch256** | **0.515** | 451.1 | 3.42× | per-band `a_f` + common slope `b` |

Three things matter here, and they are easy to misread:

1. **Our `269 LSB/µV²` constant is vindicated.** The repro repo independently fit the Welch256
   band-integral scale on RCS08 and got **270.2** (all rows) / **266.2** (stim-off) — within ~0.4%
   of our `269`. Their own summary: *"Prasad/BRAVO's 269 LSB/µV² is well supported for a Welch PSD
   band-integral route."* The median fold-error of the `269` route (1.09×) is **as good as their
   best fitted transform** — it is the RMSE (a few large outliers) that differs, not the typical
   error.

2. **Their transform "wins" only with a non-physical, drifting scale.** The repro transform reaches
   RMSE 60.6 only after fitting its own `k ≈ 353–357 LSB/µV²` — a *transform-specific* number, not a
   Medtronic constant, and **not interchangeable** with the Welch `269`. That k is unstable exactly
   where it would matter: `ZERO_THREE_RIGHT` near 26.37 Hz swings to 461–577, June rows return to
   ~346 (a >1.5× session/channel/frequency drift). For a frozen deployment threshold that must hold
   across weeks, a scale that drifts 10–16% early→late and 1.5× by channel is a liability, not an
   asset.

3. **Our frozen log-log model's r=0.515 is NOT a defect — it is a surface mismatch.** The frozen
   per-band model (`log10 LSB = a_f + b·log10 P_welch`) was fit to **percentile-anchored chronic
   Timeline LSB** for deployment-threshold use, NOT to direct block-level `BrainSenseLfp` selected-
   band power. The repro authors flag this explicitly: *"do not use that result to dismiss the model
   for its intended deployment threshold use."* It underpredicts this *particular* surface by ~3.4×
   because it is aimed at a different one. This is the single most important caveat in the whole
   comparison.

**Net:** the two efforts agree on the physics. Our `269` Welch256 route is the correct, stable,
physically-interpretable PSD→LSB conversion. Their transform is a higher-fidelity *reproducer* of one
specific export surface at the cost of a fitted, drifting scale.

---

## Punchline 2 — the optimal approach, given both codebases

The optimal PSD→LSB strategy is a **tiered fall-through**, and our deployment module already
implements the top of it. Ranked by how much trust the number deserves:

1. **Native device LSB, when the device sensed the band.** Both codebases reach the same conclusion
   independently. The repro handoff: *"Use native device LSB when available; label any TD/PSD-to-LSB
   conversion as estimated."* Our `band_lsb_and_power` already does this — it reads the device's OWN
   Timeline LSB at the matched percentile and *"sidesteps BOTH the z-scoring of the feature AND the
   fragile µV²↔LSB conversion."* **No change needed; this is correct and is the better design.**

2. **Welch256 band-integral × `269 LSB/µV²`** for any band with no native LSB. This is the
   no-refit, physically-grounded default both repos endorse, validated to 270.2/266.2 on RCS08. This
   is what should drive the **timeline** PSD→LSB trace for survey/montage bands that have a PSD but no
   native LSB column.

3. **The frozen per-band log-log model** stays as-is for its intended job (percentile-anchored
   deployment threshold), with the existing extrapolation guard (`freq_extrapolated`,
   7.8–28.3 Hz) — do **not** repurpose it as a general block-level reproducer.

4. **Never** the white-paper `100 LSB/µV²` (under-scaled ~3.5×) and **never** the repro transform's
   fitted k as a fixed constant (drifts by channel/frequency/session).

The optimal *additive* opportunity: the repro repo also nails **survey/montage magnitude (µV)**
reproduction — global r=0.9998, RMSE 0.0152 µV, 97.83% of bins within 0.01 µV — using a 250-sample,
256-pt RC+S-Hann/RMS magnitude route with a low-bin correction. We do **not** currently derive LSB
for survey/montage PSD bands on the timeline (those surfaces have a PSD but no native LSB). Adding the
Welch256+269 route there would let the timeline show a calibrated LSB trace for *every* band power,
not only the bands the device streamed natively.

---

## Proposed implementation plan (for the next session)

Two surfaces, sharing one conversion helper. Keep the frozen deployment model untouched.

### Step 0. Empirically choose the timeline conversion method (gates A/B/C)

The timeline method is **not** pre-decided. Before building the helper, independently run the
percept-spectral-repro codebase and decide which conversion drives the biomarker timeline /
exploratory plotting + calculations:

- Clone + run the repo's gates (`uv run pytest`, `ruff check .`), then re-run
  `scripts/benchmark_brainsense_power.py` and reproduce the head-to-head table. Specifically verify
  the **"repro transform + report-held-out CV k"** route (r=0.993, RMSE 62.1 LSB, median fold 1.10×)
  — the low-RMSE method whose k is fit with the SAME report held out (honest out-of-sample, not a
  same-report refit).
- **Re-score within 8–30 Hz only** — that is the band the exploratory workflow and the adaptive
  controller actually use; the published numbers span all bands. Report per-method r / RMSE /
  median-fold in-window.
- **Decide on accuracy AND stability:** at the corpus level the transform's median fold-error equals
  the Welch256+269 route's (≈1.09×) — the RMSE gap is outliers, not typical error — and the
  transform's k drifts 10–16% early→late and up to ~1.5× at ZERO_THREE_RIGHT 26.37 Hz. Weigh
  in-window accuracy against that drift and against keeping a single conversion constant shared with
  the deployment module. Write the verdict (with in-window numbers) into a new "Timeline method
  decision" section here, then build A/B with the chosen method.
- If paired TD/`BrainSenseLfp` data are not reachable from the environment, fall back to a code-level
  review of `spectral.py` + the committed `brainsense_power_head_to_head_summary.json` and say so —
  do not fabricate benchmark numbers.

The target conversion window for the exploratory workflow is **8–30 Hz**: convert PSDs (and TD where
present) to LSB across that band. The steps below assume the Welch256+269 default; substitute the
chosen method if Step 0 selects the transform.

---

## Timeline method decision — VERDICT (Step 0 executed, 2026-06-25)

**Chosen method for the exploratory timeline: Welch256 band-integral × fixed `269 LSB/µV²`.**
Same method as the deployment threshold — one conversion constant across the whole product. The
repro transform + report-CV-k is **not** adopted for the timeline.

### What was run (no fabrication — real RCS08 Stage-1 data)

- Located the raw paired data: **27** Stage-1 session JSONs carrying both `BrainSenseLfp` and
  `BrainSenseTimeDomain` (`RCS008 jsons/Stage 1`, Dropbox). The **23** reports behind the repo's
  committed head-to-head are all present (matched by `YYYYMMDDThhmmss`); 4 are additional/newer.
- Ran the repo's own gates in a Python 3.12 env: **`ruff` clean; `pytest` 37 passed / 2 skipped.**
- Re-ran `scripts/benchmark_brainsense_power.py` (serial; the sandbox blocks `ProcessPoolExecutor`)
  on the 27 paired JSONs with the frozen `RCS08.json` wired in. The fresh output is
  **bit-identical** to the committed `brainsense_power_head_to_head_summary.json` (max relative
  difference **0.0** across all 133 rows). Independently confirmed: fitted `k_median` welch256 =
  **270.2** (all) / 266.2 (off) — i.e. the committed table is faithfully reproduced, not assumed.
- Artifacts: `step0_benchmark_summary.json`, `step0_benchmark_rows.csv`, `step0_inwindow_scores.json`,
  `step0_verdict_figure.png` (Operon project artifacts).

### Decision metric: re-scored **within 8–30 Hz** (the adaptive-controller band)

Restricting to center frequencies in 8–30 Hz drops the 12 rows at 7.81 Hz (below the 8 Hz adaptive
floor — *adaptive-invalid* regardless of method), leaving **n = 119 positive-target rows**. Scored
with the repo's own `metric_for` (`median_fold_error` = median of max(p/y, y/p)):

| Method (8–30 Hz, n=119) | r | RMSE (LSB) | **Median fold** | within 1.25× | within 1.5× |
|---|---:|---:|---:|---:|---:|
| **Welch256 × fixed `269`** | 0.992 | 59.7 | **1.075** | **0.70** | 0.92 |
| Transform + report-CV k | 0.996 | 49.8 | 1.099 | 0.68 | 0.93 |
| Transform + fitted k (all) | 0.996 | 47.1 | 1.092 | 0.68 | 0.93 |
| BRAVO frozen model (Welch256) | 0.523 | 447.0 | 3.518 | 0.08 | 0.18 |

**The all-band RMSE gap was an artifact of the out-of-window rows.** Corpus-wide, Welch256+269 reads
RMSE 208.9 vs the transform's 62.1 — but **in 8–30 Hz that collapses to 59.7 vs 49.8**, because the
12 below-floor 7.81 Hz rows carried almost all of the 269 route's large residuals. Those rows are
adaptive-invalid and never drive the controller, so they are correctly excluded from the decision.

### Accuracy verdict (in-window)

On **typical** error — the metric that matters for a trace read week-to-week — **Welch256+269 is at
least as good as the fitted transform**: median fold **1.075 vs 1.099**, within-1.25× **0.70 vs
0.68**. The transform leads only on **RMSE** (49.8 vs 59.7), i.e. on a handful of outliers, and only
after fitting a transform-specific scale. The handoff's open question — "does the transform beat 269
on typical error in-window, or only on outlier RMSE?" — is answered: **only on outlier RMSE.**

### Stability verdict (in-window)

Per-row *implied* scale `k = target_LSB / µV²`:

- **Welch256 implied-k median = 272.6, within ~1.3% of the fixed `269`** — the fixed constant needs
  no refit in-window. The transform's implied-k median is **352.5** — a non-physical,
  transform-specific number ~31% above 269 that must be *fit and then maintained*.
- Residual scatter is comparable (CV 0.21 welch256 vs 0.23 transform; 90/10 spread 1.57× vs 1.61×).
  Both drift early→late (welch256 19%, transform 10%) and widen at `ZERO_THREE_RIGHT` 26.37 Hz
  (welch256 90/10 = 1.62×, transform 1.82×). **The drift is a property of the signal/channel, not of
  the conversion** — it affects both. The decisive difference is that the transform's k is a *fitted,
  maintained* parameter (the thing that can silently go stale across sessions/firmware), whereas
  Welch256 rides the already-validated fixed `269` and introduces no new fitted scale.

### Why Welch256+269 wins the timeline (all three criteria)

1. **Accuracy:** ties or beats the transform on typical (median-fold) error in 8–30 Hz; trails only
   on outlier RMSE.
2. **Stability / no new fitted parameter:** its implied k already sits on the fixed 269; the
   transform requires fitting k≈353 and keeping it current. Fewer moving parts = fewer silent-drift
   failure modes for an exploratory view that must read consistently across weeks.
3. **Single source of truth:** 269 is the exact physical constant the deployment module already uses.
   Adopting the transform for the timeline would put **two different conversions in one product** for
   no in-window accuracy gain. Rejected on Occam grounds.

Native device LSB remains preferred whenever the band was sensed; **Welch256+269 is the fallback** for
PSD-only bands. The deployment threshold stays on Welch256+269 / the frozen model regardless — so the
timeline and deployment now share one conversion, no split needed.

### Scope limit (must carry forward)

This benchmark is **RCS08-only** (n=119 in-window rows, one patient). The chosen `269` scale is
validated on a single subject. If the exploratory timeline ever displays other subjects, the scale
needs **per-patient re-validation** before its LSB trace is trusted — the conversion is labeled
"modeled (×269)" precisely so a single-patient-validated number is never mistaken for a native or
multi-patient-validated one.

### Build implication

**Step A proceeds with Welch256 × `269`** (no swap to the transform). The shared helper
`analytics.psd_band_to_lsb` implements the fixed-269 Welch256 route, and the timeline tier and the
deployment fallback both route through it — confirming, not creating, the single-conversion design.

### A. Shared, audited PSD→LSB helper

- Add `analytics.psd_band_to_lsb(psd_uv2_per_hz, freq, center_hz, half_hz=2.5)` →
  `{lsb, uv2, k_used, freq_extrapolated, validated_hz_range, method}`. It integrates the Welch256
  PSD over `[center−2.5, center+2.5) Hz` to µV², multiplies by `LSB_PER_UV2_VALIDATED = 269`, and
  reuses the existing `freq_extrapolated` guard (7.8–28.3 Hz) verbatim. One code path, one constant,
  one guard — no second copy of the conversion logic.
- Regression test: round-trip a planted µV² band at `k=269` recovers LSB within float tolerance;
  out-of-range center flags `freq_extrapolated=True`.

### B. Timeline (Biomarker view) — derive LSB for PSD-only bands

- In `availability.lsb_series` (currently native-LSB only), add a THIRD source: for survey/montage
  PSD recordings that carry `Frequency` + `FFTBinData` but no native LSB column, call
  `psd_band_to_lsb` at the recording's sensing center frequency and emit those samples with
  `source="psd_modeled"` (alongside the existing `"streaming"` / `"chronic"`).
- Frontend `BiomarkerDataTimeline.js`: render `psd_modeled` samples with a visually distinct marker
  (open/hollow) and a legend entry "modeled from PSD (×269)", so a clinician never confuses a
  modeled LSB with a native one. Carry `freq_extrapolated` through to a per-sample warning tooltip.
- This is the part the user asked for: *"drive LSB for all the band powers from the PSD"* in the
  timeline view — done conservatively, labeled, native-preferred.

### C. Closed-loop deployment module — already correct; one verification + one cross-check

- `band_lsb_and_power` already prefers native Timeline LSB and falls back to the modeled conversion
  only when the band was never sensed. **Verify** the fallback path uses the new shared helper
  (route it through `psd_band_to_lsb`) so the deployment fallback and the timeline trace cannot
  diverge.
- Add an FYI cross-check line to the sign-off card: when a native threshold exists, also show the
  Welch256+269 modeled LSB at the same percentile and the fold-difference — a silent agreement check
  that flags if native and modeled disagree by more than the model's 1.26× σ.
- **Do NOT** swap in the repro transform's fitted k or change the frozen model. The deployment
  threshold's job is stability and defensibility, and the `269` route delivers both.

### D. Validation gate

- Re-run the full backend suite via the `_agent_bridge` (`python3 _agent_bridge/run_tests.py`).
  Current baseline is **166/166**; B and C should add ~3–4 tests.
- Optional, if paired TD/LFP data is reachable: port the repro repo's
  `benchmark_brainsense_power.py` head-to-head as a one-off validation notebook to confirm our
  `269` route reproduces the 1.09× median fold on our side too — but this is confirmation, not a
  dependency.

**Scope boundary:** this plan adds a *labeled, native-preferred* PSD→LSB trace to the timeline and
hardens the deployment fallback. It does not adopt the repro transform, does not change the frozen
deployment model, and does not touch the survey/montage *magnitude* (µV) reproduction (which the
repro repo already does excellently and which is a separate surface from LSB).
