# Session handoff — deployment LSB fallback: universal TIER-1 off raw TD (2026-06-28)

**Branch:** `PS_closedloop_deployment` @ **`e8a0d3f`** (in sync with origin). **Suite 239/239 PASS.**

## What this session did
Two threads continued from the prior session:
1. Finished cleaning `MEGA_HANDOFF.md` and removed the welch256 / `k=269` family (commits `184ea74`,
   `fa2c416`, `e15e57e`, `fe31c87`, `45c39a9` — see those handoffs).
2. **A cross-module LSB-consistency code review found a CRITICAL units bug** that the k=269 removal had
   left in place, and this session fixed it (commit `09798f7`) + rebuilt the frontend (`e8a0d3f`).

## The units bug (CRITICAL, now fixed)
The deployment ROC **cut-point** is a within-(channel,source) **z-scored log-power feature** —
dimensionless, frequently negative (built by `streaming_psd.build_pooled_detail_from_matrix`,
`prelog=True`; `_band_feature_from_detail` returns it unchanged when `prelog`). The fallback ladder fed
that cut-point straight into `psd_lsb_model.estimate_lsb`, which expects a **linear µV²** band power
(`lsb = 10**(a + b·log10(clip(P,1e-12)))`). Consequences on the patient-facing stim threshold:
- z ≤ 0 (≈half of operating points) → clipped to 1e-12 → LSB ≈ 5e-9 (≈0).
- z > 0 → silently misread as µV² (z=1 → 84.6 LSB, identical to feeding µV²=1.0).

## The fix — one units-consistent modeled tier (decision 21)
- **New `availability.modeled_lsb_at_center(channel, center_hz, *, td_recordings=, psd_recordings=, half_hz=2.5)`**
  models device-LSB samples off the **raw µV TD** the ROC was built from, **at the ROC's own band
  center**: TD tier `analytics.td_to_lsb(col, fs, center_hz)` (transform ×352.62); PSD-only tier
  `analytics.device_psd_to_lsb(freqs, row, center_hz)` (bridge ≈73.63), deployable-band gated. Returns a
  1-D array; the caller anchors a threshold by **RANK (percentile)** like native — **no µV²↔LSB
  conversion of the cut-point**.
- **Honors the ROC center exactly — NO `snap_freq` clamp.** `snap_freq` clamps to the 26.4 Hz top of the
  device sensing-bin table; a high-gamma ROC winner (e.g. 55 Hz) must convert at 55 Hz. (Catching this
  fixed a high-gamma threshold that was ~4× too high: 55.5 Hz p50 26.7 LSB vs the clamped 102.5.)
- **Deployment-only.** The helper only CALLS shared primitives; `lsb_series` and the **Biomarker
  Exploration timeline are byte-unchanged in behavior**. Both endpoints (`band_lsb_and_power`,
  `deployment_summary`) source `modeled_thr` from the helper at the ROC center.
- **TIER-2 (frozen-model-on-cut-point) deleted.** `_modeled_lsb_threshold_estimate` is now a single
  modeled tier, signature `(thr_lsb, modeled_thr, n_modeled, center_hz, percentile)` (dead
  `cutpoint`/`participant`/`channel` params dropped). Fail-closed (`modeled_thr None → thr_estimate
  None`) only when there is genuinely no TD/PSD for the channel.
- `psd_lsb_model.estimate_lsb` **retained** as a tested µV²→LSB utility (no production caller) with a
  loud input-contract warning against z-scored/log/cut-point inputs.

## Hardening (review MEDIUM/LOW items, all addressed)
- Channel-name guard requires a **named column matching the target** (mirrors `lsb_series`'s
  iterate-over-names); unnamed/extra columns (malformed packets, Data cols > ChannelNames) and
  power-domain records (`fs ≤ 0`, e.g. ChronicBrainSense) are skipped — no cross-channel/units leak.
- `chronic_list` (power-domain) no longer passed to the TD tier.
- Fixed an array-truth bug: `freqs = r.get("Frequencies") or r.get("FrequenciesInHertz")` → explicit
  None check.
- Restored `test_freq_extrapolated_guard_agrees_with_frozen_model` (was called in `__main__` but
  undefined — a NameError-as-script the CI missed because pytest skips `__main__`); wired TIER-1
  `fextrap` to `analytics._freq_extrapolated` (DRY); removed a duplicate assertion; corrected stale
  ladder comments/docstrings (duplicate "Fallback" block, TIER-2 docstring line).

## Tests
+9 net. 8 new helper-branch tests in `test_availability.py` (named-match==td_to_lsb, foreign-channel
exclusion, power-domain skip, malformed extra-columns no-leak, orientation transpose, short-column skip,
empty→fail-closed, PSD band-gate freq-first, high-gamma no-snap) + the restored guard test. Updated
`test_modeled_lsb_threshold_fallback_ladder` to the new 5-arg signature and fail-closed semantics.
**Suite 239/239 PASS** via `python3 _agent_bridge/run_tests.py`.

## Verification
E2E on real RCS08 through the actual helper (not direct `td_to_lsb`): `ONE_THREE_RIGHT` — which had 0
frozen-model bands (was fail-closed/units-broken) — now gets a valid modeled threshold at every band
(n=214). 55.5 Hz high-gamma → p50 26.7 LSB (physically sane 1/f falloff; the snap bug would have set
~102). Both edited modules + tests compile in-container.

## Files changed (commit `09798f7`)
- `BRAVO/modules/Biomarkers/routines/availability.py` — new `modeled_lsb_at_center` helper.
- `BRAVO/modules/Biomarkers/routines/psd_lsb_model.py` — `estimate_lsb` input-contract docstring.
- `BRAVO/modules/Biomarkers/bravo_service.py` — both endpoints rewired; TIER-2 deleted; ladder helper
  simplified; stale comments fixed.
- `BRAVO/modules/Biomarkers/tests/test_availability.py` + `test_analytics.py` — +9 tests, signature update.
- Frontend rebuilt (`e8a0d3f`): bundle `main.52577b20.js` (drops the retired `validated_constant` /
  "from validated k=269 constant" tier label).

## Open / next
- The deployment PSD-only (bridge) tier is supported by the helper but the endpoints currently pass
  `psd_recordings=None` (montage TD covers RCS08). Wire PSD events in if a participant has PSD-only bands.
- Code-review record + diffs are saved as artifacts (`CODE_REVIEW_welch256_k269_removal.md`,
  `tier1_universal_modeled_review.patch`).
