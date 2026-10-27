/**
 * Programmed now vs candidates on the threshold card (the PI, 2026-10-26; a label only), rendered from
 * RCS08's live Closed-Loop reports captured in the server container on 2026-10-26 through
 * `run_for_participant` with the pain reports frozen (`__fixtures__/rcs08_c7opt_cl_L03_27p5_2026-10-26.json`
 * and `..._L03_15p5_...`; no serials, export names replaced, saved-answer hashes replaced by
 * placeholders, the participant code kept).
 *
 * L 0-3 27.5 Hz is the band the device runs (27.34 Hz, 373 / 251, group D). Pinned with the real
 * values: the four rows, their day and night shares, the time at the upper current, the pain
 * difference with its interval and p, the design rule's crossings, the limits sentence (13 reports,
 * too few) in caution ink, and that nothing is shown while the values are withheld. On L 0-3 15.5 Hz
 * (no home record) the programmed row names its own band and the note says the candidates cannot be
 * read at home (the design rule's crossings still apply: they come from the clinic recordings).
 */
import "@testing-library/jest-dom";
import { render as rtlRender, fireEvent } from "@testing-library/react";
import { wrap } from "testUtils/render";

import ParameterTable from "./PrescriptionPanel";
import ThresholdComparison, { painText, sharesText, designText, pairWords } from "./ThresholdComparison";
import REP27 from "./__fixtures__/rcs08_c7opt_cl_L03_27p5_2026-10-26.json";
import REP15 from "./__fixtures__/rcs08_c7opt_cl_L03_15p5_2026-10-26.json";

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

describe("Programmed now vs candidates (RCS08, L 0-3 27.5 Hz, the band the device runs)", () => {
  it("the live block carries the programmed pair from the device record and the three candidates", () => {
    const b = REP27.threshold_comparison;
    expect(b.programmed.group).toBe("GROUP_D");
    expect(b.programmed.side.upper).toBe(373);
    expect(b.programmed.side.lower).toBe(251);
    expect(b.programmed.side.centre_hz).toBe(27.34);
    expect(b.band.home_freq_hz).toBe(27.34);
    expect(b.band.n_home_readings).toBe(2424);
    expect(b.rows.map((r) => r.key)).toEqual(
      ["programmed", "clinic_recordings", "manufacturer_guidance", "fitted_on_earlier_reports"]);
    expect(b.n_reports).toBe(13);
    expect(b.fit.n_fit).toBe(9);
    expect(b.fit.n_held_out).toBe(4);
    b.rows.forEach((r) => ["all", "day", "night"].forEach((k) => {
      const s = r.shares[k];
      expect(s.n_above + s.n_between + s.n_below).toBe(s.n);
    }));
  });

  it("withheld (the device refuses this band): no comparison table, no candidate number", () => {
    rtlRender(wrap(<ParameterTable report={ok(REP27)} mode="dual" />));
    expect(document.querySelector('[data-testid="threshold-comparison"]')).toBeNull();
    expect(document.body.textContent).not.toMatch(/426\.5/);
  });

  it("the planning view: four rows with RCS08's values", () => {
    const { container } = rtlRender(wrap(<ParameterTable report={ok(REP27)} mode="dual" />));
    showPlanning(container);
    expect(container.textContent).toContain("Programmed now vs candidates");
    expect(container.textContent).toContain("Left Leg VAS · home record L 0-3 27.34 Hz · n=13 reports");
    expect(rows()).toEqual([
      "Programmed now373.0 / 251.034 / 28 / 38%2 / 5 / 92%28%+12 [−11, +30] p 0.23 (6 vs 7)≤599",
      "(a) Clinic recordings216.5 / 176.573 / 6 / 21%11 / 8 / 81%46%none (13 vs 0)≤596",
      "(b) Daytime 25th/75th426.5 / 204.025 / 50 / 25%2 / 12 / 86%35%+5 [−23, +33] p 0.69 (4 vs 9)≤599",
      "(c) Fitted, earlier reports361.0 / 201.037 / 39 / 24%3 / 11 / 86%39%+8 [−23, +26] p 0.46 (7 vs 6)≤599",
    ]);
    const lim = document.querySelector('[data-testid="threshold-comparison-limits"]');
    expect(lim.textContent).toMatch(/^▲13 Left Leg VAS reports have a home reading at this band, 13 of them filed 07:00-20:00, over 17 days\. Too few/);
    expect(lim.textContent).toContain("A clinician programs the device; nothing here writes to it.");
    expect(container.textContent).toContain("the other pages file the same readings by the device's 0.98 Hz bins (27.34 Hz as 27.3, 28.32 Hz as 28.3)");
  });
});

describe("Programmed now vs candidates on a band with no home record (L 0-3 15.5 Hz)", () => {
  it("the programmed row names its own band; the candidates cannot be read at home", () => {
    rtlRender(wrap(<ThresholdComparison data={REP15} />));
    const r = rows();
    expect(r).toHaveLength(2);
    expect(r[0].startsWith("Programmed now (L 0-3 27.34 Hz)373.0 / 251.0")).toBe(true);
    expect(r[1]).toBe("(a) Clinic recordings401.6 / 361.6–––no reports≤598");
    expect(document.body.textContent).toContain(
      "The device runs L 0-3 27.34 Hz; this report's band is L 0-3 15.5 Hz");
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
