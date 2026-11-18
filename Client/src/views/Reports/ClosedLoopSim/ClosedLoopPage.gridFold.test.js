/**
 * The band grid folds once a band is chosen, and the decision card's "change" opens it (the PI,
 * 2026-11-18: "keep the verdict on top, and add one line at the top of the decision card ... that
 * jumps to the grid. Fold the grid away once a band is chosen"). The decision card's existing band
 * line carries the "change" link, so the band is not named one more time.
 */
import "@testing-library/jest-dom";

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

// Each test renders the whole page through up to four reports and the wiring comparison: about 28 s
// alone, more when the full page-test run shares the machine, so past the 30 s default.
jest.setTimeout(120000);

const RIGHT_BC = { ...LOCAL_BC, contact: "ZERO_THREE_RIGHT", contact_label: "R 0-3", center_freq_hz: 18.5,
  hemisphere: "Right" };
const env = (bc) => ({ band_candidate: bc, committed_at: 2, action: "chosen" });

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
      return answer({ available: true, record: env(LOCAL_BC), history: [],
        by_side: { Left: env(LOCAL_BC), Right: env(RIGHT_BC) } }, 5);
    }
    if (url === "/api/queryDeploymentSummary") {
      return answer({ ...SUMMARY, identity: { ...SUMMARY.identity, contact: body.Channel,
        center_freq_hz: Number(body.CenterHz) } }, 5);
    }
    if (url === "/api/queryClosedLoopDeployment") {
      if ((body.Candidates || []).length === 0) return answer({ band_sweep_grid: FULL.band_sweep_grid }, 5);
      const c = body.Candidates[0];
      return answer({ ...REPORT, manifest: { ...(REPORT.manifest || {}), hemisphere: body.Hemisphere },
        candidates: [{ ...(REPORT.candidates || [{}])[0], channel: c.channel, center_hz: c.center_hz }] }, 5);
    }
    return answer({}, 1);
  });
});

// eslint-disable-next-line import/first
import { fireEvent, screen, within } from "@testing-library/react";

const toggle = () => screen.getByTestId("band-grid-toggle");
const gridOpen = () => toggle().getAttribute("aria-expanded") === "true";

it("with a band chosen the grid is folded, its answer line stays, and \"change\" opens it", async () => {
  window.localStorage.setItem("bravo.bandCandidate.FOLD1", JSON.stringify(env(LOCAL_BC)));
  window.localStorage.setItem("bravo:wiring:FOLD1", "independent");
  Element.prototype.scrollIntoView = jest.fn();
  renderClosedLoopPage("FOLD1");
  await settle();
  expect(gridOpen()).toBe(false);
  expect(toggle()).toHaveTextContent("Show the band grid");
  expect(screen.getByTestId("band-selection-answer")).toBeVisible();
  const lines = screen.getAllByTestId("decision-band-line");
  expect(lines.length).toBeGreaterThanOrEqual(1);
  fireEvent.click(within(lines[0]).getByText("change"));
  expect(gridOpen()).toBe(true);
  expect(toggle()).toHaveTextContent("Hide the band grid");
  expect(Element.prototype.scrollIntoView).toHaveBeenCalled();
  // the toggle folds it again
  fireEvent.click(toggle());
  expect(gridOpen()).toBe(false);
});

it("with no band chosen the grid is open, since it is how a first band is chosen", async () => {
  SessionController.query.mockImplementation((url) => {
    if (url === "/api/queryServerIdentity") return answer({ boot_token: "t" }, 1);
    if (url === "/api/queryParticipantInformation") return answer({ Name: "RCS08" }, 2);
    if (url === "/api/queryClosedLoopChosenBand") return answer({ available: true, record: null, history: [] }, 5);
    if (url === "/api/queryClosedLoopDeployment") return answer({ band_sweep_grid: FULL.band_sweep_grid }, 5);
    return answer({}, 1);
  });
  renderClosedLoopPage("FOLD2");
  await settle();
  expect(gridOpen()).toBe(true);
  expect(screen.queryAllByTestId("decision-band-line")).toHaveLength(0);
});
