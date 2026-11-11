/**
 * Page review 2026-10-02 (item 4.2): the Background panel drew L 1-3+ under "(the chosen band)"
 * while the chosen band was L 0-3+ 25.5 Hz. L 0-3+ has no stepped-current runs on RCS08, so the
 * panel fell back to the first left contact and checked only the frequency before naming it the
 * chosen band. It now says the chosen pair has no runs and which pair it shows instead, and keeps
 * "(the chosen band)" for the chosen pair itself.
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

// eslint-disable-next-line import/first
import ThreeSourceResponsePanel from "./ThreeSourceResponsePanel";

const contact = (name, runs) => ({
  sensing_contact: name, n_runs: runs, n_visits: runs, stimulation_rates_hz: [], runs: [],
  pooled_by_centre: [{ band_centre_hz: 25.5, pooled_slope_per_mA: -15.25, pooled_slope_stderr: 19.76,
    pooled_slope_p: 0.45, n: 33 }],
});
const POOLED = { data: { sides: [{ ramped_side: "Left",
  contacts: [contact("ONE_THREE_LEFT", 5), contact("ZERO_TWO_LEFT", 1)] }] } };
const LABEL = (ch) => ({ ONE_THREE_LEFT: "L 1-3+", ZERO_THREE_LEFT: "L 0-3+", ZERO_TWO_LEFT: "L 0-2+" }[ch] || ch);

const text = (committed) => rtlRender(
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>
      <ThreeSourceResponsePanel pooled={POOLED} report={null} committed={committed} contactLabel={LABEL} />
    </PlatformContextProvider>
  </ThemeProvider>).container.textContent;

describe("the Background panel names the chosen band only for the chosen contact pair", () => {
  it("chosen pair without runs: says so, shows another pair, and does not call it the chosen band", () => {
    const t = text({ contact: "ZERO_THREE_LEFT", centerHz: 25.5 });
    expect(t).toContain("No stepped-current runs on L 0-3+; showing L 1-3+");
    expect(t).not.toContain("(the chosen band)");
  });
  it("chosen pair with runs: drawn and labelled the chosen band, no fallback line", () => {
    const t = text({ contact: "ONE_THREE_LEFT", centerHz: 25.5 });
    expect(t).toContain("(the chosen band)");
    expect(t).not.toContain("No stepped-current runs");
  });
});
