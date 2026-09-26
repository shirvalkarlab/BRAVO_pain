/**
 * The PI, 2026-09-25 (answer 6 of the revised plan): the deployment summary's area under the curve
 * gets "the same number with the current taken out beside it". The server sends it on the evidence
 * block (`auc_current_removed`, Biomarkers `routines/deployment_current.py`); this pins that the
 * sign-off card prints it on the line under the plain number, with its interval and the words "with
 * the stimulation current taken out", says it is descriptive only, prints a refusal as a refusal
 * (never as a number), and prints nothing for an older response that does not carry it.
 */
import "@testing-library/jest-dom";
import { render as rtlRender } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";

import theme from "assets/theme";
import { PlatformContextProvider } from "context";

jest.mock("plotly.js-dist", () => ({
  react: jest.fn(), purge: jest.fn(), restyle: jest.fn(), relayout: jest.fn(), newPlot: jest.fn(),
  toImage: jest.fn(),
}));
jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn() } }));

// eslint-disable-next-line import/first
import DeploySignoffCard from "./DeploySignoffCard";
import payload from "./__fixtures__/rcs08_deployment_payload_2026-09-15.json";

const wrap = (ui) => (
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>
);

const REPORT = { data: JSON.parse(JSON.stringify(payload)), loading: false, err: null };
const BC = { contact: "ONE_THREE_LEFT", contact_label: "L 1-3+", center_freq_hz: 24.5, bandwidth_hz: 5,
  hemisphere: "Left" };

const summaryWith = (evidence) => ({
  data: { verdict: "deployable", match_direction: "prior", n_gates: 1, n_gates_passed: 1,
    n_necessary: 1, n_necessary_passed: 1, gates: [], caveats: [], evidence },
  loading: false, err: null,
});

const sheet = (summary) => rtlRender(wrap(
  <DeploySignoffCard participantUid="uid" bandCandidate={BC} summary={summary}
    deploymentReport={REPORT} />)).container.textContent;

const PLAIN = { auc: 0.623, auc_lo: 0.463, auc_hi: 0.731 };

describe("the sign-off card's area under the curve with the current taken out (answer 6)", () => {
  it("prints the adjusted reading with its interval beside the plain one, and says it gates nothing", () => {
    const text = sheet(summaryWith({ ...PLAIN, auc_current_removed: {
      available: true, label: "with the stimulation current taken out", auc: 0.548, auc_low: 0.401,
      auc_high: 0.684, shape: "line", shape_words: "a straight line", hemisphere: "Left",
      n_spectral_samples: 18992, n_pain_reports: 30, n_samples_without_current: 120,
      plain_on_same_samples: { auc: 0.611, auc_low: 0.452, auc_high: 0.744 } } }));
    expect(text).toMatch(/Deployment AUC — in-sample \(95% clustered-bootstrap CI\)0\.62 \(0\.46–0\.73\)/);
    expect(text).toMatch(/Deployment AUC — with the stimulation current taken out0\.55 \(0\.40–0\.68\)/);
    expect(text).toMatch(/the Left current in force at each sample taken out of the band power as a straight line/);
    expect(text).toMatch(/the plain reading on those same samples is 0\.61 \(0\.45–0\.74\)/);
    expect(text).toMatch(/120 samples recorded before the first dated setting have no current/);
    expect(text).toMatch(/Descriptive only: the plain reading above sets every gate and the verdict/);
  });

  it("prints a refusal as a refusal, with its reason, never as a number", () => {
    const text = sheet(summaryWith({ ...PLAIN, auc_current_removed: {
      available: false, auc: null, why: "the current is constant at 2 across every sample" } }));
    expect(text).toMatch(/Deployment AUC — with the stimulation current taken outnot computed/);
    expect(text).toMatch(/the current is constant at 2 across every sample/);
    expect(text).not.toMatch(/taken out—/);
  });

  it("prints nothing when an older response does not carry the reading", () => {
    const text = sheet(summaryWith({ ...PLAIN }));
    expect(text).not.toMatch(/with the stimulation current taken out/);
  });
});
