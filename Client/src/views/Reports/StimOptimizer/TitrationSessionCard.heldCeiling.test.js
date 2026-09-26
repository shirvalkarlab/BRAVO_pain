/**
 * A held side is never held above its safe ceiling (decision 308). The server holds a side whose
 * current in force is above today's ceiling AT the ceiling and says why; the titration card and
 * the next-visit line print that sentence in the warning colour, and print nothing new when the
 * current in force is under the ceiling (RCS08 today: 3.0 mA left, 2.5 mA right, ceiling 4.5 mA).
 * Rendered against the live RCS08 plan of 2026-09-21 with the right side's current in force
 * raised to 4.8 mA, the value the left delivered before its ceiling was lowered.
 */
import "@testing-library/jest-dom";
import { render as rtlRender } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";
import theme from "assets/theme";
import { PlatformContextProvider } from "context";
import TitrationSessionCard from "./TitrationSessionCard";
import CurrentMapCard from "./CurrentMapCard";
import plan from "./__fixtures__/rcs08_titration_plan_exploratory.json";
import response from "./__fixtures__/rcs08_stim_optimizer_two_stage.json";

jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn(() => Promise.resolve({ data: {} })) } }));
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
const UID = "2e3c75c00d7f4f37b53a048d195f11da";
const NOTE = "the Right side's current in force, 4.8 mA, is above today's safe ceiling for that side, "
  + "4.5 mA; it is held at 4.5 mA for this ladder, not at the current in force -- set it to 4.5 mA before the first step";

function heldAbove(p) {
  const left = p.sides.Left;
  return {
    ...p,
    sides: {
      ...p.sides,
      Left: { ...left, held_other_side: { ...left.held_other_side, current_mA: 4.5, in_force_mA: 4.8,
        ceiling_mA: 4.5, above_ceiling: true, note: NOTE } },
    },
  };
}

describe("the titration card: the held side above its ceiling", () => {
  it("prints the held current at the ceiling and the server's sentence saying why", () => {
    rtlRender(wrap(<TitrationSessionCard plan={heldAbove(plan)} participantUid={UID} />));
    const t = document.body.textContent;
    expect(t).toMatch(/left's ladder holds right at4\.5[\s ]mA/);
    expect(t).toContain("Held at the ceiling: the Right side's current in force, 4.8 mA, is above today's safe ceiling");
    expect(t).toContain("not at the current in force — set it to 4.5 mA before the first step");
    expect(t).not.toContain("in force -- set");
  });

  it("prints no such sentence when the current in force is under the ceiling", () => {
    rtlRender(wrap(<TitrationSessionCard plan={plan} participantUid={UID} />));
    expect(document.body.textContent).not.toMatch(/Held at the ceiling/);
    expect(document.querySelectorAll("[data-testid='held-above-ceiling']").length).toBe(0);
  });
});

describe("the next-visit line: the held side above its ceiling", () => {
  function planWithGap(gap) {
    const base = response.two_stage;
    const rows = base.stage1.rate_strata.map((r) => (r.fitted && r.rate_hz === 55
      ? { ...r, coverage_passes: false, coverage_gap: gap } : { ...r, coverage_gap: null }));
    return { ...base, stage1: { ...base.stage1, rate_strata: rows } };
  }
  const GAP = {
    n_pairs_missing: 1, stepped_side: "Left", held_side_mA: 4.5,
    pairs_to_top_up: [], pairs_to_add: [{ amp_mA_Left: 4, amp_mA_Right: 4.5 }],
    cheapest_way: "run L4/R4.5",
    why: "this stratum needs 1 more current pair carrying enough ratings on enough days",
    what_each_pair_needs: "at least 5 ratings at that setting, on at least 2 different days",
    held_side_note: NOTE.replace("for this ladder", "for these pairs"),
  };

  it("prints the held-side sentence under the cheapest way", () => {
    rtlRender(wrap(<CurrentMapCard plan={planWithGap(GAP)} />));
    const t = document.body.textContent;
    expect(t).toContain("What the next visit must deliver: run L4/R4.5.");
    expect(t).toContain("it is held at 4.5 mA for these pairs, not at the current in force — set it to 4.5 mA");
  });

  it("prints nothing new when no side was held above its ceiling", () => {
    const { held_side_note: _drop, ...plain } = GAP;
    rtlRender(wrap(<CurrentMapCard plan={planWithGap(plain)} />));
    expect(document.body.textContent).not.toMatch(/above today's safe ceiling/);
  });
});
