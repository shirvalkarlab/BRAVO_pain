/**
 * BinarizationPreview — live histogram of the selected pain score with the strategy's high/low
 * cuts and class counts overlaid. Pure client-side: takes the raw PRO report points, aggregates
 * them to ONE value per calendar day (the daily mean — matching the backend's daily_broadcast
 * labeler so the preview's cut equals the detector's cut), then recomputes every render so the
 * figure updates the moment the user drags a slider or changes the strategy (no backend roundtrip).
 * Class counts are reported in BOTH calendar days (the unit the detector trains on) and the raw
 * PRO samples those days carry.
 *
 * Sits in the top controls card alongside the strategy selector so the user can SEE exactly which
 * days will be labeled high vs low BEFORE clicking "Compute biomarker". Renders identically on
 * every tab (time-domain, power-domain, both) — the binarization is source-independent.
 *
 * Design notes (publication-quality, colorblind-safe):
 *   * Okabe-Ito palette — LO=#0072B2 (blue), HI=#D55E00 (vermillion), MID=#7E8794 (grey).
 *   * Histogram is a single trace with per-bin marker colors, so the high/low/excluded classes
 *     are visually contiguous (no gap artifacts from three separate overlaid histograms).
 *   * Cut lines + percentile labels above the plot area; class-count badges as in-plot annotations.
 *   * Card is intentionally compact (square-ish, height ~280px) so it sits next to the controls
 *     without dominating the page.
 */

import { useMemo, useEffect, useRef } from "react";
import Plotly from "plotly.js-dist";
import Slider from "@mui/material/Slider";
import TextField from "@mui/material/TextField";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

const LO = "#0072B2";   // blue
const HI = "#D55E00";   // vermillion
const MID = "#7E8794";  // grey (excluded middle)

// Lightweight percentile (linear interpolation, q in 0..100) over a finite-value array.
function percentile(values, q) {
  if (!values || values.length === 0) return null;
  const a = [...values].sort((x, y) => x - y);
  const idx = (q / 100) * (a.length - 1);
  const lo = Math.floor(idx), hi = Math.ceil(idx);
  if (lo === hi) return a[lo];
  return a[lo] + (a[hi] - a[lo]) * (idx - lo);
}

// Compute cuts given strategy + percentile state. Returns
//   { kind: "two-cut"|"one-cut"|"kmeans-approx", lowCut, highCut, lowCutLabel, highCutLabel }
// "kmeans-approx" is a heuristic preview: real KMeans runs in the backend on `cv_df`, but for a
// SINGLE-metric histogram preview the 1-D k=2 result is identical to a midpoint between the two
// per-cluster means — we use the median split as the visual cue and label it as approximate.
function computeCuts(vals, strategy, lowPct, highPct) {
  if (!vals || vals.length === 0) return { kind: "none" };
  if (strategy === "tertile" || strategy === "percentile") {
    return {
      kind: "two-cut",
      lowCut: percentile(vals, lowPct),
      highCut: percentile(vals, highPct),
      lowLabel: `${lowPct.toFixed(0)}th pct`,
      highLabel: `${highPct.toFixed(0)}th pct`,
    };
  }
  if (strategy === "median") {
    const m = percentile(vals, 50);
    return { kind: "one-cut", cut: m, label: "median (50th pct)" };
  }
  // KMeans: 1-D k=2 cluster — quick in-browser approximation. Initialize at the 25th and 75th
  // percentiles, iterate a few times; converges in a handful of steps on monotone PRO data.
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


// Adaptive histogram bin width for the binarization preview. Different pain metrics live on very
// different scales, so a single fixed bin width either over- or under-resolves them:
//   * NRS (0–10) and the z-scored Composite are narrow → 0.2 score-unit bins.
//   * VAS metrics (0–100) and the MPQ/NPQ sum span tens of points → 2 score-unit bins.
// Primary decision is by metric key (explicit, matches the clinician's mental model); a range-based
// fallback (span > 15 → wide bins) covers any future metric not in the map.
const WIDE_BIN_METRICS = new Set(["vas", "left_leg_vas", "back_vas", "mpq_sum", "npq_sum"]);
const NARROW_BIN_METRICS = new Set(["nrs", "composite_mpq_leftleg"]);
function binWidthForMetric(metricKey, vmin, vmax) {
  if (metricKey && NARROW_BIN_METRICS.has(metricKey)) return 0.2;
  if (metricKey && WIDE_BIN_METRICS.has(metricKey)) return 2;
  // Fallback for an unmapped metric: decide from the observed span.
  const span = (Number.isFinite(vmax) && Number.isFinite(vmin)) ? vmax - vmin : 0;
  return span > 15 ? 2 : 0.2;
}


function BinarizationPreview({ points, dailyAgg, strategy, percentileLow, percentileHigh,
                               metricLabel, metricKey, loading,
                               matchTolerance, setMatchTolerance, matchedCounts, matchDirty }) {
  const ref = useRef(null);
  const hasTolControl = typeof setMatchTolerance === "function";

  // Aggregate the raw PRO reports to ONE value per calendar day (the mean of that day's reports),
  // EXACTLY as the backend labeler does (adapter._threshold_pain_level with daily_broadcast=True:
  // it groups samples by day, takes the daily mean, and fits the cut on that daily distribution —
  // then broadcasts each day's label back to its samples). Computing the preview cut on the raw
  // report list instead would let heavily-reported days bias the split and would disagree with the
  // detector. Each point's `t` is an ISO-ish timestamp ("2025-01-15 12:30:00"); the day key is its
  // first 10 chars. We keep, per day, the daily mean AND how many raw reports fell on that day, so
  // the card can report both "days" and "raw samples" for every class.
  const dayAgg = useMemo(() => {
    // Pre-aggregated daily means take precedence (the per-(channel,frequency) decode supplies
    // `dailyAgg = [{day, mean, n_samples}]` already collapsed to one row per day at the selected
    // band). Otherwise aggregate the raw PRO reports here, exactly as the backend labeler does.
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

  // The daily-mean values are what the cut and the histogram are computed over (the x-axis is a
  // distribution of DAYS, not reports).
  const vals = useMemo(() => dayAgg.map((d) => d.mean), [dayAgg]);
  // Total raw PRO reports (samples) behind those days — for the honest "N reports across M days".
  const nReports = useMemo(() => dayAgg.reduce((s, d) => s + d.nSamples, 0), [dayAgg]);

  const cuts = useMemo(() => computeCuts(vals, strategy, percentileLow, percentileHigh),
                       [vals, strategy, percentileLow, percentileHigh]);

  // Class counts: DAYS (one per calendar day) AND the raw SAMPLES (reports) those days carry.
  // The detector trains on days (each day one label, broadcast to its samples), so days is the
  // primary count; samples is shown alongside so the clinician knows the underlying report volume.
  const stats = useMemo(() => {
    const zero = { nLowDays: 0, nHighDays: 0, nMidDays: 0, nLowSamp: 0, nHighSamp: 0, nMidSamp: 0 };
    if (!dayAgg.length || cuts.kind === "none") return zero;
    const acc = { ...zero };
    for (const d of dayAgg) {
      let cls;
      if (cuts.kind === "two-cut") {
        cls = d.mean <= cuts.lowCut ? "low" : (d.mean >= cuts.highCut ? "high" : "mid");
      } else {
        cls = d.mean <= cuts.cut ? "low" : "high";
      }
      if (cls === "low") { acc.nLowDays++; acc.nLowSamp += d.nSamples; }
      else if (cls === "high") { acc.nHighDays++; acc.nHighSamp += d.nSamples; }
      else { acc.nMidDays++; acc.nMidSamp += d.nSamples; }
    }
    return acc;
  }, [dayAgg, cuts]);

  useEffect(() => {
    if (!ref.current) return;
    if (!vals.length) { Plotly.purge(ref.current); return; }
    // Adaptive bin width by metric (see binWidthForMetric): 0.2 for narrow 0–10 / z-scored scales
    // (NRS, Composite), 2 for wide 0–100 / summed scales (VAS, MPQ/NPQ sum). Anchor the left edge to
    // a clean multiple of the bin width so boundaries fall on predictable grid lines (…, 6.8, 7.0,
    // 7.2, … for 0.2; …, 40, 42, 44, … for 2) and cut lines land cleanly between bars. A hard cap
    // guards against a pathological range producing thousands of bins.
    const rawMin = Math.min(...vals), vmax = Math.max(...vals);
    const BIN_W = binWidthForMetric(metricKey, rawMin, vmax);
    const vmin = Math.floor(rawMin / BIN_W) * BIN_W;          // align down to a BIN_W multiple
    const binW = BIN_W;
    const nBins = Math.max(1, Math.min(500, Math.ceil((vmax - vmin) / binW) || 1));
    // Build manual bins so each bin gets a per-class color (low/excluded/high) — Plotly's stacked
    // histogram can't color by cut value of the bin itself, so we precompute.
    const edges = Array.from({ length: nBins + 1 }, (_, i) => vmin + i * binW);
    const counts = new Array(nBins).fill(0);
    for (const v of vals) {
      let i = Math.floor((v - vmin) / binW);
      if (i >= nBins) i = nBins - 1; if (i < 0) i = 0;
      counts[i] += 1;
    }
    const centers = counts.map((_, i) => (edges[i] + edges[i + 1]) / 2);
    let colors;
    if (cuts.kind === "two-cut") {
      colors = centers.map((c) => (c <= cuts.lowCut ? LO : (c >= cuts.highCut ? HI : MID)));
    } else if (cuts.kind === "one-cut") {
      colors = centers.map((c) => (c <= cuts.cut ? LO : HI));
    } else {
      colors = centers.map(() => LO);
    }
    const shapes = [];
    const annotations = [];
    // Cut-line labels sit above the plot. When the two cuts are close on the x-axis (e.g. the
    // ceiling-skewed NRS tertile at 7.0 / 8.0) same-height labels overlap, so stagger them:
    // the low-cut label on a lower line anchored to the LEFT of its line, the high-cut label on
    // a higher line anchored to the RIGHT. yLevel/xanchor passed per call.
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
      // Shade the excluded middle.
      shapes.push({ type: "rect", xref: "x", yref: "paper", x0: cuts.lowCut, x1: cuts.highCut,
                    y0: 0, y1: 1, fillcolor: MID, opacity: 0.10, line: { width: 0 } });
    } else if (cuts.kind === "one-cut") {
      pushCutLine(cuts.cut, cuts.label, "#344767", 1.04, "center");
    }

    // Class-count badges in the plot area — placed at the top-left (low) and top-right (high)
    // corners; the excluded middle (if any) sits centered. Sample annotations adapted from the
    // ps-scientific-visualization guidelines (sentence case, sans-serif, no chart junk).
    const badge = (xRel, color, label, nDays, nSamp) => ({
      xref: "paper", yref: "paper", x: xRel, y: 0.94, xanchor: "center", yanchor: "top",
      text: `<b>${label}</b><br>${nDays.toLocaleString()} days<br>${nSamp.toLocaleString()} samples`,
      showarrow: false, align: "center",
      font: { size: 11, color: "#FFFFFF" },
      bgcolor: color, bordercolor: color, borderpad: 4, opacity: 0.92,
    });
    if (cuts.kind === "two-cut") {
      annotations.push(badge(0.10, LO, "Low", stats.nLowDays, stats.nLowSamp));
      // Excluded badge sits at the very BOTTOM-CENTER of the plot (bottom-anchored just above the
      // x-axis), clear of the staggered cut-line labels above the plot. Alpha is also lowered so it
      // reads as a translucent overlay — any bar behind it still shows through (combined fix:
      // bottom placement keeps it off the cut labels, lower alpha keeps it from occluding a bar).
      annotations.push({ ...badge(0.50, MID, "Excluded", stats.nMidDays, stats.nMidSamp),
                         y: 0.02, yanchor: "bottom", opacity: 0.78 });
      annotations.push(badge(0.90, HI, "High", stats.nHighDays, stats.nHighSamp));
    } else if (cuts.kind === "one-cut") {
      annotations.push(badge(0.18, LO, "Low", stats.nLowDays, stats.nLowSamp));
      annotations.push(badge(0.82, HI, "High", stats.nHighDays, stats.nHighSamp));
    }

    const traces = [{
      x: centers, y: counts, type: "bar",
      marker: { color: colors, line: { width: 0 } }, opacity: 0.88, width: binW * 0.96,
      hovertemplate: `${metricLabel || "pain"}=%{x:.1f}<br>%{y:,} days<extra></extra>`,
    }];
    const layout = {
      paper_bgcolor: "white", plot_bgcolor: "white",
      font: { family: "Roboto, Helvetica, Arial, sans-serif", size: 11, color: "#344767" },
      margin: { l: 48, r: 16, t: 54, b: 40 },
      bargap: 0.02,
      xaxis: { automargin: true, title: { text: metricLabel || "Pain score", font: { size: 11 }, standoff: 8 },
               gridcolor: "#EEF1F4", linecolor: "#B0B7BF", ticks: "outside", ticklen: 4,
               tickfont: { size: 10 }, showline: true },
      yaxis: { automargin: true, title: { text: "Days", font: { size: 11 }, standoff: 8 },
               gridcolor: "#EEF1F4", linecolor: "#B0B7BF", ticks: "outside", ticklen: 4,
               tickfont: { size: 10 }, showline: true },
      shapes, annotations, showlegend: false,
    };
    Plotly.react(ref.current, traces, layout, {
      responsive: true, displaylogo: false, displayModeBar: false,
    });
    return () => { if (ref.current) Plotly.purge(ref.current); };
  }, [vals, cuts, stats, metricLabel, metricKey]);

  return (
    <MDBox display="flex" flexDirection="column" sx={{ width: "100%", height: "100%", minHeight: 440 }}>
      <MDBox display="flex" flexDirection="row" justifyContent="space-between" alignItems="baseline" mb={0.25}>
        <MDTypography variant="button" fontWeight="bold" color="dark" sx={{ fontSize: 15 }}>
          {"Binarization preview"}
        </MDTypography>
        <MDTypography variant="caption" color="dark" sx={{ fontSize: 12, fontStyle: "italic" }}>
          {vals.length
            ? `${nReports.toLocaleString()} PRO reports across ${vals.length.toLocaleString()} days`
            : (loading ? "loading…" : "no data yet")}
        </MDTypography>
      </MDBox>

      {/* PRO<->PSD match-window control (minutes). ABOVE the histogram, since it sets which neural
          samples carry a pain label at all — and therefore the high/low counts reported below. A
          compute param: changing it makes the result stale until the user re-runs the analysis. */}
      {hasTolControl ? (
        <MDBox display="flex" flexDirection="row" alignItems="center" gap={1.25} mb={0.5}
               sx={{ px: 0.5, py: 0.5, borderRadius: 1, backgroundColor: "#F4F6F8" }}>
          <MDTypography variant="caption" fontWeight="bold" color="dark" sx={{ fontSize: 12, whiteSpace: "nowrap" }}>
            {"Match window ± "}
          </MDTypography>
          <Slider
            value={Number(matchTolerance) || 0} min={1} max={120} step={1}
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

      {/* Matched neural-sample readout — counts computed by the backend ON THE PSDs (distinct
          sessions matched to a pain report within the window), not the raw daily surveys above. */}
      {matchedCounts ? (
        <MDTypography variant="caption" color="dark" sx={{ fontSize: 12, mb: 0.25 }}>
          <b>{`${(matchedCounts.n_matched ?? 0).toLocaleString()}`}</b>
          {` of ${(matchedCounts.n_sessions ?? 0).toLocaleString()} neural samples matched a pain report `}
          {`(±${matchedCounts.tolerance_min ?? matchTolerance} min`}
          {Number.isFinite(matchedCounts.median_abs_offset_min)
            ? `, median offset ${matchedCounts.median_abs_offset_min.toFixed(1)} min` : ""}
          {") → "}
          <span style={{ color: HI, fontWeight: 700 }}>{`${(matchedCounts.n_high ?? 0).toLocaleString()} high`}</span>
          {" / "}
          <span style={{ color: LO, fontWeight: 700 }}>{`${(matchedCounts.n_low ?? 0).toLocaleString()} low`}</span>
          {matchedCounts.n_excluded_middle
            ? <span style={{ color: MID }}>{` / ${matchedCounts.n_excluded_middle.toLocaleString()} excluded`}</span>
            : null}
          {matchDirty ? <i style={{ color: "#B00" }}>{"  (stale — recompute)"}</i> : null}
        </MDTypography>
      ) : (hasTolControl ? (
        <MDTypography variant="caption" color="dark" sx={{ fontSize: 11.5, fontStyle: "italic", mb: 0.25 }}>
          {"Run the exploratory analysis to see how many neural samples match a pain report at this window."}
        </MDTypography>
      ) : null)}

      <div ref={ref} style={{ flex: 1, width: "100%", minHeight: 340 }} />
      <MDTypography variant="caption" color="dark" sx={{ fontSize: 12, textAlign: "center" }}>
        {cuts.kind === "two-cut"
          ? `Cuts on the daily distribution at ${cuts.lowCut?.toFixed(1)} / ${cuts.highCut?.toFixed(1)} — ` +
            `${stats.nMidDays.toLocaleString()} days (${stats.nMidSamp.toLocaleString()} raw samples) ` +
            `in the middle band excluded from training.`
          : cuts.kind === "one-cut"
            ? `${strategy === "median" ? "Median" : "KMeans"} cut on the daily distribution at ${cuts.cut?.toFixed(1)} — every day is labeled (none excluded).`
            : "Adjust the strategy to preview the cut."}
      </MDTypography>
    </MDBox>
  );
}

export default BinarizationPreview;
