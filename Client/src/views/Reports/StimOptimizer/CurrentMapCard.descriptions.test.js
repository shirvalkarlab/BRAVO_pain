/**
 * S5 of the 2026-09-15 review, in the PI's shape of 2026-09-17: the current-map card's prose is
 * folded behind one "Expand descriptions" push-button (as on the Biomarkers binarization card),
 * and among the folded lines is ONE succinct sentence naming which pulse-width pairings the
 * REDCap stream and the clinic-sheet stream were each fitted at -- so "no current, both streams"
 * is not read as two measurements of one configuration. Rendered against the live RCS08 fixture.
 */
import "@testing-library/jest-dom";
import { render as rtlRender, screen, fireEvent } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";
import theme from "assets/theme";
import { PlatformContextProvider } from "context";
import CurrentMapCard, { pulseWidthPairingSentence } from "./CurrentMapCard";
import response from "./__fixtures__/rcs08_stim_optimizer_two_stage.json";

jest.mock("plotly.js-dist", () => {
  const noop = () => {};
  return { react: () => Promise.resolve(), purge: noop, restyle: noop, relayout: noop, newPlot: noop };
});
jest.mock("graphing-utility/Plotly", () => ({
  PlotlyRenderManager: class {
    constructor() { this.traces = []; this.layout = {}; }
    subplots() {} clearData() {} render() {} setLayoutProps() {} setXlabel() {} setYlabel() {}
    addHeatmap() {} addScatter() {} addShape() {} addAnnotation() {} setTitle() {}
  },
}));

const wrap = (ui) => (
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>
);
const plan = response.two_stage;

describe("the pulse-width pairing sentence (S5)", () => {
  it("names the pairings fitted in both streams and in one only, from the fitted strata", () => {
    const s = pulseWidthPairingSentence(plan.stage1.rate_strata, plan.stage1.rate_strata_clinic);
    expect(s).toBe("Pulse-width pairings fitted: both streams 60/160 µs; REDCap only 140/180 µs; sheets only 100/100 µs.");
  });
  it("says so when the two streams share no pairing", () => {
    const s = pulseWidthPairingSentence(
      [{ pw_us_left: 60, pw_us_right: 160, fitted: true }], [{ pw_us_left: 100, pw_us_right: 100, fitted: true }]);
    expect(s).toBe("Pulse-width pairings fitted: none in both streams; REDCap only 60/160 µs; sheets only 100/100 µs.");
  });
});

describe("the card's prose folds behind one push-button", () => {
  it("shows no description on load, and every description after one click", () => {
    rtlRender(wrap(<CurrentMapCard plan={plan} />));
    expect(screen.queryByText(/Each square below is one stimulation speed/)).toBeNull();
    expect(screen.queryByText(/Pulse-width pairings fitted:/)).toBeNull();
    expect(screen.queryByText(/These scores come from the lab's testing workbooks/)).toBeNull();
    const btn = screen.getByRole("button", { name: /Expand descriptions/ });
    fireEvent.click(btn);
    expect(screen.getByText(/Each square below is one stimulation speed/)).toBeInTheDocument();
    expect(screen.getByText(/Pulse-width pairings fitted: both streams 60\/160 µs/)).toBeInTheDocument();
    expect(screen.getByText(/These scores come from the lab's testing workbooks/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Collapse descriptions/ })).toBeInTheDocument();
  });
  it("keeps the values visible while folded: the per-rate lines and the three checks", () => {
    rtlRender(wrap(<CurrentMapCard plan={plan} />));
    expect(screen.getAllByText(/epochs · \d+ reports/).length).toBeGreaterThan(0);
    expect(screen.getByText(/Where the two currents have been tried/)).toBeInTheDocument();
  });
});
