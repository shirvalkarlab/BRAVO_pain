/**
 * The separate area-under-the-curve q (open item of decision 497) in the Closed-Loop "Band
 * selection" q column, rendered from RCS08's live Closed-Loop grid of 2026-10-22 (the wave-2
 * fixture, NRS at the page's remembered settings) with the AUC family's fields as
 * `family_correction.correct` puts them on that same choosing view
 * (`Biomarkers/__fixtures__/rcs08_open_aucq_nrs_2026-10-22.json`, made in the server container).
 *
 * Pinned: the q column prints the correlation q, then the AUC q ("0.96 · 1.00" on R 0-3 9.5 Hz);
 * the warning mark stays on L 0-3 12.5 Hz from the correlation q; the hover names both; the footnote
 * names each pair's own AUC family; a grid served before the AUC family prints as it did.
 */
import "@testing-library/jest-dom";
import { render as rtlRender, fireEvent } from "@testing-library/react";
import { wrap } from "testUtils/render";

import BandSweepGridPanel, { qCell } from "./BandSweepGridPanel";
import CLGRID from "./__fixtures__/rcs08_wave2_clgrid_nrs_2026-10-22.json";
import AUCQ from "views/Reports/Biomarkers/__fixtures__/rcs08_open_aucq_nrs_2026-10-22.json";

jest.mock("plotly.js-dist", () => ({
  react: jest.fn(), purge: jest.fn(), restyle: jest.fn(), relayout: jest.fn(), newPlot: jest.fn(),
  toImage: jest.fn(),
}));
jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn() } }));

const q = (sel) => document.querySelector(sel);
const text = (sel) => { const el = q(sel); return el ? el.textContent : null; };
const tab = (side, label) => Array.from(document.querySelectorAll(`[data-testid="band-side-${side}"] button`))
  .find((b) => b.textContent.replace("✕", "") === label);

function withAucQ(grid) {
  const g = JSON.parse(JSON.stringify(grid));
  Object.entries(AUCQ.closed_loop).forEach(([ch, rows]) => {
    const sw = g.band_time_sweep[ch];
    if (!sw) return;
    const by = new Map(rows.map((r) => [Number(r.band_center_hz), r]));
    sw.best_auc_rows.forEach((a) => Object.assign(a, by.get(Number(a.band_center_hz)) || {}));
  });
  g.family_correction = { ...g.family_correction, ...AUCQ.closed_loop_block };
  return g;
}

const mount = (grid) => rtlRender(wrap(<BandSweepGridPanel grid={grid} participantUid="uid"
  committed={{ contact: "ZERO_THREE_RIGHT", centerHz: 9.5 }}
  committedBySide={{ Left: { contact: "ZERO_THREE_LEFT", centerHz: 15.5 },
    Right: { contact: "ZERO_THREE_RIGHT", centerHz: 9.5 } }}
  onCandidateChosen={() => {}} />));

describe("Band selection: the AUC q in the q column, its own family", () => {
  it("R 0-3 9.5 Hz prints 0.96 · 1.00 and the hover names both families", () => {
    mount(withAucQ(CLGRID));
    const id = "cl-band-ZERO_THREE_RIGHT-9.5-q";
    expect(text(`[data-testid="${id}"]`)).toBe("0.96 · 1.00");
    expect(q(`[data-testid="${id}"]`).getAttribute("title")).toBe(
      "q 0.96, corrected within this pair; AUC q 1.00, its own family, corrected within this pair");
    expect(text('[data-testid="band-grid-family-auc"]')).toBe(
      "AUC q: its own family, corrected within each pair: L 0⁻3⁺ across 22 bands; R 0⁻3⁺ across 22 bands, "
      + "by each AUC row's own shuffle p");
    // the correlation footnote is unchanged
    expect(text('[data-testid="band-grid-family"]')).toBe(
      "q: corrected within each pair: L 0⁻3⁺ across 22 bands; R 0⁻3⁺ across 22 bands, by the deciding source's p");
  });

  it("L 0-3: 15.5 Hz 0.87 · 0.74; 12.5 Hz keeps the correlation warning mark", () => {
    mount(withAucQ(CLGRID));
    fireEvent.click(tab("Left", "L 0⁻3⁺"));
    expect(text('[data-testid="cl-band-ZERO_THREE_LEFT-15.5-q"]')).toBe("0.87 · 0.74");
    expect(text('[data-testid="cl-band-ZERO_THREE_LEFT-12.5-q"]')).toBe("▲0.87 · 0.75");
    expect(q('[data-testid="cl-band-ZERO_THREE_LEFT-12.5-q"]').getAttribute("title"))
      .toMatch(/this band's q is 0\.87: it may be a chance finding; AUC q 0\.75, its own family/);
  });

  it("a pair outside both families prints out · out", () => {
    mount(withAucQ(CLGRID));
    fireEvent.click(tab("Left", "L 1⁻3⁺"));
    expect(text('[data-testid="cl-band-ONE_THREE_LEFT-23.5-q"]')).toBe("out · out");
  });

  it("a grid served before the AUC family prints the correlation q alone, and no AUC footnote", () => {
    mount(CLGRID);
    expect(text('[data-testid="cl-band-ZERO_THREE_RIGHT-9.5-q"]')).toBe("0.96");
    expect(q('[data-testid="band-grid-family-auc"]')).toBeNull();
    // a warned established AUC row marks the cell even when the correlation q is not warned
    expect(qCell({ family_q_status: "in the family", family_q: 0.5, family_q_auc_status: "in",
      family_q_auc: 0.4, family_q_auc_warning: "w" }).text).toBe("▲0.50 · 0.40");
  });
});
