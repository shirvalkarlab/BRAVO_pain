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
import { TYPE, STATE } from "assets/theme/base/tokens";

/**
 * Which state each cell role draws in (SPEC 2026-09-26 section 2.3): a pass in the ink with ✓; a
 * failure in red with ✕ only on a track whose failure means the device refuses (`track.refusal`),
 * otherwise in the caution ink with ▲; an open question in grey with ○, never as a pass. The lit
 * cell carries its glyph and a tint; the others are drawn plain, so the shape and the words carry
 * the meaning without colour.
 */
function stateFor(role, refusal) {
  if (role === "pass") return STATE.pass;
  if (role === "fail") return refusal ? STATE.refused : STATE.caution;
  if (role === "warn") return STATE.caution;
  return STATE.notChecked;
}

export default function StateTrack({ track, data, showBlurb = true, dense = false }) {
  if (!track) return null;
  const cells = track.cells || [];
  const litIndex = typeof track.lit === "function" ? track.lit(data) : -1;
  const lit = cells[litIndex] || null;

  return (
    <MDBox>
      {track.label ? (
        <MDTypography variant="caption" sx={{ ...TYPE.caption, display: "block", fontWeight: 600,
          color: PAL.ink3, mb: 0.5 }}>
          {track.label}
        </MDTypography>
      ) : null}

      <MDBox display="flex" flexDirection="row" flexWrap="wrap" alignItems="stretch" role="list">
        {cells.map((c, i) => {
          const on = i === litIndex;
          const st = stateFor(c.role, !!track.refusal);
          return (
            <MDBox key={c.key} role="listitem" px={1.5} py={dense ? 0.5 : 0.75}
              data-lit={on ? "true" : "false"} aria-current={on ? "true" : undefined}
              sx={{
                border: `1px solid ${on ? st.ink : PAL.rule}`,
                marginLeft: i === 0 ? 0 : "-1px",
                position: "relative", zIndex: on ? 1 : 0,
                borderRadius: i === 0 ? "4px 0 0 4px" : (i === cells.length - 1 ? "0 4px 4px 0" : 0),
                backgroundColor: on ? st.tint : PAL.surface,
              }}>
              <MDTypography variant="caption" sx={{ ...TYPE.body, fontWeight: on ? 600 : 400,
                color: on ? st.ink : PAL.ink3 }}>
                {on ? <span aria-hidden="true" style={{ marginRight: 6 }}>{st.glyph}</span> : null}
                <span>{c.label}</span>
              </MDTypography>
            </MDBox>
          );
        })}
      </MDBox>

      {showBlurb && lit && lit.blurb ? (
        <MDTypography variant="caption" sx={{ ...TYPE.body, display: "block", mt: 1, color: PAL.ink2 }}>
          {lit.blurb}
        </MDTypography>
      ) : null}
    </MDBox>
  );
}
