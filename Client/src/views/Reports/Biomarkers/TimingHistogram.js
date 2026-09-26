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

import { T, TYPE } from "assets/theme/base/tokens";
import { plotlyLayout, REF_LINE } from "views/Reports/figureStyle";

import { SOURCE_SERIES, TAIL_GREY, sampleOffsetsMin, timingHistogramData } from "./timingHistogramModel";

// 2026-09-26 redesign (SPEC.md section 3): the shared figure defaults, no gridlines; the window
// is a pale band, the report's own time a solid ink line, the window's edges dashed reference
// lines. The series are named in a key under the figure, in ink beside a colour swatch, rather
// than in a legend box on the canvas. The zoom/pan toolbar this figure carried before the
// redesign, briefly taken off by it, was restored by the PI the same day.

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
    const layout = plotlyLayout({
      barmode: "stack", bargap: 0.05,
      margin: { l: 56, r: 16, t: 8, b: 48 },
      // The same quantity under every direction setting: each band-power reading's signed distance
      // to its NEAREST pain report. The direction toggle changes which bars are coloured, not the axis.
      xaxis: { title: { text: `minutes from each band-power reading to its nearest ${metricLabel || "pain"} report (negative: the reading came first)` },
        range: [-lim, lim], fixedrange: false },
      yaxis: { title: { text: "band-power readings" }, rangemode: "tozero" },
      shapes: [
        { type: "rect", xref: "x", yref: "paper", x0: -W, x1: data.priorOnly ? 0 : W, y0: 0, y1: 1,
          fillcolor: T.fillMuted, line: { width: 0 }, layer: "below" },
        { type: "line", xref: "x", yref: "paper", x0: 0, x1: 0, y0: 0, y1: 1, line: { color: T.ink, width: 1.5 } },
        { type: "line", xref: "x", yref: "paper", x0: -W, x1: -W, y0: 0, y1: 1, line: REF_LINE },
        { type: "line", xref: "x", yref: "paper", x0: W, x1: W, y0: 0, y1: 1, line: REF_LINE },
      ],
      uirevision: "timing-histogram",
    });
    // This figure has carried a zoom/pan toolbar since before the redesign (no save-as-PNG button
    // on it); the PI restored it 2026-09-26 to its own old shape after the redesign took it off.
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
    ? " When each report picks its nearest recordings, a sample whose nearest report has already reached its cap can be paired with another report inside the window; the histogram places every sample by its nearest report."
    : "";
  return (
    <MDBox display="flex" flexDirection="column" gap={0.5}>
      {/* With nothing to place, the figure's space collapses to the one sentence below (taste
          audit C2, 2026-09-26); the div stays mounted, at no height, for Plotly. */}
      <div ref={ref} style={{ width: "100%", height: offsets.length ? height : 0 }}
        data-testid="timing-histogram" data-empty={offsets.length ? "false" : "true"} />
      {offsets.length ? (
      <MDBox component="p" m={0} sx={{ ...TYPE.caption, color: T.ink }}>
        {SOURCE_SERIES.map((s, i) => (
          <span key={s.key}>
            {i > 0 ? " \u00b7 " : ""}
            <span aria-hidden="true" style={{ display: "inline-block", width: 10, height: 10, marginRight: 4,
              background: s.color, verticalAlign: "baseline" }} />
            {s.name}
          </span>
        ))}
        <span>{" \u00b7 "}</span>
        <span aria-hidden="true" style={{ display: "inline-block", width: 10, height: 10, marginRight: 4,
          background: TAIL_GREY, verticalAlign: "baseline" }} />
        {"outside the window"}
      </MDBox>
      ) : null}
      <MDTypography variant="caption" sx={{ ...(offsets.length ? TYPE.caption : TYPE.body), color: T.ink3 }}
        aria-live="polite" data-testid="timing-histogram-caption">
        {offsets.length
          ? `Sources: time domain (TD), band power from up to 30 s of a streaming or a montage recording around the rating; PSD (the device's 30 s snapshot), from a patient event. ${data.nInside.toLocaleString()} samples inside ±${data.windowMin} min${dirText}; ${data.nTails.toLocaleString()} in the greyed tails (to ±${data.limMin} min). Grey also marks any side the direction setting excludes. A TD sample whose report falls inside its recording is stamped at the report's own time, so it sits at 0.${reportFirstNote}`
          : "No band-power readings to place against the pain reports yet; this histogram appears once the recordings and the pain reports have both loaded."}
      </MDTypography>
    </MDBox>
  );
}
