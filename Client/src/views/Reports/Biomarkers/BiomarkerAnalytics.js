/**
 * BiomarkerAnalytics -- the "Correlation over time (sliding window)" section of the Biomarkers page:
 * one heat map per sensing contact of the band-power/pain correlation (r) by frequency and window
 * start, drawn only when the request ran in sliding mode (`analytics.timedomain.sliding_corr_spectrum`).
 *
 * This file once held the notebook-derived chronic / power-domain section as well (ROC, honest
 * performance bars, power distribution, sliding-window performance, power-vs-pain scatter, the
 * per-band binarization preview). The PI removed that section from the page on 2026-06-28, the
 * exploratory 5 Hz scan went at decision 77 and its stability cluster at decision 80 -- but the six
 * builders and the channel-selection machinery they read stayed in this file, building panels the
 * component never returned. They were deleted on 2026-09-15 (referent audit, item 8) after a grep
 * confirmed no other reader. The calibrated band-by-length grids (`BiomarkerHeatmapGrids.js`) are
 * the headline result and the binarization preview card at the top of the page shows the split.
 * Self-contained via plotly.js-dist.
 */

import { useEffect, useRef } from "react";
import Plotly from "plotly.js-dist";

import { Card, Grid } from "@mui/material";
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

/**
 * The generic figure wrapper the analytics panels draw through.
 *
 * TWO THINGS HERE WERE DESTROYING THE READER'S VIEW ON EVERY RENDER, and both are fixed below
 * rather than at the call sites (nine when this was written; one since 2026-09-15).
 *
 * The first is that every caller passes its `layout` as an object literal written inline in the
 * markup, so a new object identity arrives on every render of the surrounding panel even when
 * nothing about the figure has changed. That object is in this effect's dependency list, so the
 * effect re-ran on every render — and its cleanup, which ran before each of those redraws as well
 * as on unmount, destroyed the graph with `Plotly.purge` and built it again from nothing. Any zoom,
 * pan or legend selection went with it. Moving a slider elsewhere on the page was enough.
 *
 * The purge now happens ONLY when the figure really goes away, which is what it is for: releasing
 * the graph's event handlers and its rendering context. `Plotly.react` is a diff against what is
 * already drawn, so re-running the effect redraws in place instead of rebuilding.
 *
 * The second is that `Plotly.react` keeps the reader's interactions only when the layout carries an
 * unchanged `uirevision`, and this base layout carried none — so even an in-place redraw reset the
 * axes to autorange. A constant revision string is added below, the same mechanism and the same
 * reasoning as the scan figure further down this file.
 *
 * Rebuilding the layout objects at the call sites still costs a redraw diff on every render, which
 * is work that could be avoided by memoising them. That is a performance question rather than a
 * correctness one, and it is left as a follow-up.
 */
function Fig({ traces, layout = {}, height = 320 }) {
  const ref = useRef(null);
  // Purge on unmount only. The node is read at cleanup time rather than captured, because this
  // effect never re-runs and the ref must be the one that is current when the figure goes away.
  useEffect(() => () => { if (ref.current) Plotly.purge(ref.current); }, []);
  useEffect(() => {
    if (!ref.current || !traces || traces.length === 0) return;
    const base = {
      ...FIG_BASE, autosize: true, height,
      // A constant revision string, so Plotly carries the reader's zoom, pan and legend choices
      // across redraws. It is spread BEFORE the caller's layout so that a caller with a genuine
      // reason to force a reset can still set its own.
      uirevision: "biomarker-analytics-figure",
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
    // No cleanup here on purpose: see the note above the component. Purging on each redraw is what
    // was throwing away the reader's zoom, pan and legend state.
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
        {/* Section header at ~2x the prior size for clear hierarchy between TD / power-domain.
            The MUI h3 variant ships a line-height TIGHTER than this bumped-up 40px fontSize, so the
            first line's ascenders/caps were clipped at the top until a zoom forced a reflow. Set an
            explicit lineHeight (1.3) ≥ the font box and a little top padding so the glyphs always
            have room and the title renders fully at default zoom. */}
        <MDTypography variant="h3" fontWeight="bold"
          sx={{ fontSize: 40, lineHeight: 1.3, pt: 0.5, overflow: "visible" }}>{title}</MDTypography>
        {subtitle ? <MDTypography variant="body2" color="dark">{subtitle}</MDTypography> : null}
      </MDBox>
      <Grid container spacing={3}>
        {header}
        {panels}
      </Grid>
    </Grid>
  );
}

export default function BiomarkerAnalytics({ analytics, metricLabel }) {
  if (!analytics) return null;
  const td = analytics.timedomain || {};
  // Human-readable pain score these correlations are computed against (every correlation panel
  // should say what it is correlated WITH). Falls back gracefully.
  const pain = metricLabel || "pain";

  const tdPanels = [];
  const scs = td.sliding_corr_spectrum || null;
  if (scs && scs.channels && scs.channels.length) {
    scs.channels.forEach((ch, i) => {
      if (!Array.isArray(ch.freqs) || !ch.freqs.length) return;   // skip channels with no freq axis
      const traces = [{ type: "heatmap", z: ch.r, x: ch.window_starts, y: ch.freqs,
        colorscale: "RdBu", reversescale: true, zmid: 0, zmin: -1, zmax: 1,
        colorbar: { title: { text: "R", side: "right" }, thickness: 12, len: 0.9 },
        hovertemplate: "%{x|%b %d %Y} · %{y:.1f} Hz · R=%{z:.2f}<extra></extra>" }];
      // 50 Hz biomarker cap: never display a sliding-correlation axis above 50 Hz.
      const fLo = Math.min(...ch.freqs);
      tdPanels.push(
        <Panel key={"scs" + i} lg={12}
          title={`Sliding correlation with ${pain} (R: frequency × time) — ${ch.channel}`}>
          <Fig traces={traces} height={360}
            layout={{ xaxis: { title: "Window start", type: "date" },
              yaxis: { title: "Frequency (Hz)", range: [Number.isFinite(fLo) ? fLo : 0, 50] } }} />
        </Panel>
      );
    });
  }

  if (tdPanels.length === 0) return null;

  return (
    <Section title="Correlation over time (sliding window)"
             subtitle="How the band-power/pain correlation for each frequency has shifted across sliding windows of the record."
             panels={tdPanels} />
  );
}
