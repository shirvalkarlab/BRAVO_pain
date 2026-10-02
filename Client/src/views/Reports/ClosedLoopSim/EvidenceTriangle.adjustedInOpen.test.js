/**
 * The band-power-to-pain link read with the stimulation current taken out is stated IN THE OPEN,
 * beside the plain reading (review finding, 2026-09-26). Since decision 302 the reading with the
 * current taken out sat only inside the closed "How this was worked out" fold, and the interim
 * current-confound sentence is suppressed whenever that reading exists, so the open card said
 * nothing about the current at all. Decisions 235 and 242 put this caveat in the open. The method
 * detail (partial correlation, the reason sentence) stays in the fold.
 *
 * ONE FIGURE, ON THE BIOMARKER MATCH WINDOW (the PI, 2026-10-02: "Window based on biomarker match").
 * The page showed this reading three ways: the sign-off card and ROC card from the summary's
 * match-window samples (0.75, 27 reports on L 0-3+ 25.5 Hz) and this card from the report's
 * settings-period estimator (0.607, 32 reports). This card now prints the summary's figure, to 2
 * decimals like the others, and never the report's. MATCH is modelled on that live summary; its
 * plain values on the same samples are constructed for the test.
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

const MATCH = {
  available: true, label: "with the stimulation current taken out", hemisphere: "Left",
  shape_words: "a straight line", auc: 0.7452, auc_low: 0.5503, auc_high: 0.9123,
  n_spectral_samples: 38, n_pain_reports: 27, partial_r: 0.31,
  plain_on_same_samples: { auc: 0.712, auc_low: 0.53, auc_high: 0.88, n_spectral_samples: 38, n_pain_reports: 27 },
};
const panel = (data, matchWindowAuc) => rtlRender(wrap(
  <EvidenceTrianglePanel report={{ data }} matchWindowAuc={matchWindowAuc} />)).container;

describe("the reading with the current taken out is in the open, on the biomarker match window", () => {
  it("one sentence carries both readings from the match window, to 2 decimals", () => {
    const container = panel(LEFT, MATCH);
    const open = container.querySelector("[data-testid='e2-current-open']");
    expect(open).toBeTruthy();
    const t = open.textContent;
    expect(t).toMatch(/biomarker match window/);
    expect(t).toMatch(/0\.71 \(0\.53 to 0\.88\)/);
    expect(t).toMatch(/0\.75 \(0\.55 to 0\.91\)/);
    expect(t).toMatch(/left stimulation current in force taken out/);
    expect(t).toMatch(/27 pain reports/);
  });

  it("the report's own settings-period reading is not printed anywhere", () => {
    const container = panel(LEFT, MATCH);
    // the fixture's E2.adjusted reads 0.553 (0.441 to 0.673) over 42 reports
    expect(container.textContent).not.toMatch(/0\.553/);
    expect(container.textContent).not.toMatch(/42 pain reports/);
  });

  it("the method detail stays in the fold", () => {
    const container = panel(LEFT, MATCH);
    expect(visibleText(container)).not.toMatch(/Correlation after taking the current out/);
    expect(container.textContent).toMatch(/Correlation after taking the current out \+0\.31/);
  });

  it("a reading that could not be made says so in the open, with its reason", () => {
    const container = panel(LEFT, { available: false, hemisphere: "Left",
      why: "the stimulation current is constant at 3 mA" });
    const t = visibleText(container);
    expect(t).toMatch(/could not be read with the left stimulation current taken out/);
    expect(t).toMatch(/constant at 3 mA/);
  });

  it("before the summary arrives, no such sentence is printed", () => {
    const container = panel(clone(LEFT), null);
    expect(container.querySelector("[data-testid='e2-current-open']")).toBeNull();
  });
});

describe("the page hands both cards the summary's match-window reading", () => {
  it("index.js takes it from the summary's evidence and passes it to the Evidence and ROC cards", () => {
    const src = require("fs").readFileSync(require("path").join(__dirname, "index.js"), "utf8");
    expect(src).toMatch(/summaryForBand\.data\.evidence\.auc_current_removed/);
    expect(src).toMatch(/<EvidenceTrianglePanel report=\{report\} matchWindowAuc=\{matchWindowAuc\} \/>/);
    expect(src).toMatch(/currentRemoved=\{matchWindowAuc\}/);
  });
});
