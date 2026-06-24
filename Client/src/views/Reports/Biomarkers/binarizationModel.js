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

// Match one PSD time to a PRO within the window, replicating streaming_psd._match_to_pro.
// `proSorted` is [{t, v}] sorted ascending by t. `direction`: "prior" pairs the PSD with the
// nearest PRO at or AFTER it (PSD precedes rating — forecasting); "nearest" is symmetric ±tol.
// Returns {v, dtMin, idx} (idx into proSorted) or null when none in window.
function matchNearest(tSec, proSorted, tolSec, direction = "prior") {
  if (!proSorted.length || !(tolSec > 0)) return null;
  // binary search for insertion point (first index with proSorted[i].t >= tSec)
  let lo = 0, hi = proSorted.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (proSorted[mid].t < tSec) lo = mid + 1; else hi = mid;
  }
  let best = -1, bestD = Infinity;
  if (direction === "prior") {
    // only PRO at or after the PSD (proSorted[lo].t >= tSec)
    if (lo >= 0 && lo < proSorted.length) {
      const d = proSorted[lo].t - tSec;
      if (d >= 0 && d <= tolSec) { best = lo; bestD = d; }
    }
  } else {
    for (const k of [lo - 1, lo]) {
      if (k >= 0 && k < proSorted.length) {
        const d = Math.abs(proSorted[k].t - tSec);
        if (d <= tolSec && d < bestD) { best = k; bestD = d; }
      }
    }
  }
  if (best < 0) return null;
  return { v: proSorted[best].v, dtMin: (proSorted[best].t - tSec) / 60, idx: best };
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
                                          strategy, percentileLow, percentileHigh,
                                          maxPerRating = 3, refractoryMin = 2,
                                          matchDirection = "prior" }) {
  const empty = {
    samples: [], binByKey: new Map(), matchedValues: [], cuts: { kind: "none" },
    counts: { n_sessions: 0, n_matched: 0, n_high: 0, n_low: 0, n_excluded_middle: 0,
              n_matched_td: 0, n_matched_montage: 0,
              by_source: { low: { td: 0, montage: 0, lsb: 0 },
                           high: { td: 0, montage: 0, lsb: 0 },
                           excluded: { td: 0, montage: 0, lsb: 0 } },
              tolerance_min: toleranceMin, median_abs_offset_min: null },
  };
  if (!Array.isArray(scanIndex) || !scanIndex.length || !painSeries
      || !painSeries.t || !painSeries.t.length) return empty;

  const tolSec = (toleranceMin && toleranceMin > 0) ? toleranceMin * 60 : 0;
  // `i0` = original index into painSeries.t/y, captured here so we can map a matched proIdx (an
  // index into proSorted) back to the DISPLAYED pain-row order for the matched/unmatched overlay.
  const proSorted = painSeries.t
    .map((t, i) => ({ t, v: painSeries.y[i], i0: i }))
    .filter((p) => Number.isFinite(p.t) && Number.isFinite(p.v))
    .sort((a, b) => a.t - b.t);

  // 1st pass: match each scan sample to a PRO within the window. Three branches:
  //   pro_first  -- walk PROs (units of independence), claim up to maxPerRating closest PSDs PER
  //                 CHANNEL each within tolerance. Maximizes PRO coverage for discovery. A PSD
  //                 already claimed cannot be re-claimed.
  //   nearest    -- PSD-first symmetric: each PSD matched to closest PRO either direction.
  //   prior      -- PSD-first forecasting: PSD must precede the rating.
  // Faithful to backend modules/Biomarkers/routines/streaming_psd.py:_match_to_pro.
  const matched = scanIndex.map((e) => ({
    t: e.t, channel: e.channel, source: e.source, v: null, dtMin: null, proIdx: -1,
  }));
  let nCappedDropped = 0;
  if (matchDirection === "pro_first" && proSorted.length && tolSec > 0 && maxPerRating >= 1) {
    // Index scan rows for searchsorted by time.
    const idxByT = matched.map((_, i) => i).sort((a, b) => matched[a].t - matched[b].t);
    const sortedT = idxByT.map((i) => matched[i].t);
    const claimed = new Array(matched.length).fill(false);
    // For each PRO in time order, find unclaimed PSDs within tol, then per channel keep K closest.
    for (let pk = 0; pk < proSorted.length; pk++) {
      const tPro = proSorted[pk].t;
      const vPro = proSorted[pk].v;
      // Binary-search the tolerance window in the time-sorted scan rows.
      let lo = 0, hi = sortedT.length;
      while (lo < hi) { const mi = (lo + hi) >> 1; if (sortedT[mi] < tPro - tolSec) lo = mi + 1; else hi = mi; }
      const winLo = lo;
      lo = 0; hi = sortedT.length;
      while (lo < hi) { const mi = (lo + hi) >> 1; if (sortedT[mi] <= tPro + tolSec) lo = mi + 1; else hi = mi; }
      const winHi = lo;
      if (winHi <= winLo) continue;
      // Bucket window candidates per channel.
      const perCh = new Map();
      for (let k = winLo; k < winHi; k++) {
        const mi = idxByT[k];
        if (claimed[mi]) continue;
        const ch = matched[mi].channel;
        if (!perCh.has(ch)) perCh.set(ch, []);
        perCh.get(ch).push(mi);
      }
      // Per channel: keep K closest to tPro; mark them matched + claimed.
      for (const idxs of perCh.values()) {
        idxs.sort((a, b) => Math.abs(matched[a].t - tPro) - Math.abs(matched[b].t - tPro));
        const take = idxs.slice(0, Math.max(1, maxPerRating));
        for (const mi of take) {
          matched[mi].v = vPro;
          matched[mi].dtMin = (tPro - matched[mi].t) / 60;
          matched[mi].proIdx = pk;
          claimed[mi] = true;
        }
      }
    }
    // pro_first enforces the cap at claim-time, so no post-hoc cap pass is needed.
  } else {
    // PSD-first ("nearest" or "prior") + post-hoc per-(channel, rating) cap.
    for (const s of matched) {
      const m = matchNearest(s.t, proSorted, tolSec, matchDirection);
      if (m) { s.v = m.v; s.dtMin = m.dtMin; s.proIdx = m.idx; }
    }
    if (maxPerRating >= 1) {
      const refSec = (refractoryMin || 0) * 60;
      const groups = new Map();   // "channel|proIdx" -> [matched index]
      matched.forEach((s, i) => {
        if (s.v != null && Number.isFinite(s.v) && s.proIdx >= 0) {
          const k = `${s.channel}|${s.proIdx}`;
          if (!groups.has(k)) groups.set(k, []);
          groups.get(k).push(i);
        }
      });
      for (const idxs of groups.values()) {
        if (idxs.length <= 1) continue;
        idxs.sort((a, b) => Math.abs(matched[a].dtMin) - Math.abs(matched[b].dtMin));
        const keptT = [];
        for (const i of idxs) {
          const drop = keptT.length >= maxPerRating
            || (refSec > 0 && keptT.some((tk) => Math.abs(matched[i].t - tk) < refSec));
          if (drop) { matched[i].v = null; matched[i].proIdx = -1; nCappedDropped++; }
          else keptT.push(matched[i].t);
        }
      }
    }
  }
  const offsets = matched.filter((s) => s.v != null && Number.isFinite(s.v))
    .map((s) => Math.abs(s.dtMin));
  // Survey usage (rating-centric): how many distinct ratings were used and how many reused.
  const usedIdx = matched.filter((s) => s.v != null && Number.isFinite(s.v) && s.proIdx >= 0)
    .map((s) => s.proIdx);
  const useCounts = new Map();
  usedIdx.forEach((k) => useCounts.set(k, (useCounts.get(k) || 0) + 1));
  const nProUsed = useCounts.size;
  let nProReused = 0;
  useCounts.forEach((c) => { if (c > 1) nProReused++; });
  const nProTotal = proSorted.length;
  // Matched/unmatched flag PER DISPLAYED PRO (aligned to painSeries.t/y order, not proSorted order),
  // for the timeline pain-row closed/open-circle overlay. A rating is "matched" iff it claimed >=1
  // PSD (its proIdx appears in useCounts). proSorted[pk].i0 maps the matcher's index back to the
  // painSeries index. Length = painSeries.t.length (unparseable rows stay false — never matchable).
  const painMatched = new Array(painSeries.t.length).fill(false);
  useCounts.forEach((_c, pk) => {
    const i0 = proSorted[pk] && proSorted[pk].i0;
    if (Number.isInteger(i0)) painMatched[i0] = true;
  });
  // cuts computed on the matched continuous values (exactly as the backend binarizes the labels).
  const matchedValues = matched.filter((s) => s.v != null && Number.isFinite(s.v)).map((s) => s.v);
  const cuts = computeCuts(matchedValues, strategy, percentileLow, percentileHigh);

  // 2nd pass: assign each sample its bin + build the (channel,t) lookup for the timeline.
  // Also tally matched samples by SOURCE (TD streaming vs montage/survey), since most of the pool
  // is TD streaming, not montage PSDs — the readout breaks the count down so "neural samples" is
  // not misread as "PSDs".
  const samples = [];
  const binByKey = new Map();
  let nHigh = 0, nLow = 0, nMid = 0, nMatchedTd = 0, nMatchedMontage = 0, nMatchedEvent = 0;
  // Per-group (low/excluded/high) modality breakdown for the in-plot detail boxes. psd_scan_index
  // ships three sources: "TD streaming", "Montage/survey", and "Patient event" (the imported
  // event-marker PSDs). LSB (band power) is NOT pooled — its slot stays 0 (renderer shows "n/a").
  const bySrc = { low: { td: 0, montage: 0, event: 0, lsb: 0 },
                  high: { td: 0, montage: 0, event: 0, lsb: 0 },
                  excluded: { td: 0, montage: 0, event: 0, lsb: 0 } };
  const srcBucket = (src) => {
    const s = String(src || "").toLowerCase();
    if (s.indexOf("td") >= 0) return "td";
    if (s.indexOf("event") >= 0) return "event";
    return "montage";
  };
  for (const s of matched) {
    let bin;
    if (s.v == null || !Number.isFinite(s.v)) bin = "unmatched";
    else {
      bin = classify(s.v, cuts);
      if (bin === "high") nHigh++; else if (bin === "low") nLow++; else nMid++;
      const srcKey = srcBucket(s.source);
      if (srcKey === "td") nMatchedTd++; else if (srcKey === "event") nMatchedEvent++; else nMatchedMontage++;
      if (bySrc[bin]) bySrc[bin][srcKey] += 1;   // bin is high|low|excluded (matched-only branch)
    }
    samples.push({ ...s, bin });
    // Collision-proof key set: `Math.round(s.t)` buckets samples to the integer second, and >=2
    // samples can share a (channel, second) — most often patient-event PSDs. Plain Map.set would be
    // last-write-wins, so the painted timeline could disagree with the badge counts (which tally the
    // full per-sample array). Resolve collisions by PRECEDENCE: a matched class (high/low/excluded)
    // always wins over "unmatched", so a key with any matched sample paints as that class.
    const tk = `${String(s.channel).toUpperCase()}|${Math.round(s.t)}`;
    const prev = binByKey.get(tk);
    if (prev === undefined || (prev === "unmatched" && bin !== "unmatched")) binByKey.set(tk, bin);
  }
  offsets.sort((a, b) => a - b);
  const medianOffset = offsets.length
    ? (offsets.length % 2 ? offsets[(offsets.length - 1) / 2]
        : (offsets[offsets.length / 2 - 1] + offsets[offsets.length / 2]) / 2)
    : null;

  return {
    samples, binByKey, matchedValues, cuts, painMatched,
    counts: {
      n_sessions: scanIndex.length,
      n_matched: matchedValues.length,
      n_high: nHigh, n_low: nLow,
      n_excluded_middle: (strategy === "tertile" || strategy === "percentile") ? nMid : 0,
      n_matched_td: nMatchedTd, n_matched_montage: nMatchedMontage,
      n_matched_event: nMatchedEvent,
      by_source: bySrc,
      tolerance_min: toleranceMin,
      median_abs_offset_min: medianOffset,
      max_per_rating: maxPerRating,
      refractory_min: refractoryMin,
      match_direction: matchDirection,
      n_capped_dropped: nCappedDropped,
      survey_usage: (() => {
        // PRO-first depth-of-coverage stats: per rating that got data, how many neural samples
        // did it receive? Reported alongside coverage so the caption can show both at once.
        const cArr = Array.from(useCounts.values());
        cArr.sort((a, b) => a - b);
        const meanPP = cArr.length ? cArr.reduce((s, x) => s + x, 0) / cArr.length : 0;
        const medianPP = cArr.length
          ? (cArr.length % 2 ? cArr[(cArr.length - 1) / 2]
              : (cArr[cArr.length / 2 - 1] + cArr[cArr.length / 2]) / 2) : 0;
        return {
          n_pro_total: nProTotal, n_pro_used: nProUsed,
          n_pro_unused: Math.max(0, nProTotal - nProUsed),
          n_pro_reused: nProReused,
          pct_pro_used: nProTotal ? Math.round((1000 * nProUsed) / nProTotal) / 10 : 0,
          psd_per_pro_mean: Math.round(meanPP * 100) / 100,
          psd_per_pro_median: Math.round(medianPP * 10) / 10,
          psd_per_pro_max: cArr.length ? cArr[cArr.length - 1] : 0,
        };
      })(),
      pct_psd_used: scanIndex.length
        ? Math.round((1000 * matchedValues.length) / scanIndex.length) / 10 : 0,
    },
  };
}
