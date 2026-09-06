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
      display: "flex", flexDirection: "row", alignItems: "flex-start", gap: 1.5, flexWrap: "wrap", minWidth: 0,
    }}>
      <MDBox flex="1 1 240px" sx={{ minWidth: 0, overflowWrap: "anywhere" }}>
        <MDTypography variant="caption" sx={{
          fontSize: 12, fontWeight: "bold", letterSpacing: 0.4, color: ink,
        }}>
          {loading ? "UPDATING RESULTS" : stale ? "SHOWING THE LAST COMPLETED RUN" : computedAt ? "CURRENT COMPLETED RUN" : "NO COMPLETED RUN"}
          {title ? ` \u00B7 ${String(title).toUpperCase()}` : ""}
        </MDTypography>

        <MDTypography variant="caption" display="block" sx={{ fontSize: 13, color: "#555" }}>
          {loading
            ? "Checking saved results or running the analysis with the current settings."
            : computedAt
              ? `Computed ${whenText(computedAt)}. Switching views, hiding a plot or reopening a `
                + "panel reuses it after checking data and access."
              : "Nothing has been computed for this participant yet."}
        </MDTypography>

        {!loading && stale && reasons.length ? (
          <MDBox mt={0.6} component="ul" sx={{ pl: 2.2, my: 0 }}>
            {reasons.map((r) => (
              <MDTypography key={r} component="li" variant="caption" display="list-item"
                sx={{ fontSize: 12, color: PAL.warnText }}>
                {r}
              </MDTypography>
            ))}
          </MDBox>
        ) : null}

        {notKept ? (
          <MDTypography variant="caption" display="block"
            sx={{ fontSize: 12, color: PAL.warnText, mt: 0.4 }}>
            {`This result was not kept in memory: ${notKept}`}
          </MDTypography>
        ) : null}

        {extra || null}
      </MDBox>

      <MDBox flex="0 0 auto">
        <MDButton size="small" disabled={!!loading} onClick={onRecompute}
          variant={stale && !loading ? "contained" : "outlined"}
          color={stale && !loading ? "warning" : "secondary"}>
          {loading ? "Updating\u2026" : !computedAt ? "Run analysis" : stale ? "Recompute" : "Recompute anyway"}
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
