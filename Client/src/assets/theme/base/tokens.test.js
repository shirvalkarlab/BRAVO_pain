/**
 * The design tokens keep the two floors the pages rely on (SPEC.md section 7, WP1):
 * every text colour is at least 4.5:1 on white, on the page background and on its own tint,
 * and no type size anywhere in the theme is under 11 px (the scale's smallest is 12).
 * Ratios are recomputed here with the WCAG formula, never copied.
 */
import {
  T, TYPE, MIN_TEXT_PX, STATE, GLYPH, TEXT_ON, contrastRatio,
} from "assets/theme/base/tokens";
import typography from "assets/theme/base/typography";
import colors from "assets/theme/base/colors";
import { TEXT_VARIANT } from "assets/theme/base/dataColors";

const TEXT_TOKENS = ["ink", "ink2", "ink3", "accent", "refused", "caution", "notChecked", "pass"];
const TINT = { accent: T.accentTint, refused: T.refusedTint, caution: T.cautionTint,
  notChecked: T.fillMuted, ink: T.fillMuted, ink2: T.fillMuted, ink3: T.fillMuted,
  pass: T.fillMuted };

describe("text colours", () => {
  test.each(TEXT_TOKENS)("%s is at least 4.5:1 on surface, page and its tint", (name) => {
    const ink = T[name];
    [T.surface, T.page, TINT[name]].forEach((bg) => {
      expect(contrastRatio(ink, bg)).toBeGreaterThanOrEqual(4.5);
    });
  });

  test("every pairing listed for use as text is at least 4.5:1", () => {
    Object.entries(TEXT_ON).forEach(([name, bgs]) => {
      bgs.forEach((bg) => {
        const fg = name === "onFill" ? T.onFill : T[name];
        expect([name, bg, contrastRatio(fg, bg) >= 4.5]).toEqual([name, bg, true]);
      });
    });
  });

  test("the text-safe variants of figure colours are at least 4.5:1 on white and page", () => {
    Object.values(TEXT_VARIANT).forEach((c) => {
      expect(contrastRatio(c, T.surface)).toBeGreaterThanOrEqual(4.5);
      expect(contrastRatio(c, T.page)).toBeGreaterThanOrEqual(4.5);
    });
  });

  test("white text on the accent and refused fills is at least 4.5:1", () => {
    expect(contrastRatio("#FFFFFF", T.accent)).toBeGreaterThanOrEqual(4.5);
    expect(contrastRatio("#FFFFFF", T.refused)).toBeGreaterThanOrEqual(4.5);
  });

  test("the graphic grey meets the 3:1 minimum for a meaningful line, and is not a text ink", () => {
    expect(contrastRatio(T.graphic, T.surface)).toBeGreaterThanOrEqual(3);
    expect(contrastRatio(T.graphic, T.surface)).toBeLessThan(4.5);
  });

  test("the contrast formula reproduces the spec's recomputed ratios", () => {
    expect(contrastRatio(T.ink3, T.surface)).toBeCloseTo(6.48, 2);
    expect(contrastRatio(T.accent, T.surface)).toBeCloseTo(6.67, 2);
    expect(contrastRatio(T.refused, T.surface)).toBeCloseTo(6.57, 2);
    expect(contrastRatio(T.caution, T.surface)).toBeCloseTo(5.93, 2);
  });

  test("the theme's text colours are text-safe on white and page", () => {
    [colors.text.main, colors.dark.main, colors.secondary.main, colors.grey[600],
      colors.info.main, colors.error.main, colors.warning.main, colors.success.main]
      .forEach((c) => {
        expect([c, contrastRatio(c, T.surface) >= 4.5]).toEqual([c, true]);
        expect([c, contrastRatio(c, T.page) >= 4.5]).toEqual([c, true]);
      });
    Object.entries(colors.badgeColors).forEach(([name, b]) => {
      expect([name, contrastRatio(b.text, b.background) >= 4.5]).toEqual([name, true]);
    });
  });

  test("the deleted light greys are no longer theme text colours", () => {
    const text = [colors.text.main, colors.text.focus, colors.secondary.main, colors.grey[600]]
      .map((c) => c.toUpperCase());
    ["#7B809A", "#6C757D", "#ADB5BD"].forEach((c) => expect(text).not.toContain(c));
  });

  test("every state ink comes with its glyph", () => {
    Object.entries(STATE).forEach(([name, s]) => {
      expect(s.glyph).toBe(GLYPH[name]);
      expect(s.glyph.length).toBeGreaterThan(0);
    });
    expect(STATE.refused.glyph).toBe("✕");
    expect(STATE.notChecked.glyph).not.toBe(STATE.pass.glyph);
  });
});

const remToPx = (v) => {
  if (typeof v === "number") return v;
  const m = String(v).match(/^([\d.]+)(rem|px)$/);
  if (!m) return null;
  return m[2] === "rem" ? parseFloat(m[1]) * 16 : parseFloat(m[1]);
};

describe("type sizes", () => {
  test("the five sizes are 12, 14, 16, 18 and 22 px, none under the floor", () => {
    const sizes = Object.values(TYPE).map((r) => r.fontSize).sort((a, b) => a - b);
    expect(sizes).toEqual([12, 14, 16, 18, 22]);
    expect(MIN_TEXT_PX).toBe(12);
    sizes.forEach((s) => expect(s).toBeGreaterThanOrEqual(11));
  });

  test("no typography variant or size step is under 11 px", () => {
    const found = [];
    const walk = (obj, path) => {
      Object.entries(obj).forEach(([k, v]) => {
        if (v && typeof v === "object") walk(v, `${path}.${k}`);
        else if (k === "fontSize" || path.endsWith(".size")) found.push([`${path}.${k}`, remToPx(v)]);
      });
    };
    walk(typography, "typography");
    expect(found.length).toBeGreaterThan(10);
    found.forEach(([where, px]) => {
      expect([where, px !== null && px >= 11]).toEqual([where, true]);
    });
  });

  test("the removed sizes and weights are gone and the kept names still resolve", () => {
    // "xxs" is a kept name (MDBadge reads it); it no longer draws at 10.4 px but at 12.
    expect(typography.size.xxs).toBe("0.75rem");
    ["d1", "d2", "d3", "d4", "d5", "d6"].forEach((d) => expect(typography[d]).toBeUndefined());
    expect(typography.fontWeightLighter).toBeUndefined();
    expect(typography.fontWeightLight).toBe(400);
    expect(typography.fontWeightBold).toBe(600);
  });

  test("sentence case: no variant draws in uppercase", () => {
    Object.values(typography).forEach((v) => {
      if (v && typeof v === "object") expect(v.textTransform).not.toBe("uppercase");
    });
  });
});

describe("the light theme still builds from the tokens", () => {
  test("createTheme accepts the rewritten base files", () => {
    // eslint-disable-next-line global-require
    const theme = require("assets/theme").default;
    expect(theme.palette.background.default).toBe(T.page);
    expect(theme.typography.fontFamily).toMatch(/IBM Plex Sans/);
    expect(theme.boxShadows.md).toBe("none");
  });
});
