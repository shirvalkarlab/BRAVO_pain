/**
 * The research checks are asked for the first time their fold is opened (speed-up item C8,
 * 2026-10-02). `ControlAnalysesSection` reads the same "has the enclosing fold ever been opened"
 * answer the Stim Optimizer's current map reads (`paper/Section`'s `SectionRevealedContext`): while
 * it is "not yet" nothing is requested; once it is "yes" the saved checks are asked for once.
 * Outside any fold the answer is "yes", so the card loads at once exactly as before.
 *
 * The Stim Optimizer page's fold is checked by rendering that page
 * (`StimOptimizer/StimOptimizer.speed.test.js`); the Biomarkers page, which needs far more to
 * render, is checked here on its source.
 */
import "@testing-library/jest-dom";
import fs from "fs";
import path from "path";
import { render, screen, waitFor } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";

import theme from "assets/theme";
import { PlatformContextProvider } from "context";
import { SectionRevealedContext } from "views/Reports/paper/Section";

jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn() } }));

// eslint-disable-next-line import/first
import { SessionController } from "database/session-control";
// eslint-disable-next-line import/first
import { ControlAnalysesSection } from "./ControlAnalysesCard";

const CHECKS = { page: "biomarkers", analyses: [{ key: "time_of_day", title: "Time of day and weekends",
  what: "Clock and weekend.", literature: [], n_runs: 0, snapshot: null }] };

const wrap = (ui) => (
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>
);
const inFold = (opened) => wrap(
  <SectionRevealedContext.Provider value={opened}>
    <ControlAnalysesSection participantUid="U1" page="biomarkers" plain />
  </SectionRevealedContext.Provider>);

beforeEach(() => {
  SessionController.query.mockReset();
  SessionController.query.mockImplementation(() => Promise.resolve({ data: CHECKS }));
});

it("outside any fold, the saved checks are asked for at once, as before", async () => {
  render(wrap(<ControlAnalysesSection participantUid="U1" page="biomarkers" />));
  await waitFor(() => expect(screen.getByTestId("control-analyses-card")).toBeInTheDocument());
  expect(SessionController.query).toHaveBeenCalledTimes(1);
  expect(SessionController.query).toHaveBeenCalledWith("/api/queryControlAnalyses",
    { ParticipantId: "U1", Page: "biomarkers" });
});

it("in a fold never opened, nothing is asked for; on the first opening, once", async () => {
  const { rerender } = render(inFold(false));
  await new Promise((r) => setTimeout(r, 20));
  expect(SessionController.query).not.toHaveBeenCalled();
  rerender(inFold(true));
  await waitFor(() => expect(screen.getByTestId("control-analyses-card")).toBeInTheDocument());
  expect(screen.getByTestId("control-analyses-card")).toHaveTextContent("Time of day and weekends");
  expect(SessionController.query).toHaveBeenCalledTimes(1);
});

it("says it is reading while the request is out, rather than showing an empty fold", async () => {
  let release;
  SessionController.query.mockImplementation(() => new Promise((r) => { release = r; }));
  render(inFold(true));
  expect(screen.getByText("Reading the saved checks…")).toBeInTheDocument();
  release({ data: CHECKS });
  await waitFor(() => expect(screen.getByTestId("control-analyses-card")).toBeInTheDocument());
  expect(screen.queryByText("Reading the saved checks…")).toBeNull();
});

it("the Biomarkers page tells the section whether its fold has been opened", () => {
  const src = fs.readFileSync(path.join(__dirname, "..", "Biomarkers", "index.js"), "utf8");
  // The fold records its first opening ...
  expect(src).toMatch(/hide="Hide the checks against chance and against the current"\s*\n\s*onChange=\{\(open\) => \{ if \(open\) setChecksOpened\(true\); \}\}>/);
  // ... and the section sits directly inside a provider carrying that answer.
  expect(src).toMatch(/<SectionRevealedContext\.Provider value=\{checksOpened\}>\s*\n\s*<ControlAnalysesSection participantUid=\{participant_uid\} page="biomarkers" clinicSheets=\{includeClinicSheetRatings\} plain \/>\s*\n\s*<\/SectionRevealedContext\.Provider>/);
  expect(src).toMatch(/const \[checksOpened, setChecksOpened\] = useState\(false\);/);
});
