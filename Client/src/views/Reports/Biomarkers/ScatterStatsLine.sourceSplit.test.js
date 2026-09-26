/**
 * P-19 (the PI, 2026-09-25): the TD / PSD line sits in the side panel ABOVE the scatter, as one line
 * of text, under the cell's own statistics; the hover is untouched. Rendered with a constructed grid
 * response and a loaded cell, since the page reaches this panel only after a click Plotly delivers.
 */
import "@testing-library/jest-dom";
import { render } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";
import theme from "assets/theme";
import { PlatformContextProvider } from "context";

import { ScatterStatsLine } from "./BiomarkerHeatmapGrids";

jest.mock("plotly.js-dist", () => ({ react: () => Promise.resolve(), purge: () => {} }));
jest.mock("graphing-utility/Plotly", () => ({ PlotlyRenderManager: class {} }));
jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn() } }));

const wrap = (ui) => (
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>
);

const SW = {
  center_freqs_hz: [24.5],
  integration_seconds_delivered: [30],
  correlation_grid: [[-0.04]], p_grid: [[0.61]], n_grid: [[162]],
  best_correlation_rows: [],
  correlation_by_recording_source: {
    available: true, min_reports: 8,
    td: { r_grid: [[-0.0512]], n_grid: [[76]], r_low_grid: [[-0.2311]], r_high_grid: [[0.1204]] },
    psd: { r_grid: [[-0.3698]], n_grid: [[86]], r_low_grid: [[-0.5611]], r_high_grid: [[-0.1893]] },
  },
};
const CELL = { loading: false, points: [{ pain: 7, power: 100, label: "high" }] };
const PINNED = { row: 0, col: 0, channel: "ONE_THREE_LEFT", center: 24.5, seconds: 30 };

test("the line is printed under the cell's own statistics, in the PI's words", () => {
  const { container, getByTestId } = render(
    wrap(<ScatterStatsLine cell={CELL} pinnedCell={PINNED} sw={SW} />));
  const line = getByTestId("source-split-line");
  expect(line.textContent).toBe(
    "TD values: r \u22120.05 (\u22120.23 to +0.12), 76 reports \u00b7 PSD values: r \u22120.37 (\u22120.56 to \u22120.19), 86 reports");
  const text = container.textContent;
  expect(text.indexOf("Pearson r = ")).toBeLessThan(text.indexOf("TD values:"));
});

test("no line for a stored grid built before the split", () => {
  const { queryByTestId } = render(
    wrap(<ScatterStatsLine cell={CELL} pinnedCell={PINNED}
      sw={{ ...SW, correlation_by_recording_source: undefined }} />));
  expect(queryByTestId("source-split-line")).toBeNull();
});
