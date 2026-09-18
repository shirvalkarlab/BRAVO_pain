import React from "react";
import { act, fireEvent, render, screen } from "@testing-library/react";
import BiomarkerHeatmapGrids from "./BiomarkerHeatmapGrids";

let mockOptions;
let mockData;
let mockLoading;
const mockQuery = jest.fn();
const mockRecompute = jest.fn();
jest.mock("./queryAnalysis", () => ({ useAnalysisQuery: () => mockQuery }));
jest.mock("database/useCachedResult", () => ({ useCachedResult: (options) => {
  mockOptions = options;
  return { data: mockData, loading: mockLoading, err: null, recompute: mockRecompute };
} }));
jest.mock("plotly.js-dist", () => ({ react: jest.fn(), purge: jest.fn() }));
jest.mock("graphing-utility/Plotly", () => ({ PlotlyRenderManager: jest.fn() }));
jest.mock("components/MDBox", () => ({ children }) => <div>{children}</div>);
jest.mock("components/MDTypography", () => ({ children }) => <span>{children}</span>);
jest.mock("components/MDButton", () => ({ children, onClick, disabled }) =>
  <button onClick={onClick} disabled={disabled}>{children}</button>);
jest.mock("@mui/material", () => ({
  Card: ({ children }) => <div>{children}</div>,
  Grid: ({ children }) => <div>{children}</div>,
  Collapse: ({ children, in: open }) => open ? <div>{children}</div> : null,
  CircularProgress: () => <span>Loading</span>,
  IconButton: ({ children, onClick }) => <button onClick={onClick}>{children}</button>,
  Checkbox: ({ checked, disabled, onChange }) =>
    <input type="checkbox" checked={checked} disabled={disabled} onChange={onChange} />,
  FormControlLabel: ({ control, label }) => <label>{control}{label}</label>,
}));

const props = { participantUid: "participant", requestParams: { LabelMetric: "left_leg_vas" },
  pageMetric: "left_leg_vas" };
beforeEach(() => {
  mockData = null;
  mockLoading = false;
  mockQuery.mockReset().mockResolvedValue({ data: { band_time_sweep: {} } });
  mockRecompute.mockReset();
});

test("stability defaults off in both cache identities and does not start computation", () => {
  render(<BiomarkerHeatmapGrids {...props} requestParams={{ IncludeCrossSettingStability: true }} />);
  expect(screen.getByRole("checkbox", { name: "Include cross-setting stability" }).checked).toBe(false);
  expect(mockOptions.settings.IncludeCrossSettingStability).toBe(false);
  expect(mockOptions.identity).toBe(mockOptions.settings);
  expect(mockOptions.autoFetch).toBe(false);
  expect(mockQuery).not.toHaveBeenCalled();
});

test("changing stability separates cached results and sends the boolean only on explicit computation", async () => {
  render(<BiomarkerHeatmapGrids {...props} />);
  const originalSettings = mockOptions.settings;
  const checkbox = screen.getByRole("checkbox", { name: "Include cross-setting stability" });
  fireEvent.click(checkbox);
  expect(mockOptions.settings).not.toBe(originalSettings);
  expect(mockOptions.settings.IncludeCrossSettingStability).toBe(true);
  expect(mockOptions.identity.IncludeCrossSettingStability).toBe(true);
  expect(mockQuery).not.toHaveBeenCalled();
  expect(mockRecompute).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Run band grid" }));
  expect(mockRecompute).toHaveBeenCalledTimes(1);
  await act(async () => { await mockOptions.fetcher(); });
  expect(mockQuery).toHaveBeenLastCalledWith("/api/queryBiomarkerAnalysis", {
    ParticipantId: "participant", LabelMetric: "left_leg_vas", SweepMetric: "left_leg_vas",
    BandTimeSweep: "1", IncludeCrossSettingStability: true,
  });
  fireEvent.click(checkbox);
  expect(mockOptions.settings.IncludeCrossSettingStability).toBe(false);
  expect(mockQuery).toHaveBeenCalledTimes(1);
});

test("changing stability clears the prior grid until a matching result is available", () => {
  mockData = { message: "Prior grid result", band_time_sweep: {} };
  render(<BiomarkerHeatmapGrids {...props} />);
  expect(screen.getByText("Prior grid result")).toBeTruthy();
  fireEvent.click(screen.getByRole("checkbox", { name: "Include cross-setting stability" }));
  expect(screen.queryByText("Prior grid result")).toBeNull();
  expect(mockQuery).not.toHaveBeenCalled();
});

test("running grids hold stability settings fixed until the current request finishes", () => {
  mockLoading = true;
  render(<BiomarkerHeatmapGrids {...props} />);
  expect(screen.getByRole("checkbox", { name: "Include cross-setting stability" }).disabled).toBe(true);
  expect(screen.getByRole("button", { name: "Run band grid" }).disabled).toBe(true);
});
