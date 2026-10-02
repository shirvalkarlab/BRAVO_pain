/**
 * Two page speed-ups on the Closed-Loop page (speed-up items C5 and C6, 2026-10-02), each read off
 * the whole page rendered against RCS08 fixtures, with every request answered by a stub.
 *
 * C5. The two figures that stay mounted inside the closed "Background" fold (how band power moves
 *     with current, measured three ways; the simulated closed loop) were drawn on page load for a
 *     fold nobody had opened. They are now drawn the first time the fold is opened. "Sign and
 *     print" (and "Export JSON") still put both on the record when the fold was never opened: the
 *     record asks the page to draw them first, then takes its pictures.
 * C6. The "Band selection" grid (22 rows of coloured cells) was rebuilt on every re-render of the page,
 *     a dozen or more times while the page loads, although nothing it shows had changed. It now
 *     re-renders only when one of its inputs changes value.
 *
 * Plotly is a stub; its `react` marks the graph div the way a real draw does (the class and
 * `_fullLayout` the record's picture-taker looks for), so "drawn" here means Plotly was asked to
 * draw into that div.
 */
import "@testing-library/jest-dom";
import { render, waitFor, fireEvent, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { ThemeProvider } from "@mui/material/styles";

import theme from "assets/theme";
import { PlatformContextProvider } from "context";

jest.mock("plotly.js-dist", () => {
  const mark = (gd) => {
    if (gd && gd.classList) { gd.classList.add("js-plotly-plot"); gd._fullLayout = { width: 700, height: 300 }; }
    return Promise.resolve(gd);
  };
  // Plain functions, not jest.fn: the test setup resets every jest.fn's behaviour before each test.
  return {
    react: mark, newPlot: mark, purge: () => {}, restyle: () => Promise.resolve(),
    relayout: () => Promise.resolve(), toImage: () => Promise.resolve("data:image/png;base64,AAAA"),
  };
});
jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn() } }));
jest.mock("layouts/DatabaseLayout", () => ({ children }) => <div>{children}</div>);

// Every render of the grid panel is recorded with its props. The wrapper keeps the panel's own
// React.memo (when it has one), so a render skipped by memo is not recorded.
global.__gridRenders = [];
jest.mock("./BandSweepGridPanel", () => {
  const React = jest.requireActual("react");
  const actual = jest.requireActual("./BandSweepGridPanel");
  const real = actual.default;
  const isMemo = !!real && real.$$typeof === Symbol.for("react.memo");
  const inner = isMemo ? real.type : real;
  function CountedGrid(props) {
    global.__gridRenders.push(props);
    return inner(props);
  }
  return { __esModule: true, ...actual, default: isMemo ? React.memo(CountedGrid, real.compare) : CountedGrid };
});

// eslint-disable-next-line import/first
import { SessionController } from "database/session-control";
// eslint-disable-next-line import/first
import { invalidateAll } from "database/resultCache";
// eslint-disable-next-line import/first
import ClosedLoopSim from "./index";
// eslint-disable-next-line import/first
import REPORT from "./__fixtures__/rcs08_cl_L13_24p5_2026-09-25.json";
// eslint-disable-next-line import/first
import SUMMARY from "./__fixtures__/rcs08_summary_L13_24p5_2026-09-25.json";
// eslint-disable-next-line import/first
import FULL from "./__fixtures__/rcs08_deployment_payload_2026-09-15.json";

const BC = { contact: "ONE_THREE_LEFT", contact_label: "L 1-3+", center_freq_hz: 24.5, bandwidth_hz: 5,
  hemisphere: "Left", threshold_mode: "dual", schema_version: "bandcandidate_v1" };
// The stored simulation's shape, as `ClosedLoopSimulationPanel.band.test.js` builds it.
const MODEL = { frac_time_at_upper: 0.3, frac_time_at_lower: 0.2, frac_time_above: 0.3,
  frac_time_between: 0.4, frac_time_below: 0.3, transitions_per_hour: 3, n_transitions_undone: 0,
  undone_per_hour: 0, mean_amplitude_mA: 3.1, amp_hist: [1, 2], longest_run_at_upper_s: 60 };
const RUN = { active_model: "M1", models: { M0: MODEL, M1: MODEL },
  curves: { M1: { kind: "linear", slope_per_mA: -3, n_points: 10, n_runs: 3 } },
  params: { amp_low_mA: 1.4, amp_high_mA: 4.5, lower: 191, upper: 241 }, drawn: [], record: {},
  amp_hist_edges_mA: [1.4, 3, 4.5] };
const SIMULATION = { available: true, timing_runs: { programmed: RUN, recommended: RUN },
  inputs: { contact: "ONE_THREE_LEFT", centre_used_hz: 24.5 },
  candidate: { channel: "ONE_THREE_LEFT", center_hz: 24.5 } };

const answer = (data, ms) => new Promise((resolve) => setTimeout(() => resolve({ data }), ms));

// THE CLOCK IS HELD STILL. The page re-renders without end while the clock moves once the
// simulation is answered (its cache key carries the report's "computed at" time, which the cache
// sets to the time of each read); that is reported on its own and is not what these tests are about.
const FIXED_NOW = 1790000000000;

beforeEach(() => {
  jest.spyOn(Date, "now").mockReturnValue(FIXED_NOW);
  invalidateAll("test setup");
  window.localStorage.clear();
  global.__gridRenders = [];
  window.print = jest.fn();
  SessionController.query.mockReset();
  SessionController.query.mockImplementation((url, body) => {
    if (url === "/api/queryServerIdentity") return answer({ boot_token: "t" }, 1);
    if (url === "/api/queryParticipantInformation") return answer({ Name: "RCS08" }, 2);
    if (url === "/api/queryClosedLoopChosenBand") {
      return answer({ available: true, record: { band_candidate: BC, committed_at: 1 } }, 5);
    }
    if (url === "/api/queryDeploymentSummary") return answer(SUMMARY, 40);
    if (url === "/api/queryClosedLoopDeployment") {
      if (body.ThreeSourcePooled) return answer({ available: true, ...FULL.three_source_pooled }, 10);
      if (body.ClosedLoopSimulation) return answer(SIMULATION, 12);
      // The grid asks with no candidate; the report asks with the chosen band as its one candidate.
      if ((body.Candidates || []).length === 0) return answer({ band_sweep_grid: FULL.band_sweep_grid }, 20);
      return answer(REPORT, 30);
    }
    return answer({}, 1);
  });
});

afterEach(() => { jest.restoreAllMocks(); });

// A fresh participant for each test: the page keeps whether its Background fold was ever opened
// per participant, for the life of the tab, so a shared one would carry an opening across tests.
let uidCount = 0;
function renderPage() {
  uidCount += 1;
  const uid = `SPEEDTEST${uidCount}`;
  return render(
    <ThemeProvider theme={theme}>
      <PlatformContextProvider initialStates={{ darkMode: false }}>
        <MemoryRouter initialEntries={[`/reports/closedloop/${uid}`]}>
          <Routes>
            <Route path="/reports/closedloop/:participant_uid" element={<ClosedLoopSim />} />
          </Routes>
        </MemoryRouter>
      </PlatformContextProvider>
    </ThemeProvider>);
}

const drawnIn = (container, id) => container.querySelectorAll(`#${id} .js-plotly-plot`).length;

/** Wait until both background panels hold their data: the simulation's headline and the
 *  three-source panel's "Sensing on ..." line are printed (both stay in the DOM while folded). */
async function untilBackgroundHasData(container) {
  await waitFor(() => {
    expect(container.querySelector("#cl-simulation").textContent).toMatch(/Closing the loop moves/);
    expect(container.querySelector("#cl-three-source").textContent).toMatch(/Sensing on /);
  }, { timeout: 3000 });
}

describe("C5: the Background fold's figures are drawn when it is first opened", () => {
  it("draws nothing inside the closed Background fold while the page loads", async () => {
    const { container } = renderPage();
    await untilBackgroundHasData(container);
    // Long enough for any draw effect the arriving data would have started.
    await new Promise((r) => setTimeout(r, 50));
    expect(drawnIn(container, "cl-three-source")).toBe(0);
    expect(drawnIn(container, "cl-simulation")).toBe(0);
  });

  it("draws both figures once the fold is opened", async () => {
    const { container } = renderPage();
    await untilBackgroundHasData(container);
    fireEvent.click(screen.getByRole("button", { name: /Show the background/ }));
    await waitFor(() => {
      expect(drawnIn(container, "cl-three-source")).toBeGreaterThan(0);
      expect(drawnIn(container, "cl-simulation")).toBeGreaterThan(0);
    });
  });

  it("'Sign and print' with the fold never opened still puts both figures on the record", async () => {
    const { container } = renderPage();
    await untilBackgroundHasData(container);
    fireEvent.click(screen.getByRole("button", { name: "Sign and print" }));
    await waitFor(() => expect(window.print).toHaveBeenCalled(), { timeout: 3000 });
    const record = container.querySelector(".cl-signoff-figures");
    expect(record).not.toBeNull();
    const pictured = Array.from(record.querySelectorAll("img")).map((img) => img.getAttribute("alt"));
    expect(pictured).toContain("Stimulation amplitude effects on band power, measured three ways");
    expect(pictured).toContain("What the automatic adjustment would have done (simulated)");
  });
});

/** True when two renders received the same inputs in value: the same objects, an object rebuilt
 *  with the same contents, or a callback re-created from the same source text. */
function sameValue(a, b) {
  if (a === b) return true;
  if (typeof a === "function" && typeof b === "function") return String(a) === String(b);
  if (a && b && typeof a === "object" && typeof b === "object") {
    try { return JSON.stringify(a) === JSON.stringify(b); } catch (e) { return false; }
  }
  return false;
}
function sameProps(p, q) {
  const keys = new Set([...Object.keys(p), ...Object.keys(q)]);
  return Array.from(keys).every((k) => sameValue(p[k], q[k]));
}

describe("C6: the band grid re-renders only when its inputs change", () => {
  it("never renders twice in a row with the same inputs while the page loads", async () => {
    const { container } = renderPage();
    await untilBackgroundHasData(container);
    await waitFor(() => expect(screen.getByText(/Chosen: L 1/)).toBeInTheDocument());
    const renders = global.__gridRenders;
    expect(renders.length).toBeGreaterThan(0);
    const repeats = renders.slice(1).filter((p, i) => sameProps(renders[i], p)).length;
    expect({ renders: renders.length, repeats }).toEqual({ renders: renders.length, repeats: 0 });
  });
});
