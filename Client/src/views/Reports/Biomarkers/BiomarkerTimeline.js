/**
 * BiomarkerTimeline -- clean stacked-subplot timeline for the unified biomarker frame.
 * Each measure (time-domain biomarker, power-domain LFP + threshold, pain, stim amplitude) gets
 * its own row sharing one time axis, with human-readable names -- avoids a cluttered single plot
 * with a long horizontal legend. Self-contained via plotly.js-dist.
 */

import { useEffect, useRef } from "react";
import Plotly from "plotly.js-dist";

import MDBox from "components/MDBox";

// Okabe-Ito colorblind-safe palette, aligned with BiomarkerAnalytics.js. Pain uses vermillion
// (the HI color) so a viewer reading the histogram and the timeline together gets the same
// color identity for "pain" across panels.
const C = {
  td: "#0072B2",        // time-domain biomarker (blue)
  lfp: "#009E73",       // power-domain LFP power (green)
  threshold: "#7E8794", // learned threshold
  pain: "#D55E00",      // NRS / pain (vermillion = HI)
  stim: "#E69F00",      // stim amplitude (orange)
};

function parseTime(t) {
  if (t === null || t === undefined) return null;
  if (typeof t === "number") return new Date(t < 1e12 ? t * 1000 : t);
  return new Date(t);
}

// Centered moving average over the non-null values (PainScores report uses a 3-point smooth as a
// thick trend line over translucent raw markers). Skips nulls so gaps don't drag the average.
function movingAverage(y, win = 3) {
  const half = Math.floor(win / 2);
  return y.map((_, i) => {
    let s = 0, c = 0;
    for (let j = i - half; j <= i + half; j++) {
      const v = y[j];
      if (j >= 0 && j < y.length && v != null && Number.isFinite(v)) { s += v; c += 1; }
    }
    return c ? s / c : null;
  });
}

function BiomarkerTimeline({ data, height }) {
  const ref = useRef(null);

  useEffect(() => {
    if (!ref.current || !data || !data.timeline || data.timeline.length === 0) return;

    const recs = data.timeline;
    const cols = new Set(data.channels || Object.keys(recs[0]));
    const x = recs.map((r) => parseTime(r.time));
    const col = (n) => recs.map((r) => (typeof r[n] === "number" ? r[n] : null));
    const has = (n) => cols.has(n) && col(n).some((v) => v !== null);
    const pick = (...names) => names.find((n) => has(n));

    // Rows, top -> bottom.
    const rows = [];
    if (has("td_biomarker_value")) {
      const b = data.summary && data.summary.timedomain && data.summary.timedomain.band;
      rows.push({
        title: b ? `Time-domain biomarker — ${b[4].toFixed(1)} Hz` : "Time-domain biomarker (PSD)",
        unit: "PSD power",
        traces: [{ name: "PSD biomarker", y: col("td_biomarker_value"), color: C.td }],
      });
    }
    if (has("powerdomain_biomarker_value")) {
      const tr = [{ name: "LFP power", y: col("powerdomain_biomarker_value"), color: C.lfp }];
      if (has("powerdomain_threshold")) {
        tr.push({ name: "Threshold", y: col("powerdomain_threshold"), color: C.threshold, dash: "dash", mode: "lines" });
      }
      rows.push({ title: "Power-domain LFP power", unit: "LFP (a.u.)", traces: tr });
    }
    const m = data.label_metric || "nrs";
    const painCol = pick(`powerdomain_${m}`, `td_${m}_min`, `td_${m}_mean`, m, "powerdomain_nrs", "td_nrs_min", "nrs");
    // Always show the pain row as markers, not just a connecting line — each marker is one
    // pain observation (the standalone Pain Scores report renders them this way).
    if (painCol) rows.push({ title: `Pain (${m})`, unit: m, isPain: true,
      traces: [{ name: m, y: col(painCol), color: C.pain, forceMarkers: true }] });
    const stimCol = pick("powerdomain_stim_amplitude", "td_stim_amplitude");
    if (stimCol) rows.push({ title: "Stimulation", unit: "mA", traces: [{ name: "Amplitude", y: col(stimCol), color: C.stim }] });

    const n = Math.max(rows.length, 1);
    const gap = 0.14;   // more breathing room so row titles don't sit on the row above
    const h = (1 - gap * (n - 1)) / n;

    const traces = [];
    const layout = {
      height: height || 170 * n + 100,
      margin: { l: 64, r: 18, t: 52, b: 48 },
      hovermode: "x unified",
      font: { family: "Roboto, Helvetica, Arial, sans-serif", size: 12, color: "#344767" },
      legend: { orientation: "h", y: 1.04, x: 0, font: { size: 11 } },
      annotations: [],
    };

    // Build a translucent "pain-event rug" — every timepoint where pain was recorded — so it can
    // be overlaid on the LFP / time-domain biomarker rows. Reading biomarker activity against
    // the pain dots is the whole point of these stacked plots; without them, the LFP trace floats
    // free of when the patient actually rated their pain.
    const painRugX = painCol
      ? recs.map((r, i) => (typeof r[painCol] === "number" && Number.isFinite(r[painCol]) ? x[i] : null))
            .filter((t) => t !== null)
      : [];

    rows.forEach((row, di) => {
      const axisNum = n - di; // bottom row = y1
      const yk = axisNum === 1 ? "y" : "y" + axisNum;
      const yaxisKey = axisNum === 1 ? "yaxis" : "yaxis" + axisNum;
      const top = 1 - di * (h + gap);
      const bottom = Math.max(0, top - h);
      layout[yaxisKey] = { domain: [bottom, top], title: { text: row.unit, font: { size: 11 } },
        zeroline: false, showgrid: true, gridcolor: "#F0F0F0", automargin: true };
      row.traces.forEach((tr) => {
        // PAIN ROW (isPain): render in the standalone Pain Scores report style — translucent
        // thin raw markers+line PLUS a thick 3-point moving-average trend line over the top, so
        // the trajectory is legible without losing individual observations.
        if (row.isPain) {
          traces.push({
            x, y: tr.y, name: tr.name, type: "scatter", mode: "lines+markers",
            line: { color: tr.color, width: 1.5 },
            marker: { size: 5, color: tr.color, line: { color: "white", width: 0.5 } },
            opacity: 0.55, yaxis: yk, xaxis: "x", connectgaps: false,
            hovertemplate: `${row.title} — ${tr.name}: %{y:.3g}<extra></extra>`,
          });
          traces.push({
            x, y: movingAverage(tr.y, 3), name: `${tr.name} (3-pt avg)`, type: "scatter",
            mode: "lines", line: { color: tr.color, width: 3 },
            yaxis: yk, xaxis: "x", connectgaps: false, hoverinfo: "skip", showlegend: false,
          });
          return;
        }
        // Drop point markers on dense series (lines-only is cleaner/faster); keep them when sparse.
        const nPts = (tr.y || []).filter((v) => v !== null && v !== undefined).length;
        const mode = tr.mode || (nPts > 200 ? "lines" : "lines+markers");
        traces.push({
          x, y: tr.y, name: tr.name, type: "scatter", mode,
          line: { color: tr.color, width: 2, dash: tr.dash || "solid" },
          marker: { size: 4, color: tr.color },
          yaxis: yk, xaxis: "x", connectgaps: false,
          hovertemplate: `${row.title} — ${tr.name}: %{y:.3g}<extra></extra>`,
        });
      });
      // Pain-event rug at the bottom of NON-pain rows: vertical line shapes (translucent vermillion)
      // anchored to this row's paper-y domain so they sit just inside the bottom of the row,
      // regardless of the row's auto-scaled data range. yref="paper" + small fraction of the row
      // height keeps them visible without dominating the trace.
      if (painRugX.length && !row.isPain) {
        const rowH = top - bottom;
        const rugY0 = bottom;
        const rugY1 = bottom + rowH * 0.10;   // 10% of row height — visible but unobtrusive
        if (!layout.shapes) layout.shapes = [];
        painRugX.forEach((tx) => {
          layout.shapes.push({
            type: "line", xref: "x", yref: "paper", x0: tx, x1: tx, y0: rugY0, y1: rugY1,
            line: { color: C.pain, width: 1, dash: "solid" }, opacity: 0.30,
          });
        });
      }
      layout.annotations.push({
        xref: "paper", yref: "paper", x: 0.004, y: Math.min(top + 0.02, 1),
        xanchor: "left", yanchor: "bottom", text: `<b>${row.title}</b>`,
        showarrow: false, font: { size: 12, color: "#344767" },
        bgcolor: "rgba(255,255,255,0.7)",   // halo so the title reads over traces
      });
    });

    layout.xaxis = { domain: [0, 1], type: "date", anchor: "y", title: { text: "Time", font: { size: 12 } },
      showgrid: true, gridcolor: "#F0F0F0" };

    Plotly.react(ref.current, traces, layout, {
      responsive: true, displaylogo: false,
      modeBarButtonsToRemove: ["select2d", "lasso2d", "autoScale2d", "toggleSpikelines"],
      toImageButtonOptions: { format: "png", scale: 2 },
    });
    return () => { if (ref.current) Plotly.purge(ref.current); };
  }, [data, height]);

  return (
    <MDBox p={1}>
      <div ref={ref} style={{ width: "100%" }} />
    </MDBox>
  );
}

export default BiomarkerTimeline;
