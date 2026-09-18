/**
=========================================================
* UF BRAVO Platform  (Pain fork)
=========================================================

* Copyright 2025 by Jackson Cagle, Fixel Institute
* The source code is made available under Open Source GPL-3.0 License

 =========================================================
*/
/** Per-metric availability in the selected, already processed report set. */
import { useEffect, useRef } from "react";
import Plotly from "plotly.js-dist";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import Card from "@mui/material/Card";

export function isNumericValue(value) {
  return (typeof value === "number" || (typeof value === "string" && value.trim() !== ""))
    && Number.isFinite(Number(value));
}

export function recordAvailability(dataToRender, form) {
  const records = Array.isArray(dataToRender) ? dataToRender : [];
  const fields = Object.entries(form || {}).flatMap(([page, definition]) =>
    Object.entries(definition?.questions || {}).map(([index, question]) => ({ ...question, page, index })));
  const metrics = fields.filter((q) => q.text !== "Time" &&
    ["score", "redcapForm", "cumulativeScore"].includes(q.type));
  return { total: records.length, metrics: metrics.map((metric) => {
    // Derived totals are available only when every named component has a numeric value.
    const components = metric.type === "cumulativeScore"
      ? (metric.list || []).map((label) => fields.find((field) => field.text === label)) : [metric];
    const count = records.filter((record) => components.length > 0 && components.every((field) =>
      field && isNumericValue(record?.Result?.[field.page]?.[field.index]))).length;
    return { label: metric.text, count };
  }) };
}

function RecordCountBars({ dataToRender, form }) {
  const ref = useRef(null);

  useEffect(() => {
    const node = ref.current;
    const { total, metrics } = recordAvailability(dataToRender, form);
    const counts = metrics.map((metric) => metric.count);
    const labels = metrics.map((metric) => metric.label);
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
      yaxis: { title: { text: "reports with numeric values", font: { size: 12 } }, rangemode: "tozero" },
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

    Plotly.react(node, [trace], layout, { responsive: true, displaylogo: false });
    return () => Plotly.purge(node);
  }, [dataToRender, form]);

  return (
    <Card sx={{ width: "100%" }}>
      <MDBox px={2} pt={2} pb={1}>
        <MDTypography variant="h6">{"Data Availability by Metric"}</MDTypography>
        <MDTypography variant="caption" color="text">
          {"Reports with a finite numeric value, including zero, in the selected processed report set. Derived totals require every component. The dashed line marks all selected reports; counts do not indicate independent samples."}
        </MDTypography>
      </MDBox>
      <MDBox px={1} pb={2}>
        <div ref={ref} style={{ width: "100%" }} />
      </MDBox>
    </Card>
  );
}

export default RecordCountBars;
