# Statistical validation of spectral pain biomarkers — RCS08

**Generated:** 2026-06-23 · **Participant:** RCS08 `2e3c75c00d7f4f37b53a048d195f11da`
**Scope:** standalone offline validation of the full-spectrum biomarker scan, run against the
**corrected** PSD pool (Survey product rescued — see AUDIT_stream_exclusions_RCS08.md), across all
six `BIOMARKER_METRICS`. Headline inference is mixed-effects logistic regression with a weekly-era
random intercept. Everything here is reproducible from the saved bundle + scripts.

---

## TL;DR

1. **Pseudoreplication is the dominant statistical risk in this dataset, and the app's current scan
   is exposed to it.** Each pain rating sits within the match window of ~7.7 PSD samples (4,722
   neural samples vs only 50–67 independent ratings per metric). Treating samples as independent
   (naive Pearson) flags **911 band×channel cells** as FDR-significant across the six metrics;
   rating-clustered logistic inference over the same grid leaves **5**. The signal is real but far
   smaller than the naive scan implies.
2. **14 band-candidates survive full rigor** (mixed-effects q<0.05, non-singular, no quasi-separation)
   out of 48 carried to inference. **12 of the 14 are on a ZERO_THREE channel** (both hemispheres).
3. **Two biomarker families emerge, with opposite signs:**
   - A **high-frequency (≈54–87 Hz) negative** family on **ZERO_THREE** (both hemispheres), validated
     for **NRS, VAS, and MPQ** — higher power ⇒ lower odds of high pain (OR 0.10–0.38). A
     same-direction high-frequency negative candidate also validates for **back-VAS**, but on a
     **different channel, ZERO_TWO_LEFT @ 86–91 Hz** (OR 0.22) — not ZERO_THREE.
   - A **beta-band (≈21–26 Hz) positive** family, validated strongest for **left-leg VAS on
     ONE_THREE_LEFT** (OR 15.4) and for **overall VAS on ZERO_THREE_LEFT @ 22–27 Hz** (OR 3.6) —
     higher beta ⇒ higher odds of high pain.
4. **Stim state matters and is testable, not assumed.** Of the 14 validated candidates, **5 are
   stim-state-dependent** (band×stim-era interaction, FDR q<0.05) and **9 are stim-stable**. Every
   stim-dependent candidate is a high-frequency ZERO_THREE band whose pain effect is present at
   OFF/LOW stim but **abolished or reversed at HIGH stim (>1.5 mA)** — consistent with high-amplitude
   DBS injecting power into those bands and masking the biomarker. **The beta-band leg-VAS candidate
   is stim-stable** (OR 11.7 / 4.8 / 4.8 across HIGH/LOW/OFF) and is therefore the most defensible
   closed-loop target.

---

## Methods

**Dataset (`phase0_bundle.npz`).** Per-channel Welch PSDs from the corrected pool — TD streaming
(948), patient-event (2,625), and montage/survey (1,149, now including the rescued Survey product) —
z-scored within (channel, source), 101 frequency bins 0.95–100 Hz, 6 main bipolar channels. Each of
4,722 rows carries one channel. Each PSD is matched to the nearest continuous PRO within a 60-min
window (capped at 3 PSDs per rating, 2-min refractory) for all six metrics. Per-sample weekly era
(0–52) and stimulation amplitude (mA, from the chronic timeline) are attached.

**Label QC (`pro_balance_RCS08.csv`).** Per metric: 50–67 independent rating-days, day-level low/high
tertile balance 0.81–1.00. NRS is the least balanced (0.81; the patient skews high-pain, median 7/10)
but still usable. No metric was too sparse to validate.

**Scan (`scan_full_RCS08.csv`).** 5 Hz sliding band, 1 Hz step, 4–100 Hz (93 bands) × 6 channels × 6
metrics. Per cell: Pearson r (continuous), Cohen's d (tertile high vs low), and a rating-clustered
logistic Wald p (cluster-robust SE on the rating index — the correct first-pass inference for the
pseudoreplicated design).

**Multiple comparisons (`scan_full_fdr_RCS08.csv`).** Benjamini-Hochberg FDR per metric over the full
558-cell band×channel family. Because adjacent 5 Hz bands at 1 Hz step share 80% of their content,
the family is strongly autocorrelated and BH is conservative; we therefore reduce contiguous runs of
raw-significant bands to **candidate clusters** (peak by |Cohen's d|) and carry each cluster peak to
definitive inference. 143 candidate clusters; top 8 per metric (48 total) fitted with mixed effects.

**Mixed-effects validation (`glmer_results_fdr_RCS08.csv`).** `pain_high ~ std_band_power +
(1 | weekly_era)`, binomial, via pymer4 0.8.2 / lme4. Per candidate we report the fixed-effect OR +
95% CI + p, a quasi-separation guard (perfect class split by power), and a singular-fit flag
(random-intercept variance ≈ 0). FDR (BH) applied per metric over the fitted candidates. **Validated**
= q<0.05 AND non-singular AND no separation. All 48 fits converged; none were singular or separated.

**Stim-era heterogeneity (`stim_hetero_fdr_RCS08.csv`).** Three stim eras from per-sample mA:
OFF (<0.1), LOW (0.1–1.5), HIGH (>1.5). For each validated candidate, a likelihood-ratio test of
`band×stim_era` interaction vs main-effects-only (both with era random intercept). FDR over the 14
tests. A significant LRT means the biomarker–pain relationship differs by stim state.

---

## Findings per metric

Full ranked table: `validated_band_candidates_RCS08.csv` (48 rows; effect sizes, OR+CI, raw+FDR p/q
at each tier, era-stability, and a per-row verdict).

| Metric | Validated | Strongest validated band | OR (95% CI) | Direction | Stim-stable? |
|---|---:|---|---|---|---|
| **VAS (overall)** | 5 | ZERO_THREE_LEFT 68–73 Hz | 0.24 (q=0.007) | higher power → lower pain | yes |
| **NRS** | 4 | ZERO_THREE_LEFT 52–57 Hz | 0.10 (q=0.009) | higher power → lower pain | yes |
| **MPQ Sum** | 3 | ZERO_THREE_RIGHT 59–64 Hz | 0.23 (q=0.029) | higher power → lower pain | **no** |
| **Left Leg VAS** | 1 | ONE_THREE_LEFT 21–26 Hz | 15.4 (q<0.001) | higher power → higher pain | yes |
| **Back VAS** | 1 | ZERO_TWO_LEFT 86–91 Hz | 0.22 (q<0.001) | higher power → lower pain | yes |
| **Composite** | 0 | (raw-sig only, FDR n.s.) | — | — | — |

**Which metric does the biomarker track best?** Overall **VAS** and **NRS** give the most validated,
stim-stable, ZERO_THREE high-frequency candidates — they are the most reliable intensity readouts for
this participant. **Left-leg VAS** gives the single strongest *individual* effect (a beta-band,
stim-stable, large-OR biomarker on ONE_THREE_LEFT), which is attractive precisely because it is a
different channel, different band, and opposite sign — a complementary, somatotopically specific
target rather than a restatement of the global intensity signal. The **composite** metric produced
raw signal but nothing surviving FDR; its blended construction appears to dilute the band-specific
effect.

---

## Caveats

- **Single participant, observational.** These are within-RCS08 associations, not a causal or
  cross-subject claim. The validation establishes which bands survive rigorous inference *for this
  participant's data*, which is exactly what closed-loop tuning needs — but it does not generalize.
- **High-frequency bands deserve artifact scrutiny.** The 54–88 Hz negative family overlaps the
  gamma range but also the 60 Hz line harmonic and stim-coupled spectral content. The stim-era
  heterogeneity result is partly a feature (it correctly flags stim contamination) and partly a
  warning: treat the high-frequency family as provisional until a notch/stim-artifact check is run on
  the raw TD.
- **FDR over autocorrelated bands is conservative.** The cluster-then-confirm design mitigates this,
  but borderline candidates (back-VAS @ 24 Hz q≈0.06, etc.) may be real and under-powered, not absent.
- **Composite = 0 validated** could be a power problem (blended label) rather than a true null.

---

## App-merge recommendations

The notebook surfaced three capabilities the live BRAVO scan does not have. In priority order:

### 1. 🔴 Rating-clustered inference in the live scan (highest value)
The app's spectral-feature-importance scan already computes a rating-clustered logistic p
(`p_logit_cluster`) **per band**, but the headline still leans on Pearson r / AUC, which are
pseudoreplicated. **Merge:** make the rating-clustered logistic p the primary significance shown on
the scan, and add the **911→5 contrast** as a one-line honesty note ("N bands significant by
rating, vs M by naive correlation"). This is the single most important rigor upgrade and it reuses
code already in `analytics.py`.

### 2. 🟠 FDR correction across the band×channel grid
The live scan reports per-band p but does not correct across the ~558-cell family. **Merge:** add a
BH-FDR pass per metric and show q alongside p, plus the cluster-reduction (contiguous raw-sig runs →
peak candidate) so the user sees *candidates*, not 200 autocorrelated "hits". Small, self-contained
addition to the scan return.

### 3. 🟠 Stim-state stability flag per candidate (closed-loop-critical)
This is the most clinically actionable new capability: a candidate that works at OFF/LOW stim but
vanishes at HIGH stim is a **bad threshold anchor** for a device that operates across stim states.
**Merge:** when the user clicks a band, run the 3-era LRT and badge the candidate **stim-stable** vs
**stim-dependent**, with the per-era OR trajectory (the Fig-3 heatmap row). This directly feeds the
"is this safe to deploy as a threshold?" decision the platform exists to support.

### 4. 🟢 Mixed-effects as the per-candidate inference (deeper, optional)
The glmer path (pymer4/rpy2) is verified and gives an interpretable OR+CI per candidate. It is
heavier (R dependency, ~0.2 s/fit) so it belongs behind the click action, not in the bulk scan:
when the user selects a band, show the mixed-effects OR + CI + singular/separation guards as the
definitive readout under the exploratory r/AUC.

**Suggested sequencing:** (1) and (2) are pure-Python and reuse existing functions — ship together as
a "rigor pass" on the scan. (3) and (4) are click-triggered and share the per-candidate design-matrix
builder — ship together as a "validate this band" action on the click panel (the same panel we just
rebuilt with the violin).

---

## Artifacts

- `validated_band_candidates_RCS08.csv` — ranked validated band-candidate table (the deliverable)
- `pro_balance_RCS08.csv` + `fig_pro_balance_RCS08.png` — label QC
- `scan_full_fdr_RCS08.csv` — full grid scan with FDR q
- `glmer_results_fdr_RCS08.csv` — mixed-effects fits + FDR
- `stim_hetero_fdr_RCS08.csv` — stim-era heterogeneity LRT
- `fig1_pseudoreplication_RCS08.png` — naive vs rigorous significance
- `fig2_forest_OR_RCS08.png` — forest plot of validated ORs
- `fig3_stim_stability_RCS08.png` — OR-by-stim-era heatmap
- `phase0_bundle.npz` — the corrected labeled dataset (checkpoint)
