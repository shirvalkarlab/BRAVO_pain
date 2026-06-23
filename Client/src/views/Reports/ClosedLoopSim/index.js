/**
 * Closed-Loop Simulation / threshold-deployment view (DESIGN_biomarker_pipeline_v2 §8b — "Option 3").
 *
 * Consumes ONE validated BandCandidate (the §6 contract emitted by the discovery/Biomarkers view)
 * and walks it toward a device-implementable Percept RC controller spec. This Phase-A scaffold
 * loads the committed candidate (from localStorage or an uploaded JSON), renders an identity header
 * + the key mixed-effects evidence + a raw-schema inspector, and stands up placeholders for the
 * panels that later phases fill: ROC + cut-point (B), LSB conversion + power (C), per-era
 * cross-validation (D), and the Deploy-to-Percept sign-off card (E).
 */
import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { Card, Chip, Grid } from "@mui/material";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import MDButton from "components/MDButton";

import DatabaseLayout from "layouts/DatabaseLayout";

import {
  loadBandCandidate, clearBandCandidate, parseUploadedCandidate, commitBandCandidate,
} from "./bandCandidateStore";

const fmt = (v, d = 2) => (v == null || !Number.isFinite(Number(v)) ? "—" : Number(v).toFixed(d));
const fmtP = (p) => (p == null || !Number.isFinite(Number(p)) ? "—"
  : Number(p) < 0.001 ? Number(p).toExponential(1) : Number(p).toFixed(3));

// Verdict badge color, mirrors the discovery view's ValidationReadout palette.
function verdictColor(verdict) {
  const v = verdict || "";
  if (/VALIDATED \(stim-stable\)/.test(v)) return "#0a7f3f";
  if (/VALIDATED \(stim-dependent\)/.test(v)) return "#B17500";
  if (/failed/.test(v)) return "#9A3324";
  return "#6c757d";
}

// A labeled key/value row used across the identity + evidence blocks.
function KV({ label, children }) {
  return (
    <MDBox display="flex" flexDirection="row" alignItems="baseline" gap={1} mb={0.4}>
      <MDTypography variant="caption" sx={{ fontSize: 11, fontWeight: "bold", minWidth: 150,
        color: "#555" }}>{label}</MDTypography>
      <MDTypography variant="caption" sx={{ fontSize: 11.5 }}>{children}</MDTypography>
    </MDBox>
  );
}

// A placeholder card for a panel a later phase will build.
function PhasePlaceholder({ phase, title, blurb }) {
  return (
    <Card sx={{ width: "100%", border: "1px dashed #cfcfcf", backgroundColor: "#fafafa" }}>
      <MDBox p={2}>
        <MDBox display="flex" alignItems="center" gap={1} mb={0.5}>
          <Chip label={phase} size="small"
            sx={{ height: 18, fontSize: 10, backgroundColor: "#e9e9e9" }} />
          <MDTypography variant="h6" sx={{ fontSize: 14, color: "#777" }}>{title}</MDTypography>
        </MDBox>
        <MDTypography variant="caption" color="text" sx={{ fontSize: 11, fontStyle: "italic" }}>
          {blurb}
        </MDTypography>
      </MDBox>
    </Card>
  );
}

function BandCandidateIdentity({ bc, envelope }) {
  const ev = bc.evidence || {};
  const lbl = bc.label || {};
  const prov = bc.provenance || {};
  return (
    <Card sx={{ width: "100%" }}>
      <MDBox p={2}>
        <MDBox display="flex" alignItems="center" gap={1.2} mb={1} flexWrap="wrap">
          <MDBox px={1.4} py={0.4} sx={{ backgroundColor: verdictColor(bc.verdict), color: "white",
            borderRadius: "10px", fontSize: 11, fontWeight: "bold" }}>
            {bc.verdict || "—"}
          </MDBox>
          <MDTypography variant="h6" sx={{ fontSize: 16 }}>
            {`${bc.contact_label || bc.contact || "band"} @ ${fmt(bc.center_freq_hz, 1)} Hz`}
          </MDTypography>
          <Chip size="small" label={lbl.pro_metric_label || lbl.pro_metric || "metric"}
            sx={{ height: 20, fontSize: 11 }} />
          {bc.adaptive_valid
            ? <Chip size="small" color="success" label="adaptive-valid (8–30 Hz)"
                sx={{ height: 20, fontSize: 10.5 }} />
            : <Chip size="small" label="off adaptive band"
                sx={{ height: 20, fontSize: 10.5, backgroundColor: "#f1d9b5" }} />}
        </MDBox>

        <Grid container spacing={3}>
          <Grid item xs={12} md={6}>
            <MDTypography variant="caption" sx={{ fontSize: 10.5, fontWeight: "bold",
              letterSpacing: 0.4, color: "#999" }}>DEVICE IDENTITY</MDTypography>
            <MDBox mt={0.6}>
              <KV label="Hemisphere">{bc.hemisphere || "—"}</KV>
              <KV label="Contact (sensing)">{bc.contact || "—"}</KV>
              <KV label="Band">{`${fmt(bc.band_lo_hz, 1)} – ${fmt(bc.band_hi_hz, 1)} Hz (${fmt(bc.bandwidth_hz, 1)} Hz wide)`}</KV>
              <KV label="Center → FFT-snap">{`${fmt(bc.center_freq_hz, 2)} → ${fmt(bc.snapped_center_freq_hz, 2)} Hz`}</KV>
              <KV label="Polarity">{bc.polarity || "—"}</KV>
              <KV label="Suggested mode">
                {bc.suggested_mode || <span style={{ color: "#B17500" }}>none — see note</span>}
              </KV>
            </MDBox>
          </Grid>
          <Grid item xs={12} md={6}>
            <MDTypography variant="caption" sx={{ fontSize: 10.5, fontWeight: "bold",
              letterSpacing: 0.4, color: "#999" }}>MIXED-EFFECTS EVIDENCE</MDTypography>
            <MDBox mt={0.6}>
              <KV label="Odds ratio (per 1 SD)">
                {`${fmt(ev.odds_ratio)} `}
                {ev.or_lo != null && ev.or_hi != null ? `(95% CI ${fmt(ev.or_lo)}–${fmt(ev.or_hi)})` : ""}
                {ev.credible_ci === false
                  ? <span style={{ color: "#9A3324" }}> · narrow CI — re-bootstrap (Phase B)</span>
                  : ev.credible_ci === true
                    ? <span style={{ color: "#0a7f3f" }}> · credible</span> : null}
              </KV>
              <KV label="p (glmer)">{fmtP(ev.p_glmer)}</KV>
              <KV label="Samples / eras">{`${ev.n_matched_samples ?? "—"} samples · ${ev.n_clusters ?? "—"} weekly eras`}</KV>
              <KV label="Stim stability">
                {ev.stim_stable == null ? "—" : ev.stim_stable ? "stim-stable" : "stim-dependent"}
                {ev.stim_lrt_p != null ? ` (LRT p = ${fmtP(ev.stim_lrt_p)})` : ""}
              </KV>
              <KV label="Per-era OR">
                {ev.or_by_era
                  ? ["OFF", "LOW", "HIGH"].map((t) => `${t}: ${fmt(ev.or_by_era[t])}`).join("  ·  ")
                  : "—"}
              </KV>
              <KV label="Label / join">{`${lbl.pro_metric || "—"} · ${(lbl.binarization && lbl.binarization.strategy) || "—"} · ${lbl.join || "—"} · n+ ${lbl.n_pos_days ?? "—"} / n− ${lbl.n_neg_days ?? "—"}`}</KV>
            </MDBox>
          </Grid>
        </Grid>

        {/* Adaptive-mode caveat for off-band / negative-direction candidates. */}
        {(!bc.adaptive_valid || bc.suggested_mode == null) && bc.suggested_mode_reason ? (
          <MDBox mt={1} p={1} sx={{ backgroundColor: "#fff6e6", borderRadius: "6px" }}>
            <MDTypography variant="caption" sx={{ fontSize: 10.8, color: "#7a5200" }}>
              {`Deployment note: ${bc.suggested_mode_reason}.`}
              {bc.adaptive_valid_reason ? ` ${bc.adaptive_valid_reason}.` : ""}
            </MDTypography>
          </MDBox>
        ) : null}

        {/* Pool-bias honesty + committed-at provenance. */}
        <MDBox mt={1}>
          <MDTypography variant="caption" color="text" sx={{ fontSize: 10.3, fontStyle: "italic" }}>
            {prov.selection_biased ? "Selection-biased pool — " : ""}
            {prov.selection_note || ""}
            {envelope && envelope.committed_at ? ` · committed ${new Date(envelope.committed_at).toLocaleString()}` : ""}
          </MDTypography>
        </MDBox>
      </MDBox>
    </Card>
  );
}

function ClosedLoopSim() {
  const navigate = useNavigate();
  const { participant_uid } = useParams();
  const fileRef = useRef(null);

  const [envelope, setEnvelope] = useState(null);   // {band_candidate, participant_uid, committed_at}
  const [showJson, setShowJson] = useState(false);

  useEffect(() => {
    if (!participant_uid) { navigate("/database", { replace: false }); return; }
    setEnvelope(loadBandCandidate(participant_uid));
  }, [participant_uid, navigate]);

  const bc = envelope && envelope.band_candidate;

  const onUpload = (e) => {
    const file = e.target.files && e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const parsed = parseUploadedCandidate(String(reader.result));
      if (parsed && parsed.band_candidate) {
        // Persist the uploaded candidate under this participant so it survives navigation.
        commitBandCandidate(participant_uid, parsed.band_candidate);
        setEnvelope(loadBandCandidate(participant_uid));
      }
    };
    reader.readAsText(file);
    e.target.value = "";   // allow re-upload of the same file
  };

  return (
    <DatabaseLayout>
      <MDBox pt={3}>
        <Grid container spacing={2}>
          <Grid item xs={12}>
            <Card sx={{ width: "100%" }}>
              <MDBox p={2} display="flex" flexDirection="row" justifyContent="space-between"
                alignItems="center" flexWrap="wrap" gap={1}>
                <MDBox>
                  <MDTypography variant="h6" fontSize={22}>Closed-Loop Threshold Deployment</MDTypography>
                  <MDTypography variant="caption" color="text" sx={{ fontSize: 11.5 }}>
                    Percept RC controller spec from one validated BandCandidate.
                  </MDTypography>
                </MDBox>
                <MDBox display="flex" gap={1} alignItems="center">
                  <input ref={fileRef} type="file" accept="application/json,.json"
                    style={{ display: "none" }} onChange={onUpload} />
                  <MDButton size="small" variant="outlined" color="info"
                    onClick={() => fileRef.current && fileRef.current.click()}>
                    Load BandCandidate JSON
                  </MDButton>
                  {bc ? (
                    <MDButton size="small" variant="text" color="secondary"
                      onClick={() => { clearBandCandidate(participant_uid); setEnvelope(null); }}>
                      Clear
                    </MDButton>
                  ) : null}
                </MDBox>
              </MDBox>
            </Card>
          </Grid>

          {!bc ? (
            <Grid item xs={12}>
              <Card sx={{ width: "100%" }}>
                <MDBox p={3} textAlign="center">
                  <MDTypography variant="h6" sx={{ fontSize: 15, color: "#777" }}>
                    No band committed yet
                  </MDTypography>
                  <MDTypography variant="caption" color="text" display="block" mt={1} sx={{ fontSize: 12 }}>
                    Open the Biomarker Exploration view, click a VALIDATED band, and press
                    “Commit this band →”. It will appear here. Or load a previously downloaded
                    BandCandidate JSON.
                  </MDTypography>
                  <MDBox mt={2}>
                    <MDButton size="small" color="info" variant="gradient"
                      onClick={() => navigate(`/reports/biomarkers/${participant_uid}`)}>
                      Go to Biomarker Exploration
                    </MDButton>
                  </MDBox>
                </MDBox>
              </Card>
            </Grid>
          ) : (
            <>
              <Grid item xs={12}>
                <BandCandidateIdentity bc={bc} envelope={envelope} />
              </Grid>

              <Grid item xs={12} md={6}>
                <PhasePlaceholder phase="Phase B" title="Deployment ROC + cut-point search"
                  blurb="Rating-clustered AUC with bootstrap CI, plus a Youden / F1 / Net-Benefit cut-point selector drawn on the ROC and the high-vs-low band-power density." />
              </Grid>
              <Grid item xs={12} md={6}>
                <PhasePlaceholder phase="Phase C" title="LSB conversion + power / sample-size"
                  blurb="Cut-point in z-units, raw band power, and Timeline LSB (empirical µV²/LSB, confidence-rated), plus the 80%-power readout for whether more data is needed." />
              </Grid>
              <Grid item xs={12} md={6}>
                <PhasePlaceholder phase="Phase D" title="Per-era cross-validation"
                  blurb="ROC + cut-point refit per stim era (OFF / LOW / HIGH); flags divergence — the deployment-time analog of the stim-stability LRT." />
              </Grid>
              <Grid item xs={12} md={6}>
                <PhasePlaceholder phase="Phase E" title="Deploy-to-Percept sign-off card"
                  blurb="Read-only clinician summary: channel, band, cut-point in LSB, direction, expected sensitivity/specificity with CI, and deployment caveats." />
              </Grid>

              <Grid item xs={12}>
                <Card sx={{ width: "100%" }}>
                  <MDBox p={2}>
                    <MDBox display="flex" justifyContent="space-between" alignItems="center">
                      <MDTypography variant="h6" sx={{ fontSize: 13, color: "#777" }}>
                        BandCandidate schema (§6 contract)
                      </MDTypography>
                      <MDButton size="small" variant="text" color="info"
                        onClick={() => setShowJson((s) => !s)}>
                        {showJson ? "Hide JSON" : "Show JSON"}
                      </MDButton>
                    </MDBox>
                    {showJson ? (
                      <MDBox mt={1} p={1} sx={{ backgroundColor: "#1e1e1e", borderRadius: "6px",
                        maxHeight: 360, overflow: "auto" }}>
                        <pre style={{ margin: 0, color: "#d4d4d4", fontSize: 10.5,
                          fontFamily: "monospace", whiteSpace: "pre-wrap" }}>
                          {JSON.stringify(bc, null, 2)}
                        </pre>
                      </MDBox>
                    ) : null}
                  </MDBox>
                </Card>
              </Grid>
            </>
          )}
        </Grid>
      </MDBox>
    </DatabaseLayout>
  );
}

export default ClosedLoopSim;
