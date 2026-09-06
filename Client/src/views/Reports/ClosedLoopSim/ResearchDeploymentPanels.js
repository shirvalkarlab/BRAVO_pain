/** Latest Prasad evidence views over the canonical, research-only BRAVO payload. */
import { useState } from "react";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import DeploymentDecisionHeader from "./DeploymentDecisionHeader";
import DeviceRuleLedger from "./DeviceRuleLedger";
import EvidenceTrianglePanel from "./EvidenceTrianglePanel";
import PrescriptionPanel from "./PrescriptionPanel";
import DutyCyclePanel from "./DutyCyclePanel";
import WhatWouldChangeThis from "./WhatWouldChangeThis";

export default function ResearchDeploymentPanels({ data, bandCandidate }) {
  const [mode, setMode] = useState("dual");
  const report = { data, loading: false, err: null };
  return <MDBox sx={{ display: "grid", gap: 2, minWidth: 0, mt: 2 }}>
    <DeploymentDecisionHeader deploymentReport={report} bandCandidate={bandCandidate} />
    <MDBox id="cl-what-changes"><WhatWouldChangeThis report={report} /></MDBox>
    <MDBox id="cl-rules"><DeviceRuleLedger report={report} /></MDBox>
    <MDBox id="cl-evidence"><EvidenceTrianglePanel report={report} /></MDBox>
    <MDBox id="cl-prescription"><PrescriptionPanel report={report} mode={mode} onMode={setMode} /></MDBox>
    <MDBox id="cl-duty"><DutyCyclePanel report={report} mode={mode} /></MDBox>
    <MDBox><MDTypography variant="h6">Titration planning</MDTypography>
      <MDTypography variant="body2">{(data.planning && data.planning.reason)
        || "A participant-specific titration plan is unavailable in this research review."}</MDTypography>
    </MDBox>
  </MDBox>;
}
