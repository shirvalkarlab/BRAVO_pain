/**
 * The timing histogram at the top of the Binarization card (the PI, 2026-09-21, option C): when
 * each neural sample falls relative to the nearest pain report, one series per source STACKED
 * (the PI, 2026-09-21, after seeing the overlaid version), in the offline figure's colours; the x-axis follows the match-window slider and shows 25% more on each side, greyed, so a
 * reader sees what the window leaves out; the direction toggle greys the side it excludes. Zoom and
 * pan are Plotly's own; a constant uirevision keeps them across slider drags.
 *
 * On screen: Biomarkers page, Binarization card, the top band, under the coverage sentence.
 */
import { useEffect, useMemo, useRef } from "react";
import Plotly from "plotly.js-dist";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import { SOURCE_SERIES, TAIL_GREY, sampleOffsetsMin, timingHistogramData } from "./timingHistogramModel";

const INK = "#1A1A1A";
const BAND = "#F4F6F8";
const GRID = "#E3E7EA";

export default function TimingHistogram({ scanIndex, painSeries, windowMin, matchDirection, metricLabel, height = 260 }) {
  const ref = useRef(null);
  const offsets = useMemo(() => sampleOffsetsMin(scanIndex, painSeries), [scanIndex, painSeries]);
  const data = useMemo(() => timingHistogramData(offsets, { windowMin, matchDirection }),
    [offsets, windowMin, matchDirection]);

  useEffect(() => {
    if (!ref.current) return;
    if (!offsets.length) { Plotly.purge(ref.current); return; }
    const W = data.windowMin, lim = data.limMin, w = data.step * 0.9;
    const traces = [];
    for (const s of SOURCE_SERIES) {
      const ser = data.series[s.key];
      traces.push({ type: "bar", name: s.name, x: data.centers, y: ser.outside, width: w,
        marker: { color: TAIL_GREY }, opacity: 0.8, showlegend: false,
        hovertemplate: `%{y} ${s.name} samples, outside the window<br>%{x:.2f} min<extra></extra>` });
    }
    for (const s of SOURCE_SERIES) {
      const ser = data.series[s.key];
      traces.push({ type: "bar", name: s.name, x: data.centers, y: ser.inside, width: w,
        marker: { color: s.color, line: { color: s.color, width: 0.5 } }, opacity: 0.85,
        hovertemplate: `%{y} ${s.name} samples<br>%{x:.2f} min<extra></extra>` });
    }
    const layout = {
      barmode: "stack", bargap: 0.05,
      margin: { l: 48, r: 12, t: 6, b: 46 },
      paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
      font: { size: 12, color: INK },
      // The same quantity under every direction setting: each neural sample's signed distance to
      // its NEAREST pain report. The direction toggle changes which bars are coloured, not the axis.
      xaxis: { title: { text: `minutes between each neural sample and its nearest ${metricLabel || "pain"} report (negative: the sample came first)`, font: { size: 12 } },
        range: [-lim, lim], gridcolor: GRID, zeroline: false, fixedrange: false },
      yaxis: { title: { text: "neural samples", font: { size: 12 } }, gridcolor: GRID, zeroline: false, rangemode: "tozero" },
      shapes: [
        { type: "rect", xref: "x", yref: "paper", x0: data.priorOnly ? -W : -W, x1: data.priorOnly ? 0 : W, y0: 0, y1: 1,
          fillcolor: BAND, line: { width: 0 }, layer: "below" },
        { type: "line", xref: "x", yref: "paper", x0: 0, x1: 0, y0: 0, y1: 1, line: { color: INK, width: 1.5 } },
        { type: "line", xref: "x", yref: "paper", x0: -W, x1: -W, y0: 0, y1: 1, line: { color: INK, width: 1, dash: "dot" } },
        { type: "line", xref: "x", yref: "paper", x0: W, x1: W, y0: 0, y1: 1, line: { color: INK, width: 1, dash: "dot" } },
      ],
      legend: { orientation: "h", x: 0, y: 1.14, font: { size: 12 } },
      uirevision: "timing-histogram",
    };
    Plotly.react(ref.current, traces, layout, { displaylogo: false, responsive: true,
      modeBarButtonsToRemove: ["select2d", "lasso2d", "toImage"] });
  }, [offsets, data, metricLabel]);

  // Purge on unmount only (never in a per-run cleanup): see BinarizationPreview's own note.
  useEffect(() => {
    const node = ref.current;
    return () => { if (node) Plotly.purge(node); };
  }, []);

  const dirText = data.priorOnly ? " on the side before the report" : "";
  const reportFirstNote = String(matchDirection || "").toLowerCase() === "pro_first"
    ? " Under Report-first matching a sample whose nearest report has already reached its cap can be paired with another report inside the window; the histogram places every sample by its nearest report."
    : "";
  return (
    <MDBox display="flex" flexDirection="column" gap={0.5}>
      <div ref={ref} style={{ width: "100%", height }} data-testid="timing-histogram" />
      <MDTypography variant="caption" color="dark" sx={{ fontSize: 12.5 }} aria-live="polite">
        {offsets.length
          ? `Sources: time domain (TD), band power from up to 30 s of a streaming or a montage recording around the rating; PSD (the device's 30 s snapshot), from a patient event. ${data.nInside.toLocaleString()} samples inside ±${data.windowMin} min${dirText}; ${data.nTails.toLocaleString()} in the greyed tails (to ±${data.limMin} min). Grey also marks any side the direction setting excludes. A TD sample whose report falls inside its recording is stamped at the report's own time, so it sits at 0.${reportFirstNote}`
          : "No neural samples to place against the pain reports yet."}
      </MDTypography>
    </MDBox>
  );
}
