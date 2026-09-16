/**
 * Review 2026-09-15, findings S1 and S2. The amplitude-limits check on RCS08 read FAIL "Left: upper
 * limit 4.8 mA exceeds the declared ceiling of 4.5 mA" when 4.8 was the highest current the device
 * had ever delivered, not a proposal. The backend now returns "not assessed" with
 * `evidence.history_above_ceiling`; the panel must print that it is history, and (S2) always print
 * the side-effect-versus-current sentence with its n.
 */
import "@testing-library/jest-dom";
import { render as rtlRender } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";

import theme from "assets/theme";
import { PlatformContextProvider } from "context";

import ClosedLoopChecks from "./ClosedLoopChecks";

const wrap = (ui) => (
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>
);

const SENTENCE = "on 15 scored clinic steps with stimulation on, reported side-effect severity does not "
  + "move measurably with current (Spearman rho = -0.04, p = 0.895); 0 of them sit above 4 mA";

const plan = {
  gate: {
    passed: false, n_conditions: 1,
    conditions: [{
      name: "amplitude_limits_inside_envelope_and_under_ceiling", passed: null,
      detail: "not assessed: Left: no limit was proposed ...",
      evidence: {
        checked: { Left: { amp_min_mA: 1.4, amp_max_mA: 4.8, envelope: [1.4, 4.8] } },
        ceiling_by_side: { Left: { ceiling_mA: 4.5, provenance: "stated by PI, 2026-09-14" } },
        defaulted: ["Left"],
        history_above_ceiling: { Left: { delivered_max_mA: 4.8, ceiling_mA: 4.5 } },
        side_effect_vs_current: { assessable: true, rho: -0.037, p: 0.895, n_scored_stim_on: 15,
          n_above_4mA: 0, sentence: SENTENCE },
      },
    }],
  },
  lfp_evidence: {},
};

test("a defaulted limit above the ceiling is printed as history, not a proposal", () => {
  const { container } = rtlRender(wrap(<ClosedLoopChecks plan={plan} />));
  expect(container.textContent).toMatch(/4\.8\s?mA delivered in the past.*history, not a proposal/);
  expect(container.textContent).toMatch(/1 not assessed/);
});

test("the side-effect-versus-current sentence and its n are always printed on that check (S2)", () => {
  const { container } = rtlRender(wrap(<ClosedLoopChecks plan={plan} />));
  expect(container.textContent).toContain("15 scored clinic steps");
});
