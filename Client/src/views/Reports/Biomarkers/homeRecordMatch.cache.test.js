/**
 * "Home record match" (wave 2, C5, decision 493) reaches the request and the saved-result key.
 *
 * The control's two choices are "10-minute average covering the report (recommended)" (the
 * default, "covering") and "Page matching window" ("window"). The page sends `ChronicMatch` only when
 * it is not the default (`chronicMatchParam`), so a default request, and the key its saved grid is
 * filed under, is exactly what it was before the control existed. Choosing the window must:
 *   1. send `ChronicMatch: "window"` in the heat-map request body;
 *   2. file the grid under a different key in the shared result cache (`resultCache.settingsKey`),
 *      so the default grid is never served for it, and say the grid on screen is out of date naming
 *      "the home record match" until it is rebuilt.
 * Rendered through the real control, the real heat-map component and the real cache, with the
 * server mocked; the page's own wiring (index.js) is pinned by reading its source.
 */
import "@testing-library/jest-dom";
import fs from "fs";
import path from "path";
import { useState } from "react";
import { render as rtlRender, fireEvent, waitFor } from "@testing-library/react";

import { getResult, invalidateAll, settingsKey } from "database/resultCache";
import { biomarkerHeatmapSlot } from "views/Reports/moduleCacheKeys";
import { wrap } from "testUtils/render";

import BiomarkerHeatmapGrids, { gridSettingsFor, settingsChangedWords } from "./BiomarkerHeatmapGrids";
import HomeRecordMatchControl from "./HomeRecordMatchControl";
import { MATCHING_DEFAULTS, CHRONIC_MATCH_OPTIONS, chronicMatchParam } from "./matchingDefaults";
import GRID from "./__fixtures__/rcs08_wave2_grid_nrs_2026-10-22.json";
import GRID_WINDOW from "./__fixtures__/rcs08_wave2_grid_nrs_window_2026-10-22.json";

jest.mock("plotly.js-dist", () => {
  const noop = () => {};
  const react = (id) => {
    const el = typeof id === "string" ? global.document.getElementById(id) : id;
    if (el) { el.on = noop; el.removeAllListeners = noop; el.data = []; }
    return Promise.resolve();
  };
  return { react, purge: noop, restyle: noop, relayout: noop, newPlot: noop };
});
jest.mock("graphing-utility/Plotly", () => ({
  PlotlyRenderManager: class {
    constructor() { this.traces = []; this.layout = {}; }
    subplots() {} clearData() {} render() {} setXlabel() {} setYlabel() {} purge() {}
    setLayoutProps(p) { Object.assign(this.layout, p); }
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
const BASE = { source: "both", LabelMetric: "nrs", LabelStrategy: "tertile", PercentileLow: 33.3333,
  PercentileHigh: 66.6667, MatchToleranceMin: 15, MatchDirection: "nearest", AllowWindowReuse: false,
  IncludeClinicSheetRatings: false, SlidingWindow: false };

/** The page's wiring in small: the control's state spread into the heat maps' request, as index.js does. */
function Harness() {
  const [chronicMatch, setChronicMatch] = useState(MATCHING_DEFAULTS.chronicMatch);
  const req = { ...BASE, ...chronicMatchParam(chronicMatch) };
  return (
    <>
      <HomeRecordMatchControl value={chronicMatch} onChange={setChronicMatch} />
      <BiomarkerHeatmapGrids participantUid={UID} requestParams={req} availableMetrics={METRICS}
        pageMetric="nrs" metricLabel="NRS (0–10)" onOpenInClosedLoop={() => {}} />
    </>
  );
}

const gridBodies = () => SessionController.query.mock.calls
  .filter(([url, body]) => url === "/api/queryBiomarkerAnalysis" && body && body.BandTimeSweep === "1")
  .map(([, body]) => body);

beforeEach(() => {
  invalidateAll("home record match test");
  window.localStorage.clear();
  SessionController.query.mockReset();
  SessionController.query.mockImplementation((url, body) => {
    if (url === "/api/queryBiomarkerAnalysis" && body && body.BandTimeSweep === "1") {
      return Promise.resolve({ data: body.ChronicMatch === "window" ? GRID_WINDOW : GRID });
    }
    return Promise.resolve({ data: { boot_token: "boot-1" } });
  });
});

describe("the two choices and the default", () => {
  it("are the PI's words, the covering average the recommended default", () => {
    expect(CHRONIC_MATCH_OPTIONS).toEqual([
      { value: "covering", label: "10-minute average covering the report (recommended)" },
      { value: "window", label: "Page matching window" },
    ]);
    expect(MATCHING_DEFAULTS.chronicMatch).toBe("covering");
  });

  it("the default sends nothing, the window sends ChronicMatch: window", () => {
    expect(chronicMatchParam("covering")).toEqual({});
    expect(chronicMatchParam(undefined)).toEqual({});
    expect(chronicMatchParam("window")).toEqual({ ChronicMatch: "window" });
  });

  it("the default is the server's own (chronic_band_choice.CHRONIC_MATCH_DEFAULT)", () => {
    const src = fs.readFileSync(path.join(__dirname, "..", "..", "..", "..", "..", "BRAVO", "modules",
      "Biomarkers", "routines", "chronic_band_choice.py"), "utf8");
    expect(src).toMatch(/^CHRONIC_MATCH_DEFAULT = CHRONIC_MATCH_COVERING$/m);
    expect(src).toMatch(/^CHRONIC_MATCH_COVERING = "covering"$/m);
    expect(src).toMatch(/^CHRONIC_MATCH_WINDOW = "window"$/m);
  });

  it("index.js spreads the control into the heat maps' request and saves it with the controls", () => {
    const page = fs.readFileSync(path.join(__dirname, "index.js"), "utf8");
    expect(page).toMatch(/\.\.\.chronicMatchParam\(chronicMatch\),\n {2}\}\), \[/);
    expect(page).toMatch(/useState\(P\.chronicMatch \|\| D\.chronicMatch\)/);
    expect(page).toMatch(/<HomeRecordMatchControl value=\{chronicMatch\} onChange=\{setChronicMatch\} \/>/);
  });
});

describe("choosing the page matching window", () => {
  it("changes the request body's ChronicMatch and the cache key; the default sent none", async () => {
    rtlRender(wrap(<Harness />));
    // the first (default) request: no ChronicMatch at all
    await waitFor(() => expect(gridBodies().length).toBe(1));
    expect(gridBodies()[0]).not.toHaveProperty("ChronicMatch");
    await waitFor(() => expect(document.querySelector('[data-testid="band-choice-table"]')).toBeTruthy());
    const defaultKey = settingsKey(gridSettingsFor(BASE, "nrs"));
    expect(getResult(biomarkerHeatmapSlot("nrs"), UID, defaultKey)).toBeTruthy();
    expect(getResult(biomarkerHeatmapSlot("nrs"), UID, defaultKey).stale).toBe(false);
    expect(document.querySelector('[data-testid="chronic-match-warning"]')).toBeNull();

    // choose "Page matching window" in the real select
    const sel = document.querySelector('[data-testid="home-record-match"] .MuiSelect-select');
    fireEvent.mouseDown(sel);
    const option = Array.from(document.querySelectorAll('li[role="option"]'))
      .find((li) => li.textContent === "Page matching window");
    expect(option).toBeTruthy();
    fireEvent.click(option);
    await waitFor(() => expect(document.querySelector('[data-testid="home-record-match"]').textContent)
      .toMatch(/Not the recommended default/));

    // the key differs: the grid held is stale for the new key, and says which setting moved
    const windowKey = settingsKey(gridSettingsFor({ ...BASE, ChronicMatch: "window" }, "nrs"));
    expect(windowKey).not.toBe(defaultKey);
    expect(JSON.parse(windowKey).ChronicMatch).toBe("window");
    expect(JSON.parse(defaultKey).ChronicMatch).toBeUndefined();
    expect(getResult(biomarkerHeatmapSlot("nrs"), UID, windowKey).stale).toBe(true);
    expect(settingsChangedWords(JSON.parse(defaultKey), JSON.parse(windowKey))).toEqual(["the home record match"]);
    await waitFor(() => expect(document.querySelector('[data-testid="heatmaps-out-of-date"]')).toBeTruthy());
    expect(document.querySelector('[data-testid="heatmaps-out-of-date"]').textContent)
      .toMatch(/computed before the home record match was changed/);
  });

  it("a rebuild under the window sends ChronicMatch: window and files the window grid under its own key", async () => {
    // what Recompute does: the stale entry is dropped and the hook fetches for the new settings
    rtlRender(wrap(
      <BiomarkerHeatmapGrids participantUid={UID} requestParams={{ ...BASE, ChronicMatch: "window" }}
        availableMetrics={METRICS} pageMetric="nrs" metricLabel="NRS (0–10)" onOpenInClosedLoop={() => {}} />));
    await waitFor(() => expect(gridBodies().length).toBeGreaterThanOrEqual(1));
    expect(gridBodies()[0].ChronicMatch).toBe("window");
    const windowKey = settingsKey(gridSettingsFor({ ...BASE, ChronicMatch: "window" }, "nrs"));
    await waitFor(() => expect(getResult(biomarkerHeatmapSlot("nrs"), UID, windowKey).stale).toBe(false));
    expect(getResult(biomarkerHeatmapSlot("nrs"), UID, windowKey).bundle.settings_applied.chronic_match).toBe("window");
    await waitFor(() => expect(document.querySelectorAll('[data-testid="chronic-match-warning"]').length).toBe(2));
    // every grid request this page sent under the window carried it
    expect(gridBodies().every((b) => b.ChronicMatch === "window")).toBe(true);
  });
});
