/**
 * The spec-wins rulings of the taste audit, locked by reading the source files themselves
 * (artifacts/design_2026-09-26_minimalist_redesign/TASTE_AUDIT.md section D; the PI's rulings of
 * 2026-09-26: D3, D4, D5, D6, D9, D11, D12, D13, D14).
 *
 * Every rule is a pure checker over (file name, source text) that returns its violations, so the
 * same checker runs on the real files and, in the "catches a planted ..." tests, on a known-bad
 * snippet: a checker that cannot see a planted break would pass forever (house rule 11).
 *
 * Exceptions are listed by file and a short pattern, each with its reason. A new exception is a
 * decision, not a convenience: add it here with the reason, or fix the page.
 */
import fs from "fs";
import path from "path";
import { render } from "@testing-library/react";

import {
  T, LAYOUT, WEIGHT, FONT_FAMILY, contrastRatio, relativeLuminance,
} from "assets/theme/base/tokens";
import colors from "assets/theme/base/colors";
import { JumpRow } from "views/Reports/paper/links";

const SRC = path.resolve(__dirname, "..", "..");
const rel = (f) => path.relative(SRC, f).split(path.sep).join("/");

function walk(dir) {
  const out = [];
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) out.push(...walk(p));
    else if (/\.jsx?$/.test(e.name) && !/\.test\.jsx?$/.test(e.name)) out.push(p);
  }
  return out;
}
const read = (f) => fs.readFileSync(f, "utf8");

// The three redesigned pages, the research-check card they share, and the shared page pieces.
const PAGE_DIRS = ["Biomarkers", "ClosedLoopSim", "StimOptimizer", "ControlAnalyses", "paper"]
  .map((d) => path.join(SRC, "views", "Reports", d));
const THEME_DIR = path.join(SRC, "assets", "theme");
const PAGE_FILES = PAGE_DIRS.flatMap(walk);
const THEME_FILES = walk(THEME_DIR);
const REPORT_FILES = walk(path.join(SRC, "views", "Reports"));

/** Source lines with comments blanked out (a rule is about what renders, not what is described). */
function codeLines(text) {
  let inBlock = false;
  return text.split("\n").map((line) => {
    let l = line;
    if (inBlock) {
      const end = l.indexOf("*/");
      if (end < 0) return "";
      l = l.slice(end + 2);
      inBlock = false;
    }
    l = l.replace(/\/\*.*?\*\//g, "");
    const start = l.indexOf("/*");
    if (start >= 0) { inBlock = true; l = l.slice(0, start); }
    // a line comment, but not "//" inside a string such as a URL
    const lc = l.search(/(^|[^:"'`])\/\//);
    if (lc >= 0) l = l.slice(0, lc + (l[lc] === "/" ? 0 : 1));
    return l;
  });
}

const isException = (list, file, line) => list.some((e) => file.endsWith(e.file) && e.pattern.test(line));
const report = (v) => v.map((x) => `${x.file}:${x.line}: ${x.text.trim()}`).join("\n");

function hexToRgb(hex) {
  const h = hex.replace("#", "");
  const f = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
  return [0, 2, 4].map((i) => parseInt(f.slice(i, i + 2), 16));
}
const rgbToHex = (r, g, b) => `#${[r, g, b].map((c) => Number(c).toString(16).padStart(2, "0")).join("")}`;
const isGrey = ([r, g, b]) => Math.max(r, g, b) - Math.min(r, g, b) <= 16;

// A line that sets the colour of a MARK (a line, a marker, a fill, a border, a tick), not text.
const MARK_LINE = /\bline:|marker|stroke|fill|border|tickcolor|gridcolor|zerolinecolor|linecolor|background/i;

// ---------------------------------------------------------------------------------------------
// D3: no text grey lighter than ink3; input outlines at least 3:1
// ---------------------------------------------------------------------------------------------
const D3_EXCEPTIONS = [
  { file: "assets/theme/components/stepper/stepConnector.js", pattern: /#9fc9ff/i,
    reason: "the stepper's connector LINE colour (MUI draws the connector from it); no text" },
  { file: "assets/theme/components/tooltip.js", pattern: /color: T\.surface/,
    reason: "the tooltip arrow's fill (MUI draws the arrow from `color`), a mark on the white tooltip" },
];

function d3Violations(file, text) {
  const ink3Lum = relativeLuminance(T.ink3);
  const out = [];
  codeLines(text).forEach((line, i) => {
    if (MARK_LINE.test(line)) return;
    const lits = [];
    for (const m of line.matchAll(/\bcolor\s*[:=]\s*\{?\s*["'`](#[0-9A-Fa-f]{6}|#[0-9A-Fa-f]{3})\b/g)) lits.push(m[1]);
    for (const m of line.matchAll(/\bcolor\s*[:=]\s*\{?\s*["'`]rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/g)) lits.push(rgbToHex(m[1], m[2], m[3]));
    lits.forEach((hex) => {
      if (isException(D3_EXCEPTIONS, file, line)) return;
      const bad = isGrey(hexToRgb(hex))
        ? relativeLuminance(hex) > ink3Lum + 1e-9
        : contrastRatio(hex, T.surface) < 4.5;
      if (bad) out.push({ file, line: i + 1, text: line });
    });
    // A token that is only for lines and surfaces, used as a text colour.
    if (/(^|[\s{,(])color\s*:\s*(T|PAL)\.(rule|graphic|gray|page|fillMuted|surface)\b/.test(line)
      && !/background/.test(line) && !isException(D3_EXCEPTIONS, file, line)) {
      out.push({ file, line: i + 1, text: line });
    }
  });
  return out;
}

describe("D3: text greys no lighter than ink3; input outlines at least 3:1", () => {
  test("every text ink in the tokens is no lighter than ink3, and at least 4.5:1 on white", () => {
    const ink3 = relativeLuminance(T.ink3);
    ["ink", "ink2", "ink3", "notChecked", "pass"].forEach((k) => {
      expect({ k, lighter: relativeLuminance(T[k]) > ink3 + 1e-9 }).toEqual({ k, lighter: false });
    });
    ["ink", "ink2", "ink3", "accent", "refused", "caution", "notChecked", "pass",
      "vermillionText", "bluishGreenText"].forEach((k) => {
      expect({ k, ok: contrastRatio(T[k], T.surface) >= 4.5 }).toEqual({ k, ok: true });
    });
  });

  test("the theme's text greys (text, secondary) are no lighter than ink3", () => {
    const ink3 = relativeLuminance(T.ink3);
    [colors.text.main, colors.text.focus, colors.secondary.main, colors.secondary.focus].forEach((c) => {
      expect({ c, lighter: relativeLuminance(c) > ink3 + 1e-9 }).toEqual({ c, lighter: false });
    });
  });

  test("the theme's input border is at least 3:1 on white and on the page colour, computed", () => {
    expect(contrastRatio(colors.inputBorderColor, T.surface)).toBeGreaterThanOrEqual(3);
    expect(contrastRatio(colors.inputBorderColor, T.page)).toBeGreaterThanOrEqual(3);
    ["input.js", "inputOutlined.js"].forEach((f) => {
      const src = read(path.join(THEME_DIR, "components", "form", f));
      expect(src).toMatch(/borderColor:\s*inputBorderColor/);
      expect(src).not.toMatch(/#[0-9A-Fa-f]{3,6}\b/);
    });
  });

  test("no literal text colour in the three pages, paper/ or the theme is lighter than ink3", () => {
    const v = [...PAGE_FILES, ...THEME_FILES].flatMap((f) => d3Violations(rel(f), read(f)));
    expect(report(v)).toBe("");
  });

  test("the checker catches a planted light grey, a faint colour and a line token as text", () => {
    expect(d3Violations("x.js", 'const a = { color: "#9A9A9A" };')).toHaveLength(1);
    expect(d3Violations("x.js", "const a = { color: 'rgba(150,150,150,1)' };")).toHaveLength(1);
    expect(d3Violations("x.js", 'const a = { color: "#9fc9ff" };')).toHaveLength(1);
    expect(d3Violations("x.js", "const a = { fontSize: 12, color: T.graphic };")).toHaveLength(1);
    expect(d3Violations("x.js", 'const a = { color: "#5E5E5E" };')).toHaveLength(0);
    expect(d3Violations("x.js", 'line: { color: "#D9D9D6" }')).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------------------------
// D4: sentence case; no uppercase transform (RecomputeBar.js, the PI's file, excepted)
// ---------------------------------------------------------------------------------------------
const UPPERCASE = /text-?transform["']?\s*[:=]\s*\{?\s*["'`]?\s*uppercase|textTransform\s*=\s*["']uppercase/i;

function d4Violations(file, text) {
  if (file.endsWith("views/Reports/RecomputeBar.js")) return [];
  return codeLines(text).map((line, i) => ({ file, line: i + 1, text: line }))
    .filter((x) => UPPERCASE.test(x.text));
}

describe("D4: sentence case everywhere, no uppercase transform", () => {
  test("no uppercase transform in views/Reports/** (RecomputeBar.js excepted) or assets/theme/**", () => {
    const v = [...REPORT_FILES, ...THEME_FILES].flatMap((f) => d4Violations(rel(f), read(f)));
    expect(report(v)).toBe("");
  });

  test("the checker catches a planted uppercase transform, in both spellings", () => {
    expect(d4Violations("x.js", 'const s = { textTransform: "uppercase" };')).toHaveLength(1);
    expect(d4Violations("x.js", "  text-transform: uppercase;")).toHaveLength(1);
    expect(d4Violations("x.js", '<Box textTransform="uppercase" />')).toHaveLength(1);
    expect(d4Violations("views/Reports/RecomputeBar.js", 'textTransform: "uppercase"')).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------------------------
// D14 (and D5's "no red tag"): red only for a device refusal or the safe ceiling, always with ✕
// ---------------------------------------------------------------------------------------------
const REFUSED_INK = /\bT\.refused(Tint)?\b|\bPAL\.fail(Text|Fill)?\b|\bSTATE\.refused\b(?!\.glyph)|\bFAIL_TEXT\b/;
// What must be near a use of the refused ink: the ✕ glyph, or the ceiling it marks.
const REFUSED_COMPANION = /✕|\\u2715|GLYPH\.refused|\.glyph\b|glyph[=:]|[Cc]eiling|<Mark state=|RefusedCross|CROSS_MARK|STATUS_GLYPH/;
const WINDOW = 8; // lines either side: the element a style sits on and its content

const D14_EXCEPTIONS = [
  { file: "views/Reports/ClosedLoopSim/palette.js", pattern: /./,
    reason: "the definition of the roles, not a use" },
  { file: "views/Reports/StimOptimizer/ExcludedSettingsChart.js", pattern: /FAIL_TEXT = T\.refused|fill=\{T\.refusedTint\} \/>$|stroke=\{T\.refused\} strokeWidth="1\.4"|leader\(.*T\.refused\)|<circle cx=\{xi\(ex\.rate\)\}|\{sw\(</,
    reason: "the ruled-out drawing: rates below the closed-loop minimum the device needs (a device " +
      "refusal) and the unconstrained preference that falls in them; its key labels both" },
  { file: "views/Reports/Biomarkers/BiomarkerHeatmapGrids.js", pattern: /stroke=\{T\.refused\}/,
    reason: "the drawn ✕ itself (an SVG cross) on a pair the device refuses" },
  { file: "views/Reports/ClosedLoopSim/DeviceRuleLedger.js", pattern: /<RuleRow .*state="violated" ink=\{PAL\.failText\}/,
    reason: "a violated device rule; RuleRow draws the ✕ glyph (RULE_MARK.violated) on every such row" },
  { file: "views/Reports/ClosedLoopSim/StateTrack.js", pattern: /return refusal \? STATE\.refused/,
    reason: "the state object (ink and glyph together) for a track marked as a device refusal" },
  { file: "views/Reports/ClosedLoopSim/WhatWouldChangeThis.js", pattern: /^\s*ink: PAL\.failText,$/,
    reason: "a violated device rule's item; Item draws ✕ for this ink" },
  { file: "views/Reports/StimOptimizer/ClosedLoopChecks.js", pattern: /refusedFail \? T\.refused : T\.ink/,
    reason: "the checks card's headline, red only when a failing check is the rate or the ceiling " +
      "(REFUSED_CHECKS); the <Mark state=\"refused\"> ✕ is drawn beside it" },
  { file: "views/Reports/StimOptimizer/StatusLine.js", pattern: /refused: \{ state: STATE\.refused/,
    reason: "the kind table; every bullet draws STATUS_GLYPH[kind] (✕) beside its words" },
];

function d14Violations(file, text) {
  const lines = codeLines(text);
  const out = [];
  lines.forEach((line, i) => {
    if (!REFUSED_INK.test(line)) return;
    if (isException(D14_EXCEPTIONS, file, line)) return;
    const near = lines.slice(Math.max(0, i - WINDOW), i + WINDOW + 1).join("\n");
    if (!REFUSED_COMPANION.test(near)) out.push({ file, line: i + 1, text: line });
  });
  return out;
}

describe("D14 and D5: the refused ink only with ✕ or a ceiling line; no pastel or red tags", () => {
  test("every use of the refused ink in the pages and paper/ carries ✕ or a ceiling line", () => {
    const v = PAGE_FILES.flatMap((f) => d14Violations(rel(f), read(f)));
    expect(report(v)).toBe("");
  });

  test("the checker catches a planted red statistical result with no ✕", () => {
    const bad = ["<span style={{ color: T.refused }}>", "  Setting not proven better", "</span>"].join("\n");
    expect(d14Violations("x.js", bad)).toHaveLength(1);
    const good = ["<span style={{ color: T.refused }}>", "  {\"\\u2715\"} Device allows no sensing pair", "</span>"].join("\n");
    expect(d14Violations("x.js", good)).toHaveLength(0);
  });

  test("the statistical results that block closed loop are 'blocked' (ink with ✕), not 'refused'", () => {
    const src = read(path.join(SRC, "views", "Reports", "StimOptimizer", "StatusLine.js"));
    expect(src).toMatch(/add\("blocked", "No usable sensing pair"/);
    expect(src).toMatch(/add\("refused", "Device allows no sensing pair"/);
    expect(src).toMatch(/openloop_choice_resolved: \(\) => "Setting not proven better"/);
    const { STATE } = jest.requireActual("assets/theme/base/tokens");
    expect(STATE.blocked.ink).toBe(T.ink);
    expect(STATE.blocked.glyph).toBe("✕");
  });

  test("no MUI Chip or pill-shaped tag in the pages, except the one listed selection control", () => {
    const allowed = ["views/Reports/ClosedLoopSim/ThreeSourceResponsePanel.js"]; // contact chooser: an outlined
    // selection control (selected = accent tint), not a status tag
    const v = PAGE_FILES.map(rel).filter((f) => !allowed.includes(f)).flatMap((f) => codeLines(read(path.join(SRC, f)))
      .map((line, i) => ({ file: f, line: i + 1, text: line }))
      .filter((x) => /<Chip\b|<MDBadge\b|borderRadius:\s*["']?(999|9999|50%|1\d\d)/.test(x.text)
        && !/width:\s*\d{1,2},\s*height:\s*\d{1,2}/.test(x.text)));
    // a round swatch of at most 99 px square (a legend key's dot) is not a tag
    expect(report(v)).toBe("");
  });

  test("the pale red and pale caution fills appear only where listed", () => {
    const uses = PAGE_FILES.flatMap((f) => codeLines(read(f)).map((line, i) => ({ file: rel(f), line: i + 1, text: line })))
      .filter((x) => /\b(T\.refusedTint|PAL\.failFill|T\.cautionTint|PAL\.warnFill)\b/.test(x.text))
      .filter((x) => !x.file.endsWith("ClosedLoopSim/palette.js"));
    const allowed = [
      // the ruled-out drawing's region of rates the device cannot run, and its key
      /StimOptimizer\/ExcludedSettingsChart\.js$/,
      // the simulation figure's shading of wrong-side steps (a figure fill, keyed)
      /ClosedLoopSim\/ClosedLoopSimulationPanel\.js$/,
      // the sign-off sheet's caution box, bordered and headed with ▲ (a block, not a tag)
      /ClosedLoopSim\/DeploySignoffCard\.js$/,
    ];
    const v = uses.filter((x) => !allowed.some((a) => a.test(x.file)));
    expect(report(v)).toBe("");
  });
});

// ---------------------------------------------------------------------------------------------
// D6: one typeface, IBM Plex Sans, weights 400 and 600
// ---------------------------------------------------------------------------------------------
const FAMILY_OK = /^(["']inherit["']|FONT_FAMILY|baseProperties\.fontFamily)$/;
const D6_EXCEPTIONS = [
  { file: "views/Reports/Biomarkers/BiomarkerDataTimeline.js", pattern: /GUTTER_FONT_FAMILY/,
    reason: "the timeline's left label column: its column positions are computed from Arial text " +
      "widths (timelineGutter.js, the bravo-timeline-layout rules); changing the face breaks the " +
      "collision-free layout. Open question for the PI, kept as it was" },
  { file: "assets/theme/base/globals.js", pattern: /fontFamily: `'\$\{family\}'`/,
    reason: "the self-hosted Material Icons fonts' classes (C8), an icon face, not text" },
];
const FOREIGN_FACE = /Arial|Roboto|Helvetica|\bLato\b|SF Pro|Geist|Georgia|Times New Roman|Courier|monospace|\bserif\b/;

function d6Violations(file, text) {
  const out = [];
  codeLines(text).forEach((line, i) => {
    const push = () => out.push({ file, line: i + 1, text: line });
    if (isException(D6_EXCEPTIONS, file, line)) return;
    for (const m of line.matchAll(/\bfontFamily\s*:\s*([^,}\n]+)/g)) if (!FAMILY_OK.test(m[1].trim())) push();
    for (const m of line.matchAll(/\bfamily\s*:\s*([^,}\n]+)/g)) {
      if (/fontFamily/.test(line.slice(Math.max(0, m.index - 4), m.index + 6))) continue;
      if (!FAMILY_OK.test(m[1].trim()) && !/CATEGORICAL/.test(m[1])) push();
    }
    if (/["'`][^"'`]*/.test(line) && FOREIGN_FACE.test(line.replace(/sans-serif/g, ""))) push();
    // Weights: in a style object only 400 / 600 or the token names; a JSX prop names a theme weight.
    for (const m of line.matchAll(/\bfontWeight\s*:\s*([^,}\n]+)/g)) {
      const expr = m[1];
      const nums = [...expr.matchAll(/\b(\d{3})\b/g)].map((x) => Number(x[1]));
      // strings compared in a condition ("grey", "pass") are not weights
      const strs = [...expr.replace(/[!=]==?\s*["'`]\w+["'`]/g, "").matchAll(/["'`](\w+)["'`]/g)].map((x) => x[1]);
      if (nums.some((n) => n !== 400 && n !== 600)) push();
      else if (strs.some((s) => !["400", "600", "normal"].includes(s))) push();
    }
  });
  return out;
}

describe("D6: one typeface, IBM Plex Sans, in weights 400 and 600 only", () => {
  test("the token face is IBM Plex Sans first, and the two weights are 400 and 600", () => {
    expect(FONT_FAMILY.split(",")[0].trim()).toBe("'IBM Plex Sans'");
    expect(WEIGHT).toEqual({ regular: 400, strong: 600 });
  });

  test("no other face and no other weight in the pages, paper/ or the theme", () => {
    const v = [...PAGE_FILES, ...THEME_FILES].flatMap((f) => d6Violations(rel(f), read(f)));
    expect(report(v)).toBe("");
  });

  test("bold tags are drawn at 600, not the browser's 700", () => {
    const globals = jest.requireActual("assets/theme/base/globals").default;
    expect(globals["b, strong"]).toEqual({ fontWeight: WEIGHT.strong });
  });

  test("the checker catches a planted Arial, a 700 weight and a 'bold' style value", () => {
    expect(d6Violations("x.js", "const s = { fontFamily: \"Arial, sans-serif\" };").length).toBeGreaterThan(0);
    expect(d6Violations("x.js", "font: { family: 'Roboto', size: 12 }").length).toBeGreaterThan(0);
    expect(d6Violations("x.js", "const s = { fontWeight: 700 };")).toHaveLength(1);
    expect(d6Violations("x.js", "const s = { fontWeight: \"bold\" };")).toHaveLength(1);
    expect(d6Violations("x.js", "const s = { fontWeight: on ? 600 : 400, fontFamily: \"inherit\" };")).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------------------------
// D9 and D11: no middle dot in a jump-link row (the approved pairing line keeps its dot)
// ---------------------------------------------------------------------------------------------
const DOT = /·|\\u00[bB]7|&middot;/;

/** The source of every jump row: the lines from each JUMP_ROW_CLASS / <JumpRow / jump list to its end. */
function jumpRowViolations(file, text) {
  const lines = codeLines(text);
  const out = [];
  lines.forEach((line, i) => {
    if (!/JUMP_ROW_CLASS\}|className=\{`[^`]*\$\{JUMP_ROW_CLASS\}|<JumpRow\b|export const (JUMPS|CONTENTS) =/.test(line)) return;
    // the element (or list) runs until its closing tag or bracket, at most 25 lines
    for (let j = i; j < Math.min(lines.length, i + 25); j += 1) {
      if (DOT.test(lines[j])) out.push({ file, line: j + 1, text: lines[j] });
      if (j > i && /^\s*(<\/MDBox>|<\/nav>|\];|\/>)\s*$/.test(lines[j])) break;
    }
  });
  return out;
}

describe("D9 and D11: no middle dot in a jump-link row", () => {
  test("every jump row in the pages is built from the shared class or component", () => {
    const rows = PAGE_FILES.filter((f) => /JUMP_ROW_CLASS\}|<JumpRow\b/.test(read(f))).map(rel);
    expect(rows).toEqual(expect.arrayContaining([
      "views/Reports/ClosedLoopSim/DecisionCard.js",
      "views/Reports/StimOptimizer/index.js",
    ]));
  });

  test("no jump row's source (its element and its list of links) carries a middle dot", () => {
    const v = PAGE_FILES.flatMap((f) => jumpRowViolations(rel(f), read(f)));
    expect(report(v)).toBe("");
  });

  test("the shared jump row renders the Stim Optimizer's contents with no dot, as a nav", () => {
    const src = read(path.join(SRC, "views", "Reports", "StimOptimizer", "index.js"));
    const block = src.slice(src.indexOf("export const CONTENTS ="), src.indexOf("];", src.indexOf("export const CONTENTS =")));
    const items = [...block.matchAll(/\["([^"]+)", "([^"]+)"\]/g)].map((m) => ({ href: `#${m[1]}`, label: m[2] }));
    expect(items.length).toBeGreaterThanOrEqual(3);
    const { container } = render(<JumpRow label="Contents" items={items} />);
    const nav = container.querySelector("nav[data-paper='jump-row']");
    expect(nav).not.toBeNull();
    expect(nav.querySelectorAll("a")).toHaveLength(items.length);
    expect(nav.textContent).not.toMatch(/·/);
  });

  test("the checker catches a planted dot between two jump links", () => {
    const bad = ["<MDBox component=\"nav\" className={`x ${JUMP_ROW_CLASS}`}>", "  <a>One</a>{\" · \"}<a>Two</a>", "</MDBox>"].join("\n");
    expect(jumpRowViolations("x.js", bad)).toHaveLength(1);
  });
});

// ---------------------------------------------------------------------------------------------
// D12: the caution ink always comes with ▲
// ---------------------------------------------------------------------------------------------
const CAUTION_INK = /\bT\.caution\b|\bPAL\.warn(Text)?\b|\bSTATE\.caution\b(?!\.glyph)|STATE\.caution\.ink/;
const CAUTION_COMPANION = /▲|\\u25[bB]2|GLYPH\.caution|\.glyph\b|glyph[=:]|<Mark state=|CAUTION_MARK|STATUS_GLYPH/;

const D12_EXCEPTIONS = [
  { file: "views/Reports/ClosedLoopSim/palette.js", pattern: /./, reason: "the definition of the roles" },
  { file: "views/Reports/StimOptimizer/BandResponseStrip.js", pattern: /HATCH = T\.caution/,
    reason: "a hatch fill in a figure (a mark), keyed in the figure's own legend" },
  { file: "views/Reports/StimOptimizer/LadderFigures.js", pattern: /stroke=\{T\.caution\}/,
    reason: "a leader line to a labelled harmonic landing (a mark)" },
  { file: "views/Reports/ClosedLoopSim/LsbPowerPanel.js", pattern: /line: \{ color: PAL\.warnText|curColor = /,
    reason: "figure marks (a line and a marker fill); the text beside them carries ▲" },
  { file: "views/Reports/ClosedLoopSim/ProvisionalNote.js", pattern: /borderLeft/,
    reason: "the note's left rule; its first line carries ▲" },
  { file: "views/Reports/ClosedLoopSim/PanelStaleNote.js", pattern: /borderLeft/,
    reason: "the note's left rule" },
  { file: "views/Reports/ClosedLoopSim/StateTrack.js", pattern: /STATE\.caution/,
    reason: "the state object (ink and ▲ together) a track draws" },
  { file: "views/Reports/StimOptimizer/StatusLine.js", pattern: /yellow: \{ state: STATE\.caution/,
    reason: "the kind table; every bullet draws STATUS_GLYPH[kind] (▲) beside its words" },
  { file: "views/Reports/ClosedLoopSim/WhatWouldChangeThis.js", pattern: /^\s*ink: PAL\.warnText,/,
    reason: "an item's ink; Item draws ▲ for this ink" },
  { file: "views/Reports/ClosedLoopSim/BandCandidateIdentity.js", pattern: /return STATE\.caution;/,
    reason: "the verdict's state object; the verdict line draws STATE.caution.glyph" },
  { file: "views/Reports/ClosedLoopSim/DeviceRuleLedger.js", pattern: /<RuleRow .*ink=\{PAL\.warnText\}/,
    reason: "an advisory rule; RuleRow draws ▲ before the rule id for this ink" },
  { file: "views/Reports/ClosedLoopSim/DeploySignoffCard.js", pattern: /^const CAVEAT_INK = /,
    reason: "the severity inks; ReportCaveats draws ▲ beside a caution-coloured severity" },
  { file: "views/Reports/ClosedLoopSim/glyphs.js", pattern: /fill=\{PAL\.warn\}/,
    reason: "AmberGlyph, a filled caution dot defined here and drawn by no page today" },
  { file: "views/Reports/ClosedLoopSim/PrescriptionPanel.js", pattern: /<Note\b[^>]*PAL\.warnText/,
    reason: "Note draws ▲ itself for the caution ink (unless its text already starts with one)" },
  { file: "views/Reports/ClosedLoopSim/LsbPowerPanel.js", pattern: /const curTextColor = /,
    reason: "the 'now' annotation's ink; its text is prefixed ▲ exactly when this ink is caution" },
  { file: "views/Reports/StimOptimizer/blockOfTime.js", pattern: /color: T\.caution/,
    reason: "the block-of-time dagger (†), its own shape, keyed by the note under each card" },
  { file: "views/Reports/ClosedLoopSim/PrescriptionPanel.js", pattern: /\$\{PAL\.warnText\}22/,
    reason: "the faint 'PLANNING ONLY' watermark behind the table; the same words are printed at " +
      "full contrast with ▲ in the banner above it. For the PI: it is under 4.5:1 by design" },
];

function d12Violations(file, text) {
  const lines = codeLines(text);
  const out = [];
  lines.forEach((line, i) => {
    if (!CAUTION_INK.test(line)) return;
    if (isException(D12_EXCEPTIONS, file, line)) return;
    const near = lines.slice(Math.max(0, i - WINDOW), i + WINDOW + 1).join("\n");
    if (!CAUTION_COMPANION.test(near)) out.push({ file, line: i + 1, text: line });
  });
  return out;
}

describe("D12: the caution ink always comes with ▲", () => {
  test("every use of the caution ink in the pages and paper/ has ▲ in the same element", () => {
    const v = PAGE_FILES.flatMap((f) => d12Violations(rel(f), read(f)));
    expect(report(v)).toBe("");
  });

  test("the checker catches a planted caution-coloured sentence with no ▲", () => {
    expect(d12Violations("x.js", "<span style={{ color: T.caution }}>not proven</span>")).toHaveLength(1);
    expect(d12Violations("x.js", "<span style={{ color: T.caution }}>▲ not proven</span>")).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------------------------
// D13: 64 px between sections, a content column of at most 1,120 px
// ---------------------------------------------------------------------------------------------
describe("D13: 64 px between sections and a content column of at most 1,120 px", () => {
  test("the tokens say 1120 and 64", () => {
    expect(LAYOUT.contentMax).toBe(1120);
    expect(LAYOUT.betweenSections).toBe(64);
  });

  test("the layout and the three pages cap their column at the token, and nothing wider", () => {
    const layout = read(path.join(SRC, "layouts", "DatabaseLayout", "DashboardLayout.js"));
    expect(layout).toMatch(/maxWidth:\s*pxToRemPlain\(LAYOUT\.contentMax\)/);
    ["Biomarkers", "ClosedLoopSim", "StimOptimizer"].forEach((p) => {
      const src = read(path.join(SRC, "views", "Reports", p, "index.js"));
      expect({ p, capped: /maxWidth:\s*LAYOUT\.contentMax/.test(src) }).toEqual({ p, capped: true });
      const wide = [...src.matchAll(/maxWidth:\s*["']?(\d{4,})/g)].map((m) => Number(m[1])).filter((n) => n > 1120);
      expect({ p, wide }).toEqual({ p, wide: [] });
    });
  });

  test("the Closed-Loop page's own sections are 64 px apart (MUI unit 8 x 8)", () => {
    const src = read(path.join(SRC, "views", "Reports", "ClosedLoopSim", "index.js"));
    ["cl-decision", "cl-grid", "cl-rules", "cl-evidence", "cl-stability"].forEach((id) => {
      expect({ id, gap: new RegExp(`id="${id}" mb=\\{8\\}`).test(src) }).toEqual({ id, gap: true });
    });
  });
});
