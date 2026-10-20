import "@testing-library/jest-dom";
import { render, screen, waitFor, fireEvent, act } from "@testing-library/react";
import { wrap } from "testUtils/render";
import { invalidateAll } from "database/resultCache";
import { biomarkerHeatmapSlot, recomputeSlots } from "views/Reports/moduleCacheKeys";
import BiomarkerHeatmapGrids from "./BiomarkerHeatmapGrids";
import sweep from "./__fixtures__/synthetic_band_sweep.json";

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


const UID = "synthetic-error-recovery";
const REQ = { MatchToleranceMin: 60, MatchDirection: "pro_first", LabelStrategy: "tertile" };
const gridCalls = () => SessionController.query.mock.calls.filter(([url, body]) =>
  url === "/api/queryBiomarkerAnalysis" && body.BandTimeSweep === "1");
function Page() {
  return <>
    {/* Same cache-slot bridge used by the page's existing top Recompute control. */}
    <button onClick={() => recomputeSlots(UID, [biomarkerHeatmapSlot("nrs")])}>Recompute</button>
    <BiomarkerHeatmapGrids participantUid={UID} requestParams={REQ}
      availableMetrics={[{key: "nrs", label: "NRS"}]} pageMetric="nrs" metricLabel="NRS"/>
  </>;
}
let response;
beforeEach(() => {
  invalidateAll("error recovery test");
  SessionController.query.mockReset();
  SessionController.query.mockImplementation((url, body) =>
    url === "/api/queryBiomarkerAnalysis" && body.BandTimeSweep === "1"
      ? response() : Promise.resolve({data: {boot_token: "recovery-test"}}));
});

test("a failed initial request stops claiming to compute; the existing Recompute bridge retries once and clears the error", async () => {
  response = () => Promise.reject(new Error("Network Error"));
  render(wrap(<Page/>));
  expect(await screen.findByRole("alert")).toHaveTextContent("Network Error");
  expect(screen.getByRole("alert")).toHaveTextContent("press Recompute at the top of the page");
  expect(screen.getByRole("alert")).toHaveTextContent("No heat map is available from this request");
  expect(screen.queryByText("Computing the calibrated grid…")).not.toBeInTheDocument();
  expect(gridCalls()).toHaveLength(1);
  let finish;
  response = () => new Promise((resolve) => { finish = resolve; });
  fireEvent.click(screen.getByRole("button", {name: "Recompute"}));
  await waitFor(() => expect(gridCalls()).toHaveLength(2));
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(screen.getByText("Computing the calibrated grid…")).toBeVisible();
  await act(async () => finish({data: sweep}));
  expect(await screen.findByTestId("heatmap-rows")).toBeVisible();
  expect(screen.queryByText("Computing the calibrated grid…")).not.toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(gridCalls()).toHaveLength(2);
});

test("failed refresh preserves the last completed maps with an explicit warning, then can recover", async () => {
  response = () => Promise.resolve({data: sweep});
  render(wrap(<Page/>));
  expect(await screen.findByTestId("heatmap-rows")).toBeVisible();
  response = () => Promise.reject(new Error("Network Error"));
  fireEvent.click(screen.getByRole("button", {name: "Recompute"}));
  expect(await screen.findByRole("alert")).toHaveTextContent("last completed result");
  expect(screen.getByTestId("heatmap-rows")).toBeVisible();
  expect(screen.queryByText("Computing the calibrated grid…")).not.toBeInTheDocument();
  response = () => Promise.resolve({data: sweep});
  fireEvent.click(screen.getByRole("button", {name: "Recompute"}));
  await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
  await waitFor(() => expect(gridCalls()).toHaveLength(3));
  expect(screen.getByTestId("heatmap-rows")).toBeVisible();
});
