/**
 * The Closed-Loop page settles once every answer is in (found 2026-10-02 while doing the page
 * speed-ups). The simulation's cache key carries the report's "computed at" time, which the shared
 * cache used to set to the time of each read, so with the clock running the key changed on every
 * render: the simulation hook re-read and set its state, the page rendered again, without end; and
 * the simulation panel was always marked as changed since it was computed. Fixed in the cache
 * (`resultCache.getResult` returns the time the answer was stored; decision 366).
 *
 * Rendered with React's own root (the one the app uses), because the test library's older root
 * runs such a loop synchronously and never returns. The clock runs normally here.
 */
import "@testing-library/jest-dom";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { ThemeProvider } from "@mui/material/styles";
import { createRoot } from "react-dom/client";

import theme from "assets/theme";
import { PlatformContextProvider } from "context";

jest.mock("plotly.js-dist", () => ({
  react: () => Promise.resolve(), newPlot: () => Promise.resolve(), purge: () => {},
  restyle: () => Promise.resolve(), relayout: () => Promise.resolve(), toImage: () => Promise.resolve(""),
}));
jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn() } }));
jest.mock("layouts/DatabaseLayout", () => ({ children }) => <div>{children}</div>);
// The recompute bar is drawn once per render of the page, so counting it counts the page's renders.
global.__pageRenders = 0;
jest.mock("views/Reports/RecomputeBar", () => () => {
  global.__pageRenders += 1;
  return <div>recompute bar</div>;
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
const pause = (ms) => new Promise((r) => setTimeout(r, ms));

beforeEach(() => {
  invalidateAll("test setup");
  window.localStorage.clear();
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
      if ((body.Candidates || []).length === 0) return answer({ band_sweep_grid: FULL.band_sweep_grid }, 20);
      return answer(REPORT, 30);
    }
    return answer({}, 1);
  });
});

it("stops re-rendering once every answer is in, and the simulation is not marked as changed", async () => {
  const prevAct = global.IS_REACT_ACT_ENVIRONMENT;
  global.IS_REACT_ACT_ENVIRONMENT = false;
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  try {
    root.render(
      <ThemeProvider theme={theme}>
        <PlatformContextProvider initialStates={{ darkMode: false }}>
          <MemoryRouter initialEntries={["/reports/closedloop/LOOPTEST"]}>
            <Routes>
              <Route path="/reports/closedloop/:participant_uid" element={<ClosedLoopSim />} />
            </Routes>
          </MemoryRouter>
        </PlatformContextProvider>
      </ThemeProvider>);
    // Every stub answers within 40 ms; wait well past that for the simulation to be shown.
    for (let i = 0; i < 60; i += 1) {
      // eslint-disable-next-line no-await-in-loop
      await pause(50);
      if (/Closing the loop moves/.test((container.querySelector("#cl-simulation") || {}).textContent || "")) break;
    }
    expect(container.querySelector("#cl-simulation").textContent).toMatch(/Closing the loop moves/);
    await pause(300);
    const settled = global.__pageRenders;
    await pause(500);
    expect({ rendersInHalfASecondAfterSettling: global.__pageRenders - settled })
      .toEqual({ rendersInHalfASecondAfterSettling: 0 });
    expect(container.querySelector("#cl-simulation").textContent)
      .not.toMatch(/Something it depends on has changed since it was computed/);
  } finally {
    root.unmount();
    container.remove();
    global.IS_REACT_ACT_ENVIRONMENT = prevAct;
  }
});
