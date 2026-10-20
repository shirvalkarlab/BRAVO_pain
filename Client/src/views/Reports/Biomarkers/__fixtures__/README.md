# Synthetic frontend response fixtures

These responses were authored from component contracts, without copying historical
participant responses. They test rendering, formatting, cache behavior, and selection.
They are not measured observations, fit-validation datasets, or scientific evidence.

- `synthetic_band_sweep.json`: six categorical channel labels, three frequency
  centers, nine signal lengths; each cell deliberately repeats correlation 0.4,
  AUC 0.75 and 12 reports. Three of twelve reports use the PSD route (25%). Six
  channels times three positive corrected bands gives 18 positive bands.
- `synthetic_calibration_in_effect.json`: invented server-summary fields with
  transform constant 100, bridge ratio 2 and composed constant 50; refit ratio 2.1
  is exactly 5% higher. Six authored points exercise eligible and excluded marks.
  Summary uncertainty fields are UI examples, not estimates from these six points.

Private historical validation belongs in separately configured local tests; these
fixtures cannot establish numeric agreement with any participant's prior results.
