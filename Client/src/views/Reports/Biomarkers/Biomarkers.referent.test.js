/**
 * Referent audit, 2026-09-15 (`.planning/2026-09-15-rendered-text-referent-audit-three-pages/
 * findings.md` §3), the Biomarkers page. The calibrated heat-map card is rendered against the REAL
 * band-by-length sweep response for RCS08 captured that evening (`__fixtures__/rcs08_band_sweep.json`);
 * the two source-text checks read the component files themselves, because a render of the whole
 * page pulls in every panel and its network calls and would prove nothing this file is for.
 *
 * THE DEFECT CLASS. (a) One fact printed twice inside one card by two code paths that can drift:
 * the backend appends the device-snapshot count to the sweep's `notes`, which the "how to read this"
 * drawer prints, while the orange caption above the grid prints the same count from
 * `gridReadouts.deviceSpectrumBullets`. (b) Display code for things no page has drawn since the
 * decisions that retired them (the "Matched samples per channel" block reads a field the backend
 * stopped computing at decision 77; `chPanels` builds six panels the component never returns).
 *
 * Item 3 is RED against today's fixture and goes green only after the BACKEND stops appending that
 * note and the verifier re-captures the fixture -- never by editing the fixture by hand. Items 7 and
 * 8 are RED until the frontend deletes the dead blocks.
 *
 * Plotly and the project's render manager are replaced: the heat maps draw through the imperative
 * `Plotly.react` interface against a real graph node, which jsdom cannot provide, and the drawing is
 * not what is under test (the same reason `ClosedLoopSim/cachedPanels.smoke.test.js` gives).
 */
import "@testing-library/jest-dom";
import fs from "fs";
import path from "path";
import { render as rtlRender, screen, fireEvent, waitFor } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";

import theme from "assets/theme";
import { PlatformContextProvider } from "context";

import { invalidateAll, putResult, settingsKey } from "database/resultCache";
import { biomarkerHeatmapSlot } from "views/Reports/moduleCacheKeys";

import BiomarkerHeatmapGrids from "./BiomarkerHeatmapGrids";
import { deviceSpectrumBullets } from "./gridReadouts";
import sweep from "./__fixtures__/rcs08_band_sweep.json";

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
    subplots() {} clearData() {} render() {} setLayoutProps() {} setXlabel() {} setYlabel() {}
  },
}));
jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn() } }));
// eslint-disable-next-line import/first
import { SessionController } from "database/session-control";

const wrap = (ui) => (
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>
);

const UID = "2e3c75c00d7f4f37b53a048d195f11da";
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

async function renderGrid() {
  const utils = rtlRender(wrap(
    <BiomarkerHeatmapGrids participantUid={UID} requestParams={REQ} availableMetrics={METRICS}
      pageMetric={METRIC} metricLabel="NRS (0–10)" onOpenInClosedLoop={() => {}} />,
  ));
  // The first channel of the response (R 0⁻3⁺, the contact with 358 snapshot-served reports) is
  // the one the drawer opens on.
  await waitFor(() => expect(screen.getByText(/How to read this/)).toBeInTheDocument());
  return utils;
}

describe("the fixture is the state these assertions were written against", () => {
  it("has nine lengths, a snapshot-served count as a field, and no snapshot sentence in the notes", () => {
    const sw = sweep.band_time_sweep.ZERO_THREE_RIGHT;
    expect(sw.integration_seconds_delivered).toHaveLength(9);
    expect(sw.n_pain_reports_from_device_spectrum).toBe(358);
    // Item 3. Before the backend fix of 2026-09-15 (rule version v17) the fixture carried the
    // snapshot sentence in `notes` as well as the count in the field, and this line read `true`;
    // the re-captured fixture carries the count only, so the drawer cannot print it a second time.
    expect(sw.notes.some((n) => /FFT snapshots/.test(n))).toBe(false);
  });
});

describe("the calibrated heat-map card (BiomarkerHeatmapGrids)", () => {
  // Item 3, DUP-1 / BND-3. The orange caption prints "358 of N matched reports (79%) ... FFT
  // snapshots" from `deviceSpectrumBullets`; the drawer prints the backend's own copy of the same
  // count from `notes[8]`. One fact, two code paths, one card. After the backend stops appending
  // the note, the caption is the only place the count lives.
  it("item 3: no drawer bullet says the reports were answered from FFT snapshots", async () => {
    const { container } = await renderGrid();
    fireEvent.click(screen.getByText(/^How to read this$/));
    const bullets = Array.from(container.querySelectorAll("*"))
      .filter((el) => el.children.length === 0 && /^• /.test(el.textContent || ""))
      .map((el) => el.textContent);
    expect(bullets.length).toBeGreaterThan(0);
    expect(bullets.filter((b) => /answered from|FFT snapshots/.test(b))).toEqual([]);
  });

  it("item 3, the other half: the orange caption still prints the snapshot count, exactly once on the card", async () => {
    const { container } = await renderGrid();
    fireEvent.click(screen.getByText(/^How to read this$/));
    const expected = deviceSpectrumBullets(sweep.band_time_sweep.ZERO_THREE_RIGHT);
    expect(expected[0]).toMatch(/^358 of \d+ matched reports \(\d+%\)/);
    const items = Array.from(container.querySelectorAll("li")).map((el) => el.textContent);
    expect(items).toContain(expected[0]);
    // The fact survives, and survives ONCE: RED today (3) because the drawer's bullet names the
    // snapshots twice more on its own.
    expect(countOf(container.textContent, "FFT snapshots")).toBe(1);
  });

  it("the drawer's first note speaks of the circled cell and nine lengths (decision 172), a pin", async () => {
    const { container } = await renderGrid();
    fireEvent.click(screen.getByText(/^How to read this$/));
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
