# Oura tab — approved design and implemented defaults

Date: September 4, 2026. This is the independent BRAVO Oura tab alongside the REDCap Timeline, Stimulation programs and Medications tabs. Oura–FreeReps remains a separate page.

## Manuscript evidence

The latest local August 30 resubmission reports daily step count as its wearable activity outcome (Extended Data Figure 3d). Supplement §S6 describes Fitbit Sense 2 / Versa 4 and Apple Watch / HealthKit data, with days retained at ≥70% wear. The main text explicitly calls the available actigraphy heterogeneous and limited to a subset, so it should not be treated as a powered group effect. Sleep, HRV and heart rate are not the wearable outcomes reported in that section.

[Main manuscript](</Users/adityabehal/UCSF DBS for Pain Dropbox/PainNeuromodulationLab/MANUSCRIPTS/2026 sEEG CL only/Nature Medicine/Re-Resubmission_2026_Aug/2026_Aug30_sEEG CLDBS_MAIN_FINAL_round2.docx>) · [Supplement §S6](</Users/adityabehal/UCSF DBS for Pain Dropbox/PainNeuromodulationLab/MANUSCRIPTS/2026 sEEG CL only/Nature Medicine/Re-Resubmission_2026_Aug/2026_Aug30_sEEG CLDBS Supplementary Materials_FINAL_round2.docx>)

## Approved defaults

The user approved six charts, in this order:

1. Steps.
2. Heart rate, retaining all available sample times.
3. Heart-rate variability, retaining all available sample times.
4. Total calories.
5. Sleep duration (longest episode).
6. Total sleep duration, including naps.

The user requested a nighttime label for the fifth chart. Source validation found that the normalized records do not retain night/nap types and 12 selected longest episodes occurred during daytime. The provisional accurate label is therefore “Sleep duration (longest episode)”; a literal nighttime definition remains an optional user choice. Both sleep charts exclude awake time. No nighttime cutoff was invented.

Heart rate and HRV retain exact timestamps and source labels across all eligible stored streams. Current stored HRV coverage is in Sleep; the implementation does not deliberately restrict it to sleep. Optional sleep-only daily summaries remain clearly separate metrics.

## Display and controls

- Six vertically stacked, responsive line charts, with no individual horizontal scrolling.
- Add/remove selector with 44 supported metrics grouped by category; unavailable metrics are disabled.
- Full Oura history, custom dates and past 28 days ending today in Pacific time.
- Study phases applicable to the selected range; no invented later trial phases.
- Exactly three toggles: 5-point rolling median (on initially), Past 28 days, Stimulation context (on initially). Points and study phases remain visible.
- Centered median uses each eligible observation plus up to two before and two after, computed before date filtering using the same helper as REDCap. Daily measures use observed daily values, HR/HRV use recorded samples. Raw traces and gaps remain visible.
- Reviewed REDCap home-program records supply transition lines and clickable settings labels, the same searchable settings panel, and timed HR/HRV hover context. Unknown intervals remain explicit. Daily totals are not assigned a single stimulation program.
- Missing and excluded observations remain gaps; sample lines break across gaps longer than 15 minutes. This is a display rule, not an exclusion.
- Daily charts report observed days; sample charts report readings and days.

## Eligibility boundary

Current RCS08 Oura QC masks the established staff-testing day/timestamp windows and source missing values. It does not apply a ≥70% daily wear rule. Preserve that policy. Oura non-wear time may be offered as an optional completeness measure, but converting it into validated wear coverage or applying the manuscript cutoff requires an explicit definition and separate approval; missing days are not zero steps.

## Full supported numeric catalog

See [the 44-metric inventory](oura-timeline-metric-inventory.md) for the complete local catalog, units, and sources. This is not a claim that every Oura consumer-app feature is ingested or that every catalog metric has participant observations. Genuine score streams are required; contributor scores are not substituted.

Implementation: the independent tab and six defaults are deployed locally. Oura–FreeReps remains separate. Shared outlined-button text colors were corrected in light and dark themes, including its Refresh view button.
