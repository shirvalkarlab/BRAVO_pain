# BRAVO_pain — Mega Handoff (consolidated)

> **Purpose.** This is the single authoritative reference for the BRAVO_pain closed-loop
> DBS platform. It synthesizes the 7 per-session handoff documents (2026-06-24 →
> 2026-06-25), the frozen PSD→LSB conversion model (`RCS08.json`), and the most recent
> commit (`e9d7a80`). Read this to be fully current. Where two sources conflicted, the
> chronologically later one wins and the supersession is noted inline.
>
> **Synthesized sources (chronological):**
> `SESSION_HANDOFF_20260624T053839Z` · `…064004Z` · `…210017Z` · `…220917Z` ·
> `…20260625T011910Z` · `…020620Z` · `…070628Z` — plus
> `BRAVO/modules/Biomarkers/data/psd_lsb_models/RCS08.json` and commit `e9d7a80`.
> (Two intermediate exploration sessions — `…20260624T231204Z` and the first half of the
> 06-25T01:19 session — are referenced by the chain but were analysis-only and produced no
> separate authoritative handoff; their conclusions are folded into §2/§3 below.)

---

## 0a. Session 2026-06-27 (continued, 2nd half): Spectral scan → CS-1…CS-4 + timeline display fixes

**Branch:** `PS_closedloop_deployment`. **Suite:** 227 → **233** (all PASS, 0 FAIL).
Extends the first half (§0b below) with four phases completing the "unify timeline and spectral" plan.

### Phase 0 — Timeline display fixes (`94343e8`)
- **Relabel modeled diamonds** (`BiomarkerDataTimeline.js`): hover text now reads the actual DSP route from `m.method` — "transform DSP ×352.62" or "PSD→LSB bridge ×73.63" per point. Old stale "survey PSD ×269" label removed everywhere except an explanatory comment.
- **Ungate per-rating modeled markers**: CS-4 hollow circles/diamonds were trapped inside `if (ov)` and borrowed its y-scale — drawing never happened for streaming-only lanes. Moved to an independent sub-lane scale outside `if (ov)`. Native filled circles dropped (native LSB already shown as the colored lane time series); TD-transform → hollow circle, PSD-bridge → hollow diamond.

### Phase 1 — Shared per-pair full-spectrum LSB cache (`09bc91b`)
- **`availability.per_pro_lsb_spectrum()`**: generalization of `per_pro_lsb` to a full 0–100 Hz band-center grid in ONE vectorized call per matched (channel, PRO). Source preference decided once per pair: TD-transform route (`td_transform_band_power × k=352.62`) when any TD-bearing recording covers the rating; CS-3 bridge (`device_psd_band_power × k≈73.63`) for PSD-only patient events (full 0–100 Hz, per-band `calibrated` flag). TD-transform `calibrated=True` everywhere (k=352.62 band-agnostic); bridge `calibrated=False` outside [7.8, 30] Hz (exploratory).
- **`bravo_service._pro_lsb_spectrum_cached()`**: content-signature-keyed in-process memo (max 8, FIFO eviction). Signature = participant + PRO-set sha1 + recording identities + band-center grid. Both `_build_availability` (timeline) and `run_for_participant` (spectral scan) call the same function — guaranteed identical numbers at any shared center. `_build_availability` emits `pro_lsb_spectrum` in payload (success + error path).
- **Routing (per PI 2026-06-27):** `td_recordings = td_list + psd_list` (all 250 Hz TD-bearing products — streaming + montage/survey); `event_psd_blocks = PatientControllerEvent FFT only` (PSD-only, no TD). Montage PSDs never reach the bridge.

### Phase 2 — Rewire spectral scan; remove k=269 + device_psd_scaled (`d1d3d3e`)
- **`streaming_psd.build_pooled_detail_from_matrix`**: REMOVED `psd_abs_uv2_per_hz`, `device_psd_scale_by_channel`, `Xabs`, `device_scale`, `psd_abs_stack` (~65 lines). `row_lsb_tier` now emits `td`/`survey`/`patient_event` (no more `device_psd_scaled`/`uncalibrated`).
- **`analytics.spectral_feature_importance`**: new `pro_lsb_spectrum_by_channel` kwarg. When provided, `feature="lsb"` reads `log10(cache[channel][pro_i]["lsb"][ci_cache])` per (channel, band) instead of integrating Welch density × 269. `feature_used` now `"lsb_cs14"`. Falls back to `"logpsd_db"` when cache absent (back-compat callers). Source priority (TD > survey > device_psd_scaled demotion loop) REMOVED — the cache already enforces TD-first per pair.
- **`bravo_service.run_for_participant`**: builds the spectrum cache at compute time (memo hit in the common case); threads `pro_lsb_spectrum_by_channel` through `_compute_analytics` → `spectral_feature_importance`.
- **Tests (3 rewritten → 3 new):** `test_spectral_scan_lsb_feature_cs14_td_and_full_spectrum`, `test_spectral_scan_lsb_cs14_cache_lookup_per_pro`, `test_builder_no_device_psd_scale_in_detail`.

### Phase 3 — Caption fixes + code review fix (`cca1241` + `25bbab5`)
- **Caption (`BiomarkerAnalytics.js`)**: match_direction 3-way (pro_first was falling into forecasting arm — fixed); survey-reuse wording corrected for pro_first; td_welch → CS-14 feature note; device_psd_scale block removed; double-dipping warning suppressed for `pro_first` (AUC grouped by rating, multi-PSD/rating intentional).
- **Code review fix (`25bbab5`)**: `isLsb` and section subtitle now OR-gate `"lsb_cs14" || "lsb_calibrated"` — `lsb_cs14` axis labels, hover templates, Cohen's d wording, and section description all update correctly.

**Commit chain (this sub-session):** `94343e8` → `09bc91b` → `d1d3d3e` → `cca1241` → `25bbab5`  
**HEAD:** `25bbab5` (synced to `origin/PS_closedloop_deployment`)

### Key constants (unchanged from Phase 0b)
`LSB_PER_UV2_TRANSFORM = 352.62` · `LSB_PER_DEVICE_PSD ≈ 73.63` · `LSB_VALIDATED_HZ_LO = 7.8` · `LSB_DEPLOYABLE_HZ_HI = 30.0`

### Open threads carried forward
- Anchor test for "timeline circle == spectral point at same center" not yet a live test (deferred — the identity holds by construction but has no E2E test across the two call sites).
- Track B audit backlog items [5]/[14]/[42]/[49] remain open; [14] needs PI judgment.
- Scratch probes in `BRAVO/_agent_bridge/` (`_per_pro_test.py`, `_overlay_test.py`, `_cs4_test_run.py`, etc.) — not production code.

---

## 0b. Session 2026-06-27 (first half): TD→LSB calibration deployment (CS-1…CS-4)

Took the lab's `percept-spectral-repro` "transform" DSP and made it the **primary TD→LSB source of
truth** end-to-end, then built the per-PRO LSB deployment selection on top. Branch
`PS_closedloop_deployment`, off `e164a7d`. **Suite 184→227** (all in-container
`python3 _agent_bridge/run_tests.py`). Each phase ran the code-review agent (correctness +
vectorization + dead-code mandates) before commit. Commits this session (all pushed through `15a87d5`;
CS-4 `beb2c97` local at the time of writing):

| Phase | Commit(s) | What |
|---|---|---|
| CS-1 | `7ea8f6d` + `ebc3000` | Vendored the transform DSP into `analytics.py` (`td_transform_band_power`, `td_to_lsb`, `_rcs_hann`); **`LSB_PER_UV2_TRANSFORM = 352.62`** (RCS08 all-stim median k, r=0.9927) is now the PRIMARY TD→LSB; demoted welch256×269 to a PSD-exploration backup. Switched `availability.lsb_series` modeled tier to the transform. Fully vectorized (strided window matrix → one batched rFFT → band-mask matmul → median). Review fixes: scoped the "k cancels in r/AUC" claim to single-source features, fail-closed Missing guard. |
| CS-2 | `ca7735e` + `b1adebd` + `e164a7d` | **PSD-source taxonomy.** `PSD_SOURCE_TAXONOMY` (patient_event / streaming_event / montage_snapshot) separates POOLING identity from DISPLAY category. Removed `_EVENT_NAME_EXCLUDE` (Streaming was hard-dropped); Streaming is now its own timeline category, not mislabeled "Montage PSD". Frontend `BiomarkerDataTimeline.js`: labeled events → diamond row, Streaming → per-lane ticks + count. |
| CS-3 | `f4d821a` + `3c438d5` + `15a87d5` | **PSD→LSB bridge** for PSD-only patient-triggered snapshot events. Found event `FFTBinData` is LINEAR µV magnitude (= survey `LFPMagnitude`), baseline-subtracted (≈⅓ bins negative → clamp to 0). Montage TD↔PSD law: **PSD_bp = 4.789·TD_bp** (geomean, r=0.987, n=10476 contact-band points). Compose: **LSB = (352.62/4.789)·PSD_bp = 73.63·PSD_bp** (`LSB_PER_DEVICE_PSD`). Helpers `clamp_device_psd`, `device_psd_band_power`, `device_psd_to_lsb`; `lsb_series` bridge tier (psd_modeled, restricted to [7.8,30]). Review caught + fixed a band-edge convention mismatch (device side half-open vs TD side closed) — K re-confirmed 4.789 unchanged under the fix. |
| CS-4 | `beb2c97` + `3c889b9` + `337ae45` | **Per-PRO LSB selection.** `availability.per_pro_lsb` strict precedence: (1) NATIVE device LSB → (2) DIRECT TD→LSB transform when any TD-bearing recording overlaps the PRO (reuses the CS-1 `transform_centered_window`: 30 s rating-centered, clip-don't-slide, 1 s-min, fail-closed >10% Missing; 50% overlap) → (3) PSD bridge ONLY for PSD-only patient events in [7.8,30]. Montage/survey TD never uses the bridge. `per_pro_lsb_overlay` = the 50%-overlap sliding-window LSB trace + per-window saturation QC (±4000 µV ADC rail) + missing rejection. `td_transform_band_power` gained `agg="none"` (per-window band power). Review (request_changes → approve_with_nits after fixes): blocking overlay trace/QC misalignment under NaN samples + native fail-open + saturated-leak + channel-canon asymmetry all fixed. |
| CS-4 wiring | `49b1904` | **Surfaced per-PRO selection on the timeline.** `bravo_service._pro_lsb_by_channel` runs `per_pro_lsb` per channel (PRO times = `pain['t']`; tier-2 TD = streaming `td_list` + montage/survey `psd_list`; tier-3 = CS-3 event blocks; center = sensing center, fallback series `center_hz`); `_build_availability` emits `pro_lsb` in the payload. Frontend `BiomarkerDataTimeline.js`: one point per rating on each LSB lane, marker SHAPE = tier (native filled ● / TD-transform ○ / PSD-bridge ◇), red ring = saturated; glyph-legend entry. **Live RCS08: 684 PROs × 30 ch → 239 values (51 native, 102 TD-transform, 86 PSD-bridge).** |

**Key constants (analytics.py):** `LSB_PER_UV2_TRANSFORM=352.62` (primary TD→LSB),
`LSB_PER_UV2_DEVICE_PSD_TD_RATIO=4.789`, `LSB_PER_DEVICE_PSD≈73.63` (PSD bridge),
`LSB_PER_UV2_VALIDATED=269.0` (welch256 backup, **retained per PI** pending a device-PSD refit
discussion), `LSB_VALIDATED_HZ_LO/HI=7.8/28.3` (calibration-validity), `LSB_DEPLOYABLE_HZ_HI=30.0`
(device adaptive ceiling), `TRANSFORM_WIN_SECONDS=1.0`, `TRANSFORM_STEP_SECONDS=0.5`,
`TRANSFORM_CENTERED_EXTENT_SECONDS=30.0`. **Provenance doc:** `CS3_FFTBinData_units_recon_2026-06-27.md`
(units finding 264/1056/3114 bins; montage TD↔PSD fit n=10476; compose).

**Per-PRO time contract (the answer to "where/how much TD per PRO"):** for a PRO at time T matched to
a TD recording, the transform runs on **30 s centered on T = [T−15 s, T+15 s]**, clipped to the
session boundary (use whatever's available if shorter, ≥1 s), >10% Missing rejected; a 1 s rcs-Hann
window slides at 500 ms (50% overlap, ≈59 windows) and the **median** in-band summed-squared-magnitude
→ one LSB.

**Still open:** welch256_density / psd_band_to_lsb deliberately retained (PI: discuss device-PSD refit
separately — welch256 produces a PSD from TD, it cannot consume a device PSD, so it was never a valid
no-TD backup). `per_pro_lsb` is now WIRED into the timeline (commit `49b1904`, payload key `pro_lsb`);
`per_pro_lsb_overlay` (the within-rating sliding-window trace) is still available but not yet drawn —
the natural next step is a hover/expand detail that shows a rating's 30 s LSB trace + saturation QC.
Track B audit backlog ([5]/[14]/[42]/[49]) untouched; [14] needs a PI judgment call.

---

## 0b. Session 2026-06-26: read second

UX + correctness + performance pass on the Biomarker and ClosedLoopSim pages. **PR #8 merged
into `v3.1.0`** (merge commit `a191b758`; 14 commits `e57a7078..a191b758`). All backend tests:
**184/184** via `python3 _agent_bridge/run_tests.py`. Active branch `PS_closedloop_deployment`
is 2 commits ahead of origin's pre-push state at session end; HEAD = `97d4e86`.

**Frontend / UX.**
- Biomarker timeline legend: right-anchored the glyph legend (`x:1.0, xanchor:"right"`) so it
  can never overlap the left-aligned title (collision-free by construction); deleted the useless
  "Sensing center (Hz)" swatch key (commit `3525c0a` + follow-ups).
- Biomarker page stat-readout UX batch A–I (commit `35a38aa`): larger stat text, ` · ` separators,
  expanded abbreviations, NOT-significant red callout, "(in-sample, not cross-validated)" AUC label,
  clearer control labels, de-reddened pain-metric picker, bigger fine print, ToggleButton aria-labels.
- **Biomarker state persistence** (commit `2fad81b`): navigating Biomarker→deployment→back no longer
  resets to the loading view. New `biomarkerStateStore.js` — Layer 1 controls in localStorage
  (`bravo.biomarkerControls.`), Layer 2 in-memory LRU cache of the ~19 MB heavy result with a
  `performance.memory` pressure guard (declines to cache above 85% heap → recompute fallback). Status
  chip shows "✓ view retained" (green) or "⚠ memory tight … recompute on return" (amber). React built.
- ClosedLoopSim: sticky deployment **verdict strip** + one-page **print stylesheet** (`0d9d51d`);
  verdict strip + sign-off card now surface the **modeled (estimated) LSB threshold** consistently
  with the LSB panel (`power ≈ X LSB (tier) · extrapolated`), resolving a same-page contradiction
  for unsensed bands (PR #8 review fix `f9a6efc`).

**Backend correctness.**
- Spectral feature-importance scan now spans the **full 0–100 Hz** (centers 2.5–97.5 with the 5 Hz
  window); 8–30 Hz interpreted as CENTER frequencies and flagged `adaptive_valid` (center-based),
  green-tinted but not scan-restricting (`dffbe9c`/`0107792`/`42316e0`). x-axis always full-range.
- Modeled-LSB fallback ladder shared between `band_lsb_and_power` and `deployment_summary` via
  `_modeled_lsb_threshold_estimate` (TIER1 modeled_timeline → TIER2 frozen PSD→LSB → TIER3 validated
  k=269); estimated values flagged so the UI never shows a modeled number as measured (`dd46c95`).
- `/queryDeploymentSummary` 500 fixed: identity dict carried a Django `Participant` model object
  (not JSON-serializable) → use `participant_uid` string (`f5963d9`).
- Intermittent "ROC request failed": embedded R (single-threaded) corrupted by concurrent glmer fits
  from sibling panels under the async worker → process-wide reentrant lock `_R_GLOBAL_LOCK` around
  every pymer4/lme4 fit + lifted the deployment-summary fetch to the parent so verdict strip and
  sign-off card share ONE call (`7d59fad`).

**Backend performance** (commit `97d4e86`; user ask: "vectorize the bootstraps/elsewhere,
parallelize across 16 cores where you cannot vectorize"). `run_for_participant` recompute ~63s→~47s.
- `threshold_biomarker._threshold_metric_arrays`: one `searchsorted` pass for sens/spec/acc across the
  whole 60–200 threshold grid, replacing 40k+ per-threshold sklearn `confusion_matrix`/`accuracy_score`
  calls (~35s of `_param_validation` overhead). Selection loop byte-for-byte unchanged. **24.8×** on
  that function (38.7→1.56 ms/call). Verified exact-match 800/800 fuzz cases (NaN/ties/one-class).
- `best_threshold_by_balanced_auc`: vectorized `roc_auc_score(y,binary)=(sens+spec)/2` for the
  sliding-window/all-data threshold-by-AUC loops. Best AUC identical to full float precision;
  tie-break among equal-AUC thresholds made **deterministic** (first/lowest AUC-optimal) where the
  original depended on sklearn float-noise — reproducible run-to-run, real LFP unaffected (boundary
  thresholds, no ties).
- `spectral_feature_importance`: per-band CV-AUC + cluster-robust logit-p refactored into an optional
  parallel pass (`_spectral_cv_threads`, **DEFAULT 1/serial**, opt-in `BRAVO_SPECTRAL_CV_THREADS`).
  Bit-identical to serial (identical digests at 1 vs 16 threads). Defaulted serial because the scan
  already runs inside the analytics thread pool and is GIL/BLAS-bound — no wall-clock gain measured;
  path kept for a future process-pool refactor.
- New tests: `test_find_best_threshold_vectorized_matches_reference`,
  `test_best_threshold_balanced_auc_matches_reference`. Verbatim pre-vectorization functions kept as
  equivalence oracles.

**Infra notes (still open).**
- Live `bravo-server` (OrbStack) gunicorn capped at min(nproc,4) workers in `boot.sh` +
  `docker-compose.yml` (commit `fd579ef`) — 16 workers × ~2.3 GB preload had exhausted RAM/swap.
  Added `--reload-engine poll` because the source tree is a VirtioFS bind mount where inotify
  reload events don't propagate (`bf62b21`). **Both take effect only on next container restart**
  (sandbox can't reach the docker daemon); meanwhile the workaround is manual worker recycle
  (`kill -TERM` in batches of 3, master respawns fresh from disk).
- High-gamma 55.5 Hz calibration is **CLOSED as not-actionable** (see §4 item 2): Percept RC
  adaptive stim is firmware-limited to 8–30 Hz, so a 55.5 Hz sensing-only band can never drive a
  closed-loop controller. The extrapolation guard (`freq_extrapolated` flag) shipped and stays; the
  data-collection action item is retired.

**Largest remaining backlog (carried, not touched this session):** the **27 medium + 24 low**
findings from the four-lens deployment audit (all HIGH — C1/C2/C3/C8 — and C4 are resolved). Not
itemized in this doc; regenerate the list from the audit before triaging. Also deferred: the
design-effect discount for autocorrelated ratings (TIME half of C4 — second-order, effective-n
already uses the clustered count).

---

## 1. Project orientation

**What BRAVO_pain is.** A Django (backend) + React (frontend) web platform that ingests
JSON exports from the Medtronic Percept RC neurostimulator and provides analysis,
visualization, and decision support for **closed-loop deep brain stimulation (DBS) for
chronic pain**. The immediate engineering goal is to turn recorded neural data into
actionable Percept sensing/threshold parameters a clinician can program. Subject is
**RCS08** (de-identified code; the only participant with a frozen model so far).

**Repo & branch.**
- Repo root: `/Users/pshirvalkar/dev/BRAVO_pain` (host), bind-mounted to `/usr/src/BRAVO`
  inside the live `bravo-server` OrbStack container.
- Remote: `https://github.com/shirvalkarlab/BRAVO_pain.git`.
- **Default branch:** `v3.1.0` (HEAD = `f915257` at the last handoff; `e9d7a80` is the
  newest commit on the active working branch). The old `v3.0.0-alpha` is deleted.
- **Active working branch:** `PS_closedloop_deployment` (off `v3.1.0` at `f915257`).
- Other live remote branches: `development` (legacy); release branches `v2.0-alpha`,
  `v2.1.0`, `v2.1.1`, `v2.2.0`, `v2.2.1`.
- **Branches retired by the last session:** `PS_biomarker_actionability`,
  `PS_biomarker_clfixes`, `PS_biomarker_module` all deleted — their code was squash-merged
  into `v3.1.0` (see §3 / §6 for PR mapping); only orphan handoff `.md` files were unique to
  `PS_biomarker_module`.

**Git commit identity.** `.git/config` is unwritable in the sandbox ("Operation not
permitted"); set identity per-commit via `GIT_AUTHOR_NAME/EMAIL` and
`GIT_COMMITTER_NAME/EMAIL` env vars as `Prasad Shirvalkar <prasad.shirvalkar@ucsf.edu>`.
The `could not write config file` / macOS keychain `-50` warnings on every git op are
**documented-harmless** — pushes and merges still succeed. Do not chase them.

**The agent bridge (how code runs in the live container).**
`BRAVO/_agent_bridge/` is a stdlib mailbox watcher running **inside** the `bravo-server`
OrbStack container, on the `./BRAVO ↔ /usr/src/BRAVO` bind mount. It executes jobs in-container
via an inbox/outbox mailbox so the agent can run real code against the live DB/REDCap.

```
python3 BRAVO/_agent_bridge/bridge_client.py --cwd /usr/src/BRAVO --timeout N --wait M "<cmd>"
python3 BRAVO/_agent_bridge/bridge_client.py --status        # heartbeat
```

- Container: **Python 3.12.3, rpy2 3.5.15, pymer4 0.8.2, pandas 2.2.3** (note: `Series.view`
  still works here — see §7).
- **Test harness (no pytest in container):** `python3 _agent_bridge/run_tests.py` — globs
  `test_*.py`, sets up Django, reloads the module. This is the authoritative backend test runner.
- Gunicorn runs `--reload`, so backend source edits on the bind mount are live immediately.
  nginx serves the mounted `Client/build`, so **frontend changes need a bundle rebuild**.
- **Important bridge gotcha:** the bridge takes effect on container **CREATE**, not restart
  (see §7).

**Live DB / participant ids.**
- Live DB is MySQL/mongoengine in-container; REDCap reachable from the container
  (`REDCAP_API_URL` / `REDCAP_API_TOKEN` set).
- **RCS08 live uid = `2e3c75c00d7f4f37b53a048d195f11da`** — use this for all container probes.
  The older `_pro_dump` export used `1eda36458758461383721208bbe6bb87`; the DB was
  re-ingested, so always use the live uid.
- Cached PRO table: `BRAVO/_pro_dump/RCS08_chronic_pro_df.csv` (679 rows).
- Source RCS08 device JSONs: OneDrive grant `/Users/.../PNL/RCS008 jsons` (Stage-1 subfolder
  filenames still contain real patient names → keep out of repo; see §4 PHI note).


---

## 2. Key constants & frozen models

### 2a. Quantitative constants in the current code

All of the following live in `BRAVO/modules/Biomarkers/routines/analytics.py` unless noted,
and are present in the live `e9d7a80` tree (verified at this handoff).

| Constant | Value | Location | Meaning |
|---|---|---|---|
| `ADC_NV_PER_LSB` | **146.0 nV/LSB** (exact) | analytics.py:2028 | Percept **time-domain** ADC count scale, per Medtronic. Exact. |
| `LSB_PER_UV2_VALIDATED` | **269.0 LSB/µV²** | analytics.py:2095 | `k`, the **power-domain** firmware band-power gain. RCS08 stim-off paired-block fit, R²=0.94. |
| `UV2_PER_LSB_VALIDATED` | **0.00372 µV²/LSB** (= 1/269) | analytics.py:2096 | Inverse of `k`; matches the Medtronic design-ledger 0.0034 µV²/LSB within 9%. |
| `LSB_UV2_LOGLOG_SLOPE` | **0.835** | analytics.py:2097 | Firmware power-law log-log slope (≠1 because the device band ≠ offline band exactly). |
| `LSB_UV2_SIGMA_FOLD` | **1.26** | analytics.py:2098 | 1σ multiplicative scatter of the TD→LSB calibration (×1.26 fold). |
| `CONVERSION_FFT_SIZE` | **256** | analytics.py:2078 | FFT size the conversion model assumes; only modes with this FFT are convertible. |
| `COMPATIBLE_THRESHOLD_MODES` | **("Dual", "SingleInverse")** | analytics.py:2079 | Percept threshold modes whose `fft_size == 256` (derived from `THRESHOLD_MODES`). |
| `THRESHOLD_MODES` | Dual (256-pt/1200 ms), Single (64-pt/100 ms), SingleInverse (256-pt/3000 ms) | analytics.py:2040 | FFT/window metadata per Percept threshold mode. **Single (64-pt) is NOT convertible.** |
| `WELCH_MAX_MISSING_FRAC` | **0.10** | streaming_psd.py:289 | Missing-fraction floor for Welch epochs; windows above it return all-NaN PSD and are skipped (Fix A). |

**Frozen TD→LSB calibration provenance (`k=269`).** Fit on **50 stim-off paired blocks**
(BrainSenseLfp + BrainSenseTimeDomain captured on the SAME signal): k=269 LSB/µV²
(1 LSB ≈ 0.0037 µV²), **R²=0.94, 5-fold CV error 1.19×, 1σ scatter 1.26×**. Validated over
**8–28 Hz only**; the adaptive band (8–30 Hz) is the firmware-actionable range. Higher
center frequencies (e.g. the 55.5 Hz high-gamma winner) are **extrapolated** and need
dedicated streaming calibration (open item, §4). The estimated-threshold path propagates k
uncertainty: `estimated_upper_lsb_lo/hi` and `sigma_fold` are emitted; the panel displays
"1 µV² ≈ 269 LSB (±1σ: 213–339)".

### 2b. Frozen per-participant PSD→LSB model — `RCS08.json`

`BRAVO/modules/Biomarkers/data/psd_lsb_models/RCS08.json` — `schema:
psd_lsb_conversion/v1`, `generated_utc: 2026-06-25T01:03:47Z`. It is a **frozen asset**
(loaded, never refit on request) so the reviewed cleaning decisions stay fixed.

**Model form (per channel):** `log10(LSB) = a_f + b·log10(µV²)` — a per-channel **common
slope `b`** with a per-frequency **intercept `a_f`** (= device LSB at 1 µV²). The on-board
power gain falls as sensing frequency rises; that frequency dependence lives entirely in
`a_f`, **not** in the slope (per-frequency slope differences are statistically unsupported:
LR n.s., adjusted-R² does not improve). The frequency effect is a **gain/intercept shift,
not a slope change**.

**Pipeline baked into the freeze:** nearest device-LSB sample per offline PSD epoch (each
PSD used once/channel); **±30 min** match window; **fixed 10-min-bin averaging**
(`floor(t/600s)`); Iglewicz-Hoaglin robust-z outlier omission per band
(`|0.6745·(r−med)/MAD| > 3.5` on `log10(LSB/µV²)`, MAD>0 guard); hard **n≥6-per-band**
reliability floor. `fit_basis`: n_total_clusters=685, n_outliers_excluded=33; estimator =
per-channel common slope (OLS log-log), intercept = robust `median(logL − b·logP)` per band.

**Fittable channels:**

| Channel | fittable | common_slope b | R² | pooled_k | n_clusters |
|---|---|---|---|---|---|
| **ZERO_THREE_RIGHT (0-3R)** | yes | **0.8545** | **0.841** | 81.35 | 524 |
| **ZERO_THREE_LEFT (0-3L)** | yes | 0.5164 | 0.253 | 278.76 | 81 |
| ONE_THREE_LEFT (1-3L) | no | — | — | 198.67 (pooled only) | 28 |
| ZERO_TWO_RIGHT (0-2R) | no | — | — | 646.27 (pooled only) | 9 |
| ZERO_TWO_LEFT (0-2L) | no | — | — | 333.98 (pooled only) | 8 |
| ONE_THREE_RIGHT (1-3R) | no | — | — | **None (unmodelable)** | 2 |

**ZERO_THREE_RIGHT per-band intercepts** (the deployed channel of record):

| center_hz | n | intercept a | intercept CI | LSB @ 1 µV² |
|---|---|---|---|---|
| **8.8** | 42 | **1.7695** | [1.7152, 1.8452] | 58.8 |
| 9.8 | 40 | 2.5995 | [2.4604, 2.6808] | 397.7 |
| 10.7 | 13 | 2.5841 | [2.5527, 2.7342] | 383.8 |
| 11.7 | 8 | 2.5673 | [2.5386, 2.6214] | 369.3 |
| 24.4 | 37 | 1.9275 | [1.9140, 1.9403] | 84.6 |
| 26.4 | 202 | 1.8544 | [1.8356, 1.8675] | 71.5 |

(ZERO_THREE_LEFT fits bands at 8.8/9.8/10.7/11.7/22.5 Hz but R²=0.25 — mostly streaming-only
LSB, treat as unreliable.)

**`special` notes in the JSON (the frozen exclusions):**
- **`ZERO_THREE_RIGHT_8.8Hz` — restricted to ≥2026-03-01.** Chronic 0-3R sensing was
  reassigned off the 8.8 Hz band on **2025-12-05**, then bounced across 28/24.4/26.4 Hz before
  settling. The 8.8 Hz gain falls through a **settling transient** over Dec–Feb (post-2025-12-05
  within-regime trend **−0.078 log10/month, p=0.039**) and only reaches stationarity from
  **~2026-02-15** (p=0.72 → 0.91 at 03-01). The 03-01 cut isolates the stable current-config
  regime (n=42, mean 1.69 log10(LSB/µV²), flat trend p=0.91). Using the config-change date
  2025-12-05 instead would inject the higher-gain declining transient and bias the deployable
  threshold. **This is item #6, now CLOSED — see §3.** ⚠️ The earlier "Spearman ρ=−0.64,
  p≈1e-24, all-time k≈157 vs recent k≈52" framing (handoff `…011910Z`) was a **vague,
  unexplained** description that `e9d7a80` **superseded** with the settling-transient mechanism.
- **`ZERO_THREE_RIGHT_23.4Hz` — excluded** (noisy, inconsistent with its 24.4/26.4 Hz neighbors).

### 2c. Constants/claims later corrected or retracted

- **Direct-fit `k = 74.1 LSB/µV²` (0.0135 µV²/LSB), free slope 1.085** from the original
  on-request PSD→LSB panel fit (handoff `…220917Z`, RCS08 0-3R n=1446 ±1h) was **superseded**
  by the rigorous stim-off paired-block calibration **`k = 269` (0.00372 µV²/LSB)** in the last
  session. The 269 value is the validated population constant now in code; the 74.1 figure was an
  earlier, looser estimate.
- **`empirical_lsb_ratio` "~3× / diverges" docstring** — retracted; corrected to reference the
  validated constant (handoff `…070628Z`).
- **8.8 Hz "ρ=−0.64 temporal regime shift, ~3× gain drop, unexplained"** — superseded by the
  documented settling-transient mechanism in `e9d7a80` (see above).
- **Forced log-log slope = 1.1** was explored as within ~0.005 R² of the forced optimum (0.90)
  once 8.8 Hz and 23.4 Hz are cleaned, but the **deployed model uses the per-channel free common
  slope** (b=0.8545 for 0-3R), not a forced 1.1.

---

## 3. Decision log

Chronological. "Status" is the current standing as of `e9d7a80`.

| # | Decision | Rationale | Evidence | Status |
|---|---|---|---|---|
| 1 | **rpy2/pymer4 glmer converter fix** — `_rpy2_converter_ctx()` returns `localconverter(ro.default_converter)`, NOT `+ pandas2ri.converter` | With an active pandas2ri rpy2py context, pymer4's `glmerControl(...)` R list was eagerly converted to a Python OrderedDict that rpy2 3.5.15 can't send back into glmer. pymer4 does its own DataFrame conversion internally, so the outer rule was never needed. | Suite PASS=133/0; real worker-thread glmer recovered an injected 20 Hz signal (z=3.57, p=3.6e-4). Commit `33f45a5`. | **Adopted** |
| 2 | **PRO-timestamp timezone correction** — REDCap `date_time_s1_daily` is **California local** wall-clock, not UTC; convert via `bravo_service._pro_timestamps_utc` (America/Los_Angeles → UTC, +7/+8h DST-aware) | Device StartTime is already UTC; first pass parsed PRO as `utc=True` → 7–8h smear → spurious 2/678 matches. User caught it. | Corrected census: **67/678** PROs match within 60-min tolerance (23 BrainSenseTD + 51 IndefiniteStream); 16 fall inside a recording span. Commit `a4e4e68` (corrects `adcaf15`). | **Adopted** |
| 3 | **Concatenation is robust to PRO matching** — keep `FixBreaking` zero-fill concat behavior; no change to matching | Asked whether merging time-separated TD recordings could move a StartTime out of a PRO match window. Both-ways re-decode (FixBreaking on/off) over the full pool: 67 vs 67 matched, 0 lost / 0 gained / 0 status changes, max nearest-match-distance change 0.00 min. | `AUDIT_concat_vs_PRO_matching_RCS08.md`. Cheap future guard noted (stamp fallback PSD at recording midpoint) but not needed for RCS08. | **Adopted (no-op)** |
| 4 | **Fix A — missing-aware Welch epochs** — TD adapter now honors `Missing`; windows over `WELCH_MAX_MISSING_FRAC=0.10` → all-NaN PSD → row skipped | FixBreaking zero-fill (and dropped-packet insertion) was entering Welch PSDs as real zeros, deflating band power. PowerDomain adapter already dropped `missing>0`; this brings TD to parity. | Suite PASS=139/0. Real recordings with 32%/15% first-window missing now REJECTED (legacy returned deflated finite PSD); clean recording byte-identical. Commits `adcaf15`, `c438ce1`. | **Adopted** |
| 5 | **ClosedLoopSim figure-reset bug fix** — `requestParams` memoized; Plotly `<div ref>` permanently mounted; draw-once + restyle-by-trace-index | Inline `requestParamsFromCandidate(bc)` produced a new object identity every render → all 4 panels refetched → every figure unmounted to loading on any child state change. | Commit `255e0ef`; merged as PR #3 → v3.1.0 (`52337f5`). Hard constraint born here (see §7). | **Adopted** |
| 6 | **Removed the `net benefit` cut-point rule** | Its objective is exactly `prevalence × cost objective` (`u_nb = p·u_cost`) — always selects the identical operating point as `cost`; two buttons that can never disagree look like a bug. | Kept one `cost` rule, deterministic first-maximizer tie-break. True Vickers net-benefit is a decision CURVE (Phase-2). PR #3. | **Adopted** |
| 7 | **C1 — de-fold the deployment-ROC bootstrap CI** — append `float(ab)`, not `max(ab,1-ab)` | Folding hid null bands; a de-folded CI lower bound can honestly fall below 0.5 on a null band. | New `ci_method` key + test `…_defolded_null_ci_drops_below_chance`. PR #5 (`c50be37`). | **Adopted** |
| 8 | **C3 — signed era AUC + pooled-orientation** — pooled computed first (orients to own data); eras reuse `pooled_flip`; era AUC signed, not folded | A folded per-era AUC masks within-era sign reversals (a closed-loop failure mode). | New keys `any_reversed`, `ci_overlaps_pooled`, `portable_by_ci`. Synthetic reversal: HIGH era AUC 0.000 reversed=True (old folded code → 1.00). PR #5. | **Adopted** |
| 9 | **C8 — tri-state deployment gates, fail-closed** — gate `state ∈ {pass, fail, indeterminate}`; stim-stable gate ABSTAINS when LRT unavailable (was fail-open green) | A gate that goes green on *absence* of evidence is unsafe for a "ready to program" decision. | New keys `ready_to_program`, `n_gates_indeterminate`, `n_necessary*`. PR #5. | **Adopted** |
| 10 | **C9/C10 actionability** — single-source `CUTPOINT_TRACE=2`; recommend→program Δ; advisory ramp guidance with conservative-abstain rule | Make the deployment recommendation actionable (delta vs currently-programmed threshold, ramp posture) while keeping fail-closed discipline. | `recommended_vs_programmed`, `_ramp_guidance` (conservative when `stim_stable is not True`). PR #6 (`b0597f8`). | **Adopted** |
| 11 | **PSD→LSB conversion panel + frozen model** — derive firmware gain from time-matched chronic streams; freeze per-participant model `RCS08.json` with tiered fallback (band → channel_freq → channel_pooled → none) | The device reports band power in LSB; offline Welch reports µV². A committed band without its own measured LSB Timeline needs an estimated threshold, clearly flagged ESTIMATED/indeterminate. | `analytics.psd_lsb_conversion`, `routines/psd_lsb_model.py`, `bravo_service.deployment_summary` fallback. Modeled threshold → `indeterminate` gate (never counts toward ready-to-program alone). Commits in PR #6 + `1fc1adc`/`771f3c2`. | **Adopted** |
| 12 | **C2 — forward-chaining / out-of-sample validation** — expanding-window, blocked-by-week forward-chaining; sign + Youden threshold fit on TRAIN clusters only; held-out AUC NOT re-folded | Every prior deployment AUC was **in-sample**. For a forward-running controller the decision-relevant number is next-week held-out performance. | `deployment_forward_chaining`; new SUPPORTIVE gate `forward_validated`. nrs 0-3R bands' in-sample AUC masked a forward reversal (26.4 Hz: in-sample 0.55 → held-out **0.24**; 8.8 Hz: 0.52 → 0.37). Suite PASS=161. Merged PR #7 (`d9d58a4`). Last HIGH finding (C1/C2/C3/C8 all resolved). | **Adopted** |
| 13 | **Remove 60 Hz mains notch default** — `_band_power_notched(notch=False)` by default | The Percept is implanted / battery-powered with **no mains coupling**, so notching real signal at 60 Hz removes information for no benefit. Interpolation retained behind explicit `notch=True`. | Commit `f915257`. | **Adopted** |
| 14 | **Modality / threshold-mode FFT-size guard** — only `COMPATIBLE_THRESHOLD_MODES=("Dual","SingleInverse")` (256-pt FFT) are convertible; **Single Threshold (64-pt) is NOT convertible** | The conversion model assumes a 256-pt FFT band power; a 64-pt Single-mode FFT produces a different quantity and cannot be converted with the same gain. | `THRESHOLD_MODES`, `CONVERSION_FFT_SIZE=256`, `_threshold_mode_block` guard. Commit `f915257`. | **Adopted** |
| 15 | **TD→LSB validation → `k=269`** — proportional `LSB = k·µV²`, validated constant | Establish a rigorous, measured firmware power gain rather than the looser on-request fit (k≈74). | 50 stim-off paired blocks, **k=269 LSB/µV², R²=0.94**, 5-fold CV 1.19×, 1σ 1.26×; matches design-ledger 0.0034 µV²/LSB within 9%. Commit `f915257`. | **Adopted** |
| 16 | **PSD→TD→LSB back-translation = null result** — direct PSD→LSB is the rigorous path | Tested whether reconstructing TD from PSD before applying the TD gain improves the estimate. | Phase-randomized TD reconstruction matches the direct PSD integral within **0.8%** — back-translation adds nothing. Commit `f915257`. | **Adopted** |
| 17 | **8.8 Hz cut stays ≥2026-03-01 (NOT the 2025-12-05 config-change date)** — item #6 | The prior handoff proposed moving the restriction to the config-change date. Stationarity analysis shows that date sits inside the declining settling transient (within-regime trend −0.078 log10/month, p=0.039; stationarity only from ~2026-02-15). The 03-01 cut isolates the stable current-config regime. | Frozen fit UNCHANGED (b=0.8545, r²=0.841, 8.8 a=1.7695). JSON `special` note + module docstring rewritten to the understood mechanism. New regression test pins it (9/9 in `test_psd_lsb_model.py`). Commit **`e9d7a80`**. | **CLOSED** |
| 18 | **Impedance term `c=1.02`** — general gain correction | `c=1.02` is statistically significant, but its **original motivation (8.8 Hz drift) was retracted** once the drift was explained as a settling transient. Whether to adopt it as a general gain correction is undecided. | Under re-evaluation on the frozen pairing data this session. | **OPEN / under re-evaluation** |

---

## 4. Open items

The user has **dropped** the "generalize beyond RCS08" and "PHI hygiene" items — do **not**
carry them forward as open work. (The last handoff `…070628Z` listed those as open #1 and #3;
they are superseded by the user's decision to drop them. PHI hygiene context is retained as an
operational note in §7 only, not as an action item.)

**Remaining open:**

1. **Impedance term `c=1.02` decision** — **CLOSED this session (`a9c3a01`): REJECTED.** Re-fit
   on the frozen ZERO_THREE_RIGHT pairing data with 487 device `DeviceImpedance` logs joined
   nearest-in-time (median gap 0 d, max 2.9 d) onto 2985 epochs. The term is significant under
   naive OLS (c=0.53, p=8e-8) only because those epochs share just 230 session-level impedance
   measurements — pseudoreplication. Corrected: impedance-cluster-robust SE → n.s. (p=0.26);
   forced alongside a collinear calendar-time covariate it is significant (c=0.90, p=0.016) but
   log10(Z) correlates with time (r=0.36) so that is shared slow drift, not impedance; coefficient
   unstable across specs (0.53 / 0.90 / 0.17 vs the claimed 1.02); deployable ≥2026-03-01 regime
   (full 2326–4712 Ω range) → c=0.17, p=0.38. Most-generous threshold impact 1.22× across observed
   Z, below model residual scatter (1.83×, 1σ) and validated k uncertainty (1.26×). Not a physical
   gain correction — a slow-time proxy. Frozen fit UNCHANGED; rationale written to the
   `psd_lsb_model.py` docstring + `RCS08.json` special block (`no_impedance_gain_term`); regression
   test `test_no_impedance_gain_term_adopted` pins it. Evidence:
   `rcs08_impedance_term_decision.png`, `rcs08_impedance_term_scan.csv`, `rcs08_impedance_series.csv`.
2. **High-gamma 55.5 Hz calibration** — *CLOSED (not actionable for closed-loop).* The Percept RC
   adaptive-stim modes are firmware-limited to 8–30 Hz, so a 55.5 Hz sensing-only band can never
   drive a closed-loop controller — there is no clinical reason to calibrate `k` there. The
   extrapolation GUARD shipped (`dac25ac`, `9de1aeb`) STAYS: `estimate_lsb` used to silently snap a
   55.5 Hz request to the nearest fitted band (26.4 Hz) and return it with the in-range r²=0.841;
   the gain is not band-flat (falls ~0.80 log10/decade), so that snap over-states the 55.5 Hz LSB
   by ~1.7× (> the model's own 1.26× σ). Guard: `analytics.LSB_VALIDATED_HZ_LO/HI`; `estimate_lsb`
   returns `freq_extrapolated` + EXTRAPOLATED warning (all tiers); deployment estimate + sign-off
   `deployable_threshold` gate carry/show the flag; test `test_highgamma_estimate_flagged_extrapolated`;
   evidence `rcs08_highgamma_extrapolation.png`. The data-collection action item is RETIRED — no
   55.5 Hz streaming calibration needed.
3. **Audit C4** — *RESOLVED (`7fcee95`).* Power readout & 'powered' gate ran on the optimistic
   point AUC (the audit's "resolves once C1 lands" note was wrong: C1 de-folded the CI but both
   `auc_power` call sites still passed `roc['auc']`, never `auc_lo`). FIX: `auc_power(..., auc_lo=)`
   reports a power BAND and `more_data_needed` fail-closes on the CI-lower-bound end; both call
   sites pass `roc['auc_lo']`; `LsbPowerPanel.js` draws the conservative marker; test
   `test_auc_power_conservative_band_gates_on_ci_lower_bound` (AUC 0.70/CI-low 0.60: 83%→29% power,
   gate flips). The design-effect discount for autocorrelated ratings (TIME half of C4) is deferred
   — effective n is already the clustered count, so residual within-cluster autocorrelation is
   second-order.
4. **Remaining audit findings** — **27 medium + 24 low** still open from the four-lens
   closed-loop deployment audit (C4 now resolved). All four HIGH findings — C1, C2, C3, C8 — are
   resolved.

**Resolved / no longer open** (for reference, so they aren't re-opened): C1, C2, C3, C8 (all
HIGH); the figure-reset bug; C5/C6/C7 (Wave-1/2 figure-honesty); C9/C10 (actionability); the
8.8 Hz cut date (item #6, CLOSED in `e9d7a80`); the 60 Hz notch default; the threshold-mode
guard; the TD→LSB validation and the PSD→TD→LSB back-translation question.

---

## 5. Test & build status

- **Backend suite: 166/166 PASS** in the live container, confirmed this session via the bridge:
  `python3 _agent_bridge/run_tests.py`. (Trajectory across sessions: 133 → 139 → 161 → 162 →
  163 → 164 → 165 → 166 as tests were added; +1 `test_no_impedance_gain_term_adopted` (item #4),
  +1 `test_highgamma_estimate_flagged_extrapolated` (high-gamma guard), +1
  `test_auc_power_conservative_band_gates_on_ci_lower_bound` (audit C4).) **There is no pytest in the container** — `run_tests.py` is the
  authoritative runner (globs `test_*.py`, sets up Django, reloads the module).
- **Local standalone runner caveat:** running `modules/Biomarkers/tests/` outside the container
  shows a few harness-only failures (e.g. 48/51 local) — `test_normalize_pro_times*`,
  `test_pain_scores_emit_utc_t_epoch`, `test_pain_series_epochs_match_pro_match_arrays` need
  Django `INSTALLED_APPS` and only pass under the Django harness; model-dependent test files
  can't run in the local importlib runner at all. These are **not** regressions and **not** in
  any diff. Use the container runner for the real number.
- **Latent pre-existing bug (untouched, out of scope):** `test_analytics.py`'s
  `if __name__=="__main__"` runner block calls some `test_*` functions before they are defined
  (`NameError` under direct `python test_analytics.py`). It pre-exists on `origin/v3.1.0`
  (runner line calls a fn defined ~70 lines later). CI/pytest uses order-independent collection,
  so it never bites there. Left alone.
- **Frontend:** ESLint clean on all modified ClosedLoopSim panels.
- **Build:** CRA production build exits 0. Command:
  `cd Client && export npm_config_cache=/tmp/npmcache && GENERATE_SOURCEMAP=false
  NODE_OPTIONS=--openssl-legacy-provider CI=false npx --no-install react-scripts build`
  (node v24.13.0, npm 11.6.2). The repo **commits `Client/build/` alongside source**
  (precedent: e32828f, 52010ec). nginx serves the mounted build, so the bundle must be rebuilt
  and committed for any frontend change. ClosedLoopSim is code-split into **chunk 431**; the
  timeline is **chunk 768**.

---

## 6. Artifacts & figures index

Grouped by the session that produced them. IDs are Operon artifact/version ids where the
handoff recorded them.

**Design spec of record (read before any biomarker-pipeline work):**
- `DESIGN_biomarker_pipeline_v2.md` (artifact/version `bab71722-0293-453e-9d21-36b77a26cbac`) —
  the consolidated **biomarker pipeline design ledger v2**. This is the spec the rethought
  pipeline is built against (nothing in it is built yet unless noted): Percept RC controller
  facts and the 8–30 Hz adaptive sensing range (§1); the three power-domain streams + corrected
  five-product BrainSense taxonomy (§2, §8a-bis); the **BandCandidate contract v1** — the
  serializable interface between the Biomarker module and the future Closed-Loop Simulation
  module (§6, REDCap-PRO-defined label; events corroborate only; selection bias recorded in
  `provenance`); the LSB↔µV² conversion as a confidence-rated FYI, not a calibration (§4);
  stim-context-era heterogeneity confounds (§5); the chosen **Option-3 UI split** and the
  **data-availability-timeline final design** that replaces `BiomarkerTimeline` (§8b–§8e); and
  the open decisions in §10. The frozen PSD→LSB constants here (`k=269`, `0.0034 µV²/LSB`)
  cross-reference §2 of this handoff.

**Session `…064004Z` (ClosedLoopSim reset fix / four-reviewer critique, PR #3):**
- `ClosedLoopSim_review.md` (artifact `29f8efc6-1f58-4c29-bf73-2b9c6c6c76f9`, version
  `83f7dea0-ff85-4dc1-9ae7-f07ea7f62ea6`) — full four-reviewer critique + interactive QA log.
- `ClosedLoopSim_source.txt` (artifact `0d4444e7-4bc9-433c-bc64-6a19b3d6f292`) — concatenated
  module source handed to reviewers (hidden).
- Plotly prototypes: `roc_cost_slider.html` (`d5b08e59-…`), `roc_rule_toggle.html`
  (`58948907-…`), `roc_matchdir_toggle.html` (`2b936e5f-…`); PNGs `roc_rule_grid.png`
  (`8521cd3d-…`), `roc_matchdir.png` (`11d57c4a-…`).
- `recommended_encodings.png` (`0384ee9b-d6cb-437c-9178-74d43a7321c2`) — Phase-2 encoding mockups.

**Session `…210017Z` (four-lens audit Wave 1+2, PR #5):**
- `closedloop_audit_report.md` (version `e3a12136-e0e1-4fff-b95f-baa42d0a0a46`) — the audit of record.
- `clfix_montage.png` (version `1d21b75f-71c6-462d-a5b2-69d61d7d2f3e`) — 4-panel before/after.
- `clfix_preview.html` (version `c73fd676-6b03-4498-bddc-f9f59bc2bed0`) — interactive Plotly preview.

**Session `…220917Z` (C9/C10 + PSD→LSB panel, PR #6):**
- `psd_lsb_conversion.png` (artifact `522fa513-…`, version `3d7da049-…`) — 3-panel conversion figure.
- `psd_lsb_pairs.csv` (artifact `0fbee806-…`) — 3652 matched (PSD, LSB) pairs.
- `psd_lsb_fit.json` (artifact `81b2242a-…`) — the ZERO_THREE_RIGHT on-request fit.

**Session `…011910Z` (frozen PSD→LSB model wired in):**
- `psd_lsb_model_RCS08_frozen.json` (version `721a309c-6685-4b9b-8ad1-6b10d5ee41bc`) — frozen model.
- `psd_lsb_deployment_panel.html` (version `97f83a6c-a615-4f28-87ec-2d07e2c6cc23`) — panel preview.
- `psd_lsb_intercept_by_freq.csv` (version `609e7de9-2115-4fa8-9824-0e1422beccf3`) — cleaned per-band intercepts.
- `psd_lsb_cleaned_forced_1p1.png` (version `b91969db-5501-4a86-a69c-088baa974b27`) — cleaned fit (b=1.1).
- `psd_lsb_88hz_time.png` (version `abc3184c-390e-418a-8efd-42c856a87205`) — 8.8 Hz temporal figure.

**Session `…020620Z` (C2 forward-chaining, PR #7):**
- `c2_forward_validation_RCS08.csv` — per-band in-sample vs held-out forward-validation table.

**Session `…070628Z` (modality-sensitive conversion + LSB validation, `f915257`):**
- `rcs08_td_lsb_calibration.png` — TD→LSB (k=269) validation figure.
- `rcs08_psd_lsb_backtranslation.png` — back-translation null-result figure.
- `rcs08_lsb_frequency_coverage.png` — 8–28 Hz frequency-coverage figure.
- `METHODS_lsb_estimation.md` (3 versions) — methods & validation source; also served as
  `Client/public/static/docs/METHODS_lsb_estimation.html` (figures embedded), linked from PsdLsbPanel.
- `td_lsb_calib.csv` — paired-block calibration data.
- `td_lsb_pairing_inventory.csv` — streaming-session pairing inventory.
- `psd_backtranslation.csv` — back-translation test data.

**In-repo audit/fix docs (not Operon artifacts):**
`AUDIT_streaming_concatenation_RCS08.md`, `AUDIT_concat_vs_PRO_matching_RCS08.md`,
`FIXHANDOUT_MASTER_biomarker_fixes.md`, the 7 `SESSION_HANDOFF_*.md`, and this `MEGA_HANDOFF.md`.

---

## 7. Known gotchas (operational traps)

- **Git config unwritable in the sandbox.** `.git/config` is protected ("Operation not
  permitted"). Set commit identity per-commit via `GIT_AUTHOR_NAME/EMAIL` +
  `GIT_COMMITTER_NAME/EMAIL` (`Prasad Shirvalkar <prasad.shirvalkar@ucsf.edu>`). The
  `could not write config file` / keychain `-50` / `~/.config/git/ignore` warnings are
  **harmless** — pushes/merges succeed.
- **Bridge takes effect on container CREATE, not restart.** Changing the agent bridge requires
  recreating the container, not just restarting it.
- **sklearn version skew — correctness risk.** The live container has **scikit-learn 1.5.2** but
  some pickled classifiers were trained under **1.6.1**. Loading a model across this skew can
  silently mis-predict. Treat any pickled-classifier result as suspect until re-validated on a
  matching version.
- **REDCap PRO timezone.** `date_time_s1_daily` is **California local wall-clock**, not UTC.
  Always convert via `bravo_service._pro_timestamps_utc` (America/Los_Angeles → UTC, DST-aware).
  Device StartTime is already UTC. Parsing PRO as UTC smears matches by 7–8h.
- **Local decode env needs a dummy Fernet key.** Conda env `bravo_app` (Python 3.11.15;
  numpy/scipy/pandas/cryptography/dateutil) for local decode: set
  `os.environ["DATASERVER_ENCRYPTION"] = Fernet.generate_key().decode()` **before** importing
  `HelperFunctions`.
- **pandas `Series.view` skew between env and container.** `bravo_app` has pandas **3.0.3**
  (dropped `Series.view`); the live container has **2.2.3** (still works). Source was migrated to
  the resolution-independent `…to_numpy().astype("datetime64[ns]").astype("int64")/1e9` at all 5
  source sites (PR #6), so the runtime shim is no longer needed. **A bare `.astype("int64")`
  would give microseconds under pandas 3.0's `datetime64[us]` default and mis-assign stim eras —
  must be ns-resolution.**
- **CRLF files.** `Server/APIs/DataAnalysis.py` and `Server/APIs/urls.py` are **CRLF**; all
  other source is LF. Writing CRLF files with raw Python `open(..., newline="")` strips the CRLF
  → giant spurious diff. **`edit_file` preserves line endings; raw Python writes do not** — use
  `edit_file` for these two files.
- **GitHub from the sandbox.** No `gh` / PyGithub on PATH — use `urllib` + `GITHUB_TOKEN`
  (Bearer, API version 2022-11-28). Self-approval of your own PR is blocked → post the review as
  an issue comment, then `PUT /pulls/{n}/merge` (squash).
- **kaleido/Chrome export broken** in env `rocqa` (py 3.13.14, plotly 6.8 + kaleido 1.3) — use
  `write_html` or matplotlib for static export, not kaleido PNG.
- **ClosedLoopSim Plotly discipline (hard constraint).** Panels draw **once** via `Plotly.react`
  and mutate via `Plotly.restyle(…, [traceIndex])` / `Plotly.relayout` — **never rebuild a figure
  on interaction** (commit `255e0ef` fixed the reset bug; all later edits, incl. the C10 modebar
  and mode-selector `updatemenus`, preserve it). A maintainer following the Python `ps-plotly`
  figure-rebuild pattern verbatim would **re-introduce** the reset bug; keep the
  restyle-by-trace-index pattern (`const CUTPOINT_TRACE = 2` in DeploymentRocPanel).
- **PHI note (operational, NOT an action item — user dropped the hygiene task).** Stage-1 device
  JSON filenames in the OneDrive grant still contain real patient names (e.g. JI/JILLIAN IMRIE).
  Keep that folder out of the repo; RCS08 is the de-identified code. Exports committed to the repo
  are derived spectral features (verified no PHI, no hardcoded secrets; `secrets/redcap.env` +
  bridge mailbox are gitignored).

---

## 8. Key file map

**Backend (`BRAVO/modules/Biomarkers/`):**
- `routines/analytics.py` — glmer converter (`_rpy2_converter_ctx`); deployment stats
  (`deployment_roc`, `deployment_roc_by_era`, `deployment_forward_chaining`); LSB constants +
  converters (`lsb_from_uv2`, `uv2_from_lsb`, `THRESHOLD_MODES`, `_band_power_notched`,
  `psd_lsb_conversion`, `empirical_lsb_ratio`); stim-era assignment (`_assign_stim_eras`,
  `_elapsed_week_cluster`).
- `routines/streaming_psd.py` — Welch (`welch_psd_for_instance` ~290,
  `welch_rating_centered` ~395, `WELCH_MAX_MISSING_FRAC` ~289).
- `routines/psd_lsb_model.py` — frozen-model loader/estimator (`load_model`, `has_model`,
  `estimate_lsb`, `model_plot_payload`); tiered fallback band → channel_freq → channel_pooled → none.
- `bravo_service.py` — Welch/match wiring (`_welch_rows_into`, `_pro_timestamps_utc` ~1815,
  `_missing_time_vector`); deployment (`deployment_summary`, `band_deployment_roc`,
  `band_deployment_roc_by_era`, `band_lsb_and_power`, `_threshold_mode_block`,
  `recommended_vs_programmed`, `_ramp_guidance`, `psd_lsb_conversion_model`,
  `band_psd_lsb_conversion`).
- `data/psd_lsb_models/RCS08.json` — frozen PSD→LSB model (§2b).
- `tests/` — `test_analytics.py`, `test_welch_missing_aware.py`, `test_psd_lsb_model.py`, etc.

**API:** `Server/APIs/DataAnalysis.py` (views `QueryPsdLsbConversion`,
`QueryPsdLsbConversionModel`) + `Server/APIs/urls.py` (routes `queryPsdLsbConversion`,
`queryPsdLsbConversionModel`). **Both files are CRLF — edit with `edit_file` only.**

**Decode chain:** `modules/MedtronicPercept/{Percept,BrainSenseStream,IndefiniteStream,Session}.py`;
ingest concatenate toggle at `modules/DataCurator.py:148/150`
(`metadata["automatic_concatenation"]` → `JSON["AutomaticStreamingFix"]` → `Session.py:423`).

**Frontend (`Client/src/views/Reports/`):**
- `ClosedLoopSim/` — `index.js`, `DeploymentRocPanel.js`, `EraRefitPanel.js`,
  `LsbPowerPanel.js`, `DeploySignoffCard.js`, `PsdLsbPanel.js`, `ConversionModelPanel.js`,
  `palette.js` (shared Okabe-Ito). Code-split into **chunk 431**.
- `Biomarkers/BiomarkerDataTimeline.js` — zoom-adaptive LSB rescale (chunk **768**).
- `Client/build/` — committed compiled bundle (rebuild + commit for any frontend change).
- `Client/public/static/docs/METHODS_lsb_estimation.html` — served methods doc.

**Data / config:** RCS08 device JSONs at OneDrive grant `/Users/.../PNL/RCS008 jsons`
(keep out of repo); cached PRO table `BRAVO/_pro_dump/RCS08_chronic_pro_df.csv` (679 rows);
`secrets/redcap.env` (gitignored).

---

## 9. PR / commit lineage (quick map)

| PR | Squash SHA | Into | Content |
|---|---|---|---|
| #3 | `52337f5` (merge) / `255e0ef` (fix) | v3.1.0 | Pain Biomarkers engine + ClosedLoopSim reset fix |
| #4 | `52010ec` (merge) | v3.1.0 | ClosedLoopSim Phase-2 visualizations |
| #5 | `c50be37` | v3.1.0 | Four-lens audit Wave 1+2 (C1/C3/C5/C6/C7/C8) |
| #6 | `b0597f8` | v3.1.0 | C9/C10 + PSD→LSB panel + pandas-3/numpy-2 forward-compat |
| #7 | `d9d58a4` (merge) / `b2e01f1` | v3.1.0 | Forward-chaining / out-of-sample validation (C2) |
| — | `771f3c2` | branch | Frozen PSD→LSB model + deployment fallback + panel |
| — | `f915257` | v3.1.0 / branch base | Modality-sensitive conversion, threshold-mode guard, LSB estimation + error propagation |
| — | **`e9d7a80`** | `PS_closedloop_deployment` (HEAD) | **8.8 Hz cut rationale; keep ≥2026-03-01 (item #6 CLOSED)** |

**Engineering envs:** `bravo_app` (py 3.11.15, local decode, pandas 3.0.3), `rocqa` (py 3.13.14,
plotly 6.8 + kaleido — broken Chrome export), `python` (read-only). Live container:
Python 3.12.3, rpy2 3.5.15, pymer4 0.8.2, pandas 2.2.3, sklearn 1.5.2.

---

*End of mega-handoff. Authoritative sources: the 7 `SESSION_HANDOFF_*.md`,
`RCS08.json`, and commit `e9d7a80`. Preserve exact numbers, SHAs, paths, and dates when editing.*
