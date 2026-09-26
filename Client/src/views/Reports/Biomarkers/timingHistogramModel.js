/**
 * The numbers behind the timing histogram at the top of the Binarization card (the PI, 2026-09-21,
 * option C): when each neural sample the card can pair falls relative to the NEAREST pain report,
 * in signed minutes (negative = the sample was recorded before the report), binned per source over
 * the match window plus 25% on each side. Inside the window the bars are in colour; in the tails,
 * and on the side the direction toggle excludes, they are grey. Pure functions, tested on a fixture;
 * `TimingHistogram.js` draws the result. (Named ...Model.js, not timingHistogram.js: the Mac's
 * filesystem folds the component's TimingHistogram.js onto that name.)
 */

/** The three sources the sample index carries, in legend order, with the offline figure's colours
 *  (matplotlib's default cycle: green for the streaming TD, blue for the montage, orange for the
 *  patient-event PSD) so the page's histogram matches the one the PI read first. The names follow
 *  the PI's one vocabulary for the page (2026-09-25): TD for band power worked out from a
 *  time-domain recording, PSD for the device's own 30 s snapshot; the caption under the legend
 *  defines both. A MONTAGE OR SURVEY SAMPLE IS TD (2026-09-26): the sample index's "Montage" rows
 *  are Welch over the recording's own time-domain signal (`_psd_sample_index` / `_welch_rows_into`
 *  in Biomarkers/bravo_service.py), so it sits in the TD group, beside streaming, as "TD (montage)".
 *  Until then it was drawn as "PSD (montage)". */
export const SOURCE_SERIES = [
  { key: "trace", name: "TD (streaming)", color: "#2CA02C" },
  { key: "td_montage", name: "TD (montage)", color: "#1F77B4" },
  { key: "event", name: "PSD (patient event)", color: "#FF7F0E" },
];
export const TAIL_GREY = "#B0B7BC";

/** Which series a sample index entry's `source` belongs to: the same buckets the card's model uses.
 *  The server writes four labels ("BrainSense streaming", "Indefinite stream", "Montage",
 *  "Patient event"); a label it does not write belongs to no series and is not drawn. */
export function seriesOf(source) {
  const s = String(source || "").toLowerCase();
  if (s.indexOf("td") >= 0 || s.indexOf("stream") >= 0 || s.indexOf("indefinite") >= 0) return "trace";
  if (s.indexOf("montage") >= 0 || s.indexOf("survey") >= 0) return "td_montage";
  if (s.indexOf("event") >= 0) return "event";
  return "other";
}

/** Signed minutes from each sample to its nearest report: sample time minus report time, so a
 *  sample recorded before the report is negative. */
export function sampleOffsetsMin(scanIndex, painSeries) {
  if (!Array.isArray(scanIndex) || !scanIndex.length) return [];
  if (!painSeries || !Array.isArray(painSeries.t) || !painSeries.t.length) return [];
  const pro = painSeries.t
    .map((t, i) => ({ t, v: painSeries.y ? painSeries.y[i] : 0 }))
    .filter((p) => Number.isFinite(p.t) && Number.isFinite(p.v))
    .map((p) => p.t)
    .sort((a, b) => a - b);
  if (!pro.length) return [];
  const out = [];
  for (const e of scanIndex) {
    const t = Number(e && e.t);
    if (!Number.isFinite(t)) continue;
    let lo = 0, hi = pro.length;
    while (lo < hi) { const m = (lo + hi) >> 1; if (pro[m] < t) lo = m + 1; else hi = m; }
    let best = Infinity;
    for (const i of [lo - 1, lo]) {
      if (i < 0 || i >= pro.length) continue;
      const d = t - pro[i];
      if (Math.abs(d) < Math.abs(best)) best = d;
    }
    out.push({ dtMin: best / 60, series: seriesOf(e.source) });
  }
  return out;
}

/** A bin width that keeps about 40 bins across the shown range, on a 1 / 2.5 / 5 / 10 ladder. */
export function niceStep(rangeMin) {
  const raw = rangeMin / 40;
  const p = Math.pow(10, Math.floor(Math.log10(raw)));
  const r = raw / p;
  return (r < 1.5 ? 1 : r < 3.5 ? 2.5 : r < 7.5 ? 5 : 10) * p;
}

/**
 * Bin the offsets for the window. `matchDirection` "prior" colours only the samples recorded
 * BEFORE the report (dtMin <= 0); "nearest" and "pro_first" colour both sides. A sample is
 * "inside" when |dt| <= window AND on a coloured side; everything else drawn is "outside" (grey).
 */
export function timingHistogramData(offsets, { windowMin, matchDirection }) {
  const W = Number(windowMin) > 0 ? Number(windowMin) : 1;
  const limMin = W * 1.25;
  const step = niceStep(2 * limMin);
  const first = -Math.ceil(limMin / step) * step;
  const edges = [];
  for (let e = first; e <= limMin + 1e-9; e += step) edges.push(+e.toFixed(6));
  if (edges[edges.length - 1] < limMin) edges.push(+(edges[edges.length - 1] + step).toFixed(6));
  const nb = edges.length - 1;
  const centers = edges.slice(0, -1).map((e) => +(e + step / 2).toFixed(6));
  const priorOnly = String(matchDirection || "").toLowerCase() === "prior";
  const series = {};
  for (const s of SOURCE_SERIES) series[s.key] = { inside: new Array(nb).fill(0), outside: new Array(nb).fill(0) };
  let nInside = 0, nTails = 0;
  for (const o of offsets || []) {
    const d = o.dtMin;
    if (!Number.isFinite(d) || d < edges[0] - 1e-9 || d > edges[nb] + 1e-9) continue;   // both edges inclusive: a sample exactly at the shown limit is a tail sample, not off the axis
    if (!series[o.series]) continue;
    const b = Math.min(nb - 1, Math.max(0, Math.floor((d - edges[0]) / step)));
    const inWindow = Math.abs(d) <= W + 1e-9;
    const onColouredSide = !priorOnly || d <= 0;
    if (inWindow && onColouredSide) { series[o.series].inside[b] += 1; nInside += 1; }
    else { series[o.series].outside[b] += 1; if (Math.abs(d) <= limMin + 1e-9) nTails += 1; }
  }
  return { windowMin: W, limMin, step, edges, centers, series, nInside, nTails, priorOnly };
}
