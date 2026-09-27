/**
 * The Biomarkers page's default for every matching and split control, in one block (decision 331).
 *
 * THE HOME IS THE SERVER'S: `BRAVO/modules/Biomarkers/routines/sweep_settings.py` (the DEFAULT_*
 * constants and `matching_defaults()`), which every endpoint and offline analysis reads when a
 * request leaves a setting out. This block carries the same values so the page's controls start
 * where the server would, and a page test (`matchingDefaults.test.js`) reads the server's file and
 * fails if a value here differs from it. Change a default there and here together, and bump MATCHING_DEFAULTS_VERSION below so
 * a viewer's saved setting from before is moved once (`biomarkerStateStore.migrateControls`).
 *
 * The values (the PI's ruling of 2026-09-26, on the measurement in
 * artifacts/analysis_2026-09-26_json_time_fields_and_matching.md):
 *  - the window, 15 minutes either side of each report (was 60): keeps 97-98% of the real PSD
 *    matches and 85-88% of the real TD matches; 60 added almost nothing real and tripled the chance
 *    matches;
 *  - the direction, "nearest" (was "pro_first"): either side of the report, and the one under which
 *    the minimum gap applies, so one report never keeps two overlapping pieces of one press;
 *  - one stretch of recording answers one report (no reuse), unchanged;
 *  - the cap per report (3), the minimum gap (2 min) and the TD length (30 s): no measured basis,
 *    kept;
 *  - the clinic-sheet ratings out, the pain score NRS and the split the lowest and highest thirds,
 *    unchanged; the split's two cuts are the server's own (33.3333 / 66.6667, the page wrote 33.3 /
 *    66.7 before).
 */
export const MATCHING_DEFAULTS = Object.freeze({
  metric: "nrs",
  strategy: "tertile",
  percentileLow: 33.3333,
  percentileHigh: 66.6667,
  matchTolerance: 15,
  matchDirection: "nearest",
  allowWindowReuse: false,
  maxPerRating: 3,
  refractoryMin: 2,
  matchExtentSec: 30,
  includeClinicSheetRatings: false,
});

/**
 * The version of these defaults a saved setting was written under. 1 is everything saved before
 * decision 331 (no version was written then); 2 is decision 331's defaults.
 */
export const MATCHING_DEFAULTS_VERSION = 2;

/**
 * The defaults each version replaced: a saved value equal to one of these, written under an older
 * version, was the old default (or, for the window, the value the PI's own page held, 5 minutes)
 * and is moved to today's default once. Anything else a viewer chose is kept.
 */
export const REPLACED_DEFAULTS = Object.freeze({
  2: {
    matchTolerance: [60, 5],
    matchDirection: ["pro_first"],
    percentileLow: [33.3],
    percentileHigh: [66.7],
  },
});

/** Each control's page name and the request key it is sent as. */
export const CONTROL_REQUEST_KEYS = Object.freeze({
  strategy: "LabelStrategy",
  percentileLow: "PercentileLow",
  percentileHigh: "PercentileHigh",
  matchTolerance: "MatchToleranceMin",
  matchDirection: "MatchDirection",
  allowWindowReuse: "AllowWindowReuse",
  maxPerRating: "MaxPerRating",
  refractoryMin: "RefractoryMin",
  matchExtentSec: "MatchExtentSec",
  includeClinicSheetRatings: "IncludeClinicSheetRatings",
});
