/**
 * THE TWO CALIBRATED HEAT MAPS, AS THE HEADLINE OF THE PAGE (Track A of the heat-map redesign).
 *
 * Builds Option 2, "search-first, minimal chrome" (decision 62 in DECISIONS_and_open_items.md):
 * no cell is pre-selected on load, hovering a cell shows a small preview, clicking pins the full
 * drill-down below the grids, and the sensing contact pair is chosen from a strip of small
 * thumbnail grids rather than a dropdown.
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
 */
import { useEffect, useMemo, useRef, useState } from "react";

import { Card, Grid, CircularProgress, Collapse, IconButton } from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import MDButton from "components/MDButton";

import { SessionController } from "database/session-control";
import PAL from "views/Reports/ClosedLoopSim/palette";

const num = (v, d = 3) => (v == null || !Number.isFinite(Number(v)) ? "—" : Number(v).toFixed(d));

// ---------------------------------------------------------------------------------------------
// COLOUR. A diverging scale around the value that means "no relationship" for each quantity --
// 0 for a correlation, 0.5 (never 0) for an area under the curve. House rule: an AUC is never
// read against zero.
// ---------------------------------------------------------------------------------------------
function diverging(v, center, halfRange) {
  if (v == null || !Number.isFinite(Number(v))) return "#e9e9e9";
  const t = Math.max(-1, Math.min(1, (Number(v) - center) / halfRange));
  const neg = [0, 114, 178];      // blue
  const pos = [213, 94, 0];       // vermillion
  const mid = [255, 255, 255];
  const lerp = (a, b, k) => a + (b - a) * k;
  const c = t < 0
    ? [lerp(neg[0], mid[0], 1 + t), lerp(neg[1], mid[1], 1 + t), lerp(neg[2], mid[2], 1 + t)]
    : [lerp(mid[0], pos[0], t), lerp(mid[1], pos[1], t), lerp(mid[2], pos[2], t)];
  return `rgb(${c.map((x) => Math.round(x)).join(",")})`;
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

/**
 * One heat map, drawn as plain SVG rather than a server-rendered figure so a cell can carry a
 * hover and a click handler directly. `frameKey` changes only when this grid's own data should
 * visually redraw (see the component-level note above); passing the same key across a re-render
 * with new numbers is what keeps the correlation grid's frame looking untouched.
 */
function Heatmap({ sw, kind, hovered, pinned, onHover, onClick, flashKey, width = 460 }) {
  const centers = sw.center_freqs_hz || [];
  const seconds = sw.integration_seconds_requested || sw.integration_seconds_delivered || [];
  const grid = kind === "auc" ? sw.auc_grid : sw.correlation_grid;
  const rows = (grid || []).length;
  const cols = centers.length;
  const center = kind === "auc" ? 0.5 : 0;
  const halfRange = kind === "auc" ? 0.5 : 1;
  const bestRows = kind === "auc" ? sw.best_auc_rows : sw.best_correlation_rows;
  const bestByCol = useMemo(() => bestCellIndexByColumn(sw, bestRows), [sw, bestRows]);

  const [flash, setFlash] = useState(false);
  useEffect(() => {
    if (!flashKey) return;
    setFlash(true);
    const t = setTimeout(() => setFlash(false), 900);
    return () => clearTimeout(t);
  }, [flashKey]);

  if (!rows || !cols) {
    return (
      <MDTypography variant="caption" color="dark" fontStyle="italic" sx={{ fontSize: 11.5 }}>
        {"No grid could be computed for this contact pair."}
      </MDTypography>
    );
  }
  const padL = 46, padB = 22, padT = 4, padR = 4;
  const height = Math.max(160, rows * 20 + padT + padB);
  const cw = (width - padL - padR) / cols;
  const ch = (height - padT - padB) / rows;

  const cells = [];
  for (let r = 0; r < rows; r += 1) {
    for (let c = 0; c < cols; c += 1) {
      const v = (grid[r] || [])[c];
      const isHover = hovered && hovered.row === r && hovered.col === c;
      const isPinned = pinned && pinned.row === r && pinned.col === c;
      const isBest = bestByCol[c] && bestByCol[c].row === r;
      const passesFamily = isBest && bestByCol[c].row_data
        && bestByCol[c].row_data.family_wise_significant_8_to_30hz === true;
      cells.push(
        <g key={`${r}-${c}`}>
          <rect
            x={padL + c * cw} y={padT + r * ch} width={cw} height={ch}
            fill={diverging(v, center, halfRange)}
            stroke={isPinned ? "#1a1a1a" : (isHover ? "#333" : "#ffffff")}
            strokeWidth={isPinned ? 2.5 : (isHover ? 1.5 : 0.6)}
            style={{ cursor: "pointer" }}
            onMouseEnter={() => onHover(r, c)}
            onClick={() => onClick(r, c)}
          />
          {passesFamily ? (
            <circle cx={padL + c * cw + cw / 2} cy={padT + r * ch + ch / 2} r={Math.min(cw, ch) * 0.14}
              fill="none" stroke="#1a1a1a" strokeWidth={1.4} />
          ) : null}
        </g>
      );
    }
  }
  // Sparse axis labels so text does not overlap: every 3rd band centre, every row's seconds.
  const xLabels = centers.map((c, i) => (i % 3 === 0 ? (
    <text key={i} x={padL + i * cw + cw / 2} y={height - padB + 12} fontSize={9} textAnchor="middle"
      fill="#444">{Number(c).toFixed(0)}</text>
  ) : null));
  const yLabels = seconds.map((s, i) => (
    <text key={i} x={padL - 4} y={padT + i * ch + ch / 2 + 3} fontSize={9} textAnchor="end"
      fill="#444">{Number(s) >= 60 ? `${Math.round(s / 60)}m` : `${Number(s).toFixed(0)}s`}</text>
  ));
  return (
    <MDBox
      onMouseLeave={() => onHover(null, null)}
      sx={flash ? {
        outline: `2px solid ${PAL.accentBorder || "#0072B2"}`,
        borderRadius: 1,
        transition: "outline-color 0.15s",
      } : { outline: "2px solid transparent", borderRadius: 1 }}
    >
      <svg width={width} height={height} style={{ display: "block" }}>
        {cells}
        {xLabels}
        {yLabels}
      </svg>
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
        return (
          <MDBox key={ch} onClick={() => setChannel(ch)}
            sx={{
              cursor: "pointer", border: active ? `2.5px solid #1a1a1a` : "1.5px solid #ccc",
              borderRadius: 1.5, p: 0.5, background: "#fff",
              boxShadow: active ? "0 0 0 2px rgba(0,0,0,0.08)" : "none",
            }}>
            <MDTypography variant="caption" fontWeight={active ? "bold" : "medium"} color="dark"
              sx={{ fontSize: 10.5, display: "block", textAlign: "center" }}>
              {ch.replace(/_/g, " ")}
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

/** The scatter + fitted line + two violins for one pinned cell. Shared between the hover preview
 * (small, no violins) and the pinned drill-down (full size, with violins). */
function CellFigure({ cell, small }) {
  if (!cell || !cell.points || !cell.points.length) {
    return (
      <MDTypography variant="caption" color="dark" fontStyle="italic" sx={{ fontSize: 11 }}>
        {cell && cell.loading ? "Loading…" : "No underlying pairs could be loaded for this cell."}
      </MDTypography>
    );
  }
  const pts = cell.points;
  const xs = pts.map((p) => p.power);
  const ys = pts.map((p) => p.pain);
  const xlo = Math.min(...xs), xhi = Math.max(...xs);
  const ylo = Math.min(...ys), yhi = Math.max(...ys);
  const w = small ? 140 : 260, h = small ? 90 : 220;
  const pad = small ? 10 : 28;
  const sx = (x) => pad + ((x - xlo) / ((xhi - xlo) || 1)) * (w - 2 * pad);
  const sy = (y) => (h - pad) - ((y - ylo) / ((yhi - ylo) || 1)) * (h - 2 * pad);
  // Least-squares fitted line, drawn only to guide the eye -- the r/AUC values on screen are the
  // grid's own, not recomputed here.
  const n = xs.length;
  const mx = xs.reduce((s, v) => s + v, 0) / n, my = ys.reduce((s, v) => s + v, 0) / n;
  let sxy = 0, sxx = 0;
  xs.forEach((x, i) => { sxy += (x - mx) * (ys[i] - my); sxx += (x - mx) ** 2; });
  const slope = sxx > 0 ? sxy / sxx : 0;
  const intercept = my - slope * mx;
  const lineX1 = xlo, lineX2 = xhi;
  const lineY1 = intercept + slope * lineX1, lineY2 = intercept + slope * lineX2;

  const colorFor = (label) => (label === "high" ? (PAL.fail || "#D55E00")
    : (label === "low" ? (PAL.accent || "#0072B2") : "#aaaaaa"));

  const violinW = small ? 0 : 90;
  const totalW = w + (small ? 0 : violinW + 16);
  const highVals = pts.filter((p) => p.label === "high").map((p) => p.power);
  const lowVals = pts.filter((p) => p.label === "low").map((p) => p.power);
  const vyScale = (v) => (h - pad) - ((v - xlo) / ((xhi - xlo) || 1)) * (h - 2 * pad);

  return (
    <MDBox display="flex" flexDirection="row" gap={2} alignItems="flex-start">
      <svg width={w} height={h}>
        {pts.map((p, i) => (
          <circle key={i} cx={sx(p.power)} cy={sy(p.pain)} r={small ? 1.6 : 2.6}
            fill={colorFor(p.label)} opacity={0.75} />
        ))}
        <line x1={sx(lineX1)} y1={sy(lineY1)} x2={sx(lineX2)} y2={sy(lineY2)}
          stroke="#1a1a1a" strokeWidth={small ? 1 : 1.5} />
        {!small ? (
          <>
            <text x={w / 2} y={h - 6} fontSize={9} textAnchor="middle" fill="#555">Band power</text>
            <text x={10} y={12} fontSize={9} fill="#555">Pain</text>
          </>
        ) : null}
      </svg>
      {!small ? (
        <svg width={violinW} height={h}>
          {[["high", highVals, violinW * 0.28], ["low", lowVals, violinW * 0.72]].map(([label, vals, cx]) => {
            const path = violinPath(vals, cx, vyScale, violinW * 0.2);
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
        </svg>
      ) : null}
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
  const [metric, setMetric] = useState(pageMetric || "nrs");
  useEffect(() => { if (pageMetric) setMetric(pageMetric); }, [pageMetric]);

  const [channel, setChannel] = useState(null);
  const [corrResult, setCorrResult] = useState(null);   // what the correlation grid is drawn from
  const [aucResult, setAucResult] = useState(null);      // what the AUC grid is drawn from
  const [aucFlashKey, setAucFlashKey] = useState(0);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);
  const [howToReadOpen, setHowToReadOpen] = useState(false);
  const prevSettingsRef = useRef(null);

  const [hoveredCorr, setHoveredCorr] = useState(null);
  const [hoveredAuc, setHoveredAuc] = useState(null);
  const [pinned, setPinned] = useState(null);      // { grid: 'correlation'|'auc', row, col, channel }
  const [previewCell, setPreviewCell] = useState(null);
  const [pinnedCellData, setPinnedCellData] = useState(null);
  const cellCacheRef = useRef(new Map());
  const hoverTimerRef = useRef(null);

  const reqKey = requestParams ? JSON.stringify(requestParams) : null;

  useEffect(() => {
    if (!participantUid || !requestParams) return undefined;
    let cancelled = false;
    const body = { ParticipantId: participantUid, ...requestParams, BandTimeSweep: "1", SweepMetric: metric };
    setLoading(true); setErr(null);
    SessionController.query("/api/queryBiomarkerAnalysis", body)
      .then((response) => {
        if (cancelled) return;
        const d = (response && response.data) || null;
        const prev = prevSettingsRef.current;
        const cur = { ...requestParams, SweepMetric: metric };
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
        setPinned(null); setPinnedCellData(null); setPreviewCell(null);
      })
      .catch((e) => { if (!cancelled) setErr((e && e.message) || String(e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [participantUid, reqKey, metric]);

  const corrSweeps = (corrResult && corrResult.band_time_sweep) || {};
  const aucSweeps = (aucResult && aucResult.band_time_sweep) || {};
  const corrSw = channel && corrSweeps[channel];
  const aucSw = channel && aucSweeps[channel];
  const matchDirectionLabel = (aucSw && aucSw.match_direction) || (corrSw && corrSw.match_direction);

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

  const handleHover = (gridKind, sw, row, col) => {
    const setHovered = gridKind === "auc" ? setHoveredAuc : setHoveredCorr;
    if (row == null || col == null) { setHovered(null); setPreviewCell(null); return; }
    setHovered({ row, col });
    const center = sw.center_freqs_hz[col];
    const seconds = (sw.integration_seconds_requested || sw.integration_seconds_delivered)[row];
    if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current);
    hoverTimerRef.current = setTimeout(() => {
      setPreviewCell({ channel, center, seconds, grid: gridKind, row, col, loading: true,
        r: (sw.correlation_grid[row] || [])[col], auc: (sw.auc_grid[row] || [])[col] });
      fetchCell(channel, center, seconds).then((cell) => {
        setPreviewCell((p) => (p && p.row === row && p.col === col && p.grid === gridKind
          ? { ...p, ...cell, loading: false } : p));
      });
    }, 220);
  };

  const handleClick = (gridKind, sw, row, col) => {
    const center = sw.center_freqs_hz[col];
    const seconds = (sw.integration_seconds_requested || sw.integration_seconds_delivered)[row];
    setPinned({ grid: gridKind, row, col, channel, center, seconds });
    setPinnedCellData({ loading: true });
    fetchCell(channel, center, seconds).then((cell) => setPinnedCellData(cell));
  };

  // Track D (`adr_2026-09-08_biomarkers_closedloop_matrix_export.md`) is what will let the whole
  // grid be exported to Closed-Loop Deployment; it had not landed as of this track's own work, so
  // this checks for the field it will add rather than assuming it exists, and stays disabled
  // with an explanation until it does -- a follow-up wires the button live once Track D ships.
  const exportReady = !!(corrResult && (corrResult.closed_loop_export_key
    || corrResult.exported_to_closed_loop || (corrSw && corrSw.closed_loop_export_ready)));

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
          <MDBox>
            <MDTypography variant="caption" fontWeight="bold" color="dark"
              sx={{ fontSize: 11, display: "block" }}>{"Patient-reported pain score"}</MDTypography>
            <select value={metric} onChange={(e) => setMetric(e.target.value)}
              style={{ fontSize: 13, padding: "3px 6px" }}>
              {options.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
            </select>
          </MDBox>
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
            <Grid container spacing={2}>
              <Grid item xs={12} md={6}>
                <MDTypography variant="button" fontWeight="bold" color="dark"
                  sx={{ fontSize: 13, display: "block", mb: 0.5 }}>
                  {"Correlation with pain — depends only on matching"}
                </MDTypography>
                <Heatmap sw={corrSw} kind="correlation" hovered={hoveredCorr}
                  pinned={pinned && pinned.grid === "correlation" ? pinned : null}
                  onHover={(r, c) => handleHover("correlation", corrSw, r, c)}
                  onClick={(r, c) => handleClick("correlation", corrSw, r, c)} />
              </Grid>
              <Grid item xs={12} md={6}>
                <MDTypography variant="button" fontWeight="bold" color="dark"
                  sx={{ fontSize: 13, display: "block", mb: 0.5 }}>
                  {"High vs low pain (AUC) — also depends on the binarization cuts above"}
                </MDTypography>
                <Heatmap sw={aucSw} kind="auc" hovered={hoveredAuc}
                  pinned={pinned && pinned.grid === "auc" ? pinned : null}
                  flashKey={aucFlashKey}
                  onHover={(r, c) => handleHover("auc", aucSw, r, c)}
                  onClick={(r, c) => handleClick("auc", aucSw, r, c)} />
              </Grid>
            </Grid>

            {previewCell ? (
              <MDBox mt={1.5} sx={{ border: "1px solid #ddd", borderRadius: 1.5, p: 1, background: "#fafafa" }}>
                <MDTypography variant="caption" fontWeight="bold" color="dark" sx={{ fontSize: 11 }}>
                  {`Preview: ${previewCell.center} Hz, ${previewCell.seconds} s of signal — `}
                  {`r = ${num(previewCell.r, 3)}, AUC = ${num(previewCell.auc, 3)}`}
                </MDTypography>
                <CellFigure cell={previewCell} small />
              </MDBox>
            ) : (
              <MDTypography variant="caption" color="dark" fontStyle="italic"
                sx={{ fontSize: 11, display: "block", mt: 1 }}>
                {"Hover a cell for a quick preview; click one to pin the full detail below."}
              </MDTypography>
            )}

            {pinned ? (
              <MDBox mt={2} sx={{ border: `2px solid ${PAL.accentBorder || "#0072B2"}`, borderRadius: 2, p: 1.5 }}>
                <MDTypography variant="button" fontWeight="bold" color="dark"
                  sx={{ fontSize: 13, display: "block", mb: 0.5 }}>
                  {`${pinned.channel} · ${pinned.center} Hz · ${pinned.seconds} s of signal`}
                </MDTypography>
                <CellFigure cell={pinnedCellData} />
              </MDBox>
            ) : null}

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
                    sx={{ fontSize: 11.5, display: "block", lineHeight: 1.45 }}>
                    {"• For the right grid, 0.5 means no ability to tell high pain from low "
                     + "pain apart — not 0. The colour scale is centred on 0.5."}
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
