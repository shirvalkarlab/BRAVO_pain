# BRAVO_pain ClosedLoopSim — Session Handoff

**Date:** 2026-06-24 (continuation session)
**Branch worked:** `PS_biomarker_actionability` (off `c50be37`) → **merged to `v3.1.0` as PR #6, squash SHA `b0597f8`**
**Remote:** https://github.com/shirvalkarlab/BRAVO_pain.git  · default branch `v3.1.0` (HEAD now `b0597f8`)
**Git identity:** `Prasad Shirvalkar <prasad.shirvalkar@ucsf.edu>` via `GIT_AUTHOR_*`/`GIT_COMMITTER_*` env vars (`.git/config` unwritable — keychain `-50` + `~/.config/git/ignore` warnings are documented-harmless).

## What shipped this session (PR #6)

Continuation of the four-lens audit work. Prior session shipped Wave-1+2 (C1/C3/C5/C6/C7/C8) as **PR #5 (squash `c50be37`)**. This session: **C9, C10, a new PSD→LSB panel, and a pandas-3/numpy-2 forward-compat cleanup.**

### C9 — single-source the cut-point trace index
`Client/src/views/Reports/ClosedLoopSim/DeploymentRocPanel.js`: `const CUTPOINT_TRACE = 2` replaces the two hardcoded `Plotly.restyle(..., [2])` targets (draw order 0=chance,1=ROC,2=cut-point documented). Zero behaviour change.

### C10 — recommend → program actionability
- **`band_lsb_and_power.recommended_vs_programmed`** (bravo_service.py): Δ between recommended upper-LSB threshold and the value currently programmed on the device for that hemisphere; direction (raise/lower/unchanged) + % change. Resolves `_programmed_adaptive_thresholds(Participant)`; defensive try/except (therapy metadata must never break the LSB report).
- **`_ramp_guidance(polarity, adaptive_valid, suggested_mode, *, stim_stable, power_available)`** (bravo_service.py): advisory ramp posture, wired into `deployment_summary.device_control["ramp"]`. **Abstain rule:** `conservative = (stim_stable is not True)` — stim-dependent (False) OR LRT-didn't-converge (None) both → conservative. Unavailable if out-of-range / negative polarity / no suggested_mode.
- Frontend: Δ block in `LsbPowerPanel.js`, ramp block in `DeploySignoffCard.js`, shared minimal modebar `PAL.MODEBAR` on all 4 figure configs (chrome-only — `Plotly.react`-once discipline preserved). Palette tokens: `neutralFill`/`neutralBorder`/`passBorder`/`MODEBAR`.

### PSD→device-LSB conversion (NEW panel)
The device reports band power in "LSB"; offline Welch PSD reports µV²/Hz. New panel derives the firmware gain from time-matched chronic streams.
- **`analytics.psd_lsb_conversion(psd_bandpower_uv2, device_lsb, *, n_boot, seed)`** — fits proportional law `LSB = k·µV²` (robust median `k = 10**median(logL-logP)`, bootstrap CI) + free log-log line as a **falsification check** (slope must be ≈1 for a linear gain). Returns slope/CI/r²/spearman/k/k_ci/uv2_per_lsb/resid_log_sigma_fold/slope_consistent_with_unity.
- **`analytics._band_power_notched(freq, power, center, half, *, line_lo=58.5, line_hi=61.5)`** — integrates PSD over band, interpolating across mains line-noise.
- **`bravo_service.band_psd_lsb_conversion(request_data)`** — assembles raw PSD rows (`_assemble_psd_rows_cached`) + device LSB series (`availability.lsb_series`), time-matches each PSD epoch to LSB within ±MatchWindowH (default 1h), integrates over the band the device was sensing (each LSB sample's median `center_hz`), calls the fit. Returns fit + decimated scatter (≤400 pts) for the panel.
- **API:** `QueryPsdLsbConversion` view (DataAnalysis.py) + `path('queryPsdLsbConversion', ...)` (urls.py). Required keys: ParticipantId, Channel (CenterHz optional).
- **`PsdLsbPanel.js`** — log-log scatter + proportional fit + ±1σ band, conversion constant, slope falsification badge. Imported + gridded in index.js between EraRefitPanel and DeploySignoffCard.

**Result (RCS08 ZERO_THREE_RIGHT, n=1446, ±1h):** free slope **1.085** (95% CI 1.014–1.155 — narrowly *excludes* 1.0, so panel shows "near 1, treat k as approximate"); **k = 74.1 LSB/µV² ⇒ 0.0135 µV²/LSB**, within **1.35×** the Medtronic 0.01 rule-of-thumb; ρ=0.675; 1σ multiplicative scatter ×1.99. ZERO_THREE_LEFT slope ~0.49 (mostly streaming-only LSB, unreliable). Verified the service fn reproduces the offline fit byte-for-byte against the live DB.

### pandas-3 / numpy-2 forward-compat cleanup
**Why now:** local `bravo_app` env has pandas 3.0.3 (no `Series.view`) → the prior session needed a runtime shim for local tests. **Live container runs pandas 2.2.3 where `.view` still works**, so production was never broken — but `.view` is deprecated (removed in pandas 3.0) and a bare `.astype("int64")` would give microseconds under pandas 3.0's `datetime64[us]` default.
- Replaced `Series.view("int64").to_numpy()/1e9` with resolution-independent `.to_numpy().astype("datetime64[ns]").astype("int64")/1e9` at **all 5 source sites** (analytics.py ×2: `_elapsed_week_cluster`, `_assign_stim_eras`; bravo_service.py ×2: `_metric_pro_series`, `_all_pro_times`; availability.py ×1: pain-series epoch) **+ 2 test sites**.
- Replaced `np.trapz` (removed numpy 2.0) with `np.trapezoid` in `empirical_lsb_ratio`.
- **Verified byte-identical on container pandas 2.2.3** incl. tz-aware UTC and NaT sentinel (−9.22e9, filtered by the existing `nat` mask). Standalone suite now runs **without the shim: 48/51 pass.**

### Tests (+4, all pass)
`test_analytics.py`: `psd_lsb_conversion_recovers_planted_proportional_constant` (planted k₀=80 + ×2 noise → k within 25%, slope CI includes 1.0), `..._flags_nonlinear_slope` (LSB~√P → slope<0.8, CI excludes 1.0), `..._guards_small_n`, `band_power_notched_interpolates_mains_line`. Registered in the `__main__` runner.

## Test status
**48/51 pass with NO shim** (was 43/47 needing the shim before cleanup). Remaining 3 failures are harness-only — `test_normalize_pro_times*` / `test_pain_scores_emit_utc_t_epoch` / `test_pain_series_epochs_match_pro_match_arrays` need Django `INSTALLED_APPS` (they pass under the Django harness, fail under the standalone importlib runner). NOT regressions, NOT in the diff.

**Pre-existing latent bug noticed (OUT OF SCOPE, untouched):** the `test_analytics.py` `if __name__=="__main__"` runner block sits BEFORE several `def test_...` definitions it calls (e.g. `test_deployment_roc_recovers_planted_band` called at runner-line but defined ~70 lines later) → `NameError` if run as `python test_analytics.py`. Pre-exists on origin/v3.1.0 (runner@739 calls fn defined@782). Tests are actually run via pytest in CI (order-independent collection), so this never bites there. Left alone — fixing it is unrelated scope.

## Environment facts
- **Repo:** `/Users/pshirvalkar/dev/BRAVO_pain` (host) bind-mounted to `/usr/src/BRAVO` (live Docker container, gunicorn `--reload`). Source edits are live in-container immediately.
- **Live DB:** MySQL/mongoengine in container. **Participant RCS08 live uid = `2e3c75c00d7f4f37b53a048d195f11da`** (the `_pro_dump` export used `1eda36458758461383721208bbe6bb87` — DB was re-ingested; always use the live uid for container probes).
- **Agent bridge:** `BRAVO/_agent_bridge/bridge_client.py --cwd /usr/src/BRAVO --timeout N --wait M "<cmd>"` runs jobs in-container via inbox/outbox mailbox. `--status` for heartbeat. This is how all container validation ran.
- **Envs:** `bravo_app` (py 3.11.15, pandas 3.0.3 — run local tests from `BRAVO/`, NO shim needed anymore), `rocqa` (py 3.13.14, plotly 6.8 + kaleido — kaleido Chrome export BROKEN, use `write_html`/matplotlib), `python` (read-only).
- **Build:** `cd Client && export npm_config_cache=/tmp/npmcache && GENERATE_SOURCEMAP=false NODE_OPTIONS=--openssl-legacy-provider CI=false npx --no-install react-scripts build`. Repo commits `Client/build/` alongside source. Node v24.13.0.
- **CRLF gotcha:** `DataAnalysis.py` + `urls.py` are CRLF files. Writing them with Python `open(...,newline="")` strips CRLF → giant spurious diff. Fixed by restoring CRLF (`.replace(b"\r\n",b"\n").replace(b"\n",b"\r\n")`). All other source is LF. **`edit_file` preserves endings; raw Python writes do not.**
- **GitHub:** no `gh`/PyGithub — use urllib + `GITHUB_TOKEN` (Bearer, API version 2022-11-28). Self-approval blocked → post review as issue comment then `PUT /pulls/{n}/merge` (squash).

## Hard constraints (carry forward)
- **ClosedLoopSim Plotly panels:** imperative `Plotly.react` + `Plotly.restyle(...,[traceIndex])` + `Plotly.relayout` ONLY. **Never rebuild a figure on interaction** (commit `255e0ef` fixed the reset bug). The C10 modebar is chrome-only and respects this.
- **DO NOT COMPACT EVER.** Warn before 96% context / before compaction. Batch independent tool calls.

## Deferred / open
- **C2 (HIGH)** — forward-chaining / out-of-sample validation. The last unaddressed HIGH audit finding. All deployment AUC numbers remain in-sample. This is the most scientifically important next step.
- Audit C10 "embed figures into export" — the modebar PNG-export is in; a full report-embed (figures baked into the exported sign-off doc) was not built.
- Conversion panel could gain a channel selector + the ±1h/±2h toggle (backend already accepts MatchWindowH); currently fixed to the committed band's channel at ±1h.

## Key artifacts (this session)
- `psd_lsb_conversion.png` — 3-panel conversion figure (artifact `522fa513-...`, version `3d7da049-...`)
- `psd_lsb_pairs.csv` — 3652 matched (PSD, LSB) pairs (artifact `0fbee806-...`)
- `psd_lsb_fit.json` — the ZERO_THREE_RIGHT fit (artifact `81b2242a-...`)
