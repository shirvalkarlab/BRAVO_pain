/** Synthetic UI contract regression. No live participant response or empirical validation. */
import "@testing-library/jest-dom";
import { render as rtlRender, screen, fireEvent, within } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";
import theme from "assets/theme";
import { PlatformContextProvider } from "context";
import { SessionController } from "database/session-control";
import BandSweepGridPanel, { bandSelectionAnswer, chosenBySide, gridCentres } from "./BandSweepGridPanel";
import payload from "./__fixtures__/synthetic_provisional_grid.json";

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

test('actual source labels and explicit source refusals control selection without changing statistical gates',()=>{
 const chosen=jest.fn();
 const row={band_center_hz:12.5,pearson_r:0.3,can_choose_band:false,cannot_choose_why:'PSD-only cannot select',grid_source:'psd'};
 const sourceGrid={available:true,band_time_sweep:{ONE_THREE_LEFT:{display_hemisphere:'Left',display_short:'Left pair',grid_source:'psd',best_correlation_rows:[row],best_auc_rows:[{...row,auc:0.7}]}}};
 const {rerender}=render(<BandSweepGridPanel grid={sourceGrid} participantUid="synthetic" onCandidateChosen={chosen}/>);
 expect(screen.getByTestId('band-grid-source')).toHaveTextContent('PSD-only grid');
 expect(gridCentres(sourceGrid,'ONE_THREE_LEFT')).toEqual([]);
 const radio=screen.getByRole('radio');expect(radio).toBeDisabled();fireEvent.click(radio);expect(chosen).not.toHaveBeenCalled();
 const td={...sourceGrid,band_time_sweep:{ONE_THREE_LEFT:{...sourceGrid.band_time_sweep.ONE_THREE_LEFT,grid_source:'td',best_correlation_rows:[{...row,grid_source:'td',can_choose_band:true}],best_auc_rows:[]}}};
 rerender(<ThemeProvider theme={theme}><PlatformContextProvider initialStates={{darkMode:false}}><BandSweepGridPanel grid={td} participantUid="synthetic" onCandidateChosen={chosen}/></PlatformContextProvider></ThemeProvider>);
 expect(screen.getByTestId('band-grid-source')).toHaveTextContent('TD-only grid');
 expect(screen.getByRole('radio')).toBeEnabled();fireEvent.click(screen.getByRole('radio'));expect(chosen).toHaveBeenCalledWith(expect.objectContaining({centerHz:12.5}));
});

test('missing TD selection shows its actual reason instead of offering mixed fallback',()=>{
 render(<BandSweepGridPanel participantUid="synthetic" grid={{available:true,band_time_sweep:{ONE_THREE_LEFT:{display_hemisphere:'Left',choosing_grid:'none',choosing_grid_reason:'No TD-only evidence',best_correlation_rows:[],best_auc_rows:[]}}}}/>);
 expect(screen.getByTestId('band-grid-source')).toHaveTextContent('No TD-only evidence');
 expect(screen.queryByRole('radio')).not.toBeInTheDocument();
});
