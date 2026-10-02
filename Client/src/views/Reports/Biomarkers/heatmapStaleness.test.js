/**
 * The heat maps when the matching or split settings have moved since they were computed (review of
 * 2026-09-26, findings 1, 2 and 12). The shared result cache does not rebuild a grid when a setting
 * changes: it hands back the grid it holds, marked stale, and the page's Recompute rebuilds it (the
 * PI's design; `database/resultCache.js` and `useCachedResult.js` are his and are not edited). Before
 * this change nothing on the heat maps said so: the maps, the status line and a clicked square's
 * scatter could each describe a different pairing of reports with recordings.
 *
 * What is pinned:
 *   1. a grid computed under other settings says, above the maps, WHICH settings changed, and offers
 *      the page's Recompute; a grid computed under the settings on screen says nothing;
 *   2. the grid tells the page it is out of date, so the page's Recompute control can turn;
 *   3. while the shown grid is out of date, no other pain score is fetched in the background;
 *   4. a clicked square is fetched with the settings the SHOWN grid was computed under;
 *   5. the clinic-sheet switch counts as a matching setting, so a response that changes it and the
 *      split together replaces both grids, not only the right-hand one;
 *   6. a q or p just under 0.05 never prints as "0.05".
 */
import "@testing-library/jest-dom";
import { render as rtlRender, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";

import theme from "assets/theme";
import { PlatformContextProvider } from "context";
import { invalidateAll, putResult, settingsKey } from "database/resultCache";
import { biomarkerHeatmapSlot } from "views/Reports/moduleCacheKeys";

import BiomarkerHeatmapGrids, {
  onlyTheAucGridChanges, settingsChangedWords, heatmapCellRequest,
} from "./BiomarkerHeatmapGrids";
import { fmtP, hoverReadout } from "./gridReadouts";
import sweep from "./__fixtures__/rcs08_band_sweep.json";

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
jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn() } }));
// eslint-disable-next-line import/first
import { SessionController } from "database/session-control";

const wrap = (ui) => (
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>
);

const UID = "2e3c75c00d7f4f37b53a048d195f11da";
const METRICS = [{ key: "nrs", label: "NRS (0–10)" }, { key: "vas", label: "VAS (0–100)" }];
const SHOWN = {
  source: "both", LabelMetric: "nrs", LabelStrategy: "tertile", PercentileLow: 33.3, PercentileHigh: 66.7,
  MatchToleranceMin: 60, MatchDirection: "pro_first", AllowWindowReuse: false,
  IncludeClinicSheetRatings: false, SlidingWindow: false,
};

function seed(settings) {
  putResult(biomarkerHeatmapSlot("nrs"), UID, settingsKey({ ...settings, SweepMetric: "nrs" }), sweep,
    { why: "staleness test" });
}

async function renderGrid(requestParams, extra = {}) {
  const utils = rtlRender(wrap(
    <BiomarkerHeatmapGrids participantUid={UID} requestParams={requestParams} availableMetrics={METRICS}
      pageMetric="nrs" metricLabel="NRS (0–10)" onOpenInClosedLoop={() => {}} {...extra} />,
  ));
  await waitFor(() => expect(screen.getByText(/How to read this/)).toBeInTheDocument());
  return utils;
}

beforeEach(() => {
  invalidateAll("staleness test setup");
  SessionController.query.mockReset();
  SessionController.query.mockImplementation(() => Promise.resolve({ data: { boot_token: "boot-1" } }));
});

describe("1. the heat maps say when they are out of date, and which settings moved", () => {
  test("a grid computed under another window and split names both above the maps and points to the page's one Recompute", async () => {
    seed(SHOWN);
    await renderGrid({ ...SHOWN, MatchToleranceMin: 30, LabelStrategy: "median" });
    const line = screen.getByTestId("heatmaps-out-of-date");
    expect(line).toHaveTextContent("▲");
    expect(line).toHaveTextContent(/computed before the match window and the high \/ low split were changed/);
    expect(line).toHaveTextContent(/Press Recompute at the top of the page/);
    // no second Recompute button of its own (the PI, 2026-10-02)
    expect(screen.queryByRole("button", { name: /Recompute/ })).toBeNull();
  });

  test("a grid computed under the settings on screen carries no out-of-date line", async () => {
    seed(SHOWN);
    await renderGrid(SHOWN);
    expect(screen.queryByTestId("heatmaps-out-of-date")).toBeNull();
  });

  test("the words name each setting once, in plain language", () => {
    expect(settingsChangedWords(SHOWN, { ...SHOWN, IncludeClinicSheetRatings: true })).toEqual(["the clinic sheet scores"]);
    expect(settingsChangedWords(SHOWN, { ...SHOWN, PercentileLow: 25, PercentileHigh: 75 })).toEqual(["the high / low split"]);
    expect(settingsChangedWords(SHOWN, { ...SHOWN, MatchDirection: "prior", AllowWindowReuse: true }))
      .toEqual(["the match direction", "whether one stretch of recording may answer more than one report"]);
    expect(settingsChangedWords(SHOWN, SHOWN)).toEqual([]);
  });
});

describe("2. the grid tells the page it is out of date", () => {
  test("onStale reports true with the changed settings", async () => {
    seed(SHOWN);
    const onStale = jest.fn();
    await renderGrid({ ...SHOWN, MatchToleranceMin: 30 }, { onStale });
    await waitFor(() => expect(onStale).toHaveBeenLastCalledWith(
      expect.objectContaining({ stale: true, changed: ["the match window"] })));
  });
});

describe("3. no background fetch of other scores while the shown grid is out of date", () => {
  test("no grid request goes out while the selected score's grid is stale", async () => {
    seed(SHOWN);
    await renderGrid({ ...SHOWN, MatchToleranceMin: 30 });
    await act(async () => { await new Promise((r) => setTimeout(r, 50)); });
    const gridCalls = SessionController.query.mock.calls.filter(([, body]) => body && body.BandTimeSweep === "1");
    expect(gridCalls).toEqual([]);
  });
});

describe("4. a clicked square uses the shown grid's own settings", () => {
  test("the cell request carries the settings the shown grid was computed under, not the live ones", () => {
    const body = heatmapCellRequest({
      participantUid: UID, shownSettings: { ...SHOWN, SweepMetric: "nrs" },
      requestParams: { ...SHOWN, MatchToleranceMin: 30 }, metric: "nrs",
      channel: "ONE_THREE_LEFT", center: 24.5, seconds: 30,
    });
    expect(body.MatchToleranceMin).toBe(60);
    expect(body).toEqual(expect.objectContaining({
      ParticipantId: UID, SweepMetric: "nrs", BandTimeSweepCell: "1", Channel: "ONE_THREE_LEFT",
      BandCenterHz: 24.5, IntegrationSeconds: 30 }));
  });

  test("with no shown settings the live request is used", () => {
    const body = heatmapCellRequest({
      participantUid: UID, shownSettings: null, requestParams: { ...SHOWN, MatchToleranceMin: 30 },
      metric: "nrs", channel: "ONE_THREE_LEFT", center: 24.5, seconds: 30,
    });
    expect(body.MatchToleranceMin).toBe(30);
  });
});

describe("5. the clinic-sheet switch is a matching setting", () => {
  test("switch and split changed together replace both grids", () => {
    expect(onlyTheAucGridChanges(SHOWN,
      { ...SHOWN, IncludeClinicSheetRatings: true, LabelStrategy: "median" })).toBe(false);
  });
  test("the split changed alone replaces only the right-hand grid", () => {
    expect(onlyTheAucGridChanges(SHOWN, { ...SHOWN, LabelStrategy: "median" })).toBe(true);
  });
});

describe("6. nothing reads as crossing 0.05 that did not", () => {
  test("values in [0.045, 0.05) print as < 0.05, never 0.05", () => {
    expect(fmtP(0.046)).toBe("< 0.05");
    expect(fmtP(0.045)).toBe("< 0.05");
    expect(fmtP(0.0499)).toBe("< 0.05");
  });
  test("0.05 and just above print as 0.05; just below 0.045 rounds down", () => {
    expect(fmtP(0.05)).toBe("0.05");
    expect(fmtP(0.054)).toBe("0.05");
    expect(fmtP(0.0449)).toBe("0.04");
  });
  test("below 0.005 stays < 0.01; 0.005 prints 0.01", () => {
    expect(fmtP(0.0049)).toBe("< 0.01");
    expect(fmtP(0.005)).toBe("0.01");
  });
  test("a best cell with q 0.046 reads q < 0.05 in its hover", () => {
    const sw = JSON.parse(JSON.stringify(sweep.band_time_sweep.ONE_THREE_LEFT));
    const best = sw.best_correlation_rows[0];
    best.family_wise_q_8_to_30hz = 0.046;
    const col = sw.center_freqs_hz.indexOf(best.band_center_hz);
    const row = sw.integration_seconds_delivered.indexOf(best.integration_seconds_delivered);
    expect(hoverReadout(sw, "correlation", col, row)).toMatch(/q < 0\.05 \(fdr 22 bands\)/);
  });
});
