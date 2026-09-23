/**
 * Step 7 of the research panels' build order: what the Closed-Loop page says about its own answer.
 *
 * Four things, each from panel D of 2026-09-22 and each pinned here on the words a clinician reads:
 *
 *  1. ONE VERDICT ON THE SIGN-OFF SHEET. The sheet carried two: the deployment report's own verdict
 *     and a second sentence from the older statistical-gate endpoint, which answers a different
 *     question (does the band discriminate?) in the same words. The gate rows stay as a checklist;
 *     the second verdict sentence goes.
 *  2. THE CAVEATS LIST on the printed record: every number the page shows without an uncertainty
 *     interval, with the card it sits on, and counted in the header so a reader sees there are some
 *     before scrolling.
 *  3. BAND STABILITY IN "WHAT WOULD CHANGE THIS ANSWER". The answer was computed and drawn on its
 *     own card and was absent from the one band on the page that tells a reader what to do next.
 *  4. THE BAND-POWER-TO-PAIN READING WITH THE CURRENT TAKEN OUT, printed beside the plain one on
 *     the evidence triangle, replacing the interim sentence that could only say it had not been
 *     measured.
 */
import "@testing-library/jest-dom";
import { render as rtlRender } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";

import theme from "assets/theme";
import { PlatformContextProvider } from "context";

// The sign-off card reaches Plotly to photograph the page's figures for the printed record, and
// Plotly asks for a canvas the moment it loads. Mocked exactly as the other tests on this page do.
jest.mock("plotly.js-dist", () => ({
  react: jest.fn(), purge: jest.fn(), restyle: jest.fn(), relayout: jest.fn(), newPlot: jest.fn(),
  toImage: jest.fn(),
}));
jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn() } }));

// eslint-disable-next-line import/first
import DeploySignoffCard from "./DeploySignoffCard";
import DeploymentDecisionHeader from "./DeploymentDecisionHeader";
import WhatWouldChangeThis from "./WhatWouldChangeThis";
import EvidenceTrianglePanel from "./EvidenceTrianglePanel";
import payload from "./__fixtures__/rcs08_deployment_payload_2026-09-15.json";

const wrap = (ui) => (
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>
);

const CAVEATS = [
  { severity: "high", card: "the evidence triangle",
    text: "The verdict rests on the point signs alone: the interval spans zero on E1 and E2." },
  { severity: "medium", card: "the parameters to transcribe",
    text: "The two switching values the device would use (190.5 and 240.5 in the stimulator's own "
        + "units) are a median reading plus or minus a fixed minimum, and carry no interval." },
  { severity: "low", card: "the closed-loop simulations",
    text: "In the closed-loop simulations only M3 resamples whole runs and so carries an interval." },
];

const SUMMARY = {
  data: {
    verdict: "deployable",
    match_direction: "prior",
    n_gates: 6, n_gates_passed: 4, n_necessary: 3, n_necessary_passed: 3,
    n_gates_indeterminate: 1,
    gates: [{ key: "auc", label: "Discrimination beats chance", state: "pass",
      detail: "AUC 0.62 (0.55-0.70)", necessary: true }],
    caveats: ["in-sample only"],
    evidence: { auc: 0.62, auc_lo: 0.55, auc_hi: 0.70 },
  },
  loading: false,
  err: null,
};

const reportWith = (patch) => {
  const d = JSON.parse(JSON.stringify(payload));
  return { data: Object.assign(d, patch || {}), loading: false, err: null };
};

const BC = { contact: "ZERO_THREE_LEFT", contact_label: "L 0-3+", center_freq_hz: 24.5,
  bandwidth_hz: 5, hemisphere: "Left" };

// --- 1. one verdict on the sheet --------------------------------------------------------------
describe("the sign-off sheet states one verdict", () => {
  it("does not print the statistical-gate endpoint's own verdict sentence", () => {
    const { container } = rtlRender(wrap(
      <DeploySignoffCard participantUid="uid" bandCandidate={BC} summary={SUMMARY}
        deploymentReport={reportWith({ caveats: CAVEATS })} />));
    expect(container.textContent).not.toMatch(/Summary verdict:/);
  });

  it("keeps the deployment report's own verdict", () => {
    const { container } = rtlRender(wrap(
      <DeploySignoffCard participantUid="uid" bandCandidate={BC} summary={SUMMARY}
        deploymentReport={reportWith({ caveats: CAVEATS })} />));
    expect(container.textContent).toMatch(/Evidence verdict from the deployment report/);
  });

  it("keeps the gate rows as a checklist, with their counts", () => {
    const { container } = rtlRender(wrap(
      <DeploySignoffCard participantUid="uid" bandCandidate={BC} summary={SUMMARY}
        deploymentReport={reportWith({ caveats: CAVEATS })} />));
    expect(container.textContent).toMatch(/Discrimination beats chance/);
    expect(container.textContent).toMatch(/4 of 6/);
  });
});

// --- 2. the caveats list ----------------------------------------------------------------------
describe("every number without an uncertainty interval is named on the printed record", () => {
  it("prints each caveat with the card it sits on", () => {
    const { container } = rtlRender(wrap(
      <DeploySignoffCard participantUid="uid" bandCandidate={BC} summary={SUMMARY}
        deploymentReport={reportWith({ caveats: CAVEATS })} />));
    const text = container.textContent;
    expect(text).toMatch(/190\.5 and 240\.5/);
    expect(text).toMatch(/the parameters to transcribe/);
    expect(text).toMatch(/only M3 resamples whole runs/);
  });

  it("says so plainly when the report carries no caveats at all", () => {
    const { container } = rtlRender(wrap(
      <DeploySignoffCard participantUid="uid" bandCandidate={BC} summary={SUMMARY}
        deploymentReport={reportWith({ caveats: [] })} />));
    expect(container.textContent).toMatch(/no caveats/i);
  });

  it("counts them in the header so a reader sees them before scrolling", () => {
    const { container } = rtlRender(wrap(
      <DeploymentDecisionHeader bandCandidate={BC} summary={SUMMARY}
        deploymentReport={reportWith({ caveats: CAVEATS })} />));
    expect(container.textContent).toMatch(/3 numbers or findings/i);
  });
});

// --- 3. band stability in "what would change this answer" -------------------------------------
describe("what would change this answer reads the band-stability answer", () => {
  it("adds a ranked item when the answer is 'cannot tell'", () => {
    const { container } = rtlRender(wrap(
      <WhatWouldChangeThis report={reportWith({
        band_stability: { answer: "cannot tell", test_ran: true,
          reason: "not rejected, but the interval is wider than the margin" } })} />));
    const text = container.textContent;
    expect(text).toMatch(/means the same thing about pain/i);
    expect(text).toMatch(/cannot tell/i);
    expect(text).toMatch(/MORE STIMULATION STATES/i);
  });

  it("says the stronger thing when the band behaves differently", () => {
    const { container } = rtlRender(wrap(
      <WhatWouldChangeThis report={reportWith({
        band_stability: { answer: "behaves differently", test_ran: true,
          reason: "p 0.032, interval -1.238 to -0.104" } })} />));
    expect(container.textContent).toMatch(/behaves differently/i);
    expect(container.textContent).toMatch(/band selection/i);
  });

  it("adds nothing when the band was shown to behave the same", () => {
    const { container } = rtlRender(wrap(
      <WhatWouldChangeThis report={reportWith({
        band_stability: { answer: "behaves the same", test_ran: true, reason: "" } })} />));
    expect(container.textContent).not.toMatch(/means the same thing about pain/i);
  });
});

// --- 4. the second reading of E2 on the triangle -----------------------------------------------
describe("the band-power-to-pain edge carries the reading with the current taken out", () => {
  const withAdjusted = (adjusted) => {
    const d = JSON.parse(JSON.stringify(payload));
    d.candidates = [{ ...(d.candidates || [{}])[0], channel: "ZERO_THREE_LEFT", center_hz: 24.5 }];
    d.edges.E2.adjusted = adjusted;
    return { data: d };
  };

  it("prints the adjusted value and its interval beside the plain one", () => {
    const { container } = rtlRender(wrap(<EvidenceTrianglePanel report={withAdjusted({
      available: true, adjusted_for: "amp_mA_Left", auc: 0.521, auc_low: 0.441, auc_high: 0.604,
      partial_r: -0.052, n_pain_reports: 32, shape: "line",
    })} />));
    const text = container.textContent;
    expect(text).toMatch(/0\.521/);
    expect(text).toMatch(/0\.441/);
    expect(text).toMatch(/current in force/i);
  });

  it("says why it could not be made rather than showing nothing", () => {
    const { container } = rtlRender(wrap(<EvidenceTrianglePanel report={withAdjusted({
      available: false, adjusted_for: "amp_mA_Left",
      why: "this band's power moves almost exactly with amp_mA_Left on these samples",
    })} />));
    expect(container.textContent).toMatch(/almost exactly with amp_mA_Left/);
  });

  it("falls back to the interim sentence when no second reading was asked for", () => {
    const d = JSON.parse(JSON.stringify(payload));
    d.candidates = [{ ...(d.candidates || [{}])[0], channel: "ZERO_THREE_LEFT", center_hz: 24.5 }];
    delete d.edges.E2.adjusted;
    const { container } = rtlRender(wrap(<EvidenceTrianglePanel report={{ data: d }} />));
    expect(container.textContent).toMatch(/stimulation current in force/i);
  });
});
