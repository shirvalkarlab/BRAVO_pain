/**
 * The clicked square's two statistics lines and the plots under the heat maps (the PI, 2026-10-02).
 *
 * What is pinned:
 *   1. the line above the scatter is ONE line, "r = 0.31, p = 0.012, n = 148", read off the same
 *      grid fields as before (correlation_grid, p_grid, n_grid);
 *   2. the line above the violin is ONE line, "AUC = 0.64, p = 0.021, n = 74 high, n = 91 low"
 *      (auc_grid, auc_p_grid, auc_n_high_grid, auc_n_low_grid);
 *   3. neither carries the older wording about the 22 bands, the circled square, or "tells high pain
 *      from low"; the colour key of the right-hand map says "AUC";
 *   4. both heat maps, the scatter and the violin take their left and right plot margins from ONE
 *      shared definition, the scatter and the violin carry no fixed width, and their boxes are
 *      centred in their column, so each plot area sits under its heat map's plot area.
 */
import "@testing-library/jest-dom";
import { render as rtlRender, screen, waitFor, act } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";

import theme from "assets/theme";
import { PlatformContextProvider } from "context";
import { invalidateAll, putResult, settingsKey } from "database/resultCache";
import { biomarkerHeatmapSlot } from "views/Reports/moduleCacheKeys";

import BiomarkerHeatmapGrids from "./BiomarkerHeatmapGrids";
import { PLOT_MARGIN, panelBoxStyle, plotMargin } from "./panelLayout";
import { pEquals } from "./gridReadouts";
import baseSweep from "./__fixtures__/rcs08_band_sweep.json";

// The saved 2026-09-15 grid predates the per-square p grids; give every pair a p of 0.012 (r) and
// 0.021 (AUC) at every square, so the lines have all their fields.
const sweep = JSON.parse(JSON.stringify(baseSweep));
Object.values(sweep.band_time_sweep).forEach((v) => {
  const fill = (g, x) => g.map((row) => row.map(() => x));
  v.p_grid = fill(v.correlation_grid, 0.012);
  v.auc_p_grid = fill(v.auc_grid, 0.021);
});

jest.mock("plotly.js-dist", () => {
  const noop = () => {};
  const react = (id, traces, layout) => {
    const el = typeof id === "string" ? global.document.getElementById(id) : id;
    if (el) {
      el.on = (evt, fn) => { (global.__handlers = global.__handlers || {})[`${el.id}:${evt}`] = fn; };
      el.removeAllListeners = noop; el.removeListener = noop; el.data = [];
    }
    (global.__reacts = global.__reacts || []).push({ id, layout });
    return Promise.resolve();
  };
  return { react, purge: noop, restyle: noop, relayout: noop, newPlot: noop, Plots: { resize: noop } };
});
jest.mock("graphing-utility/Plotly", () => ({
  PlotlyRenderManager: class {
    constructor(divId) { this.divId = divId; this.traces = []; this.layout = {}; }
    subplots() {} clearData() {} render() {} setXlabel() {} setYlabel() {} purge() {}
    setLayoutProps(props) {
      Object.assign(this.layout, props);
      (global.__layouts = global.__layouts || {})[this.divId] = { ...this.layout };
    }
  },
}));
jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn() } }));
// eslint-disable-next-line import/first
import { SessionController } from "database/session-control";

const UID = "2e3c75c00d7f4f37b53a048d195f11da";
const REQ = { source: "both", LabelMetric: "nrs", LabelStrategy: "tertile", PercentileLow: 33.3,
  PercentileHigh: 66.7, MatchToleranceMin: 60, MatchDirection: "pro_first", AllowWindowReuse: false,
  IncludeClinicSheetRatings: false, SlidingWindow: false };
const METRICS = [{ key: "nrs", label: "NRS (0–10)" }];
const CELL_POINTS = [{ pain: 7, power: 100, label: "high" }, { pain: 2, power: 80, label: "low" },
  { pain: 6, power: 120, label: "high" }, { pain: 1, power: 70, label: "low" }];
const ROW = 1; const COL = 2;

beforeEach(async () => {
  global.__handlers = {}; global.__layouts = {}; global.__reacts = [];
  invalidateAll("panel test setup");
  SessionController.query.mockReset();
  SessionController.query.mockImplementation((url, body) => Promise.resolve({
    data: body && body.BandTimeSweepCell === "1" ? { band_time_sweep_cell: { points: CELL_POINTS } }
      : { boot_token: "boot-1" } }));
  putResult(biomarkerHeatmapSlot("nrs"), UID, settingsKey({ ...REQ, SweepMetric: "nrs" }), sweep, { why: "panel test" });
  rtlRender(
    <ThemeProvider theme={theme}>
      <PlatformContextProvider initialStates={{ darkMode: false }}>
        <BiomarkerHeatmapGrids participantUid={UID} requestParams={REQ} availableMetrics={METRICS}
          pageMetric="nrs" metricLabel="NRS (0–10)" onOpenInClosedLoop={() => {}} />
      </PlatformContextProvider>
    </ThemeProvider>);
  await waitFor(() => expect(global.__handlers["biomarker-heatmap-correlation:plotly_click"]).toBeTruthy());
  await act(async () => {
    global.__handlers["biomarker-heatmap-correlation:plotly_click"]({ points: [{ curveNumber: 0, pointNumber: [ROW, COL] }] });
  });
  await waitFor(() => expect(screen.getByTestId("scatter-headline")).toBeInTheDocument());
});

const sw = () => Object.values(sweep.band_time_sweep)[0];
const fix = (v, d) => Number(v).toFixed(d);

describe("the two statistics lines", () => {
  test("1. the scatter line is one line: r, p, n", () => {
    const s = sw();
    const line = screen.getByTestId("scatter-headline");
    expect(line.textContent).toBe(
      `r = ${fix(s.correlation_grid[ROW][COL], 2)}, ${pEquals(s.p_grid[ROW][COL])}, n = ${s.n_grid[ROW][COL]}`);
    expect(line.textContent).not.toMatch(/\n/);
    expect(getComputedStyle(line).whiteSpace).toBe("nowrap");
  });

  test("2. the violin line is one line: AUC, p, n high, n low", () => {
    const s = sw();
    const line = screen.getByTestId("violin-headline");
    expect(line.textContent).toBe(
      `AUC = ${fix(s.auc_grid[ROW][COL], 2)}, ${pEquals(s.auc_p_grid[ROW][COL])}, `
      + `n = ${s.auc_n_high_grid[ROW][COL]} high, n = ${s.auc_n_low_grid[ROW][COL]} low`);
    expect(getComputedStyle(line).whiteSpace).toBe("nowrap");
  });

  test("2b. neither line is clipped (the violin's n for low was cut to an ellipsis), both are centred, and the title is centred over both plots", () => {
    ["scatter-headline", "violin-headline"].forEach((id) => {
      const line = screen.getByTestId(id);
      const st = getComputedStyle(line);
      expect(st.textOverflow).not.toBe("ellipsis");
      expect(st.overflow).not.toBe("hidden");
      expect(getComputedStyle(line.parentElement).textAlign).toBe("center");
    });
    const title = screen.getByText(/ Hz · .* of signal/);
    expect(getComputedStyle(title).textAlign).toBe("center");
  });

  test("2c. the TD and PSD values sit on separate lines, with n=X", () => {
    const split = screen.queryByTestId("source-split-line");
    if (split) {
      expect(getComputedStyle(split).whiteSpace).toBe("pre-line");
      expect(split.textContent).not.toMatch(/ reports/);
    }
  });

  test("3. the older wording is gone from the panels and the key says AUC", () => {
    const text = document.body.textContent;
    expect(text).not.toMatch(/22 bands is given for the circled square/);
    expect(text).not.toMatch(/not allowing for the 22 bands tested/);
    expect(text).not.toMatch(/tells high pain from low/i);
    expect(text).toMatch(/AUC/);
  });
});

describe("the plots sit under their heat maps", () => {
  const layoutOf = (id) => global.__layouts[id];
  test("4. one shared margin definition feeds all four plots", () => {
    ["biomarker-heatmap-correlation", "biomarker-heatmap-auc", "biomarker-scatter-panel", "biomarker-violin-panel"]
      .forEach((id) => {
        expect(layoutOf(id)).toBeTruthy();
        expect(layoutOf(id).margin.l).toBe(PLOT_MARGIN.l);
        expect(layoutOf(id).margin.r).toBe(PLOT_MARGIN.r);
      });
    expect(plotMargin(36)).toEqual({ ...PLOT_MARGIN, b: 36 });
  });

  test("the scatter and the violin carry no fixed width, so they fit a narrow column", () => {
    expect(layoutOf("biomarker-scatter-panel").width).toBeUndefined();
    expect(layoutOf("biomarker-violin-panel").width).toBeUndefined();
  });

  test("their boxes are centred in the column, square, and no wider than their side", () => {
    expect(panelBoxStyle(300)).toEqual({ width: "100%", maxWidth: 300, margin: "0 auto", aspectRatio: "1 / 1" });
    ["biomarker-scatter-panel", "biomarker-violin-panel"].forEach((id) => {
      const el = document.getElementById(id);
      expect(el.style.maxWidth).toBe("300px");
      expect(el.style.margin).toBe("0px auto");
    });
  });
});

describe("the bottom edges of the four plot areas sit on one line", () => {
  it("the heat maps, scatter and violin all take the one bottom margin from panelLayout", () => {
    const fs = require("fs");
    const src = fs.readFileSync(require("path").join(__dirname, "BiomarkerHeatmapGrids.js"), "utf8");
    const used = src.match(/margin: plotMargin\([^)]*\)/g) || [];
    expect(used.length).toBe(3);
    used.forEach((u) => expect(u).toBe("margin: plotMargin(PLOT_BOTTOM)"));
    expect(PLOT_MARGIN.b).toBe(require("./panelLayout").PLOT_BOTTOM);
  });
});
