/** Synthetic UI contract regression. No live participant response or empirical validation. */
import "@testing-library/jest-dom";
import { render, waitFor } from "@testing-library/react";


jest.mock("plotly.js-dist", () => require("testUtils/plotlyStubs").plotlyMarking());
jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn() } }));
jest.mock("layouts/DatabaseLayout", () => ({ children }) => <div>{children}</div>);

// eslint-disable-next-line import/first
import { SessionController } from "database/session-control";
// eslint-disable-next-line import/first
import { LOCAL_BC, answer, renderClosedLoopPage } from "testUtils/closedLoopPage";
// eslint-disable-next-line import/first
import { invalidateAll } from "database/resultCache";
// eslint-disable-next-line import/first
import REPORT from "./__fixtures__/synthetic_allowed_left.json";
// eslint-disable-next-line import/first
import SUMMARY from "./__fixtures__/synthetic_summary_left.json";
// eslint-disable-next-line import/first
import FULL from "./__fixtures__/synthetic_provisional_grid.json";


const SERVER_BC = { contact: "ZERO_THREE_LEFT", contact_label: "L 0-3+", center_freq_hz: 27.5, bandwidth_hz: 5,
  hemisphere: "Left", threshold_mode: "dual", schema_version: "bandcandidate_v1" };

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

it("sends no band-specific request for the browser's copy when the server names another band", async () => {
  const uid = "SYNCTEST1";
  window.localStorage.setItem(`bravo.bandCandidate.${uid}`,
    JSON.stringify({ band_candidate: LOCAL_BC, participant_uid: uid, committed_at: 1 }));
  renderClosedLoopPage(uid);
  await waitFor(() => {
    expect(asked.some((a) => a.url === "/api/queryDeploymentSummary")).toBe(true);
    expect(asked.some((a) => a.url === "/api/queryClosedLoopDeployment"
      && (a.body.Candidates || []).length === 1)).toBe(true);
  }, { timeout: 3000 });
  const forABand = asked.filter((a) => a.url === "/api/queryDeploymentSummary"
    || (a.url === "/api/queryClosedLoopDeployment" && (a.body.Candidates || []).length > 0));
  const channels = forABand.map((a) => a.body.Channel || a.body.Candidates[0].channel);
  expect(channels.length).toBeGreaterThan(0);
  expect(new Set(channels)).toEqual(new Set(["ZERO_THREE_LEFT"]));
});
