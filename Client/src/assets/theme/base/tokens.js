/**
 * The design tokens for the whole application: the one place a colour, a type size, a spacing
 * step, a radius or a shadow is written down. `colors.js`, `typography.js`, `borders.js`,
 * `boxShadows.js` and `globals.js` read from here, and page files import `T` (colours) and the
 * other named exports instead of writing a hex value of their own.
 *
 * Source: artifacts/design_2026-09-26_minimalist_redesign/SPEC.md section 2 ("a quiet clinical
 * instrument"). Every text colour below is at least 4.5:1 against white, the page background and
 * its own tint; `tokens.test.js` recomputes each ratio with the WCAG formula, so a value changed
 * here that falls below the minimum fails a test rather than a reader.
 *
 * Rules the values carry:
 *  - Red (`refused`) means one thing only: the device refuses, or a value is above the safe
 *    current ceiling. It always comes with the glyph ✕.
 *  - The meaning inks are always paired with their glyph (GLYPH below): red and blue are almost
 *    equally light, so colour alone never carries a meaning.
 *  - `rule` and `graphic` are for lines and marks only, never for text.
 *  - "not checked" is drawn in `ink3` with ○, never as a pass.
 */

export const T = {
  // Surfaces and lines (never text)
  surface: "#FFFFFF", // cards, figures
  page: "#FAFAF8", // window background
  fillMuted: "#F4F4F1", // table header band, fold rows, the selected table row
  rule: "#D9D9D6", // hairlines and dividers (1.41:1; not for text or a meaningful graphic)
  graphic: "#8A8A8A", // axis lines, interval bars, reference lines (3.45:1; never text)

  // Text inks
  ink: "#1A1A1A", // titles, answers, numbers, pass rows (with ✓)
  ink2: "#3D3D3D", // body prose
  ink3: "#5E5E5E", // captions, axis ticks and titles; the lightest text grey allowed

  // Meaning inks (text-safe) and their tints (bullet and row fills)
  accent: "#0B5CAD", // the decision answer, the one primary button, the selected tab or cell
  accentTint: "#EEF3FA",
  refused: "#B42318", // the device refuses; above the safe ceiling; blocks closed loop
  refusedTint: "#FBEFEE",
  caution: "#8A5A00", // needs more data; not yet certain; moves over time
  cautionTint: "#FBF5EA",
  notChecked: "#5E5E5E", // = ink3: a check that could not run (still blocks, counted apart)
  pass: "#1A1A1A", // = ink: passes. There is no green in page text.

  // Text-safe dark variants of two figure colours, for when a figure colour must appear as text
  vermillionText: "#A84300", // for #D55E00 (6.06:1 on white)
  bluishGreenText: "#00755A", // for #009E73 (5.69:1 on white)

  // White text on a filled accent or refused button
  onFill: "#FFFFFF",
};

/** The glyph that must accompany each meaning ink. */
export const GLYPH = {
  refused: "✕",
  caution: "▲",
  notChecked: "○",
  pass: "✓",
};

/** Which ink and tint each state draws in; one table so the pages cannot disagree. */
export const STATE = {
  refused: { ink: T.refused, tint: T.refusedTint, glyph: GLYPH.refused },
  caution: { ink: T.caution, tint: T.cautionTint, glyph: GLYPH.caution },
  notChecked: { ink: T.notChecked, tint: T.fillMuted, glyph: GLYPH.notChecked },
  pass: { ink: T.pass, tint: T.surface, glyph: GLYPH.pass },
};

/** One face, two weights. Numbers line up in columns (tabular figures, set on body). */
export const FONT_FAMILY = "'IBM Plex Sans', system-ui, sans-serif";
export const WEIGHT = { regular: 400, strong: 600 };

/**
 * The five type sizes, in px, with their line heights. No other size is used; the smallest is 12,
 * which keeps a margin above the 11 px minimum, and it applies to SVG and Plotly text as drawn.
 */
export const TYPE = {
  answer: { fontSize: 22, lineHeight: "29px", fontWeight: 600 }, // page status sentence
  title: { fontSize: 18, lineHeight: "25px", fontWeight: 600 }, // section title, as a question
  lead: { fontSize: 16, lineHeight: "24px", fontWeight: 400 }, // answer under a title; key numbers
  body: { fontSize: 14, lineHeight: "22px", fontWeight: 400 }, // body, controls, tables, folds
  caption: { fontSize: 12, lineHeight: "18px", fontWeight: 400 }, // caption, header, axis, tick
};

/** The smallest text size anywhere, in px. */
export const MIN_TEXT_PX = 12;

/** Spacing steps in px, and the MUI spacing factor for each (MUI's unit is 8 px). */
export const SPACE = { xxs: 4, xs: 8, sm: 16, md: 24, lg: 32, xl: 48, xxl: 64 };
export const SPACE_FACTOR = { xxs: 0.5, xs: 1, sm: 2, md: 3, lg: 4, xl: 6, xxl: 8 };

/** Layout: card padding, gaps, and the widths content may take. */
export const LAYOUT = {
  cardPadding: 24,
  cardPaddingWide: 32, // at 1280 px and wider
  betweenCards: 32,
  betweenSections: 64,
  titleToAnswer: 8,
  answerToFigure: 16,
  contentMax: 1120, // px, the content column
  proseMax: "68ch",
  phoneGutter: 16,
};

/** Corner radius in px: 4 for inputs, buttons and chips; 6 for cards. */
export const RADIUS = { none: 0, sm: 4, md: 6 };

/** Shadows: none on cards, bars and buttons; one soft shadow for menus, popovers and tooltips. */
export const SHADOW = { none: "none", overlay: "0 4px 16px rgba(0,0,0,.08)" };

/** A card: white, a 1 px rule border, no shadow. */
export const CARD = {
  background: T.surface,
  border: `1px solid ${T.rule}`,
  borderRadius: RADIUS.md,
  boxShadow: SHADOW.none,
};

/** The decision card alone carries a 4 px left bar: accent, or refused when the device refuses. */
export const decisionBar = (refused = false) => ({
  borderLeft: `4px solid ${refused ? T.refused : T.accent}`,
});

/** The pairs of (text, background) every text ink is used on, for the contrast test. */
export const TEXT_ON = {
  ink: [T.surface, T.page, T.fillMuted],
  ink2: [T.surface, T.page, T.fillMuted],
  ink3: [T.surface, T.page, T.fillMuted],
  accent: [T.surface, T.page, T.accentTint],
  refused: [T.surface, T.page, T.refusedTint],
  caution: [T.surface, T.page, T.cautionTint],
  notChecked: [T.surface, T.page, T.fillMuted],
  pass: [T.surface, T.page, T.fillMuted],
  vermillionText: [T.surface, T.page],
  bluishGreenText: [T.surface, T.page],
  onFill: [T.accent, T.refused],
};

/** WCAG 2 relative luminance and contrast ratio, for tests and for checking a pairing in code. */
export function relativeLuminance(hex) {
  const h = hex.replace("#", "");
  const full = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(full.slice(i, i + 2), 16) / 255)
    .map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrastRatio(a, b) {
  const [l1, l2] = [relativeLuminance(a), relativeLuminance(b)].sort((x, y) => y - x);
  return (l1 + 0.05) / (l2 + 0.05);
}

export default T;
