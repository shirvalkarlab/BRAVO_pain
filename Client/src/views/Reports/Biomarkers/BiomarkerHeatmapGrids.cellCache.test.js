/**
 * A clicked square's scatter and violin are fetched once and kept (the PI, 2026-10-02: they used to
 * stay cached; "the new speed-up caching seemed to uncache it").
 *
 * Cause found: the fetched squares lived in a per-component `useRef` map that was (a) thrown away
 * every time the shown grid object changed -- a switch to another pain score and back, and the
 * grid's first draw after any remount -- and (b) lost whenever the page was left and returned to.
 * The squares now live at module scope (`heatmapCellCache.js`), filed under participant, pain score
 * and the settings the shown grid was computed under, bounded to 200, and dropped only when that
 * pain score's grid is rebuilt or the server changed.
 *
 * What is pinned, each counted in requests for a square:
 *   1. clicking one square twice asks once;
 *   2. A, then B, then A again asks twice (A is not re-asked);
 *   3. leaving the page and coming back, then clicking A, asks nothing;
 *   4. switching to another pain score and back, then clicking A, asks nothing;
 *   5. a rebuilt grid (Recompute) drops its squares, so the next click asks again;
 *   6. the cache holds at most 200 squares and drops the oldest.
 */
import "@testing-library/jest-dom";
import { render as rtlRender, screen, waitFor, act } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";

import theme from "assets/theme";
import { PlatformContextProvider } from "context";
import { invalidate, invalidateAll, putResult, settingsKey } from "database/resultCache";
import { biomarkerHeatmapSlot } from "views/Reports/moduleCacheKeys";

import BiomarkerHeatmapGrids from "./BiomarkerHeatmapGrids";
import { putCell, getCell, cellCount, MAX_CELLS } from "./heatmapCellCache";
import sweep from "./__fixtures__/rcs08_band_sweep.json";

jest.mock("plotly.js-dist", () => {
  const noop = () => {};
  const react = (id) => {
    const el = typeof id === "string" ? global.document.getElementById(id) : id;
    if (el) {
      el.on = (evt, fn) => { (global.__handlers = global.__handlers || {})[`${el.id}:${evt}`] = fn; };
      el.removeAllListeners = (evt) => { if (global.__handlers) delete global.__handlers[`${el.id}:${evt}`]; };
      el.removeListener = noop; el.data = [];
    }
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

const UID = "2e3c75c00d7f4f37b53a048d195f11da";
const METRICS = [{ key: "nrs", label: "NRS (0–10)" }, { key: "vas", label: "Overall VAS" }];
const REQ = { source: "both", LabelMetric: "nrs", LabelStrategy: "tertile", PercentileLow: 33.3,
  PercentileHigh: 66.7, MatchToleranceMin: 60, MatchDirection: "pro_first", AllowWindowReuse: false,
  IncludeClinicSheetRatings: false, SlidingWindow: false };
const gridKey = (m) => settingsKey({ ...REQ, LabelMetric: m, SweepMetric: m });

const wrap = (metric) => (
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>
      <BiomarkerHeatmapGrids participantUid={UID} requestParams={{ ...REQ, LabelMetric: metric }}
        availableMetrics={METRICS} pageMetric={metric} metricLabel="NRS (0–10)"
        onOpenInClosedLoop={() => {}} />
    </PlatformContextProvider>
  </ThemeProvider>
);

const cellCalls = () => SessionController.query.mock.calls
  .filter(([url, body]) => url === "/api/queryBiomarkerAnalysis" && body && body.BandTimeSweepCell === "1");

async function mount(metric = "nrs") {
  const utils = rtlRender(wrap(metric));
  await waitFor(() => expect(global.__handlers && global.__handlers["biomarker-heatmap-correlation:plotly_click"])
    .toBeTruthy(), { timeout: 5000 });
  return utils;
}
const click = async (row, col) => {
  await act(async () => {
    global.__handlers["biomarker-heatmap-correlation:plotly_click"](
      { points: [{ curveNumber: 0, pointNumber: [row, col] }] });
  });
};

beforeEach(() => {
  global.__handlers = {};
  invalidateAll("cell cache test setup");
  SessionController.query.mockReset();
  SessionController.query.mockImplementation((url, body) => Promise.resolve({
    data: body && body.BandTimeSweep === "1" ? sweep
      : body && body.BandTimeSweepCell === "1"
        ? { band_time_sweep_cell: { points: [{ x: 1, y: 2 }] } } : { boot_token: "boot-1" } }));
  // two different grid objects, as the real two scores' grids are
  ["nrs", "vas"].forEach((m) => putResult(biomarkerHeatmapSlot(m), UID, gridKey(m), { ...sweep }, { why: "cell cache test" }));
});

describe("a clicked square is fetched once and kept", () => {
  test("1. clicking one square twice asks once", async () => {
    await mount();
    await click(1, 2); await click(1, 2);
    expect(cellCalls()).toHaveLength(1);
  });

  test("2. A, then B, then A again asks twice", async () => {
    await mount();
    await click(1, 2); await click(2, 3); await click(1, 2);
    expect(cellCalls()).toHaveLength(2);
  });

  test("3. leaving the page and coming back, then clicking A, asks nothing", async () => {
    const first = await mount();
    await click(1, 2);
    expect(cellCalls()).toHaveLength(1);
    first.unmount();
    global.__handlers = {};
    await mount();
    await click(1, 2);
    expect(cellCalls()).toHaveLength(1);
  });

  test("4. switching to another pain score and back, then clicking A, asks nothing", async () => {
    const utils = await mount("nrs");
    await click(1, 2);
    expect(cellCalls()).toHaveLength(1);
    await act(async () => { utils.rerender(wrap("vas")); });
    await act(async () => { utils.rerender(wrap("nrs")); });
    await waitFor(() => expect(global.__handlers["biomarker-heatmap-correlation:plotly_click"]).toBeTruthy());
    await click(1, 2);
    expect(cellCalls()).toHaveLength(1);
  });

  test("5. a rebuilt grid drops its squares, so the next click asks again", async () => {
    await mount();
    await click(1, 2);
    expect(cellCalls()).toHaveLength(1);
    await act(async () => { invalidate(biomarkerHeatmapSlot("nrs"), UID); });
    await act(async () => { putResult(biomarkerHeatmapSlot("nrs"), UID, gridKey("nrs"), { ...sweep }, { why: "rebuilt" }); });
    await waitFor(() => expect(global.__handlers["biomarker-heatmap-correlation:plotly_click"]).toBeTruthy());
    await click(1, 2);
    expect(cellCalls()).toHaveLength(2);
  });

  test("6. the cache holds at most 200 squares and drops the oldest", () => {
    expect(MAX_CELLS).toBe(200);
    for (let i = 0; i < 205; i += 1) putCell(`u|nrs|k|c|${i}|1`, { points: [i] });
    expect(cellCount()).toBe(200);
    expect(getCell("u|nrs|k|c|0|1")).toBeUndefined();
    expect(getCell("u|nrs|k|c|204|1")).toEqual({ points: [204] });
  });
});
