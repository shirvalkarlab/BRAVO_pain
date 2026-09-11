/**
 * How stimulation current moved band power, measured three separate ways and put side by side.
 *
 * WHY THIS BELONGS ON THIS PAGE. Closed loop works by watching the power in one band and moving the
 * current when that power crosses a value typed into the stimulator. There are three different ways
 * to get a band power out of this device and they come from three different recordings: from the
 * streamed voltage trace, from the device's own onboard spectrum, and from the band power the device
 * computes on board and reports directly. Whoever is about to type a threshold into the programmer
 * should be able to see all three next to each other, over the same stimulation settings, in the
 * device's own units, before they pick a number. The PI asked for exactly that.
 *
 * THIS PANEL GATES NOTHING, and that is deliberate. There is no badge, no verdict, no pass and no
 * fail anywhere on this card, no blocking status, and nothing else on the page reads it. It is
 * informative. Whether a disagreement between the three routes should stop a deployment is the PI's
 * call, not this panel's.
 *
 * WHAT A READER MUST NOT TAKE FROM IT. Three columns agreeing is NOT three independent
 * confirmations that stimulation moved the brain. The device computes its own band power on board
 * from the very voltage trace the first column reads, so those two are one recording seen two ways.
 * The contact surveys behind the second column are where the conversion into device units was
 * fitted in the first place, so that column can never be an independent user of the conversion.
 * Agreement across the columns says the conversion is behaving, and says nothing more. That sentence
 * is not left to this comment: the server computes it into the footer text this panel prints, so the
 * numbers cannot be shown without it.
 *
 * WHY THE COLUMN FOR THE DEVICE'S OWN BAND POWER HAS ONE POINT AND NOT A CURVE. The device reports
 * its own band power for the single band it was programmed to sense and for no other band. That is
 * a fact about the device, not a gap in the record, so the panel draws one point and says so rather
 * than leaving a reader to wonder what went missing.
 *
 * WHY AN EMPTY COLUMN PRINTS A SENTENCE INSTEAD OF NOTHING. A blank chart reads as broken, and a
 * missing key reads as "does not apply here". Neither is true when a route simply had no recording
 * during a stretch of rising current. Every absent column here prints the server's reason, which
 * names what was looked for and what was found instead.
 *
 * NO NUMBER ON THIS CARD IS COMPUTED HERE. Every value, every sentence and every mark comes from the
 * server payload, which is built by the same code that draws the static picture for the report. A
 * second implementation in the browser is how the page and the report would come to disagree about
 * what happened, which has cost this project real errors elsewhere.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import Plotly from "plotly.js-dist";
import {
  Card, CardContent, Typography, Box, Stack, Divider, ToggleButton, ToggleButtonGroup,
} from "@mui/material";

import { PAL, OKABE_ITO } from "./palette";
import { fmtHz, fmtMilliamps } from "./deployFormat";

/** One colour per route, matching the static picture in the report exactly. */
const ROUTE_INK = {
  "time domain voltage trace": OKABE_ITO.blue,
  "device's own spectrum": OKABE_ITO.orange,
  "device's own band power": OKABE_ITO.bluishGreen,
};
const NEUTRAL_INK = OKABE_ITO.gray;
const GRID_INK = "#DDDDDD";

/** Pale to dark within the column's own colour, so the shading says how much current was running. */
function shadeOf(hex, i, n) {
  const f = 0.25 + 0.75 * (n > 1 ? i / (n - 1) : 1);
  const r = parseInt(hex.slice(1, 3), 16), g = parseInt(hex.slice(3, 5), 16),
    b = parseInt(hex.slice(5, 7), 16);
  const mix = (c) => Math.round(255 - f * (255 - c));
  return `rgb(${mix(r)},${mix(g)},${mix(b)})`;
}

/** Three side-by-side panels in one figure, laid out by hand: plotly.js has no subplot helper. */
function threeColumnLayout(headings, xTitle, yTitle) {
  const layout = {
    margin: { l: 62, r: 16, t: 26, b: 46 },
    height: 260, plot_bgcolor: "white", paper_bgcolor: "white",
    showlegend: false, font: { size: 11 }, hovermode: "closest",
    uirevision: "three-source-response", annotations: [],
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
      tickfont: { size: 10 },
      title: k === 0 ? { text: yTitle, font: { size: 10 } } : undefined,
    };
  });
  return layout;
}

export default function ThreeSourceResponsePanel({ report }) {
  const payload = report?.data?.three_source_response;
  const comparisons = payload?.comparisons || [];
  const [which, setWhich] = useState(0);
  const [showSpectrum, setShowSpectrum] = useState(false);
  // Mounted on the first reveal and kept mounted afterwards: a Plotly figure first drawn inside a
  // hidden container measures itself as zero pixels wide and stays that size.
  const [spectrumRevealed, setSpectrumRevealed] = useState(false);
  useEffect(() => {
    if (showSpectrum && !spectrumRevealed) setSpectrumRevealed(true);
  }, [showSpectrum, spectrumRevealed]);
  const topRef = useRef(null);
  const specRef = useRef(null);

  const chosen = comparisons[Math.min(which, Math.max(comparisons.length - 1, 0))] || null;

  /** The y range is pooled across the three columns, so a taller line really is a larger number. */
  const topRange = useMemo(() => {
    if (!chosen) return null;
    const vals = chosen.columns.flatMap((c) => (c.settled_power || []).filter((v) => v != null));
    if (vals.length < 2) return null;
    const lo = Math.min(...vals), hi = Math.max(...vals);
    const pad = 0.12 * (hi - lo || hi);
    return [Math.max(0, lo - pad), hi + pad];
  }, [chosen]);

  const specRange = useMemo(() => {
    if (!chosen) return null;
    const vals = chosen.columns.flatMap((c) =>
      (c.spectrum_lines || []).flatMap((l) => (l.power || []).filter((v) => v != null)));
    if (vals.length < 2) return null;
    const lo = Math.min(...vals), hi = Math.max(...vals);
    const pad = 0.08 * (hi - lo || hi);
    return [Math.max(0, lo - pad), hi + pad];
  }, [chosen]);

  // --- TOP ROW: the one band all three routes can report, against the current delivered ---
  useEffect(() => {
    const gd = topRef.current;
    if (!gd) return;
    if (!chosen) { Plotly.purge(gd); return; }
    const traces = [];
    const layout = threeColumnLayout(chosen.columns.map((c) => c.heading),
      chosen.amp_axis_label, chosen.power_axis_label);
    chosen.columns.forEach((col, k) => {
      const ax = k === 0 ? "" : String(k + 1);
      const ink = ROUTE_INK[col.source] || NEUTRAL_INK;
      layout.annotations.push({
        text: `<b>${col.heading}</b>`, x: layout[`xaxis${ax}`].domain[0], y: 1.13,
        xref: "paper", yref: "paper", showarrow: false, xanchor: "left",
        font: { size: 11, color: "#1A1A1A" },
      });
      if ((col.settled_power || []).length) {
        traces.push({
          type: "scatter", mode: "lines+markers", xaxis: `x${ax}`, yaxis: `y${ax}`,
          x: col.current_mA, y: col.settled_power,
          line: { color: ink, width: 1.4 },
          marker: { color: ink, size: 8, line: { color: "white", width: 1 } },
          customdata: col.n_pieces,
          hovertemplate: `${col.heading}<br>%{x} mA<br>%{y:.1f} device units<br>`
            + "averaged over %{customdata} pieces<extra></extra>",
        });
        if (topRange) layout[`yaxis${ax}`].range = topRange;
      } else {
        // An empty column says why, in the server's own words, rather than sitting blank.
        layout.annotations.push({
          text: `<i>no settled value from this recording</i>`,
          x: layout[`xaxis${ax}`].domain[0] + 0.5 * (layout[`xaxis${ax}`].domain[1]
            - layout[`xaxis${ax}`].domain[0]),
          y: 0.55, xref: "paper", yref: "paper", showarrow: false, xanchor: "center",
          font: { size: 11, color: NEUTRAL_INK },
        });
        layout[`xaxis${ax}`].showticklabels = false;
        layout[`yaxis${ax}`].showticklabels = false;
        if (topRange) layout[`yaxis${ax}`].range = topRange;
      }
    });
    Plotly.react(gd, traces, layout, PAL.MODEBAR);
  }, [chosen, topRange]);

  // --- BOTTOM ROW: the rest of the spectrum, one line per stimulation setting ---
  useEffect(() => {
    const gd = specRef.current;
    if (!gd) return;
    if (!chosen) { Plotly.purge(gd); return; }
    const traces = [];
    const layout = threeColumnLayout(chosen.columns.map((c) => c.heading),
      chosen.band_axis_label, chosen.power_axis_label);
    layout.shapes = [];
    chosen.columns.forEach((col, k) => {
      const ax = k === 0 ? "" : String(k + 1);
      const ink = ROUTE_INK[col.source] || NEUTRAL_INK;
      layout[`xaxis${ax}`].range = [chosen.spectrum_lo_hz - 0.6, chosen.spectrum_hi_hz + 0.6];
      if (specRange) layout[`yaxis${ax}`].range = specRange;

      // The band centres that carry a folded multiple of the stimulation rate. This mark is a
      // data label, not a caveat: before it existed the largest apparent effect on a heat map of
      // this record was the stimulation artifact and it looked like a spectacular biomarker. It is
      // drawn faint and under the data so the values stay readable through it.
      const striped = chosen.striped_centres_hz || [];
      if (striped.length) {
        layout.shapes.push({
          type: "rect", xref: `x${ax}`, yref: "paper", layer: "below",
          x0: Math.min(...striped) - chosen.band_half_hz,
          x1: Math.max(...striped) + chosen.band_half_hz,
          y0: 0, y1: 1, fillcolor: NEUTRAL_INK, opacity: 0.1, line: { width: 0 },
        });
      }
      (chosen.landings_in_view_hz || []).forEach((f) => {
        layout.shapes.push({
          type: "line", xref: `x${ax}`, yref: "paper", layer: "below",
          x0: f, x1: f, y0: 0, y1: 1,
          line: { color: NEUTRAL_INK, width: 1, dash: "dash" },
        });
      });

      const lines = col.spectrum_lines || [];
      if (lines.length) {
        lines.forEach((ln, i) => {
          traces.push({
            type: "scatter", mode: "lines", xaxis: `x${ax}`, yaxis: `y${ax}`,
            x: ln.centres_hz, y: ln.power,
            line: { color: shadeOf(ink, i, lines.length), width: 1.6 },
            hovertemplate: `${col.heading}, ${ln.current_mA} mA<br>%{x} Hz band<br>`
              + "%{y:.1f} device units<extra></extra>",
          });
        });
      } else if (col.band_centre_hz != null && (col.settled_power || []).length) {
        traces.push({
          type: "scatter", mode: "markers", xaxis: `x${ax}`, yaxis: `y${ax}`,
          x: col.settled_power.map(() => col.band_centre_hz), y: col.settled_power,
          marker: { color: ink, size: 8, line: { color: "white", width: 1 } },
          hovertemplate: "the device reports this band and no other<br>%{x} Hz<br>"
            + "%{y:.1f} device units<extra></extra>",
        });
        layout.annotations.push({
          text: "the device reports this band and no other",
          x: layout[`xaxis${ax}`].domain[1], y: 1.06, xref: "paper", yref: "paper",
          showarrow: false, xanchor: "right", font: { size: 10, color: NEUTRAL_INK },
        });
      }
    });
    Plotly.react(gd, traces, layout, PAL.MODEBAR);
  }, [chosen, specRange, spectrumRevealed]);

  useEffect(() => () => {
    if (topRef.current) Plotly.purge(topRef.current);
    if (specRef.current) Plotly.purge(specRef.current);
  }, []);

  // --- the honest empty state: say WHICH piece was missing, never look broken ---
  if (!payload || !comparisons.length) {
    return (
      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Stimulation amplitude effects on band power, measured three ways
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
            {payload?.absent_reason
              || "the report did not carry this comparison, so nothing about it can be shown here. "
                 + "That is a missing piece of the report rather than a finding about the recordings."}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            This panel is informative only. It does not gate anything, and no verdict on this page
            depends on it.
          </Typography>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent>
        {/* Title given by the PI on 2026-09-10 ("really critical and important"). */}
        <Typography variant="h6" gutterBottom>
          Stimulation amplitude effects on band power, measured three ways
        </Typography>

        {comparisons.length > 1 && (
          <ToggleButtonGroup size="small" exclusive value={which} sx={{ mb: 1.5, flexWrap: "wrap" }}
            onChange={(_e, v) => { if (v != null) setWhich(v); }}>
            {comparisons.map((c, i) => (
              <ToggleButton key={`${c.visit_date}-${c.ramped_side}-${i}`} value={i}
                sx={{ textTransform: "none", fontSize: 12 }}>
                {`${c.visit_date}, ${c.ramped_side.toLowerCase()} side `}
                {`${fmtMilliamps(c.current_from_mA)} to ${fmtMilliamps(c.current_to_mA)}`}
              </ToggleButton>
            ))}
          </ToggleButtonGroup>
        )}

        <Typography variant="subtitle2" sx={{ fontWeight: 600, lineHeight: 1.45, mb: 0.5 }}>
          {chosen.headline}
        </Typography>
        <Typography variant="caption" color="text.secondary"
          sx={{ display: "block", lineHeight: 1.55, mb: 1 }}>
          {chosen.subtitle}
        </Typography>

        <Box ref={topRef} sx={{ width: "100%" }} />

        <Stack direction={{ xs: "column", md: "row" }} spacing={1.5} sx={{ mt: 0.5, mb: 1.5 }}>
          {chosen.columns.map((col) => (
            <Typography key={col.source} variant="caption" color="text.secondary"
              sx={{ flex: 1, lineHeight: 1.5 }}>
              {col.caption}
            </Typography>
          ))}
        </Stack>

        <Divider sx={{ my: 1.5 }} />

        {/* The whole-range row and the footer stay MOUNTED and are hidden by style, never
            unmounted -- a Plotly figure first drawn inside a hidden container measures itself as
            zero pixels wide and keeps that size, so the figure is drawn once at full width and
            then shown or hidden (the same rule the analyst fold on this page follows). */}
        <Typography variant="caption" component="button" type="button"
          onClick={() => setShowSpectrum((s) => !s)} aria-expanded={showSpectrum}
          sx={{ color: PAL.accent, cursor: "pointer", background: "none", border: 0, padding: 0,
            fontFamily: "inherit", display: "inline-flex", alignItems: "center", gap: 0.5,
            "&:hover": { textDecoration: "underline" } }}>
          <span aria-hidden="true" style={{ fontSize: 9, display: "inline-block",
            transform: showSpectrum ? "rotate(90deg)" : "none" }}>▶</span>
          {showSpectrum ? "Hide the other bands"
            : `Show every band from ${fmtHz(chosen.spectrum_lo_hz)} to ${fmtHz(chosen.spectrum_hi_hz)} over the same settings`}
        </Typography>
        {spectrumRevealed ? <Box sx={{ display: showSpectrum ? "block" : "none" }}>
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5, mb: 0.5 }}>
            Line shade runs from the lowest current to the highest.
          </Typography>
          <Box ref={specRef} sx={{ width: "100%" }} />
          <Typography variant="caption" sx={{ display: "block", mt: 1.5, color: NEUTRAL_INK,
            lineHeight: 1.55 }}>
            {chosen.footer}
          </Typography>
          <Typography variant="caption" sx={{ display: "block", mt: 0.75, color: NEUTRAL_INK }}>
            This panel is informative only. It does not gate anything, and no verdict on this page
            depends on it.
          </Typography>
        </Box> : null}
      </CardContent>
    </Card>
  );
}
