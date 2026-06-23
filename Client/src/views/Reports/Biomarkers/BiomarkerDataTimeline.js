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
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";

import MDBox from "components/MDBox";

// Binarization color identity — MUST match the histogram / binarizationModel (Okabe-Ito).
// excluded-middle is darkened to #5A6066 (was #7E8794) so "matched but dropped by the cut" is
// categorically distinct from "never matched" and readable on white (design + eng review).
const BIN_COLORS = { high: "#D55E00", low: "#0072B2", excluded: "#5A6066" };
// "Not included in the binarized set" (unmatched, or a modality the scan doesn't pool): a dimmed but
// clearly-present grey (~2:1 on white) so existing-but-unselected data never reads as ABSENT. The
// previous #D7DBDF was ~1.39:1 — effectively invisible, making real data look like missing data.
const DIM_GREY = "#AEB4BB";
const DIM_GREY_FAINT = "rgba(150,157,165,0.42)";

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

export default function BiomarkerDataTimeline({ data, height, painOverride,
                                               scanModel, colorMode, setColorMode }) {
  const ref = useRef(null);
  const av = data && data.availability ? data.availability : null;
  // Binarization color mode is active only when the parent both selects it AND a live scan model
  // (matched PSDs at the current window) exists. `binOf(ch, t)` returns "high"|"low"|"excluded"|
  // "unmatched" for a mark at (canonical channel, epoch seconds) — the lookup the scan model built.
  const binMode = colorMode === "binarization" && !!(scanModel && scanModel.binByKey);
  const binOf = (ch, tSec) => {
    if (!binMode || tSec == null) return null;
    return scanModel.binByKey.get(`${String(ch).toUpperCase()}|${Math.round(tSec)}`) || "unmatched";
  };
  const hasToggle = typeof setColorMode === "function";
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

    // ---- LEFT-LABEL COLUMN GEOMETRY (robust, self-sizing) ------------------------------------
    // The left gutter holds THREE right-to-left columns that must never overlap each other or run
    // off the figure: [LSB tick numbers] · [contact names L 0⁻3⁺ …] · [rotated hemisphere/region].
    // Earlier these used hand-tuned paper-fraction / fixed xshift values and collided when the
    // contact font was large or the plot was wide. Here we lay the columns deterministically from
    // ESTIMATED text widths (Arial ≈ 0.58·fontSize·nChars; bold ≈ 0.62) with a uniform gap, then
    // shrink the contact/region fonts together ONLY if the stack would exceed LEFT_CAP px. The
    // resulting per-column right-edge xshifts (negative = left of the plot edge) and the exact
    // left margin are computed once and reused by every left annotation — so nothing can run into
    // anything, the gutter is as tight as the labels allow, and it adapts to any width/label set.
    const LBL_GAP = 12;                          // uniform px gap between columns
    const LEFT_CAP = 230;                        // max gutter before we shrink fonts
    const textW = (s, fs, bold) => (bold ? 0.62 : 0.58) * fs * String(s).length;
    const prettyChans = channels.map((ch) => prettyContact(labelFor(ch)));
    // tick numbers: widest LSB magnitude shown (committed lanes carry a 4-digit count, ~"1727")
    const F_TICK = 14;
    const W_tick = 4.2 * 0.58 * F_TICK;          // budget for a 4-char number
    let F_CONTACT = 26, F_REGION = 18;           // start sizes (contact was 30 -> 26 baseline)
    const layoutLeft = () => {
      const W_contact = Math.max(40, ...prettyChans.map((s) => textW(s, F_CONTACT, true)));
      const W_region = 2 * 1.25 * F_REGION;      // rotated 2-line block (name / region) height
      const xTick = -LBL_GAP;
      const xContact = -(LBL_GAP + W_tick + LBL_GAP);
      const xRegionCenter = -(LBL_GAP + W_tick + LBL_GAP + W_contact + LBL_GAP + W_region / 2);
      const marginL = LBL_GAP + W_tick + LBL_GAP + W_contact + LBL_GAP + W_region + LBL_GAP;
      return { xTick, xContact, xRegionCenter, marginL, W_contact };
    };
    let L = layoutLeft();
    // Auto-shrink (down to a readable floor) until the gutter fits LEFT_CAP.
    while (L.marginL > LEFT_CAP && F_CONTACT > 16) {
      F_CONTACT -= 1; F_REGION = Math.max(13, F_REGION - 0.6); L = layoutLeft();
    }
    const X_TICK = Math.round(L.xTick);
    const X_CONTACT = Math.round(L.xContact);
    const X_REGION = Math.round(L.xRegionCenter);
    const MARGIN_L = Math.ceil(L.marginL);

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
      // right-anchored per-contact names (now larger, anchored at x ≈ -0.05) and the row labels.
      // Pinned to the left border with a FIXED-PIXEL xshift (not a paper fraction) so it hugs the
      // lanes at any width — paper-fraction x scaled with plot width and drifted off-figure when wide.
      annotations.push({ xref: "paper", yref: Y, x: 0, xshift: X_REGION, y: (top + bot) / 2,
        text: `<b>${hemi}</b><br>${HEMI2[hemi].region}`, showarrow: false, textangle: -90,
        font: { size: F_REGION, color: HEMI2[hemi].col }, align: "center" });
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

      // (a) TD coverage blocks. TD streaming IS pooled into the scan, so in BINARIZATION mode each
      // block is recolored by its matched pain bin (high=vermillion / low=blue / excluded=grey),
      // and any block not matched-and-included dims to very light grey. In MULTIMODAL mode it keeps
      // the desaturated hemisphere tint.
      recordsFor(ch, "timedomain").forEach((r) => {
        const ts = tEpoch(r.t_start);
        const te = ts + Math.max(r.dur_s || 0, 86400 * 1.6);
        let fc = tdc, op = 0.85;
        if (binMode) {
          const b = binOf(ch, ts);
          if (b === "high" || b === "low" || b === "excluded") { fc = BIN_COLORS[b]; op = 0.92; }
          else { fc = DIM_GREY; op = 0.45; }
        }
        shapes.push({ type: "rect", xref: X, yref: Y, x0: D(ts), x1: D(te),
          y0: yb + 0.04 * lh, y1: yb + 0.26 * lh, fillcolor: fc, opacity: op,
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
            // Band-power LSB is NOT in the pooled-PSD scan, so in binarization mode it is "not part
            // of the selected set" → dim. In multimodal mode it is colored by sensing center freq.
            const fc = binMode ? DIM_GREY_FAINT : (c == null ? "rgba(90,90,90,0.55)" : freqColor(c));
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
            // Streaming LSB sessions are band-power, not pooled PSDs → dim in binarization mode.
            const fc = binMode ? DIM_GREY_FAINT : freqColor(c);
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
          annotations.push({ xref: "paper", yref: Y, x: 0, xshift: X_TICK, y: BP_HI, text: `${Math.round(hi)}`,
            showarrow: false, xanchor: "right", font: { size: F_TICK, color: "#aaa" } });
          annotations.push({ xref: "paper", yref: Y, x: 0, xshift: X_TICK, y: BP_LO, text: `${Math.round(lo)}`,
            showarrow: false, xanchor: "right", font: { size: F_TICK, color: "#aaa" } });
          annotations.push({ xref: "paper", yref: Y, x: 0, xshift: X_TICK, y: (BP_LO + BP_HI) / 2,
            text: "<span style='font-size:13px;color:#bbb'>LSB</span>", showarrow: false, xanchor: "right" });
        }
      } else {
        annotations.push({ xref: "paper", yref: Y, x: 0.5, y: yb + 0.5 * lh,
          text: "no band power configured · n.d.", showarrow: false,
          font: { size: 9.5, color: "#9AA0A6" } });
      }

      // (c) PSD ticks (montage/survey) — these ARE pooled into the binarization scan. In
      // binarization mode each tick is colored by its matched pain bin (and a bit larger/taller so
      // the selected spectra read clearly); in-scan-but-unmatched ticks dim. Ticks that are NOT in
      // the scan at all (not poolable) are hidden in binarization mode — they can never be colored,
      // so showing ~1200 permanently-grey ticks is clutter with no decoding value. In multimodal
      // mode all ticks show as the neutral mid-gray "spectrum captured here" marks.
      const inScan = (r) => binMode && scanModel.binByKey.has(`${String(ch).toUpperCase()}|${Math.round(tEpoch(r.t_start))}`);
      const psdAll = recordsFor(ch, "psd");
      const psd = binMode ? psdAll.filter(inScan) : psdAll;
      if (psd.length) {
        const tickColor = (r) => {
          if (!binMode) return "#9AA0A6";
          const b = binOf(ch, tEpoch(r.t_start));
          return (b === "high" || b === "low" || b === "excluded") ? BIN_COLORS[b] : DIM_GREY;
        };
        const isEvent = (r) => r.product === "patient_event";
        // Multimodal mode: tint imported event-marker PSDs a faint teal so the new population is
        // visible against the neutral-grey montage/survey ticks; binarization mode colors both by bin.
        const colors = psd.map((r) => (!binMode && isEvent(r) ? "#3B8A8F" : tickColor(r)));
        const sizes = colors.map((c, i) => (binMode && c !== DIM_GREY ? 11 : (isEvent(psd[i]) ? 6 : 7)));
        // Hover label: for imported event-marker PSDs show the marker's own NAME (e.g. "Streaming",
        // "Higher Pain"); for ordinary snapshots show the product.
        const tickLabel = (r) => (isEvent(r) ? `${r.event_name || "Event"} (event PSD)` : r.product);
        traces.push({ type: "scattergl", mode: "markers",
          x: psd.map((r) => D(tEpoch(r.t_start))), y: psd.map(() => yb + 0.93 * lh),
          marker: { symbol: "line-ns-open", size: sizes,
                    color: colors, line: { width: binMode ? 2.0 : 1.2 } },
          customdata: psd.map((r) => tickLabel(r)),
          hovertemplate: `PSD snapshot<br>%{x}<br>%{customdata}<extra></extra>`, showlegend: false });
      }

      // (d) lane label — bold for committed, lighter for exploratory
      annotations.push({ xref: "paper", yref: Y, x: 0, xshift: X_CONTACT, y: yb + 0.5 * lh,
        text: committed.has(ch) ? `<b>${prettyContact(labelFor(ch))}</b>` : prettyContact(labelFor(ch)),
        showarrow: false, xanchor: "right",
        font: { size: F_CONTACT, color: committed.has(ch) ? PAL.ink : "#888" } });
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
      // one marker trace per label. Kept OUT of the legend (showlegend:false) but the per-event
      // hover stays: label + time + hemisphere count. Peak Hz is intentionally omitted — the raw
      // event PSD is 1/f-dominated so the peak always sits near DC and carries no information.
      labelOrder.forEach((label) => {
        const grp = evList.filter((e) => (e.label || "event") === label);
        traces.push({ type: "scattergl", mode: "markers",
          x: grp.map((e) => D(e.t)), y: grp.map(() => eventY),
          marker: { symbol: "diamond", size: 8, color: colorOf(label),
                    line: { color: "rgba(0,0,0,0.45)", width: 0.6 } },
          customdata: grp.map((e) => [label, e.n_chan == null ? "?" : e.n_chan]),
          hovertemplate: "<b>%{customdata[0]}</b><br>%{x}<br>%{customdata[1]} ch<extra></extra>",
          name: label, showlegend: false });
      });
    } else {
      annotations.push({ xref: "paper", yref: Y, x: 0.5, y: eventY,
        text: "no patient events", showarrow: false, font: { size: 9, color: "#C2A0A0" } });
    }
    annotations.push({ xref: "paper", yref: Y, x: 0, xshift: X_CONTACT, y: eventY,
      text: `<b>EVENTS</b>${evList.length ? `<br><span style="font-size:13px;color:#999">${evList.length} presses</span>` : ""}`,
      showarrow: false, xanchor: "right", font: { size: 24, color: "#555" } });

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
      // In binarization mode, color each PRO marker by which side of the LIVE cut(s) it falls on
      // (high=vermillion / low=blue / excluded-middle=grey), so the threshold the matched PSDs are
      // binarized at is visible directly on the pain row. The connecting line stays a faint neutral.
      const cuts = binMode ? scanModel.cuts : null;
      const classifyPain = (v) => {
        if (!cuts || cuts.kind === "none") return PAL.pain;
        if (cuts.kind === "two-cut") return v <= cuts.lowCut ? BIN_COLORS.low
          : (v >= cuts.highCut ? BIN_COLORS.high : BIN_COLORS.excluded);
        return v <= cuts.cut ? BIN_COLORS.low : BIN_COLORS.high;
      };
      // Multimodal pain color: a neutral dark slate (#3A4A63), NOT PAL.pain #C44E00 — the latter is
      // within ~1.2:1 of the high-pain vermillion #D55E00, so a clinician glancing at the multimodal
      // pain row would read every point as "high pain" before any binarization. Reserving vermillion
      // for the HIGH semantic that only exists in binarization mode removes that cross-toggle clash.
      const PAIN_NEUTRAL = "#3A4A63";
      const lineColor = binMode ? "rgba(120,120,120,0.35)" : PAIN_NEUTRAL;
      const markColors = binMode ? pain.y.map(classifyPain) : PAIN_NEUTRAL;
      traces.push({ type: "scattergl", mode: "lines", x: pain.t.map(D), y: py,
        line: { color: lineColor, width: 2.4 }, opacity: binMode ? 0.5 : 0.45,
        hoverinfo: "skip", showlegend: false });
      traces.push({ type: "scattergl", mode: "markers", x: pain.t.map(D), y: py,
        marker: { size: binMode ? 6 : 5, color: markColors }, opacity: binMode ? 0.92 : 0.6,
        hovertemplate: `${pain.metric || "pain"} %{customdata}<br>%{x}<extra></extra>`,
        customdata: pain.y, showlegend: false });
    } else {
      annotations.push({ xref: "paper", yref: Y, x: 0.5, y: (painBase + painTop) / 2,
        text: "no PRO data", showarrow: false, font: { size: 9.5, color: "#9AA0A6" } });
    }
    annotations.push({ xref: "paper", yref: Y, x: 0, xshift: X_CONTACT, y: (painBase + painTop) / 2,
      text: `<b>PAIN</b><br><span style="font-size:14px;color:#999">${pain.metric || ""}</span>`,
      showarrow: false, xanchor: "right", font: { size: 26, color: PAL.pain } });
    pTicks.forEach((val) => annotations.push({ xref: "paper", yref: Y, x: 0, xshift: X_TICK,
      y: yScale(val, pLo, pHi, painBase, painTop), text: String(val), showarrow: false,
      xanchor: "right", font: { size: 19, color: "#888" } }));

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
    annotations.push({ xref: "paper", yref: Y, x: 0, xshift: X_CONTACT, y: (stimBase + stimTop) / 2,
      text: "<b>STIM</b>", showarrow: false, xanchor: "right",
      font: { size: 26, color: PAL.stim } });
    [0, SMAX].forEach((val) => annotations.push({ xref: "paper", yref: Y, x: 0, xshift: X_TICK,
      y: yScale(val, 0, SMAX, stimBase, stimTop), text: String(val), showarrow: false,
      xanchor: "right", font: { size: 19, color: "#888" } }));
    annotations.push({ xref: "paper", yref: Y, x: 0, xshift: X_CONTACT, y: stimBase - 0.30,
      text: "<span style='font-size:14px;color:#999'>mA</span>", showarrow: false, xanchor: "right" });

    // ---- glyph key (top, near title) via dummy legend traces ---------------------------------
    if (binMode) {
      // Binarization view: the key explains the pain-bin colors, not the sensing-frequency colors.
      // Live counts are appended so a category that is empty (e.g. excluded-middle = 0 on integer
      // NRS) is explained, not hunted for; distinct marker SYMBOLS add a non-color channel.
      const bc = (scanModel && scanModel.counts) || {};
      traces.push({ x: [null], y: [null], mode: "markers", type: "scatter",
        marker: { symbol: "square", size: 12, color: BIN_COLORS.high },
        name: `HIGH pain  (≥ high cut)${bc.n_high != null ? `  ·  ${bc.n_high}` : ""}` });
      traces.push({ x: [null], y: [null], mode: "markers", type: "scatter",
        marker: { symbol: "square", size: 12, color: BIN_COLORS.low },
        name: `LOW pain  (≤ low cut)${bc.n_low != null ? `  ·  ${bc.n_low}` : ""}` });
      traces.push({ x: [null], y: [null], mode: "markers", type: "scatter",
        marker: { symbol: "diamond", size: 11, color: BIN_COLORS.excluded },
        name: `excluded middle  (dropped from training)${bc.n_excluded_middle != null ? `  ·  ${bc.n_excluded_middle}` : ""}` });
      traces.push({ x: [null], y: [null], mode: "markers", type: "scatter",
        marker: { symbol: "circle-open", size: 11, color: DIM_GREY, line: { width: 1.5, color: DIM_GREY } },
        name: "not in binarized set  (no PRO in window / band-power)" });
    } else {
      // Glyph key listed TOP→BOTTOM in the order the layers stack within a neural lane: raw TD
      // coverage band, then the chronic 24/7 LSB trend, then the streaming LSB session blocks, then
      // the montage/PSD ticks at the bottom of the lane. The two LSB families share a distinct GREEN
      // (#2CA02C) and are told apart by a non-color channel: chronic = squiggly/dashed line, streaming
      // = a solid block. (The lanes themselves stay colored by sensing Hz — see the right-side key.)
      const LSB_GREEN = "#2CA02C";
      traces.push({ x: [null], y: [null], mode: "markers", type: "scatter",
        marker: { symbol: "square", size: 12, color: "#C9BBDF" },
        name: "raw TD coverage  (zoom → waveform)" });
      traces.push({ x: [null], y: [null], mode: "lines", type: "scatter",
        line: { color: LSB_GREEN, width: 2.5, dash: "dashdot", shape: "spline" },
        name: "chronic LSB · 24/7 trend  (squiggle; lane color = sensing Hz)" });
      traces.push({ x: [null], y: [null], mode: "markers", type: "scatter",
        marker: { symbol: "square", size: 15, color: LSB_GREEN },
        name: "streaming LSB session · block  (lane color = sensing Hz; hover → detail)" });
      traces.push({ x: [null], y: [null], mode: "markers", type: "scatter",
        marker: { symbol: "line-ns-open", size: 10, color: "#9AA0A6", line: { width: 1.4 } },
        name: "montage PSD  (survey sweep + extra snapshots; hover → spectrum)" });
    }
    // Patient-event diamonds get their own per-label legend entries (added in the EVENT row above),
    // so no generic event glyph is needed here.

    // ---- right-side frequency legend: only realized centers (multimodal mode only — in
    // binarization mode the lanes are not frequency-colored, so the freq legend would mislead) ----
    const pcs = binMode ? [] : [...present].filter((c) => c != null).sort((a, b) => a - b);
    if (pcs.length) annotations.push({ xref: "paper", yref: "paper", x: 1.015, y: 0.90,
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
      // Left margin is COMPUTED from the label-column geometry (MARGIN_L) so it's exactly as wide
      // as the [tick · contact · region] stack needs and no wider — tight, collision-free, and
      // self-adjusting to the label set / font auto-shrink. Was a hardcoded 175/330.
      margin: { l: MARGIN_L, r: 120, t: 170, b: 46 },
      hovermode: "closest",
      // Constant uirevision: preserve the clinician's zoom/pan/legend state across re-renders driven
      // by the match-window slider, strategy, or the color-mode toggle (Plotly resets the view on
      // react() otherwise). Keyed by metric so a metric change — a genuinely different x/y domain —
      // intentionally resets the view; everything else keeps it.
      uirevision: (pain && pain.metric) ? `tl-${pain.metric}` : "tl",
      plot_bgcolor: "#ffffff", paper_bgcolor: "#ffffff",
      font: { family: "Arial, Helvetica, sans-serif", size: 11, color: PAL.ink },
      shapes, annotations,
      showlegend: true,
      // Glyph key: VERTICAL stack, solid white fill + black box, anchored HIGH (above the lanes, up
      // by the title) so it never overlaps the PSD ticks or any lane content. CENTERED horizontally
      // (x:0.5, xanchor:"center") at that same height — the box sits centered over the plot, with the
      // title on the far left and the sensing-Hz key on the far right both clear of it.
      legend: { orientation: "v", x: 0.5, xanchor: "center", y: 1.155, yanchor: "top",
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
               tickfont: { size: 17 }, ticks: "outside", ticklen: 4, tickcolor: "#ccc",
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
  }, [av, channels, height, painOverride, data, scanModel, colorMode, binMode]);

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
      {hasToggle ? (
        <MDBox display="flex" flexDirection="row" justifyContent="flex-end" alignItems="center"
               gap={1.25} sx={{ px: 1, pb: 0.5 }}>
          {/* Mode caption swaps with the toggle so the metaphor is explicit without reading the
              footer — "what does this color mean right now" is answered in place. */}
          <span style={{ fontSize: 12, color: "#777", fontStyle: "italic", textAlign: "right" }}>
            {colorMode === "binarization"
              ? "Matched samples colored by pain label; everything else dimmed"
              : "Neural lanes colored by sensing frequency"}
          </span>
          <span style={{ fontSize: 13, fontWeight: 600, color: "#555", whiteSpace: "nowrap" }}>{"Color by"}</span>
          <ToggleButtonGroup
            value={colorMode || "multimodal"} exclusive size="small"
            onChange={(e, v) => { if (v) setColorMode(v); }}
            sx={{
              "& .MuiToggleButton-root": { textTransform: "none", fontSize: 12.5, fontWeight: 600,
                px: 1.5, py: 0.4, color: "#555", borderColor: "#C7CCD1" },
              "& .Mui-selected": { color: "#fff !important", backgroundColor: "#344767 !important" },
            }}
          >
            <ToggleButton value="multimodal">{"Multimodal data"}</ToggleButton>
            <ToggleButton value="binarization" disabled={!(scanModel && scanModel.binByKey)}>
              {"Binarization"}
            </ToggleButton>
          </ToggleButtonGroup>
        </MDBox>
      ) : null}
      <div ref={ref} style={{ width: "100%" }} />
    </MDBox>
  );
}
