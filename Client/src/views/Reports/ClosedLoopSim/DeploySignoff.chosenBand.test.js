/** Synthetic UI contract regression. No live participant response or empirical validation. */
import "@testing-library/jest-dom";
import { render as rtlRender } from "@testing-library/react";
import DeploySignoffCard from "./DeploySignoffCard";
import payload from "./__fixtures__/synthetic_provisional_grid.json";
import { wrap } from "testUtils/render";

jest.mock("plotly.js-dist", () => ({
  react: jest.fn(), purge: jest.fn(), restyle: jest.fn(), relayout: jest.fn(), newPlot: jest.fn(),
  toImage: jest.fn(),
}));
jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn() } }));

// The sign-off card reaches Plotly to photograph the page's figures for the printed record, and
// Plotly asks for a canvas the moment it loads. Mocked exactly as the other tests on this page do.



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
    expect(text).toMatch(/The band signed for/);   // sentence case since 2026-09-26
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


describe("from DeploySignoffCard.burnIn", () => {
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

  describe("the sign-off record names its pain score on its own line, in bold (the PI, 2026-10-03)", () => {
    // The odds ratio and the AUCs on this card share one feature and one pain score; the score is said
    // once, by name, before any number, rather than as a code inside the device-target table.
    it("prints 'Pain score: Overall VAS' in bold, and never the bare code", () => {
      const { container } = rtlRender(wrap(
        <DeploySignoffCard participantUid="uid" bandCandidate={BC}
          summary={{ ...summaryWith({}), data: { ...summaryWith({}).data,
            identity: { pro_metric: "vas", binarization: "median", hemisphere: "Left", contact: "ZERO_THREE_LEFT" },
            device_control: { polarity: "positive", suggested_mode: "Dual" } } }}
          deploymentReport={REPORT} />));
      const line = container.querySelector('[data-testid="signoff-pain-score"]');
      expect(line).toBeTruthy();
      expect(line.textContent).toBe("Pain score: Overall VAS");
      expect(window.getComputedStyle(line).fontWeight).toBe("600");          // the house bold (D6: 400 and 600 only)
      expect(container.textContent).toMatch(/Pain score \/ high-low split.*Overall VAS \/ median/);
    });
  });
});


describe("from DeploySignoffCard.currentRemoved", () => {
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

  // Independently authored observations for display-format and source-distinction tests.
  const PLAIN = { auc: 0.8, auc_lo: 0.7, auc_hi: 0.9 };

  describe("the sign-off card's area under the curve with the current taken out (answer 6)", () => {
    it("prints the adjusted reading with its interval beside the plain one, and says it gates nothing", () => {
      const text = sheet(summaryWith({ ...PLAIN, auc_current_removed: {
        available: true, label: "with the stimulation current taken out", auc: 0.6, auc_low: 0.5,
        auc_high: 0.7, shape: "line", shape_words: "a straight line", hemisphere: "Left",
        n_spectral_samples: 24, n_pain_reports: 8, n_samples_without_current: 2,
        plain_on_same_samples: { auc: 0.75, auc_low: 0.65, auc_high: 0.85 } } }));
      // Plain labels since the redesign of 2026-09-26 ("Deployment AUC" is "How well it tells high
      // pain from low"); the numbers are the same.
      expect(text).toMatch(/How well it tells high pain from low, on the data it was fitted to \(95% range\)0\.80 \(0\.70–0\.90\)/);
      expect(text).toMatch(/How well it tells high pain from low, with the stimulation current taken out0\.60 \(0\.50–0\.70\)/);
      expect(text).toMatch(/the Left current in force at each sample taken out of the band power as a straight line/);
      expect(text).toMatch(/the plain reading on those same samples is 0\.75 \(0\.65–0\.85\)/);
      expect(text).toMatch(/2 samples recorded before the first dated setting have no current/);
      expect(text).toMatch(/Descriptive only: the plain reading above sets every gate and the verdict/);
    });

    it("prints a refusal as a refusal, with its reason, never as a number", () => {
      const text = sheet(summaryWith({ ...PLAIN, auc_current_removed: {
        available: false, auc: null, why: "the current is constant at 2 across every sample" } }));
      expect(text).toMatch(/How well it tells high pain from low, with the stimulation current taken outnot computed/);
      expect(text).toMatch(/the current is constant at 2 across every sample/);
      expect(text).not.toMatch(/taken out—/);
    });

    it("prints nothing when an older response does not carry the reading", () => {
      const text = sheet(summaryWith({ ...PLAIN }));
      expect(text).not.toMatch(/with the stimulation current taken out/);
    });
  });
});
