import ResearchDeploymentPanels from "./ResearchDeploymentPanels";
import { Card } from "@mui/material";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import MDButton from "components/MDButton";
import useDeploymentReport from "./useDeploymentReport";

const number = (value) => value == null || !Number.isFinite(Number(value)) ? "unavailable" : Number(value).toPrecision(3);
const text = (value) => value == null ? "unknown" : typeof value === "object" ? JSON.stringify(value) : String(value);
const VERDICTS = {
  blocked: "Device rules failed or unresolved",
  unsupported: "Evidence does not establish support",
  supported: "Retrospective evidence criteria met; research only",
};
const EDGES = { E1: "Amplitude → power", E2: "Power → pain", E3: "Amplitude → pain" };

function RuleRows({ title, rows }) {
  return rows.length > 0 && <MDBox mt={1}>
    <MDTypography variant="body2" fontWeight="bold">{title}</MDTypography>
    {rows.map((rule) => <MDTypography variant="body2" key={rule.rule_id} mt={0.5}>
      {rule.rule_id}: {rule.title} {rule.why} {text(rule.observed)} ({rule.source}, {rule.page})
    </MDTypography>)}
  </MDBox>;
}

export default function ResearchEvidencePanel({ participantUid, bandCandidate, requestParams, inputIdentity }) {
  const query = useDeploymentReport({ participantUid, bandCandidate, requestParams, inputIdentity });
  const result = query.raw;
  const busy = query.loading;
  const error = query.err ? "Research review could not be loaded. Retry to continue." : "";
  const run = query.recompute;
  const channel = bandCandidate && bandCandidate.contact;
  const center = bandCandidate && bandCandidate.center_freq_hz;
  const report = result || {};
  const manifest = report.manifest || {};
  const rules = report.eligibility || {};
  const coherence = report.coherence;
  const failures = rules.failures || [];
  const unknowns = rules.unknowns || [];
  const shortfalls = (rules.advisories || []).filter((rule) => rule.kind === "advisory_failed");
  const inputs = manifest.InputManifest || {};
  const mode = manifest.programmer_mode || {};
  const selectedBand = manifest.selected_band || {};
  const factProvenance = manifest.device_fact_provenance || {};
  const deviceFacts = Object.entries(manifest.device_facts || {}).filter(([key]) => !key.startsWith("_"));
  return (
    <Card><MDBox p={2}>
      <MDTypography variant="h6">Closed-loop evidence review</MDTypography>
      <MDTypography variant="body2">
        Review the selected band against approved neural spectra and cleaned daily surveys.
        This uses continuous survey values aggregated by setting epoch, separately from the binary biomarker classifier.
        Oura is not an input to this model. This review does not authorize device programming.
      </MDTypography>
      <MDButton size="small" color="info" variant="outlined" disabled={busy || !participantUid || !channel || center == null}
        onClick={run} sx={{ mt: 1 }}>{busy ? "Reviewing evidence…" : "Review selected band"}</MDButton>
      {!channel && <MDTypography variant="caption" display="block">Select and revalidate a band first.</MDTypography>}
      {error && <MDTypography variant="body2" role="alert">{error}</MDTypography>}
      {result && <MDBox mt={2}>
        <MDTypography variant="body2" role="status">{report.reason}</MDTypography>
        <MDTypography variant="body2">{report.readiness && report.readiness.reason}</MDTypography>
        {(report.historical_findings || []).map((finding) => <MDTypography key={finding.source_commit} variant="body2" mt={1}>
          Source finding: both previously nominated configurations were retired. {finding.reason}
          {" "}This is the source analysis finding, not a new result on this dataset.
        </MDTypography>)}
        {report.available && <>
          <ResearchDeploymentPanels data={report} bandCandidate={bandCandidate} />
          <details><summary>Detailed numeric evidence and source provenance</summary>
          <MDTypography variant="h6" mt={1}>{VERDICTS[report.verdict] || "Research disposition not established"}</MDTypography>
          <MDTypography variant="body2" mt={1}>
            Input: {manifest.n_approved_daily_pros} approved daily surveys; {manifest.n_outcome_epochs} outcome epochs;
            {" "}{manifest.n_table_rows} matched spectral-band observations. Outcome: {manifest.outcome}.
            Wash-in: {manifest.washin_s} seconds. Power scale: {text(manifest.power_scale)}.
            {" "}Candidate threshold mode: {text(selectedBand.threshold_mode || manifest.hypothetical_threshold_mode)} (hypothetical; not live programmer verification).
          </MDTypography>
          <MDTypography variant="body2" fontWeight="bold" mt={2}>Evidence triangle: amplitude → power → pain</MDTypography>
          <MDBox sx={{ overflowX: "auto", "& th, & td": { p: 1, textAlign: "left", verticalAlign: "top", fontSize: "0.9rem" } }}>
            <table aria-label="Closed-loop evidence triangle" style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead><tr>{["Association", "Estimate", "95% interval", "p", "Independent clusters", "Interpretation"].map((label) => <th key={label} scope="col">{label}</th>)}</tr></thead>
              <tbody>{Object.entries(report.edges || {}).map(([name, edge]) => <tr key={name}>
                <th scope="row">{name}: {EDGES[name]}<MDTypography variant="caption" display="block">{edge.note}</MDTypography></th>
                <td>{number(edge.estimate)}</td><td>{edge.ci ? edge.ci.map(number).join(" to ") : "unavailable"}</td>
                <td>{number(edge.p)}</td><td>{text(edge.n_clusters)} {edge.cluster_unit}</td>
                <td>{!edge.ci ? "Interval unavailable; see evidence note."
                  : edge.resolved ? "Interval excludes zero; retrospective association only." : "Direction unresolved."}</td>
              </tr>)}</tbody>
            </table>
          </MDBox>
          <MDTypography variant="body2" mt={1}>{manifest.inference}</MDTypography>
          <MDTypography variant="body2" mt={1}>
            Sign consistency: {coherence == null || coherence.coherent == null ? "not established"
              : coherence.coherent ? "coherent" : "not coherent"}. {coherence && coherence.note}
          </MDTypography>
          {(report.blockers || []).map((reason, i) => <MDTypography variant="body2" key={i}>{reason}</MDTypography>)}
          <MDTypography variant="body2" fontWeight="bold" mt={2}>
            Device rules: {rules.checked || 0} checked, {failures.length} failed, {unknowns.length} unknown.
          </MDTypography>
          <MDTypography variant="body2">{rules.eligible === true ? "All evaluated blocking rules pass; this is not programming authorization."
            : "Missing programmer values remain unresolved and do not count as passing."}</MDTypography>
          <RuleRows title="Blocking findings" rows={failures} />
          <RuleRows title="Unknown values — require verification" rows={unknowns} />
          <RuleRows title="Advisory shortfalls — reported, not blocking" rows={shortfalls} />
          <details><summary>Rule dependencies, device facts and source provenance</summary>
            <RuleRows title="Deferred duplicate findings — covered by their owning rule" rows={rules.deferred || []} />
            <MDTypography variant="body2" mt={1}>{manifest.device_fact_scope}</MDTypography>
            {deviceFacts.map(([key, value]) => <MDTypography variant="body2" key={key}>
              {key.replace(/_/g, " ")}: {text(value)}. {factProvenance[key]}
            </MDTypography>)}
            <MDTypography variant="body2" mt={1}>
              Programmer mode: {mode.programming_mode || "unknown"}. {mode.programming_mode_source}. {mode.programming_mode_status}
            </MDTypography>
            <MDTypography variant="body2" sx={{ overflowWrap: "anywhere" }}>
              Approved input fingerprint: {inputs.fingerprint}. Source code: {manifest.source_commit || inputs.prasad_source_commit}.
            </MDTypography>
            <MDTypography variant="body2">{manifest.spectral_sampling}</MDTypography>
            <MDTypography variant="body2">{manifest.settings_limitation}</MDTypography>
            <MDTypography variant="body2">{manifest.prospective_phases}</MDTypography>
          </details>
          </details>
        </>}
      </MDBox>}
    </MDBox></Card>
  );
}
