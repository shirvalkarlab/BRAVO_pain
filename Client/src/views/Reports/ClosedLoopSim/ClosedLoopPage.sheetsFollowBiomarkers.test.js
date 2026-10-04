/**
 * The clinic-sheet switch is gone from the Closed-Loop page (the PI, 2026-10-04: "follow biomarkers
 * page - remove toggle here"). The summary takes the clinic-sheet setting of the Biomarkers page's
 * last run, like the grid and the stability card; there is no control for it on this page.
 */
import { saveControls } from "views/Reports/Biomarkers/biomarkerStateStore";
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
    if (url === "/api/queryClosedLoopChosenBand") {
      return answer({ available: true, record: { band_candidate: LOCAL_BC, committed_at: 2 } }, 5);
    }
    if (url === "/api/queryDeploymentSummary") return answer(SUMMARY, 5);
    if (url === "/api/queryClosedLoopDeployment") {
      if ((body.Candidates || []).length === 0) return answer({ band_sweep_grid: FULL.band_sweep_grid }, 5);
      return answer(REPORT, 5);
    }
    return answer({}, 1);
  });
});

async function load(uid) {
  window.localStorage.setItem(`bravo.bandCandidate.${uid}`,
    JSON.stringify({ band_candidate: LOCAL_BC, participant_uid: uid, committed_at: 2 }));
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
  for (let i = 0; i < 30; i += 1) {
    // eslint-disable-next-line no-await-in-loop
    await act(() => new Promise((r) => setTimeout(r, 100)));
  }
  return asked.filter((a) => a.url === "/api/queryDeploymentSummary").map((a) => a.body);
}

const sheetsRun = (uid, on) => saveControls(uid, { metric: "nrs", matchingRun: {
  settings: { LabelMetric: "nrs", MatchToleranceMin: 15, MatchDirection: "nearest",
    IncludeClinicSheetRatings: on }, ranAt: Date.UTC(2026, 9, 3, 12, 0) } });

it("has no clinic-sheet switch", async () => {
  await load("SHEETS0");
  expect(document.body.textContent).not.toMatch(/Clinic-sheet ratings in the summary/);
  expect(Array.from(document.querySelectorAll("button"))
    .filter((el) => /clinic.sheet/i.test(el.textContent))).toEqual([]);
});

it("sends the Biomarkers page's clinic-sheet setting with the summary, on", async () => {
  sheetsRun("SHEETS1", true);
  const sent = await load("SHEETS1");
  expect(sent.length).toBeGreaterThan(0);
  sent.forEach((b) => expect(b.IncludeClinicSheetRatings).toBe("1"));
});

it("and off", async () => {
  sheetsRun("SHEETS2", false);
  const sent = await load("SHEETS2");
  expect(sent.length).toBeGreaterThan(0);
  sent.forEach((b) => expect(b.IncludeClinicSheetRatings).toBeUndefined());
});
