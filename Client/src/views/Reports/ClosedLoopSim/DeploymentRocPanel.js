/**
 * Phase B panel: deployment ROC + cut-point search for one committed BandCandidate.
 *
 * Fetches /api/queryDeploymentROC (rating-clustered bootstrap AUC CI) and renders:
 *   - a Plotly ROC curve with the AUC + clustered 95% CI in the title,
 *   - a match-direction toggle (prior/forecasting [deploy default] vs pro_first [discovery]),
 *   - a cut-point rule selector (Youden J / max-F1 / cost-sensitive / net-benefit) that re-solves
 *     the operating point LIVE in the browser from the returned fpr/tpr/thr/prevalence and draws it
 *     on the curve, surfacing the threshold on the oriented log-power feature scale (Phase C maps
 *     it to LSB).
 *
 * The cut-point chosen here is lifted to the parent (onCutpoint) so Phases C–E can consume it.
 */
import { useEffect, useRef, useState } from "react";
import Plotly from "plotly.js-dist";

import { Card, Grid, ToggleButton, ToggleButtonGroup, Slider } from "@mui/material";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import { SessionController } from "database/session-control";

const fmt = (v, d = 2) => (v == null || !Number.isFinite(Number(v)) ? "—" : Number(v).toFixed(d));

// Solve the operating point on the ROC for a given rule, in the browser, from the parallel
// fpr/tpr/thr arrays + prevalence. Returns {k, fpr, tpr, threshold, sensitivity, specificity, ...}.
function solveCutpoint(roc, rule, costRatio) {
  if (!roc || !Array.isArray(roc.fpr) || !roc.fpr.length) return null;
  const { fpr, tpr, thr } = roc;
  const p = roc.prevalence;
  let bestK = -1, bestU = -Infinity;
  for (let i = 0; i < fpr.length; i += 1) {
    if (thr[i] == null) continue;                 // skip the +inf sentinel at (0,0)
    let u;
    if (rule === "youden") {
      u = tpr[i] - fpr[i];
    } else if (rule === "f1") {
      // F1 from sens/ppv needs prevalence: TP=tpr*P, FP=fpr*(1-P), FN=(1-tpr)*P.
      if (!Number.isFinite(p) || p <= 0 || p >= 1) { u = tpr[i] - fpr[i]; }
      else {
        const tp = tpr[i] * p, fp = fpr[i] * (1 - p), fn = (1 - tpr[i]) * p;
        const denom = 2 * tp + fp + fn;
        u = denom > 0 ? (2 * tp) / denom : -Infinity;
      }
    } else if (rule === "cost") {
      // Cost-sensitive tangent: maximize tpr - slope*fpr, slope = costRatio*(1-p)/p.
      if (!Number.isFinite(p) || p <= 0 || p >= 1) { u = tpr[i] - fpr[i]; }
      else { u = tpr[i] - (costRatio * (1 - p) / p) * fpr[i]; }
    } else if (rule === "netbenefit") {
      // Net benefit at threshold prob pt implied by the cost ratio: NB = TP/N - FP/N * (pt/(1-pt)).
      // We use the cost ratio as the odds weight directly (pt/(1-pt) = costRatio).
      if (!Number.isFinite(p) || p <= 0 || p >= 1) { u = tpr[i] - fpr[i]; }
      else { u = tpr[i] * p - fpr[i] * (1 - p) * costRatio; }
    } else {
      u = tpr[i] - fpr[i];
    }
    if (u > bestU) { bestU = u; bestK = i; }
  }
  if (bestK < 0) return null;
  return {
    k: bestK, fpr: fpr[bestK], tpr: tpr[bestK], threshold: thr[bestK],
    sensitivity: tpr[bestK], specificity: 1 - fpr[bestK], rule,
  };
}

function DeploymentRocPanel({ participantUid, bandCandidate, requestParams, onCutpoint }) {
  const ref = useRef(null);
  const [matchDir, setMatchDir] = useState("prior");      // deploy default = causal forecasting
  const [rule, setRule] = useState("youden");
  const [logCost, setLogCost] = useState(0);              // log2(cFP/cFN); 0 => symmetric
  const [roc, setRoc] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);

  const bc = bandCandidate || {};
  const channelRaw = bc.contact;
  const centerHz = bc.center_freq_hz;
  const bandWidthHz = bc.bandwidth_hz || 5.0;

  // Fetch ROC whenever the band or the match direction changes.
  useEffect(() => {
    if (!participantUid || channelRaw == null || centerHz == null) return;
    setLoading(true); setErr(null);
    SessionController.query("/api/queryDeploymentROC", {
      ParticipantId: participantUid,
      Channel: channelRaw,
      CenterHz: Number(centerHz),
      BandWidthHz: Number(bandWidthHz),
      MatchDirection: matchDir,
      ...requestParams,
    }).then((response) => {
      const data = response && response.data;
      if (data && data.available && data.roc && data.roc.available) {
        setRoc(data.roc);
      } else {
        setRoc(null);
        setErr((data && (data.reason || (data.roc && data.roc.reason))) || "ROC unavailable");
      }
      setLoading(false);
    }).catch(() => { setRoc(null); setErr("ROC request failed"); setLoading(false); });
  }, [participantUid, channelRaw, centerHz, bandWidthHz, matchDir, requestParams]);

  const costRatio = Math.pow(2, logCost);
  const op = roc ? solveCutpoint(roc, rule, costRatio) : null;
  const opThr = op ? op.threshold : null;
  const opRule = op ? op.rule : null;
  const rocAuc = roc ? roc.auc : null;

  // Lift the chosen cut-point to the parent for Phases C–E. Keyed on the stable primitives (not the
  // freshly-rebuilt op object) so it fires only when the actual operating point changes.
  useEffect(() => {
    if (onCutpoint) {
      onCutpoint(opThr != null ? { threshold: opThr, rule: opRule, matchDir, auc: rocAuc,
        sensitivity: op && op.sensitivity, specificity: op && op.specificity,
        fpr: op && op.fpr, tpr: op && op.tpr } : null);
    }
  }, [opThr, opRule, matchDir, rocAuc]);  // eslint-disable-line react-hooks/exhaustive-deps

  // Draw the ROC.
  useEffect(() => {
    if (!ref.current) return undefined;
    if (!roc) { Plotly.purge(ref.current); return undefined; }
    const traces = [
      { x: [0, 1], y: [0, 1], type: "scatter", mode: "lines", name: "chance",
        line: { color: "#bbb", dash: "dot", width: 1 }, hoverinfo: "skip", showlegend: false },
      { x: roc.fpr, y: roc.tpr, type: "scatter", mode: "lines", name: "ROC",
        line: { color: "#1A73E8", width: 2.2 }, showlegend: false,
        hovertemplate: "FPR %{x:.2f} · TPR %{y:.2f}<extra></extra>" },
    ];
    if (op) {
      traces.push({
        x: [op.fpr], y: [op.tpr], type: "scatter", mode: "markers",
        name: "cut-point", showlegend: false,
        marker: { color: "#0a7f3f", size: 12, line: { color: "#fff", width: 2 } },
        hovertemplate: `cut-point (${op.rule})<br>power ≥ ${fmt(op.threshold)}<br>`
          + `sens ${fmt(op.sensitivity)} · spec ${fmt(op.specificity)}<extra></extra>`,
      });
    }
    const ciTxt = (roc.auc_lo != null && roc.auc_hi != null)
      ? ` (95% CI ${fmt(roc.auc_lo)}–${fmt(roc.auc_hi)})` : "";
    const layout = {
      title: { text: `AUC = ${fmt(roc.auc)}${ciTxt}`, font: { size: 13 } },
      margin: { l: 46, r: 12, t: 32, b: 42 }, height: 320,
      xaxis: { title: { text: "False positive rate", font: { size: 11 } }, range: [-0.02, 1.02],
        zeroline: false, tickfont: { size: 10 } },
      yaxis: { title: { text: "True positive rate", font: { size: 11 } }, range: [-0.02, 1.02],
        zeroline: false, tickfont: { size: 10 } },
      annotations: op ? [{
        x: op.fpr, y: op.tpr, xref: "x", yref: "y",
        text: `<b>power ≥ ${fmt(op.threshold)}</b>`, showarrow: true, arrowhead: 0,
        arrowcolor: "#0a7f3f", ax: 28, ay: 26, font: { size: 11, color: "#fff" },
        bgcolor: "#0a7f3f", bordercolor: "#0a7f3f", borderpad: 3, xanchor: "left", yanchor: "top",
      }] : [],
    };
    Plotly.react(ref.current, traces, layout, { displayModeBar: false, responsive: true });
    const gd = ref.current;
    return () => { if (gd) Plotly.purge(gd); };
  }, [roc, opThr, opRule]);  // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <Card sx={{ width: "100%" }}>
      <MDBox p={2}>
        <MDBox display="flex" justifyContent="space-between" alignItems="center" mb={1} flexWrap="wrap" gap={1}>
          <MDTypography variant="h6" sx={{ fontSize: 14 }}>Deployment ROC + cut-point</MDTypography>
          <ToggleButtonGroup size="small" exclusive value={matchDir}
            onChange={(e, v) => { if (v) setMatchDir(v); }}>
            <ToggleButton value="prior" sx={{ fontSize: 10, textTransform: "none", py: 0.2 }}>
              prior (forecasting)
            </ToggleButton>
            <ToggleButton value="pro_first" sx={{ fontSize: 10, textTransform: "none", py: 0.2 }}>
              pro_first (discovery)
            </ToggleButton>
          </ToggleButtonGroup>
        </MDBox>

        {loading ? (
          <MDTypography variant="caption" color="text" sx={{ fontStyle: "italic", fontSize: 11 }}>
            Computing rating-clustered ROC (bootstrap CI)…
          </MDTypography>
        ) : err ? (
          <MDTypography variant="caption" sx={{ fontSize: 11, color: "#9A3324" }}>
            {`ROC unavailable: ${err}.`}
          </MDTypography>
        ) : (
          <>
            <div ref={ref} style={{ width: "100%" }} />
            <Grid container spacing={1.5} alignItems="center" mt={0.2}>
              <Grid item xs={12} md={7}>
                <MDTypography variant="caption" sx={{ fontSize: 10, fontWeight: "bold", color: "#999" }}>
                  CUT-POINT RULE
                </MDTypography>
                <ToggleButtonGroup size="small" exclusive value={rule} sx={{ ml: 1 }}
                  onChange={(e, v) => { if (v) setRule(v); }}>
                  {[["youden", "Youden J"], ["f1", "max F1"], ["cost", "cost"],
                    ["netbenefit", "net benefit"]].map(([k, lbl]) => (
                    <ToggleButton key={k} value={k}
                      sx={{ fontSize: 9.5, textTransform: "none", py: 0.2, px: 0.8 }}>{lbl}</ToggleButton>
                  ))}
                </ToggleButtonGroup>
              </Grid>
              {(rule === "cost" || rule === "netbenefit") ? (
                <Grid item xs={12} md={5}>
                  <MDTypography variant="caption" sx={{ fontSize: 9.5, color: "#777" }}>
                    {`FP:FN cost = ${costRatio.toFixed(2)} : 1`}
                  </MDTypography>
                  <Slider size="small" min={-3} max={3} step={0.25} value={logCost}
                    onChange={(e, v) => setLogCost(v)} sx={{ mt: -0.5 }} />
                </Grid>
              ) : null}
            </Grid>

            {op ? (
              <MDBox mt={1} p={1} sx={{ backgroundColor: "#f3f8f4", borderRadius: "6px" }}>
                <MDTypography variant="caption" sx={{ fontSize: 11.5 }}>
                  <b>Cut-point ({op.rule}):</b>{` power ≥ ${fmt(op.threshold, 3)} `}
                  <span style={{ color: "#777" }}>(oriented log-power units — Phase C → LSB)</span>
                  {` · sensitivity ${fmt(op.sensitivity)} · specificity ${fmt(op.specificity)}`}
                </MDTypography>
                <MDTypography variant="caption" display="block" color="text" sx={{ fontSize: 10, mt: 0.3 }}>
                  {`${roc.n_samples} samples · ${roc.n_clusters} independent ratings · `
                    + `prevalence ${fmt(roc.prevalence)} · ${roc.n_boot_ok} bootstrap replicates · `
                    + `match: ${matchDir}`}
                </MDTypography>
              </MDBox>
            ) : null}
          </>
        )}
      </MDBox>
    </Card>
  );
}

export default DeploymentRocPanel;
