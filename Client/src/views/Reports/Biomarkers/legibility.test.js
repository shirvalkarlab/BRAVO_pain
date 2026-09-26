/**
 * Legibility floor for the Biomarkers page (decision 304; rewritten for the redesign of 2026-09-26,
 * artifacts/design_2026-09-26_minimalist_redesign/SPEC.md sections 2 and 7, WP3).
 *
 * What it checks now:
 *   1. every colour comes from the shared tokens (assets/theme/base/tokens.js and dataColors.js): no
 *      page file writes a hex colour of its own (the older timeline and every panel included);
 *   2. EVERY text colour it can resolve -- not only the greys -- is 4.5:1 or more on white: a literal,
 *      a token (`T.ink3`), a data colour (`PAIN.high`) or a named constant that points at one of
 *      them, in a text position (a font object, an `sx` or `style` object, an inline HTML style, an
 *      SVG <text> fill);
 *   3. no text or figure font is set under 12 px (the spec's smallest size), except in the
 *      acquisition timeline's own two files, whose fonts change only through the
 *      bravo-timeline-layout skill and keep the 11 px floor of decision 304;
 *   4. the acquisition timeline's frequency labels are ink beside a small tick in the lane's own
 *      colour (the spec's replacement for decision 304's "darker variant of the same hue" rule), and
 *      its lanes are coloured by the ordered (cividis) scale;
 *   5. the timeline's gutter geometry is untouched (bravo-timeline-layout).
 */
import fs from "fs";
import path from "path";

// Every file whose text the Biomarkers page prints. BandTimeSweepPanel.js is rendered by nothing
// (index.js keeps it as a file only) and is left out, as the page's other source tests leave it out.
const FILES = fs.readdirSync(__dirname)
  .filter((f) => f.endsWith(".js") && !f.endsWith(".test.js") && f !== "BandTimeSweepPanel.js");

const read = (f) => fs.readFileSync(path.join(__dirname, f), "utf8");
function stripComments(src) {
  return src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:"'\\])\/\/[^\n]*/g, "$1");
}

// ---- contrast ------------------------------------------------------------------------------
function rgbOf(hex) {
  let h = hex.replace("#", "");
  if (h.length === 3 || h.length === 4) h = h.slice(0, 3).split("").map((c) => c + c).join("");
  if (h.length === 8) h = h.slice(0, 6);
  if (h.length !== 6) return null;
  return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16));
}
function luminance([r, g, b]) {
  const f = (c) => { const s = c / 255; return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4; };
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
}
export function contrastOnWhite(hex) {
  const rgb = rgbOf(hex);
  return rgb ? 1.05 / (luminance(rgb) + 0.05) : null;
}

// The shared tokens and data colours, read from their own files: `T.x`, and the data colours'
// named exports (`PAIN.high`, `SIDE.left`, `CONTEXT`, `CATEGORICAL[2]`).
const THEME = path.join(__dirname, "..", "..", "..", "assets", "theme", "base");
const readTheme = (f) => fs.readFileSync(path.join(THEME, f), "utf8");
function tokenColours() {
  const out = {};
  const tok = stripComments(readTheme("tokens.js"));
  const tBlock = tok.slice(tok.indexOf("export const T = {"), tok.indexOf("};", tok.indexOf("export const T = {")));
  tBlock.replace(/^\s+([a-zA-Z0-9]+):\s*"(#[0-9A-Fa-f]{6})"/gm, (_, k, h) => { out[`T.${k}`] = h; });
  const dc = stripComments(readTheme("dataColors.js"));
  ["SIDE", "PAIN"].forEach((obj) => {
    const b = dc.slice(dc.indexOf(`export const ${obj} = {`), dc.indexOf("};", dc.indexOf(`export const ${obj} = {`)));
    b.replace(/([a-zA-Z]+):\s*"(#[0-9A-Fa-f]{6})"/g, (_, k, h) => { out[`${obj}.${k}`] = h; });
  });
  const ctx = dc.match(/export const CONTEXT = "(#[0-9A-Fa-f]{6})"/);
  if (ctx) out.CONTEXT = ctx[1];
  const cat = dc.match(/export const CATEGORICAL = \[([^\]]*)\]/);
  if (cat) (cat[1].match(/#[0-9A-Fa-f]{6}/g) || []).forEach((h, i) => { out[`CATEGORICAL[${i}]`] = h; });
  return out;
}
const TOKENS = tokenColours();

// Named colours a text position may use: `const X = "#..."` or `const X = T.y` (or a data colour)
// in any file of this folder, and the tokens themselves.
function namedColours() {
  const out = { ...TOKENS };
  FILES.forEach((f) => {
    const src = stripComments(read(f));
    const re = /(?:const|export const)\s+([A-Z_][A-Z0-9_]*)\s*=\s*"(#[0-9A-Fa-f]{3,8})"/g;
    let m = re.exec(src);
    while (m) { out[m[1]] = m[2]; m = re.exec(src); }
    const alias = /(?:const|export const)\s+([A-Z_][A-Z0-9_]*)\s*=\s*((?:T|PAIN|SIDE)\.[a-zA-Z0-9]+|CONTEXT|CATEGORICAL\[\d\])\s*;/g;
    let a = alias.exec(src);
    while (a) { if (TOKENS[a[2]]) out[a[1]] = TOKENS[a[2]]; a = alias.exec(src); }
  });
  // `import { BIN_MID as MID } from "./binarizationModel"`: the alias names the same colour.
  FILES.forEach((f) => {
    const src = stripComments(read(f));
    const re = /\b([A-Z_][A-Z0-9_]*)\s+as\s+([A-Z_][A-Z0-9_]*)\b/g;
    let m = re.exec(src);
    while (m) { if (out[m[1]] && !out[m[2]]) out[m[2]] = out[m[1]]; m = re.exec(src); }
  });
  return out;
}
const NAMED = namedColours();

/** The enclosing object's key for the `{` that opens the object a match sits in. */
function enclosingKey(src, idx) {
  let depth = 0;
  for (let i = idx - 1; i >= 0; i -= 1) {
    const ch = src[i];
    if (ch === "}") depth += 1;
    else if (ch === "{") {
      if (depth === 0) {
        const before = src.slice(Math.max(0, i - 40), i);
        const k = before.match(/([A-Za-z_$]+|"[^"]*"|'[^']*')\s*[:=]\s*\{?\s*$/);
        return k ? k[1].trim().replace(/^["']|["']$/g, "") : "";
      }
      depth -= 1;
    }
  }
  return "";
}
const NON_TEXT_TAGS = ["Slider", "LinearProgress", "CircularProgress"];
const TEXT_KEYS = /^(font|tickfont|titlefont|sx|style|& \.Mui[A-Za-z-]+|&:hover)$/;

/** Every resolvable colour in a text position under 4.5:1 on white, with its contrast. Named
 *  `textGreys` since decision 304; since 2026-09-26 it judges every colour, grey or not. */
export function textGreys(src, file = "") {
  const code = stripComments(src);
  const out = [];
  const push = (hex, where) => {
    // White (or near-white) text sits on a coloured fill of its own (a badge), never on the page.
    if (!hex || !rgbOf(hex) || luminance(rgbOf(hex)) > 0.9) return;
    const c = contrastOnWhite(hex);
    if (c != null && c < 4.5) out.push(`${file}: ${where} ${hex} (${c.toFixed(2)}:1)`);
  };
  // (1) object properties: `color: "#hex"`, `color: NAME`, `color: T.x`, `color: PAIN.x`
  const re = /\bcolor:\s*(?:"(#[0-9A-Fa-f]{3,8})"|'(#[0-9A-Fa-f]{3,8})'|((?:T|PAIN|SIDE)\.[a-zA-Z0-9]+|CATEGORICAL\[\d\])|([A-Z_][A-Z0-9_]*)\b)/g;
  let m = re.exec(code);
  while (m) {
    const key = enclosingKey(code, m.index);
    // `color` in the sx of a slider or a progress bar is the colour of its track, not of any text.
    const tags = code.slice(0, m.index).match(/<([A-Z][A-Za-z]*)\b/g) || [];
    const tag = key === "sx" && tags.length ? tags[tags.length - 1].slice(1) : "";
    if (TEXT_KEYS.test(key) && !NON_TEXT_TAGS.includes(tag)) {
      push(m[1] || m[2] || NAMED[m[3]] || NAMED[m[4]], `${key}.color`);
    }
    m = re.exec(code);
  }
  // (2) inline HTML styles inside strings: `color:#bbb`
  const html = /color:\s*(#[0-9A-Fa-f]{3,8})\b/g;
  m = html.exec(code);
  while (m) { push(m[1], "inline style"); m = html.exec(code); }
  // (3) SVG text: <text ... fill="#hex">
  const svg = /<text\b[^>]*\bfill=\{?"(#[0-9A-Fa-f]{3,8})"/g;
  m = svg.exec(code);
  while (m) { push(m[1], "svg text fill"); m = svg.exec(code); }
  return out;
}

/** Every literal hex colour outside a comment. */
export function literalHexes(src, file = "") {
  return (stripComments(src).match(/["'`(:\s]#[0-9A-Fa-f]{3,8}\b/g) || []).map((h) => `${file}: ${h.trim()}`);
}

/** Every text or figure font size under `floor` px (11 by default, the floor of decision 304). */
export function smallSizes(src, file = "", floor = 11) {
  const code = stripComments(src);
  const out = [];
  const pats = [
    /fontSize:\s*(\d+(?:\.\d+)?)(?![\d.])/g,                          // sx / style
    /(?:font|tickfont|titlefont):\s*\{[^{}]*?\bsize:\s*(\d+(?:\.\d+)?)/g, // Plotly font objects
    /fontSize="(\d+(?:\.\d+)?)"/g,                                     // SVG
    /font-size:\s*(\d+(?:\.\d+)?)px/g,                                 // inline HTML
  ];
  pats.forEach((re) => {
    let m = re.exec(code);
    while (m) { if (Number(m[1]) < floor) out.push(`${file}: ${m[0].replace(/\s+/g, " ").slice(0, 60)}`); m = re.exec(code); }
  });
  const tern = /fontSize:\s*[^,}\n]*?\?\s*(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)/g;
  let m = tern.exec(code);
  while (m) {
    [m[1], m[2]].forEach((v) => { if (Number(v) < floor) out.push(`${file}: ${m[0]}`); });
    m = tern.exec(code);
  }
  return out;
}

// The acquisition timeline's two files: their fonts change only through bravo-timeline-layout.
const TIMELINE_FILES = ["BiomarkerDataTimeline.js", "timelineGutter.js"];

describe("the Biomarkers page's legibility floor (decision 304; the redesign of 2026-09-26)", () => {
  test("no text or figure font is set below 12 px (the timeline's own files: below 11 px)", () => {
    expect(FILES.flatMap((f) => smallSizes(read(f), f, TIMELINE_FILES.includes(f) ? 11 : 12))).toEqual([]);
  });

  test("no page file writes a hex colour of its own: every colour comes from the shared tokens", () => {
    expect(FILES.flatMap((f) => literalHexes(read(f), f))).toEqual([]);
  });

  test("every text colour on the page, grey or not, is 4.5:1 or more on white", () => {
    expect(FILES.flatMap((f) => textGreys(read(f), f))).toEqual([]);
  });

  test("the check resolves the shared tokens it judges (so a token cannot slip past it)", () => {
    expect(NAMED["T.ink3"]).toBe("#5E5E5E");
    expect(NAMED["PAIN.high"]).toBe("#D55E00");
    expect(NAMED["SIDE.right"]).toBe("#E69F00");
    expect(textGreys("const a = <span style={{ color: PAIN.high }}>x</span>;")).toHaveLength(1);
    expect(textGreys("const a = <span style={{ color: SIDE.right }}>x</span>;")).toHaveLength(1);
    expect(textGreys("const a = <span style={{ color: T.ink3 }}>x</span>;")).toEqual([]);
  });

  test("the page takes its text colours from the tokens, with no darker-text wrapper of its own", () => {
    // CHANGED ON PURPOSE (SPEC.md section 2.2): the theme's text colour is now the token ink, so the
    // page no longer wraps itself in `LegibleText` (a file WP7 deletes).
    const idx = read("index.js");
    expect(idx).not.toMatch(/legibleText|<LegibleText>/);
    expect(idx).toMatch(/from "assets\/theme\/base\/tokens"/);
  });

  test("the timeline's gutter geometry is untouched by this pass (bravo-timeline-layout)", () => {
    // the column arithmetic moved into its own file on 2026-09-26 (timelineGutter.js), values unchanged
    const tl = read("timelineGutter.js");
    expect(tl).toMatch(/const LBL_GAP = 12;/);
    expect(tl).toMatch(/const LEFT_CAP = 230;/);
    expect(tl).toMatch(/const F_TICK = 14;/);
    expect(tl).toMatch(/\{ fContact = 26, fRegion = 18 \}/);
    expect(read("BiomarkerDataTimeline.js")).toMatch(/gutterGeometry\(prettyChans\)/);
  });

  // ---- the "X Hz" labels on the acquisition timeline (the redesign of 2026-09-26) ------------
  // CHANGED ON PURPOSE (SPEC.md section 5.1 item 4 and section 7, WP3): lanes take the ordered
  // cividis scale, and a label is ink beside a small tick in its lane's colour, replacing decision
  // 304's rule that each label be a darker variant of its line's hue.
  test("the timeline colours its lanes by the ordered (cividis) scale, not a hand-written palette", () => {
    const tl = stripComments(read("BiomarkerDataTimeline.js"));
    expect(tl).toMatch(/SEQUENTIAL/);
    expect(tl).not.toMatch(/const FREQ_PALETTE = \{/);
    expect(tl).not.toMatch(/const FREQ_TEXT = \{/);
  });

  test("each frequency label is ink text beside a tick in its lane's own colour", () => {
    const tl = stripComments(read("BiomarkerDataTimeline.js"));
    expect(tl).not.toMatch(/font:\s*\{[^{}]*color:\s*freqColor\(/);
    expect(tl).toMatch(/font:\s*\{[^{}]*color:\s*freqTextColor\(/);
    expect(tl).toMatch(/function freqTextColor\(\) \{\s*return T\.ink;/);
    expect(tl).toMatch(/text: freqLabel\(c\)/);
    expect(tl).toMatch(/function freqLabel\(hz\) \{\s*return `<span style="color:\$\{freqColor\(hz\)\}">/);
    expect(contrastOnWhite(NAMED["T.ink"])).toBeGreaterThan(4.5);
  });

  test("the checks catch what they are for (negative control)", () => {
    const src = 'const a = { font: { size: 9.5, color: "#9AA0A6" } };\n'
      + 'const b = <span style={{ fontSize: 10.5, color: "#777" }}>x</span>;\n'
      + "const c = \"<span style='font-size:13px;color:#bbb'>LSB</span>\";\n"
      + 'const d = { marker: { size: 6, color: "#aaa" } }; // a data mark, not text\n'
      + 'const e = { tickfont: { size: 17 }, font: { size: 11, color: "#5E5E5E" } };\n'
      + 'const f = <text x="1" fill="#7A7A7A" fontSize="9">3</text>;';
    expect(smallSizes(src)).toHaveLength(3);
    expect(smallSizes(src, "", 12)).toHaveLength(4);
    expect(textGreys(src)).toHaveLength(4);
    expect(literalHexes(src)).toHaveLength(6);
    expect(literalHexes("// only a comment about #D55E00")).toEqual([]);
    expect(contrastOnWhite("#5E5E5E")).toBeGreaterThan(4.5);
    expect(contrastOnWhite("#7A7A7A")).toBeLessThan(4.5);
  });
});
