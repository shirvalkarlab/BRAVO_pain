/** Synthetic UI contract regression. No live participant response or empirical validation. */
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
import REPORT from "./__fixtures__/synthetic_allowed_left.json";
// eslint-disable-next-line import/first
import SUMMARY from "./__fixtures__/synthetic_summary_left.json";
// eslint-disable-next-line import/first
import FULL from "./__fixtures__/synthetic_provisional_grid.json";

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
    if (url === "/api/queryParticipantInformation") return answer({ Name: "Synthetic participant" }, 2);
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

const reportAsks = () => asked.filter((a) => a.url === "/api/queryClosedLoopDeployment"
  && (a.body.Candidates || []).length && !a.body.ClosedLoopSimulation
  && a.body.Candidates[0].center_hz != null);
const ask = (channel, hemisphere) => reportAsks().filter((a) => a.body.Candidates[0].channel === channel
  && a.body.Hemisphere === hemisphere);

async function open(uid, wiring) {
  window.localStorage.setItem(`bravo.bandCandidate.${uid}`, JSON.stringify(env(LOCAL_BC)));
  window.localStorage.setItem(`bravo:wiring:${uid}`, wiring);
  renderClosedLoopPage(uid);
  await settle();
}

it("2 independent controllers: each stimulator is checked with its own side's band", async () => {
  await open("TWOSIDES_IND", "independent");
  const left = ask("ONE_THREE_LEFT", "Left");
  const right = ask("ZERO_THREE_RIGHT", "Right");
  expect(left.length).toBeGreaterThanOrEqual(1);
  expect(right).toHaveLength(1);
  expect(right[0].body.Candidates[0].contralateral_pairing_acknowledged).toBeUndefined();
  expect(right[0].body.Candidates[0].center_hz).toBe(18.5);
  // the right band has its own summary
  expect(asked.filter((a) => a.url === "/api/queryDeploymentSummary" && a.body.Channel === "ZERO_THREE_RIGHT"))
    .toHaveLength(1);
  // no contralateral report is asked for
  expect(reportAsks().filter((a) => a.body.Candidates[0].contralateral_pairing_acknowledged)).toHaveLength(0);
  const text = document.body.textContent;
  expect(text).toMatch("Left stimulator · ipsilateral sensing");
  expect(text).toMatch("Right stimulator · ipsilateral sensing");
  expect(text).not.toMatch(/Not checked: no band chosen/);
  expect(text).not.toMatch(/settings have changed since/);
  expect(text).not.toMatch(/not the chosen band/);
});

it("left sensing drives both: the right stimulator uses the left band, contralateral, and the right band is not asked", async () => {
  await open("TWOSIDES_LB", "left_both");
  const contra = ask("ONE_THREE_LEFT", "Right");
  expect(contra).toHaveLength(1);
  expect(contra[0].body.Candidates[0].contralateral_pairing_acknowledged).toBe(true);
  expect(reportAsks().filter((a) => a.body.Candidates[0].channel === "ZERO_THREE_RIGHT")).toHaveLength(0);
  expect(asked.filter((a) => a.url === "/api/queryDeploymentSummary" && a.body.Channel === "ZERO_THREE_RIGHT"))
    .toHaveLength(0);
  const text = document.body.textContent;
  expect(text).toMatch("Right stimulator · contralateral sensing, from the left band");
  expect(text).not.toMatch(/settings have changed since/);
  // the right column of Band selection is greyed
  expect(document.querySelector('[data-testid="band-side-Right"]')).toHaveAttribute("aria-disabled", "true");
});

it("right sensing drives both, page band on the left: both stimulators use the right band", async () => {
  await open("TWOSIDES_RB", "right_both");
  expect(ask("ZERO_THREE_RIGHT", "Right")).toHaveLength(1);
  const contra = ask("ZERO_THREE_RIGHT", "Left");
  expect(contra).toHaveLength(1);
  expect(contra[0].body.Candidates[0].contralateral_pairing_acknowledged).toBe(true);
  const text = document.body.textContent;
  expect(text).toMatch("Left stimulator · contralateral sensing, from the right band");
  expect(text).toMatch("Right stimulator · ipsilateral sensing");
  expect(text).not.toMatch(/settings have changed since/);
});
