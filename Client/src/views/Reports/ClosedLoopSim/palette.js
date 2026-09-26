/**
 * The Closed-Loop page's named colour roles, now read from the shared design tokens.
 *
 * Rewritten 2026-09-26 for the minimalist redesign (artifacts/design_2026-09-26_minimalist_redesign/
 * SPEC.md sections 2 and 7, WP6). Until then this file held its own Okabe-Ito hexes; it now
 * RE-EXPORTS the tokens (`assets/theme/base/tokens.js`) and the data colours
 * (`assets/theme/base/dataColors.js`), so no page file holds a hex value of its own. The role names
 * are kept because the Stim Optimizer, Biomarkers and recompute-bar files import them too.
 *
 * What each role now means (SPEC section 2.3):
 *  - `pass` is the ink (#1A1A1A) and always comes with ✓: there is no green in page text.
 *  - `fail` is the refused red (#B42318) and always comes with ✕. Red means one thing only: the
 *    device refuses, or a value is above the safe current ceiling.
 *  - `warn` / `warnText` are the caution ink (#8A5A00), always with ▲.
 *  - `neutral` / `indeterminate` are the lightest text grey (#5E5E5E), with ○ for "not checked".
 *  - `accent` is the one accent blue (#0B5CAD): the decision answer, the primary button, the
 *    selected tab or cell, links. It is NOT a chart series colour; figures use `series` (the left
 *    side's blue) and the other data colours below.
 *
 * `legibility.test.js` rejects `PAL.fail`, `PAL.pass` and `PAL.warn` as text colours in this folder:
 * text uses `PAL.failText`, `PAL.passText`, `PAL.warnText` or a token ink.
 */
import { T, FONT_FAMILY, TYPE } from "assets/theme/base/tokens";
import { CATEGORICAL, SIDE, PAIN, CONTEXT, SEQUENTIAL, DIVERGING as DIV } from "assets/theme/base/dataColors";
import { PLOTLY_CONFIG_WITH_TOOLBAR } from "views/Reports/figureStyle";

export { T } from "assets/theme/base/tokens";
export { SIDE, PAIN, CONTEXT, DIVERGING, TEXT_VARIANT } from "assets/theme/base/dataColors";

// The data colours by name (marks and fills only; never text).
export const OKABE_ITO = {
  blue: CATEGORICAL[0],
  orange: CATEGORICAL[1],
  bluishGreen: CATEGORICAL[2],
  reddishPurple: CATEGORICAL[3],
  skyBlue: CATEGORICAL[4],
  vermillion: CATEGORICAL[5],
  gray: CONTEXT,
};

/** A colour with an alpha suffix (two hex digits), for light fills of a token colour. */
const alpha = (hex, aa) => `${hex}${aa}`;

export const PAL = {
  // Interface
  accent: T.accent,
  series: SIDE.left, // the main data series in a figure (a mark colour, not text)

  // Decision axis. Text uses the *Text roles; the bare roles are glyph and mark fills.
  pass: T.pass,
  fail: T.refused,
  warn: T.caution,
  neutral: T.ink3,
  indeterminate: T.notChecked,
  passText: T.ink,
  failText: T.refused,
  warnText: T.caution,
  onWarn: T.onFill, // white text on a filled caution mark (5.93:1)
  onFill: T.onFill,

  // Plain inks, so no file writes a grey of its own
  ink: T.ink,
  ink2: T.ink2,
  ink3: T.ink3,
  rule: T.rule,
  graphic: T.graphic,
  surface: T.surface,
  fillMuted: T.fillMuted,

  // Cut-point marker on the ROC
  cutpoint: T.ink,
  cutpointDegenerate: T.caution,

  // Feature distribution: high pain vermillion, low pain blue (the shared pain colours)
  painHigh: PAIN.high,
  painLow: PAIN.low,
  painHighOutline: PAIN.high,
  thresholdLine: T.ink,

  // Light fills and borders for boxes
  accentFill: T.accentTint,
  accentBorder: T.rule,
  passFill: T.surface,
  passBorder: T.rule,
  warnFill: T.cautionTint,
  warnBorder: alpha(T.caution, "55"),
  neutralFill: T.fillMuted,
  neutralBorder: T.rule,
  failFill: T.refusedTint,
  failBorder: alpha(T.refused, "55"),

  // Provenance of a prescribed value (left edge of a row)
  originParticipant: T.accent,
  originManufacturer: null, // deliberately no ink: absence is the signal
  originClinician: T.caution,
  originNone: T.ink3,

  // A rule whose finding is counted under another rule: not blocking, drawn in grey
  deferred: T.ink3,
  deferredFill: T.fillMuted,
  deferredBorder: T.rule,

  // Band-power states (ordered): three steps of one ordered scale
  dutyBelow: SEQUENTIAL[5],
  dutyBetween: SEQUENTIAL[3],
  dutyAbove: SEQUENTIAL[0],

  // The hatch means "modelled or unconfirmed, not observed", and nothing else
  hatch: (ink, bg = "transparent") => `repeating-linear-gradient(45deg, ${ink} 0 2px, ${bg} 2px 5px)`,

  // One face everywhere; digits line up through tabular figures
  mono: FONT_FAMILY,

  // Plotly: the save-as-PNG/zoom/pan toolbar, restored by the PI on 2026-09-26 so reviewers can
  // save a figure for the deployment record (the redesign of SPEC section 3 had taken it off).
  MODEBAR: PLOTLY_CONFIG_WITH_TOOLBAR,
};

// The five type sizes in px (SPEC section 2.4); no other size is used on the page.
PAL.fs = {
  caption: TYPE.caption.fontSize, // 12: captions, table headers, axis titles, ticks
  body: TYPE.body.fontSize, // 14: body, controls, tables, fold text
  lead: TYPE.lead.fontSize, // 16: the answer under a title; key numbers
  title: TYPE.title.fontSize, // 18: section titles, written as questions
  answer: TYPE.answer.fontSize, // 22: the page's status sentence and the verdict
};
export const FS = PAL.fs;

// Stimulation state (off / low current / high current): one ordered scale, pooled in ink.
const ERA_COLORS = {
  OFF: CONTEXT,
  LOW: DIV[1][1],
  HIGH: SEQUENTIAL[0],
  Pooled: T.ink,
};
PAL.eraColor = (tag) => ERA_COLORS[tag] || T.ink;
PAL.ERA_COLORS = ERA_COLORS;
PAL.gray = CONTEXT;

export default PAL;
