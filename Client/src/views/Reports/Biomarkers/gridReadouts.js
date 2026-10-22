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
 *
 * Wording (the PI, 2026-09-26: printing the corrected q as "p" is a mislabel -- a q and a p are
 * different numbers; shortened 2026-09-27 to the "fdr" shorthand). The value the server sends as
 * `family_wise_q_8_to_30hz` is a Benjamini-Hochberg q, corrected for testing every one of the 22
 * band centres; it is now printed as "q 0.03 (fdr 22 bands)", never as "p". A cell's own
 * uncorrected p is printed as "p". Every p and q prints at most two decimals, "< 0.01" below 0.005
 * (the PI, 2026-09-26), and "< 0.05" from 0.045 up to 0.05, so nothing rounds onto the cut it did
 * not cross.
 */
import { T } from "assets/theme/base/tokens";

/** "grid q 0.03 (fdr 22 bands)" -- never "p" for a corrected q (the PI, 2026-09-26: a q and a p are
 *  different numbers; 2026-09-27: shortened from "(p corrected for testing 22 bands)" to the
 *  "fdr" shorthand -- his standing rule now, once context is clear). 22 is the fixed row count the
 *  heat maps have always drawn, the same source `ALLOWANCE` named before this rewording.
 *  "grid q" since wave 2 (decisions 497, 498): this is the shown grid's own q, over its own 22
 *  bands; the q that is "corrected within each pair" by the deciding source's p is a different
 *  number and is printed bare, "q 0.84" (`familyQWords`), so the two are never given one name. */
export function qWords(q, n = 22) {
  return `grid q ${fmtQ(q)} (fdr ${n} bands)`;
}

/** "9s", "1m" -- the delivered length of signal a row holds. */
export function secondsLabel(s) {
  return Number(s) >= 60 ? `${Math.round(Number(s) / 60)}m` : `${Number(s).toFixed(0)}s`;
}

function fmtSigned(v, d = 2) {
  const n = Number(v);
  if (!Number.isFinite(n)) return "not given";
  return `${n < 0 ? "−" : ""}${Math.abs(n).toFixed(d)}`;
}

/** "p < 0.01" or "p = 0.03": the p with its sign, so a small p never reads "p = < 0.01". */
export function pEquals(p) {
  const t = fmtP(p);
  return t.startsWith("<") ? `p ${t}` : `p = ${t}`;
}

function fmtQ(q) {
  return fmtP(q);
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

/** "117 ratings", or "117 ratings (about 98 independent)" when the row carries the effective count
 *  (panel A item 4, 2026-09-22: ratings filed close together are worth fewer independent
 *  observations than their number; the backend's `stats_utils.effective_n` on the pairs the cell
 *  correlated). A row without the field prints exactly what it always did. */
function ratingsPhrase(row) {
  const n = Number(row.n_pain_reports);
  const e = row.n_pain_reports_effective == null ? NaN : Number(row.n_pain_reports_effective);
  return Number.isFinite(e) ? `${n} ratings (about ${Math.round(e)} independent)` : `${n} ratings`;
}

/** The corrected statistics for one cell, or the sentence that says why there are none. */
export function bestCellReadout(sw, kind, colIndex, rowIndex, { includeN = true } = {}) {
  const best = bestRowFor(sw, kind, colIndex);
  if (!best) return { isBest: false, text: "" };
  const bestRow = rowIndexOf(sw, best.integration_seconds_delivered);
  if (bestRow !== rowIndex) {
    // Nothing for a cell that is not its column's best (the PI, 2026-10-02: the sentence pointing at
    // the circled square is gone).
    return { isBest: false, text: "" };
  }
  // `includeN`: the hover carries the count (nothing else on a hover does); the panel lines beside
  // the scatter and the violin leave it out, since the plain line above them already has it.
  // The corrected q first, then the cell's interval, the same two parts for the scatter and the
  // violin (the PI, 2026-10-02). The verdict word and the across-settings answer are the Closed-Loop
  // page's to print, not this one's.
  const parts = includeN ? [ratingsPhrase(best)] : [];
  parts.push(qWords(best.family_wise_q_8_to_30hz));
  const lo = kind === "auc" ? best.auc_low : best.pearson_r_low;
  const hi = kind === "auc" ? best.auc_high : best.pearson_r_high;
  if (lo != null && hi != null) parts.push(`interval ${fmtSigned(lo)} to ${fmtSigned(hi)}`);
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

/** The symbol drawn on a column's best cell for its cross-setting stability answer, by SHAPE only
 *  (the redesign of 2026-09-26, SPEC.md section 3.2): ✓ the same, ✕ different, ? cannot tell, in ink
 *  on a white disc, no green or red; null for "not tested", so nothing is drawn where nothing is
 *  known. `glyph` is the character drawn; `symbol` names the shape. */
export function stabilityMark(stab) {
  const answer = stab && stab.answer;
  if (answer === "behaves the same") return { symbol: "tick", glyph: "\u2713", color: T.ink, label: "behaves the same at every setting" };
  if (answer === "behaves differently") return { symbol: "cross", glyph: "\u2715", color: T.ink, label: "behaves differently across settings" };
  if (answer === "cannot tell") return { symbol: "question", glyph: "?", color: T.ink, label: "cannot tell" };
  return null;
}

/** One caption bullet for the symbols, under 24 words like the tier bullets. */
export function stabilityBullet() {
  return "Circle: \u2713 band tracks pain equally at every stimulation setting; \u2715 differently; ? unknown";
}

/** A p or q at most two decimals (the PI, 2026-09-26: "max 2 digits after the decimal"): "0.03",
 *  "< 0.01" below 0.005 so a small value never prints as zero. A value from 0.045 up to (not
 *  including) 0.05 prints "< 0.05": rounded it would read "0.05", the same as a value just above
 *  the cut, while the heavy ring and the status line count it as under 0.05 (review of 2026-09-26). */
export function fmtP(p) {
  const n = Number(p);
  if (!Number.isFinite(n)) return "not given";
  if (n < 0.005) return "< 0.01";
  if (n >= 0.045 && n < 0.05) return "< 0.05";
  return n.toFixed(2);
}

/** The hover's third line (the PI, 2026-09-16: "X ratings, q = Y" and nothing else -- the interval,
 *  the answer and the stability word are on the panel lines beside the scatter and the violin).
 *  The column's best cell prints its corrected q; every other cell, and a best cell whose q was not
 *  assessed, prints its own uncorrected p, read off the response (`p_grid`: Pearson's; `auc_p_grid`:
 *  the Mann-Whitney rank test's, scipy's own). A cell with no count prints nothing.
 *
 *  The best cell's rating count stays the plain number here (never `ratingsPhrase`'s "(about N
 *  independent)" addendum, 2026-09-27, the PI: trim the hover) -- that detail stays on the pinned
 *  panel line (`bestCellReadout`), which is where a reader who wants it already is. */
export function hoverReadout(sw, kind, colIndex, rowIndex) {
  const best = bestRowFor(sw, kind, colIndex);
  const isBest = best && rowIndexOf(sw, best.integration_seconds_delivered) === rowIndex;
  if (isBest) {
    const n = `${Number(best.n_pain_reports)} ratings`;
    // `Number(null)` is 0, which would print "q = 0.0" for a q that was never assessed.
    const q = best.family_wise_q_8_to_30hz == null ? NaN : Number(best.family_wise_q_8_to_30hz);
    if (Number.isFinite(q)) return `${n} \u00b7 ${qWords(q)}`;
    const p = best.p_selection_aware == null ? NaN : Number(best.p_selection_aware);
    return Number.isFinite(p) ? `${n} \u00b7 p ${fmtP(p)}, uncorrected` : n;
  }
  const { n, p } = cellNP(sw, kind, colIndex, rowIndex);
  if (!(n > 0)) return "";
  return p == null ? `${n} ratings` : `${n} ratings \u00b7 p ${fmtP(p)}`;
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

/** "30 s", "1 min": the length of signal with a spaced unit, for the notes under the maps. */
function spacedSeconds(s) {
  return Number(s) >= 60 ? `${Math.round(Number(s) / 60)} min` : `${Number(s).toFixed(0)} s`;
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
export function tierBullets(ranges, secondsList, sw) {
  if (!ranges || !Array.isArray(ranges.averaging_s)) return [];
  const rows = (secondsList || []).map(Number).filter(Number.isFinite);
  const avgRows = rows.filter((s) => rowTier(s, ranges).tier === "averaging");
  const onsetRows = rows.filter((s) => rowTier(s, ranges).tier === "onset");
  const beyondRows = rows.filter((s) => rowTier(s, ranges).tier === "beyond");
  const out = [];
  // Minimal words, a spaced unit ("30 s", "1 min"), the PI's own forms (2026-10-02).
  if (avgRows.length) {
    out.push(`Rows \u2264${spacedSeconds(Math.max(...avgRows))}: device averaging window `
      + `(${ranges.averaging_s[0]}\u2013${ranges.averaging_s[1]} s on tablet)`);
  }
  // Rows over 30 s: only the PSD count, starred, and only when some report was read from PSD.
  const starred = onsetRows.filter((s) => needsMultiplePsds(sw, s));
  if (starred.length) {
    out.push(`*${multiPsdRows({ integration_seconds_delivered: starred }).join("; ")} (ceil(window/30 s))`);
  }
  if (beyondRows.length) {
    out.push(`Rows from ${spacedSeconds(Math.min(...beyondRows))}: beyond any device setting`);
  }
  return out;
}

/** The PSD share, as two short bullets, or nothing when no report was read that way. The two
 *  sources are named in the PI's words on every part of the heat maps (2026-09-25): TD for band
 *  power from the time-domain recording, PSD for the device's own 30 s snapshots. */
export function deviceSpectrumBullets(sw) {
  const n = sw && Number(sw.n_pain_reports_from_device_spectrum);
  if (!n) return [];
  const tot = ((sw && sw.device_spectrum_total_grid) || []).reduce((m, row) => Math.max(m, ...(row || [0])), 0);
  const share = tot > 0 ? ` (${Math.round((100 * n) / tot)}%)` : "";
  const ofTot = tot > 0 ? ` of ${tot}` : "";
  // Wave 2, C4 (decision 492): the maps above are the mixed grid, which no longer chooses; the
  // caption names the grid and its source counts, in place of the old mixed-source sentence.
  // A grid stored before C4 carries no `grid_source`, and its mixed grid did choose: the old words.
  const name = gridSourceName(sw && sw.grid_source);
  return [
    name
      ? `${name}: ${n}${ofTot} matched reports${share} read from PSD (no TD in match window); shown, cannot choose`
      : `${n}${ofTot} matched reports${share} had no TD in match window; read from PSD`,
    "Match window defined under \"Adjust matching parameters\"",
  ];
}

/** One PSD covers 30 s, so a row of N s needs ceil(N/30) of them. */
const PSD_SNAPSHOT_S = 30;

/** The rows (delivered lengths) that need more than one PSD, as "45 s and 1 min rows need 2 PSDs". */
function multiPsdRows(sw) {
  const rows = ((sw && sw.integration_seconds_delivered) || []).map(Number).filter(Number.isFinite);
  const byK = {};
  rows.forEach((s) => {
    const k = Math.ceil(s / PSD_SNAPSHOT_S - 1e-9);
    if (k > 1) (byK[k] = byK[k] || []).push(s);
  });
  return Object.keys(byK).map(Number).sort((a, b) => a - b).map((k) => {
    const names = byK[k].map(spacedSeconds);
    const list = names.length > 1 ? `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}` : names[0];
    return `${list} row${names.length > 1 ? "s" : ""} ${psdNeed(k, names.length > 1)}`;
  });
}

/** "need 2 PSDs" written whole, not assembled, so a search of the built chunks finds it (the rows
 *  up to 60 s only ever need 2); other counts are assembled. */
function psdNeed(k, plural) {
  if (k === 2) return plural ? "need 2 PSDs" : "needs 2 PSDs";
  return `${plural ? "need" : "needs"} ${k} PSDs`;
}

/** Rows whose label carries the asterisk: those that need more than one PSD, when any report was
 *  read from PSD (the asterisk points at that note). */
export function needsMultiplePsds(sw, seconds) {
  return !!(sw && Number(sw.n_pain_reports_from_device_spectrum) > 0)
    && Math.ceil(Number(seconds) / PSD_SNAPSHOT_S - 1e-9) > 1;
}

/** The clinic-sheet caveat (decision 186): what the heat maps pool, and how many of this contact
 *  pair's ratings came from the clinic or at-home testing sheets when the switch is on. Nothing
 *  for a response that predates the switch. */
export function clinicSheetBullets(sw) {
  const cs = sw && sw.clinic_sheet_ratings;
  if (!cs) return [];
  if (!cs.included) {
    return ["Heat maps use home pain surveys only; clinic titration sessions toggled off"];
  }
  if (!cs.n_added) {
    return [cs.reason ? `Sheet scores on, but ${cs.reason}` : "Sheet scores on, but none carried this score"];
  }
  const n = sw.n_pain_reports_from_clinic_sheet;
  const tot = sw.n_pain_reports;
  const scale = Number(cs.scale) === 1 ? "as scored (0–10)" : `times ${Number(cs.scale)}`;
  const head = (n != null && tot != null) ? `${n} of the ${tot} ratings here` : `${cs.n_added} ratings`;
  return [`${head} are clinic titration sessions' scores, ${scale}, taken while current was stepped`];
}


/** "+0.12" / "\u22120.31" / "0.00": an R with its sign always written. */
function fmtR(v) {
  const n = Number(v);
  if (v == null || !Number.isFinite(n)) return "not given";
  const a = Math.abs(n).toFixed(2);
  if (a === "0.00") return a;
  return `${n < 0 ? "\u2212" : "+"}${a}`;
}

/** P-19 (the PI, 2026-09-25: a heat map split by recording source, as text only). One line for the
 *  pinned cell, printed above the scatter: the same correlation on the reports whose band power
 *  came from TD alone and on those from PSD alone, each with its interval and count, read off the
 *  grid response (`correlation_by_recording_source`, computed on the server with the cell's own
 *  routine, interval method, outlier rule and matching). A source under the server's minimum reads
 *  "too few reports". Null for a stored grid built before the split, or one that could not make it,
 *  so nothing is printed rather than a guess. It selects no band and changes no verdict. */
export function sourceSplitLine(sw, colIndex, rowIndex) {
  const split = sw && sw.correlation_by_recording_source;
  if (!split || !split.available) return null;
  const min = Number(split.min_reports) || 8;
  const at = (g) => { const row = (g && g[rowIndex]) || []; const v = row[colIndex]; return v == null ? null : Number(v); };
  const part = (name, src) => {
    if (!src) return null;
    const n = at(src.n_grid);
    if (n == null || !Number.isFinite(n)) return null;
    if (n < min) return `${name} values: n=${n}, too few`;
    const r = at(src.r_grid);
    const lo = at(src.r_low_grid);
    const hi = at(src.r_high_grid);
    const iv = (lo != null && hi != null) ? ` (${fmtR(lo)} to ${fmtR(hi)})` : "";
    return `${name} values: R ${fmtR(r)}${iv}, n=${n}`;
  };
  const parts = [part("TD", split.td), part("PSD", split.psd)].filter(Boolean);
  // One source per line (the PI, 2026-10-02): TD, then PSD on a new line.
  return parts.length ? parts.join("\n") : null;
}


// ---- WAVE 2: WHICH GRID CHOOSES, WHO DECIDES, AND THE WARNINGS ON EACH BAND (decisions 484, 492-498)
// Every word below is read off the response; nothing is worked out here but the formatting. A field
// a response does not carry prints nothing (an older stored grid), never a guess.

/** The grid a sweep or row came from, in the PI's words (C4, decision 492: `grid_source`). */
const GRID_SOURCE_NAME = {
  td: "TD only",
  psd: "PSD only",
  td_psd_where_no_td: "Mixed grid (TD, PSD where no TD)",
};
export function gridSourceName(src) {
  return GRID_SOURCE_NAME[src] || null;
}

/** "chooses" / "shown, cannot choose" for one best row (`can_choose_band`), null when not carried. */
export function chooseWords(row) {
  if (!row || row.can_choose_band == null) return null;
  return row.can_choose_band ? "chooses the band" : "shown, cannot choose";
}

/** A grid's title for the heat maps by source: "TD only · chooses the band". */
export function sourceGridTitle(sw) {
  const rows = (sw && sw.best_correlation_rows) || [];
  const name = gridSourceName(rows[0] && rows[0].grid_source) || gridSourceName(sw && sw.grid_source);
  const choose = chooseWords(rows[0]);
  return [name, choose].filter(Boolean).join(" · ") || null;
}

/** Why a grid cannot choose (`cannot_choose_why`), read off its first best row; null when it can. */
export function cannotChooseWhy(sw) {
  const rows = (sw && sw.best_correlation_rows) || [];
  const r = rows.find((x) => x && x.can_choose_band === false && x.cannot_choose_why);
  return r ? r.cannot_choose_why : null;
}

/** Whose answer a row chooses by (C5, decision 493): "home" where the home record (chronic log)
 *  decides (`decided_by`, on the choosing view; or `choice_source` with a covering chronic block, on
 *  the Biomarkers grid), "TD" where TD does, "none" for a row that never chooses, null if unknown. */
export function deciderOf(row) {
  if (!row) return null;
  if (row.decided_by === "chronic") return "home";
  if (row.choice_source === "chronic" && row.chronic && row.chronic.covered) return "home";
  if (row.choice_source === "TD" || row.choice_source === "chronic") return "TD";
  if (row.choice_source === "none") return "none";
  return null;
}

/** "Decided by: home record" / "Decided by: TD" / "Shown, cannot choose". */
export function decidedByWords(row) {
  const d = deciderOf(row);
  if (d === "home") return "Decided by: home record";
  if (d === "TD") return "Decided by: TD";
  if (d === "none") return "Shown, cannot choose";
  return null;
}

/** The deciding answer's r, interval and count: the chronic block's where the home record decides on
 *  the Biomarkers grid (there the row's own fields are still TD's), else the row's own (on the
 *  choosing view `chronic_decides` has already put the chronic answer into them). */
export function decidingValues(row) {
  if (!row) return null;
  if (deciderOf(row) === "home" && row.decided_by !== "chronic") {
    const c = row.chronic || {};
    return { r: c.pearson_r, lo: c.pearson_r_low, hi: c.pearson_r_high, n: c.n_reports,
      currentRemoved: c.current_removed_check, dailySwing: c.daily_swing, recent: c.recent_check,
      matchWarning: c.warning || null };
  }
  return { r: row.pearson_r, lo: row.pearson_r_low, hi: row.pearson_r_high, n: row.n_pain_reports,
    currentRemoved: row.current_removed_check, dailySwing: row.daily_swing, recent: row.recent_check,
    matchWarning: row.chronic_match_warning || null };
}

/** "r +0.08 [−0.30, +0.30], n=30". */
export function rIntervalN(r, lo, hi, n) {
  if (r == null || !Number.isFinite(Number(r))) return "no r";
  const iv = (lo != null && hi != null) ? ` [${fmtR(lo)}, ${fmtR(hi)}]` : "";
  return `r ${fmtR(r)}${iv}${n != null ? `, n=${n}` : ""}`;
}

/** The home record's report counts on one band (`n_reports`, `n_reports_in_gap`,
 *  `n_reports_log_elsewhere`): "30 matched · 429 in a gap · 142 log elsewhere"; null without them. */
export function chronicCountsWords(ch) {
  if (!ch || !ch.covered || ch.n_reports == null) return null;
  const parts = [`${ch.n_reports} matched`];
  if (ch.n_reports_in_gap != null) parts.push(`${ch.n_reports_in_gap} in a gap`);
  if (ch.n_reports_log_elsewhere != null) parts.push(`${ch.n_reports_log_elsewhere} log elsewhere`);
  return parts.join(" · ");
}

const CURRENT_STATUS_WORD = { holds: "holds", warning: "▲ warning", "constant current": "constant current",
  "not assessed": "not assessed" };
/** The current-removed check (decision 484, a warning only): "holds · p 0.03", "▲ warning · p 0.72". */
export function currentOutWords(chk) {
  if (!chk) return null;
  const word = CURRENT_STATUS_WORD[chk.status] || chk.status || "not assessed";
  const p = chk.p_rotation != null ? chk.p_rotation : chk.p;
  return p != null && Number.isFinite(Number(p)) ? `${word} · p ${fmtP(p)}` : word;
}

/** The daily swing (decision 494, a warning only): "▲ 2.6-fold (low 17:00, high 00:00)", or the
 *  server's status where nothing was measured ("no home record at this band"). */
export function dailySwingWords(ds) {
  if (!ds) return null;
  if (ds.status !== "measured" || ds.ratio == null) return ds.status || null;
  const hh = (h) => `${String(h).padStart(2, "0")}:00`;
  const warn = ds.warn_at_ratio != null && Number(ds.ratio) >= Number(ds.warn_at_ratio);
  return `${warn ? "▲ " : ""}${Number(ds.ratio).toFixed(1)}-fold (low ${hh(ds.hour_low)}, high ${hh(ds.hour_high)})`;
}

/** The recent-reports check (decision 496, a warning only; no p, the recent reports were also used
 *  in choosing): "▲ r −0.22 [−0.53, +0.13], n=25", "too few (n=8)", "none". */
export function recentWords(rc) {
  if (!rc) return null;
  if (rc.status === "checked") {
    return `${rc.warning ? "▲ " : ""}${rIntervalN(rc.pearson_r, rc.pearson_r_low, rc.pearson_r_high, rc.n_after)}`;
  }
  if (rc.status === "too few recent reports") return `too few (n=${rc.n_after != null ? rc.n_after : "?"})`;
  return rc.status || null;
}

/** The q corrected within each contact pair (decisions 497, 498): "q 0.84", "▲ q 0.87" when warned,
 *  or the row's status when it is outside the family ("not an allowed sensing pair"). */
export function familyQWords(row) {
  if (!row || !row.family_q_status) return null;
  if (row.family_q == null) return row.family_q_status;
  return `${row.family_q_warning ? "▲ " : ""}q ${fmtP(row.family_q)}`;
}

/** The footnote under the q: "q: corrected within each pair: L 0⁻3⁺ across 22 bands; R 0⁻3⁺ across
 *  22 bands", from the block's `per_pair`; the server's own `words` when there is no per-pair block. */
export function familyFootnote(fc) {
  if (!fc || fc.available === false) return null;
  const per = fc.per_pair || null;
  if (per && Object.keys(per).length) {
    const parts = Object.keys(per).map((k) => `${per[k].display || k} across ${per[k].n_in_family} bands`);
    return `q: corrected within each pair: ${parts.join("; ")}`;
  }
  return fc.words ? `q: ${fc.words}` : null;
}

/** The band centres on a grid where the home record decides (the chronic marks on the TD map). */
export function chronicMarkCentres(sw) {
  return ((sw && sw.best_correlation_rows) || []).filter((r) => deciderOf(r) === "home")
    .map((r) => Number(r.band_center_hz)).filter(Number.isFinite).sort((a, b) => a - b);
}

/** "Later 30% of ratings: after 2026-04-03 (rolling cut)", from the response's `recent_check_cut`. */
export function cutDateWords(cut) {
  if (!cut || !cut.choice_cut_date) return null;
  return `Later 30% of ratings: after ${cut.choice_cut_date}${cut.rolling ? " (rolling cut)" : ""}`;
}

/** The warning a chosen non-default home-record match carries (C5: `settings_applied.chronic_match`
 *  not the default), read off the first chronic block that carries one; null at the default. */
export function chronicMatchWarning(result) {
  const sa = (result && result.settings_applied) || {};
  if (!sa.chronic_match || sa.chronic_match_is_default !== false) return null;
  const sweeps = (result && result.band_time_sweep) || {};
  const found = Object.keys(sweeps).map((ch) => {
    const sw = sweeps[ch] || {};
    const td = (sw.by_source_grid || {}).td || sw;
    const row = (td.best_correlation_rows || []).find((r) => (r.chronic && r.chronic.warning) || r.chronic_match_warning);
    return (sw.chronic_band_choice && sw.chronic_band_choice.warning)
      || (row && ((row.chronic && row.chronic.warning) || row.chronic_match_warning)) || null;
  }).find(Boolean);
  return found || "Not the recommended default way of matching reports to the home record.";
}
