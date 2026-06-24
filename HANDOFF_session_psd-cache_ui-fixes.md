# HANDOFF — Biomarker module session (2026-06-22)
### PSD cache, OOM fix, slider fix, PI UI changes + design-doc reconciliation

Repo: `/Users/pshirvalkar/dev/BRAVO_pain`  ·  Branch: `PS_biomarker_module`
**HEAD at end of session: `7cf8ab0`**  ·  Prior-session tip: `ae77e59`
Production bundle deployed: **`main.be606ed0.js`** (nginx :80)
Real participant: RCS08 uid `2e3c75c00d7f4f37b53a048d195f11da`
Design source of truth: `DESIGN_biomarker_pipeline_v2.md` (artifact version_id `bab71722-0293-453e-9d21-36b77a26cbac`)

---

## 0. Dev-loop facts (unchanged, carry forward)
- Backend runs **in Docker** (bind-mount `./BRAVO:/usr/src/BRAVO`, gunicorn `--reload`). Edits to `BRAVO/...` are live.
- Run in-container via bridge: `cd BRAVO/_agent_bridge; python3 bridge_client.py --cwd /usr/src/BRAVO --timeout N "<shell>"`.
  - Django bootstrap: `DJANGO_SETTINGS_MODULE=BRAVO.settings; django.setup()`.
  - **Bridge watcher caps captured runs at ~600 s.** For long jobs: launch detached (`nohup … >/tmp/x.log 2>&1 &`), write results to a file, poll the file.
- **pytest NOT installed** in container. Biomarkers tests run via a manual collector (import each `test_*.py`, call zero-arg `test_*` functions). **Baseline 95/95.**
- Frontend build: `cd Client; export PATH="/usr/local/bin:$PATH"; export npm_config_cache=/tmp/npmcache; env CI=false GENERATE_SOURCEMAP=false npm run build`.
- Heredoc/process-substitution `>(...)` and `$(...)` inside heredocs are **blocked by the safety filter** — use `edit_file` for file writes.
- Commit identity: `git -c user.name="Prasad Shirvalkar" -c user.email="prasad.shirvalkar@ucsf.edu" commit --author="Prasad Shirvalkar <prasad.shirvalkar@ucsf.edu>"`.
- Recurring benign warning: `unable to access '/Users/pshirvalkar/.config/git/ignore' Operation not permitted`.

---

## 1. Commits this session (oldest → newest), all on `PS_biomarker_module`

| Commit | Scope | Files |
|---|---|---|
| `ade2595` | PI UI changes + timeline color-mode toggle + design/eng review fixes | bravo_service.py (+psd_scan_index), routes.js, index.js, BinarizationPreview.js, BiomarkerDataTimeline.js, **new** binarizationModel.js, Client/build/ |
| `3106012` | Enlarge closed metric-dropdown value; per-group source counts in binarization boxes | index.js, binarizationModel.js, BinarizationPreview.js, Client/build/ |
| `d2664ed` | **OOM fix**: chunk the AUC permutation null (the >10-min hang) | routines/stats_utils.py |
| `925338c` | Percentile sliders live under default Tertile (drag promotes Tertile→Percentile) | index.js, Client/build/ |
| `7cf8ab0` | **Per-recording PSD cache + auto-warm on ingestion** | bravo_service.py (+288/-48), DataCurator.py (+24) |

`git log --oneline ae77e59..HEAD` reproduces this list.

---

## 2. Artifacts produced this session (project `proj_937f45eb8797`, frame `3931a1e3-…`)

| Filename | version_id | What it is | Status |
|---|---|---|---|
| `plan_eliminate-the-189s-cold-load-on-calculat_3931a1e3.json` | `bdc1bf0f-66a7-4201-a358-8790a59aa527` | Approved 5-step plan for the PSD cache | executed, complete |
| `pain_decoding_review.html` | `3e4b7d57-bd76-41b9-b13d-2c327eb4781b` | Self-contained interactive review page (Plotly **inlined**, 6.6 MB) of the pain-decoding view on real RCS08 data | **current** (v3; v1=`8a6b1b20…`, v2=`fccca96f…` were CDN-broken) |
| `preview_timeline_toggle.png` | `34aebd7b-1786-4000-8c56-0ffcd373243a` | Matplotlib mock: multimodal (top) vs binarization (bottom) timeline coloring | current (v4; v1–v3 had stale title/color) |
| `preview_binarization_hist.png` | `3d07eb57-3967-487f-85b7-a15c33c13cb8` | Matplotlib mock: binarization histogram at ±15 and ±60 min | current (v2) |
| `preview_hist_boxes.png` | `e1203e5a-f7fa-4c52-a27d-f66af63a36c8` | Matplotlib mock: per-group Low/Excluded/High source-count boxes on the histogram | current |

The HTML and PNGs are **review mocks built from a real RCS08 export** (`BRAVO/_review_export_rcs08.json`, 3.0 MB, untracked: records 3480, scan_index 1530, pain_t 682, 10 PRO metrics). They are NOT the live React app — Chromium can't screenshot the live app in-sandbox, so these are the visual proxies. Two design/eng review sub-agents (design frame `ae94c1f9-…`, eng frame `3f08d0e0-…`) reviewed them; their feedback drove the color/encoding changes in §5.

---

## 3. Function changes / additions (backend)

### `bravo_service.py`
- **NEW `_psd_sample_index(td_list, psd_list)`** (added `ade2595`): lightweight `[{t,channel,source}]` of the pooled-PSD samples the scan would include, built from StartTimes with the identical `_MAIN_BIPOLAR` filter — **no Welch**. Wired into `_build_availability` as `psd_scan_index` (and `[]` in the empty fallback). Powers the frontend's live match+binarize replica. Validated EXACT-match vs `matched_sample_counts` (N=1530; ±15min → 26 matched, 12 high/14 low).
- **NEW per-recording PSD cache** (`7cf8ab0`):
  - `_welch_rows_into(rows, recs, source_label, _sp)` — single source of truth for row schema `{channel,source,t,freq,power}`. Both legacy `_assemble_psd_rows` and the cache build through it → byte-identical matrix.
  - `_psd_rows_cache_dir()` → `DATASERVER_PATH/cache/biomarker_psd_rows/`.
  - `_recording_psd_cache_path(uid, hash)` → `"<uid>_<hash[:16]>.npz"`. **(GOTCHA fixed: `np.savez` appends `.npz`, so the temp file must keep the `.npz` suffix — `path[:-4]+".tmp.npz"`. First build silently wrote `..._hash.npz.tmp.npz` and every warm lookup MISSED.)**
  - `_save_recording_psd_rows` / `_load_recording_psd_rows` — atomic per-recording npz (empty list = valid 0-row entry, never re-decoded).
  - `_recording_rows_for_psd(uid)` — ORM-only list (uid+hash+source), **no file decode**.
  - `_assemble_psd_rows_cached(uid)` → `(rows, n_cached, n_computed)` — reads cached rows, decodes+Welches ONLY misses (threaded), persists each.
  - `_psd_matrix_signature_orm(uid)` — matrix-cache signature from DB rows alone (no load). Legacy `_psd_matrix_signature` retained, no longer primary.
  - `_cached_psd_matrix(uid, td_list=None, psd_list=None)` — keys the assembled-matrix npz off the ORM signature, assembles via cached path on miss. Args kept for call-site compat but unused.
  - `warm_psd_cache(uid)` — public, non-fatal entry; called by warm-pool and ingestion hook.
  - Call sites simplified: warm-pool now `_PSD_WARM_POOL.submit(warm_psd_cache, uid)`; compute path now `_cached_psd_matrix(uid)`. Both dropped a redundant `_load_recordings`.

### `DataCurator.py`
- **Ingestion auto-warm** (`7cf8ab0`): at the end of `MedtronicPerceptJSONDecoder` (after `person.save()`, before `return True`) a **daemon thread** fires `warm_psd_cache(person.uid)` via a **lazy** `from modules.Biomarkers import bravo_service` inside a broad `except`. Newly uploaded files are Welch'd + cached immediately, off the upload critical path; a cache failure can never break ingestion.

### `routines/stats_utils.py`
- **OOM fix** (`d2664ed`): `auc_block_perm_null` materialized three `(n_perm=1000, n=301600)` arrays at once (~2.4 GB each, ~7 GB transient) → SIGKILL/thrash = the >10-min hang. Rewrote lines ~251–256 to **stream permutations in chunks** (`CHUNK_ELEMS=8_000_000`, `chunk = max(1, min(P, CHUNK_ELEMS//max(1,n)))` ≈ 64 MB transient regardless of n). RANKS stay fixed; only labels permuted. **Bit-identical** to single-shot (null dist matches; observed/p identical). 301,600-sample series: OOM(>5 GB) → **0.9 s at 310 MB**.

### Verified performance (RCS08)
- Matrix byte-identical (logX/t/channel/source/f_set) legacy vs cached, N=1530×101.
- Warm assembly `cached=707 computed=0` in 0.16 s; cold build 3.0 s (OS-disk-warm; ~189 s on a truly cold container).
- After assembled-matrix invalidation (one new file ingested): rebuild from row cache **0.19 s, 0 decodes** (vs full re-Welch of 707 recordings).
- Full `run_for_participant` ~45–68 s at ~4.4 GB peak (post-OOM-fix). **Backend tests 95/95.**

**Scope boundary (state honestly):** the time-domain DETECTOR branch (`run_timedomain_branch → compute_psd_pain_correlation`) consumes raw TD streams, so it still loads raw TD. The cache eliminates the repeated Welch/matrix rebuild for the pooled-PSD scan + availability warm-pool and makes ingestion incremental — it does NOT remove the detector's raw-TD load.

---

## 4. Visual / UI changes (frontend)

### PI-requested (from prior-session handoff), committed `ade2595`/`3106012`
1. **Card title** → **"Pain Biomarker Exploration"**.
2. **Metric dropdown label** → **"Pain metric (drives exploratory analysis):"**.
3. **Nav name** (key `biomarkers`) → **"Biomarker Exploration"**.
4. **Binarization preview = match-window-gated AVAILABILITY** (matched-PSD subset distribution), recolors/recounts LIVE as the match-window slider moves. New `binarizationModel.js` (client replica of `_match_to_pro` + `_binarize_labels`) drives it; verified identical to backend.
5. **Timeline binarization coloring + color-mode toggle**: ToggleButtonGroup "Multimodal data / Binarization". In binarization mode all matched neural marks recolor by pain label (high `#D55E00`, low `#0072B2`, excluded `#5A6066`), everything else dimmed.
6. **Closed metric-dropdown value font** → `.MuiSelect-select { fontSize:30px !important; fontWeight:700 }` (matches open-menu items).
7. **Per-group source boxes** on the binarization histogram: Low/High float at y=0.80, Excluded at y=0.97 above a dotted max-line; each shows `N TD · N PSD · LSB n/a` (LSB not pooled → n/a).

### Slider fix, committed `925338c`
- Dragging Low/High percentile sliders while strategy=`tertile` **promotes strategy→percentile** so the cut moves live AND the backend honors the same values on Compute (preview==compute). Tertile preset (fixed 33⅓/66⅔) preserved as a selectable option. Caption updated. (Confirmed NOT a regression — slider wiring byte-identical since `ade2595`; tertile ignoring sliders is longstanding by design.)

---

## 5. REGRESSIONS / changes from old viz — candidates to WALK BACK

The new `BiomarkerDataTimeline.js` (44 KB) renders in front of the old `BiomarkerTimeline.js` (38 KB) whenever `availability.records` exist (priority fallback in `index.js:353-363`; old one only shows if no availability payload). Both files still exist. Review-driven color/encoding shifts the PI may want reverted or reconciled:

| # | Change made this session | Old / design value | Why flagged | Recommendation |
|---|---|---|---|---|
| R1 | **Multimodal pain row color** `PAIN_NEUTRAL = #3A4A63` (slate) | old `BiomarkerTimeline.C.pain = #D55E00`; new file's own `PAL.pain = #C44E00` | Pain trace no longer vermillion in multimodal mode — vermillion reserved for HIGH-pain binarization semantic. PI may expect pain=vermillion as platform identity. | **Confirm with PI.** Easy revert to `PAL.pain`. |
| R2 | **Excluded grey darkened** `#7E8794 → #5A6066` | design/prior `#7E8794` | Review: `#7E8794` vs `#D7DBDF` were indistinguishable. | Likely keep; mention. |
| R3 | **Dim grey lifted** `#D7DBDF → #AEB4BB` | prior `#D7DBDF` | `#D7DBDF` was 1.39:1 on white (looked ABSENT). | Likely keep. |
| R4 | **Non-poolable PSD ticks HIDDEN in binarization mode** (~1194 ticks) | prior: all ticks shown | They can never be colored by pain (not in scan). Hiding declutters but REMOVES data marks. | **Confirm** — PI flagged wanting all data shown. |
| R5 | **Right-side frequency legend SUPPRESSED in binarization mode** | prior: always shown | Mode-exclusive legend. | Confirm acceptable. |
| R6 | **Stim-amplitude row height** STIM_H=0.9 vs PAIN_H=1.6 | design §8e: stim 0.34, pain 0.60 | Ratio ~0.56 matches spirit; absolute values differ from design's numbers. | Cosmetic; align if PI cares. |
| R7 | **Old `BiomarkerTimeline.js` + `BiomarkerAnalytics.js` (86 KB) still mounted** | design §8b/§8d: clean/replace | New timeline replaces old visually (priority), but BOTH old files still imported; `BiomarkerAnalytics` still renders the full decode panel set below. Not yet refactored per §8c/§8d. | **Decide**: keep parallel during transition, or remove old timeline import once new one is trusted. |

**No data/statistical regressions** — backend numerics unchanged (95/95; pearson 0.965, power_pain_scatter r=0.777 p=1.9e-78, auc signal p=0.0030 stable). OOM fix is bit-identical. All flagged items are VISUAL choices from the design/eng review loop.

---

## 6. Diffs vs DESIGN_biomarker_pipeline_v2.md

### Delivered / advanced this session
- **§8e data-availability timeline**: `BiomarkerDataTimeline.js` implements the core — per-channel compact lanes (TD coverage block + LSB inline trend + PSD ticks), grouped LEFT/RIGHT, categorical `FREQ_PALETTE` (NOT cividis — design's own correction honored), pain + stim rows on shared x-axis, title says **"Percept RC"** (title-fix honored, NOT "RC+S").
- **§8e "dynamic downstream plots under binarization"**: binarization preview + timeline recolor live as the dichotomization changes (cutoff/median/tertile/percentile + PRO metric). The design's "see how grouping reshapes the data" link — partially delivered (timeline coloring + histogram; the high/low PSD comparison gallery is NOT built).
- **§8b infrastructure**: `psd_scan_index` ships the pooled-sample index, enabling the live client-side match/binarize the discovery scan needs.
- **Performance** (not in design, but unblocks everything): OOM fix + PSD cache.

### Still MISSING vs design (backlog)
- **§6 BandCandidate emission** — backend does NOT yet emit the BandCandidate object from `pipeline.py`/`bravo_service.py`. The whole contract to the (future) Closed-Loop Sim module. **Not started.**
- **§8b spectral feature-importance plot** — 5 Hz sliding-band-vs-PRO scan ({Pearson r, logistic/mixed AUC} vs band center 0–100 Hz, 8–30 Hz adaptive-valid shading). §8d notes `BiomarkerAnalytics.js:452` PSD-correlation panel is a PARTIAL starting point (extend, don't rebuild). **Not built.**
- **§8c one-tab collapse** — TD/PD/Both still separate `<Section>`s in `BiomarkerAnalytics.js`; sliding-window toggle still present (design says REMOVE). **Not done.**
- **§8e INSPECTOR column + semantic zoom** — right-hand per-channel full-res PSD/TD/LSB inspector + zoom-to-waveform are **only docstring comments in `BiomarkerDataTimeline.js`, NOT built.** Overview lanes exist; the detail half does not.
- **§8e EVENT overlay** — labeled "Higher/High/Lower Pain" snapshot markers on streaming/PRO axes. `psd_scan_index` + `_load_patient_events` plumbing exists; markers not rendered on the new timeline.
- **§8e PSD GALLERY** — separate figure of all montage+event PSD curves. **Not built.**
- **§4 LSB↔µV² conversion check** (FYI capability). **Not built.**
- **§8a-bis/§8c stream taxonomy in evidence** — `per_stream_n` gaining `indefinite`/`montage`/`td_derived`, `montage_prior`. Tied to BandCandidate emission. **Not started.**
- §10 open items unchanged: PD-mode param ranges; discovery-scoring headline (ROC/LASSO vs mixed-effects); stim-era heterogeneity test; PRO-day balance check.

---

## 7. Recommended NEXT STEPS (priority order)

1. **PI review of the 7 regression candidates (§5)** — fastest; decides what to walk back before more is built on top. Especially R1 (pain color), R4 (hidden ticks), R7 (old files still mounted).
2. **Event overlay on the new timeline (§8e)** — PI explicitly wanted events visible; plumbing (`psd_scan_index` + `_load_patient_events`) exists; highest user-visible value.
3. **Spectral feature-importance plot (§8b)** — extend the existing `BiomarkerAnalytics.js:452` PSD-correlation panel (add per-band AUC/logistic y-series, 8–30 Hz shading, feed Indefinite+on-demand-TD+Events). The design's headline "Discover" visual.
4. **One-tab collapse + remove sliding-window toggle (§8c/§8d)** — merge TD/PD Sections; contained refactor (33 decode-only state bindings, no display coupling).
5. **BandCandidate emission (§6)** — wire the schema out of `bravo_service`/`pipeline` (one per committed band). Unblocks the Closed-Loop Sim module.
6. **Inspector column + semantic zoom (§8e)** — the deferred detail half of the timeline.
7. **PSD gallery + LSB↔µV² check (§8e/§4)** — corroboration surfaces.

### Standing offers (raised, awaiting PI)
- Extend the warm-pool to **pre-load TD recordings** off the request thread for first-click clinic latency (the cold-start ~189 s is raw-TD disk I/O the PSD cache doesn't touch).

---

## 8. Key file map (Client/src/views/Reports/Biomarkers/)
- `index.js` (40 KB) — page shell; mounts BiomarkerDataTimeline (priority) → BiomarkerTimeline (fallback), BinarizationPreview, BiomarkerAnalytics. Slider/strategy/metric state; scanModel memo.
- `BiomarkerDataTimeline.js` (44 KB) — **NEW** §8e availability timeline (overview lanes only; inspector NOT built).
- `BiomarkerTimeline.js` (38 KB) — **OLD** linked stack; still mounted as fallback (R7).
- `BiomarkerAnalytics.js` (86 KB) — decode panels (ROC/dist/PSD-corr/scatter); NOT yet refactored (§8c/§8d).
- `BinarizationPreview.js` (24 KB) — live matched-sample histogram + per-group source boxes; "Matched neural samples" axis.
- `binarizationModel.js` (9 KB) — **NEW** client replica of backend match+binarize; `BIN_HI/LO/MID`, `computeMatchedScanModel`, per-source `by_source` counts.
