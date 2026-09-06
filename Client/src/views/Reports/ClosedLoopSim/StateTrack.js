/**
 * A track of N labelled cells with exactly one filled — the renderer for every N-valued answer on
 * the Closed-Loop Deployment page.
 *
 * WHY ALL THE CELLS ARE DRAWN, including the ones that are not the current answer. A badge that
 * shows only the current state cannot tell a reader how many other states there were. That matters
 * most for the answer this component was built for: sign coherence returns true, false, or null,
 * and a reader who sees only the word "not coherent" has no way to know that "not established" was
 * also a possible answer and was not the one returned. Drawing the unlit cells puts the arity of
 * the question on the page, so the reader can see what was asked as well as what came back.
 *
 * WHY POSITION CARRIES THE ANSWER AS WELL AS FILL. The sign-off record prints, and it may print in
 * greyscale. The lit cell is identifiable by which position along the track is filled, so the
 * answer survives losing the colour entirely. The colour is a second, redundant encoding rather
 * than the only one.
 *
 * The role-to-ink mapping is deliberately narrow: a "not established" cell always takes the neutral
 * grey role and never the failure role. Grey says the question is still open; the failure ink says
 * an answer came back and it was bad. Painting an unanswered question red would tell a reader to
 * abandon a configuration that has not been assessed.
 */
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import PAL from "./palette";

const INK = { pass: PAL.pass, fail: PAL.fail, warn: PAL.warn, neutral: PAL.neutral };

// White text sits at 2.25:1 on the warn amber, which is below every WCAG threshold, so a warn-role
// cell takes near-black text instead. Keyed on the same role the fill is keyed on so the two can
// never disagree.
const ON_INK = (role) => (role === "warn" ? PAL.onWarn : "#FFFFFF");

export default function StateTrack({ track, data, showBlurb = true, dense = false }) {
  if (!track) return null;
  const cells = track.cells || [];
  const litIndex = typeof track.lit === "function" ? track.lit(data) : -1;
  const lit = cells[litIndex] || null;

  return (
    <MDBox>
      {track.label ? (
        <MDTypography variant="caption" sx={{ display: "block", fontSize: 10,
          fontWeight: "bold", letterSpacing: 0.4, color: "#8A8A8A", mb: 0.5 }}>
          {track.label.toUpperCase()}
        </MDTypography>
      ) : null}

      <MDBox display="flex" flexDirection="row" gap={0.5} flexWrap="wrap" alignItems="stretch">
        {cells.map((c, i) => {
          const on = i === litIndex;
          const ink = INK[c.role] || PAL.neutral;
          return (
            <MDBox key={c.key} px={dense ? 0.8 : 1.1} py={dense ? 0.25 : 0.5}
              sx={{
                borderRadius: "4px",
                border: `1.5px solid ${on ? ink : "rgba(0,0,0,0.18)"}`,
                backgroundColor: on ? ink : "transparent",
                minWidth: dense ? 0 : 64,
              }}>
              <MDTypography variant="caption" sx={{
                fontSize: dense ? 9.5 : 10.5,
                fontWeight: on ? 700 : 500,
                letterSpacing: 0.3,
                lineHeight: 1.2,
                color: on ? ON_INK(c.role) : "#9A9A9A",
              }}>
                {c.label}
              </MDTypography>
            </MDBox>
          );
        })}
      </MDBox>

      {showBlurb && lit && lit.blurb ? (
        <MDTypography variant="caption" sx={{ display: "block", fontSize: 11, mt: 0.6,
          color: "#4A4A4A" }}>
          {lit.blurb}
        </MDTypography>
      ) : null}
    </MDBox>
  );
}
