/** Synthetic UI contract regression. No live participant response or empirical validation. */
import fs from "fs";
import path from "path";
import "@testing-library/jest-dom";
import { render as rtlRender } from "@testing-library/react";

import theme from "assets/theme";
import { T } from "assets/theme/base/tokens";
import { wrap, clone } from "testUtils/render";

jest.mock("plotly.js-dist", () => ({
  react: jest.fn(), purge: jest.fn(), restyle: jest.fn(), relayout: jest.fn(), newPlot: jest.fn(),
  toImage: jest.fn(),
}));
jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn() } }));
jest.mock("layouts/DatabaseLayout", () => ({ children }) => <div>{children}</div>);
jest.mock("graphing-utility/Plotly", () => ({
  PlotlyRenderManager: class { subplots() {} clearData() {} render() {} setLayoutProps() {} purge() {} },
}));

// eslint-disable-next-line import/first
import DecisionCard, { ContentsRow, JUMPS } from "./DecisionCard";
// eslint-disable-next-line import/first
import ParameterTable, { fmtProgrammed } from "./PrescriptionPanel";
// eslint-disable-next-line import/first
import { CrossGlyph } from "./glyphs";
// eslint-disable-next-line import/first
import BandCandidateIdentity, { verdictState } from "./BandCandidateIdentity";
// eslint-disable-next-line import/first
import { DOCUMENT_TITLE, PAGE_QUESTION } from "./index";
// eslint-disable-next-line import/first
import LEFT from "./__fixtures__/synthetic_allowed_left.json";
// eslint-disable-next-line import/first
import RIGHT from "./__fixtures__/synthetic_refused_right.json";
// eslint-disable-next-line import/first
import SUM_R from "./__fixtures__/synthetic_summary_right.json";

const render = (ui) => rtlRender(wrap(ui));
const src = (f) => fs.readFileSync(path.join(__dirname, f), "utf8");
const pageFiles = fs.readdirSync(__dirname).filter((f) => f.endsWith(".js") && !f.endsWith(".test.js"));


const hex = (rgb) => {
  const m = String(rgb).match(/\d+/g);
  return m ? `#${m.slice(0, 3).map((n) => Number(n).toString(16).padStart(2, "0")).join("")}` : rgb;
};

const BC_R = { contact: "ZERO_THREE_RIGHT", contact_label: "R 0-3+", center_freq_hz: 24.5, bandwidth_hz: 5,
  hemisphere: "Right" };

describe("C10: one number grouping per row", () => {
  it("prints the programmed value with the Value column's formatter", () => {
    expect(fmtProgrammed({ units: "ms", programmed: 30000 })).toBe("30 000");
    expect(fmtProgrammed({ units: "ms", programmed: "30000" })).toBe("30 000");
    expect(fmtProgrammed({ units: "mA", programmed: 3 })).toBe("3.00");
    expect(fmtProgrammed({ units: "LFP power", programmed: 242 })).toBe("242.0000");
    expect(fmtProgrammed({ units: "mode", programmed: "dual" })).toBe("dual");
    expect(fmtProgrammed({ units: "ms" })).toBeNull();
  });

  it("the table shows the same grouping in both columns of an onset row", () => {
    const { container } = render(<ParameterTable report={{ data: LEFT, loading: false }} mode="dual" onMode={() => {}} />);
    const row = Array.from(container.querySelectorAll("[data-param-row]"))
      .find((r) => /Upper onset duration/.test(r.textContent));
    expect(row).toBeTruthy();
    expect(row.textContent).not.toMatch(/30000/);
    expect((row.textContent.match(/30 000/g) || []).length).toBe(2);
  });
});

describe("C3 and C11: the contents row", () => {
  it("carries the jump-row class and no middle dot", () => {
    const { container } = render(<ContentsRow />);
    const nav = container.querySelector("nav");
    expect(nav).toHaveClass("paper-jump-row");
    expect(nav.textContent).not.toMatch(/·/);
    JUMPS.forEach((j) => expect(nav.textContent).toContain(j.label));
  });
});

describe("C5: section headings balance their line breaks", () => {
  it("every section-title and answer heading in the page files spreads WRAP.balance", () => {
    pageFiles.forEach((f) => {
      const s = src(f);
      const bare = s.match(/\.\.\.TYPE\.(title|answer), (?!\.\.\.WRAP\.balance)/g) || [];
      expect({ file: f, bare }).toEqual({ file: f, bare: [] });
    });
  });
});

describe("C6 and C7: the page head", () => {
  const page = src("index.js");
  it("is the shared PageHead, with the shared CeilingLine", () => {
    expect(page).toMatch(/import PageHead from "views\/Reports\/paper\/PageHead"/);
    expect(page).toMatch(/<PageHead title=\{PAGE_QUESTION\}/);
    expect(page).toMatch(/<CeilingLine leftMa=/);
    expect(page).not.toMatch(/component="h1"/);
    expect(PAGE_QUESTION).toBe("Closed-loop feasibility and entry values");
  });
  it("names the browser tab", () => {
    expect(DOCUMENT_TITLE).toBe("Closed-loop deployment");
    expect(page).toMatch(/documentTitle=\{DOCUMENT_TITLE\}/);
  });
});

describe("C9: empty values are words", () => {
  it("no page file prints an em dash for a missing value", () => {
    pageFiles.forEach((f) => {
      expect({ file: f, dash: /(\? |\?\? |\|\| |: )"—"/.test(src(f)) }).toEqual({ file: f, dash: false });
    });
  });
});

describe("D4: sentence case", () => {
  it("no uppercase transform and no page-written capitals", () => {
    pageFiles.forEach((f) => {
      const s = src(f);
      expect({ file: f, t: /textTransform: "uppercase"|text-transform: *uppercase/.test(s) })
        .toEqual({ file: f, t: false });
    });
    expect(src("DeploySignoffCard.js")).not.toMatch(/NOT THE SAME/);
    expect(src("EraRefitPanel.js")).not.toMatch(/WRONG way|REVERSED against/);
  });
});

describe("D5: no coloured tags", () => {
  it("the band identity draws its verdict as text with its glyph, and uses no chip", () => {
    expect(src("BandCandidateIdentity.js")).not.toMatch(/<Chip/);
    expect(verdictState("VALIDATED (stim-stable)").glyph).toBe("✓");
    expect(verdictState("failed").glyph).toBe("▲");
    expect(verdictState("failed").ink).not.toBe(T.refused);
    const { container } = render(<BandCandidateIdentity bc={{ verdict: "failed", adaptive_valid: false,
      contact: "ONE_THREE_LEFT", center_freq_hz: 24.5 }} envelope={null} />);
    const v = container.querySelector("[data-discovery-verdict]");
    expect(v.textContent).toBe("▲failed");
    expect(container.textContent).toMatch(/▲outside the adaptive band/);
  });
});

describe("D14: red only for the device refusing", () => {
  it("the device's refusal bullets stay red with ✕ and their words", () => {
    const { container } = render(
      <DecisionCard participantUid="uid" bandCandidate={BC_R}
        deploymentReport={{ data: RIGHT, loading: false, err: null }}
        summary={{ data: SUM_R, loading: false, err: null }}
        chosenBand={{ band_candidate: BC_R }} bandRecord={{ where: "server", saved: true }}
        mode={null} onMode={() => {}} />);
    const bullets = Array.from(container.querySelectorAll(".cl-bullets-red li [data-bullet]"));
    expect(bullets.length).toBeGreaterThan(0);
    bullets.forEach((b) => {
      expect(b.textContent).toMatch(/^(Unmet|Unchecked): /);
      expect(hex(b.style.color || getComputedStyle(b).color)).toBe(T.refused.toLowerCase());
    });
  });

  it("the analysis's own blocker sentences are ink with ✕, never red, and printed as sent", () => {
    const rep = clone(RIGHT);
    rep.verdict_detail.blockers = ["only one therapeutic Right amplitude on record for this cell (3 mA), "
      + "so no low and high capture amplitudes exist (D24) and no thresholds were placed"];
    const { container } = render(
      <DecisionCard participantUid="uid" bandCandidate={BC_R}
        deploymentReport={{ data: rep, loading: false, err: null }}
        summary={{ data: SUM_R, loading: false, err: null }}
        chosenBand={{ band_candidate: BC_R }} bandRecord={{ where: "server", saved: true }}
        mode={null} onMode={() => {}} />);
    const el = container.querySelector("[data-blocker]");
    expect(el).toBeTruthy();
    expect(el.textContent).toBe(`✕${rep.verdict_detail.blockers[0]}`);
    expect(hex(getComputedStyle(el).color)).toBe(T.ink.toLowerCase());
  });

  it("the statistical cross glyph is filled in ink, not red", () => {
    const { container } = render(<CrossGlyph label="different" />);
    const fill = container.querySelector("rect").getAttribute("fill");
    expect(fill).toBe(T.ink);
    expect(fill).not.toBe(T.refused);
  });
});
