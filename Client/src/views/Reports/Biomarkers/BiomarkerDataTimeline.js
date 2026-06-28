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

// Robust low/high window from a sample list: the p_lo / p_hi percentiles (linear interpolation),
// so a single LSB spike or dropout can't compress the visible trend. Used by the zoom-adaptive LSB
// rescale to fill each lane with the 1st–99th percentile of the data currently in view. Returns
// null when too few finite samples to be meaningful (caller falls back to the global window).
function robustWindow(vals, pLo = 1, pHi = 99) {
  const a = vals.filter((v) => v != null && Number.isFinite(v)).sort((x, y) => x - y);
  if (a.length < 3) return null;
  const q = (p) => {
    const idx = (p / 100) * (a.length - 1);
    const i = Math.floor(idx), f = idx - i;
    return i + 1 < a.length ? a[i] * (1 - f) + a[i + 1] * f : a[i];
  };
  let lo = q(pLo), hi = q(pHi);
  if (!(hi > lo)) { const m = (hi + lo) / 2 || 0; lo = m - 0.5; hi = m + 0.5; }  // degenerate guard
  return [lo, hi];
}

// Human-readable date / clock-time / duration for the time-domain coverage-block hover. The block
// rects are Plotly SHAPES (no hover), so the hover lives on invisible anchor markers; these helpers
// build its three lines: acquisition date, streaming start time, and captured duration.
const fmtHoverDate = (epoch_s) => toDate(epoch_s).toLocaleDateString("en-US",
  { year: "numeric", month: "short", day: "numeric" });
const fmtHoverTime = (epoch_s) => toDate(epoch_s).toLocaleTimeString("en-US",
  { hour: "2-digit", minute: "2-digit" });
const fmtDur = (s) => {
  if (s == null || !Number.isFinite(s) || s <= 0) return "—";
  if (s < 90) return `${Math.round(s)} s`;
  if (s < 5400) return `${(s / 60).toFixed(1)} min`;      // < 90 min
  if (s < 172800) return `${(s / 3600).toFixed(1)} h`;    // < 2 days
  return `${(s / 86400).toFixed(1)} days`;
};

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
// Hemisphere accent/tint only — NO hardcoded brain region. The region label (e.g. GPi / VIM / VPL)
// must come from the participant's electrode/lead metadata (per-channel `region` on the record, or
// data.region_map), never a static guess: hardcoding LEFT→GPi / RIGHT→VIM mislabels anatomy the
// moment this view opens on a participant with different targets. We fall back to NO region label
// rather than a wrong one (FRONTEND_review item 6).
const HEMI2 = {
  LEFT: { col: "#5E3C99", td: "#C9BBDF", band: "rgba(94,60,153,0.05)" },
  RIGHT: { col: "#117733", td: "#B4D8C2", band: "rgba(17,119,51,0.05)" },
};
const PAL = { pain: "#C44E00", stim: "#7E6BB0", ink: "#1a1a1a", proLsb: "#1F4E79" };

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
  // TD coverage rects re-sized on zoom: each entry is {i: shape index, ts: epoch_s, dur_s} so the
  // plotly_relayout handler can recompute x1 against the live x-range (constant-PIXEL floor, true
  // length when zoomed in). Rebuilt on every draw; read only by the zoom handler.
  const tdRectsRef = useRef([]);
  // Per-lane LSB band-power rescale state, rebuilt every draw and read by the zoom handler. Each
  // entry carries the lane's pixel band [BP_LO,BP_HI], its GLOBAL magnitude window [full_lo,full_hi]
  // (used at full-span so the default view is unchanged), the raw (unscaled) LSB samples per trace
  // with their epoch-second timestamps, and the annotation indices of the lane's low/high LSB ticks.
  // On zoom the handler recomputes a ROBUST window (1st–99th pct) over the samples visible in the
  // live x-range and restyles the trace y + tick text, so the LSB mini-axis fills the lane.
  const lsbScaleRef = useRef([]);
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
      const chronicT = [], chronicY = [], chronicHz = [], sessions = [], modeled = [];
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
        // MODELED tier (psd_modeled): calibrated LSB via the transform DSP (survey/montage TD →
        // td_to_lsb ×352.62) or the CS-3 PSD→LSB bridge (×73.63); each point's `method` names which.
        // Kept separate so it renders as a DISTINCT HOLLOW marker, never a sensed session block.
        (d.modeled || []).forEach((m) => modeled.push(m));
        if (Number.isFinite(d.y_lo)) yLo = Math.min(yLo, d.y_lo);
        if (Number.isFinite(d.y_hi)) yHi = Math.max(yHi, d.y_hi);
      });
      if (!chronicT.length && !sessions.length && !modeled.length) return null;
      // time-sort chronic samples (merged keys may interleave); carry center_hz with the reorder
      // so the chronic line can be colored by its (time-varying) sensing center frequency.
      let chronic = null;
      if (chronicT.length) {
        const ord = chronicT.map((_, i) => i).sort((a, b) => chronicT[a] - chronicT[b]);
        chronic = { t: ord.map((i) => chronicT[i]), y: ord.map((i) => chronicY[i]),
                    center_hz: ord.map((i) => chronicHz[i]) };
      }
      sessions.sort((a, b) => a.t0 - b.t0);
      modeled.sort((a, b) => a.t - b.t);
      return { chronic, sessions, modeled,
               y_lo: Number.isFinite(yLo) ? yLo : 0, y_hi: Number.isFinite(yHi) ? yHi : 1 };
    };
    // CS-4 per-PRO LSB SELECTION for a lane: av.pro_lsb is keyed by RAW channel, one entry per pain
    // rating tagged with the source TIER (native sensed > direct TD->LSB transform > PSD-only-event
    // bridge) it was chosen from. Collapse raw keys onto the normalized lane and keep only the ratings
    // that actually resolved to an LSB (tier != null). Returns [{t, lsb, tier, center_hz, saturated}].
    const proLsbFor = (ch) => {
      const pl = av.pro_lsb || {};
      const keys = Object.keys(pl).filter((k) => normalizeChannel(k) === ch);
      if (!keys.length) return [];
      const pts = [];
      keys.forEach((k) => (pl[k] || []).forEach((r) => {
        if (r && r.lsb != null && r.tier) pts.push(r);
      }));
      pts.sort((a, b) => a.t - b.t);
      return pts;
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
    tdRectsRef.current = [];   // rebuilt this draw; the zoom handler resizes these TD rects
    lsbScaleRef.current = [];   // rebuilt this draw; the zoom handler rescales the per-lane LSB axis

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
      // Region label from metadata only: a per-channel `region` on the record (backend
      // format_channel) or data.region_map[channel]; fall back to NO region (hemisphere alone)
      // rather than a hardcoded guess.
      const regionOf = (h) => {
        const rmap = (data && data.region_map) || {};
        const rec = (av.records || []).find((r) =>
          (r.hemisphere || (String(r.channel).toUpperCase().indexOf("LEFT") >= 0 ? "LEFT" : "RIGHT")) === h
          && (r.region || rmap[r.channel]));
        const reg = rec ? (rec.region || rmap[rec.channel]) : null;
        return (reg && String(reg).trim()) ? String(reg).trim() : "";
      };
      const regionLabel = regionOf(hemi);
      annotations.push({ xref: "paper", yref: Y, x: 0, xshift: X_REGION, y: (top + bot) / 2,
        text: `<b>${hemi}</b>${regionLabel ? `<br>${regionLabel}` : ""}`, showarrow: false, textangle: -90,
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
      // The visible block has a constant-PIXEL minimum width (MIN_TD_PX) so a short stream stays
      // visible when zoomed out (like the PSD raster ticks) WITHOUT the old constant-TIME floor that
      // painted a 30 s session 1.6 days wide and made it look like it covered nearby ratings. The
      // zoom handler (plotly_relayout, below) recomputes each block's x1 against the live x-range, so
      // as you zoom in the block shrinks to its TRUE dur_s once the real length exceeds the floor.
      // The HOVER always reports the REAL captured duration (r.dur_s). Anchor the hover marker at the
      // block's TRUE center (ts + dur_s/2) so it stays over the rect at any zoom (the 18 px marker
      // easily covers a floor-width block when zoomed out).
      // INITIAL x1 uses a floor of span/200 (~= MIN_TD_PX at full-view pixel width) so the very first
      // paint is already short-and-visible, not 1.6 days; the handler refines it on the first zoom.
      const initFloorS = Math.max((t1 - t0) / 200, 1);
      const tdHx = [], tdHy = [], tdHc = [];
      recordsFor(ch, "timedomain").forEach((r) => {
        const ts = tEpoch(r.t_start);
        const durS = r.dur_s || 0;
        const te = ts + Math.max(durS, initFloorS);
        // Montage/survey TD (product "montage_td") is raw 250 Hz coverage just like streaming, but
        // from the stim-off survey sweep — render it with the SAME coverage block, tagged in the
        // hover so it is not misread as a streaming session.
        const isMontageTd = r.product === "montage_td";
        let fc = tdc, op = 0.85;
        if (binMode) {
          const b = binOf(ch, ts);
          if (b === "high" || b === "low" || b === "excluded") { fc = BIN_COLORS[b]; op = 0.92; }
          else { fc = DIM_GREY; op = 0.45; }
        }
        tdRectsRef.current.push({ i: shapes.length, ts, dur_s: durS });
        shapes.push({ type: "rect", xref: X, yref: Y, x0: D(ts), x1: D(te),
          y0: yb + 0.04 * lh, y1: yb + 0.26 * lh, fillcolor: fc, opacity: op,
          line: { width: 0 }, layer: "above" });
        tdHx.push(D(ts + durS / 2));
        tdHy.push(yb + 0.15 * lh);
        tdHc.push([fmtHoverDate(ts), fmtHoverTime(ts), fmtDur(r.dur_s),
                   isMontageTd ? "montage / survey sweep (stim-off)" : "streaming"]);
      });
      if (tdHx.length) {
        // Invisible markers span the FULL block height band so the hover triggers anywhere over the
        // coverage rect, reporting date · start time · captured duration (the info the PSD/montage
        // hovers already show, which TD blocks were missing entirely). The source word distinguishes
        // streaming TD from the montage/survey TD coverage now drawn from the same lane.
        traces.push({ type: "scattergl", mode: "markers", x: tdHx, y: tdHy,
          marker: { size: 18, color: "rgba(0,0,0,0)" }, customdata: tdHc,
          hovertemplate: `${prettyContact(labelFor(ch))} · time-domain %{customdata[3]}<br>`
            + `%{customdata[0]} · started %{customdata[1]}<br>`
            + `duration %{customdata[2]}<extra></extra>`,
          showlegend: false });
      }

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
        // Zoom-adaptive LSB rescale registration. `reg` collects everything the plotly_relayout
        // handler needs to refit THIS lane's band-power mini-axis to the data currently in view:
        //   - reg.samples : representative {t, v} magnitude points (chronic samples + session
        //                   medians) used to compute the robust 1st–99th-pct window over the visible
        //                   x-range. Span-wide view falls back to the global [full_lo, full_hi] so
        //                   the default look is unchanged.
        //   - reg.traces  : each scalable trace as {idx, raw} where `raw` is the UNSCALED LSB array
        //                   aligned to the trace's y (nulls preserved), so the handler can re-map
        //                   y = raw.map(scale) under the new window without rebuilding the figure.
        //   - tickHiIdx/tickLoIdx : annotation indices of the lane's high/low LSB tick text, so the
        //                   numbers shown on the left edge track the live window.
        const reg = { BP_LO, BP_HI, full_lo: lo, full_hi: hi,
                      samples: [], traces: [], tickHiIdx: null, tickLoIdx: null };
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
            reg.traces.push({ idx: traces.length, raw: ys });
            xs.forEach((tt, ii) => reg.samples.push({ t: tt, v: ys[ii] }));
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
            const byRaw = [], wyRaw = [], anchRaw = [];   // unscaled LSB, aligned to by/wy/anchor y
            ss.forEach((s) => {
              const x0 = D(s.t0), x1 = D(Math.max(s.t1, s.t0 + 86400 * 1.2)); // min visible width
              const ym = sc(s.med);
              // thick median bar as a 2-point horizontal segment (cheap vs filled rect per session)
              bx.push(x0, x1, null); by.push(ym, ym, null);
              byRaw.push(s.med, s.med, null);
              // 10-90 whisker at session midpoint
              const xm = D((s.t0 + s.t1) / 2);
              wx.push(xm, xm, null); wy.push(sc(s.lo), sc(s.hi), null);
              wyRaw.push(s.lo, s.hi, null);
              anchRaw.push(s.med);
              cd.push([Math.round(s.med), Math.round(s.lo), Math.round(s.hi), fmtHz(c), s.n]);
              // session median is the representative magnitude sample for the visible-window refit
              reg.samples.push({ t: (s.t0 + s.t1) / 2, v: s.med });
            });
            // whiskers (thin, same color, no hover)
            reg.traces.push({ idx: traces.length, raw: wyRaw });
            traces.push({ type: "scattergl", mode: "lines", x: wx, y: wy,
              line: { color: fc, width: 1 }, opacity: 0.5, hoverinfo: "skip", showlegend: false });
            // median bars (thick) — hover carries the session summary
            reg.traces.push({ idx: traces.length, raw: byRaw });
            traces.push({ type: "scattergl", mode: "lines", x: bx, y: by,
              line: { color: fc, width: committed.has(ch) ? 5 : 6 },
              hoverinfo: "skip", showlegend: false });
            // invisible hover anchors at each session median (one marker per session, tiny count)
            reg.traces.push({ idx: traces.length, raw: anchRaw });
            traces.push({ type: "scattergl", mode: "markers",
              x: ss.map((s) => D((s.t0 + s.t1) / 2)), y: ss.map((s) => sc(s.med)),
              marker: { size: 10, color: "rgba(0,0,0,0)" }, customdata: cd,
              hovertemplate: `${prettyContact(labelFor(ch))} · ${key === "na" ? "?" : fmtHz(c)} Hz<br>`
                + `median %{customdata[0]} LSB (10-90: %{customdata[1]}–%{customdata[2]})<br>`
                + `n=%{customdata[4]} samples<extra></extra>`,
              showlegend: false });
          });
        }
        // MODELED tier (psd_modeled): a calibrated-but-not-sensed LSB, drawn as DISTINCT HOLLOW
        // DIAMONDS so it is never read as a sensed value. Two DSP routes feed this tier and each point
        // carries its `method` string (availability.lsb_series):
        //   td_transform_x_k=352.62  -> montage/survey 250 Hz TD through the PRIMARY transform DSP
        //                               (analytics.td_to_lsb, k=352.62). NOT Welch256×269 (removed
        //                               2026-06-27); the hover names the actual route from m.method.
        //   event_psd_bridge_x_k=73.63 -> a PSD-only patient event with no TD, through the CS-3
        //                               PSD->LSB bridge (analytics.device_psd_to_lsb, k≈73.63).
        // These modeled points are pooled into the binarization scan, so unlike the sensed band-power
        // LSB they CAN be assigned to a pain bin. In binarization mode we color each diamond by its
        // matched pain bin (via binOf on the point's own timestamp); unmatched modeled points stay
        // faint. In frequency mode they color by sensing center freq (same FREQ_PALETTE). They ride the
        // lane's y-scale but did NOT set it (native-only window), so a modeled outlier clips at the
        // lane edge rather than rescaling.
        if (ov.modeled && ov.modeled.length) {
          const byFreqM = {};
          ov.modeled.forEach((m) => {
            const c = snapFreq(m.center_hz);
            if (c != null) present.add(c);
            (byFreqM[c == null ? "na" : String(c)] = byFreqM[c == null ? "na" : String(c)] || []).push(m);
          });
          // Color one modeled point: by pain bin in binMode (matched -> bin color, else faint),
          // by sensing frequency otherwise.
          const modeledColor = (m, c) => {
            if (!binMode) return freqColor(c);
            const b = binOf(ch, m.t);
            return (b === "high" || b === "low" || b === "excluded") ? BIN_COLORS[b] : DIM_GREY_FAINT;
          };
          // Human label for the DSP route a modeled point came from, read from its `method` string.
          const routeLabel = (method) => {
            const s = String(method || "");
            if (s.startsWith("td_transform")) return "transform DSP ×352.62";
            if (s.startsWith("event_psd_bridge")) return "PSD→LSB bridge ×73.63";
            return "modeled";
          };
          Object.keys(byFreqM).forEach((key) => {
            const ms = byFreqM[key];
            const c = key === "na" ? null : Number(key);
            // Split by DSP route: circle-open = td_transform, diamond-open = event_psd_bridge.
            // This keeps the SAME reserved glyphs as the per-rating tier so both layers are consistent.
            const ms_td  = ms.filter((m) => String(m.method || "").startsWith("td_transform"));
            const ms_psd = ms.filter((m) => String(m.method || "").startsWith("event_psd_bridge"));
            [[ms_td, "circle-open"], [ms_psd, "diamond-open"]].forEach(([pts, sym]) => {
              if (!pts.length) return;
              const cols = pts.map((m) => modeledColor(m, c));
              // Matched modeled points read a touch larger in binMode so the assigned ones stand out.
              const sizes = cols.map((col) => (binMode && col !== DIM_GREY_FAINT ? 9 : 7));
              const lineCols = cols;
              const mxRaw = pts.map((m) => m.y);
              reg.traces.push({ idx: traces.length, raw: mxRaw });
              traces.push({ type: "scattergl", mode: "markers",
                x: pts.map((m) => D(m.t)), y: pts.map((m) => sc(m.y)),
                marker: { symbol: sym, size: sizes, color: cols,
                          line: { color: lineCols, width: 1.4 } },
                customdata: pts.map((m) => [Math.round(m.y), key === "na" ? "?" : fmtHz(c),
                  binMode ? (binOf(ch, m.t) || "unmatched") : "", routeLabel(m.method)]),
                hovertemplate: `${prettyContact(labelFor(ch))} · modeled (%{customdata[3]}) · %{customdata[1]} Hz<br>`
                  + `≈%{customdata[0]} LSB (modeled, not sensed)`
                  + (binMode ? `<br>bin: %{customdata[2]}` : "")
                  + `<br>%{x}<extra></extra>`,
                showlegend: false });
            });
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
          reg.tickHiIdx = annotations.length;
          annotations.push({ xref: "paper", yref: Y, x: 0, xshift: X_TICK, y: BP_HI, text: `${Math.round(hi)}`,
            showarrow: false, xanchor: "right", font: { size: F_TICK, color: "#aaa" } });
          reg.tickLoIdx = annotations.length;
          annotations.push({ xref: "paper", yref: Y, x: 0, xshift: X_TICK, y: BP_LO, text: `${Math.round(lo)}`,
            showarrow: false, xanchor: "right", font: { size: F_TICK, color: "#aaa" } });
          annotations.push({ xref: "paper", yref: Y, x: 0, xshift: X_TICK, y: (BP_LO + BP_HI) / 2,
            text: "<span style='font-size:13px;color:#bbb'>LSB</span>", showarrow: false, xanchor: "right" });
        }
        // Register this lane for zoom-adaptive rescale only if it carries scalable LSB geometry.
        if (reg.traces.length) lsbScaleRef.current.push(reg);
      } else {
        annotations.push({ xref: "paper", yref: Y, x: 0.5, y: yb + 0.5 * lh,
          text: "no band power configured · n.d.", showarrow: false,
          font: { size: 9.5, color: "#9AA0A6" } });
      }

      // CS-4 PER-RATING MODELED LSB — one MODELED point per pain rating, on its OWN independent,
      // separable y-scale. This draws REGARDLESS of whether the lane had band-power overview geometry
      // (it lives OUTSIDE the `if (ov)` block above), so streaming-only / survey-sparse periods
      // (e.g. Feb–Mar 2026 onward) still get their per-rating markers.
      //
      // We deliberately DROP the native (sensed) tier here: native streamed LSB is ALREADY drawn as
      // the colored per-lane band-power time series above, so re-plotting it as a marker would
      // double-count the same measurement. Only the MODELED-at-rating values are shown, kept visually
      // separable by source:
      //   td_transform -> HOLLOW CIRCLE   (rating-centered 30 s TD through td_to_lsb, k=352.62)
      //   psd_bridge   -> HOLLOW DIAMOND  (PSD-only patient event through the CS-3 bridge, k≈73.63)
      // A saturated rating (TD window hit the ADC rail but a bridge value was still found) gets a red
      // outline. The y-scale is this lane's own robust min/max over the modeled per-rating LSB values
      // (independent of the band-power overview), registered for zoom-rescale like the other LSB layers.
      const proPtsAll = proLsbFor(ch).filter((p) => p.tier && p.tier !== "native" && p.lsb != null);
      if (proPtsAll.length) {
        const pvals = proPtsAll.map((p) => p.lsb).filter((v) => Number.isFinite(v)).sort((a, b) => a - b);
        const q = (arr, f) => arr[Math.min(arr.length - 1, Math.max(0, Math.round(f * (arr.length - 1))))];
        // robust 5th–95th-pct window so a single outlier rating doesn't flatten the rest
        const pLo = pvals.length ? q(pvals, 0.05) : 0;
        const pHi = pvals.length ? q(pvals, 0.95) : 1;
        const PRO_LO = yb + 0.04 * lh, PRO_HI = yb + 0.30 * lh;   // lower sub-band, separate from BP band
        const scP = (v) => PRO_LO + (PRO_HI - PRO_LO)
          * Math.min(Math.max((v - pLo) / (pHi - pLo + 1e-9), 0), 1);
        const regP = { BP_LO: PRO_LO, BP_HI: PRO_HI, full_lo: pLo, full_hi: pHi,
                       samples: [], traces: [], tickHiIdx: null, tickLoIdx: null };
        const TIER_SYMBOL = { td_transform: "circle-open", psd_bridge: "diamond-open" };
        const TIER_LABEL = { td_transform: "transform DSP ×352.62", psd_bridge: "PSD→LSB bridge ×73.63" };
        const byTier = {};
        proPtsAll.forEach((p) => { (byTier[p.tier] = byTier[p.tier] || []).push(p); });
        Object.keys(byTier).forEach((tier) => {
          const ps = byTier[tier];
          // binMode: color by the rating's pain bin (so the high/low selection is visible); else a
          // single steel tone (the marker SHAPE already encodes which DSP route produced the value).
          const colOf = (p) => {
            if (binMode) {
              const b = binOf(ch, p.t);
              return (b === "high" || b === "low" || b === "excluded") ? BIN_COLORS[b] : DIM_GREY_FAINT;
            }
            return PAL.proLsb || "#1F4E79";
          };
          const cols = ps.map(colOf);
          const lineCols = ps.map((p, i) => (p.saturated ? "#C0392B" : cols[i]));
          ps.forEach((p) => regP.samples.push({ t: p.t, v: p.lsb }));
          regP.traces.push({ idx: traces.length, raw: ps.map((p) => p.lsb) });
          traces.push({ type: "scattergl", mode: "markers",
            x: ps.map((p) => D(p.t)), y: ps.map((p) => scP(p.lsb)),
            marker: { symbol: TIER_SYMBOL[tier] || "circle-open", size: ps.map((p) => (p.saturated ? 9 : 7)),
                      color: "rgba(0,0,0,0)", line: { color: lineCols, width: ps.map((p) => (p.saturated ? 2 : 1.4)) } },
            customdata: ps.map((p) => [Math.round(p.lsb), fmtHz(p.center_hz), TIER_LABEL[tier] || tier,
              p.saturated ? " · TD saturated" : "", binMode ? (binOf(ch, p.t) || "unmatched") : ""]),
            hovertemplate: `${prettyContact(labelFor(ch))} · per-rating modeled LSB · %{customdata[2]}%{customdata[3]}<br>`
              + `≈%{customdata[0]} LSB @ %{customdata[1]} Hz (modeled, not sensed)`
              + (binMode ? `<br>bin: %{customdata[4]}` : "")
              + `<br>%{x}<extra></extra>`,
            showlegend: false });
        });
        if (regP.traces.length) lsbScaleRef.current.push(regP);
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

      // (d) lane label — ALWAYS bold AND always dark ink, so every contact (committed or
      // exploratory, e.g. R 1-3+, R 0-2+) reads identically crisp and black. (The committed vs
      // exploratory distinction is carried elsewhere — lane content / commit markers — not by
      // dimming the label, which made the exploratory names look like a washed-out grey.)
      // The gutter geometry already budgets every contact at the bold width (textW(..., true) on
      // line ~303), so bolding all of them does not widen the column.
      annotations.push({ xref: "paper", yref: Y, x: 0, xshift: X_CONTACT, y: yb + 0.5 * lh,
        text: `<b>${prettyContact(labelFor(ch))}</b>`,
        showarrow: false, xanchor: "right",
        font: { size: F_CONTACT, color: PAL.ink } });
    });

    // ---- EVENT row: PATIENT-ANNOTATED events (labeled button presses) ------------------------
    // One diamond per event at its time, COLORED BY LABEL (Higher Pain / Tingly-Burning / Feeling
    // Good / Medication / …), plus a faint drop-line up through the neural lanes so the flagged
    // moment is locatable against every channel. Hover LEADS with the patient's label, then time,
    // peak Hz, and channel count. These corroborate only (DESIGN §2/§6) — never decode.
    const evWrap = av.events || { events: [] };
    // The backend already separates the two PSD-event axes: `av.events.events` carries ONLY the
    // labeled patient presses (the diamond row), and `av.events.streaming_count` is the number of auto
    // 'Streaming' LFP snapshots — those render as per-lane event-PSD ticks (teal) from a SEPARATE
    // payload (av.records), not here, so they don't flood the diamond row. We trust that contract
    // rather than re-deriving the split by string-matching a category literal on the frontend.
    const evList = (evWrap.events || []).filter((e) => e && Number.isFinite(e.t));
    const streamingCount = Number.isFinite(evWrap.streaming_count) ? evWrap.streaming_count : 0;
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
      text: `<b>EVENTS</b>${evList.length ? `<br><span style="font-size:13px;color:#999">${evList.length} labeled` +
        `${streamingCount ? ` · ${streamingCount} streaming` : ""}</span>` : ""}`,
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
      traces.push({ type: "scattergl", mode: "lines", x: pain.t.map(D), y: py,
        line: { color: lineColor, width: 2.4 }, opacity: binMode ? 0.5 : 0.45,
        hoverinfo: "skip", showlegend: false });
      if (binMode) {
        // Binarization mode: each REAL pain rating encodes two things at once —
        //   fill  : CLOSED circle = this rating claimed >=1 PSD (matched); OPEN circle = matched none;
        //   color : class color (high=vermillion / low=blue / excluded-mid=grey) from the live cut.
        // painMatched (from binarizationModel) is aligned to pain.t order. For an open circle Plotly
        // draws an unfilled ring in marker.line.color, so we set the ring to the class color -> an
        // open marker still reads as its class.
        const cls = pain.y.map(classifyPain);
        const pm = (scanModel && scanModel.painMatched) || [];
        const symb = pain.y.map((_v, i) => (pm[i] ? "circle" : "circle-open"));
        const classifyName = (v) => {
          if (!cuts || cuts.kind === "none") return "pain";
          if (cuts.kind === "two-cut") return v <= cuts.lowCut ? "low"
            : (v >= cuts.highCut ? "high" : "excluded");
          return v <= cuts.cut ? "low" : "high";
        };
        traces.push({ type: "scattergl", mode: "markers", x: pain.t.map(D), y: py,
          marker: { size: 8, symbol: symb, color: cls, line: { width: 1.6, color: cls } },
          opacity: 0.95,
          customdata: pain.y.map((v, i) => [v, (pm[i] ? "matched" : "no neural match"),
            classifyName(v), fmtHoverDate(pain.t[i]), fmtHoverTime(pain.t[i])]),
          hovertemplate: `<b>${pain.metric || "pain"} %{customdata[0]}</b><br>`
            + `%{customdata[3]} · %{customdata[4]}<br>`
            + `%{customdata[2]} pain · %{customdata[1]}<extra></extra>`,
          showlegend: false });
      } else {
        traces.push({ type: "scattergl", mode: "markers", x: pain.t.map(D), y: py,
          marker: { size: 5, color: PAIN_NEUTRAL }, opacity: 0.6,
          customdata: pain.y.map((v, i) => [v, fmtHoverDate(pain.t[i]), fmtHoverTime(pain.t[i])]),
          hovertemplate: `<b>${pain.metric || "pain"} %{customdata[0]}</b><br>`
            + `%{customdata[1]} · %{customdata[2]}<extra></extra>`,
          showlegend: false });
      }
    } else {
      annotations.push({ xref: "paper", yref: Y, x: 0.5, y: (painBase + painTop) / 2,
        text: "no PRO data", showarrow: false, font: { size: 9.5, color: "#9AA0A6" } });
    }
    annotations.push({ xref: "paper", yref: Y, x: 0, xshift: X_CONTACT, y: (painBase + painTop) / 2,
      text: `<b>PAIN</b><br><span style="font-size:14px;color:#999">${pain.metric || ""}</span>`,
      showarrow: false, xanchor: "right", font: { size: 26, color: PAL.pain } });
    // Binarization-mode pain-row subtitle: matched vs unmatched ratings (closed vs open circles).
    if (binMode) {
      const su = (scanModel && scanModel.counts && scanModel.counts.survey_usage) || {};
      if (su.n_pro_total) {
        annotations.push({ xref: "paper", yref: Y, x: 0, xshift: X_CONTACT, y: painBase - 0.30,
          text: `<span style="font-size:13px;color:#999">${su.n_pro_used || 0} matched · ${su.n_pro_unused || 0} unmatched of ${su.n_pro_total} (${su.pct_pro_used != null ? su.pct_pro_used : 0}%)</span>`,
          showarrow: false, xanchor: "right" });
      }
    }
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
      // per-rating MODELED LSB still renders in binMode (colored by pain bin); document its shapes.
      // Native is NOT shown here — it's the colored band-power lane trace; these are modeled-at-rating.
      traces.push({ x: [null], y: [null], mode: "markers", type: "scatter",
        marker: { symbol: "circle-open", size: 9, color: "rgba(0,0,0,0)", line: { width: 1.4, color: DIM_GREY } },
        name: "per-rating modeled LSB  (same symbols: ○ TD-transform · ◇ PSD-bridge; color = bin)" });
    } else {
      // Glyph key listed TOP→BOTTOM in the order the layers actually stack within a neural lane:
      // montage/PSD ticks at the TOP, then the chronic 24/7 LSB trend, then the streaming LSB session
      // blocks, then the raw TD coverage band at the BOTTOM. The two LSB families share a distinct
      // GREEN (#2CA02C) and are told apart by a non-color channel: chronic = squiggly/dashed line,
      // streaming = a solid block. (The lanes themselves stay colored by sensing Hz — right-side key.)
      const LSB_GREEN = "#2CA02C";
      // PSD tick glyphs — TWO distinct sources that previously both read as "montage PSD":
      //  • grey ticks = montage/survey + NeuralActivitySnapshot device PSDs (carry their own TD)
      //  • teal ticks = patient-triggered EVENT PSDs (incl. the auto 'Streaming' snapshots), PSD-only
      traces.push({ x: [null], y: [null], mode: "markers", type: "scatter",
        marker: { symbol: "line-ns-open", size: 10, color: "#9AA0A6", line: { width: 1.4 } },
        name: "montage PSD  (survey sweep + montage snapshot; hover → spectrum)" });
      traces.push({ x: [null], y: [null], mode: "markers", type: "scatter",
        marker: { symbol: "line-ns-open", size: 10, color: "#3B8A8F", line: { width: 1.4 } },
        name: "streaming / event PSD  (patient-triggered LFP snapshot; PSD-only)" });
      // Patient-event diamonds (the EVENTS row) — one filled diamond per LABELED press, colored by
      // label. Add an explicit glyph so the row is documented (the per-label colors stay in the row).
      traces.push({ x: [null], y: [null], mode: "markers", type: "scatter",
        marker: { symbol: "diamond", size: 10, color: "#888", line: { color: "rgba(0,0,0,0.45)", width: 0.6 } },
        name: "patient event  (labeled press: Pain / Medication / …; color = label)" });
      traces.push({ x: [null], y: [null], mode: "lines", type: "scatter",
        line: { color: LSB_GREEN, width: 2.5, dash: "dashdot", shape: "spline" },
        name: "chronic LSB · 24/7 trend  (squiggle; lane color = sensing Hz)" });
      traces.push({ x: [null], y: [null], mode: "markers", type: "scatter",
        marker: { symbol: "square", size: 15, color: LSB_GREEN },
        name: "streaming LSB session · block  (lane color = sensing Hz; hover → detail)" });
      traces.push({ x: [null], y: [null], mode: "markers", type: "scatter",
        marker: { symbol: "circle-open", size: 11, color: LSB_GREEN, line: { width: 1.5, color: LSB_GREEN } },
        name: "modeled LSB  (○ TD-transform ×352.62 — hollow circle)" });
      traces.push({ x: [null], y: [null], mode: "markers", type: "scatter",
        marker: { symbol: "diamond-open", size: 11, color: LSB_GREEN, line: { width: 1.5, color: LSB_GREEN } },
        name: "modeled LSB  (◇ PSD→LSB bridge ×73.63 — hollow diamond)" });
      // CS-4 per-rating MODELED LSB — one modeled point per pain rating on its own sub-lane scale.
      // Native is NOT shown here (it's the colored band-power lane trace); shape = DSP route:
      // ○ hollow circle = TD-transform (×352.62), ◇ hollow diamond = PSD-bridge (×73.63); red ring = saturated.
      traces.push({ x: [null], y: [null], mode: "markers", type: "scatter",
        marker: { symbol: "circle-open", size: 9, color: "rgba(0,0,0,0)", line: { width: 1.4, color: PAL.proLsb } },
        name: "per-rating modeled LSB  (same symbols: ○ TD-transform · ◇ PSD-bridge; red ring = saturated)" });
      traces.push({ x: [null], y: [null], mode: "markers", type: "scatter",
        marker: { symbol: "square", size: 12, color: "#C9BBDF" },
        name: "raw TD coverage  (streaming + montage/survey sweep; zoom → waveform)" });
    }

    // ---- TOP-BAND GEOMETRY (title + the two flanking key boxes) -------------------------------
    // The legend and Hz key live in the top margin, ABOVE the plot. The previous version positioned
    // them with fixed paper-Y fractions (e.g. legend top at y=1.155), but a paper fraction is a
    // fraction of the PLOT HEIGHT — which varies with the channel count — so a box pinned by its TOP
    // grew DOWNWARD into the lanes when the plot was short (few channels) and looked fine only when it
    // was tall. That is exactly the overlap in the screenshot. Fix: derive every top-band Y from a
    // FIXED PIXEL offset converted through the live plot pixel height, and anchor each box by its
    // BOTTOM (just above the plot top) so it grows UP into the margin, never down into a lane.
    const nLegRows = binMode ? 5 : 9;            // glyph-legend entries per mode (see traces above)
    const LEG_H_PX = nLegRows * 20 + 18;         // legend box pixel height (per-row + padding)
    const TITLE_H_PX = 64;                       // two-line title block
    const TOP_GAP_PX = 14;                       // gap between title and the legend boxes
    const LEG_BOTTOM_PX = 12;                     // gap between the legend boxes and the plot top
    // Top margin auto-fits the tallest content (title + legend + gaps), so the title never clips and
    // the boxes always fit — for BOTH modes (binarization's 7-row legend is taller).
    const TOP_MARGIN = TITLE_H_PX + TOP_GAP_PX + LEG_H_PX + LEG_BOTTOM_PX + 10;
    const figH = height || Math.max(560, 150 * channels.length + TOP_MARGIN + 60);
    const plotHpx = Math.max(figH - TOP_MARGIN - 46, 200);   // 46 = bottom margin
    const pxY = (p) => p / plotHpx;              // pixels -> paper-Y units (0 = plot top)
    // Legend box: bottom pinned just above the plot, grows UP. Top = bottom + its pixel height.
    const LEG_BOT_Y = 1.0 + pxY(LEG_BOTTOM_PX);
    const LEG_TOP_Y = 1.0 + pxY(LEG_BOTTOM_PX + LEG_H_PX);
    const TITLE_Y = 1.0 + pxY(LEG_BOTTOM_PX + LEG_H_PX + TOP_GAP_PX + TITLE_H_PX);  // title baseline (top-anchored)

    // ---- provenance subtitle (hoisted here so the title-width estimate below can use sub.length)
    const fmtDate = (e) => new Date(e * 1000).toLocaleDateString("en-US",
      { month: "short", day: "2-digit", year: "numeric", timeZone: "UTC" });
    const subj = (data && data.participant_label) || (av && av.participant) || "";
    const sub = `${subj ? subj + " · " : ""}Percept RC · ${fmtDate(t0)} – ${fmtDate(t1)}`;

    // ---- legend & Hz-key placement (deterministic, width-independent) -----------------------
    // Per bravo-timeline-layout skill: the glyph legend is pinned to the plot's RIGHT edge
    // (x:1.0, xanchor:"right") below, so it can NEVER overlap the LEFT-anchored title/subtitle
    // regardless of figure width. No DOM-width measurement and no resize hook are needed — the
    // non-overlap is guaranteed by construction (legend grows leftward from the right edge; the
    // Hz key grows rightward from the left edge; their combined width ≪ 1.0). Verified
    // numerically with assert_no_overlap: gap ≈ 0.33 at nominal width, and widening only
    // increases it because both footprints shrink as paper fractions.

    // ---- (frequency-color "Sensing center (Hz)" key removed per request: it was redundant with
    // the per-lane Hz hover/labels and the lane coloring, and crowded the top band.) The lanes are
    // still frequency-colored via freqColor(); the legend on the right covers the glyph types.

    const layout = {
      height: figH,
      // Left margin is COMPUTED from the label-column geometry (MARGIN_L) so it's exactly as wide
      // as the [tick · contact · region] stack needs and no wider — tight, collision-free, and
      // self-adjusting to the label set / font auto-shrink. Was a hardcoded 175/330.
      // TOP margin is COMPUTED (TOP_MARGIN) to exactly fit the title + the tallest legend box + gaps,
      // so the title never clips and the key boxes always sit fully inside the margin (not in a lane).
      // Right margin holds a small buffer so the rightmost glyphs/diamonds aren't clipped at the edge.
      margin: { l: MARGIN_L, r: 60, t: TOP_MARGIN, b: 46 },
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
      // Glyph key: VERTICAL stack, solid white fill + black box. BOTTOM-anchored at LEG_BOT_Y
      // so the box grows UP into the margin and never spills into a lane. RIGHT-anchored
      // (x:1.0, xanchor:"right") per bravo-timeline-layout: pinned to the plot's right edge, the
      // legend grows leftward and can never overlap the LEFT-anchored title/subtitle at ANY width.
      // This makes the old DOM-width measurement + plotly_afterplot resize hook unnecessary.
      legend: { orientation: "v", x: 1.0, xanchor: "right", y: LEG_BOT_Y, yanchor: "bottom",
                font: { size: 11.5 }, bgcolor: "rgba(255,255,255,0.96)",
                bordercolor: "#1a1a1a", borderwidth: 1.5,
                itemsizing: "constant", tracegroupgap: 2 },
      // Title sits ABOVE the legend boxes (TITLE_Y, top-anchored), inside the computed top margin, so
      // its two lines always clear the legend top and are never cut off at the figure edge.
      title: { text: `<b>Biomarker Data Timeline</b><br><span style="font-size:13px;color:#777">${sub}</span>`,
               x: 0.012, xanchor: "left", y: TITLE_Y, yanchor: "top", font: { size: 26, color: "#1a1a1a" } },
      // DYNAMIC time gridlines: no fixed dtick, so Plotly auto-picks the tick interval for the
      // current zoom (year/month -> week -> day -> 6 h -> hour) and REDRAWS on every zoom/pan. The
      // gridlines span the whole single y-axis, so they carry through every neural lane + pain +
      // stim. Darker than the old faint shapes per the request.
      // Default x-range covers the FULL data span with a small buffer on each end so the first/last
      // glyphs (e.g. the rightmost modeled diamonds) are never clipped at the plot edge. The right
      // buffer is a touch larger than the left. Span is in epoch-seconds; D() makes the axis dates.
      xaxis: { range: [D(t0 - (t1 - t0) * 0.01), D(t1 + (t1 - t0) * 0.03)], type: "date", autorange: false,
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

    // Zoom-adaptive TD block widths: keep every TD coverage rect at least MIN_TD_PX wide on screen
    // (so a short stream stays visible like a raster tick when zoomed OUT), but never wider than its
    // true dur_s (so it renders its real length when zoomed IN). Recomputed on each zoom/pan from the
    // live x-range; one batched Plotly.relayout, no React re-render -> negligible overhead. This is
    // what removes the "fake-out" where a 30 s session looked like it spanned days.
    const MIN_TD_PX = 6;
    const applyTdWidths = () => {
      const rects = tdRectsRef.current;
      if (!rects || !rects.length || !gd._fullLayout || !gd._fullLayout.xaxis) return;
      const xa = gd._fullLayout.xaxis;
      const rng = xa.range;                       // [ms-or-date, ...] in the axis' coordinate space
      const x0ms = new Date(rng[0]).getTime(), x1ms = new Date(rng[1]).getTime();
      const plotPx = (xa._length || gd._fullLayout.width || 1000);
      const sPerPx = ((x1ms - x0ms) / 1000) / Math.max(plotPx, 1);   // seconds of data per pixel
      const floorS = MIN_TD_PX * sPerPx;          // min block width expressed in seconds
      const upd = {};
      rects.forEach(({ i, ts, dur_s }) => {
        const wS = Math.max(dur_s || 0, floorS);  // true length, or the pixel floor if shorter
        upd[`shapes[${i}].x1`] = toDate(ts + wS);
      });
      Plotly.relayout(gd, upd);
    };
    applyTdWidths();                              // set correct widths for the initial view

    // Zoom-adaptive LSB band-power rescale: when zoomed into a time window, refit each lane's
    // band-power mini-axis to the data IN VIEW, using a robust 1st–99th-percentile window so a
    // single spike/dropout can't compress the trend. At (or near) full span, fall back to the lane's
    // global window so the default look is identical to before. Restyles only the affected traces'
    // y arrays + the two LSB tick numbers — one batched Plotly.restyle/relayout, no React re-render.
    // The 3-left + 3-right row structure is untouched: this only remaps Y WITHIN each lane's band.
    const FULL_SPAN_S = Math.max(t1 - t0, 1);
    const applyLsbScales = () => {
      const lanes = lsbScaleRef.current;
      if (!lanes || !lanes.length || !gd._fullLayout || !gd._fullLayout.xaxis) return;
      const xa = gd._fullLayout.xaxis;
      const rng = xa.range;
      const vLo = new Date(rng[0]).getTime() / 1000;   // visible window in epoch SECONDS
      const vHi = new Date(rng[1]).getTime() / 1000;
      // "Zoomed in" = the visible window is meaningfully narrower than the full span. At full view we
      // keep the global window so nothing shifts from the original rendering.
      const zoomedIn = (vHi - vLo) < 0.985 * FULL_SPAN_S;
      const tyVals = [], tyIdx = [], annUpd = {};
      lanes.forEach((L) => {
        let lo = L.full_lo, hi = L.full_hi;
        if (zoomedIn) {
          const vis = L.samples.filter((p) => p.v != null && p.t >= vLo && p.t <= vHi).map((p) => p.v);
          const w = robustWindow(vis, 1, 99);
          if (w) { lo = w[0]; hi = w[1]; }   // else: not enough visible points -> keep global window
        }
        const span = (hi - lo) + 1e-9;
        const sc = (v) => (v == null ? null
          : L.BP_LO + (L.BP_HI - L.BP_LO) * Math.min(Math.max((v - lo) / span, 0), 1));
        L.traces.forEach((tr) => { tyVals.push(tr.raw.map(sc)); tyIdx.push(tr.idx); });
        if (L.tickHiIdx != null) annUpd[`annotations[${L.tickHiIdx}].text`] = `${Math.round(hi)}`;
        if (L.tickLoIdx != null) annUpd[`annotations[${L.tickLoIdx}].text`] = `${Math.round(lo)}`;
      });
      if (tyIdx.length) Plotly.restyle(gd, { y: tyVals }, tyIdx);
      if (Object.keys(annUpd).length) Plotly.relayout(gd, annUpd);
    };
    applyLsbScales();                             // set correct LSB scaling for the initial view

    const onRelayout = (ev) => {
      // Only react to x-range changes (zoom/pan/autorange), not to our own shape edits or y/legend.
      if (!ev) return;
      const touchedX = Object.keys(ev).some((k) => k.indexOf("xaxis") === 0) || ev.autosize;
      if (touchedX) { applyTdWidths(); applyLsbScales(); }
    };
    gd.on("plotly_relayout", onRelayout);
    // No resize hook: the legend is right-anchored and the Hz key left-anchored, so collision-
    // freedom holds at every width by construction — nothing to recompute on resize.
    return () => {
      try { gd.removeListener("plotly_relayout", onRelayout); } catch (e) { /* noop */ }
    };
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
