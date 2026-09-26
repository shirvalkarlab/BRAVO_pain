/**
 * The block-of-time mark beside every recommended current (the PI, 2026-09-25, answer 4 of the
 * revised plan: "Format elegantly (e.g., asterisks); label exists elsewhere").
 *
 * Decision 253 checks every fitted pain map (one per stimulation speed and pulse-width pairing):
 * held out one block of time at a time, does it still predict? Where its misses are shared by
 * whole blocks, the check's own label is "moves between blocks of time". Decision 275 then showed,
 * for the one map on RCS08 that reads so, that the movement is the whole group's readings moving
 * over those weeks, not something about one current. The page prints a small dagger beside a
 * recommended current whose map reads so, and one note per card saying what it means. It changes
 * no recommendation.
 *
 * Pinned here: the mark and its note appear only when the map the current is read from moves; a
 * map with another reading gets none; a map that was never checked says so rather than passing
 * silently; no recommended current means no mark, even on a map that moves (RCS08 today); one note
 * per card however many marks; the note follows decision 275, not 253's withdrawn sentence.
 */
import "@testing-library/jest-dom";
import { render as rtlRender } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";

import theme from "assets/theme";
import { PlatformContextProvider } from "context";

import DecisionStrip from "./DecisionStrip";
import CurrentMapCard from "./CurrentMapCard";
import { BLOCK_OF_TIME_VERDICT, blockOfTimeState, rateRowForSetting } from "./blockOfTime";
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
const calibration = (verdict) => ({ blocking: false, passes: false, diagnosis: { verdict, n_blocks: 3 } });
const marks = () => document.querySelectorAll('[data-testid="block-of-time-mark"]');
const notes = () => document.querySelectorAll('[data-testid="block-of-time-footnote"]');

/** The fixture's plan with the 55 Hz, 60/160 us REDCap map given `verdict` (null: no check on
 * the response) and, when `recommend`, a current recommended from it on both sides. */
function plan({ verdict, recommend }) {
  const p = clone(response.two_stage);
  p.stage1.rate_strata.forEach((r) => {
    if (r.fitted && r.rate_hz === 55 && r.pw_us_left === 60 && r.pw_us_right === 160) {
      if (verdict) r.calibration = calibration(verdict); else delete r.calibration;
      if (recommend) r.resolved = true;
    }
  });
  if (recommend) {
    p.stage1.frozen_configuration.settings.forEach((s) => {
      s.amplitude_preferred_mA = s.hemisphere === "Left" ? 3.5 : 3.5;
      s.resolved = true;
    });
  }
  return p;
}

describe("which map a recommended current is read from", () => {
  it("finds the row at the chosen rate and the chosen pulse-width PAIR", () => {
    const p = plan({ verdict: BLOCK_OF_TIME_VERDICT, recommend: true });
    const left = p.stage1.frozen_configuration.settings.find((s) => s.hemisphere === "Left");
    const row = rateRowForSetting(p, left);
    expect(row.rate_hz).toBe(55);
    expect([row.pw_us_left, row.pw_us_right]).toEqual([60, 160]);
  });

  it("reads the check's own label, in three states", () => {
    expect(blockOfTimeState({ calibration: calibration(BLOCK_OF_TIME_VERDICT) })).toBe("moves");
    expect(blockOfTimeState({ calibration: calibration("honest but uninformative: thin data") })).toBe("checked");
    expect(blockOfTimeState({ fitted: true })).toBe("not checked");
    expect(blockOfTimeState(null)).toBe("not checked");
  });
});

describe("the decision strip", () => {
  it("marks each side's recommended current when its map moves, with one note", () => {
    rtlRender(wrap(<DecisionStrip arms={{}} plan={plan({ verdict: BLOCK_OF_TIME_VERDICT, recommend: true })}
      inForce={response.in_force_by_side} />));
    expect(marks()).toHaveLength(2);
    expect(notes()).toHaveLength(1);
    const t = notes()[0].textContent;
    expect(t).toContain("moves between blocks of time");
    expect(t).toContain("whole group");
    expect(t).toContain("regression to the mean or a shared calendar effect");
    expect(t).toContain("changes no recommendation");
    // decision 253's sentence, withdrawn by decision 275
    expect(t).not.toMatch(/response to it did/);
  });

  it("prints no mark and no note when the map has another reading", () => {
    rtlRender(wrap(<DecisionStrip arms={{}} plan={plan({ verdict: "calibrated", recommend: true })}
      inForce={response.in_force_by_side} />));
    expect(marks()).toHaveLength(0);
    expect(notes()).toHaveLength(0);
  });

  it("prints no mark where no current is recommended, even on a map that moves (RCS08 today)", () => {
    rtlRender(wrap(<DecisionStrip arms={{}} plan={plan({ verdict: BLOCK_OF_TIME_VERDICT, recommend: false })}
      inForce={response.in_force_by_side} />));
    expect(marks()).toHaveLength(0);
    expect(notes()).toHaveLength(0);
  });

  it("says a recommended current's map was not checked, rather than passing it silently", () => {
    rtlRender(wrap(<DecisionStrip arms={{}} plan={plan({ verdict: null, recommend: true })}
      inForce={response.in_force_by_side} />));
    expect(marks()).toHaveLength(0);
    expect(document.body.textContent).toContain("not checked for movement between blocks of time");
  });
});

describe("the current map card", () => {
  // PIN CHANGED 2026-09-26: "at this rate", never "at this speed" (the design review).
  function mapPlan(verdict, { clinicToo = false, resolved = true } = {}) {
    const p = plan({ verdict, recommend: false });
    p.stage1.rate_strata.forEach((r) => { if (r.fitted && r.rate_hz === 55) r.resolved = resolved; });
    if (clinicToo) {
      p.stage1.rate_strata_clinic.forEach((r) => {
        if (r.fitted && r.rate_hz === 55) { r.resolved = true; r.calibration = calibration(verdict); }
      });
    }
    return p;
  }

  it("names the recommended current and marks it when its map moves", () => {
    rtlRender(wrap(<CurrentMapCard plan={mapPlan(BLOCK_OF_TIME_VERDICT)} />));
    // a number and its unit are joined by a narrow no-break space when drawn
    expect(document.body.textContent.replace(/\u202f/g, " "))
      .toContain("a current CAN be recommended at this rate: left 3.5 mA, right 3.5 mA");
    expect(marks()).toHaveLength(1);
    expect(notes()).toHaveLength(1);
  });

  it("keeps ONE note per card when the REDCap and the clinic maps both move", () => {
    rtlRender(wrap(<CurrentMapCard plan={mapPlan(BLOCK_OF_TIME_VERDICT, { clinicToo: true })} />));
    expect(marks()).toHaveLength(2);
    expect(notes()).toHaveLength(1);
  });

  it("prints no mark when the map has another reading", () => {
    rtlRender(wrap(<CurrentMapCard plan={mapPlan("honest but uninformative: thin data")} />));
    expect(marks()).toHaveLength(0);
    expect(notes()).toHaveLength(0);
  });

  it("prints no mark on a map that moves but recommends no current", () => {
    rtlRender(wrap(<CurrentMapCard plan={mapPlan(BLOCK_OF_TIME_VERDICT, { resolved: false })} />));
    expect(marks()).toHaveLength(0);
    expect(notes()).toHaveLength(0);
  });
});
