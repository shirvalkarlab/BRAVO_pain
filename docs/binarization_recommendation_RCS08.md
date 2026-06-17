# Pain-score binarization — methodology decision (RCS08)

**Question (HANDOFF §7-A):** what is the most rigorous way to turn a continuous daily PRO into the
binary high/low `pain_level` that (a) trains the LFP closed-loop detector and (b) a clinician reads
against stim parameters? KMeans (current), fixed percentile, median, or tertile — and single metric
vs 2–3-metric composite?

Decision criteria, weighted **equally** (label feeds both the aDBS classifier target *and* clinical
interpretation): **class balance · stability/generalization · separability by LFP · transparency.**

Analyzed on the real chronic series dumped from the live pipeline (`scripts/dump_chronic_pros.py`):
678 daily-PRO survey rows spanning **312 unique calendar days**; the binarization analysis and figure
use the 312 deduplicated days (one row per day).

---

## Two findings that change the framing

### 1. The current KMeans cut is confounded by recording density (a bug-class issue, not a tuning knob)
The pipeline runs KMeans on the **per-sample** `cv_df` — every ~10-min chronic sample carries its
nearest-date PRO. Recording density ranges **6 to 73,868 samples/day**. So the cut is implicitly
weighted by how much each day was recorded, which is device/behavior, not pain:

| unit | NRS cut | low fraction | n_low / n_high |
|---|---|---|---|
| **Unique days** (one row/day — the honest unit) | 6.42 | **10.3% of days** | 32 / 280 |
| Raw PRO rows (handoff basis) | 6.42 | 12.1% of rows | 82 / 596 |
| **Per-sample** (current pipeline) | 6.42 | 41.4% of samples | 116,409 / 166,301 |

Same cut, wildly different balance depending on the counting unit (the handoff's 82/596 = 12.1% was over
raw PRO rows, not deduplicated days; on unique days it is 32/280 = 10.3%). **Recommendation:
fit the labeler at the daily (PRO) level, then broadcast the daily label to that day's samples** — never
fit the cut on the density-inflated per-sample array. This alone removes most of the instability and the
88%-high imbalance the handoff flagged.

### 2. NRS is the worst available metric to binarize
NRS is ceiling-skewed (median 8, 25th pct 7, range 2–10). Every split on it is fragile and clinically
thin. MPQ-sum, back-VAS, and the MPQ+left-leg composite are far better behaved.

---

## Strategy comparison (daily level, equal-weight score over 4 axes)

Mean over all six metrics:

| strategy | balance | stability | separability (mag) | transparency | **score** |
|---|---|---|---|---|---|
| **Two-sided 30/70** (drop middle) | 0.97 | 1.00 | 0.38 | 0.90 | **0.812** |
| **Tertile 33/67** (drop middle) | 0.97 | 1.00 | 0.37 | 0.90 | **0.809** |
| **Median** | 0.99 | 0.97 | 0.27 | 1.00 | **0.809** |
| KMeans (current) | 0.83 | 0.97 | 0.24 | 0.30 | 0.586 |

- **KMeans is last on every axis except retention.** It is opaque (cluster boundary moves with the
  data), imbalanced on skewed metrics (VAS/back-VAS ~70% high), and gives the *weakest* LFP separation.
- **Dropping the ambiguous middle (tertile / two-sided) buys the most separability** — the LFP
  discriminates clear-high from clear-low days much better than it separates marginal days
  (e.g. back-VAS AUC 0.69→0.78, MPQ 0.70→0.77). Cost: you label ~50–65% of days and abstain on the rest.
- **Median is the transparency winner** and keeps all days; slightly lower separability.

## Single vs composite
The MPQ + left-leg-VAS composite is well-balanced and stable but **does not separate LFP better** than
its best single component (composite AUC ≈ 0.60–0.66 vs MPQ alone 0.70–0.77). For RCS08 a **single
well-behaved metric (MPQ-sum) beats the composite** on the discriminative axis. Composite's value is
robustness when any one PRO is missing, not signal.

### Composite recalculation (z-score vs min-max)
The original composite min-max-normalized each part to its 0–100 range then averaged — outlier-driven
(the range is set by the single most extreme survey) and it went NaN whenever *either* part was missing.
Replaced with **the average of z-scored parts** (z(MPQ-sum) and z(left-leg-VAS) across all surveys,
averaging whichever parts are present per row). On RCS08 this:
- **lifts coverage 253 → 312 days** (keeps a day when either part exists, not only both),
- **improves separability** (two-sided AUC 0.653 → 0.691) and ties balance/stability,
- rank-correlates 0.996 with the old composite on shared days (same ordering, better scale + coverage).
Adopted as the composite definition (`_resolve_biomarker_metric`).

---

## Recommendation for Prasad

1. **Stop fitting the labeler per-sample. Label at the daily level, broadcast to samples.** (Highest
   leverage — fixes the density confound behind the 88%-high / 12th-percentile artifact.)
2. **Default labeler: two-threshold (tertile / 30–70) with the middle excluded**, not KMeans. Transparent,
   maximally balanced and stable, and gives the detector the cleanest target. Surface the % of days
   retained so the abstention is explicit.
3. **Offer median as the "keep every day" alternative** when retention matters more than separability.
4. **Retire KMeans as the default** (keep it selectable for notebook parity). It is opaque and the worst
   performer here.
5. **Prefer MPQ-sum (or back-VAS) over NRS** as the binarization metric for RCS08; NRS's ceiling makes it
   the least informative. Use the composite only as a missing-data fallback, not for its (absent) signal gain.

**Caveat:** even the best binarization does not rescue the detector — the handoff's negative result
(CV ≈ chance, batch confound) stands. A cleaner label improves the *target*; it does not manufacture an
LFP signal that the rigor pass showed isn't there. The per-target / per-source separation and train-fold
relabeling (HANDOFF §7-C) remain the real levers on detector validity.

Engineering follow-up (HANDOFF §7-A): wire `label_strategy="percentile"`/`"tertile"` (+ daily-broadcast)
through `adapter.bravo_chronic_to_lfp_df` → `_resolve_biomarker_metric` → the card UI. `pain_binarization`
already reports percentiles, so the panel is ready.

---

## What was implemented (this session)

Backend (`BRAVO/modules/Biomarkers/`):
- **`adapter._threshold_pain_level`** — new median / tertile / percentile labelers. The cut is computed
  on the **daily** metric distribution and broadcast to samples (`daily_broadcast=True`, default), so
  recording density no longer biases the split. Tertile/percentile excludes the ambiguous middle (NaN).
- **`adapter.bravo_chronic_to_lfp_df`** — `label_strategy` now accepts `kmeans` | `cutoff` | `median` |
  `tertile` | `percentile`; added `low_pct` / `high_pct` / `daily_broadcast` params.
- **`pipeline.run_powerdomain_branch` / `run_biomarker`** — thread the new params through.
- **`bravo_service`** — `_label_strategy_params` reads `LabelStrategy` / `PercentileLow` / `PercentileHigh`
  from the request (**default `tertile`**); `BINARIZATION_STRATEGIES` exposed; response echoes
  `label_strategy` / `available_strategies` / `percentile_low|high`. Composite recomputed as the
  z-score average (above).
- **`analytics.pain_binarization`** — strategy-aware: reports the actual strategy, the two tertile cuts
  (`p_low` / `p_high`), and the excluded-middle counts.
- **Tests** — 4 new adapter tests (tertile drops middle, median keeps all, daily-broadcast fixes the
  density confound, tertile end-to-end). All five suites pass.

Frontend (`Client/src/views/Reports/Biomarkers/`):
- **`index.js`** — binarization selector (tertile default / median / KMeans legacy) + percentile-cut
  sliders (shown for tertile/percentile); strategy echoed in the results caption; sent as
  `LabelStrategy` / `PercentileLow` / `PercentileHigh`.
- **`BiomarkerAnalytics.js`** — binarization panel draws two cuts + a shaded excluded-middle band for
  tertile (single cut otherwise) and a strategy-specific caption.

_Figures: `binarization_comparison_RCS08.png`. Tables: `binarization_comparison_RCS08.csv`,
`binarization_density_confound_RCS08.csv`._
