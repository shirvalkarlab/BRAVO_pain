/**
 * The sign-off sheet says which band it signs and which grid that band came from (panel D item 8,
 * with the PI's ruling 8 of decision 233; built 2026-09-23).
 *
 * The sheet's "DEVICE TARGET" block is read from the deployment summary, whose pain score and split
 * are rebuilt from the band's label -- and a band chosen on the "Choose a band" grid carries an
 * empty label, so that line shows the summary's defaults, not the grid the band was picked from.
 * The new block is read from the chosen band itself: the band, when and by whom it was chosen,
 * whether the server holds that record or only this browser does, and the grid's own settings
 * line. A band chosen before its grid was recorded says so rather than printing nothing.
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
import payload from "./__fixtures__/rcs08_deployment_payload_2026-09-15.json";

const wrap = (ui) => (
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>
);

const SUMMARY = { data: { verdict: "deployable", match_direction: "prior", n_gates: 1, n_gates_passed: 1,
  n_necessary: 1, n_necessary_passed: 1, gates: [], caveats: [], evidence: {} }, loading: false, err: null };
const REPORT = { data: JSON.parse(JSON.stringify(payload)), loading: false, err: null };
const GRID = { sweep_metric: "left_leg_vas", metric_label: "Left Leg VAS", match_tolerance_min: 60,
  match_direction: "pro_first", allow_window_reuse: false, label_strategy: "tertile",
  percentile_low: 33.3333, percentile_high: 66.6667, include_clinic_sheet_ratings: true };
const BC = { contact: "ONE_THREE_LEFT", contact_label: "L 1-3+", center_freq_hz: 24.5, bandwidth_hz: 5,
  hemisphere: "Left", grid_settings: GRID };
const ENVELOPE = { band_candidate: BC, committed_at: "2026-09-23T08:00:00.000Z" };
const ON_SERVER = { where: "server", saved: true, reason: null, chosenBy: "clinician@example.org",
  recordedUtc: "2026-09-23T08:00:01.000Z" };

const sheet = (props) => rtlRender(wrap(
  <DeploySignoffCard participantUid="uid" bandCandidate={BC} summary={SUMMARY} deploymentReport={REPORT}
    chosenBand={ENVELOPE} bandRecord={ON_SERVER} {...props} />)).container.textContent;

describe("the sign-off sheet names the band it signs", () => {
  it("prints the band, who chose it, and that the server holds the record", () => {
    const text = sheet();
    expect(text).toMatch(/THE BAND SIGNED FOR/);
    expect(text).toMatch(/L 1-3\+ at 24\.5 Hz/);
    expect(text).toMatch(/clinician@example\.org/);
    expect(text).toMatch(/recorded on the server/);
  });

  it("prints the grid the band was picked from, clinic-sheet switch included", () => {
    const text = sheet();
    expect(text).toMatch(/Left Leg VAS/);
    expect(text).toMatch(/±60 min window/);
    expect(text).toMatch(/clinic-sheet ratings included/);
  });

  it("says when the grid was not recorded, rather than printing nothing", () => {
    const { grid_settings: _drop, ...bare } = BC;
    const text = sheet({ bandCandidate: bare, chosenBand: { ...ENVELOPE, band_candidate: bare } });
    expect(text).toMatch(/not recorded with this band/);
  });

  it("says when the band is held in this browser only", () => {
    const text = sheet({ bandRecord: { where: "browser", saved: false, reason: "network down" } });
    expect(text).toMatch(/held in this browser only/);
    expect(text).toMatch(/network down/);
  });
});

describe("a band chosen before the server kept a record", () => {
  it("names who carried it over, never as the one who chose it", () => {
    const text = sheet({ bandRecord: { ...ON_SERVER, source: "browser_storage", chosenBy: "demo@bravo.local" } });
    expect(text).toMatch(/chosen in a browser before the server kept a record/);
    expect(text).toMatch(/carried over to the server by demo@bravo\.local/);
    expect(text).not.toMatch(/, by demo@bravo\.local; recorded/);
  });
});
