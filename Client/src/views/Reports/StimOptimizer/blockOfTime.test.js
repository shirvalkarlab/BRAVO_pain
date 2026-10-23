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
 *
 * Merged here 2026-10-05: blockOfTime.pooledFits.test.js. Each merged file's tests sit in a
 * describe block named after it, with its reason above it.
 */

import "@testing-library/jest-dom";
import { fireEvent, render as rtlRender, screen } from "@testing-library/react";
import DecisionStrip from "./DecisionStrip";
import CurrentMapCard from "./CurrentMapCard";
import { BLOCK_OF_TIME_VERDICT, blockOfTimeState, notCheckedText, rateRowForSetting } from "./blockOfTime";
import response from "./__fixtures__/rcs08_stim_optimizer_two_stage.json";
import { clone, wrap } from "testUtils/render";

jest.mock("plotly.js-dist", () => require("testUtils/plotlyStubs").plotlyNoop());
jest.mock("graphing-utility/Plotly", () => require("testUtils/plotlyStubs").renderManagerStub());

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

/* From blockOfTime.pooledFits.test.js.
 * The block-of-time mark on the maps POOLED ACROSS PULSE WIDTHS (the PI, 2026-09-25: "deal with the
 * Q4 edge cases"). Since the server runs decision 253's check on those maps too (REDCap, decision
 * 222; clinic stream, decision 255), a current recommended from one is marked exactly as one from a
 * per-pairing map: the dagger when its map moves between blocks of time, nothing when it was checked
 * and reads otherwise. "Not checked" is kept for a map with no check on the response, and for a
 * check that ran and could not reach a reading, which then says why.
 */
describe("from blockOfTime.pooledFits", () => {
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
    // PIN CHANGED 2026-09-26: "at this rate", never "at this speed" (the design review).
    it("marks a current read from a pooled map that moves, with one note", () => {
      showPooled(pooledPlan(BLOCK_OF_TIME_VERDICT));
      expect(text()).toContain("a current CAN be recommended at this rate: left 3.5 mA, right 3.0 mA");
      expect(marks()).toHaveLength(1);
      expect(notes()).toHaveLength(1);
      expect(text()).not.toContain("not checked for movement between blocks of time");
    });

    it("prints nothing beside a current read from a pooled map that was checked and holds", () => {
      showPooled(pooledPlan("honest but uninformative: thin data"));
      expect(text()).toContain("a current CAN be recommended at this rate: left 3.5 mA, right 3.0 mA.");
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
});
