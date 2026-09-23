/**
 * What the next visit must deliver, on the current map (decision 239, wired 2026-09-23).
 *
 * The card's "Enough combinations tried?" check said only that coverage failed. The server now
 * carries, on every row whose coverage fails, which current pairs to repeat or add and why
 * (`coverage_gap`), and the card prints it under that check, cheapest way first. A row whose
 * coverage passes prints nothing extra.
 */
import "@testing-library/jest-dom";
import { render as rtlRender, screen, fireEvent } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";
import theme from "assets/theme";
import { PlatformContextProvider } from "context";
import CurrentMapCard from "./CurrentMapCard";
import response from "./__fixtures__/rcs08_stim_optimizer_two_stage.json";

jest.mock("plotly.js-dist", () => {
  const noop = () => {};
  return { react: () => Promise.resolve(), purge: noop, restyle: noop, relayout: noop, newPlot: noop };
});
jest.mock("graphing-utility/Plotly", () => ({
  PlotlyRenderManager: class {
    constructor() { this.traces = []; this.layout = {}; }
    subplots() {} clearData() {} render() {} setLayoutProps() {} setXlabel() {} setYlabel() {}
    addHeatmap() {} addScatter() {} addShape() {} addAnnotation() {} setTitle() {} purge() {}
  },
}));

const wrap = (ui) => (
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>
);

function planWithGap(gap, passes = false) {
  const base = response.two_stage;
  const rows = base.stage1.rate_strata.map((r) => (r.fitted && r.rate_hz === 55
    ? { ...r, coverage_passes: passes, coverage_gap: gap } : { ...r, coverage_gap: null }));
  return { ...base, stage1: { ...base.stage1, rate_strata: rows } };
}

const GAP = {
  n_pairs_missing: 1, stepped_side: "Left", held_side_mA: 2.5,
  pairs_to_top_up: [{ amp_mA_Left: 3, amp_mA_Right: 2.5, needs_more_ratings: 1, needs_more_days: 0 }],
  pairs_to_add: [{ amp_mA_Left: 4, amp_mA_Right: 2.5 }, { amp_mA_Left: 4.5, amp_mA_Right: 2.5 }],
  cheapest_way: "repeat L3/R2.5 (1 more rating) -- settings the record already has, which need topping up rather than a new pair",
  why: "this stratum needs 1 more current pair carrying enough ratings on enough days",
  what_each_pair_needs: "at least 5 ratings at that setting, on at least 2 different days",
};

describe("CurrentMapCard: what the next visit must deliver", () => {
  it("prints the cheapest way, the reason and the new pairs under a failing coverage check", () => {
    rtlRender(wrap(<CurrentMapCard plan={planWithGap(GAP)} />));
    const t = document.body.textContent;
    expect(t).toContain("What the next visit must deliver: repeat L3/R2.5 (1 more rating)");
    expect(t).toContain("this stratum needs 1 more current pair carrying enough ratings on enough days");
    expect(t).toContain("Each pair needs at least 5 ratings at that setting, on at least 2 different days.");
    expect(t).toContain("New settings that would also count: L4/R2.5, L4.5/R2.5.");
  });

  it("prints nothing extra where coverage passes or no gap came back", () => {
    rtlRender(wrap(<CurrentMapCard plan={planWithGap(null, true)} />));
    expect(document.body.textContent).not.toMatch(/What the next visit must deliver/);
  });
});
