/**
 * The matcher's shared-report warning (the PI, 2026-09-21, on decision 118's open question):
 * how many matched pain reports were claimed by more than one recording session in the
 * time-domain correlation. No cap is applied; the correlation's p-value groups on the
 * report, so the sharing is accounted for downstream. Reads
 * `summary.timedomain.report_sharing` off the module response; draws nothing when no report
 * is shared or the run used the same-day path.
 *
 * On screen: Biomarkers page, under "Biomarker computed against", after Compute.
 */
import MDTypography from "components/MDTypography";

import PAL from "views/Reports/ClosedLoopSim/palette";

export default function ReportSharingNote({ summary }) {
  const sh = summary && summary.timedomain && summary.timedomain.report_sharing;
  if (!sh || !sh.warning) return null;
  return (
    <MDTypography variant="caption" component="div" data-testid="report-sharing-warning"
      sx={{ color: PAL.warnText, fontStyle: "italic", display: "block", mt: 0.25 }}>
      {sh.warning}
    </MDTypography>
  );
}
