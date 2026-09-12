# BRAVO Pain Biomarker — Session Handoff (2026-06-23 20:58)

## STATE AT HANDOFF
- **Repo:** `/Users/pshirvalkar/dev/BRAVO_pain`  · **Branch:** `PS_biomarker_module` · **HEAD:** `b870b3f` (nothing committed this session)
- **Frontend bundle (built, uncommitted):** `Client/build/static/js/main.93ef207f.js`
- **Working tree DIRTY** — modified, not committed:
  - `BRAVO/modules/Biomarkers/bravo_service.py`
  - `BRAVO/modules/Biomarkers/routines/analytics.py`
  - `BRAVO/modules/Biomarkers/routines/streaming_psd.py`
  - `Client/src/views/Reports/Biomarkers/BiomarkerAnalytics.js`
  - `Client/src/views/Reports/Biomarkers/BiomarkerDataTimeline.js`
  - new: `BRAVO/modules/Biomarkers/tests/test_welch_rating_centered.py`
- **Bridge suite:** running/reachable (per user) — backend changes need a reload to take effect.
- **Test patient:** RCS08, uid `2e3c75c00d7f4f37b53a048d195f11da`. Bridge container cwd `/usr/src/BRAVO`.

---

## WHAT WE'RE FIXING RIGHT NOW (both OPEN)

### A. rpy2 / pymer4 mixed-effects fits fail on every band click — PARTIALLY FIXED, STILL BROKEN
The two R-backed panels on the click-validate plot fail (the numpy/scipy line — Cohen's d, median Δ, rating-clustered p — works fine):
- **Mixed-effects fit unavailable: glmer fit failed**
- **Stim-stability test unavailable: LRT failed**

**Error #1 (fixed this session):** `Conversion rules for rpy2.robjects appear to be missing … in a contextvars.ContextVar … multithreading code not passing context to the thread.`
- **Root cause:** rpy2 ≥ 3.5 keeps the active pandas↔R converter in a `contextvars.ContextVar`. pymer4 0.8.2 calls `pandas2ri.activate()` once at import on the main thread; Django serves the request on a **worker thread** (plus a `ThreadPoolExecutor` in the PSD path), where that ContextVar is empty → conversion raises.
- **Fix applied** in `analytics.py`: added helper `_rpy2_converter_ctx()` (line ~1902) returning `localconverter(ro.default_converter + pandas2ri.converter)` (nullcontext if rpy2 absent). Wrapped all 4 conversion-sensitive sites: the glmer fit + `.fit()` in `band_mixedmodel_inference`, its lazy `mod.ranef_var` read, and both LRT fits (`m0`, `m1`) in `band_stim_stability`.

**Error #2 (NOW SHOWING — still open):** `Conversion 'py2rpy' not defined for objects of type '<class 'rpy2.rlike.container.OrdDict'>'`
- The converter-context fix moved past the ContextVar error; now it's a **different, deeper** pymer4-0.8.2 ↔ rpy2-version mismatch. pymer4 0.8.2 builds the R model frame using `rpy2.rlike.container.OrdDict`, and the installed rpy2 has no `py2rpy` rule registered for `OrdDict` (it was the default-converter content in older rpy2; newer rpy2 dropped/changed it).
- **NOT yet diagnosed/fixed.** Candidate directions to investigate next session (need the bridge to see the actual installed rpy2 version — `pymer4==0.8.2` is pinned, `rpy2` comes from the OS `apt python3-rpy2`):
  1. Register an explicit `py2rpy` conversion for `OrdDict` in `_rpy2_converter_ctx()` (e.g. convert OrdDict→`rpy2.robjects.vectors.ListVector`/named list) before the fit — most surgical.
  2. Check the installed rpy2 version on the bridge; pymer4 0.8.2 was written against rpy2 ~3.4–3.5. If the image has rpy2 ≥ 3.6 a known-good pin may be needed, OR a monkeypatch of the one pymer4 call that constructs the OrdDict.
  3. Confirm whether `pandas2ri.converter` alone (without `default_converter`) or a `+ numpy2ri.converter` changes which branch pymer4 hits.
- **Repro:** click any band (FDR-significant or not) on the spectral feature-importance click-validate panel for RCS08. Both R panels error identically.
- **Files:** `BRAVO/modules/Biomarkers/routines/analytics.py` — `band_mixedmodel_inference` (~1928), `band_stim_stability` (~2046), helper `_rpy2_converter_ctx` (~1902).

### B. Streaming-session concatenation hypothesis — INVESTIGATION JUST STARTED, NOT RESOLVED
**User hypothesis:** when a JSON is ingested, multiple TD streaming sessions within one file/day may be **concatenated into one recording and stamped with a single timestamp**, which could (a) manufacture the 30–45 min "sessions" and (b) make one session answer multiple pain scores at one timestamp.

**What's been read so far** (`BRAVO/modules/MedtronicPercept/BrainSenseStream.py`, `saveBrainSenseStreams`, lines 33–152):
- Sessions are **sorted** by `FirstPacketDateTime + len(Data)/SamplingRate` (line 49).
- The `while` loop pairs **two channels of the SAME session** when `StreamingTD[n].FirstPacketDateTime == StreamingTD[n+1].FirstPacketDateTime` (lines 67–90) — that's left+right of one recording, NOT two time-separated sessions. Different-time neighbors fall to the single-channel branch (92–103).
- **So far, no evidence of cross-time concatenation in THIS function** — it pairs hemispheres, not sequential sessions. Each output `Recording` gets `StartTime = FirstPacketDateTime` and `Duration = Data.shape[0]/SamplingRate`.
- **STILL TO CHECK (next session):**
  1. Whether an **upstream** step (the JSON decoder `Session.py`, or `IndefiniteStream.saveIndefiniteStreams`) concatenates packets across a gap into one `Data` array with one `FirstPacketDateTime` — IndefiniteStream is the long/gappy one and the likeliest culprit for a multi-hour span at one timestamp.
  2. **Load real RCS08 JSONs** and compare raw `FirstPacketDateTime`s + packet counts against what's wired into the cache (`psd_scan_index` / the per-recording npz). The bridge can decode the actual `.bdat`/JSON for RCS08.
  3. Confirm the relationship `Duration == nsamp/fs` holds on real data (it does in code: BrainSenseStream lines 63/88/101) — if a 45-min "session" has `nsamp/fs == 45 min` of CONTIGUOUS samples that's real; if `nsamp/fs` ≪ wall-clock span, something inflated it.
  4. If concatenation IS found: the rating-centered Welch already centers on each PRO inside `[t0, t0+dur]`, so a correctly-decoded long session is handled — but a session that concatenates across a TRUE time gap would have a wrong `ci = round((pro−t0)·fs)` sample index (assumes contiguous samples). The `Missing` array (BrainSenseStream lines 60/74/77) flags gaps and could gate this.

---

## DONE THIS SESSION (uncommitted, on disk)

### 1. Spectral feature-importance plot — 3 frontend fixes (`BiomarkerAnalytics.js`)
- **Legend isolation bug:** decoupled `sel` from the main draw effect; selected-band guide line now applied via a lightweight `Plotly.relayout` effect keyed on `[sel, scan]`, so clicking a band/curve no longer purges+rebuilds the plot and no longer resurrects hidden curves. Legend `itemclick: "toggle"`.
- **Hover readability:** scan-specific `hoverlabel` — `bgcolor rgba(255,255,255,0.97)`, `bordercolor #5A6470`, font size 14, color `#1A1A1A`.
- **Two-line bold title** centered over both panels: line 1 `${ch.short} (n=${nShown})` (22px), line 2 `${center.toFixed(1)} Hz · Pearson r = … (p = …)` (18px). Title-clip fix: `lineHeight 1.45`, `display:"block"`, `pt:1`. `nShown = sc.x.length` (matches what's plotted).

### 2. Biomarker Data Timeline (`BiomarkerDataTimeline.js`)
- **Lane labels:** ALL bold AND black (`PAL.ink`) — `R 1⁻3⁺` / `R 0⁻2⁺` were the only non-bold/grey ones; committed vs exploratory is now carried by lane CONTENT, not label dimming.
- **TD-block hover:** invisible `scattergl` anchor markers report date · start time · **real captured duration** (`fmtDur(r.dur_s)`), anchored at the block's true center. (PSD/montage/event already had hover; TD had none.)
- **TD-block zoom-adaptive width (NEW, this session):** replaced the constant-TIME floor (`Math.max(dur_s, 86400*1.6)` = 1.6-day min, which made a 30 s session look like it spanned days and "covered" ratings it didn't) with a constant-PIXEL floor. Each TD rect is ≥ `MIN_TD_PX = 6` px on screen (visible/raster-like when zoomed out) but never wider than its true `dur_s` (renders true length when zoomed in). A `plotly_relayout` handler recomputes rect `x1` against the live x-range on each zoom/pan (one batched `Plotly.relayout`, no React re-render). `tdRectsRef` holds `{i, ts, dur_s}` per rect, reset each draw.
- **VAS/PRO hover date+time (NEW, this session):** both pain-row hovers (binarization + multimodal) now lead with bold value then a `fmtHoverDate · fmtHoverTime` line, then class/match status. Previously binarization-mode showed no timestamp, multimodal showed a raw `%{x}`.

### 3. Rating-centered TD-streaming PSD pipeline (backend) — the big one
**Problem solved:** legacy `welch_psd_for_instance` Welch'd only the FIRST 30 s of each streaming session and stamped the PSD at the session START, so a pain rating mid-session read "no neural match" despite TD coverage (the Jan-6 VAS 47 case).

- **`streaming_psd.py`** — new `welch_rating_centered(channel_data, channel_names, fs, chan_order, centers_s, *, f_set, win_s=WELCH_MAX_SECONDS, min_s=WELCH_CENTERED_MIN_SECONDS)`: cuts a `win_s` (30 s) window CENTERED on each rating inside `[t0,t0+dur]`, clipped to the session boundary (never slid across it — a rating 5 s before end → asymmetric 20 s window), drops windows < `WELCH_CENTERED_MIN_SECONDS = 10.0`. Returns `(psd (K,nch,F), used_dur_s (K,), kept_mask)`. Identical DSP to the legacy path (4th-order Butterworth HP @ 1/nyq, Welch nperseg≤1024, linear interp, NO 60 Hz notch). Full windows → one batched gather+Welch+interp-matmul; edge-clipped → individual Welch. Benchmarked ~110 ms typical / ~500 ms worst-case for RCS08-scale data.
- **`bravo_service.py`** — wired PRO-awareness through the cache:
  - `_welch_rows_into(..., pro_times=None)`: for TD, emit one rating-centered PSD per overlapping PRO stamped at the PRO's `t`; **fall back** to a single session-start PSD when no PRO overlaps (or all dropped by the floor) — the FIX for greyed-out short-session lanes.
  - `_psd_sample_index(..., pro_times=None)`: same keep-rule WITHOUT Welch (live count parity); same fall-back.
  - PRO-set signature folded into cache keys (TD only): `_pro_set_signature`, `_all_pro_times` (metric-AGNOSTIC so the key is stable across metric switches), `_recording_psd_cache_path(..., pro_sig)`, `_psd_matrix_signature_orm(..., pro_times)`, `_cached_psd_matrix(..., pro_times)` (persists `dur` in the matrix npz).
  - **Decode-free warm cache** (fixes a 45 s / 90%-all-cores stall): `warm_psd_cache(..., decoded_td, decoded_psd)` → `_warm_centered_matrix_from_decoded(...)` builds the centered matrix straight from the already-decoded in-memory signals (no second decode pass). Warm fired ONLY on the timeline path (`_build_availability(..., warm=True)`) so it doesn't race the scan.
  - `_TD_CENTERED_VERSION = "v2_fallback"` token folded into the TD cache key + matrix signature, invalidating stale TD caches without forcing montage re-decode.
- **Tests:** `test_welch_rating_centered.py` — 8/8 pass locally (centering vs reference, asymmetric edge-clip, 10 s floor, empty input, multi-rating, channel slotting, no-overlap→empty-keptmask fallback, partial floor-drop). Backend suite expected 125 + 8 = **133** via the bridge.

**Normalization note (unchanged by design):** centered TD carries `source="TD streaming"` and is z-scored within (channel, source) per-frequency on `10·log10(power)` exactly like every other source; pooling is unweighted after that z-score.

---

## OUTSTANDING / TO-DO (this + prior sessions)

### High priority (blocking or user-facing)
1. **[OPEN] Fix the `OrdDict py2rpy` error** (§A above) — the click-validate R panels still don't work. Needs the bridge to inspect installed rpy2 version; likely an explicit OrdDict→named-list converter or a pymer4/rpy2 version reconciliation.
2. **[OPEN] Concatenation investigation** (§B above) — load real RCS08 JSONs via the bridge, compare raw packet `FirstPacketDateTime`s/counts vs the cache, confirm whether IndefiniteStream or the JSON decoder concatenates across time gaps. Resolve whether the 30–45 min sessions are real contiguous data or concatenation artifacts.
3. **[OPEN — needs user confirmation] Verify in-browser** after backend reload: TD lanes color again, matched count climbs above ~50%, Jan-6 VAS 47 resolves to a real match. Confirm round-1 frontend fixes (`main.93ef207f.js`) render correctly (legend isolation, hover, titles, zoom-adaptive TD blocks, VAS hover date/time).
4. **[OPEN] Run the bridge suite** — expect 133 (125 prior + 8 new welch tests). User said the bridge is running.

### Carried from prior sessions (Wave 2 threads, not yet done)
5. **Live count confirmation** — user had not confirmed Overall VAS at ±60 min reads ~290/682 after the timezone `t_epoch` fix (was showing 61/682 due to a browser-side `Date.parse` Pacific re-read).
6. **`PainScores/index.js`** (separate Pain Scores report page) still does `Date.parse(p.t)` for stage-window logic — may show the same +7h timezone drift; left untouched, may need the same `t_epoch` treatment.
7. **Latent timestamp-normalization gap** — only `date_time_s1_daily` is normalized; other REDCap timestamp columns still have the naive-UTC bug.
8. **High-freq stim-artifact scrutiny** — Wave-2 thread, unresolved.
9. **The 5 narrow-CI bootstrap bands** — Wave-2 thread, unresolved.
10. **Composite power** feature — Wave-2 thread, unresolved.
11. **VAS@61.5 caveat** — documented as an honest optimizer-vintage difference on a singular fit, NOT a bug; do not re-chase.

### Housekeeping
12. **Nothing is committed.** Once the OrdDict fix + concatenation check land and the browser/bridge are confirmed, commit the session's work (3 backend files + 2 frontend files + new test + new bundle).
13. Many scratch/audit files are untracked in the tree (HANDOFF_*.md, VALIDATION_*.md, audit scripts, preview PNGs/HTML, scan CSVs) — decide what to keep vs gitignore before committing.

---

## KEY CODE LOCATIONS
- Click-validate R fits: `analytics.py` — `_rpy2_converter_ctx` (~1902), `band_mixedmodel_inference` (~1928), `band_stim_stability` (~2046).
- Streaming decode/concat: `MedtronicPercept/BrainSenseStream.py` `saveBrainSenseStreams` (33), `MedtronicPercept/IndefiniteStream.py` `saveIndefiniteStreams`, `MedtronicPercept/Session.py` (streaming dispatch ~405–444).
- Rating-centered Welch: `streaming_psd.py` `welch_rating_centered`, `WELCH_CENTERED_MIN_SECONDS=10.0`, `WELCH_MAX_SECONDS=30.0`.
- Cache wiring: `bravo_service.py` `_welch_rows_into`, `_psd_sample_index`, `_all_pro_times`, `_pro_set_signature`, `_recording_psd_cache_path`, `_psd_matrix_signature_orm`, `_cached_psd_matrix`, `warm_psd_cache`, `_warm_centered_matrix_from_decoded`, `_build_availability(warm=)`. Tokens: `_CHANNEL_CANON_VERSION="v2_ring_aware"`, `_TD_CENTERED_VERSION="v2_fallback"`.
- Timeline render: `BiomarkerDataTimeline.js` — TD block (~387), `tdRectsRef`/`MIN_TD_PX=6`/`applyTdWidths`/`plotly_relayout` handler (~837 region), pain-row hover (~682/689).
- Spectral plot: `BiomarkerAnalytics.js` — draw effect, relayout guide effect, two-line title.
