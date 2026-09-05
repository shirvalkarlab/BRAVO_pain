/**
 * The one-line staleness disclosure carried by each analyst panel.
 *
 * WHY A PANEL NEEDS ITS OWN NOTICE RATHER THAN RELYING ON THE PAGE'S RECOMPUTE CONTROL. Now that a
 * panel's answer is kept in the shared result cache, the panel can be showing a figure that was
 * computed for inputs that have since changed — a different match direction, a different operating
 * point, or a band candidate that has been replaced. The cache is explicit that it returns such a
 * result rather than discarding it, and that the caller must say so. The page's Recompute control
 * says it for the page as a whole, but a reader looking at one figure a long scroll below that
 * control cannot see it, and a receiver-operating-characteristic curve for the previous band would
 * look exactly like a curve for the current one.
 *
 * WHY IT IS NOT THE FULL RECOMPUTE CONTROL. `views/Reports/RecomputeBar` answers a question about
 * the whole page and is sized for the top of one. Repeating it inside five panels would put five
 * amber blocks on a page that already has one, and would invite a reader to press the one nearest
 * their thumb rather than the one that rebuilds what they are looking at. This is one sentence and
 * one text button, in the same caution amber, and it appears only when there is something to say.
 */
import PropTypes from "prop-types";
import React from "react";

import MDBox from "components/MDBox";
import MDButton from "components/MDButton";
import MDTypography from "components/MDTypography";

import PAL from "./palette";

export default function PanelStaleNote({ stale, staleReasons, loading, onRecompute, notKept }) {
  const reasons = staleReasons || [];
  // While a refetch is in flight the panel is already saying so in its own words, in the place it
  // has always said it. Adding a second sentence here would put two progress messages in one card,
  // so this notice stands down for the duration and returns when there is a result to qualify.
  if (loading) return null;
  if (!stale && !notKept) return null;

  return (
    <MDBox mb={0.8} p={0.8} sx={{ backgroundColor: PAL.warnFill, borderRadius: "5px",
      border: `1px solid ${PAL.warnBorder}`, display: "flex", flexDirection: "row",
      alignItems: "flex-start", gap: 1 }}>
      <MDBox flex="1 1 auto">
        {stale ? (
          <MDTypography variant="caption" display="block"
            sx={{ fontSize: 10, color: PAL.warnText }}>
            {"This figure is the last completed run for this panel. "}
            {reasons.length
              ? reasons.join(" ")
              : "Something it depends on has changed since it was computed."}
          </MDTypography>
        ) : null}
        {notKept ? (
          <MDTypography variant="caption" display="block"
            sx={{ fontSize: 9.5, color: PAL.warnText }}>
            {`This panel's result was not kept in memory: ${notKept}`}
          </MDTypography>
        ) : null}
      </MDBox>
      {stale && onRecompute ? (
        <MDBox flex="0 0 auto">
          <MDButton size="small" variant="text" color="warning" onClick={onRecompute}
            sx={{ textTransform: "none", fontSize: 10.5, minHeight: 0, py: 0.2 }}>
            Recompute this panel
          </MDButton>
        </MDBox>
      ) : null}
    </MDBox>
  );
}

PanelStaleNote.propTypes = {
  stale: PropTypes.bool,
  staleReasons: PropTypes.arrayOf(PropTypes.string),
  loading: PropTypes.bool,
  onRecompute: PropTypes.func,
  notKept: PropTypes.string,
};

PanelStaleNote.defaultProps = {
  stale: false, staleReasons: [], loading: false, onRecompute: null, notKept: null,
};
