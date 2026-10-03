/**
 * First-load request trace (page review 2026-10-02, item 4.7: the report request was seen 5 times
 * on one first load, each ~32 s on the server). The real page, stand-in answers, every request
 * recorded until the page settles; each kind of Closed-Loop request is asked for once.
 */
import "@testing-library/jest-dom";
import { render, act } from "@testing-library/react";
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


const SERVER_BC = { contact: "ZERO_THREE_LEFT", contact_label: "L 0-3+", center_freq_hz: 27.5, bandwidth_hz: 5,
  hemisphere: "Left", threshold_mode: "dual", schema_version: "bandcandidate_v1" };
const LOCAL_BC = { contact: "ONE_THREE_LEFT", contact_label: "L 1-3+", center_freq_hz: 24.5, bandwidth_hz: 5,
  hemisphere: "Left", threshold_mode: "dual", schema_version: "bandcandidate_v1" };
const answer = (data, ms) => new Promise((resolve) => setTimeout(() => resolve({ data }), ms));

let asked;
beforeEach(() => {
  invalidateAll("test setup");
  window.localStorage.clear();
  asked = [];
  SessionController.query.mockReset();
  SessionController.query.mockImplementation((url, body) => {
    asked.push({ url, body });
    if (url === "/api/queryServerIdentity") return answer({ boot_token: "t" }, 1);
    if (url === "/api/queryParticipantInformation") return answer({ Name: "RCS08" }, 2);
    // The server's record is slower than the page's first render, as on the live page.
    if (url === "/api/queryClosedLoopChosenBand") {
      return answer({ available: true, record: { band_candidate: SERVER_BC, committed_at: 2 } }, 60);
    }
    if (url === "/api/queryDeploymentSummary") return answer(SUMMARY, 5);
    if (url === "/api/queryClosedLoopDeployment") {
      if ((body.Candidates || []).length === 0) return answer({ band_sweep_grid: FULL.band_sweep_grid }, 5);
      return answer(REPORT, 5);
    }
    return answer({}, 1);
  });
});

const kind = (a) => {
  const b = a.body || {};
  if (b.ThreeSourcePooled) return "pooled";
  if (b.ClosedLoopSimulation) return "simulation";
  return (b.Candidates || []).length ? "report" : "grid";
};

async function firstLoad(uid, withLocalCopy) {
  if (withLocalCopy) {
    window.localStorage.setItem(`bravo.bandCandidate.${uid}`,
      JSON.stringify({ band_candidate: LOCAL_BC, participant_uid: uid, committed_at: 1 }));
  }
  render(
    <ThemeProvider theme={theme}>
      <PlatformContextProvider initialStates={{ darkMode: false }}>
        <MemoryRouter initialEntries={[`/reports/closedloop/${uid}`]}>
          <Routes>
            <Route path="/reports/closedloop/:participant_uid" element={<ClosedLoopSim />} />
          </Routes>
        </MemoryRouter>
      </PlatformContextProvider>
    </ThemeProvider>);
  // Time moves in 100 ms steps inside act, which flushes React's pending work after each step as a
  // browser's scheduler does at once. Without it, work queued after the last network answer waits
  // for the test's teardown (traced 2026-10-03), so the trace would miss requests a browser sends.
  for (let i = 0; i < 50; i += 1) {
    // eslint-disable-next-line no-await-in-loop
    await act(() => new Promise((r) => setTimeout(r, 100)));
  }
  const cl = asked.filter((a) => a.url === "/api/queryClosedLoopDeployment").map(kind);
  const counts = cl.reduce((m, k) => ({ ...m, [k]: (m[k] || 0) + 1 }), {});
  return counts;
}

it("still once each when the browser holds a copy of another band", async () => {
  expect(await firstLoad("TRACE2", true)).toEqual({ grid: 1, report: 1, pooled: 1, simulation: 1 });
});

it("asks for each kind of Closed-Loop result once on a first load", async () => {
  expect(await firstLoad("TRACE1", false)).toEqual({ grid: 1, report: 1, pooled: 1, simulation: 1 });
});
