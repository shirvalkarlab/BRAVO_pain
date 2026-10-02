/**
 * The Closed-Loop page inherits the matching settings the Biomarkers page most recently ran
 * (decision 331; the PI, 2026-09-26).
 *
 * What is pinned:
 *   1. one source: what the Biomarkers page saved as its last run decides the "Choose a band" grid's
 *      request, the report's (for the stability card) and the deployment summary's -- change a
 *      Biomarkers setting and run it, and all three requests change;
 *   2. the grid request carries the clinic-sheet switch the Biomarkers page ran with (it read the
 *      last Compute request, which no longer carries the switch, so it asked for the sheets-off grid);
 *   3. the summary takes every setting but the direction, which the ROC's own toggle sets;
 *   4. a report or summary computed under other matching settings is withheld and named;
 *   5. the page's one line says which settings it inherited.
 */
import { saveControls } from "views/Reports/Biomarkers/biomarkerStateStore";

import { biomarkerGridSettings } from "./useBandSweepGrid";
import { deploymentReportBody } from "./useDeploymentReport";
import { summaryRequestParams, withheldIfOtherBand } from "./candidateRequestParams";
import { inheritedMatching, inheritedMatchingLine, matchingRequestKeys, MATCHING_KEYS }
  from "./inheritedMatching";

const UID = "u-331";
const BAND = { contact: "ONE_THREE_LEFT", center_freq_hz: 24.5, label: {}, grid_settings: {
  sweep_metric: "nrs", label_strategy: "tertile", percentile_low: 33.3, percentile_high: 66.7,
  match_tolerance_min: 60 } };
const CAND = { channel: "ONE_THREE_LEFT", centerHz: 24.5, bandWidthHz: 5, sensingHemisphere: "Left" };

// What the Biomarkers page saves when Recompute runs (index.js `compute`).
const run = (settings) => saveControls(UID, { metric: settings.LabelMetric || "nrs",
  matchingRun: { settings, ranAt: Date.UTC(2026, 8, 26, 21, 5) } });
const requests = () => {
  const inh = inheritedMatching(UID);
  return {
    grid: biomarkerGridSettings(UID),
    report: deploymentReportBody({ participantUid: UID, bandCandidate: CAND, painScore: "nrs",
      matching: matchingRequestKeys(inh, MATCHING_KEYS) }),
    summary: summaryRequestParams(BAND, !!matchingRequestKeys(inh).IncludeClinicSheetRatings,
      "nrs", inh),
  };
};

beforeEach(() => window.localStorage.clear());

describe("1-3. a Biomarkers run changes what the Closed-Loop page requests", () => {
  test("the defaults when the Biomarkers page has not been run", () => {
    const r = requests();
    expect(r.grid).toMatchObject({ MatchToleranceMin: 15, MatchDirection: "nearest", SweepMetric: "nrs" });
    expect(r.report).toMatchObject({ MatchToleranceMin: 15, MatchDirection: "nearest", MaxPerRating: 3 });
    expect(r.summary.MatchToleranceMin).toBe(15);
  });

  test("changing the window, the switch and the split on the Biomarkers page and running it", () => {
    const before = requests();
    run({ LabelMetric: "left_leg_vas", MatchToleranceMin: 30, MatchDirection: "prior",
      AllowWindowReuse: false, MaxPerRating: 1, RefractoryMin: 4, MatchExtentSec: 30,
      IncludeClinicSheetRatings: true, LabelStrategy: "median", PercentileLow: 33.3333,
      PercentileHigh: 66.6667 });
    const after = requests();
    expect(after.grid).not.toEqual(before.grid);
    expect(after.report).not.toEqual(before.report);
    expect(after.summary).not.toEqual(before.summary);
    // the grid: every setting the heat maps read, the switch included (2.)
    expect(after.grid).toMatchObject({ SweepMetric: "left_leg_vas", MatchToleranceMin: 30,
      MatchDirection: "prior", IncludeClinicSheetRatings: "1", LabelStrategy: "median" });
    // the report, for the stability card: every matching setting; its pain score is the page's own
    expect(after.report).toMatchObject({ MatchToleranceMin: 30, MatchDirection: "prior",
      MaxPerRating: 1, RefractoryMin: 4, IncludeClinicSheetRatings: "1", LabelStrategy: "median",
      PainScore: "nrs" });
    // the summary: all but the direction (3.), the Biomarkers run winning over the band's own 60
    expect(after.summary).toMatchObject({ MatchToleranceMin: 30, MaxPerRating: 1, RefractoryMin: 4,
      IncludeClinicSheetRatings: "1", LabelStrategy: "median", LabelMetric: "nrs" });
    expect(after.summary).not.toHaveProperty("MatchDirection");
  });
});

describe("4. a result computed under other matching settings is withheld", () => {
  const report = { data: { candidates: [{ channel: "ONE_THREE_LEFT", center_hz: 24.5 }],
    pain_score: { key: "nrs", label: "NRS" }, matching: { match_tolerance_min: 60,
      match_direction: "nearest", allow_window_reuse: false, max_per_rating: 3, refractory_min: 2,
      include_clinic_sheet_ratings: false, label_strategy: "tertile", percentile_low: 33.3333,
      percentile_high: 66.6667 } } };
  test("a report at 60 minutes when the page inherited 15", () => {
    const want = { painScore: "nrs", matching: matchingRequestKeys(inheritedMatching(UID)) };
    const out = withheldIfOtherBand(report, BAND, "report", want);
    expect(out.data).toBeNull();
    expect(out.bandMismatch).toMatchObject({ what: "match window", chosen: "15", computedFor: "60" });
  });
  test("the same report at 15 minutes is shown", () => {
    const at15 = { data: { ...report.data, matching: { ...report.data.matching, match_tolerance_min: 15 } } };
    const want = { painScore: "nrs", matching: matchingRequestKeys(inheritedMatching(UID)) };
    expect(withheldIfOtherBand(at15, BAND, "report", want).data).toBe(at15.data);
  });
  test("an answer that echoes no matching settings is not contradicted", () => {
    const old = { data: { ...report.data, matching: undefined } };
    const want = { painScore: "nrs", matching: matchingRequestKeys(inheritedMatching(UID)) };
    expect(withheldIfOtherBand(old, BAND, "report", want).data).toBe(old.data);
  });
});

describe("5. the page says which settings it inherited", () => {
  test("the defaults, said as defaults", () => {
    expect(inheritedMatchingLine(inheritedMatching(UID))).toMatch(
      /^Matching, defaults: ±15 min, nearest, ≤3 per report, 2 min apart, no reuse, clinic sheets out, tertile split/);
  });
  test("a run, with when it ran", () => {
    run({ LabelMetric: "left_leg_vas", MatchToleranceMin: 30, MatchDirection: "nearest",
      IncludeClinicSheetRatings: true, LabelStrategy: "median" });
    const line = inheritedMatchingLine(inheritedMatching(UID));
    expect(line).toMatch(/^Matching from Biomarkers, 2026-09-26 21:05 UTC: ±30 min/);
    expect(line).toMatch(/clinic sheets in, median split, Left Leg VAS\.$/);
  });
});
