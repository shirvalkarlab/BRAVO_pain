/**
 * ONE PAIN SCORE ON THE WHOLE PAGE (decision 307; found live 2026-09-26, the same class as the band
 * fix of decision 302).
 *
 * After the clinician changed the pain-score dropdown (Left Leg VAS -> NRS) and before Recompute,
 * the decision card still showed the previous score's full verdict and "Values to enter", its header
 * reading "pain score Left Leg VAS" under a dropdown reading NRS; only the recompute bar said the
 * settings had changed. A report or summary computed on another pain score -- or, for the summary,
 * with the clinic-sheet switch the other way -- is now withheld from every card exactly as one
 * computed for another band is, and the card names both and offers Recompute.
 */
import fs from "fs";
import path from "path";
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
import DecisionCard from "./DecisionCard";
// eslint-disable-next-line import/first
import { withheldIfOtherBand } from "./candidateRequestParams";
import LEFT from "./__fixtures__/rcs08_cl_L13_24p5_2026-09-25.json";
import SUM_L from "./__fixtures__/rcs08_summary_L13_24p5_2026-09-25.json";

const wrap = (ui) => (
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>
);
const clone = (o) => JSON.parse(JSON.stringify(o));
const BC_L = { contact: "ONE_THREE_LEFT", contact_label: "L 1-3+", center_freq_hz: 24.5, bandwidth_hz: 5,
  hemisphere: "Left" };
function visibleText(container) {
  const c = container.cloneNode(true);
  c.querySelectorAll(".MuiCollapse-hidden").forEach((n) => n.remove());
  return c.textContent;
}

/** The live left report as computed on Left Leg VAS. */
const LLVAS = (() => {
  const r = clone(LEFT);
  r.pain_score = { key: "left_leg_vas", label: "Left Leg VAS", requested: "left_leg_vas",
    fell_back_to_nrs: false, reason: null };
  return r;
})();

describe("a report computed on another pain score is withheld", () => {
  it("withholds it and names both scores", () => {
    const shown = withheldIfOtherBand({ data: LLVAS, loading: false, err: null, stale: true }, BC_L,
      "report", { painScore: "nrs" });
    expect(shown.data).toBeNull();
    expect(shown.bandMismatch).toEqual({ what: "pain score", chosen: "NRS (0–10)",
      computedFor: "Left Leg VAS" });
    expect(shown.err).toMatch(/Left Leg VAS/);
  });

  it("passes a report on the chosen score through untouched", () => {
    const same = { data: LLVAS, loading: false, err: null };
    expect(withheldIfOtherBand(same, BC_L, "report", { painScore: "left_leg_vas" })).toBe(same);
    // and a caller that names no pain score gets the band check alone, as before
    expect(withheldIfOtherBand(same, BC_L)).toBe(same);
  });

  it("names the band first when both the band and the score differ", () => {
    const other = clone(LLVAS);
    other.candidates = [{ ...other.candidates[0], channel: "ZERO_TWO_LEFT", center_hz: 23.5 }];
    const shown = withheldIfOtherBand({ data: other }, BC_L, "report", { painScore: "nrs" });
    expect(shown.bandMismatch.what).toBe("band");
    expect(shown.bandMismatch.computedFor).toMatch(/ZERO_TWO_LEFT at 23\.5 Hz/);
  });
});

describe("a summary computed on another pain score or clinic-sheet setting is withheld", () => {
  it("withholds a summary on another score", () => {
    expect(withheldIfOtherBand({ data: SUM_L }, BC_L, "summary",
      { painScore: "left_leg_vas", includeSheets: false }).data).toBeNull();
    expect(withheldIfOtherBand({ data: SUM_L }, BC_L, "summary",
      { painScore: "nrs", includeSheets: false }).data).toBe(SUM_L);
  });

  it("withholds a summary built with the clinic-sheet switch the other way", () => {
    const shown = withheldIfOtherBand({ data: SUM_L }, BC_L, "summary",
      { painScore: "nrs", includeSheets: true });
    expect(shown.data).toBeNull();
    expect(shown.bandMismatch).toEqual({ what: "clinic-sheet setting",
      chosen: "clinic-sheet ratings included", computedFor: "REDCap ratings only" });
  });
});

describe("the decision card says so and shows nothing computed on the old score", () => {
  it("names the score it was computed on, the chosen one, and offers Recompute", () => {
    const shown = withheldIfOtherBand({ data: LLVAS, loading: false, err: null, stale: true }, BC_L,
      "report", { painScore: "nrs" });
    const { container } = rtlRender(wrap(
      <DecisionCard participantUid="uid" bandCandidate={BC_L} deploymentReport={shown}
        summary={{ data: SUM_L, loading: false, err: null }} mode={null} onMode={() => {}}
        onRecompute={() => {}} />));
    const t = visibleText(container);
    expect(t).toMatch(/Recompute: the analysis shown is for Left Leg VAS/);
    expect(t).toMatch(/The chosen pain score is NRS \(0–10\)/);
    expect(t).toMatch(/Recompute for NRS \(0–10\)/);
    expect(t).not.toMatch(/Device allows it|Device refuses/);
    expect(t).not.toMatch(/Values withheld|Adaptive amplitude limit/);
  });
});

describe("the page hands the guard its current pain score and clinic-sheet switch", () => {
  it("both calls in the page file pass them", () => {
    const src = fs.readFileSync(path.join(__dirname, "index.js"), "utf8");
    expect(src).toMatch(/withheldIfOtherBand\(deploymentReport, bc, "report", \{ painScore \}\)/);
    expect(src).toMatch(/withheldIfOtherBand\(summary, bc, "summary", \{ painScore, includeSheets \}\)/);
  });
});
