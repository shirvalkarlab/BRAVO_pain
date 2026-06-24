/**
=========================================================
* UF BRAVO Platform  (Pain fork)
=========================================================

* Copyright 2025 by Jackson Cagle, Fixel Institute
* The source code is made available under Open Source GPL-3.0 License

 =========================================================
*/
/**
 * RecordCountBars
 * ---------------
 * A per-metric data-availability bar chart shown ABOVE the record timeline. For each score-type
 * question in the form's FieldMapping it counts how many of the participant's records carry a
 * non-null value for that metric, and draws one bar per metric. This makes "how much data exists
 * for each individual metric" obvious at a glance (e.g. NRS 678 vs Tingly 187), which the timeline
 * itself does not convey.
 *
 * Counts are computed from exactly the same (dataToRender, form) props the timeline uses, so the
 * numbers always agree with what the timeline plots.
 */
import { useEffect, useRef } from "react";
import Plotly from "plotly.js-dist";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import Card from "@mui/material/Card";

// A value "exists" if it is neither null/undefined nor an empty string, and (when numeric) finite.
function isPresent(v) {
  if (v === null || v === undefined) return false;
  if (typeof v === "string") return v.trim() !== "";
  if (typeof v === "number") return Number.isFinite(v);
  return true;
}

function RecordCountBars({ dataToRender, form }) {
  const ref = useRef(null);

  useEffect(() => {
    if (!ref.current) return;
    const records = Array.isArray(dataToRender) ? dataToRender : [];

    // Collect score-type questions (skip the hidden "Time" marker), preserving FieldMapping order.
    const metrics = [];
    for (const page in form) {
      const questions = (form[page] && form[page].questions) || [];
      for (const i in questions) {
        const q = questions[i];
        if (q.text === "Time") continue;
        if (q.type === "score" || q.type === "redcapForm" || q.type === "cumulativeScore") {
          metrics.push({ label: q.text, page, index: i });
        }
      }
    }

    // Count non-null values per metric across all records.
    const counts = metrics.map((m) => {
      let c = 0;
      for (const r of records) {
        const result = r && r.Result;
        if (!result || !result[m.page]) continue;
        if (isPresent(result[m.page][m.index])) c += 1;
      }
      return c;
    });

    const total = records.length;
    const labels = metrics.map((m) => m.label);
    // Colour by coverage: fuller coverage = deeper teal; sparse = amber, so gaps stand out.
    const colors = counts.map((c) => {
      const frac = total > 0 ? c / total : 0;
      return frac >= 0.9 ? "#1A7F7A" : frac >= 0.5 ? "#3DA5A0" : "#E8A13B";
    });

    const trace = {
      type: "bar",
      x: labels,
      y: counts,
      marker: { color: colors },
      text: counts.map((c) => (total > 0 ? `${c}` : "0")),
      textposition: "outside",
      cliponaxis: false,
      hovertemplate: total > 0
        ? "%{x}<br>%{y} of " + total + " records (%{customdata:.0%})<extra></extra>"
        : "%{x}<br>%{y} records<extra></extra>",
      customdata: counts.map((c) => (total > 0 ? c / total : 0)),
    };

    const layout = {
      height: 260,
      margin: { l: 48, r: 16, t: 16, b: 90 },
      yaxis: { title: { text: "records with a value", font: { size: 12 } }, rangemode: "tozero" },
      xaxis: { tickangle: -35, automargin: true },
      shapes: total > 0 ? [{
        type: "line", xref: "paper", x0: 0, x1: 1, yref: "y", y0: total, y1: total,
        line: { color: "#9aa0a6", width: 1, dash: "dash" },
      }] : [],
      annotations: total > 0 ? [{
        xref: "paper", x: 1, y: total, yref: "y", xanchor: "right", yanchor: "bottom",
        text: `${total} total reports`, showarrow: false, font: { size: 10, color: "#9aa0a6" },
      }] : [],
      bargap: 0.35,
    };

    Plotly.react(ref.current, [trace], layout, { responsive: true, displaylogo: false });
    return () => { if (ref.current) Plotly.purge(ref.current); };
  }, [dataToRender, form]);

  return (
    <Card sx={{ width: "100%" }}>
      <MDBox px={2} pt={2} pb={1}>
        <MDTypography variant="h6">{"Data Availability by Metric"}</MDTypography>
        <MDTypography variant="caption" color="text">
          {"Number of records that contain a value for each metric (non-null). The dashed line marks the total report count."}
        </MDTypography>
      </MDBox>
      <MDBox px={1} pb={2}>
        <div ref={ref} style={{ width: "100%" }} />
      </MDBox>
    </Card>
  );
}

export default RecordCountBars;
