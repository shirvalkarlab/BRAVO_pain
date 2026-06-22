/**
 * BiomarkerDataTimeline -- per-channel DATA-AVAILABILITY timeline over real calendar time.
 *
 * Replaces BiomarkerTimeline. Answers "what data exists, when, and what does it look like?" for the
 * Percept RC. Per sensing channel (grouped LEFT then RIGHT) one compact OVERVIEW lane carries three
 * DENSITY-gated sub-bands on one shared time axis:
 *   - time-domain raw uV  -> grey COVERAGE block   (250 Hz is meaningless at calendar scale; zoom)
 *   - band-power LSB       -> INLINE trend line     (colored by sensing center frequency, categorical)
 *   - PSD snapshots        -> TICKS                 (one-shot spectra; click/hover -> the curve)
 * Below the neural lanes, on the SAME x-axis: a patient-reported PAIN row (full height) and a
 * compact STIMULATION-amplitude row. A right-hand INSPECTOR shows the selected channel's real PSD
 * curve, raw uV waveform, and LSB trend. Selecting a lane sets the inspector channel; the timeline
 * is the front door to the decode (select band -> threshold -> controller).
 *
 * Consumes `data.availability` from QueryBiomarkerAnalysis:
 *   { records:[{channel,label,hemisphere,dtype,product,t_start,dur_s,meta:{center_hz,peak_hz,n}}],
 *     pain:{metric,t:[epoch_s],y:[val]}, stim:{t:[epoch_s],y:[mA]}, freq_bands:[hz], span:[t0,t1] }
 * Self-contained via plotly.js-dist. Categorical FREQ_PALETTE ported from BiomarkerTimeline.js.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import Plotly from "plotly.js-dist";

import MDBox from "components/MDBox";

// ---- platform palette (ported verbatim from BiomarkerTimeline.js) -----------------------------
const C = { pain: "#D55E00", stim: "#E69F00", td: "#BCBCBC", ink: "#1a1a1a" };
const HEMI = {
  Left: { lane: "#0072B2", sel: "rgba(0,114,178,0.10)" },
  Right: { lane: "#D55E00", sel: "rgba(213,94,0,0.10)" },
};
const FREQ_BIN_HZ = 250 / 256;
const FREQ_PALETTE = {
  3.9: "#882255", 4.9: "#AA4499", 5.9: "#CC6677", 6.8: "#993377",
  7.8: "#332288", 8.8: "#0072B2", 9.8: "#56B4E9", 10.7: "#009E73",
  11.7: "#94C973", 12.7: "#E69F00", 13.7: "#F0A860", 14.6: "#B8860B",
  15.6: "#7E6E1F", 16.6: "#A6761D", 17.6: "#666633",
  18.6: "#44AA99", 19.5: "#117733", 20.5: "#88CCEE", 21.5: "#6699CC",
  22.5: "#4477AA", 23.4: "#D55E00", 24.4: "#BB5566", 25.4: "#AA3377", 26.4: "#CC79A7",
};
const FREQ_FALLBACK = ["#332288", "#0072B2", "#56B4E9", "#009E73", "#94C973",
                       "#E69F00", "#D55E00", "#CC79A7", "#44AA99", "#882255"];
function snapFreq(hz) {
  if (hz == null || !Number.isFinite(hz)) return null;
  return Math.round((Math.round(hz / FREQ_BIN_HZ) * FREQ_BIN_HZ) * 10) / 10;
}
function freqColor(hz) {
  const b = snapFreq(hz);
  if (b == null) return "#BDBDBD";
  if (FREQ_PALETTE[b] != null) return FREQ_PALETTE[b];
  return FREQ_FALLBACK[Math.abs(Math.round(b)) % FREQ_FALLBACK.length];
}
function textOn(hexcol) {
  const h = hexcol.replace("#", "");
  const r = parseInt(h.slice(0, 2), 16), g = parseInt(h.slice(2, 4), 16), b = parseInt(h.slice(4, 6), 16);
  return (0.299 * r + 0.587 * g + 0.114 * b) > 150 ? "#111111" : "#FFFFFF";
}
function fmtHz(hz) {
  const b = snapFreq(hz);
  if (b == null) return "";
  return Number.isInteger(b) ? String(b) : b.toFixed(1).replace(/\.0$/, "");
}
function prettyContact(label) {
  const SUP = { "-": "\u207B", "+": "\u207A" };
  if (label == null) return "";
  const s = String(label);
  if (s.indexOf("\u207B") >= 0 || s.indexOf("\u207A") >= 0) return s;
  return s.replace(/(\d+)\s*-\s*(\d+)/, (_, a, b) => `${a}${SUP["-"]}${b}${SUP["+"]}`);
}
const toDate = (epoch_s) => new Date(epoch_s * 1000);
// hex "#RRGGBB" -> "rgba(r,g,b,a)" for translucent fills (freqColor always returns hex).
function hexA(hexcol, a) {
  const h = String(hexcol).replace("#", "");
  if (h.length < 6) return hexcol;
  const r = parseInt(h.slice(0, 2), 16), g = parseInt(h.slice(2, 4), 16), b = parseInt(h.slice(4, 6), 16);
  return `rgba(${r},${g},${b},${a})`;
}

// Normalize a Percept channel label to its physical contact-pair identity, so the SAME pair
// recorded by different products (streaming "ZERO_THREE_LEFT" vs montage "ZERO_AND_THREE_LEFT")
// collapses into ONE lane. Maps the contact-word pair + hemisphere to a canonical "<PAIR>_<HEMI>".
// Ring/segment contacts keep their full label (they are distinct sensing geometries).
const _WORDNUM = { ZERO: 0, ONE: 1, TWO: 2, THREE: 3 };
function normalizeChannel(ch) {
  const up = String(ch).toUpperCase();
  if (up.indexOf("RING") >= 0 || up.indexOf("SEGMENT") >= 0) return up;
  const hemi = up.indexOf("LEFT") >= 0 ? "LEFT" : (up.indexOf("RIGHT") >= 0 ? "RIGHT" : "");
  const nums = (up.match(/ZERO|ONE|TWO|THREE/g) || []).map((w) => _WORDNUM[w]);
  if (nums.length >= 2 && hemi) {
    const a = Math.min(nums[0], nums[1]), b = Math.max(nums[0], nums[1]);
    const PAIR = ["ZERO", "ONE", "TWO", "THREE"];
    return `${PAIR[a]}_${PAIR[b]}_${hemi}`;
  }
  return up;
}

// ---- canonical channel ordering: LEFT pairs then RIGHT pairs ----------------------------------
const PAIR_ORDER = ["ZERO_THREE", "ONE_THREE", "ZERO_TWO", "ZERO_ONE", "TWO_THREE", "ONE_TWO"];
function channelSortKey(ch) {
  const up = String(ch).toUpperCase();
  const hemi = up.indexOf("LEFT") >= 0 ? 0 : 1;
  let pair = PAIR_ORDER.findIndex((p) => up.indexOf(p) >= 0);
  if (pair < 0) pair = PAIR_ORDER.length;
  return hemi * 100 + pair;
}
// DEFAULT VIEW = the main bipolar SENSING pairs (0-3, 1-3, 0-2 per hemisphere). The Percept also
// exposes many ring/segment montage contacts (…_RING, …_SEGMENT) and adjacent montage pairs; per
// the design these belong in an "expert" toggle, not the default lanes — otherwise 40+ lanes crowd
// the view. A channel is a main sensing pair if it names a 2-contact pair and is NOT a ring/segment.
function isMainSensingChannel(ch) {
  const up = String(ch).toUpperCase();
  if (up.indexOf("RING") >= 0 || up.indexOf("SEGMENT") >= 0) return false;
  // accept the canonical decoder pairs (ZERO_THREE / ONE_THREE / ZERO_TWO) in either label form
  return /(ZERO_THREE|ONE_THREE|ZERO_TWO|ZERO_AND_THREE|ONE_AND_THREE|ZERO_AND_TWO)/.test(up);
}

// ---- inspector: selected channel's real PSD curve, raw uV waveform, LSB trend ----------------
// Uses decimated `samples` the backend attaches per channel under av.samples[channel] =
//   { psd:{freq:[],mag:[],peak_hz}, td:{fs,sample:[]}, lsb:{t:[epoch_s],y:[]} }.
// Each is optional; a missing block shows an honest placeholder. Three stacked panels in the
// right column [OV_R..1], rows mapped onto dedicated axes appended after the overview axes.
function buildInspector(traces, layout, OV_R, av, selected, centerHzOf, recordsFor) {
  const IL = OV_R + 0.06;             // inspector left edge
  // av.samples is keyed by RAW channel; selected is a NORMALIZED pair id — find a sample whose
  // raw key normalizes to the selection (prefer one that actually carries a signal block).
  let samp = null;
  if (av.samples && selected) {
    const keys = Object.keys(av.samples).filter((k) => normalizeChannel(k) === selected);
    samp = keys.map((k) => av.samples[k]).find((s) => s && (s.psd || s.td || s.lsb)) || (keys.length ? av.samples[keys[0]] : null);
  }
  const chz = selected ? centerHzOf(selected) : null;
  const fc = chz != null ? freqColor(chz) : "#0072B2";
  const hemi = selected && selected.toUpperCase().indexOf("LEFT") >= 0 ? "Left" : "Right";
  const accent = HEMI[hemi] ? HEMI[hemi].lane : "#0072B2";

  // three stacked inspector panels (top->bottom): PSD, TD, LSB
  const panels = [
    { key: "psd", title: "Spectrum (PSD)", dom: [0.70, 0.92] },
    { key: "td", title: "Raw time-domain · 250 Hz", dom: [0.40, 0.62] },
    { key: "lsb", title: `Band power${chz != null ? ` @ ${fmtHz(chz)} Hz` : ""}`, dom: [0.08, 0.30] },
  ];
  // axis numbering continues after overview axes already placed on the layout
  let axN = 1;
  while (layout[axN === 1 ? "xaxis" : `xaxis${axN}`]) axN += 1;

  layout.annotations.push({
    xref: "paper", yref: "paper", x: IL, y: 0.965, xanchor: "left",
    text: selected ? `INSPECTOR — ${prettyContact((av.records.find((r) => normalizeChannel(r.channel) === selected) || {}).label || selected)}`
                   : "INSPECTOR",
    showarrow: false, font: { size: 11, color: accent, family: "Arial Black, Arial" },
  });

  panels.forEach((p) => {
    const xKey = `xaxis${axN}`, yKey = `yaxis${axN}`;
    const xref = `x${axN}`, yref = `y${axN}`;
    layout[xKey] = { domain: [IL, 1.0], anchor: yref, showgrid: false,
                     tickfont: { size: 8 }, linecolor: "#C9CCD6" };
    layout[yKey] = { domain: p.dom, anchor: xref, showgrid: false, zeroline: false,
                     tickfont: { size: 8 }, title: { text: p.title, font: { size: 9 } } };

    if (p.key === "psd" && samp && samp.psd && samp.psd.freq) {
      traces.push({ type: "scatter", mode: "lines", x: samp.psd.freq, y: samp.psd.mag,
        xaxis: xref, yaxis: yref, line: { color: fc, width: 1.4 }, fill: "tozeroy",
        fillcolor: hexA(fc, 0.12), hoverinfo: "x+y" });
      if (chz != null) layout.shapes.push({ type: "line", xref, yref,
        x0: chz, x1: chz, y0: 0, y1: 1, line: { color: C.ink, width: 0.8, dash: "dot" } });
      layout[xKey].title = { text: "Frequency (Hz)", font: { size: 9 } };
      layout[xKey].range = [0, 97];
    } else if (p.key === "td" && samp && samp.td && samp.td.sample) {
      const fs = samp.td.fs || 250;
      const tt = samp.td.sample.map((_, i) => i / fs);
      traces.push({ type: "scattergl", mode: "lines", x: tt, y: samp.td.sample,
        xaxis: xref, yaxis: yref, line: { color: fc, width: 0.6 }, hoverinfo: "x+y" });
      layout[xKey].title = { text: "Time (s)", font: { size: 9 } };
    } else if (p.key === "lsb" && samp && samp.lsb && samp.lsb.t) {
      traces.push({ type: "scattergl", mode: "lines", x: samp.lsb.t.map(toDate), y: samp.lsb.y,
        xaxis: xref, yaxis: yref, line: { color: fc, width: 1.0 }, hoverinfo: "x+y" });
      layout[xKey].type = "date";
    } else {
      layout.annotations.push({ xref: "paper", yref: "paper",
        x: (IL + 1) / 2, y: (p.dom[0] + p.dom[1]) / 2,
        text: "n.d.", showarrow: false, font: { size: 10, color: "#bbb" } });
    }
    axN += 1;
  });
}

export default function BiomarkerDataTimeline({ data, height }) {
  const ref = useRef(null);
  const av = data && data.availability ? data.availability : null;
  const [expert, setExpert] = useState(false);   // show ring/segment + montage contacts too

  // unique channels present, ordered L-then-R by contact pair. Default view shows only the main
  // bipolar sensing pairs; expert mode adds the ring/segment montage contacts.
  const { channels, nHidden } = useMemo(() => {
    if (!av || !av.records) return { channels: [], nHidden: 0 };
    // group by NORMALIZED contact-pair identity (collapses streaming+montage labels for one pair)
    const seen = new Set();
    av.records.forEach((r) => seen.add(normalizeChannel(r.channel)));
    const all = [...seen];
    const main = all.filter(isMainSensingChannel);
    const shown = (expert ? all : (main.length ? main : all))
      .sort((a, b) => channelSortKey(a) - channelSortKey(b));
    return { channels: shown, nHidden: all.length - shown.length };
  }, [av, expert]);

  const [selected, setSelected] = useState(null);
  useEffect(() => {
    // default selection: first channel that actually has a configured band power (a trend to show)
    if (!channels.length) { setSelected(null); return; }
    const withBand = channels.find((ch) =>
      (av.records || []).some((r) => normalizeChannel(r.channel) === ch && r.dtype === "bandpower" && r.meta && r.meta.center_hz != null));
    setSelected((prev) => (prev && channels.includes(prev)) ? prev : (withBand || channels[0]));
  }, [channels, av]);

  useEffect(() => {
    if (!ref.current || !av || !channels.length) return;
    const gd = ref.current;

    // match records by NORMALIZED contact-pair identity (a lane unifies a pair's products)
    const recordsFor = (ch, dtype) => (av.records || [])
      .filter((r) => normalizeChannel(r.channel) === ch && r.dtype === dtype);
    const labelFor = (ch) => {
      const r = (av.records || []).find((x) => normalizeChannel(x.channel) === ch);
      return r ? (r.label || ch) : ch;
    };
    const centerHzOf = (ch) => {
      const bp = (av.records || []).find((r) => normalizeChannel(r.channel) === ch
        && r.dtype === "bandpower" && r.meta && r.meta.center_hz != null);
      return bp ? bp.meta.center_hz : null;
    };

    // ---- layout geometry: N channel lanes + pain + stim, shared x ---------------------------
    const nLane = channels.length;
    const LANE_H = 0.46, PAIN_H = 0.62, STIM_H = 0.34, GAP = 0.16;
    const units = [];
    channels.forEach((ch) => units.push({ kind: "lane", ch, h: LANE_H }));
    units.push({ kind: "pain", h: PAIN_H });
    units.push({ kind: "stim", h: STIM_H });
    const totalH = units.reduce((s, u) => s + u.h, 0) + GAP * (units.length - 1);

    // overview occupies left ~74%, inspector right ~26%
    const OV_R = 0.72;
    const domains = [];
    let acc = 1.0;
    units.forEach((u) => {
      const top = acc, bot = acc - u.h / totalH;
      domains.push([Math.max(0, bot), top]);
      acc = bot - GAP / totalH;
    });

    const traces = [];
    const layout = {
      height: height || Math.max(420, 64 * nLane + 200),
      margin: { l: 96, r: 14, t: 64, b: 44 },
      showlegend: false,
      hovermode: "closest",
      plot_bgcolor: "#ffffff", paper_bgcolor: "#ffffff",
      font: { family: "Arial, Helvetica, sans-serif", size: 11, color: C.ink },
      shapes: [], annotations: [],
      title: {
        text: "Biomarker Data Timeline — Percept RC sensing overview",
        x: 0.005, xanchor: "left", font: { size: 15 },
      },
    };

    const xSpan = (av.span && av.span.length === 2)
      ? [toDate(av.span[0]), toDate(av.span[1])]
      : undefined;

    // ---- per-channel overview lanes ----------------------------------------------------------
    units.forEach((u, i) => {
      const axN = i + 1;
      const xaxisKey = axN === 1 ? "xaxis" : `xaxis${axN}`;
      const yaxisKey = axN === 1 ? "yaxis" : `yaxis${axN}`;
      const xref = axN === 1 ? "x" : `x${axN}`;
      const yref = axN === 1 ? "y" : `y${axN}`;
      layout[xaxisKey] = {
        domain: [0, OV_R], anchor: yref,
        type: "date", showgrid: true, gridcolor: "#EEF1F4",
        range: xSpan, matches: axN === 1 ? undefined : "x",
        showticklabels: i === units.length - 1,
        tickfont: { size: 9 }, linecolor: "#C9CCD6",
      };
      layout[yaxisKey] = {
        domain: domains[i], anchor: xref,
        showgrid: false, zeroline: false,
      };

      if (u.kind === "lane") {
        const ch = u.ch;
        const hemi = ch.toUpperCase().indexOf("LEFT") >= 0 ? "Left" : "Right";
        const hc = HEMI[hemi];
        const sel = ch === selected;
        const chz = centerHzOf(ch);
        const fc = chz != null ? freqColor(chz) : "#BDBDBD";
        layout[yaxisKey].range = [0, 1];
        layout[yaxisKey].showticklabels = false;

        if (sel) {
          layout.shapes.push({
            type: "rect", xref: "paper", yref, x0: 0, x1: OV_R,
            y0: 0, y1: 1, fillcolor: hc.sel, line: { width: 0 }, layer: "below",
          });
        }

        // (1) TD coverage blocks
        recordsFor(ch, "timedomain").forEach((r) => {
          const x0 = toDate(r.t_start);
          const x1 = toDate(r.t_start + Math.max(r.dur_s, 60));
          layout.shapes.push({
            type: "rect", xref, yref, x0, x1, y0: 0.04, y1: 0.30,
            fillcolor: C.td, opacity: 0.85, line: { width: 0 }, layer: "above",
          });
        });

        // (2) band-power LSB inline trend, colored by sensing freq (categorical)
        const bp = recordsFor(ch, "bandpower")
          .slice().sort((a, b) => a.t_start - b.t_start);
        if (bp.length) {
          // one marker per bandpower recording at its start, scaled into the lane mid-band
          const xs = bp.map((r) => toDate(r.t_start));
          const ys = bp.map((r) => (r.meta && Number.isFinite(r.meta.n) ? r.meta.n : 1));
          const ymin = Math.min(...ys), ymax = Math.max(...ys);
          const norm = ys.map((v) => 0.34 + (ymax > ymin ? (v - ymin) / (ymax - ymin) : 0.5) * 0.58);
          traces.push({
            type: "scattergl", mode: "lines+markers", x: xs, y: norm,
            xaxis: xref, yaxis: yref,
            line: { color: fc, width: 2.4 }, marker: { color: fc, size: 4 },
            hovertemplate: `${prettyContact(labelFor(ch))} band power<br>%{x}<br>@ ${fmtHz(chz)} Hz<extra></extra>`,
          });
          // left-edge categorical swatch + luminance-aware Hz label
          layout.shapes.push({
            type: "rect", xref: "paper", yref, x0: -0.014, x1: -0.004,
            y0: 0, y1: 1, fillcolor: fc, line: { color: C.ink, width: 0.4 }, layer: "above",
          });
          layout.annotations.push({
            xref: "paper", yref, x: -0.009, y: 0.5, text: `${fmtHz(chz)} Hz`,
            showarrow: false, textangle: -90, font: { size: 8, color: textOn(fc) },
          });
        } else {
          layout.annotations.push({
            xref: "paper", yref, x: OV_R / 2, y: 0.55, text: "no band power configured · n.d.",
            showarrow: false, font: { size: 9, color: "#8a8a8a" },
          });
        }

        // (3) PSD ticks (shared sensing-freq color when configured, else ink)
        const psd = recordsFor(ch, "psd");
        if (psd.length) {
          traces.push({
            type: "scattergl", mode: "markers",
            x: psd.map((r) => toDate(r.t_start)),
            y: psd.map(() => 0.95),
            xaxis: xref, yaxis: yref,
            marker: { color: chz != null ? fc : C.ink, size: 6, symbol: "line-ns-open",
                      line: { width: 1.4, color: chz != null ? fc : C.ink } },
            customdata: psd.map((r) => r.product),
            hovertemplate: `PSD snapshot<br>%{x}<br>%{customdata}<extra></extra>`,
          });
        }

        // lane label (channel) — clickable target handled by relayout/click below
        layout.annotations.push({
          xref: "paper", yref, x: -0.052, y: 0.5,
          text: prettyContact(labelFor(ch)),
          showarrow: false, xanchor: "right",
          font: { size: 11, color: hc.lane, family: sel ? "Arial Black, Arial" : "Arial" },
        });
      } else if (u.kind === "pain") {
        const p = av.pain || { t: [], y: [] };
        layout[yaxisKey].title = { text: `Pain (${p.metric || "PRO"})`, font: { size: 10 } };
        layout[yaxisKey].showticklabels = true;
        layout[yaxisKey].tickfont = { size: 9 };
        if (p.t && p.t.length) {
          traces.push({
            type: "scattergl", mode: "markers", x: p.t.map(toDate), y: p.y,
            xaxis: xref, yaxis: yref,
            marker: { color: C.pain, size: 5, opacity: 0.6 },
            hovertemplate: `pain %{y}<br>%{x}<extra></extra>`,
          });
        } else {
          layout.annotations.push({ xref: "paper", yref, x: OV_R / 2, y: 0.5,
            text: "no PRO data", showarrow: false, font: { size: 9, color: "#8a8a8a" } });
        }
      } else { // stim
        const s = av.stim || { t: [], y: [] };
        layout[yaxisKey].title = { text: "Stim (mA)", font: { size: 10 } };
        layout[yaxisKey].showticklabels = true;
        layout[yaxisKey].tickfont = { size: 9 };
        if (s.t && s.t.length) {
          traces.push({
            type: "scattergl", mode: "lines", x: s.t.map(toDate), y: s.y,
            xaxis: xref, yaxis: yref, line: { color: C.stim, width: 1.5, shape: "hv" },
            hovertemplate: `stim %{y} mA<br>%{x}<extra></extra>`,
          });
        } else {
          layout.annotations.push({ xref: "paper", yref, x: OV_R / 2, y: 0.5,
            text: "no stim data", showarrow: false, font: { size: 9, color: "#8a8a8a" } });
        }
      }
    });

    // ---- inspector (right column): selected channel PSD / TD / LSB ---------------------------
    buildInspector(traces, layout, OV_R, av, selected, centerHzOf, recordsFor);

    Plotly.react(gd, traces, layout, { responsive: true, displayModeBar: true,
      modeBarButtonsToRemove: ["lasso2d", "select2d"] });

    // click a lane -> select that channel for the inspector
    const onClick = (ev) => {
      if (!ev || !ev.points || !ev.points.length) return;
      const pt = ev.points[0];
      const axName = pt.data && pt.data.yaxis ? pt.data.yaxis : "y";
      const idx = axName === "y" ? 0 : parseInt(axName.slice(1), 10) - 1;
      const u = units[idx];
      if (u && u.kind === "lane") setSelected(u.ch);
    };
    gd.on("plotly_click", onClick);

    return () => {
      try { gd.removeAllListeners && gd.removeAllListeners("plotly_click"); } catch (e) { /* noop */ }
      Plotly.purge(gd);
    };
  }, [av, channels, selected, height]);

  if (!av || !channels.length) {
    return (
      <MDBox p={2} sx={{ color: "#8a8a8a", fontStyle: "italic" }}>
        No availability data — the timeline needs decoded Percept recordings for this participant.
      </MDBox>
    );
  }
  return (
    <MDBox p={1}>
      <div ref={ref} style={{ width: "100%" }} />
      <MDBox display="flex" alignItems="center" justifyContent="center" mt={1} mb={0.5} sx={{ gap: 2 }}>
        {nHidden > 0 || expert ? (
          <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer",
                          fontSize: 13, color: expert ? "#117733" : "#344767", userSelect: "none",
                          border: `1.5px solid ${expert ? "#117733" : "#C9CCD6"}`, borderRadius: 6,
                          padding: "5px 12px", background: expert ? "#F1F8F2" : "#FAFAFB" }}>
            <input type="checkbox" checked={expert} onChange={(e) => setExpert(e.target.checked)}
                   style={{ width: 15, height: 15, accentColor: "#117733", cursor: "pointer" }} />
            <b>Expert: all contacts</b>
            <span style={{ color: "#7E8794", fontWeight: 400 }}>
              {expert ? "— showing ring/segment + montage contacts"
                      : `— ${nHidden} ring/segment/montage contact${nHidden === 1 ? "" : "s"} hidden`}
            </span>
          </label>
        ) : null}
      </MDBox>
    </MDBox>
  );
}
