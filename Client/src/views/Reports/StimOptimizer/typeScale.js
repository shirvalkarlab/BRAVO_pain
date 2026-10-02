/**
 * The Stim Optimizer page's type, inks and small shared pieces, all read from the one set of design
 * tokens (`assets/theme/base/tokens.js`, SPEC.md section 2). No file in this folder writes a hex
 * value or a font size of its own; it imports them from here.
 *
 * Written 2026-09-12 as the page's own type scale; re-based on the shared tokens on 2026-09-26 for
 * the minimalist redesign (SPEC.md sections 2.4 and 5.3). Five sizes only (12, 14, 16, 18, 22 px);
 * the smallest is 12, above the 11 px minimum. Headers are sentence case, 12 px, weight 600, the
 * lightest grey text allowed (`ink3`), never uppercase and never letter-spaced.
 *
 * The page's reveal control (`SizedFold`) lives here too, so the page no longer borrows the
 * Closed-Loop page's: one 14 px row, "▸ Label", whose content stays MOUNTED while closed (hidden
 * inside a collapsed MUI Collapse), so tests and search still read folded text.
 */
import { useState } from "react";
import { Collapse } from "@mui/material";

import MDBox from "components/MDBox";
import FoldArrow from "../paper/FoldArrow";

import {
  T, TYPE as TOKEN_TYPE, FONT_FAMILY, WEIGHT, STATE, GLYPH, SPACE, WRAP, RADIUS,
} from "assets/theme/base/tokens";

export { T, FONT_FAMILY, WEIGHT, STATE, GLYPH, SPACE, WRAP };

/** Sizes in px, by the role each plays on this page. Every value is one of the five token sizes. */
export const TYPE = {
  headline: TOKEN_TYPE.answer.fontSize,   // 22: the page's status sentence
  section: TOKEN_TYPE.title.fontSize,     // 18: a section's title, written as a question
  lead: TOKEN_TYPE.lead.fontSize,         // 16: the answer under a title
  body: TOKEN_TYPE.body.fontSize,         // 14: prose, table rows, fold rows
  small: TOKEN_TYPE.body.fontSize,        // 14: captions, secondary lines (the PI, 2026-10-02: no 12 px prose)
  head: TOKEN_TYPE.caption.fontSize,      // 12: column headers, sentence case
  axis: TOKEN_TYPE.caption.fontSize,      // 12: text inside a figure
  numLarge: TOKEN_TYPE.lead.fontSize,     // 16: the setting in force and the suggested setting
  num: TOKEN_TYPE.body.fontSize,          // 14: any other number a reader compares
  gain: TOKEN_TYPE.body.fontSize,         // 14: the gain beside its bar
};

/** Column header: 12 px, weight 600, `ink3`, sentence case (SPEC.md section 2.4). */
export const HEAD = { fontSize: TYPE.head, fontWeight: WEIGHT.strong, color: T.ink3,
  textTransform: "none", letterSpacing: 0, overflowWrap: "normal", wordBreak: "normal", lineHeight: 1.4 };
/** A number: the one face, figures that line up in columns. */
export const MONO = { fontFamily: FONT_FAMILY, fontVariantNumeric: "tabular-nums", fontSize: TYPE.num,
  color: T.ink, whiteSpace: "nowrap" };
/** A secondary line. */
export const SMALL = { fontSize: TYPE.small, color: T.ink3, lineHeight: 1.5 };
/** Body prose. */
export const BODY = { fontSize: TYPE.body, color: T.ink2, lineHeight: 1.57 };
/** A value with its unit, which must never be split across lines. */
export const NOWRAP = { whiteSpace: "nowrap" };
/** A sub-heading inside a section (a section's title is the 18 px question). */
export const SUBHEAD = { fontSize: TYPE.body, fontWeight: WEIGHT.strong, color: T.ink, lineHeight: 1.5 };
/** A heading inside a section: the sub-heading type, its lines broken evenly (TASTE_AUDIT.md C5). */
export const HEADING = { ...SUBHEAD, ...WRAP.balance };
/** A hairline between two parts of one section (never a box inside a box). */
export const HAIRLINE = `1px solid ${T.rule}`;

/**
 * A state glyph with its ink, for a reader and a screen reader alike: ✓ passes (ink), ✕ refused
 * by the device or above the ceiling (red, state "refused"), ✕ blocks on a statistical or evidence
 * result (ink, state "blocked"; the PI's ruling of 2026-09-26), ▲ needs more data or caution (amber), ○ not checked (grey). Colour never
 * carries the meaning alone; the glyph always does. `label` is what a screen reader hears.
 */
export function Mark({ state, label, size = TYPE.body }) {
  const s = STATE[state] || STATE.notChecked;
  return (
    <span role="img" aria-label={label} title={label || undefined}
      style={{ color: s.ink, fontSize: size, fontWeight: WEIGHT.strong, lineHeight: 1,
        display: "inline-block", minWidth: "1em", textAlign: "center" }}>
      {s.glyph}
    </span>
  );
}

/**
 * A still grey block standing in for a value that is still being computed (TASTE_AUDIT.md C2):
 * shaped like what will replace it, never animated, hidden from screen readers (the waiting words
 * beside it say what is happening).
 */
export function Placeholder({ width = 64, height = 14, mt = 0 }) {
  return (
    <span aria-hidden="true" data-testid="placeholder-block"
      style={{ display: "inline-block", width, maxWidth: "100%", height, marginTop: mt,
        background: T.rule, borderRadius: RADIUS.sm, verticalAlign: "middle" }} />
  );
}

/**
 * The fold: one 14 px row, "▸ Label", that opens to show its content. The content stays mounted
 * while closed. `show` names what is inside; `hide` is the row's words while open.
 */
export function SizedFold({ show, hide, defaultOpen = false, children, mt = 1, dense = false,
  onChange = null }) {
  const [open, setOpen] = useState(!!defaultOpen);
  const toggle = () => setOpen((o) => { const n = !o; if (onChange) onChange(n); return n; });
  return (
    <MDBox mt={mt}>
      <button type="button" onClick={toggle} aria-expanded={open}
        style={{ fontSize: TYPE.body, lineHeight: "22px", color: T.ink2, background: "none", border: 0,
          padding: 0, cursor: "pointer", fontFamily: "inherit", textAlign: "left",
          display: "inline-flex", gap: SPACE.xs, alignItems: "center" }}>
        <FoldArrow open={open} />
        <span>{open ? (hide || "Hide") : show}</span>
      </button>
      <Collapse in={open} unmountOnExit={false}>
        <MDBox mt={dense ? 0.5 : 1} sx={{ fontSize: TYPE.body, color: T.ink2 }}>{children}</MDBox>
      </Collapse>
    </MDBox>
  );
}

export default TYPE;
