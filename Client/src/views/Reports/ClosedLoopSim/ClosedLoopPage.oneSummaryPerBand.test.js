/**
 * Choosing a band gives one up-to-date summary (the PI, 2026-10-04: after choosing a band the record
 * read "the settings have changed since"). The summary needs a cut-point for its switching value;
 * the ROC panel, a separate request, picked one about 250 ms after it answered and the page then
 * sent it with the summary, so the summary just computed was marked changed (and a cut-point chosen
 * on one band was sent with the next band's summary). Now the server uses the ROC's own default
 * point when none is sent, and the page sends a cut-point only when the reader moved the ROC off its
 * defaults on THIS band.
 */
import { fireEvent } from "@testing-library/react";
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

import { summaryCutpoint } from "./candidateRequestParams";

const ROC = { available: true, roc: { available: true, auc: 0.71, auc_ci: [0.6, 0.8], prevalence: 0.5,
  n_clusters: 40, fpr: [0, 0.2, 0.5, 1], tpr: [0, 0.5, 0.8, 1], thr: [9, 3, 2, 0],
  operating_points: { youden: { threshold: 2.0, rule: "youden", fpr: 0.5, tpr: 0.8, sensitivity: 0.8,
    specificity: 0.5 }, f1: { threshold: 3.0, rule: "f1", fpr: 0.2, tpr: 0.5, sensitivity: 0.5,
    specificity: 0.8 }, cost: [] } } };

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
    if (url === "/api/queryDeploymentROC") return answer(ROC, 5);
    if (url === "/api/queryClosedLoopDeployment") {
      if ((body.Candidates || []).length === 0) return answer({ band_sweep_grid: FULL.band_sweep_grid }, 5);
      return answer(REPORT, 5);
    }
    return answer({}, 1);
  });
});

const settle = async (n = 30) => {
  for (let i = 0; i < n; i += 1) {
    // eslint-disable-next-line no-await-in-loop
    await act(() => new Promise((r) => setTimeout(r, 100)));
  }
};

it("asks for the summary once, with no cut-point, and it stays current once the ROC answers", async () => {
  const uid = "CUT1";
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
  await settle();
  const show = Array.from(document.querySelectorAll("button"))
    .find((b) => /Show the background/.test(b.textContent));
  expect(show).toBeDefined();
  await act(async () => { fireEvent.click(show); });
  await settle();
  expect(asked.some((a) => a.url === "/api/queryDeploymentROC")).toBe(true);
  const sums = asked.filter((a) => a.url === "/api/queryDeploymentSummary").map((a) => a.body);
  expect(sums.length).toBe(1);
  expect(sums[0].Cutpoint).toBeUndefined();
  expect(document.body.textContent).not.toMatch(/settings have changed since/);
});

describe("which cut-point the summary is sent", () => {
  const BAND = "ONE_THREE_LEFT|24.5";
  const cut = (o) => ({ threshold: 2.5, rule: "f1", matchDir: "prior", forBand: BAND, isDefault: false, ...o });
  test("none before the ROC has answered", () => {
    expect(summaryCutpoint(null, BAND)).toEqual({ cutThr: null, matchDir: "prior" });
  });
  test("none for the ROC's own default point", () => {
    expect(summaryCutpoint(cut({ isDefault: true }), BAND)).toEqual({ cutThr: null, matchDir: "prior" });
  });
  test("none for a point chosen on another band", () => {
    expect(summaryCutpoint(cut({ forBand: "ZERO_TWO_LEFT|23.5" }), BAND))
      .toEqual({ cutThr: null, matchDir: "prior" });
  });
  test("the reader's own point on this band", () => {
    expect(summaryCutpoint(cut({ matchDir: "nearest" }), BAND)).toEqual({ cutThr: 2.5, matchDir: "nearest" });
  });
});
