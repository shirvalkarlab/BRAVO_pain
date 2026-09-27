/**
 * The Biomarkers page's settings and its two results (review of 2026-09-26, findings 1, 3, 5, 6, 7,
 * 10 and 13). The page holds two results built from the matching settings: the heat-map grid and the
 * older all-band scan. Neither is rebuilt when a setting moves; the page's Recompute rebuilds both.
 * The whole page is rendered with the saved RCS08 heat-map grid of 2026-09-15; Plotly and the page
 * frame are replaced (jsdom cannot draw; the frame is the app's).
 *
 * What is pinned:
 *   1. the heat-map request carries no cap per report, gap or TD length (the grid reads none of them,
 *      and sending them made every other score be fetched again for nothing);
 *   2. the page's Recompute control turns when only the heat maps are out of date, and the heat maps'
 *      own Recompute rebuilds the selected score's grid under the settings on screen;
 *   3. the page no longer says the heat maps follow the controls live;
 *   4. the clinic-sheet switch does not mark the all-band scan out of date (the scan reads REDCap
 *      ratings only), and the scan's settings say so;
 *   5. the last scan's settings print a tertile split as thirds, in the page's own words, and no
 *      fold opens on nothing;
 *   6. the matching summary names the split and makes no claim about a cap per report; the three
 *      controls the heat maps ignore say so.
 */
import "@testing-library/jest-dom";
import { render as rtlRender, screen, waitFor, act, fireEvent, within } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import theme from "assets/theme";
import { PlatformContextProvider } from "context";
import { invalidateAll, putResult, settingsKey, MODULES } from "database/resultCache";
import { biomarkerHeatmapSlot, CL } from "views/Reports/moduleCacheKeys";

import sweep from "./__fixtures__/rcs08_band_sweep.json";
import calib from "./__fixtures__/rcs08_calibration_in_effect.json";
import { saveControls } from "./biomarkerStateStore";
import { matchingSummary } from "./MatchWindowBand";

jest.mock("plotly.js-dist", () => {
  const noop = () => {};
  const react = (id) => {
    const el = typeof id === "string" ? global.document.getElementById(id) : id;
    if (el) { el.on = noop; el.removeAllListeners = noop; el.removeListener = noop; el.data = []; }
    return Promise.resolve();
  };
  return { react, purge: noop, restyle: noop, relayout: noop, newPlot: noop, Plots: { resize: noop } };
});
jest.mock("graphing-utility/Plotly", () => ({
  PlotlyRenderManager: class {
    constructor() { this.traces = []; this.layout = {}; }
    subplots() {} clearData() {} render() {} setLayoutProps() {} setXlabel() {} setYlabel() {} purge() {}
  },
}));
jest.mock("layouts/DatabaseLayout", () => ({ children }) => <div data-testid="page">{children}</div>);
jest.mock("database/session-control", () => ({
  SessionController: { query: jest.fn(), displayError: jest.fn(), setSession: () => {}, getSession: () => null },
}));
// eslint-disable-next-line import/first
import { SessionController } from "database/session-control";
// eslint-disable-next-line import/first
import Biomarkers from "./index";

const UID = "2e3c75c00d7f4f37b53a048d195f11da";
// The heat-map request as the page builds it from its defaults.
const GRID_REQ = {
  source: "both", LabelMetric: "nrs", LabelStrategy: "tertile", PercentileLow: 33.3, PercentileHigh: 66.7,
  MatchToleranceMin: 60, MatchDirection: "pro_first", AllowWindowReuse: false,
  IncludeClinicSheetRatings: false, SlidingWindow: false,
};
// The all-band scan's request as the page builds it from its defaults (no clinic-sheet switch).
const SCAN_REQ = {
  source: "both", LabelMetric: "nrs", LabelStrategy: "tertile", PercentileLow: 25, PercentileHigh: 75,
  MatchToleranceMin: 60, MaxPerRating: 3, RefractoryMin: 2, MatchDirection: "pro_first",
  MatchExtentSec: 30, AllowWindowReuse: false, SlidingWindow: false,
};
// A small scan answer: a tertile split whose echoed cuts are the request's 25 / 75, and an
// analytics block with no sliding correlation (the page always asks for none).
const SCAN = {
  summary: {}, label_metric: "nrs", label_strategy: "tertile", percentile_low: 25, percentile_high: 75,
  available_strategies: [{ key: "tertile", label: "Tertile (low/high, drop middle)" },
    { key: "median", label: "Median split" }, { key: "kmeans", label: "KMeans (legacy)" }],
  analytics: { timedomain: {} },
};

const gridCalls = () => SessionController.query.mock.calls
  .filter(([url, body]) => url === "/api/queryBiomarkerAnalysis" && body && body.BandTimeSweep === "1");

async function renderPage({ gridSettings = GRID_REQ, scan = false, controls = null, scanKey = null } = {}) {
  invalidateAll("page staleness test");
  window.localStorage.clear();
  SessionController.query.mockReset();
  SessionController.query.mockImplementation(() => Promise.resolve({ data: { boot_token: "boot-1" } }));
  putResult(biomarkerHeatmapSlot("nrs"), UID, settingsKey({ ...gridSettings, SweepMetric: "nrs" }), sweep,
    { why: "page staleness test" });
  putResult(CL.conversionModel, UID, settingsKey({}), calib, { why: "page staleness test" });
  if (controls) saveControls(UID, controls);
  if (scan) putResult(MODULES.biomarkers, UID, settingsKey(scanKey || controls.requestParams), SCAN, { why: "page staleness test" });
  let utils;
  await act(async () => {
    utils = rtlRender(
      <ThemeProvider theme={theme}>
        <PlatformContextProvider initialStates={{ darkMode: false }}>
          <MemoryRouter initialEntries={[`/reports/biomarkers/${UID}`]}>
            <Routes><Route path="/reports/biomarkers/:participant_uid" element={<Biomarkers />} /></Routes>
          </MemoryRouter>
        </PlatformContextProvider>
      </ThemeProvider>);
  });
  await waitFor(() => expect(screen.getAllByText(/How to read this/).length).toBeGreaterThan(0), { timeout: 10000 });
  return utils;
}

const barState = () => screen.queryByText(/^SHOWING THE LAST COMPLETED RUN/) ? "stale"
  : screen.queryByText(/^UP TO DATE/) ? "current" : "other";

jest.setTimeout(30000);

describe("1. the heat-map request carries only what the grid reads", () => {
  test("no cap per report, gap or TD length is sent for the heat maps", async () => {
    await renderPage();
    // the page's one Recompute control (the heat maps are current, so theirs is not drawn)
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: /^Recompute( anyway)?$/ })); });
    // generous: under the whole jest run the rebuild's request can take more than the default 1 s
    await waitFor(() => expect(gridCalls().length).toBeGreaterThan(0), { timeout: 10000 });
    gridCalls().forEach(([, body]) => {
      expect(body).not.toHaveProperty("MaxPerRating");
      expect(body).not.toHaveProperty("RefractoryMin");
      expect(body).not.toHaveProperty("MatchExtentSec");
    });
  });
});

describe("2. the page's Recompute control and the heat maps agree", () => {
  test("the Recompute control turns when only the heat maps are out of date", async () => {
    await renderPage({ gridSettings: { ...GRID_REQ, MatchToleranceMin: 30 } });
    await waitFor(() => expect(barState()).toBe("stale"), { timeout: 10000 });
    expect(screen.getByTestId("heatmaps-out-of-date")).toHaveTextContent(/the match window was changed/);
  });

  test("the heat maps' Recompute rebuilds the selected score's grid under the settings on screen", async () => {
    await renderPage({ gridSettings: { ...GRID_REQ, MatchToleranceMin: 30 } });
    const line = screen.getByTestId("heatmaps-out-of-date");
    await act(async () => { fireEvent.click(within(line).getByRole("button", { name: "Recompute" })); });
    await waitFor(() => expect(gridCalls().some(([, b]) => b.SweepMetric === "nrs" && b.MatchToleranceMin === 60)).toBe(true), { timeout: 10000 });
  });
});

describe("3. the page does not say the heat maps follow the controls live", () => {
  test("no sentence calls the heat maps live", async () => {
    await renderPage();
    expect(document.body.textContent).not.toMatch(/heat maps are already live/);
  });
});

describe("4. the clinic-sheet switch and the all-band scan", () => {
  const controls = {
    metric: "nrs", strategy: "tertile", percentileLow: 25, percentileHigh: 75, matchTolerance: 60,
    maxPerRating: 3, refractoryMin: 2, matchDirection: "pro_first", matchExtentSec: 30,
    allowWindowReuse: false, includeClinicSheetRatings: false, requestParams: SCAN_REQ,
  };
  test("turning the switch on does not call the scan out of date", async () => {
    await renderPage({ scan: true, controls, gridSettings: { ...GRID_REQ, PercentileLow: 25, PercentileHigh: 75 } });
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: /\+ clinic titration sessions/, hidden: true })); });
    expect(document.body.textContent)
      .not.toMatch(/the controls on this page have been changed since this analysis was computed/);
  });

  test("a scan request saved with the switch in it is not called out of date on return", async () => {
    await renderPage({ scan: true, scanKey: SCAN_REQ,
      controls: { ...controls, requestParams: { ...SCAN_REQ, IncludeClinicSheetRatings: false } },
      gridSettings: { ...GRID_REQ, PercentileLow: 25, PercentileHigh: 75 } });
    expect(document.body.textContent)
      .not.toMatch(/the controls on this page have been changed since this analysis was computed/);
  });

  test("the scan's settings say it uses the home pain surveys only", async () => {
    await renderPage({ scan: true, controls, gridSettings: { ...GRID_REQ, PercentileLow: 25, PercentileHigh: 75 } });
    expect(document.body.textContent).toMatch(/The all-band scan uses the home pain surveys only/);
  });
});

describe("5. the last scan's settings", () => {
  const controls = {
    metric: "nrs", strategy: "tertile", percentileLow: 25, percentileHigh: 75, matchTolerance: 60,
    maxPerRating: 3, refractoryMin: 2, matchDirection: "pro_first", matchExtentSec: 30,
    allowWindowReuse: false, includeClinicSheetRatings: false, requestParams: SCAN_REQ,
  };
  test("a tertile split prints the thirds, not the echoed 25th and 75th, in the page's words", async () => {
    await renderPage({ scan: true, controls, gridSettings: { ...GRID_REQ, PercentileLow: 25, PercentileHigh: 75 } });
    const text = document.body.textContent;
    expect(text).toMatch(/Split into high and low by: Lowest and highest thirds \(middle left out\) \(at or below the 33rd and at or above the 67th percentile/);
    expect(text).not.toMatch(/at or below the 25th/);
    expect(text).not.toMatch(/Tertile \(low\/high, drop middle\)|KMeans \(legacy\)/);
  });

  test("no fold opens on an empty sliding correlation", async () => {
    await renderPage({ scan: true, controls, gridSettings: { ...GRID_REQ, PercentileLow: 25, PercentileHigh: 75 } });
    expect(document.body.textContent).not.toMatch(/How each band's link with pain changed over time/);
  });
});

describe("6. the matching summary and the controls the heat maps ignore", () => {
  test("the summary names the split and claims no cap per report", () => {
    const s = matchingSummary({ matchTolerance: 60, matchDirection: "pro_first", maxPerRating: 3,
      includeClinicSheetRatings: false, strategy: "tertile", percentileLow: 33.3, percentileHigh: 66.7 });
    expect(s).not.toMatch(/per report/);
    expect(s).toMatch(/lowest and highest thirds/);
    expect(matchingSummary({ matchTolerance: 60, matchDirection: "pro_first", strategy: "percentile",
      percentileLow: 25, percentileHigh: 75 })).toMatch(/high \/ low split at the 25th and 75th percentiles/);
    expect(matchingSummary({ matchTolerance: 60, matchDirection: "pro_first", strategy: "median" }))
      .toMatch(/median split/);
  });

  test("the cap, the gap and the TD length each say they apply to the all-band scan, not the heat maps", async () => {
    await renderPage();
    const more = screen.getByTestId("more-matching-options");
    expect((more.textContent.match(/applies to the all-band scan[^.]*, not the heat maps/g) || []).length).toBe(3);
  });
});
