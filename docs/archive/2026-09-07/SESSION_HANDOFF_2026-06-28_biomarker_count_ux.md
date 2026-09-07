# Session handoff — Biomarker count integrity, hover-N audit, UI text, raw LSB cache (2026-06-28)

**Branch:** `PS_closedloop_deployment` · **Suite: 253/253 PASS** (bridge `run_tests.py`) · frontend rebuilt.

This session addressed a connected set of count-integrity bugs and UX requests on the Biomarkers
exploration view, plus the first (cache) half of the LSB caching/matching refactor. The matching
swap itself is deferred to a focused follow-up (PI decision — see §Deferred).

---

## 1. Scatter / violin count integrity (root cause + fix)

**Symptom (PI):** at 25.5 Hz the click-scatter low pane showed ~2 visible points but the title said
`n=98, shown=84`; "scatter and swarm show the same points"; channels with fewer recordings claimed
more matches.

**Root cause:** in LSB mode the left scatter plots `x = log10(modeled-LSB)` (modeled PER RATING) vs
`y = PRO rating`. Every matched PSD sharing a rating collapses to the SAME `(x, y)` → massive
overplotting, NOT dropped points. The title `nShown` was the sum of `n_grp` (high+low+mid), which
counted ALL matched rows including the rating-duplicates. `len_x` could even exceed `n_channel`
because `n_channel` counts montage-recorded matched PSDs while the scatter pooled across LSB sources
capped at `max_scatter=400`. The violin jittered the same `x`, so it looked denser than the stacked
scatter — same data, different overplotting.

**Fix (`analytics.py`, `spectral_feature_importance`):**
- Scatter build now DE-DUPLICATES to one observation per distinct rating (`rg`, the per-epoch rating
  index) when `auc_groups`/`rg` are present (`dedup_by_rating`). One epoch per `int(rg[i])`, first
  wins. `n_grp` is computed from the de-duplicated `idx`, so `nlo+nhi+nmid == n_obs == len(x)` by
  construction — rendered dots equal the headline n.
- `n_obs` is set AFTER the `max_scatter` cap (was before — fixed a cap-parity edge where distinct
  ratings > cap made `n_obs` exceed `len(x)`; proven by unit test: 994 distinct → 400 cap, parity
  holds). `n_distinct` (pre-cap) and `n_rows` (raw matched rows) are also on the payload.
- New scatter payload fields: `n_obs`, `n_distinct`, `n_rows`, `dedup_by_rating`, plus per-band
  `n_td` / `n_psd` (rendered TD/PSD-derived counts via `epoch_tier` lookup from the LSB cache).

**Fix (`BiomarkerAnalytics.js`):** title/violin now report `n = nShown` (= rendered dots) with the
TD/PSD source split and an "of n_distinct" note only when subsampled. Examples now rendering:
- Scatter title: `R 0⁻3⁺ (n=99: 16 TD · 83 PSD) @ 25.5 Hz`
- Violin caption: `n=99: … · LSB source: 16 TD · 83 PSD`

**Bridge-verified** at 25.5 Hz across all 6 channels: `n_obs == len_x == nGrpSum`, `hi+lo+exc ==
n_channel`. The PER-BAND rendered split `scatter.n_td + scatter.n_psd == n_obs` (e.g. R 0⁻3⁺
`16 TD · 83 PSD == 99`, the figure on the scatter TITLE). NOTE this is distinct from the per-CHANNEL
`ch.n_td`/`ch.n_psd_bridge` (the verify table's td/psd column, e.g. R 0⁻3⁺ `18/83`) which counts
LSB vectors over the whole channel, not just the rendered band, and need NOT sum to a band's `n_obs`.
(R 0⁻3⁺: distinctXY=98 vs n_obs=99 — two ratings share a rounded pixel; 99 is the honest count.)

## 2. Hover-N audit (all traces)

8 count-bearing label sites audited: **3 misreporting, 5 already honest.** All 3 bad sites printed
`n_channel` (matched PSD ROWS) where the count of independent rendered LSB vectors belonged —
inflating by 130–925 (R 0⁻3⁺ spectrum legend claimed `n=1026` vs ~101 independent LSB vectors). The
cited "AUC N=98 == Pearson N=98 (both equal)" is ONE `n_channel` echoed onto BOTH the r-curve and
AUC-curve traces via the hover `<extra>%{fullData.name}</extra>`. `ch.n_r` (Pearson N) is rendered
NOWHERE — there is no separate Pearson-N widget.
- FIXED: spectrum curve legend+hover (`BiomarkerAnalytics.js` ~L303, both r & AUC), scatter detail
  title (~L556), violin caption (~L584). All now print `(<n_td> TD · <n_psd_bridge> PSD)`.
- OK (already honest): distribution histogram day-bars, chronic power-pain scatter, chronic 24/7
  `n_effective`, streaming-LSB block hover, binarization legend.

**Count vocabulary (PI):** everywhere a sample count appears in the spectral-feature-importance area,
report TWO values only — TD-LSB count and PSD-LSB count (the independent LSB vectors feeding
analysis). Backend emits per-channel `n_high/n_low/n_excluded/n_td/n_psd_bridge` and per-band
`n_td/n_psd`.

## 3. UI text overhaul

- **`index.js`** — removed the legacy `summaryLine()` Time-/Power-domain dual-pipeline prose (and its
  now-orphaned module-level `fmt`/`fmtP`). Replaced with a concise per-channel summary below the
  Recompute button: each channel's `high / low / excluded` matched-sample counts and `TD / PSD` LSB
  source counts, plus a pooled-binarization line noting only modeled/real LSB feeds the scan.
- **`BiomarkerAnalytics.js` Full Spectrum caption** — condensed 6 dense 14px paragraphs (matching
  policy / survey usage / n_pooled / binarization split / LSB source) into 2 compact lines, keeping
  the bold two-way-screen takeaway and the conditional double-dipping warning.
- **`BiomarkerAnalytics.js` mixed-effects (`ValidationReadout`)** — enlarged + bolded the takeaways:
  verdict badge 10.5→14px, new 16px bold `OR / 95% CI / p` headline, 15px bold direction line, bold
  colored `Stim stable/dependent` verdict + bold LRT p. Method prose retained at 11.5px below.
- **`BiomarkerDataTimeline.js` glyph key** — removed stale symbols: the legend drew chronic /
  streaming / modeled LSB glyphs in green (`LSB_GREEN = #2CA02C`), but NO rendered trace is ever
  green (real LSB traces are colored by sensing frequency `freqColor` or steel-blue `PAL.proLsb` —
  verified by grep + the live payload). Recolored those glyphs to neutral `DIM_GREY` (`LANE_NEUTRAL`)
  and collapsed two duplicate modeled-LSB rows (○ TD / ◇ PSD were listed 3×) into one. Non-binMode
  legend 9 → 7 rows; `nLegRows` updated so the legend-box geometry stays correct.

## 4. Raw match-agnostic LSB cache (Phase-4 first half)

New `availability.raw_lsb_spectrum_cache(channel, centers_hz, *, td_recordings, event_psd_recordings,
window_s=RAW_LSB_WINDOW_SECONDS=3.0, band_half_hz=2.5, max_missing_frac=0.10)` — the DECOUPLED source
of truth the refactor asked for. Tiles the WHOLE recording history into 3 s non-overlapping windows,
full 0–100 Hz, separate per channel, **with no PRO/rating in the computation** (cache key is purely
channel + recordings + centers, so the same cache serves every metric/strategy/match policy).
- **TD family** — tiles by WALL-CLOCK SAMPLE INDEX (gap-correct, unlike `td_transform_band_power(agg=
  "none")` whose window axis is finite-sample space). Each tile = the validated 1 s rcs-Hann / 256-FFT
  transform, 50 % overlap, median across its internal sub-windows, × `LSB_PER_UV2_TRANSFORM` (352.62).
  A tile with < 1 s finite signal, > `max_missing_frac` non-finite, or any sample at the ADC rail
  (≥ `PRO_LSB_SATURATION_UV` = 4000 µV) emits a flagged all-NaN row (`saturated` / `ok=False`).
- **PSD family** — one window per PSD-only patient event, `device_psd_band_power` × `LSB_PER_DEVICE_PSD`
  (≈73.63); per-band `calibrated` True only inside [7.8, 30] Hz (exploratory outside, flagged).
- **Provenance** — each window tagged by source for the future binarization-hover breakdown:
  `TD_PRODUCT_SOURCE_LABEL` maps the recording `product` key (`streaming_td` / `indefinite` /
  `montage_td`) → `BrainSense streaming` / `Indefinite stream` / `Montage`; PSD events carry their own
  `source`. The CALLER must stamp `r["product"]` / `event["source"]` (per DB-type list) for labels to
  resolve — the decoded recording dicts carry none natively. Constant `RAW_LSB_WINDOW_SECONDS = 3.0`
  added to `analytics.py`.
- **Bridge-verified** on RCS08 `ZERO_THREE_RIGHT`: 60 528 TD windows (sources Montage / Indefinite /
  BrainSense) + 445 PSD windows; ~3 s spacing; ascending timestamps; PSD calibrated band 8.5–29.5 Hz;
  synthetic saturation (all-rail → 3/3 flagged) and missing (>10 % NaN → rejected) unit-tested.
- **LSB-source viz indicator** — new chip under the spectral-panel header pooling independent
  TD-transform vs PSD-bridge LSB-vector counts across displayed channels, stating "derived from
  TD + PSD sections (0–100 Hz)".

## Deferred (next focused session — PI decision "cache layer first, matching next session")

The new cache is NOT yet wired into `bravo_service` (no call site) or consumed by the scan/timeline —
the existing `per_pro_lsb_spectrum` PRO-coupled path stays live. The follow-up session implements:
1. **Live matching** against `raw_lsb_spectrum_cache`: median of the 3 s windows falling inside a
   configurable (~30 s default) rating-centered extent; TD preferred over PSD within the window.
2. **No-reuse rule** — each individual 3 s-TD or PSD LSB vector matched to at most ONE PRO. This
   reduces today's pseudoreplication (pct_nonindependent ≈ 79.7 %, max reuse 18×) and WILL shift
   r/AUC — report before/after as a validity improvement, with its own rigor pass.
3. **Binarization histogram hover** redesign: match the feature-importance hover styling; KEEP the
   per-category DAY count pinned at the top; add a source breakdown below — TD: Montage / Indefinite /
   BrainSense; PSD: Montage / Patient-triggered / other. Uses the same per-window provenance tags the
   new cache already carries.

## Files touched
- `BRAVO/modules/Biomarkers/routines/analytics.py` — scatter de-dup + per-band/per-channel TD/PSD
  counts; `RAW_LSB_WINDOW_SECONDS`.
- `BRAVO/modules/Biomarkers/routines/availability.py` — `raw_lsb_spectrum_cache`,
  `TD_PRODUCT_SOURCE_LABEL`.
- `Client/src/views/Reports/Biomarkers/BiomarkerAnalytics.js` — title/violin/legend TD-PSD labels,
  condensed caption, enlarged mixed-effects, LSB-source chip.
- `Client/src/views/Reports/Biomarkers/index.js` — legacy summary removed, per-channel summary added.
- `Client/src/views/Reports/Biomarkers/BiomarkerDataTimeline.js` — stale green legend symbols removed.
