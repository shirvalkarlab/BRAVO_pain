# BRAVO Pain Biomarkers — Session Handoff

> Single source of truth for continuing this work. Live as of commit `5b20c48` on branch
> `PS_biomarker_module` (`github.com/shirvalkarlab/BRAVO_pain`). Latest biomarker bundle
> `main.bf6ab33c.js`. Migrations through `0009_sourcefile_device_institute`.
> **§NOW (below) is the current state and supersedes §4–§9** where they disagree — those older
> sections (commit `f57e9c0` era) are kept as historical context for the science and architecture.

---

## NOW — current state (most recent sessions)

### Latest first: what to know before editing
- **Branch/commit:** `PS_biomarker_module` (latest = the biomarker-UI-enhancement commit below; the prior
  clean checkpoint was `f5f1794`), working tree committed (not yet pushed — `git push origin
  PS_biomarker_module` when ready). Latest biomarker bundle `Client/build/static/js/main.bf6ab33c.js`
  (was `main.3eec6e4f.js`).
- **Migrations:** leaf is `0009_sourcefile_device_institute`. `0007` (SourceFile.unique_hashed),
  `0008` (Recording.content_fingerprint), `0009` (SourceFile.device + SourceFile.institute) all apply
  cleanly in the harness. The container auto-runs `migrate` on start, so they should be applied on the
  user's MySQL — but this sandbox cannot reach Docker, so that has NOT been directly observed here.
  Verify with `docker compose exec bravo-server python3 manage.py showmigrations Server | grep -E "0008|0009"`
  (expect `[X]` on both).
- **Commit identity:** every commit uses per-commit `GIT_AUTHOR_*`/`GIT_COMMITTER_*` =
  `Prasad Shirvalkar <prasad.shirvalkar@ucsf.edu>` + trailer `Co-Authored-By: Claude (Operon)
  <noreply@anthropic.com>`. NEVER write global git config (`~/.config/git/ignore` "Operation not
  permitted" warnings on every git call are benign — ignore them).

### The Django app harness (KEY TOOL — the sandbox cannot reach Docker)
This sandbox **cannot reach the Docker socket** (orbstack socket → "permission denied"; container ops
are user-run only). To exercise the real upload/decode/insert code path without the container, there is
a **Django app harness** running the real models/migrations against throwaway SQLite:
- Env: **`bravo_app`** (py3.11; django 5.1.3, DRF 3.15.2, blosc2 3.3.3, cryptography, pywavelets,
  numpy/scipy/sklearn/pandas, + pytz/dateutil/pyjwt/whitenoise/boto3/specparam).
- Harness dir: `/tmp/bravo_harness/` — `harness_settings.py` (imports real `BRAVO.settings`, forces
  SQLite at `/tmp/bravo_harness/db.sqlite3`, sets `DATASERVER_PATH`), `repro.py` (decoder path),
  `repro_handler.py` (full `DataUploadHandler.post` via RequestFactory + force-auth).
- Run pattern:
  ```bash
  cd /Users/pshirvalkar/dev/BRAVO_pain/BRAVO
  PY=/Users/pshirvalkar/.operon/conda/envs/bravo_app/bin/python3
  export PYTHONPATH=/tmp/bravo_harness:$PWD DJANGO_SETTINGS_MODULE=harness_settings
  export DATASERVER_ENCRYPTION=$($PY -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())")
  export DATASERVER_HASHKEY=harnesshashkey FIBIT_CLIENT_ID="" FIBIT_CLIENT_SECRET=""
  rm -f /tmp/bravo_harness/db.sqlite3; rm -rf /tmp/bravo_harness/dataserver
  $PY manage.py migrate -v0
  $PY /tmp/bravo_harness/repro_handler.py   # or repro.py
  ```
  Real RCS08 JSONs (granted, read-only): `~/Library/CloudStorage/OneDrive-UCSF/Desktop/PNL/RCS008 jsons/`
  (11.5 MB `Report_JI Pacu_…20250716T222813.json`, 23 MB `…20250716T182401.json`, 66 MB
  `RCS08 - …20250904T142449.json`). NOTE: the harness measures SQLite timings; it proves
  correctness/dedup/query-shape but NOT absolute MySQL latency. **Biomarker unit tests run in the
  `rcs_v14_analysis` env** (see §2 below for the container path).

### Tests (run in `rcs_v14_analysis`, PYTHONPATH=…/BRAVO)
`PY=/Users/pshirvalkar/.operon/conda/envs/rcs_v14_analysis/bin/python3;
PYTHONPATH=/Users/pshirvalkar/dev/BRAVO_pain/BRAVO $PY modules/Biomarkers/tests/<NAME>.py`
— suites: `test_adapter`, `test_analytics`, `test_pipeline_stats`, `test_stats_utils`,
`test_process_redcap`. **All green** as of `5b20c48`.

### What shipped since `f57e9c0`

**Binarization redesign (DONE — §7-A is resolved):** default labeler is now **tertile** (33.3/66.7
pct, ambiguous middle dropped), with a **median** toggle ("keep every day") and **KMeans retired as
default** (still selectable for notebook parity). The cut is fit on the **daily PRO distribution** and
broadcast to per-sample rows. A **z-scored composite** (`composite_mpq_leftleg` = mean of z(MPQ-sum),
z(left-leg-VAS)) is offered. The user picks the metric/strategy in the UI; the backend does NOT
auto-select. Live **binarization preview** card recomputes client-side.

**Statistical-rigor batch (DONE):**
- `MAX_BIOMARKER_FREQ_HZ = 50.0` cap — bands ≥50 Hz excluded from selection everywhere
  (`select_biomarker_band`, `_band_inference` perm family, `corr_spectrum`). Rationale: the validated
  theta/alpha/beta/low-gamma sensing range (NOT a power-line argument — that was retracted).
- **MAD≥3 robust outlier rejection** applied at ALL correlation/threshold sources.
- **FDR-corrected** spectrum significance markers (BH q<0.05 over the displayed <50 Hz family).
- **Balanced-accuracy chance baseline = 0.50** always (not the majority fraction); `majority_accuracy`
  reported separately as reference.
- Parallel 4-track code review fixed: savgol even-window over-smoothing, PtConfig path-traversal
  confinement, token-exfil, 5 frontend null/NaN crashes; +9 regression tests.

**Upload pipeline (DONE — was the big arc):**
- **CSRF bug was why uploads did nothing** (`c4409fa`): all 14 FilePond uploaders read
  `document.querySelector('[name=csrfmiddlewaretoken]').value` UNguarded; the element doesn't exist in
  the SPA → `TypeError` BEFORE `request.send()` → request never sent, spinner forever. Fixed with the
  null-guard `session-control.js` already used. **This was the actual blocker.**
- **Slow-upload (on a populated DB) fixes:** the duplicate checks were un-indexable JSON-field
  full-table scans run once per recording. Now all index seeks: `SourceFile.unique_hashed` (0007),
  `Recording.content_fingerprint` (0008, a **deterministic** HMAC over the UNCOMPRESSED payload —
  note `saveSourceFile.hashed` hashes blosc2-COMPRESSED bytes and is **non-deterministic**, so it
  could never dedup), `SourceFile.device` + `SourceFile.institute` (0009, killed the last
  JSON_EXTRACTs). Harness-verified JSON_EXTRACT per upload 34–45 → **0**, dedup exact (re-upload adds 0).
- Dedup lock is now **per-hash** (`SourceFileDuplicateCheck_<hash>.lock`), not a single global lock —
  unrelated uploads no longer serialize.
- **Decode ~3.5× faster:** shallow per-stream dict copy (the deepcopy of multi-M-element sample lists
  was the cost) + `csv2floatarray` (np.fromstring) for the Sequences/PacketSizes/Ticks fields. Decode
  output verified **byte-identical** old-vs-new on all 3 RCS08 files.
- **Logging:** `django.db.backends` pinned to INFO (was emitting one DEBUG line per SQL query to a
  synchronous file) + a console handler added so app logs reach `docker logs`.

**This session's backlog clear (DONE):**
- Therapy/TherapyModification + institute dedup → indexed columns (0009); per-hash lock.
- Removed hardcoded demo password from `scripts/upload_percept_folder.sh` (now
  `BRAVO_UPLOAD_EMAIL`/`BRAVO_UPLOAD_PASSWORD` or `--email`/`--password`, required).
- `DataAnalysis.py` customized-analysis no longer leaks `str(e)` to the client (generic message +
  server-side traceback). (Upload-decode `str(e)` in `DataHandler` kept — user-actionable messages.)
- `stats_utils.block_length_for` uses **positive** lag-1 autocorr only (was `abs`) — anti-persistence
  no longer inflates block length / over-shrinks effective N. +test.
- **Chronic-trend sensing center frequency** wired end-to-end: `analytics.chronic_center_freqs(groups)`
  → `Session.decodeMedtronicJSON` stamps each chronic recording's `metadata['CenterFrequencyHz']` from
  the GROUP-level config → `_load_recordings` merges it onto the loaded dict → `_compute_analytics`
  emits `powerdomain.chronic_center_hz` → `BiomarkerAnalytics.js` shows it in the Power-domain subtitle.
  (Real RCS08: Left 10.74 Hz, Right 8.79 Hz.) +3 tests.
- Per-stream insert parallelization (old TODO): **measured and decided AGAINST** — blob writes are
  36 ms / 4% of decode, and ORM threads carry real risk. Removed the speculative import.
- WebSocket `/socket/notification`: confirmed a **missing feature** (HTTP-only ASGI, no Channels
  consumer), not a regression. Per decision, made it **fail quietly** (no console spam, no reconnect);
  `onmessage` kept so a future Channels+Redis backend works with no frontend change.

**Biomarker UI enhancement pass (DONE — bundle `main.3eec6e4f.js`):** acted on the user's review of the
Pain Biomarkers card. Frontend = `Client/src/views/Reports/Biomarkers/{index,BinarizationPreview,
BiomarkerAnalytics}.js`; backend = `modules/Biomarkers/routines/analytics.py` + `bravo_service.py`.
- **Typography & contrast:** left-panel "Pain metric" / "Binarization" labels enlarged (17px bold) and
  the Select/MenuItem option text to 16px; every light-gray caption (`color="text"`=#7b809a) across all
  three components switched to `color="dark"` (#344767) per the user "too light" note.
- **Binarization preview correctness (the important fix):** the card was labeling the RAW PRO report
  count "N daily PRO observations" (e.g. 679 reports ≠ days) AND computing its cut on the raw report
  list — disagreeing with the backend, which fits the cut on the **daily-mean** distribution
  (`adapter._threshold_pain_level`, `daily_broadcast=True`). `BinarizationPreview.js` now aggregates the
  report points to one value per calendar day (daily mean) before the cut, so the preview equals the
  detector. Header reads "N PRO reports across M days"; the Low/High/Excluded badges and the summary
  caption report BOTH day counts and raw-sample counts.
- **Per-signal + per-window ROC overlay:** ROC panel overlays one curve per bipolar contact (each AUC in
  the legend) plus a pooled black curve in "All contacts" view, and faint per-window ROC curves when a
  sliding window is active. Required a backend add: `sliding_window_analytics` now emits a downsampled
  per-window `roc:{fpr,tpr}` (test-fold, oriented AUC≥0.5, ≤60 vertices) on each window. +regression test.
- **Power-domain relabel + provenance:** power-domain panel titles/axes "LFP" → "Power" (the chronic
  trend is on-board band POWER, not streaming LFP); time-domain streaming-LFP labels left intact. Each
  power panel (ROC, distribution, sliding-window) now annotates the source channel + sensing center
  frequency (`powerProvenance` from `chronic_center_hz`/per-channel selection).
- **Sensing-config change markers:** `bravo_service._compute_analytics` now emits
  `powerdomain.sensing_config_changes` — a per-hemisphere, time-ordered list of `{hemi,t,center_hz,
  channel,changed[]}`, only when a real post-initial change occurs. The sliding-window-over-time panel
  draws a dashed vertical line + label at each change so a mid-record frequency/channel switch is clear.
- **Tests:** all Biomarkers suites green in `rcs_v14_analysis` (test_analytics incl. the new per-window
  ROC test, test_pipeline_stats, test_stats_utils, test_adapter, test_process_redcap). NOTE: the
  `sensing_config_changes` diff logic lives in the Django-coupled `bravo_service` and was not exercised
  on the live container (sandbox can't reach Docker) — verify on a real RCS08 run after a restart.

**Biomarker rigor + ROC/bar-plot follow-up (DONE — bundle `main.bf6ab33c.js`):** acted on the user's
second review of the same card. Same files + `routines/stats_utils.py`.
- **Permutation-null AUC on the bar plot (rigor ask):** the "Honest performance" bar plot's chance line
  was the ANALYTIC 0.5 (correct, but no empirical test). Added `stats_utils.auc_block_perm_null(score,
  labels, n_perm=1000)` — circular-block label permutation (block = lag-1 decorrelation timescale, reuses
  `block_length_for`/`circular_block_perm_matrix`), recomputes the direction-folded `max(AUC,1-AUC)` per
  shuffle via the rank identity (one `rankdata`, then vectorized), returns `{observed, p_value (add-one),
  null_q{p50,p95,p99}, n_perm, block}`. Wired into `pipeline.run_powerdomain_branch` as
  `summary["auc_perm"]` AND per-channel `ch_summary["auc_perm"]`. Bar plot draws a red dashed ceiling at
  the null 95th pct over the AUC bar + the empirical p in the caption. +regression test
  `test_auc_block_perm_null` (null p>0.05, signal p<0.01, observed==sklearn AUC, autocorr→block≥2,
  degenerate→None). This is the ONLY power-domain inferential test; balanced-accuracy chance stays the
  analytic 0.5 (verified invariant to imbalance).
- **ROC mean-of-contacts redesign:** Phase-3 had overwritten the per-window ROC with per-contact-only
  curves. Now: pooled view (All contacts / hemisphere) draws a BOLD MEAN ROC (vertical/threshold average
  onto a 101-pt FPR grid via `meanRoc()`) with the thin colored per-contact curves behind it; single
  contact draws just that curve. Per-window faint orange ROCs are overlaid in BOTH layouts whenever a
  sliding window is active (restored — the per-window curves were NOT removed from the backend, only the
  frontend had stopped showing them alongside the mean).
- **Bar-plot swarm:** in the pooled view with ≥2 split contacts, each bar carries jittered open dots
  (one per bipolar contact: in-sample AUC over bar 0, CV balanced acc over bar 1) so the bar reads as a
  mean over contacts. Bar plot moved to a numeric x-axis with `ticktext` to allow the jitter.
- **Sliding-window panel visibility bug (user: "only shows when sliding is OFF"):** root cause was the
  frontend gate `if (swWindows.length)` — with sliding ON + tertile labels, sparse one-class test folds
  get skipped, the windows array comes back empty, and the whole panel vanished (sliding OFF always
  yields one `_all_data_window`, so it showed). Backend was fine (41–93 windows on a 120-day synthetic
  run). Now renders whenever `swWindows.length || swSummary`; empty windows shows an explanatory message
  + the coverage caption instead of disappearing.
- **Change-markers REVERTED (user: "way too many vertical dashed lines"):** the
  `sensing_config_changes` overlay flagged nearly every recording (chronic center Hz wobbles per
  recording). Removed the change-marker shapes/annotations and the `configChanges` memo from
  `BiomarkerAnalytics.js`; the sliding-window-over-time panel is back to the clean dot-and-line, one dot
  per computed window. NOTE: the backend `sensing_config_changes` emit in `bravo_service` is still there
  (harmless, unused by the UI now) — a future change-detection that debounces the Hz wobble could reuse
  it. The earlier "draws a dashed vertical line at each change" claim is superseded by this revert.
- **Time-domain y-axis LFP→Power:** `BiomarkerTimeline.js` power-domain row was still labeled "LFP power"
  / unit "LFP (a.u.)" / title "Power-domain LFP power" — it plots `powerdomain_biomarker_value` (on-board
  band power). Now trace "Power", unit "Power (a.u.)", title "Power-domain band power".
- **Tests:** all 5 Biomarkers suites green in `rcs_v14_analysis` incl. the new `test_auc_block_perm_null`.
  Same Docker caveat — the `auc_perm` integration path and the panel changes were not run against the
  live container; verify on a real RCS08 run after `docker compose restart bravo-server` + hard refresh.

**Per-hemisphere ROC/swarm grouping + white-screen fix (DONE — see latest bundle below):**
- **White-screen-on-compute fix:** the previous pass crashed render with a temporal-dead-zone
  `ReferenceError` — the honest-perf bar block referenced `isPooled` before its `const` declaration
  (which sat further down in the ROC block). Hoisted `isPooled` (now superseded by the view-mode
  flags) to the derived-values area. Babel parse-check can't catch this (runtime, not syntax); only
  a render exercises it.
- **Live verification (saved RCS08 `queryBiomarkerAnalysis` JSON, read off disk):** confirmed
  per-window `roc:{fpr,tpr}` (60 vertices, endpoints 0→1) and per-channel ROCs are present and
  correct; `sliding_window.summary` showed `n_total=20, n_with_auc=4, n_skipped_test_one_class=11`
  (the sparse case the visibility fix covers). **`auc_perm` was ABSENT** — the running container still
  serves the pre-`d466cd0` backend (frontend bundle is live-mounted, Python is not auto-reloaded);
  `docker compose restart bravo-server` will surface it. The binarization-preview daily-aggregation
  fix and dual day/sample badges render correctly live.
- **per_channel is 8 mixed keys**, NOT just "Left/Right LFP": 2 chronic hemisphere AGGREGATES
  (`LeftHemisphere LFP`, `RightHemisphere LFP`) + 6 individual bipolar CONTACTS (`L 0⁻-2⁺`, … ,
  `R 1⁻-3⁺`), spanning two stimulation targets (Left GPi, Right VIM). Three contacts show AUC≈1.0 —
  the backend's own `powerdomain_pooled_warning` flags this as a batch/scale artifact, not real
  discrimination.
- **Per-hemisphere mean (user decision):** never draw a single grand mean (that would pool Left GPi
  with Right VIM). Backend `pipeline.py` now TAGS each per_channel entry with `summary.hemisphere`
  (Left/Right) and `summary.kind` (contact/aggregate). Frontend `BiomarkerAnalytics.js` groups by
  those tags (with a name-parse fallback for the un-restarted backend), and for each hemisphere in
  view draws a BOLD MEAN ROC (vertical average over that hemisphere's CONTACTS only, aggregates
  excluded) with the individual contact curves behind it. Toggle is now: All contacts · Left
  hemisphere · L-contacts · Right hemisphere · R-contacts.
- **Legend/draw order grouped by hemisphere, Left-then-Right** (never interleaved), per the user's
  standing principle. Left = blue family (`#56B4E9/#0072B2/…`), Right = orange family
  (`#E69F00/#D55E00/…`), each mean in the darkest shade; Plotly `legendgroup`+`legendgrouptitle`.
  Bar-plot swarm dots likewise: contacts only, ordered L-then-R, colored by hemisphere. **This
  grouping principle was committed to the `ps-scientific-visualization` skill (§"Legend Ordering —
  Group by Category, Never Interleave").**
- **Tests:** all 5 Biomarkers suites green (`rcs_v14_analysis`). Same Docker caveat — restart the
  container to load the tagged backend + `auc_perm`, then hard-refresh for the new bundle.
- **NEXT (queued, not yet done):** the TIME-DOMAIN "PSD correlation with composite" panel needs the
  same Left-then-Right legend grouping, AND its peak detection currently takes the max SIGNED peak,
  not the max-MAGNITUDE peak — so a large negative correlation loses to a small positive one. Fix to
  use `abs()` magnitude for the dominant-peak pick.

**Time-domain legend grouping, sliding default OFF, preview bins (DONE — see latest bundle below):**
- **Time-domain PSD-correlation spectrum legend** now grouped by hemisphere, Left-then-Right, with
  hemisphere color families (blue = Left, orange = Right; "Other" = green/pink last), Plotly
  `legendgroup`+`legendgrouptitle` per side — same principle as the power-domain ROC and the skill.
- **Max-MAGNITUDE peak: verified ALREADY CORRECT, no code change.** Audited every peak/argmax path:
  band selection (`pipeline.py:146`, `argmax(|corr|)`, since commit `0f735bd`), the ★ spectrum
  markers (`analytics.py` `find_peaks` on `absr`), and the peak-scatter (`argmax(absr)`) are all
  magnitude-based. Proof from the saved RCS08 payload: the time-domain headline selected
  `L 0⁻-2⁺ @ 26.7 Hz, r = −0.4526` — a NEGATIVE correlation that beat the strongest positive peak
  (+0.355); a signed-max bug would have picked the +0.355. Composite flows through the identical
  path (it only changes the label vector), so it's covered too. Added a code comment on the ★ trace
  noting peaks are strongest-|R| (positive or negative).
- **Sliding window now defaults OFF** (`index.js`: `useState(false)`).
- **Power-domain sliding-window-over-time panel hidden when sliding is OFF.** The backend returns a
  single `all_data:true` window when sliding=False; rendering a one-point "over time" line is
  meaningless, so the panel is suppressed unless there's a genuine sliding run
  (`slidingActive = !isAllDataOnly && (windows>0 || summary.n_total>1)`). The contact/hemisphere
  TOGGLE is unaffected — it's the power-domain Section `header`, gated only on `channelKeys>=1`, so it
  still shows with the SW panel gone. Section subtitle is now conditional on `slidingActive`.
- **"Window 2026-05-18" ROC mislabel explained + fixed:** it was NOT a contact — it was the last
  sliding window's per-window ROC overlay (pooled window starts were 2025-10-20 / 11-19 / 2026-04-03 /
  05-18). The per-window ROC overlay now also excludes `all_data` windows, so the date-labeled curve
  won't appear when sliding is off.
- **Binarization preview bins → fixed 0.2 width** (per user). Replaced Freedman–Diaconis auto-count
  with a constant `BIN_W = 0.2` anchored to a clean 0.2 grid (edges on …6.8/7.0/7.2…), 500-bin cap
  guard; removed the now-unused `chooseBins` helper.
- Tests: all Biomarkers suites green. Same Docker caveat (restart for tagged backend + `auc_perm`).

**Frequency-provenance fixes + power-domain timeline labeling (DONE — see latest bundle below):**
- **ROC/distribution/sliding provenance bug (user-reported):** the ROC annotation read "Right
  hemisphere (3 contacts) @ 28.3 Hz", but NO right contact recorded at 28.3 Hz — the right contacts
  recorded at 23.4 / 26.4 / 8.8 Hz. Root cause: the frontend `powerProvenance` fell back to
  `chronic_center_hz` (RightHemisphere=28.32, LeftHemisphere=26.37), which is the **chronic 10-min
  TREND's** fixed sensing frequency — a separate series from the per-contact streaming band power the
  ROC/distribution/sliding panels are actually computed on. Fix: pass `recorded_powers` into
  `BiomarkerAnalytics` (new `recordedPowers` prop from `index.js`) and build provenance from each
  plotted contact's OWN recorded `center_hz`. Now: single contact → that contact's Hz; hemisphere →
  the distinct recorded Hz across its contacts ("Right hemisphere (3 contacts) @ 8.8 / 23.4 / 26.4
  Hz"); pooled → per-side recorded Hz. Falls back to chronic Hz only if no recorded frequencies exist.
- **chronicHzText relabeled** to "Chronic 10-min trend sensing frequency (distinct from the
  per-contact recorded bands below)" so the chronic-trend value is never mistaken for the ROC bands.
- **Time-domain peak-scatter / spectrum verified CORRECT** — those titles use the streaming-PSD
  correlation peak frequency (`peak_scatter.peak_freq`), computed directly from the data, which is
  the right frequency for those panels (and legitimately differs from the chronic frequency).
- **Power-domain timeline plot now labeled (task 1):** the green "Power-domain band power" row plots
  the on-board band-power feature (`powerdomain_biomarker_value`) POOLED across all recorded contacts
  (the `powerdomain_pooled_warning` confirms it pools Left GPi + Right VIM into one raw-scale
  threshold; the series carries NO per-row channel/freq). Title now states what + frequency + range:
  "Power-domain band power @ <recorded Hz set> — N contacts pooled · range <min>–<max> a.u.", unit
  "Band power (device units, a.u.)", with a second annotation line naming the pooled contacts and
  recorded center frequencies.
- Both frequency lists now sort NUMERICALLY (were string-sorted).
- Frontend-only change except the (already-committed) per_channel hemisphere/kind tags. Tests still
  green. Same Docker caveat (restart for tagged backend + auc_perm; recorded_powers is already served).

**ROC drawn-vs-recorded count fix, swarm count fix, + a reusable provenance AUDIT tool (DONE — see latest bundle):**
- **ROC "3 frequencies / mean of 2 contacts" mismatch (user-reported):** the ROC panel reused the
  page-wide `powerProvenance`, which listed the recorded Hz for ALL contacts in a hemisphere — but a
  single-class contact (here `R 1⁻-3⁺` @ 8.8 Hz) has no ROC and is dropped from the curves and the
  mean. So "Right @ 8.8/23.4/26.4 Hz" disagreed with "Right mean of 2 contacts". Fixed: the ROC panel
  now builds its OWN provenance from `drawnByHemi` (only contacts with an ROC actually plotted), so
  the frequency list and contact count match the drawn curves. Caption notes single-class contacts
  are omitted.
- **Honest-performance swarm count:** the caption said "N contacts the bars average" with N = all
  contacts that have a summary, but Plotly drops the null-valued dots (single-class → no
  auc_in_sample; only 1 contact had a balanced_accuracy). Fixed: dots are plotted per metric only
  where the value is finite; `swarmContacts` is now the union of contacts that contribute ≥1 dot, so
  the count is honest. Also corrected the wording — the bar is the POOLED detector, NOT the mean of
  the dots.
- **NEW reusable reviewer:** `BRAVO/modules/Biomarkers/tools/audit_biomarker_payload.py` — runs
  against a saved `queryBiomarkerAnalysis` response JSON and reports label-vs-data inconsistencies
  (ROC drawn-vs-recorded frequencies/counts, chronic-vs-recorded provenance, swarm dot counts,
  per_channel hemisphere partition, AUC≈1.0 batch artifacts, sliding-window visibility, pooled-target
  warning). `python audit_biomarker_payload.py payload.json [--json]`; exit 1 on any ERROR so it can
  gate CI. This is the practical "visualization reviewer" — it checks the JSON that drives every
  panel (the sandbox can't see rendered pixels, but every issue surfaced so far has been a
  label-vs-data mismatch this catches). To use: in the browser Network tab, copy the
  queryBiomarkerAnalysis response to a file and run the script (or save it to
  ~/tempClaudeBullshit/ and point me at it).

### Current TODO (what's actually left — START HERE)
1. **REDCap field-map wiring** (§7-B, still open): wire `redcap_pull.py` processing into
   `redcap_client`/`bravo_service` so raw REDCap columns map to the tidy columns; field map in
   `pt_config/<pt>_config.json`. Until then, POST `ProcessedPRO` tidy dicts in the request.
2. **Deferred rigor** (§7-C, still open, touches verbatim science): per-target/per-source separation
   (the detector pools Left GPi + Right thalamus and Chronic+PowerDomain into ONE raw-scale threshold);
   **train-fold KMeans** (label leakage across folds — re-fit labeler inside each train fold);
   block-bootstrap CIs; a pre-specified confirmatory band test; the data-quality question (~170/284
   sessions zero/NaN PSD at the selected band).
3. **Verify on the live container:** the harness proves correctness on SQLite, but a sanity upload +
   biomarker run on the real MySQL/container after `docker compose restart bravo-server` is worth doing
   (esp. the chronic-freq and decode-vectorization paths, which touch decode/storage).
4. **Optional:** full Channels+Redis WebSocket implementation if live job-progress push is wanted
   (Redis is already in the compose stack); CodeRabbit re-run (needs consent — external API).

---

## 0. TL;DR

A **Pain Biomarkers** analysis module + card and a **Pain Scores** report were added to a fork of the
UF BRAVO platform, run **locally in Docker (OrbStack)**. It now runs on **real patient data (RCS08)**.
The most recent work was a **statistical-rigor pass** + a **plot review** that made the analysis and
its figures honest.

**Headline scientific result (RCS08):** after correcting for the band search and temporal
autocorrelation, **neither biomarker branch is statistically validated** — the time-domain beta
correlation is not significant (permutation p≈0.62, FDR q≈0.23) and the power-domain detector's
in-sample AUC≈0.79 does not generalize (cross-validated balanced accuracy≈chance) and carries a
merged-source batch confound. This is an honest negative/exploratory result, surfaced clearly on the
card. See §5.

---

## 1. Environment (CORRECTED — read this, the old paths are wrong)

- **Repo (USE THIS PATH):** `/Users/pshirvalkar/dev/BRAVO_pain`
  - ⚠️ The original handoff said `~/Documents/GitHub/BRAVO_pain` (OneDrive) — that copy corrupted
    (OneDrive dehydrates files mid-session). The repo was re-cloned to `~/dev/BRAVO_pain`. Work ONLY here.
- **Docker = OrbStack**, not Docker Desktop. Context `orbstack`. If `docker` commands fail with a
  socket error, run `open -a OrbStack` and wait for `docker info` to succeed before retrying.
- **Containers** (compose project `bravo_pain`): `bravo_pain-bravo-server-1` (Django+gunicorn+uvicorn+nginx),
  `bravo_pain-mysql-1`, `bravo_pain-redis-1`.
- **Server stack:** gunicorn with `-w $(nproc)` uvicorn workers (multi-worker ASGI; the old
  single-threaded `runserver` is gone — the slow-upload issue below is largely resolved).
- **Ports:** the app is at **http://localhost/** (port **80**, nginx — serves the React SPA from the
  live-mounted `Client/build` and proxies `/api`). **Port 27286 is raw uvicorn** (the ASGI app / API),
  which serves Django's *collected* static — do NOT eyeball the UI there, it serves a stale bundle.
  Use **http://localhost/** for the real, current frontend.
- **Git:** branch `PS_biomarker_module`. `git push origin PS_biomarker_module` works. Main/PR base
  in this fork has been `v3.0.0-alpha`.
- **Reference notebooks** (the science of record): `git clone https://github.com/shirvalkarlab/dbs_stage2_percept`.
  Key files: `threshold_biomarker.ipynb` (power-domain), `biomarker_analysis_streaming.ipynb`
  (time-domain), `redcap_pull.py` / `full_trend_pain_score.ipynb` (PRO metrics + stages).

### Secrets (NEVER commit)
- `secrets/redcap.env` is gitignored. REDCap tokens also live at `~/.bravo/redcap_api_info.json`
  (perms 600). Active = Percept token `3AF88F28…`. Do not echo or commit these.

---

## 2. Dev workflow

- **Python is live-mounted** (`./BRAVO` → `/usr/src/BRAVO`). gunicorn runs `--reload`, but it is
  occasionally stale — **`docker restart bravo_pain-bravo-server-1`** after backend edits to be safe.
- **React requires a rebuild** (the served bundle is `Client/build`, live-mounted into nginx). Host
  Node is new enough now (v24):
  ```bash
  cd /Users/pshirvalkar/dev/BRAVO_pain/Client && npm run build
  ```
  Then **`docker restart bravo_pain-bravo-server-1`** (OrbStack's virtiofs mount can lag — nginx may
  serve a stale `index.html` until the container restarts) and hard-refresh the browser.
  Verify the served bundle matches the build:
  ```bash
  curl -s "http://localhost/?cb=$(date +%s)" | grep -oE "main\.[a-z0-9]+\.js" | head -1
  grep -oE "main\.[a-z0-9]+\.js" Client/build/index.html | head -1     # must match
  ```
- **Tests** (all pass) — run each inside the container:
  ```bash
  docker exec -w /usr/src/BRAVO bravo_pain-bravo-server-1 python3 -W ignore \
    modules/Biomarkers/tests/<NAME>.py
  ```
  Suites: `test_adapter.py`, `test_process_redcap.py`, `test_stats_utils.py`,
  `test_pipeline_stats.py`, `test_analytics.py`.
- **Live-verify a run** without the browser (exercises the real code path):
  ```bash
  docker exec -w /usr/src/BRAVO bravo_pain-bravo-server-1 python3 -W ignore manage.py shell -c "
  from modules.Biomarkers import bravo_service; from Server import models
  p = models.Participant.find(name='RCS08')
  out = bravo_service.run_for_participant({'ParticipantId': p.uid, 'source':'both'})
  print(out['summary']['timedomain']); print(out['summary']['powerdomain'])"
  ```
- **Browser verification** (Claude-in-Chrome / computer-use): the user is already logged in; navigate
  http://localhost/ → Database → RCS08 → "Pain Biomarkers" → select **Both** → **Compute** (~10–40 s).
  NOTE: clicking the source toggle re-renders and can swallow an immediately-following Compute click —
  click Compute as a *separate* action. The MCP screenshot captures ~1092 px wide regardless of window;
  use JS (`document.scrollingElement` / `scrollIntoView` / read `.js-plotly-plot[].data`) to verify
  off-screen panels rather than trusting screenshot width.

---

## 3. What exists (architecture map)

### Backend — `BRAVO/modules/Biomarkers/`
- `routines/streaming_psd.py` — time-domain PSD↔pain (transform/correlation **verbatim** from the
  streaming notebook). `pearson_corr_psd_label` computes the (channel×freq) corr/p grid.
- `routines/threshold_biomarker.py` — power-domain sliding-window LFP threshold detector +
  **`kmeans_pain_level`** (the 2-cluster KMeans pain labeler) — **byte-for-byte** from the notebook.
- `routines/redcap_client.py` — REDCap PRO pull (PyCap; token via env). `process_redcap` (NaN-preserving).
- `routines/analytics.py` — all figure data: `corr_spectrum`, `psd_spectra`, `psd_spectrogram`,
  `td_sliding_corr_spectrum`, `sliding_window_analytics`, `roc_analysis`, `lfp_distribution`,
  `cluster_scatter`, **`pain_binarization`** (new), `format_channel()`.
- `routines/stats_utils.py` — **NEW (rigor)**: `bh_fdr`, `fisher_z_ci`, `lag1_autocorr`,
  `effective_n`, `partial_corr`, `block_length_for`, `circular_block_indices`,
  `circular_block_perm_matrix` (vectorized), `block_perm_pvalue`, `balanced_metrics`. Pure numpy/scipy.
- `adapter.py` — recording dicts → routine inputs; PRO alignment; `bravo_chronic_to_lfp_df` (the merged
  power-domain tidy frame + KMeans label, z-scored features); MAD outlier rejection; plot decimation.
- `pipeline.py` — `run_biomarker(source="timedomain"|"powerdomain"|"both", …)`; per-branch runners;
  `select_biomarker_band` (FDR-gated), `_band_inference` (the honest TD stats),
  `_maxabs_corr` + `_block_perm_maxcorr_pvalue` (vectorized permutation null).
- `bravo_service.py` — Django glue: `run_for_participant`, `_compute_analytics`, `_region_map`
  (infers contact region from **device metadata**), `_recorded_powers`, window params.
- API: `BRAVO/Server/APIs/DataAnalysis.py` → `/api/queryBiomarkerAnalysis`, `/api/queryPainScores`.

### Frontend — `Client/src/views/Reports/`
- `Biomarkers/index.js` — the card: red **Compute** button (recompute only on click) + progress
  indicator, source toggle, **pain-metric selector**, window/step (months) controls, and the honest
  **summary block** (perm p / FDR q / effective n / CI / overfit + batch + pooled warnings / label
  provenance). Route `/reports/biomarkers/:participant_uid`.
- `Biomarkers/BiomarkerTimeline.js` — stacked-subplot timeline (TD biomarker, LFP+threshold, pain, stim).
- `Biomarkers/BiomarkerAnalytics.js` — the plot panels, in three sections: **"How the pain score is
  binarized"** (new, top), **Time-domain analysis**, **Power-domain analysis**.
- `PainScores/` — Pain Scores report (per-metric grid, normalized overlay, correlation heatmap,
  trial-stage bands). Route `/pain-scores/:participant_uid`.

### Local-dev auth / permissions (DEBUG only; production untouched)
- `Server/authentication.CsrfExemptSessionAuthentication` (login 403 fix).
- DEBUG bypass in `Database.checkManagePermission` and `Server/models/User.Institute.has_permission`
  (so a localhost instance never blocks edits/deletes/uploads). Authentication still required.

---

## 4. What changed in the rigor + plot sessions (the recent work)

Commits (newest first):
- `f57e9c0` top **pain-binarization** histogram + sticky-navbar `scroll-margin`.
- `91e2456` plot review v2 — remove mains band, **label the pain score on every panel**, permutation +
  overfit plots.
- `de90195` plot review — hover-on-demand (no fixed labels), peaks tied to curves (legendgroup), cleanups.
- `1204e63` **fully vectorize** the block-permutation null (~12× faster, float-identical).
- `0f735bd` **statistical-rigor pass** — honest inference + reporting.
- `47d0b34` DEBUG-only permission bypass.

### Rigor fixes (all live-verified on RCS08)
1. **Two root-cause bugs** that had inflated significance:
   - **TD recordings were ~47% out of time order** → daily-pain lag-1 autocorrelation collapsed from
     its true ~0.86 to ~0, silently neutralizing every serial-dependence correction. Fixed by
     time-sorting sessions in `run_timedomain_branch` (this also fixed the spectrogram time axis).
   - The family-max **permutation null ran on the raw-PSD grid while r/FDR used the feature grid** →
     it tested a different, spuriously-stronger cell. Fixed with a NaN-aware pairwise feature-grid
     `_maxabs_corr`; perm p went 0.001→~0.6 and now *agrees* with the independent FDR.
2. **Effective-N FDR** (`_autocorr_adjusted_pgrid`) drives band selection + `fdr_significant`.
3. **Honest TD summary**: perm p (headline), FDR q, effective n, Fisher-z CI + caveat, stim-adjusted
   partial r + provenance note, selection-bias flag, narrow-peak (instrumental-line) warning.
4. **Honest power-domain summary**: balanced accuracy vs chance/prevalence, **directed** in-sample AUC,
   **overfit warning** (in-sample AUC vs CV balanced accuracy), **batch-confound diagnostic**
   (undirected source↔LFP and source↔pain separation), KMeans-label provenance + Spearman, pooled-
   targets warning.
5. **Permutation fully vectorized** (`circular_block_perm_matrix` + `_block_perm_maxcorr_pvalue`):
   all permutations as matrix ops; float-identical to the loop, ~12× faster; empirically calibrated.

### Plot review (BiomarkerAnalytics.js + analytics.py)
- **Removed the "mains ~60 Hz" caution band** and `mains_region_warning` — the device is an implanted
  IPG, not wall-powered, so there is no line-noise reference.
- **Pain score labeled on every correlation/AUC/ROC/PSD panel** (title + axis say e.g. "NRS (0–10)").
- Correlation spectrum: **no fixed per-peak labels** — values on hover; ★ peak markers **color-paired
  and legendgroup-linked** to their curve (deselecting a curve hides its stars).
- **NEW permutation-null panel** (directly under the spectrum): histogram of the family max|R| under
  block-shuffled pain, observed value marked, p-value + plain-language caption.
- **NEW power-domain "honest performance" bar**: in-sample AUC vs CV balanced accuracy vs chance.
- **ROC downsampled** to ≤400 plotted vertices (AUC still on full data).
- **`cluster_scatter` made generic** over the actual KMeans feature(s) (was hard-coded to
  left_leg_vas/mpq_sum → silently empty for single metrics); de-duplicated to unique PRO observations.
- **LFP-distribution histogram** binned over the robust 1st–99th percentile (the un-normalized merged
  sources span ~−20k…146k device units with sparse outliers and collapsed it to one bar).
- **NEW "How the pain score is binarized" section (top)** — see §6.

---

## 5. Key scientific findings (carry these forward)

- **RCS08, NRS:** TD best band r=0.36 @ 23.7 Hz (Left GPi) — **not significant** (perm p≈0.62,
  FDR q≈0.23, effective n≈70 from n=114). Power-domain in-sample AUC≈0.79 but **CV balanced
  accuracy≈0.52 ≈ chance (0.59)** → does not generalize; plus a **batch/scale confound** (the merged
  Chronic + per-session Power-Domain sources are separable by LFP scale ≈0.79 and differ in pain
  prevalence ≈0.68, so the pooled AUC partly measures *which sensing modality*, not pain).
- **NRS is heavily skewed high** for this patient: the KMeans binarization cut lands at 6.4 — the
  **12th percentile** (82 low / 596 high of 678 days). The high/low split is very imbalanced.
- Memory notes (in `~/.claude/projects/-Users-pshirvalkar-dev-BRAVO-pain/memory/`):
  `biomarker-rigor-finding.md`, `biomarker-deferred-rigor.md`.

---

## 6. The binarization panel (context for the open question below)

`analytics.pain_binarization(cv_df, label_metric, kmeans_features, pro_df)` → for the **selected** pain
score (any metric; two panels for the composite), returns the raw daily-PRO value distribution, the
**empirical** high/low decision boundary derived from the *actual* labels, the percentile that boundary
lands at, and 30th/70th percentile references. The frontend renders overlaid low/high histograms with
a solid "cut" line + dotted percentile lines, at the top of the analytics.

**Important:** the labeler is the notebook's **2-cluster KMeans** (`kmeans_pain_level`), NOT a fixed
percentile. The panel shows where the KMeans cut lands (and annotates its percentile) — the 30th/70th
lines are reference context only.

---

## 7. TODO / handoff items

### A. Binarization (Prasad's open design question — START HERE)
- [ ] **Add a percentile-based binarization option** (e.g. user picks a percentile cut, or a
      two-threshold low<30th / high>70th scheme with the middle excluded). Today the only labeler is
      2-cluster KMeans on z-scored feature(s) (`kmeans` strategy) with a `median` `cutoff` fallback.
      Wire a `label_strategy="percentile"` (+ percentile params) through
      `adapter.bravo_chronic_to_lfp_df` → `_resolve_biomarker_metric` → the card, and surface it in the
      pain-metric / binarization UI. `pain_binarization` already reports percentiles, so the panel is ready.
- [ ] **DECISION for Prasad:** what is the most robust / rigorous way to binarize these PROs? KMeans
      (data-driven but unstable + imbalanced here — 88% "high"), fixed percentile (transparent but
      arbitrary), median, or a tertile (drop the ambiguous middle)? And **does a 2- vs 3-metric
      composite binarization make more sense** (e.g. NRS + MPQ + Left-Leg-VAS) than a single metric?
      The skew (NRS cut at the 12th pct) and the imbalance/overfit findings make this the highest-leverage
      methodological choice. Consider per-target / per-source labels too (see C).

### B. REDCap field-map wiring
- [ ] Wire `redcap_pull.py`'s processing (filter instrument + pivot) into `redcap_client`/`bravo_service`
      so raw REDCap column names map to the tidy columns (`nrs`, `vas`, `left_leg_vas`, `back_vas`,
      `relief`, `mpq_sum/aff/sen`, `date_time_s1_daily`, …). Field map lives in
      `pt_config/<pt>_config.json`. Until wired, you can POST `ProcessedPRO` (tidy dicts) in the request.
- [ ] Trial **stages**: pass `Stages` or derive from `pt_config.program_dates` server-side.

### C. Deferred rigor (larger / touch verbatim science — see `biomarker-deferred-rigor.md`)
- [ ] **Per-target / per-source separation:** the power-domain detector pools Left GPi + Right medial
      thalamus and Chronic vs Power-Domain sources into ONE raw-scale threshold (flagged by the pooled +
      batch-confound warnings). Fit/report per target & per source, or z-normalize per source before merge.
- [ ] **Train-fold KMeans:** `pain_level` is KMeans over the WHOLE series → label leakage across the
      sliding-window folds. Re-fit the labeler inside each train fold (touches verbatim `kmeans_pain_level`).
- [ ] **Block-bootstrap CIs** for the detector metrics (sens/spec/balanced accuracy), not point estimates.
- [ ] **Pre-specified confirmatory band test** (e.g. beta-only on GPi) to avoid the ~600-cell multiple-
      comparison penalty that is killing TD power.
- [ ] **Data-quality:** at the selected TD band, ~170/284 sessions have zero/NaN PSD (n drops 284→114).
      Investigate why so many sessions are zero at that frequency.

### D. Smaller / verify
- [ ] Slow Percept uploads (~73 MB "spin"): the multi-worker ASGI likely fixed this — confirm; if not,
      offload decode to `modules/AsyncJobScheduler`.
- [ ] Re-run CodeRabbit (CLI not installed here; sends diffs to an external API — get consent for
      patient-research code before enabling).

---

## 8. Gotchas (things that cost time)
- **OrbStack mount lag:** after `npm run build`, nginx may serve a stale `index.html` until the
  container is restarted. Always restart + verify the served hash (§2).
- **Port 27286 is uvicorn, not the app** — its static is stale; use http://localhost/ (nginx :80).
- **gunicorn `--reload` is sometimes stale** — restart after backend edits.
- **MCP screenshots cap ~1092 px** regardless of window width → "content cut off at right" / "navbar
  mid-screen with blank gaps" are *capture artifacts*, NOT layout bugs (verified: `overflowX=0`,
  standard `position:sticky` navbar). Don't chase them; verify layout with JS.
- **Verbatim-science invariant:** `run_sliding_window_dual`, `kmeans_pain_level`,
  `_find_best_threshold_for_metric`, and the streaming transform/correlation funcs must stay
  byte-for-byte. Only glue/orchestration/visualization changes.
- **Region names come from device metadata** (`_region_map`), not a static map. RCS08 = Left GPi +
  Right medial thalamus (the "Percept Benchtop" device + its orphaned electrodes were deleted).

---

## 9. Quick API smoke (session/cookie path)
```bash
J=/tmp/j; curl -s -c $J -b $J -X POST -H 'Content-Type: application/json' \
  -d '{"Email":"<your-login>","Password":"<your-pw>"}' http://localhost/api/login
# RCS08 uid: 1eda36458758461383721208bbe6bb87
curl -s -c $J -b $J -X POST -H 'Content-Type: application/json' \
  -d '{"ParticipantId":"1eda36458758461383721208bbe6bb87","source":"both"}' \
  http://localhost/api/queryBiomarkerAnalysis | head -c 800
```

---

## Appendix — original handoff (foundation; some facts superseded above)

> From commit `6f119f6`. Kept for the "what we built" foundation. **Superseded:** repo path is now
> `~/dev/BRAVO_pain` (NOT `~/Documents/GitHub`); the server is multi-worker gunicorn+uvicorn (not
> `runserver`); React builds with host `npm run build` (not the Node-16 docker one-liner); the module
> is no longer "library mode only" (it has the Django endpoint + React card).

- **What we built (foundation):** the Biomarkers module (`routines/` verbatim science, `adapter.py`,
  `pipeline.py`, `bravo_service.py`), the DRF APIs (`QueryBiomarkerAnalysis`, `QueryPainScores`), the
  React **Pain Biomarkers** card and **Pain Scores** report, and local-dev auth relaxations (DEBUG only).
- **Demo participant** (synthetic; still works): MRN `DEMO_BIOMARKER`,
  uid `e30b54dc17d3488dbe1945bb911f5549` — any participant with that MRN returns synthetic demo data.
- **REDCap env:** set `REDCAP_API_URL` / `REDCAP_API_TOKEN` on the `bravo-server` service (compose) for
  live PRO pulls; otherwise only demo data flows.
