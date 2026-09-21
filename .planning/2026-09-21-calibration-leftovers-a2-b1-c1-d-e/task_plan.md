# Task Plan: Calibration leftovers, the PI's rulings of 2026-09-21

## Goal
A2: the modelled threshold's band from the calibration blocks' raw scatter, not the deleted model's 1.26. B1: the Biomarkers page's left refit panel deleted, the calibration-in-effect panel takes its place. C1: that panel carries a bootstrap interval on the median ratio, a 1-MAD band and a raw proportionality check. D: stale-constant comments reworded. E: the two uncalled statistics helpers deleted.

## Next Step
None: closed (decision 227).

## Current Phase
Phase 3

### Phase 1: B1, the panels
- [x] `PsdLsbPanel.js`, `/queryPsdLsbConversion`, `band_psd_lsb_conversion`, `analytics.psd_lsb_conversion` (the log-log fit) and their tests deleted; the committed-band read on the page gone
- [x] The calibration-in-effect panel in the left slot, section text rewritten; jest; bundle; watched live
- **Status:** complete

### Phase 2: C1 and A2, the raw scatter
- [x] `calibration.transform_k` reports a bootstrap interval on the median ratio, the 1-MAD band and a raw proportionality check; the panel draws and prints them (tests first)
- [x] The modelled threshold's band reads the blocks' scatter; `MODELED_LSB_SIGMA_FOLD` deleted; the Closed-Loop card's sentence reworded; live before/after on RCS08
- **Status:** complete

### Phase 3: D and E
- [x] Every comment quoting 352.62 / 73.63 / 270.22 reworded to name the constant in effect
- [x] `_cv_logistic_auc` and `_cluster_robust_logit_p` deleted
- [x] Suites; decision row 227; push
- **Status:** complete

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| The surviving calibration panel goes full width | one panel in a two-column row reads as a gap; the PI said "move it there" |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
