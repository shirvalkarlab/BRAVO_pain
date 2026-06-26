/**
 * Top-of-page verdict strip — audit finding #1 ("the answer is at the bottom").
 *
 * A clinician opening this view asks two questions immediately: (1) is this band ready to program,
 * and (2) what LSB threshold? Today both answers live only in the Deploy-to-Percept card at the
 * BOTTOM of a seven-section scroll. This sticky strip surfaces the SAME verdict + threshold at the
 * top, with jump-links to each section, so the headline is the first thing read, not the last.
 *
 * It reuses the IDENTICAL /api/queryDeploymentSummary call as the sign-off card (via
 * useDeploymentSummary), so the two can never disagree — same deterministic inputs, same payload.
 * No new analysis happens here; it is a second read of the one authoritative summary.
 */
import { Card, Icon } from "@mui/material";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import useDeploymentSummary from "./useDeploymentSummary";
import PAL from "./palette";

const fmt = (v, d = 2) => (v == null || !Number.isFinite(Number(v)) ? "—" : Number(v).toFixed(d));

// Anchor links to the panels below. IDs are set on the Grid items in index.js.
const JUMPS = [
  { id: "cl-roc", label: "ROC + cut-point" },
  { id: "cl-lsb", label: "LSB + power" },
  { id: "cl-era", label: "Per-era refit" },
  { id: "cl-signoff", label: "Sign-off ↓" },
];

function jumpTo(id) {
  const el = document.getElementById(id);
  if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
}

export default function DeploymentVerdictStrip({ participantUid, bandCandidate, requestParams, cutpoint }) {
  const bc = bandCandidate || {};
  const cutThr = cutpoint ? cutpoint.threshold : null;
  const matchDir = cutpoint ? cutpoint.matchDir : "prior";
  const { data, loading, err } = useDeploymentSummary({
    participantUid, channel: bc.contact, centerHz: bc.center_freq_hz,
    bandWidthHz: bc.bandwidth_hz || 5.0, matchDir, cutThr, requestParams,
  });

  // audit C8: readiness keys on NECESSARY gates, not the passed-count (mirrors DeploySignoffCard).
  const ready = data
    ? (data.ready_to_program != null ? !!data.ready_to_program : data.n_gates_passed === data.n_gates)
    : false;
  const th = data && data.threshold;
  const thresholdReady = th && th.available;
  // A modeled (estimated) threshold is shown distinctly from a measured one (≈ vs ≥).
  const estimated = th && th.estimated;

  const barColor = !data ? PAL.neutral : ready ? PAL.pass : PAL.warn;
  const barFill = !data ? "#6C757D10" : ready ? PAL.passFill : PAL.warnFill;
  const textColor = !data ? PAL.neutral : ready ? PAL.pass : PAL.warnText;

  return (
    // `cl-verdict-strip` is targeted by the @media print rule so the printed sheet starts here.
    <Card id="cl-verdict-strip" className="cl-verdict-strip"
      sx={{ width: "100%", position: "sticky", top: 8, zIndex: 5,
        border: `2px solid ${barColor}`, backgroundColor: barFill }}>
      <MDBox px={2} py={1.2} display="flex" flexDirection="row" alignItems="center"
        justifyContent="space-between" flexWrap="wrap" gap={1.5}>
        {/* LEFT: the verdict */}
        <MDBox display="flex" alignItems="center" gap={1.2} flex="1 1 280px">
          <Icon sx={{ fontSize: "30px !important", color: barColor }}>
            {!data ? "hourglass_empty" : ready ? "check_circle" : "report_problem"}
          </Icon>
          <MDBox>
            <MDTypography variant="h6" sx={{ fontSize: 16, lineHeight: 1.15, color: textColor }}>
              {loading ? "Assembling deployment verdict…"
                : err ? "Deployment verdict unavailable"
                  : ready ? "Ready to program — all required gates passed"
                    : (data && data.n_necessary != null
                      ? `Not ready — ${data.n_necessary_passed} of ${data.n_necessary} required gates passed`
                      : "Not ready — review caveats before programming")}
            </MDTypography>
            <MDTypography variant="caption" display="block" sx={{ fontSize: 11, color: "#666" }}>
              {data
                ? `${bc.contact_label || bc.contact || "band"} @ ${fmt(bc.center_freq_hz, 1)} Hz · `
                  + `${data.n_gates_passed}/${data.n_gates} gates`
                  + (data.n_gates_indeterminate ? ` · ${data.n_gates_indeterminate} not tested` : "")
                  + ` · ${data.verdict}`
                : err ? `${err} — pick a cut-point on the ROC panel below`
                  : "\u00A0"}
            </MDTypography>
          </MDBox>
        </MDBox>

        {/* MIDDLE: the threshold to program */}
        <MDBox textAlign="center" flex="0 0 auto" px={1.5}
          sx={{ borderLeft: "1px solid #ddd", borderRight: "1px solid #ddd" }}>
          <MDTypography variant="caption" sx={{ fontSize: 9, fontWeight: "bold", color: "#999",
            letterSpacing: 0.4 }}>
            THRESHOLD TO PROGRAM
          </MDTypography>
          <MDTypography variant="h5" sx={{ fontSize: 19, lineHeight: 1.1,
            color: thresholdReady ? (estimated ? PAL.warnText : PAL.accent) : PAL.neutral }}>
            {thresholdReady
              ? `power ${estimated ? "≈" : "≥"} ${fmt(th.upper_lsb, 1)} LSB`
              : "— not deployable"}
          </MDTypography>
          {thresholdReady ? (
            <MDTypography variant="caption" display="block" sx={{ fontSize: 9, color: "#888" }}>
              {estimated
                ? `estimated (${th.tier || "modeled"})${th.freq_extrapolated ? " · extrapolated" : ""}`
                : `p${fmt(th.percentile, 0)} of device Timeline`}
            </MDTypography>
          ) : null}
        </MDBox>

        {/* RIGHT: jump links (hidden in print) */}
        <MDBox className="cl-jumps" display="flex" flexDirection="row" gap={1} flexWrap="wrap"
          flex="0 1 auto" alignItems="center">
          {JUMPS.map((j) => (
            <MDTypography key={j.id} variant="caption" onClick={() => jumpTo(j.id)}
              sx={{ fontSize: 11, color: PAL.accent, cursor: "pointer", whiteSpace: "nowrap",
                "&:hover": { textDecoration: "underline" } }}>
              {j.label}
            </MDTypography>
          ))}
        </MDBox>
      </MDBox>
    </Card>
  );
}
