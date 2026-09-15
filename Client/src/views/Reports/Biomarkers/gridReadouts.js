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
 * B4. A row's length of signal is compared with the device's DOCUMENTED ranges carried on the
 * response (`device_timing_ranges`, from `DecodeCommon.device_ranges`, never a number typed here):
 * up to the averaging range it is an averaging window the device can be set to; above that and up
 * to the Dual onset range it is a level the device can only HOLD past a threshold through its
 * onset, not average; beyond that nothing on the device reaches it.
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
export function bestCellReadout(sw, kind, colIndex, rowIndex) {
  const best = bestRowFor(sw, kind, colIndex);
  if (!best) return { isBest: false, text: "no corrected statistic for this column" };
  const bestRow = rowIndexOf(sw, best.integration_seconds_delivered);
  if (bestRow !== rowIndex) {
    return {
      isBest: false,
      text: `corrected statistics are computed for this column's best cell only (${secondsLabel(best.integration_seconds_delivered)}, circled)`,
    };
  }
  const parts = [`${Number(best.n_pain_reports)} ratings`];
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
export function rowTier(seconds, ranges) {
  const s = Number(seconds);
  const avg = ranges && Array.isArray(ranges.averaging_s) ? Number(ranges.averaging_s[1]) : null;
  const onset = ranges && Array.isArray(ranges.onset_dual_s) ? Number(ranges.onset_dual_s[1]) : null;
  if (!Number.isFinite(s) || !Number.isFinite(avg)) return { tier: "unknown" };
  if (s <= avg + 1e-9) return { tier: "averaging" };
  if (Number.isFinite(onset) && s <= onset + 1e-9) return { tier: "onset" };
  return { tier: "beyond" };
}

const TIER_SUFFIX = { averaging: "", onset: " ⏵ onset", beyond: " ⏵ beyond device", unknown: "" };

export function rowLabelWithTier(seconds, ranges) {
  return `${secondsLabel(seconds)}${TIER_SUFFIX[rowTier(seconds, ranges).tier]}`;
}

/** The one-paragraph caption under the grids, built from the ranges and the rows actually drawn. */
export function tierCaption(ranges, secondsList) {
  if (!ranges || !Array.isArray(ranges.averaging_s)) return "";
  const rows = (secondsList || []).map(Number).filter(Number.isFinite);
  const avgRows = rows.filter((s) => rowTier(s, ranges).tier === "averaging");
  const onsetRows = rows.filter((s) => rowTier(s, ranges).tier === "onset");
  const beyondRows = rows.filter((s) => rowTier(s, ranges).tier === "beyond");
  const bits = [];
  if (avgRows.length) {
    bits.push(`Rows up to ${secondsLabel(Math.max(...avgRows))} are an averaging window the device can be set to `
      + `(${ranges.averaging_source}).`);
  }
  if (onsetRows.length) {
    bits.push(`Rows from ${secondsLabel(Math.min(...onsetRows))} to ${secondsLabel(Math.max(...onsetRows))} are longer `
      + "than any documented averaging window; the device can only require a level held that long through its "
      + `onset duration (Dual Threshold, up to ${secondsLabel(ranges.onset_dual_s[1])}; ${ranges.onset_source}), `
      + "which holds an averaged reading past a threshold rather than averaging over it.");
  }
  if (beyondRows.length) {
    bits.push(`Rows from ${secondsLabel(Math.min(...beyondRows))} are beyond anything the device can be set to.`);
  }
  if (ranges.averaging_caveat) bits.push(ranges.averaging_caveat.replace("sensing-era", "sensing-era"));
  return bits.join(" ");
}
