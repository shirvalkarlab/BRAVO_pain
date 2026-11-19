/**
 * The separate area-under-the-curve q (open item of decision 497) in the Biomarkers band table,
 * rendered from RCS08's live grid response of 2026-10-22 (the wave-2 fixture, NRS at the page's
 * defaults) with the AUC family's fields as `family_correction.attach` puts them on that same
 * response (`__fixtures__/rcs08_open_aucq_nrs_2026-10-22.json`, made in the server container from
 * the fixture with its own sensing rule; the correlation q came out field-for-field unchanged).
 *
 * Pinned: the "AUC q" column beside the correlation q, its live values (R 0-3 9.5 Hz AUC q 0.64,
 * the correlation q still 0.84), a warned established AUC row on L 0-3 29.5 Hz, the status on a pair
 * outside the family, and the footnote naming each pair's own AUC family.
 */
import "@testing-library/jest-dom";
import { render as rtlRender, fireEvent, waitFor } from "@testing-library/react";

import { invalidateAll, putResult, settingsKey } from "database/resultCache";
import { biomarkerHeatmapSlot } from "views/Reports/moduleCacheKeys";
import { wrap } from "testUtils/render";

import BiomarkerHeatmapGrids, { gridSettingsFor, gridStatusLine } from "./BiomarkerHeatmapGrids";
import GRID from "./__fixtures__/rcs08_wave2_grid_nrs_2026-10-22.json";
import AUCQ from "./__fixtures__/rcs08_open_aucq_nrs_2026-10-22.json";
import { familyQAucWords, familyAucFootnote } from "./gridReadouts";

jest.mock("plotly.js-dist", () => {
  const noop = () => {};
  const react = (id, traces, layout) => {
    const el = typeof id === "string" ? global.document.getElementById(id) : id;
    if (el) { el.on = noop; el.removeAllListeners = noop; el.data = []; }
    (global.__plotlyReact = global.__plotlyReact || []).push({ id, layout });
    return Promise.resolve();
  };
  return { react, purge: noop, restyle: noop, relayout: noop, newPlot: noop };
});
jest.mock("graphing-utility/Plotly", () => ({
  PlotlyRenderManager: class {
    constructor(divId) { this.divId = divId; this.traces = []; this.layout = {}; }
    subplots() {} clearData() {} render() {} setXlabel() {} setYlabel() {} purge() {}
    setLayoutProps(props) { Object.assign(this.layout, props); }
  },
}));
jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn() } }));
jest.mock("views/Reports/ClosedLoopSim/neighbourPrefetch", () => ({
  prefetchClosedLoopFromBiomarkers: () => Promise.resolve(),
}));
// eslint-disable-next-line import/first
import { SessionController } from "database/session-control";

const UID = "2e3c75c00d7f4f37b53a048d195f11da";
const METRICS = [{ key: "nrs", label: "NRS (0–10)" }];
const REQ = { source: "both", LabelMetric: "nrs", LabelStrategy: "tertile", PercentileLow: 33.3333,
  PercentileHigh: 66.6667, MatchToleranceMin: 15, MatchDirection: "nearest", AllowWindowReuse: false,
  IncludeClinicSheetRatings: false, SlidingWindow: false };

const q = (sel) => document.querySelector(sel);
const text = (sel) => { const el = q(sel); return el ? el.textContent : null; };

async function renderGrid(grid, req) {
  putResult(biomarkerHeatmapSlot("nrs"), UID, settingsKey(gridSettingsFor(req, "nrs")), grid,
    { why: "wave 2 render test" });
  let status = null;
  const out = rtlRender(wrap(
    <BiomarkerHeatmapGrids participantUid={UID} requestParams={req} availableMetrics={METRICS}
      pageMetric="nrs" metricLabel="NRS (0–10)" onOpenInClosedLoop={() => {}}
      onStatus={(s) => { status = s; }} />,
  ));
  await waitFor(() => expect(q('[data-testid="pair-thumb"][data-channel="ZERO_THREE_RIGHT"]')).toBeTruthy());
  fireEvent.click(q('[data-testid="pair-thumb"][data-channel="ZERO_THREE_RIGHT"]'));
  await waitFor(() => expect(q('[data-testid="band-choice-table"]')).toBeTruthy());
  return { ...out, status: () => status };
}

beforeEach(() => {
  global.__plotlyReact = [];
  invalidateAll("wave 2 render test");
  SessionController.query.mockReset();
  SessionController.query.mockImplementation(() => Promise.resolve({ data: { boot_token: "boot-1" } }));
});


/** The wave-2 grid with the AUC family's fields put on each TD-only AUC row (a copy). */
function withAucQ(grid) {
  const g = JSON.parse(JSON.stringify(grid));
  Object.entries(AUCQ.biomarkers).forEach(([ch, rows]) => {
    const td = g.band_time_sweep[ch] && g.band_time_sweep[ch].by_source_grid
      && g.band_time_sweep[ch].by_source_grid.td;
    if (!td) return;
    const by = new Map(rows.map((r) => [Number(r.band_center_hz), r]));
    td.best_auc_rows.forEach((a) => Object.assign(a, by.get(Number(a.band_center_hz)) || {}));
  });
  g.family_correction = { ...g.family_correction, ...AUCQ.biomarkers_block };
  return g;
}

describe("the AUC q in the band table: its own family, within each pair", () => {
  it("R 0-3 9.5 Hz: AUC q 0.64 beside the unchanged correlation q 0.84", async () => {
    await renderGrid(withAucQ(GRID), REQ);
    expect(text('[data-testid="band-q-auc-9.5"]')).toBe("AUC q 0.64");
    expect(text('[data-testid="band-q-9.5"]')).toBe("q 0.84");
    expect(document.body.textContent).toMatch(
      /AUC q: its own family, corrected within each pair: L 0⁻3⁺ across 22 bands; R 0⁻3⁺ across 22 bands/);
    expect(document.body.textContent).toMatch(
      /q: corrected within each pair: L 0⁻3⁺ across 22 bands; R 0⁻3⁺ across 22 bands/);
  });

  it("L 0-3 29.5 Hz: an established AUC row above 0.05 is marked, with the server's warning", async () => {
    await renderGrid(withAucQ(GRID), REQ);
    fireEvent.click(q('[data-testid="pair-thumb"][data-channel="ZERO_THREE_LEFT"]'));
    await waitFor(() => expect(text('[data-testid="band-q-auc-29.5"]')).toBe("▲ AUC q 0.46"));
    expect(q('[data-testid="band-q-auc-29.5"]').getAttribute("title")).toBe(
      "After correcting for the 22 area-under-the-curve bands tested on L 0⁻3⁺, this band's q is "
      + "0.46: it may be a chance finding");
  });

  it("a pair outside the family prints its status in the AUC q column", async () => {
    await renderGrid(withAucQ(GRID), REQ);
    fireEvent.click(q('[data-testid="pair-thumb"][data-channel="ONE_THREE_LEFT"]'));
    await waitFor(() => expect(text('[data-testid="band-q-auc-23.5"]')).toBe("not an allowed sensing pair"));
  });

  it("a grid served before the AUC family prints an empty AUC q and no AUC footnote", async () => {
    await renderGrid(GRID, REQ);
    expect(text('[data-testid="band-q-auc-9.5"]')).toBe("");
    expect(document.body.textContent).not.toMatch(/AUC q: its own family/);
    expect(familyQAucWords(null)).toBeNull();
    expect(familyAucFootnote({ available: false })).toBeNull();
  });
});
