/**
 * The Biomarkers page's layout after the design review of 2026-09-26 (decision 304; the PI: "yes to
 * all six, build them"). The whole page is rendered with the two saved RCS08 responses this folder
 * keeps (the heat-map grid of 2026-09-15 and the calibration in effect of 2026-09-20); the acquisition
 * timeline, the pain reports and the sample index are not answered, so the top card renders its own
 * empty states. Plotly and the page frame are replaced (jsdom cannot draw; the frame is the app's).
 *
 * What is pinned, each watched failing on the page as it was:
 *   1. the pain-score selector comes first, above everything it drives, and is called "pain score";
 *   2. no box inside a box: no card, and no box with a border on all four sides, sits inside another
 *      (controls -- buttons, inputs, the pair thumbnails -- are not boxes);
 *   3. the build action has one name, Recompute;
 *   4. the developer lines (when the stored results were built, the browser's memory use) sit in one
 *      fold, and the "computed on N samples" line and the recorded-channel list are not on view;
 *   5. the calibration section says "composed" once on load and "not measured" once in all;
 *   6. the 2026-09-21 search lines are in their own fold, not in "How to read this";
 *   7. the pairs the device refuses with today's contacts carry a red bullet and a cross, when the
 *      response says which pairs the device allows (and nothing is marked when it does not);
 *   8. "TD" says which TD: up to 30 s around the rating on the matching card, 3 s pieces on the grid.
 */
import "@testing-library/jest-dom";
import fs from "fs";
import path from "path";
import { render as rtlRender, screen, waitFor, act, fireEvent, within } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import theme from "assets/theme";
import { PlatformContextProvider } from "context";
import { invalidateAll, putResult, settingsKey } from "database/resultCache";
import { biomarkerHeatmapSlot, CL } from "views/Reports/moduleCacheKeys";

import sweep from "./__fixtures__/rcs08_band_sweep.json";
import calib from "./__fixtures__/rcs08_calibration_in_effect.json";

jest.mock("plotly.js-dist", () => {
  const noop = () => {};
  const react = (id) => {
    const el = typeof id === "string" ? global.document.getElementById(id) : id;
    if (el) { el.on = noop; el.removeAllListeners = noop; el.removeListener = noop; el.data = []; }
    return Promise.resolve();
  };
  return { react, purge: noop, restyle: noop, relayout: noop, newPlot: noop, Plots: { resize: noop } };
});
jest.mock("graphing-utility/Plotly", () => ({
  PlotlyRenderManager: class {
    constructor() { this.traces = []; this.layout = {}; }
    subplots() {} clearData() {} render() {} setLayoutProps() {} setXlabel() {} setYlabel() {} purge() {}
  },
}));
jest.mock("layouts/DatabaseLayout", () => ({ children }) => <div data-testid="page">{children}</div>);
jest.mock("database/session-control", () => ({
  SessionController: { query: jest.fn(), displayError: jest.fn(), setSession: () => {}, getSession: () => null },
}));
// eslint-disable-next-line import/first
import { SessionController } from "database/session-control";
// eslint-disable-next-line import/first
import Biomarkers from "./index";

const UID = "2e3c75c00d7f4f37b53a048d195f11da";
const REQ = {
  source: "both", LabelMetric: "nrs", LabelStrategy: "tertile", PercentileLow: 33.3, PercentileHigh: 66.7,
  MatchToleranceMin: 60, MaxPerRating: 3, RefractoryMin: 2, MatchDirection: "pro_first",
  MatchExtentSec: 30, AllowWindowReuse: false, IncludeClinicSheetRatings: false, SlidingWindow: false,
};

// The device's sensing rule for RCS08 with the contacts in force since 2026-09-03 (decisions 217
// and 247: the left lead stimulates on contact 2, the right on 1 and 2), in the shape the Stim
// Optimizer's response already carries it (`closed_loop.sensing_rule`, decision 243). The heat-map
// grid's response does not carry it yet; the page marks refused pairs only once it does.
const SENSING_RULE = {
  decision: 217,
  sentence: "While today's contacts are stimulating, the device allows one sensing pair per lead: L 1⁻3⁺ and R 0⁻3⁺.",
  by_side: {
    Left: { stim_rings: [2], rule_applied: true, allowed_pair: [1, 3], allowed_channel: "ONE_THREE_LEFT",
      allowed_display: "L 1⁻3⁺", why: "stimulating on contact(s) 2, the device senses only on the two contacts flanking them" },
    Right: { stim_rings: [1, 2], rule_applied: true, allowed_pair: [0, 3], allowed_channel: "ZERO_THREE_RIGHT",
      allowed_display: "R 0⁻3⁺", why: "stimulating on contact(s) 1, 2, the device senses only on the two contacts flanking them" },
  },
};

const read = (f) => fs.readFileSync(path.join(__dirname, f), "utf8");
function stripComments(src) {
  return src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:"'\\])\/\/[^\n]*/g, "$1");
}
function printable(src) {
  const code = stripComments(src);
  const lits = code.match(/"(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*'|`(?:[^`\\]|\\.)*`/g) || [];
  const jsx = (code.match(/>([^<>{}]*[A-Za-z][^<>{}]*)</g) || []).map((s) => s.slice(1, -1));
  return lits.concat(jsx);
}
/** What a reader sees: everything outside a closed fold. */
function visibleText(node) {
  const c = node.cloneNode(true);
  c.querySelectorAll(".MuiCollapse-hidden").forEach((n) => n.remove());
  return c.textContent;
}
const countOf = (text, re) => (text.match(new RegExp(re.source, `${re.flags.replace("g", "")}g`)) || []).length;
const wordCount = (s) => String(s).trim().split(/\s+/).filter(Boolean).length;

async function renderPage(grid = sweep) {
  invalidateAll("layout test");
  window.localStorage.clear();
  SessionController.query.mockReset();
  SessionController.query.mockImplementation(() => Promise.resolve({ data: { boot_token: "boot-1" } }));
  putResult(biomarkerHeatmapSlot("nrs"), UID, settingsKey({ ...REQ, SweepMetric: "nrs" }), grid, { why: "layout test" });
  putResult(CL.conversionModel, UID, settingsKey({}), calib, { why: "layout test" });
  let utils;
  await act(async () => {
    utils = rtlRender(
      <ThemeProvider theme={theme}>
        <PlatformContextProvider initialStates={{ darkMode: false }}>
          <MemoryRouter initialEntries={[`/reports/biomarkers/${UID}`]}>
            <Routes><Route path="/reports/biomarkers/:participant_uid" element={<Biomarkers />} /></Routes>
          </MemoryRouter>
        </PlatformContextProvider>
      </ThemeProvider>);
  });
  await waitFor(() => expect(screen.getAllByText(/How to read this/).length).toBeGreaterThan(0));
  await waitFor(() => expect(screen.getAllByText(/345\.59/).length).toBeGreaterThan(0));
  return utils;
}

/** A box: a card, or anything with a solid border on all four sides that is not a control. */
function isBox(el) {
  if (el.classList.contains("MuiCard-root")) return true;
  if (el.closest("button, fieldset, label, input, [role='button'], .MuiInputBase-root, .MuiToggleButtonGroup-root")) return false;
  const cs = getComputedStyle(el);
  return ["Top", "Right", "Bottom", "Left"].every((s) => cs[`border${s}Style`] === "solid"
    && parseFloat(cs[`border${s}Width`]) >= 1);
}
function boxDepths(root) {
  const out = [];
  root.querySelectorAll("*").forEach((el) => {
    if (!isBox(el)) return;
    let d = 1;
    for (let p = el.parentElement; p && p !== root; p = p.parentElement) if (isBox(p)) d += 1;
    out.push({ d, text: (el.textContent || "").slice(0, 50) });
  });
  return out;
}

describe("1. the pain-score selector comes first", () => {
  test("in the page source it is placed above the timeline, the matching card and the heat maps", () => {
    const src = read("index.js");
    const at = (s) => { const i = src.indexOf(s); expect(i).toBeGreaterThan(-1); return i; };
    const selector = at("setMetric(e.target.value)");
    ["<BiomarkerDataTimeline", "<MatchWindowBand", "<BinarizationPreview", "<BiomarkerHeatmapGrids"]
      .forEach((later) => expect(selector).toBeLessThan(at(later)));
  });

  test("it is called the pain score, as the heat maps and the Closed-Loop page call it", () => {
    const text = printable(read("index.js")).join(" ");
    expect(text).toMatch(/Pain score/);
    expect(text).not.toMatch(/Pain metric/);
  });

  test("rendered, the selector is the first control on the page", async () => {
    const { container } = await renderPage();
    const select = container.querySelector("[data-testid='pain-score-select']");
    expect(select).not.toBeNull();
    const first = container.querySelector(".MuiSelect-select, input, [role='slider'], .MuiToggleButton-root");
    expect(select.contains(first)).toBe(true);
  });
});

describe("2. no box inside a box", () => {
  test("no card or bordered box sits inside another", async () => {
    const { container } = await renderPage();
    const deep = boxDepths(container).filter((b) => b.d > 1);
    expect(deep).toEqual([]);
  });
});

describe("3. one name for the build action", () => {
  test("the page's own text says Recompute, never Compute, for the button", () => {
    const text = printable(read("index.js")).join(" | ");
    expect(text).not.toMatch(/\bCompute\b/);
    expect(text).not.toMatch(/press Compute|Compute biomarker/);
    // decision 298's pin stays: the prompt names the all-band scan
    expect(read("index.js")).toContain("<strong>Recompute</strong>{\" above to run the all-band scan.\"}");
  });
});

describe("4. developer lines are folded", () => {
  test("the stored-results line and the memory lines sit in one fold; no sample-count line", () => {
    const src = stripComments(read("index.js"));
    const fold = src.indexOf("data-testid=\"developer-details\"");
    expect(fold).toBeGreaterThan(-1);
    const end = src.indexOf("</Fold>", fold);
    const inside = (s) => { const i = src.indexOf(s); return i > fold && i < end; };
    expect(inside("<CacheStatusLine")).toBe(true);
    expect(inside("memoryInfo()")).toBe(true);
    expect(src).not.toMatch(/full-resolution samples/);
  });

  test("the recorded-channel list is not on view (the timeline's own lanes say it)", () => {
    const src = stripComments(read("index.js"));
    const i = src.indexOf("Recorded power channels");
    if (i < 0) return;
    const fold = src.lastIndexOf("<Fold", i);
    expect(fold).toBeGreaterThan(-1);
    expect(src.lastIndexOf("</Fold>", i)).toBeLessThan(fold);
    expect(src).not.toMatch(/\u26a0/);
  });
});

describe("5. the calibration section says composed once", () => {
  test("the page adds no calibration prose of its own around the panel", () => {
    const text = printable(read("index.js")).join(" ");
    expect(text).not.toMatch(/composed|not measured|least-significant-bit/i);
  });

  test("rendered: the two constants on view, 'composed' once on load, 'not measured' once in all", async () => {
    const { container } = await renderPage();
    const section = container.querySelector("[data-testid='calibration-section']");
    expect(section).not.toBeNull();
    const vis = visibleText(section);
    expect(vis).toMatch(/1 µV² = 345\.59 LSB/);
    expect(vis).toMatch(/1 device-µV² = 72\.16 LSB/);
    expect(countOf(vis, /composed/i)).toBe(1);
    expect(countOf(section.textContent, /not measured/i)).toBe(1);
    // the fitting detail is still there, one click away
    expect(section.textContent).toMatch(/at least 3 s of signal and 6 device readings/);
    expect(vis).not.toMatch(/at least 3 s of signal and 6 device readings/);
  });
});

describe("6. the 2026-09-21 search lines have their own fold", () => {
  test("closed on load, seven lines inside, none of them in 'How to read this'", async () => {
    const { container } = await renderPage();
    const lines = Array.from(container.querySelectorAll("[data-testid='l13-search-line']"));
    expect(lines).toHaveLength(7);
    const fold = container.querySelector("[data-testid='l13-search-fold']");
    expect(fold).not.toBeNull();
    lines.forEach((l) => expect(fold.contains(l)).toBe(true));
    expect(visibleText(container)).not.toMatch(/Exploratory search, 2026-09-21/);
    const drawer = container.querySelector("[data-testid='reading-notes']");
    expect(drawer).not.toBeNull();
    expect(drawer.textContent).not.toMatch(/Exploratory search|252 settings/);
  });
});

describe("7. the pairs the device refuses with today's contacts", () => {
  test("with the rule on the response: one red bullet, five words or fewer, and a cross on each refused pair", async () => {
    const { container } = await renderPage({ ...sweep, sensing_rule: SENSING_RULE });
    const status = container.querySelector("[data-testid='grid-status']");
    expect(status).not.toBeNull();
    const red = Array.from(status.querySelectorAll("[data-testid='red-bullet']")).map((b) => b.textContent.trim());
    expect(red).toEqual(["4 of 6 pairs refused"]);
    red.forEach((b) => expect(wordCount(b)).toBeLessThanOrEqual(5));
    expect(status.textContent).toMatch(/Allowed pairs today: L 1⁻3⁺, R 0⁻3⁺/);
    const refused = Array.from(container.querySelectorAll("[data-testid='pair-thumb']"))
      .filter((t) => within(t).queryByText(/Refused today/));
    expect(refused.map((t) => t.getAttribute("data-channel")).sort())
      .toEqual(["ONE_THREE_RIGHT", "ZERO_THREE_LEFT", "ZERO_TWO_LEFT", "ZERO_TWO_RIGHT"]);
    refused.forEach((t) => expect(t.querySelector("svg[role='img']")).not.toBeNull());
    // the why is one click away, not on view
    expect(visibleText(status)).not.toMatch(/flanking/);
    expect(status.textContent).toMatch(/flanking/);
  });

  test("without it the page marks nothing and says nothing about allowed pairs (no rule invented here)", async () => {
    const { container } = await renderPage();
    expect(container.querySelectorAll("[data-testid='red-bullet']")).toHaveLength(0);
    expect(container.textContent).not.toMatch(/Refused today|Allowed pairs today/);
  });

  test("the status line says, from the grid, how many bands clear the 22-band correction and which way", async () => {
    const { container } = await renderPage();
    const status = container.querySelector("[data-testid='grid-status']");
    expect(status.textContent).toMatch(/NRS/);
    expect(status.textContent).toMatch(/60-min window/);
    // RCS08, NRS, 2026-09-15: no band rises with pain past the correction; 30 fall with it
    expect(status.textContent).toMatch(/0 bands rise with pain and 30 fall with it/);
  });
});

describe("8. TD says which TD", () => {
  test("the matching card: up to 30 s around the rating, no method name", () => {
    const text = printable(read("BinarizationPreview.js")).join(" ");
    expect(text).toMatch(/TD \(up to 30 s around the rating\)/);
    expect(text).not.toMatch(/Welch/);
  });
  test("the heat maps: 3 s pieces", () => {
    expect(printable(read("BiomarkerHeatmapGrids.js")).join(" ")).toMatch(/TD\) recording, in 3 s pieces/);
  });
});
