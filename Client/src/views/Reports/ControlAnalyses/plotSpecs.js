/**
 * The Plotly figures of the saved checks against chance and against the current, as pure functions
 * from a saved result to `{ data, layout }` (the PI, 2026-10-02: the figures at the foot of the
 * Biomarkers page were hand-drawn SVG with no hover; they are Plotly figures now, and hovering a
 * mark prints its own numbers).
 *
 * RULES THESE FOLLOW
 *  - No number is computed here. Every value drawn or printed on a hover is a field of the saved
 *    result (the only arithmetic is the distance from a dot to the ends of its own interval, which
 *    Plotly's error bars need).
 *  - The hover text of a mark is built only from fields that mark's row already carries; a field the
 *    row lacks prints "not given", never a guess.
 *  - Every x axis runs from a tick to a tick and ends on a labelled tick, so the last value is never
 *    left unlabelled (`niceAxis`). The Stepped-current figure's band axis used to carry fixed ticks
 *    at 10 to 50 Hz while its bands run beyond them, so the right-hand edge had no number on it.
 *  - Series are named by a label at their right end, never a legend box; colours are the shared
 *    data colours.
 */
import { T, TYPE } from "assets/theme/base/tokens";
import { CATEGORICAL, SIDE, CONTEXT, textInk } from "assets/theme/base/dataColors";
import { FONT_FAMILY, FIGURE_TEXT_PX, REF_LINE, directLabel } from "views/Reports/figureStyle";
import { painScoreLabel } from "views/Reports/painScores";
import { fmtP } from "views/Reports/Biomarkers/gridReadouts";

export const SERIES = [CATEGORICAL[0], CATEGORICAL[2], CATEGORICAL[3], CATEGORICAL[5], CATEGORICAL[4], CATEGORICAL[1]];
export const READING = { current: CONTEXT, bands: CATEGORICAL[0], adjusted: CATEGORICAL[2] };
export const GROUP_INK = { family: CATEGORICAL[0], far: CATEGORICAL[2] };
const SIDE_INK = { Left: SIDE.left, Right: SIDE.right };
/** The right margin that holds the direct labels, in px. */
export const LABEL_MARGIN = 170;
/** The one `uirevision` of every check figure: a redraw in place never resets a reader's zoom. */
export const UIREVISION = "control-check";

const TITLE_PX = TYPE.body.fontSize;   // the page's body size, as the notes under the heat maps

const WORD = { ZERO: "0", ONE: "1", TWO: "2", THREE: "3" };
/** A sensing pair as the pages write it: ONE_THREE_LEFT -> L 1-3+. */
export function pairName(ch) {
  const p = String(ch).split("_");
  return p.length === 3 && WORD[p[0]] && WORD[p[1]] && (p[2] === "LEFT" || p[2] === "RIGHT")
    ? `${p[2][0]} ${WORD[p[0]]}-${WORD[p[1]]}⁺` : String(ch);
}

const fin = (v) => v != null && Number.isFinite(Number(v));
/** A fixed-decimal number from a field, or "not given". */
export const fx = (v, d = 2) => (fin(v) ? Number(v).toFixed(d) : "not given");
/** "+0.38" / "-0.34": a signed number from a field. */
export const sg = (v, d = 2) => (fin(v) ? `${Number(v) >= 0 ? "+" : "−"}${Math.abs(Number(v)).toFixed(d)}` : "not given");
const range95 = (lo, hi, f = sg) => (fin(lo) && fin(hi) ? `95% range ${f(lo)} to ${f(hi)}` : "no 95% range");
const pq = (p, q) => [fin(q) ? `q ${fmtP(q)} (after allowing for the bands tested)` : null,
  fin(p) ? `p ${fmtP(p)}` : null].filter(Boolean).join(" · ");

/**
 * An axis that runs from a tick to a tick. `step` is the tick spacing; the range starts at the tick
 * at or below the smallest value and ends at the tick at or above the largest, so the last value
 * always has a labelled tick at or beyond it, and the right-hand edge carries a number. `include`
 * lists values the range must also cover.
 */
export function niceAxis(values, step, include = []) {
  const all = [...values, ...include].filter(fin).map(Number);
  if (!all.length) return { range: [0, step], tickvals: [0, step], ticktext: ["0", String(step)] };
  const dec = Math.max(0, Math.ceil(-Math.log10(step) - 1e-9));
  const lo = Math.floor(Math.min(...all) / step + 1e-9) * step;
  const hi = Math.ceil(Math.max(...all) / step - 1e-9) * step;
  const n = Math.round((hi - lo) / step);
  const round = (v) => Number(v.toFixed(Math.max(dec, 0) + 2));
  const tickvals = Array.from({ length: n + 1 }, (_, i) => round(lo + i * step));
  return { range: [round(lo), round(hi)], tickvals, ticktext: tickvals.map((v) => v.toFixed(dec)) };
}

const TICKFONT = { family: FONT_FAMILY, size: FIGURE_TEXT_PX, color: T.ink3 };
const axisTitle = (text) => ({ text, font: { family: FONT_FAMILY, size: FIGURE_TEXT_PX, color: T.ink3 }, standoff: 8 });

/** Labels at the right end of each series, pushed apart (in data units) so none overlaps the next. */
function endLabels(items, span) {
  const gap = span * 0.07;
  const sorted = [...items].sort((a, b) => a.y - b.y);
  for (let i = 1; i < sorted.length; i += 1) {
    if (sorted[i].y - sorted[i - 1].y < gap) sorted[i] = { ...sorted[i], y: sorted[i - 1].y + gap };
  }
  return sorted.map((it) => ({ ...directLabel(1, it.y, it.text, textInk(it.color)), xref: "paper", yref: "y" }));
}

const refLineY = (y) => ({ type: "line", xref: "paper", x0: 0, x1: 1, yref: "y", y0: y, y1: y, line: REF_LINE });
const refLineX = (x, text) => ({
  shape: { type: "line", xref: "x", x0: x, x1: x, yref: "paper", y0: 0, y1: 1, line: REF_LINE },
  note: { xref: "x", yref: "paper", x, y: 1, yanchor: "bottom", xanchor: "center", showarrow: false, text,
    font: { family: FONT_FAMILY, size: FIGURE_TEXT_PX, color: T.ink3 } },
});

const hoverLabel = { font: { family: FONT_FAMILY, size: FIGURE_TEXT_PX, color: T.ink }, bgcolor: T.surface, bordercolor: T.rule };

/** Error bars from a dot to the ends of its own saved interval; a missing end draws none. */
const errY = (rows, val, lo, hi, color) => ({
  type: "data", symmetric: false, color, thickness: 1.5, width: 0,
  array: rows.map((r) => (fin(r[hi]) && fin(r[val]) ? Number(r[hi]) - Number(r[val]) : 0)),
  arrayminus: rows.map((r) => (fin(r[lo]) && fin(r[val]) ? Number(r[val]) - Number(r[lo]) : 0)),
});

/** Every figure's title: short, says what is plotted, no question and no lay phrase (the PI, 2026-10-02). */
export const TITLE = {
  zeroMa: "Band-pain correlation, current removed",
  currentExplains: "Out-of-sample stimulation-current prediction",
  currentMemory: "Out-of-sample R\u00b2 by current memory",
  regression: "Regression to the mean: block averages",
  carryOver: "Pain change, descending vs ascending current",
  persistence: "Pain autocorrelation by lag",
  stepped: "Band-power change per mA",
  research: "Out-of-sample pain prediction by band",
  device: "AUC by band centre",
};

/** The pale neutral behind every second row of a row figure (the PI, 2026-10-02: rows were hard to
 *  follow). The shared table-band grey; none of the figures' dot or line colours is this one. */
export const ROW_SHADE = T.fillMuted;

/** Alternating row bands, drawn below the data, for a figure with one row per pair or length. */
export const rowShades = (n) => Array.from({ length: n }, (_, i) => i).filter((i) => i % 2 === 1)
  .map((i) => ({ type: "rect", xref: "paper", x0: 0, x1: 1, yref: "y", y0: i - 0.5, y1: i + 0.5,
    fillcolor: ROW_SHADE, line: { width: 0 }, layer: "below" }));

const base = ({ figureTitle, ...extra }) => {
  const margin = { l: 56, r: 24, t: 16, b: 52, ...(extra.margin || {}) };
  return {
    showlegend: false, hovermode: "closest", hoverlabel: hoverLabel, uirevision: UIREVISION, ...extra,
    margin: { ...margin, t: Math.max(margin.t, 44) },
    title: { text: figureTitle, x: 0, xanchor: "left", y: 0.98, yanchor: "top",
      font: { family: FONT_FAMILY, size: TITLE_PX, color: T.ink } },
  };
};
const hoverTrace = (t) => ({ hoverinfo: "text", showlegend: false, ...t });

/** 1. Band against pain with the current off: one series per stretch, filled where q < 0.05. */
export function zeroMaSpec({ rows, stretches }) {
  const centres = rows.map((b) => b.centre);
  const m = stretches.length;
  const xa = niceAxis(centres, 5, [8, 30]);
  const ys = rows.flatMap((b) => [b.rho, b.lo, b.hi]).filter(fin).map(Number);
  const ymax = Math.max(0.8, Math.ceil(Math.max(0, ...ys.map(Math.abs)) * 10) / 10);
  const data = stretches.map((s, k) => {
    const rs = rows.filter((b) => b.stretch === s);
    const col = SERIES[k % SERIES.length];
    return hoverTrace({
      type: "scatter", mode: "markers", name: s,
      x: rs.map((b) => Number(b.centre) + (k - (m - 1) / 2) * 0.25), y: rs.map((b) => b.rho),
      error_y: errY(rs, "rho", "lo", "hi", col),
      marker: { size: 9, color: rs.map((b) => (fin(b.q) && b.q < 0.05 ? col : T.surface)), line: { color: col, width: 1.5 } },
      hovertext: rs.map((b) => [`${b.centre} Hz · ${s}`,
        `correlation with pain ${sg(b.rho)} (${range95(b.lo, b.hi)})`, pq(b.p, b.q),
        `${fx(b.n, 0)} ratings on ${fx(b.days, 0)} days`].filter(Boolean).join("<br>")),
    });
  });
  return {
    data,
    layout: base({ figureTitle: TITLE.zeroMa,
      xaxis: { title: axisTitle("band centre (Hz)"), tickfont: TICKFONT, ...xa },
      yaxis: { title: axisTitle("correlation with pain"), tickfont: TICKFONT, range: [-ymax, ymax],
        zeroline: false },
      shapes: [refLineY(0)],
    }),
  };
}

/** One row per sensing pair and length of signal, three readings per row, each with a bar at its
 *  own shuffled-data 95th percentile (2 and 8). */
function rowPlot({ figureTitle, rows, readings, xValues, xInclude, xStep, xTitle, refX, refText, rightMargin, rowLabel }) {
  const n = rows.length;
  const xa = niceAxis(xValues, xStep, xInclude);
  const data = [];
  readings.forEach(({ key, label, baseColor, fill, dy, value, interval, nullAt, hover }) => {
    const pts = rows.map((r, i) => ({ r, i })).filter(({ r }) => fin(value(r)));
    if (!pts.length) return;
    const t = hoverTrace({
      type: "scatter", mode: "markers", name: key,
      x: pts.map(({ r }) => Number(value(r))), y: pts.map(({ i }) => i + dy),
      marker: { size: 9, color: pts.map(({ r }) => fill(r)), line: { color: baseColor, width: 1.5 } },
      hovertext: pts.map(({ r }) => hover(r)),
    });
    if (interval) {
      const lo = pts.map(({ r }) => interval(r)[0]); const hi = pts.map(({ r }) => interval(r)[1]);
      t.error_x = { type: "data", symmetric: false, color: baseColor, thickness: 1.5, width: 0,
        array: hi.map((h, j) => (fin(h) ? Number(h) - Number(value(pts[j].r)) : 0)),
        arrayminus: lo.map((l, j) => (fin(l) ? Number(value(pts[j].r)) - Number(l) : 0)) };
    }
    data.push(t);
    if (nullAt) {
      const np = pts.filter(({ r }) => fin(nullAt(r)));
      if (np.length) {
        data.push(hoverTrace({
          type: "scatter", mode: "markers", name: `null:${key}`,
          x: np.map(({ r }) => Number(nullAt(r))), y: np.map(({ i }) => i + dy),
          marker: { symbol: "line-ns", size: 16, color: baseColor, line: { color: baseColor, width: 3 } },
          hovertext: np.map(({ r }) => `${rowLabel(r)} \u00b7 ${label}<br>chance alone reaches this 1 time in 20: ${fx(nullAt(r), 3)}`),
        }));
      }
    }
  });
  const ref = refX ? refLineX(refX, refText) : null;
  const first = readings.map((rd) => ({ y: rd.dy, text: rd.label, color: rd.baseColor }));
  const annotations = [
    ...(ref ? [ref.note] : []),
    ...(n > 0 ? first.map((it) => ({ ...directLabel(1, it.y, it.text, textInk(it.color)), xref: "paper", yref: "y" })) : []),
  ];
  return {
    data,
    layout: base({
      figureTitle,
      margin: { l: 150, r: rightMargin, t: 64, b: 56 },
      xaxis: { title: axisTitle(xTitle), tickfont: TICKFONT, ...xa },
      yaxis: { tickmode: "array", tickvals: rows.map((_, i) => i), ticktext: rows.map(rowLabel),
        range: [n - 0.5, -0.5], zeroline: false, showgrid: false, tickfont: { ...TICKFONT, color: T.ink } },
      shapes: [...rowShades(n), ...(ref ? [ref.shape] : [])],
      annotations,
    }),
  };
}
const READING_BY_KEY = {
  current_alone: READING.current, bands: READING.bands, bands_without_current: READING.adjusted,
};
const READING_COLOR = (key) => READING_BY_KEY[key];

/** 2. What the current explains: held-out area for the current alone, every band, bands without the
 *  current, each against its own shuffled-data 95th percentile. */
export function currentExplainsSpec({ rows }) {
  const rowLabel = (r) => `${pairName(r.pair)}, ${r.seconds} s (${r.n})`;
  const mk = (key, label, dy, nullKey, pKey) => ({
    key, label, dy, baseColor: READING_COLOR(key), fill: () => READING_COLOR(key),
    value: (r) => r[key], nullAt: nullKey ? (r) => r[nullKey] : null,
    hover: (r) => [`${rowLabel(r)} · ${label}`, `${fx(r[key], 3)} (0.5 = coin toss)`,
      pKey && fin(r[pKey]) ? `p ${fmtP(r[pKey])}` : null].filter(Boolean).join("<br>"),
  });
  const readings = [mk("current_alone", "current alone", -0.25, null, null),
    mk("bands", "every band", 0, "null_p95", "p"),
    mk("bands_without_current", "every band, current taken out", 0.25, "bands_without_current_null_p95", "bands_without_current_p")];
  const xValues = rows.flatMap((r) => [r.current_alone, r.bands, r.bands_without_current, r.null_p95, r.bands_without_current_null_p95]);
  return rowPlot({ figureTitle: TITLE.currentExplains, rows, readings, xValues, xInclude: [0.3, 0.9, 0.5], xStep: 0.1,
    xTitle: "how well it predicts pain in weeks it was not fitted on (0.5 = coin toss)",
    refX: 0.5, refText: "0.5 = coin toss", rightMargin: LABEL_MARGIN + 60, rowLabel });
}

/** Band detector, research version: held-out rank correlation (0 is chance) with 95% ranges. */
export function bandDetectorResearchSpec({ rows }) {
  const rowLabel = (r) => `${pairName(r.pair)}, ${r.seconds} s (${r.reading.n})`;
  const mk = (key, label, dy) => ({
    key, label, dy, baseColor: READING_COLOR(key),
    fill: (r) => { const b = r.reading[key]; return fin(b && b.q) && b.q < 0.05 ? READING_COLOR(key) : T.surface; },
    value: (r) => (r.reading[key] ? r.reading[key].rho : null),
    interval: (r) => [r.reading[key] ? r.reading[key].lo : null, r.reading[key] ? r.reading[key].hi : null],
    nullAt: key === "current_alone" ? null : (r) => (r.reading[key] ? r.reading[key].null_p95 : null),
    hover: (r) => { const b = r.reading[key] || {};
      return [`${rowLabel(r)} · ${label}`, `held-out rank correlation ${sg(b.rho)} (${range95(b.lo, b.hi)})`,
        pq(b.p, b.q)].filter(Boolean).join("<br>"); },
  });
  const readings = [mk("current_alone", "current alone", -0.25), mk("bands", "every band", 0),
    mk("bands_without_current", "every band, current taken out", 0.25)];
  const xValues = rows.flatMap((r) => ["current_alone", "bands", "bands_without_current"].flatMap((k) => {
    const b = r.reading[k] || {}; return [b.rho, b.lo, b.hi, b.null_p95]; }));
  return rowPlot({ figureTitle: TITLE.research, rows, readings, xValues, xInclude: [-0.6, 0.8, 0], xStep: 0.2,
    xTitle: "how well it predicts pain in weeks it was not fitted on (rank correlation; 0 = chance)",
    refX: 0, refText: "0 = chance", rightMargin: LABEL_MARGIN + 60, rowLabel });
}

/** 4. A current with memory: held-out R squared against the time constant, one line per pain score. */
export function currentMemorySpec({ curves }) {
  const taus = curves.length ? curves[0].rows.map((r) => r.tau_h) : [];
  const lab = (t) => (t === 0 ? "0" : t < 24 ? `${t} h` : `${t / 24} d`);
  const all = curves.flatMap((c) => c.rows.map((r) => r.r2)).filter(fin).map(Number);
  const lo = Math.min(-0.2, ...all); const hi = Math.max(0.3, ...all);
  const ya = niceAxis([lo, hi], 0.1);
  const data = curves.map((c, k) => {
    const col = SERIES[k % SERIES.length];
    return hoverTrace({
      type: "scatter", mode: "lines+markers", name: c.score,
      x: c.rows.map((_, i) => i), y: c.rows.map((r) => r.r2),
      line: { color: col, width: 2 }, marker: { size: 7, color: col },
      hovertext: c.rows.map((r) => [`${painScoreLabel(c.score)} · current remembered ${lab(r.tau_h)}`,
        `share of pain predicted (R²) ${sg(r.r2, 3)}`, `${fx(c.n, 0)} ratings`].join("<br>")),
    });
  });
  const ends = curves.filter((c) => c.rows.length).map((c, k) => ({
    y: c.rows[c.rows.length - 1].r2, text: `${painScoreLabel(c.score)} (${c.n} ratings)`, color: SERIES[k % SERIES.length] }));
  return {
    data,
    layout: base({ figureTitle: TITLE.currentMemory,
      margin: { l: 56, r: LABEL_MARGIN + 30, t: 16, b: 56 },
      xaxis: { title: axisTitle("how long the current is remembered (0 is the current in force)"), tickfont: TICKFONT,
        tickmode: "array", tickvals: taus.map((_, i) => i), ticktext: taus.map(lab),
        range: [-0.4, Math.max(taus.length - 0.6, 1)] },
      yaxis: { title: axisTitle("share of pain predicted (R²)"), tickfont: TICKFONT, range: ya.range,
        tickvals: ya.tickvals, ticktext: ya.ticktext, zeroline: false },
      shapes: [refLineY(0)],
      annotations: endLabels(ends, ya.range[1] - ya.range[0]),
    }),
    taus,
  };
}

/** 7. Regression to the mean: block averages of the target setting against every other setting. */
export function regressionToMeanSpec({ result }) {
  const setting = result.setting || {};
  const nBlocks = result.n_blocks || 3;
  const series = [
    ["target", `${setting.amp_mA_Left}/${setting.amp_mA_Right} mA (${result.n_target || 0} stretches)`, CATEGORICAL[0], result.target || { by_block: [] }],
    ["other", `every other setting in this group (${result.n_other || 0})`, CONTEXT, result.other || { by_block: [] }],
  ];
  const means = series.flatMap(([, , , g]) => (g.by_block || []).flatMap((r) => [r.mean, fin(r.se) ? r.mean + r.se : r.mean, fin(r.se) ? r.mean - r.se : r.mean])).filter(fin).map(Number);
  const ymax = Math.max(1, ...means.map(Math.abs));
  const ya = niceAxis([-ymax, ymax], ymax > 4 ? 2 : 1);
  const data = series.map(([key, lab, col, g], k) => {
    const rs = g.by_block || [];
    return hoverTrace({
      type: "scatter", mode: "markers", name: key,
      x: rs.map((r) => r.block + (k - 0.5) * 0.12), y: rs.map((r) => r.mean),
      error_y: { type: "data", symmetric: false, color: col, thickness: 1.5, width: 0,
        array: rs.map((r) => (fin(r.se) ? r.se : 0)), arrayminus: rs.map((r) => (fin(r.se) ? r.se : 0)) },
      marker: { size: 9, color: col },
      hovertext: rs.map((r) => [`${lab} · block ${r.block + 1}`, `average ${sg(r.mean)}`,
        `± 1 standard error ${fx(r.se, 2)}`, `${fx(r.n, 0)} stretches`].join("<br>")),
    });
  });
  const ends = series.filter(([, , , g]) => (g.by_block || []).length).map(([, lab, col, g]) => ({
    y: g.by_block[g.by_block.length - 1].mean, text: lab, color: col }));
  return {
    data,
    layout: base({ figureTitle: TITLE.regression,
      margin: { l: 56, r: LABEL_MARGIN + 80, t: 16, b: 56 },
      xaxis: { title: axisTitle("block of weeks, in time order"), tickfont: TICKFONT, tickmode: "array",
        tickvals: Array.from({ length: nBlocks }, (_, i) => i), ticktext: Array.from({ length: nBlocks }, (_, i) => `block ${i + 1}`),
        range: [-0.4, nBlocks - 0.6] },
      yaxis: { title: axisTitle("pain against today's setting"), tickfont: TICKFONT, range: ya.range,
        tickvals: ya.tickvals, ticktext: ya.ticktext, zeroline: false },
      shapes: [refLineY(0)],
      annotations: endLabels(ends, ya.range[1] - ya.range[0]),
    }),
  };
}

/** 6. Up the ladder and down: pain on the way down minus on the way up at each current, per side. */
export function carryOverSpec({ pts }) {
  const ya = niceAxis(pts.map((r) => r.diff), 1, [-2, 2]);
  const xa = niceAxis(pts.map((r) => r.current_mA), 1, [0, 5]);
  const data = Object.entries(SIDE_INK).map(([side, col]) => {
    const rs = pts.filter((r) => r.side === side);
    if (!rs.length) return null;
    return hoverTrace({
      type: "scatter", mode: "markers", name: `${side.toLowerCase()} side stepped`,
      x: rs.map((r) => r.current_mA), y: rs.map((r) => r.diff),
      marker: { size: 11, color: rs.map((r) => (r.falling_first ? T.surface : col)), line: { color: col, width: 2 } },
      hovertext: rs.map((r) => [`${side} side, ${fx(r.current_mA, 1)} mA`,
        `down minus up ${sg(r.diff)} (up ${fx(r.rising, 1)}, down ${fx(r.falling, 1)})`,
        `${r.falling_first ? "the fall came first" : "the fall came after the rise"}`,
        fin(r.minutes_apart) ? `${fx(r.minutes_apart, 0)} min apart` : null].filter(Boolean).join("<br>")),
    });
  }).filter(Boolean);
  return {
    data,
    layout: base({ figureTitle: TITLE.carryOver,
      xaxis: { title: axisTitle("current on the side that was stepped (mA)"), tickfont: TICKFONT, ...xa },
      yaxis: { title: axisTitle("down minus up (pain points)"), tickfont: TICKFONT, ...ya, zeroline: false },
      shapes: [refLineY(0)],
      annotations: [{ xref: "paper", yref: "y", x: 1, y: 0, xanchor: "left", xshift: 6, showarrow: false, text: "no difference",
        font: { family: FONT_FAMILY, size: FIGURE_TEXT_PX, color: T.ink3 } }],
      margin: { l: 56, r: 100, t: 16, b: 56 },
    }),
  };
}

/** A4: day-to-day correlation of the daily mean rating at each lag. */
export function ratingPersistenceSpec({ lags, score, nRatings, nDays }) {
  const rs = lags.filter((l) => fin(l.r));
  const data = [hoverTrace({
    type: "scatter", mode: "lines+markers", name: score,
    x: rs.map((l) => l.lag_days), y: rs.map((l) => l.r),
    line: { color: SERIES[0], width: 2 }, marker: { size: 8, color: SERIES[0] },
    hovertext: rs.map((l) => [`${painScoreLabel(score)} · ${l.lag_days} day${l.lag_days === 1 ? "" : "s"} apart`,
      `correlation ${sg(l.r)}`, `${fx(l.n_pairs, 0)} pairs of days`,
      fin(nRatings) ? `${nRatings} ratings on ${fx(nDays, 0)} days in all` : null].filter(Boolean).join("<br>")),
  })];
  const xa = niceAxis(lags.map((l) => l.lag_days), 1, [1]);
  return {
    data,
    layout: base({ figureTitle: TITLE.persistence,
      xaxis: { title: axisTitle("days apart"), tickfont: TICKFONT, ...xa,
        ticktext: xa.tickvals.map((v) => `${v} d`) },
      yaxis: { title: axisTitle("correlation"), tickfont: TICKFONT, range: [-1, 1],
        tickvals: [-1, -0.5, 0, 0.5, 1], zeroline: false },
      shapes: [refLineY(0)],
    }),
  };
}

/** A5: change in settled band power per mA, by band centre. The band axis runs to the last band's
 *  centre, rounded up to the next 10 Hz tick, so the right-hand edge is labelled. */
export function steppedCurrentSpec({ rows }) {
  const centres = rows.map((b) => b.centre_hz);
  const xa = niceAxis(centres, 10, [10]);
  const vals = rows.flatMap((b) => [b.relative_slope_per_mA, b.lo, b.hi]).filter(fin).map(Number);
  const ymax = Math.max(0.05, ...vals.map(Math.abs));
  const groupOf = (b) => (b.group === "family" || b.group === "far" ? b.group : "other");
  const NAMES = Object.fromEntries([["family", "21.5–27.5 Hz family"],
    ["far", "far bands (< 12 Hz or > 32 Hz)"], ["other", "other bands"]]);
  const COLOR = { ...GROUP_INK, other: CONTEXT };
  const data = ["family", "far", "other"].map((g) => {
    const rs = rows.filter((b) => groupOf(b) === g && fin(b.relative_slope_per_mA));
    if (!rs.length) return null;
    return hoverTrace({
      type: "scatter", mode: "markers", name: g,
      x: rs.map((b) => b.centre_hz), y: rs.map((b) => b.relative_slope_per_mA),
      error_y: errY(rs, "relative_slope_per_mA", "lo", "hi", COLOR[g]),
      marker: { size: 8, color: COLOR[g] },
      hovertext: rs.map((b) => [`${b.centre_hz} Hz · ${NAMES[g]}`,
        `change per mA ${fin(b.relative_slope_per_mA) ? `${(100 * b.relative_slope_per_mA).toFixed(1)}%` : "not given"} of the band's settled power`,
        fin(b.lo) && fin(b.hi) ? `95% range ${(100 * b.lo).toFixed(1)}% to ${(100 * b.hi).toFixed(1)}%` : "no 95% range",
        `${fx(b.n, 0)} points in ${fx(b.n_runs, 0)} ladder runs`].join("<br>")),
    });
  }).filter(Boolean);
  const yr = Math.round(ymax * 1000) / 1000;
  return {
    data,
    layout: base({ figureTitle: TITLE.stepped,
      xaxis: { title: axisTitle("band centre (Hz)"), tickfont: TICKFONT, ...xa },
      yaxis: { title: axisTitle("change per mA (share of band power)"), tickfont: TICKFONT, range: [-yr, yr],
        tickvals: [-yr, 0, yr], zeroline: false },
      shapes: [refLineY(0)],
      margin: { l: 64, r: 24, t: 16, b: 56 },
    }),
  };
}

/** Band detector, device-shaped version: area under the curve per band, plainly and with the current
 *  taken out; a dashed line for the current alone; a tick under a band that carries a folded multiple. */
export function bandDeviceSpec({ p }) {
  const bands = (p.bands || []).filter((b) => b.reading && b.reading.band && fin(b.reading.band.auc));
  const first = bands.length ? bands[0].reading : {};
  const alone = first.current_alone && first.current_alone.auc;
  const series = [["band", "the band", READING.bands, -0.18], ["band_without_current", "the band, current taken out", READING.adjusted, 0.18]];
  const xa = niceAxis(bands.map((b) => b.centre_hz), 5, [10, 30]);
  const data = [];
  series.forEach(([k, lab, col, dx]) => {
    const bs = bands.filter((b) => b.reading[k] && fin(b.reading[k].auc));
    if (!bs.length) return;
    data.push(hoverTrace({
      type: "scatter", mode: "markers", name: k,
      x: bs.map((b) => b.centre_hz + dx), y: bs.map((b) => b.reading[k].auc),
      error_y: errY(bs.map((b) => b.reading[k]), "auc", "lo", "hi", col),
      marker: { size: 8, color: bs.map((b) => (fin(b.reading[k].q) && b.reading[k].q < 0.05 ? col : T.surface)), line: { color: col, width: 1.5 } },
      hovertext: bs.map((b) => { const r = b.reading[k];
        return [`${b.centre_hz} Hz · ${lab}`, `area under the curve ${fx(r.auc, 2)} (${range95(r.lo, r.hi, (v) => fx(v, 2))})`,
          pq(r.p, r.q), b.carries_folded_multiple ? "carries a folded multiple of the rate in force (advisory)" : null,
          `${fx(b.reading.n, 0)} ratings in the two pain groups`].filter(Boolean).join("<br>"); }),
    }));
  });
  const folded = bands.filter((b) => b.carries_folded_multiple);
  if (folded.length) {
    data.push(hoverTrace({
      type: "scatter", mode: "markers", name: "folded",
      x: folded.map((b) => b.centre_hz), y: folded.map(() => 0.2),
      marker: { symbol: "line-ns", size: 12, color: T.ink, line: { color: T.ink, width: 1.5 } },
      hovertext: folded.map((b) => `${b.centre_hz} Hz carries a folded multiple of the stimulation rate in force (advisory)`),
    }));
  }
  const shapes = [refLineY(0.5)];
  const annotations = [{ xref: "paper", yref: "y", x: 1, y: 0.5, xanchor: "left", xshift: 6, showarrow: false,
    text: "0.5 = coin toss", font: { family: FONT_FAMILY, size: FIGURE_TEXT_PX, color: T.ink3 } }];
  if (fin(alone)) {
    shapes.push({ ...refLineY(alone), line: { color: CONTEXT, width: 1.5, dash: "dash" } });
    annotations.push({ xref: "paper", yref: "y", x: 1, y: alone, xanchor: "left", xshift: 6, showarrow: false,
      yshift: Math.abs(alone - 0.5) < 0.04 ? 12 : 0, text: "current alone",
      font: { family: FONT_FAMILY, size: FIGURE_TEXT_PX, color: T.ink3 } });
  }
  const last = bands.length ? bands[bands.length - 1] : null;
  if (last) {
    endLabels(series.filter(([k]) => last.reading[k] && fin(last.reading[k].auc))
      .map(([k, lab, col]) => ({ y: last.reading[k].auc, text: lab, color: col })), 0.8)
      .forEach((a) => annotations.push({ ...a, yshift: a.y > 0.5 ? -14 : 14 }));
  }
  return {
    data,
    layout: base({ figureTitle: TITLE.device,
      margin: { l: 56, r: LABEL_MARGIN, t: 22, b: 56 },
      xaxis: { title: axisTitle("band centre (Hz)"), tickfont: TICKFONT, ...xa },
      yaxis: { title: axisTitle("AUC"), tickfont: TICKFONT, range: [0.2, 1.0], tickvals: [0.2, 0.4, 0.6, 0.8, 1.0], zeroline: false },
      shapes, annotations,
    }),
  };
}

