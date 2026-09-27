/**
 * The clinic-sheet export rebuilds the Stim Optimizer response from its own request
 * (`DataAnalysis.ExportTitrationSheet` hands `request.data` to `run_for_participant`). It sends the
 * page's own request, so it is answered from the stored response the page already built, not by a
 * full recompute under another key (before 2026-09-26 it sent the participant and date only, and
 * the server's default figure backend made it a different stored answer).
 */
import "@testing-library/jest-dom";
import { render as rtlRender, screen, fireEvent, waitFor } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";
import theme from "assets/theme";
import { PlatformContextProvider } from "context";
import { SessionController } from "database/session-control";
import TitrationSessionCard from "./TitrationSessionCard";
import { OPTIMIZER_REQUEST } from "./optimizerRequest";
import plan from "./__fixtures__/rcs08_titration_plan_exploratory.json";

jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn(() => Promise.resolve({
  headers: { "content-type": "application/json" },
  data: { text: () => Promise.resolve(JSON.stringify({ available: false, reason: "test" })) },
})) } }));

const wrap = (ui) => (
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>
);
const UID = "2e3c75c00d7f4f37b53a048d195f11da";

it("the sheet export sends the page's own request with the participant and the visit date", async () => {
  rtlRender(wrap(<TitrationSessionCard plan={plan} participantUid={UID} />));
  fireEvent.click(screen.getAllByRole("button", { name: /Make Google sheet/, hidden: true })[0]);
  await waitFor(() => expect(SessionController.query).toHaveBeenCalled());
  const [url, body] = SessionController.query.mock.calls[0];
  expect(url).toBe("/api/exportTitrationSheet");
  expect(body).toEqual(expect.objectContaining({ ...OPTIMIZER_REQUEST, ParticipantId: UID }));
  expect(body.Backend).toBe("none");
  expect(body.VisitDate).toMatch(/^\d{4}-\d{2}-\d{2}$/);
});
