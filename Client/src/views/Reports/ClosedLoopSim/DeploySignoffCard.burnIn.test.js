/**
 * P-04: the sign-off card never said that the mixed-effects check leaves out the first three
 * weeks of the whole record. The server already computes the count
 * (`Biomarkers.routines.analytics.band_mixedmodel_inference`'s `excluded_first_weeks` /
 * `n_excluded_burn_in`, VALIDATION_EXCLUDE_FIRST_WEEKS = 3); this pins the plain-language sentence
 * once the evidence block carries those two fields, and pins that nothing is printed when an older
 * cached response does not carry them.
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

describe("the sign-off card's mixed-effects burn-in sentence (P-04)", () => {
  it("names the excluded weeks and ratings, counted from the first sample, not a setting change", () => {
    const text = sheet(summaryWith({ excluded_first_weeks: 3, n_excluded_burn_in: 21 }));
    expect(text).toMatch(/leaves out the first 3 weeks of the whole record/);
    expect(text).toMatch(/counted from the first recorded sample \(not from each setting change\)/);
    expect(text).toMatch(/21 ratings excluded/);
  });

  it("uses the singular for one excluded week or rating", () => {
    const text = sheet(summaryWith({ excluded_first_weeks: 1, n_excluded_burn_in: 1 }));
    expect(text).toMatch(/first 1 week of the whole record/);
    expect(text).toMatch(/1 rating excluded/);
  });

  it("prints nothing when the served evidence carries no burn-in count", () => {
    const text = sheet(summaryWith({}));
    expect(text).not.toMatch(/leaves out the first/);
  });
});
