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

    rows.forEach((row, di) => {
      const axisNum = n - di; // bottom row = y1
      const yk = axisNum === 1 ? "y" : "y" + axisNum;
      const yaxisKey = axisNum === 1 ? "yaxis" : "yaxis" + axisNum;
      const top = 1 - di * (h + gap);
      const bottom = Math.max(0, top - h);
      // Explicit padded y-range so the top data value never touches the row's upper edge (where the
      // row title sits) — auto-range alone clipped the peak of the first row. Pad 12% above max and
      // a small margin below min; fall back to autorange if the row has no finite data.
      const allY = row.traces.flatMap((tr) => (tr.y || [])).filter((v) => v != null && Number.isFinite(v));
      let yrange = null;
      if (allY.length) {
        const ymin = Math.min(...allY), ymax = Math.max(...allY);
        const span = ymax - ymin || Math.abs(ymax) || 1;
        yrange = [ymin - span * 0.06, ymax + span * 0.12];
      }
      layout[yaxisKey] = { domain: [bottom, top], title: { text: row.unit, font: { size: 11 } },
        zeroline: false, showgrid: true, gridcolor: "#F0F0F0", automargin: true,
        ...(yrange ? { range: yrange } : { autorange: true }) };
      row.traces.forEach((tr) => {
        // PAIN ROW (isPain): render exactly like the standalone Pain Scores report — translucent
        // thin raw markers+line plus a thick moving-average trend over the top. CRITICAL: the pain
        // column is sparse (one value per survey) embedded in a per-sample array full of nulls, so
        // a moving average over ARRAY indices just re-traces the raw values (a redundant double
        // line). Compact to the non-null (x, y) observations FIRST, then smooth over consecutive
        // observations — that produces a real trend identical to the PainScores report (which is
        // fed one point per survey with no gaps).
        if (row.isPain) {
          const cx = [], cy = [];
          (tr.y || []).forEach((v, i) => {
            if (v != null && Number.isFinite(v)) { cx.push(x[i]); cy.push(v); }
          });
          traces.push({
            x: cx, y: cy, name: tr.name, type: "scatter", mode: "lines+markers",
            line: { color: tr.color, width: 1.5 },
            marker: { size: 5, color: tr.color, line: { color: "white", width: 0.5 } },
            opacity: 0.55, yaxis: yk, xaxis: "x", connectgaps: false,
            hovertemplate: `${row.title} — ${tr.name}: %{y:.3g}<extra></extra>`,
          });
          if (cy.length >= 3) {
            traces.push({
              x: cx, y: movingAverage(cy, 3), name: `${tr.name} (3-pt avg)`, type: "scatter",
              mode: "lines", line: { color: tr.color, width: 3 },
              yaxis: yk, xaxis: "x", connectgaps: false, hoverinfo: "skip", showlegend: false,
            });
          }
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
