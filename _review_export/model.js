// ---- Ported from binarizationModel.js (the production client logic) ----------------------
function percentile(values, q) {
  if (!values || values.length === 0) return null;
  const a = [...values].sort((x, y) => x - y);
  const idx = (q / 100) * (a.length - 1);
  const lo = Math.floor(idx), hi = Math.ceil(idx);
  if (lo === hi) return a[lo];
  return a[lo] + (a[hi] - a[lo]) * (idx - lo);
}
function matchNearest(tSec, proSorted, tolSec) {
  if (!proSorted.length || !(tolSec > 0)) return null;
  let lo = 0, hi = proSorted.length;
  while (lo < hi) { const mid = (lo + hi) >> 1; if (proSorted[mid].t < tSec) lo = mid + 1; else hi = mid; }
  let best = -1, bestD = Infinity;
  for (const k of [lo - 1, lo]) {
    if (k >= 0 && k < proSorted.length) {
      const dd = Math.abs(proSorted[k].t - tSec);
      if (dd <= tolSec && dd < bestD) { best = k; bestD = dd; }
    }
  }
  if (best < 0) return null;
  return { v: proSorted[best].v, dtMin: (proSorted[best].t - tSec) / 60 };
}
function computeCuts(vals, strategy, lowPct, highPct) {
  if (!vals || vals.length === 0) return { kind: "none" };
  if (strategy === "tertile" || strategy === "percentile") {
    const loQ = strategy === "tertile" ? 33.3333 : Number(lowPct);
    const hiQ = strategy === "tertile" ? 66.6667 : Number(highPct);
    return { kind: "two-cut", lowCut: percentile(vals, loQ), highCut: percentile(vals, hiQ) };
  }
  if (strategy === "median") return { kind: "one-cut", cut: percentile(vals, 50) };
  let c0 = percentile(vals, 25), c1 = percentile(vals, 75);
  for (let it = 0; it < 25; it++) {
    let s0 = 0, n0 = 0, s1 = 0, n1 = 0;
    for (const v of vals) { if (Math.abs(v - c0) <= Math.abs(v - c1)) { s0 += v; n0++; } else { s1 += v; n1++; } }
    const nc0 = n0 ? s0 / n0 : c0, nc1 = n1 ? s1 / n1 : c1;
    if (Math.abs(nc0 - c0) < 1e-9 && Math.abs(nc1 - c1) < 1e-9) { c0 = nc0; c1 = nc1; break; }
    c0 = nc0; c1 = nc1;
  }
  return { kind: "one-cut", cut: (c0 + c1) / 2 };
}
function classify(v, cuts) {
  if (cuts.kind === "two-cut") return v <= cuts.lowCut ? "low" : (v >= cuts.highCut ? "high" : "excluded");
  if (cuts.kind === "one-cut") return v <= cuts.cut ? "low" : "high";
  return "unmatched";
}
function computeMatchedScanModel(scanIndex, painSeries, toleranceMin, strategy, lowPct, highPct) {
  const empty = { samples: [], binByKey: new Map(), matchedValues: [], cuts: { kind: "none" },
    counts: { n_sessions: 0, n_matched: 0, n_high: 0, n_low: 0, n_excluded_middle: 0,
              tolerance_min: toleranceMin, median_abs_offset_min: null } };
  if (!Array.isArray(scanIndex) || !scanIndex.length || !painSeries || !painSeries.t.length) return empty;
  const tolSec = (toleranceMin && toleranceMin > 0) ? toleranceMin * 60 : 0;
  const proSorted = painSeries.t.map((t, i) => ({ t, v: painSeries.y[i] }))
    .filter((p) => Number.isFinite(p.t) && Number.isFinite(p.v)).sort((a, b) => a.t - b.t);
  const matched = [], offsets = [];
  for (const e of scanIndex) {
    const m = matchNearest(e.t, proSorted, tolSec);
    matched.push({ t: e.t, channel: e.channel, source: e.source, v: m ? m.v : null });
    if (m) offsets.push(Math.abs(m.dtMin));
  }
  const matchedValues = matched.filter((s) => s.v != null && Number.isFinite(s.v)).map((s) => s.v);
  const cuts = computeCuts(matchedValues, strategy, lowPct, highPct);
  const samples = [], binByKey = new Map();
  let nHigh = 0, nLow = 0, nMid = 0;
  for (const s of matched) {
    let bin;
    if (s.v == null || !Number.isFinite(s.v)) bin = "unmatched";
    else { bin = classify(s.v, cuts); if (bin === "high") nHigh++; else if (bin === "low") nLow++; else nMid++; }
    samples.push({ ...s, bin });
    binByKey.set(`${String(s.channel).toUpperCase()}|${Math.round(s.t)}`, bin);
  }
  offsets.sort((a, b) => a - b);
  const medianOffset = offsets.length ? (offsets.length % 2 ? offsets[(offsets.length - 1) / 2]
      : (offsets[offsets.length / 2 - 1] + offsets[offsets.length / 2]) / 2) : null;
  return { samples, binByKey, matchedValues, cuts,
    counts: { n_sessions: scanIndex.length, n_matched: matchedValues.length, n_high: nHigh, n_low: nLow,
      n_excluded_middle: (strategy === "tertile" || strategy === "percentile") ? nMid : 0,
      tolerance_min: toleranceMin, median_abs_offset_min: medianOffset } };
}
const BIN = { high: "#D55E00", low: "#0072B2", excluded: "#5A6066" };
const DIM = "#AEB4BB", DIMF = "rgba(150,157,165,0.42)";