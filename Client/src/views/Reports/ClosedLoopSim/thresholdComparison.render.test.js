/** Synthetic rendering contracts; no participant observations or empirical-validation claim. */
import "@testing-library/jest-dom";
import { render as rtlRender, fireEvent } from "@testing-library/react";
import { wrap } from "testUtils/render";

import ParameterTable from "./PrescriptionPanel";
import ThresholdComparison, { painText, sharesText, designText, pairWords } from "./ThresholdComparison";
import { REP27 } from "./__fixtures__/synthetic_november_contracts";
import { REP15 } from "./__fixtures__/synthetic_november_contracts";

jest.mock("plotly.js-dist", () => ({
  react: jest.fn(), purge: jest.fn(), restyle: jest.fn(), relayout: jest.fn(), newPlot: jest.fn(),
  toImage: jest.fn(),
}));
jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn() } }));

const ok = (data) => ({ data, loading: false, err: null });
const rows = () => Array.from(document.querySelectorAll('[data-testid="threshold-comparison-row"]'))
  .map((el) => el.textContent);
const showPlanning = (container) => fireEvent.click(Array.from(container.querySelectorAll("button"))
  .find((b) => b.textContent === "Show the values for planning (not for programming)"));

describe("Programmed now vs candidates (synthetic example, L 0-3 27.5 Hz, the band the device runs)", () => {
  it("the synthetic block carries the programmed pair from the device record and the three candidates", () => {
    const b = REP27.threshold_comparison;
    expect(b.programmed.group).toBe("GROUP_A");
    expect(b.programmed.side.upper).toBe(120);
    expect(b.programmed.side.lower).toBe(60);
    expect(b.programmed.side.centre_hz).toBe(27.50);
    expect(b.band.home_freq_hz).toBe(27.50);
    expect(b.band.n_home_readings).toBe(24);
    expect(b.rows.map((r) => r.key)).toEqual(
      ["programmed", "clinic_recordings", "manufacturer_guidance", "fitted_on_earlier_reports"]);
    expect(b.n_reports).toBe(8);
    expect(b.fit.n_fit).toBe(5);
    expect(b.fit.n_held_out).toBe(3);
    b.rows.forEach((r) => ["all", "day", "night"].forEach((k) => {
      const s = r.shares[k];
      expect(s.n_above + s.n_between + s.n_below).toBe(s.n);
    }));
  });

  it("withheld (the device refuses this band): no comparison table, no candidate number", () => {
    rtlRender(wrap(<ParameterTable report={ok(REP27)} mode="dual" />));
    expect(document.querySelector('[data-testid="threshold-comparison"]')).toBeNull();
    expect(document.body.textContent).not.toMatch(/140\.0/);
  });

  it("the planning view: four rows with synthetic example's values", () => {
    const { container } = rtlRender(wrap(<ParameterTable report={ok(REP27)} mode="dual" />));
    showPlanning(container);
    expect(container.textContent).toContain("Programmed now vs candidates");
    expect(container.textContent).toContain("NRS · home record L 0-3 27.50 Hz · n=8 reports");
    expect(rows()).toEqual([
      "Programmed now120.0 / 60.025 / 50 / 25%25 / 50 / 25%25%+4 [−2, +10] p 0.50 (2 vs 6)≤4",
      "(a) Clinic recordings130.0 / 70.025 / 50 / 25%25 / 50 / 25%25%+4 [−2, +10] p 0.50 (2 vs 6)≤4",
      "(b) Daytime 25th/75th140.0 / 80.025 / 50 / 25%25 / 50 / 25%25%+4 [−2, +10] p 0.50 (2 vs 6)≤4",
      "(c) Fitted, earlier reports150.0 / 90.025 / 50 / 25%25 / 50 / 25%25%+4 [−2, +10] p 0.50 (2 vs 6)≤4",
    ]);
    const lim = document.querySelector('[data-testid="threshold-comparison-limits"]');
    expect(lim.textContent).toMatch(/^▲8 NRS reports have a home reading at this band\. Too few/);
    expect(lim.textContent).toContain("A clinician programs the device; nothing here writes to it.");
    expect(container.textContent).toContain("Synthetic device frequency bins are shown without inventing home data.");
  });
});

describe("Programmed now vs candidates on a band with no home record (L 0-3 15.5 Hz)", () => {
  it("the programmed row names its own band; the candidates cannot be read at home", () => {
    rtlRender(wrap(<ThresholdComparison data={REP15} />));
    const r = rows();
    expect(r).toHaveLength(2);
    expect(r[0].startsWith("Programmed now (L 0-3 27.50 Hz)120.0 / 60.0")).toBe(true);
    expect(r[1]).toBe("(a) Clinic recordings130.0 / 70.0–––no reports≤4");
    expect(document.body.textContent).toContain(
      "The device runs L 0-3 27.50 Hz; this report's band is L 0-3 15.5 Hz");
    expect(document.body.textContent).toContain("No home record at this band");
  });
});

describe("cell formatting", () => {
  it("formats shares, pain, the design rule and pair names", () => {
    expect(sharesText({ above: 0.337, between: 0.285, below: 0.378 })).toBe("34 / 28 / 38%");
    expect(sharesText(null)).toBe("–");
    expect(painText({ n_reports: 0 })).toBe("no reports");
    expect(painText({ n_reports: 13, difference: { value: null, n_above: 13, n_rest: 0 } })).toBe("none (13 vs 0)");
    expect(painText({ n_reports: 3, difference: { value: -4, low: null, high: null, p_rotation: null, n_above: 2, n_rest: 2 } }))
      .toBe("−4 (2 vs 2)");
    expect(designText({ applies: false })).toBe("–");
    expect(designText({ applies: true, crossings_per_hour_at_most: 0.9 })).toBe("≤1");
    expect(pairWords("ZERO_THREE_RIGHT")).toBe("R 0-3");
  });

  it("nothing at all without the block (the neutral setting)", () => {
    rtlRender(wrap(<ThresholdComparison data={{ available: true }} />));
    expect(document.querySelector('[data-testid="threshold-comparison"]')).toBeNull();
  });
});

it("an unavailable comparison shows the server reason, with an honest fallback", () => {
  const out = rtlRender(wrap(<ThresholdComparison data={{ threshold_comparison: { available: false, reason: "no matching device record" } }} />));
  expect(out.container.textContent.trim()).toBe("Programmed now vs candidates: not available (no matching device record).");
  out.rerender(wrap(<ThresholdComparison data={{ threshold_comparison: { available: false } }} />));
  expect(out.container.textContent.trim()).toBe("Programmed now vs candidates: not available (no reason given).");
});

it("a sparse summary preserves unknowns, while zero remains a measured value", () => {
  const out = rtlRender(wrap(<ThresholdComparison data={{ threshold_comparison: {} }} />));
  expect(out.container.textContent).toContain("pain · home record  none · n=0 reports");
  out.rerender(wrap(<ThresholdComparison data={{ threshold_comparison: {
    rows: [{ key: "example", label: "Sparse candidate", upper: null, lower: NaN,
      shares: { day: { above: 0.2, between: null, below: 0.8 } },
      pain: { n_reports: 4, difference: { value: 0, low: null, n_above: 2, n_rest: 2 } },
      flags: ["Synthetic warning remains visible"] }],
  } }} />));
  expect(rows()[0]).toContain("Sparse candidate– / –20 / – / 80%––0 (2 vs 2)–");
  expect(out.container.textContent).toContain("▲Synthetic warning remains visible");
  expect(document.querySelector('[data-testid="threshold-comparison-limits"]')).toBeTruthy();
});

it("unrecognized pairs and missing pain differences are explicit", () => {
  expect(pairWords()).toBe("");
  expect(pairWords("OTHER")).toBe("OTHER");
  expect(pairWords("ZERO_THREE")).toBe("? 0-3");
  expect(painText({ n_reports: 4 })).toBe("none (4)");
  expect(painText({ n_reports: 4, difference: { value: 0, low: null, n_above: 2, n_rest: 2 } }))
    .toBe("0 (2 vs 2)");
});
