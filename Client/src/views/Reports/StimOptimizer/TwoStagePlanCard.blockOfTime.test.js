/** Synthetic display-contract regression tests.
 * Independently authored examples; no participant responses or live scientific validation.
 */

import "@testing-library/jest-dom";
import { render as rtlRender } from "@testing-library/react";
import TwoStagePlanCard, { ACROSS_RATES_NOT_CHECKED } from "./TwoStagePlanCard";
import response from "./__fixtures__/synthetic_optimizer_basic.json";
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
