/**
=========================================================
* Material Dashboard 2 React - v2.1.0
=========================================================

* Product Page: https://www.creative-tim.com/product/material-dashboard-react
* Copyright 2022 Creative Tim (https://www.creative-tim.com)

Coded by www.creative-tim.com

 =========================================================

* The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
*/

// Values come from the design tokens (SPEC.md section 2, 2026-09-26): the page background,
// body text in ink2, one typeface, and tabular figures so mA and device-unit columns line up.
//
// Added for the taste follow-up (TASTE_AUDIT.md section C, the PI's go-ahead of 2026-09-26):
//  C1  a visible keyboard focus ring (2 px accent outline, 2 px offset) on :focus-visible only;
//  C3  links inside sentences are underlined, so they are recognisable without colour (the
//      accent against body text is only 1.63:1). Navigation, buttons and jump-link rows stay
//      un-underlined: a jump-link row carries the class in `views/Reports/paper/links.js`;
//  C4  "reduce motion": smooth scrolling and every transition become instant (the fold arrow,
//      the side menu); spinners keep turning, since they say something is loading;
//  C5  prose breaks lines "pretty" (no lone last word);
//  C8  the icon font classes, now that Material Icons is self-hosted (assets/theme/fonts.js)
//      instead of loaded from Google, whose stylesheet used to define them.
import { T, FONT_FAMILY, FOCUS_RING, REDUCED_MOTION, WEIGHT } from "assets/theme/base/tokens";

/** The class a jump-link row (or a single jump link) carries to keep its links un-underlined. */
export const JUMP_ROW_CLASS = "paper-jump-row";
export const JUMP_LINK_CLASS = "paper-jump-link";

// Where a link counts as "inside a sentence".
const PROSE = ["p", "li", "td", "dd", "figcaption", "blockquote", ".paper-prose"];
const inProse = (suffix = "") => PROSE.map((c) => `${c} a${suffix}`).join(", ");

const iconFont = (family) => ({
  fontFamily: `'${family}'`,
  fontWeight: "normal",
  fontStyle: "normal",
  lineHeight: 1,
  letterSpacing: "normal",
  textTransform: "none",
  display: "inline-block",
  whiteSpace: "nowrap",
  wordWrap: "normal",
  direction: "ltr",
  fontFeatureSettings: "'liga'",
  WebkitFontSmoothing: "antialiased",
});

const globals = {
  html: {
    scrollBehavior: "smooth",
  },
  body: {
    backgroundColor: T.page,
    color: T.ink2,
    fontFamily: FONT_FAMILY,
    fontVariantNumeric: "tabular-nums",
  },
  "*, *::before, *::after": {
    margin: 0,
    padding: 0,
  },
  "p, li, dd, figcaption": {
    textWrap: "pretty",
  },
  // D6: one face in two weights. A <b> or <strong> would otherwise ask the browser for 700.
  "b, strong": { fontWeight: WEIGHT.strong },

  // C1: the focus ring, keyboard only.
  ":focus-visible": { ...FOCUS_RING },
  ":focus:not(:focus-visible)": { outline: "none" },
  // The main region is focused by the skip link; it is a landmark, not a control.
  "#main-content:focus": { outline: "none" },

  // C3: no underline by default (navigation, menus, buttons), underlined inside sentences.
  "a, a:link, a:visited": {
    textDecoration: "none",
  },
  [inProse()]: {
    textDecoration: "underline",
    textUnderlineOffset: "2px",
    textDecorationThickness: "1px",
  },
  [[
    `nav a`, `footer a`, `[role='navigation'] a`, `a.MuiButtonBase-root`, `a.MuiButton-root`,
    `.${JUMP_ROW_CLASS} a`, `a.${JUMP_LINK_CLASS}`,
  ].join(", ")]: {
    textDecoration: "none",
  },
  "a.link, .link, a.link:link, .link:link, a.link:visited, .link:visited": {
    color: `${T.ink} !important`,
    transition: "color 150ms ease-in !important",
  },
  "a.link:hover, .link:hover, a.link:focus, .link:focus": {
    color: `${T.accent} !important`,
  },

  // C8: the self-hosted icon fonts' classes (MUI's Icon uses "material-icons-round").
  ".material-icons": iconFont("Material Icons"),
  ".material-icons-round": iconFont("Material Icons Round"),

  // C4: readers who asked for less motion get none; nothing clinical is ever animated in.
  [REDUCED_MOTION]: {
    html: { scrollBehavior: "auto" },
    "*, *::before, *::after": {
      scrollBehavior: "auto !important",
      transitionDuration: "0s !important",
      transitionDelay: "0s !important",
    },
  },
};

export default globals;
