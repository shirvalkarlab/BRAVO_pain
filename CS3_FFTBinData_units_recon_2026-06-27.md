# CS-3 recon: event FFTBinData units (RCS08, 2026-06-27)

Sampled 3119 patient-event PSD hemisphere-blocks (all PatientControllerEvent, incl. Streaming).

## Key finding: FFTBinData is LINEAR-quantized, NOT log/dB
- Global range: min -0.1133, max 44.96, mean 0.499.
- 33.7% of all bins negative; 90.1% of blocks carry >=1 negative bin; median per-block neg-frac 0.53.
- **Values are quantized**: smallest positive uniques = 0.1118, 0.2237, 0.3355, 0.4473 = 1x,2x,3x,4x of a
  quantum ~= 0.112 uV. (A second, ~1.3% larger quantum 0.1133/0.2267/0.34 appears too -> likely the two
  hemispheres carry slightly different scale factors, or two FFT amplitude resolutions.)
- **Negative floor is exactly -1 quantum** (-0.1133 / -0.1118). Nothing more negative.
- 2720/3119 blocks peak at bin 0/1 (1/f- or DC-dominated raw amplitude spectrum).

## Interpretation
The integer-multiple quantization in LINEAR space + a hard floor at exactly -1 quantum is the signature of
a **linear amplitude with baseline subtraction**: FFTBinData ~= quantum * round((amp - baseline)/quantum).
Negatives are bins where measured amplitude fell just below the subtracted noise baseline -> quantization
noise around zero. This is NOT a dB/log transform (log-domain would not show a -1-quantum hard floor or
integer-multiple linear quantization).

## CONFIRMED (2026-06-27, paired regression): FFTBinData == LFPMagnitude unit
Paired survey-LFPMagnitude <-> event-FFTBinData bins on hemisphere-matched, time-coincident blocks
(2-50 Hz, positive bins both sides), log-log OLS:
- TOL=60s : 6 pairs, 264 bins  -> FFTbin = exp(0.073)*LFPmag^1.022, R2=0.795, r=0.892
- TOL=300s: 24 pairs,1056 bins  -> FFTbin = exp(0.069)*LFPmag^1.047, R2=0.833, r=0.913
- TOL=900s: 66 pairs,3114 bins  -> FFTbin = exp(-0.062)*LFPmag^0.956, R2=0.764, r=0.874
Slope ~= 1.0 (proportional, NOT a power law); intercept ~= 0 (proportionality constant ~= 1).
At TOL=300s: slope 1.047 (95% CI [1.019,1.075]), exp(intercept)=1.072, slope-1-constrained geom-mean
ratio FFTbin/LFPmag = 1.037, log-resid Jarque-Bera p=0.54 (normal). 

=> event FFTBinData is the SAME physical unit as survey LFPMagnitude: linear uV onboard-FFT magnitude,
related by FFTbin ~= 1.04 x LFPmag (essentially identity). The negatives are baseline-subtracted
sub-noise-floor bins (LFPMagnitude clamps them >=0; FFTBinData dithers +-1 quantum around 0).

## Reconciliation rule for the bridge
To put event FFTBinData into the montage device-PSD (LFPMagnitude, linear uV) frame: **clamp negative
bins to 0** (they are sub-floor noise), then treat as linear uV magnitude. Band power = sum of squared
in-band magnitudes (same definition as the montage device-PSD band integral). No log/anti-log, no scale
factor needed (ratio 1.04 is within the 1.26x calibration scatter). This feeds CS-3 step 2 (montage
TD<->PSD law) and step 3 (compose PSD->LSB): the montage LFPMagnitude IS the bridge's PSD side, and the
event FFTBinData enters it unchanged after the negative-clamp.

## CS-3 COMPLETE — montage TD↔PSD law + composed PSD→LSB bridge (committed f4d821a)

### Montage TD↔PSD law (RCS08 surveys, TD + device-PSD on the SAME recording)
Same band-power definition both sides (Σ squared in-band magnitudes), within-survey contact-channel
pairing, 5–45 Hz, n=10476 contact-band points across 219 surveys / 12 contacts:
- GLOBAL log-log: PSD_bp = exp(1.592)·TD_bp^1.022, R²=0.975, r=0.987, slope 95% CI [1.019,1.025].
- Slope-1-constrained: PSD_bp = K_TD_PSD · TD_bp, K_TD_PSD = 4.789 (geomean, 95% CI [4.772,4.806]),
  fold 1.215× (< 1.26× calibration scatter), offset 6.80 dB (matches the code's ~6 dB note).
- Per-contact K very stable: 4.73–4.87 across all 12 contacts (±2%).
- The earlier r=0.62/slope=0.57 first pass was a band-definition + contact-pairing artifact, now fixed.

### Composed PSD→LSB
LSB = LSB_PER_UV2_TRANSFORM·TD_bp and TD_bp = PSD_bp/K_TD_PSD ⇒
  LSB = (352.62 / 4.789) · PSD_bp = LSB_PER_DEVICE_PSD · PSD_bp,  LSB_PER_DEVICE_PSD ≈ 73.63
  (95% CI [73.37, 73.89]).
End-to-end on montage (LSB via bridge vs direct TD→LSB, n=10476): geomean fold 1.000 (unbiased),
scatter 1.21×, r=0.987 — reproduces the direct transform within calibration scatter.

### Applied to
PSD-only patient-triggered snapshot events ONLY (analytics.device_psd_to_lsb; availability.lsb_series
psd_modeled bridge tier, modeled=True, method=event_psd_bridge_x_k=73.63, restricted to [7.8,30] Hz).
Montage/survey products carry TD → direct transform (they are the bridge's CALIBRATION SOURCE).
Verified e2e on RCS08: 3119 bridge LSB points, all source=psd_modeled, centers in [7.8,22.5], median 522.
Suite 219/219.
