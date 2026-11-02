/** Synthetic rendering contracts; no participant observations or empirical-validation claim. */
import "@testing-library/jest-dom";
import { render as rtlRender, fireEvent } from "@testing-library/react";
import { wrap, clone } from "testUtils/render";

import ParameterTable, { ParameterDetails, belowZeroWarnings } from "./PrescriptionPanel";
import { REP26 } from "./__fixtures__/synthetic_november_contracts";
import { REP_R } from "./__fixtures__/synthetic_november_contracts";

jest.mock("plotly.js-dist", () => ({
  react: jest.fn(), purge: jest.fn(), restyle: jest.fn(), relayout: jest.fn(), newPlot: jest.fn(),
  toImage: jest.fn(),
}));
jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn() } }));

const q = (sel) => document.querySelector(sel);
const all = (sel) => Array.from(document.querySelectorAll(sel)).map((el) => el.textContent);
const ok = (data) => ({ data, loading: false, err: null });
const WARN = "The lower threshold is below zero (−20.00); band power cannot go below zero, so the "
  + "device would never cross it.";
const showPlanning = (container) => fireEvent.click(Array.from(container.querySelectorAll("button"))
  .find((b) => b.textContent === "Show the values for planning (not for programming)"));

describe("Threshold card: a lower threshold below zero (R 0-3 26.5 Hz, 80 / −20.00)", () => {
  it("the synthetic report carries the pair, the block and the warning", () => {
    expect(REP26.threshold.upper).toBeCloseTo(80, 2);
    expect(REP26.threshold.lower).toBeCloseTo(-20.00, 2);
    expect(REP26.threshold_placement.below_zero.below_zero).toEqual(["lower"]);
    expect(REP26.threshold_placement.below_zero.warning).toBe(WARN);
    expect(REP26.closed_loop_design_rule.below_zero.below_zero).toEqual(["lower"]);
    expect(REP26.verdict_detail.device_eligible).toBe(false);
  });

  it("values withheld (the device refuses): a visible line, without the value", () => {
    rtlRender(wrap(<ParameterTable report={ok(REP26)} mode="dual" />));
    expect(all('[data-testid="below-zero-line"]')).toEqual(
      ["▲The lower threshold is below zero; band power cannot go below zero, so the device would never cross it."]);
    expect(document.body.textContent).not.toMatch(/−20\.00/);
  });

  it("the planning view: the line with the value, beside the home-swing line", () => {
    const { container } = rtlRender(wrap(<ParameterTable report={ok(REP26)} mode="dual" />));
    showPlanning(container);
    expect(all('[data-testid="below-zero-line"]')).toEqual([`▲${WARN}`]);
    expect(q('[data-testid="home-swing-line"]')).toBeTruthy();
  });

  it("Single mode: its threshold (50) is above zero, so no line", () => {
    rtlRender(wrap(<ParameterTable report={ok(REP26)} mode="single" />));
    expect(q('[data-testid="below-zero-line"]')).toBeNull();
    const single = REP26.prescriptions.modes.single.fields.find((f) => f.parameter === "Single LFP threshold");
    expect(single.value).toBeCloseTo(50, 2);
    expect(single.why).not.toMatch(/below zero/);
  });

  it("the Lower row's reason ends with the warning (shown in the details on a band the device allows)", () => {
    const lower = REP26.prescriptions.modes.dual.fields.find((f) => f.parameter === "Lower LFP threshold");
    expect(lower.why.endsWith(` ${WARN}`)).toBe(true);
    const upper = REP26.prescriptions.modes.dual.fields.find((f) => f.parameter === "Upper LFP threshold");
    expect(upper.why).not.toMatch(/below zero/);
    const allowed = clone(REP26);
    allowed.verdict_detail.device_eligible = true;
    rtlRender(wrap(<ParameterDetails report={ok(allowed)} mode="dual" />));
    expect(document.body.textContent).toContain(WARN);
  });

  it("a pair above zero (R 0-3 9.5 Hz, without the check) shows no line", () => {
    const { container } = rtlRender(wrap(<ParameterTable report={ok(REP_R)} mode="dual" />));
    showPlanning(container);
    expect(q('[data-testid="below-zero-line"]')).toBeNull();
    expect(belowZeroWarnings(REP_R, REP_R.prescriptions.modes.dual.fields)).toEqual([]);
  });
});
