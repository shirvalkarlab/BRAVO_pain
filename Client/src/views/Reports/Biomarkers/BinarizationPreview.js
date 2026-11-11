/**
 * BinarizationPreview — live histogram of WHICH NEURAL DATA IS AVAILABLE TO BINARIZE at the current
 * PRO<->PSD match window, with the strategy's high/low cuts and class counts overlaid.
 *
 * PRIMARY (matched) mode — when the parent supplies a `scanModel` (built client-side from
 * availability.psd_scan_index, the PSDs the exploratory scan pools): the histogram plots the pain
 * values of the MATCHED PSD samples — i.e. exactly the band-power readings that feeds the binarized
 * biomarker at this window — and RECOLORS + RECOUNTS LIVE as the match-window slider moves (no
 * backend recompute). Moving the slider visibly changes how much data feeds binarization. The
 * counts are verified identical to the backend `matched_sample_counts`.
 *
 * FALLBACK (daily) mode — when no scanModel is available (e.g. demo data): the legacy behavior,
 * histogramming the daily-mean PRO distribution. Kept so the card degrades gracefully.
 *
 * Sits in the top controls card alongside the strategy selector so the user SEES exactly which
 * band-power readings will be labeled high vs low BEFORE clicking "Start exploratory analysis".
 *
 * Design notes (publication-quality, colorblind-safe):
 *   * The shared pain colours (dataColors.PAIN): low blue, high vermillion, the middle light grey.
 *   * Histogram is a single trace with per-bin marker colors, so the high/low/excluded classes
 *     are visually contiguous (no gap artifacts from three separate overlaid histograms).
 *   * Cut lines + percentile labels above the plot area; class-count badges as in-plot annotations.
 */

import { useMemo, useEffect, useRef } from "react";
import Plotly from "plotly.js-dist";
import Slider from "@mui/material/Slider";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import { T, TYPE, STATE } from "assets/theme/base/tokens";
import { textInk } from "assets/theme/base/dataColors";
import { plotlyLayout, PLOTLY_CONFIG, REF_LINE } from "views/Reports/figureStyle";

import { BIN_LO as LO, BIN_HI as HI, BIN_MID as MID, computeCuts as computeCutsShared,
  classBalanceFlag } from "./binarizationModel";
import { MATCHING_DEFAULTS } from "./matchingDefaults";

// Text colours (the redesign of 2026-09-26, SPEC.md section 2): the bars keep the pain colours
// (marks only); any word in a pain colour takes its text-safe variant, and the middle third's words
// take the lightest allowed grey.
const SUBTLE = T.ink3;
const MID_TEXT = T.ink3;
const HI_TEXT = textInk(HI);
const LO_TEXT = textInk(LO);

// Daily-mode (legacy fallback) cuts: the shared, backend-faithful computeCuts for the numeric
// values, with the same UI percentile/strategy labels matchedCuts (below) attaches to the
// matched-mode cuts -- one cut-computation implementation for both modes instead of two.
function computeCuts(vals, strategy, lowPct, highPct) {
  const c = computeCutsShared(vals, strategy, lowPct, highPct);
  if (c.kind === "two-cut") {
    return { ...c,
      lowLabel: `${(strategy === "tertile" ? 33.3 : lowPct).toFixed(0)}th pct`,
      highLabel: `${(strategy === "tertile" ? 66.7 : highPct).toFixed(0)}th pct` };
  }
  if (c.kind === "one-cut") {
    return { ...c, label: strategy === "median" ? "median (50th pct)" : "Midpoint between two clusters (preview)" };
  }
  return c;
}

// Integer-valued pain metrics: NRS and the count-like sums are reported on an integer scale, so the
// histogram must use width-1 bins CENTERED ON the integers (edges at k-0.5) — otherwise fractional
// bins sit between the integer tick labels and a bar over "8" doesn't land on 8.
const INTEGER_METRICS = new Set(["nrs", "mpq_sum", "npq_sum", "mpq_aff", "mpq_sen"]);
// Wide continuous metrics (0–100 VAS-style).
const WIDE_BIN_METRICS = new Set(["vas", "left_leg_vas", "back_vas"]);
function isIntegerMetric(metricKey, vals) {
  if (metricKey && INTEGER_METRICS.has(metricKey)) return true;
  // Fallback: treat as integer if every finite value is (near-)integer.
  return vals.length > 0 && vals.every((v) => Math.abs(v - Math.round(v)) < 1e-9);
}
function binWidthForMetric(metricKey, vmin, vmax) {
  if (metricKey && WIDE_BIN_METRICS.has(metricKey)) return 2;
  const span = (Number.isFinite(vmax) && Number.isFinite(vmin)) ? vmax - vmin : 0;
  return span > 15 ? 2 : 0.5;
}

function BinarizationPreview({ points, dailyAgg, strategy, percentileLow, percentileHigh,
                               metricLabel, metricKey, loading, totalReports,
                               matchTolerance, matchDirty,
                               scanModel, matchedLoading,
                               setPercentileLow, setPercentileHigh, setStrategy }) {
  const ref = useRef(null);
  // The match-window control itself moved to the card's top band (MatchWindowBand, option C); this
  // panel only needs to know whether a window is in force to explain an empty match.
  const hasTolControl = Number.isFinite(Number(matchTolerance)) && Number(matchTolerance) > 0;

  // Aggregate the raw PRO reports to ONE value per calendar day — the legacy daily-mode fallback.
  const dayAgg = useMemo(() => {
    if (Array.isArray(dailyAgg)) {
      return dailyAgg
        .filter((d) => d && typeof d.mean === "number" && Number.isFinite(d.mean))
        .map((d) => ({ day: String(d.day).slice(0, 10),
                       mean: d.mean,
                       nSamples: Number.isFinite(d.n_samples) ? d.n_samples : (d.nSamples || 1) }))
        .sort((a, b) => (a.day < b.day ? -1 : 1));
    }
    const byDay = {};
    for (const p of points || []) {
      const v = p && p.v;
      if (typeof v !== "number" || !Number.isFinite(v)) continue;
      const day = p.t ? String(p.t).slice(0, 10) : null;
      if (!day) continue;
      (byDay[day] = byDay[day] || { sum: 0, n: 0 });
      byDay[day].sum += v; byDay[day].n += 1;
    }
    return Object.keys(byDay).sort().map((day) => ({
      day, mean: byDay[day].sum / byDay[day].n, nSamples: byDay[day].n,
    }));
  }, [points, dailyAgg]);

  // PRIMARY: when the live matched-scan model carries matched PSDs, the histogram is of the MATCHED
  // PSD pain values (the data that actually feeds binarization at this window). Otherwise fall back
  // to the daily-PRO distribution.
  const matchedMode = !!(scanModel && scanModel.matchedValues && scanModel.matchedValues.length > 0);
  const counts = scanModel ? scanModel.counts : null;
  // Match-direction-aware framing constants. PRO-first leads with pain ratings as the unit of
  // independence; PSD-first (nearest/prior) leads with the band-power reading count. `su` is the
  // survey-usage block carried on counts (n_pro_total, n_pro_used, pct_pro_used, depth stats).
  const su = counts && counts.survey_usage;
  const dir = (counts && counts.match_direction) || MATCHING_DEFAULTS.matchDirection;

  const dailyVals = useMemo(() => dayAgg.map((d) => d.mean), [dayAgg]);
  const dailyCuts = useMemo(() => computeCuts(dailyVals, strategy, percentileLow, percentileHigh),
                            [dailyVals, strategy, percentileLow, percentileHigh]);
  // In matched mode, attach pct labels to the model's cuts (which carry only numeric cut values).
  const matchedCuts = useMemo(() => {
    if (!matchedMode) return null;
    const c = scanModel.cuts;
    if (c.kind === "two-cut") {
      return { ...c,
        lowLabel: `${(strategy === "tertile" ? 33.3 : percentileLow).toFixed(0)}th pct`,
        highLabel: `${(strategy === "tertile" ? 66.7 : percentileHigh).toFixed(0)}th pct` };
    }
    if (c.kind === "one-cut") return { ...c, label: strategy === "median" ? "median (50th pct)" : "Midpoint between two clusters" };
    return c;
  }, [matchedMode, scanModel, strategy, percentileLow, percentileHigh]);

  const vals = matchedMode ? scanModel.matchedValues : dailyVals;
  const cuts = matchedMode ? matchedCuts : dailyCuts;
  const hasFigure = vals.length > 0;

  // Legacy day/sample class counts (daily mode only).
  const dailyStats = useMemo(() => {
    const zero = { nLowDays: 0, nHighDays: 0, nMidDays: 0, nLowSamp: 0, nHighSamp: 0, nMidSamp: 0 };
    if (!dayAgg.length || dailyCuts.kind === "none") return zero;
    const acc = { ...zero };
    for (const d of dayAgg) {
      let cls;
      if (dailyCuts.kind === "two-cut") {
        cls = d.mean <= dailyCuts.lowCut ? "low" : (d.mean >= dailyCuts.highCut ? "high" : "mid");
      } else {
        cls = d.mean <= dailyCuts.cut ? "low" : "high";
      }
      if (cls === "low") { acc.nLowDays++; acc.nLowSamp += d.nSamples; }
      else if (cls === "high") { acc.nHighDays++; acc.nHighSamp += d.nSamples; }
      else { acc.nMidDays++; acc.nMidSamp += d.nSamples; }
    }
    return acc;
  }, [dayAgg, dailyCuts]);

  // Decision 337 (the PI, 2026-09-27): warn when the high/low split is too small or too lopsided
  // to trust, in the same units the "Split -> N high / N low" line already shows.
  const balanceFlag = matchedMode
    ? classBalanceFlag(counts.n_low, counts.n_high)
    : classBalanceFlag(dailyStats.nLowDays, dailyStats.nHighDays);

  useEffect(() => {
    if (!ref.current) return;
    if (!vals.length) { Plotly.purge(ref.current); return; }
    const rawMin = Math.min(...vals), vmax = Math.max(...vals);
    const integerMode = isIntegerMetric(metricKey, vals);
    let edges, binW;
    if (integerMode) {
      // Width-1 bins centered on integers: edges at k-0.5 so a bar over "8" means the value 8.
      const lo = Math.round(rawMin), hi = Math.round(vmax);
      binW = 1;
      edges = Array.from({ length: (hi - lo) + 2 }, (_, i) => lo - 0.5 + i);
    } else {
      const BIN_W = binWidthForMetric(metricKey, rawMin, vmax);
      const vmin = Math.floor(rawMin / BIN_W) * BIN_W;
      binW = BIN_W;
      const nBins = Math.max(1, Math.min(500, Math.ceil((vmax - vmin) / binW) || 1));
      edges = Array.from({ length: nBins + 1 }, (_, i) => vmin + i * binW);
      // For continuous metrics, inject the cut value(s) as bin edges so NO bar straddles a threshold
      // (a straddling bar would be painted one color while containing two classes — see eng review).
      const cutEdges = cuts.kind === "two-cut" ? [cuts.lowCut, cuts.highCut]
        : (cuts.kind === "one-cut" ? [cuts.cut] : []);
      for (const ce of cutEdges) {
        if (Number.isFinite(ce) && ce > edges[0] && ce < edges[edges.length - 1] && !edges.includes(ce)) edges.push(ce);
      }
      edges = [...new Set(edges)].sort((a, b) => a - b);
    }
    const nBins = edges.length - 1;
    const cnt = new Array(nBins).fill(0);
    for (const v of vals) {
      // binary-search the bin whose [edge_i, edge_{i+1}) contains v
      let i = 0;
      while (i < nBins - 1 && v >= edges[i + 1]) i += 1;
      cnt[i] += 1;
    }
    const centers = cnt.map((_, i) => (edges[i] + edges[i + 1]) / 2);

    // Per-bar provenance for the hover (matched mode only). Re-bin the matched samples into the SAME
    // edges and, per bar, tally: distinct calendar days, the TD split (BrainSense / Indefinite /
    // Montage) and the PSD split (Patient-trigger / other). Every sample the scan pools is either
    // Welch'd from a recording's own time-domain signal (BrainSense and Indefinite streaming AND the
    // montage/survey recordings -- a montage row is Welch over the recording's `Data`) or the device's
    // own patient-event snapshot -- so the two groups below are TD vs PSD. Until 2026-09-26 the
    // montage sat under PSD here; it is TD (the PI).
    const binOf = (v) => { let i = 0; while (i < nBins - 1 && v >= edges[i + 1]) i += 1; return i; };
    const srcGroup = (src) => {
      const s = String(src || "").toLowerCase();
      if (s.indexOf("brainsense") >= 0 || (s.indexOf("td") >= 0 && s.indexOf("stream") >= 0)) return ["td", "BrainSense"];
      if (s.indexOf("indefinite") >= 0) return ["td", "Indefinite"];
      if (s.indexOf("montage") >= 0 || s.indexOf("survey") >= 0) return ["td", "Montage"];
      if (s.indexOf("patient") >= 0 || s.indexOf("event") >= 0) return ["psd", "Patient-trigger"];
      return ["psd", "Other"];
    };
    const barProv = matchedMode
      ? (() => {
          const z = () => ({ days: new Set(),
                             td: { BrainSense: 0, Indefinite: 0, Montage: 0 },
                             psd: { "Patient-trigger": 0, Other: 0 } });
          const acc = Array.from({ length: nBins }, z);
          for (const s of (scanModel.samples || [])) {
            if (s.v == null || !Number.isFinite(s.v) || s.bin === "unmatched") continue;
            const bi = binOf(s.v);
            if (bi < 0 || bi >= nBins) continue;
            const day = Number.isFinite(s.t) ? new Date(s.t * 1000).toISOString().slice(0, 10) : null;
            if (day) acc[bi].days.add(day);
            const [grp, label] = srcGroup(s.source);
            if (acc[bi][grp] && acc[bi][grp][label] != null) acc[bi][grp][label] += 1;
          }
          return acc;
        })()
      : null;

    let colors;
    if (cuts.kind === "two-cut") {
      colors = centers.map((c) => (c <= cuts.lowCut ? LO : (c >= cuts.highCut ? HI : MID)));
    } else if (cuts.kind === "one-cut") {
      colors = centers.map((c) => (c <= cuts.cut ? LO : HI));
    } else {
      colors = centers.map(() => LO);
    }
    // Per-bar widths (continuous mode can have uneven cut-snapped bins).
    const widths = cnt.map((_, i) => (edges[i + 1] - edges[i]) * 0.96);
    const shapes = [];
    const annotations = [];
    // Cut lines are DISPLAY-ONLY dashed notches at the current thresholds — the percentile cut points
    // are set by the two-handle range slider above the histogram (see JSX), not by dragging in-plot.
    // The notch + its percentile label simply mirror the slider's current low/high.
    const pushCutLine = (x, label, color, yLevel = 1.04, xanchor = "center") => {
      shapes.push({ type: "line", xref: "x", yref: "paper", x0: x, x1: x, y0: 0, y1: 1,
                    line: { color, width: 2, dash: "dash" } });
      annotations.push({ x, yref: "paper", y: yLevel, xanchor, yanchor: "bottom",
                         text: `${x.toFixed(1)} (${label})`, showarrow: false,
                         font: { size: 12, color: textInk(color) } });
    };
    if (cuts.kind === "two-cut") {
      pushCutLine(cuts.lowCut, cuts.lowLabel, LO, 1.02, "right");
      pushCutLine(cuts.highCut, cuts.highLabel, HI, 1.13, "left");
      shapes.push({ type: "rect", xref: "x", yref: "paper", x0: cuts.lowCut, x1: cuts.highCut,
                    y0: 0, y1: 1, fillcolor: MID, opacity: 0.10, line: { width: 0 } });
    } else if (cuts.kind === "one-cut") {
      pushCutLine(cuts.cut, cuts.label, T.ink, 1.04, "center");
    }

    // Class-count badges. In matched mode the unit is matched NEURAL SAMPLES (the band-power readings that
    // feeds binarization); in daily mode it is calendar days + the raw reports they carry.
    //
    // EACH BADGE CARRIES ONLY ITS ESSENTIAL COUNT (the PI, 2026-09-27: these boxes ran off the
    // screen). Until this fix each also appended the per-group TD/montage/PSD modality breakdown,
    // which could run to a second full line; that breakdown stays available on hover (the
    // hovertemplate below still carries it), so nothing is lost, only shortened here. The badges are
    // floated into y-axis HEADROOM (the matched-mode yaxis range is extended below) so they sit ABOVE
    // the tallest bar and never overlap the histogram.
    const yMax = cnt.length ? Math.max(1, ...cnt) : 1;
    const badge = (xRel, yRel, color, label, primary, secondary) => ({
      xref: "paper", yref: "paper", x: xRel, y: yRel, xanchor: "center", yanchor: "top",
      text: `<b>${label}</b><br>${primary}${secondary ? `<br>${secondary}` : ""}`,
      showarrow: false, align: "center",
      // Ink on white with a border in the group's colour (white text on vermillion or the light
      // grey of the middle third fell below 4.5:1).
      font: { size: 12, color: T.ink },
      bgcolor: T.surface, bordercolor: color, borderwidth: 1.5, borderpad: 4, opacity: 1,
    });
    // Signpost-badge copy. In matched mode the FRAMING follows the match-direction toggle:
    //   pro_first   -- leads with the PRO count (units of independence), then PSDs as supporting
    //                  detail. Matches the headline caption's framing.
    //   nearest/prior (PSD-first) -- leads with the PSD count, then PROs as supporting detail.
    // Unmatched-mode (daily PRO distribution) still shows days + raw samples as before.
    //
    // PRO counts come from rating_group via the matched-sample bin → which rating it belongs to.
    // Pre-compute unique-PRO counts per bin once on each render.
    const proIdxByBin = (matchedMode && Array.isArray(scanModel && scanModel.samples))
      ? (() => {
          const sets = { low: new Set(), high: new Set(), excluded: new Set() };
          for (const s of scanModel.samples) {
            if (s.proIdx != null && s.proIdx >= 0 && sets[s.bin]) sets[s.bin].add(s.proIdx);
          }
          return { low: sets.low.size, high: sets.high.size, excluded: sets.excluded.size };
        })()
      : { low: 0, high: 0, excluded: 0 };
    const proFirst = matchedMode && dir === "pro_first";
    const psdLine = (n) => `${(n || 0).toLocaleString()} band-power reading${n === 1 ? "" : "s"}`;
    const proLine = (n) => `${(n || 0).toLocaleString()} pain rating${n === 1 ? "" : "s"}`;
    const lowTxt = matchedMode
      ? (proFirst ? [proLine(proIdxByBin.low), psdLine(counts.n_low)]
                  : [psdLine(counts.n_low), proLine(proIdxByBin.low)])
      : [`${dailyStats.nLowDays.toLocaleString()} days`, `${dailyStats.nLowSamp.toLocaleString()} samples`];
    const highTxt = matchedMode
      ? (proFirst ? [proLine(proIdxByBin.high), psdLine(counts.n_high)]
                  : [psdLine(counts.n_high), proLine(proIdxByBin.high)])
      : [`${dailyStats.nHighDays.toLocaleString()} days`, `${dailyStats.nHighSamp.toLocaleString()} samples`];
    const midTxt = matchedMode
      ? (proFirst ? [proLine(proIdxByBin.excluded), psdLine(counts.n_excluded_middle)]
                  : [psdLine(counts.n_excluded_middle), proLine(proIdxByBin.excluded)])
      : [`${dailyStats.nMidDays.toLocaleString()} days`, `${dailyStats.nMidSamp.toLocaleString()} samples`];
    if (cuts.kind === "two-cut") {
      if (matchedMode) {
        // Float Low/High in the headroom band; Excluded sits higher still, above the max line.
        annotations.push(badge(0.12, 0.80, LO, "Low", lowTxt[0], lowTxt[1]));
        annotations.push(badge(0.88, 0.80, HI, "High", highTxt[0], highTxt[1]));
        annotations.push(badge(0.50, 0.97, MID, "Left out (middle)", midTxt[0], midTxt[1]));
        // Dotted reference rule at the tallest-bar height — the Excluded badge's border sits above it.
        shapes.push({ type: "line", xref: "paper", yref: "y", x0: 0, x1: 1, y0: yMax, y1: yMax,
                      line: REF_LINE });
      } else {
        annotations.push(badge(0.10, 0.94, LO, "Low", lowTxt[0], lowTxt[1]));
        annotations.push({ ...badge(0.50, 0.02, MID, "Left out (middle)", midTxt[0], midTxt[1]),
                           yanchor: "bottom" });
        annotations.push(badge(0.90, 0.94, HI, "High", highTxt[0], highTxt[1]));
      }
    } else if (cuts.kind === "one-cut") {
      annotations.push(badge(0.18, matchedMode ? 0.84 : 0.94, LO, "Low", lowTxt[0], lowTxt[1]));
      annotations.push(badge(0.82, matchedMode ? 0.84 : 0.94, HI, "High", highTxt[0], highTxt[1]));
    }

    const yTitle = matchedMode ? "Matched band-power readings" : "Days";
    const hoverUnit = matchedMode ? "samples" : "days";
    // Hover: in matched mode, lead with the calendar-day count for the bar (the unit the reviewer
    // cares about — how many DAYS contribute), then the time-domain source split (BrainSense /
    // Indefinite / Montage) and the PSD split (Patient-trigger / other). customdata carries
    // the pre-rendered breakdown lines so the hovertemplate stays declarative.
    const className = (c) => (cuts.kind === "two-cut")
      ? (c <= cuts.lowCut ? "Low pain" : (c >= cuts.highCut ? "High pain" : "Left out (middle)"))
      : (cuts.kind === "one-cut" ? (c <= cuts.cut ? "Low pain" : "High pain") : "");
    let traces;
    if (matchedMode && barProv) {
      const fmtGrp = (obj) => {
        const parts = Object.entries(obj).filter(([, n]) => n > 0)
          .map(([k, n]) => `${k} ${n.toLocaleString()}`);
        return parts.length ? parts.join(" · ") : "none";
      };
      const customdata = centers.map((c, i) => {
        const p = barProv[i];
        const nDays = p ? p.days.size : 0;
        const tdN = p ? (p.td.BrainSense + p.td.Indefinite + p.td.Montage) : 0;
        const psdN = p ? (p.psd["Patient-trigger"] + p.psd.Other) : 0;
        return [
          nDays.toLocaleString(),                          // 0: distinct days (pinned on top)
          className(c),                                    // 1: class label
          tdN.toLocaleString(), p ? fmtGrp(p.td) : "not given",    // 2,3: TD total + split
          psdN.toLocaleString(), p ? fmtGrp(p.psd) : "not given",  // 4,5: PSD total + split
        ];
      });
      traces = [{
        x: centers, y: cnt, type: "bar",
        marker: { color: colors, line: { width: 0 } }, opacity: 0.88, width: widths,
        customdata,
        hovertemplate:
          "<b>%{customdata[0]} days</b> · %{y:,} samples<br>"
          + `${metricLabel || "pain"} ≈ %{x:.1f}  ·  %{customdata[1]}<br>`
          + "TD (%{customdata[2]}): %{customdata[3]}<br>"
          + "PSD (%{customdata[4]}): %{customdata[5]}"
          + "<extra></extra>",
      }];
    } else {
      traces = [{
        x: centers, y: cnt, type: "bar",
        marker: { color: colors, line: { width: 0 } }, opacity: 0.88, width: widths,
        hovertemplate: `${metricLabel || "pain"}=%{x:.1f}<br>%{y:,} ${hoverUnit}<extra></extra>`,
      }];
    }
    const layout = plotlyLayout({
      // Preserve any zoom the user applied to the histogram across live recolors; reset only when
      // the metric changes (different value domain).
      uirevision: `hist-${metricKey || "metric"}`,
      margin: { l: 56, r: 16, t: 80, b: 44 },
      bargap: 0.02,
      xaxis: { title: { text: metricLabel || "Pain score" } },
      yaxis: { title: { text: yTitle },
               // Matched mode: extend the range to ~1.6x the tallest bar so the floated per-group
               // detail badges (Low/High at ~0.80 paper, Excluded at ~0.97) clear the bars cleanly.
               ...(matchedMode && cuts.kind === "two-cut" ? { range: [0, yMax * 1.6] } : {}) },
      shapes, annotations,
    });
    // The percentile cut points are set by the two-handle RANGE SLIDER rendered ABOVE the histogram
    // (see the JSX below), NOT by dragging inside the plot. Plotly's `edits.shapePosition` is a single
    // boolean with no per-axis constraint — a shape drag moves in x AND y and can resize the line — so
    // in-plot editing is DISABLED here and the cut lines are display-only dashed notches at the current
    // thresholds. This removes the broken vertical-drag/resize behavior and keeps the slider as the one
    // source of truth for percentileLow/High.
    Plotly.react(ref.current, traces, layout, { ...PLOTLY_CONFIG, edits: { shapePosition: false } });
    // Defensive: drop any stale relayout drag handler from an earlier render of this component.
    const gd = ref.current;
    if (gd && gd.removeAllListeners) gd.removeAllListeners("plotly_relayout");
    // NOTE: no per-run Plotly.purge cleanup here. Purging before each re-run destroys the graph div,
    // which defeats the `uirevision: hist-${metricKey}` set below — the user's histogram zoom would
    // reset on every match-window / strategy drag. Plotly.react diffs in place, so the live recolor
    // works without a purge; we purge only on unmount (separate effect below), mirroring
    // BiomarkerDataTimeline's deliberate same pattern.
  // scanModel added: proIdxByBin reads scanModel.samples; omitting it caused stale per-bin
  // rating counts after scanModel rebuilt (e.g. matchDirection change) without other deps changing.
  }, [vals, cuts, dailyStats, counts, matchedMode, metricLabel, metricKey, scanModel]);

  // Purge ONCE on unmount only (not before every recompute) so zoom survives live recolors.
  useEffect(() => {
    const node = ref.current;
    return () => { if (node) Plotly.purge(node); };
  }, []);

  // Header caption — PRO-first by default (the discovery framing). For PSD-first modes (nearest /
  // prior) lead with the PSD-coverage number instead, so the headline matches the toggle.
  //
  // EVERY COUNT HERE IS FOR THE SELECTED SCORE, AND SAYS SO (PI, 2026-09-10). Not every report
  // answers every score: on RCS08 there are 764 reports, 764 with an NRS value and 599 with a
  // Left Leg VAS value. The caption used to read "599 PRO reports across 315 days" with no score
  // named, so next to a record of 764 it looked like a stale number that had not updated -- and
  // because several scores share a count (NRS = VAS = Relief = 764; Left Leg = Back = 599),
  // switching between those visibly changed nothing. The score is now in the sentence and the
  // record total sits beside it, so a smaller count reads as "reports carrying this score".
  const scoreName = metricLabel || metricKey || "this score";
  const totalTxt = Number.isFinite(totalReports) && totalReports > 0
    ? ` · ${totalReports.toLocaleString()} reports in the record` : "";
  const headerCaption = matchedMode
    ? (dir === "pro_first" && su
        ? `${(su.n_pro_used || 0).toLocaleString()} of ${(su.n_pro_total || 0).toLocaleString()} ${scoreName} reports paired with band-power readings at ±${matchTolerance} min (${su.pct_pro_used}%)${totalTxt}`
        : `${(counts.n_matched || 0).toLocaleString()} of ${(counts.n_sessions || 0).toLocaleString()} band-power readings paired with a ${scoreName} report at ±${matchTolerance} min${totalTxt}`)
    : (vals.length
        ? `${dayAgg.reduce((s, d) => s + d.nSamples, 0).toLocaleString()} ${scoreName} reports across ${vals.length.toLocaleString()} days${totalTxt}`
        : ((loading || matchedLoading) ? "loading…" : "no data yet"));

  // Footer caption.
  // Full range of the per-rating match offsets (same |Δt| distribution as the median). Appended ONLY
  // to the "X of Y pain reports … median match offset" line below, per PI — not the other offset texts.
  const rangeTxt = (counts && counts.min_abs_offset_min != null && counts.max_abs_offset_min != null)
    ? ` (range ${counts.min_abs_offset_min.toFixed(1)} to ${counts.max_abs_offset_min.toFixed(1)} min)`
    : "";
  const offsetSummary = (counts && counts.median_abs_offset_min != null)
    ? ` · median match offset ${counts.median_abs_offset_min.toFixed(1)} min.` : ".";
  const footerCaption = (() => {
    if (matchedMode) {
      if (cuts.kind === "two-cut") {
        // When the matched values are too few / too discrete (integer NRS) to form a middle tertile,
        // the excluded-middle bin is empty by construction — say so, so the missing grey isn't a mystery.
        const emptyMiddle = (counts.n_excluded_middle || 0) === 0;
        const offsetTxt = offsetSummary;
        if (emptyMiddle) {
          return `Cut at ${cuts.lowCut?.toFixed(1)} / ${cuts.highCut?.toFixed(1)} — no excluded-middle bin: ` +
            `the matched values are too discrete (e.g. integer NRS) to form a middle tertile, so every matched sample is high or low` + offsetTxt;
        }
        return `Matched band-power readings cut at ${cuts.lowCut?.toFixed(1)} / ${cuts.highCut?.toFixed(1)} — ` +
          `${(counts.n_excluded_middle || 0).toLocaleString()} middle readings left out of training` + offsetTxt;
      }
      if (cuts.kind === "one-cut") {
        return `Matched band-power readings cut at ${cuts.cut?.toFixed(1)} — every matched sample is labeled (none excluded)` +
          offsetSummary;
      }
      return "No band-power reading matched a pain report at this window — widen the match window.";
    }
    if (cuts.kind === "two-cut") {
      return `Cuts on the daily distribution at ${cuts.lowCut?.toFixed(1)} / ${cuts.highCut?.toFixed(1)} — ` +
        `${dailyStats.nMidDays.toLocaleString()} days (${dailyStats.nMidSamp.toLocaleString()} raw samples) ` +
        `in the middle band excluded from training.`;
    }
    if (cuts.kind === "one-cut") {
      return `${strategy === "median" ? "Median" : "Two-cluster"} cut on the daily distribution at ${cuts.cut?.toFixed(1)} — every day is labeled (none excluded).`;
    }
    return "Adjust the strategy to preview the cut.";
  })();

  return (
    // With nothing to draw, the reserved figure space collapses to one sentence saying what would
    // fill it (taste audit C2, 2026-09-26); the plot div stays mounted, at no height, for Plotly.
    <MDBox display="flex" flexDirection="column"
      sx={{ width: "100%", height: hasFigure ? "100%" : "auto", minHeight: hasFigure ? 440 : 0 }}>
      <MDBox display="flex" flexDirection="row" justifyContent="space-between" alignItems="baseline" mb={0.25}>
        <MDTypography component="h3" sx={{ ...TYPE.body, fontWeight: 600, color: T.ink, m: 0 }}>
          {matchedMode ? "Readings available to split into high and low pain" : "Preview of the high / low pain split"}
        </MDTypography>
        {/* Matched mode: no grey caption here. It repeated the readout line below word for word
            (the PI, 2026-10-07: "delete the gray 673 of 3474 band power readings"). */}
        {matchedMode ? null : (
          <MDTypography variant="caption" sx={{ ...TYPE.body, color: T.ink3 }}>
            {headerCaption}
          </MDTypography>
        )}
      </MDBox>

      {/* Matched band-power reading readout — PRO-first leads the headline (units of independence),
          PSD coverage carries the supporting numbers; in PSD-first modes the order flips. The
          pool is mostly TD (streaming and montage recordings), so the count is broken down by source and
          uses the modality-neutral noun "band-power readings". aria-live announces updates to readers. */}
      {matchedMode && su ? (
        <MDTypography variant="caption" sx={{ ...TYPE.body, color: T.ink2, mb: 0.25 }}
                      aria-live="polite">
          {dir === "pro_first" ? (
            <>
              <b>{`${(su.n_pro_used || 0).toLocaleString()}`}</b>
              {` of ${(su.n_pro_total || 0).toLocaleString()} pain reports `}
              <b>{`(${su.pct_pro_used}%)`}</b>
              {` paired with band-power readings within ±${matchTolerance} min`}
              {Number.isFinite(counts.median_abs_offset_min)
                ? `, median match offset ${counts.median_abs_offset_min.toFixed(1)} min${rangeTxt}` : ""}
              {`. Each paired rating carries ${su.psd_per_pro_mean} band-power readings on average (median ${su.psd_per_pro_median}, max ${su.psd_per_pro_max}; cap ${(counts.max_per_rating || 3)}/channel).`}
            </>
          ) : (
            <>
              <b>{`${(counts.n_matched ?? 0).toLocaleString()}`}</b>
              {` of ${(counts.n_sessions ?? 0).toLocaleString()} band-power readings `}
              <b>{`(${counts.pct_psd_used != null ? counts.pct_psd_used + "%" : "not given"})`}</b>
              {` paired with a pain report within ±${matchTolerance} min`}
              {Number.isFinite(counts.median_abs_offset_min)
                ? `, median offset ${counts.median_abs_offset_min.toFixed(1)} min` : ""}
              {`. ${(su.n_pro_used || 0).toLocaleString()} of ${(su.n_pro_total || 0).toLocaleString()} pain reports (${su.pct_pro_used}%) received at least one band-power reading`}
              {su.n_pro_reused ? `; ${su.n_pro_reused} received >1.` : "."}
            </>
          )}
          {matchDirty ? <i style={{ color: SUBTLE, fontStyle: "normal" }}>{"  (live preview — recompute to score)"}</i> : null}
        </MDTypography>
      ) : null}
      {matchedMode ? (
        <MDTypography variant="caption" sx={{ ...TYPE.body, color: T.ink2, mb: 0.25, display: "block" }}
                      aria-live="polite">
          {`Split → `}
          <span style={{ color: HI_TEXT, fontWeight: 600 }}>{`${(counts.n_high ?? 0).toLocaleString()} high pain`}</span>
          {" / "}
          <span style={{ color: LO_TEXT, fontWeight: 600 }}>{`${(counts.n_low ?? 0).toLocaleString()} low pain`}</span>
          {counts.n_excluded_middle
            ? <span style={{ color: MID_TEXT }}>{` / ${counts.n_excluded_middle.toLocaleString()} middle (left out)`}</span>
            : null}
          {(counts.n_matched_td != null && counts.n_matched_td_montage != null && counts.n_matched > 0)
            ? <span style={{ color: SUBTLE }}>
                {`  · sources: ${counts.n_matched_td.toLocaleString()} TD (${(counts.n_matched_td - counts.n_matched_td_montage).toLocaleString()} streaming, ${counts.n_matched_td_montage.toLocaleString()} montage), ${(counts.n_matched_event || 0).toLocaleString()} PSD (patient event)`}
              </span>
            : null}
          {counts.n_capped_dropped
            ? <span style={{ color: SUBTLE }}>{` · ${counts.n_capped_dropped} band-power readings over the per-rating cap`}</span>
            : null}
        </MDTypography>
      ) : null}
      {balanceFlag ? (
        <MDTypography variant="caption" data-testid="class-balance-caution"
          sx={{ ...TYPE.body, color: STATE.caution.ink, mb: 0.25, display: "block" }}>
          <span aria-hidden="true" style={{ marginRight: 6 }}>{STATE.caution.glyph}</span>
          {balanceFlag}
        </MDTypography>
      ) : null}
      {matchedMode ? (
        <MDTypography variant="caption" sx={{ ...TYPE.body, color: T.ink3, mb: 0.25, display: "block" }}>
          {"Pooled: TD (up to 30 s around the rating) from streaming, montage and survey recordings, and PSD from patient events. "}
          {"The device's own band-power readings cover one band, not every frequency, so they are not pooled here."}
        </MDTypography>
      ) : (hasTolControl ? (
        // WHY THIS IS THREE MESSAGES AND NOT ONE. The card falls back to the daily pain-report
        // distribution whenever no band-power reading carries a pain label, and it used to explain that
        // fallback with a single sentence — "No PSD scan index available" — regardless of the
        // reason. That sentence is true in only one of the three cases, and in the case that
        // matters most it is actively wrong: when the scan index and the pain series are both
        // present and the match window is simply too narrow for anything to pair, the correct
        // statement is that ZERO of the available band-power readings reached a pain rating at this
        // window, which is a measured result the reader can fix by widening the window. Announcing
        // a missing input instead sends them looking for a data problem that does not exist. The
        // scan model now reports which situation it is in, so each gets its own sentence.
        <MDTypography variant="caption" sx={{ ...TYPE.body, color: T.ink2, mb: 0.25 }}>
          {(loading || matchedLoading)
            ? "Loading band-power reading availability…"
            : (scanModel && scanModel.matchable)
              ? `None of the ${(scanModel.counts && scanModel.counts.n_sessions) || 0} available `
                + `band-power readings fell within \u00b1${matchTolerance} min of a pain rating, so nothing `
                + "can be split into high and low pain at this window. Widen the match window above. The histogram "
                + "below has fallen back to the daily pain-report distribution, which is a "
                + "different quantity: it shows the pain scores themselves, not the band-power readings "
                + "they could label."
              : (scanModel && scanModel.unmatchableReason === "no_pain_series")
                ? "No pain reports are available for the selected metric, so no band-power reading can "
                  + "be labelled and matching was not attempted. This is an absence of pain data, "
                  + "not a finding about the band-power readings."
                : "The band-power reading index for this participant has not been loaded, so matching "
                  + "was not attempted and nothing here describes how much band-power readings could be "
                  + "split into high and low pain. The histogram below is the daily pain-report distribution."}
        </MDTypography>
      ) : null)}

      {/* Percentile cut control — ONE slider bar with TWO handles (low + high endpoints), sitting
          directly ABOVE the histogram so the dashed notch lines below track the handles. This is the
          single source of truth for the cut points (the in-plot lines are display-only). Shown in
          two-cut percentile/tertile mode when the parent supplies the setters. Dragging promotes a
          tertile preset to "percentile" (same as the old slider onChange) so the custom cuts persist. */}
      {(hasFigure && cuts.kind === "two-cut" && setPercentileLow && setPercentileHigh) ? (
        <MDBox sx={{ px: 1, pt: 0.5, pb: 0.25 }}>
          <MDBox display="flex" flexDirection="row" justifyContent="space-between" alignItems="baseline">
            <MDTypography variant="caption" sx={{ ...TYPE.body, fontWeight: 600, color: LO_TEXT }}>
              {`low: ${(strategy === "tertile" ? 33 : Number(Number(percentileLow).toFixed(1)))}th percentile and below`}
            </MDTypography>
            <MDTypography variant="caption" sx={{ ...TYPE.body, color: SUBTLE }}>
              {"drag the two handles to set the cuts"}
            </MDTypography>
            <MDTypography variant="caption" sx={{ ...TYPE.body, fontWeight: 600, color: HI_TEXT }}>
              {`high: ${(strategy === "tertile" ? 67 : Number(Number(percentileHigh).toFixed(1)))}th and above`}
            </MDTypography>
          </MDBox>
          <Slider
            value={[
              strategy === "tertile" ? 33 : percentileLow,
              strategy === "tertile" ? 67 : percentileHigh,
            ]}
            min={1} max={99} step={1} size="small" valueLabelDisplay="auto"
            disableSwap
            getAriaLabel={(i) => (i === 0 ? "low percentile cut" : "high percentile cut")}
            valueLabelFormat={(v) => `${v}th`}
            onChange={(e, v) => {
              if (!Array.isArray(v)) return;
              let [lo, hi] = v;
              // Keep a ≥1-pct gap so the cuts never cross (disableSwap holds order; this holds the gap).
              lo = Math.min(Math.max(Math.round(lo), 1), 98);
              hi = Math.max(Math.min(Math.round(hi), 99), lo + 1);
              if (strategy === "tertile" && setStrategy) setStrategy("percentile");
              setPercentileLow(lo);
              setPercentileHigh(hi);
            }}
            sx={{
              mt: 0.25,
              // Two-tone track: the selected (mid-band) range is neutral grey, rail faint.
              color: MID,
              "& .MuiSlider-thumb": { height: 16, width: 16 },
              // MUI stamps each thumb with data-index (0 = low, 1 = high) — color them to match the
              // low/high classes and the dashed notch lines below.
              "& .MuiSlider-thumb[data-index='0']": { backgroundColor: LO },
              "& .MuiSlider-thumb[data-index='1']": { backgroundColor: HI },
            }}
          />
        </MDBox>
      ) : null}

      <div ref={ref} data-testid="split-figure" data-empty={hasFigure ? "false" : "true"}
        style={hasFigure ? { flex: 1, width: "100%", minHeight: 340 } : { width: "100%", height: 0 }} />
      {hasFigure ? (
        <MDTypography variant="caption" sx={{ ...TYPE.body, color: T.ink3, textAlign: "center" }}>
          {footerCaption}
        </MDTypography>
      ) : (
        <MDTypography component="p" data-testid="split-empty"
          sx={{ ...TYPE.body, color: T.ink3, m: 0, mt: 0.5 }}>
          {(loading || matchedLoading)
            ? "The histogram of the high and low pain split appears here once the pain reports have loaded."
            : `The histogram of the high and low pain split appears here once there are ${scoreName} reports to split.`}
        </MDTypography>
      )}
    </MDBox>
  );
}

export default BinarizationPreview;
