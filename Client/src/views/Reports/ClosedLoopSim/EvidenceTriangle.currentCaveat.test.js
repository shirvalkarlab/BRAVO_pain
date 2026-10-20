/** Synthetic UI contract regression. No live participant response or empirical validation. */
import "@testing-library/jest-dom";
import { render as rtlRender } from "@testing-library/react";
import EvidenceTrianglePanel from "./EvidenceTrianglePanel";
import payload from "./__fixtures__/synthetic_provisional_grid.json";
import LEFT from "./__fixtures__/synthetic_allowed_left.json";
import earlyPayload from "./__fixtures__/synthetic_blocked_rules.json";
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

const CAVEAT = /no displayed estimate adjusted for the current in force/i;

describe("unadjusted band-power-to-pain evidence carries a general caveat", () => {
  it.each([
    ["ZERO_THREE_LEFT", 24.5],
    ["ZERO_THREE_RIGHT", 24.5],
    ["ZERO_THREE_LEFT", 12.5],
  ])("states the limitation independently of side or band: %s / %s Hz", (channel, hz) => {
    const { container } = rtlRender(wrap(
      <EvidenceTrianglePanel report={{ data: withCandidate(channel, hz) }} />));
    expect(container.textContent).toMatch(CAVEAT);
    expect(container.textContent).not.toMatch(/\+0\.08|\+0\.01/);
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


describe("from EvidenceTriangle.adjustedInOpen", () => {
  
  function visibleText(container) {
    const c = container.cloneNode(true);
    c.querySelectorAll(".MuiCollapse-hidden").forEach((n) => n.remove());
    return c.textContent;
  }

  const MATCH = {
    available: true, label: "with the stimulation current taken out", hemisphere: "Left",
    shape_words: "a straight line", auc: 0.8125, auc_low: 0.625, auc_high: 0.9375,
    n_spectral_samples: 24, n_pain_reports: 8, partial_r: 0.31,
    plain_on_same_samples: { auc: 0.7, auc_low: 0.5, auc_high: 0.9, n_spectral_samples: 24, n_pain_reports: 8 },
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
      expect(t).toMatch(/0\.70 \(0\.50 to 0\.90\)/);
      expect(t).toMatch(/0\.81 \(0\.63 to 0\.94\)/);
      expect(t).toMatch(/left stimulation current in force taken out/);
      expect(t).toMatch(/8 pain reports/);
    });

    it("the report's own settings-period reading is not printed anywhere", () => {
      const report = clone(LEFT);
      report.edges.E2.adjusted = { available: true, auc: 0.625, auc_low: 0.5,
        auc_high: 0.75, n_pain_reports: 12 };
      const container = panel(report, MATCH);
      expect(container.textContent).not.toMatch(/0\.625/);
      expect(container.textContent).not.toMatch(/12 pain reports/);
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
        auc: 0.6, auc_low: 0.5, auc_high: 0.7, partial_r: -0.2, n_pain_reports: 8,
      }} />));
      expect(line(container)).toMatch(/^With the left stimulation current in force taken out of the band power, on the biomarker match window: 0\.60/);
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
