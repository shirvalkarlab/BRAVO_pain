/**
 * Decision 189's option A behind a toggle (the PI, 2026-09-21): the current-map card draws the
 * per-pairing fit by default and, on one push-button, the fit pooled over every pulse-width
 * pairing (one surface per stimulation speed, read at the pairing in force). Rendered against
 * the live RCS08 fixture plus a pooling block built from its own fitted 55 Hz row.
 */
import "@testing-library/jest-dom";
import { render as rtlRender, screen, fireEvent } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";
import theme from "assets/theme";
import { PlatformContextProvider } from "context";
import CurrentMapCard from "./CurrentMapCard";
import response from "./__fixtures__/rcs08_stim_optimizer_two_stage.json";

jest.mock("plotly.js-dist", () => {
  const noop = () => {};
  return { react: () => Promise.resolve(), purge: noop, restyle: noop, relayout: noop, newPlot: noop };
});
jest.mock("graphing-utility/Plotly", () => ({
  PlotlyRenderManager: class {
    constructor() { this.traces = []; this.layout = {}; }
    subplots() {} clearData() {} render() {} setLayoutProps() {} setXlabel() {} setYlabel() {}
    addHeatmap() {} addScatter() {} addShape() {} addAnnotation() {} setTitle() {} purge() {}
  },
}));

const wrap = (ui) => (
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>
);

const NOTE = "Pooling fits one surface per stimulation speed over every pulse-width pairing, with the two pulse widths as inputs, and reads it at the pairing in force: more ratings per fit, and the coverage check counts current pairs across pairings, which is why it resolves more often. It assumes the current-to-pain shape is shared across pairings. The separate fit is the default; the toggle shows the pooled one.";

function planWithPooling() {
  const base = response.two_stage;
  const fitted = base.stage1.rate_strata.find((r) => r.fitted && r.rate_hz === 55);
  const pooledRow = {
    ...fitted, pw_us_left: 60, pw_us_right: 160, pooled_pulse_widths: true, n_pairings_pooled: 3,
    n_epochs: 41, n_reports: 250,
    pairings: [{ pw_us_left: 60, pw_us_right: 160, n_epochs: 17, n_reports: 120 },
      { pw_us_left: 100, pw_us_right: 100, n_epochs: 12, n_reports: 70 },
      { pw_us_left: 140, pw_us_right: 180, n_epochs: 12, n_reports: 60 }],
    surface: { ...fitted.surface, points: fitted.surface.points.map((p) => ({ ...p, pw_us_left: 60, pw_us_right: 160 })) },
  };
  const unfitted = { pw_us_left: 60, pw_us_right: 160, rate_hz: 165, fitted: false, n_epochs: 4,
    pooled_pulse_widths: true, n_pairings_pooled: 2, pairings: [],
    reason: "4 epochs over every pulse-width pairing, below the 8-epoch floor" };
  return { ...base, stage1: { ...base.stage1, pulse_width_pooling: {
    available: true, default: "separate", note: NOTE, in_force_pairing: { pw_us_left: 60, pw_us_right: 160 },
    n_rates: 2, n_rates_fitted: 1, rate_strata_pooled: [pooledRow, unfitted] } } };
}

describe("CurrentMapCard: pooling across pulse widths behind a toggle", () => {
  it("draws the separate fit on load, with the toggle offering the pooled one", () => {
    rtlRender(wrap(<CurrentMapCard plan={planWithPooling()} />));
    const t = document.body.textContent;
    expect(t).toContain("left pulse width 60\u202f\u00b5s · right pulse width 160\u202f\u00b5s");
    expect(t).toContain("left pulse width 140\u202f\u00b5s · right pulse width 180\u202f\u00b5s");
    expect(t).not.toMatch(/pooled over/i);
    expect(screen.getByRole("button", { name: /Pool pulse widths/ })).toBeInTheDocument();
  });

  it("one click shows the pooled fit: one group at the pairing in force, its pairings named, the assumption stated", () => {
    rtlRender(wrap(<CurrentMapCard plan={planWithPooling()} />));
    fireEvent.click(screen.getByRole("button", { name: /Pool pulse widths/ }));
    const t = document.body.textContent;
    expect(t).toContain("pooled over 3 pulse-width pairings, read at left 60\u202f\u00b5s / right 160\u202f\u00b5s");
    expect(t).toContain("60/160\u202f\u00b5s (17 epochs), 100/100\u202f\u00b5s (12 epochs), 140/180\u202f\u00b5s (12 epochs)");
    expect(t).toContain("41 epochs · 250 reports");
    expect(t).toContain("165\u202fHz · 4 epochs");        // the unfitted pooled rate still says so
    expect(t).toMatch(/assumes the current-to-pain shape is shared across pairings/i);
    expect(t).not.toContain("left pulse width 140\u202f\u00b5s · right pulse width 180\u202f\u00b5s");
    expect(screen.getByRole("button", { name: /Keep pulse widths separate/ })).toBeInTheDocument();
  });

  it("a second click restores the separate fit", () => {
    rtlRender(wrap(<CurrentMapCard plan={planWithPooling()} />));
    fireEvent.click(screen.getByRole("button", { name: /Pool pulse widths/ }));
    fireEvent.click(screen.getByRole("button", { name: /Keep pulse widths separate/ }));
    expect(document.body.textContent).toContain("left pulse width 140\u202f\u00b5s · right pulse width 180\u202f\u00b5s");
    expect(document.body.textContent).not.toMatch(/pooled over/i);
  });

  it("offers no toggle when the response carries no pooled fit, and says why under the descriptions", () => {
    const plan = response.two_stage;   // the fixture predates the block
    rtlRender(wrap(<CurrentMapCard plan={plan} />));
    expect(screen.queryByRole("button", { name: /Pool pulse widths/ })).toBeNull();
    const plan2 = { ...plan, stage1: { ...plan.stage1, pulse_width_pooling: { available: false, default: "separate",
      reason: "the pulse-width pairing in force is not known", rate_strata_pooled: [] } } };
    rtlRender(wrap(<CurrentMapCard plan={plan2} />));
    expect(screen.queryByRole("button", { name: /Pool pulse widths/ })).toBeNull();
    fireEvent.click(screen.getAllByRole("button", { name: /Expand descriptions/ })[1]);
    expect(document.body.textContent).toContain("the pulse-width pairing in force is not known");
  });
});
