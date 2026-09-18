import React from "react";
import { render, screen } from "@testing-library/react";
import Plotly from "plotly.js-dist";
import RecordCountBars, { isNumericValue, recordAvailability } from "./RecordCountBars";

jest.mock("plotly.js-dist", () => ({ react: jest.fn(), purge: jest.fn() }));
jest.mock("components/MDBox", () => ({ children }) => <div>{children}</div>);
jest.mock("components/MDTypography", () => ({ children }) => <span>{children}</span>);
jest.mock("@mui/material/Card", () => ({ children }) => <div>{children}</div>);

const form = { page: { questions: [
  { text: "Pain", type: "score" }, { text: "Function", type: "redcapForm" },
  { text: "Total", type: "cumulativeScore", list: ["Pain", "Function"] },
  { text: "Time", type: "score" }, { text: "Comment", type: "text" },
] } };
const reports = [
  { Result: { page: [0, " 4 "] } }, { Result: { page: [2, "missing"] } },
  { Result: { page: [3, null] } }, { Result: { page: [1, 5] } },
];

test.each([0, -1, 2.5, "0", " -3.2 "])("counts numeric values including zero: %s", value => {
  expect(isNumericValue(value)).toBe(true);
});
test.each([null, undefined, "", " ", "missing", "2mg", NaN, Infinity, true, {}, []])(
  "rejects missing or nonnumeric value: %s", value => expect(isNumericValue(value)).toBe(false));

test("preserves metric order and requires every component for derived scores", () => {
  expect(recordAvailability(reports, form)).toEqual({ total: 4, metrics: [
    { label: "Pain", count: 4 }, { label: "Function", count: 2 }, { label: "Total", count: 2 },
  ] });
  expect(recordAvailability([null, {}, { Result: {} }, { Result: { page: {} } }], form).metrics
    .map(metric => metric.count)).toEqual([0, 0, 0]);
});
test("handles incomplete forms and never infers a missing derived component", () => {
  expect(recordAvailability(null, null)).toEqual({ total: 0, metrics: [] });
  expect(recordAvailability([], { absent: null, empty: {} })).toEqual({ total: 0, metrics: [] });
  const incomplete = { page: { questions: [
    { text: "Missing component", type: "cumulativeScore", list: ["unknown"] },
    { text: "Empty list", type: "cumulativeScore", list: [] },
    { text: "No list", type: "cumulativeScore" },
  ] } };
  expect(recordAvailability(reports, incomplete).metrics.map(metric => metric.count)).toEqual([0, 0, 0]);
});
test("renders correct denominators, sparse coverage, empty state and cleans up the original node", () => {
  Plotly.react.mockClear(); Plotly.purge.mockClear();
  const { rerender, unmount } = render(<RecordCountBars dataToRender={reports} form={form}/>);
  expect(screen.getByText(/counts do not indicate independent samples/)).toBeTruthy();
  const [node, traces, layout] = Plotly.react.mock.calls[0];
  expect(traces[0].y).toEqual([4, 2, 2]);
  expect(traces[0].customdata).toEqual([1, .5, .5]);
  expect(traces[0].marker.color).toEqual(["#1A7F7A", "#3DA5A0", "#3DA5A0"]);
  expect(layout.shapes[0].y0).toBe(4);
  rerender(<RecordCountBars dataToRender={[{}]} form={form}/>);
  expect(Plotly.react.mock.calls[1][1][0].marker.color).toEqual(["#E8A13B", "#E8A13B", "#E8A13B"]);
  rerender(<RecordCountBars dataToRender={[]} form={form}/>);
  const [, empty, emptyLayout] = Plotly.react.mock.calls[2];
  expect(empty[0].text).toEqual(["0", "0", "0"]);
  expect(empty[0].customdata).toEqual([0, 0, 0]);
  expect(emptyLayout.shapes).toEqual([]);
  expect(emptyLayout.annotations).toEqual([]);
  unmount(); expect(Plotly.purge).toHaveBeenLastCalledWith(node);
});
