/**
 * Band selection in two columns, one per side (the PI, 2026-10-08: "if the user chooses left and
 * right independently, there should be a band selection option, one from each side ... horizontally
 * compressed"). Each side has its own contact-pair tabs and its own "Use" radio; a side the
 * sense-to-control wiring does not read is greyed and cannot be ticked.
 */
import "@testing-library/jest-dom";
import { render as rtlRender, screen, fireEvent, within } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";
import theme from "assets/theme";
import { PlatformContextProvider } from "context";
import { SessionController } from "database/session-control";
import BandSweepGridPanel, { bandSelectionAnswer, chosenBySide } from "./BandSweepGridPanel";
import payload from "./__fixtures__/rcs08_deployment_payload_2026-09-15.json";

jest.mock("plotly.js-dist", () => ({
  react: jest.fn(), purge: jest.fn(), restyle: jest.fn(), relayout: jest.fn(), newPlot: jest.fn(),
}));
jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn() } }));

const render = (ui) => rtlRender(
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>,
);
const grid = payload.band_sweep_grid;
const sweeps = grid.band_time_sweep;
const label = (ch) => sweeps[ch].display_short;

beforeEach(() => {
  window.localStorage.clear();
  SessionController.query.mockReset();
  SessionController.query.mockImplementation(() => Promise.resolve({ data: { saved: false, reason: "test" } }));
});

test("each side has its own column, its own tabs and its own chosen band", () => {
  render(<BandSweepGridPanel grid={grid} participantUid="uid"
    committed={{ contact: "ONE_THREE_LEFT", centerHz: 24.5 }}
    committedBySide={{ Left: { contact: "ONE_THREE_LEFT", centerHz: 24.5 },
      Right: { contact: "ZERO_THREE_RIGHT", centerHz: 18.5 } }}
    onCandidateChosen={() => {}} />);
  const left = screen.getByTestId("band-side-Left");
  const right = screen.getByTestId("band-side-Right");
  // the left column holds only left pairs, the right only right
  expect(within(left).getByRole("group", { name: "Left sensing contact pair" })).toBeInTheDocument();
  expect(within(left).queryByRole("button", { name: new RegExp(`^${label("ZERO_THREE_RIGHT")}`) })).toBeNull();
  expect(within(right).queryByRole("button", { name: new RegExp(`^${label("ONE_THREE_LEFT")}`) })).toBeNull();
  expect(within(left).getByTestId("band-side-Left-chosen"))
    .toHaveTextContent(`Chosen: ${label("ONE_THREE_LEFT")} at 24.5 Hz`);
  expect(within(right).getByTestId("band-side-Right-chosen"))
    .toHaveTextContent(`Chosen: ${label("ZERO_THREE_RIGHT")} at 18.5 Hz`);
  // one radio ticked per side
  expect(within(left).getAllByRole("radio").filter((r) => r.checked)).toHaveLength(1);
  expect(within(right).getAllByRole("radio").filter((r) => r.checked)).toHaveLength(1);
  expect(screen.getByTestId("band-selection-answer")).toHaveTextContent(
    `Left: ${label("ONE_THREE_LEFT")} at 24.5 Hz · Right: ${label("ZERO_THREE_RIGHT")} at 18.5 Hz. `
    + `The sections below the decision describe ${label("ONE_THREE_LEFT")} at 24.5 Hz, the band ticked last.`);
});

test("ticking a band on the right records it as a right band, leaving the left column alone", () => {
  const chosen = jest.fn();
  render(<BandSweepGridPanel grid={grid} participantUid="uid"
    committed={{ contact: "ONE_THREE_LEFT", centerHz: 24.5 }} onCandidateChosen={chosen} />);
  const right = screen.getByTestId("band-side-Right");
  fireEvent.click(within(right).getAllByRole("radio")[3]);
  expect(chosen).toHaveBeenCalledTimes(1);
  expect(chosen.mock.calls[0][0].sensingHemisphere).toBe("Right");
  const [, body] = SessionController.query.mock.calls[0];
  expect(body.BandCandidate.hemisphere).toBe("Right");
  expect(within(screen.getByTestId("band-side-Left")).getAllByRole("radio").filter((r) => r.checked))
    .toHaveLength(1);
});

test("a side the wiring does not read is greyed, cannot be ticked, and says why", () => {
  const chosen = jest.fn();
  render(<BandSweepGridPanel grid={grid} participantUid="uid"
    committed={{ contact: "ONE_THREE_LEFT", centerHz: 24.5 }} activeSides={["Left"]}
    offNote="Not used: left sensing drives both stimulators." onCandidateChosen={chosen} />);
  const right = screen.getByTestId("band-side-Right");
  expect(right).toHaveAttribute("aria-disabled", "true");
  within(right).getAllByRole("radio").forEach((r) => expect(r).toBeDisabled());
  expect(within(right).getByTestId("band-side-Right-off"))
    .toHaveTextContent("Not used: left sensing drives both stimulators.");
  expect(screen.getByTestId("band-side-Left")).toHaveAttribute("aria-disabled", "false");
  expect(screen.getByTestId("band-selection-answer"))
    .toHaveTextContent(`Left: ${label("ONE_THREE_LEFT")} at 24.5 Hz.`);
});

test("the answer line with nothing chosen, and with one side only", () => {
  const lab = (ch) => ch;
  const none = { Left: null, Right: null };
  expect(bandSelectionAnswer(none, null, lab, null))
    .toBe("No band chosen yet: tick one to check it against the device and the evidence below.");
  const one = { Left: { contact: "L13", centerHz: 24.5 }, Right: null };
  expect(bandSelectionAnswer(one, one.Left, lab, null)).toBe("Left: L13 at 24.5 Hz · Right: none chosen.");
});

test("the page's band counts for its own side", () => {
  const sideOf = (ch) => (/LEFT/.test(ch) ? "Left" : "Right");
  expect(chosenBySide({ contact: "ONE_THREE_LEFT", centerHz: 24.5 }, null, sideOf))
    .toEqual({ Left: { contact: "ONE_THREE_LEFT", centerHz: 24.5 }, Right: null });
});
