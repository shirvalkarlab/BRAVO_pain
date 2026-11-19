/**
 * The recording timeline's detail panel (item P-18, the PI's go-ahead 2026-10-06), on the
 * Biomarkers page directly under the timeline. Opens when a mark on a contact pair's lane is
 * clicked: a voltage block, a PSD tick, or a point of the band-power line or a session block.
 *
 * Shows what the device recorded for THAT contact pair only, from /api/queryTimelineDetail
 * (`Biomarkers/routines/timeline_detail.py`): the voltage trace (µV), the device's own PSD (µVp for
 * a montage or survey, µV for a patient event) and the device's sensed band power (LSB) within 12 h.
 * Linear axes (log power enters no plot, decision 202); no pain rating (decision 216); nothing
 * computed or judged. A piece the mark does not have is said in words, never drawn as an empty axis.
 *
 * Sits under the timeline, not beside it, so the timeline keeps its full width and its left-label
 * columns (bravo-timeline-layout) are untouched.
 */
import { useEffect, useRef, useState } from "react";
import Plotly from "plotly.js-dist";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import { SessionController } from "database/session-control";
import { T, TYPE } from "assets/theme/base/tokens";
import { CATEGORICAL } from "assets/theme/base/dataColors";
import { plotlyLayout, PLOTLY_CONFIG_WITH_TOOLBAR } from "views/Reports/figureStyle";

const WORDS = { 0: "0", 1: "1", 2: "2", 3: "3" };
const NUM = { ZERO: 0, ONE: 1, TWO: 2, THREE: 3 };

/** "L 0⁻3⁺" from "ZERO_THREE_LEFT" (the pair the server answered for). */
export function pairLabel(pair) {
  const up = String(pair || "").toUpperCase();
  const side = up.indexOf("LEFT") >= 0 ? "L" : (up.indexOf("RIGHT") >= 0 ? "R" : "");
  const n = (up.match(/ZERO|ONE|TWO|THREE/g) || []).map((w) => NUM[w]);
  if (side && n.length >= 2) return `${side} ${WORDS[n[0]]}⁻${WORDS[n[1]]}⁺`;
  return up;
}

/** The line under the timeline naming the streaming runs left out for reading 0 throughout
 *  (decision 462), from the server's per-pair counts; "" when none were. */
export function zeroRunsLine(byPair) {
  const keys = Object.keys(byPair || {}).filter((k) => byPair[k] > 0);
  if (!keys.length) return "";
  const parts = keys.map((k) => [pairLabel(k), byPair[k]]).sort((a, b) => (a[0] < b[0] ? -1 : 1))
    .map(([l, n]) => `${l} ${n}`);
  return `Streaming runs reading 0 throughout, not counted as band power: ${parts.join(", ")}`;
}

const KIND = {
  streaming_td: "BrainSense streaming", indefinite: "indefinite streaming",
  montage_td: "montage or survey", montage_psd: "montage or survey", survey_psd: "survey",
  patient_event: "patient event", timeline_lsb: "chronic band power",
  streaming_lsb: "streaming band power",
};

const when = (t) => (t == null ? "" : new Date(Number(t) * 1000).toLocaleString("en-US",
  { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }));

/** The panel's one-line heading: pair, kind and time. */
export function detailHeading(sel, detail) {
  const pair = pairLabel((detail && detail.pair) || (sel && sel.Channel));
  const kind = KIND[sel && sel.Product] || "recording";
  return `${pair} · ${kind} · ${when(sel && sel.TStart)}`;
}

/** The sentences for what this mark has none of, in the server's own words. */
export function missingLines(detail) {
  const m = (detail && detail.missing) || {};
  const out = [];
  if (m.all) out.push(m.all);
  if (m.trace) out.push(`Voltage trace: ${m.trace}.`);
  if (m.psd) out.push(`Device PSD: ${m.psd}.`);
  if (m.band_power) out.push(`Band power: ${m.band_power}.`);
  return out;
}

/** The note under the trace when it was sent thinned. */
export function traceNote(tr) {
  if (!tr) return "";
  const dur = tr.dur_s >= 90 ? `${(tr.dur_s / 60).toFixed(1)} min` : `${Math.round(tr.dur_s)} s`;
  const thin = tr.envelope ? `; drawn as the lowest and highest of every ${tr.every_nth} samples` : "";
  return `${tr.n.toLocaleString()} samples, ${tr.fs} per second, ${dur}${thin}`;
}

function TracePlot({ tr }) {
  const ref = useRef(null);
  useEffect(() => {
    if (!ref.current || !tr) return;
    const x = tr.x_s || tr.y.map((_, i) => i / tr.fs);
    Plotly.react(ref.current, [{ x, y: tr.y, type: "scattergl", mode: "lines",
      line: { color: CATEGORICAL[0], width: 1 }, connectgaps: false,
      hovertemplate: "%{y:.1f} µV at %{x:.2f} s<extra></extra>" }],
    plotlyLayout({ height: 220, uirevision: "detail-trace", margin: { l: 56, r: 16, t: 8, b: 44 },
      xaxis: { title: { text: "Seconds from the start" } },
      yaxis: { title: { text: "Voltage (µV)" } } }), PLOTLY_CONFIG_WITH_TOOLBAR);
  }, [tr]);
  useEffect(() => () => { if (ref.current) Plotly.purge(ref.current); }, []);
  return <div ref={ref} data-testid="detail-trace" style={{ width: "100%" }} />;
}

function PsdPlot({ psd }) {
  const ref = useRef(null);
  useEffect(() => {
    if (!ref.current || !psd) return;
    const peak = Number(psd.peak_hz) > 0 ? Number(psd.peak_hz) : null;
    Plotly.react(ref.current, [{ x: psd.freq, y: psd.mag, type: "scatter", mode: "lines",
      line: { color: CATEGORICAL[1], width: 1.6 },
      hovertemplate: `%{y:.3f} ${psd.unit} at %{x:.2f} Hz<extra></extra>` }],
    plotlyLayout({ height: 220, uirevision: "detail-psd", margin: { l: 56, r: 16, t: 8, b: 44 },
      xaxis: { title: { text: "Frequency (Hz)" }, range: [0, 60] },
      yaxis: { title: { text: `Device PSD (${psd.unit})` }, rangemode: "tozero" },
      shapes: peak ? [{ type: "line", xref: "x", yref: "paper", x0: peak, x1: peak, y0: 0, y1: 1,
        line: { color: T.ink3, width: 1, dash: "dash" } }] : [] }), PLOTLY_CONFIG_WITH_TOOLBAR);
  }, [psd]);
  useEffect(() => () => { if (ref.current) Plotly.purge(ref.current); }, []);
  return <div ref={ref} data-testid="detail-psd" style={{ width: "100%" }} />;
}

function BandPowerPlot({ bp, tMark }) {
  const ref = useRef(null);
  useEffect(() => {
    if (!ref.current || !bp) return;
    const D = (t) => new Date(t * 1000);
    const groups = {};
    bp.t.forEach((t, i) => { const k = bp.source[i] || "device"; (groups[k] = groups[k] || []).push(i); });
    const traces = Object.keys(groups).map((k, j) => ({
      x: groups[k].map((i) => D(bp.t[i])), y: groups[k].map((i) => bp.y[i]),
      type: "scattergl", mode: k === "chronic" ? "lines+markers" : "markers", name: k,
      marker: { size: 4, color: CATEGORICAL[(j + 2) % CATEGORICAL.length] },
      customdata: groups[k].map((i) => (bp.center_hz[i] == null ? "?" : Number(bp.center_hz[i]).toFixed(1))),
      hovertemplate: `${k}: %{y:.0f} LSB at %{customdata} Hz<br>%{x}<extra></extra>`,
    }));
    Plotly.react(ref.current, traces, plotlyLayout({ height: 220, uirevision: "detail-bp",
      showlegend: true, margin: { l: 56, r: 16, t: 8, b: 44 },
      xaxis: { type: "date" }, yaxis: { title: { text: "Band power (LSB)" } },
      shapes: tMark == null ? [] : [{ type: "line", xref: "x", yref: "paper", x0: D(tMark), x1: D(tMark),
        y0: 0, y1: 1, line: { color: T.ink3, width: 1, dash: "dash" } }] }), PLOTLY_CONFIG_WITH_TOOLBAR);
  }, [bp, tMark]);
  useEffect(() => () => { if (ref.current) Plotly.purge(ref.current); }, []);
  return <div ref={ref} data-testid="detail-band-power" style={{ width: "100%" }} />;
}

export default function TimelineDetailPanel({ participantUid, selection, onClose }) {
  const [state, setState] = useState({ loading: false, detail: null, err: null });
  useEffect(() => {
    if (!participantUid || !selection) return undefined;
    let live = true;
    setState({ loading: true, detail: null, err: null });
    SessionController.query("/api/queryTimelineDetail", { ParticipantId: participantUid, ...selection })
      .then((res) => {
        if (!live) return;
        const d = res && res.data;
        if (d && d.available) setState({ loading: false, detail: d, err: null });
        else setState({ loading: false, detail: null, err: (d && d.reason) || "not available" });
      })
      .catch((e) => { if (live) setState({ loading: false, detail: null, err: String(e) }); });
    return () => { live = false; };
  }, [participantUid, selection]);

  if (!selection) return null;
  const { loading, detail, err } = state;
  const LINE = { ...TYPE.body, color: T.ink2, display: "block" };
  return (
    <MDBox mt={2} pt={2} data-testid="timeline-detail-panel" sx={{ borderTop: `1px solid ${T.rule}` }}>
      <MDBox display="flex" justifyContent="space-between" alignItems="baseline">
        <MDTypography component="h3" sx={{ ...TYPE.title, color: T.ink, m: 0 }}>
          {detailHeading(selection, detail)}
        </MDTypography>
        <button type="button" onClick={onClose}
          style={{ ...TYPE.body, background: "none", border: "none", color: T.accent, cursor: "pointer" }}>
          Close
        </button>
      </MDBox>
      <MDTypography variant="caption" sx={{ ...LINE, color: T.ink3 }}>
        What the device recorded on this contact pair; nothing here is matched to pain.
      </MDTypography>
      {loading ? (
        <MDTypography variant="caption" sx={{ ...LINE, mt: 1, color: T.ink3 }}>Loading the recording…</MDTypography>
      ) : err ? (
        <MDTypography variant="caption" sx={{ ...LINE, mt: 1, color: T.caution }}>{`▲ Not available: ${err}`}</MDTypography>
      ) : detail ? (
        <MDBox>
          {missingLines(detail).map((s) => (
            <MDTypography key={s} variant="caption" sx={{ ...LINE, mt: 0.5 }}>{s}</MDTypography>
          ))}
          {detail.trace ? (
            <MDBox mt={1}>
              <MDTypography variant="caption" sx={{ ...LINE, fontWeight: 600, color: T.ink }}>Voltage trace</MDTypography>
              <TracePlot tr={detail.trace} />
              <MDTypography variant="caption" sx={{ ...TYPE.caption, color: T.ink3, display: "block" }}>
                {traceNote(detail.trace)}
              </MDTypography>
            </MDBox>
          ) : null}
          {detail.psd ? (
            <MDBox mt={1}>
              <MDTypography variant="caption" sx={{ ...LINE, fontWeight: 600, color: T.ink }}>
                {`Device PSD, ${detail.psd.source}`}
              </MDTypography>
              <PsdPlot psd={detail.psd} />
            </MDBox>
          ) : null}
          {detail.band_power ? (
            <MDBox mt={1}>
              <MDTypography variant="caption" sx={{ ...LINE, fontWeight: 600, color: T.ink }}>
                {`Device band power, 12 h either side (n=${detail.band_power.n.toLocaleString()})`}
              </MDTypography>
              <BandPowerPlot bp={detail.band_power} tMark={selection.TStart} />
            </MDBox>
          ) : null}
        </MDBox>
      ) : null}
    </MDBox>
  );
}
