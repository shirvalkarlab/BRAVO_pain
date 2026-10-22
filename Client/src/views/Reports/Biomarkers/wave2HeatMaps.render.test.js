/**
 * Wave 2 on the Biomarkers heat maps (decisions 484, 492-498), rendered from RCS08's live grid
 * response of 2026-10-22 (NRS, the page's defaults: 15-min window, nearest, tertiles, home surveys
 * only), captured in the server container through `band_time_sweep_for_participant`, the function the
 * API calls; and the same request with `ChronicMatch: "window"`.
 *
 * Pinned, with the values the live response carries:
 *   C4  the large maps name their grid and say it cannot choose; TD-only and PSD-only maps side by
 *       side, the PSD map "shown, cannot choose" with its reason;
 *   C5  ▼ marks above the columns the home record decides (R 0-3: 8.5, 9.5, 10.5, 11.5, 24.5, 26.5
 *       Hz); "Decided by" per band with that answer's r, interval and n, and the home record's
 *       report counts; the window-match warning only with the override;
 *   484 the current-removed check, 494 the daily swing, 496 the later 30% with its cut date, each a
 *       warning only;
 *   497/498 the q corrected within each pair, its footnote, and the status of a pair outside it.
 *
 * The DOM is queried directly (`document.querySelector`), not by role: on a page this large a role
 * query takes minutes (this host's notes, 2026-10-04).
 */
import "@testing-library/jest-dom";
import { render as rtlRender, fireEvent, waitFor } from "@testing-library/react";

import { invalidateAll, putResult, settingsKey } from "database/resultCache";
import { biomarkerHeatmapSlot } from "views/Reports/moduleCacheKeys";
import { wrap } from "testUtils/render";

import BiomarkerHeatmapGrids, { gridSettingsFor, gridStatusLine } from "./BiomarkerHeatmapGrids";
import GRID from "./__fixtures__/rcs08_wave2_grid_nrs_2026-10-22.json";
import GRID_WINDOW from "./__fixtures__/rcs08_wave2_grid_nrs_window_2026-10-22.json";

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
const REQ_WINDOW = { ...REQ, ChronicMatch: "window" };

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

describe("C4: which grid chooses, and the TD and PSD maps side by side", () => {
  it("the large maps are named the mixed grid, shown and unable to choose, with the server's reason", async () => {
    await renderGrid(GRID, REQ);
    expect(text('[data-testid="grid-source-line"]')).toBe(
      "Maps below: Mixed grid (TD, PSD where no TD) · shown, cannot choose. Mixed grid (TD, PSD "
      + "where no TD): shown, never chooses a band; the band is chosen from the TD-only grid.");
    // the old mixed-source sentence is replaced by the source caption: 399 of 471 reports from PSD
    expect(document.body.textContent).toMatch(
      /Mixed grid \(TD, PSD where no TD\): 399 of 471 matched reports \(85%\) read from PSD \(no TD in match window\); shown, cannot choose/);
    expect(document.body.textContent).not.toMatch(/had no TD in match window; read from PSD/);
  });

  it("TD-only and PSD-only maps are drawn side by side; PSD says it cannot choose and why", async () => {
    await renderGrid(GRID, REQ);
    expect(q("#biomarker-heatmap-td")).toBeTruthy();
    expect(q("#biomarker-heatmap-psd")).toBeTruthy();
    expect(text('[data-testid="source-grid-title-td"]')).toBe("R with pain: TD only · chooses the band");
    expect(text('[data-testid="source-grid-title-psd"]')).toBe("R with pain: PSD only · shown, cannot choose");
    expect(text('[data-testid="source-grid-psd-why"]')).toBe(
      "PSD only: shown, cannot choose a band (the PI, 2026-10-18); the band is chosen from the TD-only grid");
  });
});

describe("C5: who decides each band, and the home-record match", () => {
  it("▼ above the six columns the home record decides on R 0-3, drawn on the TD map only", async () => {
    await renderGrid(GRID, REQ);
    expect(document.body.textContent).toMatch(/▼ home record decides: 8\.5, 9\.5, 10\.5, 11\.5, 24\.5, 26\.5 Hz/);
    const td = global.__plotlyReact.filter((c) => c.id === "biomarker-heatmap-td").pop();
    expect(td.layout.annotations.map((a) => a.x)).toEqual([8.5, 9.5, 10.5, 11.5, 24.5, 26.5]);
    expect(td.layout.annotations.every((a) => a.text === "▼")).toBe(true);
    const psd = global.__plotlyReact.filter((c) => c.id === "biomarker-heatmap-psd").pop();
    expect(psd.layout.annotations).toEqual([]);
  });

  it("R 0-3 9.5 Hz: decided by the home record, its r, interval and n, and the report counts", async () => {
    await renderGrid(GRID, REQ);
    expect(text('[data-testid="band-decided-9.5"]')).toBe("home record");
    expect(text('[data-testid="band-r-9.5"]')).toBe("r +0.08 [−0.30, +0.30], n=30");
    expect(text('[data-testid="band-home-9.5"]')).toBe("30 matched · 429 in a gap · 142 log elsewhere");
    // a band the home record does not cover is decided by TD, with TD's own numbers
    expect(text('[data-testid="band-decided-15.5"]')).toBe("TD");
    expect(text('[data-testid="band-home-15.5"]')).toBe("no home record at this band");
  });

  it("no window-match warning at the recommended default", async () => {
    await renderGrid(GRID, REQ);
    expect(GRID.settings_applied.chronic_match).toBe("covering");
    expect(q('[data-testid="chronic-match-warning"]')).toBeNull();
    expect(document.body.textContent).toMatch(/Home record match applied: 10-minute average covering the report \(recommended\)/);
  });

  it("with the page matching window the warning shows above the maps and the band table, and the answer moves", async () => {
    await renderGrid(GRID_WINDOW, REQ_WINDOW);
    expect(GRID_WINDOW.settings_applied.chronic_match).toBe("window");
    const warnings = document.querySelectorAll('[data-testid="chronic-match-warning"]');
    expect(warnings.length).toBe(2);
    warnings.forEach((w) => expect(w.textContent).toMatch(
      /^▲Not the recommended default: this home-record answer pairs each pain report with the chronic readings within the page's matching window \(15 minutes either side\)\./));
    expect(text('[data-testid="band-r-9.5"]')).toBe("r −0.13 [−0.39, +0.24], n=39");
    expect(text('[data-testid="band-q-9.5"]')).toBe("q 0.68");
    expect(document.body.textContent).toMatch(/Home record match applied: Page matching window/);
  });
});

describe("484, 494, 496: the three warnings on each band", () => {
  it("R 0-3 9.5 Hz: current out warns, 2.6-fold daily swing, later 30% after 2026-04-03", async () => {
    await renderGrid(GRID, REQ);
    expect(text('[data-testid="band-current-9.5"]')).toBe("▲ warning · p 1.00");
    expect(text('[data-testid="band-swing-9.5"]')).toBe("▲ 2.6-fold (low 17:00, high 00:00)");
    expect(text('[data-testid="band-recent-9.5"]')).toBe("r +0.44 [0.00, +0.80], n=10");
    expect(document.body.textContent).toMatch(/Later 30% of ratings: after 2026-04-03 \(rolling cut\)/);
    // a band with no home record says so, with no hour blocks anywhere
    expect(text('[data-testid="band-swing-15.5"]')).toBe("no home record at this band");
    expect(document.body.textContent).not.toMatch(/hour block/i);
  });
});

describe("497/498: the q corrected within each pair", () => {
  it("R 0-3 9.5 Hz prints q 0.84, the footnote names each pair and its 22 bands", async () => {
    await renderGrid(GRID, REQ);
    expect(text('[data-testid="band-q-9.5"]')).toBe("q 0.84");
    expect(document.body.textContent).toMatch(
      /q: corrected within each pair: L 0⁻3⁺ across 22 bands; R 0⁻3⁺ across 22 bands/);
    // the per-grid q keeps its own name, never "corrected"
    expect(document.body.textContent).toMatch(/heavy ring: grid q < 0\.05 \(fdr 22 bands, this grid's own p/);
  });

  it("a pair outside the family prints its status on every band", async () => {
    await renderGrid(GRID, REQ);
    fireEvent.click(q('[data-testid="pair-thumb"][data-channel="ONE_THREE_LEFT"]'));
    await waitFor(() => expect(text('[data-testid="band-q-23.5"]')).toBe("not an allowed sensing pair"));
  });

  it("the status line counts the q within each allowed pair: none reaches 0.05 on RCS08 NRS", () => {
    expect(gridStatusLine(GRID, "NRS (0–10)")).toBe("NRS (0–10), 15-min window: corrected within each "
      + "allowed pair (L 0⁻3⁺, R 0⁻3⁺; 22 bands each), 0 bands rise with pain and 0 fall with it at q ≤ 0.05.");
  });

  it("L 0-3 12.5 Hz carries the server's warning as a marked q", async () => {
    await renderGrid(GRID, REQ);
    fireEvent.click(q('[data-testid="pair-thumb"][data-channel="ZERO_THREE_LEFT"]'));
    await waitFor(() => expect(text('[data-testid="band-q-12.5"]')).toBe("▲ q 0.88"));
    expect(q('[data-testid="band-q-12.5"]').getAttribute("title"))
      .toMatch(/this band's q is 0\.88: it may be a chance finding/);
  });
});
