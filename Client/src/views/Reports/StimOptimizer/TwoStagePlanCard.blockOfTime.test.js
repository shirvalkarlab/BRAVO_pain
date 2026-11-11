/**
 * The closed-loop card's folded table of fits prints a "best left / right current" per pulse-width
 * pairing, read from ONE fit pooled across every stimulation rate (on RCS08, 1.5 / 1.0 mA at
 * 55 Hz, 60/160 µs). Decision 253's block-of-time check is not run on that fit, because a stretch
 * of time held out of it is also a set of rates held out, and a miss could not be told apart from a
 * rate the fit had not learnt (the PI, 2026-09-25: "deal with the Q4 edge cases"). So the table
 * says, in plain words, that those currents are not checked and why, and carries no dagger; the
 * current the page recommends is read from each rate's own map, which is checked.
 *
 * Merged here 2026-10-05: TwoStagePlanCard.excludedRightPanel.test.js. Each merged file's tests
 * sit in a describe block named after it, with its reason above it.
 */

import "@testing-library/jest-dom";
import { render as rtlRender } from "@testing-library/react";
import TwoStagePlanCard, { ACROSS_RATES_NOT_CHECKED } from "./TwoStagePlanCard";
import response from "./__fixtures__/rcs08_stim_optimizer_two_stage.json";
import { wrap } from "testUtils/render";

describe("the table of fits pooled across rates", () => {
  it("says its best currents are not checked across blocks of time, and why", () => {
    const { container } = rtlRender(wrap(<TwoStagePlanCard plan={response.two_stage} loading={false} err={null} />));
    const t = container.textContent;
    expect(t).toContain("The fit for each pulse width and side");
    expect(t).toMatch(/best left current \(mA\)/i);   // PIN CHANGED 2026-09-26: headers are sentence case (SPEC.md section 7, WP5)
    expect(ACROSS_RATES_NOT_CHECKED).toMatch(/not checked across blocks of time/);
    expect(ACROSS_RATES_NOT_CHECKED).toMatch(/pooled across rates/);
    expect(ACROSS_RATES_NOT_CHECKED).toMatch(/held-out stretch is also a held-out rate/);
    expect(ACROSS_RATES_NOT_CHECKED).toMatch(/each rate's own map/);
    expect(t).toContain(ACROSS_RATES_NOT_CHECKED);
    expect(container.querySelectorAll('[data-testid="block-of-time-mark"]')).toHaveLength(0);
  });

  it("prints the sentence only where the table is drawn", () => {
    const plan = JSON.parse(JSON.stringify(response.two_stage));
    plan.stage1.strata = [];
    const { container } = rtlRender(wrap(<TwoStagePlanCard plan={plan} loading={false} err={null} />));
    expect(container.textContent).not.toContain("not checked across blocks of time");
  });
});

/* From TwoStagePlanCard.excludedRightPanel.test.js.
 * "Ruled-out settings, drawn" draws one panel per side, each with that side's per-pulse-
 * width best cells (grey marks labelled with the side's own pulse width). The strata list carries a
 * Left and a Right row per joint fit; the table of fits keeps one row per joint fit, but the drawing
 * needs both sides' rows, or the Right panel draws none of its own (found 2026-09-26).
 */
describe("from TwoStagePlanCard.excludedRightPanel", () => {
  const panelLabels = (container, side) => {
    const svg = container.querySelector(`svg[aria-label^="${side} side"]`);
    return svg ? Array.from(svg.querySelectorAll("text")).map((t) => t.textContent).filter((t) => /µs$/.test(t)) : null;
  };

  describe("the ruled-out settings drawing", () => {
    it("draws each side's own per-pulse-width best cells", () => {
      const { container } = rtlRender(wrap(<TwoStagePlanCard plan={response.two_stage} loading={false} err={null} />));
      const right = response.two_stage.stage1.strata.filter((r) => r.hemisphere === "Right").map((r) => `${r.pw_us.toFixed(0)} µs`);
      const left = response.two_stage.stage1.strata.filter((r) => r.hemisphere === "Left").map((r) => `${r.pw_us.toFixed(0)} µs`);
      expect(right.length).toBeGreaterThan(0);
      expect(panelLabels(container, "Right")).toEqual(expect.arrayContaining(right));
      expect(panelLabels(container, "Left")).toEqual(expect.arrayContaining(left));
    });

    it("keeps one row per joint fit in the table", () => {
      const { container } = rtlRender(wrap(<TwoStagePlanCard plan={response.two_stage} loading={false} err={null} />));
      const joint = new Set(response.two_stage.stage1.strata.map((r) => r.joint_stratum_key));
      const table = Array.from(container.querySelectorAll("table")).find((t) => /Left pulse width/.test(t.textContent));
      expect(table.querySelectorAll("tbody tr").length).toBe(joint.size);
    });
  });
});
