/**
 * What the calibrated heat maps print beside a cell and beside a row. Pure functions, so they can
 * be tested without Plotly (review 2026-09-15, findings B1 and B4; the pattern the review asked
 * for -- the strings a clinician must be able to read, asserted against the numbers).
 *
 * B1. The backend computes, for each column's ONE best cell (the best of the ten lengths of
 * signal), the rating count, the bootstrap interval, the selection-corrected p and the 22-band
 * corrected q (`best_correlation_rows` / `best_auc_rows`). The grid read those rows only to place
 * the circle. Now the hover and the pinned panel print them, beside -- never instead of -- the
 * plain per-cell number, and say plainly that the other nine cells in a column carry no corrected
 * statistic at all.
 *
 * B4. A row's length of signal is compared with the device's ranges carried on the response
 * (`device_timing_ranges`, from `DecodeCommon.device_ranges`, never a number typed here): up to
 * the averaging range it is an averaging window the device can be set to; above that and up to
 * the HOLD HORIZON (one averaging window plus one onset hold -- 30 s + 30 s on the clinician
 * tablet, read 2026-09-15) it is a level the device can only HOLD past a threshold through its
 * onset, not average; beyond that nothing on the device reaches it. On RCS08 the strongest cells
 * sit at 5 min, which is beyond.
 */

/** "9s", "1m" -- the delivered length of signal a row holds. */
export function secondsLabel(s) {
  return Number(s) >= 60 ? `${Math.round(Number(s) / 60)}m` : `${Number(s).toFixed(0)}s`;
}

function fmtSigned(v, d = 2) {
  const n = Number(v);
  if (!Number.isFinite(n)) return "—";
  return `${n < 0 ? "−" : ""}${Math.abs(n).toFixed(d)}`;
}

function fmtQ(q) {
  const n = Number(q);
  if (!Number.isFinite(n)) return "—";
  if (n >= 0.01) return n.toFixed(3).replace(/0+$/, "").replace(/\.$/, "");
  return n.toPrecision(2);
}

function bestRowFor(sw, kind, colIndex) {
  const centers = (sw && sw.center_freqs_hz) || [];
  const rows = (kind === "auc" ? sw && sw.best_auc_rows : sw && sw.best_correlation_rows) || [];
  const c = centers[colIndex];
  if (c == null) return null;
  return rows.find((r) => Math.abs(Number(r.band_center_hz) - Number(c)) < 1e-6) || null;
}

function rowIndexOf(sw, seconds) {
  const delivered = (sw && sw.integration_seconds_delivered) || [];
  return delivered.findIndex((d) => Math.abs(Number(d) - Number(seconds)) < 1e-6);
}

/** The corrected statistics for one cell, or the sentence that says why there are none. */
export function bestCellReadout(sw, kind, colIndex, rowIndex, { includeN = true } = {}) {
  const best = bestRowFor(sw, kind, colIndex);
  if (!best) return { isBest: false, text: "no corrected statistic for this column" };
  const bestRow = rowIndexOf(sw, best.integration_seconds_delivered);
  if (bestRow !== rowIndex) {
    // The PI's wording, 2026-09-15: point at the circled best cell and stop.
    return { isBest: false, text: `best cell corrected (${secondsLabel(best.integration_seconds_delivered)} circled)` };
  }
  // `includeN`: the hover carries the count (nothing else on a hover does); the panel lines beside
  // the scatter and the violin leave it out, since the plain line above them already has it.
  const parts = includeN ? [`${Number(best.n_pain_reports)} ratings`] : [];
  if (kind !== "auc" && best.pearson_r_low != null && best.pearson_r_high != null) {
    parts.push(`interval ${fmtSigned(best.pearson_r_low)} to ${fmtSigned(best.pearson_r_high)}`);
  }
  parts.push(`corrected q = ${fmtQ(best.family_wise_q_8_to_30hz)}`);
  parts.push(String(best.answer || "").replace(/_/g, " ") || "not resolved");
  return { isBest: true, text: parts.join(" · ") };
}

/** rows x columns of readout strings, in the heat map's own orientation, for `customdata`. */
export function hoverCustomData(sw, kind) {
  const grid = (kind === "auc" ? sw && sw.auc_grid : sw && sw.correlation_grid) || [];
  const ncol = ((sw && sw.center_freqs_hz) || []).length;
  return grid.map((_, ri) => Array.from({ length: ncol }, (__, ci) => bestCellReadout(sw, kind, ci, ri).text));
}

/** Which of the device's documented tiers a row's length of signal falls in. */
function holdHorizon(ranges) {
  if (!ranges) return null;
  if (Number.isFinite(Number(ranges.hold_horizon_s))) return Number(ranges.hold_horizon_s);
  const avg = Array.isArray(ranges.averaging_s) ? Number(ranges.averaging_s[1]) : NaN;
  const onset = Array.isArray(ranges.onset_dual_s) ? Number(ranges.onset_dual_s[1]) : NaN;
  return Number.isFinite(avg) && Number.isFinite(onset) ? avg + onset : null;
}

export function rowTier(seconds, ranges) {
  const s = Number(seconds);
  const avg = ranges && Array.isArray(ranges.averaging_s) ? Number(ranges.averaging_s[1]) : null;
  const horizon = holdHorizon(ranges);
  if (!Number.isFinite(s) || !Number.isFinite(avg)) return { tier: "unknown" };
  if (s <= avg + 1e-9) return { tier: "averaging" };
  if (Number.isFinite(horizon) && s <= horizon + 1e-9) return { tier: "onset" };
  return { tier: "beyond" };
}

/** Short bullets for the caption under the grids (the PI, 2026-09-15: "MUCH more concise, ideally
 * with bullet points"; the row labels themselves stay plain numbers). Sources are named in a word,
 * not spelled out; the full sentences stay on the response for anyone who opens it. */
export function tierBullets(ranges, secondsList) {
  if (!ranges || !Array.isArray(ranges.averaging_s)) return [];
  const rows = (secondsList || []).map(Number).filter(Number.isFinite);
  const avgRows = rows.filter((s) => rowTier(s, ranges).tier === "averaging");
  const onsetRows = rows.filter((s) => rowTier(s, ranges).tier === "onset");
  const beyondRows = rows.filter((s) => rowTier(s, ranges).tier === "beyond");
  const out = [];
  if (avgRows.length) {
    out.push(`Rows to ${secondsLabel(Math.max(...avgRows))}: an averaging window the device can be set to `
      + `(${ranges.averaging_s[0]}-${ranges.averaging_s[1]} s on the tablet).`);
  }
  if (onsetRows.length) {
    out.push(`Rows ${secondsLabel(Math.min(...onsetRows))}-${secondsLabel(Math.max(...onsetRows))}: one averaging window plus `
      + `an onset hold (each \u2264${ranges.onset_dual_s[1]} s); the device holds a level there, it does not average.`);
  }
  if (beyondRows.length) {
    out.push(`Rows from ${secondsLabel(Math.min(...beyondRows))}: beyond anything the device can be set to.`);
  }
  return out;
}

/** The snapshot-served share, as two short bullets, or nothing when no report was served that way. */
export function deviceSpectrumBullets(sw) {
  const n = sw && Number(sw.n_pain_reports_from_device_spectrum);
  if (!n) return [];
  const tot = ((sw && sw.device_spectrum_total_grid) || []).reduce((m, row) => Math.max(m, ...(row || [0])), 0);
  const share = tot > 0 ? ` (${Math.round((100 * n) / tot)}%)` : "";
  const ofTot = tot > 0 ? ` of ${tot}` : "";
  return [
    `${n}${ofTot} matched reports${share} had no voltage trace in the match window and were read from the device's `
      + "30 s FFT snapshots: a row of N s uses the nearest ceil(N/30) snapshots, or nothing.",
    "Matching here uses the histogram card's tolerance.",
  ];
}
