# Handoff — Biomarker Task B (full-spectrum exploration) + what's next

**Repo:** `shirvalkarlab/BRAVO_pain`  **Branch:** `PS_biomarker_module`
**HEAD:** `bc4b471` (pushed to origin). Author identity for commits:
`git -c user.name="Prasad Shirvalkar" -c user.email="prasad.shirvalkar@ucsf.edu" commit --author="Prasad Shirvalkar <prasad.shirvalkar@ucsf.edu>"`.

**Source of truth:** `DESIGN_biomarker_pipeline_v2.md` (artifact version_id
`bab71722-0293-453e-9d21-36b77a26cbac`). Read §8b/§8c before touching the scan.

---

## How to run / test (the dev loop)

- **Backend is in a Docker container**, NOT the local conda env. Edits to
  `BRAVO/...` take effect live via the bind-mount (gunicorn `--reload`).
- **Run anything in-container via the agent bridge** (the sandbox cannot reach
  the Docker socket):
  ```
  cd ~/dev/BRAVO_pain/BRAVO/_agent_bridge
  python3 bridge_client.py --cwd /usr/src/BRAVO --timeout N "<shell>"
  ```
  Long jobs (full decode / glmer) can exceed the client wait — the job keeps
  running in-container and writes `outbox/<jobid>.out`; poll for it.
- **Django won't import standalone** — set
  `DJANGO_SETTINGS_MODULE=BRAVO.settings; django.setup()` first, or run with
  `--cwd /usr/src/BRAVO/modules` for routine-only imports.
- **pytest is NOT installed in the container.** Tests are pytest-style
  functions; run them with a manual collector (import module, call every
  `test_*`). 95/95 currently pass. Test files:
  `BRAVO/modules/Biomarkers/tests/test_*.py`.
- **Frontend build** (needs `/usr/local/bin` on PATH):
  ```
  cd ~/dev/BRAVO_pain/Client
  export PATH="/usr/local/bin:$PATH"; export npm_config_cache=/tmp/npmcache
  env CI=false GENERATE_SOURCEMAP=false npm run build
  ```
  App served by **nginx on http://localhost/ (:80)** — NOT :27286 (that's raw
  uvicorn with a stale bundle). Current bundle: `main.7fcb5534.js`.
- **Real test participant:** uid `2e3c75c00d7f4f37b53a048d195f11da` (RCS08).
  Entry point: `bravo_service.run_for_participant(request_data)`.

---

## What Task B delivered (commit bc4b471)

The exploratory **spectral feature-importance** scan (DESIGN §8b), now running
over **all pooled full-spectrum PSDs per channel** (§8c), not just TD streaming.

### Backend — `routines/analytics.py`
- `spectral_feature_importance(td_detail, ...)` — 5 Hz sliding band 0–100 Hz,
  per channel: Pearson **r** vs continuous PRO + cross-validated logistic **AUC**
  vs binarized PRO, same band-center x-axis. Flags 8–30 Hz adaptive-valid band,
  returns per-band `peaks` + click-to-scatter `scatter`. Honors
  `td_detail["prelog"]` (mean-over-band when the feature is already log+z-scored).
- `matched_sample_counts`, `_binarize_labels`, `_cv_logistic_auc(x,y)->(auc,n)`.
- `band_mixedmodel_inference(...)` — **glmer logistic** (lme4 via pymer4),
  `pain_high ~ band_power + (1|cluster)`, cluster = weekly ISO era, band power
  z-scored. **Separation guard:** `|coef|>10` → returns `separation:True`, null
  OR/z/p, "widen the window" note. NOT yet called from the frontend (see Open).

### Backend — pooled PSD assembly + cache (`routines/streaming_psd.py`, `bravo_service.py`)
- `psd_rows_to_matrix` (cacheable: Welch+interp, depends only on recordings) /
  `build_pooled_detail_from_matrix` (cheap: z-score within (channel,source) +
  match-to-PRO, reruns per compute). `build_pooled_psd_detail` wraps both.
- `_assemble_psd_rows` — Welch over TD streaming + montage/survey for the 6 main
  bipolar pairs (`_MAIN_BIPOLAR`). Montage Data is `(n_samples, n_ch)` → transpose
  for `welch_psd_for_instance` which wants `(n_ch, n_samples)`.
- `_cached_psd_matrix` — npz under `DATASERVER_PATH/cache/biomarker_psd/`, keyed
  by `_psd_matrix_signature` (content hash of recording StartTimes + chan counts).
  **Warmed eagerly** off the request thread in `availability_for_participant`
  (`_PSD_WARM_POOL`) so it's on disk by the time the user clicks compute.
- `_compute_analytics` builds the pooled detail from the cached matrix + PRO
  match arrays; scan + matched counts run on it. `pool_meta` (per-source +
  per-channel breakdown) added to the td-analytics payload.

### Backend — time-window PRO↔PSD matching (`adapter.py`, `pipeline.py`, `bravo_service.py`)
- `align_pros(match_tolerance_min=...)` — nearest PRO within ±window (daily REDCap
  PROs carry real clock times via `date_time_s1_daily`); None → legacy same-day.
- `_match_tolerance_param` (default `DEFAULT_MATCH_TOLERANCE_MIN=15.0`),
  `_pro_match_arrays(pro_df, label_metric)`.

### Frontend (`Client/src/views/Reports/Biomarkers/`)
- `BiomarkerAnalytics.js`: new `SpectralFeatureImportance` component — per-channel
  dual-axis curve (r left / AUC right), 8–30 Hz shaded + labeled, **click a band**
  → band-power-vs-PRO scatter below. **Replaces** the 3 old TD panels
  (corr-spectrum, perm-null+scatter, mean-PSD). TD `<Section>` retitled
  "Full-spectrum exploration (all PSDs pooled per channel)".
- `BinarizationPreview.js`: match-window slider (1–120 min) + numeric field above
  the histogram; matched-neural-sample readout (N of M, high/low/excluded, median
  offset) with stale-recompute flag. New props: `matchTolerance`,
  `setMatchTolerance`, `matchedCounts`, `matchDirty`.
- `index.js`: `matchTolerance` state + `MatchToleranceMin` compute param; compute
  button relabeled "Start exploratory analysis" / "Recompute full-spectrum
  exploration" and **moved beneath the Pain Biomarkers box**.

### Deps (pinned `BRAVO/requirements.txt`)
`pymer4==0.8.2` + `seaborn`. **rpy2 is OS-level** (`apt python3-rpy2 3.5.15` —
the PyPI sdist fails to link its C extension in this image). R 4.3.3 +
`r-cran-lme4/lmertest/emmeans` installed via apt. **These OS deps are NOT in the
Dockerfile yet** — a container rebuild loses them (see Open).

---

## Key real-data findings (RCS08, to avoid re-deriving)

- PSD inventory vs 683 pain reports, matches at ±15m / ±60m / same-day:
  TD streaming (n=332) 6/37/328 · montage-survey (n=375) 5/57/362 ·
  chronic 10-min (n=420) 23/96/416 · **named patient events (n=185) 0/14/139**
  (authoritative metadata DateTime, "Streaming" excluded — they barely co-occur
  with daily surveys; a button-press ≠ a survey form-fill, so NOT a privileged
  source) · NeuralActivitySnapshot (n=319) `.date` is a processing stamp ~11 days
  off, tight-window counts artifactual.
- **Pooled** scan (TD + montage/survey, per channel): ±15m matches rise 6→26,
  ±60m→206. Cache build over all recordings ~1.2s; reload 0.002s.
- Coherent signal: peak |r| in **beta (20–32 Hz)** on all 6 main bipolar channels,
  mostly negative (higher beta → lower pain), AUC 0.75–0.83, inside the 8–30 Hz
  adaptive band. glmer on R 0⁻2⁺ @23.5 Hz: OR 0.12, p=0.066, no separation, n=32.
- **Decided (user):** event PSDs match the continuous PRO like every other PSD;
  their self-tag ("Higher/Lower Pain") is NOT used for scoring (timeline marker
  only). NeuralActivitySnapshot + event PSDs are EXCLUDED from the per-channel
  scan (reference-montage / per-hemisphere identities don't map to a bipolar pair).

---

## Requested UI changes — IMPLEMENT NEXT SESSION (from PI, 06-22)

These four were requested after Task B landed; none are built yet.

1. **Binarization preview should show match-window-gated data AVAILABILITY, not
   the raw PRO distribution.** Today `BinarizationPreview.js` histograms the daily
   PROs. Instead it should show *what neural data is available to binarize at the
   current match window* — i.e. the distribution of the **matched PSD subset**,
   and it must **update live as the match-window slider moves** (today the matched
   readout only refreshes on recompute, with a "stale" flag). Options: (a) a cheap
   client-side recount if the matched timestamps/labels are already in the payload,
   or (b) a lightweight endpoint that returns matched counts for a given tolerance
   without rerunning the full scan. The histogram bars should be the matched-PSD
   pain values, so moving the slider visibly changes how much data feeds binarization.

2. **Metric dropdown label** — `index.js:358`: change
   `"Pain metric (drives the pain plot above):"` →
   `"Pain metric (drives exploratory analysis):"`.

3. **Timeline plot — gray out non-binarized data, color the binarized data**
   (`BiomarkerDataTimeline.js`). Points/segments that are NOT matched-and-binarized
   render gray; the matched data that feeds binarization renders in color (e.g.
   high = vermillion `#D55E00`, low = blue `#0072B2`, excluded-middle = gray), so
   the user sees exactly which neural samples drive the analysis at the current
   match window. The timeline already has the gray idiom (`rgba(90,90,90,0.55)` at
   L323; `colorOf`/`eventColor` at L430) — extend it: the timeline needs the matched
   PSD timestamps + high/low/excluded labels for the current tolerance (same data
   item 1 needs), then color each marker by its bin and gray the unmatched ones.

4. **Titles** — two places:
   - In-card header `index.js:319`: `"Pain Biomarkers"` → `"Pain Biomarker
     Exploration"`.
   - Nav/breadcrumb name `routes.js:402` (`name: "Pain Biomarkers"`, the top-level
     "Biomarkers" the PI sees): → `"Biomarker Exploration"`.

---

## Open threads / next steps

1. **Wire `band_mixedmodel_inference` to the click-to-scatter.** The glmer is
   written, installed, and verified standalone, but the frontend scatter does not
   yet call it. When a band is clicked, fetch/show the mixed-effects OR + p (with
   the separation note) for that (channel, band). Needs a small backend endpoint
   or to include per-peak inference in the scan payload (cost: one R fit per call,
   ~seconds — do it on click, not in the scan loop).
2. **Dockerfile: pin the OS-level R stack.** Add to `dockerfile` (root):
   `apt-get install -y r-base r-cran-lme4 r-cran-lmertest r-cran-emmeans python3-rpy2`
   and `pip install pymer4==0.8.2 seaborn`. Without this a rebuild loses glmer.
   (rpy2 must be apt, not pip — C-link failure on arm64.)
3. **Snapshot/event PSDs into the scan (optional, flagged to user).** Currently
   excluded. If wanted, map their channels onto a bipolar pair or scan them as
   their own per-hemisphere lane.
4. **Binarization on the matched subset can collapse the middle** (e.g. ±60m gave
   144 high / 62 low / 0 excluded — narrow NRS range). Correct behavior, but
   consider surfacing "tertile cuts collapsed" when n_excluded_middle==0.
5. **Remaining DESIGN work** beyond Task B: §D empirical verifications (LSB↔µV²,
   stim-context era heterogeneity) and **§E the separate ClosedLoopSim module**
   (consumes the BandCandidate the biomarker module emits — schema finalized in
   DESIGN §6, not yet wired into `bravo_service`/`pipeline`).
6. **Scratch files** (17 untracked `opt*/live_review*/timeline_v2_preview` PNG/HTML
   + `RedcapImport*.py`) remain untracked by design — leave or clean.

## Gotchas
- `plt.savefig`-style lineage rules don't apply here (this is app code, not
  notebook figures).
- kaleido/Chromium can't spawn in the sandbox — render mocks with matplotlib if
  you need to verify Plotly layout/overlap offline.
- The bridge `_status.json` occasionally fails to parse mid-restart; a trivial
  `echo alive` confirms the watcher.
