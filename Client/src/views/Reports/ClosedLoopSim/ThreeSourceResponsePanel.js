/**
 * Stimulation amplitude effects on band power, measured three ways -- pooled across every visit.
 *
 * REDRAWN 2026-09-11 on the PI's brief: "you basically don't want separate visits with separate
 * tabs because you pool across all visits for right side and left side. Maybe it's just two tabs
 * for right side amplitude change and left side amplitude change pooled across all visits."
 *
 * WHAT THIS READS. `pooled` is the background fetch of the stored per-run points and the stored
 * pooled table (`useThreeSourcePooled`, asked for AFTER the report has answered so the first
 * figures never wait on it). Every number here comes from those two stored tables, written once
 * from a build that held every run (decisions 103 and 10 of the redesign plan); the panel groups
 * and draws, and computes nothing new. The three column titles are the PI's own words.
 *
 * WHAT IS DRAWN. One tab per side that was turned up. Inside a side, one sensing contact at a time
 * (the left side of RCS08 has two with runs), never pooled across contacts (decision 74). Every
 * run's settled points at ONE band centre -- the committed band's, snapped to the nearest stored
 * centre -- one marker shape per run, in the three routes' inks. On the time-domain column the
 * stored pooled slope (decision 55's shared slope, one baseline per run) is drawn through the
 * anchor the server chose (decision 12: the mean of the per-run centroids). The direct route only
 * has points for runs whose sensed band IS the drawn centre; the device's own PSD route has none
 * on this participant, and says so.
 *
 * THE FOLD shows the pooled slope at every band centre for the chosen contact, with its standard
 * error, which is the same stored row the evidence triangle reads (decision 9).
 *
 * THIS PANEL GATES NOTHING; the payload says so and no verdict reads it.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import Plotly from "plotly.js-dist";
import {
  Card, CardContent, Typography, Box, Stack, Divider, ToggleButton, ToggleButtonGroup, Chip,
} from "@mui/material";

import { PAL, OKABE_ITO } from "./palette";
import { fmtHz, fmtNum, fmtP } from "./deployFormat";
import Fold from "./Fold";

/** One colour per route, matching the static picture in the report exactly. */
const ROUTE_INK = { time_domain: OKABE_ITO.blue, psd: OKABE_ITO.orange, direct: OKABE_ITO.bluishGreen };
const ROUTE_TITLE = { time_domain: "Time domain derived LSB", psd: "PSD derived LSB",
  direct: "Direct LSB recording" };
const ROUTES = ["time_domain", "psd", "direct"];
const NEUTRAL_INK = OKABE_ITO.gray;
const GRID_INK = "#DDDDDD";
/** One marker shape per run, so a visit can be told apart without a legend lookup. */
const SYMBOLS = ["circle", "square", "diamond", "triangle-up", "cross", "x", "star", "hexagon",
  "triangle-down", "pentagon", "circle-open", "square-open"];
const SPECTRUM_LO_HZ = 7.5, SPECTRUM_HI_HZ = 30.0;

/** Three side-by-side panels in one figure, laid out by hand: plotly.js has no subplot helper. */
function threeColumnLayout(headings, xTitle, yTitle) {
  const layout = {
    margin: { l: 62, r: 16, t: 26, b: 46 },
    height: 270, plot_bgcolor: "white", paper_bgcolor: "white",
    showlegend: false, font: { size: 11 }, hovermode: "closest",
    uirevision: "three-source-pooled", annotations: [],
  };
  const gap = 0.055;
  const w = (1 - 2 * gap) / 3;
  headings.forEach((h, k) => {
    const x0 = k * (w + gap);
    const ax = k === 0 ? "" : String(k + 1);
    layout[`xaxis${ax}`] = {
      domain: [x0, x0 + w], anchor: `y${ax}`, title: { text: xTitle, font: { size: 10 } },
      gridcolor: GRID_INK, zeroline: false, tickfont: { size: 10 },
    };
    layout[`yaxis${ax}`] = {
      domain: [0, 1], anchor: `x${ax}`, gridcolor: GRID_INK, zeroline: false,
      tickfont: { size: 10 }, title: k === 0 ? { text: yTitle, font: { size: 10 } } : undefined,
    };
    layout.annotations.push({
      text: `<b>${h}</b>`, x: x0, y: 1.13, xref: "paper", yref: "paper", showarrow: false,
      xanchor: "left", font: { size: 11, color: "#1A1A1A" },
    });
  });
  return layout;
}

const near = (a, b, tol = 0.011) => a != null && b != null && Math.abs(Number(a) - Number(b)) <= tol;

/** The column of a route's matrix at one centre: [x, y, pieces] arrays, or null. */
function routeColumn(block, centreHz) {
  if (!block || !block.centres_hz || !block.centres_hz.length) return null;
  const j = block.centres_hz.findIndex((c) => near(c, centreHz));
  if (j < 0) return null;
  const xs = [], ys = [], ps = [];
  block.currents_mA.forEach((x, i) => {
    const y = block.power[i] ? block.power[i][j] : null;
    if (y != null) { xs.push(x); ys.push(y); ps.push(block.n_pieces ? block.n_pieces[i] : null); }
  });
  return xs.length ? { x: xs, y: ys, pieces: ps } : null;
}

function sideOf(contact) {
  return /LEFT/i.test(contact || "") ? "Left" : (/RIGHT/i.test(contact || "") ? "Right" : null);
}

export default function ThreeSourceResponsePanel({ pooled, report, committed, contactLabel }) {
  const view = pooled && pooled.data;
  const sides = useMemo(() => (view && view.sides) || [], [view]);
  const committedSide = sideOf(committed && committed.contact);
  const [sidePick, setSidePick] = useState(null);
  const [contactPick, setContactPick] = useState({});
  const [showSpectrum, setShowSpectrum] = useState(false);
  const [spectrumRevealed, setSpectrumRevealed] = useState(false);
  useEffect(() => { if (showSpectrum && !spectrumRevealed) setSpectrumRevealed(true); },
    [showSpectrum, spectrumRevealed]);
  const topRef = useRef(null);
  const specRef = useRef(null);

  // Which side, then which contact on it: the committed band's when it has runs, else the first.
  const side = useMemo(() => {
    const names = sides.map((s) => s.ramped_side);
    if (sidePick && names.includes(sidePick)) return sidePick;
    if (committedSide && names.includes(committedSide)) return committedSide;
    return names[0] || null;
  }, [sides, sidePick, committedSide]);
  const sideObj = sides.find((s) => s.ramped_side === side) || null;
  const contacts = useMemo(() => (sideObj && sideObj.contacts) || [], [sideObj]);
  const contact = useMemo(() => {
    const names = contacts.map((c) => c.sensing_contact);
    const pick = contactPick[side];
    if (pick && names.includes(pick)) return pick;
    if (committed && names.includes(committed.contact)) return committed.contact;
    return names[0] || null;
  }, [contacts, contactPick, side, committed]);
  const contactObj = contacts.find((c) => c.sensing_contact === contact) || null;
  const label = (ch) => (contactLabel ? contactLabel(ch) : String(ch || "").replace(/_/g, " "));

  // The centre drawn: the committed band's, snapped to the nearest stored centre.
  const centre = useMemo(() => {
    if (!contactObj) return null;
    const stored = (contactObj.pooled_by_centre || []).map((r) => r.band_centre_hz)
      .filter((c) => c != null);
    const fromRuns = contactObj.runs.flatMap((r) => (r.routes.time_domain.centres_hz || []));
    const all = Array.from(new Set([...stored, ...fromRuns])).sort((a, b) => a - b);
    if (!all.length) return null;
    const want = committed && committed.centerHz != null ? Number(committed.centerHz) : all[0];
    return all.reduce((best, c) => (Math.abs(c - want) < Math.abs(best - want) ? c : best), all[0]);
  }, [contactObj, committed]);
  const pooledRow = useMemo(() => (contactObj
    ? (contactObj.pooled_by_centre || []).find((r) => near(r.band_centre_hz, centre)) || null
    : null), [contactObj, centre]);

  // --- TOP ROW: every run's points at the drawn centre, one marker per run, pooled line on TD ---
  useEffect(() => {
    const gd = topRef.current;
    if (!gd) return;
    if (!contactObj || centre == null) { Plotly.purge(gd); return; }
    const traces = [];
    const layout = threeColumnLayout(ROUTES.map((r) => ROUTE_TITLE[r]),
      `Current delivered by the ${String(side).toLowerCase()} stimulator (mA)`,
      "Settled band power (device units)");
    const allY = [];
    ROUTES.forEach((route, k) => {
      const ax = k === 0 ? "" : String(k + 1);
      let any = false;
      contactObj.runs.forEach((run, i) => {
        // The direct and PSD routes report ONE band -- the one the device was sensing -- so their
        // points exist at the drawn centre only for runs that sensed it.
        if (route !== "time_domain" && !near(run.programmed_centre_hz, centre)) return;
        const col = routeColumn(run.routes[route], centre);
        if (!col) return;
        any = true;
        allY.push(...col.y);
        traces.push({
          type: "scatter", mode: "lines+markers", xaxis: `x${ax}`, yaxis: `y${ax}`,
          x: col.x, y: col.y, customdata: col.pieces,
          line: { color: ROUTE_INK[route], width: 1, dash: "dot" },
          marker: { color: ROUTE_INK[route], size: 9, symbol: SYMBOLS[i % SYMBOLS.length],
            line: { color: "white", width: 1 } },
          hovertemplate: `${run.visit_date} · ${fmtHz(run.stimulation_rate_hz)} Hz stimulation`
            + "<br>%{x} mA · %{y:.1f} device units · %{customdata} pieces<extra></extra>",
        });
      });
      if (route === "time_domain" && pooledRow && pooledRow.pooled_slope_per_mA != null
          && pooledRow.anchor) {
        const xs = traces.filter((t) => t.xaxis === `x${ax}`).flatMap((t) => t.x);
        if (xs.length) {
          const lo = Math.min(...xs), hi = Math.max(...xs);
          const { x: x0, y: y0 } = pooledRow.anchor;
          const s = pooledRow.pooled_slope_per_mA;
          traces.push({
            type: "scatter", mode: "lines", xaxis: `x${ax}`, yaxis: `y${ax}`,
            x: [lo, hi], y: [y0 + s * (lo - x0), y0 + s * (hi - x0)],
            line: { color: ROUTE_INK.time_domain, width: 2.2, dash: "dash" },
            hovertemplate: `pooled slope ${fmtNum(s, 2)} device units per mA`
              + `<br>${pooledRow.n} points across ${pooledRow.n_visits} visits<extra></extra>`,
          });
        }
      }
      if (!any) {
        const dom = layout[`xaxis${ax}`].domain;
        layout.annotations.push({
          text: "<i>no settled value from this recording</i>",
          x: dom[0] + 0.5 * (dom[1] - dom[0]), y: 0.55, xref: "paper", yref: "paper",
          showarrow: false, xanchor: "center", font: { size: 11, color: NEUTRAL_INK },
        });
        layout[`xaxis${ax}`].showticklabels = false;
        layout[`yaxis${ax}`].showticklabels = false;
      }
    });
    if (allY.length >= 2) {
      const lo = Math.min(...allY), hi = Math.max(...allY);
      const pad = 0.12 * (hi - lo || hi);
      ROUTES.forEach((_r, k) => {
        layout[`yaxis${k === 0 ? "" : String(k + 1)}`].range = [Math.max(0, lo - pad), hi + pad];
      });
    }
    Plotly.react(gd, traces, layout, PAL.MODEBAR);
  }, [contactObj, centre, pooledRow, side]);

  // --- THE FOLD: the pooled slope at every band centre for this contact, with its uncertainty ---
  useEffect(() => {
    const gd = specRef.current;
    if (!gd) return;
    if (!contactObj) { Plotly.purge(gd); return; }
    const rows = (contactObj.pooled_by_centre || [])
      .filter((r) => r.band_centre_hz != null && r.band_centre_hz >= SPECTRUM_LO_HZ - 1e-9
        && r.band_centre_hz <= SPECTRUM_HI_HZ + 1e-9)
      .sort((a, b) => a.band_centre_hz - b.band_centre_hz);
    const have = rows.filter((r) => r.pooled_slope_per_mA != null);
    const xs = have.map((r) => r.band_centre_hz);
    const ys = have.map((r) => r.pooled_slope_per_mA);
    const se = have.map((r) => (r.pooled_slope_stderr != null ? r.pooled_slope_stderr : 0));
    const striped = new Set();
    contactObj.runs.forEach((run) => {
      const td = run.routes.time_domain;
      (td.striped || []).forEach((f, j) => { if (f) striped.add(td.centres_hz[j]); });
    });
    const traces = [];
    if (xs.length) {
      traces.push({
        type: "scatter", mode: "lines", x: [...xs, ...xs.slice().reverse()],
        y: [...ys.map((y, i) => y + 2 * se[i]), ...ys.map((y, i) => y - 2 * se[i]).reverse()],
        fill: "toself", fillcolor: "rgba(0,114,178,0.12)", line: { width: 0 }, hoverinfo: "skip",
      });
      traces.push({
        type: "scatter", mode: "lines+markers", x: xs, y: ys,
        line: { color: ROUTE_INK.time_domain, width: 1.6 },
        marker: { color: ROUTE_INK.time_domain, size: 5 },
        customdata: have.map((r) => [r.n, r.n_visits, r.pooled_slope_p]),
        hovertemplate: "%{x} Hz band · pooled slope %{y:.2f} device units per mA"
          + "<br>%{customdata[0]} points across %{customdata[1]} visits · p = %{customdata[2]:.3f}"
          + "<extra></extra>",
      });
    }
    const shapes = [];
    Array.from(striped).filter((f) => f >= SPECTRUM_LO_HZ - 0.5 && f <= SPECTRUM_HI_HZ + 0.5)
      .forEach((f) => shapes.push({ type: "rect", xref: "x", yref: "paper", layer: "below",
        x0: f - 0.5, x1: f + 0.5, y0: 0, y1: 1, fillcolor: NEUTRAL_INK, opacity: 0.1,
        line: { width: 0 } }));
    if (centre != null) {
      shapes.push({ type: "line", xref: "x", yref: "paper", x0: centre, x1: centre, y0: 0, y1: 1,
        line: { color: "#1A1A1A", width: 1, dash: "dot" } });
    }
    const layout = {
      margin: { l: 62, r: 16, t: 10, b: 46 }, height: 240, plot_bgcolor: "white",
      paper_bgcolor: "white", showlegend: false, font: { size: 11 }, hovermode: "closest",
      uirevision: "three-source-pooled-slopes", shapes,
      xaxis: { title: { text: "Band centre (Hz)", font: { size: 10 } }, gridcolor: GRID_INK,
        range: [SPECTRUM_LO_HZ - 0.6, SPECTRUM_HI_HZ + 0.6], zeroline: false, tickfont: { size: 10 } },
      yaxis: { title: { text: "Pooled slope (device units per mA)", font: { size: 10 } },
        gridcolor: GRID_INK, zeroline: true, zerolinecolor: "#999", tickfont: { size: 10 } },
      annotations: xs.length ? [] : [{ text: "<i>no pooled slope is stored for this contact yet</i>",
        x: 0.5, y: 0.55, xref: "paper", yref: "paper", showarrow: false,
        font: { size: 11, color: NEUTRAL_INK } }],
    };
    Plotly.react(gd, traces, layout, PAL.MODEBAR);
  }, [contactObj, centre, spectrumRevealed]);

  useEffect(() => () => {
    if (topRef.current) Plotly.purge(topRef.current);
    if (specRef.current) Plotly.purge(specRef.current);
  }, []);

  const title = "Stimulation amplitude effects on band power, measured three ways";
  const reportBlock = report && report.data && report.data.three_source_response;
  const footer = reportBlock && reportBlock.comparisons && reportBlock.comparisons[0]
    ? reportBlock.comparisons[0].footer : null;

  // --- the honest empty and loading states ---
  if (!view) {
    let reason;
    if (pooled && pooled.err) reason = pooled.err;
    else if (pooled && pooled.loading) reason = "gathering every run of rising current from the stored tables…";
    else if (reportBlock && reportBlock.absent_reason) reason = reportBlock.absent_reason;
    else if (report && report.data) {
      reason = "the pooled view is fetched after the report; if it does not appear, the stored "
        + "tables have not been written yet and the next full report writes them";
    } else reason = "waiting for the report";
    return (
      <Card><CardContent>
        <Typography variant="h6" gutterBottom>{title}</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>{reason}</Typography>
        <Typography variant="caption" color="text.secondary">
          This panel is informative only. It does not gate anything, and no verdict on this page
          depends on it.
        </Typography>
      </CardContent></Card>
    );
  }
  if (!sides.length) {
    return (
      <Card><CardContent>
        <Typography variant="h6" gutterBottom>{title}</Typography>
        <Typography variant="body2" color="text.secondary">
          {view.absent_reason || "no run of rising current on one side is stored for this participant"}
        </Typography>
      </CardContent></Card>
    );
  }

  // One-line captions under the three columns, from the stored numbers only.
  const runsSensing = contactObj
    ? contactObj.runs.filter((r) => near(r.programmed_centre_hz, centre)).length : 0;
  let tdCaption;
  if (pooledRow && pooledRow.pooled_slope_per_mA != null) {
    tdCaption = `${pooledRow.n} points across ${pooledRow.n_visits} visits · pooled slope `
      + `${fmtNum(pooledRow.pooled_slope_per_mA, 2)} ± ${fmtNum(pooledRow.pooled_slope_stderr, 2)} `
      + `device units per mA (p = ${fmtP(pooledRow.pooled_slope_p)}) · ${pooledRow.pooled_direction}`;
    if (pooledRow.curves) {
      tdCaption += ` · a bend was detected (p = ${fmtP(pooledRow.p_curvature)})`;
      if (pooledRow.peaks_inside && pooledRow.peak_mA != null) {
        tdCaption += `, peak near ${fmtNum(pooledRow.peak_mA, 1)} mA`;
      }
    }
  } else if (pooledRow) {
    tdCaption = `pooled slope ${pooledRow.curvature_note || "not assessed"}`;
  } else {
    tdCaption = "no pooled row is stored for this band yet";
  }
  const directCaption = `${runsSensing} of ${contactObj ? contactObj.n_runs : 0} runs sensed this `
    + "band; the device reports the band it was programmed to sense and no other";
  const psdReasons = contactObj
    ? contactObj.runs.map((r) => r.routes.psd.absent_reason).filter(Boolean) : [];
  const anyPsd = !!(contactObj
    && contactObj.runs.some((r) => (r.routes.psd.currents_mA || []).length));
  const psdCaption = anyPsd ? "the device's own FFT snapshots, where it computed any during a run"
    : (psdReasons[0] || "no settled value in any run");

  return (
    <Card>
      <CardContent>
        <Typography variant="h6" gutterBottom>{title}</Typography>

        <ToggleButtonGroup size="small" exclusive value={side} sx={{ mb: 1, flexWrap: "wrap" }}
          onChange={(_e, v) => { if (v != null) setSidePick(v); }}>
          {sides.map((s) => (
            <ToggleButton key={s.ramped_side} value={s.ramped_side}
              sx={{ textTransform: "none", fontSize: 12 }}>
              {`${s.ramped_side} stimulator turned up · pooled over `
                + `${s.contacts.reduce((n, c) => n + c.n_runs, 0)} runs`}
            </ToggleButton>
          ))}
        </ToggleButtonGroup>

        {contacts.length > 1 ? (
          <Stack direction="row" spacing={0.6} sx={{ mb: 1 }} alignItems="center">
            <Typography variant="caption" color="text.secondary">Sensing contact:</Typography>
            {contacts.map((c) => (
              <Chip key={c.sensing_contact} size="small"
                onClick={() => setContactPick({ ...contactPick, [side]: c.sensing_contact })}
                label={`${label(c.sensing_contact)} · ${c.n_runs} run${c.n_runs === 1 ? "" : "s"}`}
                sx={{ fontSize: 11.5, fontWeight: c.sensing_contact === contact ? 700 : 400,
                  backgroundColor: c.sensing_contact === contact ? PAL.accentFill : "transparent",
                  border: `1px solid ${c.sensing_contact === contact ? PAL.accentBorder : PAL.neutralBorder}` }} />
            ))}
          </Stack>
        ) : null}

        {contactObj ? (
          <Typography variant="subtitle2" sx={{ fontWeight: 600, lineHeight: 1.45, mb: 0.5 }}>
            {`Sensing on ${label(contact)} · drawn at ${fmtHz(centre)} Hz`}
            {committed && near(centre, committed.centerHz) ? " (the committed band)" : ""}
            {` · ${contactObj.n_runs} run${contactObj.n_runs === 1 ? "" : "s"} across `
              + `${contactObj.n_visits} visit${contactObj.n_visits === 1 ? "" : "s"}`}
            {contactObj.stimulation_rates_hz && contactObj.stimulation_rates_hz.length
              ? ` · stimulation at ${contactObj.stimulation_rates_hz.map((r) => fmtHz(r)).join(", ")} Hz`
              : ""}
          </Typography>
        ) : null}
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
          One marker shape per run; each point is the mean of the settled window before the next
          step up. The dashed line is the pooled slope across every run on this contact, drawn
          through the mean of the runs&apos; own centres.
        </Typography>

        <Box ref={topRef} sx={{ width: "100%" }} />

        <Stack direction={{ xs: "column", md: "row" }} spacing={1.5} sx={{ mt: 0.5, mb: 1 }}>
          {[tdCaption, psdCaption, directCaption].map((c, i) => (
            <Typography key={ROUTES[i]} variant="caption" color="text.secondary"
              sx={{ flex: 1, lineHeight: 1.5 }}>{c}</Typography>
          ))}
        </Stack>

        <Divider sx={{ my: 1.2 }} />

        {/* Mounted on first reveal and kept mounted: a Plotly figure first drawn inside a hidden
            container measures itself as zero pixels wide and keeps that size. */}
        <Typography variant="caption" component="button" type="button"
          onClick={() => setShowSpectrum((s) => !s)} aria-expanded={showSpectrum}
          sx={{ color: PAL.accent, cursor: "pointer", background: "none", border: 0, padding: 0,
            fontFamily: "inherit", display: "inline-flex", alignItems: "center", gap: 0.5,
            "&:hover": { textDecoration: "underline" } }}>
          <span aria-hidden="true" style={{ fontSize: 9, display: "inline-block",
            transform: showSpectrum ? "rotate(90deg)" : "none" }}>▶</span>
          {showSpectrum ? "Hide the other bands"
            : `Show the pooled slope at every band from ${fmtHz(SPECTRUM_LO_HZ)} to ${fmtHz(SPECTRUM_HI_HZ)} Hz`}
        </Typography>
        {spectrumRevealed ? (
          <Box sx={{ display: showSpectrum ? "block" : "none" }}>
            <Typography variant="caption" color="text.secondary"
              sx={{ display: "block", mt: 0.5, mb: 0.5 }}>
              Time domain derived LSB only, which is the one route every run reports at every band.
              The band is ±2 standard errors; striped bands carry a folded multiple of the
              stimulation rate; the dotted line marks the band drawn above.
            </Typography>
            <Box ref={specRef} sx={{ width: "100%" }} />
          </Box>
        ) : null}

        <Fold show="Why agreement here is not three confirmations" hide="Hide" dense>
          <Typography variant="caption" sx={{ display: "block", color: NEUTRAL_INK, lineHeight: 1.55 }}>
            {footer || ("The three columns are not independent: the device computes its own band "
              + "power from the voltage trace the first column reads, so agreement checks the "
              + "conversion, not the effect three times.")}
          </Typography>
          <Typography variant="caption" sx={{ display: "block", mt: 0.5, color: NEUTRAL_INK }}>
            This panel is informative only. It does not gate anything, and no verdict on this page
            depends on it.
          </Typography>
        </Fold>
      </CardContent>
    </Card>
  );
}
