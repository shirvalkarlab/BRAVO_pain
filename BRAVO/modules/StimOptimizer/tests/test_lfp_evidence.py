

# --- 2026-09-06: two tests were here and were REMOVED the same night -----------------------------
# They pinned a scale factor of 215 that I had added to lfp_evidence.py and then reverted, after
# HANDOFF_TD_LSB_calibration_2026-06-27.md showed the constant contradicted a written architecture
# decision (one recipe, k = 352.62, for both the exploration panels and this module) and that my
# measurement of it reproduced a pairing error rather than a device property. Recorded rather than
# deleted silently, so that a reader who finds the factor discussed elsewhere can see it was
# withdrawn on purpose. The replacement is to source band power from the calibrated route
# (Biomarkers.routines.analytics.td_to_lsb), which is a change of DSP and not a change of constant,
# and it needs its own tests when it lands.
