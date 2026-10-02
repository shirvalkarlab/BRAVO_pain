/**
 * The taste follow-up in the theme (TASTE_AUDIT.md sections C and D; the PI's rulings of
 * 2026-09-26). Each test reads the style objects or the files themselves, so it checks the
 * values the browser will be given, not a screenshot.
 */
import fs from "fs";
import path from "path";

import {
  T, STATE, GLYPH, FOCUS_RING, WRAP, REDUCED_MOTION, FONT_FAMILY, WEIGHT,
  contrastRatio,
} from "assets/theme/base/tokens";
import globals, { JUMP_ROW_CLASS, JUMP_LINK_CLASS } from "assets/theme/base/globals";
import typography from "assets/theme/base/typography";
import colors from "assets/theme/base/colors";
import buttonRoot from "assets/theme/components/button/root";
import buttonBase from "assets/theme/components/buttonBase";
import iconButton from "assets/theme/components/iconButton";
import radio from "assets/theme/components/form/radio";
import checkbox from "assets/theme/components/form/checkbox";
import switchButton from "assets/theme/components/form/switchButton";
import stepLabel from "assets/theme/components/stepper/stepLabel";
import { FONT_STYLESHEETS } from "assets/theme/fonts";

const THEME_DIR = __dirname;
const CLIENT = path.join(__dirname, "..", "..", "..");
const walk = (dir) => fs.readdirSync(dir, { withFileTypes: true }).flatMap((d) => {
  const p = path.join(dir, d.name);
  return d.isDirectory() ? walk(p) : [p];
});
const themeSources = walk(THEME_DIR).filter((p) => p.endsWith(".js") && !p.endsWith(".test.js"));
const hexIn = (s) => (String(s).match(/#[0-9A-Fa-f]{6}\b/) || [null])[0];

describe("C1: a visible keyboard focus ring", () => {
  test("the ring is a 2 px accent outline 2 px outside, at least 3:1 on white and the page", () => {
    expect(FOCUS_RING).toEqual({ outline: `2px solid ${T.accent}`, outlineOffset: "2px" });
    expect(contrastRatio(T.accent, T.surface)).toBeGreaterThanOrEqual(3);
    expect(contrastRatio(T.accent, T.page)).toBeGreaterThanOrEqual(3);
  });

  test("it is drawn on keyboard focus only, globally and on every button", () => {
    expect(globals[":focus-visible"]).toEqual(FOCUS_RING);
    expect(globals[":focus:not(:focus-visible)"]).toEqual({ outline: "none" });
    const sel = "&:focus-visible, &.Mui-focusVisible";
    expect(buttonRoot[sel]).toEqual(FOCUS_RING);
    expect(buttonBase.styleOverrides.root[sel]).toEqual(FOCUS_RING);
    expect(iconButton.styleOverrides.root[sel]).toEqual(FOCUS_RING);
  });
});

describe("C3: links inside sentences are underlined; navigation and jump rows are not", () => {
  const entries = Object.entries(globals);
  const ruleFor = (selectorPart) => entries.find(([k]) => k.split(", ").includes(selectorPart));

  test("a link in a paragraph, list item or table cell is underlined", () => {
    ["p a", "li a", "td a"].forEach((sel) => {
      expect(ruleFor(sel)[1].textDecoration).toBe("underline");
    });
  });

  test("links in navigation, buttons and jump-link rows keep no underline, after the prose rule", () => {
    const keys = entries.map(([k]) => k);
    const prose = keys.findIndex((k) => k.split(", ").includes("p a"));
    ["nav a", `.${JUMP_ROW_CLASS} a`, `a.${JUMP_LINK_CLASS}`, "a.MuiButtonBase-root"].forEach((sel) => {
      const [key, rule] = ruleFor(sel);
      expect(rule.textDecoration).toBe("none");
      expect(keys.indexOf(key)).toBeGreaterThan(prose);
    });
  });

  test("the blanket 'no underline anywhere' rule is gone", () => {
    expect(globals["a, a:link, a:visited"].textDecoration).toBe("none");
    expect(JSON.stringify(globals)).not.toContain("none !important\",\"textUnderline");
    expect(globals["a, a:link, a:visited"].textDecoration).not.toContain("!important");
  });
});

describe("C4: reduced motion", () => {
  test("smooth scrolling and every transition become instant when the reader asks", () => {
    const rm = globals[REDUCED_MOTION];
    expect(REDUCED_MOTION).toBe("@media (prefers-reduced-motion: reduce)");
    expect(rm.html.scrollBehavior).toBe("auto");
    expect(rm["*, *::before, *::after"].transitionDuration).toBe("0s !important");
    expect(rm["*, *::before, *::after"].scrollBehavior).toBe("auto !important");
  });

  test("the side menu's drawer names the reduced-motion case itself", () => {
    const src = fs.readFileSync(path.join(CLIENT, "src/components/SideMenu/SidenavRoot.js"), "utf8");
    expect(src).toContain("[REDUCED_MOTION]: { transition: \"none !important\" }");
  });
});

describe("C5: balanced headings and pretty prose", () => {
  test("h1 to h6 balance their lines; body and subtitle text is pretty", () => {
    ["h1", "h2", "h3", "h4", "h5", "h6"].forEach((h) => {
      expect(typography[h].textWrap).toBe(WRAP.balance.textWrap);
    });
    ["body1", "body2", "subtitle1", "subtitle2"].forEach((v) => {
      expect(typography[v].textWrap).toBe(WRAP.pretty.textWrap);
    });
    expect(globals["p, li, dd, figcaption"].textWrap).toBe("pretty");
  });
});

describe("C8: self-hosted fonts", () => {
  test("each stylesheet resolves and every font file it names exists", () => {
    expect(FONT_STYLESHEETS).toEqual([
      "@fontsource/ibm-plex-sans/400.css", "@fontsource/ibm-plex-sans/600.css",
      "@fontsource/material-icons/400.css", "@fontsource/material-icons-round/400.css",
    ]);
    FONT_STYLESHEETS.forEach((sheet) => {
      const file = require.resolve(sheet);
      const css = fs.readFileSync(file, "utf8");
      const urls = Array.from(css.matchAll(/url\(([^)]+)\)/g)).map((m) => m[1]);
      expect(urls.length).toBeGreaterThan(0);
      urls.forEach((u) => expect(fs.existsSync(path.join(path.dirname(file), u))).toBe(true));
    });
  });

  test("only weights 400 and 600 of IBM Plex Sans are loaded", () => {
    const src = fs.readFileSync(path.join(THEME_DIR, "fonts.js"), "utf8");
    const weights = Array.from(src.matchAll(/ibm-plex-sans\/(\d+)\.css/g)).map((m) => m[1]);
    expect(Array.from(new Set(weights))).toEqual(["400", "600"]);
  });

  test("the app imports the fonts once, and the page loads nothing from Google Fonts", () => {
    const index = fs.readFileSync(path.join(CLIENT, "src/index.js"), "utf8");
    expect(index.match(/import "assets\/theme\/fonts";/g)).toHaveLength(1);
    const html = fs.readFileSync(path.join(CLIENT, "public/index.html"), "utf8");
    expect(html).not.toMatch(/fonts\.googleapis\.com|fonts\.gstatic\.com/);
  });

  test("the icon classes name the self-hosted icon faces", () => {
    expect(globals[".material-icons"].fontFamily).toBe("'Material Icons'");
    expect(globals[".material-icons-round"].fontFamily).toBe("'Material Icons Round'");
  });
});

describe("D3: control outlines at least 3:1; no text grey lighter than ink3", () => {
  test("input, radio, checkbox and switch outlines are at least 3:1 on white and the page", () => {
    const outlines = [
      colors.inputBorderColor,
      hexIn(radio.styleOverrides.root["& .MuiSvgIcon-root"].border),
      hexIn(checkbox.styleOverrides.root["& .MuiSvgIcon-root"].border),
      hexIn(switchButton.styleOverrides.thumb.border),
      hexIn(switchButton.styleOverrides.track.border),
    ];
    outlines.forEach((c) => {
      expect(c).toMatch(/^#/);
      expect(contrastRatio(c, T.surface)).toBeGreaterThanOrEqual(3);
      expect(contrastRatio(c, T.page)).toBeGreaterThanOrEqual(3);
    });
  });

  test("the theme's text greys are ink3 or darker", () => {
    [colors.text.main, colors.text.focus, colors.secondary.main, colors.grey[600],
      colors.grey[700], colors.grey[800], colors.grey[900]].forEach((c) => {
      expect(contrastRatio(c, T.surface)).toBeGreaterThanOrEqual(contrastRatio(T.ink3, T.surface));
    });
  });

  test("the stepper's labels are white on the accent fill, at least 4.5:1", () => {
    const label = stepLabel.styleOverrides.label;
    expect(hexIn(label.color)).toBe(T.onFill);
    expect(contrastRatio(T.onFill, T.accent)).toBeGreaterThanOrEqual(4.5);
  });
});

describe("D4: sentence case in the theme", () => {
  test.each(themeSources.map((p) => path.relative(THEME_DIR, p)))("%s sets no uppercase", (rel) => {
    const src = fs.readFileSync(path.join(THEME_DIR, rel), "utf8");
    expect(src).not.toMatch(/uppercase/i);
  });
});

describe("D6: one face, two weights", () => {
  test("the face is IBM Plex Sans first, in the theme and every typography variant", () => {
    expect(FONT_FAMILY.startsWith("'IBM Plex Sans'")).toBe(true);
    Object.values(typography).filter((v) => v && typeof v === "object" && v.fontFamily)
      .forEach((v) => expect(v.fontFamily).toBe(FONT_FAMILY));
  });

  test("no theme file names another face", () => {
    themeSources.forEach((p) => {
      expect([path.basename(p), /Roboto|Arial|Helvetica|Lato|SF Pro/.test(fs.readFileSync(p, "utf8"))])
        .toEqual([path.basename(p), false]);
    });
  });

  test("typography uses weights 400 and 600 only", () => {
    const weights = new Set();
    Object.entries(typography).forEach(([k, v]) => {
      if (k.startsWith("fontWeight")) weights.add(v);
      if (v && typeof v === "object" && v.fontWeight !== undefined) weights.add(v.fontWeight);
    });
    expect(Array.from(weights).sort()).toEqual([WEIGHT.regular, WEIGHT.strong]);
  });
});

describe("D14: red only for a device refusal or a value above the ceiling", () => {
  test("a statistical block is drawn in ink with the ✕ glyph, never red", () => {
    expect(STATE.blocked.ink).toBe(T.ink);
    expect(STATE.blocked.glyph).toBe(GLYPH.refused);
    expect(STATE.blocked.ink).not.toBe(T.refused);
    expect(STATE.refused.ink).toBe(T.refused);
  });

  test("the token comment states the PI's ruling", () => {
    const src = fs.readFileSync(path.join(THEME_DIR, "base", "tokens.js"), "utf8");
    expect(src).toContain("is only for a device refusal or a value above the safe current ceiling");
    expect(src).toContain("is drawn\n *    in `ink` with ✕, never in red (the PI's ruling of 2026-09-26)");
    expect(src).not.toContain("above the safe ceiling; blocks closed loop");
  });
});
