/**
 * BiomarkerAnalytics -- reproduces Yiyuan Han's notebook biomarker figures, split into a
 * Time-domain section and a Chronic section:
 *   Time-domain: PSD correlation spectrum (R vs freq), mean PSD high-vs-low pain, PSD spectrogram.
 *   Chronic: sliding-window AUC+R+sens+spec+threshold, ROC curve, LFP/Otsu histogram, cluster scatter.
 * Channel labels use contact numbers + polarity + brain region (from the backend formatter).
 * Self-contained via plotly.js-dist.
 */

import { useEffect, useRef, useState, useMemo } from "react";
import Plotly from "plotly.js-dist";

import { Card, Grid, ToggleButton, ToggleButtonGroup } from "@mui/material";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

// Publication-quality shared style for every panel — one font, faint gridlines, generous
// axis-title spacing (standoff), readable tick fonts, x-unified hover. Per-panel props can override
// any field by setting it on `layout` (a panel that passes layout.xaxis merges into the base xaxis).
const AXIS_BASE = {
  automargin: true, gridcolor: "#EEF1F4", zerolinecolor: "#D0D7DE", linecolor: "#B0B7BF",
  showline: true, mirror: false, ticks: "outside", ticklen: 4, tickcolor: "#B0B7BF",
  tickfont: { size: 11, color: "#495057" },
  title: { font: { size: 12, color: "#344767" }, standoff: 12 },
};
const FIG_BASE = {
  paper_bgcolor: "white", plot_bgcolor: "white",
  font: { family: "Roboto, Helvetica, Arial, sans-serif", size: 12, color: "#344767" },
  margin: { l: 64, r: 28, t: 44, b: 56 },
  legend: { orientation: "h", x: 0, y: -0.18, font: { size: 11 } },
  hovermode: "closest",
  hoverlabel: { bgcolor: "white", bordercolor: "#B0B7BF",
                font: { family: "Roboto, Helvetica, Arial, sans-serif", size: 11 } },
};
const mergeAxis = (override = {}) => ({
  ...AXIS_BASE, ...override,
  title: typeof override.title === "string"
    ? { ...AXIS_BASE.title, text: override.title }
    : { ...AXIS_BASE.title, ...(override.title || {}) },
});

function Fig({ traces, layout = {}, height = 320 }) {
  const ref = useRef(null);
  useEffect(() => {
    if (!ref.current || !traces || traces.length === 0) return;
    const base = {
      ...FIG_BASE, autosize: true, height,
      ...layout,
      xaxis: mergeAxis(layout.xaxis),
      yaxis: mergeAxis(layout.yaxis),
      ...(layout.yaxis2 ? { yaxis2: { ...AXIS_BASE, ...layout.yaxis2,
        title: typeof layout.yaxis2.title === "string"
          ? { ...AXIS_BASE.title, text: layout.yaxis2.title }
          : { ...AXIS_BASE.title, ...(layout.yaxis2.title || {}) } } } : {}),
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
      <Card sx={{ width: "100%", height: "100%", scrollMarginTop: "96px" }}>
        <MDBox p={2}>
          <MDTypography variant="h6" fontSize={17} mb={0.5}>{title}</MDTypography>
          {children}
        </MDBox>
      </Card>
    </Grid>
  );
}

function Section({ title, subtitle, panels, header = null }) {
  if (!panels || panels.length === 0) return null;
  return (
    <Grid item xs={12}>
      <MDBox mt={4} mb={2}>
        {/* Section header at ~2x the prior size for clear hierarchy between TD / power-domain. */}
        <MDTypography variant="h3" fontSize={40} fontWeight="bold">{title}</MDTypography>
        {subtitle ? <MDTypography variant="body2" color="text">{subtitle}</MDTypography> : null}
      </MDBox>
      <Grid container spacing={3}>
        {header}
        {panels}
      </Grid>
    </Grid>
  );
}

// Okabe-Ito colorblind-safe palette (8% of males have red-green color blindness; this set is
// distinguishable to every common type and remains legible in grayscale). HI/LO pair: orange/blue
// (orange = high pain, blue = low pain) — the strongest contrast in the palette.
const HI = "#D55E00", LO = "#0072B2";   // vermillion / blue
const PALETTE = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#56B4E9", "#E69F00", "#F0E442", "#000000"];

// Compact p-value formatter (scientific for tiny p), matching the report card's style.
const fmtP = (x) => {
  if (x === null || x === undefined || Number.isNaN(Number(x))) return "—";
  const n = Number(x);
  if (n > 0 && n < 1e-3) return n.toExponential(1);
  return n.toFixed(3);
};

// Friendly display names for the raw PRO feature keys (fallback: title-case the key).
const FEATURE_LABELS = {
  nrs: "NRS", vas: "Overall VAS", left_leg_vas: "Left Leg VAS", back_vas: "Back VAS",
  mpq_sum: "MPQ Sum", mpq_sen: "MPQ Sensory", mpq_aff: "MPQ Affective",
};
const featLabel = (k) => FEATURE_LABELS[k] || String(k).replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

export default function BiomarkerAnalytics({ analytics, summary, metricLabel }) {
  if (!analytics) return null;
  const td = analytics.timedomain || {};
  const pdRoot = analytics.powerdomain || analytics.chronic || {};

  // Per-channel split (rigor review §7-C): the backend now ships analytics for each LFP series
  // (e.g. "Left LFP" / "Right LFP") alongside the pooled run. Default to pooled — switching to a
  // channel swaps the LFP histogram, sliding-window curve, ROC, and headline summary in place;
  // no re-fetch (the per-channel payload is part of the same response).
  const perChannel = pdRoot.per_channel || {};
  const channelKeys = Object.keys(perChannel);
  const [chSel, setChSel] = useState("pooled");
  // If the response no longer carries the previously-selected channel, reset to pooled.
  const safeChSel = (chSel === "pooled" || perChannel[chSel]) ? chSel : "pooled";
  const chronic = useMemo(() => (
    safeChSel === "pooled" ? pdRoot : { ...pdRoot, ...perChannel[safeChSel] }
  ), [safeChSel, pdRoot, perChannel]);

  // Human-readable pain score these correlations / AUCs are computed against (biological best
  // practice: every correlation/AUC panel should say what it is correlated WITH). Falls back gracefully.
  const pain = metricLabel || "pain";
  const tdSum = (summary && summary.timedomain) || {};
  const pdSum = (summary && summary.powerdomain) || {};
  // When a per-channel view is active, overlay its summary on the pooled one so the honest-perf
  // bar reflects the selected channel's AUC.
  const pdSumEff = safeChSel === "pooled" ? pdSum : { ...pdSum, ...(chronic.summary || {}) };
  const chSuffix = safeChSel === "pooled" ? "" : ` · ${safeChSel}`;

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
  // sliding_window is now {windows, summary} (was a bare list). Tolerate both shapes for back-compat.
  const swRaw = chronic.sliding_window;
  const swWindows = Array.isArray(swRaw) ? swRaw : (swRaw && swRaw.windows) || [];
  const swSummary = (swRaw && !Array.isArray(swRaw) && swRaw.summary) || null;
  if (swWindows.length) {
    const x = swWindows.map((w) => w.test_start);
    // connectgaps=true keeps the trace continuous across skipped windows. The skips are honest
    // (one-class test folds) and the backend caption below tells the reader the coverage.
    const mk = (key, name, opts = {}) => ({ x, y: swWindows.map((w) => w[key]), name, type: "scatter",
      mode: "lines+markers", marker: { size: 6 }, connectgaps: true, ...opts });
    const traces = [
      mk("auc", "AUC", { line: { width: 3, color: PALETTE[0] } }),
      mk("r", "Pearson R", { line: { width: 3, color: PALETTE[1] } }),
      mk("sens", "Sensitivity", { line: { width: 1.5, color: PALETTE[2], dash: "dot" } }),
      mk("spec", "Specificity", { line: { width: 1.5, color: PALETTE[5], dash: "dot" } }),
      mk("threshold", "Threshold", { yaxis: "y2", mode: "lines",
        line: { width: 1.5, color: "#7E8794", dash: "dash" }, hovertemplate: "thr=%{y:.1f}<extra></extra>" }),
    ];
    chPanels.push(
      <Panel key="sw" title={`Sliding-window performance over time — LFP vs ${pain}${chSuffix}`} lg={12}>
        <Fig height={360} traces={traces} layout={{
          xaxis: { type: "date", title: "Test window start" },
          yaxis: { title: "AUC / R / Sensitivity / Specificity", range: [-1.05, 1.05],
                   zeroline: true, zerolinewidth: 1 },
          yaxis2: { title: "LFP threshold (device units)", overlaying: "y", side: "right",
                    showgrid: false },
          hovermode: "x unified",
          // 0.5 reference for the AUC ceiling-vs-chance read
          shapes: [{ type: "line", x0: x[0], x1: x[x.length - 1], y0: 0.5, y1: 0.5, yref: "y",
                     line: { color: "#C8CED5", width: 1, dash: "dot" } }],
        }} />
        {swSummary ? (
          <MDTypography variant="caption" color="text" display="block" mt={1} fontStyle="italic" sx={{ fontSize: 11 }}>
            {`Reporting ${swSummary.n_with_auc} of ${swSummary.n_total} candidate windows where both pain classes appeared in the test fold (within an expansion cap of ${swSummary.max_test_days} days). ` +
             `Skipped: ${swSummary.n_skipped_test_one_class} for one-class test folds (common with tertile binarization — the excluded middle leaves stretches of all-low or all-high days) and ${swSummary.n_skipped_no_data} for empty/degenerate folds.`}
          </MDTypography>
        ) : null}
      </Panel>
    );
  }

  // Honest performance vs overfit: the threshold-free in-sample AUC looks strong, but the
  // cross-validated balanced accuracy (the generalization estimate) sits near the chance baseline.
  // Plotting them side by side makes the generalization gap explicit. (new honest-stats panel)
  if (pdSumEff.auc != null || pdSumEff.balanced_accuracy != null) {
    const labels = ["In-sample AUC", "CV balanced accuracy", "Chance"];
    const vals = [pdSumEff.auc, pdSumEff.balanced_accuracy, pdSumEff.chance_accuracy];
    const colors = [PALETTE[0], PALETTE[2], "#7E8794"];
    chPanels.push(
      <Panel key="honest" title={`Honest performance: in-sample vs cross-validated — LFP vs ${pain}${chSuffix}`}>
        <Fig height={320} traces={[{ x: labels, y: vals.map((v) => (v == null ? null : v)),
          type: "bar", marker: { color: colors, line: { color: "#344767", width: 0.5 } },
          text: vals.map((v) => (v == null ? "" : v.toFixed(2))), textposition: "outside",
          textfont: { size: 12, color: "#344767" },
          hovertemplate: "%{x}: %{y:.3f}<extra></extra>" }]}
          layout={{ yaxis: { title: "Score", range: [0, 1.05] }, xaxis: { title: "" },
            showlegend: false,
            shapes: pdSumEff.chance_accuracy != null ? [{ type: "line", x0: -0.5, x1: 2.5,
              y0: pdSumEff.chance_accuracy, y1: pdSumEff.chance_accuracy,
              line: { color: "#7E8794", width: 1, dash: "dot" } }] : [] }} />
        <MDTypography variant="caption" color="text" display="block" mt={1} sx={{ fontSize: 11 }}>
          {`In-sample AUC is computed on all data with no train/test split (optimistic). ` +
           `Cross-validated balanced accuracy is the held-out generalization estimate — when it sits ` +
           `near chance, the in-sample AUC is not reproduced out-of-fold.${pdSumEff.overfit_warning ? "  ⚠ " + pdSumEff.overfit_warning : ""}`}
        </MDTypography>
      </Panel>
    );
  }
  const roc = chronic.roc || null;
  if (roc && roc.fpr && roc.fpr.length) {
    const traces = [
      { x: roc.fpr, y: roc.tpr, name: `ROC (AUC=${(roc.auc ?? 0).toFixed(3)})`, type: "scatter", mode: "lines",
        line: { width: 3, color: PALETTE[0] }, fill: "tozeroy", fillcolor: "rgba(0,114,178,0.12)",
        hovertemplate: "FPR=%{x:.2f}<br>TPR=%{y:.2f}<extra></extra>" },
      { x: [0, 1], y: [0, 1], name: "chance", type: "scatter", mode: "lines",
        line: { width: 1, color: "#7E8794", dash: "dash" }, hoverinfo: "skip" },
    ];
    chPanels.push(
      <Panel key="roc" title={`ROC curve — power-domain LFP vs ${pain}${chSuffix} (in-sample)`}>
        <Fig height={340} traces={traces} layout={{
          xaxis: { title: "False positive rate", range: [-0.02, 1.02], scaleanchor: "y", scaleratio: 1 },
          yaxis: { title: "True positive rate", range: [-0.02, 1.02] } }} />
      </Panel>
    );
  }
  const dist = chronic.lfp_distribution || null;
  if (dist && dist.counts && dist.counts.length) {
    const edges = dist.bin_edges;
    const centers = dist.counts.map((_, i) => (edges[i] + edges[i + 1]) / 2);
    chPanels.push(
      <Panel key="dist" title={`LFP power distribution + Otsu threshold${chSuffix}`}>
        <Fig height={340} traces={[{
          x: centers, y: dist.counts, type: "bar",
          marker: { color: PALETTE[0], line: { width: 0 } }, opacity: 0.85,
          hovertemplate: "LFP=%{x:.1f}<br>%{y:,} samples<extra></extra>",
        }]}
          layout={{
            xaxis: { title: "LFP power (device units, 1st–99th pct display range)" },
            yaxis: { title: "Sample count" }, bargap: 0.04,
            shapes: dist.otsu != null ? [{ type: "line", x0: dist.otsu, x1: dist.otsu, yref: "paper",
              y0: 0, y1: 1, line: { color: PALETTE[1], width: 2.5, dash: "dash" } }] : [],
            annotations: dist.otsu != null ? [{ x: dist.otsu, yref: "paper", y: 1.02,
              text: `Otsu = ${dist.otsu.toFixed(1)}`, showarrow: false,
              font: { color: PALETTE[1], size: 11 }, xanchor: "left", yanchor: "bottom" }] : [] }} />
        <MDTypography variant="caption" color="text" display="block" mt={1} sx={{ fontSize: 11 }}>
          {`${(dist.n_total || 0).toLocaleString()} samples; histogram is plotted over the robust ` +
           `1st–99th percentile so the bulk is visible. ` +
           (dist.n_clipped ? `${dist.n_clipped.toLocaleString()} extreme outlier sample(s) sit off-range (Otsu still computed on all data).` : "")}
        </MDTypography>
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

  // ---------------- PAIN-LABEL BINARIZATION (top of the report) ----------------
  // Show the raw distribution of the SELECTED pain score and exactly how it is split into the binary
  // high/low pain_level the detector is trained against — the foundation for every correlation/AUC below.
  const binData = chronic.pain_binarization || null;
  const binStrategy = (binData && binData.strategy) || "kmeans";
  const isTertile = binStrategy === "tertile" || binStrategy === "percentile";
  const STRAT_LABEL = { tertile: "tertile split (drop middle)", percentile: "percentile split (drop middle)",
    median: "median split", kmeans: "2-cluster KMeans labeler", cutoff: "fixed cutoff" };
  const binPanels = [];
  if (binData && binData.features && binData.features.length) {
    binData.features.forEach((ft, i) => {
      const name = featLabel(ft.name);
      // Tertile: the two cuts are the low/high percentile lines; the middle band is excluded.
      // Single-threshold strategies (median/kmeans/cutoff): one empirical boundary.
      let loCut = ft.boundary, hiCut = ft.boundary;
      if (isTertile && ft.p_low != null && ft.p_high != null) { loCut = ft.p_low; hiCut = ft.p_high; }
      const lo = ft.values.filter((v) => loCut != null && v <= loCut);
      const hi = ft.values.filter((v) => hiCut != null && v >= hiCut);
      const mid = isTertile ? ft.values.filter((v) => loCut != null && hiCut != null && v > loCut && v < hiCut) : [];
      const shapes = [];
      const anns = [];
      if (isTertile && loCut != null && hiCut != null) {
        // shade the excluded middle band
        shapes.push({ type: "rect", x0: loCut, x1: hiCut, yref: "paper", y0: 0, y1: 1,
          fillcolor: "#9E9E9E", opacity: 0.12, line: { width: 0 } });
        [[loCut, "low cut"], [hiCut, "high cut"]].forEach(([val, lbl]) => {
          shapes.push({ type: "line", x0: val, x1: val, yref: "paper", y0: 0, y1: 1,
            line: { color: "#111", width: 2 } });
          anns.push({ x: val, yref: "paper", y: 1, yanchor: "bottom", xanchor: "center",
            text: `${lbl} ${val.toFixed(1)}`, showarrow: false, font: { size: 10, color: "#111" } });
        });
      } else if (ft.boundary != null) {
        shapes.push({ type: "line", x0: ft.boundary, x1: ft.boundary, yref: "paper", y0: 0, y1: 1,
          line: { color: "#111", width: 2.5 } });
        anns.push({ x: ft.boundary, yref: "paper", y: 1, yanchor: "bottom", xanchor: "center",
          text: `cut ${ft.boundary.toFixed(1)}${ft.boundary_percentile != null ? ` (${ft.boundary_percentile.toFixed(0)}th pct)` : ""}`,
          showarrow: false, font: { size: 10, color: "#111" } });
      }
      [["30th", ft.p30], ["70th", ft.p70]].forEach(([lbl, val]) => {
        if (val != null && !isTertile) {
          shapes.push({ type: "line", x0: val, x1: val, yref: "paper", y0: 0, y1: 1,
            line: { color: "#9E9E9E", width: 1, dash: "dot" } });
          anns.push({ x: val, yref: "paper", y: 0.9, yanchor: "top", xanchor: "center",
            text: lbl, showarrow: false, font: { size: 9, color: "#9E9E9E" } });
        }
      });
      const traces = [
        { x: lo, type: "histogram", name: "low pain", marker: { color: LO }, opacity: 0.65,
          hovertemplate: `${name}=%{x}<br>low pain · %{y} day(s)<extra></extra>` },
        { x: hi, type: "histogram", name: "high pain", marker: { color: HI }, opacity: 0.65,
          hovertemplate: `${name}=%{x}<br>high pain · %{y} day(s)<extra></extra>` },
      ];
      if (isTertile && mid.length) {
        traces.push({ x: mid, type: "histogram", name: "excluded (middle)", marker: { color: "#9E9E9E" }, opacity: 0.45,
          hovertemplate: `${name}=%{x}<br>excluded · %{y} day(s)<extra></extra>` });
      }
      // Daily excluded-middle count — matches the histogram bars (drawn over ft.values, n_obs days).
      // (binData.n_excluded_middle is the PER-SAMPLE excluded count and does not match these bars.)
      const nMid = isTertile ? mid.length : 0;
      binPanels.push(
        <Panel key={"bin" + i} lg={binData.features.length > 1 ? 6 : 12}
          title={`Pain-score binarization — ${name}`}>
          <Fig height={320} traces={traces}
            layout={{ barmode: "overlay", xaxis: { title: name },
            yaxis: { title: "PRO observations (days)" }, legend: { orientation: "h", y: -0.25 },
            shapes, annotations: anns }} />
          <MDTypography variant="caption" color="text" display="block" mt={1}>
            {`Daily ${name} split into high vs low pain by the ${STRAT_LABEL[binStrategy] || binStrategy}, ` +
             `with the cut computed on the daily distribution (not the density-weighted samples). ` +
             (isTertile
               ? (binData.low_pct != null
                   ? `Days ≤ ${binData.low_pct.toFixed(0)}th pct → low, ≥ ${binData.high_pct.toFixed(0)}th pct → high; ` +
                     `the shaded middle band (${nMid.toLocaleString()} of ${ft.n_obs} days) is excluded from training. `
                   : `The shaded middle band is excluded from training. `)
               : (ft.boundary != null
                   ? `The cut falls at ${ft.boundary.toFixed(1)} — the ${ft.boundary_percentile.toFixed(0)}th percentile ` +
                     `(${ft.n_low} low / ${ft.n_high} high of ${ft.n_obs} days). Dotted lines mark the 30th/70th percentiles for reference. `
                   : ""))}
          </MDTypography>
        </Panel>
      );
    });
  }

  if (tdPanels.length === 0 && chPanels.length === 0 && binPanels.length === 0) return null;

  // Channel selector — visible only when the backend split the chronic stream into per-channel
  // analytics. Default "Pooled" preserves the legacy single-detector view; the other buttons swap
  // the LFP histogram / sliding window / ROC / honest-perf panels to that channel.
  const channelToggle = channelKeys.length >= 1 ? (
    <Grid item xs={12}>
      <MDBox mt={2} mb={0.5} display="flex" flexDirection="row" alignItems="center" gap={2} flexWrap="wrap">
        <MDTypography variant="button" fontWeight="medium" color="text" sx={{ fontSize: 13 }}>
          {"Power-domain channel:"}
        </MDTypography>
        <ToggleButtonGroup value={safeChSel} exclusive size="small"
          onChange={(_, v) => { if (v) setChSel(v); }}>
          <ToggleButton value="pooled">Pooled</ToggleButton>
          {channelKeys.map((k) => (
            <ToggleButton key={k} value={k}>{k}</ToggleButton>
          ))}
        </ToggleButtonGroup>
        <MDTypography variant="caption" color="text" fontStyle="italic" sx={{ fontSize: 11 }}>
          {safeChSel === "pooled"
            ? "All recorded LFP series merged into one threshold (legacy view)."
            : `Showing only the ${safeChSel} series — independent threshold, AUC, and sliding-window curve.`}
        </MDTypography>
      </MDBox>
    </Grid>
  ) : null;

  return (
    <>
      <Section title="How the pain score is binarized"
               subtitle="Raw distribution of the selected pain score and the high/low cut the detector is trained on."
               panels={binPanels} />
      <Section title="Time-domain analysis (250 Hz streaming PSD)"
               subtitle="Pearson-R spectrum, mean PSD by pain state, and PSD spectrogram per contact pair."
               panels={tdPanels} />
      <Section title="Power-domain analysis (Chronic 10-min trend + per-session band power)"
               subtitle="Sliding-window classifier (AUC / R / sensitivity / specificity / threshold), ROC, LFP distribution, and pain clusters."
               panels={chPanels}
               header={channelToggle} />
    </>
  );
}
