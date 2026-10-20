import React from "react";
import { render, waitFor } from "@testing-library/react";
import GenericTimeline from "./GenericTimeline";
const mockPlot = jest.fn();
const mockScatter = jest.fn();
const mockYlabel = jest.fn();
jest.mock("context", () => ({ usePlatformContext: () => [{ language: "en" }, jest.fn()] }));
jest.mock("components/MDBox", () => ({ children, id }) => <div id={id}>{children}</div>);
jest.mock("components/MDTypography", () => ({ children }) => <div>{children}</div>);
jest.mock("components/MDButton", () => ({ children }) => <button>{children}</button>);
jest.mock("@mui/material", () => {
  const Box = ({ children }) => <div>{children}</div>;
  return { Card: Box, Menu: Box, MenuItem: Box, Dialog: () => null, DialogContent: Box,
    Grid: Box, IconButton: Box, Popover: Box, TextField: Box, DialogActions: Box };
});
jest.mock("@mui/x-date-pickers/AdapterMoment", () => ({ AdapterMoment: function Adapter() {} }));
jest.mock("@mui/x-date-pickers/LocalizationProvider", () => ({ LocalizationProvider: () => null }));
jest.mock("@mui/x-date-pickers/DatePicker", () => ({ DatePicker: () => null }));
jest.mock("@mui/x-date-pickers", () => ({ TimePicker: () => null }));
jest.mock("react-resize-detector", () => ({ useResizeDetector: () => ({ ref: null }) }));
jest.mock("graphing-utility/Plotly", () => ({ PlotlyRenderManager: function PlotlyRenderManager() { return ({
  fresh: true, traces: [], subplots: (n) => Array.from({length:n}, (_, i) => ({id:i})),
  setYlabel: (...args) => mockYlabel(...args), setSubtitle: jest.fn(), setSubplotId: jest.fn(),
  setLegend: jest.fn(), setLayoutProps: jest.fn(), getAxes: (name) => name ? {id:name} : [],
  setYlim: jest.fn(), setScaleType: jest.fn(), render: jest.fn(),
  plot: (...args) => mockPlot(...args), scatter: (...args) => mockScatter(...args)
}); } }));
beforeEach(() => jest.clearAllMocks());
test("native timeline sends zero intervals, missing gaps, final point and mA label to renderer", async () => {
  render(<GenericTimeline data={[{ AnalysisType:"CustomizedTimelineData", Time:[10,20,30], Duration:[10,10,null],
    ChannelNames:["stim"], ChannelUnits:["mA"], Data:[[0,null,2]] }]}
    availableChannels={{active:["stim"]}} annotations={[]} updateColor={jest.fn()} figureTitle="synthetic" />);
  await waitFor(() => expect(mockPlot).toHaveBeenCalled());
  const [x,y,options]=mockPlot.mock.calls.at(-1);
  expect(x.map(t=>t===null?null:t.getTime())).toEqual([10000,20000,null]);
  expect(y).toEqual([0,0,null]);
  expect(options.connectgaps).toBe(false);
  expect(mockScatter.mock.calls.at(-1)[1]).toEqual([2]);
  expect(mockYlabel.mock.calls.some(([label])=>label==="mA")).toBe(true);
});
test("survey zero reaches the plotted points", async () => {
  render(<GenericTimeline data={[{ AnalysisType:"CustomizedSurveyData", Time:[10,20],
    ChannelNames:["survey"], ChannelUnits:[""], Data:[[0,null]] }]}
    availableChannels={{active:["survey"]}} annotations={[]} updateColor={jest.fn()} figureTitle="synthetic" />);
  await waitFor(() => expect(mockScatter).toHaveBeenCalled());
  expect(mockScatter.mock.calls.at(-1)[1]).toEqual([0]);
});
