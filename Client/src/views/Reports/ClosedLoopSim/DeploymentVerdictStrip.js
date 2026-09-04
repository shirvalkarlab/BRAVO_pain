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

export default function DeploymentVerdictStrip({ bandCandidate, summary, deploymentReport }) {
  const bc = bandCandidate || {};
  // Consume the SHARED summary fetch lifted to the parent (no own /queryDeploymentSummary call).
  const { data, loading, err } = summary || { data: null, loading: false, err: null };

  // audit C8: readiness keys on NECESSARY gates, not the passed-count (mirrors DeploySignoffCard).
  const ready = data
    ? (data.ready_to_program != null ? !!data.ready_to_program : data.n_gates_passed === data.n_gates)
    : false;
  const th = data && data.threshold;
  // deployment_summary keeps threshold.available=False / upper_lsb=None for an ESTIMATED (modeled)
  // threshold and nests the modeled value under threshold.estimate.{estimated_upper_lsb,tier,
  // freq_extrapolated} — the same fail-closed split the sign-off card uses (a modeled value is never
  // surfaced as `available`/measured). Read the estimate from there so this strip matches what the
  // LSB panel shows for an unsensed-but-modelable band, instead of rendering "not deployable".
  const est = th && th.estimated && th.estimate ? th.estimate : null;

  // THE DEVICE VERDICT GATES THE NUMBER, added 2026-09-04. Until now this cell printed
  // `power ≥ N LSB` at nineteen-point type gated only on `thresholdShown`, which derives entirely
  // from /queryDeploymentSummary — the STATISTICAL gates. This component had no reference to the
  // device rules at all, so the Percept could forbid the configuration outright and the largest
  // number on the page would still be a value to program. For RCS08 that is the live state: rule
  // D19 fails because the band's power RISES with amplitude, which would close a positive-feedback
  // loop, and four further rules cannot be evaluated.
  //
  // The two endpoints answer different questions and both must clear. The summary asks where the
  // threshold goes and whether the statistical gates pass; the deployment report asks whether the
  // device would permit the configuration at all. A band can pass every gate in the first and be
  // undeployable in the second.
  //
  // SUPPRESSED RATHER THAN GREYED, deliberately. A greyed number is still a number, still legible,
  // and still the largest thing on the strip, and the failure mode being guarded against is a
  // number being on screen during a programming visit — a number in that position gets typed. The
  // reason and the count of what is withheld are printed in its place, so a reader knows something
  // exists and has been held back rather than being simply absent.
  const rep = deploymentReport && deploymentReport.data ? deploymentReport.data : deploymentReport;
  const vd = (rep && rep.verdict_detail) || {};
  // Fail closed: a report that has not loaded, or that carries no device answer, withholds. An
  // absent verdict is not permission.
  const deviceOk = !!(rep && rep.available && vd.device_eligible === true);
  const deviceBlocks = !deviceOk;
  const nFail = ((rep && rep.eligibility && rep.eligibility.failures) || []).length;
  const nUnknown = ((rep && rep.eligibility && rep.eligibility.unknowns) || []).length;

  const thresholdShown = !!(th && (th.available || est)) && !deviceBlocks;
  const estimated = !!est;                                 // modeled → ≈ + tier; measured → ≥
  const upperLsb = th && th.available ? th.upper_lsb : (est && est.estimated_upper_lsb);
  const estTier = est && est.tier;
  const estExtrap = est && est.freq_extrapolated;

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
            {deviceBlocks ? "THRESHOLD TO PROGRAM — WITHHELD" : "THRESHOLD TO PROGRAM"}
          </MDTypography>
          <MDTypography variant="h5" sx={{ fontSize: 19, lineHeight: 1.1,
            color: thresholdShown ? (estimated ? PAL.warnText : PAL.accent)
              : deviceBlocks ? PAL.warnText : PAL.neutral }}>
            {thresholdShown
              ? `power ${estimated ? "≈" : "≥"} ${fmt(upperLsb, 1)} LSB`
              : deviceBlocks ? "no value shown" : "— not deployable"}
          </MDTypography>
          {thresholdShown ? (
            <MDTypography variant="caption" display="block" sx={{ fontSize: 9, color: "#888" }}>
              {estimated
                ? `estimated (${estTier || "modeled"})${estExtrap ? " · extrapolated" : ""}`
                : `p${fmt(th.percentile, 0)} of device Timeline`}
            </MDTypography>
          ) : deviceBlocks ? (
            // Say WHY, and say that something is being held back rather than missing. A reader who
            // sees an empty cell looks for a bug; a reader who sees the reason goes to the rule
            // ledger, which is where the answer is.
            <MDTypography variant="caption" display="block"
              sx={{ fontSize: 9, color: PAL.warnText, maxWidth: 210 }}>
              {!rep || !rep.available
                ? "device rules not yet evaluated for this configuration"
                : `the device does not permit this configuration${
                    nFail ? ` — ${nFail} rule${nFail === 1 ? "" : "s"} violated` : ""}${
                    nUnknown ? `, ${nUnknown} cannot be evaluated` : ""}. See the device rules below.`}
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
