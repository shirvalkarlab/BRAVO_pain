/**
 * The two bands either side of the chosen one are worked out ahead (the PI, 2026-10-04: "when a band
 * is selected ... have 2 bands on either side automatically computed in parallel", decision 425).
 * Once the chosen band's report and summary are in, the page sends the report and summary requests
 * for the neighbouring grid rows on the same contact; each goes to another worker, and the server
 * saves the answer (decision 423). Ticking a neighbour then sends EXACTLY the requests already sent,
 * so the saved answers match. Each neighbour is asked for once.
 */
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
import REPORT from "./__fixtures__/rcs08_cl_L13_24p5_2026-09-25.json";
// eslint-disable-next-line import/first
import SUMMARY from "./__fixtures__/rcs08_summary_L13_24p5_2026-09-25.json";
// eslint-disable-next-line import/first
import FULL from "./__fixtures__/rcs08_deployment_payload_2026-09-15.json";



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
    if (url === "/api/recordClosedLoopChosenBand" || /ChosenBand/.test(url)) {
      return answer({ available: true, recorded: true }, 2);
    }
    // The stand-in server answers for the band it was asked about, as the real one does.
    if (url === "/api/queryDeploymentROC") {
      return answer({ available: true, roc: { available: true, auc: 0.7, prevalence: 0.5, n_clusters: 30,
        fpr: [0, 0.5, 1], tpr: [0, 0.8, 1], thr: [9, 2, 0],
        operating_points: { youden: { threshold: 2.0 + Number(body.CenterHz) / 100, rule: "youden",
          fpr: 0.5, tpr: 0.8, sensitivity: 0.8, specificity: 0.5 }, f1: null, cost: [] } } }, 5);
    }
    if (url === "/api/queryDeploymentSummary") {
      return answer({ ...SUMMARY, identity: { ...SUMMARY.identity, contact: body.Channel,
        center_freq_hz: Number(body.CenterHz) } }, 5);
    }
    if (url === "/api/queryClosedLoopDeployment") {
      if ((body.Candidates || []).length === 0) return answer({ band_sweep_grid: FULL.band_sweep_grid }, 5);
      const c = body.Candidates[0];
      return answer({ ...REPORT, candidates: [{ ...(REPORT.candidates || [{}])[0], channel: c.channel,
        center_hz: c.center_hz }] }, 5);
    }
    return answer({}, 1);
  });
});

const reportAsks = () => asked.filter((a) => a.url === "/api/queryClosedLoopDeployment"
  && (a.body.Candidates || []).length && !a.body.ClosedLoopSimulation);
const summaryAsks = () => asked.filter((a) => a.url === "/api/queryDeploymentSummary");

it("asks ahead for the two bands either side, exactly as ticking them would", async () => {
  const uid = "NEIGHBOURS";
  window.localStorage.setItem(`bravo.bandCandidate.${uid}`,
    JSON.stringify({ band_candidate: LOCAL_BC, participant_uid: uid, committed_at: 2 }));
  renderClosedLoopPage(uid);
  await settle(40);
  const centres = (b) => b.Candidates[0].center_hz;
  const ahead = reportAsks().filter((a) => a.body.Candidates[0].channel === "ONE_THREE_LEFT"
    && centres(a.body) !== 24.5).map((a) => centres(a.body)).sort((a, b) => a - b);
  expect(ahead).toEqual([22.5, 23.5, 25.5, 26.5]);
  const sumAhead = summaryAsks().filter((a) => Number(a.body.CenterHz) !== 24.5)
    .map((a) => Number(a.body.CenterHz)).sort((a, b) => a - b);
  expect(sumAhead).toEqual([22.5, 23.5, 25.5, 26.5]);

  const before = asked.length;
  const prefetchedReport = reportAsks().find((a) => centres(a.body) === 25.5).body;
  const prefetchedSummary = summaryAsks().find((a) => Number(a.body.CenterHz) === 25.5).body;
  const radio = document.querySelector('input[aria-label="use the 25.5 Hz band on L 1⁻3⁺"]')
    || Array.from(document.querySelectorAll('input[type="radio"][name^="cl-use-band-"]'))
      .find((r) => /25\.5 Hz/.test(r.getAttribute("aria-label") || ""));
  expect(radio).toBeTruthy();
  await act(async () => { fireEvent.click(radio); });
  await settle(40);
  const after = asked.slice(before);
  const clickReport = after.find((a) => a.url === "/api/queryClosedLoopDeployment"
    && (a.body.Candidates || []).length && !a.body.ClosedLoopSimulation && centres(a.body) === 25.5);
  const clickSummary = after.find((a) => a.url === "/api/queryDeploymentSummary"
    && Number(a.body.CenterHz) === 25.5);
  expect(clickReport.body).toEqual(prefetchedReport);
  expect(clickSummary.body).toEqual(prefetchedSummary);
  // neighbours of the new band that were already asked for are not asked again
  const again = asked.slice(before).filter((a) => a.url === "/api/queryClosedLoopDeployment"
    && (a.body.Candidates || []).length && !a.body.ClosedLoopSimulation
    && [23.5, 26.5].includes(centres(a.body)));
  expect(again.length).toBe(0);
});


it("asks ahead for the Background panels of the chosen band and its neighbours, as the panels will (decision 428)", async () => {
  const uid = "PANELS";
  window.localStorage.setItem(`bravo.bandCandidate.${uid}`,
    JSON.stringify({ band_candidate: LOCAL_BC, participant_uid: uid, committed_at: 2 }));
  renderClosedLoopPage(uid);
  await settle(40);
  const hz = (url) => asked.filter((a) => a.url === url).map((a) => Number(a.body.CenterHz)).sort((a, b) => a - b);
  expect(hz("/api/queryDeploymentROC")).toEqual([22.5, 23.5, 24.5, 25.5, 26.5]);
  expect(hz("/api/queryDeploymentRocByEra")).toEqual([22.5, 23.5, 24.5, 25.5, 26.5]);
  expect(hz("/api/queryLsbPower")).toEqual([22.5, 23.5, 24.5, 25.5, 26.5]);
  const lsb245 = asked.find((a) => a.url === "/api/queryLsbPower" && Number(a.body.CenterHz) === 24.5).body;
  expect(lsb245.Cutpoint).toBeCloseTo(2.245, 12);                   // the ROC's own default point
  const ahead = (url) => asked.find((a) => a.url === url && Number(a.body.CenterHz) === 24.5).body;
  const before = asked.length;
  const show = Array.from(document.querySelectorAll("button"))
    .find((b) => /Show the background/.test(b.textContent));
  await act(async () => { fireEvent.click(show); });
  await settle(40);
  const opened = asked.slice(before);
  ["/api/queryDeploymentROC", "/api/queryDeploymentRocByEra", "/api/queryLsbPower"].forEach((url) => {
    const mine = opened.filter((a) => a.url === url && Number(a.body.CenterHz) === 24.5);
    expect(mine.length).toBe(1);
    expect(mine[0].body).toEqual(ahead(url));
  });
});
