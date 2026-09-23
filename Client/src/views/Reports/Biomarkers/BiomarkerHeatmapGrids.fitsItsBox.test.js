/**
 * The two heat maps are drawn at the width of the box they sit in, not at a fixed 750 pixels.
 *
 * WHY (the PI, 2026-09-22, found while watching the page live). Each heat map's box measured 527
 * pixels on the page, but the figure was drawn 750 wide, so the extra 223 pixels spilled to the
 * right. With no cell picked they spilled into the empty half of the card and nothing looked wrong;
 * once a cell was picked, the side panel covered them -- the columns from about 25 Hz up, including
 * the 24.5-27.5 Hz band family this patient's left lead is watched on, disappeared, and a hover
 * label near there was cut off mid-word ("75 ratings (about 66 indepen").
 *
 * The cause is the fixed `width` in the figure's layout: with a fixed width, Plotly's responsive
 * resize does not shrink the figure to its box. The side panels already fill their boxes (measured
 * 300 of 300 on the same page); only the heat maps overflowed. So the layout no longer names a
 * width, and 750 stays only as the box's own upper limit.
 */
import "@testing-library/jest-dom";
import { render as rtlRender, screen, waitFor } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";

import theme from "assets/theme";
import { PlatformContextProvider } from "context";

import { invalidateAll, putResult, settingsKey } from "database/resultCache";
import { biomarkerHeatmapSlot } from "views/Reports/moduleCacheKeys";

import BiomarkerHeatmapGrids from "./BiomarkerHeatmapGrids";
import sweep from "./__fixtures__/rcs08_band_sweep.json";

jest.mock("plotly.js-dist", () => {
  // Plain functions, not jest.fn: react-scripts runs jest with `resetMocks: true`, which would strip
  // an implementation before each test. The calls are kept on `global` so the test can read them.
  const noop = () => {};
  const react = (id, traces, layout, config) => {
    const el = typeof id === "string" ? global.document.getElementById(id) : id;
    if (el) { el.on = noop; el.removeAllListeners = noop; el.data = []; }
    (global.__plotlyReact = global.__plotlyReact || []).push({ id, layout, config });
    return Promise.resolve();
  };
  return { react, purge: noop, restyle: noop, relayout: noop, newPlot: noop };
});
jest.mock("graphing-utility/Plotly", () => ({
  // Records every layout each figure is given, by the <div> it draws into.
  PlotlyRenderManager: class {
    constructor(divId) { this.divId = divId; this.traces = []; this.layout = {}; }
    subplots() {} clearData() {} render() {} setXlabel() {} setYlabel() {} purge() {}
    setLayoutProps(props) {
      Object.assign(this.layout, props);
      (global.__layoutCalls = global.__layoutCalls || []).push({ divId: this.divId, props });
    }
  },
}));
jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn() } }));
// eslint-disable-next-line import/first
import { SessionController } from "database/session-control";

const UID = "2e3c75c00d7f4f37b53a048d195f11da";
const METRIC = "nrs";
const REQ = { MatchToleranceMin: 60, MatchDirection: "pro_first", LabelStrategy: "tertile" };
const METRICS = [{ key: "nrs", label: "NRS (0–10)" }];
const HEATMAPS = ["biomarker-heatmap-correlation", "biomarker-heatmap-auc"];

beforeEach(() => {
  global.__layoutCalls = [];
  global.__plotlyReact = [];
  invalidateAll("fits-its-box test setup");
  SessionController.query.mockReset();
  SessionController.query.mockImplementation(() => Promise.resolve({ data: { boot_token: "boot-1" } }));
  putResult(biomarkerHeatmapSlot(METRIC), UID, settingsKey({ ...REQ, SweepMetric: METRIC }), sweep,
    { why: "fits-its-box test" });
});

async function renderGrid() {
  rtlRender(
    <ThemeProvider theme={theme}>
      <PlatformContextProvider initialStates={{ darkMode: false }}>
        <BiomarkerHeatmapGrids participantUid={UID} requestParams={REQ} availableMetrics={METRICS}
          pageMetric={METRIC} metricLabel="NRS (0–10)" onOpenInClosedLoop={() => {}} />
      </PlatformContextProvider>
    </ThemeProvider>,
  );
  await waitFor(() => expect(screen.getByText(/How to read this/)).toBeInTheDocument());
  await waitFor(() => expect(global.__layoutCalls.some((c) => HEATMAPS.includes(c.divId))).toBe(true));
}

describe("the heat maps fit the box they sit in", () => {
  it("never fixes the figure's width, so Plotly draws it at its box's width", async () => {
    await renderGrid();
    const calls = global.__layoutCalls.filter((c) => HEATMAPS.includes(c.divId));
    expect(calls.length).toBeGreaterThan(0);
    for (const c of calls) {
      expect(c.props).not.toHaveProperty("width");
      expect(c.props.height).toBeGreaterThan(0);          // the shared height is unchanged
    }
    const drawn = global.__plotlyReact.filter((c) => HEATMAPS.includes(c.id));
    expect(drawn.length).toBeGreaterThan(0);
    for (const d of drawn) {
      expect(d.layout.width).toBeUndefined();
      expect(d.config.responsive).toBe(true);             // Plotly keeps it fitted on resize
    }
  });

  it("keeps 750 pixels as the box's upper limit, so a wide screen draws it no larger than before", async () => {
    await renderGrid();
    for (const id of HEATMAPS) {
      const el = document.getElementById(id);
      if (el) expect(el.style.maxWidth).toBe("750px");
    }
    expect(HEATMAPS.some((id) => document.getElementById(id))).toBe(true);
  });
});
