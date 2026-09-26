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

describe("the card's prose folds behind one push-button, except the legend", () => {
  // THE LEGEND IS OPEN ON LOAD (the PI, 2026-09-23, amending his S5 ruling of 2026-09-17 for this
  // one paragraph; panel C item 5, report C §5.3): what the colours, the cross, the dots and the
  // star mean is needed to read the squares at all. Every other description stays folded.
  it("shows the legend on load and no other description, and every description after one click", () => {
    rtlRender(wrap(<CurrentMapCard plan={plan} />));
    expect(screen.getByText(/Each square below is one stimulation rate/)).toBeInTheDocument(); // PIN CHANGED 2026-09-26 (the design review, the PI's "yes to all six"): "rate", never "speed"
    expect(screen.queryByText(/Pulse-width pairings fitted:/)).toBeNull();
    expect(screen.queryByText(/These scores come from the lab's testing workbooks/)).toBeNull();
    const btn = screen.getByRole("button", { name: /Expand descriptions/ });
    fireEvent.click(btn);
    expect(screen.getByText(/Each square below is one stimulation rate/)).toBeInTheDocument(); // PIN CHANGED 2026-09-26 (the design review, the PI's "yes to all six"): "rate", never "speed"
    expect(screen.getByText(/Pulse-width pairings fitted: both streams 60\/160 µs/)).toBeInTheDocument();
    expect(screen.getByText(/These scores come from the lab's testing workbooks/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Collapse descriptions/ })).toBeInTheDocument();
  });
  it("keeps the values visible while folded: the per-rate lines and the three checks", () => {
    rtlRender(wrap(<CurrentMapCard plan={plan} />));
    // PIN CHANGED 2026-09-26 (the design review, the PI's "yes to all six"): "stretches", never "epochs"
    expect(screen.getAllByText(/stretches · \d+ reports/).length).toBeGreaterThan(0);
    expect(screen.getByText(/Where the two currents have been tried/)).toBeInTheDocument();
  });
});

describe("absolute numbers on the squares, colour centred on today (the PI, 2026-09-17)", () => {
  const { absoluteSurface } = require("./CurrentMapCard");
  it("adds the rating at the setting in force back to every cell and centres the scale on it", () => {
    const s = { mu: [[0, -1.5], [2, 0.5]], safe: [[true, true], [true, false]], pain_reference: 5.25, pain_item: "left_leg_vas" };
    const a = absoluteSurface(s);
    expect(a.z).toEqual([[5.25, 3.75], [7.25, null]]);
    expect(a.zmid).toBe(5.25);
    expect(a.zmin).toBeLessThanOrEqual(3.75);
    expect(a.zmax).toBeGreaterThanOrEqual(7.25);
    expect(a.zmax - a.zmid).toBeCloseTo(a.zmid - a.zmin, 9);   // symmetric, so the grey midpoint IS today's value
    expect(a.title).toMatch(/predicted .*rating/);
    expect(a.title).not.toMatch(/score/);
  });
  it("an older response with no reference still draws, as the relative score it always was", () => {
    const a = absoluteSurface({ mu: [[0, -1]], safe: [[true, true]] });
    expect(a.z).toEqual([[0, -1]]);
    expect(a.zmid).toBe(0);
    expect(a.title).toBe("score (lower is better)");
  });
  // PIN CHANGED 2026-09-26: the scale is blue - light grey - orange (colour-blind safe), so the
  // midpoint that means "today" is light grey, not yellow.
  it("the intro says light grey is today's predicted rating, not that zero is the score", () => {
    rtlRender(wrap(<CurrentMapCard plan={plan} />));
    fireEvent.click(screen.getByRole("button", { name: /Expand descriptions/ }));
    expect(screen.getAllByText(/light grey is the predicted rating at the setting programmed today/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText(/zero, on the colour scale/)).toBeNull();
  });
});
