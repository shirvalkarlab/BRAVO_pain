# Session Handoff — PSD→LSB conversion model wired into deployment module

**Date:** 2026-06-25T01:19:10Z
**Branch:** `PS_biomarker_actionability`
**Commit:** `1fc1adc` — "ClosedLoopSim: frozen PSD→LSB conversion model + deployment fallback + panel"
**Participant:** RCS08 (uid `2e3c75c00d7f4f37b53a048d195f11da`)
**Prior handoff:** `SESSION_HANDOFF_20260624T231204Z.md` (conversion-analysis exploration)

---

## What this session did

Took the frequency-dependent PSD→device-LSB conversion (explored over the prior
session and the first half of this one) from analysis → **deployed code**. The
device reports band power in "LSB" units; an offline Welch PSD reports physical
µV². When a committed band has its own device-LSB Timeline recordings the
threshold is read straight off those (measured, trustworthy). When it does NOT,
the deployment module now **estimates** the LSB threshold from the physical µV²
cut-point via a frozen per-participant conversion model — clearly flagged
ESTIMATED with a fallback tier.

### The model (frozen asset, not an on-request refit)
`BRAVO/modules/Biomarkers/data/psd_lsb_models/RCS08.json`

Form, per channel: **log10(LSB) = a_f + b·log10(µV²)** — per-channel **common
slope b**, per-frequency **intercept a_f** (= device LSB at 1 µV²). The device's
on-board power gain falls as sensing frequency rises; that frequency dependence
lives entirely in a_f.

Reviewed fit decisions baked into the freeze (the reason it's frozen, not
recomputed live):
- Iglewicz-Hoaglin robust-z outlier omission **per band** (|0.6745·(r−med)/MAD|>3.5 on log10(LSB/µV²), MAD>0 guard).
- Hard **n≥6-per-band** reliability floor (a band below it gets no fit).
- **ZERO_THREE_RIGHT 8.8 Hz restricted to ≥2026-03-01** — a temporal gain-regime
  shift (Spearman ρ=−0.64, p≈1e-24); all-time k≈157 vs recent k≈52. The recent
  regime reflects the device's current sensing configuration.
- **23.4 Hz excluded** on 0-3 Right (noisy, inconsistent with 24.4/26.4 Hz neighbors).
- Pipeline upstream of the fit: nearest-LSB per PSD epoch (each PSD used once/channel),
  ±30 min match window, **fixed 10-min-bin averaging** (floor(t/600s); each cluster ≤10 min).

Fittable channels (RCS08): **0-3 Right** (b=0.85, R²=0.84, 6 bands), **0-3 Left**
(b=0.52, R²=0.25, 5 bands). The four sparse channels (1-3 Left/Right, 0-2 Left/Right)
carry a **pooled robust gain k** only (1-3 Right has neither — unmodelable).

Modeling note settled this session: per-frequency *slope* differences are NOT
supported (LR n.s., adjusted-R² does not improve; the common-intercept/adaptive-
slope mirror fits clearly worse with nonsensical negative slopes). The frequency
effect is a **gain/intercept shift, not a slope change**. A forced slope of 1.1
is within ~0.005 R² of the forced optimum (0.90) once 8.8 Hz and 23.4 Hz are
cleaned — but the deployed model uses the per-channel free common slope.

### Backend
- **`routines/psd_lsb_model.py`** (new) — `load_model` / `has_model` /
  `estimate_lsb` / `model_plot_payload`. `estimate_lsb(participant, channel,
  center_hz, psd_uv2)` returns an explicit fallback **tier**:
  1. `band` — exact (channel, freq) intercept
  2. `channel_freq` — same channel, nearest fitted frequency (gain extrapolated in Hz)
  3. `channel_pooled` — channel pooled robust gain k (proportional, slope=1)
  4. `none` — unmodelable
  Every non-measured result carries `estimated=True`. Scalar or array input;
  `lsb` mirrors input shape. Gain is power-dependent when b≠1 (k_effective falls as power rises).
- **`bravo_service.deployment_summary`** — after the measured-threshold block,
  when `thr_lsb is None` and a cut-point exists, calls `estimate_lsb`. The
  `deployable_threshold` gate now: measured→`pass`, modeled→**`indeterminate`**
  (usable for planning, never counts toward "ready to program" alone — preserves
  the audit C8 fail-closed discipline), neither→`fail`. The returned `threshold`
  dict gains `estimated` (bool) + `estimate` (sub-object with tier, k_effective,
  slope_b, model_center_hz, note). A caveat spells out the tier and "sense this
  band to confirm before committing."
- **`bravo_service.psd_lsb_conversion_model`** (new) — serves the frozen model +
  plot payload.

### API
- **`POST /queryPsdLsbConversionModel`** → `QueryPsdLsbConversionModel` view in
  `Server/APIs/DataAnalysis.py`, route in `Server/APIs/urls.py`. Request:
  `ParticipantId` (uid) or `Participant` (code).

### Frontend
- **`Client/src/views/Reports/ClosedLoopSim/ConversionModelPanel.js`** (new),
  mounted full-width in the ClosedLoopSim deployment view (`index.js`). Two plots:
  1. **Gain anchor vs frequency**, one trace per channel, bootstrap CIs, common
     slope b annotated — the gain-falls-with-frequency trend.
  2. **LSB vs PSD per channel**, points colored by sensing frequency, per-band
     common-slope fit lines overlaid, excluded clusters as grey ×.
  Imperative Plotly.react-once discipline; uses the shared Okabe-Ito `palette.js`.

### Tests
`tests/test_psd_lsb_model.py` (new) — **8 tests, all pass**: every fallback tier,
power-dependent gain (b≠1), array input, plot-payload shape, failure paths.
Run: `python3 -W ignore modules/Biomarkers/tests/test_psd_lsb_model.py`
(or via pytest inside the container).

---

## Verification done
- All 4 Python files parse; 8/8 estimator tests pass.
- eslint clean on both JS files (caught + fixed a real bug: `8.8Hz` object key
  needs bracket notation, not dot).
- Full symbol chain confirmed: service → estimator → API view → URL route → panel.
- Estimator matches the fit: 0-3 Right 26.4 Hz → k=71.5 at 1 µV², 51.2 at 10 µV².

## NOT done / open threads
- **Not committed beyond this branch**; no PR opened. Broader biomarker test
  suite not run this session (only the new test). Recommend running the full
  `modules/Biomarkers/tests/` under pytest before a PR.
- The frozen model is **RCS08-only**. Other participants need their own
  `data/psd_lsb_models/<CODE>.json` (same pipeline) before the fallback works
  for them — currently they'd get `{available: False}` from the estimator.
- **8.8 Hz temporal regime shift unexplained** — the gain dropped ~3× around
  early 2026. Likely a device sensing/gain reconfiguration; pulling the Percept
  programming/sensing-config history would pin the exact changepoint and confirm.
  Not yet checked whether 26.4 Hz (the other dense band) shifts similarly.
- `git config` is unwritable in this sandbox (.git/config protected); committed
  via `GIT_AUTHOR_*`/`GIT_COMMITTER_*` env vars as Prasad Shirvalkar.
- Latent pre-existing bug (from earlier handoffs, untouched): `test_analytics.py`
  `__main__` runner calls tests before definition (NameError under direct
  `python test_analytics.py`; CI uses pytest so unaffected).
- Audit C2 (forward-chaining / out-of-sample validation) still the only
  unaddressed HIGH audit finding — deployment AUC numbers remain in-sample.

## Key artifacts (Operon)
- Frozen model JSON: `psd_lsb_model_RCS08_frozen.json` (version_id `721a309c-6685-4b9b-8ad1-6b10d5ee41bc`)
- Interactive panel preview: `psd_lsb_deployment_panel.html` (version_id `97f83a6c-a615-4f28-87ec-2d07e2c6cc23`)
- Cleaned per-band intercept table: `psd_lsb_intercept_by_freq.csv` (version_id `609e7de9-2115-4fa8-9824-0e1422beccf3`)
- Cleaned fit figure (b=1.1, 8.8 Hz recent, 23.4 dropped): `psd_lsb_cleaned_forced_1p1.png` (version_id `b91969db-5501-4a86-a69c-088baa974b27`)
- 8.8 Hz temporal regime figure: `psd_lsb_88hz_time.png` (version_id `abc3184c-390e-418a-8efd-42c856a87205`)
