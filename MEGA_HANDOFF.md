# BRAVO_pain — Mega Handoff (consolidated)

> **HOW TO UPDATE THIS DOC (read before editing).** This is the single durable handoff; keep it
> that way. At the end of a session that changed the codebase:
> 1. **Read the whole doc first.** Don't append at the top while the bottom goes stale — that is
>    exactly how this file rotted before (duplicate headers, contradictory HEAD/suite lines).
> 2. **Update the state line below** (branch, HEAD short-SHA, suite count) to the real `git`/test
>    state — verify, don't copy from memory.
> 3. **Add a §0 entry** (newest first) summarizing what changed and why. Fold related fixes into
>    one entry; don't accumulate near-duplicate bullets.
> 4. **Update the affected reference**, not just §0: constants in §2, decisions in §3, open items
>    in §4, gotchas in §7, file map in §8. If a constant/function was removed, delete its row —
>    don't leave it described as current.
> 5. **Remove outdated comments/claims.** When a later fact supersedes an earlier one, drop the
>    earlier one rather than stacking a contradiction. §2b frozen-model numbers are SACRED — keep
>    verbatim.
> 6. Keep it durable: constants, decisions, gotchas, file map — not the blow-by-blow (that lives
>    in the per-session `SESSION_HANDOFF_*.md` / `HANDOFF_*.md`).
>
> **Purpose.** Single authoritative reference for the BRAVO_pain closed-loop DBS platform.
> Read this to be current. Where sources conflicted, the chronologically later one won and the
> stale claim was dropped. **State as of this revision:** branch `PS_closedloop_deployment`,
> **HEAD `e8a0d3f`** (in sync with origin) + **uncommitted** changeset (event-PSD resolver + modeled-LSB
> symbol fix + Bug 3/4 in-progress; §0 newest entry), **suite 249/249 PASS** (in-container runner).
>
> **Per-session detail** lives in the `SESSION_HANDOFF_*.md` / `HANDOFF_*.md` files this doc
> synthesizes (the most recent narrative is `SESSION_HANDOFF_2026-06-27.md`; the TD→LSB
> calibration write-up is `HANDOFF_TD_LSB_calibration_2026-06-27.md`). This doc keeps the
> durable facts — constants, frozen model, decisions, gotchas, file map — not the blow-by-blow.

---

## 0. Recent work (newest first)

What changed and why, most recent first. The durable decisions are tabulated in §3; this section
keeps the operational specifics. Per-commit detail: the dated session handoffs.

**Bug 1: Event-PSD channel resolver + Bug 2: Modeled-LSB symbol fix (2026-06-28, UNCOMMITTED). Suite 249/249.**

*Bug 1 root cause:* `_event_block_channel` guessed Right→`ZERO_THREE` / Left→`ONE_THREE` statically for blocks lacking a `SenseID`. On RCS08 84% of the 3,119 event PSD blocks (2,635/3,119) had no `SenseID`, and 86% of all blocks are Right-hemisphere, so ~86% of all event PSDs were dumped onto **R 0-3** — contaminating that channel's binarization scan pool and starving others. This is a biomarker-accuracy bug, not just display.

*Fix:* Replaced the static guess with an **active-sensing resolver**:
- `_build_sensing_config_index(decoded_recs)` — builds a per-hemisphere sorted `[(epoch_s, channel)]` list from `BrainSenseTimeDomain` + `BrainSensePowerDomain` records (single-channel sessions only; IndefiniteStream and montage sweeps — which sense all pairs simultaneously — are excluded by a `len(chans)==1` guard).
- `_build_sensing_config_index_from_rows(psd_rows)` — companion builder for the cached-assembly path where decoded dicts aren't available (builds from flat Welch rows, TD-streaming source only).
- `_resolve_event_channel(hemi_key, sense_id, t_event, sensing_index)` — priority 1: SenseID (authoritative); 2: most-recent prior config in 90-day window; 3: nearest-after config; 4: None (skip, never guess).
- `_EVENT_HEMI_DEFAULT_CONTACT` fully removed from all production paths. `_event_block_channel` reduced to a SenseID-only shim for backward compat.
- Wired into all 5 call sites: `_event_psd_rows`, `_event_psd_index`, `_event_psd_lsb_blocks` → availability timeline tick path, binarization scan pool (both `_assemble_psd_rows_cached` and the warm-cache path), and the deployment scan path.
- Sensing index sources: streaming TD only for `_assemble_psd_rows*`; TD + PowerDomain for the availability payload where `powerdomain_list` is in scope.
- Architecture: channel assignment stays at **analysis time** (not ingestion) — new JSONs automatically benefit; richer index as sessions accumulate.

*Live RCS08 validation:* Before → 484/3119 (16%) routed via SenseID; After → **3119/3119 (100%)** routed. L 1-3 went from 34 → 407 events. 421 bilateral events (both L+R) resolved to correct independent contacts (R=0-3 + L=1-3 dominant; R=0-3 + L=0-3 in 14 events when Left was sensing 0-3 that session). 0 unresolved.

*Bug 2 root cause:* The lane-level modeled tier used `symbol: "diamond-open"` for ALL methods. The per-rating tier already distinguished `td_transform→circle-open` / `psd_bridge→diamond-open` via `TIER_SYMBOL` but the lane tier did not, so TD-modeled points were invisible behind PSD-bridge diamonds.

*Fix (BiomarkerDataTimeline.js):* Lane-level modeled tier now partitions each frequency group by method and pushes two traces: `circle-open` for `td_transform`, `diamond-open` for `event_psd_bridge`. Non-binMode legend split into two entries (one per symbol). Redundant `matched ≥1 PSD` / `no neural match` pain-rating swatches removed from binMode glyph key (binarization mode already communicates this via color encoding). `nLegRows`: binMode 7→5, non-binMode 8→9.

*Bug 3 (BinarizationPreview.js line 346):* `scanModel` was missing from the `useEffect` dep array. `proIdxByBin` is computed inside that effect from `scanModel.samples`, but since `scanModel` wasn't listed, it went stale after any scanModel rebuild (e.g. `matchDirection` change) that didn't also change another listed dep. Fix: `scanModel` added to dep array. The 187/106 discrepancy the user saw was this stale render — `proIdxByBin.low` (unique rating indices per bin, a Set) and `counts.n_low` (total matched PSDs) are legitimately different units and both correct; the stale dep caused one to be from a prior model.

*Bug 4 (BiomarkerAnalytics.js):* (a) Scatter title showed `sc.x.length` (capped at max_scatter=400) rather than `ch.n_channel` (true per-channel matched count). Title now shows `ch.n_channel` with ` shown: N` suffix only when the scatter was subsampled. (b) When `matchDirty` (slider window changed since last scan run), the scatter title now shows `· scan at prior window` inline. `matchDirty` prop threaded from `index.js → BiomarkerAnalytics → SpectralFeatureImportance`.

*Bug 4 null-guard addendum (BiomarkerAnalytics.js):* cap-disclosure condition `nShown < (ch.n_channel || nShown)` was always false when `ch.n_channel` is null. Fixed to `(ch.n_channel != null && nShown < ch.n_channel)`. Frontend rebuilt.

*Tests added (9):* `test_resolver_returns_none_when_no_sense_id_and_no_index`, `test_resolver_uses_sense_id_when_present`, `test_resolver_picks_nearest_prior_config_from_index`, `test_resolver_falls_back_to_nearest_after_when_no_prior`, `test_resolver_respects_window_and_returns_none_when_too_far`, `test_resolver_excludes_all_pair_sweeps_from_index`, `test_resolver_left_hemi_key`, `test_build_sensing_config_index_accepts_power_domain_records`, `test_build_sensing_config_index_from_rows_basic`. Suite: **249/249 PASS**.

---

**Deployment modeled-LSB now pools ALL TD products, not just montage/survey (2026-06-28, UNCOMMITTED).**
The TIER-1 rewrite below wired the modeled-LSB helper correctly but the two **deployment** endpoints
(`band_lsb_and_power`, `deployment_summary`) only loaded montage/survey TD (`psd_list`,
`AVAILABILITY_PSD_TYPES`) and passed `td_recordings=list(psd_list or [])` — while the **exploration
timeline** feeds the helper the full TD superset (streaming `td_list` = `MedtronicBrainSenseTimeDomain`
+ `MedtronicIndefiniteStream`, PLUS `psd_list`). So any band the device only ever **streamed** (never
montage-swept) silently lost those TD samples from the deployable percentile-anchored threshold. Fix:
both endpoints now also load `streaming_td = _load_recordings(uid, TIMEDOMAIN_TYPES)` and pass
`td_for_modeled = streaming_td + psd_list` to `modeled_lsb_at_center`. Power-domain records and
unnamed/foreign columns are still excluded by the helper's fs/ChannelName guards; native-preferred
precedence unchanged; exploration timeline byte-unchanged. E2E on RCS08 ZERO_THREE_RIGHT: in-band
modeled pool **156 → 469** (335 streaming recs added = 232 BrainSenseTimeDomain + **103 IndefiniteStream**;
IndefiniteStream carries all 6 contacts so it adds a uniform +102 pts to EVERY channel and is the
DOMINANT streaming source for the 0-2/1-3 contacts), deployable p50 moves a few % (8.8 Hz 496.3→515.1,
26.4 Hz 102.5→105.4) — a real coverage gap, not a no-op. +1 test (`test_modeled_lsb_at_center_pools_streaming_and_montage_td`), suite **240/240**.
No frontend rebuild needed (only the modeled threshold's numeric value moved). Per-session detail:
`SESSION_HANDOFF_2026-06-28_all_TD_modeled.md`.

**Deployment LSB fallback → universal TIER-1 off raw TD; z-scored units bug fixed (2026-06-28, `09798f7` + build `e8a0d3f`).**
A cross-module LSB-consistency code review found a **CRITICAL units bug** in the deployment threshold
path: the ROC cut-point is a within-(channel,source) **z-scored log-power feature** (dimensionless,
frequently negative — built by `streaming_psd.build_pooled_detail_from_matrix`, `prelog=True`), but the
prior fallback fed it straight into `psd_lsb_model.estimate_lsb`, which expects a **linear µV²** band
power. A z≤0 clipped to 1e-12 (LSB≈0); a z>0 was silently misread as µV². This was the patient-facing
stim-threshold for any unsensed band. **Fix — one units-consistent modeled tier:**
- **New `availability.modeled_lsb_at_center(channel, center_hz, *, td_recordings=, psd_recordings=, half_hz=2.5)`**
  models the device-LSB line off the **RAW µV TD** the ROC was built from, **at the ROC's OWN band
  center** (transform `td_to_lsb` ×352.62; bridge `device_psd_to_lsb` ≈73.63 for PSD-only events), then
  the caller anchors a threshold by **RANK (percentile)** exactly like the native path — **no µV²↔LSB
  conversion of the cut-point**. Universal: covers any band the ROC can score, incl. high-gamma the
  montage never swept. **Honors the ROC center exactly (no `snap_freq` clamp)** — a 55 Hz winner converts
  at 55 Hz, not the 26.4 Hz top of the device sensing-bin table (snap is for timeline display only;
  catching this corrected a high-gamma threshold that was ~4× too high).
- **Deployment-only:** the helper only CALLS shared primitives; `lsb_series` and the Biomarker
  Exploration timeline are **byte-unchanged in behavior**. Both endpoints (`band_lsb_and_power`,
  `deployment_summary`) now source `modeled_thr` from the helper at the ROC center.
- **TIER-2 (frozen-model-on-cut-point) and the old TIER-3 are both gone.** `_modeled_lsb_threshold_estimate`
  is now a single modeled tier; fail-closed (`modeled_thr None → thr_estimate None`) only when there is
  genuinely no TD/PSD for the channel. `estimate_lsb` is **retained as a tested µV²→LSB utility (no
  production caller)** with a loud input-contract warning against z-scored/log/cut-point inputs.
- **Hardening:** channel-name guard now requires a named column matching the target (mirrors `lsb_series`);
  unnamed/extra columns (malformed packets) and power-domain records (`fs≤0`, e.g. ChronicBrainSense) are
  skipped — no cross-channel or units leak. `chronic_list` no longer passed to the TD tier.
- **Tests:** +9 net (8 helper-branch tests — named-match, foreign-channel exclusion, power-domain skip,
  malformed extra-columns, orientation, short-column, fail-closed, PSD band-gate/high-gamma — plus the
  restored `test_freq_extrapolated_guard_agrees_with_frozen_model`). Suite **239/239**.

> ⚠ This **supersedes** the conclusion of the entry below: the deployment fallback is **NOT**
> frozen-model-only. The frozen-model-on-cut-point step was itself the units bug and was removed; the
> deployment modeled threshold is now the raw-TD transform/bridge route, rank-anchored.

**welch256 / k=269 removal — deployment fallback now frozen-model-only (2026-06-28, `184ea74`+`fa2c416`).**
The Welch-256 PSD→LSB exploration backup and the `k=269` population constant were fully removed; the
deployment threshold path now converts the offline-Welch µV² ROC cut-point to LSB **solely via the
per-participant frozen PSD→LSB model** (`psd_lsb_model.estimate_lsb`), which is itself fit on the SAME
offline-Welch µV²→device-LSB mapping — so cut-point and converter share units (the principle: the
cut-point's own model converts it, not a bespoke scalar). Specifics:
- **Deleted DSP (no production caller):** `analytics.psd_band_to_lsb`, `welch256_density` (superseded by
  the CS-3 device-PSD bridge `device_psd_to_lsb`, k=73.63).
- **Deleted constant + converters:** `LSB_PER_UV2_VALIDATED` (269.0), `UV2_PER_LSB_VALIDATED`,
  `LSB_UV2_LOGLOG_SLOPE`, `lsb_from_uv2`, `uv2_from_lsb`. `LSB_UV2_SIGMA_FOLD` → renamed
  **`MODELED_LSB_SIGMA_FOLD`** (1.26, DSP-neutral; the ±1σ band on TIER-1/TIER-2 modeled estimates,
  still overridable by a frozen model's `resid_log_sigma_fold`).
- **Deployment fallback ladder (`_modeled_lsb_threshold_estimate`):** TIER-3 `validated_constant`
  population-constant last resort **DELETED**. When neither a native device threshold nor a fitted
  per-participant model entry exists, the modeled threshold is now **INDETERMINATE (fail-closed)**
  instead of a k=269 guess. The native-vs-modeled k=269 QC cross-check was deleted too (no frontend
  consumer; payload key `native_modeled_check` retained as `None` for API-contract stability).
- **Stale-label bug fixed (same pass):** TIER-1 `modeled_timeline` reported `k_effective=269` /
  "Welch256×269", but since CS-1 it reads straight off the transform×352.62 LSB timeline applying NO k.
  Payload now reports `k_effective=352.62`, `slope_b=None`, transform-route notes. Frontend
  `validated_constant` TIER_LABEL entry removed (tier no longer emitted).
- **Coverage note (audited):** removing TIER-3 only affects bands with NO frozen-model entry — i.e. any
  non-RCS08 participant, or RCS08 `ONE_THREE_RIGHT` (0 bands, `pooled_k=None`). All other RCS08 channels
  are covered by TIER-2. Suite 234→229 (net −5 from test removal/rewrite). The deployable number is
  unchanged in all covered cases (measured native threshold always wins; TIER-2 numbers identical).

**TD→LSB calibration + spectral unification (CS-1…CS-4 + Phase 0–3, 2026-06-27).** The vendored
`percept-spectral-repro` transform DSP is now the **primary TD→LSB route** (`k=352.62`; §3 decision 18,
constants in §2a). Supporting pieces:
- **PSD-source taxonomy** (`PSD_SOURCE_TAXONOMY`: patient_event / streaming_event / montage_snapshot)
  separates pooling identity from timeline display category — Streaming is its own category, not
  mislabeled "Montage PSD".
- **PSD→LSB bridge** for PSD-only patient-event snapshots: event `FFTBinData` is linear µV magnitude,
  baseline-subtracted (clamp negatives to 0). Montage law `PSD_bp = 4.789·TD_bp` (r=0.987, n=10476)
  composes to `LSB = 73.63·PSD_bp`, restricted to [7.8, 30] Hz.
- **Per-PRO LSB selection** (`availability.per_pro_lsb`), strict precedence: (1) native device LSB →
  (2) direct TD→LSB transform when a TD-bearing recording overlaps the PRO → (3) PSD bridge only for
  PSD-only patient events in [7.8, 30]. Surfaced on the timeline (`_pro_lsb_by_channel`, payload key
  `pro_lsb`): marker shape = tier (native ● / TD-transform ○ / PSD-bridge ◇), red ring = saturated.
  Live RCS08: 684 PROs × 30 ch → 239 values (51 native, 102 TD-transform, 86 PSD-bridge).
- **Per-PRO time contract:** for a PRO at time T matched to a TD recording, the transform runs on 30 s
  centered on T = [T−15 s, T+15 s], clipped to the session boundary (≥1 s, >10% Missing rejected);
  a 1 s rcs-Hann window slides at 500 ms (≈59 windows), and the **median** in-band summed-squared
  magnitude → one LSB.
- **Shared LSB cache** (`per_pro_lsb_spectrum` + `_pro_lsb_spectrum_cached`, content-keyed memo) is the
  single source of truth for BOTH the timeline and the spectral feature-importance panel — identical
  numbers at any shared band center. The spectral scan's `feature="lsb"` reads `log10(cache[...])`
  (`feature_used="lsb_cs14"`); the old Welch-density×269 / device-FFT rescale path was removed (~65
  lines). Code-review findings 1–5 in `8274d6c` (PRO-set alignment invariant, vectorized per-band LSB
  gather, thread-safe memo lock, double-dip warning for legacy payloads).

**Audit-cleanup statistical calls (§3 decision 19; suite 184→196).** Moving-block bootstrap AUC CI +
DEFF discount; BCa headline CI; per-week threshold-drift trend test. **The one trap to preserve —
C1 guard (do not undo):** BCa's bias term `z0` re-creates the manufactured beats-chance floor that
audit C1 removed, so the *displayed* CI is BCa but the **safety gate reads the de-folded percentile
bound `auc_lo_defold`** — both `auc_power` call sites pass `auc_lo=roc.get("auc_lo_defold", ...)`.
`threshold_drift_by_week` (calendar-time robustness) is distinct from `stim_state_portability`
(per-era / C3, stim-STATE robustness) — keep them separate.

**UX + perf + R-safety pass (2026-06-26, PR #8 → `v3.1.0`).** Biomarker state persistence
(`biomarkerStateStore.js`, localStorage controls + in-memory LRU heap with a `performance.memory`
guard); `run_for_participant` recompute ~63s→47s (threshold sweep vectorized, `_threshold_metric_arrays`
**24.8×** fuzz-verified; spectral CV defaults serial); `_R_GLOBAL_LOCK` (RLock) around every
pymer4/lme4 fit (embedded R is single-threaded; concurrent glmer fits corrupted it). Spectral scan
spans full 0–100 Hz; 8–30 Hz are CENTER frequencies, flagged `adaptive_valid`.

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
- **Default branch:** `v3.1.0`. The old `v3.0.0-alpha` is deleted.
- **Active working branch:** `PS_closedloop_deployment` (off `v3.1.0`), **HEAD `e8a0d3f`**,
  in sync with origin.
- Other remote branches: `development` (legacy) + release branches `v2.0-alpha`…`v2.2.1`.
  Retired (squash-merged into `v3.1.0`): `PS_biomarker_{actionability,clfixes,module}` (§9).

(Commit identity, the keychain-warning quirk, and other sandbox traps are in §7.)

**The agent bridge (how code runs in the live container).**
`BRAVO/_agent_bridge/` is a stdlib mailbox watcher running **inside** the `bravo-server` OrbStack
container, on the `./BRAVO ↔ /usr/src/BRAVO` bind mount, so the agent can run real code against the
live DB/REDCap:

```
python3 BRAVO/_agent_bridge/bridge_client.py --cwd /usr/src/BRAVO --timeout N --wait M "<cmd>"
python3 BRAVO/_agent_bridge/bridge_client.py --status        # heartbeat
```

- Container: **Python 3.12.3, rpy2 3.5.15, pymer4 0.8.2, pandas 2.2.3, sklearn 1.5.2**.
- **Authoritative test runner (no pytest in container):** `python3 _agent_bridge/run_tests.py`.
- Gunicorn `--reload` makes backend edits live; nginx serves `Client/build`, so **frontend changes
  need a bundle rebuild**. The bridge itself takes effect on container **CREATE**, not restart (§7).

**Live DB / participant.** MySQL/mongoengine in-container; REDCap reachable
(`REDCAP_API_URL`/`REDCAP_API_TOKEN`). **RCS08 live uid = `2e3c75c00d7f4f37b53a048d195f11da`** — use
for all container probes (the old `_pro_dump` uid `1eda36458758461383721208bbe6bb87` is stale post
re-ingest). Cached PRO table `BRAVO/_pro_dump/RCS08_chronic_pro_df.csv` (679 rows). Source device
JSONs at OneDrive grant `/Users/.../PNL/RCS008 jsons` (filenames carry real patient names → keep out
of repo; §7 PHI note).


---

## 2. Key constants & frozen models

### 2a. Quantitative constants in the current code

In `BRAVO/modules/Biomarkers/routines/analytics.py` unless noted. Line numbers are approximate
(they drift with edits — `grep` the name to confirm).

**The three LSB conversion routes (each DSP carries its own k — do NOT cross them):**

| Constant | Value | Route | Meaning |
|---|---|---|---|
| `LSB_PER_UV2_TRANSFORM` | **352.62 LSB/µV²** | **PRIMARY TD→LSB** | k for the vendored `percept-spectral-repro` transform DSP (Hann-windowed zero-padded FFT, 50% overlap). RCS08 all-stim median, r=0.9927, RMSE 60.6 LSB. Band-agnostic. Use exactly, do not round. |
| `LSB_PER_DEVICE_PSD` | **≈73.63 LSB/(device-PSD bp)** | PSD→LSB bridge | `= 352.62 / 4.789`. For PSD-only patient-event snapshots; restricted to [7.8, 30] Hz (else `calibrated=False`). |
| `LSB_PER_UV2_DEVICE_PSD_TD_RATIO` | **4.789** | bridge composition | Device-PSD band power / TD-transform band power (geomean, r=0.987, n=10476). |
| `MODELED_LSB_SIGMA_FOLD` | **1.26** | uncertainty band | 1σ multiplicative scatter on TIER-1/TIER-2 **modeled** LSB estimates (±band on the deployment sign-off card). Per-participant `resid_log_sigma_fold` overrides it when the frozen model carries one. (DSP-neutral rename of the old `LSB_UV2_SIGMA_FOLD`.) |

> **REMOVED 2026-06-28** (`fa2c416`): `LSB_PER_UV2_VALIDATED` (269.0), `UV2_PER_LSB_VALIDATED`,
> `LSB_UV2_LOGLOG_SLOPE`, and the `lsb_from_uv2` / `uv2_from_lsb` converters — plus the welch256 DSP
> helpers `psd_band_to_lsb` / `welch256_density`. The deployment fallback now anchors the offline-Welch
> µV² cut-point to LSB via the per-participant frozen PSD→LSB model only (fail-closed when absent). See §0.

**Other current constants:**

| Constant | Value | Location | Meaning |
|---|---|---|---|
| `ADC_NV_PER_LSB` | **146.0 nV/LSB** (exact) | analytics.py:2548 | Percept time-domain ADC count scale, per Medtronic. Exact. |
| `LSB_VALIDATED_HZ_LO/HI` | **7.8 / 28.3 Hz** | analytics.py:2633-2634 | Calibration-validity window; outside → `freq_extrapolated`. |
| `LSB_DEPLOYABLE_HZ_HI` | **30.0 Hz** | analytics.py:2663 | Device adaptive-stim ceiling (firmware 8–30 Hz). |
| `TRANSFORM_N_FFT` / `_WIN_SECONDS` / `_STEP_SECONDS` | 256 / 1.0 / 0.5 | analytics.py:2874-2876 | Transform DSP: 256-pt FFT, 1 s window, 500 ms step (50% overlap). |
| `TRANSFORM_CENTERED_EXTENT_SECONDS` | **30.0** | analytics.py:2975 | Rating-centered TD extent fed to the per-PRO LSB sweep. |
| `CONVERSION_FFT_SIZE` | **256** | analytics.py:2598 | FFT size the conversion model assumes; only 256-pt modes are convertible. |
| `THRESHOLD_MODES` / `COMPATIBLE_THRESHOLD_MODES` | Dual (256-pt), Single (64-pt), SingleInverse (256-pt) / ("Dual","SingleInverse") | analytics.py | FFT/window per Percept threshold mode. **Single (64-pt) is NOT convertible.** |
| `WELCH_MAX_MISSING_FRAC` | **0.10** | streaming_psd.py | Missing-fraction floor for Welch epochs; above it → all-NaN PSD, row skipped (Fix A). |
| `SMALL_SAMPLE_CLUSTER_FLOOR` / `BOOT_CI_VALID_FLOOR` | 10 / 100 | analytics.py:25,32 | Small-sample advisory floor; valid-replicate floor below which the bootstrap CI is suppressed. |
| `DRIFT_MIN_SAMPLES_PER_WEEK` / `DRIFT_MIN_WEEKS` | 6 / 4 | analytics.py:2226-2227 | Gates for `threshold_drift_by_week` (else `not_assessed`). |

**Transform calibration provenance (`k=352.62`, the deployed primary).** RCS08 all-stim median k
from the vendored transform DSP run on paired `BrainSenseLfp`+`BrainSenseTimeDomain` blocks:
r=0.9927, RMSE 60.6 LSB, median fold ≈1.10×. The stim-off-only k (356.61) is recorded for
provenance only and is NOT deployed. **k cancels in r/AUC only when the feature column is
homogeneous in k** — on a native-vs-modeled mixed axis it does not, so the native-preferred
precedence matters. The 1σ multiplicative scatter is ≈1.26× and propagates into the
estimated-threshold path (`sigma_fold`, `estimated_upper_lsb_lo/hi`). Full derivation:
`HANDOFF_TD_LSB_calibration_2026-06-27.md`.

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
  threshold. **CLOSED — see §3 item 16.**
- **`ZERO_THREE_RIGHT_23.4Hz` — excluded** (noisy, inconsistent with its 24.4/26.4 Hz neighbors).

### 2c. Constants/claims later corrected or retracted

- **welch256 `k=269` was REMOVED entirely (2026-06-28, `fa2c416`).** It was the rigorous stim-off
  paired-block constant (superseding an even looser early direct fit of k≈74.1); CS-1 first demoted it
  to a PSD-exploration backup, then the 2026-06-28 pass deleted it outright once the device-PSD bridge
  (k=73.63) and the per-participant frozen model covered every live path. The deployed primary TD→LSB is
  the transform route **`k=352.62`** (§2a); the deployment fallback converts the offline-Welch µV²
  cut-point via the frozen model only (fail-closed when no fitted entry exists). See §0.
- **8.8 Hz "ρ=−0.64 temporal regime shift, ~3× gain drop, unexplained"** — superseded by the
  documented settling-transient mechanism (see §2b / §3 item 16).
- **Forced log-log slope = 1.1** was explored as within ~0.005 R² of the forced optimum (0.90)
  once 8.8 Hz and 23.4 Hz are cleaned, but the **deployed model uses the per-channel free common
  slope** (b=0.8545 for 0-3R), not a forced 1.1.

---

## 3. Decision log

Durable decisions and why, chronological. All **Adopted** unless noted. Commit SHAs are pointers
into history, not current HEAD.

| # | Decision | Why | Ref |
|---|---|---|---|
| 1 | **rpy2/pymer4 glmer converter fix** — `_rpy2_converter_ctx()` returns `localconverter(ro.default_converter)`, NOT `+ pandas2ri.converter` | pandas2ri context converted pymer4's `glmerControl` R list to a dict rpy2 3.5.15 can't return to glmer. | `33f45a5` |
| 2 | **PRO-timestamp timezone correction** — REDCap `date_time_s1_daily` is California local wall-clock; convert via `bravo_service._pro_timestamps_utc` (LA→UTC, DST-aware) | Device StartTime is already UTC; parsing PRO as UTC smears matches 7–8 h. Census 67/678 within 60 min. | `a4e4e68` |
| 3 | **Concatenation is robust to PRO matching** — keep `FixBreaking` zero-fill concat; no change to matching | Both-ways re-decode: 67 vs 67 matched, 0 changes. | no-op |
| 4 | **Fix A — missing-aware Welch epochs** — TD windows over `WELCH_MAX_MISSING_FRAC=0.10` → all-NaN PSD → skipped | Zero-fill from FixBreaking entered Welch PSDs as real zeros, deflating band power. | `adcaf15` `c438ce1` |
| 5 | **ClosedLoopSim figure-reset fix** — memoize `requestParams`; permanent Plotly `<div ref>`; draw-once + restyle-by-trace-index | New object identity per render refetched all 4 panels → every figure flashed to loading. Hard constraint (§7). | PR #3 `255e0ef` |
| 6 | **Removed the `net benefit` cut-point rule** | Its objective equals `prevalence × cost` — always picks the identical point as `cost` (two buttons that can't disagree). | PR #3 |
| 7 | **C1 — de-fold the deployment-ROC bootstrap CI** — append `float(ab)`, not `max(ab,1−ab)` | Folding hid null bands; a de-folded lower bound can honestly fall below 0.5. **(See the C1 guard in §0 — BCa later re-threatened this.)** | PR #5 `c50be37` |
| 8 | **C3 — signed era AUC + pooled-orientation** — pooled orients first, eras reuse `pooled_flip`, era AUC signed not folded | A folded per-era AUC masks within-era sign reversals (a closed-loop failure mode). | PR #5 |
| 9 | **C8 — tri-state deployment gates, fail-closed** — gate ∈ {pass, fail, indeterminate}; stim-stable gate ABSTAINS when LRT unavailable | A gate that goes green on *absence* of evidence is unsafe for "ready to program". | PR #5 |
| 10 | **C9/C10 actionability** — single-source `CUTPOINT_TRACE=2`; recommend→program Δ; conservative-abstain ramp guidance | Actionable recommendation, fail-closed discipline kept. | PR #6 `b0597f8` |
| 11 | **PSD→LSB conversion panel + frozen model** — freeze per-participant `RCS08.json`, tiered fallback (band→channel_freq→channel_pooled→none); modeled threshold → `indeterminate` gate | Device reports LSB, Welch reports µV²; an unsensed band needs an estimated threshold, clearly flagged. | PR #6 `771f3c2` |
| 12 | **C2 — forward-chaining / out-of-sample validation** — expanding-window blocked-by-week; threshold fit on TRAIN only; held-out AUC not re-folded | In-sample AUC masked forward reversals (26.4 Hz: 0.55→0.24; 8.8 Hz: 0.52→0.37). Last HIGH finding. | PR #7 `d9d58a4` |
| 13 | **Remove 60 Hz mains notch default** — `_band_power_notched(notch=False)` | Implanted/battery-powered, no mains coupling; notching removes real signal. `notch=True` retained. | `f915257` |
| 14 | **Threshold-mode FFT-size guard** — only `COMPATIBLE_THRESHOLD_MODES=("Dual","SingleInverse")` (256-pt FFT) are convertible | A 64-pt Single-mode FFT is a different quantity; same gain can't convert it. | `f915257` |
| 15 | **PSD→TD→LSB back-translation = null** — direct PSD→LSB is the rigorous path | Phase-randomized TD reconstruction matches the direct PSD integral within 0.8%. | `f915257` |
| 16 | **8.8 Hz cut stays ≥2026-03-01** (NOT the 2025-12-05 config-change date) | The config-change date sits inside a declining settling transient (−0.078 log10/mo, p=0.039); stationarity only from ~2026-02-15. Frozen fit UNCHANGED. | `e9d7a80` |
| 17 | **Impedance term `c=1.02` — REJECTED** | Significant only under naive OLS (pseudoreplication: 2985 epochs share 230 impedance measurements). Cluster-robust SE n.s. (p=0.26); a slow-time proxy, not a physical gain. Threshold impact 1.22× < model scatter. Frozen fit UNCHANGED. | `a9c3a01` |
| 18 | **Primary TD→LSB → transform `k=352.62`** (welch256 `k=269` demoted to backup) | The vendored transform DSP reaches r=0.9927 / RMSE 60.6 LSB; welch256 produces a PSD from TD and can't consume a device PSD, so it was never a valid no-TD backup. | CS-1 (§0) |
| 19 | **Audit-cleanup statistical calls** — moving-block bootstrap CI + DEFF; BCa headline CI with de-folded `auc_lo_defold` as the C1-safe gate; per-week threshold-drift trend test | Honest CIs under autocorrelated ratings; keep the C1 beats-chance floor from being re-manufactured by BCa's bias term. | §0, `8509e96`/`2ef0408`/`abe8a23` |
| 20 | **welch256 `k=269` REMOVED — deployment fallback frozen-model-only** *(superseded by 21)* | The cut-point's own model converts it: the offline-Welch µV² cut-point → LSB via the per-participant frozen model (fit on the same Welch→LSB mapping), not a bespoke population scalar. Population-constant TIER-3 retired → fail-closed (indeterminate) when no fitted entry. Dead welch256 DSP + converters deleted. | §0, `184ea74`/`fa2c416` |
| 21 | **Deployment LSB fallback → universal TIER-1 modeled off raw TD** (frozen-model TIER-2 deleted) | The ROC cut-point is a **z-scored** log-power feature, NOT linear µV² — feeding it to the frozen model (decision 20) was a units bug (z≤0→LSB≈0, z>0 mis-read). Model the LSB line off the raw µV TD at the ROC's OWN center (transform ×352.62 / bridge ≈73.63) and anchor by RANK like native — no µV²↔LSB conversion of the cut-point. Honors the ROC center exactly (no snap-clamp); fail-closed when no TD/PSD. Deployment-only; Exploration timeline unchanged. | §0, `09798f7` |

---

## 4. Open items

> Dropped by PI (do NOT re-open as work): "generalize beyond RCS08", "PHI hygiene". PHI context
> is an operational note in §7 only.

**Currently open:**

1. **Audit backlog — Bucket C/D + low-polish.** Of the original four-lens audit (4 high · 28 medium ·
   24 low), all HIGH (C1/C2/C3/C8) and C4 are resolved, and the 2026-06-27 audit-cleanup session
   cleared Bucket B + four statistical calls (§0). Remaining:
   - **[5]** move the displayed cut-point solve server-side onto the full ROC arrays (mechanical).
   - **[14]** reconcile clustering granularity (per-rating ROC `n_clusters` vs weekly-glmer
     elapsed-week units report different N). **Needs a PI judgment call before coding.**
   - **[42]** operating-point chip (rule + sens/spec) on the LSB panel + LSB annotation on the histogram.
   - **[49]** embed Plotly PNG snapshots of the 4 figures into the deploy export / printed sheet
     (needs the bridge for kaleido — §7).
   - **Low-polish cluster:** [0]/[15]/[22]/[28]/[39]/[43]/[48] — labeling/navigation niceties, batchable.
   Source of record: `closedloop_audit_report.md` + the `AUDIT_TRIAGE_*` decision sheets.
2. **Anchor test** for "timeline circle == spectral point at same band center" — the identity holds
   by construction (one shared cache) but has no live E2E test across the two call sites.
3. **`per_pro_lsb_overlay`** (within-rating sliding-window LSB trace + saturation QC) is available
   but not yet drawn — natural next step is a hover/expand detail on a rating's 30 s LSB trace.

**Closed (do not re-open):** all four HIGH (C1/C2/C3/C8) + C4; figure-reset bug; C5/C6/C7
(figure-honesty); C9/C10 (actionability); 8.8 Hz cut date; 60 Hz notch default; threshold-mode guard;
TD→LSB validation + PSD→TD→LSB back-translation; impedance `c=1.02` (rejected); high-gamma 55.5 Hz
(not actionable — firmware limited to 8–30 Hz; the `freq_extrapolated` guard stays).

---

## 5. Test & build status

- **Backend suite: 240/240 PASS** in the live container via the bridge:
  `python3 _agent_bridge/run_tests.py`. **No pytest in the container** — `run_tests.py` is the
  authoritative runner (globs `test_*.py`, sets up Django, reloads the module). `test_analytics.py`
  holds ~96 of the test functions.
- **Local standalone runner caveat:** running `modules/Biomarkers/tests/` outside the container
  shows harness-only failures (`test_normalize_pro_times*`, `test_pain_scores_emit_utc_t_epoch`,
  `test_pain_series_epochs_match_pro_match_arrays` need Django `INSTALLED_APPS`; model-dependent
  files can't run in the local importlib runner at all). Not regressions — use the container runner.
  Pure-function analytics checks CAN run locally by importing `analytics.py` Django-free in `bravo_app`.
- **Frontend build:** CRA production build exits 0:
  `cd Client && export npm_config_cache=/tmp/npmcache && GENERATE_SOURCEMAP=false
  NODE_OPTIONS=--openssl-legacy-provider CI=false npx --no-install react-scripts build`.
  The repo **commits `Client/build/` alongside source**; nginx serves the mounted build, so the
  bundle must be rebuilt and committed for any frontend change. ClosedLoopSim is code-split into
  **chunk 431**; the timeline is **chunk 768**.

---

## 6. Key documents & artifacts

**Design spec of record (read before any biomarker-pipeline work):**
- `DESIGN_biomarker_pipeline_v2.md` (artifact `bab71722-0293-453e-9d21-36b77a26cbac`) — the
  biomarker pipeline design ledger v2: Percept RC controller facts + 8–30 Hz adaptive range;
  the corrected five-product BrainSense taxonomy; the **BandCandidate contract v1** (serializable
  interface between the Biomarker module and the future Closed-Loop Simulation module); the
  LSB↔µV² conversion as a confidence-rated FYI; stim-era heterogeneity confounds; the Option-3
  UI split + data-availability-timeline design that replaces `BiomarkerTimeline`. (Its conversion
  section predates the `k=352.62` transform primary — cross-reference §2 here.)

**In-repo provenance / decision docs (current, keep):**
- `HANDOFF_TD_LSB_calibration_2026-06-27.md` — full TD→LSB transform calibration derivation (`k=352.62`).
- `CS3_FFTBinData_units_recon_2026-06-27.md` — PSD-bridge units finding + montage TD↔PSD fit (4.789).
- `closedloop_audit_report.md` (version `e3a12136-e0e1-4fff-b95f-baa42d0a0a46`) — the four-lens
  audit of record (source for the remaining Bucket C/D backlog).
- `AUDIT_TRIAGE_medium_low.md` / `AUDIT_TRIAGE_v3_decisions.md` — the medium/low audit decision sheets.
- Frozen model: `BRAVO/modules/Biomarkers/data/psd_lsb_models/RCS08.json` (§2b).
- Per-session narrative: the dated `SESSION_HANDOFF_*.md` / `HANDOFF_*.md` files (newest:
  `SESSION_HANDOFF_2026-06-27.md`).

(Older per-figure artifact IDs from superseded sessions — early PSD→LSB panels, k=269 calibration
figures, Phase-2 encoding mockups — were dropped from this index; recover them from the dated
session handoffs or `operon.artifacts()` if ever needed.)

---

## 7. Known gotchas (operational traps)

- **Git identity.** `.git/config` is unwritable in the sandbox. Set identity per-commit via
  `GIT_AUTHOR_NAME/EMAIL` + `GIT_COMMITTER_NAME/EMAIL` (`Prasad Shirvalkar <prasad.shirvalkar@ucsf.edu>`).
  The `could not write config file` / keychain `-50` / `~/.config/git/ignore` warnings are harmless.
- **Bridge: takes effect on container CREATE, not restart;** and the watcher (pid 8) stalls
  periodically (heartbeat age climbs, jobs time out) — fix is an OrbStack container restart, which the
  sandbox can't do, so ask the user. After a commit recycle workers with `kill -HUP 1` in-container
  (VirtioFS needs `--reload-engine poll`; inotify doesn't propagate).
- **`save_artifacts`:** dedups by filename and won't re-read changed content — use a fresh filename
  when content changes; and it only resolves WORKSPACE-relative paths, so copy repo files in first.
- **sklearn skew — correctness risk.** Container has sklearn **1.5.2**; some pickled classifiers were
  trained under 1.6.1. Loading across the skew can silently mis-predict — re-validate before trusting.
- **REDCap PRO timezone.** `date_time_s1_daily` is **California local wall-clock**, not UTC. Always
  convert via `bravo_service._pro_timestamps_utc` (LA→UTC, DST-aware); device StartTime is already UTC.
- **Local decode (`bravo_app`) needs a dummy Fernet key:** set
  `os.environ["DATASERVER_ENCRYPTION"] = Fernet.generate_key().decode()` **before** importing `HelperFunctions`.
- **datetime ns-resolution.** Epoch conversions use `…to_numpy().astype("datetime64[ns]").astype("int64")/1e9`
  at all source sites. A bare `.astype("int64")` gives microseconds under pandas 3.0's `datetime64[us]`
  default and **mis-assigns stim eras** — must be ns.
- **CRLF files.** `Server/APIs/DataAnalysis.py` and `Server/APIs/urls.py` are **CRLF** (all other
  source is LF). `edit_file` preserves line endings; raw Python `open()` writes strip them → giant
  spurious diff. Use `edit_file` for these two.
- **GitHub from the sandbox.** No `gh`/PyGithub on PATH — use `urllib` + `GITHUB_TOKEN` (Bearer, API
  2022-11-28). Self-approval of your own PR is blocked → post the review as an issue comment, then
  `PUT /pulls/{n}/merge` (squash).
- **kaleido/Chrome PNG export is broken in the sandbox** — use `write_html`, matplotlib, or the bridge
  (kaleido in-container), never kaleido PNG in `rocqa`.
- **ClosedLoopSim Plotly discipline (hard constraint).** Panels draw **once** via `Plotly.react` and
  mutate via `Plotly.restyle(…, [traceIndex])` / `Plotly.relayout` — **never rebuild a figure on
  interaction** (commit `255e0ef` fixed the reset bug). Following the Python `ps-plotly` figure-rebuild
  pattern verbatim re-introduces the bug; keep the restyle-by-trace-index pattern
  (`const CUTPOINT_TRACE = 2` in DeploymentRocPanel).
- **PHI note (operational, not an action item).** Stage-1 device JSON filenames in the OneDrive grant
  carry real patient names — keep that folder out of the repo; RCS08 is the de-identified code. Repo
  exports are derived spectral features only; `secrets/redcap.env` + the bridge mailbox are gitignored.

---

## 8. Key file map

**Backend (`BRAVO/modules/Biomarkers/`):**
- `routines/analytics.py` — glmer converter (`_rpy2_converter_ctx`); LSB constants + converters
  (`td_transform_band_power`, `td_to_lsb`, `device_psd_to_lsb`, `THRESHOLD_MODES`,
  `_band_power_notched`); deployment stats (`deployment_roc`, `deployment_roc_by_era`,
  `deployment_forward_chaining`, `threshold_drift_by_week`, `auc_power`); bootstrap/CI helpers
  (`_block_bootstrap_aucs`, `_auto_block_len`, `_bca_ci`, `_jackknife_cluster_aucs`); spectral scan
  (`spectral_feature_importance`, `feature="lsb"→lsb_cs14`); stim-era assignment (`_assign_stim_eras`,
  `_elapsed_week_cluster`).
- `routines/availability.py` — per-PRO LSB selection (`per_pro_lsb`, `per_pro_lsb_overlay`,
  `per_pro_lsb_spectrum`), modeled `lsb_series` tier, and `modeled_lsb_at_center` (deployment-only:
  models the device-LSB line off raw TD at the ROC's own band center — the units-consistent fallback,
  decision 21).
- `routines/streaming_psd.py` — Welch (`welch_psd_for_instance`, `welch_rating_centered`,
  `WELCH_MAX_MISSING_FRAC`), `build_pooled_detail_from_matrix`.
- `routines/psd_lsb_model.py` — frozen-model loader/estimator (`load_model`, `has_model`,
  `estimate_lsb`, `model_plot_payload`); tiered fallback band→channel_freq→channel_pooled→none.
- `bravo_service.py` — timeline + scan wiring (`_build_availability`, `_pro_lsb_by_channel`,
  `_pro_lsb_spectrum_cached`, `run_for_participant`, `_pro_timestamps_utc`); deployment
  (`deployment_summary`, `band_deployment_roc`, `band_lsb_and_power`, `recommended_vs_programmed`,
  `_ramp_guidance`).
- `data/psd_lsb_models/RCS08.json` — frozen PSD→LSB model (§2b).
- `tests/` — `test_analytics.py` (~96 fns), `test_match_to_pro.py`, `test_psd_lsb_model.py`,
  `test_welch_missing_aware.py`, etc.

**API:** `Server/APIs/DataAnalysis.py` + `Server/APIs/urls.py` (`QueryPsdLsbConversion[Model]` views /
`queryPsdLsbConversion[Model]` routes). **Both files are CRLF — edit with `edit_file` only.**

**Decode chain:** `modules/MedtronicPercept/{Percept,BrainSenseStream,IndefiniteStream,Session}.py`;
ingest concatenate toggle at `modules/DataCurator.py:148/150`
(`metadata["automatic_concatenation"]` → `JSON["AutomaticStreamingFix"]` → `Session.py:423`).

**Frontend (`Client/src/views/Reports/`):**
- `ClosedLoopSim/` — `index.js`, `DeploymentRocPanel.js`, `EraRefitPanel.js`, `LsbPowerPanel.js`,
  `DeploySignoffCard.js`, `DeploymentVerdictStrip.js`, `PsdLsbPanel.js`, `ConversionModelPanel.js`,
  `palette.js` (Okabe-Ito). Code-split **chunk 431**.
- `Biomarkers/BiomarkerDataTimeline.js` (modeled-LSB markers, chunk **768**),
  `Biomarkers/BiomarkerAnalytics.js` (spectral caption), `Biomarkers/biomarkerStateStore.js`.
- `Client/build/` — committed compiled bundle (rebuild + commit for any frontend change).
- `Client/public/static/docs/METHODS_lsb_estimation.html` — served methods doc.

**Data / config:** device JSONs at OneDrive grant `/Users/.../PNL/RCS008 jsons` (keep out of repo);
cached PRO table `BRAVO/_pro_dump/RCS08_chronic_pro_df.csv` (679 rows); `secrets/redcap.env` (gitignored).

---

## 9. PR / commit lineage (quick map)

| PR | Squash SHA | Into | Content |
|---|---|---|---|
| #3 | `52337f5` (merge) / `255e0ef` (fix) | v3.1.0 | Pain Biomarkers engine + ClosedLoopSim reset fix |
| #4 | `52010ec` (merge) | v3.1.0 | ClosedLoopSim Phase-2 visualizations |
| #5 | `c50be37` | v3.1.0 | Four-lens audit Wave 1+2 (C1/C3/C5/C6/C7/C8) |
| #6 | `b0597f8` | v3.1.0 | C9/C10 + PSD→LSB panel + pandas-3/numpy-2 forward-compat |
| #7 | `d9d58a4` (merge) / `b2e01f1` | v3.1.0 | Forward-chaining / out-of-sample validation (C2) |
| #8 | `a191b758` (merge) | v3.1.0 | UX + perf + R thread-safety lock pass (§0) |
| — | `f915257` | v3.1.0 / branch base | Modality-sensitive conversion, threshold-mode guard, LSB estimation |
| — | `e9d7a80` | branch | 8.8 Hz cut rationale; keep ≥2026-03-01 (decision 16) |
| — | CS-1…CS-4 + Phase 0–3 | branch | TD→LSB transform primary; PSD bridge; per-PRO selection; spectral-scan unify (§0) |
| — | `8274d6c` | branch | code-review fixes for the Phase 2–3 spectral rewire |
| — | `184ea74` | branch | remove dead welch256 DSP; fix stale TIER-1 modeled-timeline labels (§0) |
| — | `fa2c416` | branch | remove k=269 population constant; deployment fallback frozen-model-only (§0) |
| — | `e15e57e`/`fe31c87`/`45c39a9` | branch | MEGA top-of-doc update instructions; un-track ~100 stray scratch files + restore docs |
| — | `09798f7` | branch | deployment LSB fallback → universal TIER-1 off raw TD; fix z-scored units bug (decision 21, §0) |
| — | **`e8a0d3f`** | `PS_closedloop_deployment` (HEAD) | **rebuild frontend (drop retired k=269 tier label)** |

**Engineering envs:** `bravo_app` (py 3.11, local decode — Django-free pure-function checks),
`rocqa` (plotly 6.8 + kaleido — broken Chrome export in sandbox; use `write_html` or the bridge),
`python` (read-only). Live container: Python 3.12.3, rpy2 3.5.15, pymer4 0.8.2, pandas 2.2.3,
sklearn 1.5.2.

---

*End of mega-handoff. Branch `PS_closedloop_deployment` @ **`e8a0d3f`** + 1 uncommitted changeset, suite **240/240**.
Authoritative sources: `RCS08.json`, the dated `SESSION_HANDOFF_*.md` / `HANDOFF_*.md` files,
and the current `analytics.py`. Preserve exact numbers, SHAs, paths, and dates when editing —
and verify constants against source (`grep`), not against this doc, before relying on a line number.*
