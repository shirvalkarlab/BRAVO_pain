/**
 * The Recompute control shared by the three analysis views.
 *
 * WHAT IT IS FOR. Now that results persist across navigation, a reader needs to be able to tell at
 * a glance whether what they are looking at reflects the settings currently on the page. This
 * control answers that in one place: it says when the result was computed, whether anything has
 * changed since, and what would change if they pressed the button.
 *
 * THE THREE APPEARANCES, and why the middle one is not the failure ink.
 *
 *   - CURRENT: an outlined button in the neutral ink, with the time the result was computed.
 *     Pressing it is allowed but pointless, and the caption says so, because a reader who does not
 *     know whether anything is stale will otherwise press it to be sure.
 *   - STALE: filled in the caution amber with every reason listed in full sentences. Amber rather
 *     than the failure vermillion is deliberate: nothing has failed and the numbers on screen are
 *     not wrong — they are answers to a question that is no longer the one being asked. Using the
 *     failure ink here would spend it on a state that needs no alarm, and would leave nothing
 *     distinct for a result that genuinely could not be computed.
 *   - RECOMPUTING: disabled, with the button reporting that it is running so a second press cannot
 *     queue a second identical request.
 *
 * The reasons are rendered as a list rather than summarised into a count, because "the settings
 * have changed" and "the server has restarted" call for different judgements about whether the
 * displayed numbers are still worth reading.
 */
import PropTypes from "prop-types";
import React from "react";

import MDBox from "components/MDBox";
import MDButton from "components/MDButton";
import MDTypography from "components/MDTypography";

import PAL from "views/Reports/ClosedLoopSim/palette";

function whenText(ts) {
  if (!ts) return null;
  const secs = Math.max(0, Math.round((Date.now() - ts) / 1000));
  if (secs < 45) return "a moment ago";
  if (secs < 5400) return `${Math.round(secs / 60)} min ago`;
  return new Date(ts).toLocaleString();
}

export default function RecomputeBar({
  title, stale, staleReasons, computedAt, loading, onRecompute, notKept, extra,
}) {
  const reasons = staleReasons || [];
  const ink = loading ? PAL.neutral : stale ? PAL.warnText : PAL.neutral;
  const fill = stale && !loading ? PAL.warnFill : "transparent";
  const border = loading ? PAL.neutral : stale ? PAL.warnText : "#ddd";

  return (
    <MDBox mb={1.5} p={1.2} sx={{
      borderRadius: "6px", backgroundColor: fill, border: `1px solid ${border}`,
      display: "flex", flexDirection: "row", alignItems: "flex-start", gap: 1.5,
    }}>
      <MDBox flex="1 1 auto">
        <MDTypography variant="caption" sx={{
          fontSize: 9.5, fontWeight: "bold", letterSpacing: 0.4, color: ink,
        }}>
          {loading ? "RECOMPUTING" : stale ? "SHOWING THE LAST COMPLETED RUN" : "UP TO DATE"}
          {title ? ` \u00B7 ${String(title).toUpperCase()}` : ""}
        </MDTypography>

        <MDTypography variant="caption" display="block" sx={{ fontSize: 10.5, color: "#555" }}>
          {loading
            ? "Running the analysis against the current settings."
            : computedAt
              ? `Computed ${whenText(computedAt)}. Switching views, hiding a plot or reopening a `
                + "panel will not recompute it."
              : "Nothing has been computed for this participant yet."}
        </MDTypography>

        {!loading && stale && reasons.length ? (
          <MDBox mt={0.6} component="ul" sx={{ pl: 2.2, my: 0 }}>
            {reasons.map((r) => (
              <MDTypography key={r} component="li" variant="caption" display="list-item"
                sx={{ fontSize: 10, color: PAL.warnText }}>
                {r}
              </MDTypography>
            ))}
          </MDBox>
        ) : null}

        {notKept ? (
          <MDTypography variant="caption" display="block"
            sx={{ fontSize: 9.5, color: PAL.warnText, mt: 0.4 }}>
            {`This result was not kept in memory: ${notKept}`}
          </MDTypography>
        ) : null}

        {extra || null}
      </MDBox>

      <MDBox flex="0 0 auto">
        <MDButton size="small" disabled={!!loading} onClick={onRecompute}
          variant={stale && !loading ? "contained" : "outlined"}
          color={stale && !loading ? "warning" : "secondary"}>
          {loading ? "Recomputing\u2026" : stale ? "Recompute" : "Recompute anyway"}
        </MDButton>
      </MDBox>
    </MDBox>
  );
}

RecomputeBar.propTypes = {
  title: PropTypes.string,
  stale: PropTypes.bool,
  staleReasons: PropTypes.arrayOf(PropTypes.string),
  computedAt: PropTypes.number,
  loading: PropTypes.bool,
  onRecompute: PropTypes.func.isRequired,
  notKept: PropTypes.string,
  extra: PropTypes.node,
};

RecomputeBar.defaultProps = {
  title: null, stale: false, staleReasons: [], computedAt: null, loading: false,
  notKept: null, extra: null,
};
