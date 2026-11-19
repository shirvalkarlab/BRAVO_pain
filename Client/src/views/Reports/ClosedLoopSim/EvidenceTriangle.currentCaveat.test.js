/**
 * The interim caveat on the band-power-to-pain edge, and the provisional sentence in the open.
 *
 * WHY. The triangle's second edge (band power to pain) is estimated with no term for the
 * stimulation current that was running at the time. Measured on 2026-09-22: on this participant's
 * left lead, taking the current in force out of the same band family shrinks every positive reading
 * (on L 0-3+, 22.5-27.5 Hz, +0.08 to +0.20 becomes +0.01 to +0.12 against NRS). Until that edge is
 * re-estimated with the current taken out, a clinician reading this card should see the fact stated,
 * not have to know it. The caveat is scoped: the left lead, and the band family that was measured.
 *
 * The second half: the module already writes "PROVISIONAL: ... intervals span zero ... the pattern
 * rests on the point signs alone" into the coherence note, and the card kept it inside a fold. The
 * sentence that says the verdict rests on point signs alone is not a detail; it reads in the open.
 *
 * Merged here 2026-10-05: EvidenceTriangle.adjustedInOpen.test.js,
 * EvidenceTriangle.noColumnNames.test.js, EvidenceTriangle.source.test.js. Each merged file's
 * tests sit in a describe block named after it, with its reason above it.
 */

import "@testing-library/jest-dom";
import { render as rtlRender } from "@testing-library/react";
import EvidenceTrianglePanel from "./EvidenceTrianglePanel";
import payload from "./__fixtures__/rcs08_deployment_payload_2026-09-15.json";
import LEFT from "./__fixtures__/rcs08_cl_L13_24p5_2026-09-25.json";
import earlyPayload from "./__fixtures__/rcs08_deployment_payload.json";
import { clone, wrap } from "testUtils/render";

jest.mock("plotly.js-dist", () => ({
  react: jest.fn(), purge: jest.fn(), restyle: jest.fn(), relayout: jest.fn(), newPlot: jest.fn(),
  toImage: jest.fn(),
}));

const withCandidate = (channel, centerHz) => {
  const d = JSON.parse(JSON.stringify(payload));
  d.candidates = [{ ...(d.candidates || [{}])[0], channel, center_hz: centerHz }];
  return d;
};

const CAVEAT = /stimulation current in force/i;

describe("the band-power-to-pain edge names the current in force as an unadjusted confound", () => {
  it("says it for a left-lead band inside the family that was measured", () => {
    const { container } = rtlRender(wrap(
      <EvidenceTrianglePanel report={{ data: withCandidate("ZERO_THREE_LEFT", 24.5) }} />));
    const text = container.textContent;
    expect(text).toMatch(CAVEAT);
    // the measurement itself, so the sentence is a finding and not an opinion
    expect(text).toMatch(/\+0\.08/);
    expect(text).toMatch(/\+0\.01/);
    // and it says plainly that this link carries no such adjustment yet
    // PIN CHANGED 2026-09-26 (auditor): "edge" became "link" per SPEC section 6.
    expect(text).toMatch(/this link is not adjusted for it/i);
  });

  it("does not say it on the right lead, where the measurement was not made", () => {
    const { container } = rtlRender(wrap(
      <EvidenceTrianglePanel report={{ data: withCandidate("ZERO_THREE_RIGHT", 24.5) }} />));
    expect(container.textContent).not.toMatch(CAVEAT);
  });

  it("does not say it for a left band outside the family that was measured", () => {
    const { container } = rtlRender(wrap(
      <EvidenceTrianglePanel report={{ data: withCandidate("ZERO_THREE_LEFT", 12.5) }} />));
    expect(container.textContent).not.toMatch(CAVEAT);
  });
});

// A closed fold keeps its children mounted (`Collapse unmountOnExit={false}`), so "the text is in
// the document" says nothing about whether a reader can see it. These helpers ask the question that
// matters: is the sentence inside a fold that is currently closed?
const leafWith = (root, re) => Array.from(root.querySelectorAll("*"))
  .filter((el) => el.children.length === 0 && re.test(el.textContent || ""))[0];
const insideClosedFold = (el) => {
  let n = el;
  while (n) {
    if (n.classList && n.classList.contains("MuiCollapse-hidden")) return true;
    n = n.parentElement;
  }
  return false;
};

describe("the coherence note is one fold again (decision 302, superseding decision 235's split)", () => {
  // Decision 235 printed the note's "PROVISIONAL: ... intervals span zero" half in the open. By
  // 2026-09-26 the same fact was on the page three more times -- each edge row's "INTERVAL SPANS
  // ZERO" with its numbers, the triangle's "uncertain" labels, and the decision card's status
  // line -- and the PI ruled that repeated statements go. Updated on purpose: the whole note,
  // both halves, sits in "How the sign agreement was tested".
  it("keeps the provisional half, now inside the closed fold", () => {
    const { container } = rtlRender(wrap(
      <EvidenceTrianglePanel report={{ data: withCandidate("ZERO_THREE_LEFT", 24.5) }} />));
    expect(container.textContent).toMatch(/How the sign agreement was tested/);
    const node = leafWith(container, /rests on the point signs alone/i);
    expect(node).toBeTruthy();
    expect(insideClosedFold(node)).toBe(true);
  });

  it("the edge rows still say, in the open, which intervals span zero", () => {
    const { container } = rtlRender(wrap(
      <EvidenceTrianglePanel report={{ data: withCandidate("ZERO_THREE_LEFT", 24.5) }} />));
    // Plain words since the redesign of 2026-09-26: "SIGN − (INTERVAL SPANS ZERO)" reads "... the
    // range crosses zero, so not yet certain" (SPEC section 6).
    const node = leafWith(container, /the range crosses zero, so not yet certain/);
    expect(node).toBeTruthy();
    expect(insideClosedFold(node)).toBe(false);
  });

  it("leaves the rest of the note where it was, inside the fold", () => {
    const { container } = rtlRender(wrap(
      <EvidenceTrianglePanel report={{ data: withCandidate("ZERO_THREE_LEFT", 24.5) }} />));
    const rest = leafWith(container, /Dual Threshold ramps amplitude UP/i);
    expect(rest).toBeTruthy();
    expect(insideClosedFold(rest)).toBe(true);
  });
});

/* From EvidenceTriangle.adjustedInOpen.test.js.
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
describe("from EvidenceTriangle.adjustedInOpen", () => {
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
});

/* From EvidenceTriangle.noColumnNames.test.js.
 * No column name on the evidence triangle (decision 314, following 313). The line that reads E2
 * again with the current taken out printed "the stimulation current in force (amp_mA_Left)": the
 * name of a table column, in front of a clinician. Since 2026-10-02 the line reads the summary's
 * match-window reading, which names the side (`hemisphere`); with no side it reads "the stimulation
 * current in force", never the column.
 */
describe("from EvidenceTriangle.noColumnNames", () => {
  const report = () => {
    const d = JSON.parse(JSON.stringify(payload));
    d.candidates = [{ ...(d.candidates || [{}])[0], channel: "ONE_THREE_LEFT", center_hz: 24.5 }];
    return { data: d };
  };

  const line = (container) => container.querySelector("[data-testid='e2-adjusted']").textContent;

  describe("the evidence triangle names the current in words, never its column", () => {
    it("names the side in words", () => {
      const { container } = rtlRender(wrap(<EvidenceTrianglePanel report={report()} matchWindowAuc={{
        available: true, adjusted_for: "amp_mA_Left", hemisphere: "Left",
        auc: 0.469, auc_low: 0.348, auc_high: 0.596, partial_r: -0.114, n_pain_reports: 30,
      }} />));
      expect(line(container)).toMatch(/^With the left stimulation current in force taken out of the band power, on the biomarker match window: 0\.47/);
      expect(container.textContent).not.toMatch(/amp_mA/);
    });

    it("with no side named, still shows no column", () => {
      const { container } = rtlRender(wrap(<EvidenceTrianglePanel report={report()} matchWindowAuc={{
        available: false, adjusted_for: "amp_mA_Left",
        why: "this band's power moves almost exactly with the left stimulation current on these samples",
      }} />));
      expect(line(container)).toMatch(/^With the stimulation current in force taken out of the band power, on the biomarker match window: not made here/);
      expect(container.textContent).not.toMatch(/amp_mA/);
    });
  });
});

/* From EvidenceTriangle.source.test.js.
 * Review 2026-09-15, finding C1. On the committed band E1 is the screening statistic (its note
 * begins "SCREENING STATISTIC ONLY") and was drawn exactly like a measured edge. The payload now
 * carries `edges.E1.source`; the triangle must draw a screening E1 differently and say the word.
 */
describe("from EvidenceTriangle.source", () => {
  const withSource = (source) => {
    const d = JSON.parse(JSON.stringify(earlyPayload));
    d.edges.E1.source = source;
    return { data: d, loading: false, err: null };
  };

  test("a screening E1 is drawn dotted and labelled 'screening'", () => {
    const { container } = rtlRender(wrap(<EvidenceTrianglePanel report={withSource("screening_historical")} />));
    const line = container.querySelector('line[data-edge="E1"]');
    expect(line).not.toBeNull();
    expect(line.getAttribute("stroke-dasharray")).toBe("1.5 3.5");
    expect(container.textContent).toMatch(/screening/i);
  });

  test("a pooled-titration E1 keeps the solid measured-edge stroke and carries no screening label", () => {
    const { container } = rtlRender(wrap(<EvidenceTrianglePanel report={withSource("pooled_titration")} />));
    const line = container.querySelector('line[data-edge="E1"]');
    expect(line.getAttribute("stroke-dasharray")).toBeNull();
    // the legend may explain the convention; the LABEL must not be on this edge
    expect(container.textContent).not.toMatch(/screening statistic, not a measurement/i);
  });
});
