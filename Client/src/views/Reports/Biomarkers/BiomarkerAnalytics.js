/**
 * BiomarkerAnalytics -- reproduces Yiyuan Han's notebook biomarker figures below the timeline:
 *  - Sliding-window performance over time (AUC + Pearson R + sensitivity + specificity + threshold)
 *  - ROC curve (FPR vs TPR + AUC)
 *  - Streaming PSD correlation spectrum (Pearson R vs frequency, per channel, with significance)
 *  - LFP distribution + Otsu threshold
 *  - Pain-level cluster scatter (Left Leg VAS vs MPQ Sum, coloured by pain level)
 * Self-contained via plotly.js-dist.
 */

import { useEffect, useRef } from "react";
import Plotly from "plotly.js-dist";

import { Card, Grid } from "@mui/material";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

function Fig({ traces, layout, height = 340 }) {
  const ref = useRef(null);
  useEffect(() => {
    if (!ref.current || !traces || traces.length === 0) return;
    Plotly.react(ref.current, traces, { autosize: true, height, margin: { l: 55, r: 55, t: 40, b: 45 }, ...layout },
      { responsive: true, displaylogo: false });
    return () => { if (ref.current) Plotly.purge(ref.current); };
  }, [traces, layout, height]);
  return <div ref={ref} style={{ width: "100%", height }} />;
}

function Panel({ title, children }) {
  return (
    <Grid item xs={12} lg={6}>
      <Card sx={{ width: "100%", height: "100%" }}>
        <MDBox p={2}>
          <MDTypography variant="h6" fontSize={18} mb={1}>{title}</MDTypography>
          {children}
        </MDBox>
      </Card>
    </Grid>
  );
}

export default function BiomarkerAnalytics({ analytics }) {
  if (!analytics) return null;
  const chronic = analytics.chronic || {};
  const td = analytics.timedomain || {};
  const sw = chronic.sliding_window || [];
  const roc = chronic.roc || null;
  const dist = chronic.lfp_distribution || null;
  const cluster = chronic.cluster_scatter || null;
  const spectrum = td.corr_spectrum || null;

  const panels = [];

  // --- Sliding-window performance over time -------------------------------------------------
  if (sw.length > 0) {
    const x = sw.map((w) => w.test_start);
    const mk = (key, name, opts = {}) => ({
      x, y: sw.map((w) => w[key]), name, type: "scatter", mode: "lines+markers",
      connectgaps: false, ...opts,
    });
    const traces = [
      mk("auc", "AUC", { line: { width: 3, color: "#1A73E8" } }),
      mk("r", "Pearson R", { line: { width: 3, color: "#E91E63" } }),
      mk("sens", "Sensitivity", { line: { width: 1.5, color: "#43A047", dash: "dot" } }),
      mk("spec", "Specificity", { line: { width: 1.5, color: "#FB8C00", dash: "dot" } }),
      mk("threshold", "Threshold", { yaxis: "y2", line: { width: 1.5, color: "#9E9E9E", dash: "dash" }, mode: "lines" }),
    ];
    panels.push(
      <Panel key="sw" title="Sliding-window performance over time">
        <Fig traces={traces} layout={{
          xaxis: { type: "date", title: "Test window start" },
          yaxis: { title: "AUC / R / Sens / Spec", range: [-1.05, 1.05], zeroline: true },
          yaxis2: { title: "LFP threshold", overlaying: "y", side: "right", showgrid: false },
          legend: { orientation: "h", y: -0.25 }, hovermode: "x unified",
        }} />
      </Panel>
    );
  }

  // --- ROC curve ----------------------------------------------------------------------------
  if (roc && roc.fpr && roc.fpr.length > 0) {
    const traces = [
      { x: roc.fpr, y: roc.tpr, name: `ROC (AUC=${(roc.auc ?? 0).toFixed(3)})`, type: "scatter",
        mode: "lines", line: { width: 3, color: "#1A73E8" }, fill: "tozeroy", fillcolor: "rgba(26,115,232,0.1)" },
      { x: [0, 1], y: [0, 1], name: "chance", type: "scatter", mode: "lines",
        line: { width: 1, color: "#9E9E9E", dash: "dash" }, hoverinfo: "skip" },
    ];
    panels.push(
      <Panel key="roc" title="ROC curve (chronic LFP vs pain)">
        <Fig traces={traces} layout={{
          xaxis: { title: "False positive rate", range: [-0.02, 1.02], scaleanchor: "y", scaleratio: 1 },
          yaxis: { title: "True positive rate", range: [-0.02, 1.02] },
          legend: { orientation: "h", y: -0.25 },
        }} />
      </Panel>
    );
  }

  // --- Streaming correlation spectrum -------------------------------------------------------
  if (spectrum && spectrum.channels && spectrum.channels.length > 0) {
    const f = spectrum.freqs;
    const traces = [];
    spectrum.channels.forEach((ch) => {
      traces.push({ x: f, y: ch.r, name: ch.name, type: "scatter", mode: "lines", line: { width: 2 }, connectgaps: false });
      if (ch.significant && ch.significant.some((v) => v !== null)) {
        traces.push({ x: f, y: ch.significant, name: `${ch.name} (p<${spectrum.p_significant})`,
          type: "scatter", mode: "markers", marker: { symbol: "cross", size: 7, color: "black" }, showlegend: false });
      }
    });
    panels.push(
      <Panel key="spec" title="Streaming PSD correlation with pain (Pearson R vs frequency)">
        <Fig traces={traces} layout={{
          xaxis: { title: "Frequency (Hz)" },
          yaxis: { title: "Correlation with pain (R)", range: [-1.05, 1.05], zeroline: true },
          legend: { orientation: "h", y: -0.25 },
        }} />
      </Panel>
    );
  }

  // --- LFP distribution + Otsu --------------------------------------------------------------
  if (dist && dist.counts && dist.counts.length > 0) {
    const edges = dist.bin_edges;
    const centers = dist.counts.map((_, i) => (edges[i] + edges[i + 1]) / 2);
    const traces = [{ x: centers, y: dist.counts, type: "bar", name: "LFP", marker: { color: "#1A73E8" } }];
    const shapes = dist.otsu != null ? [{ type: "line", x0: dist.otsu, x1: dist.otsu, yref: "paper", y0: 0, y1: 1,
      line: { color: "#E91E63", width: 2, dash: "dash" } }] : [];
    panels.push(
      <Panel key="dist" title="LFP power distribution + Otsu threshold">
        <Fig traces={traces} layout={{
          xaxis: { title: "LFP power (device units)" }, yaxis: { title: "Count" },
          shapes, annotations: dist.otsu != null ? [{ x: dist.otsu, yref: "paper", y: 1, text: `Otsu ${dist.otsu.toFixed(0)}`,
            showarrow: false, font: { color: "#E91E63" }, xanchor: "left" }] : [],
          bargap: 0.02,
        }} />
      </Panel>
    );
  }

  // --- Pain-level cluster scatter -----------------------------------------------------------
  if (cluster && cluster.pain_level && cluster.pain_level.length > 0) {
    const colors = cluster.pain_level.map((p) => (p === 1 ? "#E91E63" : "#1A73E8"));
    const traces = [{ x: cluster.left_leg_vas, y: cluster.mpq_sum, type: "scatter", mode: "markers",
      marker: { color: colors, size: 8, opacity: 0.6 }, name: "samples",
      text: cluster.pain_level.map((p) => (p === 1 ? "high pain" : "low pain")) }];
    panels.push(
      <Panel key="cluster" title="Pain-level clusters (Left Leg VAS vs MPQ Sum)">
        <Fig traces={traces} layout={{ xaxis: { title: "Left Leg VAS" }, yaxis: { title: "MPQ Sum" } }} />
      </Panel>
    );
  }

  if (panels.length === 0) return null;

  return (
    <Grid item xs={12}>
      <MDBox mt={1} mb={1}>
        <MDTypography variant="h5" fontSize={20}>Biomarker analysis (Yiyuan Han pipeline)</MDTypography>
      </MDBox>
      <Grid container spacing={2}>{panels}</Grid>
    </Grid>
  );
}
