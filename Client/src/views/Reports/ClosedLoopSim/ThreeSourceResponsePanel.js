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

import { useContext, useEffect, useMemo, useRef, useState } from "react";
import Plotly from "plotly.js-dist";
import {
  Card, CardContent, Typography, Box, Stack, Divider, ToggleButton, ToggleButtonGroup, Chip,
} from "@mui/material";

import { PAL, OKABE_ITO } from "./palette";
import { fmtHz, fmtNum, fmtP } from "./deployFormat";
import Fold from "./Fold";
import FoldArrow from "../paper/FoldArrow";
import { TYPE, WRAP, CARD } from "assets/theme/base/tokens";
import { plotlyLayout } from "views/Reports/figureStyle";
import { SectionRevealedContext } from "views/Reports/paper/Section";

/** One colour per route, matching the static picture in the report exactly. */
// Each route's own mark colour; orange is the right side on every page, so it is not used here.
const ROUTE_INK = { time_domain: OKABE_ITO.blue, psd: OKABE_ITO.reddishPurple, direct: OKABE_ITO.bluishGreen };
const ROUTE_TITLE = { time_domain: "From the recording (TD)",
  psd: "From the device's 30-second snapshot (PSD)", direct: "The device's own band-power reading" };
const ROUTES = ["time_domain", "psd", "direct"];
const NEUTRAL_INK = OKABE_ITO.gray;

/** One marker shape per run, so a visit can be told apart without a legend lookup. */
const SYMBOLS = ["circle", "square", "diamond", "triangle-up", "cross", "x", "star", "hexagon",
  "triangle-down", "pentagon", "circle-open", "square-open"];
const SPECTRUM_LO_HZ = 7.5, SPECTRUM_HI_HZ = 30.0;

/** Three side-by-side panels in one figure, laid out by hand: plotly.js has no subplot helper. */
function threeColumnLayout(headings, xTitle, yTitle) {
  const base = plotlyLayout();
  const layout = {
    ...base,
    margin: { l: 62, r: 16, t: 32, b: 48 },
    height: 280, showlegend: false, hovermode: "closest",
    uirevision: "three-source-pooled", annotations: [],
  };
  const gap = 0.055;
  const w = (1 - 2 * gap) / 3;
  headings.forEach((h, k) => {
    const x0 = k * (w + gap);
    const ax = k === 0 ? "" : String(k + 1);
    layout[`xaxis${ax}`] = {
      ...base.xaxis, domain: [x0, x0 + w], anchor: `y${ax}`,
      title: { ...base.xaxis.title, text: xTitle },
    };
    layout[`yaxis${ax}`] = {
      ...base.yaxis, domain: [0, 1], anchor: `x${ax}`,
      title: k === 0 ? { ...base.yaxis.title, text: yTitle } : undefined,
    };
    layout.annotations.push({
      text: h, x: x0, y: 1.12, xref: "paper", yref: "paper", showarrow: false,
      xanchor: "left", font: { size: PAL.fs.body, color: PAL.ink },
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
  // Drawn only once the page's Background fold, which holds this panel, has been opened (or the
  // sign-off record asks for its picture): it starts closed, and this figure was drawn on page load
  // for nobody to see (speed-up item C5, 2026-10-02). Once drawn it stays drawn.
  const revealed = useContext(SectionRevealedContext);

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
    if (!gd || !revealed) return;
    if (!contactObj || centre == null) { Plotly.purge(gd); return; }
    const traces = [];
    const layout = threeColumnLayout(ROUTES.map((r) => ROUTE_TITLE[r]),
      `current, ${String(side).toLowerCase()} side (mA)`,
      "band power, held steady (device units, LSB)");
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
            line: { color: PAL.surface, width: 1 } },
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
            hovertemplate: `change in band power per milliamp, all visits together: ${fmtNum(s, 2)} device units`
              + `<br>${pooledRow.n} points across ${pooledRow.n_visits} visits<extra></extra>`,
          });
        }
      }
      if (!any) {
        const dom = layout[`xaxis${ax}`].domain;
        layout.annotations.push({
          text: "no steady reading from this source",
          x: dom[0] + 0.5 * (dom[1] - dom[0]), y: 0.55, xref: "paper", yref: "paper",
          showarrow: false, xanchor: "center", font: { size: PAL.fs.body, color: PAL.ink3 },
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
  }, [revealed, contactObj, centre, pooledRow, side]);

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
        fill: "toself", fillcolor: PAL.accentFill, line: { width: 0 }, hoverinfo: "skip",
      });
      traces.push({
        type: "scatter", mode: "lines+markers", x: xs, y: ys,
        line: { color: ROUTE_INK.time_domain, width: 1.6 },
        marker: { color: ROUTE_INK.time_domain, size: 5 },
        customdata: have.map((r) => [r.n, r.n_visits, r.pooled_slope_p]),
        hovertemplate: "%{x} Hz band · change in band power per milliamp, all visits together: %{y:.2f} device units"
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
        line: { color: PAL.ink, width: 1, dash: "dot" } });
    }
    const layout = plotlyLayout({
      margin: { l: 62, r: 16, t: 16, b: 48 }, height: 240, showlegend: false, hovermode: "closest",
      uirevision: "three-source-pooled-slopes", shapes,
      xaxis: { title: { text: "band centre (Hz)" }, range: [SPECTRUM_LO_HZ - 0.6, SPECTRUM_HI_HZ + 0.6] },
      yaxis: { title: { text: "change per milliamp (device units)" }, zeroline: true, zerolinecolor: PAL.graphic },
      annotations: xs.length ? [] : [{ text: "no change per milliamp is stored for this contact yet",
        x: 0.5, y: 0.55, xref: "paper", yref: "paper", showarrow: false,
        font: { size: PAL.fs.body, color: PAL.ink3 } }],
    });
    Plotly.react(gd, traces, layout, PAL.MODEBAR);
  }, [contactObj, centre, spectrumRevealed]);

  useEffect(() => () => {
    if (topRef.current) Plotly.purge(topRef.current);
    if (specRef.current) Plotly.purge(specRef.current);
  }, []);

  const title = "Band power change per mA, three ways";
  const reportBlock = report && report.data && report.data.three_source_response;
  const footer = reportBlock && reportBlock.comparisons && reportBlock.comparisons[0]
    ? reportBlock.comparisons[0].footer : null;

  // --- the honest empty and loading states ---
  if (!view) {
    let reason;
    if (pooled && pooled.err) reason = pooled.err;
    else if (pooled && pooled.loading) reason = "gathering every run of stepped current from the stored tables…";
    else if (reportBlock && reportBlock.absent_reason) reason = reportBlock.absent_reason;
    else if (report && report.data) {
      reason = "the pooled view is fetched after the report; if it does not appear, the stored "
        + "tables have not been written yet and the next full report writes them";
    } else reason = "waiting for the report";
    return (
      <Card sx={CARD}><CardContent sx={{ p: 3 }}>
        <Typography component="h3" sx={{ ...TYPE.title, ...WRAP.balance, color: PAL.ink, mb: 1 }}>{title}</Typography>
        <Typography sx={{ ...TYPE.body, color: PAL.ink2, mb: 1 }}>{reason}</Typography>
        <Typography sx={{ ...TYPE.body, color: PAL.ink3 }}>
          This panel is informative only. It does not gate anything, and no verdict on this page
          depends on it.
        </Typography>
      </CardContent></Card>
    );
  }
  if (!sides.length) {
    return (
      <Card sx={CARD}><CardContent sx={{ p: 3 }}>
        <Typography component="h3" sx={{ ...TYPE.title, ...WRAP.balance, color: PAL.ink, mb: 1 }}>{title}</Typography>
        <Typography sx={{ ...TYPE.body, color: PAL.ink2 }}>
          {view.absent_reason || "no run of stepped current on one side is stored for this participant"}
        </Typography>
      </CardContent></Card>
    );
  }

  // One-line captions under the three columns, from the stored numbers only.
  const runsSensing = contactObj
    ? contactObj.runs.filter((r) => near(r.programmed_centre_hz, centre)).length : 0;
  let tdCaption;
  if (pooledRow && pooledRow.pooled_slope_per_mA != null) {
    tdCaption = `${pooledRow.n} points across ${pooledRow.n_visits} visits · change in band power per milliamp, all visits together, `
      + `${fmtNum(pooledRow.pooled_slope_per_mA, 2)} ± ${fmtNum(pooledRow.pooled_slope_stderr, 2)} `
      + `device units per mA (p = ${fmtP(pooledRow.pooled_slope_p)}) · ${pooledRow.pooled_direction}`;
    if (pooledRow.curves) {
      tdCaption += ` · a bend was detected (p = ${fmtP(pooledRow.p_curvature)})`;
      if (pooledRow.peaks_inside && pooledRow.peak_mA != null) {
        tdCaption += `, peak near ${fmtNum(pooledRow.peak_mA, 1)} mA`;
      }
    }
  } else if (pooledRow) {
    tdCaption = `change per milliamp, all visits together: ${pooledRow.curvature_note || "not assessed"}`;
  } else {
    tdCaption = "no pooled row is stored for this band yet";
  }
  const directCaption = `${runsSensing} of ${contactObj ? contactObj.n_runs : 0} runs sensed this `
    + "band; the device reports the band it was programmed to sense and no other";
  const psdReasons = contactObj
    ? contactObj.runs.map((r) => r.routes.psd.absent_reason).filter(Boolean) : [];
  const anyPsd = !!(contactObj
    && contactObj.runs.some((r) => (r.routes.psd.currents_mA || []).length));
  const psdCaption = anyPsd ? "the device's own 30-second snapshots, where it took any during a run"
    : (psdReasons[0] || "no settled value in any run");

  return (
    <Card sx={CARD}>
      <CardContent sx={{ p: 3 }}>
        <Typography component="h3" sx={{ ...TYPE.title, ...WRAP.balance, color: PAL.ink, mb: 1 }}>{title}</Typography>

        <ToggleButtonGroup size="small" exclusive value={side} sx={{ mb: 1, flexWrap: "wrap" }}
          onChange={(_e, v) => { if (v != null) setSidePick(v); }}>
          {sides.map((s) => (
            <ToggleButton key={s.ramped_side} value={s.ramped_side}
              sx={{ textTransform: "none", ...TYPE.body, borderColor: PAL.graphic }}>
              {`${s.ramped_side} side turned up · all visits together, `
                + `${s.contacts.reduce((n, c) => n + c.n_runs, 0)} runs`}
            </ToggleButton>
          ))}
        </ToggleButtonGroup>

        {contacts.length > 1 ? (
          <Stack direction="row" spacing={0.6} sx={{ mb: 1 }} alignItems="center">
            <Typography sx={{ ...TYPE.body, color: PAL.ink3 }}>Sensing contact pair:</Typography>
            {contacts.map((c) => (
              <Chip key={c.sensing_contact} size="small"
                onClick={() => setContactPick({ ...contactPick, [side]: c.sensing_contact })}
                label={`${label(c.sensing_contact)} · ${c.n_runs} run${c.n_runs === 1 ? "" : "s"}`}
                sx={{ ...TYPE.body, fontWeight: c.sensing_contact === contact ? 600 : 400,
                  backgroundColor: c.sensing_contact === contact ? PAL.accentFill : "transparent",
                  border: `1px solid ${c.sensing_contact === contact ? PAL.accent : PAL.graphic}` }} />
            ))}
          </Stack>
        ) : null}

        {contactObj ? (
          <Typography sx={{ ...TYPE.body, fontWeight: 600, color: PAL.ink, mb: 0.5 }}>
            {`Sensing on ${label(contact)} · drawn at ${fmtHz(centre)} Hz`}
            {committed && near(centre, committed.centerHz) ? " (the chosen band)" : ""}
            {` · ${contactObj.n_runs} run${contactObj.n_runs === 1 ? "" : "s"} across `
              + `${contactObj.n_visits} visit${contactObj.n_visits === 1 ? "" : "s"}`}
            {contactObj.stimulation_rates_hz && contactObj.stimulation_rates_hz.length
              ? ` · stimulation at ${contactObj.stimulation_rates_hz.map((r) => fmtHz(r)).join(", ")} Hz`
              : ""}
          </Typography>
        ) : null}
        <Typography sx={{ ...TYPE.body, color: PAL.ink3, display: "block", mb: 1 }}>
          One marker shape per run; each point is the average of the steady stretch before the next
          step. The dashed line is the change per milliamp across every run on this contact, drawn
          through the average of the runs&apos; own centres.
        </Typography>

        <Box ref={topRef} sx={{ width: "100%" }} />

        <Stack direction={{ xs: "column", md: "row" }} spacing={1.5} sx={{ mt: 0.5, mb: 1 }}>
          {[tdCaption, psdCaption, directCaption].map((c, i) => (
            <Typography key={ROUTES[i]} sx={{ ...TYPE.body, color: PAL.ink3, flex: 1 }}>{c}</Typography>
          ))}
        </Stack>

        <Divider sx={{ my: 1.2 }} />

        {/* Mounted on first reveal and kept mounted: a Plotly figure first drawn inside a hidden
            container measures itself as zero pixels wide and keeps that size. */}
        <Typography component="button" type="button"
          onClick={() => setShowSpectrum((s) => !s)} aria-expanded={showSpectrum}
          sx={{ ...TYPE.body, color: PAL.ink2, cursor: "pointer", background: "none", border: 0, padding: 0,
            fontFamily: "inherit", display: "inline-flex", alignItems: "center", gap: 1,
            "&:hover": { textDecoration: "underline" } }}>
          <FoldArrow open={showSpectrum} />
          {showSpectrum ? "Hide the other bands"
            : `Show the change per milliamp at every band from ${fmtHz(SPECTRUM_LO_HZ)} to ${fmtHz(SPECTRUM_HI_HZ)} Hz`}
        </Typography>
        {spectrumRevealed ? (
          <Box sx={{ display: showSpectrum ? "block" : "none" }}>
            <Typography sx={{ ...TYPE.body, color: PAL.ink3, display: "block", mt: 0.5, mb: 0.5 }}>
              From the recording (TD) only, the one source every run reports at every band.
              The shaded band is ±2 standard errors; striped bands carry a folded multiple of the
              stimulation rate; the dotted line marks the band drawn above.
            </Typography>
            <Box ref={specRef} sx={{ width: "100%" }} />
          </Box>
        ) : null}

        <Fold show="Agreement caveat" hide="Hide" dense>
          <Typography sx={{ ...TYPE.body, display: "block", color: PAL.ink2 }}>
            {footer || ("The three columns are not independent: the device computes its own band "
              + "power from the voltage trace the first column reads, so agreement checks the "
              + "conversion, not the effect three times.")}
          </Typography>
          <Typography sx={{ ...TYPE.body, display: "block", mt: 0.5, color: PAL.ink2 }}>
            This panel is informative only. It does not gate anything, and no verdict on this page
            depends on it.
          </Typography>
        </Fold>
      </CardContent>
    </Card>
  );
}
