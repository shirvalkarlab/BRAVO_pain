/**
 * Two page speed-ups on the Stim Optimizer page (speed-up items C6 and C8, 2026-10-02), read off
 * the whole page rendered against the RCS08 fixture, with its requests answered by a stub.
 *
 * C6. The page re-renders several times while it loads (its own answer, the two-stage plan, the
 *     study code, every cache event). Each time, every card below was rebuilt, though none of their
 *     inputs had changed; the next-visit card alone (its clinic sheet is hundreds of table cells,
 *     folded but mounted) took about a quarter of a second per rebuild in this test environment.
 *     The heavy cards now rebuild only when one of their inputs changes value.
 * C8. The research checks at the foot of the page ("Checks against chance and against the current
 *     (run offline)") sit in a closed fold, but their request was sent and their card drawn on page
 *     load. The request now goes out the first time the fold is opened.
 */
import "@testing-library/jest-dom";
import { render, waitFor, fireEvent, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { ThemeProvider } from "@mui/material/styles";

import theme from "assets/theme";
import { PlatformContextProvider } from "context";

jest.mock("plotly.js-dist", () => ({
  react: () => Promise.resolve(), purge: () => {}, restyle: () => Promise.resolve(),
  relayout: () => Promise.resolve(), newPlot: () => Promise.resolve(), toImage: () => Promise.resolve(),
}));
jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn() } }));
jest.mock("layouts/DatabaseLayout", () => ({ children }) => <div>{children}</div>);
// The recompute bar is drawn once per render of the page, so counting it counts the page's renders.
global.__pageRenders = 0;
jest.mock("views/Reports/RecomputeBar", () => () => {
  global.__pageRenders += 1;
  return <div>recompute bar</div>;
});

// Every render of each heavy card is recorded with its props. The wrapper keeps the card's own
// React.memo (when it has one), so a render skipped by memo is not recorded.
global.__cardRenders = {};
function mockCounted(name, actual) {
  const React = jest.requireActual("react");
  const real = actual.default;
  const isMemo = !!real && real.$$typeof === Symbol.for("react.memo");
  const inner = isMemo ? real.type : real;
  function Counted(props) {
    global.__cardRenders[name] = (global.__cardRenders[name] || []).concat([props]);
    return inner(props);
  }
  return { __esModule: true, ...actual, default: isMemo ? React.memo(Counted, real.compare) : Counted };
}
jest.mock("./TitrationSessionCard", () => mockCounted("TitrationSessionCard", jest.requireActual("./TitrationSessionCard")));
jest.mock("./SensingEvidenceTable", () => mockCounted("SensingEvidenceTable", jest.requireActual("./SensingEvidenceTable")));
jest.mock("./TwoStagePlanCard", () => mockCounted("TwoStagePlanCard", jest.requireActual("./TwoStagePlanCard")));
jest.mock("./DecisionStrip", () => mockCounted("DecisionStrip", jest.requireActual("./DecisionStrip")));
jest.mock("./CurrentMapCard", () => mockCounted("CurrentMapCard", jest.requireActual("./CurrentMapCard")));

// eslint-disable-next-line import/first
import { SessionController } from "database/session-control";
// eslint-disable-next-line import/first
import { invalidateAll } from "database/resultCache";
// eslint-disable-next-line import/first
import StimOptimizer from "./index";
// eslint-disable-next-line import/first
import FX from "./__fixtures__/rcs08_stim_optimizer_two_stage.json";

const CHECKS = { page: "stim_optimizer", analyses: [{ key: "time_of_day", title: "Time of day and weekends",
  what: "Clock and weekend.", literature: [], n_runs: 0, snapshot: null }] };

const answer = (data, ms) => new Promise((resolve) => setTimeout(() => resolve({ data }), ms));
const checksRequests = () => SessionController.query.mock.calls
  .filter(([url]) => url === "/api/queryControlAnalyses").length;

beforeEach(() => {
  invalidateAll("test setup");
  global.__pageRenders = 0;
  global.__cardRenders = {};
  SessionController.query.mockReset();
  SessionController.query.mockImplementation((url, body) => {
    if (url === "/api/queryServerIdentity") return answer({ boot_token: "t" }, 1);
    if (url === "/api/queryParticipantInformation") return answer({ Name: "RCS08" }, 2);
    if (url === "/api/queryControlAnalyses") return answer(CHECKS, 3);
    if (url === "/api/queryStimOptimizer") return answer(FX, body.TwoStage ? 30 : 20);
    return answer({}, 1);
  });
});

function renderPage() {
  return render(
    <ThemeProvider theme={theme}>
      <PlatformContextProvider initialStates={{ darkMode: false }}>
        <MemoryRouter initialEntries={["/reports/stimoptimizer/SPEEDTEST"]}>
          <Routes>
            <Route path="/reports/stimoptimizer/:participant_uid" element={<StimOptimizer />} />
          </Routes>
        </MemoryRouter>
      </PlatformContextProvider>
    </ThemeProvider>);
}

/** Wait until both answers are on the page: the current map is drawn only once the two-stage plan
 *  has arrived, and the evidence footer only once the page's own answer has. */
async function untilLoaded() {
  await waitFor(() => {
    expect(screen.getByText(/Evidence base:/)).toBeInTheDocument();
    expect((global.__cardRenders.CurrentMapCard || []).length).toBeGreaterThan(0);
  }, { timeout: 3000 });
  // Long enough for the late answers (the study code, the server identity) to land.
  await new Promise((r) => setTimeout(r, 50));
}

/** True when two renders received the same inputs in value: the same objects, an object rebuilt
 *  with the same contents, or a callback re-created from the same source text. */
function sameValue(a, b) {
  if (a === b) return true;
  if (typeof a === "function" && typeof b === "function") return String(a) === String(b);
  if (a && b && typeof a === "object" && typeof b === "object") {
    try { return JSON.stringify(a) === JSON.stringify(b); } catch (e) { return false; }
  }
  return false;
}
function sameProps(p, q) {
  const keys = new Set([...Object.keys(p), ...Object.keys(q)]);
  return Array.from(keys).every((k) => sameValue(p[k], q[k]));
}

describe("C6: the heavy cards re-render only when their inputs change", () => {
  it("the page itself re-renders while it loads (so the check below means something)", async () => {
    renderPage();
    await untilLoaded();
    expect(global.__pageRenders).toBeGreaterThan(2);
  });

  ["TitrationSessionCard", "SensingEvidenceTable", "TwoStagePlanCard", "DecisionStrip", "CurrentMapCard"]
    .forEach((name) => {
      it(`${name} never renders twice in a row with the same inputs`, async () => {
        renderPage();
        await untilLoaded();
        const renders = global.__cardRenders[name] || [];
        expect(renders.length).toBeGreaterThan(0);
        const repeats = renders.slice(1).filter((p, i) => sameProps(renders[i], p)).length;
        expect({ renders: renders.length, repeats }).toEqual({ renders: renders.length, repeats: 0 });
      });
    });
});

describe("C8: the research checks are asked for when their fold is first opened", () => {
  it("sends no request for them while the fold stays closed", async () => {
    renderPage();
    await untilLoaded();
    expect(checksRequests()).toBe(0);
    expect(screen.queryByTestId("control-analyses-card")).toBeNull();
  });

  it("sends one request when the fold is opened, and shows the card", async () => {
    renderPage();
    await untilLoaded();
    fireEvent.click(screen.getByRole("button", { name: /Chance and current checks \(offline\)/ }));
    await waitFor(() => expect(screen.getByTestId("control-analyses-card")).toBeInTheDocument());
    expect(screen.getByTestId("control-analyses-card")).toHaveTextContent("Time of day and weekends");
    expect(checksRequests()).toBe(1);
    // Closing and opening again asks nothing more.
    fireEvent.click(screen.getByRole("button", { name: /Chance and current checks \(offline\)/ }));
    fireEvent.click(screen.getByRole("button", { name: /Chance and current checks \(offline\)/ }));
    await new Promise((r) => setTimeout(r, 20));
    expect(checksRequests()).toBe(1);
  });
});
