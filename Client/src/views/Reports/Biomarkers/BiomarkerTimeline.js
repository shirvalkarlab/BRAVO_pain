/**
 * BiomarkerTimeline -- plots the unified biomarker `timeline` (td_* + chronic_* series + PRO)
 * returned by /api/queryBiomarkerAnalysis. Uses plotly.js-dist directly so the component is
 * self-contained (no dependency on the platform's PlotlyRenderManager API).
 */

import { useEffect, useRef } from "react";
import Plotly from "plotly.js-dist";

import MDBox from "components/MDBox";

// Columns routed to the right-hand (PRO / pain-label) axis; everything else is a biomarker series.
const PRO_HINTS = ["nrs", "vas", "mpq", "pain_level", "pred"];

function isProSeries(name) {
  const n = name.toLowerCase();
  return PRO_HINTS.some((h) => n.includes(h));
}

function parseTime(t) {
  if (t === null || t === undefined) return null;
  if (typeof t === "number") return new Date(t < 1e12 ? t * 1000 : t); // unix s vs ms
  return new Date(t); // ISO string
}

function BiomarkerTimeline({ data, figureTitle = "BiomarkerTimeline", height = 420 }) {
  const ref = useRef(null);

  useEffect(() => {
    if (!ref.current || !data || !data.timeline || data.timeline.length === 0) return;

    const records = data.timeline;
    const columns = (data.channels || Object.keys(records[0])).filter(
      (c) => c !== "time" && c !== "date"
    );
    const x = records.map((r) => parseTime(r.time));

    const traces = [];
    for (const col of columns) {
      // Keep only numeric, not-entirely-null series.
      let anyValue = false;
      const y = records.map((r) => {
        const v = r[col];
        if (v === null || v === undefined || typeof v !== "number") return null;
        anyValue = true;
        return v;
      });
      if (!anyValue) continue;

      const pro = isProSeries(col);
      traces.push({
        x,
        y,
        name: col,
        type: "scatter",
        mode: col.includes("pred") || col.includes("pain_level") ? "lines" : "lines+markers",
        line: { shape: col.includes("threshold") ? "hv" : "linear", width: col.includes("threshold") ? 1 : 2, dash: col.includes("threshold") ? "dash" : "solid" },
        marker: { size: 4 },
        yaxis: pro ? "y2" : "y",
        connectgaps: false,
      });
    }

    const layout = {
      title: { text: `Biomarker timeline (source: ${data.source || "?"})`, font: { size: 16 } },
      height,
      margin: { l: 60, r: 60, t: 50, b: 50 },
      xaxis: { type: "date", title: "Time" },
      yaxis: { title: "Biomarker value", zeroline: false },
      yaxis2: { title: "PRO / pain", overlaying: "y", side: "right", zeroline: false },
      legend: { orientation: "h", y: -0.2 },
      hovermode: "x unified",
    };

    Plotly.react(ref.current, traces, layout, { responsive: true, displaylogo: false });

    return () => {
      if (ref.current) Plotly.purge(ref.current);
    };
  }, [data, height]);

  return (
    <MDBox p={2}>
      <div id={figureTitle} ref={ref} style={{ width: "100%", height: height }} />
    </MDBox>
  );
}

export default BiomarkerTimeline;
