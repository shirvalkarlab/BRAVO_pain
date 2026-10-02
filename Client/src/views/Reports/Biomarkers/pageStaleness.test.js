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
import { saveControls, loadMatchingRun } from "./biomarkerStateStore";
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
// (decision 331: 15 minutes either side, each recording paired with its nearest report, the
// server's own split cuts)
const GRID_REQ = {
  source: "both", LabelMetric: "nrs", LabelStrategy: "tertile", PercentileLow: 33.3333, PercentileHigh: 66.6667,
  MatchToleranceMin: 15, MatchDirection: "nearest", AllowWindowReuse: false,
  IncludeClinicSheetRatings: false, SlidingWindow: false,
};
// The all-band scan's request as the page builds it from its defaults (decision 334: the switch
// travels with the request now, like every other matching setting).
const SCAN_REQ = {
  source: "both", LabelMetric: "nrs", LabelStrategy: "tertile", PercentileLow: 25, PercentileHigh: 75,
  MatchToleranceMin: 60, MaxPerRating: 3, RefractoryMin: 2, MatchDirection: "pro_first",
  MatchExtentSec: 30, AllowWindowReuse: false, IncludeClinicSheetRatings: false, SlidingWindow: false,
};
// A small scan answer: a tertile split whose echoed cuts are the request's 25 / 75, and an
// analytics block with no sliding correlation (the page always asks for none). `clinic_sheet_ratings`
// is the same shape the heat-map grid's response carries (decision 334): the switch was off.
const SCAN = {
  summary: {}, label_metric: "nrs", label_strategy: "tertile", percentile_low: 25, percentile_high: 75,
  available_strategies: [{ key: "tertile", label: "Tertile (low/high, drop middle)" },
    { key: "median", label: "Median split" }, { key: "kmeans", label: "KMeans (legacy)" }],
  analytics: { timedomain: {} },
  clinic_sheet_ratings: { included: false, n_available: 0, n_added: 0, sheet_column: null, scale: null, reason: null },
};
// The same scan answer with the switch on and 12 sheet ratings merged.
const SCAN_WITH_SHEETS = {
  ...SCAN,
  clinic_sheet_ratings: { included: true, n_available: 12, n_added: 12, sheet_column: "overall", scale: 1, reason: null },
};

const gridCalls = () => SessionController.query.mock.calls
  .filter(([url, body]) => url === "/api/queryBiomarkerAnalysis" && body && body.BandTimeSweep === "1");

async function renderPage({ gridSettings = GRID_REQ, scan = false, controls = null, scanKey = null,
  scanResult = SCAN } = {}) {
  invalidateAll("page staleness test");
  window.localStorage.clear();
  SessionController.query.mockReset();
  SessionController.query.mockImplementation(() => Promise.resolve({ data: { boot_token: "boot-1" } }));
  putResult(biomarkerHeatmapSlot("nrs"), UID, settingsKey({ ...gridSettings, SweepMetric: "nrs" }), sweep,
    { why: "page staleness test" });
  putResult(CL.conversionModel, UID, settingsKey({}), calib, { why: "page staleness test" });
  if (controls) saveControls(UID, controls);
  if (scan) putResult(MODULES.biomarkers, UID, settingsKey(scanKey || controls.requestParams), scanResult, { why: "page staleness test" });
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

  test("only one Recompute button is on the page, even when the heat maps are out of date", async () => {
    await renderPage({ gridSettings: { ...GRID_REQ, MatchToleranceMin: 30 } });
    await waitFor(() => expect(barState()).toBe("stale"), { timeout: 10000 });
    expect(screen.getByTestId("heatmaps-out-of-date")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /Recompute/ })).toHaveLength(1);
    expect(within(screen.getByTestId("heatmaps-out-of-date")).queryByRole("button")).toBeNull();
  });

  test("the page's one Recompute rebuilds the selected score's grid under the settings on screen", async () => {
    await renderPage({ gridSettings: { ...GRID_REQ, MatchToleranceMin: 30 } });
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: /^Recompute( anyway)?$/ })); });
    await waitFor(() => expect(gridCalls().some(([, b]) => b.SweepMetric === "nrs" && b.MatchToleranceMin === 15)).toBe(true), { timeout: 10000 });
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

  test("turning the switch on DOES call the scan out of date (decision 334: it now has an effect)", async () => {
    await renderPage({ scan: true, controls, gridSettings: { ...GRID_REQ, PercentileLow: 25, PercentileHigh: 75 } });
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: /\+ clinic titration sessions/, hidden: true })); });
    expect(document.body.textContent)
      .toMatch(/the controls on this page have been changed since this analysis was computed/);
  });

  test("a saved request whose switch already matches the controls is not called out of date", async () => {
    await renderPage({ scan: true, scanKey: SCAN_REQ,
      controls: { ...controls, requestParams: { ...SCAN_REQ, IncludeClinicSheetRatings: false } },
      gridSettings: { ...GRID_REQ, PercentileLow: 25, PercentileHigh: 75 } });
    expect(document.body.textContent)
      .not.toMatch(/the controls on this page have been changed since this analysis was computed/);
  });

  test("with the switch off, the scan's settings say the home surveys only", async () => {
    await renderPage({ scan: true, controls, gridSettings: { ...GRID_REQ, PercentileLow: 25, PercentileHigh: 75 } });
    expect(document.body.textContent).toMatch(/Home pain surveys only; the same switch the heat maps use is off/);
  });

  test("with the switch on, the scan's settings say how many sheet ratings were added", async () => {
    const onReq = { ...SCAN_REQ, IncludeClinicSheetRatings: true };
    await renderPage({ scan: true, scanKey: onReq, scanResult: SCAN_WITH_SHEETS,
      controls: { ...controls, includeClinicSheetRatings: true, requestParams: onReq },
      gridSettings: { ...GRID_REQ, PercentileLow: 25, PercentileHigh: 75 } });
    expect(document.body.textContent).toMatch(/Includes 12 clinic and at-home sheet ratings/);
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

describe("7. the run the Closed-Loop page inherits (decision 331)", () => {
  // eslint-disable-next-line global-require
  const { biomarkerGridSettings } = require("views/Reports/ClosedLoopSim/useBandSweepGrid");
  test("a heat-map grid shown as current records its settings as the last run", async () => {
    await renderPage();
    await waitFor(() => expect(loadMatchingRun(UID).source).toBe("run"), { timeout: 10000 });
    expect(loadMatchingRun(UID).settings).toMatchObject({ MatchToleranceMin: 15,
      MatchDirection: "nearest", MaxPerRating: 3, RefractoryMin: 2 });
  });

  test("changing a setting and pressing Recompute changes what the Closed-Loop page asks for", async () => {
    const controls = { metric: "nrs", strategy: "tertile", percentileLow: 33.3333,
      percentileHigh: 66.6667, matchTolerance: 30, maxPerRating: 1, refractoryMin: 2,
      matchDirection: "nearest", matchExtentSec: 30, allowWindowReuse: false,
      includeClinicSheetRatings: true };
    await renderPage({ controls, gridSettings: { ...GRID_REQ, MatchToleranceMin: 15 } });
    // nothing has run at 30 minutes yet: the grid on screen is the 15-minute one, marked stale
    expect(biomarkerGridSettings(UID).MatchToleranceMin).not.toBe(30);
    // the page's one Recompute control
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: /^Recompute( anyway)?$/ })); });
    await waitFor(() => expect(loadMatchingRun(UID).settings.MatchToleranceMin).toBe(30), { timeout: 10000 });
    expect(loadMatchingRun(UID).settings).toMatchObject({ MaxPerRating: 1, IncludeClinicSheetRatings: true });
    expect(biomarkerGridSettings(UID)).toMatchObject({ MatchToleranceMin: 30,
      IncludeClinicSheetRatings: "1", SweepMetric: "nrs" });
  });
});

describe("8. the pain-score dropdown is not a reason to recompute (the PI, 2026-10-02)", () => {
  const SCAN_CONTROLS = {
    metric: "nrs", strategy: "tertile", percentileLow: 25, percentileHigh: 75, matchTolerance: 60,
    maxPerRating: 3, refractoryMin: 2, matchDirection: "pro_first", matchExtentSec: 30,
    allowWindowReuse: false, includeClinicSheetRatings: false, requestParams: SCAN_REQ,
  };
  const answerSweeps = () => SessionController.query.mockImplementation((url, body) => Promise.resolve(
    { data: body && body.BandTimeSweep === "1" ? sweep : { boot_token: "boot-1" } }));
  const pickScore = async (label) => {
    const trigger = document.querySelector('[data-testid="pain-score-select"] .MuiSelect-select');
    await act(async () => { fireEvent.mouseDown(trigger); });
    await act(async () => { fireEvent.click(screen.getByRole("option", { name: label })); });
  };
  const gridCallsFor = (m) => gridCalls().filter(([, b]) => b.SweepMetric === m);
  const noStaleNote = () => {
    expect(screen.queryByTestId("heatmaps-out-of-date")).toBeNull();
    expect(document.body.textContent).not.toMatch(/the settings on this page have changed/);
    expect(document.body.textContent).not.toMatch(/the controls on this page have been changed/);
  };

  test("switching to a score whose grid was already fetched in the background says nothing is out of date and fetches nothing", async () => {
    await renderPage();
    answerSweeps();
    await waitFor(() => expect(gridCallsFor("vas").length).toBe(1), { timeout: 10000 });
    await waitFor(() => expect(barState()).toBe("current"));
    await pickScore("Overall VAS");
    await act(async () => { await new Promise((r) => setTimeout(r, 50)); });
    expect(barState()).toBe("current");
    noStaleNote();
    expect(gridCallsFor("vas").length).toBe(1);          // the background fetch; none after the switch
  });

  test("with an all-band scan on screen, switching the score does not turn the Recompute control", async () => {
    // the grid seeded under the very settings the saved controls give, so the page starts up to date
    await renderPage({ scan: true, controls: SCAN_CONTROLS,
      gridSettings: { ...GRID_REQ, PercentileLow: 25, PercentileHigh: 75, MatchToleranceMin: 60,
        MatchDirection: "pro_first" } });
    answerSweeps();
    await waitFor(() => expect(barState()).toBe("current"));
    await pickScore("Overall VAS");
    await act(async () => { await new Promise((r) => setTimeout(r, 50)); });
    expect(barState()).toBe("current");
    noStaleNote();
  });

  test("a matching setting still turns it: the clinic-sheet switch says so", async () => {
    await renderPage();
    await waitFor(() => expect(barState()).toBe("current"));
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: /\+ clinic titration sessions/, hidden: true })); });
    await waitFor(() => expect(barState()).toBe("stale"), { timeout: 10000 });
    expect(screen.getByTestId("heatmaps-out-of-date")).toHaveTextContent(/clinic sheet scores/);
  });
});
