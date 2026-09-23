/**
 * A band picked on the "Choose a band" grid carries its grid's pain score, split and match window
 * to the deployment summary (2026-09-23). Before, its empty label contributed nothing and the
 * summary used NRS and a tertile split whatever grid the band came from.
 */
import requestParamsFromCandidate from "./candidateRequestParams";

const GRID = { sweep_metric: "left_leg_vas", metric_label: "Left Leg VAS", match_tolerance_min: 60,
  match_direction: "pro_first", allow_window_reuse: false, label_strategy: "tertile",
  percentile_low: 33.3333, percentile_high: 66.6667, include_clinic_sheet_ratings: true };

test("a grid-chosen band carries its grid's pain score, split and window", () => {
  expect(requestParamsFromCandidate({ contact: "ONE_THREE_LEFT", label: {}, grid_settings: GRID }))
    .toEqual({ LabelMetric: "left_leg_vas", LabelStrategy: "tertile", PercentileLow: 33.3333,
      PercentileHigh: 66.6667, MatchToleranceMin: 60 });
});

test("never the match direction, which the cut-point sets, nor the clinic-sheet switch", () => {
  const rp = requestParamsFromCandidate({ label: {}, grid_settings: GRID });
  expect(rp).not.toHaveProperty("MatchDirection");
  expect(rp).not.toHaveProperty("IncludeClinicSheetRatings");
});

test("a discovery candidate's own label still wins where it says something", () => {
  const bc = { label: { pro_metric: "nrs", binarization: { strategy: "median" }, match_tolerance_min: 30 },
    grid_settings: GRID };
  expect(requestParamsFromCandidate(bc)).toEqual({ LabelMetric: "nrs", LabelStrategy: "median",
    PercentileLow: 33.3333, PercentileHigh: 66.6667, MatchToleranceMin: 30 });
});

test("a band with neither says nothing, as before", () => {
  expect(requestParamsFromCandidate({ label: {} })).toEqual({});
  expect(requestParamsFromCandidate(null)).toEqual({});
});
