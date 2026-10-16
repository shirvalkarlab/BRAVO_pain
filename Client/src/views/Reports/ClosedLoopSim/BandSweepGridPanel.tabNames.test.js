/**
 * The six sensing-pair tabs above the "Choose a band" grid each have a name of their own (decision
 * 307; found live 2026-09-26). A screen reader heard "Left GPi" three times and "Right VIM" three
 * times -- the region, from the tab's hover title -- so the three pairs on a side could not be told
 * apart. Each tab's accessible name now carries its pair and then its region ("L 1⁻3⁺, Left GPi"),
 * and the tab in force says it is pressed.
 *
 * Merged here 2026-10-05: BandSweepGridPanel.qLabel.test.js. Each merged file's tests sit in a
 * describe block named after it, with its reason above it.
 */

import "@testing-library/jest-dom";
import { render as rtlRender, screen } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";
import theme from "assets/theme";
import { PlatformContextProvider } from "context";
import BandSweepGridPanel, { allowanceWords } from "./BandSweepGridPanel";
import payload from "./__fixtures__/rcs08_deployment_payload_2026-09-15.json";

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

/* From BandSweepGridPanel.qLabel.test.js.
 * The "Choose a band" grid's family-wise mark named the corrected value it prints "p"
 * ("p 0.002 after allowing for all 22 bands tested"), but the number the server sends
 * (`family_wise_q_8_to_30hz`) is a Benjamini-Hochberg q, not a p. The PI, 2026-09-26: print it as
 * q, with the correction named in words -- "q 0.002 (fdr 22 bands)".
 */
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
