/**
 * The six sensing-pair tabs above the "Choose a band" grid each have a name of their own (decision
 * 307; found live 2026-09-26). A screen reader heard "Left GPi" three times and "Right VIM" three
 * times -- the region, from the tab's hover title -- so the three pairs on a side could not be told
 * apart. Each tab's accessible name now carries its pair and then its region ("L 1⁻3⁺, Left GPi"),
 * and the tab in force says it is pressed.
 */
import "@testing-library/jest-dom";
import { render as rtlRender, screen } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";

import theme from "assets/theme";
import { PlatformContextProvider } from "context";

jest.mock("plotly.js-dist", () => ({
  react: jest.fn(), purge: jest.fn(), restyle: jest.fn(), relayout: jest.fn(), newPlot: jest.fn(),
}));
jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn() } }));

// eslint-disable-next-line import/first
import BandSweepGridPanel from "./BandSweepGridPanel";
import payload from "./__fixtures__/rcs08_deployment_payload_2026-09-15.json";

const render = (ui) => rtlRender(
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>,
);

describe("the sensing-pair tabs have distinct accessible names", () => {
  it("names each tab by its pair and its region, and no two alike", () => {
    const sweeps = payload.band_sweep_grid.band_time_sweep;
    render(<BandSweepGridPanel grid={payload.band_sweep_grid} participantUid="uid"
      committed={{ contact: "ONE_THREE_LEFT", centerHz: 24.5 }} onCandidateChosen={() => {}} />);
    const chans = Object.keys(sweeps);
    expect(chans.length).toBeGreaterThanOrEqual(2);
    const names = chans.map((ch) => {
      const sw = sweeps[ch];
      const want = sw.display_region ? `${sw.display_short}, ${sw.display_region}` : sw.display_short;
      const btn = screen.getByRole("button", { name: want });
      return btn.getAttribute("aria-label");
    });
    expect(new Set(names).size).toBe(names.length);
    // the same region never stands alone as a tab's name
    const regions = new Set(chans.map((ch) => sweeps[ch].display_region).filter(Boolean));
    regions.forEach((r) => expect(screen.queryByRole("button", { name: r })).toBeNull());
  });

  it("says which tab is in force", () => {
    const sweeps = payload.band_sweep_grid.band_time_sweep;
    render(<BandSweepGridPanel grid={payload.band_sweep_grid} participantUid="uid"
      committed={{ contact: "ONE_THREE_LEFT", centerHz: 24.5 }} onCandidateChosen={() => {}} />);
    const sw = sweeps.ONE_THREE_LEFT;
    const on = screen.getByRole("button", { name: `${sw.display_short}, ${sw.display_region}` });
    expect(on).toHaveAttribute("aria-pressed", "true");
    const other = Object.keys(sweeps).find((ch) => ch !== "ONE_THREE_LEFT");
    const o = sweeps[other];
    expect(screen.getByRole("button", { name: o.display_region ? `${o.display_short}, ${o.display_region}` : o.display_short }))
      .toHaveAttribute("aria-pressed", "false");
  });
});
