/** Synthetic display-contract regression tests.
 * Independently authored examples; no participant responses or live scientific validation.
 */
import "@testing-library/jest-dom";
import { render as rtlRender } from "@testing-library/react";

import ClosedLoopChecks from "./ClosedLoopChecks";
import TwoStagePlanCard from "./TwoStagePlanCard";
import { TITRATION_CARD_TITLE } from "./TitrationSessionCard";
import response from "./__fixtures__/synthetic_optimizer_basic.json";
import { wrap } from "testUtils/render";

const plan = response.two_stage;

describe("the fixture is the state these assertions were written against", () => {
  it("carries the gate with one failed condition and one not assessed, and the history evidence", () => {
    expect(plan.gate.verdict).toBe("Stage 2 MUST NOT START: 2 of 4 conditions block");
    expect(plan.gate.n_conditions).toBe(4);
    expect(plan.gate.failed).toEqual(["openloop_choice_resolved"]);
    expect(plan.gate.not_assessed).toEqual(["amplitude_limits_inside_envelope_and_under_ceiling"]);
    const amp = plan.gate.conditions.find((c) => c.name === "amplitude_limits_inside_envelope_and_under_ceiling");
    expect(amp.passed).toBeNull();
    expect(amp.evidence.history_above_ceiling.Left).toEqual({ delivered_max_mA: 4.9, ceiling_mA: 4.5 });
    expect(amp.evidence.side_effect_vs_current.n_scored_stim_on).toBe(8);
  });
});

describe("Closed loop: may it start? (ClosedLoopChecks)", () => {
  it("pin (decision 168, S1): the amplitude condition prints the delivered maximum as history, not a proposal", () => {
    const { container } = rtlRender(wrap(<ClosedLoopChecks plan={plan} />));
    expect(container.textContent).toMatch(/4\.9\s?mA delivered in the past is above today's 4\.5\s?mA ceiling — history, not a proposal/);
  });

  // PIN CHANGED 2026-09-26 (the design review): the headline answers the card's title question,
  // "No: ...", because the page's status line now says "closed loop cannot start" in words and the
  // page said it four times. The two counts, kept apart, are what this pin protects.
  it("pin: the headline counts the blocking check and the not-assessed check separately, in the card's own words", () => {
    const { container } = rtlRender(wrap(<ClosedLoopChecks plan={plan} />));
    expect(container.textContent).toContain("No: 1 of 4 checks block, 1 not assessed");
    // The server's code-name verdict must not reach the page (the component's own rule).
    expect(container.textContent).not.toMatch(/MUST NOT START/);
    expect(container.textContent).not.toMatch(/2 of 4 conditions block/);
  });

  it("pin (decision 168, S2): the side-effect-versus-current sentence and its n are on the card", () => {
    const { container } = rtlRender(wrap(<ClosedLoopChecks plan={plan} />));
    expect(container.textContent).toContain("8 scored clinic steps");
    expect(container.textContent).toMatch(/Spearman rho = 0\.25, p = 0\.400/);
  });
});

describe("Closed loop: may it start on the frozen setting? (TwoStagePlanCard)", () => {
  // An authored three-cell queue must stay folded and never become a second clinical plan.
  it("prints no second in-clinic recommendation; the queue is named, folded, as not a second plan", () => {
    expect(Array.isArray(plan.stage1.queue) && plan.stage1.queue.length).toBe(3);
    const { container } = rtlRender(wrap(<TwoStagePlanCard plan={plan} loading={false} err={null} />));
    const text = container.textContent;
    expect(text).not.toMatch(/What to test at the next visit/);
    expect(text).not.toMatch(/ranked by expected improvement/);
    expect(text).not.toContain(TITRATION_CARD_TITLE);
    expect(text).toContain("untested cells are on the response and are not a second in-clinic plan");
  });
});
