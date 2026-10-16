/**
 * classBalanceFlag — decision 337 (the PI, 2026-09-27): warn when the high/low pain-day split that
 * feeds the discrimination reading (an area-under-the-curve figure, computed as though from a
 * one-band logistic fit) is too lopsided to trust. Two thresholds from the literature, the
 * stricter of the two wins:
 *   - Peduzzi, Concato, Kemper, Holford & Feinstein 1996 (J Clin Epidemiol) — the widely used
 *     "events per variable" rule for a logistic fit: below 10 members in the smaller of the two
 *     outcome groups per fitted term, the fitted numbers and their spread become unreliable. With
 *     one term (the band's own power) that is 10 in the smaller group.
 *   - A widely used general severity scale for an uneven split (see e.g. MachineLearningMastery's
 *     imbalanced-classification guide, summarising Kotsiantis et al. 2006 and others): once the
 *     larger group is at least 3 times the smaller, the split counts as "moderate" imbalance and
 *     is worth a caution.
 *
 * Merged here 2026-10-05: BinarizationPreview.test.js. Each merged file's tests sit in a describe
 * block named after it, with its reason above it.
 */

import { classBalanceFlag } from "./binarizationModel";
import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import BinarizationPreview from "./BinarizationPreview";
import { wrap } from "testUtils/render";

const reactCalls = [];
jest.mock("plotly.js-dist", () => ({
  react: (...args) => { reactCalls.push(args); return Promise.resolve(); },
  purge: () => {}, restyle: () => {}, relayout: () => {}, newPlot: () => {},
}));

test("no flag when both groups are sized well and close to even", () => {
  expect(classBalanceFlag(40, 45)).toBeNull();
  expect(classBalanceFlag(0, 0)).toBeNull();
});

test("flags too few in the smaller group, even when the two are close", () => {
  const msg = classBalanceFlag(8, 9);
  expect(msg).toMatch(/8/);
  expect(msg).toMatch(/10/);
});

test("flags a lopsided split even once both groups clear the size floor", () => {
  const msg = classBalanceFlag(12, 60);
  expect(msg).toMatch(/12/);
  expect(msg).toMatch(/60/);
});

test("the boundary cases: ratio just under 3 passes, at 3 flags; 10 passes, 9 flags", () => {
  expect(classBalanceFlag(10, 29)).toBeNull();
  expect(classBalanceFlag(10, 30)).not.toBeNull();
  expect(classBalanceFlag(10, 10)).toBeNull();
  expect(classBalanceFlag(9, 9)).not.toBeNull();
});

test("never uses jargon the house rules ban from page text", () => {
  const msg = classBalanceFlag(5, 50);
  const lower = msg.toLowerCase();
  for (const banned of ["class imbalance", "predictor", "coefficient", "logistic", "classifier",
                        "epv", "events per variable"]) {
    expect(lower).not.toContain(banned);
  }
});

/* From BinarizationPreview.test.js.
 * Two of the PI's rulings of 2026-09-27, dictated:
 *  - the "Low"/"High" boxes drawn on top of the histogram were running off the screen; each now
 *    carries only its essential count, not the source (TD/PSD) breakdown, which stays available on
 *    hover (decision 337);
 *  - a caution line, in the page's one "needs more data" ink, when the high/low split is too small
 *    or too lopsided to trust (decision 337, `binarizationModel.classBalanceFlag`).
 */
describe("from BinarizationPreview", () => {


  function scanModelWith(nLow, nHigh) {
    const matchedValues = Array.from({ length: nLow + nHigh }, (_, i) => i % 10);
    return {
      matchedValues,
      cuts: { kind: "two-cut", lowCut: 3, highCut: 7 },
      samples: [],
      counts: {
        n_sessions: matchedValues.length, n_matched: matchedValues.length,
        n_high: nHigh, n_low: nLow, n_excluded_middle: 0,
        n_matched_td: matchedValues.length, n_matched_td_montage: 2, n_matched_event: 0,
        n_matched_other: 0,
        by_source: { low: { td: nLow, td_montage: 1, event: 0, other: 0, lsb: 0 },
                     high: { td: nHigh, td_montage: 1, event: 0, other: 0, lsb: 0 },
                     excluded: { td: 0, td_montage: 0, event: 0, other: 0, lsb: 0 } },
        tolerance_min: 15, median_abs_offset_min: 2, min_abs_offset_min: 0, max_abs_offset_min: 5,
        max_per_rating: 3, refractory_min: 2, match_direction: "nearest",
        n_capped_dropped: 0,
        survey_usage: { n_pro_total: 10, n_pro_used: 10, n_pro_unused: 0, n_pro_reused: 0,
                       pct_pro_used: 100, psd_per_pro_mean: 1, psd_per_pro_median: 1, psd_per_pro_max: 1 },
        n_obs: matchedValues.length, pct_psd_used: 100,
      },
      matchable: true, unmatchableReason: null,
    };
  }

  const baseProps = {
    points: [], dailyAgg: [], strategy: "tertile", percentileLow: 33.3333, percentileHigh: 66.6667,
    metricLabel: "NRS", metricKey: "nrs", loading: false, totalReports: 100,
    matchTolerance: 15, matchDirty: false, matchedLoading: false,
    setPercentileLow: () => {}, setPercentileHigh: () => {}, setStrategy: () => {},
  };

  beforeEach(() => { reactCalls.length = 0; });

  test("the low/high boxes on the histogram carry only the essential count, not the source split", () => {
    render(wrap(<BinarizationPreview {...baseProps} scanModel={scanModelWith(15, 15)} />));
    const [, , layout] = reactCalls[reactCalls.length - 1];
    const text = (layout.annotations || []).map((a) => a.text).join("\n");
    expect(text).not.toMatch(/montage\)/);
    expect(text).not.toMatch(/patient event\)/);
    expect(text).not.toMatch(/no sources/);
    // still carries the essential counts
    expect(text).toMatch(/Low/);
    expect(text).toMatch(/High/);
  });

  test("a lopsided split shows the caution line naming both counts", () => {
    render(wrap(<BinarizationPreview {...baseProps} scanModel={scanModelWith(4, 40)} />));
    const caution = screen.getByTestId("class-balance-caution");
    expect(caution.textContent).toMatch(/4/);
    expect(caution.textContent).toMatch(/40/);
  });

  test("a well-balanced, well-sized split shows no caution line", () => {
    render(wrap(<BinarizationPreview {...baseProps} scanModel={scanModelWith(20, 22)} />));
    expect(screen.queryByTestId("class-balance-caution")).toBeNull();
  });
});
