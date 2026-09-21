/**
 * The coverage sentence at the top of the Binarization card (the PI, 2026-09-21): how many pain
 * reports have ANY neural sample within the match window, and within two wider windows, so a reader
 * sees what the window admits and what it leaves out. Counted in the browser from the sample index
 * and the pain series the card already holds, so it follows the slider live.
 */
import "@testing-library/jest-dom";
import { render as rtlRender } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";
import theme from "assets/theme";
import { PlatformContextProvider } from "context";

import { reportCoverage, computeMatchedScanModel } from "./binarizationModel";
import BinarizationPreview from "./BinarizationPreview";

jest.mock("plotly.js-dist", () => {
  const noop = () => {};
  return { react: () => Promise.resolve(), purge: noop, restyle: noop, relayout: noop, newPlot: noop };
});

const wrap = (ui) => (
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>
);

const H = 3600;
// five reports one hour apart; samples: one 30 s BEFORE report 0, one 5 min AFTER report 1,
// one 30 min before report 2 (streaming), nothing near reports 3 and 4 except a sample 90 min after 4
const painSeries = { t: [0, H, 2 * H, 3 * H, 4 * H], y: [5, 6, 7, 8, 9] };
const scanIndex = [
  { t: -30, channel: "ZERO_THREE_LEFT", source: "Indefinite stream" },
  { t: H + 300, channel: "ZERO_THREE_LEFT", source: "Patient event" },
  { t: 2 * H - 1800, channel: "ONE_THREE_LEFT", source: "BrainSense streaming" },
  { t: 4 * H + 5400, channel: "ZERO_THREE_RIGHT", source: "Montage" },
];

describe("reportCoverage", () => {
  it("counts distinct reports with any sample within the window and two wider windows, either direction", () => {
    const c = reportCoverage({ scanIndex, painSeries, toleranceMin: 2 });
    expect(c.n_reports).toBe(5);
    expect(c.tolerance_min).toBe(2);
    expect(c.n_within_window).toBe(1);          // report 0 (30 s before)
    expect(c.n_within_10).toBe(2);              // + report 1 (5 min after)
    expect(c.n_within_60).toBe(3);              // + report 2 (30 min before); report 4's sample is 90 min away
    expect(c.n_within_window_prior).toBe(1);    // the sample precedes report 0
  });

  it("a wider window at the slider makes the window count the largest of the three", () => {
    const c = reportCoverage({ scanIndex, painSeries, toleranceMin: 120 });
    expect(c.n_within_window).toBe(5);          // report 3 sits 90 min after report 2's sample and 90 min before report 4's
    expect(c.n_within_10).toBe(2);
    expect(c.n_within_60).toBe(3);              // report 3's nearest sample is 90 min away
    expect(c.n_within_window_prior).toBe(4);    // 0, 1 (the -30 s sample is 60.5 min before it), 2 and 3
  });

  it("returns null counts without inputs", () => {
    expect(reportCoverage({ scanIndex: [], painSeries, toleranceMin: 2 })).toBeNull();
    expect(reportCoverage({ scanIndex, painSeries: null, toleranceMin: 2 })).toBeNull();
  });

  it("the card prints the sentence in bold at the top, with the metric named and the prior-only count", () => {
    const scanModel = computeMatchedScanModel({ scanIndex, painSeries, toleranceMin: 2, strategy: "median",
      percentileLow: 33, percentileHigh: 67, matchDirection: "prior" });
    const { container } = rtlRender(wrap(
      <BinarizationPreview points={[]} strategy="median" percentileLow={33} percentileHigh={67}
        metricLabel="Left Leg VAS" metricKey="left_leg_vas" totalReports={5} loading={false}
        matchTolerance={2} setMatchTolerance={() => {}} scanModel={scanModel} matchedLoading={false}
        matchDirty={false} setPercentileLow={() => {}} setPercentileHigh={() => {}} setStrategy={() => {}}
        showDescriptions={false} matchDirection="prior" coverage={reportCoverage({ scanIndex, painSeries, toleranceMin: 2 })} />));
    const el = container.querySelector('[data-testid="report-coverage"]');
    expect(el).not.toBeNull();
    const bold = el.querySelector("b");
    expect(bold.textContent).toBe("1 of 5 Left Leg VAS reports have a neural sample within ±2 min; 2 within ±10 min; 3 within ±60 min.");
    expect(el.textContent).toContain("Only the first group can enter the grid at this window; matching from before the report only keeps 1 of them.");
    // the sentence sits above the match-window control
    const all = container.textContent;
    expect(all.indexOf("reports have a neural sample")).toBeLessThan(all.indexOf("Match window"));
  });
});
