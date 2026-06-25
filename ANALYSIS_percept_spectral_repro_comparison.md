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
