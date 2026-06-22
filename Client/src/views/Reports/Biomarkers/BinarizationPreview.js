/**
 * BinarizationPreview — live histogram of WHICH NEURAL DATA IS AVAILABLE TO BINARIZE at the current
 * PRO<->PSD match window, with the strategy's high/low cuts and class counts overlaid.
 *
 * PRIMARY (matched) mode — when the parent supplies a `scanModel` (built client-side from
 * availability.psd_scan_index, the PSDs the exploratory scan pools): the histogram plots the pain
 * values of the MATCHED PSD samples — i.e. exactly the neural data that feeds the binarized
 * biomarker at this window — and RECOLORS + RECOUNTS LIVE as the match-window slider moves (no
 * backend recompute). Moving the slider visibly changes how much data feeds binarization. The
 * counts are verified identical to the backend `matched_sample_counts`.
 *
 * FALLBACK (daily) mode — when no scanModel is available (e.g. demo data): the legacy behavior,
 * histogramming the daily-mean PRO distribution. Kept so the card degrades gracefully.
 *
 * Sits in the top controls card alongside the strategy selector so the user SEES exactly which
 * neural samples will be labeled high vs low BEFORE clicking "Start exploratory analysis".
 *
 * Design notes (publication-quality, colorblind-safe):
 *   * Okabe-Ito palette — LO=#0072B2 (blue), HI=#D55E00 (vermillion), MID=#7E8794 (grey).
 *   * Histogram is a single trace with per-bin marker colors, so the high/low/excluded classes
 *     are visually contiguous (no gap artifacts from three separate overlaid histograms).
 *   * Cut lines + percentile labels above the plot area; class-count badges as in-plot annotations.
 */

import { useMemo, useEffect, useRef } from "react";
import Plotly from "plotly.js-dist";
import Slider from "@mui/material/Slider";
import TextField from "@mui/material/TextField";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import { BIN_LO as LO, BIN_HI as HI, BIN_MID as MID } from "./binarizationModel";

// Lightweight percentile (linear interpolation, q in 0..100) over a finite-value array.
function percentile(values, q) {
  if (!values || values.length === 0) return null;
  const a = [...values].sort((x, y) => x - y);
  const idx = (q / 100) * (a.length - 1);
  const lo = Math.floor(idx), hi = Math.ceil(idx);
  if (lo === hi) return a[lo];
  return a[lo] + (a[hi] - a[lo]) * (idx - lo);
}

// Compute cuts given strategy + percentile state (legacy daily-mode fallback only; matched mode
// takes its cuts straight from the scanModel so they are byte-identical to the backend labeler).
function computeCuts(vals, strategy, lowPct, highPct) {
  if (!vals || vals.length === 0) return { kind: "none" };
  if (strategy === "tertile" || strategy === "percentile") {
    return {
      kind: "two-cut",
      lowCut: percentile(vals, strategy === "tertile" ? 33.3333 : lowPct),
      highCut: percentile(vals, strategy === "tertile" ? 66.6667 : highPct),
      lowLabel: `${(strategy === "tertile" ? 33.3 : lowPct).toFixed(0)}th pct`,
      highLabel: `${(strategy === "tertile" ? 66.7 : highPct).toFixed(0)}th pct`,
    };
  }
  if (strategy === "median") {
    const m = percentile(vals, 50);
    return { kind: "one-cut", cut: m, label: "median (50th pct)" };
  }
  let c0 = percentile(vals, 25), c1 = percentile(vals, 75);
  for (let it = 0; it < 30; it++) {
    const mid = (c0 + c1) / 2;
    let s0 = 0, n0 = 0, s1 = 0, n1 = 0;
    for (const v of vals) {
      if (v <= mid) { s0 += v; n0 += 1; } else { s1 += v; n1 += 1; }
    }
    const nc0 = n0 ? s0 / n0 : c0, nc1 = n1 ? s1 / n1 : c1;
    if (Math.abs(nc0 - c0) < 1e-9 && Math.abs(nc1 - c1) < 1e-9) { c0 = nc0; c1 = nc1; break; }
    c0 = nc0; c1 = nc1;
  }
  return { kind: "one-cut", cut: (c0 + c1) / 2, label: "KMeans midpoint (1-D preview)" };
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
                               metricLabel, metricKey, loading,
                               matchTolerance, setMatchTolerance, matchDirty,
                               scanModel, matchedLoading }) {
  const ref = useRef(null);
  const hasTolControl = typeof setMatchTolerance === "function";

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
    if (c.kind === "one-cut") return { ...c, label: strategy === "median" ? "median (50th pct)" : "KMeans midpoint" };
    return c;
  }, [matchedMode, scanModel, strategy, percentileLow, percentileHigh]);

  const vals = matchedMode ? scanModel.matchedValues : dailyVals;
  const cuts = matchedMode ? matchedCuts : dailyCuts;

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
    const pushCutLine = (x, label, color, yLevel = 1.04, xanchor = "center") => {
      shapes.push({ type: "line", xref: "x", yref: "paper", x0: x, x1: x, y0: 0, y1: 1,
                    line: { color, width: 2, dash: "dash" } });
      annotations.push({ x, yref: "paper", y: yLevel, xanchor, yanchor: "bottom",
                         text: `${x.toFixed(1)} (${label})`, showarrow: false,
                         font: { size: 10, color } });
    };
    if (cuts.kind === "two-cut") {
      pushCutLine(cuts.lowCut, cuts.lowLabel, LO, 1.02, "right");
      pushCutLine(cuts.highCut, cuts.highLabel, HI, 1.13, "left");
      shapes.push({ type: "rect", xref: "x", yref: "paper", x0: cuts.lowCut, x1: cuts.highCut,
                    y0: 0, y1: 1, fillcolor: MID, opacity: 0.10, line: { width: 0 } });
    } else if (cuts.kind === "one-cut") {
      pushCutLine(cuts.cut, cuts.label, "#344767", 1.04, "center");
    }

    // Class-count badges. In matched mode the unit is matched NEURAL SAMPLES (the neural data that
    // feeds binarization); in daily mode it is calendar days + the raw reports they carry.
    //
    // In matched mode each badge also shows the per-group MODALITY breakdown (TD streaming / montage
    // PSD / band-power LSB). LSB is not pooled into the binarization scan (the scan index only carries
    // "TD streaming" / "Montage/survey" sources), so it is shown as "n/a" rather than a misleading 0.
    // The badges are floated into y-axis HEADROOM (the matched-mode yaxis range is extended below) so
    // they sit ABOVE the tallest bar and never overlap the histogram. The Excluded badge in particular
    // is placed above a dotted "max" reference line drawn at the tallest-bar height.
    const yMax = cnt.length ? Math.max(1, ...cnt) : 1;
    const bySrc = (matchedMode && counts && counts.by_source) ? counts.by_source : null;
    const srcLine = (g) => g
      ? `${(g.td || 0).toLocaleString()} TD · ${(g.montage || 0).toLocaleString()} PSD · LSB n/a`
      : null;
    const badge = (xRel, yRel, color, label, primary, secondary) => ({
      xref: "paper", yref: "paper", x: xRel, y: yRel, xanchor: "center", yanchor: "top",
      text: `<b>${label}</b><br>${primary}${secondary ? `<br>${secondary}` : ""}`,
      showarrow: false, align: "center",
      font: { size: 10.5, color: "#FFFFFF" },
      bgcolor: color, bordercolor: color, borderwidth: 1.5, borderpad: 4, opacity: 0.94,
    });
    const lowTxt = matchedMode ? [`${(counts.n_low || 0).toLocaleString()} samples`, srcLine(bySrc && bySrc.low)]
                               : [`${dailyStats.nLowDays.toLocaleString()} days`, `${dailyStats.nLowSamp.toLocaleString()} samples`];
    const highTxt = matchedMode ? [`${(counts.n_high || 0).toLocaleString()} samples`, srcLine(bySrc && bySrc.high)]
                                : [`${dailyStats.nHighDays.toLocaleString()} days`, `${dailyStats.nHighSamp.toLocaleString()} samples`];
    const midTxt = matchedMode ? [`${(counts.n_excluded_middle || 0).toLocaleString()} samples`, srcLine(bySrc && bySrc.excluded)]
                               : [`${dailyStats.nMidDays.toLocaleString()} days`, `${dailyStats.nMidSamp.toLocaleString()} samples`];
    if (cuts.kind === "two-cut") {
      if (matchedMode) {
        // Float Low/High in the headroom band; Excluded sits higher still, above the max line.
        annotations.push(badge(0.12, 0.80, LO, "Low", lowTxt[0], lowTxt[1]));
        annotations.push(badge(0.88, 0.80, HI, "High", highTxt[0], highTxt[1]));
        annotations.push({ ...badge(0.50, 0.97, MID, "Excluded", midTxt[0], midTxt[1]), opacity: 0.88 });
        // Dotted reference rule at the tallest-bar height — the Excluded badge's border sits above it.
        shapes.push({ type: "line", xref: "paper", yref: "y", x0: 0, x1: 1, y0: yMax, y1: yMax,
                      line: { color: MID, width: 1, dash: "dot" } });
      } else {
        annotations.push(badge(0.10, 0.94, LO, "Low", lowTxt[0], lowTxt[1]));
        annotations.push({ ...badge(0.50, 0.02, MID, "Excluded", midTxt[0], midTxt[1]),
                           yanchor: "bottom", opacity: 0.78 });
        annotations.push(badge(0.90, 0.94, HI, "High", highTxt[0], highTxt[1]));
      }
    } else if (cuts.kind === "one-cut") {
      annotations.push(badge(0.18, matchedMode ? 0.84 : 0.94, LO, "Low", lowTxt[0], lowTxt[1]));
      annotations.push(badge(0.82, matchedMode ? 0.84 : 0.94, HI, "High", highTxt[0], highTxt[1]));
    }

    const yTitle = matchedMode ? "Matched neural samples" : "Days";
    const hoverUnit = matchedMode ? "samples" : "days";
    const traces = [{
      x: centers, y: cnt, type: "bar",
      marker: { color: colors, line: { width: 0 } }, opacity: 0.88, width: widths,
      hovertemplate: `${metricLabel || "pain"}=%{x:.1f}<br>%{y:,} ${hoverUnit}<extra></extra>`,
    }];
    const layout = {
      // Preserve any zoom the user applied to the histogram across live recolors; reset only when
      // the metric changes (different value domain).
      uirevision: `hist-${metricKey || "metric"}`,
      paper_bgcolor: "white", plot_bgcolor: "white",
      font: { family: "Roboto, Helvetica, Arial, sans-serif", size: 11, color: "#344767" },
      margin: { l: 48, r: 16, t: 54, b: 40 },
      bargap: 0.02,
      xaxis: { automargin: true, title: { text: metricLabel || "Pain score", font: { size: 11 }, standoff: 8 },
               gridcolor: "#EEF1F4", linecolor: "#B0B7BF", ticks: "outside", ticklen: 4,
               tickfont: { size: 10 }, showline: true },
      yaxis: { automargin: true, title: { text: yTitle, font: { size: 11 }, standoff: 8 },
               gridcolor: "#EEF1F4", linecolor: "#B0B7BF", ticks: "outside", ticklen: 4,
               tickfont: { size: 10 }, showline: true,
               // Matched mode: extend the range to ~1.6x the tallest bar so the floated per-group
               // detail badges (Low/High at ~0.80 paper, Excluded at ~0.97) clear the bars cleanly.
               ...(matchedMode && cuts.kind === "two-cut" ? { range: [0, yMax * 1.6] } : {}) },
      shapes, annotations, showlegend: false,
    };
    Plotly.react(ref.current, traces, layout, {
      responsive: true, displaylogo: false, displayModeBar: false,
    });
    return () => { if (ref.current) Plotly.purge(ref.current); };
  }, [vals, cuts, dailyStats, counts, matchedMode, metricLabel, metricKey]);

  // Header caption.
  const headerCaption = matchedMode
    ? `${(counts.n_matched || 0).toLocaleString()} of ${(counts.n_sessions || 0).toLocaleString()} PSDs matched at ±${matchTolerance} min`
    : (vals.length
        ? `${dayAgg.reduce((s, d) => s + d.nSamples, 0).toLocaleString()} PRO reports across ${vals.length.toLocaleString()} days`
        : ((loading || matchedLoading) ? "loading…" : "no data yet"));

  // Footer caption.
  const footerCaption = (() => {
    if (matchedMode) {
      if (cuts.kind === "two-cut") {
        // When the matched values are too few / too discrete (integer NRS) to form a middle tertile,
        // the excluded-middle bin is empty by construction — say so, so the missing grey isn't a mystery.
        const emptyMiddle = (counts.n_excluded_middle || 0) === 0;
        const offsetTxt = counts.median_abs_offset_min != null
          ? ` · median match offset ${counts.median_abs_offset_min.toFixed(1)} min.` : ".";
        if (emptyMiddle) {
          return `Cut at ${cuts.lowCut?.toFixed(1)} / ${cuts.highCut?.toFixed(1)} — no excluded-middle bin: ` +
            `the matched values are too discrete (e.g. integer NRS) to form a middle tertile, so every matched sample is high or low` + offsetTxt;
        }
        return `Matched neural samples cut at ${cuts.lowCut?.toFixed(1)} / ${cuts.highCut?.toFixed(1)} — ` +
          `${(counts.n_excluded_middle || 0).toLocaleString()} middle samples excluded from training` + offsetTxt;
      }
      if (cuts.kind === "one-cut") {
        return `Matched neural samples cut at ${cuts.cut?.toFixed(1)} — every matched sample is labeled (none excluded)` +
          (counts.median_abs_offset_min != null ? ` · median match offset ${counts.median_abs_offset_min.toFixed(1)} min.` : ".");
      }
      return "No neural sample matched a pain report at this window — widen the match window.";
    }
    if (cuts.kind === "two-cut") {
      return `Cuts on the daily distribution at ${cuts.lowCut?.toFixed(1)} / ${cuts.highCut?.toFixed(1)} — ` +
        `${dailyStats.nMidDays.toLocaleString()} days (${dailyStats.nMidSamp.toLocaleString()} raw samples) ` +
        `in the middle band excluded from training.`;
    }
    if (cuts.kind === "one-cut") {
      return `${strategy === "median" ? "Median" : "KMeans"} cut on the daily distribution at ${cuts.cut?.toFixed(1)} — every day is labeled (none excluded).`;
    }
    return "Adjust the strategy to preview the cut.";
  })();

  return (
    <MDBox display="flex" flexDirection="column" sx={{ width: "100%", height: "100%", minHeight: 440 }}>
      <MDBox display="flex" flexDirection="row" justifyContent="space-between" alignItems="baseline" mb={0.25}>
        <MDTypography variant="button" fontWeight="bold" color="dark" sx={{ fontSize: 15 }}>
          {matchedMode ? "Data available to binarize" : "Binarization preview"}
        </MDTypography>
        <MDTypography variant="caption" color="dark" sx={{ fontSize: 12, fontStyle: "italic" }}>
          {headerCaption}
        </MDTypography>
      </MDBox>

      {/* PRO<->PSD match-window control (minutes). ABOVE the histogram: it sets which neural samples
          carry a pain label at all — and therefore the high/low counts shown below. In matched mode
          the histogram updates LIVE as this moves (no recompute needed). */}
      {hasTolControl ? (
        <MDBox display="flex" flexDirection="row" alignItems="center" gap={1.25} mb={0.5}
               sx={{ px: 0.5, py: 0.5, borderRadius: 1, backgroundColor: "#F4F6F8" }}>
          <MDTypography variant="caption" fontWeight="bold" color="dark" sx={{ fontSize: 12, whiteSpace: "nowrap" }}>
            {"Match window ± "}
          </MDTypography>
          <Slider
            value={Math.min(Number(matchTolerance) || 0, 240)} min={1} max={240} step={1}
            valueLabelDisplay="auto" size="small" sx={{ flex: 1, mx: 0.5 }}
            onChange={(e, v) => setMatchTolerance(v)}
          />
          <TextField
            value={matchTolerance} type="number" size="small" variant="outlined"
            onChange={(e) => {
              const v = parseFloat(e.target.value);
              if (Number.isFinite(v) && v > 0) setMatchTolerance(v);
            }}
            inputProps={{ min: 1, max: 240, step: 1, style: { width: 52, padding: "4px 6px", fontSize: 13 } }}
          />
          <MDTypography variant="caption" color="dark" sx={{ fontSize: 12 }}>{"min"}</MDTypography>
        </MDBox>
      ) : null}

      {/* Matched neural-sample readout — counts computed LIVE on the samples the scan pools. The
          pool is mostly TD-streaming (not montage PSDs), so the count is broken down by source and
          uses the modality-neutral noun "neural samples". aria-live announces updates to readers. */}
      {matchedMode ? (
        <MDTypography variant="caption" color="dark" sx={{ fontSize: 12, mb: 0.25 }}
                      aria-live="polite">
          <b>{`${(counts.n_matched ?? 0).toLocaleString()}`}</b>
          {` of ${(counts.n_sessions ?? 0).toLocaleString()} neural samples matched a pain report `}
          {`(±${matchTolerance} min`}
          {Number.isFinite(counts.median_abs_offset_min)
            ? `, median offset ${counts.median_abs_offset_min.toFixed(1)} min` : ""}
          {") → "}
          <span style={{ color: HI, fontWeight: 700 }}>{`${(counts.n_high ?? 0).toLocaleString()} high`}</span>
          {" / "}
          <span style={{ color: LO, fontWeight: 700 }}>{`${(counts.n_low ?? 0).toLocaleString()} low`}</span>
          {counts.n_excluded_middle
            ? <span style={{ color: MID }}>{` / ${counts.n_excluded_middle.toLocaleString()} excluded`}</span>
            : null}
          {(counts.n_matched_td != null && counts.n_matched_montage != null && counts.n_matched > 0)
            ? <span style={{ color: "#777" }}>
                {`  (${counts.n_matched_td.toLocaleString()} TD-streaming · ${counts.n_matched_montage.toLocaleString()} montage PSD)`}
              </span>
            : null}
          {matchDirty ? <i style={{ color: "#777" }}>{"  (live preview — recompute to score)"}</i> : null}
        </MDTypography>
      ) : (hasTolControl ? (
        <MDTypography variant="caption" color="dark" sx={{ fontSize: 11.5, fontStyle: "italic", mb: 0.25 }}>
          {(loading || matchedLoading)
            ? "Loading neural-sample availability…"
            : "No PSD scan index available — showing the daily PRO distribution."}
        </MDTypography>
      ) : null)}

      <div ref={ref} style={{ flex: 1, width: "100%", minHeight: 340 }} />
      <MDTypography variant="caption" color="dark" sx={{ fontSize: 12, textAlign: "center" }}>
        {footerCaption}
      </MDTypography>
    </MDBox>
  );
}

export default BinarizationPreview;
