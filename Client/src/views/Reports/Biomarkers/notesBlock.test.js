/**
 * The notes under the two heat maps, in minimal words and body-size type (the PI, 2026-10-02): one
 * short line per fact, the counts computed from the grid response, never typed in.
 *
 * What is pinned:
 *   1. each of the six lines renders with its numbers filled in from the response;
 *   2. every line is a body-size (14 px) line, not a caption-size one (12 px).
 */
import "@testing-library/jest-dom";
import { render as rtlRender, screen, waitFor, within } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";

import theme from "assets/theme";
import { PlatformContextProvider } from "context";
import { TYPE } from "assets/theme/base/tokens";
import { invalidateAll, putResult, settingsKey } from "database/resultCache";
import { biomarkerHeatmapSlot } from "views/Reports/moduleCacheKeys";

import BiomarkerHeatmapGrids from "./BiomarkerHeatmapGrids";
import baseSweep from "./__fixtures__/rcs08_band_sweep.json";

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

const UID = "2e3c75c00d7f4f37b53a048d195f11da";
const REQ = { source: "both", LabelMetric: "nrs", LabelStrategy: "tertile", PercentileLow: 33.3,
  PercentileHigh: 66.7, MatchToleranceMin: 60, MatchDirection: "pro_first", AllowWindowReuse: false,
  IncludeClinicSheetRatings: false, SlidingWindow: false };

// A response with every note present: some reports read from PSD, the device's ranges, the clinic
// sheets off, and one best row carrying a cross-setting answer (so the circle key is drawn).
const sweep = JSON.parse(JSON.stringify(baseSweep));
Object.values(sweep.band_time_sweep).forEach((v) => {
  v.n_pain_reports_from_device_spectrum = 104;
  v.device_spectrum_total_grid = v.correlation_grid.map((row) => row.map(() => 139));
  v.device_timing_ranges = { averaging_s: [0, 30], onset_dual_s: [0, 30] };
  v.integration_seconds_delivered = [3, 6, 9, 15, 21, 24, 30, 45, 60];
  v.clinic_sheet_ratings = { included: false, n_added: 0 };
  if (v.best_correlation_rows && v.best_correlation_rows[0]) {
    v.best_correlation_rows[0].cross_setting_stability = { answer: "behaves the same" };
  }
});
sweep.device_timing_ranges = { averaging_s: [0, 30], onset_dual_s: [0, 30] };

beforeEach(async () => {
  invalidateAll("notes test setup");
  SessionController.query.mockReset();
  SessionController.query.mockImplementation(() => Promise.resolve({ data: { boot_token: "boot-1" } }));
  putResult(biomarkerHeatmapSlot("nrs"), UID, settingsKey({ ...REQ, SweepMetric: "nrs" }), sweep, { why: "notes test" });
  rtlRender(
    <ThemeProvider theme={theme}>
      <PlatformContextProvider initialStates={{ darkMode: false }}>
        <BiomarkerHeatmapGrids participantUid={UID} requestParams={REQ}
          availableMetrics={[{ key: "nrs", label: "NRS (0–10)" }]} pageMetric="nrs"
          metricLabel="NRS (0–10)" onOpenInClosedLoop={() => {}} />
      </PlatformContextProvider>
    </ThemeProvider>);
  await waitFor(() => expect(screen.getByText(/Reading guide/)).toBeInTheDocument());
});

const SIX = [
  "104 of 139 matched reports (75%) had no TD in match window; read from PSD",
  "Match window defined under \"Adjust matching parameters\"",
  "Heat maps use home pain surveys only; clinic titration sessions toggled off",
  "Rows ≤30 s: device averaging window (0–30 s on tablet)",
  "*Rows 45 s–1 min: one averaging window + onset hold (each ≤30 s); no device setting averages this long. 45 s and 1 min rows need 2 PSDs (ceil(window/30 s))",
  "Circle: ✓ band tracks pain equally at every stimulation setting; ✕ differently; ? unknown",
];

test("1. each of the six note lines renders, the counts filled in from the response", () => {
  const items = screen.getAllByRole("listitem").map((li) => li.textContent);
  SIX.forEach((line) => expect(items).toContain(line));
});

test("2. the notes are body-size type, one bullet per line", () => {
  SIX.forEach((line) => {
    const li = screen.getAllByRole("listitem").find((x) => x.textContent === line);
    expect(li).toBeTruthy();
    expect(getComputedStyle(li).fontSize).toBe(`${TYPE.body.fontSize}px`);
    expect(getComputedStyle(li).lineHeight).toBe(TYPE.body.lineHeight);
  });
  expect(TYPE.body.fontSize).toBeGreaterThan(TYPE.caption.fontSize);
});
