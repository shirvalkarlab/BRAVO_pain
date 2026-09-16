/**
 * Referent audit, 2026-09-15 (`.planning/2026-09-15-rendered-text-referent-audit-three-pages/
 * findings.md` §3), the Stim Optimizer page. The closed-loop checks card is rendered against the
 * REAL two-stage response for RCS08 captured that evening
 * (`__fixtures__/rcs08_stim_optimizer_two_stage.json`).
 *
 * WHAT THIS PINS, AND WHY IT IS GREEN ON PURPOSE. The ranked list's only Stim Optimizer entry
 * (item 12, DUP-5 / DUP-6: the rate row's folded sentence restating the open Numbers line, and the
 * sensing-evidence fold restating its caption) is recorded as DELIBERATE -- the fold's job is to
 * restate in prose -- so there is nothing to make RED here. What this page did need was a pin on
 * the strings decision 168 corrected the same day, against the live fixture rather than a
 * hand-written one, so a regression reads as a failing test and not as an amber line quietly
 * turning into a red one on a clinician's screen:
 *
 *  - the amplitude-limits condition with `passed: null` and `history_above_ceiling.Left` prints
 *    "history, not a proposal" (S1: 4.8 mA delivered in the past is not an unsafe proposal);
 *  - the card's own headline counts that condition as NOT ASSESSED, separately from the one that
 *    blocks. The server's `gate.verdict` string says "2 of 4 conditions block"; the card never
 *    prints that string (its header comment says so) and reads "1 of 4 checks block, 1 not
 *    assessed" -- the honest split. The brief for this file asked for "2 of 4"; that is the
 *    server's wording, not the page's, and the page's is what a reader sees.
 *  - the side-effect-versus-current sentence with its n is on the card (S2).
 */
import "@testing-library/jest-dom";
import { render as rtlRender } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";

import theme from "assets/theme";
import { PlatformContextProvider } from "context";

import ClosedLoopChecks from "./ClosedLoopChecks";
import TwoStagePlanCard from "./TwoStagePlanCard";
import { TITRATION_CARD_TITLE } from "./TitrationSessionCard";
import response from "./__fixtures__/rcs08_stim_optimizer_two_stage.json";

const wrap = (ui) => (
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>
);

const plan = response.two_stage;

describe("the fixture is the state these assertions were written against", () => {
  it("carries the gate with one failed condition and one not assessed, and the history evidence", () => {
    expect(plan.gate.verdict).toBe("Stage 2 MUST NOT START: 2 of 4 conditions block");
    expect(plan.gate.n_conditions).toBe(4);
    expect(plan.gate.failed).toEqual(["openloop_choice_resolved"]);
    expect(plan.gate.not_assessed).toEqual(["amplitude_limits_inside_envelope_and_under_ceiling"]);
    const amp = plan.gate.conditions.find((c) => c.name === "amplitude_limits_inside_envelope_and_under_ceiling");
    expect(amp.passed).toBeNull();
    expect(amp.evidence.history_above_ceiling.Left).toEqual({ delivered_max_mA: 4.8, ceiling_mA: 4.5 });
    expect(amp.evidence.side_effect_vs_current.n_scored_stim_on).toBe(15);
  });
});

describe("Closed loop: may it start? (ClosedLoopChecks)", () => {
  it("pin (decision 168, S1): the amplitude condition prints the delivered maximum as history, not a proposal", () => {
    const { container } = rtlRender(wrap(<ClosedLoopChecks plan={plan} />));
    expect(container.textContent).toMatch(/4\.8\s?mA delivered in the past is above today's 4\.5\s?mA ceiling — history, not a proposal/);
  });

  it("pin: the headline counts the blocking check and the not-assessed check separately, in the card's own words", () => {
    const { container } = rtlRender(wrap(<ClosedLoopChecks plan={plan} />));
    expect(container.textContent).toContain("Closed loop may not start: 1 of 4 checks block, 1 not assessed");
    // The server's code-name verdict must not reach the page (the component's own rule).
    expect(container.textContent).not.toMatch(/MUST NOT START/);
    expect(container.textContent).not.toMatch(/2 of 4 conditions block/);
  });

  it("pin (decision 168, S2): the side-effect-versus-current sentence and its n are on the card", () => {
    const { container } = rtlRender(wrap(<ClosedLoopChecks plan={plan} />));
    expect(container.textContent).toContain("15 scored clinic steps");
    expect(container.textContent).toMatch(/Spearman rho = -0\.04, p = 0\.895/);
  });
});

describe("Closed loop: may it start on the frozen setting? (TwoStagePlanCard)", () => {
  // The PI, 2026-09-15 evening: the page carried TWO in-clinic recommendations -- the titration
  // session card he designed (decisions 146, 160, 163) and, at the foot of this card, the joint
  // model's "What to test at the next visit" queue from decision 157: 25 untested (rate, left,
  // right) cells whose predicted values are identical to three decimals on this record, so the
  // ranking is noise, and which mixes 55/70/85/110 Hz. One in-clinic plan: the titration session.
  it("prints no second in-clinic recommendation; it points at the titration session card instead", () => {
    expect(Array.isArray(plan.stage1.queue) && plan.stage1.queue.length).toBe(25);
    const { container } = rtlRender(wrap(<TwoStagePlanCard plan={plan} loading={false} err={null} />));
    const text = container.textContent;
    expect(text).not.toMatch(/What to test at the next visit/);
    expect(text).not.toMatch(/ranked by expected improvement/);
    expect(text).toContain(TITRATION_CARD_TITLE);
  });
});
