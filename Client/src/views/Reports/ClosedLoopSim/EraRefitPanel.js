/**
 * Phase D panel: per-era refit of the deployment ROC (OFF / LOW / HIGH stim).
 *
 * Fetches /api/queryDeploymentRocByEra and renders the per-era AUC (with clustered bootstrap CI)
 * and Youden cut-point side by side against the pooled value, plus a portability verdict: a band
 * whose AUC or cut-point swings across stim eras is a fragile closed-loop anchor even with a strong
 * pooled AUC. Eras with too few high/low samples are shown as "insufficient" rather than hidden.
 */
import { useEffect, useState } from "react";

import { Card, Grid } from "@mui/material";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import { SessionController } from "database/session-control";

const fmt = (v, d = 2) => (v == null || !Number.isFinite(Number(v)) ? "—" : Number(v).toFixed(d));
const ERA_COLORS = { OFF: "#6c757d", LOW: "#B17500", HIGH: "#1A73E8", Pooled: "#0a7f3f" };

function EraCard({ tag, era, count }) {
  const ok = era && era.available;
  const op = ok && era.operating_point;
  const color = ERA_COLORS[tag] || "#344767";
  return (
    <MDBox p={1} sx={{ borderRadius: "6px", border: `1px solid ${color}33`,
      backgroundColor: `${color}0d`, height: "100%" }}>
      <MDTypography variant="caption" sx={{ fontSize: 10, fontWeight: "bold", color }}>
        {tag}{tag !== "Pooled" ? ` · ${count ?? 0} samples` : ""}
      </MDTypography>
      {ok ? (
        <>
          <MDTypography variant="h6" sx={{ fontSize: 17, color, lineHeight: 1.1 }}>
            {`AUC ${fmt(era.auc)}`}
          </MDTypography>
          <MDTypography variant="caption" display="block" sx={{ fontSize: 9, color: "#777" }}>
            {(era.auc_lo != null && era.auc_hi != null)
              ? `95% CI ${fmt(era.auc_lo)}–${fmt(era.auc_hi)}` : "CI n/a"}
          </MDTypography>
          <MDTypography variant="caption" display="block" sx={{ fontSize: 10, mt: 0.3 }}>
            {op ? `cut ≥ ${fmt(op.threshold, 2)}` : "no cut-point"}
          </MDTypography>
          <MDTypography variant="caption" display="block" sx={{ fontSize: 9, color: "#999" }}>
            {`${era.n_clusters ?? "—"} ratings · prev ${fmt(era.prevalence)}`}
          </MDTypography>
        </>
      ) : (
        <MDTypography variant="caption" display="block" sx={{ fontSize: 10, color: "#999", mt: 0.5 }}>
          {(era && era.reason) || "not estimable"}
        </MDTypography>
      )}
    </MDBox>
  );
}

function EraRefitPanel({ participantUid, bandCandidate, requestParams }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);

  const bc = bandCandidate || {};
  const channelRaw = bc.contact;
  const centerHz = bc.center_freq_hz;
  const bandWidthHz = bc.bandwidth_hz || 5.0;

  useEffect(() => {
    if (!participantUid || channelRaw == null || centerHz == null) return;
    setLoading(true); setErr(null);
    SessionController.query("/api/queryDeploymentRocByEra", {
      ParticipantId: participantUid,
      Channel: channelRaw,
      CenterHz: Number(centerHz),
      BandWidthHz: Number(bandWidthHz),
      ...requestParams,
    }).then((response) => {
      const d = response && response.data;
      if (d && d.available && d.by_era && d.by_era.available) setData(d.by_era);
      else { setData(null); setErr((d && (d.reason || (d.by_era && d.by_era.reason))) || "unavailable"); }
      setLoading(false);
    }).catch(() => { setData(null); setErr("request failed"); setLoading(false); });
  }, [participantUid, channelRaw, centerHz, bandWidthHz, requestParams]);

  // Portability verdict from the spreads.
  let verdict = null;
  if (data) {
    const aucSpread = data.auc_spread;
    const cutSpread = data.cutpoint_spread;
    const estimable = data.n_eras_estimable;
    if (estimable < 2) {
      verdict = { color: "#6c757d", text: "Only one stim era has enough data — per-era portability can't be assessed." };
    } else if ((aucSpread != null && aucSpread > 0.10) || (cutSpread != null && cutSpread > 0.5)) {
      verdict = { color: "#9A3324", text: `Fragile across stim states: AUC swings ${fmt(aucSpread)} and the cut-point swings ${fmt(cutSpread, 2)} between eras. The same threshold may not hold once stim changes.` };
    } else {
      verdict = { color: "#0a7f3f", text: `Portable across stim states: AUC varies only ${fmt(aucSpread)} between eras — the threshold travels.` };
    }
  }

  return (
    <Card sx={{ width: "100%" }}>
      <MDBox p={2}>
        <MDTypography variant="h6" sx={{ fontSize: 14, mb: 1 }}>
          Per-era refit (OFF / LOW / HIGH stim)
        </MDTypography>
        {loading ? (
          <MDTypography variant="caption" color="text" sx={{ fontStyle: "italic", fontSize: 11 }}>
            Refitting the ROC within each stim era…
          </MDTypography>
        ) : err ? (
          <MDTypography variant="caption" sx={{ fontSize: 11, color: "#9A3324" }}>
            {`Unavailable: ${err}.`}
          </MDTypography>
        ) : data ? (
          <>
            <Grid container spacing={1}>
              <Grid item xs={6} md={3}><EraCard tag="OFF" era={data.eras.OFF} count={data.era_counts.OFF} /></Grid>
              <Grid item xs={6} md={3}><EraCard tag="LOW" era={data.eras.LOW} count={data.era_counts.LOW} /></Grid>
              <Grid item xs={6} md={3}><EraCard tag="HIGH" era={data.eras.HIGH} count={data.era_counts.HIGH} /></Grid>
              <Grid item xs={6} md={3}><EraCard tag="Pooled" era={data.pooled} /></Grid>
            </Grid>
            {verdict ? (
              <MDBox mt={1.2} p={1} sx={{ borderRadius: "6px", backgroundColor: `${verdict.color}12`,
                border: `1px solid ${verdict.color}40` }}>
                <MDTypography variant="caption" sx={{ fontSize: 11, color: verdict.color, fontWeight: "bold" }}>
                  {verdict.text}
                </MDTypography>
              </MDBox>
            ) : null}
            <MDTypography variant="caption" display="block" color="text" sx={{ fontSize: 9, mt: 0.6 }}>
              {`Eras: OFF < ${data.thresholds_mA.off_max} mA · LOW ≤ ${data.thresholds_mA.low_max} mA · HIGH above. `
                + "Same era boundaries as the stim-stability LRT."}
            </MDTypography>
          </>
        ) : null}
      </MDBox>
    </Card>
  );
}

export default EraRefitPanel;
