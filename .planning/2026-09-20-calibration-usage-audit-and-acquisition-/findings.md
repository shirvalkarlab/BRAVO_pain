# Findings: calibration usage audit and acquisition timeline

## Context (from the code, 2026-09-20)
- Constants: `analytics.LSB_PER_UV2_TRANSFORM = 345.59` (voltage trace -> LSB), `LSB_PER_DEVICE_PSD = 72.16` (device FFT snapshot -> LSB, composed = 345.59 / 4.789).
- Readers (grep 2026-09-20): `availability.py` (timeline modeled points, tiers `td_transform`, `psd_bridge`), `bravo_service.py` (modeled threshold tier ~6440-6500; `_raw_lsb_constants_block` ~1243), `DecodeCommon/per_pro_lsb_indexed.py`, `DecodeCommon/representation.py`, `ClosedLoopDeployment/three_source_response.py`; StimOptimizer reads device-native power and neither constant.
- Frozen model `psd_lsb_model.py`: `estimate_lsb` has no live caller since 2026-06-28; the plot payload was deleted in decision 212.
- Stale comments still say 352.62 / 73.63 in `availability.py` (612, 621, 754, 943, 949, 1331, 1340, 1454), `bravo_service.py` 676, `constraints.py` 170, `lfp_evidence.py` 114: comments only, code reads the constants.

## Audit A findings (2026-09-20, verified against the code by the main session where marked *)
1. ERROR* (Closed-Loop page, analyst fold, "LSB & power" card, the muV^2/LSB cross-check line): `analytics.empirical_lsb_ratio` (analytics.py:2883) multiplies the stored voltage trace by 0.146 (ADC nV per count / 1000) before a Welch band power, while `td_to_lsb` and the calibration recipe feed the SAME stored samples in as microvolts. Its printed ratio is 0.146^2 of the platform's unit and on a different recipe (Welch). No constant is multiplied, no threshold moves. Fix: delete the routine and the card line, or compute with `td_transform_band_power` on unscaled samples.
2. RISK (Biomarkers bottom-left refit panel): `band_psd_lsb_conversion` fits k on Welch band power (streaming_psd.py:362, analytics.py:2985) and the page (since 212) prints it as a percentage of the transform constant: two recipes, two constants (lfp_evidence.py:158-160 records transform 352.62 vs Welch-256 270.22). Fix: compute the panel's P with the transform, or drop the percentage sentence.
3. RISK (same panel): the refit's interval, slope check and scatter band are in log10 (analytics.py:3020-3032); the headline k equals the raw median ratio. Already on the PI's list.
4. RISK (Closed-Loop modeled threshold only): `MODELED_LSB_SIGMA_FOLD = 1.26` (analytics.py:2500) is the June log-space scatter of the retired frozen model, applied as the +/-1 sigma band (bravo_service.py:6466-6469).
5. COSMETIC: `LsbPowerPanel.js:258` reads `data.lsb_ratio.sigma_fold`, a field the backend never sends; the bars on an estimated threshold never draw (the field that exists is `threshold_lsb.sigma_fold`).
6. COSMETIC: ~48 comment/docstring lines still quote 352.62 / 73.63 (lists in both reports); no code line carries a stale literal. `DEVICE_percept_rc.md:311` says 131 blocks (now 133).
Confirmed correct: td_to_lsb, device_psd_to_lsb, the timeline's modeled points, the modeled threshold tier (rank, not conversion), per-rating LSB tiers, tiles, event/montage snapshot blocks -> bridge, three-source panel, Stim Optimizer reads tiles, frozen model imported by no live module, no log on power except finding 3, composed constant labelled composed, no pooling across electrodes.

## Audit B findings (2026-09-20)
A1. RISK*: the Closed-Loop `inputs` store entry (adapter.py ~790-844) holds calibrated LSB columns from the tiles but its key is the recording-set signature alone: no constant, no rule version (the tile key is in provenance only). After a constant change it serves stale LSB until a recording is added or removed (daily on RCS08). Fix: fold `_raw_lsb_constants_block()` or the tile key and a rule version into the key; test first.
A2. COST (design, decision 53): the full-spectrum matrix and per-recording spectrum files key on the pain-report TIME set (`_pro_set_signature`), so every new report recomputes rating-centred spectra; the timeline endpoint fires `warm_psd_cache` on every miss. PI's call.
A3. CORRECT: tiles are LSB before storage with both constants in the key; every Closed-Loop derived kind and the Stim Optimizer response key on the tile key; sweep kinds key on tiles + report snapshot by design; the matrix is raw power consumed raw; native power never converted.
A4. `therapy_pain_matched` and the Closed-Loop `inputs` design matrix carry ratings joined to settings (raw-derived, decision 37); A1 makes `inputs` the one file where a stale LSB and a rating sit together.
Q2 matching: `_pro_lsb_by_channel` -> `per_pro_lsb` (per report x contact, three tiers) is read ONLY by the timeline's hollow circles/diamonds (`BiomarkerDataTimeline.js:305-320, 708-757`) -- the PI's belief confirmed for that step. But the endpoint is pain-dependent in two more places: the rating-centred `psd_scan_index` feeds the Binarization histogram card and the timeline's binarization colour mode; `warm_psd_cache(pro_times=...)` pre-builds the older exploratory matrix. No measurement separates the matching step from the ~5.0 s build (decision 92's split: loads ~2.9 s, build ~5.0 s).
A5. COST: the timeline result memo is per worker, in memory, 8 entries, keyed on the report digest: four workers each pay the cold build; every restart and every new report is a full rebuild.
A6*. RISK: `_native_lsb_tolerance_param` (bravo_service.py:3750-3753) substitutes 60 min when the tolerance is <= 0, so "matching disabled" still draws circles matched at 60 min.
A7-A10 COSMETIC: stale-constant comments; `index.js:171-176` describes the 120 s window decision 120 removed; `native_tol_s=120.0` default in five signatures; `BiomarkerDataTimeline.js:15` names the wrong endpoint.

## Timeline design (audit B's proposal, not yet approved)
1. Measure first: time `_build_availability` as is / without `_pro_lsb_by_channel` / without it and the rating-centred index, alternating rounds, non-matched fields 0 differing.
2. New raw kind `acquisition_timeline` in the one store, key = (kind, RULE_VERSION, recording-set identity, constants block); no metric, tolerance or report digest. Payload: records, lsb_overview (native + the two modelled routes tagged with their constant), stim, events, montage_events, samples, freq_bands, span, psd_scan_index built with pro_times=None.
3. Per-recording calibrated LSB: median of the ok tiles inside each recording at the contact's sensing centre, route from the tile family; empty where tiles absent.
4. Endpoint drops `_load_pros`, metric, tolerance; memo fronts the store read. `warm_psd_cache` dispatch: PI's call.
5. Frontend: delete `proLsbFor` and the per-rating trace block; binarization mode kept; left-label geometry untouched; rebuild; chunk string proof.
6. Tests first: no `pro_lsb`; key unchanged on a new report; key changes on a constant change; jest fixture test for the retired hover strings.
7. Proof: field/difference counts on every retained field (0), alternating timings cold and served, zero writes on a filed report.
Loses: the hollow circle/diamond per pain report per lane; still available in the heat-map grids' drill-down, the Closed-Loop "Choose a band" card, and the binarization colour mode.
Estimate (not measured): 3-5 s cold, sub-second served.

## Titration session, open item 30 (the PI, 2026-09-20: "I think we've already run that")
- The platform's own test (`post_ramp.margin_becomes_available`): a session counts when one run of rising current holds at least 8 distinct settled currents on the voltage-trace route (the curvature test's minimum, decision 55).
- On RCS08 today (stored per-run points table, written 2026-09-20 09:07 UTC, 16 runs): the RIGHT run of 2026-09-16 13:00 (other side held at 3 mA, sensing 0-3 Right) holds 9 -> `available: True`, "1 of 16 runs hold at least 8". The LEFT's best run is 2026-08-18 12:51 on 1-3 Left with 6; 2026-09-16 12:24 on 1-3 Left holds 4.
- So the record already answers: right side done, left side not. The 20 s margin switch (`USE_POST_RAMP_MARGIN`) is still OFF (decision 179, his call). The digest's "code side waits on the data" is stale for the right side.
- No code rule ties a sensing pair to the stimulating contact (grep: none); the readiness screen judges every pair. His rule: stim on contact 2 forbids 0-2; 1-3 required (0-3 also brackets contact 2).

## The 2026-09-16 session, re-checked against the device's own current record (the PI's items 1-4)
- Streaming was restarted twice during the left ladder: three recordings, 12:16:11-12:22:25, 12:22:37-12:40:51 (a 12 s gap, current held at L 2.0 across it), 12:53:24-13:37:31.
- The left ladder as delivered (right held at 2.5 mA, each step ~110-120 s): 0.5 (from 12:16, the recording began at it), 1.0, 1.5, 2.0 (18 s, cut by the restart), 2.5, 3.0, 3.5, 4.0, 4.5 up -- the 9 distinct currents he describes -- then 3.5, 2.5, 1.5 down, and after the second gap 0.5, 0.0.
- The right ladder (left held at 3.0): 0.0 (48 s), 0.5 ... 4.5 up (9), then 3.5 (32 s), 4.0 (38 s), 2.5, 1.5, 0.5, 0.0 down; then four joint corners (1/1, 4/1, 1/4, 4/4).
- What the platform kept, and why: (1) `find_single_side_runs_from_device` never joins two recordings, so the left ladder is two runs (12:18: 1.0-2.0; 12:24: 2.5-4.5 + down leg); (2) `mean_power_before_next_change(require_rise_into_setting=True)` uses a setting only when the current ROSE into it from the previous setting in the same recording, so the first setting of every recording (left 1.0 and 2.5; right 0.0) is refused and every down-leg step is refused; (3) 2.0 (18 s) and 3.5-down (32 s) are too short for 10 pieces after the ramp. Net: left 1 + 4 settled settings in two runs, right 9 (10 rows, 4.0 twice). The falling steps are not split into a second run; they are discarded.
- Fix candidates: (a) join recordings whose gap is under the move-grouping window (20 s) and whose current is unchanged across the gap -- gives one left run of 8 settled currents (1.0-4.5), passing the 8-setting test; (b) whether falling steps count is the PI's (the ladder was designed up-then-down for hysteresis; E1 is defined on rising current).

## Item 3, step 1: where the timeline's fresh build spends its seconds (RCS08, 2026-09-20, `_tl_measure.py`, `_tl_profile.py`)
- Recording load 2.18 s cold, memoised after. Build as is 5.04 / 5.05 / 5.10 s; without the per-report matching 4.43 / 4.49 / 4.59 s; without it and with the sample index built at session starts 4.53 / 4.51 / 4.55 s. Three alternating rounds.
- Inside the build: native LSB series 1.3 s, its overview 0.9 s, loading the PSD-bearing recordings 0.9 s, the patient-event PSD index 0.7 s, per-report matching 0.6 s, patient events 0.4 s, event PSD blocks 0.4 s; the sample index 0.00 s.
- Fields: 618,594 as is; `pro_lsb` is 162,960 of them (26 percent); dropping matching changes 0 other fields. Building the sample index without pain times changes 10,711 fields inside `psd_scan_index` (the Binarization card's matched mode reads it).
- So: the matching step is 11 percent of the build. The cost the PI sees is the rebuild on every new pain report (the report digest is in the memo key) on every worker (per-process memo, not the store). The fix is the key and the store, with matching removed as asked.
