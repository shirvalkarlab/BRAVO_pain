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

import { Grid } from "@mui/material";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import MDButton from "components/MDButton";

import Plotly from "plotly.js-dist";
import { PlotlyRenderManager } from "graphing-utility/Plotly";
import { SessionController } from "database/session-control";
import { prefetchClosedLoopFromBiomarkers } from "views/Reports/ClosedLoopSim/neighbourPrefetch";
import { useCachedResult } from "database/useCachedResult";
// Read only (the PI's file, not edited): the settings the shown grid was computed under.
import { getResult, settingsKey } from "database/resultCache";
import { biomarkerHeatmapSlot, prefetchBiomarkerHeatmapMetric } from "views/Reports/moduleCacheKeys";
import { cellKey, getCell, putCell } from "./heatmapCellCache";
import { PLOT_MARGIN, PLOT_BOTTOM, plotMargin, panelBoxStyle } from "./panelLayout";
import { T, TYPE, LAYOUT } from "assets/theme/base/tokens";
import { DIVERGING, RANGE, textInk } from "assets/theme/base/dataColors";
import { PLOTLY_LAYOUT, PLOTLY_CONFIG, FONT_FAMILY, FIGURE_TEXT_PX, directLabel, mergeDeep } from "views/Reports/figureStyle";
import ColorKey from "views/Reports/paper/ColorKey";
import Fold from "./Fold";
import GridSkeleton from "./GridSkeleton";
import Section from "views/Reports/paper/Section";
import { BIN_HI, BIN_LO, BIN_HI_RGB, BIN_LO_RGB, BIN_MID, diverging } from "./binarizationModel";
import { contactSortKey } from "./contactOrder";
import { bestCellReadout, cellNP, fmtP, pEquals, hoverCustomData, tierBullets, deviceSpectrumBullets, needsMultiplePsds, stabilityMark, stabilityBullet, clinicSheetBullets, sourceSplitLine } from "./gridReadouts";

/** Participants whose likeliest Closed-Loop bands were asked for in this page load (decision 430). */
const CL_PREFETCHED = new Set();

// The heat maps' hover text, a size under the figure text (the PI, 2026-09-26: "reduce font size");
// 11 px is the page's floor (decision 258).
const HEATMAP_HOVERLABEL = { ...PLOTLY_LAYOUT.hoverlabel,
  font: { ...PLOTLY_LAYOUT.hoverlabel.font, size: 11 } };
const num = (v, d = 2) => (v == null || !Number.isFinite(Number(v)) ? "not given" : Number(v).toFixed(d));

// COLOUR (the redesign of 2026-09-26, SPEC.md section 3.1): the one nine-stop diverging scale
// (dataColors.DIVERGING, blue -> light grey -> vermillion) on FIXED symmetric ranges: a correlation
// from -0.5 to +0.5, an area under the curve from 0.25 to 0.75 around 0.5 (a coin toss). Values
// beyond the range draw at the end colour; the hover prints the true value. The thumbnails use the
// same range as the large maps, so every map on the card reads against one key.
const SCALE = {
  correlation: { center: 0, halfRange: (RANGE.correlation[1] - RANGE.correlation[0]) / 2 },
  auc: { center: 0.5, halfRange: (RANGE.areaUnderCurve[1] - RANGE.areaUnderCurve[0]) / 2 },
};

/** The red cross beside a pair the device refuses (drawn, not typed, so it adds no text). */
function RefusedCross({ label, size = 12 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" role="img" aria-label={label}>
      <path d="M3.5 3.5 L12.5 12.5 M12.5 3.5 L3.5 12.5" stroke={T.refused} strokeWidth="2.4"
        strokeLinecap="round" />
    </svg>
  );
}

/** A plain axis in the shared figure style, for the render manager's figures. */
function axisStyle(extra = {}) {
  return mergeDeep(PLOTLY_LAYOUT.xaxis, extra);
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
// area, `_l13_search_left_leg_vas.csv`). Re-run 2026-09-26 when every chance test became the exact
// rotation test (decision 315; `_ns315/l13_after_left_leg_vas.csv`): the counts below are that run's. Its headline lines are printed in bold at the top of the
// "Reading guide" drawer, for RCS08 only: they are a finding about one record, not a rule.
export const L13_SEARCH_UID = "2e3c75c00d7f4f37b53a048d195f11da";
/** The one plain sentence the search's fold opens on (SPEC.md section 5.1, Background). */
export const L13_SEARCH_LEAD = "Across 252 ways of pairing reports with recordings on L 1\u207b3\u207a, no band "
  + "rose with Left Leg VAS pain enough to survive the 22-band correction.";
export const L13_SEARCH_LINES = [
  "Exploratory search, 2026-09-21 (counts re-run 2026-09-26), L 1\u207b3\u207a, Left Leg VAS: 252 settings \u2014 windows 2, 5, 10, 20, 30, 60, "
    + "120 min; pairing (report picks nearest recordings; recording picks nearest report; recording picks next report); "
    + "cap 1, 3, 10 per rating; reuse on/off (one recording may answer several reports); clinic sheets on/off.",
  "No positive band survives the 22-band correction on L 1\u207b3\u207a: 0 positive rows with q < 0.05 out of 5,544 "
    + "(q = p corrected for all 22 bands).",
  // THE WHOLE SEARCH'S ANSWER (panel A item 2, 2026-09-22): the measured proxy, published once.
  // The full shuffle of the whole 252-setting search is not run (about 33 min per shuffle).
  "Whole search: a positive cell with p < 0.05 appeared in none of the 252 settings; about 106 would if the settings "
    + "were independent (they are not, so fewer). Sheets off: 4.1% of cells under p 0.05 against the 5% chance gives; "
    + "sheets on: 23%, all negative. A count, not a calibrated p-value for the search as a whole.",
  "Sheets off (home surveys only): no cell reaches the grid\u2019s \u201cestablished\u201d verdict. Nearest: 24.5 Hz "
    + "at 60 s, 120-min window, each recording picking the next report after it: r 0.32 (0.16 to 0.46), n 61, q 0.25. "
    + "\u201cEstablished\u201d = interval clears zero and beats the shuffled best of nine lengths; this cell meets only "
    + "the first, and q 0.25 fails the 22-band correction. 21.5\u201325.5 Hz are \u201csupported\u201d in 0\u20138 settings "
    + "per window, as chance gives on the negative side.",
  "Sheets on (+ clinic titration scores): positive cluster vanishes; 10\u201322 of 22 bands per setting fall "
    + "with pain, 72 rows with q < 0.05 on the negative side, all with sheets in. Titration scores carry a "
    + "strong negative pain\u2013power link the chronic record lacks.",
  "Current in force explains much of the rest (2026-09-22). With the current at each report removed from band power "
    + "and score (the \u201cadjust for the current in force\u201d switch), positive readings shrink: L 0\u207b3\u207a, "
    + "22.5\u201327.5 Hz, +0.08 to +0.20 becomes +0.01 to +0.12 (NRS); L 1\u207b3\u207a negatives strengthen "
    + "(\u22120.13 to \u22120.18 becomes \u22120.23 to \u22120.28). The plain value still selects bands and sets "
    + "verdicts; the adjusted one is shown beside it.",
  "Lead for the next titration session (24.5 Hz, 60 s), not a band to program.",
];

// ---- THE STATUS AT THE HEAD OF THE HEAT MAPS (decision 304; the review's B3, and the Closed-Loop
// decision card's pattern of 2026-09-26: one status line, red bullets of five words or fewer for what
// the device refuses, yellow for evidence not yet evaluated, the details folded, nothing said twice).

/** The side a sweep's contact pair is on, from the response's own fields. */
function sideOf(ch, sw) {
  const h = (sw && sw.display_hemisphere) || "";
  if (/left/i.test(h) || /_LEFT$/.test(ch)) return "Left";
  if (/right/i.test(h) || /_RIGHT$/.test(ch)) return "Right";
  return null;
}

/**
 * Which pairs the device refuses with today's stimulating contacts, READ from the response's
 * `sensing_rule` block (decisions 217, 243, 247: the Stim Optimizer's `sensing_rule_block` shape,
 * `by_side[side].allowed_channel`). Nothing is worked out here: with no block on the response the
 * answer is null and the page marks nothing. A side with no rule applied (no stimulating contact on
 * record) refuses nothing; a side whose contacts allow no pair refuses every pair on it.
 */
export function refusedPairs(sweeps, rule) {
  const bySide = rule && rule.by_side;
  if (!bySide) return null;
  const names = Object.keys(sweeps || {});
  const refused = names.filter((ch) => {
    const side = sideOf(ch, sweeps[ch]);
    const r = side && bySide[side];
    return !!(r && r.rule_applied && r.allowed_channel !== ch);
  });
  const allowed = ["Left", "Right"].map((side) => bySide[side])
    .filter((r) => r && r.rule_applied && r.allowed_channel && names.includes(r.allowed_channel))
    .map((r) => r.allowed_display || r.allowed_channel);
  return { refused, allowed, total: names.length };
}

/** How many (pair, band) best cells clear the 22-band correction, split by direction. */
export function correctionCounts(sweeps) {
  let rise = 0; let fall = 0; const pairs = [];
  Object.keys(sweeps || {}).forEach((ch) => {
    const sw = sweeps[ch];
    let here = 0;
    ((sw && sw.best_correlation_rows) || []).forEach((r) => {
      const q = r.family_wise_q_8_to_30hz == null ? NaN : Number(r.family_wise_q_8_to_30hz);
      const rr = Number(r.pearson_r);
      if (!(q < 0.05) || !Number.isFinite(rr) || rr === 0) return;
      if (rr > 0) rise += 1; else fall += 1;
      here += 1;
    });
    if (here) pairs.push((sw && sw.display_short) || ch);
  });
  return { rise, fall, pairs };
}

/** The status line, from the grid response alone. */
export function gridStatusLine(result, metricLabel) {
  const sweeps = (result && result.band_time_sweep) || {};
  const win = result && result.settings_applied && result.settings_applied.match_tolerance_min;
  const head = [metricLabel, Number.isFinite(Number(win)) ? `${Number(win)}-min window` : null]
    .filter(Boolean).join(", ");
  const { rise, fall, pairs } = correctionCounts(sweeps);
  const where = pairs.length ? `, on ${pairs.join(", ")}` : "";
  const band = (n) => (n === 1 ? "band" : "bands");
  const verb = (n, one, many) => (n === 1 ? one : many);
  return `${head ? `${head}: ` : ""}after allowing for the 22 bands tested in each pair, ${rise} ${band(rise)} `
    + `${verb(rise, "rises", "rise")} with pain and ${fall} ${verb(fall, "falls", "fall")} with it${where}.`;
}

/**
 * The page head's status, read off the correlation grid (SPEC.md section 5.1 item 1, the taste
 * audit's E4, 2026-09-26): the status sentence, and the status list -- a red ✕ item for the pairs
 * the device refuses with today's contacts, an amber ▲ item when no stability answer has reached
 * the grid. The words are the ones the heat-map card printed before they moved to the page head.
 * Returns null while there is no grid.
 */
export function gridStatusParts(result, sw, metricLabel) {
  if (!result || !sw) return null;
  const sweeps = result.band_time_sweep || {};
  const rule = result.sensing_rule;
  const pairs = refusedPairs(sweeps, rule);
  const rows = sw.best_correlation_rows || [];
  const stabilityUntested = rows.length > 0 && rows.every((r) => r.cross_setting_stability)
    && rows.every((r) => (r.cross_setting_stability || {}).answer === "not tested");
  const items = [];
  if (pairs && pairs.refused.length) {
    items.push({ state: "refused", text: `${pairs.refused.length} of ${pairs.total} pairs refused`, key: "refused" });
  }
  if (stabilityUntested) items.push({ state: "caution", text: "Stability not yet tested", key: "stability" });
  const sentence = `${pairs && pairs.allowed.length ? `Allowed pairs today: ${pairs.allowed.join(", ")}. ` : ""}`
    + gridStatusLine(result, metricLabel);
  return { sentence, items, pairs, rule };
}

/** The device's sensing rule in plain words, printed in the open beside the refused count. */
export const SENSING_RULE_PLAIN = "Sensing only on the two contacts on either side of the stimulating "
  + "contact; other pairs can't be programmed today.";

/**
 * Why the device refuses the pairs: one plain sentence in the open, next to the refused count (a
 * refusal's reason is never folded, SPEC section 4 rule 4), and each lead's own reason one click
 * away. Nothing when no pair is refused.
 */
export function RefusalReason({ pairs, rule }) {
  if (!pairs || !pairs.refused.length || !rule || !rule.by_side) return null;
  return (
    <MDBox data-testid="refusal-reason" mt={1}>
      <MDTypography component="p" sx={{ ...TYPE.body, color: T.ink, m: 0, maxWidth: LAYOUT.proseMax }}>
        {SENSING_RULE_PLAIN}
      </MDTypography>
      <Fold show="Contacts and allowed pair" hide="Hide each lead's contacts">
        {["Left", "Right"].map((side) => {
          const r = rule.by_side[side];
          if (!r || !r.rule_applied) return null;
          return (
            <MDTypography key={side} component="span" display="block" sx={{ ...TYPE.body, color: T.ink2 }}>
              {`${side}: ${r.allowed_display ? `${r.allowed_display} only` : "no allowed pair"}`}
            </MDTypography>
          );
        })}
      </Fold>
    </MDBox>
  );
}

export function bulletsFor(sw) {
  // Concise since 2026-09-15 (the PI). The backend's own notes are already short; the three
  // display-only bullets say one thing each; the snapshot bullet is gone from here because the
  // orange caption above the grid already carries it (say a small point once).
  const notes = sw.notes || [];
  return [
    ...notes.slice(0, 3),
    "Dark ring: column's best square; heavy ring: survives correction for 22 bands (research finding, "
      + "not a device setting).",
    "Left grid ignores high/low cuts; right grid recomputes.",
    "Click a square: its R (Pearson) and Mann-Whitney p, uncorrected.",
    "Colours saturate at \u00b10.5 (R) and 0.25/0.75 (AUC; 0.5 = chance); hover shows the true value.",
    // P-19 (the PI, 2026-09-25): the two sources, named here once in full and TD / PSD everywhere else.
    "Band power: time domain (TD) recording, in 3 s pieces, if any fall in the match window; else "
      + "PSD (the device's 30 s snapshot). The TD/PSD lines above the scatter describe the cell only.",
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
  const { center, halfRange } = kind === "auc" ? SCALE.auc : SCALE.correlation;
  const bestRows = kind === "auc" ? sw.best_auc_rows : sw.best_correlation_rows;
  const bestByCol = useMemo(() => bestCellIndexByColumn(sw, bestRows), [sw, bestRows]);

  // Plain lengths of signal on the axis (the PI, 2026-09-15: nothing appended -- which rows the
  // device can be set to is said once, in the caption's bullets).
  // An asterisk to the left of a row that needed two or more PSDs (see the PSD bullet).
  const yLabels = useMemo(
    () => seconds.map((s) => (needsMultiplePsds(sw, s) ? "*" : "") + secondsLabel(s)), [seconds, sw]);
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
  // heatmap 0, the best-cell rings' white outline 1, the rings 2, stability shapes 3 (decision 185)
  const HIGHLIGHT_TRACE = 4;

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
      colorscale: DIVERGING, zmin: center - halfRange,
      zmax: center + halfRange, zmid: center, showscale: false,
      xgap: 1.5, ygap: 1.5,
      customdata,
      hovertemplate: `${kind === "auc" ? "high pain told from low" : "R"} %{z:.2f}<br>%{x} Hz, %{y} of signal<br>%{customdata}<extra></extra>`,
    });
    // THE BEST-CELL RING (SPEC.md section 3.2): a dark ring on every column's best cell, 1.5 px, with
    // a 1 px white outline so it reads on either end of the scale; 2.5 px where that cell also clears
    // the allowance for 22 bands. (Until 2026-09-26 a white ring; the hover's "circled" points at it.)
    const bestX = [], bestY = [], bestW = [];
    Object.keys(bestByCol).forEach((c) => {
      const b = bestByCol[c];
      if (!b) return;
      bestX.push(centers[Number(c)]); bestY.push(yLabels[b.row]);
      bestW.push(b.row_data && b.row_data.family_wise_significant_8_to_30hz === true ? 2.5 : 1.5);
    });
    fig.traces.push({
      type: "scatter", mode: "markers", x: bestX, y: bestY, showlegend: false,
      marker: { symbol: "circle-open", size: 15, color: T.surface, line: { width: bestW.map((w) => w + 2), color: T.surface } },
      hoverinfo: "skip",
    });
    fig.traces.push({
      type: "scatter", mode: "markers", x: bestX, y: bestY, showlegend: false,
      marker: { symbol: "circle-open", size: 15, color: T.ink, line: { width: bestW, color: T.ink } },
      hoverinfo: "skip",
    });
    // B3 (decision 185): inside each column's ring, the cross-setting stability answer by SHAPE in
    // ink on a small white disc (✓ the same, ✕ different, ? cannot tell), nothing where the answer
    // is not known yet. Read off the best row's `cross_setting_stability`.
    const stX = [], stY = [], stText = [];
    Object.keys(bestByCol).forEach((c) => {
      const b = bestByCol[c];
      const m = b && b.row_data ? stabilityMark(b.row_data.cross_setting_stability) : null;
      if (!m) return;
      stX.push(centers[Number(c)]); stY.push(yLabels[b.row]); stText.push(m.glyph);
    });
    fig.traces.push({
      type: "scatter", mode: "markers+text", x: stX, y: stY, text: stText, showlegend: false,
      textposition: "middle center",
      textfont: { family: FONT_FAMILY, size: FIGURE_TEXT_PX, color: T.ink },
      marker: { symbol: "circle", size: 11, color: T.surface, line: { width: 0 } },
      hoverinfo: "skip",
    });
    // The shared cross-highlight, trace index HIGHLIGHT_TRACE -- always pushed, empty until the
    // second effect below fills it in via restyle. Keeping it here (rather than only when active)
    // is what fixes the highlight trace's index in place across every redraw this effect causes.
    fig.traces.push({
      type: "scatter", mode: "markers", x: [], y: [], showlegend: false,
      marker: { symbol: "square-open", size: 22, color: T.accent, line: { width: 2, color: T.accent } },
      hoverinfo: "skip",
    });
    // The per-cell dash markers for snapshot-served reports (decision 106) were REMOVED on
    // 2026-09-10 at the PI's direction ("the caption in orange below the title is sufficient");
    // the snapshot route now honours the length axis (decision 121), so there is no frozen column
    // to mark. Nothing else is pushed after the highlight trace, whose index is restyled below.
    // Every 3rd band centre, labelled with its TRUE centre ("8.5, 11.5 ..."; SPEC.md section 3.2:
    // never rounded to a whole number, which put "9" under a band centred on 8.5 Hz).
    const xTickVals = centers.filter((c, i) => i % 3 === 0);
    const xTickText = xTickVals.map((c) => String(Number(c)));
    // NO `width` HERE (2026-09-22, found watching the page live). A fixed width stops Plotly's
    // responsive resize from shrinking the figure to its box: the box measured 527 pixels, the
    // figure was drawn at 750, and the 223 extra pixels spilled right -- invisible until a cell was
    // picked, when the side panel covered them and took the columns from about 25 Hz up with it,
    // and cut the hover label off mid-word. Left unset, Plotly draws at the box's width; `width`
    // stays below as the box's own upper limit, so a wide screen draws it no larger than before.
    fig.setLayoutProps({
      height, margin: plotMargin(PLOT_BOTTOM),
      font: PLOTLY_LAYOUT.font, paper_bgcolor: T.surface, plot_bgcolor: T.surface,
      // The heat maps' hover is three lines; set smaller than the figure text (the PI, 2026-09-26).
      hoverlabel: HEATMAP_HOVERLABEL,
      // No gridlines (the cell borders via xgap/ygap already separate the cells), no axis line,
      // no tick marks (`ticks: ""`) on either axis -- floating labels only. The x-axis also
      // replaces Plotly's own automatic tick choice with an explicit array so it labels a real
      // band centre every 3rd column, matching the y-axis's one-label-per-row convention instead
      // of whatever round numbers Plotly would have picked on its own.
      xaxis: axisStyle({ showline: false, ticks: "", tickmode: "array", tickvals: xTickVals,
        ticktext: xTickText, title: { text: "Band centre (Hz)" } }),
      yaxis: axisStyle({ type: "category", autorange: "reversed", showline: false, ticks: "",
        title: { text: "Length of signal" } }),
      hovermode: "closest",
    });
    fig.render();
    // `fig.render()` always shows the hover-activated modebar (zoom/pan/download icons) with its
    // own hardcoded config -- `PlotlyRenderManager` has no override for that, and it is a shared
    // class used by many other pages, so it is not changed here. Instead this one call re-applies
    // the SAME data/layout the render manager just drew, but with the modebar switched off, scoped
    // only to these two heat maps.
    Plotly.react(divId, fig.traces, fig.layout, { ...PLOTLY_CONFIG, doubleClick: false });

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
      <MDTypography variant="caption" sx={{ ...TYPE.body, color: T.ink3 }}>
        {"No grid could be computed for this contact pair."}
      </MDTypography>
    );
  }

  return (
    <MDBox
      sx={flash ? {
        outline: `2px solid ${T.accent}`,
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
function ContactStrip({ sweeps, channel, setChannel, refused }) {
  const names = Object.keys(sweeps || {}).sort((a, b) => {
    const ka = contactSortKey(a, sweeps[a]);
    const kb = contactSortKey(b, sweeps[b]);
    return (ka[0] - kb[0]) || (ka[1] - kb[1]);
  });
  if (names.length <= 1) return null;
  return (
    <MDBox display="flex" flexDirection="row" flexWrap="wrap" gap={2} mb={2}>
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
          <MDBox key={ch} onClick={() => setChannel(ch)} role="button" tabIndex={0}
            aria-pressed={active} data-testid="pair-thumb" data-channel={ch}
            onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setChannel(ch); } }}
            sx={{
              // Small multiples (SPEC.md section 5.1): 120 x 60 px on the SAME colour range as the
              // large maps, the label above in 12 px; the selected pair underlined in the accent; a
              // pair the device refuses today greyed, with its red cross and "Refused today".
              cursor: "pointer", p: 0, background: "none",
              borderBottom: `2px solid ${active ? T.accent : "transparent"}`, pb: 0.5,
              opacity: refused && refused.includes(ch) ? 0.55 : 1,
            }}>
            <MDTypography component="span"
              sx={{ ...TYPE.body, fontWeight: active ? 600 : 400, color: active ? T.accent : T.ink,
                display: "block" }}>
              {label}
            </MDTypography>
            {refused && refused.includes(ch) ? (
              <MDBox display="flex" alignItems="center" gap={0.5}>
                <RefusedCross label="refused by the device" size={12} />
                <MDTypography component="span" sx={{ ...TYPE.body, fontWeight: 600, color: `${T.refused} !important` }}>
                  {"Refused today"}
                </MDTypography>
              </MDBox>
            ) : null}
            {rows && cols ? (
              <svg width={120} height={60} aria-hidden="true">
                {grid.map((row, r) => row.map((v, c) => (
                  <rect key={`${r}-${c}`} x={(c / cols) * 120} y={(r / rows) * 60}
                    width={120 / cols + 0.5} height={60 / rows + 0.5}
                    fill={diverging(v, SCALE.correlation.center, SCALE.correlation.halfRange)} />
                )))}
              </svg>
            ) : (
              <MDBox sx={{ width: 120, height: 60, background: T.fillMuted }} />
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
    const hiColor = BIN_HI;
    const loColor = BIN_LO;
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
      hovertemplate: "%{y:.1f} device units (LSB)<extra>High pain</extra>",
    });
    fig.traces.push({
      type: "violin", x: lowVals.map(() => "Low pain"), y: lowVals,
      name: "Low pain", legendgroup: "low", showlegend: false,
      points: "all", pointpos: 0, jitter: 0.4, marker: loPoint,
      line: { color: loColor }, fillcolor: loFill,
      box: { visible: false }, meanline: { visible: true },
      hovertemplate: "%{y:.1f} device units (LSB)<extra>Low pain</extra>",
    });
    fig.setLayoutProps({
      height: side, margin: plotMargin(PLOT_BOTTOM),
      font: PLOTLY_LAYOUT.font, paper_bgcolor: T.surface, plot_bgcolor: T.surface,
      hoverlabel: PLOTLY_LAYOUT.hoverlabel,
      // The two groups are named on the axis itself ("High pain", "Low pain"): a direct label.
      xaxis: axisStyle({ tickfont: { size: FIGURE_TEXT_PX, color: T.ink } }),
      yaxis: axisStyle({ title: { text: "Band power (device units, LSB)" } }),
      violinmode: "group", showlegend: false,
    });
    fig.render();
    // Same reasoning as PlotlyHeatmap's own identical call: fig.render() always shows the
    // hover-activated modebar with no override in the shared render-manager class; re-apply the
    // same data/layout with it switched off, and with the responsive resize this component exists
    // for, scoped to just this one div.
    // Drag to zoom, double-click back to the full view, no toolbar (the PI, 2026-10-03).
    Plotly.react(divId, fig.traces, fig.layout, { ...PLOTLY_CONFIG, doubleClick: "reset+autosize" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [divId, highVals, lowVals, side]);

  useEffect(() => () => {
    // Guarded: Plotly'''s own .purge() throws (uncaught, since this runs in an effect cleanup with
    // no React error boundary anywhere in this app) if the div it manages is already gone from the
    // DOM -- observed live on a native double-click, which Plotly'''s own internal click pipeline
    // can apparently unmount/rebuild around (this plot's reset-on-double-click is on since
    // 2026-10-03; the heat maps keep it off). Checking first makes this
    // cleanup robust to that regardless of why the div is already gone, rather than chasing the
    // exact internal Plotly sequence that removes it.
    if (figRef.current && document.getElementById(divId)) figRef.current.purge();
  }, [divId]);

  // A true square: width 100% up to `side`, height locked to match via aspect-ratio, so the panel
  // itself is square and Plotly's own responsive resize fills exactly that square.
  return <div id={divId} style={panelBoxStyle(side)} />;
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
    <MDBox component="ul" sx={{ m: 0, mb: 0.5, pl: 2.5 }}>
      {items.map((line) => (
        // Body-size type, left-aligned, one bullet per line (the PI, 2026-10-02: the notes were
        // small caption type, 12 px / 18 px; now 14 px / 22 px, the page's body size).
        <MDTypography key={line} component="li"
          sx={{ ...TYPE.body, display: "list-item", textAlign: "left", color: color || T.ink2 }}>
          {line}
        </MDTypography>
      ))}
    </MDBox>
  );
}

/** Two short bullets (the PI, 2026-09-15: "MUCH more concise, ideally with bullet points"). A
 * contact with no snapshot-served report renders nothing. */
// A note, not a caution (SPEC 2.3: the caution ink always carries ▲), so it is drawn in the caption
// grey like the other notes under the maps.
function DeviceSpectrumCaption({ sw }) {
  return <CaptionBullets items={deviceSpectrumBullets(sw)} />;
}

/** Which rows the device can be set to, from the ranges on the response (`device_timing_ranges`,
 * the one home), as bullets. */
function DeviceTierCaption({ ranges, sw }) {
  return <CaptionBullets items={tierBullets(ranges, (sw && sw.integration_seconds_delivered) || [], sw)} />;
}

/** The symbols inside the circles (decision 185): one bullet, shown only once a stored stability
 * answer has reached at least one row -- a legend for symbols that are not drawn is noise. */
/** What the heat maps pool (decision 186): at-home ratings only, or the sheets' scores too. */
function ClinicSheetCaption({ sw }) {
  return <CaptionBullets items={clinicSheetBullets(sw)} />;
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
    <MDTypography component="p"
      sx={{ ...TYPE.title, color: T.ink, display: "block", mb: 0.5, mt: 0, textAlign: "center" }}>
      {`${channelLabel(pinnedCell.channel)} · ${pinnedCell.center} Hz · `}
      {`${secondsLabel(pinnedCell.secondsDisplay != null ? pinnedCell.secondsDisplay : pinnedCell.seconds)} of signal`}
    </MDTypography>
  );
}

/** The box a statistics line sits in: the same centred box and left inset as the plot below it, so
 *  the line starts where the plot area starts (the PI, 2026-10-02: the lines were offset). */
const statsBoxSx = () => ({ width: "100%", textAlign: "center", minWidth: 0 });

/** ONE line, never wrapped: the headline statistic above a plot. */
function HeadlineLine({ testId, title, children }) {
  return (
    <MDTypography component="p" data-testid={testId} title={title}
      sx={{ ...TYPE.body, color: T.ink, display: "block", mb: 0.25, mt: 0,
        whiteSpace: "nowrap" }}>
      {children}
    </MDTypography>
  );
}

/**
 * The clicked square's two statistics lines. Since the redesign of 2026-09-26 the two large maps sit
 * side by side and the clicked square's title (`PanelTitle`), these lines and the two plots sit in
 * the row under them: the scatter under the correlation map, the violin under the area map.
 */
export function ScatterStatsLine({ cell, pinnedCell, sw, side }) {
  if (!pinnedCell) {
    return (
      <MDTypography variant="caption" sx={{ ...TYPE.body, color: T.ink3 }}>
        {"Click a square to see its ratings plotted against band power, with the fitted line."}
      </MDTypography>
    );
  }
  if (!cell || cell.loading || !cell.points || !cell.points.length) {
    return (
      <MDTypography variant="caption" sx={{ ...TYPE.body, color: T.ink3 }}>
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
  const nSheet = cell.points.filter((pt) => pt.from_clinic_sheet).length;
  return (
    <MDBox sx={statsBoxSx(side)}>
      <HeadlineLine testId="scatter-headline" title="p is uncorrected">
        {`r = ${num(r, 2)}, ${pEquals(p)}, n = ${n}`}
      </HeadlineLine>
      {/* The scatter and the line below are fitted to these same n pairs; the clinic-sheet ratings
          among them (decision 186) are drawn hollow and counted here, under the headline. */}
      {nSheet ? (
        <MDTypography variant="caption" sx={{ ...TYPE.body, color: T.ink3, display: "block", mb: 0.5 }}>
          {`${nSheet} of them clinic-sheet scores (hollow points)`}
        </MDTypography>
      ) : null}
      {readout && readout.text ? (
        <MDTypography variant="caption" sx={{ ...TYPE.body, display: "block", mb: 0.5,
          color: readout.isBest ? T.ink : T.ink3, fontWeight: readout.isBest ? 600 : 400 }}>
          {readout.text}
        </MDTypography>
      ) : null}
      {/* P-19 (the PI, 2026-09-25): the cell's correlation on its TD reports alone and on its PSD
          reports alone, one line of text above the scatter, off the grid response. Never in the
          hover, never a figure; nothing for a stored grid built before the split. */}
      {(() => {
        const line = sourceSplitLine(sw, pinnedCell.col, pinnedCell.row);
        return line ? (
          <MDTypography variant="caption" data-testid="source-split-line"
            sx={{ ...TYPE.body, color: T.ink2, display: "block", mb: 0.5, whiteSpace: "pre-line" }}>
            {line}
          </MDTypography>
        ) : null;
      })()}
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

    const colorFor = (label) => (label === "high" ? BIN_HI : (label === "low" ? BIN_LO : BIN_MID));
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
          hovertemplate: `%{x:.0f} device units, %{y:.1f}${sheet ? " (clinic sheet)" : ""}<extra></extra>`,
        });
      });
    });
    fig.traces.push({
      type: "scatter", mode: "lines", showlegend: false, hoverinfo: "skip",
      x: [xlo, xhi], y: [intercept + slope * xlo, intercept + slope * xhi],
      line: { color: T.ink, width: 1.5 },
    });

    // Direct labels (SPEC.md section 5.1): "r = ..." at the end of the fitted line, and the three
    // kinds of point named once at the right edge, in their text-safe inks, instead of a legend.
    const rVal = (() => {
      const syy = ys.reduce((a, v) => a + (v - my) ** 2, 0);
      return sxx > 0 && syy > 0 ? sxy / Math.sqrt(sxx * syy) : null;
    })();
    const annotations = [];
    if (rVal != null) {
      // Inside the plot, above the line's end: the right margin is the small shared gap now.
      annotations.push({ ...directLabel(xhi, intercept + slope * xhi, `r = ${num(rVal, 2)}`, T.ink),
        xanchor: "right", xshift: -4, yanchor: "bottom", yshift: 4 });
    }
    const named = [];
    if (groups.high.length) named.push(["high pain", textInk(BIN_HI)]);
    if (groups.low.length) named.push(["low pain", BIN_LO]);
    if (points.some((pt) => pt.from_clinic_sheet)) named.push(["\u25cb clinic sheet", T.ink3]);
    named.forEach(([text, color], i) => annotations.push({
      xref: "paper", yref: "paper", x: 1, y: 1 - i * 0.07, xanchor: "right", yanchor: "top",
      text, showarrow: false, font: { family: FONT_FAMILY, size: FIGURE_TEXT_PX, color },
    }));

    fig.setLayoutProps({
      height: side, margin: plotMargin(PLOT_BOTTOM),
      font: PLOTLY_LAYOUT.font, paper_bgcolor: T.surface, plot_bgcolor: T.surface,
      hoverlabel: PLOTLY_LAYOUT.hoverlabel,
      xaxis: axisStyle({ title: { text: "Band power (device units, LSB)" } }),
      yaxis: axisStyle({ title: { text: `Pain${metricLabel ? ` (${metricLabel})` : ""}` } }),
      annotations,
      showlegend: false,
    });
    fig.render();
    // Drag to zoom, double-click back to the full view, no toolbar (the PI, 2026-10-03).
    Plotly.react(divId, fig.traces, fig.layout, { ...PLOTLY_CONFIG, doubleClick: "reset+autosize" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [divId, points, side, metricLabel]);

  useEffect(() => () => {
    // Guarded: Plotly'''s own .purge() throws (uncaught, since this runs in an effect cleanup with
    // no React error boundary anywhere in this app) if the div it manages is already gone from the
    // DOM -- observed live on a native double-click, which Plotly'''s own internal click pipeline
    // can apparently unmount/rebuild around (this plot's reset-on-double-click is on since
    // 2026-10-03; the heat maps keep it off). Checking first makes this
    // cleanup robust to that regardless of why the div is already gone, rather than chasing the
    // exact internal Plotly sequence that removes it.
    if (figRef.current && document.getElementById(divId)) figRef.current.purge();
  }, [divId]);

  if (!points.length) return null;
  // A true square: width 100% up to `side`, height locked to match via aspect-ratio, so the panel
  // itself is square and Plotly's own responsive resize fills exactly that square -- rather than
  // filling a rectangular column at a fixed height (the previous, non-square "fill the panel" fix).
  return <div id={divId} style={panelBoxStyle(side)} />;
}

/** Persistent panel next to the AUC grid: two violins (high/low pain) and the cell's own AUC with
 * its Mann-Whitney p and the two counts, read off the grid response (decision 188). */
function ViolinPanel({ cell, pinnedCell, channelLabel, height, aucValue, sw, part = "both" }) {
  // `part` (2026-09-26): the statistics and the plot are drawn in separate rows of the shared grid,
  // so the violin starts at the same height as the scatter; "both" keeps the old single block.
  const showStats = part !== "plot";
  const showPlot = part !== "stats";
  if (!pinnedCell) {
    if (!showStats) return null;
    return (
      <MDTypography variant="caption" sx={{ ...TYPE.body, color: T.ink3 }}>
        {"Click a square to compare band power in high-pain and low-pain reports."}
      </MDTypography>
    );
  }
  if (!cell || cell.loading || !cell.points || !cell.points.length) {
    if (!showStats) return <MDBox sx={{ height }} />;
    return (
      <MDTypography variant="caption" sx={{ ...TYPE.body, color: T.ink3 }}>
        {cell && cell.loading ? "Loading…" : "No underlying pairs could be loaded for this cell."}
      </MDTypography>
    );
  }
  const pts = cell.points;
  const highVals = pts.filter((p) => p.label === "high").map((p) => p.power);
  const lowVals = pts.filter((p) => p.label === "low").map((p) => p.power);
  const { p, nHigh, nLow } = cellNP(sw, "auc", pinnedCell.col, pinnedCell.row);

  const statsBlock = (
    <MDBox sx={statsBoxSx(height)}>
      {/* No title here -- it duplicated the scatter panel's own title exactly (both describe the
          same pinned cell); that one copy, above the scatter panel, is now the only one. */}
      <HeadlineLine testId="violin-headline" title="p is uncorrected">
        {`AUC = ${num(aucValue, 2)}, ${pEquals(p)}, n = ${nHigh} high, n = ${nLow} low`}
      </HeadlineLine>
      {/* The grid's own corrected statistic for this cell, the same small line in the same ink as
          beside the scatter (the PI, 2026-09-15); the plot below moves down by its height. */}
      {(() => {
        const readout = (sw && pinnedCell)
          ? bestCellReadout(sw, "auc", pinnedCell.col, pinnedCell.row, { includeN: false }) : null;
        return readout && readout.text ? (
          <MDTypography variant="caption" sx={{ ...TYPE.body, display: "block", mb: 0.5,
            color: readout.isBest ? T.ink : T.ink3, fontWeight: readout.isBest ? 600 : 400 }}>
            {readout.text}
          </MDTypography>
        ) : null;
      })()}
    </MDBox>
  );
  const plotBlock = (
    <PlotlyViolin divId="biomarker-violin-panel" highVals={highVals} lowVals={lowVals}
      side={height} />
  );
  if (!showPlot) return statsBlock;
  if (!showStats) return plotBlock;
  return <MDBox>{statsBlock}{plotBlock}</MDBox>;
}

// SweepMetric (which raw pain score the correlation and AUC are computed against) is grouped with
// the matching keys rather than left unclassified: changing which score is used changes BOTH
// grids, the same as changing the match window or direction, so it must trigger the "replace both"
// path rather than accidentally falling into the catch-all branch that also happens to replace
// both -- correct by construction rather than by coincidence of the fallback's own behaviour.
// The clinic-sheet switch is a matching setting too: it decides which ratings are paired, so it
// changes the correlation grid as well as the area grid (review of 2026-09-26, finding 2).
const MATCH_SETTING_KEYS = ["MatchToleranceMin", "MatchDirection", "AllowWindowReuse", "LabelMetric",
  "SweepMetric", "IncludeClinicSheetRatings"];
const BIN_SETTING_KEYS = ["LabelStrategy", "PercentileLow", "PercentileHigh"];

function settingsSubset(params, keys) {
  const out = {};
  keys.forEach((k) => { out[k] = params ? params[k] : undefined; });
  return out;
}

/** True when a new grid differs from the one on screen ONLY in the high / low split, so the
 *  correlation grid (which the split cannot change) keeps its frame and only the area grid is
 *  replaced (PRD section 3). Any matching change, or no earlier grid, replaces both. */
export function onlyTheAucGridChanges(prev, next) {
  if (!prev || !next) return false;
  const differs = (k) => settingsSubset(prev, [k])[k] !== settingsSubset(next, [k])[k];
  return !MATCH_SETTING_KEYS.some(differs) && BIN_SETTING_KEYS.some(differs);
}

// The settings a reader can move, in the words the matching panel uses for them. A key listed as
// ignored cannot differ between the grid on screen and the request (the score has its own slot) or
// is not a setting at all.
const SETTING_WORDS = [
  [["MatchToleranceMin"], "the match window"],
  [["MatchDirection"], "the match direction"],
  [["AllowWindowReuse"], "whether one stretch of recording may answer more than one report"],
  [["LabelStrategy", "PercentileLow", "PercentileHigh"], "the high / low split"],
  [["IncludeClinicSheetRatings"], "the clinic sheet scores"],
];
const SETTINGS_NOT_NAMED = ["source", "SlidingWindow", "SweepMetric", "LabelMetric"];

/** Which settings differ between the grid on screen and the controls, in plain words, each once. */
export function settingsChangedWords(shown, current) {
  if (!shown || !current) return [];
  const norm = (o) => { try { return JSON.parse(settingsKey(o)) || {}; } catch (e) { return {}; } };
  const a = norm(shown);
  const b = norm(current);
  const differs = (k) => JSON.stringify(a[k] === undefined ? null : a[k])
    !== JSON.stringify(b[k] === undefined ? null : b[k]);
  const words = SETTING_WORDS.filter(([keys]) => keys.some(differs)).map(([, w]) => w);
  const named = new Set(SETTINGS_NOT_NAMED.concat(...SETTING_WORDS.map(([keys]) => keys)));
  if (Object.keys({ ...a, ...b }).some((k) => !named.has(k) && differs(k))) words.push("another setting");
  return words;
}

/** "a", "a and b", "a, b and c". */
function joinWords(words) {
  if (words.length <= 1) return words.join("");
  return `${words.slice(0, -1).join(", ")} and ${words[words.length - 1]}`;
}

/** The request for one clicked square. It carries the settings the SHOWN grid was computed under,
 *  so the scatter and violin pair the same reports with the same recordings as the r and q printed
 *  for that square, even when the controls have moved since (review of 2026-09-26, finding 1). */
export function heatmapCellRequest({ participantUid, shownSettings, requestParams, metric,
  channel, center, seconds }) {
  const base = { ...(shownSettings || requestParams || {}) };
  delete base.SweepMetric;
  return {
    ParticipantId: participantUid, ...base, SweepMetric: metric,
    BandTimeSweepCell: "1", Channel: channel, BandCenterHz: center, IntegrationSeconds: seconds,
  };
}

/** The settings one pain score's grid is filed under (its slot's key). The page's own score is NOT
 *  part of another score's key: every score's grid carries its own `LabelMetric` and `SweepMetric`
 *  (the server reads `SweepMetric` first, `sweep_metric_param`), so a grid fetched in the background
 *  while another score was on screen is the same entry as the one fetched on the switch. Before
 *  this, the background fetch carried the page's score and the switch looked for its own, so every
 *  switch said "the settings on this page have changed" (the PI, 2026-10-02). Only matching and
 *  split settings can differ between two keys of one score. */
export function gridSettingsFor(requestParams, metricKey) {
  return { ...requestParams, LabelMetric: metricKey, SweepMetric: metricKey };
}

function BiomarkerHeatmapGrids({ participantUid, requestParams, availableMetrics, pageMetric,
  metricLabel, onOpenInClosedLoop, onStatus, onStale }) {
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
  const prevSettingsRef = useRef(null);

  // ONE shared hover state and ONE shared pinned state, read by BOTH grids -- this is what makes
  // hovering or clicking a cell in either grid highlight the SAME cell on the other one, and what
  // lets one click populate both persistent side panels at once (open item 7, part 4d).
  const [hoveredCell, setHoveredCell] = useState(null);       // { row, col } | null
  const [pinnedCell, setPinnedCell] = useState(null);         // { row, col, channel, center, seconds }
  const [pinnedCellData, setPinnedCellData] = useState(null);
  // The fetched squares live at module scope (`heatmapCellCache.js`), so they survive a switch of
  // pain score, a remount and leaving the page (the PI, 2026-10-02).

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
  const cur = useMemo(() => gridSettingsFor(requestParams, metric),
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

  // WHAT THE SHOWN GRID WAS COMPUTED UNDER. The shared cache hands back the grid it holds when a
  // setting moves, marked stale, and starts no request (the PI's design: the page's Recompute
  // rebuilds). The entry's own key is the settings it was computed with; it is read here so the
  // grid can say which settings have moved, and so a clicked square is fetched with the SAME
  // settings as the grid it was clicked on.
  const shownKey = (participantUid && cachedGrid.data)
    ? ((getResult(biomarkerHeatmapSlot(metric), participantUid, null) || {}).key || null) : null;
  const shownSettings = useMemo(() => {
    try { return shownKey ? JSON.parse(shownKey) : null; } catch (e) { return null; }
  }, [shownKey]);
  // Out of date: a grid is on screen and was computed under other settings (or before a server
  // restart). Not while its rebuild is running: the waiting words say that instead.
  const outOfDate = !!cachedGrid.data && cachedGrid.stale && !loading;
  const changedWords = useMemo(() => (outOfDate ? settingsChangedWords(shownSettings, cur) : []),
    [outOfDate, shownSettings, cur]);
  const otherStaleReasons = (cachedGrid.staleReasons || []).filter(
    (r) => !/settings on this page have changed/.test(r));
  const staleSentence = !outOfDate ? null
    : changedWords.length
      ? `These heat maps were computed before ${joinWords(changedWords)} ${changedWords.length > 1 ? "were" : "was"} changed; they still show the earlier settings.`
      : `These heat maps may be out of date: ${otherStaleReasons[0] || "they were computed under other settings"}.`;
  const staleSignature = `${outOfDate}|${staleSentence || ""}`;
  useEffect(() => {
    if (onStale) {
      onStale({ stale: outOfDate, changed: changedWords,
        reasons: outOfDate ? [`the heat maps: ${staleSentence}`] : [] });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [onStale, staleSignature]);

  // THE ASYMMETRIC CORRELATION/AUC UPDATE RULE (PRD §3), UNCHANGED, now keyed off the cached
  // bundle's own identity rather than a raw network response -- it fires exactly when the bundle
  // for the CURRENTLY SELECTED metric changes, whether that is a genuine fetch or a switch onto a
  // metric that was already warm from the background prefetch below.
  useEffect(() => {
    const d = cachedGrid.data;
    if (!d) return;
    // Compared between the settings the previous grid and this one were COMPUTED under (read off
    // the cache entry), not the controls: with a grid served stale the two can differ.
    const prev = prevSettingsRef.current;
    const next = shownSettings || cur;
    prevSettingsRef.current = next;

    if (corrResult && onlyTheAucGridChanges(prev, next)) {
      // Correlation depends only on matching (PRD §3): keep the previous correlation grid's
      // object identity so its frame does not redraw, and replace the AUC grid with a flash.
      setAucResult(d);
      setAucFlashKey((k) => k + 1);
    } else {
      // A matching setting moved, there was no grid yet, or nothing that changes either grid
      // moved (then the freshest response is still taken, so a served-from-store flag is current).
      setCorrResult(d);
      setAucResult(d);
    }
    const sweeps = (d && d.band_time_sweep) || {};
    const keys = Object.keys(sweeps);
    if (keys.length && (!channel || !sweeps[channel])) setChannel(keys[0]);
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
    // Not while the selected score's own grid is out of date: the other scores would be built under
    // settings the grid on screen does not show, before the reader has asked for them.
    if (!participantUid || !requestParams || loading || cachedGrid.stale) return undefined;
    const gen = (prefetchGenRef.current += 1);
    const others = options.filter((o) => o.key !== metric);
    let cancelled = false;
    (async () => {
      // eslint-disable-next-line no-restricted-syntax
      for (const o of others) {
        if (cancelled || prefetchGenRef.current !== gen) return;
        const otherCur = gridSettingsFor(requestParams, o.key);
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
  }, [participantUid, reqKey, metric, loading, options, cachedGrid.stale]);

  // THE CLOSED-LOOP ANSWERS FOR THE LIKELIEST BANDS, asked for from here (decision 430): once this
  // grid is in and current, and 5 s after, so the reader's own requests go first. Once per page
  // load per participant; the server saves the answers, so choosing one of these bands on the
  // Closed-Loop page is served at once.
  useEffect(() => {
    if (!participantUid || loading || cachedGrid.stale || !cachedGrid.data) return undefined;
    if (CL_PREFETCHED.has(participantUid)) return undefined;
    const t = setTimeout(() => {
      CL_PREFETCHED.add(participantUid);
      prefetchClosedLoopFromBiomarkers(participantUid).catch(() => {});
    }, 5000);
    return () => clearTimeout(t);
  }, [participantUid, loading, cachedGrid.stale, cachedGrid.data]);

  const corrSweeps = (corrResult && corrResult.band_time_sweep) || {};
  const aucSweeps = (aucResult && aucResult.band_time_sweep) || {};
  const corrSw = channel && corrSweeps[channel];
  const aucSw = channel && aucSweeps[channel];
  // The page head prints the status sentence and list (SPEC.md section 5.1 item 1); they are read
  // off this grid, so the grid hands them up whenever what they are read from changes.
  useEffect(() => {
    if (onStatus) onStatus(gridStatusParts(corrResult, corrSw || null, metricLabel));
  }, [onStatus, corrResult, corrSw, metricLabel]);
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
    const key = cellKey(participantUid, metric, shownKey, ch, center, seconds);
    const held = getCell(key);
    if (held !== undefined) return Promise.resolve(held);
    const body = heatmapCellRequest({ participantUid, shownSettings, requestParams, metric,
      channel: ch, center, seconds });
    return SessionController.query("/api/queryBiomarkerAnalysis", body).then((response) => {
      const d = (response && response.data) || {};
      const cell = d.band_time_sweep_cell || { points: [], message: d.message };
      putCell(key, cell);
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

  // THE LAYOUT (the redesign of 2026-09-26, SPEC.md section 5.1 item 2): one card, its title the
  // question it answers, its answer the status line read off the grid; then the pair thumbnails as
  // small multiples on one colour range, the two large maps side by side (each with its key), the
  // clicked square's scatter and violin under them, the caption keys, and two folds.
  const corrKey = (
    <ColorKey scale={DIVERGING} range={RANGE.correlation} lowLabel="falls with pain"
      midLabel="0" highLabel="rises with pain" title="R with pain" />
  );
  const aucKey = (
    <ColorKey scale={DIVERGING} range={RANGE.areaUnderCurve} lowLabel="lower in high pain"
      midLabel="0.5 coin toss" highLabel="higher in high pain"
      title="AUC" />
  );
  const subhead = { ...TYPE.body, fontWeight: 600, color: T.ink, display: "block", mb: 0, mt: 0 };
  const aucCellValue = (pinnedCell && aucSw && aucSw.auc_grid && aucSw.auc_grid[pinnedCell.row])
    ? aucSw.auc_grid[pinnedCell.row][pinnedCell.col] : null;

  // The shared section (taste audit C6, 2026-09-26): the question as its title, the rest as its
  // body. While a grid is being worked out there is no spinner (C2): with a grid already on screen
  // the waiting words sit beside the title; with none, still grey blocks shaped like the grid.
  const waitingWords = "Computing the calibrated grid…";
  return (
    <Section id="biomarker-heat-maps" question="Power–pain heat maps"
      actions={loading && corrSw && aucSw ? (
        <MDTypography component="span" role="status" sx={{ ...TYPE.body, color: T.ink3 }}>
          {waitingWords}
        </MDTypography>
      ) : null}>

        {/* THE HEAT MAPS SAY WHEN THEY ARE OUT OF DATE (review of 2026-09-26, finding 1): a changed
            matching or split setting does not rebuild them; this line names what moved, above the
            maps, and points to the page's one Recompute button (the PI, 2026-10-02: two buttons were redundant). */}
        {staleSentence ? (
          <MDBox data-testid="heatmaps-out-of-date" role="status" mt={1}
            display="flex" flexDirection="row" alignItems="center" flexWrap="wrap" gap={1.5}>
            <MDTypography component="p" sx={{ ...TYPE.body, color: T.ink, m: 0, maxWidth: LAYOUT.proseMax }}>
              <span aria-hidden="true" style={{ color: T.caution, marginRight: 6 }}>{"\u25b2"}</span>
              {staleSentence}
              {" Press Recompute at the top of the page to rebuild them."}
            </MDTypography>
          </MDBox>
        ) : null}

        {err ? (
          <MDTypography component="p" sx={{ ...TYPE.body, display: "block", mt: 1,
            color: T.ink }}>{`The grid could not be computed: ${err}`}</MDTypography>
        ) : null}
        {corrResult && corrResult.message ? (
          <MDTypography component="p"
            sx={{ ...TYPE.body, color: T.ink2, display: "block", mt: 1 }}>{corrResult.message}</MDTypography>
        ) : null}

        {corrSw && aucSw ? (
          <>
            {/* The one caveat line above the maps (SPEC.md section 5.1): how the reports were paired. */}
            {matchDirectionLabel ? (
              <MDTypography component="p" sx={{ ...TYPE.body, color: T.ink3, mt: 2, mb: 2 }}>
                {matchDirectionLabel === "prior"
                  ? "Matched using recordings from before each rating. A research reading, not a setting to program."
                  : "Matched using recordings from either time direction. A research reading, not a setting to program."}
              </MDTypography>
            ) : <MDBox mt={2} />}

            <ContactStrip sweeps={corrSweeps} channel={channel} setChannel={setChannel}
              refused={(refusedPairs(corrSweeps, corrResult && corrResult.sensing_rule) || {}).refused} />

            {/* ONE GRID OF SHARED ROWS (the PI, 2026-09-26: the two maps, and the scatter and the
                violin, sat at different heights because the right title wrapped and the two
                statistics blocks differ in length). Title, key, map, statistics and plot each take
                one row across both columns, so the two columns start every row at the same height
                whatever either holds; on a phone the areas stack column by column. */}
            <MDBox data-testid="heatmap-rows" sx={{
              display: "grid", columnGap: 3, rowGap: 1, alignItems: "start",
              gridTemplateColumns: { xs: "minmax(0, 1fr)", md: "minmax(0, 1fr) minmax(0, 1fr)" },
              gridTemplateAreas: {
                xs: `"t1" "k1" "m1" "t2" "k2" "m2" "pt" "s1" "g1" "s2" "g2" "cap"`,
                md: `"t1 t2" "k1 k2" "m1 m2" "pt pt" "s1 s2" "g1 g2" "cap cap"`,
              },
            }}>
              <MDTypography component="h3" sx={{ ...subhead, gridArea: "t1" }}>
                {"R with pain"}
              </MDTypography>
              <MDBox sx={{ gridArea: "k1" }}>{corrKey}</MDBox>
              <MDBox sx={{ gridArea: "m1", minWidth: 0 }}>
                <PlotlyHeatmap divId="biomarker-heatmap-correlation" sw={corrSw} kind="correlation"
                  deviceRanges={deviceRanges}
                  hoveredCell={hoveredCell} pinnedCell={pinnedCell}
                  onHover={handleHover} onClick={(r, c) => handleClick(corrSw, r, c)} />
              </MDBox>
              <MDTypography component="h3" sx={{ ...subhead, gridArea: "t2" }}>
                {"High vs. low pain classification"}
              </MDTypography>
              <MDBox sx={{ gridArea: "k2" }}>{aucKey}</MDBox>
              <MDBox sx={{ gridArea: "m2", minWidth: 0 }}>
                <PlotlyHeatmap divId="biomarker-heatmap-auc" sw={aucSw} kind="auc"
                  deviceRanges={deviceRanges}
                  hoveredCell={hoveredCell} pinnedCell={pinnedCell} flashKey={aucFlashKey}
                  onHover={handleHover} onClick={(r, c) => handleClick(aucSw, r, c)} />
              </MDBox>

              {/* The clicked square: its title, its two statistics blocks and the two plots. A click
                  on EITHER grid fills both and highlights the square on both. */}
              <MDBox sx={{ gridArea: "pt", mt: 2 }}>
                <PanelTitle pinnedCell={pinnedCell} channelLabel={channelLabel} />
              </MDBox>
              <MDBox sx={{ gridArea: "s1" }}>
                <ScatterStatsLine cell={pinnedCellData} pinnedCell={pinnedCell} sw={corrSw} side={panelHeight} />
              </MDBox>
              <MDBox sx={{ gridArea: "g1", minWidth: 0 }}>
                <PlotlyScatter divId="biomarker-scatter-panel" cell={pinnedCellData}
                  pinnedCell={pinnedCell} side={panelHeight} metricLabel={metricLabel} />
              </MDBox>
              <MDBox sx={{ gridArea: "s2" }}>
                <ViolinPanel part="stats" cell={pinnedCellData} pinnedCell={pinnedCell}
                  channelLabel={channelLabel} height={panelHeight} sw={aucSw}
                  aucValue={aucCellValue} />
              </MDBox>
              <MDBox sx={{ gridArea: "g2", minWidth: 0 }}>
                <ViolinPanel part="plot" cell={pinnedCellData} pinnedCell={pinnedCell}
                  channelLabel={channelLabel} height={panelHeight} sw={aucSw}
                  aucValue={aucCellValue} />
              </MDBox>

              <MDBox sx={{ gridArea: "cap", mt: 2 }}>
                <DeviceSpectrumCaption sw={corrSw} />
                <ClinicSheetCaption sw={corrSw} />
                <DeviceTierCaption ranges={deviceRanges} sw={corrSw} />
                <StabilityCaption sw={corrSw} />
              </MDBox>
            </MDBox>

            <MDBox mt={2} display="flex" flexDirection="row" alignItems="center" flexWrap="wrap" gap={2}>
              <MDButton variant="outlined" color="dark" size="small" disabled={!gridReady}
                sx={{ textTransform: "none", ...TYPE.body, borderColor: T.ink3, color: T.ink }}
                onClick={() => onOpenInClosedLoop && onOpenInClosedLoop({ channel, sweep: corrSw })}>
                {"Open this grid in Closed-Loop \u2192"}
              </MDButton>
              <MDTypography component="span" sx={{ ...TYPE.body, color: T.ink3, maxWidth: 360 }}>
                {gridReady
                  ? "The closed-loop settings page reads this same grid; any square can be picked there as a candidate band."
                  : "Available once the grid has been computed for a sensing contact pair."}
              </MDTypography>
            </MDBox>

            <MDBox mt={2}>
              <Fold show="Reading guide">
                {/* No box inside the card (decision 304): a hairline down the left edge marks the
                    drawer, whose notes are 14 px at weight 400 (SPEC.md section 5.1). `aucSw.notes`
                    is dropped -- both grids come from the same per-channel sweep response. Order:
                    the backend's three "how to read the statistics" notes, the display notes, then
                    the sweep's own mechanical bookkeeping (`bulletsFor`). */}
                <MDBox data-testid="reading-notes"
                  sx={{ borderLeft: `1px solid ${T.rule}`, pl: 2, maxWidth: LAYOUT.proseMax }}>
                  {bulletsFor(corrSw).map((n, i) => (
                    <MDTypography key={i} component="p"
                      sx={{ ...TYPE.body, color: T.ink2, display: "block", mb: 1, mt: 0 }}>
                      {`\u2022 ${n}`}
                    </MDTypography>
                  ))}
                </MDBox>
              </Fold>
              {/* THE 2026-09-21 SEARCH ON L 1-3+, FOR RCS08 ONLY, IN ITS OWN FOLD (decision 304). The
                  lines are a finding about one record, not a way to read the grid. Since the redesign
                  of 2026-09-26 they open on one plain sentence and are set at 14 px, weight 400. */}
              {participantUid === L13_SEARCH_UID ? (
                <MDBox data-testid="l13-search-fold">
                  <Fold show={`The 2026-09-21 search on L 1\u207b3\u207a (${L13_SEARCH_LINES.length} lines)`}
                    hide="Hide the 2026-09-21 search">
                    <MDBox sx={{ borderLeft: `1px solid ${T.rule}`, pl: 2, maxWidth: LAYOUT.proseMax }}>
                      <MDTypography component="p" sx={{ ...TYPE.body, color: T.ink, mt: 0, mb: 1 }}>
                        {L13_SEARCH_LEAD}
                      </MDTypography>
                      {L13_SEARCH_LINES.map((n, i) => (
                        <MDTypography key={`l13-${i}`} component="p" data-testid="l13-search-line"
                          sx={{ ...TYPE.body, color: T.ink2, display: "block", mb: 1, mt: 0 }}>
                          {`\u2022 ${n}`}
                        </MDTypography>
                      ))}
                    </MDBox>
                  </Fold>
                </MDBox>
              ) : null}
            </MDBox>
          </>
        ) : (!loading ? (
          <MDTypography component="p"
            sx={{ ...TYPE.body, color: T.ink3, display: "block", mt: 1 }}>
            {corrResult ? "No band centre produced a grid for this contact pair."
              : waitingWords}
          </MDTypography>
        ) : <GridSkeleton words={waitingWords} shape="heatmaps" />)}
    </Section>
  );
}

export default BiomarkerHeatmapGrids;
