/**
 * The readiness list holds only the combinations with something on them (a band that qualifies,
 * falls with current, or responds to a change in current), at most 30
 * (`bravo_service.closed_loop_readiness`). A pair the device allows today that has no row was
 * still screened and is counted in the sentence above; the page says it is not in the list, never
 * that "nothing was screened" on it (2026-09-26).
 */
import React from "react";
import { render as rtlRender } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";
import theme from "assets/theme";
import { PlatformContextProvider } from "context";
import SensingEvidenceTable from "./SensingEvidenceTable";

const wrap = (ui) => (
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>
);

const closedLoop = {
  available: true, ready: false, n_cells_screened: 50, n_cells_deployable: 0,
  sensing_rule: { sentence: "One sensing pair per lead: L 1-3+ and R 0-3+.", by_side: {
    Left: { rule_applied: true, allowed_channel: "ONE_THREE_LEFT", allowed_display: "L 1⁻3⁺", n_usable_on_allowed_pair: 0 },
    Right: { rule_applied: true, allowed_channel: "ZERO_THREE_RIGHT", allowed_display: "R 0⁻3⁺", n_usable_on_allowed_pair: 0 } } },
  responding_cells: [{ channel: "ZERO_TWO_LEFT", hemisphere: "Left", rate_hz: 55, n_bands: 22, n_responding: 1,
    n_era_negative_significant: 0, n_pain_positive: 0, n_qualifying: 0, qualifying_centers_hz: [],
    deployable: false, blocking_reasons: "sensing pair not allowed", display_short: "L 0⁻2⁺" }],
};

it("says an allowed pair with no row is not in the list, not that nothing was screened", () => {
  const { container } = rtlRender(wrap(<SensingEvidenceTable closedLoop={closedLoop} />));
  const t = container.textContent;
  expect(t).not.toMatch(/Nothing was screened/);
  expect(t).toContain("No combination on L 1⁻3⁺ or R 0⁻3⁺ is in this list");
  expect(t).toMatch(/only combinations with a band that qualifies, falls with current or responds to a change in current/);
});
