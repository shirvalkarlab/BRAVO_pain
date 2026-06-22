/**
 * binarizationModel — single client-side source of truth for "which neural samples feed the
 * binarized biomarker at the current match window, and how each one is labeled."
 *
 * The backend's exploratory scan pools every full-spectrum PSD (TD streaming + montage/survey) on
 * the six main bipolar channels, matches each to the NEAREST continuous PRO within ±tolerance, and
 * binarizes the matched values (tertile / percentile / median / kmeans). The availability payload
 * now ships `psd_scan_index` — one {t, channel, source} per pooled PSD — so the frontend can
 * reproduce that match + binarization LIVE (no recompute) as the user drags the match-window slider
 * or changes the strategy. This module is that reproduction; it is verified to return counts
 * IDENTICAL to the backend `matched_sample_counts` (RCS08 @±15 min: 26 matched, 12 high / 14 low).
 *
 * Both the binarization-preview histogram (which samples feed binarization, at this window) and the
 * timeline color overlay (highlight the selected samples, dim the rest) consume one model instance.
 *
 * Okabe-Ito, colorblind-safe — MUST match BinarizationPreview / the histogram:
 *   HIGH = #D55E00 (vermillion), LOW = #0072B2 (blue), EXCLUDED middle = #7E8794 (grey).
 *   UNMATCHED / not-selected is rendered VERY light grey by the consumer (not a class here).
 */

export const BIN_HI = "#D55E00";   // high pain
export const BIN_LO = "#0072B2";   // low pain
export const BIN_MID = "#7E8794";  // excluded middle

// numpy-percentile (linear interpolation, q in 0..100) over a finite-value array.
function percentile(values, q) {
  if (!values || values.length === 0) return null;
  const a = [...values].sort((x, y) => x - y);
  const idx = (q / 100) * (a.length - 1);
  const lo = Math.floor(idx), hi = Math.ceil(idx);
  if (lo === hi) return a[lo];
  return a[lo] + (a[hi] - a[lo]) * (idx - lo);
}

// Nearest PRO within ±tolerance for one sample time, replicating streaming_psd._match_to_pro.
// `proSorted` is [{t, v}] sorted ascending by t. Returns {v, dtMin} or null when none in window.
function matchNearest(tSec, proSorted, tolSec) {
  if (!proSorted.length || !(tolSec > 0)) return null;
  // binary search for insertion point
  let lo = 0, hi = proSorted.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (proSorted[mid].t < tSec) lo = mid + 1; else hi = mid;
  }
  let best = -1, bestD = Infinity;
  for (const k of [lo - 1, lo]) {
    if (k >= 0 && k < proSorted.length) {
      const d = Math.abs(proSorted[k].t - tSec);
      if (d <= tolSec && d < bestD) { best = k; bestD = d; }
    }
  }
  if (best < 0) return null;
  return { v: proSorted[best].v, dtMin: (proSorted[best].t - tSec) / 60 };
}

// Compute the cut(s) on the matched continuous values, faithful to analytics._binarize_labels:
//   * "tertile"  -> FIXED 33.3333 / 66.6667 percentiles (sliders ignored, matches backend)
//   * "percentile" -> low/high slider percentiles
//   * "median"   -> single median cut (>= median => high)
//   * "kmeans"   -> 1-D 2-means (Lloyd from p25/p75), split at the cluster midpoint
function computeCuts(vals, strategy, lowPct, highPct) {
  if (!vals || vals.length === 0) return { kind: "none" };
  if (strategy === "tertile" || strategy === "percentile") {
    const loQ = strategy === "tertile" ? 33.3333 : Number(lowPct);
    const hiQ = strategy === "tertile" ? 66.6667 : Number(highPct);
    return { kind: "two-cut", lowCut: percentile(vals, loQ), highCut: percentile(vals, hiQ) };
  }
  if (strategy === "median") return { kind: "one-cut", cut: percentile(vals, 50) };
  // kmeans: Lloyd step from the quartiles; converges in a handful of iterations on PRO data.
  let c0 = percentile(vals, 25), c1 = percentile(vals, 75);
  for (let it = 0; it < 25; it++) {
    let s0 = 0, n0 = 0, s1 = 0, n1 = 0;
    for (const v of vals) {
      if (Math.abs(v - c0) <= Math.abs(v - c1)) { s0 += v; n0 += 1; }
      else { s1 += v; n1 += 1; }
    }
    const nc0 = n0 ? s0 / n0 : c0, nc1 = n1 ? s1 / n1 : c1;
    if (Math.abs(nc0 - c0) < 1e-9 && Math.abs(nc1 - c1) < 1e-9) { c0 = nc0; c1 = nc1; break; }
    c0 = nc0; c1 = nc1;
  }
  return { kind: "one-cut", cut: (c0 + c1) / 2 };
}

// Classify one matched continuous value into its bin given the cuts.
function classify(v, cuts) {
  if (cuts.kind === "two-cut") return v <= cuts.lowCut ? "low" : (v >= cuts.highCut ? "high" : "excluded");
  if (cuts.kind === "one-cut") return v <= cuts.cut ? "low" : "high"; // backend: >=cut => high
  return "unmatched";
}

/**
 * Build the matched-scan model.
 *   scanIndex   : [{t (epoch_s), channel, source}]   — availability.psd_scan_index
 *   painSeries  : {t:[epoch_s], y:[val], metric}      — the LIVE PRO series for the selected metric
 *   toleranceMin: match window (minutes); <=0/None => nothing matched
 *   strategy, percentileLow, percentileHigh           — binarization controls
 *
 * Returns:
 *   { samples: [{t, channel, source, v, bin}],        // bin: high|low|excluded|unmatched
 *     binByKey: Map "<CHANNEL>|<roundT>" -> bin,       // for timeline mark coloring
 *     matchedValues: [v…],                             // continuous values of MATCHED samples
 *     cuts,                                            // {kind, lowCut/highCut | cut}
 *     counts: {n_sessions, n_matched, n_high, n_low, n_excluded_middle, tolerance_min,
 *              median_abs_offset_min} }
 */
export function computeMatchedScanModel({ scanIndex, painSeries, toleranceMin,
                                          strategy, percentileLow, percentileHigh }) {
  const empty = {
    samples: [], binByKey: new Map(), matchedValues: [], cuts: { kind: "none" },
    counts: { n_sessions: 0, n_matched: 0, n_high: 0, n_low: 0, n_excluded_middle: 0,
              tolerance_min: toleranceMin, median_abs_offset_min: null },
  };
  if (!Array.isArray(scanIndex) || !scanIndex.length || !painSeries
      || !painSeries.t || !painSeries.t.length) return empty;

  const tolSec = (toleranceMin && toleranceMin > 0) ? toleranceMin * 60 : 0;
  const proSorted = painSeries.t
    .map((t, i) => ({ t, v: painSeries.y[i] }))
    .filter((p) => Number.isFinite(p.t) && Number.isFinite(p.v))
    .sort((a, b) => a.t - b.t);

  // 1st pass: match each scan sample to its nearest PRO within the window.
  const matched = [];   // {t, channel, source, v, dtMin}
  const offsets = [];
  for (const e of scanIndex) {
    const m = matchNearest(e.t, proSorted, tolSec);
    matched.push({ t: e.t, channel: e.channel, source: e.source, v: m ? m.v : null });
    if (m) offsets.push(Math.abs(m.dtMin));
  }
  // cuts computed on the matched continuous values (exactly as the backend binarizes the labels).
  const matchedValues = matched.filter((s) => s.v != null && Number.isFinite(s.v)).map((s) => s.v);
  const cuts = computeCuts(matchedValues, strategy, percentileLow, percentileHigh);

  // 2nd pass: assign each sample its bin + build the (channel,t) lookup for the timeline.
  // Also tally matched samples by SOURCE (TD streaming vs montage/survey), since most of the pool
  // is TD streaming, not montage PSDs — the readout breaks the count down so "neural samples" is
  // not misread as "PSDs".
  const samples = [];
  const binByKey = new Map();
  let nHigh = 0, nLow = 0, nMid = 0, nMatchedTd = 0, nMatchedMontage = 0;
  for (const s of matched) {
    let bin;
    if (s.v == null || !Number.isFinite(s.v)) bin = "unmatched";
    else {
      bin = classify(s.v, cuts);
      if (bin === "high") nHigh++; else if (bin === "low") nLow++; else nMid++;
      if (String(s.source || "").toLowerCase().indexOf("td") >= 0) nMatchedTd++; else nMatchedMontage++;
    }
    samples.push({ ...s, bin });
    binByKey.set(`${String(s.channel).toUpperCase()}|${Math.round(s.t)}`, bin);
  }
  offsets.sort((a, b) => a - b);
  const medianOffset = offsets.length
    ? (offsets.length % 2 ? offsets[(offsets.length - 1) / 2]
        : (offsets[offsets.length / 2 - 1] + offsets[offsets.length / 2]) / 2)
    : null;

  return {
    samples, binByKey, matchedValues, cuts,
    counts: {
      n_sessions: scanIndex.length,
      n_matched: matchedValues.length,
      n_high: nHigh, n_low: nLow,
      n_excluded_middle: (strategy === "tertile" || strategy === "percentile") ? nMid : 0,
      n_matched_td: nMatchedTd, n_matched_montage: nMatchedMontage,
      tolerance_min: toleranceMin,
      median_abs_offset_min: medianOffset,
    },
  };
}
