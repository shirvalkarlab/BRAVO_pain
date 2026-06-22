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

import { useEffect, useMemo, useRef } from "react";
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
  // SEGMENT montages (e.g. ONE_A_AND_TWO_A) are a distinct sensing geometry — keep their full
  // identity. RING pairs are NOT distinct: a full-ring 0-3 sensing config IS the standard 0-3
  // bipolar, so collapse it onto the canonical contact-pair lane instead of drawing a duplicate.
  if (up.indexOf("SEGMENT") >= 0) return up;
  const hemi = up.indexOf("LEFT") >= 0 ? "LEFT" : (up.indexOf("RIGHT") >= 0 ? "RIGHT" : "");
  const nums = (up.match(/ZERO|ONE|TWO|THREE/g) || []).map((w) => _WORDNUM[w]);
  // Only collapse a genuine two-DISTINCT-contact pair (0≠3); a same-number pair is degenerate and
  // is dropped upstream, never normalized to a real lane.
  if (nums.length >= 2 && hemi && nums[0] !== nums[1]) {
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
// The ONLY lanes shown are the main bipolar SENSING pairs (0-3, 1-3, 0-2 per hemisphere). The
// Percept also exposes many ring/segment montage contacts (…_RING, …_SEGMENT) and adjacent montage
// pairs; these are not used for biomarker discovery and are dropped entirely. A channel is a main
// sensing pair if it names a 2-contact pair and is NOT a ring/segment.
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
// hemisphere identity: saturated accent for headers, DESATURATED tint for TD coverage (so the
// saturated frequency color on the band-power trend is the only loud mark in a lane), faint band.
const HEMI2 = {
  LEFT: { col: "#5E3C99", td: "#C9BBDF", band: "rgba(94,60,153,0.05)", region: "GPi" },
  RIGHT: { col: "#117733", td: "#B4D8C2", band: "rgba(17,119,51,0.05)", region: "VIM" },
};
const PAL = { pain: "#C44E00", stim: "#7E6BB0", ink: "#1a1a1a" };

// Categorical colors for PATIENT-EVENT labels (Higher Pain / Tingly-Burning / Feeling Good / …).
// Pain-type labels lean red/orange; relief/medication lean blue/green; others fall through to a
// colorblind-aware cycle. Keyed by a normalized (lowercased) label so minor spelling variants pool.
const EVENT_COLORS = {
  "higher pain": "#D62728", "high pain": "#B2182B", "lower pain": "#F4A582",
  "tingly/burning": "#CC79A7", "dyskinesia": "#882255", "feeling off": "#E69F00",
  "feeling good": "#1B7837", "medication": "#2166AC", "took medication": "#4393C3",
  "percocet": "#56B4E9",
};
const EVENT_FALLBACK = ["#332288", "#0072B2", "#009E73", "#94C973", "#44AA99", "#999933"];
function eventColor(label, idx) {
  const k = String(label || "").trim().toLowerCase();
  if (EVENT_COLORS[k]) return EVENT_COLORS[k];
  return EVENT_FALLBACK[idx % EVENT_FALLBACK.length];
}
// Pain y-axis range BY METRIC: NRS 0-10, MPQ ~0-50, VAS family 0-100, composite by its own range.
// Returns [lo, hi, ticks[]] so the pain row's scale adapts to whichever PRO the picker shows.
function painAxis(metric, yvals) {
  const m = String(metric || "").toLowerCase();
  if (m === "nrs") return [0, 10, [0, 5, 10]];
  if (m.indexOf("mpq") >= 0 && m.indexOf("composite") < 0) return [0, 50, [0, 25, 50]];
  if (m.indexOf("vas") >= 0) return [0, 100, [0, 50, 100]];
  // composite / unknown -> span the data (rounded), guard empty
  const ys = (yvals || []).filter((v) => Number.isFinite(v));
  if (!ys.length) return [0, 10, [0, 5, 10]];
  const hi = Math.ceil(Math.max(...ys, 1));
  const lo = Math.min(0, Math.floor(Math.min(...ys)));
  return [lo, hi, [lo, Math.round((lo + hi) / 2), hi]];
}

export default function BiomarkerDataTimeline({ data, height, painOverride }) {
  const ref = useRef(null);
  const av = data && data.availability ? data.availability : null;
  // Unique channels present, ordered L-then-R by contact pair. Only the main bipolar SENSING pairs
  // (0-3, 1-3, 0-2 per hemisphere) are shown: ring/segment montage contacts are not used for
  // biomarker discovery and are dropped entirely (no expert view). RING variants of a standard pair
  // collapse onto that pair's lane via normalizeChannel; true segment/ring montages are filtered.
  const { channels } = useMemo(() => {
    if (!av || !av.records) return { channels: [] };
    const seen = new Set();
    av.records.forEach((r) => seen.add(normalizeChannel(r.channel)));
    const main = [...seen]
      .filter(isMainSensingChannel)
      .sort((a, b) => channelSortKey(a) - channelSortKey(b));
    return { channels: main };
  }, [av]);

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
    // COMPACT LSB overview for a lane: av.lsb_overview is keyed by RAW channel; collapse to this
    // normalized pair and merge any raw keys that map to it. The overview is render-cheap geometry
    // (a decimated chronic LINE + one BLOCK per streaming session) so the page stays responsive
    // while zooming — vs tens of thousands of 2 Hz points. Returns:
    //   { chronic:{t:[],y:[],center_hz:[]}|null, sessions:[{t0,t1,med,lo,hi,center_hz,n}],
    //     y_lo, y_hi } | null
    const lsbFor = (ch) => {
      const ov = av.lsb_overview || {};
      const keys = Object.keys(ov).filter((k) => normalizeChannel(k) === ch);
      if (!keys.length) return null;
      const chronicT = [], chronicY = [], chronicHz = [], sessions = [];
      let yLo = Infinity, yHi = -Infinity;
      keys.forEach((k) => {
        const d = ov[k] || {};
        if (d.chronic && d.chronic.t && d.chronic.t.length) {
          const ch_hz = d.chronic.center_hz || [];
          (d.chronic.t).forEach((tt, i) => {
            chronicT.push(tt); chronicY.push(d.chronic.y[i]);
            chronicHz.push(ch_hz[i] == null ? null : ch_hz[i]);
          });
        }
        (d.sessions || []).forEach((s) => sessions.push(s));
        if (Number.isFinite(d.y_lo)) yLo = Math.min(yLo, d.y_lo);
        if (Number.isFinite(d.y_hi)) yHi = Math.max(yHi, d.y_hi);
      });
      if (!chronicT.length && !sessions.length) return null;
      // time-sort chronic samples (merged keys may interleave); carry center_hz with the reorder
      // so the chronic line can be colored by its (time-varying) sensing center frequency.
      let chronic = null;
      if (chronicT.length) {
        const ord = chronicT.map((_, i) => i).sort((a, b) => chronicT[a] - chronicT[b]);
        chronic = { t: ord.map((i) => chronicT[i]), y: ord.map((i) => chronicY[i]),
                    center_hz: ord.map((i) => chronicHz[i]) };
      }
      sessions.sort((a, b) => a.t0 - b.t0);
      return { chronic, sessions,
               y_lo: Number.isFinite(yLo) ? yLo : 0, y_hi: Number.isFinite(yHi) ? yHi : 1 };
    };
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
    // EVENT strip: a thin row between the neural lanes and the pain row where patient-triggered
    // snapshot events (button-press 30 s PSDs) are demarcated as diamonds, with a faint drop-line
    // up through the neural lanes so each press is locatable against every channel.
    const EVENT_H = 0.5;
    const eventTop = neuralBottom - ROWGAP * 0.5, eventBase = eventTop - EVENT_H;
    const eventY = (eventTop + eventBase) / 2;
    const painTop = eventBase - ROWGAP * 0.55, painBase = painTop - PAIN_H;
    const stimTop = painBase - ROWGAP * 0.55, stimBase = stimTop - STIM_H;
    const FULL_TOP = 0.40;
    const yScale = (v, lo, hi, yb, yt) => yb + (yt - yb) * (v - lo) / (hi - lo + 1e-9);

    const traces = [];
    const shapes = [];
    const annotations = [];
    const X = "x", Y = "y";

    // (0) vertical time gridlines are drawn by the x-axis itself (showgrid below), NOT as fixed
    // shapes — so they auto-densify on zoom (month -> week -> day -> hour) and span the whole
    // single y-axis (all neural lanes + pain + stim). See the xaxis config in `layout`.

    // (1) hemisphere tint bands + rotated region headers
    ["LEFT", "RIGHT"].forEach((hemi) => {
      const hl = channels.filter((ch) => hemiOf(ch) === hemi);
      if (!hl.length) return;
      const top = laneTop[hl[0]] + 0.04, bot = laneBase[hl[hl.length - 1]] - 0.04;
      shapes.push({ type: "rect", xref: "paper", yref: Y, x0: 0, x1: 1, y0: bot, y1: top,
        fillcolor: HEMI2[hemi].band, line: { width: 0 }, layer: "below" });
      // Hemisphere/region label pinned to the far LEFT BORDER (rotated 90°), clear of the
      // right-anchored per-contact names (at x ≈ -0.018) which it used to overlap.
      annotations.push({ xref: "paper", yref: Y, x: -0.135, y: (top + bot) / 2,
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

      // (b) band-power: the REAL LSB, drawn as RENDER-CHEAP geometry (av.lsb_overview) so the page
      // stays fast while zooming. Two layers carry the same information as the raw 2 Hz cloud:
      //   - chronic  -> ONE grey line of the real ~10-min around-the-clock trend
      //   - streaming-> ONE thick colored BLOCK per recording session, at that session's median LSB
      //                 (color = sensing center freq; hover shows median/range/n/freq). Sessions are
      //                 grouped into one trace PER frequency, so a lane is ~13 traces, not 50k points.
      // Both layers share the lane's robust magnitude window so the mini LSB axis is consistent.
      const ov = lsbFor(ch);
      const BP_LO = yb + 0.34 * lh, BP_HI = yb + 0.76 * lh;
      if (ov) {
        const lo = ov.y_lo, hi = ov.y_hi;
        const sc = (v) => BP_LO + (BP_HI - BP_LO) * Math.min(Math.max((v - lo) / (hi - lo + 1e-9), 0), 1);
        // chronic real line — colored by sensing CENTER FREQUENCY (which changes over the implant
        // as the chronic 24/7 sensing band is reprogrammed). Split the decimated polyline into
        // contiguous same-frequency runs and draw each run in its band color (categorical
        // FREQ_PALETTE, same as streaming), so the chronic trend visibly recolors at each
        // re-config and the hover reports the band. Falls back to grey for samples with no freq.
        if (ov.chronic && ov.chronic.t.length) {
          const ct = ov.chronic.t, cy = ov.chronic.y;
          const cc = ov.chronic.center_hz || [];
          const snapAt = (i) => (cc[i] == null ? null : snapFreq(cc[i]));
          let seg = 0;
          for (let k = 1; k <= ct.length; k += 1) {
            const brk = (k === ct.length) || (snapAt(k) !== snapAt(seg));
            if (!brk) continue;
            // run [seg, k); include the boundary point so adjacent runs join visually
            const end = Math.min(k + 1, ct.length);
            const c = snapAt(seg);
            if (c != null) present.add(c);
            const fc = c == null ? "rgba(90,90,90,0.55)" : freqColor(c);
            const xs = ct.slice(seg, end), ys = cy.slice(seg, end);
            traces.push({ type: "scattergl", mode: "lines",
              x: xs.map(D), y: ys.map(sc),
              line: { color: fc, width: 1.4 },
              customdata: ys.map((v) => [Math.round(v), c == null ? "?" : fmtHz(c)]),
              hovertemplate: `${prettyContact(labelFor(ch))} · chronic 24/7 · %{customdata[1]} Hz<br>`
                + `%{customdata[0]} LSB<br>%{x}<extra></extra>`,
              showlegend: false });
            seg = k;
          }
        }
        // streaming sessions: one BLOCK (median bar + 10-90 whisker) per recording, batched by freq
        if (ov.sessions.length) {
          const byFreq = {};
          ov.sessions.forEach((s) => {
            const c = snapFreq(s.center_hz);
            if (c != null) present.add(c);
            const key = c == null ? "na" : String(c);
            (byFreq[key] = byFreq[key] || []).push(s);
          });
          Object.keys(byFreq).forEach((key) => {
            const ss = byFreq[key];
            const c = key === "na" ? null : Number(key);
            const fc = freqColor(c);
            const bx = [], by = [], wx = [], wy = [], cd = [];
            ss.forEach((s) => {
              const x0 = D(s.t0), x1 = D(Math.max(s.t1, s.t0 + 86400 * 1.2)); // min visible width
              const ym = sc(s.med);
              // thick median bar as a 2-point horizontal segment (cheap vs filled rect per session)
              bx.push(x0, x1, null); by.push(ym, ym, null);
              // 10-90 whisker at session midpoint
              const xm = D((s.t0 + s.t1) / 2);
              wx.push(xm, xm, null); wy.push(sc(s.lo), sc(s.hi), null);
              cd.push([Math.round(s.med), Math.round(s.lo), Math.round(s.hi), fmtHz(c), s.n]);
            });
            // whiskers (thin, same color, no hover)
            traces.push({ type: "scattergl", mode: "lines", x: wx, y: wy,
              line: { color: fc, width: 1 }, opacity: 0.5, hoverinfo: "skip", showlegend: false });
            // median bars (thick) — hover carries the session summary
            traces.push({ type: "scattergl", mode: "lines", x: bx, y: by,
              line: { color: fc, width: committed.has(ch) ? 5 : 6 },
              hoverinfo: "skip", showlegend: false });
            // invisible hover anchors at each session median (one marker per session, tiny count)
            traces.push({ type: "scattergl", mode: "markers",
              x: ss.map((s) => D((s.t0 + s.t1) / 2)), y: ss.map((s) => sc(s.med)),
              marker: { size: 10, color: "rgba(0,0,0,0)" }, customdata: cd,
              hovertemplate: `${prettyContact(labelFor(ch))} · ${key === "na" ? "?" : fmtHz(c)} Hz<br>`
                + `median %{customdata[0]} LSB (10-90: %{customdata[1]}–%{customdata[2]})<br>`
                + `n=%{customdata[4]} samples<extra></extra>`,
              showlegend: false });
          });
        }
        // Hz labels at each sensing-frequency transition across sessions (committed lanes)
        if (committed.has(ch) && ov.sessions.length) {
          let lastLbl = -1e18, lastCen = null;
          ov.sessions.forEach((s) => {
            const c = snapFreq(s.center_hz);
            if (c !== lastCen && c != null && (s.t0 - lastLbl) >= MIN_LBL_GAP) {
              annotations.push({ xref: X, yref: Y, x: D(s.t0), y: BP_HI, text: fmtHz(c),
                showarrow: false, yshift: 8, font: { size: 9, color: freqColor(c) } });
              lastLbl = s.t0;
            }
            if (c != null) lastCen = c;
          });
        }
        // real LSB mini-axis: low/high tick on the left edge so magnitude is legible
        if (committed.has(ch)) {
          annotations.push({ xref: "paper", yref: Y, x: -0.004, y: BP_HI, text: `${Math.round(hi)}`,
            showarrow: false, xanchor: "right", font: { size: 8, color: "#aaa" } });
          annotations.push({ xref: "paper", yref: Y, x: -0.004, y: BP_LO, text: `${Math.round(lo)}`,
            showarrow: false, xanchor: "right", font: { size: 8, color: "#aaa" } });
          annotations.push({ xref: "paper", yref: Y, x: -0.004, y: (BP_LO + BP_HI) / 2,
            text: "<span style='font-size:7.5px;color:#bbb'>LSB</span>", showarrow: false, xanchor: "right" });
        }
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

    // ---- EVENT row: PATIENT-ANNOTATED events (labeled button presses) ------------------------
    // One diamond per event at its time, COLORED BY LABEL (Higher Pain / Tingly-Burning / Feeling
    // Good / Medication / …), plus a faint drop-line up through the neural lanes so the flagged
    // moment is locatable against every channel. Hover LEADS with the patient's label, then time,
    // peak Hz, and channel count. These corroborate only (DESIGN §2/§6) — never decode.
    const evWrap = av.events || { events: [] };
    const evList = (evWrap.events || []).filter((e) => e && Number.isFinite(e.t));
    if (evList.length) {
      // stable label order (by first appearance) so colors + legend are deterministic
      const labelOrder = [];
      evList.forEach((e) => { const l = e.label || "event"; if (!labelOrder.includes(l)) labelOrder.push(l); });
      const colorOf = (label) => eventColor(label, labelOrder.indexOf(label));
      // faint drop-lines spanning the neural region, tinted by the event's label color
      evList.forEach((e) => shapes.push({ type: "line", xref: X, yref: Y,
        x0: D(e.t), x1: D(e.t), y0: eventY, y1: neuralBottom + 0.02,
        line: { color: colorOf(e.label || "event"), width: 0.8 }, opacity: 0.22, layer: "below" }));
      // one marker trace per label (so each is a legend entry and shares a color)
      labelOrder.forEach((label) => {
        const grp = evList.filter((e) => (e.label || "event") === label);
        traces.push({ type: "scattergl", mode: "markers",
          x: grp.map((e) => D(e.t)), y: grp.map(() => eventY),
          marker: { symbol: "diamond", size: 8, color: colorOf(label),
                    line: { color: "rgba(0,0,0,0.45)", width: 0.6 } },
          customdata: grp.map((e) => [
            label,
            e.peak_hz == null ? "n/a" : fmtHz(e.peak_hz),
            e.n_chan == null ? "?" : e.n_chan]),
          hovertemplate: "<b>%{customdata[0]}</b><br>%{x}<br>"
            + "peak %{customdata[1]} Hz · %{customdata[2]} ch<extra></extra>",
          name: label, showlegend: false });
      });
    } else {
      annotations.push({ xref: "paper", yref: Y, x: 0.5, y: eventY,
        text: "no patient events", showarrow: false, font: { size: 9, color: "#C2A0A0" } });
    }
    annotations.push({ xref: "paper", yref: Y, x: -0.018, y: eventY,
      text: `<b>EVENTS</b>${evList.length ? `<br><span style="font-size:8px;color:#999">${evList.length} presses</span>` : ""}`,
      showarrow: false, xanchor: "right", font: { size: 12, color: "#555" } });

    // ---- montage-PSD events: NeuralActivitySnapshot montage sweeps NOT already shown as a
    // montage/survey PSD recording (de-duplicated server-side). Rendered as small grey ticks along
    // the BOTTOM of the event strip so they read as "extra montage spectra captured here" without
    // competing with the colored patient-annotation diamonds above them.
    const mWrap = av.montage_events || { events: [] };
    const mList = (mWrap.events || []).filter((e) => e && Number.isFinite(e.t));
    if (mList.length) {
      traces.push({ type: "scattergl", mode: "markers",
        x: mList.map((e) => D(e.t)), y: mList.map(() => eventBase + 0.06),
        marker: { symbol: "line-ns-open", size: 7, color: "#9AA0A6", line: { width: 1.2 } },
        customdata: mList.map((e) => [
          e.peak_hz == null ? "n/a" : fmtHz(e.peak_hz),
          e.n_chan == null ? "?" : e.n_chan]),
        hovertemplate: "montage PSD · %{x}<br>peak %{customdata[0]} Hz · %{customdata[1]} ch<extra></extra>",
        name: "montage PSD", showlegend: false });
    }

    // ---- pain row: dots + medium-alpha overlay line, with y-axis ticks -----------------------
    const pain = (painOverride && painOverride.t && painOverride.t.length)
      ? painOverride : (av.pain || { t: [], y: [], metric: "PRO" });
    const [pLo, pHi, pTicks] = painAxis(pain.metric, pain.y);
    shapes.push({ type: "line", xref: "paper", yref: Y, x0: 0, x1: 1,
      y0: painTop + 0.16, y1: painTop + 0.16, line: { color: "#e0e0e0", width: 1 } });
    if (pain.t && pain.t.length) {
      const py = pain.y.map((v) => yScale(v, pLo, pHi, painBase, painTop));
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
      text: `<b>PAIN</b><br><span style="font-size:8px;color:#999">${pain.metric || ""}</span>`,
      showarrow: false, xanchor: "right", font: { size: 13, color: PAL.pain } });
    pTicks.forEach((val) => annotations.push({ xref: "paper", yref: Y, x: -0.004,
      y: yScale(val, pLo, pHi, painBase, painTop), text: String(val), showarrow: false,
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
    traces.push({ x: [null], y: [null], mode: "lines", type: "scatter",
      line: { color: "#009E73", width: 2 },
      name: "chronic LSB · 24/7 trend · color = sensing Hz" });
    traces.push({ x: [null], y: [null], mode: "lines", type: "scatter",
      line: { color: "#009E73", width: 6 },
      name: "streaming LSB session · color = sensing Hz (hover → detail)" });
    traces.push({ x: [null], y: [null], mode: "markers", type: "scatter",
      marker: { symbol: "line-ns-open", size: 10, color: "#9AA0A6", line: { width: 1.4 } },
      name: "montage PSD  (survey sweep + extra snapshots; hover → spectrum)" });
    // Patient-event diamonds get their own per-label legend entries (added in the EVENT row above),
    // so no generic event glyph is needed here.

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
      margin: { l: 170, r: 120, t: 170, b: 46 },
      hovermode: "closest",
      plot_bgcolor: "#ffffff", paper_bgcolor: "#ffffff",
      font: { family: "Arial, Helvetica, sans-serif", size: 11, color: PAL.ink },
      shapes, annotations,
      showlegend: true,
      // Glyph key: VERTICAL stack, solid white fill + black box, anchored HIGH (above the lanes,
      // up by the title) so it never overlaps the PSD ticks or any lane content.
      legend: { orientation: "v", x: 0.30, xanchor: "left", y: 1.13, yanchor: "top",
                font: { size: 11.5 }, bgcolor: "rgba(255,255,255,0.96)",
                bordercolor: "#1a1a1a", borderwidth: 1.5,
                itemsizing: "constant", tracegroupgap: 2 },
      title: { text: `<b>Biomarker Data Timeline</b><br><span style="font-size:13px;color:#777">${sub}</span>`,
               x: 0.012, xanchor: "left", y: 0.965, font: { size: 26, color: "#1a1a1a" } },
      // DYNAMIC time gridlines: no fixed dtick, so Plotly auto-picks the tick interval for the
      // current zoom (year/month -> week -> day -> 6 h -> hour) and REDRAWS on every zoom/pan. The
      // gridlines span the whole single y-axis, so they carry through every neural lane + pain +
      // stim. Darker than the old faint shapes per the request.
      xaxis: { range: [D(t0), D(t1)], type: "date", autorange: false,
               showgrid: true, gridcolor: "rgba(0,0,0,0.18)", gridwidth: 1,
               tickfont: { size: 11.5 }, ticks: "outside", ticklen: 4, tickcolor: "#ccc",
               showspikes: true, spikemode: "across", spikethickness: 1,
               spikecolor: "rgba(0,0,0,0.35)", spikedash: "solid" },
      yaxis: { visible: false, range: [stimBase - 0.5, FULL_TOP], fixedrange: true },
    };

    // Plotly.react updates the EXISTING graph in place (diff), so a dependency change (e.g. the
    // pain row recoloring when the metric changes) redraws without tearing the div down. We do NOT
    // purge on every re-run: purging collapses the div to zero height, which yanks the page scroll
    // back to the top on each metric/binarization change. Purge happens once on unmount (below).
    Plotly.react(gd, traces, layout, { responsive: true, displayModeBar: true,
      modeBarButtonsToRemove: ["lasso2d", "select2d"] });
  }, [av, channels, height, painOverride, data]);

  // Free the WebGL context only when the component actually unmounts (NOT between redraws).
  useEffect(() => () => { if (ref.current) Plotly.purge(ref.current); }, []);

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
    </MDBox>
  );
}
