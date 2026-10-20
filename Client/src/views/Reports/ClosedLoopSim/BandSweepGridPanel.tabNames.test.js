/** Synthetic UI contract regression. No live participant response or empirical validation. */
import "@testing-library/jest-dom";
import { render as rtlRender, screen } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";
import theme from "assets/theme";
import { PlatformContextProvider } from "context";
import BandSweepGridPanel, { allowanceWords } from "./BandSweepGridPanel";
import payload from "./__fixtures__/synthetic_provisional_grid.json";

jest.mock("plotly.js-dist", () => ({
  react: jest.fn(), purge: jest.fn(), restyle: jest.fn(), relayout: jest.fn(), newPlot: jest.fn(),
}));
jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn() } }));

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


describe("from BandSweepGridPanel.qLabel", () => {
  describe("allowanceWords", () => {
    it("names the number q, and says the p it corrects rather than being called p itself", () => {
      expect(allowanceWords(0.002)).toBe("q 0.002 (fdr 22 bands)");
    });

    it("takes the band count it was given", () => {
      // 18, not the default 22: with 22 this test also passed when the count was ignored.
      expect(allowanceWords(0.002, 18)).toBe("q 0.002 (fdr 18 bands)");
    });

    it("is null when no q is given, same as before", () => {
      expect(allowanceWords(null)).toBeNull();
    });
  });

  test("the grid tooltip carries the corrected value once, with no brackets inside brackets", () => {
    const fs = require("fs");
    const src = fs.readFileSync(require.resolve("./BandSweepGridPanel.js"), "utf8");
    expect(src).not.toMatch(/tested\$\{words \? ` \(\$\{words\}\)`/);
  });
});
