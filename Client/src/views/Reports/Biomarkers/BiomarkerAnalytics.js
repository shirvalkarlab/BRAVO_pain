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

// Compact p-value formatter (scientific for tiny p), matching the report card's style.
const fmtP = (x) => {
  if (x === null || x === undefined || Number.isNaN(Number(x))) return "—";
  const n = Number(x);
  if (n > 0 && n < 1e-3) return n.toExponential(1);
  return n.toFixed(3);
};

export default function BiomarkerAnalytics({ analytics, summary, metricLabel }) {
  if (!analytics) return null;
  const td = analytics.timedomain || {};
  const chronic = analytics.powerdomain || analytics.chronic || {};
  // Human-readable pain score these correlations / AUCs are computed against (biological best
  // practice: every correlation/AUC panel should say what it is correlated WITH). Falls back gracefully.
  const pain = metricLabel || "pain";
  const tdSum = (summary && summary.timedomain) || {};
  const pdSum = (summary && summary.powerdomain) || {};

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
    tdPanels.push(
      <Panel key="spec" title={`PSD correlation with ${pain} (Pearson R vs frequency) — peaks marked with ★`} lg={12}>
        <Fig traces={traces} height={380} layout={{ xaxis: { title: "Frequency (Hz)" },
          yaxis: { title: `Correlation with ${pain} (R)`, range: [-1.05, 1.05], zeroline: true },
          legend: { orientation: "h", y: -0.2, groupclick: "togglegroup" } }} />
      </Panel>
    );
  }

  // Permutation null for the strongest correlation — placed right after the spectrum it tests, so the
  // correlation and its significance test read together. Each null value is the largest |R| over ALL
  // contacts x frequencies when the pain labels are circularly block-shuffled (preserving day-to-day
  // autocorrelation); the observed strongest |R| is the red line. p = fraction of the null >= observed.
  if (tdSum.perm_null && tdSum.perm_null.length && tdSum.perm_obs != null) {
    const obs = tdSum.perm_obs;
    const pStr = tdSum.perm_p == null ? "—" : fmtP(tdSum.perm_p);
    const sig = tdSum.perm_p != null && tdSum.perm_p < 0.05;
    const verdict = sig ? "stronger than chance" : "within the chance distribution → not significant";
    const nCells = (spectrum && spectrum.channels ? spectrum.channels.length : 0) *
                   (spectrum && spectrum.freqs ? spectrum.freqs.length : 0);
    tdPanels.push(
      <Panel key="perm" lg={12}
        title={`Permutation null — strongest PSD↔${pain} correlation vs chance (p=${pStr})`}>
        <Fig height={320} traces={[
          { x: tdSum.perm_null, type: "histogram", name: "null (shuffled pain)",
            marker: { color: "#90A4AE" }, opacity: 0.85, nbinsx: 40,
            hovertemplate: "max|R|≈%{x:.2f} · %{y} shuffles<extra></extra>" },
        ]} layout={{
          xaxis: { title: "Family-max |R| over all contacts × frequencies", range: [0, 1] },
          yaxis: { title: "Permutations" }, bargap: 0.02, showlegend: false,
          shapes: [{ type: "line", x0: obs, x1: obs, yref: "paper", y0: 0, y1: 1,
            line: { color: "#E53935", width: 3 } }],
          annotations: [{ x: obs, yref: "paper", y: 1, yanchor: "bottom", xanchor: "center",
            text: `observed R=${obs.toFixed(2)}`, showarrow: false, font: { color: "#E53935", size: 11 } }],
        }} />
        <MDTypography variant="caption" color="text" display="block" mt={1}>
          {`The observed strongest correlation (R=${obs.toFixed(2)}) is ${verdict} (permutation p=${pStr}, ` +
           `${tdSum.perm_n || tdSum.perm_null.length} block-permutations). This corrects for BOTH the ` +
           `~${nCells}-cell band search (it compares the strongest correlation anywhere in the grid) AND the ` +
           `day-to-day autocorrelation of ${pain} (block shuffling preserves it). It is the honest ` +
           `significance statement for the selected band; the per-cell FDR q is a more conservative companion.`}
        </MDTypography>
      </Panel>
    );
  }

  const spectra = td.psd_spectra || null;
  if (spectra && spectra.channels) {
    spectra.channels.forEach((ch, i) => {
      const traces = [
        { x: spectra.freqs, y: ch.high, name: `High ${pain}`, type: "scatter", mode: "lines", line: { color: HI, width: 2 }, connectgaps: false },
        { x: spectra.freqs, y: ch.low, name: `Low ${pain}`, type: "scatter", mode: "lines", line: { color: LO, width: 2 }, connectgaps: false },
      ];
      tdPanels.push(
        <Panel key={"psd" + i} title={`Mean PSD by ${pain} — ${ch.short}`}>
          <Fig traces={traces} layout={{ xaxis: { title: "Frequency (Hz)" },
            yaxis: { title: `Power (${spectra.unit})` }, legend: { orientation: "h", y: -0.25 },
            title: { text: ch.region || "", font: { size: 11 } } }} />
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
          title={`Sliding correlation with ${pain} (R: frequency × time) — ${ch.channel}`}>
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
      <Panel key="sw" title={`Sliding-window performance over time (LFP vs ${pain})`} lg={12}>
        <Fig traces={traces} layout={{ xaxis: { type: "date", title: "Test window start" },
          yaxis: { title: "AUC / R / Sens / Spec", range: [-1.05, 1.05], zeroline: true },
          yaxis2: { title: "LFP threshold", overlaying: "y", side: "right", showgrid: false },
          legend: { orientation: "h", y: -0.25 }, hovermode: "x unified" }} />
      </Panel>
    );
  }

  // Honest performance vs overfit: the threshold-free in-sample AUC looks strong, but the
  // cross-validated balanced accuracy (the generalization estimate) sits near the chance baseline.
  // Plotting them side by side makes the generalization gap explicit. (new honest-stats panel)
  if (pdSum.auc != null || pdSum.balanced_accuracy != null) {
    const labels = ["In-sample AUC", "CV balanced accuracy", "Chance"];
    const vals = [pdSum.auc, pdSum.balanced_accuracy, pdSum.chance_accuracy];
    const colors = ["#1A73E8", "#43A047", "#9E9E9E"];
    chPanels.push(
      <Panel key="honest" title={`Honest performance: in-sample vs cross-validated (LFP vs ${pain})`}>
        <Fig height={300} traces={[{ x: labels, y: vals.map((v) => (v == null ? null : v)),
          type: "bar", marker: { color: colors },
          text: vals.map((v) => (v == null ? "" : v.toFixed(2))), textposition: "outside",
          hovertemplate: "%{x}: %{y:.3f}<extra></extra>" }]}
          layout={{ yaxis: { title: "Score", range: [0, 1] }, xaxis: { automargin: true },
            shapes: pdSum.chance_accuracy != null ? [{ type: "line", x0: -0.5, x1: 2.5,
              y0: pdSum.chance_accuracy, y1: pdSum.chance_accuracy, line: { color: "#9E9E9E", width: 1, dash: "dot" } }] : [] }} />
        <MDTypography variant="caption" color="text" display="block" mt={1}>
          {`In-sample AUC is computed on all data with no train/test split (optimistic). The ` +
           `cross-validated balanced accuracy is the held-out generalization estimate; when it sits ` +
           `near chance, the in-sample AUC is not reproduced out-of-fold. ${pdSum.overfit_warning ? "⚠ " + pdSum.overfit_warning : ""}`}
        </MDTypography>
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
      <Panel key="roc" title={`ROC curve — power-domain LFP vs ${pain}-derived pain level (in-sample)`}>
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
        {dist.n_clipped ? (
          <MDTypography variant="caption" color="text" display="block" mt={1}>
            {`Plotted over the 1st–99th percentile so the bulk is visible; ${dist.n_clipped.toLocaleString()} ` +
             `extreme outlier sample(s) from the un-normalized merged sources are off-range (Otsu computed on all data).`}
          </MDTypography>
        ) : null}
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
