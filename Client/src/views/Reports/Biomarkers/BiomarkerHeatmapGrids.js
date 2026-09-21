/**
 * THE TWO CALIBRATED HEAT MAPS, AS THE HEADLINE OF THE PAGE (Track A of the heat-map redesign,
 * redrawn in Plotly for open item 7's display cleanup).
 *
 * Builds Option 2, "search-first, minimal chrome" (decision 62 in DECISIONS_and_open_items.md):
 * no cell is pre-selected on load, hovering a cell highlights it on both grids at once, clicking
 * pins a persistent scatter/violin panel beside each grid, and the sensing contact pair is chosen
 * from a strip of small thumbnail grids rather than a dropdown.
 *
 * WHY THIS COMPONENT FETCHES ON ITS OWN, ON MOUNT, RATHER THAN WAITING FOR A BUTTON. The PRD's
 * complaint was that the calibrated grid used to be gated behind the older full-spectrum scan
 * having already run. `requestParams` here is built by the parent from the LIVE top-of-page
 * controls (see `heatmapRequestParams` in index.js) rather than from the older routine's
 * click-triggered snapshot, so the very first render already has something to ask for and the
 * request fires without any button press.
 *
 * WHY THE TWO GRIDS ARE TRACKED AS TWO SEPARATE DISPLAYED RESULTS. The correlation grid depends
 * only on how pain reports are matched to recordings; the AUC grid depends on that AND on the
 * binarization cuts (PRD §3). One server call always returns both together, so the asymmetry has
 * to be made up for on this side: when only the binarization settings changed since the last
 * fetch, the freshly fetched correlation numbers are thrown away in favour of keeping the
 * PREVIOUS correlation grid on screen (they are the same numbers up to floating point, since
 * correlation does not read the binarization settings at all, but re-assigning the object identity
 * would make its frame redraw, which is exactly the behaviour the design says must NOT happen),
 * while the AUC grid is replaced and briefly highlighted. When the matching settings changed
 * (or this is the very first fetch), both grids are replaced.
 *
 * A single fetch already returns every sensing contact pair's grid at once
 * (`bravo_service._band_time_sweep_channels` loops over every channel in one call), so the
 * small-multiples strip costs nothing extra: it is drawn straight from the one response already
 * held, never a separate request per thumbnail.
 *
 * PLOTLY, NOT HAND-ROLLED SVG, FOR THE TWO BIG GRIDS -- a deliberate reversal of decision 66's
 * choice, on the PI's own direct instruction. Decision 66 chose SVG specifically because "the
 * existing figures were never built to carry per-cell hover and click" at the time; this
 * project's own Plotly render manager (`graphing-utility/Plotly`) has since grown native
 * `plotly_click`/`plotly_hover` event support elsewhere, so that original constraint no longer
 * rules Plotly out. The two per-cell side panels (scatter+fit line, violin) stay hand-rolled SVG:
 * they are single, non-gridded plots with no per-cell hit-testing problem to solve, and the
 * existing SVG code for them already worked well.
 */
import { useEffect, useMemo, useRef, useState } from "react";

import { Card, Grid, CircularProgress, Collapse, IconButton } from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import MDButton from "components/MDButton";

import Plotly from "plotly.js-dist";
import { PlotlyRenderManager } from "graphing-utility/Plotly";
import { SessionController } from "database/session-control";
import { useCachedResult } from "database/useCachedResult";
import { biomarkerHeatmapSlot, prefetchBiomarkerHeatmapMetric } from "views/Reports/moduleCacheKeys";
import PAL from "views/Reports/ClosedLoopSim/palette";
import { BIN_HI, BIN_LO, BIN_HI_RGB, BIN_LO_RGB, divergingRgb, diverging } from "./binarizationModel";
import { contactSortKey } from "./contactOrder";
import { bestCellReadout, cellNP, fmtP, hoverCustomData, tierBullets, deviceSpectrumBullets, stabilityMark, stabilityBullet, clinicSheetBullets } from "./gridReadouts";

const num = (v, d = 3) => (v == null || !Number.isFinite(Number(v)) ? "—" : Number(v).toFixed(d));

// COLOUR: the diverging scale lives in binarizationModel.js (one definition, shared with the
// Closed-Loop page's band heat map since 2026-09-11).
// A fixed-stop colorscale Plotly can interpolate continuously between, built from the same two
// Okabe-Ito colours as every other diverging scale on this page (BIN_LO/BIN_HI) so this grid does
// not introduce a third, uncoordinated colour convention.
function divergingColorscale(center, halfRange) {
  const stops = [-1, -0.5, 0, 0.5, 1];
  return stops.map((t) => {
    const v = center + t * halfRange;
    const c = divergingRgb(v, center, halfRange);
    return [(t + 1) / 2, `rgb(${c.map((x) => Math.round(x)).join(",")})`];
  });
}

/** Which grid cell (row = length of signal, column = band centre) is the "best" one the server
 * already picked for that column, so a family-wise marker can be drawn on the right cell. */
function bestCellIndexByColumn(sw, rows) {
  const out = {};
  const centers = sw.center_freqs_hz || [];
  const delivered = sw.integration_seconds_delivered || [];
  (rows || []).forEach((r) => {
    const c = centers.findIndex((cc) => Math.abs(cc - r.band_center_hz) < 1e-6);
    if (c < 0) return;
    const ri = delivered.findIndex((d) => Math.abs(d - r.integration_seconds_delivered) < 1e-6);
    if (ri < 0) return;
    out[c] = { row: ri, row_data: r };
  });
  return out;
}

/** "9s", "1m" -- the DELIVERED length of signal a row actually holds (see the note on `seconds`
 * below for why this is delivered, not requested). */
function secondsLabel(s) {
  return Number(s) >= 60 ? `${Math.round(Number(s) / 60)}m` : `${Number(s).toFixed(0)}s`;
}

/** The one formula for a heat map's pixel height, given its row count -- used by `PlotlyHeatmap`
 * itself AND by the side panels (which must match it exactly, since they sit in the same Grid row)
 * so the two can never drift out of sync the way they did once already when the heat maps were
 * enlarged 25% but the panel height formula was a separate, duplicated literal. */
function heatmapHeight(rows) {
  return Math.max(225, rows * 25 + 75);
}

/** The "how to read this" drawer's bullet text, in priority order (open item 7, decision
 * 2026-09-09): the backend's own first three notes (best-of-ten selection bias, what 0.5 means,
 * direction/folding -- the two the PI made non-negotiable plus the direction note, which the
 * backend now emits already grouped together), then the two display-only notes readers need most
 * (the circled-cell correction, why the left grid doesn't redraw), then the single-cell-statistic
 * caveat, then the backend's remaining mechanical notes (tile rounding, cell independence,
 * outliers, the shuffled reference, the split rule). Only `corrSw.notes` is read -- `aucSw.notes`
 * is never different (both grids share one per-channel sweep response), so reading both and
 * concatenating them, as this drawer used to, only doubled every bullet for no reason. */
// THE L 1-3+ SEARCH (the PI, 2026-09-21): a one-off exploratory search over every setting of the
// matching knobs on RCS08's L 1-3+ (the one left-side pair the sensing rule allows), Left Leg VAS,
// the page's own grid routine with its full shuffles and resamples (the table is in the scratch
// area, `_l13_search_left_leg_vas.csv`). Its headline lines are printed in bold at the top of the
// "How to read this" drawer, for RCS08 only: they are a finding about one record, not a rule.
export const L13_SEARCH_UID = "2e3c75c00d7f4f37b53a048d195f11da";
export const L13_SEARCH_LINES = [
  "Exploratory search, 2026-09-21, L 1\u207b3\u207a on Left Leg VAS: 252 settings (windows 2, 5, 10, 20, 30, 60, 120 min; "
    + "Report-first, Neural-first, Neural-first pre-report; cap 1, 3, 10 per rating; reuse on/off; clinic sheets on/off).",
  "No band rises with pain past the 22-band correction under any setting: 0 positive rows with q < 0.05 out of 5,544.",
  "Sheets off (REDCap only): the only cell to reach the grid\u2019s \u201cestablished\u201d verdict is 24.5 Hz at 60 s, "
    + "120-min window, Neural-first pre-report: r 0.33 (0.17 to 0.48), n 59, q 0.23. 21.5\u201325.5 Hz (mostly 23.5) "
    + "come out \u201csupported\u201d in 1\u20138 settings per window, the same count the negative side reaches by chance.",
  "Sheets on (+ clinic titration scores): the positive cluster vanishes and 11\u201322 of 22 bands per setting fall with pain, "
    + "1,545 rows with q < 0.05 on the negative side, all with the sheets in. The titration scores carry a strong "
    + "negative pain\u2013power relationship that the chronic record does not.",
  "Read as a lead for the next titration session (24.5 Hz, 60 s), not a band to program.",
];

function bulletsFor(sw) {
  // Concise since 2026-09-15 (the PI). The backend's own notes are already short; the three
  // display-only bullets say one thing each; the snapshot bullet is gone from here because the
  // orange caption above the grid already carries it (say a small point once).
  const notes = sw.notes || [];
  return [
    ...notes.slice(0, 3),
    "A white circle marks each column's best cell; a heavy ring also clears the 22-band correction "
      + "\u2014 a research finding, not a device-ready setting.",
    "The left grid ignores the binarization cuts (a continuous score has no split); the right grid "
      + "recomputes and flashes.",
    "Clicking a cell shows its plain, uncorrected Pearson r/p and Mann-Whitney p \u2014 not the grid's corrected numbers.",
    ...notes.slice(3),
  ];
}

// The two side panels print each cell's own uncorrected statistics -- Pearson r with its p, the
// AUC with its Mann-Whitney p -- READ OFF THE GRID RESPONSE (`p_grid`, `auc_p_grid`, decision 188).
// Nothing statistical is computed in the browser any more; the t-test and the incomplete-beta
// machinery decision 87 wrote here are gone (the PI, 2026-09-16: "Get rid of the t-test code").

/**
 * ONE HEAT MAP, IN PLOTLY. Row 0 is the shortest length of signal (top of the grid, matching the
 * previous SVG's layout); the y-axis is CATEGORICAL (string labels), not numeric, so every row
 * gets equal visual height regardless of how far apart the underlying seconds values actually are
 * -- exactly the same "equal cell size, irregular tick labels" layout the SVG version drew, now
 * built the way Plotly expects it. Highlighting (hover/pinned) is drawn as a second, tiny
 * scatter trace holding one square-outline marker at the highlighted cell's own data coordinates,
 * rather than a raw shape indexed by row/col -- data coordinates are unambiguous regardless of
 * axis type, where a shape positioned by category index is not.
 */
function PlotlyHeatmap({ divId, sw, kind, hoveredCell, pinnedCell, onHover, onClick, flashKey,
  width = 750, deviceRanges = null }) {
  const centers = useMemo(() => sw.center_freqs_hz || [], [sw]);
  // DELIVERED, not requested, for the axis LABEL -- see the module-level note. (The cell
  // drill-down request must still send the REQUESTED value; that happens in the parent, not here.)
  const seconds = useMemo(
    () => sw.integration_seconds_delivered || sw.integration_seconds_requested || [], [sw]);
  const grid = kind === "auc" ? sw.auc_grid : sw.correlation_grid;
  const rows = (grid || []).length;
  const cols = centers.length;
  const center = kind === "auc" ? 0.5 : 0;
  const halfRange = kind === "auc" ? 0.5 : 1;
  const bestRows = kind === "auc" ? sw.best_auc_rows : sw.best_correlation_rows;
  const bestByCol = useMemo(() => bestCellIndexByColumn(sw, bestRows), [sw, bestRows]);

  // Plain lengths of signal on the axis (the PI, 2026-09-15: nothing appended -- which rows the
  // device can be set to is said once, in the caption's bullets).
  const yLabels = useMemo(() => seconds.map((s) => secondsLabel(s)), [seconds]);
  // Review 2026-09-15, B1: the corrected statistics for each column's best cell, on hover.
  const customdata = useMemo(() => hoverCustomData(sw, kind === "auc" ? "auc" : "corr"), [sw, kind]);
  // Sized 25% larger than the first Plotly pass, per the PI's own comparison against the size
  // before this redesign.
  const height = heatmapHeight(rows);

  const figRef = useRef(null);
  const [flash, setFlash] = useState(false);
  useEffect(() => {
    if (!flashKey) return undefined;
    setFlash(true);
    const t = setTimeout(() => setFlash(false), 900);
    return () => clearTimeout(t);
  }, [flashKey]);

  // Trace 2 (the cross-highlight) is ALWAYS present, even with empty x/y when nothing is active,
  // so its index never shifts -- the second effect below can restyle it directly by index without
  // touching trace 0 (the heatmap) or trace 1 (the best-cell markers).
  const HIGHLIGHT_TRACE = 3;   // heatmap 0, best-cell circles 1, stability symbols 2 (decision 185)

  useEffect(() => {
    if (!rows || !cols) return undefined;
    if (!figRef.current) figRef.current = new PlotlyRenderManager(divId, "en");
    const fig = figRef.current;
    fig.clearData();
    // Populates this.layout.xaxis/yaxis from the manager's own defaults -- required before
    // setXlabel/setYlabel below can touch them (they assume subplots() has already run, the same
    // as every other consumer of this class in the codebase).
    fig.subplots(1, 1, { sharex: false, sharey: false });
    fig.traces.push({
      type: "heatmap", z: grid, x: centers, y: yLabels,
      colorscale: divergingColorscale(center, halfRange), zmin: center - halfRange,
      zmax: center + halfRange, zmid: center, showscale: false,
      xgap: 1.5, ygap: 1.5,
      customdata,
      hovertemplate: `${kind === "auc" ? "AUC" : "r"} = %{z:.3f}<br>%{x} Hz, %{y}<br>%{customdata}<extra></extra>`,
    });
    // A WHITE circle on every column's best cell (the PI, 2026-09-15: "use a white circle for the
    // relevant values on top of the relevant cell" -- the hover's "(1m circled)" points at it), a
    // heavier ring where that cell also clears the 22-band correction. Until today only the
    // corrected cells carried a marker, in dark ink, so "circled" often pointed at nothing.
    const bestX = [], bestY = [], bestW = [];
    Object.keys(bestByCol).forEach((c) => {
      const b = bestByCol[c];
      if (!b) return;
      bestX.push(centers[Number(c)]); bestY.push(yLabels[b.row]);
      bestW.push(b.row_data && b.row_data.family_wise_significant_8_to_30hz === true ? 3 : 1.4);
    });
    fig.traces.push({
      type: "scatter", mode: "markers", x: bestX, y: bestY, showlegend: false,
      marker: { symbol: "circle-open", size: 14, color: "#FFFFFF", line: { width: bestW, color: "#FFFFFF" } },
      hoverinfo: "skip",
    });
    // B3 (decision 185): inside each column's circle, the cross-setting stability answer -- the
    // Closed-Loop card's own symbol (green tick, red cross, amber disc), nothing where the answer
    // is not known yet. Read off the best row's `cross_setting_stability`, which the backend
    // attaches from the store at request time. Trace index STABILITY_TRACE, before the highlight.
    const stX = [], stY = [], stSym = [], stCol = [];
    Object.keys(bestByCol).forEach((c) => {
      const b = bestByCol[c];
      const m = b && b.row_data ? stabilityMark(b.row_data.cross_setting_stability) : null;
      if (!m) return;
      stX.push(centers[Number(c)]); stY.push(yLabels[b.row]); stSym.push(m.symbol); stCol.push(m.color);
    });
    fig.traces.push({
      type: "scatter", mode: "markers", x: stX, y: stY, showlegend: false,
      marker: { symbol: stSym, size: 7, color: stCol, line: { width: 1.5, color: stCol } },
      hoverinfo: "skip",
    });
    // The shared cross-highlight, trace index HIGHLIGHT_TRACE -- always pushed, empty until the
    // second effect below fills it in via restyle. Keeping it here (rather than only when active)
    // is what fixes the highlight trace's index in place across every redraw this effect causes.
    fig.traces.push({
      type: "scatter", mode: "markers", x: [], y: [], showlegend: false,
      marker: { symbol: "square-open", size: 22, color: "#1a1a1a", line: { width: 2 } },
      hoverinfo: "skip",
    });
    // The per-cell dash markers for snapshot-served reports (decision 106) were REMOVED on
    // 2026-09-10 at the PI's direction ("the caption in orange below the title is sufficient");
    // the snapshot route now honours the length axis (decision 121), so there is no frozen column
    // to mark. Nothing else is pushed after the highlight trace, whose index is restyled below.
    // Every 3rd band centre, exactly the sparse labelling the original SVG grid used (too many of
    // the 22 centres to label all of them without the text overlapping).
    const xTickVals = centers.filter((c, i) => i % 3 === 0);
    const xTickText = xTickVals.map((c) => Number(c).toFixed(0));
    fig.setLayoutProps({
      height, width, margin: { l: 46, r: 8, t: 8, b: 40 },
      // No gridlines (the cell borders via xgap/ygap already separate the cells), no axis line,
      // no tick marks (`ticks: ""`) on either axis -- floating labels only. The x-axis also
      // replaces Plotly's own automatic tick choice with an explicit array so it labels a real
      // band centre every 3rd column, matching the y-axis's one-label-per-row convention instead
      // of whatever round numbers Plotly would have picked on its own.
      xaxis: { showgrid: false, zeroline: false, showline: false, ticks: "",
        tickmode: "array", tickvals: xTickVals, ticktext: xTickText },
      yaxis: { type: "category", autorange: "reversed", showgrid: false, zeroline: false,
        showline: false, ticks: "" },
      hovermode: "closest",
    });
    fig.setXlabel("Band centre (Hz)", { fontSize: 12 });
    fig.setYlabel("Length of signal", { fontSize: 12 });
    fig.render();
    // `fig.render()` always shows the hover-activated modebar (zoom/pan/download icons) with its
    // own hardcoded config -- `PlotlyRenderManager` has no override for that, and it is a shared
    // class used by many other pages, so it is not changed here. Instead this one call re-applies
    // the SAME data/layout the render manager just drew, but with the modebar switched off, scoped
    // only to these two heat maps.
    Plotly.react(divId, fig.traces, fig.layout,
      { displayModeBar: false, responsive: true, doubleClick: false });

    const el = document.getElementById(divId);
    if (el) {
      el.on("plotly_hover", (evt) => {
        const p = evt.points && evt.points[0];
        if (p && p.curveNumber === 0 && Array.isArray(p.pointNumber)) {
          onHover(p.pointNumber[0], p.pointNumber[1]);
        }
      });
      el.on("plotly_unhover", () => onHover(null, null));
      el.on("plotly_click", (evt) => {
        const p = evt.points && evt.points[0];
        if (p && p.curveNumber === 0 && Array.isArray(p.pointNumber)) {
          onClick(p.pointNumber[0], p.pointNumber[1]);
        }
      });
    }
    return () => {
      if (el) { el.removeAllListeners("plotly_hover"); el.removeAllListeners("plotly_unhover");
        el.removeAllListeners("plotly_click"); }
    };
    // Deliberately NOT keyed on hoveredCell/pinnedCell -- see the effect below and the comment on
    // `HIGHLIGHT_TRACE` above for why (this used to rebuild the whole figure, tear down and
    // reattach the click listener, on every single hover movement across the grid).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [divId, grid, centers, yLabels, kind, center, halfRange, bestByCol, height, width]);

  // The cross-highlight alone, kept in its own effect and updated with `Plotly.restyle` (which
  // touches only the one named trace, not the whole figure) so that moving the mouse across the
  // grid never tears down and reattaches the plotly_click listener the effect above sets up.
  // That teardown-on-hover was the actual cause of the click-sometimes-needs-two-tries bug: a real
  // mouse glides across several cells before landing on the one to click, firing several hover
  // events -- each of which, under the old single-effect version, rebuilt the whole plot (and its
  // listeners) via `Plotly.react`; if that rebuild landed between the click's mousedown and
  // mouseup, Plotly had nothing listening for the click's mouseup and the click was dropped.
  useEffect(() => {
    if (!rows || !cols) return undefined;
    const el = document.getElementById(divId);
    if (!el || !el.data || el.data.length <= HIGHLIGHT_TRACE) return undefined;
    const activeCell = pinnedCell || hoveredCell;
    const active = activeCell && activeCell.row < rows && activeCell.col < cols;
    try {
      Plotly.restyle(divId, {
        x: [active ? [centers[activeCell.col]] : []],
        y: [active ? [yLabels[activeCell.row]] : []],
        "marker.line.width": [pinnedCell ? 3 : 2],
      }, [HIGHLIGHT_TRACE]);
    } catch (e) {
      // Swallowed: the div passed the existence/trace-count check just above, but Plotly's own
      // click/double-click pipeline can still tear it down between that check and this call (the
      // same underlying issue the purge-cleanup guard above documents) -- a missed highlight
      // redraw is a cosmetic no-op, not worth crashing the page over.
    }
    return undefined;
  }, [divId, hoveredCell, pinnedCell, rows, cols, centers, yLabels]);

  useEffect(() => () => {
    // Guarded: Plotly'''s own .purge() throws (uncaught, since this runs in an effect cleanup with
    // no React error boundary anywhere in this app) if the div it manages is already gone from the
    // DOM -- observed live on a native double-click, which Plotly'''s own internal click pipeline
    // can apparently unmount/rebuild around even with the built-in reset-on-dblclick action turned
    // off (doubleClick: false, set on the Plotly.react calls below). Checking first makes this
    // cleanup robust to that regardless of why the div is already gone, rather than chasing the
    // exact internal Plotly sequence that removes it.
    if (figRef.current && document.getElementById(divId)) figRef.current.purge();
  }, [divId]);

  if (!rows || !cols) {
    return (
      <MDTypography variant="caption" color="dark" fontStyle="italic" sx={{ fontSize: 11.5 }}>
        {"No grid could be computed for this contact pair."}
      </MDTypography>
    );
  }

  return (
    <MDBox
      sx={flash ? {
        outline: `2px solid ${PAL.accentBorder || "#0072B2"}`,
        borderRadius: 1,
        transition: "outline-color 0.15s",
      } : { outline: "2px solid transparent", borderRadius: 1 }}
    >
      <div id={divId} style={{ width: "100%", maxWidth: width }} />
    </MDBox>
  );
}

// Left-then-right contact ordering: contactOrder.js (shared with the Closed-Loop page's band
// heat map since 2026-09-11).
/** A small strip of thumbnail correlation grids, one per sensing contact pair, all drawn from the
 * one response already held -- clicking a thumbnail is what chooses the contact pair for the two
 * big grids below (Option 2's replacement for a dropdown, task A3). */
function ContactStrip({ sweeps, channel, setChannel }) {
  const names = Object.keys(sweeps || {}).sort((a, b) => {
    const ka = contactSortKey(a, sweeps[a]);
    const kb = contactSortKey(b, sweeps[b]);
    return (ka[0] - kb[0]) || (ka[1] - kb[1]);
  });
  if (names.length <= 1) return null;
  return (
    <MDBox display="flex" flexDirection="row" flexWrap="wrap" gap={1.25} mb={1.5}>
      {names.map((ch) => {
        const sw = sweeps[ch];
        const active = ch === channel;
        const grid = sw && sw.correlation_grid;
        const rows = (grid || []).length;
        const cols = (sw && sw.center_freqs_hz && sw.center_freqs_hz.length) || 0;
        // Medtronic-style label ("L 0⁻2⁺ (Left GPi)"), matching the "Recorded power channels"
        // convention elsewhere on this page -- built server-side (bravo_service._band_time_sweep_
        // channels via analytics.format_channel), never re-derived from the raw key here. Falls
        // back to the raw key only if an older, unlabeled cached response is served.
        const label = (sw && sw.display_short)
          ? (sw.display_region ? `${sw.display_short} (${sw.display_region})` : sw.display_short)
          : ch.replace(/_/g, " ");
        return (
          <MDBox key={ch} onClick={() => setChannel(ch)}
            sx={{
              cursor: "pointer", border: active ? `2.5px solid #1a1a1a` : "1.5px solid #ccc",
              borderRadius: 1.5, p: 0.5, background: "#fff",
              boxShadow: active ? "0 0 0 2px rgba(0,0,0,0.08)" : "none",
            }}>
            <MDTypography variant="caption" fontWeight={active ? "bold" : "medium"} color="dark"
              sx={{ fontSize: 10.5, display: "block", textAlign: "center" }}>
              {label}
            </MDTypography>
            {rows && cols ? (
              <svg width={92} height={46}>
                {grid.map((row, r) => row.map((v, c) => (
                  <rect key={`${r}-${c}`} x={(c / cols) * 92} y={(r / rows) * 46}
                    width={92 / cols + 0.5} height={46 / rows + 0.5}
                    fill={diverging(v, 0, 1)} />
                )))}
              </svg>
            ) : (
              <MDBox sx={{ width: 92, height: 46, background: "#f2f2f2" }} />
            )}
          </MDBox>
        );
      })}
    </MDBox>
  );
}

/** The high/low violin comparison as a native Plotly `violin` trace, rendered through this
 * project's own `PlotlyRenderManager` -- the same wrapper `PlotlyHeatmap` above already uses.
 * Passing `responsive: true` to `Plotly.react` (exactly as `PlotlyHeatmap` does) hands the resize
 * job to Plotly itself: it measures the actual rendered size of the `<div>` below and redraws to
 * fill it, on mount and on every window/layout resize, which is the genuine "auto-resize to fill
 * the panel" behaviour a hand-measured SVG (the previous approach) could only approximate. */
function PlotlyViolin({ divId, highVals, lowVals, side }) {
  const figRef = useRef(null);
  useEffect(() => {
    if (!highVals.length && !lowVals.length) return undefined;
    if (!figRef.current) figRef.current = new PlotlyRenderManager(divId, "en");
    const fig = figRef.current;
    fig.clearData();
    fig.subplots(1, 1, { sharex: false, sharey: false });
    const hiColor = PAL.fail || BIN_HI;
    const loColor = PAL.accent || BIN_LO;
    // Same hue for the violin body and its jittered points, in each group's own colour -- the
    // fill is given a LOW alpha (rgba at 0.4) while the marker stays solid/near-opaque, so the
    // markers read as visibly darker than the pale fill they sit on without needing a second,
    // different colour or an outline (a white ring looked "super weird" against this palette).
    const fillRgba = (rgb, a = 0.4) => `rgba(${rgb.join(",")},${a})`;
    const hiFill = fillRgba(BIN_HI_RGB);
    const loFill = fillRgba(BIN_LO_RGB);
    const hiPoint = { size: 4, color: hiColor, opacity: 0.9, line: { width: 0 } };
    const loPoint = { size: 4, color: loColor, opacity: 0.9, line: { width: 0 } };
    fig.traces.push({
      type: "violin", x: highVals.map(() => "High pain"), y: highVals,
      name: "High pain", legendgroup: "high", showlegend: false,
      points: "all", pointpos: 0, jitter: 0.4, marker: hiPoint,
      line: { color: hiColor }, fillcolor: hiFill,
      box: { visible: false }, meanline: { visible: true },
      hovertemplate: "%{y:.1f} LSB<extra>High pain</extra>",
    });
    fig.traces.push({
      type: "violin", x: lowVals.map(() => "Low pain"), y: lowVals,
      name: "Low pain", legendgroup: "low", showlegend: false,
      points: "all", pointpos: 0, jitter: 0.4, marker: loPoint,
      line: { color: loColor }, fillcolor: loFill,
      box: { visible: false }, meanline: { visible: true },
      hovertemplate: "%{y:.1f} LSB<extra>Low pain</extra>",
    });
    fig.setLayoutProps({
      height: side, width: side, margin: { l: 56, r: 8, t: 8, b: 34 },
      xaxis: { showgrid: false, zeroline: false, tickfont: { size: 14 } },
      yaxis: { showgrid: false, zeroline: false },
      violinmode: "group", showlegend: false,
    });
    fig.setYlabel("Band power (LSB)", { fontSize: 13 });
    fig.render();
    // Same reasoning as PlotlyHeatmap's own identical call: fig.render() always shows the
    // hover-activated modebar with no override in the shared render-manager class; re-apply the
    // same data/layout with it switched off, and with the responsive resize this component exists
    // for, scoped to just this one div.
    Plotly.react(divId, fig.traces, fig.layout,
      { displayModeBar: false, responsive: true, doubleClick: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [divId, highVals, lowVals, side]);

  useEffect(() => () => {
    // Guarded: Plotly'''s own .purge() throws (uncaught, since this runs in an effect cleanup with
    // no React error boundary anywhere in this app) if the div it manages is already gone from the
    // DOM -- observed live on a native double-click, which Plotly'''s own internal click pipeline
    // can apparently unmount/rebuild around even with the built-in reset-on-dblclick action turned
    // off (doubleClick: false, set on the Plotly.react calls below). Checking first makes this
    // cleanup robust to that regardless of why the div is already gone, rather than chasing the
    // exact internal Plotly sequence that removes it.
    if (figRef.current && document.getElementById(divId)) figRef.current.purge();
  }, [divId]);

  // A true square: width 100% up to `side`, height locked to match via aspect-ratio, so the panel
  // itself is square and Plotly's own responsive resize fills exactly that square.
  return <div id={divId} style={{ width: "100%", maxWidth: side, aspectRatio: "1 / 1" }} />;
}

/** The shared title line for both persistent side panels: channel, band centre, length of signal. */
/**
 * OPEN ITEM 26, the always-visible half. The dashes on the grid say WHICH cells; this says how much
 * of this contact pair is affected, without opening the drawer -- because on this record the answer
 * can be most of it (measured on RCS08, 2026-09-10: 358 of 451 matched reports on R 0-3+, and that
 * contact's correlation then travels only 0.037 across the whole length axis against 0.160-0.253 on
 * the two contacts with none). A contact with none renders nothing at all rather than a reassuring
 * line: there is nothing to reassure about, and a caveat that appears everywhere stops being read.
 */
function CaptionBullets({ items, color }) {
  if (!items || !items.length) return null;
  return (
    <MDBox component="ul" sx={{ m: 0, mb: 0.5, pl: 2.2 }}>
      {items.map((line) => (
        <MDTypography key={line} component="li" variant="caption" color="dark"
          sx={{ fontSize: 13, display: "list-item", color }}>
          {line}
        </MDTypography>
      ))}
    </MDBox>
  );
}

/** Two short bullets (the PI, 2026-09-15: "MUCH more concise, ideally with bullet points"). A
 * contact with no snapshot-served report renders nothing. */
function DeviceSpectrumCaption({ sw }) {
  return <CaptionBullets items={deviceSpectrumBullets(sw)} color="#8a5a00" />;
}

/** Which rows the device can be set to, from the ranges on the response (`device_timing_ranges`,
 * the one home), as bullets. */
function DeviceTierCaption({ ranges, sw }) {
  return <CaptionBullets items={tierBullets(ranges, (sw && sw.integration_seconds_delivered) || [])} />;
}

/** The symbols inside the circles (decision 185): one bullet, shown only once a stored stability
 * answer has reached at least one row -- a legend for symbols that are not drawn is noise. */
/** What the heat maps pool (decision 186): at-home ratings only, or the sheets' scores too. */
function ClinicSheetCaption({ sw }) {
  return <CaptionBullets items={clinicSheetBullets(sw)} color="#8a5a00" />;
}

function StabilityCaption({ sw }) {
  const rows = (sw && sw.best_correlation_rows) || [];
  const any = rows.some((r) => stabilityMark(r.cross_setting_stability));
  if (!any) return null;
  return <CaptionBullets items={[stabilityBullet()]} />;
}

function PanelTitle({ pinnedCell, channelLabel }) {
  if (!pinnedCell) return null;
  // Shown ONLY above the scatter panel now -- the violin panel repeated the identical title
  // immediately below it, which was pure duplication (the two panels always describe the same
  // pinned cell). Font size doubled from the original 11.5 now that it is the one copy carrying
  // this information for both panels.
  return (
    <MDTypography variant="caption" fontWeight="bold" color="dark"
      sx={{ fontSize: 23, display: "block", mb: 0.5 }}>
      {`${channelLabel(pinnedCell.channel)} · ${pinnedCell.center} Hz · `}
      {`${secondsLabel(pinnedCell.secondsDisplay != null ? pinnedCell.secondsDisplay : pinnedCell.seconds)} of signal`}
    </MDTypography>
  );
}

/**
 * The scatter panel is split into two pieces that render in DIFFERENT places on the page now
 * (open item 7 feedback: the big pinned-cell title and the statistics line were "forcing the top
 * plot to look janky" by sitting inside the same box as the plot, which is what was carving space
 * out of it):
 *   - `ScatterStatsLine` renders next to the correlation heat map's own heading, at the SAME row.
 *   - `PlotlyScatter` renders next to the correlation heat map itself, as a native Plotly figure
 *     sized to a genuine square (not merely the heat map's height) -- nothing is reserved above it
 *     any more, since the title and stats line moved elsewhere.
 * The big pinned-cell title (`PanelTitle`) moves out further still, up to sit beside the contact
 * strip (see the main render below) so its own bottom edge lines up with the strip's.
 */
function ScatterStatsLine({ cell, pinnedCell, sw }) {
  if (!pinnedCell) {
    return (
      <MDTypography variant="caption" color="dark" fontStyle="italic" sx={{ fontSize: 11 }}>
        {"Click a cell to see the underlying scatter and its fit."}
      </MDTypography>
    );
  }
  if (!cell || cell.loading || !cell.points || !cell.points.length) {
    return (
      <MDTypography variant="caption" color="dark" fontStyle="italic" sx={{ fontSize: 11 }}>
        {cell && cell.loading ? "Loading…" : "No underlying pairs could be loaded for this cell."}
      </MDTypography>
    );
  }
  // The cell's own r, p and n off the grid response (decision 188: nothing statistical is
  // computed in the browser; decision 66 proved the drill-down's r reproduces the grid's).
  const r = sw && sw.correlation_grid && sw.correlation_grid[pinnedCell.row]
    ? sw.correlation_grid[pinnedCell.row][pinnedCell.col] : null;
  const { n, p } = cellNP(sw, "corr", pinnedCell.col, pinnedCell.row);
  // Review 2026-09-15, B1: the grid's OWN corrected statistic for this cell, printed beside the
  // plain one and labelled as a different thing. Only each column's best cell has one; for any
  // other cell the readout says so rather than leaving the reader to assume the plain r is it.
  const readout = (sw && pinnedCell)
    ? bestCellReadout(sw, "corr", pinnedCell.col, pinnedCell.row, { includeN: false }) : null;
  return (
    <MDBox>
      <MDTypography variant="caption" color="dark" sx={{ fontSize: 15, display: "block", mb: 0.25 }}>
        {`Pearson r = ${num(r, 3)}, p = ${fmtP(p)}, n = ${n} (uncorrected)`}
        {(() => {
          // The scatter and the line below are fitted to these same n pairs; the clinic-sheet
          // ratings among them (decision 186) are drawn hollow and counted here.
          const nSheet = cell.points.filter((pt) => pt.from_clinic_sheet).length;
          return nSheet ? <span style={{ fontSize: 12, color: "#6A6A6A" }}>{` · ${nSheet} of them clinic-sheet scores (hollow points)`}</span> : null;
        })()}
      </MDTypography>
      {readout ? (
        <MDTypography variant="caption" sx={{ fontSize: 13, display: "block", mb: 0.5,
          color: readout.isBest ? PAL.accent : "#6A6A6A" }}>
          {readout.text}
        </MDTypography>
      ) : null}
    </MDBox>
  );
}

/** The scatter + fitted line as a native Plotly figure (via `PlotlyRenderManager`, the same
 * wrapper `PlotlyHeatmap` and `PlotlyViolin` above use), for the same reason as the violin:
 * `responsive: true` hands the fill-the-panel job to Plotly's own resize handling instead of a
 * hand-measured SVG. No title, no statistics text -- those render elsewhere (see the note above).
 * Returns `null` if there's nothing pinned or loaded yet, same contract as the old SVG version. */
function PlotlyScatter({ divId, cell, pinnedCell, side, metricLabel }) {
  // Memoized so this array's identity is stable across renders that don't actually change the
  // underlying points -- otherwise it is a fresh reference every render, which would defeat the
  // effect's own dependency array (the exact bug decision 80 already fixed once on this page).
  const points = useMemo(
    () => ((pinnedCell && cell && !cell.loading && cell.points) ? cell.points : []),
    [pinnedCell, cell]);
  const figRef = useRef(null);
  useEffect(() => {
    if (!points.length) return undefined;
    if (!figRef.current) figRef.current = new PlotlyRenderManager(divId, "en");
    const fig = figRef.current;
    fig.clearData();
    fig.subplots(1, 1, { sharex: false, sharey: false });

    const xs = points.map((p) => p.power);
    const ys = points.map((p) => p.pain);
    const n = xs.length;
    const mx = xs.reduce((s, v) => s + v, 0) / n, my = ys.reduce((s, v) => s + v, 0) / n;
    let sxy = 0, sxx = 0;
    xs.forEach((x, i) => { sxy += (x - mx) * (ys[i] - my); sxx += (x - mx) ** 2; });
    const slope = sxx > 0 ? sxy / sxx : 0;
    const intercept = my - slope * mx;
    const xlo = Math.min(...xs), xhi = Math.max(...xs);

    const colorFor = (label) => (label === "high" ? (PAL.fail || BIN_HI)
      : (label === "low" ? (PAL.accent || BIN_LO) : "#aaaaaa"));
    // One trace per class and per source: a rating from the clinic or at-home sheets (decision
    // 186, when the switch is on) is drawn hollow, so the reader sees which points the sheets
    // added; the line below is fitted to every point, the same pairs the grid correlated.
    const groups = { high: [], low: [], other: [] };
    points.forEach((pt) => { (groups[pt.label] || groups.other).push(pt); });
    ["high", "low", "other"].forEach((label) => {
      [false, true].forEach((sheet) => {
        const pts = groups[label].filter((pt) => !!pt.from_clinic_sheet === sheet);
        if (!pts.length) return;
        fig.traces.push({
          type: "scatter", mode: "markers", showlegend: false,
          name: `${label === "high" ? "High pain" : label === "low" ? "Low pain" : "Excluded"}${sheet ? ", clinic sheet" : ""}`,
          x: pts.map((pt) => pt.power), y: pts.map((pt) => pt.pain),
          marker: sheet
            ? { size: 6, color: "rgba(0,0,0,0)", opacity: 0.9, line: { color: colorFor(label), width: 1.5 } }
            : { size: 5, color: colorFor(label), opacity: 0.75 },
          hovertemplate: `%{x:.0f} LSB, %{y:.1f}${sheet ? " (clinic sheet)" : ""}<extra></extra>`,
        });
      });
    });
    fig.traces.push({
      type: "scatter", mode: "lines", showlegend: false, hoverinfo: "skip",
      x: [xlo, xhi], y: [intercept + slope * xlo, intercept + slope * xhi],
      line: { color: "#1a1a1a", width: 1.5 },
    });

    fig.setLayoutProps({
      height: side, width: side, margin: { l: 56, r: 8, t: 8, b: 40 },
      xaxis: { showgrid: false, zeroline: false },
      yaxis: { showgrid: false, zeroline: false },
      showlegend: false,
    });
    fig.setXlabel("Band power (LSB)", { fontSize: 13 });
    fig.setYlabel(`Pain${metricLabel ? ` (${metricLabel})` : ""}`, { fontSize: 13 });
    fig.render();
    Plotly.react(divId, fig.traces, fig.layout,
      { displayModeBar: false, responsive: true, doubleClick: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [divId, points, side, metricLabel]);

  useEffect(() => () => {
    // Guarded: Plotly'''s own .purge() throws (uncaught, since this runs in an effect cleanup with
    // no React error boundary anywhere in this app) if the div it manages is already gone from the
    // DOM -- observed live on a native double-click, which Plotly'''s own internal click pipeline
    // can apparently unmount/rebuild around even with the built-in reset-on-dblclick action turned
    // off (doubleClick: false, set on the Plotly.react calls below). Checking first makes this
    // cleanup robust to that regardless of why the div is already gone, rather than chasing the
    // exact internal Plotly sequence that removes it.
    if (figRef.current && document.getElementById(divId)) figRef.current.purge();
  }, [divId]);

  if (!points.length) return null;
  // A true square: width 100% up to `side`, height locked to match via aspect-ratio, so the panel
  // itself is square and Plotly's own responsive resize fills exactly that square -- rather than
  // filling a rectangular column at a fixed height (the previous, non-square "fill the panel" fix).
  return <div id={divId} style={{ width: "100%", maxWidth: side, aspectRatio: "1 / 1" }} />;
}

/** Persistent panel next to the AUC grid: two violins (high/low pain) and the cell's own AUC with
 * its Mann-Whitney p and the two counts, read off the grid response (decision 188). */
function ViolinPanel({ cell, pinnedCell, channelLabel, height, aucValue, sw }) {
  if (!pinnedCell) {
    return (
      <MDTypography variant="caption" color="dark" fontStyle="italic" sx={{ fontSize: 11 }}>
        {"Click a cell to see the high/low pain comparison."}
      </MDTypography>
    );
  }
  if (!cell || cell.loading || !cell.points || !cell.points.length) {
    return (
      <MDBox sx={{ height }}>
        <MDTypography variant="caption" color="dark" fontStyle="italic" sx={{ fontSize: 11 }}>
          {cell && cell.loading ? "Loading…" : "No underlying pairs could be loaded for this cell."}
        </MDTypography>
      </MDBox>
    );
  }
  const pts = cell.points;
  const highVals = pts.filter((p) => p.label === "high").map((p) => p.power);
  const lowVals = pts.filter((p) => p.label === "low").map((p) => p.power);
  const { p, nHigh, nLow } = cellNP(sw, "auc", pinnedCell.col, pinnedCell.row);

  return (
    <MDBox>
      {/* No title here -- it duplicated the scatter panel's own title exactly (both describe the
          same pinned cell); that one copy, above the scatter panel, is now the only one. */}
      <MDTypography variant="caption" color="dark" sx={{ fontSize: 15, display: "block", mb: 0.5 }}>
        {`AUC = ${num(aucValue, 3)}, p = ${fmtP(p)} (Mann-Whitney; high n=${nHigh}, low n=${nLow})`}
      </MDTypography>
      {/* The grid's own corrected statistic for this cell, the same small line in the same ink as
          beside the scatter (the PI, 2026-09-15); the plot below moves down by its height. */}
      {(() => {
        const readout = (sw && pinnedCell)
          ? bestCellReadout(sw, "auc", pinnedCell.col, pinnedCell.row, { includeN: false }) : null;
        return readout ? (
          <MDTypography variant="caption" sx={{ fontSize: 13, display: "block", mb: 0.5,
            color: readout.isBest ? PAL.accent : "#6A6A6A" }}>
            {readout.text}
          </MDTypography>
        ) : null;
      })()}
      <PlotlyViolin divId="biomarker-violin-panel" highVals={highVals} lowVals={lowVals}
        side={height} />
    </MDBox>
  );
}

// SweepMetric (which raw pain score the correlation and AUC are computed against) is grouped with
// the matching keys rather than left unclassified: changing which score is used changes BOTH
// grids, the same as changing the match window or direction, so it must trigger the "replace both"
// path rather than accidentally falling into the catch-all branch that also happens to replace
// both -- correct by construction rather than by coincidence of the fallback's own behaviour.
const MATCH_SETTING_KEYS = ["MatchToleranceMin", "MatchDirection", "AllowWindowReuse", "LabelMetric",
  "SweepMetric"];
const BIN_SETTING_KEYS = ["LabelStrategy", "PercentileLow", "PercentileHigh"];

function settingsSubset(params, keys) {
  const out = {};
  keys.forEach((k) => { out[k] = params ? params[k] : undefined; });
  return out;
}

function BiomarkerHeatmapGrids({ participantUid, requestParams, availableMetrics, pageMetric,
  metricLabel, onOpenInClosedLoop }) {
  const options = useMemo(() => (
    (availableMetrics && availableMetrics.length ? availableMetrics : [])
  ), [availableMetrics]);
  // The pain-score metric is now chosen by the ONE consolidated dropdown at the page level
  // (index.js) rather than by a second dropdown here -- this component just reads it. No local
  // state and no sync effect are needed, which also removes the one-way-sync gap that let this
  // component's own selection drift from the page's.
  const metric = pageMetric || "nrs";

  const [channel, setChannel] = useState(null);
  const [corrResult, setCorrResult] = useState(null);   // what the correlation grid is drawn from
  const [aucResult, setAucResult] = useState(null);      // what the AUC grid is drawn from
  const [aucFlashKey, setAucFlashKey] = useState(0);
  const [howToReadOpen, setHowToReadOpen] = useState(false);
  const prevSettingsRef = useRef(null);

  // ONE shared hover state and ONE shared pinned state, read by BOTH grids -- this is what makes
  // hovering or clicking a cell in either grid highlight the SAME cell on the other one, and what
  // lets one click populate both persistent side panels at once (open item 7, part 4d).
  const [hoveredCell, setHoveredCell] = useState(null);       // { row, col } | null
  const [pinnedCell, setPinnedCell] = useState(null);         // { row, col, channel, center, seconds }
  const [pinnedCellData, setPinnedCellData] = useState(null);
  const cellCacheRef = useRef(new Map());

  const reqKey = requestParams ? JSON.stringify(requestParams) : null;

  // THE FETCH ITSELF, SHARED ACROSS NAVIGATION, ONE SLOT PER PAIN-SCORE METRIC.
  //
  // This used to be a plain component-local useEffect/useState, so React Router unmounting this
  // component on every navigation away from the page threw the fetched grid away and refetched it
  // on return even when nothing had changed -- the rest of the page already survives navigation
  // through `useCachedResult`/`database/resultCache`; this component simply never used it. Routed
  // through the same shared cache now, keyed by `biomarkerHeatmapSlot(metric)` rather than one
  // shared slot, because `resultCache` holds exactly one entry per slot and marks it stale (not a
  // second entry) on a settings change -- one slot per metric is what lets six pain scores stay
  // simultaneously cached instead of each switch evicting the last one.
  const cur = useMemo(() => ({ ...requestParams, SweepMetric: metric }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [reqKey, metric]);
  const cachedGrid = useCachedResult({
    moduleKey: biomarkerHeatmapSlot(metric),
    uid: participantUid,
    settings: cur,
    enabled: !!participantUid && !!requestParams,
    fetcher: () => SessionController.query("/api/queryBiomarkerAnalysis",
      { ParticipantId: participantUid, ...requestParams, BandTimeSweep: "1", SweepMetric: metric })
      .then((response) => (response && response.data) || null),
  });
  const loading = cachedGrid.loading;
  const err = cachedGrid.err;

  // THE ASYMMETRIC CORRELATION/AUC UPDATE RULE (PRD §3), UNCHANGED, now keyed off the cached
  // bundle's own identity rather than a raw network response -- it fires exactly when the bundle
  // for the CURRENTLY SELECTED metric changes, whether that is a genuine fetch or a switch onto a
  // metric that was already warm from the background prefetch below.
  useEffect(() => {
    const d = cachedGrid.data;
    if (!d) return;
    const prev = prevSettingsRef.current;
    const matchChanged = !prev || MATCH_SETTING_KEYS.some(
      (k) => settingsSubset(prev, [k])[k] !== settingsSubset(cur, [k])[k]);
    const binChanged = BIN_SETTING_KEYS.some(
      (k) => prev && settingsSubset(prev, [k])[k] !== settingsSubset(cur, [k])[k]);
    prevSettingsRef.current = cur;

    if (matchChanged || !corrResult) {
      setCorrResult(d);
      setAucResult(d);
    } else if (binChanged) {
      // Correlation depends only on matching (PRD §3): keep the previous correlation grid's
      // object identity so its frame does not redraw, and replace the AUC grid with a flash.
      setAucResult(d);
      setAucFlashKey((k) => k + 1);
    } else {
      // Nothing that changes either grid moved (e.g. only the contact-pair strip was
      // clicked) -- still take the freshest response so a served-from-store flag is current.
      setCorrResult(d);
      setAucResult(d);
    }
    const sweeps = (d && d.band_time_sweep) || {};
    const keys = Object.keys(sweeps);
    if (keys.length && (!channel || !sweeps[channel])) setChannel(keys[0]);
    cellCacheRef.current = new Map();
    setPinnedCell(null); setPinnedCellData(null); setHoveredCell(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cachedGrid.data]);

  // BACKGROUND PREFETCH OF THE OTHER PAIN-SCORE METRICS, so switching the dropdown to a metric
  // already warmed this way is a plain cache read instead of a fresh recompute. Runs only once the
  // SELECTED metric's own fetch/cache-check has settled (never competes with the request the reader
  // is actually waiting on), one metric at a time rather than all at once (a burst of concurrent
  // permutation/bootstrap computations is real load on the backend for grids nobody has asked to
  // see yet), and is cancelled by a generation token whenever the participant, the live controls or
  // the selected metric change again before it finishes -- a fast slider drag or a quick run of
  // dropdown switches must not pile up an ever-growing queue of superseded background requests.
  const prefetchGenRef = useRef(0);
  useEffect(() => {
    if (!participantUid || !requestParams || loading) return undefined;
    const gen = (prefetchGenRef.current += 1);
    const others = options.filter((o) => o.key !== metric);
    let cancelled = false;
    (async () => {
      // eslint-disable-next-line no-restricted-syntax
      for (const o of others) {
        if (cancelled || prefetchGenRef.current !== gen) return;
        const otherCur = { ...requestParams, SweepMetric: o.key };
        // eslint-disable-next-line no-await-in-loop
        await prefetchBiomarkerHeatmapMetric(participantUid, o.key, otherCur, () =>
          SessionController.query("/api/queryBiomarkerAnalysis",
            { ParticipantId: participantUid, ...requestParams, BandTimeSweep: "1", SweepMetric: o.key })
            .then((response) => (response && response.data) || null));
      }
    })();
    return () => { cancelled = true; };
    // `reqKey` is the stable proxy for `requestParams` here, same as the fetch above -- including
    // the object itself would fire on every render (a new reference each time).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [participantUid, reqKey, metric, loading, options]);

  const corrSweeps = (corrResult && corrResult.band_time_sweep) || {};
  const aucSweeps = (aucResult && aucResult.band_time_sweep) || {};
  const corrSw = channel && corrSweeps[channel];
  const aucSw = channel && aucSweeps[channel];
  // The device's documented timing ranges, carried on the response since rule version v12
  // (review 2026-09-15, B4). Absent on an older response: the rows are then labelled plainly.
  const deviceRanges = (corrResult && corrResult.device_timing_ranges) || null;
  const matchDirectionLabel = (aucSw && aucSw.match_direction) || (corrSw && corrSw.match_direction);
  // Medtronic-style display name for a raw channel key, matching "Recorded power channels" —
  // reused everywhere this section names a contact pair (the panel titles).
  const channelLabel = (ch) => {
    const sw = corrSweeps[ch] || aucSweeps[ch];
    if (sw && sw.display_short) {
      return sw.display_region ? `${sw.display_short} (${sw.display_region})` : sw.display_short;
    }
    return ch ? ch.replace(/_/g, " ") : ch;
  };

  const fetchCell = (ch, center, seconds) => {
    const key = `${ch}|${center}|${seconds}`;
    if (cellCacheRef.current.has(key)) return Promise.resolve(cellCacheRef.current.get(key));
    const body = {
      ParticipantId: participantUid, ...requestParams, SweepMetric: metric,
      BandTimeSweepCell: "1", Channel: ch, BandCenterHz: center, IntegrationSeconds: seconds,
    };
    return SessionController.query("/api/queryBiomarkerAnalysis", body).then((response) => {
      const d = (response && response.data) || {};
      const cell = d.band_time_sweep_cell || { points: [], message: d.message };
      cellCacheRef.current.set(key, cell);
      return cell;
    });
  };

  // Hover is now cheap: it only moves the shared cross-highlight, no fetch. The persistent panels
  // (part 4c) are driven by CLICK alone, per the redesign -- a click fetches once and both panels
  // stay populated (and cross-linked to both grids) until the next click.
  const handleHover = (row, col) => {
    setHoveredCell(row == null || col == null ? null : { row, col });
  };

  const handleClick = (sw, row, col) => {
    const center = sw.center_freqs_hz[col];
    // The REQUESTED length of signal is what `band_time_sweep_cell_for_participant` keys its own
    // internal lookup on (see bravo_service.py) -- it must be sent to the server exactly as is or
    // the lookup misses. `secondsDisplay` (delivered) is what the axis and the panel titles show,
    // so a reader never sees two different numbers for the one row they clicked.
    const seconds = (sw.integration_seconds_requested || sw.integration_seconds_delivered)[row];
    const secondsDisplay = (sw.integration_seconds_delivered || sw.integration_seconds_requested)[row];
    setPinnedCell({ row, col, channel, center, seconds, secondsDisplay });
    setPinnedCellData({ loading: true });
    fetchCell(channel, center, seconds).then((cell) => setPinnedCellData(cell));
  };

  // THERE IS NO EXPORT STEP, AND THIS BUTTON NO LONGER WAITS FOR ONE. When this section was first
  // built, Track D had not landed and this control was left disabled, watching for a
  // "the grid has been exported" field that Track D was expected to add. Track D then landed and
  // decided the opposite (decision 67): the calibrated grid was ALREADY the whole content of the
  // stored `biomarker_band_sweep` entry, so no new field was needed and nothing pushes anything
  // anywhere. Closed-Loop Deployment simply READS that stored entry as a registered consumer
  // (`ClosedLoopDeployment.adapter.band_sweep_grid_for_closed_loop`) and browses it in its own
  // `BandSweepGridPanel`. The three fields the old check watched for are written by nothing in
  // this repository, so the button could never have lit up and the note under it told a reader to
  // wait for something that had already shipped in a different shape.
  //
  // What replaces it is the only thing left that a reader on THIS page actually needs: a way to
  // get to the grid on the page that can act on it. Enabled whenever there is a grid on screen,
  // which in the ordinary case is also a grid in the store, since `band_time_sweep_for_participant`
  // writes its own response back on the way out. It is NOT a guarantee -- that write is skipped
  // when no signature could be built for the request -- and this button deliberately does not try
  // to prove otherwise from here: the Closed-Loop panel already states its own empty case ("no
  // calibrated grid is available for this participant yet") rather than showing a blank table, so
  // the rare miss lands on an explanation instead of on nothing.
  const gridReady = !!corrSw;

  // `heatmapHeight` is the SAME function `PlotlyHeatmap` calls for its own `height` -- the panels
  // must match the heat maps' height exactly, since they sit in the same Grid row.
  const panelHeight = heatmapHeight((corrSw && (corrSw.correlation_grid || []).length) || 0);

  return (
    <Card sx={{ width: "100%" }}>
      <MDBox p={2}>
        <MDBox display="flex" flexDirection="row" justifyContent="space-between" alignItems="center"
          flexWrap="wrap" gap={1}>
          <MDTypography variant="h5" fontWeight="bold" sx={{ fontSize: 24, lineHeight: 1.3 }}>
            {"How well each band tracks pain"}
          </MDTypography>
          {loading ? <CircularProgress size={20} /> : null}
        </MDBox>
        <MDBox display="flex" flexDirection="row" alignItems="center" flexWrap="wrap" gap={1.5} mt={1}>
          {/* The pain-score dropdown that used to live here is gone -- one consolidated dropdown
              now lives at the top of the page (index.js, below the binarization box) and drives
              this section through the `pageMetric` prop. */}
          {metricLabel ? (
            <MDTypography variant="caption" color="dark" sx={{ fontSize: 12 }}>
              {`Pain score: ${metricLabel}`}
            </MDTypography>
          ) : null}
          {matchDirectionLabel ? (
            <MDBox sx={{ border: `1.5px solid ${PAL.accentBorder || "#0072B2"}`, borderRadius: 1.5,
              px: 1, py: 0.4, background: "#0072B208" }}>
              <MDTypography variant="caption" fontWeight="medium" color="dark" sx={{ fontSize: 11 }}>
                {matchDirectionLabel === "prior"
                  ? "Matched using recordings from before each rating"
                  : "Matched using recordings from either time direction"}
              </MDTypography>
            </MDBox>
          ) : null}
          <MDBox sx={{ ml: "auto" }}>
            <MDButton variant="outlined" color="dark" size="small" disabled={!gridReady}
              onClick={() => onOpenInClosedLoop && onOpenInClosedLoop({ channel, sweep: corrSw })}>
              {"Open this grid in Closed-Loop →"}
            </MDButton>
            <MDTypography variant="caption" color="dark" fontStyle="italic"
              sx={{ fontSize: 10, display: "block", mt: 0.25, maxWidth: 240 }}>
              {gridReady
                ? "Closed-Loop Deployment reads this same grid. Opens it there, where any point "
                  + "can be picked as a candidate band."
                : "Available once the grid has been computed for a sensing contact pair."}
            </MDTypography>
          </MDBox>
        </MDBox>

        {err ? (
          <MDTypography variant="caption" sx={{ fontSize: 11.5, display: "block", mt: 1,
            color: PAL.fail || "#D55E00" }}>{`The grid could not be computed: ${err}`}</MDTypography>
        ) : null}
        {corrResult && corrResult.message ? (
          <MDTypography variant="caption" color="dark" fontStyle="italic"
            sx={{ fontSize: 11.5, display: "block", mt: 1 }}>{corrResult.message}</MDTypography>
        ) : null}

        {corrSw && aucSw ? (
          <>
            {/* THE PINNED-CELL TITLE, moved out of the scatter panel entirely and up to sit beside
                the contact strip -- its own row, with `alignItems="flex-end"` so the title's
                BOTTOM edge lines up with the strip's bottom edge, per direct feedback ("should be
                higher up, so that the floor is aligned with the small clickable heat map
                sub-panels"). A separate, small Grid container rather than folding into the main
                one below: this is the only row that wants bottom-alignment, and the main grid's
                other rows want top-alignment (a heading beside a same-height plot, etc). */}
            <Grid container spacing={2} alignItems="flex-end">
              <Grid item xs={12} md={7}>
                <ContactStrip sweeps={corrSweeps} channel={channel} setChannel={setChannel} />
              </Grid>
              <Grid item xs={12} md={5} />
            </Grid>

            {/* Each grid sits at ~2/3 of its previous footprint, with a persistent panel to its
                right at matching height (open item 7, parts 4b-4d): the scatter+fit panel next to
                the correlation grid, the violin panel next to the AUC grid. A click on EITHER grid
                populates BOTH panels (they describe the same cell) and highlights that cell on
                BOTH grids; hovering either grid highlights the cell on both without fetching.
                The correlation section's heading and the scatter panel's statistics line share a
                row (both now sit OUTSIDE their own plot, at the same level) -- per direct
                feedback, moving the title out of the scatter panel was "forcing the top plot to
                look janky"; splitting its statistics line out the same way is what lets the actual
                plot below be a full, undiminished square matching the heat map's own height. The
                AUC section is unchanged: the violin panel already keeps its statistics line inside
                its own box, above its own plot, and reads fine there already ("the bottom violin
                plot looks better aligned... leave it as is"). */}
            <Grid container spacing={2} alignItems="flex-start">
              <Grid item xs={12} md={7}>
                <MDTypography variant="button" fontWeight="bold" color="dark"
                  sx={{ fontSize: 15, display: "block", mb: 0.5 }}>
                  {"Correlation with pain — depends only on matching"}
                </MDTypography>
                <DeviceSpectrumCaption sw={corrSw} />
                <ClinicSheetCaption sw={corrSw} />
                <DeviceTierCaption ranges={deviceRanges} sw={corrSw} />
                <StabilityCaption sw={corrSw} />
              </Grid>
              {/* The pinned cell's title and its two statistics lines sit at the BOTTOM of this
                  cell, visually just above the scatter plot (the PI, 2026-09-15: they "sat way too
                  high"). `alignSelf: stretch` + a column flex with `justifyContent: flex-end`
                  pushes them down against whatever height the captions on the left take. */}
              <Grid item xs={12} md={5} sx={{ display: "flex", flexDirection: "column",
                justifyContent: "flex-end", alignSelf: "stretch" }}>
                <PanelTitle pinnedCell={pinnedCell} channelLabel={channelLabel} />
                <ScatterStatsLine cell={pinnedCellData} pinnedCell={pinnedCell} sw={corrSw} />
              </Grid>

              <Grid item xs={12} md={7}>
                <PlotlyHeatmap divId="biomarker-heatmap-correlation" sw={corrSw} kind="correlation"
                  deviceRanges={deviceRanges}
                  hoveredCell={hoveredCell} pinnedCell={pinnedCell}
                  onHover={handleHover} onClick={(r, c) => handleClick(corrSw, r, c)} />
              </Grid>
              <Grid item xs={12} md={5}>
                <PlotlyScatter divId="biomarker-scatter-panel" cell={pinnedCellData}
                  pinnedCell={pinnedCell} side={panelHeight} metricLabel={metricLabel} />
              </Grid>

              <Grid item xs={12} md={7}>
                <MDTypography variant="button" fontWeight="bold" color="dark"
                  sx={{ fontSize: 15, display: "block", mb: 0.5 }}>
                  {"High vs low pain (AUC) — also depends on the binarization cuts above"}
                </MDTypography>
                <PlotlyHeatmap divId="biomarker-heatmap-auc" sw={aucSw} kind="auc"
                  deviceRanges={deviceRanges}
                  hoveredCell={hoveredCell} pinnedCell={pinnedCell} flashKey={aucFlashKey}
                  onHover={handleHover} onClick={(r, c) => handleClick(aucSw, r, c)} />
              </Grid>
              <Grid item xs={12} md={5}>
                <ViolinPanel cell={pinnedCellData} pinnedCell={pinnedCell}
                  channelLabel={channelLabel} height={panelHeight} sw={aucSw}
                  aucValue={(pinnedCell && aucSw && aucSw.auc_grid
                    && aucSw.auc_grid[pinnedCell.row] && aucSw.auc_grid[pinnedCell.row][pinnedCell.col])}
                />
              </Grid>
            </Grid>

            <MDBox mt={1.5}>
              <MDBox display="flex" alignItems="center" sx={{ cursor: "pointer" }}
                onClick={() => setHowToReadOpen((v) => !v)}>
                <IconButton size="small" sx={{ transform: howToReadOpen ? "rotate(180deg)" : "none" }}>
                  <ExpandMoreIcon fontSize="small" />
                </IconButton>
                <MDTypography variant="caption" fontWeight="bold" color="dark" sx={{ fontSize: 12 }}>
                  {"How to read this"}
                </MDTypography>
              </MDBox>
              <Collapse in={howToReadOpen}>
                <MDBox sx={{ border: `1.5px solid ${PAL.accentBorder || "#0072B255"}`, borderRadius: 2,
                  p: 1.25, background: "#0072B208", mt: 0.5 }}>
                  {/* `aucSw.notes` is dropped -- both grids come from the same per-channel sweep
                      response and its `notes` never differs between them, so concatenating the two
                      only ever rendered every note twice (open item 7, decision 2026-09-09).
                      Order, reduced from 13 bullets to 8 and reordered by priority: the three
                      "how to read the statistics" notes the backend already puts first (best-of-ten
                      selection bias, what 0.5 means, direction/folding) -- the two the PI required
                      plus the direction note moved up beside them -- then the two remaining
                      display-only notes that matter most for reading the page at a glance (the
                      circled-cell correction, why the left grid doesn't redraw), then the
                      single-cell-statistic caveat, then the sweep's own mechanical bookkeeping
                      (tile rounding, cell independence, outliers, the shuffled reference, the split
                      rule) last. The old fourth static bullet ("0.5 means... not 0") is deleted
                      outright -- it restated the backend's own second note nearly verbatim. */}
                  {participantUid === L13_SEARCH_UID ? L13_SEARCH_LINES.map((n, i) => (
                    <MDTypography key={`l13-${i}`} variant="caption" color="dark" data-testid="l13-search-line"
                      sx={{ fontSize: 17, display: "block", mb: 0.5, lineHeight: 1.4, fontWeight: 700 }}>
                      {`• ${n}`}
                    </MDTypography>
                  )) : null}
                  {bulletsFor(corrSw).map((n, i) => (
                    <MDTypography key={i} variant="caption" color="dark"
                      sx={{ fontSize: 17, display: "block", mb: 0.5, lineHeight: 1.4 }}>
                      {`• ${n}`}
                    </MDTypography>
                  ))}
                </MDBox>
              </Collapse>
            </MDBox>
          </>
        ) : (!loading ? (
          <MDTypography variant="caption" color="dark" fontStyle="italic"
            sx={{ fontSize: 11.5, display: "block", mt: 1 }}>
            {corrResult ? "No band centre produced a grid for this contact pair."
              : "Computing the calibrated grid…"}
          </MDTypography>
        ) : null)}
      </MDBox>
    </Card>
  );
}

export default BiomarkerHeatmapGrids;
