/**
 * The taste follow-up on the Stim Optimizer page (TASTE_AUDIT.md sections C and D; the PI's
 * rulings of 2026-09-26): one focused test per item built here.
 *
 *  D14  red means ONLY a device refusal or a value above the safe ceiling; a statistical or
 *       evidence result that blocks closed loop is drawn in ink with ✕.
 *  C2   still grey blocks shaped like the table, never a spinner, with the waiting words kept.
 *  C5   the page's own headings break their lines evenly (text-wrap: balance).
 *  C6   the page head is the shared PageHead.
 *  C7   the browser tab's title is "Stim optimizer".
 *  C9   an empty cell is a word ("not given", "none", "same"), never "—".
 *  C11  no "·" in the jump-link row; C3 the row is the shared, un-underlined jump row.
 */
import "@testing-library/jest-dom";
import fs from "fs";
import path from "path";
import { render as rtlRender } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";

import theme from "assets/theme";
import { PlatformContextProvider } from "context";
import { T } from "assets/theme/base/tokens";
import { JUMP_ROW_CLASS } from "assets/theme/base/globals";

import oldResponse from "./__fixtures__/rcs08_stim_optimizer_two_stage.json";
import newResponse from "./__fixtures__/rcs08_stim_optimizer_2026-09-25.json";
import DecisionStrip from "./DecisionStrip";
import TwoStagePlanCard from "./TwoStagePlanCard";
import SensingEvidenceTable from "./SensingEvidenceTable";
import ClosedLoopChecks from "./ClosedLoopChecks";
import { HEADING } from "./typeScale";
import { EMPTY, fmtMa, fmtHz, fmtUs, fmtOf, contactLabel } from "./stimFormat";

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
import StimOptimizer, { TAB_TITLE } from "./index";

const wrap = (ui) => (
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>
);
const render = (ui) => rtlRender(wrap(ui));
function renderPage(fx) {
  global.__SO_FX__ = fx;
  return rtlRender(wrap(<StimOptimizer />));
}

/** "#B42318" -> "rgb(180, 35, 24)", as jsdom reports an inline colour. */
const rgb = (hex) => {
  const h = hex.replace("#", "");
  return `rgb(${[0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16)).join(", ")})`;
};

/** Every element whose own whole text is a bare dash (an empty cell drawn as "—"). */
const bareDashes = (root) => Array.from(root.querySelectorAll("*"))
  .filter((el) => /^—(\s*(µs|mA|Hz))?$/.test(el.textContent.trim()));

describe("D14: red only for a device refusal or a value above the ceiling", () => {
  it("draws a 'not usable' row on a pair the device allows in ink, one on a pair it refuses in red", () => {
    const { container } = render(<SensingEvidenceTable closedLoop={newResponse.closed_loop} />);
    const marks = (allowed) => Array.from(container.querySelectorAll(`[data-testid="readiness-row"][data-allowed="${allowed}"] [aria-label="not usable"]`));
    const allowedMarks = marks("true");
    const refusedMarks = marks("false");
    expect(allowedMarks.length).toBeGreaterThan(0);
    expect(refusedMarks.length).toBeGreaterThan(0);
    allowedMarks.forEach((m) => { expect(m.style.color).toBe(rgb(T.ink)); expect(m.textContent).toBe("✕"); });
    refusedMarks.forEach((m) => { expect(m.style.color).toBe(rgb(T.refused)); expect(m.textContent).toBe("✕"); });
    // The count headline ("0 of 50 ... usable") is a statistical result: ink with ✕, never red.
    const none = container.querySelector('[aria-label="no usable combination"]');
    expect(none.textContent).toBe("✕");
    expect(none.style.color).toBe(rgb(T.ink));
    // The allowed pairs' sentence blocks are ink, never red.
    container.querySelectorAll('[data-testid="readiness-row"][data-allowed="true"] span').forEach((s) => {
      expect(s.style.color).not.toBe(rgb(T.refused));
    });
  });

  it("the four checks: 'not proven better' and 'no band moves' fail in ink, the rate and the ceiling in red", () => {
    const plan = JSON.parse(JSON.stringify(newResponse.two_stage));
    const mk = (name) => ({ name, verdict: "FAIL", detail: "x", evidence: {} });
    const colourOf = (conditions) => {
      plan.gate = { passed: false, conditions };
      const { container, unmount } = render(<ClosedLoopChecks plan={plan} />);
      const out = Array.from(container.querySelectorAll('[aria-label="fails"]')).map((m) => m.style.color);
      const head = container.querySelector('[aria-label="may not start"]').style.color;
      unmount();
      return { out, head };
    };
    const stat = colourOf([mk("openloop_choice_resolved"), mk("adaptive_band_passes_lfp_response")]);
    expect(stat.out).toEqual([rgb(T.ink), rgb(T.ink)]);
    expect(stat.head).toBe(rgb(T.ink));
    // PIN CHANGED 2026-09-26: the current-limits check is red only when a proposed limit is above
    // the ceiling (the other ways it fails block in ink), so this one names that cause.
    const dev = colourOf([mk("rate_at_or_above_adaptive_minimum"),
      { ...mk("amplitude_limits_inside_envelope_and_under_ceiling"),
        detail: "Left: upper limit 4.8 mA exceeds the declared ceiling of 4.5 mA" }]);
    expect(dev.out).toEqual([rgb(T.refused), rgb(T.refused)]);
    expect(dev.head).toBe(rgb(T.refused));
  });

  it("the status list on RCS08 carries no red: both of its blocks are statistical", () => {
    const { container } = renderPage(newResponse);
    const glyphs = Array.from(container.querySelectorAll('[data-testid="status-glyph"]'));
    expect(glyphs.length).toBeGreaterThan(0);
    glyphs.forEach((g) => expect(g.style.color).not.toBe(rgb(T.refused)));
    const blocked = Array.from(container.querySelectorAll('[data-testid="status-bullet"][data-kind="blocked"]'));
    expect(blocked.map((b) => b.textContent)).toEqual(["✕No usable sensing pair", "✕Setting not proven better"]);
    // The ceiling line's safety sentence stays word for word.
    expect(container.textContent).toContain("Nothing above it is offered on this page.");
  });
});

describe("C2: composed loading states, no spinner", () => {
  it("the decision strip is the Today | Suggested | Difference table in still grey blocks, with the waiting words", () => {
    const { container, getByTestId } = render(<DecisionStrip arms={{}} plan={null} planLoading inForce={null} />);
    const box = getByTestId("decision-strip-loading");
    expect(box.textContent).toContain("computing (about a minute the first time)");
    ["Today", "Suggested", "Difference", "Rate", "Pulse width", "Current", "Left", "Right"].forEach((w) => expect(box.textContent).toContain(w));
    expect(container.querySelectorAll('[data-testid="placeholder-block"]').length).toBeGreaterThanOrEqual(18);
    expect(container.querySelector('[role="progressbar"], .MuiCircularProgress-root')).toBeNull();
    container.querySelectorAll('[data-testid="placeholder-block"]').forEach((b) => {
      expect(b.getAttribute("aria-hidden")).toBe("true");
      expect(b.style.animation || "").toBe("");
      expect(b.style.transition || "").toBe("");
    });
  });

  it("the two-stage card is the four checks' grid in still grey blocks, with the waiting words", () => {
    const { container, getByTestId } = render(<TwoStagePlanCard plan={null} loading err={null} />);
    expect(getByTestId("two-stage-loading").textContent).toContain(
      "computing the two-stage plan (about a minute the first time; a few seconds afterwards)");
    expect(container.querySelectorAll('[data-testid="placeholder-block"]').length).toBe(13);
    expect(container.querySelector('[role="progressbar"], .MuiCircularProgress-root')).toBeNull();
  });
});

describe("C6, C7, C11, C3, C5: the page head", () => {
  it("is the shared PageHead, with the question, the status sentence and the ceiling line", () => {
    const { container } = renderPage(newResponse);
    const head = container.querySelector("header[data-paper='page-head']");
    expect(head).not.toBeNull();
    expect(head.querySelector("h1").textContent).toBe("Should today's setting change, and can closed loop start?");
    expect(head.querySelector("[role='status']").textContent).toBe("Keep today's setting on both sides; closed loop cannot start.");
    expect(head.querySelector("[data-paper='ceiling-line']")).not.toBeNull();
    expect(head.querySelector('[data-testid="status-line"]')).not.toBeNull();
  });

  it("sets the tab's title to 'Stim optimizer'", () => {
    expect(TAB_TITLE).toBe("Stim optimizer");
    renderPage(newResponse);
    expect(document.title).toMatch(/^Stim optimizer/);
  });

  it("the contents row has no middle dot and is the shared, un-underlined jump row", () => {
    const { container } = renderPage(newResponse);
    const nav = container.querySelector('nav[aria-label="Contents"]');
    expect(nav).not.toBeNull();
    expect(nav.classList.contains(JUMP_ROW_CLASS)).toBe(true);
    expect(nav.textContent).not.toContain("·");
    const links = Array.from(nav.querySelectorAll("a"));
    expect(links.map((a) => a.textContent)).toEqual(["Proven better?", "Currents tried", "Closed loop", "Next visit"]);
    links.forEach((a) => expect(a.style.textDecoration).toBe("none"));
  });

  it("the page's own headings break their lines evenly", () => {
    expect(HEADING.textWrap).toBe("balance");
    // jsdom drops the `text-wrap` property from computed styles, so the rule is read off the
    // source: every section heading in this folder's own files is styled with HEADING.
    const dir = __dirname;
    const files = fs.readdirSync(dir).filter((f) => f.endsWith(".js") && !f.endsWith(".test.js"));
    const offenders = [];
    let n = 0;
    files.forEach((f) => {
      fs.readFileSync(path.join(dir, f), "utf8").split("\n").forEach((line, i) => {
        if (/component="h[2-6]"/.test(line)) {
          n += 1;
          if (!/HEADING/.test(line)) offenders.push(`${f}:${i + 1}`);
        }
      });
    });
    expect(n).toBeGreaterThan(5);
    expect(offenders).toEqual([]);
  });
});

describe("C9: an empty cell is a word, never '—'", () => {
  it("the formatters say 'not given'", () => {
    expect(EMPTY).toBe("not given");
    expect([fmtMa(null), fmtHz(undefined), fmtUs(NaN), contactLabel(null)]).toEqual(Array(4).fill("not given"));
    expect(fmtOf(null, 18)).toBe("not given (of 18)");
  });

  it("the decision strip prints no bare dash, and the missing right pulse width reads 'not given'", () => {
    const { container } = render(<DecisionStrip arms={{}} plan={oldResponse.two_stage} inForce={oldResponse.in_force_by_side || null} />);
    expect(bareDashes(container)).toEqual([]);
    expect(container.textContent).not.toMatch(/— µs/);
  });

  it("the readiness rows print no bare dash; an empty band list reads 'none'", () => {
    const cl = JSON.parse(JSON.stringify(newResponse.closed_loop));
    cl.responding_cells = cl.responding_cells.map((c, i) => (i === 0
      ? { ...c, qualifying_centers_hz: [], median_separation_d: null, hemisphere: null } : c));
    const { container } = render(<SensingEvidenceTable closedLoop={cl} />);
    expect(bareDashes(container)).toEqual([]);
    expect(container.textContent).toContain("none");
    expect(container.textContent).toContain("not given");
  });

  it("the two-stage card's tables print 'not given' for a missing value", () => {
    const { container } = render(<TwoStagePlanCard plan={oldResponse.two_stage} loading={false} err={null} />);
    expect(bareDashes(container)).toEqual([]);
  });
});
