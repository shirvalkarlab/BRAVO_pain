# Findings

- The left panel fitted from Welch band power (analytics.psd_lsb_conversion, log-log check, log-space scatter); the right panel runs the adopted recipe (routines/calibration.py: raw median ratio, 5-MAD rule) with no interval.
- MODELED_LSB_SIGMA_FOLD = 1.26 is read at one site (bravo_service._modeled_lsb_threshold_estimate) and printed by LsbPowerPanel.js as "±1σ … (× fold)".
- 59 comment lines quote 352.62 / 73.63 / 270.22; no code line does.
