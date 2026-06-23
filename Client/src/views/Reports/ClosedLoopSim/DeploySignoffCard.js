/**
 * Phase E: the read-only Deploy-to-Percept sign-off card.
 *
 * One authoritative fetch (/api/queryDeploymentSummary) → a clinician-facing review: device identity,
 * the deployable LSB threshold (big), the gate checklist they sign against, evidence with CI,
 * per-era portability, and the deployment caveats. Printable (window.print) and exportable to JSON
 * for the device-programming record. This is a SUMMARY, not a new analysis — every number here is
 * the same one the Phase B–D panels show, gathered in one place.
 */
import { useEffect, useState } from "react";

import { Card, Grid, Icon } from "@mui/material";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import MDButton from "components/MDButton";

import { SessionController } from "database/session-control";

const fmt = (v, d = 2) => (v == null || !Number.isFinite(Number(v)) ? "—" : Number(v).toFixed(d));

function GateRow({ gate }) {
  const ok = gate.pass;
  return (
    <MDBox display="flex" alignItems="flex-start" py={0.4}
      sx={{ borderBottom: "1px solid #f0f0f0" }}>
      <Icon sx={{ fontSize: "18px !important", color: ok ? "#0a7f3f" : "#9A3324", mr: 1, mt: 0.1 }}>
        {ok ? "check_circle" : "cancel"}
      </Icon>
      <MDBox flex={1}>
        <MDTypography variant="caption" sx={{ fontSize: 11.5, fontWeight: "bold",
          color: ok ? "#0a7f3f" : "#9A3324" }}>
          {gate.label}
        </MDTypography>
        <MDTypography variant="caption" display="block" sx={{ fontSize: 10, color: "#777" }}>
          {gate.detail}
        </MDTypography>
      </MDBox>
    </MDBox>
  );
}

function KV({ k, v }) {
  return (
    <MDBox display="flex" justifyContent="space-between" py={0.25}>
      <MDTypography variant="caption" sx={{ fontSize: 10.5, color: "#999" }}>{k}</MDTypography>
      <MDTypography variant="caption" sx={{ fontSize: 10.5, fontWeight: "bold", textAlign: "right" }}>{v}</MDTypography>
    </MDBox>
  );
}

function DeploySignoffCard({ participantUid, bandCandidate, requestParams, cutpoint }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);

  const bc = bandCandidate || {};
  const channelRaw = bc.contact;
  const centerHz = bc.center_freq_hz;
  const bandWidthHz = bc.bandwidth_hz || 5.0;
  const cutThr = cutpoint ? cutpoint.threshold : null;
  const matchDir = cutpoint ? cutpoint.matchDir : "prior";

  useEffect(() => {
    if (!participantUid || channelRaw == null || centerHz == null) return;
    setLoading(true); setErr(null);
    const body = {
      ParticipantId: participantUid, Channel: channelRaw, CenterHz: Number(centerHz),
      BandWidthHz: Number(bandWidthHz), MatchDirection: matchDir, ...requestParams,
    };
    if (cutThr != null) body.Cutpoint = Number(cutThr);
    SessionController.query("/api/queryDeploymentSummary", body).then((response) => {
      const d = response && response.data;
      if (d && d.available) setData(d);
      else { setData(null); setErr((d && d.reason) || "unavailable"); }
      setLoading(false);
    }).catch(() => { setData(null); setErr("request failed"); setLoading(false); });
  }, [participantUid, channelRaw, centerHz, bandWidthHz, matchDir, cutThr, requestParams]);

  const exportJson = () => {
    if (!data) return;
    const blob = new Blob([JSON.stringify({ schema_version: "deploy_signoff_v1",
      generated_at: new Date().toISOString(), summary: data }, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `DeploySignoff_${participantUid}_${channelRaw}_${centerHz}Hz.json`;
    a.click(); URL.revokeObjectURL(a.href);
  };

  const id = data && data.identity;
  const dc = data && data.device_control;
  const ev = data && data.evidence;
  const th = data && data.threshold;
  const pw = data && data.power;
  const allPass = data && data.n_gates_passed === data.n_gates;

  return (
    <Card sx={{ width: "100%", border: data ? `2px solid ${allPass ? "#0a7f3f" : "#B17500"}` : undefined }}>
      <MDBox p={2.5}>
        <MDBox display="flex" justifyContent="space-between" alignItems="center" mb={1}>
          <MDTypography variant="h5" sx={{ fontSize: 18 }}>Deploy-to-Percept review</MDTypography>
          {data ? (
            <MDBox>
              <MDButton size="small" variant="outlined" color="dark" onClick={() => window.print()} sx={{ mr: 1 }}>
                Print
              </MDButton>
              <MDButton size="small" variant="gradient" color="info" onClick={exportJson}>
                Export JSON
              </MDButton>
            </MDBox>
          ) : null}
        </MDBox>

        {loading ? (
          <MDTypography variant="caption" sx={{ fontStyle: "italic", fontSize: 11 }}>
            Assembling the deployment review…
          </MDTypography>
        ) : err ? (
          <MDTypography variant="caption" sx={{ fontSize: 11, color: "#9A3324" }}>{`Unavailable: ${err}.`}</MDTypography>
        ) : data ? (
          <>
            {/* headline verdict */}
            <MDBox p={1} mb={1.5} sx={{ borderRadius: "6px",
              backgroundColor: allPass ? "#e9f7ef" : "#fff6e6" }}>
              <MDTypography variant="h6" sx={{ fontSize: 14, color: allPass ? "#0a7f3f" : "#B17500" }}>
                {`${data.n_gates_passed} of ${data.n_gates} deployment gates passed`}
                {allPass ? " — ready to program" : " — review caveats before programming"}
              </MDTypography>
              <MDTypography variant="caption" sx={{ fontSize: 10.5, color: "#666" }}>
                {`Verdict: ${data.verdict} · match direction: ${data.match_direction}`}
              </MDTypography>
            </MDBox>

            <Grid container spacing={2}>
              {/* LEFT: identity + threshold + evidence */}
              <Grid item xs={12} md={6}>
                <MDTypography variant="caption" sx={{ fontSize: 10, fontWeight: "bold", color: "#999" }}>
                  DEVICE TARGET
                </MDTypography>
                {id ? (
                  <>
                    <KV k="Contact" v={`${id.contact} (${id.hemisphere || "—"})`} />
                    <KV k="Region" v={id.region || "—"} />
                    <KV k="Band" v={`${fmt(id.band_lo_hz, 1)}–${fmt(id.band_hi_hz, 1)} Hz`} />
                    <KV k="Center (FFT-snapped)" v={`${fmt(id.center_freq_hz, 1)} → ${fmt(id.snapped_center_freq_hz, 2)} Hz`} />
                    <KV k="PRO metric / binarization" v={`${id.pro_metric} / ${id.binarization}`} />
                    <KV k="Polarity / suggested mode" v={`${dc.polarity} / ${dc.suggested_mode || "—"}`} />
                  </>
                ) : null}

                <MDBox mt={1.2} p={1.2} sx={{ borderRadius: "6px",
                  backgroundColor: th && th.available ? "#eef5ff" : "#fff6e6",
                  border: `1px solid ${th && th.available ? "#cfe0fb" : "#f3d99b"}` }}>
                  <MDTypography variant="caption" sx={{ fontSize: 10, fontWeight: "bold",
                    color: th && th.available ? "#1A73E8" : "#B17500" }}>
                    THRESHOLD TO PROGRAM
                  </MDTypography>
                  {th && th.available ? (
                    <>
                      <MDTypography variant="h4" sx={{ fontSize: 24, color: "#1A73E8", lineHeight: 1.1 }}>
                        {`power ≥ ${fmt(th.upper_lsb, 1)} LSB`}
                      </MDTypography>
                      <MDTypography variant="caption" sx={{ fontSize: 9.5, color: "#777" }}>
                        {`p${fmt(th.percentile, 0)} of device Timeline LSB · ${th.n_timeline_samples} in-band samples`}
                      </MDTypography>
                    </>
                  ) : (
                    <MDTypography variant="caption" display="block" sx={{ fontSize: 11, mt: 0.3 }}>
                      No deployable LSB threshold — this band is off the device's adaptive sensing range.
                    </MDTypography>
                  )}
                </MDBox>

                <MDBox mt={1.2}>
                  <MDTypography variant="caption" sx={{ fontSize: 10, fontWeight: "bold", color: "#999" }}>
                    EVIDENCE
                  </MDTypography>
                  {ev ? (
                    <>
                      <KV k="Deployment AUC (95% CI)" v={`${fmt(ev.auc)} (${fmt(ev.auc_lo)}–${fmt(ev.auc_hi)})`} />
                      <KV k="Odds ratio (95% CI)" v={`${fmt(ev.odds_ratio)} (${fmt(ev.or_ci_low)}–${fmt(ev.or_ci_high)})${ev.credible_ci ? " ✓" : ""}`} />
                      <KV k="Mixed-effects p" v={ev.p_glmer != null ? ev.p_glmer.toExponential(2) : "—"} />
                      <KV k="Matched samples / ratings" v={`${ev.n_matched_samples ?? "—"} / ${ev.n_clusters ?? "—"}`} />
                      {pw && pw.available ? (
                        <KV k="Power (vs AUC 0.5)" v={`${fmt(pw.power_current * 100, 0)}% · need ${pw.n_ratings_needed} ratings`} />
                      ) : null}
                    </>
                  ) : null}
                </MDBox>
              </Grid>

              {/* RIGHT: gates + caveats */}
              <Grid item xs={12} md={6}>
                <MDTypography variant="caption" sx={{ fontSize: 10, fontWeight: "bold", color: "#999" }}>
                  DEPLOYMENT GATES
                </MDTypography>
                <MDBox mb={1.2}>
                  {(data.gates || []).map((g) => <GateRow key={g.key} gate={g} />)}
                </MDBox>

                <MDTypography variant="caption" sx={{ fontSize: 10, fontWeight: "bold", color: "#B17500" }}>
                  CAVEATS
                </MDTypography>
                <MDBox component="ul" sx={{ pl: 2, mt: 0.5, mb: 0 }}>
                  {(data.caveats || []).map((c, i) => (
                    <MDTypography key={i} component="li" variant="caption"
                      sx={{ fontSize: 10, color: "#555", display: "list-item", mb: 0.3 }}>
                      {c}
                    </MDTypography>
                  ))}
                </MDBox>
              </Grid>
            </Grid>
          </>
        ) : null}
      </MDBox>
    </Card>
  );
}

export default DeploySignoffCard;
