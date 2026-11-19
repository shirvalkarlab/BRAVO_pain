/**
 * Two things on the Closed-Loop page that read as empty or as a result when they were neither (the
 * PI, 2026-11-18):
 *   - the grid's "fdr" column printed a bare "–" on every RCS08 row, which looked like an empty
 *     column; each was a real "not clear" with its own q. The q is now printed, "✓" when q < 0.05.
 *   - the stability card printed "Not tested ... no band assessed" while the report was loading.
 * The grid is RCS08's live Closed-Loop grid of 2026-10-22 (the wave-2 fixture).
 */
import "@testing-library/jest-dom";
import { render as rtlRender } from "@testing-library/react";
import { wrap, clone } from "testUtils/render";

import BandSweepGridPanel from "./BandSweepGridPanel";
import BandStabilityPanel from "./BandStabilityPanel";
import CLGRID from "./__fixtures__/rcs08_wave2_clgrid_nrs_2026-10-22.json";

jest.mock("plotly.js-dist", () => ({ react: jest.fn(), purge: jest.fn(), newPlot: jest.fn() }));
jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn() } }));

const mountGrid = (grid) => rtlRender(wrap(<BandSweepGridPanel grid={grid} participantUid="uid"
  committed={{ contact: "ZERO_THREE_RIGHT", centerHz: 9.5 }}
  committedBySide={{ Left: { contact: "ZERO_THREE_LEFT", centerHz: 15.5 },
    Right: { contact: "ZERO_THREE_RIGHT", centerHz: 9.5 } }}
  onCandidateChosen={() => {}} />));

const rowsOf = (grid, ch) => {
  const s = grid.band_time_sweep[ch];
  return s.best_correlation_rows;
};

describe("the fdr column prints each band's grid q", () => {
  it("every shown row carries its own q to two places, never a bare dash", () => {
    mountGrid(CLGRID);
    const cells = Array.from(document.querySelectorAll('[data-testid="fdr-cell"]'));
    expect(cells.length).toBeGreaterThan(0);
    // the right side's first tab is the one shown; compare its rows' q with the cells, in order
    const shown = cells.map((c) => c.textContent);
    expect(shown.some((t) => t === "–")).toBe(false);
    const qs = rowsOf(CLGRID, "ZERO_THREE_RIGHT").map((r) => r.family_wise_q_8_to_30hz);
    const want = qs.filter((v) => v != null).map((v) => v.toFixed(2));
    // every value of R 0-3 appears among the cells (the left side's tab adds its own)
    want.forEach((w) => expect(shown.join(" ")).toMatch(w));
  });

  it("a band clear of the allowance shows a tick before its q", () => {
    const g = clone(CLGRID);
    const row = rowsOf(g, "ZERO_THREE_RIGHT").find((r) => r.band_center_hz === 9.5);
    row.family_wise_q_8_to_30hz = 0.031;
    row.family_wise_significant_8_to_30hz = true;
    mountGrid(g);
    const cells = Array.from(document.querySelectorAll('[data-testid="fdr-cell"]')).map((c) => c.textContent);
    expect(cells).toContain("✓0.03");
  });

  it("a row with no q still says not assessed", () => {
    const g = clone(CLGRID);
    rowsOf(g, "ZERO_THREE_RIGHT").forEach((r) => {
      r.family_wise_q_8_to_30hz = null; r.family_wise_significant_8_to_30hz = null;
    });
    mountGrid(g);
    expect(document.querySelectorAll('[aria-label="allowance not assessed"]').length).toBeGreaterThan(0);
  });
});

describe("the stability card while there is no report", () => {
  it("loading: says it is testing, never 'Not tested' or 'no band assessed'", () => {
    const { container } = rtlRender(wrap(<BandStabilityPanel stability={undefined} noReport loading />));
    expect(container.textContent).toMatch("Testing the chosen band…");
    expect(container.textContent).not.toMatch(/not tested/i);
    expect(container.textContent).not.toMatch("no band assessed");
  });

  it("failed: says the report has not loaded, with why", () => {
    const { container } = rtlRender(wrap(<BandStabilityPanel stability={undefined} noReport
      err="Network Error" />));
    expect(container.textContent).toMatch("No answer yet: the report for this band has not loaded (Network Error).");
    expect(container.textContent).not.toMatch(/not tested/i);
  });

  it("with a report, the four answers are drawn as before", () => {
    const { container } = rtlRender(wrap(<BandStabilityPanel stability={{ answer: "cannot tell",
      test_ran: true, band_center_hz: 9.5, band_width_hz: 5 }} />));
    expect(container.textContent).toMatch("Cannot tell");
    expect(container.querySelector('[data-testid="stability-waiting"]')).toBeNull();
  });
});
