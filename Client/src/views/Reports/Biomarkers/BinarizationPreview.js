/**
 * BinarizationPreview — live histogram of the selected pain score with the strategy's high/low
 * cuts and class counts overlaid. Pure client-side: takes the raw daily PRO values, the strategy
 * key, and the percentile sliders, and recomputes every render so the figure updates the moment
 * the user drags a slider or changes the strategy (no backend roundtrip).
 *
 * Sits in the top controls card alongside the strategy selector so the user can SEE exactly which
 * days will be labeled high vs low BEFORE clicking "Compute biomarker". Renders identically on
 * every tab (time-domain, power-domain, both) — the binarization is source-independent.
 *
 * Design notes (publication-quality, colorblind-safe):
 *   * Okabe-Ito palette — LO=#0072B2 (blue), HI=#D55E00 (vermillion), MID=#7E8794 (grey).
 *   * Histogram is a single trace with per-bin marker colors, so the high/low/excluded classes
 *     are visually contiguous (no gap artifacts from three separate overlaid histograms).
 *   * Cut lines + percentile labels above the plot area; class-count badges as in-plot annotations.
 *   * Card is intentionally compact (square-ish, height ~280px) so it sits next to the controls
 *     without dominating the page.
 */

import { useMemo, useEffect, useRef } from "react";
import Plotly from "plotly.js-dist";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

const LO = "#0072B2";   // blue
const HI = "#D55E00";   // vermillion
const MID = "#7E8794";  // grey (excluded middle)

// Lightweight percentile (linear interpolation, q in 0..100) over a finite-value array.
function percentile(values, q) {
  if (!values || values.length === 0) return null;
  const a = [...values].sort((x, y) => x - y);
  const idx = (q / 100) * (a.length - 1);
  const lo = Math.floor(idx), hi = Math.ceil(idx);
  if (lo === hi) return a[lo];
  return a[lo] + (a[hi] - a[lo]) * (idx - lo);
}

// Compute cuts given strategy + percentile state. Returns
//   { kind: "two-cut"|"one-cut"|"kmeans-approx", lowCut, highCut, lowCutLabel, highCutLabel }
// "kmeans-approx" is a heuristic preview: real KMeans runs in the backend on `cv_df`, but for a
// SINGLE-metric histogram preview the 1-D k=2 result is identical to a midpoint between the two
// per-cluster means — we use the median split as the visual cue and label it as approximate.
function computeCuts(vals, strategy, lowPct, highPct) {
  if (!vals || vals.length === 0) return { kind: "none" };
  if (strategy === "tertile" || strategy === "percentile") {
    return {
      kind: "two-cut",
      lowCut: percentile(vals, lowPct),
      highCut: percentile(vals, highPct),
      lowLabel: `${lowPct.toFixed(0)}th pct`,
      highLabel: `${highPct.toFixed(0)}th pct`,
    };
  }
  if (strategy === "median") {
    const m = percentile(vals, 50);
    return { kind: "one-cut", cut: m, label: "median (50th pct)" };
  }
  // KMeans: 1-D k=2 cluster — quick in-browser approximation. Initialize at the 25th and 75th
  // percentiles, iterate a few times; converges in a handful of steps on monotone PRO data.
  let c0 = percentile(vals, 25), c1 = percentile(vals, 75);
  for (let it = 0; it < 30; it++) {
    const mid = (c0 + c1) / 2;
    let s0 = 0, n0 = 0, s1 = 0, n1 = 0;
    for (const v of vals) {
      if (v <= mid) { s0 += v; n0 += 1; } else { s1 += v; n1 += 1; }
    }
    const nc0 = n0 ? s0 / n0 : c0, nc1 = n1 ? s1 / n1 : c1;
    if (Math.abs(nc0 - c0) < 1e-9 && Math.abs(nc1 - c1) < 1e-9) { c0 = nc0; c1 = nc1; break; }
    c0 = nc0; c1 = nc1;
  }
  return { kind: "one-cut", cut: (c0 + c1) / 2, label: "KMeans midpoint (1-D preview)" };
}

// Auto-bin count by Freedman–Diaconis (capped) — adapts to spread/skew without forcing the user
// to think about it. Falls back to Sturges for small n.
function chooseBins(vals) {
  const n = vals.length;
  if (n < 2) return 1;
  if (n < 30) return Math.max(1, Math.ceil(Math.log2(n) + 1));   // Sturges
  const sorted = [...vals].sort((a, b) => a - b);
  const q1 = sorted[Math.floor(0.25 * (n - 1))];
  const q3 = sorted[Math.floor(0.75 * (n - 1))];
  const iqr = q3 - q1;
  const range = sorted[n - 1] - sorted[0];
  if (iqr <= 0 || range <= 0) return Math.max(1, Math.ceil(Math.log2(n) + 1));
  const w = 2 * iqr / Math.cbrt(n);
  return Math.min(60, Math.max(8, Math.round(range / w)));
}

function BinarizationPreview({ points, strategy, percentileLow, percentileHigh, metricLabel, loading }) {
  const ref = useRef(null);

  // Strip nulls/NaNs once; cuts and bins are computed on the cleaned values.
  const vals = useMemo(() => (points || []).map((p) => p.v)
    .filter((v) => typeof v === "number" && Number.isFinite(v)), [points]);

  const cuts = useMemo(() => computeCuts(vals, strategy, percentileLow, percentileHigh),
                       [vals, strategy, percentileLow, percentileHigh]);

  // Class counts and bin assignments for the trace coloring.
  const stats = useMemo(() => {
    if (!vals.length || cuts.kind === "none") return { nLow: 0, nHigh: 0, nMid: 0 };
    if (cuts.kind === "two-cut") {
      let nLow = 0, nHigh = 0, nMid = 0;
      for (const v of vals) {
        if (v <= cuts.lowCut) nLow++;
        else if (v >= cuts.highCut) nHigh++;
        else nMid++;
      }
      return { nLow, nHigh, nMid };
    }
    const cut = cuts.cut;
    let nLow = 0, nHigh = 0;
    for (const v of vals) (v <= cut ? nLow++ : nHigh++);
    return { nLow, nHigh, nMid: 0 };
  }, [vals, cuts]);

  useEffect(() => {
    if (!ref.current) return;
    if (!vals.length) { Plotly.purge(ref.current); return; }
    const nBins = chooseBins(vals);
    const vmin = Math.min(...vals), vmax = Math.max(...vals);
    const binW = (vmax - vmin) / nBins || 1;
    // Build manual bins so each bin gets a per-class color (low/excluded/high) — Plotly's stacked
    // histogram can't color by cut value of the bin itself, so we precompute.
    const edges = Array.from({ length: nBins + 1 }, (_, i) => vmin + i * binW);
    const counts = new Array(nBins).fill(0);
    for (const v of vals) {
      let i = Math.floor((v - vmin) / binW);
      if (i >= nBins) i = nBins - 1; if (i < 0) i = 0;
      counts[i] += 1;
    }
    const centers = counts.map((_, i) => (edges[i] + edges[i + 1]) / 2);
    let colors;
    if (cuts.kind === "two-cut") {
      colors = centers.map((c) => (c <= cuts.lowCut ? LO : (c >= cuts.highCut ? HI : MID)));
    } else if (cuts.kind === "one-cut") {
      colors = centers.map((c) => (c <= cuts.cut ? LO : HI));
    } else {
      colors = centers.map(() => LO);
    }
    const shapes = [];
    const annotations = [];
    // Cut-line labels sit above the plot. When the two cuts are close on the x-axis (e.g. the
    // ceiling-skewed NRS tertile at 7.0 / 8.0) same-height labels overlap, so stagger them:
    // the low-cut label on a lower line anchored to the LEFT of its line, the high-cut label on
    // a higher line anchored to the RIGHT. yLevel/xanchor passed per call.
    const pushCutLine = (x, label, color, yLevel = 1.04, xanchor = "center") => {
      shapes.push({ type: "line", xref: "x", yref: "paper", x0: x, x1: x, y0: 0, y1: 1,
                    line: { color, width: 2, dash: "dash" } });
      annotations.push({ x, yref: "paper", y: yLevel, xanchor, yanchor: "bottom",
                         text: `${x.toFixed(1)} (${label})`, showarrow: false,
                         font: { size: 10, color } });
    };
    if (cuts.kind === "two-cut") {
      pushCutLine(cuts.lowCut, cuts.lowLabel, LO, 1.02, "right");
      pushCutLine(cuts.highCut, cuts.highLabel, HI, 1.13, "left");
      // Shade the excluded middle.
      shapes.push({ type: "rect", xref: "x", yref: "paper", x0: cuts.lowCut, x1: cuts.highCut,
                    y0: 0, y1: 1, fillcolor: MID, opacity: 0.10, line: { width: 0 } });
    } else if (cuts.kind === "one-cut") {
      pushCutLine(cuts.cut, cuts.label, "#344767", 1.04, "center");
    }

    // Class-count badges in the plot area — placed at the top-left (low) and top-right (high)
    // corners; the excluded middle (if any) sits centered. Sample annotations adapted from the
    // ps-scientific-visualization guidelines (sentence case, sans-serif, no chart junk).
    const badge = (xRel, color, label, count) => ({
      xref: "paper", yref: "paper", x: xRel, y: 0.94, xanchor: "center", yanchor: "top",
      text: `<b>${label}</b><br>${count.toLocaleString()} days`,
      showarrow: false, align: "center",
      font: { size: 11, color: "#FFFFFF" },
      bgcolor: color, bordercolor: color, borderpad: 4, opacity: 0.92,
    });
    if (cuts.kind === "two-cut") {
      annotations.push(badge(0.10, LO, "Low", stats.nLow));
      // Excluded badge sits at the very BOTTOM-CENTER of the plot (bottom-anchored just above the
      // x-axis), clear of the staggered cut-line labels above the plot. Alpha is also lowered so it
      // reads as a translucent overlay — any bar behind it still shows through (combined fix:
      // bottom placement keeps it off the cut labels, lower alpha keeps it from occluding a bar).
      annotations.push({ ...badge(0.50, MID, "Excluded", stats.nMid),
                         y: 0.02, yanchor: "bottom", opacity: 0.78 });
      annotations.push(badge(0.90, HI, "High", stats.nHigh));
    } else if (cuts.kind === "one-cut") {
      annotations.push(badge(0.18, LO, "Low", stats.nLow));
      annotations.push(badge(0.82, HI, "High", stats.nHigh));
    }

    const traces = [{
      x: centers, y: counts, type: "bar",
      marker: { color: colors, line: { width: 0 } }, opacity: 0.88, width: binW * 0.96,
      hovertemplate: `${metricLabel || "pain"}=%{x:.1f}<br>%{y:,} days<extra></extra>`,
    }];
    const layout = {
      paper_bgcolor: "white", plot_bgcolor: "white",
      font: { family: "Roboto, Helvetica, Arial, sans-serif", size: 11, color: "#344767" },
      margin: { l: 48, r: 16, t: 54, b: 40 },
      bargap: 0.02,
      xaxis: { automargin: true, title: { text: metricLabel || "Pain score", font: { size: 11 }, standoff: 8 },
               gridcolor: "#EEF1F4", linecolor: "#B0B7BF", ticks: "outside", ticklen: 4,
               tickfont: { size: 10 }, showline: true },
      yaxis: { automargin: true, title: { text: "Days", font: { size: 11 }, standoff: 8 },
               gridcolor: "#EEF1F4", linecolor: "#B0B7BF", ticks: "outside", ticklen: 4,
               tickfont: { size: 10 }, showline: true },
      shapes, annotations, showlegend: false,
    };
    Plotly.react(ref.current, traces, layout, {
      responsive: true, displaylogo: false, displayModeBar: false,
    });
    return () => { if (ref.current) Plotly.purge(ref.current); };
  }, [vals, cuts, stats, metricLabel]);

  return (
    <MDBox display="flex" flexDirection="column" sx={{ width: "100%", height: "100%", minHeight: 440 }}>
      <MDBox display="flex" flexDirection="row" justifyContent="space-between" alignItems="baseline" mb={0.25}>
        <MDTypography variant="button" fontWeight="medium" color="text" sx={{ fontSize: 13 }}>
          {"Binarization preview"}
        </MDTypography>
        <MDTypography variant="caption" color="text" sx={{ fontSize: 10, fontStyle: "italic" }}>
          {vals.length ? `${vals.length} daily PRO observations` : (loading ? "loading…" : "no data yet")}
        </MDTypography>
      </MDBox>
      <div ref={ref} style={{ flex: 1, width: "100%", minHeight: 380 }} />
      <MDTypography variant="caption" color="text" sx={{ fontSize: 10, textAlign: "center" }}>
        {cuts.kind === "two-cut"
          ? `Tertile cuts at ${cuts.lowCut?.toFixed(1)} / ${cuts.highCut?.toFixed(1)} — middle ${stats.nMid} days excluded from training.`
          : cuts.kind === "one-cut"
            ? `${strategy === "median" ? "Median" : "KMeans"} cut at ${cuts.cut?.toFixed(1)} — every day is labeled.`
            : "Adjust the strategy to preview the cut."}
      </MDTypography>
    </MDBox>
  );
}

export default BinarizationPreview;
