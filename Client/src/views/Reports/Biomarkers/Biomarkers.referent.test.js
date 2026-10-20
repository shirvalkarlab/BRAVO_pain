// Uses independently authored synthetic response fixtures; no participant-validation claim.
/** Authored synthetic grid tests: display/cache behavior, never participant evidence. */
import "@testing-library/jest-dom";
import fs from "fs";
import path from "path";
import { render as rtlRender, screen, fireEvent, waitFor } from "@testing-library/react";

import { invalidateAll, putResult, settingsKey } from "database/resultCache";
import { biomarkerHeatmapSlot } from "views/Reports/moduleCacheKeys";

import BiomarkerHeatmapGrids from "./BiomarkerHeatmapGrids";
import { deviceSpectrumBullets } from "./gridReadouts";
import sweep from "./__fixtures__/synthetic_band_sweep.json";
import { wrap } from "testUtils/render";

jest.mock("plotly.js-dist", () => {
  // The real `Plotly.react` turns the target <div> into a graph node with `.on`,
  // `.removeAllListeners` and `.data`; the grid's hover/click effect reads those, so the stand-in
  // attaches inert versions. Nothing is drawn. A plain function rather than `jest.fn(impl)`,
  // because react-scripts runs jest with `resetMocks: true`, which strips the implementation off
  // every jest.fn before each test and would leave the node without `.on` again.
  const noop = () => {};
  const react = (id) => {
    // `global.document` rather than `document`: a jest.mock factory may not close over a
    // bare out-of-scope name, but `global` is on its allow-list.
    const el = typeof id === "string" ? global.document.getElementById(id) : id;
    if (el) { el.on = noop; el.removeAllListeners = noop; el.data = []; }
    return Promise.resolve();
  };
  return { react, purge: noop, restyle: noop, relayout: noop, newPlot: noop };
});
jest.mock("graphing-utility/Plotly", () => ({
  // Every method the grid calls on its figure is a no-op; `traces`/`layout` are the two fields
  // it reads back before handing them to the (mocked) Plotly.react.
  PlotlyRenderManager: class {
    constructor() { this.traces = []; this.layout = {}; }
    subplots() {} clearData() {} render() {} setLayoutProps() {} setXlabel() {} setYlabel() {} purge() {}
  },
}));
jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn() } }));
// eslint-disable-next-line import/first
import { SessionController } from "database/session-control";

const UID = "synthetic-biomarker-subject";
const METRIC = "nrs";
const REQ = { MatchToleranceMin: 60, MatchDirection: "pro_first", LabelStrategy: "tertile" };
const METRICS = [{ key: "nrs", label: "NRS (0–10)" }];

/** How many times a phrase occurs in a block of text, case-insensitively. */
function countOf(text, phrase) {
  const re = new RegExp(phrase.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi");
  return (text.match(re) || []).length;
}

beforeEach(() => {
  invalidateAll("referent test setup");
  SessionController.query.mockReset();
  // The hook's server-identity call and any prefetch of another score answer inertly; the grid
  // itself is read from the cache, seeded below, exactly as a return to the page reads it.
  SessionController.query.mockImplementation(() => Promise.resolve({ data: { boot_token: "boot-1" } }));
  putResult(biomarkerHeatmapSlot(METRIC), UID, settingsKey({ ...REQ, SweepMetric: METRIC }), sweep,
    { why: "referent test" });
});

async function renderGrid({ participantUid = UID } = {}) {
  if (participantUid !== UID) {
    putResult(biomarkerHeatmapSlot(METRIC), participantUid, settingsKey({ ...REQ, SweepMetric: METRIC }), sweep,
      { why: "referent test, another participant" });
  }
  const utils = rtlRender(wrap(
    <BiomarkerHeatmapGrids participantUid={participantUid} requestParams={REQ} availableMetrics={METRICS}
      pageMetric={METRIC} metricLabel="NRS (0–10)" onOpenInClosedLoop={() => {}} />,
  ));
  // The first channel of the response (R 0⁻3⁺, the channel with three synthetic PSD-served reports) is
  // the one the drawer opens on.
  await waitFor(() => expect(screen.getByText(/Reading guide/)).toBeInTheDocument());
  return utils;
}

describe("the fixture is the state these assertions were written against", () => {
  it("has nine lengths, a snapshot-served count as a field, and no snapshot sentence in the notes", () => {
    const sw = sweep.band_time_sweep.ZERO_THREE_RIGHT;
    expect(sw.integration_seconds_delivered).toHaveLength(9);
    expect(sw.n_pain_reports_from_device_spectrum).toBe(3);
    // Item 3. Before the backend fix of 2026-09-15 (rule version v17) the fixture carried the
    // snapshot sentence in `notes` as well as the count in the field, and this line read `true`;
    // the synthetic fixture carries the count only, so the drawer cannot print it a second time.
    expect(sw.notes.some((n) => /FFT snapshots/.test(n))).toBe(false);
  });
});

describe("the calibrated heat-map card (BiomarkerHeatmapGrids)", () => {
  // Item 3, DUP-1 / BND-3. The orange caption prints "3 of 12 matched reports (25%) ... FFT
  // snapshots" from `deviceSpectrumBullets`; the drawer prints the backend's own copy of the same
  // count from `notes[8]`. One fact, two code paths, one card. After the backend stops appending
  // the note, the caption is the only place the count lives.
  it("item 3: no drawer bullet says the reports were answered from FFT snapshots", async () => {
    const { container } = await renderGrid();
    fireEvent.click(screen.getByText(/^Reading guide$/));
    const bullets = Array.from(container.querySelectorAll("*"))
      .filter((el) => el.children.length === 0 && /^• /.test(el.textContent || ""))
      .map((el) => el.textContent);
    expect(bullets.length).toBeGreaterThan(0);
    expect(bullets.filter((b) => /answered from|FFT snapshots/.test(b))).toEqual([]);
  });

  it("does not render private historical research summaries for synthetic participants", async () => {
    const {container}=await renderGrid();
    expect(container.querySelector('[data-testid="l13-search-fold"]')).toBeNull();
    expect(container.querySelectorAll('[data-testid="l13-search-line"]')).toHaveLength(0);
  });

  it("item 3, the other half: the orange caption still prints the snapshot count, exactly once on the card", async () => {
    const { container } = await renderGrid();
    fireEvent.click(screen.getByText(/^Reading guide$/));
    const expected = deviceSpectrumBullets(sweep.band_time_sweep.ZERO_THREE_RIGHT);
    expect(expected[0]).toMatch(/^3 of 12 matched reports \(25%\)/);
    const items = Array.from(container.querySelectorAll("li")).map((el) => el.textContent);
    expect(items).toContain(expected[0]);
    // The fact survives, and survives ONCE: RED today (3) because the drawer's bullet names the
    // snapshots twice more on its own. Counted on the caption's own words since the heat maps took
    // the PI's vocabulary (2026-09-25: TD and PSD), which renamed "FFT snapshots" to "PSD". The
    // caption lost its bracketed "(N s row = ...)" tail on 2026-10-02, so the count is on the text
    // that stays.
    expect(countOf(container.textContent, "read from PSD")).toBe(1);
  });

  it("the drawer's first note speaks of the circled cell and nine lengths (decision 172), a pin", async () => {
    const { container } = await renderGrid();
    fireEvent.click(screen.getByText(/^Reading guide$/));
    const text = container.textContent;
    expect(text).toMatch(/circled cell in each column/);
    expect(text).not.toMatch(/ten lengths/i);
    expect(text).not.toMatch(/best-of-ten/i);
  });
});

const SRC = (f) => fs.readFileSync(path.join(__dirname, f), "utf8");

describe("Biomarkers/index.js source text", () => {
  // Item 7, INV-1. The "Matched samples per channel" block reads
  // `data.analytics.timedomain.spectral_feature_importance`, which the backend has not computed
  // since decision 77 (0 hits in bravo_service.py). Never drawn; the source must not carry it.
  it("item 7: no 'Matched samples per channel' block", () => {
    const src = SRC("index.js");
    expect(src).not.toContain("Matched samples per channel");
    expect(src).not.toContain("spectral_feature_importance");
  });
});

describe("Biomarkers/BiomarkerAnalytics.js source text", () => {
  // Item 8, INV-2. `chPanels` builds six panels with real titles and the component returns only
  // `tdPanels`. Six panels' display code that nothing renders (decisions 66, 77, 80 retired the
  // display it served).
  it("item 8: no `chPanels` builder", () => {
    expect(SRC("BiomarkerAnalytics.js")).not.toMatch(/\bchPanels\b/);
  });
});

describe("the committed band on this page (decision 80 deleted the commit button)", () => {
  // Decision 174 found two comments in `index.js` (lines 40 and 202 that day) describing "the commit
  // button inside BiomarkerAnalytics" as the writer of the committed band. That button went with the
  // `ValidationReadout` cluster in decision 80; a band is committed on the Closed-Loop Deployment
  // page's "Choose a band" card (decision 122) and read here from localStorage. `BiomarkerAnalytics`
  // reads two props (`analytics`, `metricLabel`); the `onBandCommitted` handler this page passed it
  // was reached by nothing. The PI asked for the comments fixed on 2026-09-15.
  const read = (f) => fs.readFileSync(path.join(__dirname, f), "utf8");

  it("index.js no longer says a commit button inside BiomarkerAnalytics writes the band", () => {
    const idx = read("index.js");
    expect(idx).not.toMatch(/commit button (inside|in) BiomarkerAnalytics/);
    expect(idx).toMatch(/Choose a band/);
  });

  it("index.js no longer passes BiomarkerAnalytics a commit handler nothing reads", () => {
    expect(read("index.js")).not.toMatch(/onBandCommitted/);
    expect(read("BiomarkerAnalytics.js")).not.toMatch(/onBandCommitted|commitBandCandidate/);
  });
});
