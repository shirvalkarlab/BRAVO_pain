/** Synthetic UI contract regression. No live participant response or empirical validation. */
import React from "react";
import "@testing-library/jest-dom";
import { render as rtlRender } from "@testing-library/react";

import DeploySignoffCard from "./DeploySignoffCard";
import { headline } from "./ClosedLoopSimulationPanel";
import payload from "./__fixtures__/synthetic_provisional_grid.json";
import { wrap } from "testUtils/render";

jest.mock("plotly.js-dist", () => ({
  react: jest.fn(), purge: jest.fn(), restyle: jest.fn(), relayout: jest.fn(), newPlot: jest.fn(),
  toImage: jest.fn(),
}));
jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn() } }));

describe("C3: the simulation headline names the timing values the record cannot decide", () => {
  const run = {
    active_model: "M1",
    models: { M0: { frac_time_at_upper: 0.4 }, M1: { frac_time_at_upper: 0.2 } },
    curves: { M1: { kind: "linear", slope_per_mA: -2, n_points: 8, n_runs: 2 } },
    timing_low_confidence_fields: ["detection_blanking_ms", "transition_up_ms", "transition_down_ms"],
    timing_qualifier: "using three timing values the record cannot decide (detection blanking, transition up, transition down; graded Low on the parameter card)",
  };
  it("prepends the qualifier, capitalised, when the regime carries one", () => {
    const h = headline(run);
    expect(h.startsWith("Using three timing values the record cannot decide (detection blanking, transition up, transition down; graded Low on the parameter card): ")).toBe(true);
    expect(h).toContain("Closing the loop moves time at the upper amplitude limit from 40.0% to 20.0%");
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
