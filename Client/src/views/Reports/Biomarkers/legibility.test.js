/**
 * Legibility floor for the Biomarkers page (decision 304; the design review of 2026-09-26, B6).
 *
 * Decision 258 set the floor for the Closed-Loop and Stim Optimizer pages -- no text or figure font
 * under 11 px, no grey text under 4.5:1 on white -- and its test (`ClosedLoopSim/legibility.test.js`)
 * does not read this folder. The review counted 35 text sizes under 11 px across five files here
 * (the calibration panel 20, the binarization preview 5, the acquisition timeline 5, the older
 * timeline 3, the heat maps 2) and timeline text at 2.3 to 2.6:1 (`#aaa` tick numbers, `#9AA0A6`
 * "no ... data" notes, `#bbb` "LSB").
 *
 * This test is stricter than 258's in one respect: it does not list the forbidden greys, it computes
 * the contrast of every grey it finds in a text position (a font object, an `sx` or `style` object,
 * an inline HTML style, an SVG <text> fill), so a new light grey cannot slip past a list. A colour
 * with visible hue (the Okabe-Ito inks, the frequency colours) is not a grey and is not judged by that
 * check. The one place a frequency colour is TEXT -- the acquisition timeline's "X Hz" labels at each
 * change of sensing frequency -- has its own check below (the design review's B5, 2026-09-26): each
 * line hue is drawn as text through a darker variant of the same hue at 4.5:1 or more, and
 * neighbouring frequencies stay at least as far apart as the line colours themselves are.
 *
 * The acquisition timeline's left gutter is sized from its fonts (bravo-timeline-layout: `F_TICK`,
 * the contact and region fonts, `LBL_GAP`, `LEFT_CAP`); this test changes none of those, and the last
 * check pins them so a legibility pass cannot move the gutter by accident.
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
const isGrey = (hex) => { const rgb = rgbOf(hex); return !!rgb && Math.max(...rgb) - Math.min(...rgb) <= 24; };

// Named colours a text position may use: `const X = "#..."` in any file of this folder, and the
// shared palette's roles (`PAL.x`).
function namedColours() {
  const out = {};
  FILES.concat(["../ClosedLoopSim/palette.js", "../legibleText.js"]).forEach((f) => {
    const src = stripComments(read(f));
    const re = /(?:const|export const)\s+([A-Z_][A-Z0-9_]*)\s*=\s*"(#[0-9A-Fa-f]{3,8})"/g;
    let m = re.exec(src);
    while (m) { out[m[1]] = m[2]; m = re.exec(src); }
    const pal = /^\s+([a-zA-Z]+):\s*(?:OKABE_ITO\.([a-zA-Z]+)|"(#[0-9A-Fa-f]{3,8})")/gm;
    if (/palette\.js$/.test(f)) {
      const oi = {};
      const oiRe = /^\s+([a-zA-Z]+):\s*"(#[0-9A-Fa-f]{6})"/gm;
      const oiBlock = src.slice(src.indexOf("OKABE_ITO = {"), src.indexOf("};", src.indexOf("OKABE_ITO = {")));
      let o = oiRe.exec(oiBlock);
      while (o) { oi[o[1]] = o[2]; o = oiRe.exec(oiBlock); }
      const palBlock = src.slice(src.indexOf("export const PAL = {"));
      let p = pal.exec(palBlock);
      while (p) { out[`PAL.${p[1]}`] = p[3] || oi[p[2]]; p = pal.exec(palBlock); }
    }
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

/** Every grey in a text position, with its contrast. */
export function textGreys(src, file = "") {
  const code = stripComments(src);
  const out = [];
  const push = (hex, where) => {
    // White (or near-white) text sits on a coloured fill of its own (a badge), never on the page.
    if (!hex || !isGrey(hex) || luminance(rgbOf(hex)) > 0.9) return;
    const c = contrastOnWhite(hex);
    if (c != null && c < 4.5) out.push(`${file}: ${where} ${hex} (${c.toFixed(2)}:1)`);
  };
  // (1) object properties: `color: "#hex"`, `color: NAME`, `color: PAL.x`
  const re = /\bcolor:\s*(?:"(#[0-9A-Fa-f]{3,8})"|'(#[0-9A-Fa-f]{3,8})'|(PAL\.[a-zA-Z]+)|([A-Z_][A-Z0-9_]*)\b)/g;
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

/** Every text or figure font size under 11 px. */
export function smallSizes(src, file = "") {
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
    while (m) { if (Number(m[1]) < 11) out.push(`${file}: ${m[0].replace(/\s+/g, " ").slice(0, 60)}`); m = re.exec(code); }
  });
  const tern = /fontSize:\s*[^,}\n]*?\?\s*(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)/g;
  let m = tern.exec(code);
  while (m) {
    [m[1], m[2]].forEach((v) => { if (Number(v) < 11) out.push(`${file}: ${m[0]}`); });
    m = tern.exec(code);
  }
  return out;
}

describe("the Biomarkers page's legibility floor (decision 304)", () => {
  test("no text or figure font on the page is set below 11 px", () => {
    expect(FILES.flatMap((f) => smallSizes(read(f), f))).toEqual([]);
  });

  test("no grey text on the page is below 4.5:1 on white", () => {
    expect(FILES.flatMap((f) => textGreys(read(f), f))).toEqual([]);
  });

  test("the page wraps its content in the darker text colour, as the other two pages do", () => {
    expect(read("index.js")).toMatch(/<LegibleText>/);
  });

  test("the timeline's gutter geometry is untouched by this pass (bravo-timeline-layout)", () => {
    const tl = read("BiomarkerDataTimeline.js");
    expect(tl).toMatch(/const LBL_GAP = 12;/);
    expect(tl).toMatch(/const LEFT_CAP = 230;/);
    expect(tl).toMatch(/const F_TICK = 14;/);
    expect(tl).toMatch(/let F_CONTACT = 26, F_REGION = 18;/);
  });

  // ---- the frequency-coloured "X Hz" labels on the acquisition timeline (B5, 2026-09-26) --------
  function hexesIn(block) { return (block.match(/#[0-9A-Fa-f]{6}/g) || []).map((h) => h.toUpperCase()); }
  function freqTables() {
    const tl = stripComments(read("BiomarkerDataTimeline.js"));
    const grab = (name, open, close) => {
      const i = tl.indexOf(`const ${name} = ${open}`);
      return i < 0 ? null : tl.slice(i, tl.indexOf(close, i) + 1);
    };
    const pal = grab("FREQ_PALETTE", "{", "};");
    const byHz = {};
    (pal || "").replace(/(\d+(?:\.\d+)?):\s*"(#[0-9A-Fa-f]{6})"/g, (_, hz, h) => { byHz[Number(hz)] = h.toUpperCase(); });
    const text = {};
    (grab("FREQ_TEXT", "{", "};") || "").replace(/"(#[0-9A-Fa-f]{6})":\s*"(#[0-9A-Fa-f]{6})"/g,
      (_, a, b) => { text[a.toUpperCase()] = b.toUpperCase(); });
    return { tl, byHz, fallback: hexesIn(grab("FREQ_FALLBACK", "[", "];") || ""), text };
  }
  const srgbLin = (c) => { const x = c / 255; return x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4; };
  function oklab(hex) {
    const [r, g, b] = rgbOf(hex).map(srgbLin);
    const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
    const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
    const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
    return [0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
      1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
      0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s];
  }
  const deltaE = (a, b) => { const p = oklab(a); const q = oklab(b); return 100 * Math.hypot(p[0] - q[0], p[1] - q[1], p[2] - q[2]); };

  test("the timeline draws its frequency labels in a text colour, never the raw line colour", () => {
    const { tl } = freqTables();
    expect(tl).not.toMatch(/font:\s*\{[^{}]*color:\s*freqColor\(/);
    expect(tl).toMatch(/font:\s*\{[^{}]*color:\s*freqTextColor\(/);
  });

  test("every frequency label colour is 4.5:1 or more on white, in the same hue family as its line", () => {
    const { byHz, fallback, text } = freqTables();
    const lines = Array.from(new Set(Object.values(byHz).concat(fallback)));
    expect(lines.length).toBeGreaterThanOrEqual(24);
    const low = lines.map((h) => [h, text[h] || h]).filter(([, t]) => contrastOnWhite(t) < 4.5)
      .map(([h, t]) => `${h} -> ${t} (${contrastOnWhite(t).toFixed(2)}:1)`);
    expect(low).toEqual([]);
    // a darker variant, not a different colour: hue angle within 35 degrees of the line's
    const hue = (h) => { const [, a, b] = oklab(h); return Math.atan2(b, a) * 180 / Math.PI; };
    lines.forEach((h) => {
      const t = text[h] || h;
      const d = Math.abs(((hue(t) - hue(h)) + 540) % 360 - 180);
      expect([h, d <= 35]).toEqual([h, true]);
    });
  });

  test("neighbouring frequencies' labels stay at least as distinguishable as their lines", () => {
    const { byHz, text } = freqTables();
    const hz = Object.keys(byHz).map(Number).sort((a, b) => a - b);
    const lab = (f) => text[byHz[f]] || byHz[f];
    let worstLine = Infinity; let worstText = Infinity;
    for (let i = 1; i < hz.length; i += 1) {
      worstLine = Math.min(worstLine, deltaE(byHz[hz[i - 1]], byHz[hz[i]]));
      worstText = Math.min(worstText, deltaE(lab(hz[i - 1]), lab(hz[i])));
    }
    expect(worstText).toBeGreaterThanOrEqual(worstLine);
    expect(worstText).toBeGreaterThanOrEqual(9);
  });

  test("the checks catch what they are for (negative control)", () => {
    const src = 'const a = { font: { size: 9.5, color: "#9AA0A6" } };\n'
      + 'const b = <span style={{ fontSize: 10.5, color: "#777" }}>x</span>;\n'
      + "const c = \"<span style='font-size:13px;color:#bbb'>LSB</span>\";\n"
      + 'const d = { marker: { size: 6, color: "#aaa" } }; // a data mark, not text\n'
      + 'const e = { tickfont: { size: 17 }, font: { size: 11, color: "#5E5E5E" } };\n'
      + 'const f = <text x="1" fill="#7A7A7A" fontSize="9">3</text>;';
    expect(smallSizes(src)).toHaveLength(3);
    expect(textGreys(src)).toHaveLength(4);
    expect(contrastOnWhite("#5E5E5E")).toBeGreaterThan(4.5);
    expect(contrastOnWhite("#7A7A7A")).toBeLessThan(4.5);
  });
});
