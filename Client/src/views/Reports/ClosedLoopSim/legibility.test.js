/**
 * Legibility floor for the Closed-Loop and Stim Optimizer pages (the PI, 2026-09-24: "make sure
 * everything is optimized for legibility").
 *
 * Measured on the live Closed-Loop page first: 79 of its 117 visible text elements were under 11 px
 * (down to 8.5 px in the source) and its captions used greys at about 3.5:1 against white, below the
 * 4.5:1 minimum for body text. The Stim Optimizer page already had a type scale (body 13 px,
 * secondary 12 px, secondary grey #5E5E5E). The Closed-Loop page now has a floor of 11 px for text
 * and for figure fonts, and #5E5E5E (about 6.4:1) where the light greys were. This test reads the
 * source of both pages so the floor cannot quietly erode.
 */
import fs from "fs";
import path from "path";

const DIRS = ["ClosedLoopSim", "StimOptimizer", "ControlAnalyses"].map((d) => path.join(__dirname, "..", d));
const FILES = DIRS.flatMap((d) => fs.readdirSync(d)
  .filter((f) => f.endsWith(".js") && !f.endsWith(".test.js"))
  .map((f) => path.join(d, f)))
  // the recompute bar both pages show (the PI lifted rule 7 for it on 2026-09-24). Since the
  // redesign of 2026-09-26 (WP7) the test READS this file and the file itself is not edited: it
  // keeps literal colours of its own, so it is held to the floors below and not to the redesign's
  // no-hex rule, which is for files the redesign may change.
  .concat([path.join(__dirname, "..", "RecomputeBar.js")])
  // the shared lines and components the three pages render (WP7)
  .concat(["CacheStatusLine.js", "figureStyle.js"].map((f) => path.join(__dirname, "..", f)))
  .concat(fs.readdirSync(path.join(__dirname, "..", "paper"))
    .filter((f) => f.endsWith(".js") && !f.endsWith(".test.js"))
    .map((f) => path.join(__dirname, "..", "paper", f)));
// #7A7A7A added 2026-09-26 (the design review of the Stim Optimizer and Biomarkers pages, §1.2(e)):
// it measures 4.29:1 on white, under the 4.5:1 minimum, and five Stim Optimizer chart files drew
// their axis text in it while this list, which left it out, passed them.
const LIGHT_GREYS = ["#777", "#888", "#8A8A8A", "#999", "#999999", "#9A9A9A", "#7A7A7A"];

/** WCAG contrast ratio of a hex colour against white. */
function contrastOnWhite(hex) {
  let h = hex.replace("#", "");
  if (h.length === 3) h = h.split("").map((c) => c + c).join("");
  const lin = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255)
    .map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  const L = 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2];
  return 1.05 / (L + 0.05);
}

test("no text or figure font on either page is set below 11 px", () => {
  const offenders = [];
  FILES.forEach((f) => {
    const src = fs.readFileSync(f, "utf8");
    const re = /(?:fontSize: |font: \{ ?size: )(\d+(?:\.\d+)?)(?![\d.])/g;
    let m = re.exec(src);
    while (m) {
      if (Number(m[1]) < 11) offenders.push(`${path.basename(f)}: ${m[0]}`);
      m = re.exec(src);
    }
  });
  expect(offenders).toEqual([]);
});

test("the sizes the first check could not see are over the floor too (decision 302)", () => {
  // The first check reads `fontSize: 12`. It could not see `fontSize: dense ? 9.5 : 10.5`, nor an
  // SVG's `fontSize="9"`, and those were exactly the small text under "Sign agreement" and in the
  // triangle's E1/E2/E3 labels the PI could not read (2026-09-26).
  const offenders = [];
  FILES.forEach((f) => {
    const src = fs.readFileSync(f, "utf8");
    const tern = /fontSize: [^,}\n]*?\? *(\d+(?:\.\d+)?) *: *(\d+(?:\.\d+)?)/g;
    let m = tern.exec(src);
    while (m) {
      [m[1], m[2]].forEach((v) => { if (Number(v) < 11) offenders.push(`${path.basename(f)}: ${m[0]}`); });
      m = tern.exec(src);
    }
    const svg = /fontSize="(\d+(?:\.\d+)?)"/g;
    m = svg.exec(src);
    while (m) {
      if (Number(m[1]) < 11) offenders.push(`${path.basename(f)}: ${m[0]}`);
      m = svg.exec(src);
    }
  });
  expect(offenders).toEqual([]);
});

test("no caption on either page uses a grey below 4.5:1 on white", () => {
  const offenders = [];
  FILES.forEach((f) => {
    const src = fs.readFileSync(f, "utf8");
    LIGHT_GREYS.forEach((g) => {
      // text colours only (`color: "#..."`): a fill or a stroke in the same grey is not text
      if (new RegExp(`color: ?"${g}"`, "i").test(src)) offenders.push(`${path.basename(f)}: ${g}`);
    });
  });
  expect(offenders).toEqual([]);
});

test("no chart text on either page is drawn in a grey below 4.5:1 on white (SVG fill)", () => {
  // The caption check above reads `color:` only. Text inside an SVG chart takes its colour from
  // `fill`, so axis ticks and axis titles in #7A7A7A passed it on five Stim Optimizer charts (the
  // design review of 2026-09-26, §1.2(e)). This reads every `<text ... fill="#...">` (or
  // `fill={"#..."}`) and fails any literal colour under 4.5:1 on white. A fill given by a variable
  // (a palette role) is not a literal and is not read here.
  const offenders = [];
  FILES.forEach((f) => {
    const src = fs.readFileSync(f, "utf8");
    const re = /<text\b[^>]*?\bfill=\{?"(#[0-9A-Fa-f]{3,6})"/g;
    let m = re.exec(src);
    while (m) {
      if (contrastOnWhite(m[1]) < 4.5) offenders.push(`${path.basename(f)}: ${m[1]} (${contrastOnWhite(m[1]).toFixed(2)}:1)`);
      m = re.exec(src);
    }
  });
  expect(offenders).toEqual([]);
});

test("the contrast arithmetic the chart-text check relies on", () => {
  expect(contrastOnWhite("#7A7A7A")).toBeCloseTo(4.29, 2);
  expect(contrastOnWhite("#5E5E5E")).toBeGreaterThan(6.4);
  expect(contrastOnWhite("#FFFFFF")).toBeCloseTo(1, 5);
});

// Replaced 2026-09-26 (WP7 of the redesign), because its name would now be untrue: the test "the
// Closed-Loop page still wraps its content in the darker text colour" checked for the wrapper
// `LegibleText`, which gave the theme's text colour (#7b809a, 3.9:1) a darker grey. The theme's own
// text colour is now that grey (`ink3`, #5E5E5E, 6.48:1), so the wrapper is deleted. What it
// protected is checked where it now lives: the theme itself.
test("the app theme's text colour is at least 4.5:1 on white and on the page background", () => {
  // eslint-disable-next-line global-require
  const colors = require("assets/theme/base/colors").default;
  // eslint-disable-next-line global-require
  const { T, contrastRatio } = require("assets/theme/base/tokens");
  expect(contrastOnWhite(colors.text.main)).toBeGreaterThanOrEqual(4.5);
  expect(contrastRatio(colors.text.main, T.page)).toBeGreaterThanOrEqual(4.5);
  expect(colors.text.main.toUpperCase()).toBe("#5E5E5E");
});

test("no page file wraps itself in the deleted legibility wrapper", () => {
  expect(fs.existsSync(path.join(__dirname, "..", "legibleText.js"))).toBe(false);
  const offenders = FILES.concat(["Biomarkers"].flatMap((d) => fs.readdirSync(path.join(__dirname, "..", d))
    .filter((f) => f.endsWith(".js") && !f.endsWith(".test.js"))
    .map((f) => path.join(__dirname, "..", d, f))))
    .filter((f) => /legibleText|<LegibleText/.test(fs.readFileSync(f, "utf8")));
  expect(offenders).toEqual([]);
});

test("every literal text colour in the recompute bar is at least 4.5:1 on white (read, not edited)", () => {
  // Decisions 258 and 259: the bar's text was enlarged and darkened. It is the PI's file (CLAUDE.md
  // section 8 rule 7), so it keeps its own literals; this reads each `color: "#..."` and the ink it
  // assigns, and fails if any falls under the minimum.
  const src = fs.readFileSync(path.join(__dirname, "..", "RecomputeBar.js"), "utf8");
  const lits = (src.match(/color: ?"(#[0-9A-Fa-f]{3,6})"/g) || []).map((m) => m.match(/#[0-9A-Fa-f]+/)[0])
    .concat((src.match(/const ink = [^;]*"(#[0-9A-Fa-f]{3,6})"/g) || []).map((m) => m.match(/#[0-9A-Fa-f]+/)[0]));
  expect(lits.length).toBeGreaterThan(0);
  lits.forEach((h) => expect(contrastOnWhite(h)).toBeGreaterThanOrEqual(4.5));
});

// THE REDESIGN OF 2026-09-26 (SPEC section 7, WP6). The Closed-Loop page takes every colour from
// the shared tokens through `palette.js`, and the pass, refused and caution FILL roles are never a
// text colour: text uses the *Text roles or a token ink, each with its glyph.
const OWN = fs.readdirSync(__dirname)
  .filter((f) => f.endsWith(".js") && !f.endsWith(".test.js"))
  .map((f) => [f, fs.readFileSync(path.join(__dirname, f), "utf8")]);
const stripComments = (src) => src.replace(/\/\*[\s\S]*?\*\//g, "")
  .replace(/(^|[^:"'\\])\/\/[^\n]*/g, "$1");

test("no Closed-Loop file draws text in the pass, refused or caution fill role", () => {
  const offenders = [];
  OWN.forEach(([f, src]) => {
    const re = /\bcolor: *(?:[^,}\n]*\?[^,}\n]*:)?[^,}\n]*\bPAL\.(fail|pass|warn)\b(?!Text|Fill|Border)/g;
    let m = re.exec(stripComments(src));
    while (m) {
      offenders.push(`${f}: ${m[0]}`);
      m = re.exec(stripComments(src));
    }
  });
  expect(offenders).toEqual([]);
});

test("no Closed-Loop file other than palette.js writes a hex colour of its own", () => {
  const offenders = [];
  OWN.filter(([f]) => f !== "palette.js").forEach(([f, src]) => {
    const hexes = stripComments(src).match(/["'`]#[0-9A-Fa-f]{3,8}\b/g) || [];
    hexes.forEach((h) => offenders.push(`${f}: ${h}`));
  });
  expect(offenders).toEqual([]);
});

test("no Closed-Loop file writes a font size as a number of its own", () => {
  const offenders = [];
  OWN.forEach(([f, src]) => {
    const code = stripComments(src);
    const re = /(?:fontSize: |fontSize=\{?"?|font: \{[^}]*?size: |tickfont: \{[^}]*?size: )(\d+(?:\.\d+)?)/g;
    let m = re.exec(code);
    while (m) {
      offenders.push(`${f}: ${m[0]}`);
      m = re.exec(code);
    }
  });
  expect(offenders).toEqual([]);
});
