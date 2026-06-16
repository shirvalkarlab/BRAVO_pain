/**
 * BiomarkerAnalytics -- reproduces Yiyuan Han's notebook biomarker figures, split into a
 * Time-domain section and a Chronic section:
 *   Time-domain: PSD correlation spectrum (R vs freq), mean PSD high-vs-low pain, PSD spectrogram.
 *   Chronic: sliding-window AUC+R+sens+spec+threshold, ROC curve, LFP/Otsu histogram, cluster scatter.
 * Channel labels use contact numbers + polarity + brain region (from the backend formatter).
 * Self-contained via plotly.js-dist.
 */

import { useEffect, useRef } from "react";
import Plotly from "plotly.js-dist";

import { Card, Grid } from "@mui/material";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

function Fig({ traces, layout = {}, height = 320 }) {
  const ref = useRef(null);
  useEffect(() => {
    if (!ref.current || !traces || traces.length === 0) return;
    // Shared styling for every panel: one font, faint gridlines, and automargin so axis titles
    // never clip. xaxis/yaxis merge per-axis so a panel's own axis props are preserved.
    const base = {
      autosize: true, height, margin: { l: 60, r: 28, t: 40, b: 48 },
      font: { family: "Roboto, Helvetica, Arial, sans-serif", size: 12, color: "#344767" },
      ...layout,
      xaxis: { automargin: true, gridcolor: "#F0F0F0", ...(layout.xaxis || {}) },
      yaxis: { automargin: true, gridcolor: "#F0F0F0", ...(layout.yaxis || {}) },
    };
    Plotly.react(ref.current, traces, base, {
      responsive: true, displaylogo: false,
      modeBarButtonsToRemove: ["select2d", "lasso2d", "autoScale2d", "toggleSpikelines"],
      toImageButtonOptions: { format: "png", scale: 2 },   // crisp 2x PNG export for figures/slides
    });
    return () => { if (ref.current) Plotly.purge(ref.current); };
  }, [traces, layout, height]);
  return <div ref={ref} style={{ width: "100%", height }} />;
}

function Panel({ title, children, lg = 6 }) {
  return (
    <Grid item xs={12} lg={lg}>
      <Card sx={{ width: "100%", height: "100%" }}>
        <MDBox p={2}>
          <MDTypography variant="h6" fontSize={17} mb={0.5}>{title}</MDTypography>
          {children}
        </MDBox>
      </Card>
    </Grid>
  );
}

function Section({ title, subtitle, panels }) {
  if (!panels || panels.length === 0) return null;
  return (
    <Grid item xs={12}>
      <MDBox mt={4} mb={2}>
        {/* Section header at ~2x the prior size for clear hierarchy between TD / power-domain. */}
        <MDTypography variant="h3" fontSize={40} fontWeight="bold">{title}</MDTypography>
        {subtitle ? <MDTypography variant="body2" color="text">{subtitle}</MDTypography> : null}
      </MDBox>
      <Grid container spacing={3}>{panels}</Grid>
    </Grid>
  );
}

const HI = "#E53935", LO = "#1A73E8";

// Distinct per-channel colors so a curve and its peak stars share one color (and read as a pair).
const PALETTE = ["#1A73E8", "#E53935", "#43A047", "#FB8C00", "#8E24AA", "#00ACC1", "#6D4C41", "#C0CA33"];

// Power line-noise band (~60 Hz US mains). A faint caution shade + subtle label so peaks that land
// here are read as likely line-noise artifact, not a neural pain rhythm. Reused across freq panels.
const mainsBand = () => ({
  shapes: [{ type: "rect", xref: "x", yref: "paper", x0: 55, x1: 65, y0: 0, y1: 1,
    fillcolor: "rgba(120,120,120,0.10)", line: { width: 0 }, layer: "below" }],
  annotations: [{ xref: "x", yref: "paper", x: 60, y: 1, yanchor: "bottom", text: "mains ~60 Hz",
    showarrow: false, font: { size: 9, color: "#9E9E9E" } }],
});

export default function BiomarkerAnalytics({ analytics }) {
  if (!analytics) return null;
  const td = analytics.timedomain || {};
  const chronic = analytics.powerdomain || analytics.chronic || {};

  // ---------------- TIME-DOMAIN ----------------
  const tdPanels = [];
  const spectrum = td.corr_spectrum || null;
  if (spectrum && spectrum.channels && spectrum.channels.length) {
    const f = spectrum.freqs;
    const traces = [];
    spectrum.channels.forEach((ch, ci) => {
      const color = PALETTE[ci % PALETTE.length];
      // Hover (not fixed labels) gives the value on demand, matching the other panels. The curve and
      // its peaks share a color + legendgroup, so toggling the curve in the legend also hides its stars.
      traces.push({ x: f, y: ch.r, name: ch.name, type: "scatter", mode: "lines",
        line: { width: 2, color }, connectgaps: false, legendgroup: ch.name,
        hovertemplate: "%{x:.1f} Hz · R=%{y:.2f}<extra>%{fullData.name}</extra>" });
      if (ch.peaks && ch.peaks.length) {
        // Stars only MARK the peaks (no permanent text); the value is read by hovering.
        traces.push({ x: ch.peaks.map((p) => p.freq), y: ch.peaks.map((p) => p.r),
          type: "scatter", mode: "markers", legendgroup: ch.name, showlegend: false,
          marker: { symbol: "star", size: 12, color, line: { width: 1, color: "#fff" } },
          name: `${ch.name} peak`,
          hovertemplate: "peak · %{x:.1f} Hz · R=%{y:.2f}<extra>%{fullData.name}</extra>" });
      }
    });
    const mb = mainsBand();
    tdPanels.push(
      <Panel key="spec" title="PSD correlation with pain (Pearson R vs frequency) — peaks marked with ★" lg={12}>
        <Fig traces={traces} height={380} layout={{ xaxis: { title: "Frequency (Hz)" },
          yaxis: { title: "Correlation with pain (R)", range: [-1.05, 1.05], zeroline: true },
          legend: { orientation: "h", y: -0.2, groupclick: "togglegroup" },
          shapes: mb.shapes, annotations: mb.annotations }} />
      </Panel>
    );
  }

  const spectra = td.psd_spectra || null;
  if (spectra && spectra.channels) {
    spectra.channels.forEach((ch, i) => {
      const traces = [
        { x: spectra.freqs, y: ch.high, name: "High pain", type: "scatter", mode: "lines", line: { color: HI, width: 2 }, connectgaps: false },
        { x: spectra.freqs, y: ch.low, name: "Low pain", type: "scatter", mode: "lines", line: { color: LO, width: 2 }, connectgaps: false },
      ];
      const mb = mainsBand();
      tdPanels.push(
        <Panel key={"psd" + i} title={`Mean PSD by pain — ${ch.short}`}>
          <Fig traces={traces} layout={{ xaxis: { title: "Frequency (Hz)" },
            yaxis: { title: `Power (${spectra.unit})` }, legend: { orientation: "h", y: -0.25 },
            title: { text: ch.region || "", font: { size: 11 } },
            shapes: mb.shapes, annotations: mb.annotations }} />
        </Panel>
      );
    });
  }

  const sg = td.spectrogram || null;
  if (sg && sg.channels) {
    sg.channels.forEach((ch, i) => {
      const traces = [{ type: "heatmap", z: ch.z, x: sg.times, y: sg.freqs, colorscale: "Viridis",
        colorbar: { title: sg.unit, titleside: "right" },
        hovertemplate: `%{x|%b %d %Y} · %{y:.1f} Hz · %{z:.1f} ${sg.unit}<extra></extra>` }];
      tdPanels.push(
        <Panel key={"sg" + i} title={`PSD over sessions — ${ch.short}`}>
          <Fig traces={traces} layout={{ xaxis: { title: "Session", type: "date" }, yaxis: { title: "Frequency (Hz)" },
            title: { text: ch.region || "", font: { size: 11 } } }} />
        </Panel>
      );
    });
  }

  const scs = td.sliding_corr_spectrum || null;
  if (scs && scs.channels && scs.channels.length) {
    scs.channels.forEach((ch, i) => {
      const traces = [{ type: "heatmap", z: ch.r, x: ch.window_starts, y: ch.freqs,
        colorscale: "RdBu", reversescale: true, zmid: 0, zmin: -1, zmax: 1,
        colorbar: { title: { text: "R", side: "right" }, thickness: 12, len: 0.9 },
        hovertemplate: "%{x|%b %d %Y} · %{y:.1f} Hz · R=%{z:.2f}<extra></extra>" }];
      tdPanels.push(
        <Panel key={"scs" + i} lg={12}
          title={`Sliding correlation with pain (R: frequency × time) — ${ch.channel}`}>
          <Fig traces={traces} height={360}
            layout={{ xaxis: { title: "Window start", type: "date" }, yaxis: { title: "Frequency (Hz)" } }} />
        </Panel>
      );
    });
  }

  // ---------------- CHRONIC ----------------
  const chPanels = [];
  const sw = chronic.sliding_window || [];
  if (sw.length) {
    const x = sw.map((w) => w.test_start);
    const mk = (key, name, opts = {}) => ({ x, y: sw.map((w) => w[key]), name, type: "scatter",
      mode: "lines+markers", connectgaps: false, ...opts });
    const traces = [
      mk("auc", "AUC", { line: { width: 3, color: "#1A73E8" } }),
      mk("r", "Pearson R", { line: { width: 3, color: "#E91E63" } }),
      mk("sens", "Sensitivity", { line: { width: 1.5, color: "#43A047", dash: "dot" } }),
      mk("spec", "Specificity", { line: { width: 1.5, color: "#FB8C00", dash: "dot" } }),
      mk("threshold", "Threshold", { yaxis: "y2", mode: "lines", line: { width: 1.5, color: "#9E9E9E", dash: "dash" } }),
    ];
    chPanels.push(
      <Panel key="sw" title="Sliding-window performance over time" lg={12}>
        <Fig traces={traces} layout={{ xaxis: { type: "date", title: "Test window start" },
          yaxis: { title: "AUC / R / Sens / Spec", range: [-1.05, 1.05], zeroline: true },
          yaxis2: { title: "LFP threshold", overlaying: "y", side: "right", showgrid: false },
          legend: { orientation: "h", y: -0.25 }, hovermode: "x unified" }} />
      </Panel>
    );
  }
  const roc = chronic.roc || null;
  if (roc && roc.fpr && roc.fpr.length) {
    const traces = [
      { x: roc.fpr, y: roc.tpr, name: `ROC (AUC=${(roc.auc ?? 0).toFixed(3)})`, type: "scatter", mode: "lines",
        line: { width: 3, color: "#1A73E8" }, fill: "tozeroy", fillcolor: "rgba(26,115,232,0.1)",
        hovertemplate: "FPR=%{x:.2f} · TPR=%{y:.2f}<extra></extra>" },
      { x: [0, 1], y: [0, 1], name: "chance", type: "scatter", mode: "lines",
        line: { width: 1, color: "#9E9E9E", dash: "dash" }, hoverinfo: "skip" },
    ];
    chPanels.push(
      <Panel key="roc" title="ROC curve (power-domain LFP vs pain)">
        <Fig traces={traces} layout={{ xaxis: { title: "False positive rate", range: [-0.02, 1.02], scaleanchor: "y", scaleratio: 1 },
          yaxis: { title: "True positive rate", range: [-0.02, 1.02] }, legend: { orientation: "h", y: -0.25 } }} />
      </Panel>
    );
  }
  const dist = chronic.lfp_distribution || null;
  if (dist && dist.counts && dist.counts.length) {
    const edges = dist.bin_edges;
    const centers = dist.counts.map((_, i) => (edges[i] + edges[i + 1]) / 2);
    chPanels.push(
      <Panel key="dist" title="LFP power distribution + Otsu threshold">
        <Fig traces={[{ x: centers, y: dist.counts, type: "bar", marker: { color: "#1A73E8" },
          hovertemplate: "LFP≈%{x:.0f} · %{y} samples<extra></extra>" }]}
          layout={{ xaxis: { title: "LFP power (device units)" }, yaxis: { title: "Count" }, bargap: 0.02,
            shapes: dist.otsu != null ? [{ type: "line", x0: dist.otsu, x1: dist.otsu, yref: "paper", y0: 0, y1: 1, line: { color: "#E91E63", width: 2, dash: "dash" } }] : [],
            annotations: dist.otsu != null ? [{ x: dist.otsu, yref: "paper", y: 1, text: `Otsu ${dist.otsu.toFixed(0)}`, showarrow: false, font: { color: "#E91E63" }, xanchor: "left" }] : [] }} />
      </Panel>
    );
  }
  const cluster = chronic.cluster_scatter || null;
  if (cluster && cluster.x && cluster.x.length) {
    const lvl = cluster.pain_level || [];
    const xlab = cluster.x_label || "feature";
    if (cluster.y && cluster.y.length) {
      // 2-D clustering features (e.g. the MPQ+VAS composite): scatter colored by pain level.
      const colors = lvl.map((p) => (p === 1 ? HI : LO));
      const ylab = cluster.y_label || "feature 2";
      chPanels.push(
        <Panel key="cluster" title={`Pain-level clusters (${xlab} vs ${ylab})`}>
          <Fig traces={[{ x: cluster.x, y: cluster.y, type: "scatter", mode: "markers",
            marker: { color: colors, size: 8, opacity: 0.6 },
            customdata: lvl.map((p) => (p === 1 ? "high pain" : "low pain")),
            hovertemplate: `${xlab}=%{x}<br>${ylab}=%{y}<br>%{customdata}<extra></extra>` }]}
            layout={{ xaxis: { title: xlab }, yaxis: { title: ylab } }} />
        </Panel>
      );
    } else {
      // 1-D clustering feature (e.g. nrs / vas): overlaid high/low-pain histograms so the KMeans
      // split on the single metric is visible (where the binary cut landed).
      const hi = cluster.x.filter((_, i) => lvl[i] === 1);
      const lo = cluster.x.filter((_, i) => lvl[i] === 0);
      chPanels.push(
        <Panel key="cluster" title={`Pain-level clusters (${xlab})`}>
          <Fig traces={[
            { x: lo, type: "histogram", name: "low pain", marker: { color: LO }, opacity: 0.6,
              hovertemplate: `${xlab}=%{x}<br>low pain · %{y}<extra></extra>` },
            { x: hi, type: "histogram", name: "high pain", marker: { color: HI }, opacity: 0.6,
              hovertemplate: `${xlab}=%{x}<br>high pain · %{y}<extra></extra>` },
          ]} layout={{ barmode: "overlay", xaxis: { title: xlab }, yaxis: { title: "Count" },
            legend: { orientation: "h", y: -0.25 } }} />
        </Panel>
      );
    }
  }

  if (tdPanels.length === 0 && chPanels.length === 0) return null;

  return (
    <>
      <Section title="Time-domain analysis (250 Hz streaming PSD)"
               subtitle="Pearson-R spectrum, mean PSD by pain state, and PSD spectrogram per contact pair."
               panels={tdPanels} />
      <Section title="Power-domain analysis (Chronic 10-min trend + per-session band power)"
               subtitle="Sliding-window classifier (AUC / R / sensitivity / specificity / threshold), ROC, LFP distribution, and pain clusters."
               panels={chPanels} />
    </>
  );
}
