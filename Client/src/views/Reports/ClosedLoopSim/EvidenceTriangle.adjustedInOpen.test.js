/**
 * The band-power-to-pain link read with the stimulation current taken out is stated IN THE OPEN,
 * beside the plain reading (review finding, 2026-09-26). Since decision 302 the reading with the
 * current taken out sat only inside the closed "How this was worked out" fold, and the interim
 * current-confound sentence is suppressed whenever that reading exists, so the open card said
 * nothing about the current at all. Decisions 235 and 242 put this caveat in the open. The method
 * detail (partial correlation, the reason sentence) stays in the fold.
 *
 * Rendered against the live RCS08 response of 2026-09-25 (L 1-3+ at 24.5 Hz, NRS): plain 0.564
 * (0.438 to 0.678), with the left current taken out 0.553 (0.441 to 0.673), 42 pain reports.
 */
import "@testing-library/jest-dom";
import { render as rtlRender } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";

import theme from "assets/theme";
import { PlatformContextProvider } from "context";

import EvidenceTrianglePanel from "./EvidenceTrianglePanel";
import LEFT from "./__fixtures__/rcs08_cl_L13_24p5_2026-09-25.json";

const wrap = (ui) => (
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>
);
const clone = (o) => JSON.parse(JSON.stringify(o));
/** Text a reader can see: everything outside a closed fold. */
function visibleText(container) {
  const c = container.cloneNode(true);
  c.querySelectorAll(".MuiCollapse-hidden").forEach((n) => n.remove());
  return c.textContent;
}

describe("the reading with the current taken out is in the open", () => {
  it("one sentence carries both readings, plain and with the current taken out", () => {
    const { container } = rtlRender(wrap(<EvidenceTrianglePanel report={{ data: LEFT }} />));
    const open = container.querySelector("[data-testid='e2-current-open']");
    expect(open).toBeTruthy();
    const t = open.textContent;
    expect(t).toMatch(/0\.564 \(0\.438 to 0\.678\)/);
    expect(t).toMatch(/0\.553 \(0\.441 to 0\.673\)/);
    expect(t).toMatch(/stimulation current in force taken out/);
    expect(visibleText(container)).toMatch(/0\.553 \(0\.441 to 0\.673\)/);
  });

  it("the method detail stays in the fold", () => {
    const { container } = rtlRender(wrap(<EvidenceTrianglePanel report={{ data: LEFT }} />));
    expect(visibleText(container)).not.toMatch(/Correlation after taking the current out/);
    expect(container.textContent).toMatch(/Correlation after taking the current out/);
  });

  it("a reading that could not be made says so in the open, with its reason", () => {
    const d = clone(LEFT);
    d.edges.E2.adjusted = { available: false, why: "the stimulation current is constant at 3 mA",
      adjusted_for_words: "the left stimulation current" };
    const { container } = rtlRender(wrap(<EvidenceTrianglePanel report={{ data: d }} />));
    const t = visibleText(container);
    expect(t).toMatch(/could not be read with the left stimulation current taken out/);
    expect(t).toMatch(/constant at 3 mA/);
  });

  it("a report with no such reading prints no such sentence", () => {
    const d = clone(LEFT);
    delete d.edges.E2.adjusted;
    const { container } = rtlRender(wrap(<EvidenceTrianglePanel report={{ data: d }} />));
    expect(container.querySelector("[data-testid='e2-current-open']")).toBeNull();
  });
});
