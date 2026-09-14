/**
 * The one type scale for the Stim Optimizer page, in pixels, so every component draws the same
 * sizes and nothing on the page is set below what a reader can read.
 *
 * Added 2026-09-12 after the PI read the redesigned page and found "text running into images"
 * and text too small ("make text larger where possible - wisely use white space"). The rules,
 * from that review: no rendered text under 11 px; body 13-14 px; section titles 16-18 px; the
 * page headline 18-20 px; numbers in the tabular font at least 13 px; nothing wraps inside a
 * number, a unit or a word; no text over a bar, a line or a point.
 */
import MDBox from "components/MDBox";

import Fold from "views/Reports/ClosedLoopSim/Fold";
import PAL from "views/Reports/ClosedLoopSim/palette";

export const TYPE = {
  headline: 19,   // the one sentence at the top of the page
  section: 17,    // a card's or section's title
  body: 13,       // prose and table rows
  small: 12,      // secondary lines: sub-lines under a value, footnotes, folded prose
  head: 11,       // column headers, uppercase
  axis: 11,       // axis tick labels inside an SVG chart
  numLarge: 16,   // the setting in force and the preferred setting
  num: 14,        // any other number a reader compares
  gain: 15,       // the gain beside its bar in the arms strip
};

/** Column header: uppercase, never breaks inside a word (it may wrap between words). */
export const HEAD = { fontSize: TYPE.head, fontWeight: 700, letterSpacing: 0.5, color: "#6E6E6E",
  textTransform: "uppercase", overflowWrap: "normal", wordBreak: "normal", lineHeight: 1.25 };
/** A number in the tabular font. */
export const MONO = { fontFamily: PAL.mono, fontSize: TYPE.num, color: "#1A1A1A", whiteSpace: "nowrap" };
/** A secondary line. */
export const SMALL = { fontSize: TYPE.small, color: "#5E5E5E", lineHeight: 1.35 };
/** A value with its unit, which must never be split across lines. */
export const NOWRAP = { whiteSpace: "nowrap" };

/**
 * The shared reveal control (`ClosedLoopSim/Fold`) draws its toggle at 10.5 or 11 px, which is
 * below this page's minimum. That file belongs to the Closed-Loop page and is not edited here;
 * the toggle is resized from outside instead, through a descendant rule on the wrapper. The
 * children are untouched.
 */
export function SizedFold({ size = TYPE.small, ...props }) {
  return (
    <MDBox sx={{ "& > div > button": { fontSize: `${size}px !important` },
      "& > div > button > span[aria-hidden]": { fontSize: `${TYPE.axis}px !important` } }}>
      <Fold {...props} />
    </MDBox>
  );
}

export default TYPE;
