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
import { BIN_HI, BIN_LO, BIN_HI_RGB, BIN_LO_RGB } from "./binarizationModel";

const num = (v, d = 3) => (v == null || !Number.isFinite(Number(v)) ? "—" : Number(v).toFixed(d));

// ---------------------------------------------------------------------------------------------
// COLOUR. A diverging scale around the value that means "no relationship" for each quantity --
// 0 for a correlation, 0.5 (never 0) for an area under the curve. House rule: an AUC is never
// read against zero. Used both for the Plotly heatmap colorscale and the ContactStrip thumbnails.
// ---------------------------------------------------------------------------------------------
function divergingRgb(v, center, halfRange) {
  const t = Math.max(-1, Math.min(1, (Number(v) - center) / halfRange));
  const neg = BIN_LO_RGB;         // blue
  const pos = BIN_HI_RGB;         // vermillion
  const mid = [255, 255, 255];
  const lerp = (a, b, k) => a + (b - a) * k;
  return t < 0
    ? [lerp(neg[0], mid[0], 1 + t), lerp(neg[1], mid[1], 1 + t), lerp(neg[2], mid[2], 1 + t)]
    : [lerp(mid[0], pos[0], t), lerp(mid[1], pos[1], t), lerp(mid[2], pos[2], t)];
}
function diverging(v, center, halfRange) {
  if (v == null || !Number.isFinite(Number(v))) return "#e9e9e9";
  const c = divergingRgb(v, center, halfRange);
  return `rgb(${c.map((x) => Math.round(x)).join(",")})`;
}
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

// ---------------------------------------------------------------------------------------------
// STANDARD, UNCORRECTED PER-CELL STATISTICS for the two persistent side panels -- Pearson's r's
// own parametric p-value, and a Welch two-sample t-test between the high/low groups. These are
// NOT the grid's own permutation- and bootstrap-corrected, family-wise-adjusted statistics
// (`best_correlation_rows`/`best_auc_rows`, computed only for each column's single best-of-ten-
// lengths row) -- there is no such rigorous answer stored for an arbitrary cell, and computing one
// would mean adding new backend permutation machinery. A plain, standard statistic computed from
// the cell's own already-fetched (power, pain) pairs is what was asked for ("t-test if no other
// exists"), and is labelled in the UI as exactly that rather than conflated with the grid's own
// headline numbers.
// ---------------------------------------------------------------------------------------------
function pearsonR(xs, ys) {
  const n = xs.length;
  if (n < 3) return { r: null, n };
  const mx = xs.reduce((s, v) => s + v, 0) / n;
  const my = ys.reduce((s, v) => s + v, 0) / n;
  let sxy = 0, sxx = 0, syy = 0;
  for (let i = 0; i < n; i += 1) {
    const dx = xs[i] - mx, dy = ys[i] - my;
    sxy += dx * dy; sxx += dx * dx; syy += dy * dy;
  }
  const denom = Math.sqrt(sxx * syy);
  return { r: denom > 0 ? sxy / denom : null, n };
}
// Log of the complete Gamma function (Lanczos approximation), used only through
// `regularizedIncompleteBeta` below to get an EXACT two-tailed Student's-t p-value -- not a
// normal-distribution approximation, which would be wrong at the small sample sizes a single
// cell can have.
function logGamma(x) {
  const g = 7;
  const c = [0.99999999999980993, 676.5203681218851, -1259.1392167224028,
    771.32342877765313, -176.61502916214059, 12.507343278686905,
    -0.13857109526572012, 9.9843695780195716e-6, 1.5056327351493116e-7];
  if (x < 0.5) return Math.log(Math.PI / Math.sin(Math.PI * x)) - logGamma(1 - x);
  const xx = x - 1;
  let a = c[0];
  const t = xx + g + 0.5;
  for (let i = 1; i < g + 2; i += 1) a += c[i] / (xx + i);
  return 0.5 * Math.log(2 * Math.PI) + (xx + 0.5) * Math.log(t) - t + Math.log(a);
}
// Continued-fraction evaluation for the regularized incomplete beta function (the standard
// textbook algorithm), used only through `regularizedIncompleteBeta` immediately below.
function betacf(x, a, b) {
  const MAXIT = 200, EPS = 3e-14, FPMIN = 1e-300;
  const qab = a + b, qap = a + 1, qam = a - 1;
  let c = 1, d = 1 - (qab * x) / qap;
  if (Math.abs(d) < FPMIN) d = FPMIN;
  d = 1 / d;
  let h = d;
  for (let m = 1; m <= MAXIT; m += 1) {
    const m2 = 2 * m;
    let aa = (m * (b - m) * x) / ((qam + m2) * (a + m2));
    d = 1 + aa * d; if (Math.abs(d) < FPMIN) d = FPMIN;
    c = 1 + aa / c; if (Math.abs(c) < FPMIN) c = FPMIN;
    d = 1 / d; h *= d * c;
    aa = (-(a + m) * (qab + m) * x) / ((a + m2) * (qap + m2));
    d = 1 + aa * d; if (Math.abs(d) < FPMIN) d = FPMIN;
    c = 1 + aa / c; if (Math.abs(c) < FPMIN) c = FPMIN;
    d = 1 / d;
    const del = d * c; h *= del;
    if (Math.abs(del - 1) < EPS) break;
  }
  return h;
}
// The regularized incomplete beta function I_x(a, b). Verified against known reference values
// before use (t=2.228, df=10 -> p=0.0500; r=0.5, n=30 -> p=0.0049).
function regularizedIncompleteBeta(x, a, b) {
  if (x <= 0) return 0;
  if (x >= 1) return 1;
  const bt = Math.exp(logGamma(a + b) - logGamma(a) - logGamma(b)
    + a * Math.log(x) + b * Math.log(1 - x));
  return x < (a + 1) / (a + b + 2)
    ? (bt * betacf(x, a, b)) / a
    : 1 - (bt * betacf(1 - x, b, a)) / b;
}
// Two-tailed p-value for a Student's t statistic with `df` degrees of freedom (real-valued df is
// fine -- Welch's t-test below produces a fractional one): p = I_{df/(df+t^2)}(df/2, 1/2).
function tTestPValue(t, df) {
  if (!Number.isFinite(t) || !Number.isFinite(df) || df <= 0) return null;
  const x = df / (df + t * t);
  return regularizedIncompleteBeta(x, df / 2, 0.5);
}
function meanOf(xs) { return xs.reduce((s, v) => s + v, 0) / xs.length; }
function sampleVariance(xs, m) {
  return xs.length > 1 ? xs.reduce((s, v) => s + (v - m) ** 2, 0) / (xs.length - 1) : 0;
}
// Welch's two-sample t-test (does not assume the two groups have equal variance -- the standard
// general-purpose default) between the high- and low-pain groups' band-power values for one cell.
function welchTTest(a, b) {
  if (a.length < 2 || b.length < 2) return { t: null, df: null, p: null, n1: a.length, n2: b.length };
  const ma = meanOf(a), mb = meanOf(b);
  const va = sampleVariance(a, ma), vb = sampleVariance(b, mb);
  const se2 = va / a.length + vb / b.length;
  const t = se2 > 0 ? (ma - mb) / Math.sqrt(se2) : null;
  const df = se2 > 0
    ? (se2 * se2) / ((va * va) / (a.length * a.length * (a.length - 1))
      + (vb * vb) / (b.length * b.length * (b.length - 1)))
    : null;
  const p = (t != null && df != null) ? tTestPValue(t, df) : null;
  return { t, df, p, n1: a.length, n2: b.length, mean1: ma, mean2: mb };
}

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
  width = 750 }) {
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

  const yLabels = useMemo(() => seconds.map((s) => secondsLabel(s)), [seconds]);
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
      hovertemplate: `${kind === "auc" ? "AUC" : "r"} = %{z:.3f}<br>%{x} Hz, %{y}<extra></extra>`,
    });
    // Family-wise-significant "best of ten lengths" cells -- an open circle, exactly the marker
    // the SVG version drew.
    const bestX = [], bestY = [];
    Object.keys(bestByCol).forEach((c) => {
      const b = bestByCol[c];
      if (b && b.row_data && b.row_data.family_wise_significant_8_to_30hz === true) {
        bestX.push(centers[Number(c)]); bestY.push(yLabels[b.row]);
      }
    });
    if (bestX.length) {
      fig.traces.push({
        type: "scatter", mode: "markers", x: bestX, y: bestY, showlegend: false,
        marker: { symbol: "circle-open", size: 14, color: "#1a1a1a", line: { width: 1.4 } },
        hoverinfo: "skip",
      });
    }
    // The shared cross-highlight -- one square-outline marker at the hovered or pinned cell,
    // drawn on BOTH grids from the same (row, col) so the two stay in visual sync.
    const activeCell = pinnedCell || hoveredCell;
    if (activeCell && activeCell.row < rows && activeCell.col < cols) {
      fig.traces.push({
        type: "scatter", mode: "markers",
        x: [centers[activeCell.col]], y: [yLabels[activeCell.row]], showlegend: false,
        marker: { symbol: "square-open", size: 22, color: "#1a1a1a",
          line: { width: pinnedCell ? 3 : 2 } },
        hoverinfo: "skip",
      });
    }
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
    Plotly.react(divId, fig.traces, fig.layout, { displayModeBar: false, responsive: true });

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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [divId, grid, centers, yLabels, kind, center, halfRange, bestByCol, hoveredCell, pinnedCell,
    height, width]);

  useEffect(() => () => {
    if (figRef.current) figRef.current.purge();
  }, []);

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

/** A small strip of thumbnail correlation grids, one per sensing contact pair, all drawn from the
 * one response already held -- clicking a thumbnail is what chooses the contact pair for the two
 * big grids below (Option 2's replacement for a dropdown, task A3). */
function ContactStrip({ sweeps, channel, setChannel }) {
  const names = Object.keys(sweeps || {});
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

/** A lightweight kernel-density violin for one group of values, mirrored around a vertical axis. */
function violinPath(values, cx, yScale, halfWidth) {
  const vs = (values || []).filter((v) => Number.isFinite(v));
  if (vs.length < 2) return null;
  const mean = vs.reduce((s, v) => s + v, 0) / vs.length;
  const sd = Math.sqrt(vs.reduce((s, v) => s + (v - mean) ** 2, 0) / vs.length) || 1;
  const iqr = (() => {
    const sorted = [...vs].sort((a, b) => a - b);
    const q = (p) => sorted[Math.min(sorted.length - 1, Math.max(0, Math.floor(p * (sorted.length - 1))))];
    return q(0.75) - q(0.25);
  })();
  const bw = 0.9 * Math.min(sd, iqr / 1.34 || sd) * Math.pow(vs.length, -0.2) || sd * 0.3 || 1;
  const lo = Math.min(...vs), hi = Math.max(...vs);
  const N = 32;
  const dens = [];
  let maxD = 0;
  for (let i = 0; i <= N; i += 1) {
    const x = lo + ((hi - lo) * i) / N;
    let d = 0;
    vs.forEach((v) => { const u = (x - v) / bw; d += Math.exp(-0.5 * u * u); });
    d /= (vs.length * bw * Math.sqrt(2 * Math.PI));
    dens.push({ x, d });
    if (d > maxD) maxD = d;
  }
  if (maxD <= 0) return null;
  const left = dens.map((p) => [cx - (p.d / maxD) * halfWidth, yScale(p.x)]);
  const right = dens.map((p) => [cx + (p.d / maxD) * halfWidth, yScale(p.x)]).reverse();
  const pts = [...left, ...right];
  return pts.map((p) => p.join(",")).join(" ");
}

/** The shared title line for both persistent side panels: channel, band centre, length of signal. */
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

/** "Nice" round-number axis ticks (1/2/5 × 10^n steps) spanning [lo, hi], the standard algorithm
 * behind most charting libraries' default axes -- used to draw real tick marks and labels on the
 * scatter and violin panels below, which previously had a bare text label and no scale at all. */
function niceTicks(lo, hi, count = 4) {
  if (!(hi > lo)) return [lo];
  const span = hi - lo;
  const rawStep = span / count;
  const mag = 10 ** Math.floor(Math.log10(rawStep));
  const norm = rawStep / mag;
  const step = (norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10) * mag;
  const decimals = Math.max(0, -Math.floor(Math.log10(step)));
  const start = Math.ceil(lo / step) * step;
  const ticks = [];
  for (let v = start; v <= hi + step * 1e-6; v += step) ticks.push(Number(v.toFixed(10)));
  return { ticks, decimals };
}

/** A plain left+bottom axis (line, tick marks, numeric labels) for one Cartesian panel. Pass
 * `xTicks: null` to draw only the y-axis (the violin panel's x is categorical and already labels
 * its two groups with text under each violin). */
function PanelAxes({ w, h, pad, xlo, xhi, sx, ylo, yhi, sy, xTicks = true }) {
  const yT = niceTicks(ylo, yhi, 4);
  const xT = xTicks ? niceTicks(xlo, xhi, 4) : null;
  return (
    <g>
      <line x1={pad} y1={pad} x2={pad} y2={h - pad} stroke="#888" strokeWidth={1} />
      <line x1={pad} y1={h - pad} x2={w - pad} y2={h - pad} stroke="#888" strokeWidth={1} />
      {yT.ticks.map((v) => (
        <g key={`y${v}`}>
          <line x1={pad - 3} y1={sy(v)} x2={pad} y2={sy(v)} stroke="#888" strokeWidth={1} />
          <text x={pad - 6} y={sy(v) + 5} fontSize={16} textAnchor="end" fill="#666">
            {v.toFixed(yT.decimals)}
          </text>
        </g>
      ))}
      {xT ? xT.ticks.map((v) => (
        <g key={`x${v}`}>
          <line x1={sx(v)} y1={h - pad} x2={sx(v)} y2={h - pad + 3} stroke="#888" strokeWidth={1} />
          <text x={sx(v)} y={h - pad + 20} fontSize={16} textAnchor="middle" fill="#666">
            {v.toFixed(xT.decimals)}
          </text>
        </g>
      )) : null}
    </g>
  );
}

/** Persistent panel next to the correlation grid: scatter + fitted line, Pearson r and its own
 * (uncorrected, single-cell) p-value. */
function ScatterFitPanel({ cell, pinnedCell, channelLabel, height, metricLabel }) {
  if (!pinnedCell) {
    return (
      <MDTypography variant="caption" color="dark" fontStyle="italic" sx={{ fontSize: 11 }}>
        {"Click a cell to see the underlying scatter and its fit."}
      </MDTypography>
    );
  }
  if (!cell || cell.loading || !cell.points || !cell.points.length) {
    return (
      <MDBox sx={{ height }}>
        <PanelTitle pinnedCell={pinnedCell} channelLabel={channelLabel} />
        <MDTypography variant="caption" color="dark" fontStyle="italic" sx={{ fontSize: 11 }}>
          {cell && cell.loading ? "Loading…" : "No underlying pairs could be loaded for this cell."}
        </MDTypography>
      </MDBox>
    );
  }
  const pts = cell.points;
  const xs = pts.map((p) => p.power);
  const ys = pts.map((p) => p.pain);
  const { r, n } = pearsonR(xs, ys);
  const t = (r != null && n > 2) ? r * Math.sqrt((n - 2) / (1 - r * r)) : null;
  const p = t != null ? tTestPValue(t, n - 2) : null;

  const xlo = Math.min(...xs), xhi = Math.max(...xs);
  const ylo = Math.min(...ys), yhi = Math.max(...ys);
  // Square, and sized to fill the same height as the heat map next to it (64 px reserved above
  // the plot for the title plus the statistics line). `pad` widened to fit the larger tick labels
  // plus the rotated axis title running alongside them on the left.
  const h = Math.max(160, height - 64);
  const w = h;
  const pad = 62;
  const sx = (x) => pad + ((x - xlo) / ((xhi - xlo) || 1)) * (w - 2 * pad);
  const sy = (y) => (h - pad) - ((y - ylo) / ((yhi - ylo) || 1)) * (h - 2 * pad);
  const mx = xs.reduce((s, v) => s + v, 0) / n, my = ys.reduce((s, v) => s + v, 0) / n;
  let sxy = 0, sxx = 0;
  xs.forEach((x, i) => { sxy += (x - mx) * (ys[i] - my); sxx += (x - mx) ** 2; });
  const slope = sxx > 0 ? sxy / sxx : 0;
  const intercept = my - slope * mx;
  const colorFor = (label) => (label === "high" ? (PAL.fail || BIN_HI)
    : (label === "low" ? (PAL.accent || BIN_LO) : "#aaaaaa"));

  return (
    <MDBox sx={{ height }}>
      <PanelTitle pinnedCell={pinnedCell} channelLabel={channelLabel} />
      <MDTypography variant="caption" color="dark" sx={{ fontSize: 11, display: "block", mb: 0.5 }}>
        {`Pearson r = ${num(r, 3)}, p = ${p == null ? "—" : num(p, 4)} (n = ${n})`}
      </MDTypography>
      <svg width={w} height={h}>
        <PanelAxes w={w} h={h} pad={pad} xlo={xlo} xhi={xhi} sx={sx} ylo={ylo} yhi={yhi} sy={sy} />
        {pts.map((pt, i) => (
          <circle key={i} cx={sx(pt.power)} cy={sy(pt.pain)} r={2.6}
            fill={colorFor(pt.label)} opacity={0.75} />
        ))}
        <line x1={sx(xlo)} y1={sy(intercept + slope * xlo)} x2={sx(xhi)} y2={sy(intercept + slope * xhi)}
          stroke="#1a1a1a" strokeWidth={1.5} />
        {/* Axis titles, same convention as the heat maps' own: the x title centred below its
            axis, the y title rotated -90 and run alongside the tick labels rather than sitting
            sideways-on as a horizontal string. Units named explicitly: band power is always in
            the device's own least-significant-bit units on this page (LSB); the pain axis names
            whichever score is currently selected, since the same axis serves NRS, VAS, MPQ, etc. */}
        <text x={pad + (w - 2 * pad) / 2} y={h - 8} fontSize={13} textAnchor="middle" fill="#555">
          Band power (LSB)
        </text>
        <text x={16} y={pad + (h - 2 * pad) / 2} fontSize={13} textAnchor="middle" fill="#555"
          transform={`rotate(-90 16 ${pad + (h - 2 * pad) / 2})`}>
          {`Pain${metricLabel ? ` (${metricLabel})` : ""}`}
        </text>
      </svg>
    </MDBox>
  );
}

/** Persistent panel next to the AUC grid: two violins (high/low pain) and a Welch two-sample
 * t-test between them, reported because no other per-cell comparison statistic is stored. */
function ViolinPanel({ cell, pinnedCell, channelLabel, height }) {
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
  const { t, df, p, n1, n2 } = welchTTest(highVals, lowVals);

  const all = highVals.concat(lowVals);
  const lo = Math.min(...all), hi = Math.max(...all);
  // Square, and sized to fill the same height as the heat map next to it (30 px reserved above
  // for the statistics line -- there is no title here any more). `pad` widened to fit the larger
  // tick labels plus the rotated axis title running alongside them on the left.
  const h = Math.max(160, height - 30);
  const w = h;
  const pad = 62;
  const vyScale = (v) => (h - pad) - ((v - lo) / ((hi - lo) || 1)) * (h - 2 * pad);
  const colorFor = (label) => (label === "high" ? (PAL.fail || BIN_HI)
    : (label === "low" ? (PAL.accent || BIN_LO) : "#aaaaaa"));

  return (
    <MDBox sx={{ height }}>
      {/* No title here -- it duplicated the scatter panel's own title exactly (both describe the
          same pinned cell); that one copy, above the scatter panel, is now the only one. */}
      <MDTypography variant="caption" color="dark" sx={{ fontSize: 11, display: "block", mb: 0.5 }}>
        {`Welch t(${num(df, 1)}) = ${num(t, 2)}, p = ${p == null ? "—" : num(p, 4)} `}
        {`(high n=${n1}, low n=${n2})`}
      </MDTypography>
      <svg width={w} height={h}>
        {/* Only the y-axis (band power) is drawn -- x is the two categorical groups, already
            labelled by the "High pain"/"Low pain" text under each violin. */}
        <PanelAxes w={w} h={h} pad={pad} xlo={0} xhi={1} sx={() => 0} ylo={lo} yhi={hi}
          sy={vyScale} xTicks={false} />
        {/* Centres pulled in from the panel's own earlier 0.28/0.72 (a width-260 layout) to
            0.3/0.7 with a slightly narrower half-width, so neither violin's tails run past the
            panel edge now that this canvas is square and much larger than before. */}
        {[["high", highVals, w * 0.3], ["low", lowVals, w * 0.7]].map(([label, vals, cx]) => {
          const path = violinPath(vals, cx, vyScale, w * 0.17);
          return (
            <g key={label}>
              {path ? <polygon points={path} fill={colorFor(label)} opacity={0.35}
                stroke={colorFor(label)} strokeWidth={1} /> : null}
              {vals.map((v, i) => (
                <circle key={i} cx={cx + (((i * 37) % 11) - 5) * 0.6} cy={vyScale(v)} r={1.6}
                  fill={colorFor(label)} opacity={0.6} />
              ))}
              <text x={cx} y={h - 6} fontSize={9} textAnchor="middle" fill="#555">
                {label === "high" ? "High pain" : "Low pain"}
              </text>
            </g>
          );
        })}
        <text x={16} y={pad + (h - 2 * pad) / 2} fontSize={13} textAnchor="middle" fill="#555"
          transform={`rotate(-90 16 ${pad + (h - 2 * pad) / 2})`}>
          Band power (LSB)
        </text>
      </svg>
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
  metricLabel, onCommitBand }) {
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

  // Track D (`adr_2026-09-08_biomarkers_closedloop_matrix_export.md`) is what will let the whole
  // grid be exported to Closed-Loop Deployment; it had not landed as of this track's own work, so
  // this checks for the field it will add rather than assuming it exists, and stays disabled
  // with an explanation until it does -- a follow-up wires the button live once Track D ships.
  const exportReady = !!(corrResult && (corrResult.closed_loop_export_key
    || corrResult.exported_to_closed_loop || (corrSw && corrSw.closed_loop_export_ready)));

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
            <MDButton variant="outlined" color="dark" size="small" disabled={!exportReady}
              onClick={() => onCommitBand && onCommitBand({ channel, sweep: corrSw })}>
              {"Export full grid to Closed-Loop…"}
            </MDButton>
            {!exportReady ? (
              <MDTypography variant="caption" color="dark" fontStyle="italic"
                sx={{ fontSize: 10, display: "block", mt: 0.25, maxWidth: 220 }}>
                {"Waiting on the Closed-Loop export field from the other track building it; this "
                 + "button will light up once that lands."}
              </MDTypography>
            ) : null}
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

        <ContactStrip sweeps={corrSweeps} channel={channel} setChannel={setChannel} />

        {corrSw && aucSw ? (
          <>
            {/* Each grid sits at ~2/3 of its previous footprint, with a persistent panel to its
                right at matching height (open item 7, parts 4b-4d): the scatter+fit panel next to
                the correlation grid, the violin panel next to the AUC grid. A click on EITHER grid
                populates BOTH panels (they describe the same cell) and highlights that cell on
                BOTH grids; hovering either grid highlights the cell on both without fetching. */}
            <Grid container spacing={2} alignItems="flex-start">
              <Grid item xs={12} md={7}>
                <MDTypography variant="button" fontWeight="bold" color="dark"
                  sx={{ fontSize: 15, display: "block", mb: 0.5 }}>
                  {"Correlation with pain — depends only on matching"}
                </MDTypography>
                <PlotlyHeatmap divId="biomarker-heatmap-correlation" sw={corrSw} kind="correlation"
                  hoveredCell={hoveredCell} pinnedCell={pinnedCell}
                  onHover={handleHover} onClick={(r, c) => handleClick(corrSw, r, c)} />
              </Grid>
              <Grid item xs={12} md={5}>
                <ScatterFitPanel cell={pinnedCellData} pinnedCell={pinnedCell}
                  channelLabel={channelLabel} height={panelHeight} metricLabel={metricLabel} />
              </Grid>

              <Grid item xs={12} md={7}>
                <MDTypography variant="button" fontWeight="bold" color="dark"
                  sx={{ fontSize: 15, display: "block", mb: 0.5 }}>
                  {"High vs low pain (AUC) — also depends on the binarization cuts above"}
                </MDTypography>
                <PlotlyHeatmap divId="biomarker-heatmap-auc" sw={aucSw} kind="auc"
                  hoveredCell={hoveredCell} pinnedCell={pinnedCell} flashKey={aucFlashKey}
                  onHover={handleHover} onClick={(r, c) => handleClick(aucSw, r, c)} />
              </Grid>
              <Grid item xs={12} md={5}>
                <ViolinPanel cell={pinnedCellData} pinnedCell={pinnedCell}
                  channelLabel={channelLabel} height={panelHeight} />
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
                  {(corrSw.notes || []).concat(aucSw.notes || []).map((n, i) => (
                    <MDTypography key={i} variant="caption" color="dark"
                      sx={{ fontSize: 11.5, display: "block", mb: 0.4, lineHeight: 1.45 }}>
                      {`• ${n}`}
                    </MDTypography>
                  ))}
                  <MDTypography variant="caption" color="dark"
                    sx={{ fontSize: 11.5, display: "block", mb: 0.4, lineHeight: 1.45 }}>
                    {"• The left grid never redraws when you move the binarization cuts above, "
                     + "because a correlation between band power and a continuous pain score does "
                     + "not use the high/low split at all. The right grid does, and briefly flashes "
                     + "when it recomputes."}
                  </MDTypography>
                  <MDTypography variant="caption" color="dark"
                    sx={{ fontSize: 11.5, display: "block", mb: 0.4, lineHeight: 1.45 }}>
                    {"• A circled cell clears an additional multiple-comparison correction across "
                     + "all 22 band centres in this grid — a research finding, not a statement "
                     + "that a configuration is ready for the device."}
                  </MDTypography>
                  <MDTypography variant="caption" color="dark"
                    sx={{ fontSize: 11.5, display: "block", mb: 0.4, lineHeight: 1.45 }}>
                    {"• For the right grid, 0.5 means no ability to tell high pain from low "
                     + "pain apart — not 0. The colour scale is centred on 0.5."}
                  </MDTypography>
                  <MDTypography variant="caption" color="dark"
                    sx={{ fontSize: 11.5, display: "block", lineHeight: 1.45 }}>
                    {"• The Pearson r/p and Welch t-test shown when you click a cell are plain, "
                     + "single-cell statistics computed on the spot from that cell's own points — "
                     + "not the grid's own permutation- and bootstrap-corrected numbers, which "
                     + "exist only for each column's single best-of-ten-lengths row."}
                  </MDTypography>
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
