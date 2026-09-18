/* Participant-specific motivating examples are maintained outside source control. */

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
  // B3 (decision 185): the cross-setting stability answer, the same words the Closed-Loop card's
  // "Choose a band" column prints, read off the row the backend attached it to. A row with no
  // answer field at all (an older stored response) leaves the line as it was.
  const stab = best.cross_setting_stability;
  if (stab && stab.answer) parts.push(`across settings: ${stabilityAnswerWord(stab)}`);
  return { isBest: true, text: parts.join(" · ") };
}

/** The answer word for the hover: the backend's own word, except that "not tested" for the
 *  reason that the background run has not landed yet reads "not yet computed" -- the reader's
 *  question is "will this fill in", and it will. */
export function stabilityAnswerWord(stab) {
  if (!stab || !stab.answer) return "";
  if (stab.answer === "not tested" && /not been computed/.test(String(stab.reason || ""))) return "not yet computed";
  return stab.answer;
}

/** The symbol drawn on a column's best cell for its cross-setting stability answer -- the
 *  Closed-Loop card's own three (tick / cross / amber disc), null for "not tested" so nothing is
 *  drawn where nothing is known. Plotly marker symbols: a filled circle stands in for the tick. */
export function stabilityMark(stab) {
  const answer = stab && stab.answer;
  if (answer === "behaves the same") return { symbol: "circle", color: "#2e7d32", label: "behaves the same at every setting" };
  if (answer === "behaves differently") return { symbol: "x", color: "#c62828", label: "behaves differently across settings" };
  if (answer === "cannot tell") return { symbol: "diamond", color: "#e0a100", label: "cannot tell" };
  return null;
}

/** One caption bullet for the symbols, under 24 words like the tier bullets. */
export function stabilityBullet() {
  return "Inside a circle: green tick, the band tracks pain the same at every stimulation setting; red cross, differently; amber, cannot tell.";
}

export function fmtP(p) {
  const n = Number(p);
  if (!Number.isFinite(n)) return "—";
  if (n >= 0.001) return n.toFixed(3).replace(/0+$/, "").replace(/\.$/, "");
  return n.toPrecision(3);
}

/** The hover's third line (the PI, 2026-09-16: "X ratings, q = Y" and nothing else -- the interval,
 *  the answer and the stability word are on the panel lines beside the scatter and the violin).
 *  The column's best cell prints its corrected q; every other cell, and a best cell whose q was not
 *  assessed, prints its own uncorrected p, read off the response (`p_grid`: Pearson's; `auc_p_grid`:
 *  the Mann-Whitney rank test's, scipy's own). A cell with no count prints nothing. */
export function hoverReadout(sw, kind, colIndex, rowIndex) {
  const best = bestRowFor(sw, kind, colIndex);
  const isBest = best && rowIndexOf(sw, best.integration_seconds_delivered) === rowIndex;
  if (isBest) {
    const n = Number(best.n_pain_reports);
    // `Number(null)` is 0, which would print "q = 0.0" for a q that was never assessed.
    const q = best.family_wise_q_8_to_30hz == null ? NaN : Number(best.family_wise_q_8_to_30hz);
    if (Number.isFinite(q)) return `${n} ratings, q = ${fmtQ(q)}`;
    const p = best.p_selection_aware == null ? NaN : Number(best.p_selection_aware);
    return Number.isFinite(p) ? `${n} ratings, p = ${fmtP(p)}` : `${n} ratings`;
  }
  const { n, p } = cellNP(sw, kind, colIndex, rowIndex);
  if (!(n > 0)) return "";
  return p == null ? `${n} ratings` : `${n} ratings, p = ${fmtP(p)}`;
}

/** One cell's own count and uncorrected p off the response; `p` null where the response has none. */
export function cellNP(sw, kind, colIndex, rowIndex) {
  const at = (a) => { const row = (a && a[rowIndex]) || []; const v = row[colIndex]; return v == null ? NaN : Number(v); };
  const p = at(kind === "auc" ? sw && sw.auc_p_grid : sw && sw.p_grid);
  const n = kind === "auc"
    ? at(sw && sw.auc_n_high_grid) + at(sw && sw.auc_n_low_grid)
    : at(sw && sw.n_grid);
  return { n: Number.isFinite(n) ? n : 0, p: Number.isFinite(p) ? p : null,
    nHigh: kind === "auc" ? at(sw && sw.auc_n_high_grid) : null, nLow: kind === "auc" ? at(sw && sw.auc_n_low_grid) : null };
}

/** rows x columns of hover strings, in the heat map's own orientation, for `customdata`. */
export function hoverCustomData(sw, kind) {
  const grid = (kind === "auc" ? sw && sw.auc_grid : sw && sw.correlation_grid) || [];
  const ncol = ((sw && sw.center_freqs_hz) || []).length;
  return grid.map((_, ri) => Array.from({ length: ncol }, (__, ci) => hoverReadout(sw, kind, ci, ri)));
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

/** The clinic-sheet caveat (decision 186): what the heat maps pool, and how many of this contact
 *  pair's ratings came from the clinic or at-home testing sheets when the switch is on. Nothing
 *  for a response that predates the switch. */
export function clinicSheetBullets(sw) {
  const cs = sw && sw.clinic_sheet_ratings;
  if (!cs) return [];
  if (!cs.included) {
    return ["The heat maps use the chronic REDCap ratings only; the clinic titration sessions' scores are off (a switch on the matching card)."];
  }
  if (!cs.n_added) {
    return [cs.reason ? `Sheet scores on, but ${cs.reason}.` : "Sheet scores on, but none carried this score."];
  }
  const n = sw.n_pain_reports_from_clinic_sheet;
  const tot = sw.n_pain_reports;
  const scale = Number(cs.scale) === 1 ? "as scored (0–10)" : `times ${Number(cs.scale)}`;
  const head = (n != null && tot != null) ? `${n} of the ${tot} ratings here` : `${cs.n_added} ratings`;
  return [`${head} are the clinic titration sessions' scores, ${scale}, taken while current was being stepped.`];
}
