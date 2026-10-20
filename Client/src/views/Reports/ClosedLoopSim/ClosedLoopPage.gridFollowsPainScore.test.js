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
    if (url === "/api/queryDeploymentSummary") return answer(SUMMARY, 5);
    if (url === "/api/queryClosedLoopDeployment") {
      if ((body.Candidates || []).length === 0) return answer({ band_sweep_grid: FULL.band_sweep_grid }, 5);
      return answer(REPORT, 5);
    }
    return answer({}, 1);
  });
});

const gridAsks = () => asked.filter((a) => a.url === "/api/queryClosedLoopDeployment"
  && !(a.body.Candidates || []).length && !a.body.ThreeSourcePooled && !a.body.ClosedLoopSimulation);

it("asks for the grid again under the score chosen in the dropdown", async () => {
  const uid = "GRIDSCORE";
  window.localStorage.setItem(`bravo.bandCandidate.${uid}`,
    JSON.stringify({ band_candidate: LOCAL_BC, participant_uid: uid, committed_at: 2 }));
  renderClosedLoopPage(uid);
  await settle();
  const before = gridAsks().length;
  expect(before).toBeGreaterThan(0);
  expect(gridAsks()[before - 1].body.LabelMetric || "nrs").toBe("nrs");

  // Found directly: a role query over this whole page takes minutes.
  const labelled = document.querySelector('[aria-label^="Pain score"]');
  expect(labelled).not.toBeNull();
  const select = labelled.closest(".MuiInputBase-root").querySelector(".MuiSelect-select");
  await act(async () => { fireEvent.mouseDown(select); });
  const option = Array.from(document.querySelectorAll('li[role="option"]'))
    .find((li) => li.textContent === "Left Leg VAS");
  expect(option).toBeDefined();
  await act(async () => { fireEvent.click(option); });
  await settle();

  const after = gridAsks();
  expect(after.length).toBe(before + 1);
  expect(after[after.length - 1].body).toMatchObject({ LabelMetric: "left_leg_vas",
    SweepMetric: "left_leg_vas", MatchToleranceMin: 15, MatchDirection: "nearest" });
});
