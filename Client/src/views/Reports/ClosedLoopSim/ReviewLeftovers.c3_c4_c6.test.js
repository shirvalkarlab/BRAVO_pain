/**
 * The 2026-09-15 clinician review's leftovers on this page, built 2026-09-17 (decision 200):
 *   C3  the CL-DBS simulation headline says when it rests on timing values the record cannot decide;
 *   C4  the reliable-change card prints when its pairs were filed, beside the count;
 *   C6  the Deploy-to-Percept review carried a standing off-label line -- REMOVED 2026-09-19 on the PI's
 *       ruling (research context; approved-indication constraints are not applied). The test now pins its absence.
 */
import React from "react";
import "@testing-library/jest-dom";
import { render as rtlRender } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";

import theme from "assets/theme";
import { PlatformContextProvider } from "context";

import DeploySignoffCard from "./DeploySignoffCard";
import { headline } from "./ClosedLoopSimulationPanel";
import payload from "./__fixtures__/rcs08_deployment_payload_2026-09-15.json";

jest.mock("plotly.js-dist", () => ({
  react: jest.fn(), purge: jest.fn(), restyle: jest.fn(), relayout: jest.fn(), newPlot: jest.fn(),
  toImage: jest.fn(),
}));
jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn() } }));

const wrap = (ui) => (
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>
);

describe("C3: the simulation headline names the timing values the record cannot decide", () => {
  const run = {
    active_model: "M1",
    models: { M0: { frac_time_at_upper: 0.265 }, M1: { frac_time_at_upper: 0.238 } },
    curves: { M1: { kind: "linear", slope_per_mA: -3.62, n_points: 13, n_runs: 4 } },
    timing_low_confidence_fields: ["detection_blanking_ms", "transition_up_ms", "transition_down_ms"],
    timing_qualifier: "using three timing values the record cannot decide (detection blanking, transition up, transition down; graded Low on the parameter card)",
  };
  it("prepends the qualifier, capitalised, when the regime carries one", () => {
    const h = headline(run);
    expect(h.startsWith("Using three timing values the record cannot decide (detection blanking, transition up, transition down; graded Low on the parameter card): ")).toBe(true);
    expect(h).toContain("Closing the loop moves time at the upper amplitude limit from 26.5% to 23.8%");
  });
  it("prints the sentence as before when the regime carries none (as programmed today)", () => {
    const h = headline({ ...run, timing_low_confidence_fields: [], timing_qualifier: null });
    expect(h.startsWith("Closing the loop moves")).toBe(true);
    expect(h).not.toMatch(/cannot decide/);
  });
});

describe("C6 (reversed 2026-09-19): the Deploy-to-Percept review carries NO off-label line", () => {
  it("prints nothing about approved indications, in any state", () => {
    const { container } = rtlRender(wrap(
      <DeploySignoffCard participantUid="TEST01" bandCandidate={{ contact: "ZERO_TWO_LEFT", center_freq_hz: 24.5, bandwidth_hz: 5 }}
        requestParams={{}} cutpoint={null} summary={{ data: null, loading: true, err: null }} deploymentReport={null} />));
    expect(container.textContent).not.toMatch(/approved indication|labelled for Parkinson/);
  });
});
