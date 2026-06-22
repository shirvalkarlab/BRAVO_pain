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

// ---- platform palette (ported from BiomarkerTimeline.js) --------------------------------------
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

// ---- epoch coercion: backend emits epoch floats; the older probe emitted ISO strings ----------
function tEpoch(v) {
  if (v == null) return null;
  if (typeof v === "number" && Number.isFinite(v)) return v;
  const p = Date.parse(String(v));
  return Number.isFinite(p) ? p / 1000 : null;
}
// run-length groups of equal snapped center over a time-sorted record list -> [{cen,recs}]
function freqRuns(recs) {
  const out = [];
  recs.forEach((r) => {
    const cen = snapFreq(r.meta && r.meta.center_hz);
    const last = out[out.length - 1];
    if (last && last.cen === cen) last.recs.push(r);
    else out.push({ cen, recs: [r] });
  });
  return out;
}

// hemisphere identity: saturated accent for headers, DESATURATED tint for TD coverage (so the
// saturated frequency color on the band-power trend is the only loud mark in a lane), faint band.
const HEMI2 = {
  LEFT: { col: "#5E3C99", td: "#C9BBDF", band: "rgba(94,60,153,0.05)", region: "GPi" },
  RIGHT: { col: "#117733", td: "#B4D8C2", band: "rgba(17,119,51,0.05)", region: "VIM" },
};
const PAL = { pain: "#C44E00", stim: "#7E6BB0", ink: "#1a1a1a" };
const linspace = (a, b, n) => (n <= 1 ? [a] : Array.from({ length: n }, (_, i) => a + (b - a) * i / (n - 1)));
const monthStarts = (t0, t1) => {
  const out = [];
  const d = new Date(t0 * 1000);
  d.setUTCDate(1); d.setUTCHours(0, 0, 0, 0);
  while (d.getTime() / 1000 < t1) {
    if (d.getTime() / 1000 >= t0) out.push(d.getTime() / 1000);
    d.setUTCMonth(d.getUTCMonth() + 1);
  }
  return out;
};

export default function BiomarkerDataTimeline({ data, height, painOverride }) {
  const ref = useRef(null);
  const av = data && data.availability ? data.availability : null;
  const [expert, setExpert] = useState(false);   // show ring/segment + montage contacts too

  // unique channels present, ordered L-then-R by contact pair. Default view shows only the main
  // bipolar sensing pairs; expert mode adds the ring/segment montage contacts.
  const { channels, nHidden } = useMemo(() => {
    if (!av || !av.records) return { channels: [], nHidden: 0 };
    const seen = new Set();
    av.records.forEach((r) => seen.add(normalizeChannel(r.channel)));
    const all = [...seen];
    const main = all.filter(isMainSensingChannel);
    const shown = (expert ? all : (main.length ? main : all))
      .sort((a, b) => channelSortKey(a) - channelSortKey(b));
    return { channels: shown, nHidden: all.length - shown.length };
  }, [av, expert]);

  useEffect(() => {
    if (!ref.current || !av || !channels.length) return;
    const gd = ref.current;

    const recordsFor = (ch, dtype) => (av.records || [])
      .filter((r) => normalizeChannel(r.channel) === ch && r.dtype === dtype);
    const labelFor = (ch) => {
      const r = (av.records || []).find((x) => normalizeChannel(x.channel) === ch);
      return r ? (r.label || ch) : ch;
    };
    const hemiOf = (ch) => (ch.toUpperCase().indexOf("LEFT") >= 0 ? "LEFT" : "RIGHT");
    // a lane is "committed" (long-term sensing) if it carries many configured band-power records;
    // exploratory lanes (early channel-switching) get a thinner lane and lighter label.
    const nBand = (ch) => recordsFor(ch, "bandpower")
      .filter((r) => r.meta && r.meta.center_hz != null).length;
    const committed = new Set(channels.filter((ch) => nBand(ch) >= 20));

    // ---- time span ---------------------------------------------------------------------------
    const allT = (av.records || []).map((r) => tEpoch(r.t_start)).filter((v) => v != null);
    const t0 = (av.span && av.span.length === 2) ? tEpoch(av.span[0]) : Math.min(...allT);
    const t1 = (av.span && av.span.length === 2) ? tEpoch(av.span[1]) : Math.max(...allT);
    const SPAN = Math.max(t1 - t0, 1);
    const MIN_LBL_GAP = SPAN * 0.05;            // min spacing between Hz transition labels
    const D = (e) => toDate(e);

    // ---- vertical geometry (data-coord single axis; mirrors the signed-off figure) -----------
    const GAPL = 0.28, ROWGAP = 0.62, PAIN_H = 1.6, STIM_H = 0.9, INTER_GAP = 1.0;
    const LH = (ch) => (committed.has(ch) ? 1.5 : 0.72);
    const laneTop = {}, laneBase = {};
    let y = 0.0, prev = null;
    channels.forEach((ch) => {
      const h = hemiOf(ch);
      if (prev === "LEFT" && h === "RIGHT") y -= (0.9 + GAPL) * INTER_GAP;
      laneTop[ch] = y; laneBase[ch] = y - LH(ch); y = laneBase[ch] - GAPL; prev = h;
    });
    const neuralBottom = y + GAPL;
    const painTop = neuralBottom - ROWGAP, painBase = painTop - PAIN_H;
    const stimTop = painBase - ROWGAP * 0.55, stimBase = stimTop - STIM_H;
    const FULL_TOP = 0.40;
    const yScale = (v, lo, hi, yb, yt) => yb + (yt - yb) * (v - lo) / (hi - lo + 1e-9);

    const traces = [];
    const shapes = [];
    const annotations = [];
    const X = "x", Y = "y";

    // (0) full-height month reference lines (carry through pain/stim so you can drop a plumb line)
    monthStarts(t0, t1).forEach((ms) => shapes.push({
      type: "line", xref: X, yref: Y, x0: D(ms), x1: D(ms), y0: stimBase - 0.3, y1: FULL_TOP,
      line: { color: "rgba(0,0,0,0.07)", width: 1 }, layer: "below",
    }));

    // (1) hemisphere tint bands + rotated region headers
    ["LEFT", "RIGHT"].forEach((hemi) => {
      const hl = channels.filter((ch) => hemiOf(ch) === hemi);
      if (!hl.length) return;
      const top = laneTop[hl[0]] + 0.04, bot = laneBase[hl[hl.length - 1]] - 0.04;
      shapes.push({ type: "rect", xref: "paper", yref: Y, x0: 0, x1: 1, y0: bot, y1: top,
        fillcolor: HEMI2[hemi].band, line: { width: 0 }, layer: "below" });
      annotations.push({ xref: "paper", yref: Y, x: -0.085, y: (top + bot) / 2,
        text: `<b>${hemi}</b><br>${HEMI2[hemi].region}`, showarrow: false, textangle: -90,
        font: { size: 14, color: HEMI2[hemi].col }, align: "center" });
    });
    // faint lane separators
    channels.forEach((ch) => shapes.push({ type: "line", xref: "paper", yref: Y,
      x0: 0, x1: 1, y0: laneBase[ch] - 0.02, y1: laneBase[ch] - 0.02,
      line: { color: "rgba(0,0,0,0.13)", width: 1 }, layer: "below" }));

    // ---- per-channel lane content ------------------------------------------------------------
    const present = new Set();
    channels.forEach((ch) => {
      const yb = laneBase[ch], lh = LH(ch), hemi = hemiOf(ch);
      const tdc = HEMI2[hemi].td;

      // (a) TD coverage = desaturated hemisphere color blocks
      recordsFor(ch, "timedomain").forEach((r) => {
        const ts = tEpoch(r.t_start);
        const te = ts + Math.max(r.dur_s || 0, 86400 * 1.6);
        shapes.push({ type: "rect", xref: X, yref: Y, x0: D(ts), x1: D(te),
          y0: yb + 0.04 * lh, y1: yb + 0.26 * lh, fillcolor: tdc, opacity: 0.85,
          line: { width: 0 }, layer: "above" });
      });

      // (b) band-power: ONE time-ordered trend, color changes with sensing center freq.
      const bp = recordsFor(ch, "bandpower")
        .filter((r) => r.meta && r.meta.center_hz != null)
        .slice().sort((a, b) => tEpoch(a.t_start) - tEpoch(b.t_start));
      const BP_LO = yb + 0.36 * lh, BP_HI = yb + 0.74 * lh;
      if (bp.length) {
        const n = bp.length;
        const runs = freqRuns(bp);
        runs.forEach((r) => present.add(r.cen));
        if (n === 1) {
          const cen = snapFreq(bp[0].meta.center_hz);
          traces.push({ type: "scattergl", mode: "markers", x: [D(tEpoch(bp[0].t_start))],
            y: [(BP_LO + BP_HI) / 2], line: { width: 0 },
            marker: { size: 8, color: freqColor(cen) }, hoverinfo: "skip", showlegend: false });
          annotations.push({ xref: X, yref: Y, x: D(tEpoch(bp[0].t_start)), y: BP_HI,
            text: fmtHz(cen), showarrow: false, yshift: 6,
            font: { size: 8.5, color: freqColor(cen) } });
        } else {
          // deterministic gentle wave so the trend reads as a line; magnitude shown on zoom/hover
          const wave = linspace(0, 9, n).map((v) => 0.5 + 0.42 * Math.sin(v));
          const yy = wave.map((v) => BP_LO + (BP_HI - BP_LO) * Math.min(Math.max(v, 0), 1));
          let idx = 0, lastLbl = -1e18;
          runs.forEach((run) => {
            const a = idx, b = idx + run.recs.length - 1;
            const fc = freqColor(run.cen);
            traces.push({ type: "scattergl", mode: "lines+markers",
              x: run.recs.map((r) => D(tEpoch(r.t_start))), y: yy.slice(a, b + 1),
              line: { color: fc, width: 3.0 }, marker: { size: 4, color: fc },
              hovertemplate: `${prettyContact(labelFor(ch))} · ${fmtHz(run.cen)} Hz<br>%{x}<extra></extra>`,
              showlegend: false });
            if (committed.has(ch)) {
              const ts = tEpoch(run.recs[0].t_start);
              if (ts - lastLbl >= MIN_LBL_GAP) {
                annotations.push({ xref: X, yref: Y, x: D(ts), y: yy[a], text: fmtHz(run.cen),
                  showarrow: false, yshift: 10, font: { size: 9, color: fc } });
                lastLbl = ts;
              }
            }
            if (b + 1 < n) {  // connect runs so the trend stays continuous (next color)
              traces.push({ type: "scattergl", mode: "lines",
                x: [D(tEpoch(bp[b].t_start)), D(tEpoch(bp[b + 1].t_start))], y: [yy[b], yy[b + 1]],
                line: { color: freqColor(snapFreq(bp[b + 1].meta.center_hz)), width: 3.0 },
                hoverinfo: "skip", showlegend: false });
            }
            idx += run.recs.length;
          });
        }
        if (committed.has(ch)) annotations.push({ xref: "paper", yref: Y, x: -0.004,
          y: (BP_LO + BP_HI) / 2, text: "<span style='font-size:8px;color:#aaa'>LSB</span>",
          showarrow: false, xanchor: "right" });
      } else {
        annotations.push({ xref: "paper", yref: Y, x: 0.5, y: yb + 0.5 * lh,
          text: "no band power configured · n.d.", showarrow: false,
          font: { size: 9.5, color: "#9AA0A6" } });
      }

      // (c) PSD ticks — demoted to mid-gray, short
      const psd = recordsFor(ch, "psd");
      if (psd.length) traces.push({ type: "scattergl", mode: "markers",
        x: psd.map((r) => D(tEpoch(r.t_start))), y: psd.map(() => yb + 0.93 * lh),
        marker: { symbol: "line-ns-open", size: 7, color: "#9AA0A6", line: { width: 1.2 } },
        customdata: psd.map((r) => r.product),
        hovertemplate: `PSD snapshot<br>%{x}<br>%{customdata}<extra></extra>`, showlegend: false });

      // (d) lane label — bold for committed, lighter for exploratory
      annotations.push({ xref: "paper", yref: Y, x: -0.018, y: yb + 0.5 * lh,
        text: committed.has(ch) ? `<b>${prettyContact(labelFor(ch))}</b>` : prettyContact(labelFor(ch)),
        showarrow: false, xanchor: "right",
        font: { size: 15, color: committed.has(ch) ? PAL.ink : "#888" } });
    });

    // ---- pain row: dots + medium-alpha overlay line, with y-axis ticks -----------------------
    const pain = (painOverride && painOverride.t && painOverride.t.length)
      ? painOverride : (av.pain || { t: [], y: [], metric: "PRO" });
    shapes.push({ type: "line", xref: "paper", yref: Y, x0: 0, x1: 1,
      y0: painTop + 0.16, y1: painTop + 0.16, line: { color: "#e0e0e0", width: 1 } });
    if (pain.t && pain.t.length) {
      const py = pain.y.map((v) => yScale(v, 0, 10, painBase, painTop));
      traces.push({ type: "scattergl", mode: "lines", x: pain.t.map(D), y: py,
        line: { color: PAL.pain, width: 2.4 }, opacity: 0.45, hoverinfo: "skip", showlegend: false });
      traces.push({ type: "scattergl", mode: "markers", x: pain.t.map(D), y: py,
        marker: { size: 5, color: PAL.pain }, opacity: 0.6,
        hovertemplate: `${pain.metric || "pain"} %{customdata}<br>%{x}<extra></extra>`,
        customdata: pain.y, showlegend: false });
    } else {
      annotations.push({ xref: "paper", yref: Y, x: 0.5, y: (painBase + painTop) / 2,
        text: "no PRO data", showarrow: false, font: { size: 9.5, color: "#9AA0A6" } });
    }
    annotations.push({ xref: "paper", yref: Y, x: -0.018, y: (painBase + painTop) / 2,
      text: "<b>PAIN</b>", showarrow: false, xanchor: "right",
      font: { size: 13, color: PAL.pain } });
    [0, 5, 10].forEach((val) => annotations.push({ xref: "paper", yref: Y, x: -0.004,
      y: yScale(val, 0, 10, painBase, painTop), text: String(val), showarrow: false,
      xanchor: "right", font: { size: 9.5, color: "#888" } }));

    // ---- thin separator between pain and stim, then stim step with y-axis --------------------
    shapes.push({ type: "line", xref: "paper", yref: Y, x0: 0, x1: 1,
      y0: (painBase + stimTop) / 2, y1: (painBase + stimTop) / 2,
      line: { color: "#cfcfcf", width: 1 } });
    const stim = av.stim || { t: [], y: [] };
    const SMAX = stim.y && stim.y.length ? Math.max(3, Math.ceil(Math.max(...stim.y))) : 3;
    if (stim.t && stim.t.length) {
      traces.push({ type: "scattergl", mode: "lines", x: stim.t.map(D),
        y: stim.y.map((v) => yScale(v, 0, SMAX, stimBase, stimTop)),
        line: { color: PAL.stim, width: 1.8, shape: "hv" },
        hovertemplate: `stim %{customdata} mA<br>%{x}<extra></extra>`, customdata: stim.y,
        showlegend: false });
    } else {
      annotations.push({ xref: "paper", yref: Y, x: 0.5, y: (stimBase + stimTop) / 2,
        text: "no stim data", showarrow: false, font: { size: 9.5, color: "#9AA0A6" } });
    }
    annotations.push({ xref: "paper", yref: Y, x: -0.018, y: (stimBase + stimTop) / 2,
      text: "<b>STIM</b>", showarrow: false, xanchor: "right",
      font: { size: 13, color: PAL.stim } });
    [0, SMAX].forEach((val) => annotations.push({ xref: "paper", yref: Y, x: -0.004,
      y: yScale(val, 0, SMAX, stimBase, stimTop), text: String(val), showarrow: false,
      xanchor: "right", font: { size: 9.5, color: "#888" } }));
    annotations.push({ xref: "paper", yref: Y, x: -0.018, y: stimBase - 0.30,
      text: "<span style='font-size:9px;color:#999'>mA</span>", showarrow: false, xanchor: "right" });

    // ---- glyph key (top, near title) via dummy legend traces ---------------------------------
    traces.push({ x: [null], y: [null], mode: "markers", type: "scatter",
      marker: { symbol: "square", size: 12, color: "#C9BBDF" },
      name: "raw TD coverage  (zoom → waveform)" });
    traces.push({ x: [null], y: [null], mode: "lines+markers", type: "scatter",
      line: { color: "#009E73", width: 3 }, marker: { size: 5, color: "#009E73" },
      name: "band-power (LSB) · color = sensing Hz" });
    traces.push({ x: [null], y: [null], mode: "markers", type: "scatter",
      marker: { symbol: "line-ns-open", size: 10, color: "#9AA0A6", line: { width: 1.4 } },
      name: "PSD snapshot  (hover → spectrum)" });

    // ---- right-side frequency legend: only realized centers ----------------------------------
    const pcs = [...present].filter((c) => c != null).sort((a, b) => a - b);
    annotations.push({ xref: "paper", yref: "paper", x: 1.015, y: 0.90,
      text: "<b>Sensing center (Hz)</b>", showarrow: false, xanchor: "left",
      font: { size: 11, color: "#333" } });
    pcs.forEach((cen, i) => {
      const yy = 0.855 - i * 0.046;
      shapes.push({ type: "rect", xref: "paper", yref: "paper", x0: 1.015, x1: 1.033,
        y0: yy - 0.014, y1: yy + 0.014, fillcolor: freqColor(cen), line: { color: "#fff", width: 0.5 } });
      annotations.push({ xref: "paper", yref: "paper", x: 1.039, y: yy, text: fmtHz(cen),
        showarrow: false, xanchor: "left", font: { size: 10.5, color: "#333" } });
    });

    // ---- provenance subtitle -----------------------------------------------------------------
    const fmtDate = (e) => new Date(e * 1000).toLocaleDateString("en-US",
      { month: "short", day: "2-digit", year: "numeric", timeZone: "UTC" });
    const subj = (data && data.participant_label) || (av && av.participant) || "";
    const sub = `${subj ? subj + " · " : ""}Percept RC · ${fmtDate(t0)} – ${fmtDate(t1)}`;

    const layout = {
      height: height || Math.max(560, 150 * channels.length + 320),
      margin: { l: 140, r: 120, t: 128, b: 46 },
      hovermode: "closest",
      plot_bgcolor: "#ffffff", paper_bgcolor: "#ffffff",
      font: { family: "Arial, Helvetica, sans-serif", size: 11, color: PAL.ink },
      shapes, annotations,
      showlegend: true,
      legend: { orientation: "h", x: 0.31, xanchor: "left", y: 1.075, yanchor: "top",
                font: { size: 11.5 }, bgcolor: "rgba(255,255,255,0)" },
      title: { text: `<b>Biomarker Data Timeline</b><br><span style="font-size:13px;color:#777">${sub}</span>`,
               x: 0.012, xanchor: "left", y: 0.965, font: { size: 26, color: "#1a1a1a" } },
      xaxis: { range: [D(t0), D(t1)], type: "date", showgrid: false, dtick: "M1",
               tickfont: { size: 11.5 }, ticks: "outside", ticklen: 4, tickcolor: "#ccc" },
      yaxis: { visible: false, range: [stimBase - 0.5, FULL_TOP], fixedrange: true },
    };

    Plotly.react(gd, traces, layout, { responsive: true, displayModeBar: true,
      modeBarButtonsToRemove: ["lasso2d", "select2d"] });

    return () => { Plotly.purge(gd); };
  }, [av, channels, height, painOverride, data]);

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
