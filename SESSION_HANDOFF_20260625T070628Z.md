# Session Handoff — 20260625T070628Z

## Branch
- **Working branch:** `PS_closedloop_deployment` (pushed to origin)
- **Base:** `v3.1.0` at `f915257`
- **Default branch:** `v3.1.0` — the commit `f915257` is also on v3.1.0 HEAD (pushed directly, then branched)
- **Remote:** `https://github.com/shirvalkarlab/BRAVO_pain.git`

## What was done this session

### Phase 1 — Modality-sensitive conversion correctness
1. **Removed 60 Hz mains notch default.** `_band_power_notched` in analytics.py now defaults `notch=False` — the Percept is implanted/battery-powered with no mains coupling. Interpolation retained behind explicit `notch=True`.
2. **Encoded threshold-mode FFT metadata.** `THRESHOLD_MODES` dict (Dual 256-pt/1200ms, Single 64-pt/100ms, SingleInverse 256-pt/3000ms), `CONVERSION_FFT_SIZE=256`, `COMPATIBLE_THRESHOLD_MODES=("Dual","SingleInverse")` in analytics.py.
3. **Guard flags Single Threshold** (64-pt FFT) as not convertible.
4. **PsdLsbPanel.js** — modality breakdown (chronic vs streaming k, controller-relevant flag), threshold-mode Plotly `updatemenus` dropdown (client-side, no refetch), fixed stale notch caption.

### Phase 2 — Mode-aware deployment
5. **`_threshold_mode_block` helper** in bravo_service.py — checks FFT/adaptive-band compatibility per Percept mode, returns all-modes verdicts for client-side switching.
6. **Wired into `band_lsb_and_power`** (threshold path) and **`deployment_summary`** (sign-off card).
7. **Plotly mode selector** on PsdLsbPanel — `updatemenus` dropdown swapping bar emphasis + verdict annotation per mode.

### Phase 3 — Rigorous LSB estimation
8. **TD→LSB validated** on 50 stim-off paired blocks (BrainSenseLfp + BrainSenseTimeDomain on the SAME signal): k=269 LSB/µV² (1 LSB ≈ 0.0037 µV²), R²=0.94, 5-fold CV error 1.19×, 1σ scatter 1.26×. Matches design-ledger 0.0034 µV²/LSB within 9%.
9. **Back-translation settled:** phase-randomized TD reconstruction matches direct PSD integral within 0.8% — PSD→TD→LSB adds nothing; direct PSD→LSB is rigorous.
10. **`lsb_from_uv2` / `uv2_from_lsb`** converters added to analytics.py with `LSB_PER_UV2_VALIDATED=269`, `LSB_UV2_SIGMA_FOLD=1.26`.
11. **Tiered fallback** in deployment_summary: frozen per-participant model → validated population constant (clearly flagged `tier="validated_constant"`).
12. **k uncertainty propagated** into estimated thresholds: `estimated_upper_lsb_lo/hi` and `sigma_fold` emitted; PsdLsbPanel shows "1 µV² ≈ 269 LSB (±1σ: 213–339)".
13. **Plotly threshold gauge** on LsbPowerPanel: threshold diamond marker on the Timeline LSB distribution (p10–median–p90), with ±1σ error bars when estimated (k-derived), clean line when percentile-anchored (exact).
14. **Methods & validation HTML doc** served from `/static/docs/METHODS_lsb_estimation.html` with all figures embedded; linked from PsdLsbPanel ("Methods & validation ↗").
15. **Frequency coverage caveat:** k validated 8–28 Hz only; adaptive band (8–30 Hz) is the firmware-actionable range; higher frequencies need dedicated streaming calibration.

### Post-plan additions (user requests)
- Updated `empirical_lsb_ratio` docstring — stale "~3× / diverges" claim corrected to reference the validated constant.
- Test `test_lsb_uv2_converters_roundtrip_and_validated_constant` added (suite now 162/162).

## Key constants
| constant | value | location |
|---|---|---|
| `ADC_NV_PER_LSB` | 146.0 nV/LSB (time-domain, exact) | analytics.py |
| `LSB_PER_UV2_VALIDATED` | 269.0 LSB/µV² (power-domain, validated) | analytics.py |
| `UV2_PER_LSB_VALIDATED` | 0.00372 µV²/LSB | analytics.py |
| `LSB_UV2_LOGLOG_SLOPE` | 0.835 | analytics.py |
| `LSB_UV2_SIGMA_FOLD` | 1.26 | analytics.py |
| `CONVERSION_FFT_SIZE` | 256 | analytics.py |
| `COMPATIBLE_THRESHOLD_MODES` | ("Dual", "SingleInverse") | analytics.py |

## Test status
- **Backend:** PASS=162 FAIL=0 (runner: `BRAVO/_agent_bridge/run_tests.py`)
- **Frontend:** ESLint clean on all modified ClosedLoopSim panels
- **Build:** exit 0 (CRA production build)

## Files changed (14 files, +1043 / −62)
- `BRAVO/modules/Biomarkers/routines/analytics.py` — notch default, THRESHOLD_MODES, LSB constants, converters
- `BRAVO/modules/Biomarkers/bravo_service.py` — modality guard, _threshold_mode_block, tiered fallback, error propagation
- `BRAVO/modules/Biomarkers/tests/test_analytics.py` — notch test rewrite, converter test
- `Client/src/views/Reports/ClosedLoopSim/PsdLsbPanel.js` — modality/mode panels, σ display, methods link
- `Client/src/views/Reports/ClosedLoopSim/LsbPowerPanel.js` — Plotly threshold gauge with error bars
- `Client/public/static/docs/METHODS_lsb_estimation.html` — self-contained methods doc with embedded figures
- `Client/build/` — rebuilt bundle
- `METHODS_lsb_estimation.md` — methods source

## Open items for next session
1. **Generalize beyond RCS08** — frozen model and k constant are participant-specific; multi-participant support needed.
2. **Remaining audit findings:** 28 medium + 24 low (C4 is 4th priority).
3. **PHI hygiene:** JI/JILLIAN IMRIE filenames in the device JSON folder.
4. **Impedance term** c=1.02 is significant but its original motivation (8.8 Hz drift) was retracted; decide whether to adopt it as a general gain correction.
5. **High-gamma calibration:** the 55.5 Hz forward-validated winner needs streaming sessions at that center frequency to calibrate k there (currently extrapolated from the 8–28 Hz validated range).
6. **8.8 Hz sensing-config segment:** the frozen model restricts 8.8 Hz to ≥2026-03-01 but the real config change is 2025-12-05; update the restriction date.

## Artifacts saved this session
- `rcs08_td_lsb_calibration.png` — TD→LSB validation figure
- `rcs08_psd_lsb_backtranslation.png` — back-translation test figure
- `rcs08_lsb_frequency_coverage.png` — frequency coverage figure
- `METHODS_lsb_estimation.md` — methods & validation note (3 versions)
- `td_lsb_calib.csv` — paired-block calibration data
- `td_lsb_pairing_inventory.csv` — streaming session inventory
- `psd_backtranslation.csv` — back-translation test data

## Branch cleanup (this session)
- **Deleted `PS_biomarker_actionability`** (local) — 0 commits ahead; content merged via PR #7.
- **Deleted `PS_biomarker_clfixes`** (remote already gone, pruned tracking ref; local deleted) — unique commit `1086cab` was squash-merged as `c50be37` on v3.1.0.
- **Deleted `PS_biomarker_module`** (remote + local) — only unique content was a session handoff .md, no code.
- **Kept `PS_closedloop_deployment`** — new working branch, identical to v3.1.0 HEAD at `f915257`.

### Remaining remote branches
- `origin/PS_closedloop_deployment` — **active working branch**
- `origin/development` — legacy
- `origin/v2.0-alpha`, `origin/v2.1.0`, `origin/v2.1.1`, `origin/v2.2.0`, `origin/v2.2.1` — release tags/branches
- `origin/v3.1.0` — **default branch** (HEAD = `f915257`)
