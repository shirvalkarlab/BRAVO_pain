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
    if (url === "/api/recordClosedLoopChosenBand" || /ChosenBand/.test(url)) {
      return answer({ available: true, recorded: true }, 2);
    }
    // The stand-in server answers for the band it was asked about, as the real one does.
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

it("computes the newly chosen band instead of showing the old one as stale", async () => {
  const uid = "NEWBAND";
  window.localStorage.setItem(`bravo.bandCandidate.${uid}`,
    JSON.stringify({ band_candidate: LOCAL_BC, participant_uid: uid, committed_at: 2 }));
  renderClosedLoopPage(uid);
  await settle();
  const gridsBefore = asked.filter((a) => a.url === "/api/queryClosedLoopDeployment"
    && !(a.body.Candidates || []).length && !a.body.ThreeSourcePooled).length;
  const reportsBefore = reportAsks().length;
  const summariesBefore = asked.filter((a) => a.url === "/api/queryDeploymentSummary").length;

  // another band on the same contact's tab: the first radio that is not the chosen one
  const radios = Array.from(document.querySelectorAll('input[type="radio"][name^="cl-use-band-"]'));
  const other = radios.find((r) => !r.checked);
  expect(other).toBeDefined();
  await act(async () => { fireEvent.click(other); });
  await settle();

  // the chosen band's own requests come first; the neighbours' (decision 425) follow once they are in
  const newReports = reportAsks().slice(reportsBefore);
  const cand = newReports[0].body.Candidates[0];
  expect(cand.center_hz).not.toBe(LOCAL_BC.center_freq_hz);
  expect(newReports.filter((a) => a.body.Candidates[0].center_hz === cand.center_hz).length).toBe(1);
  const newSummaries = asked.filter((a) => a.url === "/api/queryDeploymentSummary").slice(summariesBefore);
  expect(Number(newSummaries[0].body.CenterHz)).toBe(cand.center_hz);
  expect(newSummaries.filter((a) => Number(a.body.CenterHz) === cand.center_hz).length).toBe(1);
  expect(asked.filter((a) => a.url === "/api/queryClosedLoopDeployment"
    && !(a.body.Candidates || []).length && !a.body.ThreeSourcePooled).length).toBe(gridsBefore);
  expect(document.body.textContent).not.toMatch(/settings have changed since/);
  expect(document.body.textContent).not.toMatch(/not the chosen band/);
});
