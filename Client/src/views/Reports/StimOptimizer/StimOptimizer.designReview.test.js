/**
 * The design review of 2026-09-26 (`artifacts/design_review_2026-09-26_stim_optimizer_and_biomarkers.md`,
 * §1), built on the PI's "yes to all six, build them" of the same day. The Closed-Loop page's
 * pattern, applied here:
 *
 *  1. ONE status line above the readiness card, with red bullets (the device refuses or a check
 *     blocks) and yellow bullets (evidence not evaluated), each five words or fewer and each with a
 *     glyph as well as a colour; the detail behind them folded.
 *  2. Folded by default: the definition of "proven better", the exposure line and the stopping rule
 *     (243(b), 243(d), 245(b)); the stored-results line beside the recompute bar; the readiness rows
 *     on pairs the device does not allow today; the clinic-sheet table; the home schedule, now inside
 *     the next-visit card; the two charts on the closed-loop checks; each current-map square's
 *     closing sentence; the control analyses.
 *  3. Nothing said twice in the open: "no current can be recommended", "closed loop cannot start",
 *     the ceiling, the pointer-only sentences, the per-side stopping rule, a line per unfitted rate.
 *  4. One set of words: stretches (never epochs), proven better (never resolved), closed loop (never
 *     adaptive mode), minimum (never floor), the power gap in units of its scatter (never
 *     "Separation (SD)"), no decision numbers.
 *
 * Rendered whole against two saved RCS08 responses: the one the page's other tests use
 * (2026-09-15) and the one served on 2026-09-25, which carries the fields added since (the sensing
 * rule, the block-of-time check, the next session's coverage, the stopping rule).
 */
import "@testing-library/jest-dom";
import fs from "fs";
import path from "path";
import { render as rtlRender } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";

import theme from "assets/theme";
import { PlatformContextProvider } from "context";

import oldResponse from "./__fixtures__/rcs08_stim_optimizer_two_stage.json";
import newResponse from "./__fixtures__/rcs08_stim_optimizer_2026-09-25.json";
import { statusSummary, STATUS_GLYPH } from "./StatusLine";
import { CURRENT_MAP_COLORSCALE } from "./CurrentMapCard";

jest.mock("react-router-dom", () => ({
  ...jest.requireActual("react-router-dom"),
  useParams: () => ({ participant_uid: "2e3c75c00d7f4f37b53a048d195f11da" }),
}));
jest.mock("layouts/DatabaseLayout", () => ({ children }) => <div>{children}</div>);
jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn(() => new Promise(() => {})) } }));
jest.mock("plotly.js-dist", () => ({
  react: () => Promise.resolve(), purge: () => {}, restyle: () => Promise.resolve(),
  relayout: () => Promise.resolve(), newPlot: () => Promise.resolve(), toImage: () => Promise.resolve(),
}));
jest.mock("graphing-utility/Plotly", () => ({
  PlotlyRenderManager: class {
    constructor() { this.traces = []; this.layout = {}; }
    subplots() {} clearData() {} render() {} setLayoutProps() {} setXlabel() {} setYlabel() {}
    addHeatmap() {} addScatter() {} addShape() {} addAnnotation() {} setTitle() {} purge() {}
  },
}));
jest.mock("views/Reports/RecomputeBar", () => () => <div>recompute bar</div>);
jest.mock("views/Reports/ControlAnalyses/ControlAnalysesCard", () => ({
  ControlAnalysesSection: () => <div data-testid="control-analyses">control analyses</div>,
}));
jest.mock("database/useCachedResult", () => ({
  useCachedResult: () => ({ data: global.__SO_FX__, loading: false, err: null, hasCached: true,
    stale: false, staleReasons: [], computedAt: null, notKept: false }),
}));

// eslint-disable-next-line import/first
import StimOptimizer from "./index";

const wrap = (ui) => (
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>
);

function renderPage(fx) {
  global.__SO_FX__ = fx;
  return rtlRender(wrap(<StimOptimizer />));
}

/** Inside a closed fold: some ancestor is a collapsed MUI Collapse. */
const isFolded = (el) => !!(el && el.closest(".MuiCollapse-hidden"));

/** The text a reader sees on load: every text node not inside a closed fold. */
function visibleText(root) {
  let out = "";
  const walk = (n) => {
    if (n.nodeType === 3) { out += n.textContent; return; }
    if (n.nodeType !== 1) return;
    if (n.classList && n.classList.contains("MuiCollapse-hidden")) return;
    n.childNodes.forEach(walk);
  };
  walk(root);
  return out.replace(/\s+/g, " ");
}
const countOf = (text, re) => (text.match(new RegExp(re.source, `${re.flags.replace("g", "")}g`)) || []).length;
const words = (s) => (String(s).trim().match(/\S+/g) || []).length;

const cardWithTitle = (container, title) => Array.from(container.querySelectorAll(".MuiCard-root"))
  .find((c) => c.textContent.includes(title));

// ---------------------------------------------------------------------------------------------
describe("1. the status line", () => {
  it("states the answer in one line, from the numbers (2026-09-25 response)", () => {
    const s = statusSummary(newResponse, newResponse.two_stage);
    expect(s.headline).toBe("Keep today's setting on both sides; closed loop cannot start.");
  });

  it("lists the device's refusals and the blocking checks in red, the unevaluated evidence in yellow", () => {
    const s = statusSummary(newResponse, newResponse.two_stage);
    const red = s.bullets.filter((b) => b.kind === "red").map((b) => b.text);
    const yellow = s.bullets.filter((b) => b.kind === "yellow").map((b) => b.text);
    expect(red).toEqual(["No usable sensing pair", "Setting not proven better"]);
    expect(yellow).toEqual(expect.arrayContaining([
      "Band response not assessed", "Current limits not proposed", "Pulse width not assessed",
      "Next visit: 4 pairs short", "Pain map moves over time"]));
    // red before yellow
    const kinds = s.bullets.map((b) => b.kind);
    expect(kinds.indexOf("yellow")).toBeGreaterThan(kinds.lastIndexOf("red"));
  });

  it("reads the older response without the fields it predates, and invents no bullet", () => {
    const s = statusSummary(oldResponse, oldResponse.two_stage);
    expect(s.headline).toBe("Keep today's setting on both sides; closed loop cannot start.");
    expect(s.bullets.map((b) => b.text)).toEqual(
      ["Setting not proven better", "Current limits not proposed", "Pulse width not assessed"]);
  });

  it("every bullet is five words or fewer and carries a glyph as well as a colour", () => {
    const { container } = renderPage(newResponse);
    const bullets = container.querySelectorAll('[data-testid="status-bullet"]');
    expect(bullets.length).toBe(7);
    bullets.forEach((b) => {
      const kind = b.getAttribute("data-kind");
      const glyph = b.querySelector('[data-testid="status-glyph"]');
      expect(glyph.textContent).toBe(STATUS_GLYPH[kind]);
      const label = b.querySelector('[data-testid="status-text"]').textContent.replace("†", "");
      expect(words(label)).toBeLessThanOrEqual(5);
      expect(b.getAttribute("aria-label")).toMatch(kind === "red" ? /^blocked: / : /^not evaluated: /);
    });
    expect(STATUS_GLYPH.red).toBe("●");
    expect(STATUS_GLYPH.yellow).toBe("▲");
  });

  it("keeps the decision-294 dagger on its bullet, and its note in the folded detail", () => {
    const { container } = renderPage(newResponse);
    const moves = Array.from(container.querySelectorAll('[data-testid="status-bullet"]'))
      .find((b) => b.textContent.includes("Pain map moves over time"));
    expect(moves.textContent).toContain("†");
    const detail = container.querySelector('[data-testid="status-details"]');
    expect(detail.textContent).toContain("moves between blocks of time");
    expect(isFolded(detail)).toBe(true);
  });

  it("sits above the readiness card and below the recompute bar", () => {
    const { container } = renderPage(newResponse);
    const t = container.textContent;
    const status = t.indexOf("Keep today's setting on both sides");
    expect(status).toBeGreaterThan(t.indexOf("recompute bar"));
    expect(status).toBeLessThan(t.indexOf("contact-and-rate combinations usable for closed loop"));
  });
});

// ---------------------------------------------------------------------------------------------
describe("2. folds closed on load", () => {
  let container;
  beforeEach(() => { ({ container } = renderPage(newResponse)); });
  const byTestId = (id) => container.querySelector(`[data-testid="${id}"]`);

  it("the definition of 'proven better', the exposure line and the stopping rule (243(b), 243(d), 245(b))", () => {
    const def = Array.from(container.querySelectorAll("div")).find((d) => /^Proven better means/.test(d.textContent));
    expect(def).toBeTruthy();
    expect(isFolded(def)).toBe(true);
    expect(isFolded(byTestId("stopping-rule"))).toBe(true);
  });

  it("the stored-results line beside the recompute bar", () => {
    expect(isFolded(byTestId("cache-status-fold-body"))).toBe(true);
  });

  it("the readiness rows on pairs the device does not allow today; the two allowed pairs open", () => {
    const open = container.querySelectorAll('[data-testid="readiness-row"][data-allowed="true"]');
    const rest = container.querySelectorAll('[data-testid="readiness-row"][data-allowed="false"]');
    expect(open.length).toBeGreaterThan(0);
    expect(rest.length).toBeGreaterThan(0);
    open.forEach((r) => {
      expect(isFolded(r)).toBe(false);
      expect(r.textContent).toMatch(/L 1⁻3⁺|R 0⁻3⁺/);
    });
    rest.forEach((r) => expect(isFolded(r)).toBe(true));
  });

  it("the clinic-sheet table and the home schedule, both inside the next-visit card", () => {
    const card = cardWithTitle(container, "Titration session to run next");
    const sheet = byTestId("clinic-sheet-tables");
    const home = byTestId("home-schedule");
    expect(card.contains(sheet)).toBe(true);
    expect(card.contains(home)).toBe(true);
    expect(isFolded(sheet)).toBe(true);
    expect(isFolded(home.querySelector("table"))).toBe(true);
    // the home schedule is no longer a card of its own
    const titled = Array.from(container.querySelectorAll(".MuiCard-root"))
      .filter((c) => c.textContent.includes("Home programming schedule"));
    expect(titled).toHaveLength(1);
    expect(titled[0]).toBe(card);
  });

  it("the two charts on the closed-loop checks", () => {
    container.querySelectorAll('svg[aria-label^="Left side"], svg[aria-label^="Right side"]')
      .forEach((svg) => expect(isFolded(svg)).toBe(true));
    container.querySelectorAll('svg[aria-label^="gap between the two power levels"]')
      .forEach((svg) => expect(isFolded(svg)).toBe(true));
  });

  it("the control analyses", () => {
    expect(isFolded(byTestId("control-analyses"))).toBe(true);
  });
});

// ---------------------------------------------------------------------------------------------
describe("3. nothing said twice in the open", () => {
  [["2026-09-25", newResponse], ["2026-09-15", oldResponse]].forEach(([label, fx]) => {
    it(`${label}: "no current can be recommended" at most once, "closed loop cannot start" once`, () => {
      const { container } = renderPage(fx);
      const v = visibleText(container);
      expect(countOf(v, /no current can be recommended/i)).toBeLessThanOrEqual(1);
      expect(countOf(v, /closed loop (cannot|may not) start/i)).toBe(1);
    });

    it(`${label}: the ceiling's value is stated in the next-visit card, and not again in the open`, () => {
      // Counts statements of the ceiling's VALUE ("ceiling L 4.5 mA", "4.5 mA ceiling"), not the
      // word: the current-limits check is named "... under the ceiling", which states no value.
      // (The first version of this test counted the word and so counted the check's name.)
      const VALUE = /ceiling\s*(?:[LR]\s*)?\d|\d\s?mA ceiling/i;
      const { container } = renderPage(fx);
      const v = visibleText(container);
      const next = visibleText(cardWithTitle(container, "Titration session to run next"));
      expect(countOf(next, VALUE)).toBe(1);
      // the only other open statement is the check's history line (decision 168, kept open)
      const others = countOf(v, VALUE) - 1;
      expect(others).toBeLessThanOrEqual(1);
      if (others === 1) expect(v).toMatch(/\d\s?mA ceiling — history, not a proposal/);
    });

    it(`${label}: no sentence that only points at another card`, () => {
      const { container } = renderPage(fx);
      const v = visibleText(container);
      expect(v).not.toMatch(/at the top of this page/i);
      expect(v).not.toMatch(/at the foot of this page/i);
      expect(v).not.toMatch(/card above/i);
      expect(v).not.toMatch(/Nothing was drawn up/);
    });

    it(`${label}: one line per unfitted pulse-width pairing, not one per rate`, () => {
      const { container } = renderPage(fx);
      const v = visibleText(container);
      expect(v).not.toMatch(/not enough data/i);
      const lines = container.querySelectorAll('[data-testid="unfitted-rates"]');
      const pairings = new Set();
      [...fx.two_stage.stage1.rate_strata, ...(fx.two_stage.stage1.rate_strata_clinic || [])]
        .filter((r) => r && !r.fitted).forEach((r) => pairings.add(`${r.pw_us_left}/${r.pw_us_right}/${r.source || ""}`));
      expect(lines.length).toBeGreaterThan(0);
      expect(lines.length).toBeLessThanOrEqual(pairings.size);
    });
  });

  it("the stopping rule reads once for both sides when both read alike", () => {
    const { container } = renderPage(newResponse);
    const t = container.querySelector('[data-testid="stopping-rule"]').textContent;
    expect(t).toMatch(/Both sides: not assessable/);
    expect(t).not.toMatch(/Left: not assessable/);
    expect(countOf(t, /untried combinations still look worth trying/)).toBe(1);
  });
});

// ---------------------------------------------------------------------------------------------
/**
 * Server-written sentences in the two SAVED responses that still carry a retired word. The server
 * no longer writes them (titration_plan.py, bravo_service.py, 2026-09-26), but a saved response
 * keeps the words it was served with until it is captured again. Each entry must still be found in
 * its fixture, so an entry cannot outlive the text: when the fixture is re-captured, delete it.
 */
const PENDING_SERVER_TEXT = {
  "2026-09-25": [
    "full epoch table (newest device setting, rated or not)",
    "which reads spuriously high (decision 133)",
    "was programmed for 14 epochs",
    "1 epoch on part of a ring only",
    "stop the up leg at the first step with a side-effect score of 2 or more (decision 165)",
    "at a fixed measurement current, decision 133)",
    "only while the contacts it flanks stimulate together (decision 217)",
    "an impedance test before and after at a fixed measurement current (decision 133)",
  ],
  "2026-09-15": [
    "full epoch table (newest device setting, rated or not)",
    "which reads spuriously high (decision 133)",
    "the 20 s post-ramp margin (decision 144)",
  ],
};

describe("4. one set of words", () => {
  [["2026-09-25", newResponse], ["2026-09-15", oldResponse]].forEach(([label, fx]) => {
    it(`${label}: every pending server sentence is still in its saved response`, () => {
      const raw = JSON.stringify(fx);
      PENDING_SERVER_TEXT[label].forEach((t) => expect(raw).toContain(t));
    });

    it(`${label}: the retired words are not in the open`, () => {
      const { container } = renderPage(fx);
      const v = PENDING_SERVER_TEXT[label].reduce((acc, t) => acc.split(t).join(" "), visibleText(container));
      expect(v).not.toMatch(/\bepochs?\b/i);
      expect(v).not.toMatch(/Separation \(SD\)/i);
      expect(v).not.toMatch(/\bfloor\b/i);
      expect(v).not.toMatch(/time removed|once time is removed/i);
      expect(v).not.toMatch(/adaptive mode/i);
      expect(v).not.toMatch(/\bnot resolved\b|Resolved means/);
      expect(v).not.toMatch(/decision \d{2,3}/i);
      expect(v).not.toMatch(/stimulation speed|at this speed/i);
    });
  });

  it("no string this page's own files print carries a decision number", () => {
    const dir = __dirname;
    const offenders = [];
    fs.readdirSync(dir).filter((f) => f.endsWith(".js") && !f.endsWith(".test.js")).forEach((f) => {
      const code = fs.readFileSync(path.join(dir, f), "utf8")
        .replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:"'\\])\/\/[^\n]*/g, "$1");
      const lits = code.match(/"(?:[^"\\\n]|\\.)*"|`(?:[^`\\]|\\.)*`/g) || [];
      const jsx = (code.match(/>([^<>{}]*[A-Za-z][^<>{}]*)</g) || []);
      lits.concat(jsx).forEach((s) => { if (/decision \d{2,3}/i.test(s)) offenders.push(`${f}: ${s.slice(0, 80)}`); });
    });
    expect(offenders).toEqual([]);
  });
});

// ---------------------------------------------------------------------------------------------
describe("5. the current map's colour scale is colour-blind safe", () => {
  it("runs blue (better) through a neutral grey (today) to orange (worse), never red to green", () => {
    expect(CURRENT_MAP_COLORSCALE[0]).toEqual([0, "#0072B2"]);
    expect(CURRENT_MAP_COLORSCALE[CURRENT_MAP_COLORSCALE.length - 1]).toEqual([1, "#D55E00"]);
    const mid = CURRENT_MAP_COLORSCALE.find(([t]) => t === 0.5)[1];
    const [r, g, b] = [1, 3, 5].map((i) => parseInt(mid.slice(i, i + 2), 16));
    expect(r).toBe(g);
    expect(g).toBe(b);
    const src = fs.readFileSync(path.join(__dirname, "CurrentMapCard.js"), "utf8");
    expect(src).not.toMatch(/#1A9850|#D73027|#FEE08B/i);
  });

  it("the legend says so in words, and no longer says green and red", () => {
    const { container } = renderPage(newResponse);
    const legend = container.querySelector('[data-testid="current-map-legend"]').textContent;
    expect(legend).toMatch(/blue is better than today and orange worse/);
    expect(legend).not.toMatch(/\b(green|red|yellow)\b/i);
  });
});

// ---------------------------------------------------------------------------------------------
describe("6. no horizontal scroll on a laptop", () => {
  // A 1,280 px laptop screen less the app's side navigation and the card's padding leaves about
  // 940 px for a card's content.
  const BUDGET = 940;
  const files = fs.readdirSync(__dirname).filter((f) => f.endsWith(".js") && !f.endsWith(".test.js"));

  it("no fixed minimum width wider than a laptop's card", () => {
    const offenders = [];
    files.forEach((f) => {
      const src = fs.readFileSync(path.join(__dirname, f), "utf8");
      const re = /minWidth: ?(\d+)/g;
      let m = re.exec(src);
      while (m) { if (Number(m[1]) > BUDGET) offenders.push(`${f}: ${m[0]}`); m = re.exec(src); }
    });
    expect(offenders).toEqual([]);
  });

  it("no grid whose fixed column minimums and gaps add up to more than a laptop's card", () => {
    const offenders = [];
    files.forEach((f) => {
      const src = fs.readFileSync(path.join(__dirname, f), "utf8");
      const re = /(?:COLUMNS|gridTemplateColumns)\s*[:=]\s*"([^"]+)"/g;
      let m = re.exec(src);
      while (m) {
        const cols = m[1].match(/minmax\([^)]*\)|\S+/g) || [];
        const min = cols.reduce((s, c) => {
          const mm = /^minmax\((\d+)px/.exec(c) || /^(\d+)px$/.exec(c);
          return s + (mm ? Number(mm[1]) : 0);
        }, 0) + (cols.length - 1) * 14;
        if (min > BUDGET) offenders.push(`${f}: ${m[1]} (${min} px)`);
        m = re.exec(src);
      }
    });
    expect(offenders).toEqual([]);
  });
});

// ---------------------------------------------------------------------------------------------
describe("7. the two stale passages", () => {
  it("the readiness fold states decision 277's harmonic rule, and the PI's advisory wording", () => {
    const src = fs.readFileSync(path.join(__dirname, "SensingEvidenceTable.js"), "utf8");
    expect(src).not.toMatch(/\|250 − rate\|/);
    expect(src).not.toMatch(/may be the stimulator, not the brain/);
    expect(src).toMatch(/carries a folded multiple of the stimulation rate/);
    expect(src).toMatch(/every whole multiple of the rate/);
  });
});
