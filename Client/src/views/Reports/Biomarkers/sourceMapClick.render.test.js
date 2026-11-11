/**
 * Clicking a square of the TD-only or PSD-only map (open item of decision 492) opens the same
 * scatter and violins the mixed map opens, from that grid's own matched pairs. Rendered from RCS08's
 * live grid response of 2026-10-22 (the wave-2 fixture: NRS at the page's defaults) with the cell
 * answers the server gave for R 0-3 9.5 Hz at 30 s on the same settings
 * (`__fixtures__/rcs08_open_cells_R03_9p5_2026-10-22.json`: mixed n 465, TD only n 73, PSD only
 * n 418, each equal to its own grid's n for that square).
 *
 * Pinned: the request sends `Source` only for a source map; the cache keeps the three apart; the
 * panel title names the grid; the scatter's headline is the clicked grid's own r and n.
 */
import "@testing-library/jest-dom";
import { render as rtlRender, fireEvent, waitFor } from "@testing-library/react";

import { invalidateAll, putResult, settingsKey } from "database/resultCache";
import { biomarkerHeatmapSlot } from "views/Reports/moduleCacheKeys";
import { wrap } from "testUtils/render";

import BiomarkerHeatmapGrids, { gridSettingsFor, gridStatusLine } from "./BiomarkerHeatmapGrids";
import GRID from "./__fixtures__/rcs08_wave2_grid_nrs_2026-10-22.json";
import CELLS from "./__fixtures__/rcs08_open_cells_R03_9p5_2026-10-22.json";
import { heatmapCellRequest } from "./BiomarkerHeatmapGrids";
import { cellKey } from "./heatmapCellCache";

jest.mock("plotly.js-dist", () => {
  const noop = () => {};
  const react = (id, traces, layout) => {
    const el = typeof id === "string" ? global.document.getElementById(id) : id;
    if (el) {
      // keep each map's handlers, so a test can click a square the way Plotly would
      el.on = (ev, fn) => { ((global.__plotlyOn = global.__plotlyOn || {})[el.id] = global.__plotlyOn[el.id] || {})[ev] = fn; };
      el.removeAllListeners = noop; el.data = [];
    }
    (global.__plotlyReact = global.__plotlyReact || []).push({ id, layout, traces });
    return Promise.resolve();
  };
  return { react, purge: noop, restyle: noop, relayout: noop, newPlot: noop };
});
jest.mock("graphing-utility/Plotly", () => ({
  PlotlyRenderManager: class {
    constructor(divId) { this.divId = divId; this.traces = []; this.layout = {}; }
    subplots() {} clearData() {} render() {} setXlabel() {} setYlabel() {} purge() {}
    setLayoutProps(props) { Object.assign(this.layout, props); }
  },
}));
jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn() } }));
jest.mock("views/Reports/ClosedLoopSim/neighbourPrefetch", () => ({
  prefetchClosedLoopFromBiomarkers: () => Promise.resolve(),
}));
// eslint-disable-next-line import/first
import { SessionController } from "database/session-control";

const UID = "2e3c75c00d7f4f37b53a048d195f11da";
const METRICS = [{ key: "nrs", label: "NRS (0–10)" }];
const REQ = { source: "both", LabelMetric: "nrs", LabelStrategy: "tertile", PercentileLow: 33.3333,
  PercentileHigh: 66.6667, MatchToleranceMin: 15, MatchDirection: "nearest", AllowWindowReuse: false,
  IncludeClinicSheetRatings: false, SlidingWindow: false };

const q = (sel) => document.querySelector(sel);
const text = (sel) => { const el = q(sel); return el ? el.textContent : null; };

async function renderGrid(grid, req) {
  putResult(biomarkerHeatmapSlot("nrs"), UID, settingsKey(gridSettingsFor(req, "nrs")), grid,
    { why: "wave 2 render test" });
  let status = null;
  const out = rtlRender(wrap(
    <BiomarkerHeatmapGrids participantUid={UID} requestParams={req} availableMetrics={METRICS}
      pageMetric="nrs" metricLabel="NRS (0–10)" onOpenInClosedLoop={() => {}}
      onStatus={(s) => { status = s; }} />,
  ));
  await waitFor(() => expect(q('[data-testid="pair-thumb"][data-channel="ZERO_THREE_RIGHT"]')).toBeTruthy());
  fireEvent.click(q('[data-testid="pair-thumb"][data-channel="ZERO_THREE_RIGHT"]'));
  await waitFor(() => expect(q('[data-testid="band-choice-table"]')).toBeTruthy());
  return { ...out, status: () => status };
}

beforeEach(() => {
  global.__plotlyReact = [];
  global.__plotlyOn = {};
  invalidateAll("wave 2 render test");
  SessionController.query.mockReset();
  SessionController.query.mockImplementation(() => Promise.resolve({ data: { boot_token: "boot-1" } }));
});


const CELL_FOR = { td: CELLS.td, psd: CELLS.psd, mixed: CELLS.default };

function answerCells() {
  SessionController.query.mockImplementation((url, body) => {
    if (body && body.BandTimeSweepCell === "1") {
      return Promise.resolve({ data: CELL_FOR[body.Source || "mixed"] });
    }
    return Promise.resolve({ data: { boot_token: "boot-1" } });
  });
}

/** Click (row, col) on one map, the way Plotly reports a click on the heat-map trace. */
function clickMap(divId, row, col) {
  const on = (global.__plotlyOn || {})[divId] || {};
  expect(typeof on.plotly_click).toBe("function");
  on.plotly_click({ points: [{ curveNumber: 0, pointNumber: [row, col] }] });
}

const cellCalls = () => SessionController.query.mock.calls.map((c) => c[1])
  .filter((b) => b && b.BandTimeSweepCell === "1");
const ROW_30S = GRID.band_time_sweep.ZERO_THREE_RIGHT.integration_seconds_requested.indexOf(30);
const COL_9P5 = GRID.band_time_sweep.ZERO_THREE_RIGHT.center_freqs_hz.indexOf(9.5);

describe("TD-only and PSD-only maps: a click opens that grid's own scatter", () => {
  it("the TD-only square R 0-3 9.5 Hz, 30 s: Source td sent, 73 pairs, the TD grid's r", async () => {
    answerCells();
    await renderGrid(GRID, REQ);
    clickMap("biomarker-heatmap-td", ROW_30S, COL_9P5);
    await waitFor(() => expect(text('[data-testid="scatter-headline"]')).toMatch(/n = 73$/));
    const sent = cellCalls().pop();
    expect(sent).toMatchObject({ Channel: "ZERO_THREE_RIGHT", BandCenterHz: 9.5, IntegrationSeconds: 30,
      Source: "td" });
    expect(text('[data-testid="scatter-headline"]')).toMatch(/^r = .0\.34, /);
    expect(text('[data-testid="pinned-title"]')).toMatch(/· 9\.5 Hz · .* of signal · TD only$/);
  });

  it("the PSD-only square: Source psd sent, 418 pairs, the PSD grid's r", async () => {
    answerCells();
    await renderGrid(GRID, REQ);
    clickMap("biomarker-heatmap-psd", ROW_30S, COL_9P5);
    await waitFor(() => expect(text('[data-testid="scatter-headline"]')).toMatch(/n = 418$/));
    expect(cellCalls().pop()).toMatchObject({ Source: "psd", BandCenterHz: 9.5, IntegrationSeconds: 30 });
    expect(text('[data-testid="scatter-headline"]')).toMatch(/^r = 0\.03, /);
    expect(text('[data-testid="pinned-title"]')).toMatch(/PSD only$/);
  });

  it("the mixed map still sends no Source and shows the mixed grid's 465 pairs", async () => {
    answerCells();
    await renderGrid(GRID, REQ);
    clickMap("biomarker-heatmap-correlation", ROW_30S, COL_9P5);
    await waitFor(() => expect(text('[data-testid="scatter-headline"]')).toMatch(/n = 465$/));
    expect("Source" in cellCalls().pop()).toBe(false);
    expect(text('[data-testid="pinned-title"]')).not.toMatch(/only$/);
  });

  it("the request and the cache key carry the source only for a source map", () => {
    const base = { participantUid: "u", requestParams: REQ, metric: "nrs", channel: "C", center: 9.5, seconds: 30 };
    expect("Source" in heatmapCellRequest(base)).toBe(false);
    expect(heatmapCellRequest({ ...base, source: "td" }).Source).toBe("td");
    const k = cellKey("u", "nrs", "s", "C", 9.5, 30);
    expect(k).toBe("u|nrs|s|C|9.5|30");                    // the mixed key as it always was
    expect(new Set([k, cellKey("u", "nrs", "s", "C", 9.5, 30, "td"),
      cellKey("u", "nrs", "s", "C", 9.5, 30, "psd")]).size).toBe(3);
  });
});
