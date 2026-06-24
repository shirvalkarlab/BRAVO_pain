# MASTER FIX HANDOUT — BRAVO biomarker module (backend parity + frontend review)

**Compiled:** 2026-06-23 · **For:** the engineering agent actively committing on `PS_biomarker_module`
**Do NOT treat this as edits already made — it is a prioritized spec. Another agent (you) holds the files.**

This consolidates three review passes run this session:
1. **Backend parity audit** — offline validation/scan pipeline vs the live biomarker-exploration backend. Full report: `PARITY_audit_validation_vs_backend.md` (artifact `aa7e4f54-3fd9-4eaf-8be0-3cc46b06328f`).
2. **Frontend review** — the React/Plotly exploration view. Full report: `FRONTEND_review_biomarker_exploration.md` (artifact `33c765f1-3590-41b1-8002-10c2cb26e7a2`).
3. **PRO timezone deep-dive** — the original symptom that started this. Full report: `FIXHANDOUT_pro_timezone_mismatch.md` (artifact `dd5f0022-62a5-48ad-81eb-870ea4067d40`).

Both review agents verified code at/near HEAD (`bb64b9b` → `11d025e` during the passes), ran empirical bridge probes on RCS08, and edited nothing.

---

## Priority-ordered fix list

| # | Severity | Area | One-line | Source report |
|---|---|---|---|---|
| 1 | **HIGH** | Backend — stim-era interpolation | Live `band_stim_stability` uses NEXT-sample stim; offline + physically-correct is LOCF. 814/4722 rows (17%) get the wrong stim era → biases the stim-stability LRT that picks closed-loop anchors. | Parity §7 |
| 2 | **MED** | Backend — glmer click-validate | `weekly_era` derived differently (49 elapsed-week buckets offline vs 29 ISO-week strings live) AND glmer binarizes globally vs per-channel. Click-validate OR/CI/p won't reproduce the validated table. | Parity §6 |
| 3 | **MED** | Backend — PRO timezone | `availability.pain_series` + `adapter` PRO readers parse REDCap time naively (no tz) → pain values 7–8 h early. Corrupts the availability-timeline pain row and the legacy chronic-detector alignment. (Does NOT corrupt the spectral numbers, and does NOT affect the exploration view's live counts — see note below.) | Parity §2 + tz deep-dive |
| 4 | **MED** | Frontend — refractory slider | Slider is enabled+draggable but INERT under the default `pro_first` mode (refractory only applies in nearest/prior). This is the "sometimes misbehaves." | Frontend §1 |
| 5 | **MED** | Frontend — stale empty-state copy | "Choose a source… click Compute biomarker now" describes a UI that no longer exists (no source tabs, button is "▶ Start exploratory analysis"). | Frontend §4 |
| 6 | low-med | Frontend — timeline key collisions | binByKey `(CHANNEL\|round(t))` collides on same-second samples (270 keys ≥2 samples); last-write-wins mis-colors ≤3/4452 marks and makes the painted timeline disagree with badge counts. | Frontend §2 |
| 7 | low-med | Frontend — histogram purges on every recompute | `BinarizationPreview` calls `Plotly.purge` in the effect cleanup, defeating its own `uirevision`; histogram zoom resets on every slider drag. | Frontend §7 |
| 8 | low | Frontend — abbreviations | FDR / glmer / logit not spelled out (project standard). | Frontend §5 |
| 9 | low | Frontend — hardcoded GPi/VIM region map | `HEMI2` hardcodes LEFT→GPi, RIGHT→VIM; not participant-derived — mislabels anatomy on any other subject. | Frontend §6 |
| 10 | low | Both — stale comments | `index.js` comment "44/682 → ~288"; real is 290/682. Non-user-facing. | Frontend §8 |
| — | FEATURE | Frontend — pain-score overlay | Your requested matched/unmatched + class encoding on the pain row. Full spec below. | Frontend §3 |

**What is NOT broken (verified clean):** PSD↔PRO matching parity (offline genuinely ran `pro_first`, reproduces 290/682 exactly), scan binarization, band-power feature (log/z-score stack identical), clustered-inference cluster key, and all 6 claimed wave-1/2 commits are present at HEAD. The exploration view's client matcher is byte-faithful to the backend.

---

## Important clarification on the timezone bug and your "67/682 on screen"

The frontend reviewer measured this precisely, and it resolves the confusion from earlier:

- The **Exploration view** builds its live model from **`/api/queryPainScores`**, which is at **0.00 h offset (correct)**. Reproducing the client matcher on those inputs gives **290/682 (42.5%)** — matching the backend scan exactly. **So the exploration view's on-screen counts are right.**
- The **−7/−8 h bug** lives on the **`availability.pain`** payload (the data-availability timeline's pain row) and the **adapter** chronic-detector path. That is the path that produces a wrong-looking count and a pain row drawn 7–8 h off from the PSD marks.

So: fix #3 (timezone) is real and worth doing — it fixes the **timeline pain-row alignment** and the **legacy chronic detector** — but it is NOT the reason the exploration binarization panel would read 67. If you saw 67 in the *exploration* view it was likely before a refresh / on an older bundle; the reviewer confirms the current exploration path computes 290. (The 67 figure is what `prior` direction yields — worth confirming the toggle wasn't on Prior.)

---

## Fix detail by item

### 1 — Stim-era interpolation direction (HIGH)

`band_stim_stability` (analytics.py ~1731-1733) assigns each PSD its stim era via
`idx = np.searchsorted(stim_t, t_epoch); stim_y[idx]` — this picks the **next** stim reading at or
after the PSD time (NOCB). The offline pipeline and the physically-correct semantics use **LOCF** (the
stim amplitude in effect *at or before* the PSD): `phase2b_hetero_v2.py` uses
`scipy.interp1d(kind="previous")`. Empirically 3253/4722 mA values differ and **814 rows (17%) change
era bucket** (OFF/LOW/HIGH), which biases the band×stim-era interaction LRT — the test that labels a
band stim-stable vs stim-dependent for closed-loop selection.

**Fix:** `idx = np.searchsorted(stim_t, t_epoch, side="right") - 1` (clip to ≥0), or
`scipy.interpolate.interp1d(stim_t, stim_y, kind="previous", bounds_error=False, fill_value=(first,last))`.
After the fix, re-confirm the era counts match offline (OFF 1376 / LOW 2073 / HIGH 1273 on vas).
**This changes which bands are reported stim-stable, so the click-validate stim verdict and any
deployment-anchor recommendation should be re-checked after the fix.**

### 2 — glmer click-validate parity (MED)

Two divergences make the per-band click-validate OR/CI/p differ from the offline validated table:
- **weekly_era:** live `band_mixedmodel_inference` (analytics.py ~1606-1607) uses ISO-calendar-week
  string `"{year}-W{week}"` (29 clusters); offline uses integer elapsed-week index
  `((t_epoch - t0)/(7*86400)).astype(int)` (49 clusters). The partitions are NOT a relabeling.
- **binarization basis:** live cuts the tertile on the **global** pooled labels then masks to the
  channel; offline cuts on the **channel's own** labels. Borderline samples flip class between them.
- Minor: live z-scores with ddof=0 (`np.nanstd`), offline ddof=1; live separation guard `|coef|>10`,
  offline `|beta|>50`.

**Fix:** decide ONE canonical definition. Recommended: make `band_mixedmodel_inference` use the
integer-elapsed-week cluster and per-channel binarization (match phase2), since the validated table is
the reference deliverable. If the global/ISO basis is intentionally preferred for the live path, re-run
the offline validation with those choices so the report and the app agree. Either way, the report's
12-band table and the click-validate panel must use the same definitions.

### 3 — PRO timezone (MED) — see `FIXHANDOUT_pro_timezone_mismatch.md` for the full treatment

`availability.pain_series` (availability.py:189) and `adapter.align_pros` (adapter.py:134) +
`bravo_chronic_to_lfp_df` parse `date_time_s1_daily` with bare `pd.to_datetime` (naive → treated as
UTC). Route them through `bravo_service._pro_timestamps_utc` (localize America/Los_Angeles → UTC,
DST-aware). **Best fix is at ingestion** — normalize once in `_load_pros` so no downstream reader ever
sees a naive local string; that handout's "Backend recommendation" section spells out the
ingestion-normalizer approach and the need to cover ALL REDCap timestamp columns (not just
`date_time_s1_daily`).

### 4 — Refractory slider inert under pro_first (MED)

Wiring, units (min→sec), NaN-guard, and useMemo deps are all correct — no double-application. The
issue: refractory is only applied in the PSD-first (`nearest`/`prior`) branch of
`computeMatchedScanModel`; the default `pro_first` branch claims at claim-time and never reads
`refSec`. The slider's only `disabled` guard is `maxPerRating <= 1`, so in pro_first it stays enabled
and draggable but does nothing. (Backend matches this — `build_pooled_detail_from_matrix` also skips
refractory under pro_first; `n_capped_dropped=0`.)

**Fix:** `disabled={maxPerRating <= 1 || matchDirection === "pro_first"}` and, when disabled for that
reason, caption: "Refractory gap does not apply in PRO-first matching (a PSD claimed by one rating
can't be reused, so bursts can't double-count); switch to Nearest or Prior to enforce a gap." No
change to the numeric path.

### 5 — Stale empty-state copy (MED)

`index.js` empty state says "Choose a source, pain metric, and (for Power-domain) the window above,
then click **Compute biomarker now**." All three clauses are stale: no source tabs (source is fixed
`"both"`), no Power-domain selector in this view, and the button reads "▶ Start exploratory analysis".
**Fix:** "Pick a pain metric and binarization above; the timeline and binarization preview are already
live. Click **▶ Start exploratory analysis** to run the full-spectrum scan."

### 6 — Timeline key collisions (low-med)

`binByKey.set(`${CH}|${Math.round(s.t)}`, bin)` collides on same-second samples (270 keys hold ≥2;
Map last-write-wins). 3 of them disagree in class (patient-event PSDs), so ≤3/4452 marks paint the
wrong class and the timeline can differ from the signpost badges by ≤3. Channel canonicalization was
verified CORRECT (0 key misses across 4722 records) — that was NOT the bug.
**Fix:** make the key collision-proof — either source-qualify it (`${CH}|${round(t)}|${s.source}`),
round sub-second (`Math.round(s.t*1000)` — scan t has sub-second precision), or store an array per key
and prefer a matched bin over "unmatched" on collision (option 3 also reconciles the painted timeline
with badge counts exactly).

### 7 — Histogram purge defeats uirevision (low-med)

`BinarizationPreview.js` histogram effect's cleanup `return () => Plotly.purge(ref.current)` runs
before every re-run (deps include vals/cuts/counts which change on every slider drag), so each tick
purges+rebuilds and the `uirevision: hist-${metricKey}` can't preserve zoom. The timeline component
deliberately avoids this.
**Fix:** drop the per-run cleanup; purge only on unmount via a separate
`useEffect(() => () => Plotly.purge(ref.current), [])`. `Plotly.react` diffs in place, so live recolor
still works and zoom persists.

### 8 — Abbreviations (low)

Spell out on first use: **FDR → False Discovery Rate** (`index.js` summaryLine, `BiomarkerAnalytics.js`
scan legend + caption); **glmer** → "mixed-effects logistic regression (lme4::glmer)" or drop the bare
token in the spinner; **logit → logistic** in the "rating-clustered logit" legend. `ValidationReadout`
is already compliant.

### 9 — Hardcoded region map (low / latent)

`BiomarkerDataTimeline.js` `HEMI2` hardcodes LEFT→GPi, RIGHT→VIM. Correct for RCS08 if that's the
anatomy, but wrong the moment this view opens on another subject. **Fix:** source region per hemisphere
from lead/target metadata; fall back to no region label rather than a wrong one.

### 10 — Stale comment (low)

`index.js` `matchTolerance` comment "44/682 → ~288/682" — real is 290/682 (42.5%). User-facing captions
are dynamic and correct; only the comment drifted.

---

## FEATURE — pain-score matched/unmatched overlay on the timeline

This is your requested feature: show actual pain scores on the pain row, with **closed circle =
matched neural data, open circle = no PSD match**, **orange = high pain, blue = low, grey =
excluded/mid**. The frontend reviewer wrote a complete implementation spec — reproduced here.

**Component:** `BiomarkerDataTimeline.js`, the pain-row markers trace. The **color** half (class →
orange/blue/grey via `classifyPain` + `scanModel.cuts`) is ALREADY implemented in binarization mode.
The **only** missing piece is the matched-vs-unmatched (closed/open) channel.

**The one new field (client-side only — no backend change needed).** The client matcher already knows
which ratings were claimed (`s.proIdx` into the matcher's internal sorted-PRO array; the claimed set is
`useCounts.keys()`), but it doesn't expose a per-rating flag aligned to the displayed pain series. Add,
in `computeMatchedScanModel` after the match passes, a boolean array aligned to the INPUT painSeries
order:

```js
// proSorted[j].i0 = original index into painSeries.t/y (capture during the sort)
const proSorted = painSeries.t
  .map((t, i) => ({ t, v: painSeries.y[i], i0: i }))
  .filter(p => Number.isFinite(p.t) && Number.isFinite(p.v))
  .sort((a, b) => a.t - b.t);
// … matcher already sets matched[*].proIdx = pk (index into proSorted) …
const painMatched = new Array(painSeries.t.length).fill(false);
useCounts.forEach((_, pk) => { painMatched[proSorted[pk].i0] = true; });
// return painMatched on the model (length === painSeries.t.length)
```

**Plotly marker encoding** (pain row; Plotly honors arrays for symbol/color/line.color):

```js
const cls  = pain.y.map(classifyPain);                 // BIN_COLORS.low/high/excluded
const symb = pain.y.map((_, i) =>
  (scanModel.painMatched && scanModel.painMatched[i]) ? "circle" : "circle-open");
traces.push({
  type: "scattergl", mode: "markers",
  x: pain.t.map(D), y: py,
  marker: { size: 8, symbol: symb, color: cls, line: { width: 1.6, color: cls } },
  customdata: pain.y.map((v, i) => [
    v, (scanModel.painMatched && scanModel.painMatched[i]) ? "matched" : "no neural match",
    classifyName(v)]),
  hovertemplate: `${pain.metric} %{customdata[0]}<br>%{customdata[2]} pain · %{customdata[1]}<extra></extra>`,
  showlegend: false,
});
```

For `circle-open` Plotly draws an unfilled ring in `marker.line.color`; setting it to `cls` makes the
open circle still read as its class. (If you prefer a white-filled open circle, set `marker.color`
white for the open points and keep `marker.line.color = cls`.)

**Y-position:** unchanged — the real rating value on the shared y-axis (this is what shows actual
scores, not a binary tick).

**Legend:** the cleanest compact key is two symbol-axis entries ("● matched / ○ no neural match", both
grey) plus the existing HIGH/LOW/excluded color swatches already in the binMode key — let the reader
compose the two encodings.

**Row subtitle (free):** `scanModel.counts.survey_usage` already has `n_pro_used` (closed),
`n_pro_unused` (open), `pct_pro_used` — so the subtitle can read "290 matched · 392 unmatched of 682
ratings (42.5% matched)" with no new computation.

**Scope:** binarization-mode only; leave the multimodal pain row neutral, consistent with the view's
mode semantics.

---

## Suggested ordering for the engineering agent

1. **#1 stim interpolation** first — it changes scientific conclusions (stim-stability verdicts) and is a one-line backend fix. Re-check the validated-band stim verdicts after.
2. **#2 glmer parity** — pick the canonical era+binarization definition so the click-validate panel reproduces the validated table.
3. **#4 + #5 + #7 frontend** — quick, user-visible, low-risk (slider gate, empty-state copy, purge removal).
4. **#3 timezone** — ideally the ingestion-normalizer approach (covers the timeline pain row + chronic detector + all future readers).
5. **FEATURE pain overlay** — adds the matched/unmatched intuition the user asked for; one new client field.
6. **#6, #8, #9, #10** — polish.

Each backend fix should keep the test suite green (was 109/109) and add a regression test where noted (the timezone handout includes one; the stim-interpolation fix should assert LOCF era counts match offline).

---

## rpy2/pymer4 glmer fit — RESOLVED (session 2026-06-24)

**Symptom (carried from prior handoff):** `band_mixedmodel_inference` and `band_stim_stability_lrt`
crashed on the live container with `NotImplementedError: Conversion 'py2rpy' not defined for objects
of type '<class 'rpy2.rlike.container.OrdDict'>'`. A prior attempt registering an OrdDict→ListVector
converter surfaced a deeper `unused arguments (checkControl=..., checkConv=...)` from glmer.

**Container versions (read via bridge):** Python 3.12.3, rpy2 **3.5.15**, pymer4 **0.8.2**, lme4 present.

**Root cause:** `_rpy2_converter_ctx()` activated `(default_converter + pandas2ri.converter)` around
the fit. pymer4 0.8.2 builds its control object with `robjects.r("glmerControl(...)")`; under an
active pandas2ri **rpy2py** context that R named list is eagerly converted to a Python `OrdDict`,
losing its R class. pymer4 then passes the OrdDict back into `lme4::glmer(control=...)`. rpy2 3.5.15
has no `py2rpy` rule for OrdDict → crash. The nested glmerControl structure (checkControl/checkConv/
optCtrl) also can't be reconstructed as a plain R list, hence the "unused arguments" follow-on.

**Fix (analytics.py `_rpy2_converter_ctx`):** use the PLAIN `default_converter` only. It is non-empty
(so the worker-thread "rules missing" ContextVar error is still avoided) but lacks pandas2ri's
rpy2py rule, so glmerControl stays a native R ListVector. pymer4 does its OWN DataFrame conversion
internally (pymer4.bridge.pandas2R/R2pandas each open their own localconverter), so the outer context
never needed pandas2ri.

**Validation (in-container via bridge):**
- Both fit paths succeed: single-band glmer (coef/OR/CI/z/p) and the reduced-vs-full LRT with a
  Categorical `stim_era` factor (correctly expands to stim_eraLOW/HIGH).
- Real `band_mixedmodel_inference` run **on a ThreadPoolExecutor worker thread** (the original
  failure mode) → `available: True`, recovers an injected 20 Hz signal (z=3.57, p=3.6e-4).
- Full module suite: **PASS=133 FAIL=0** (run_tests.py, analytics reloaded in live container).

Gunicorn `--reload` picks up the edit automatically. No image rebuild needed.

---

## Fix A — Missing-aware TD Welch epochs (concatenation zero-fill no longer biases the PSD)

**Date:** 2026-06-24 (this session). **Files:** `routines/streaming_psd.py`, `bravo_service.py`,
new `tests/test_welch_missing_aware.py`. **Audits:** `AUDIT_streaming_concatenation_RCS08.md`,
`AUDIT_concat_vs_PRO_matching_RCS08.md`.

**Background.** `BrainSenseStream.saveBrainSenseStreams`' `FixBreaking` block concatenates
consecutive, time-separated TD recordings and ZERO-FILLS the inter-recording gap (≤30 s ceiling),
marking those samples 1 in the recording's `Missing` array. Verified firing on real RCS08 data:
2 of 3 multi-time sessions merged pairs, zero-filling real gaps of 26.0 / 29.5 / 25.5 s. The TD→Welch
adapter ignored `Missing` (while the PowerDomain adapter already drops `missing>0`), so those zeros
entered the Welch PSD as genuine signal — deflating broadband power and leaking spectrally.

**Prerequisite check (done first, per PI):** confirmed neural matching is ROBUST to concatenation
before touching the PSD. Across all 224 ingested RCS08 TD recordings and 678 PROs, concatenation
changes ZERO PRO→neural matches (only 2/678 PROs fall within the 60-min tolerance of any TD start;
both match identically with/without concat). See AUDIT_concat_vs_PRO_matching_RCS08.md. The risk is
real structurally (nearest-fallback keys on a single StartTime) but nil empirically here because
streaming sessions and pain ratings are almost entirely disjoint in time.

**Fix.** Added `WELCH_MAX_MISSING_FRAC = 0.10` and an optional `missing=` arg to both
`welch_psd_for_instance` (first-window path → returns all-NaN when the window exceeds the floor, and
`_welch_rows_into` skips storing a NaN row) and `welch_rating_centered` (per-window prefix-sum
rejection → drops over-missing centers from `kept_mask`, so the caller's first-window fallback still
gets a clean shot). `_welch_rows_into` collapses each recording's `Missing` to a per-sample flag via
new helper `_missing_time_vector` (any-channel rule) and passes it to both Welch calls. Cache
invalidation: new `_TD_MISSING_VERSION = "v1_missing_aware"` folded into the per-recording TD cache
key (BASE, unconditional — the first-window path serves montage/survey too) and the matrix signature.

**Validation (in-container via bridge):**
- Full module suite **PASS=138 FAIL=0** (133 prior + 5 new missing-aware tests).
- Real-data effect: two real RCS08 recordings with 32% and 15% first-window missing produce a finite
  (deflated) PSD under the legacy path and are correctly REJECTED under fix A.
- No regression: a real clean (0% missing) recording yields byte-identical rows pre/post fix.

Gunicorn `--reload` picks up the edit. No image rebuild needed.
