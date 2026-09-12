# Translating offline band power (µV²) to device LFP Power (LSB) — methods & validation

**Participant:** RCS08 (Percept RC, closed-loop DBS for chronic pain).
**Question:** how do we convert a physical band power in µV² (from an offline PSD) into the device's
own "LFP Power" LSB units — the units the Percept actually programs a threshold in — and do we need to
reconstruct a time series (PSD→TD→LSB) to do it, or is a direct PSD→LSB integral enough?

## 1. Ground truth: simultaneous TD + LSB exists

On-demand **BrainSense Streaming** records the same signal two ways at once:
- `BrainSenseLfp` → the device's on-board **LFP Power in LSB** (`LfpData[].Right/.Left`), streamed at
  ~2 Hz (3000 ms averaging — the Sensing-Only / streaming class), with per-sample stim `mA` and the
  sensing center frequency in `TherapySnapshot.{Left,Right}.FrequencyInHertz`.
- `BrainSenseTimeDomain` → the raw **250 Hz time domain in µV** (`TimeDomainData`, `Gain` enum 222 L /
  225 R already applied).

They share `FirstPacketDateTime`, so each LSB block has a byte-identical TD twin — **no time-matching
slop**. Inventory across RCS08's JSONs: **28 streaming sessions, 113 paired blocks**, of which **52 are
stim-off**; **50** of those 52 survive the fit filter (positive TD band power and positive device LSB)
and enter the calibration below. See `td_lsb_pairing_inventory.csv`.

## 2. TD → LSB estimator

For each paired block (stim-off, for a clean fit): Welch **256-pt** PSD of the TD µV (matching the
device's 256-pt FFT), integrate over the hemisphere's sensed band (±2.5 Hz), and regress the result on
the median device LFP power on the same block.

| quantity | value |
|---|---|
| **k (LSB per µV²)** | **269** (1 LSB ≈ **0.0037 µV²**) |
| log-log slope b | 0.835 (95% CI 0.78–0.89) |
| R² | 0.94 (n = 50 stim-off blocks) |
| 5-fold CV fold-error | **1.19×** |
| 1σ multiplicative scatter | 1.26× |
| stim-on vs stim-off gain | 1.05× (small contamination) |
| k across 8–28 Hz | ~260–340 (≈ band-flat firmware gain) |

This **independently reproduces the design ledger's empirical 0.0034 µV²/LSB to within 9%**, and is
0.37× the Medtronic 0.01-µV²/LSB rule of thumb. The slope 0.835 matches the frozen PSD→LSB model's 0.85
for this channel. Figure: `rcs08_td_lsb_calibration.png`. Data: `td_lsb_calib.csv`.

## 3. PSD → LSB, and the back-translation question

Device LFP Power **is** the band integral of the PSD, and a band integral is **phase-independent**.
So reconstructing a time series from the PSD (PSD→TD→LSB) — which requires inventing the phase — cannot
add or remove band-power information. Tested directly on all 113 blocks: band power from a
**phase-randomized TD reconstruction** matched the direct PSD integral to within **0.8%** (median ratio
1.008, r = 0.999). **Conclusion: the direct PSD→LSB integrate-then-scale is sufficient and rigorous;
back-translation is unnecessary.** Figure: `rcs08_psd_lsb_backtranslation.png`. Data:
`psd_backtranslation.csv`.

Because the PSD here is the TD's own Welch spectrum, the PSD→LSB estimator is numerically the same fit
as TD→LSB: k = 269, R² = 0.94, median fold-error 1.07×.

## 3b. Frequency coverage: validated 8–28 Hz only

The paired-block ground truth spans **nine discrete center frequencies from 7.8 to 28.3 Hz** — the
range the device happened to sense during RCS08's streaming sessions. Within 9–28 Hz (excluding the
anomalous 7.8 Hz, n=4), k ranges 258–317 (1.23× span) — approximately band-flat but not perfectly
constant (26.4 Hz has k=317, ~18% above the pooled 269). The log-frequency trend is positive but not
significant (p=0.17).

**Below ~8 Hz or above ~28 Hz there is no calibration data.** The Welch PSD approach is mathematically
valid at any frequency from 0 to 125 Hz (Nyquist at 250 Hz sampling), but without paired device LSB
ground truth at those frequencies, k would be an untested extrapolation. Bands outside 8–30 Hz (e.g.
high-gamma 55–80 Hz) would need their own streaming-session calibration at those center frequencies.

This limitation is not clinically restrictive for the adaptive modes: Dual and Single Threshold are
firmware-restricted to adaptive sensing within **8–30 Hz**, so the validated range covers the
controller's actionable band almost exactly. Single-Inverse (sensing-only) sees 1–96 Hz, but there
the threshold is reviewed against, not actuated — and the converter is appropriately flagged as an
estimate. Figure: `rcs08_lsb_frequency_coverage.png`.

## 4. Reconciliation — which route, which data source

- **Deployed threshold:** unchanged — **percentile-anchored on the device's own Timeline LSB**. The
  absolute µV²↔LSB constant is normalization-dependent, so it never *sets* the deployed number.
- **When the device never sensed the band** (no Timeline anchor): translate the physical µV² cut-point
  to LSB, tiered:
  1. per-participant **frozen PSD→LSB model** (`psd_lsb_model.estimate_lsb`) — preferred;
  2. **validated population constant** `analytics.lsb_from_uv2` (k = 269) — last resort, clearly
     flagged `tier="validated_constant"`, with the 1σ 1.26× scatter, "confirm live before deploying".
- **Two LSBs are distinct:** 146 nV/LSB (`ADC_NV_PER_LSB`) is the *exact* time-domain ADC count scale;
  269 LSB/µV² (`LSB_PER_UV2_VALIDATED`) is the *firmware power-domain* band-power LSB — a confidence-
  rated estimate, not exact.
- **Mode compatibility:** only the **256-pt** modes (Dual, Single-Inverse) are valid targets. Single
  Threshold's **64-pt** FFT integrates a different set of bins — its LFP Power is not comparable, and
  the guard / deployment refuse to translate to it.

## 5. Code

- `analytics.LSB_PER_UV2_VALIDATED / UV2_PER_LSB_VALIDATED / LSB_UV2_LOGLOG_SLOPE / LSB_UV2_SIGMA_FOLD`
- `analytics.lsb_from_uv2(uv2, k=...)`, `analytics.uv2_from_lsb(lsb, k=...)`
- `bravo_service.deployment_summary` — validated-constant fallback tier
- test: `test_lsb_uv2_converters_roundtrip_and_validated_constant`
