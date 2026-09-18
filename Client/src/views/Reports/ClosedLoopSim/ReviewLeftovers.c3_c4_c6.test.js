/**
 * The 2026-09-15 clinician review's leftovers on this page, built 2026-09-17 (decision 200):
 *   C3  the CL-DBS simulation headline says when it rests on timing values the record cannot decide;
 *   C4  the reliable-change card prints when its pairs were filed, beside the count;
 *   C6  the Deploy-to-Percept review carries the standing off-label line.
 */
import React from "react";
import "@testing-library/jest-dom";
import { render as rtlRender } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";

import theme from "assets/theme";
import { PlatformContextProvider } from "context";

import ReliableChangePanel from "./ReliableChangePanel";
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

describe("C4: the reliable-change card prints when the pairs were filed", () => {
  const rc = JSON.parse(JSON.stringify(payload.reliable_change));
  const first = Object.keys(rc.items).find((k) => Number.isFinite(Number(rc.items[k].pooled_sd)));
  rc.items[first].earliest_pair_utc = "2025-07-23T18:04:00+00:00";
  rc.items[first].latest_pair_utc = "2026-04-27T21:40:00+00:00";
  rc.items[first].pair_span_days = 278.15;
  it("prints the first and last pair's dates and the span beside the count", () => {
    const { container } = rtlRender(wrap(<ReliableChangePanel reliableChange={rc} />));
    const text = container.textContent;
    expect(text).toMatch(/\d+ pairs? across \d+ stretch(es)? of unchanged settings/);
    expect(text).toContain("filed between 2025-07-23 and 2026-04-27 (278 days apart)");
  });
  it("prints no dates when the item carries none (an older response)", () => {
    const bare = JSON.parse(JSON.stringify(payload.reliable_change));
    const { container } = rtlRender(wrap(<ReliableChangePanel reliableChange={bare} />));
    expect(container.textContent).not.toMatch(/filed between/);
  });
});

describe("C6: the Deploy-to-Percept review carries the standing off-label line", () => {
  it("prints it in every state, including before the summary has loaded", () => {
    const { container } = rtlRender(wrap(
      <DeploySignoffCard participantUid="TEST01" bandCandidate={{ contact: "ZERO_TWO_LEFT", center_freq_hz: 24.5, bandwidth_hz: 5 }}
        requestParams={{}} cutpoint={null} summary={{ data: null, loading: true, err: null }} deploymentReport={null} />));
    expect(container.textContent).toContain("Chronic pain is not an approved indication for this device; Adaptive Therapy is labelled for Parkinson's disease.");
  });
});
