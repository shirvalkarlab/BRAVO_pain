/** Synthetic UI contract regression. No live participant response or empirical validation. */
import "@testing-library/jest-dom";
import { act, fireEvent } from "@testing-library/react";


jest.mock("plotly.js-dist", () => require("testUtils/plotlyStubs").plotlyMarking());
jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn() } }));
jest.mock("layouts/DatabaseLayout", () => ({ children }) => <div>{children}</div>);

// eslint-disable-next-line import/first
import { SessionController } from "database/session-control";
// eslint-disable-next-line import/first
import { LOCAL_BC, answer, settle, renderClosedLoopPage } from "testUtils/closedLoopPage";
// eslint-disable-next-line import/first
import { invalidateAll } from "database/resultCache";
// eslint-disable-next-line import/first
import REPORT from "./__fixtures__/synthetic_allowed_left.json";
// eslint-disable-next-line import/first
import SUMMARY from "./__fixtures__/synthetic_summary_left.json";
// eslint-disable-next-line import/first
import FULL from "./__fixtures__/synthetic_provisional_grid.json";



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
    if (url === "/api/queryParticipantInformation") return answer({ Name: "Synthetic participant" }, 2);
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


it("asks for the summary once, with no cut-point, and it stays current once the ROC answers", async () => {
  const uid = "CUT1";
  window.localStorage.setItem(`bravo.bandCandidate.${uid}`,
    JSON.stringify({ band_candidate: LOCAL_BC, participant_uid: uid, committed_at: 2 }));
  renderClosedLoopPage(uid);
  await settle();
  const show = Array.from(document.querySelectorAll("button"))
    .find((b) => /Show the background/.test(b.textContent));
  expect(show).toBeDefined();
  await act(async () => { fireEvent.click(show); });
  await settle();
  expect(asked.some((a) => a.url === "/api/queryDeploymentROC")).toBe(true);
  // the chosen band's summary only; the neighbours' are asked for ahead (decision 425)
  const sums = asked.filter((a) => a.url === "/api/queryDeploymentSummary"
    && Number(a.body.CenterHz) === LOCAL_BC.center_freq_hz).map((a) => a.body);
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
