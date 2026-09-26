/**
 * The block-of-time mark on the maps POOLED ACROSS PULSE WIDTHS (the PI, 2026-09-25: "deal with the
 * Q4 edge cases"). Since the server runs decision 253's check on those maps too (REDCap, decision
 * 222; clinic stream, decision 255), a current recommended from one is marked exactly as one from a
 * per-pairing map: the dagger when its map moves between blocks of time, nothing when it was checked
 * and reads otherwise. "Not checked" is kept for a map with no check on the response, and for a
 * check that ran and could not reach a reading, which then says why.
 */
import "@testing-library/jest-dom";
import { render as rtlRender, screen, fireEvent } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";

import theme from "assets/theme";
import { PlatformContextProvider } from "context";

import CurrentMapCard from "./CurrentMapCard";
import { BLOCK_OF_TIME_VERDICT, blockOfTimeState, notCheckedText } from "./blockOfTime";
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
const clone = (x) => JSON.parse(JSON.stringify(x));
const marks = () => document.querySelectorAll('[data-testid="block-of-time-mark"]');
const notes = () => document.querySelectorAll('[data-testid="block-of-time-footnote"]');
const text = () => document.body.textContent.replace(/ /g, " ");
const NOT_COMPUTABLE = { blocking: false, passes: null,
  diagnosis: { verdict: null, n_blocks: 1, reason: "not computable: fewer than two blocks of time to hold out" } };
const cal = (verdict) => (verdict === "none" ? undefined
  : verdict === "not computable" ? NOT_COMPUTABLE
    : { blocking: false, passes: false, diagnosis: { verdict, n_blocks: 3 } });

/** The fixture with a pooled-over-pulse-widths row at 55 Hz on the REDCap stream (and, with
 * `clinic`, on the clinic stream), recommending 3.5 / 3.0 mA, its check reading `verdict`
 * ("none": no check on the row). Every per-pairing row is left unrecommended, so any mark or
 * "not checked" on the card comes from the pooled row. */
function pooledPlan(verdict, { clinic = false } = {}) {
  const p = clone(response.two_stage);
  const s1 = p.stage1;
  const fitted = s1.rate_strata.find((r) => r.fitted && r.rate_hz === 55);
  s1.rate_strata.forEach((r) => { r.resolved = false; delete r.calibration; });
  (s1.rate_strata_clinic || []).forEach((r) => { r.resolved = false; delete r.calibration; });
  const row = {
    ...clone(fitted), pooled_pulse_widths: true, n_pairings_pooled: 2, resolved: true,
    amp_mA_left: 3.5, amp_mA_right: 3.0,
    pairings: [{ pw_us_left: 60, pw_us_right: 160, n_epochs: 17, n_reports: 120 },
      { pw_us_left: 100, pw_us_right: 150, n_epochs: 10, n_reports: 60 }],
  };
  delete row.calibration;
  const c = cal(verdict);
  if (c) row.calibration = c;
  const block = { available: true, default: "separate", note: "pooled", rate_strata_pooled: [row],
    in_force_pairing: { pw_us_left: 60, pw_us_right: 160 } };
  s1.pulse_width_pooling = block;
  s1.pulse_width_pooling_clinic = clinic ? clone(block) : { available: false, reason: "not in this test", rate_strata_pooled: [] };
  return p;
}

function showPooled(plan) {
  rtlRender(wrap(<CurrentMapCard plan={plan} />));
  fireEvent.click(screen.getByRole("button", { name: /Pool pulse widths/ }));
}

describe("the three readings of one row", () => {
  it("tells a check that ran and reached no reading from one that never ran", () => {
    expect(blockOfTimeState({ calibration: NOT_COMPUTABLE })).toBe("not computable");
    expect(notCheckedText({ calibration: NOT_COMPUTABLE }))
      .toBe("not checked for movement between blocks of time: fewer than two blocks of time to hold out");
    expect(notCheckedText({ fitted: true })).toBe("not checked for movement between blocks of time");
    expect(notCheckedText({ calibration: cal("calibrated") })).toBeNull();
    expect(notCheckedText({ calibration: cal(BLOCK_OF_TIME_VERDICT) })).toBeNull();
  });
});

describe("the current map card, pulse widths pooled", () => {
  it("marks a current read from a pooled map that moves, with one note", () => {
    showPooled(pooledPlan(BLOCK_OF_TIME_VERDICT));
    expect(text()).toContain("a current CAN be recommended at this speed: left 3.5 mA, right 3.0 mA");
    expect(marks()).toHaveLength(1);
    expect(notes()).toHaveLength(1);
    expect(text()).not.toContain("not checked for movement between blocks of time");
  });

  it("prints nothing beside a current read from a pooled map that was checked and holds", () => {
    showPooled(pooledPlan("honest but uninformative: thin data"));
    expect(text()).toContain("a current CAN be recommended at this speed: left 3.5 mA, right 3.0 mA.");
    expect(marks()).toHaveLength(0);
    expect(notes()).toHaveLength(0);
    expect(text()).not.toContain("not checked for movement between blocks of time");
  });

  it("marks the clinic stream's pooled map too, keeping one note per card", () => {
    showPooled(pooledPlan(BLOCK_OF_TIME_VERDICT, { clinic: true }));
    expect(marks()).toHaveLength(2);
    expect(notes()).toHaveLength(1);
  });

  it("says a pooled map was not checked only when the response carries no check for it", () => {
    showPooled(pooledPlan("none"));
    expect(marks()).toHaveLength(0);
    expect(text()).toContain("left 3.5 mA, right 3.0 mA (not checked for movement between blocks of time).");
  });

  it("gives the reason when the check ran and could not reach a reading", () => {
    showPooled(pooledPlan("not computable"));
    expect(marks()).toHaveLength(0);
    expect(text()).toContain("(not checked for movement between blocks of time: fewer than two blocks of time to hold out).");
  });
});
