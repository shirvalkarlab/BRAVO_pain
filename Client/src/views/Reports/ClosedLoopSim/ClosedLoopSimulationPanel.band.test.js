/**
 * The simulated closed loop is about ONE band, and says which (review findings, 2026-09-26):
 *
 * - its band label read `bandCandidate.channel` while the page hands it the chosen band, which
 *   carries `contact`, so the label never printed;
 * - it ignored `stale`, so a simulation read for an earlier report was drawn unmarked;
 * - it never checked the simulation was computed for the chosen band: right after a band change the
 *   cache hands back the previous band's simulation, and the panel drew it under the new band's page
 *   (the report and the summary are withheld in that case since decision 302; the simulation was not);
 * - it printed the controller's switching values and current limits while the device refuses the
 *   configuration, which the decision card withholds, and the limits to one decimal of a milliamp.
 */
import "@testing-library/jest-dom";
import { render } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";

import theme from "assets/theme";
import { PlatformContextProvider } from "context";

jest.mock("plotly.js-dist", () => ({
  react: jest.fn(), purge: jest.fn(), restyle: jest.fn(), relayout: jest.fn(), newPlot: jest.fn(),
}));

// eslint-disable-next-line import/first
import ClosedLoopSimulationPanel from "./ClosedLoopSimulationPanel";
// eslint-disable-next-line import/first
import { withheldIfOtherBand } from "./candidateRequestParams";

const wrap = (ui) => (
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>
);

const model = { frac_time_at_upper: 0.3, frac_time_at_lower: 0.2, frac_time_above: 0.3,
  frac_time_between: 0.4, frac_time_below: 0.3, transitions_per_hour: 3, n_transitions_undone: 0,
  undone_per_hour: 0, mean_amplitude_mA: 3.1, amp_hist: [1, 2], longest_run_at_upper_s: 60 };
const run = { active_model: "M1", models: { M0: model, M1: model },
  curves: { M1: { kind: "linear", slope_per_mA: -3, n_points: 10, n_runs: 3 } },
  params: { amp_low_mA: 1.4, amp_high_mA: 4.5, lower: 191.1398, upper: 241.1398 },
  drawn: [], record: {}, amp_hist_edges_mA: [1.4, 3, 4.5] };
const simFor = (channel, hz) => ({ available: true, timing_runs: { programmed: run, recommended: run },
  inputs: { contact: channel, centre_used_hz: hz }, candidate: { channel, center_hz: hz } });
const SIM_L = simFor("ONE_THREE_LEFT", 24.5);
const BC_L = { contact: "ONE_THREE_LEFT", contact_label: "L 1-3+", center_freq_hz: 24.5, hemisphere: "Left" };
const contactLabel = (ch) => ({ ONE_THREE_LEFT: "L 1-3+", ZERO_TWO_LEFT: "L 0-2+" }[ch] || ch);
const panel = (sim, extra = {}) => render(wrap(
  <ClosedLoopSimulationPanel sim={sim} hemisphere="Left" contactLabel={contactLabel} bandCandidate={BC_L}
    deviceAllows {...extra} />));

describe("the simulation names its band and is withheld for any other", () => {
  it("prints the chosen band's label", () => {
    const { container } = panel({ data: SIM_L, loading: false, err: null });
    expect(container.textContent).toMatch(/L 1-3\+ · 24\.5 Hz/);
  });
  it("a simulation computed for another band is withheld, naming both bands", () => {
    const shown = withheldIfOtherBand({ data: simFor("ZERO_TWO_LEFT", 23.5), loading: false, err: null },
      BC_L, "simulation");
    expect(shown.data).toBeNull();
    const { container } = panel(shown);
    expect(container.textContent).toMatch(/ZERO_TWO_LEFT at 23\.5 Hz/);
    expect(container.textContent).toMatch(/L 1-3\+ at 24\.5 Hz/);
    expect(container.textContent).not.toMatch(/Closing the loop moves/);
  });
  it("the simulation for the chosen band is not withheld", () => {
    const same = { data: SIM_L, loading: false, err: null };
    expect(withheldIfOtherBand(same, BC_L, "simulation")).toBe(same);
  });
  it("a stale simulation says so", () => {
    const { container } = panel({ data: SIM_L, loading: false, err: null, stale: true, staleReasons: [] });
    expect(container.textContent).toMatch(/last completed run/);
  });
});

describe("the controller settings follow the decision card's rule", () => {
  it("the current limits in caption C are printed to two decimals when the device allows it", () => {
    const { container } = panel({ data: SIM_L, loading: false, err: null });
    expect(container.textContent).toMatch(/between the limits 1\.40–4\.50 mA/);
  });
  it("while the device refuses, no switching value or current limit is printed", () => {
    const { container } = panel({ data: SIM_L, loading: false, err: null }, { deviceAllows: false });
    expect(container.textContent).not.toMatch(/191\.1/);
    expect(container.textContent).not.toMatch(/241\.1/);
    expect(container.textContent).not.toMatch(/1\.40–4\.50/);
    expect(container.textContent).not.toMatch(/1\.4–4\.5/);
    expect(container.textContent).toMatch(/withheld: the device has not allowed this configuration/);
  });
});
