import { DEFAULT_PAIN_SCORE, PAIN_SCORE_OPTIONS, painScoreLabel } from "views/Reports/painScores";

/**
 * The discovery request settings a committed band was chosen under, for the deployment summary and
 * the panels that share its request (moved here from `index.js` on 2026-09-23 so it can be tested).
 *
 * WHY: so the deployment ROC defines the band feature with the SAME pain score, split and match
 * window the candidate was validated under. A candidate from the discovery page carries them in its
 * `label`. A band picked on the "Choose a band" grid carries an empty label and, since decision 249,
 * the grid's own settings tag (`grid_settings`); until 2026-09-23 it contributed nothing here, so the
 * summary fell back to its defaults (NRS, tertile split) whatever grid the band was picked from.
 *
 * The label wins where it says something; the grid tag fills what it leaves out. The match
 * DIRECTION is not carried: the summary takes it from the chosen cut-point, and a value here would
 * override that. The clinic-sheet switch is not carried either: the summary reads REDCap ratings
 * only, and has no way to include the sheets.
 */
export default function requestParamsFromCandidate(bc) {
  const lbl = (bc && bc.label) || {};
  const bin = lbl.binarization || {};
  const gs = (bc && bc.grid_settings) || {};
  const rp = {};
  const metric = lbl.pro_metric || gs.sweep_metric;
  if (metric) rp.LabelMetric = metric;
  const strategy = bin.strategy || gs.label_strategy;
  if (strategy) rp.LabelStrategy = strategy;
  const low = bin.low_pct != null ? bin.low_pct : gs.percentile_low;
  if (low != null) rp.PercentileLow = low;
  const high = bin.high_pct != null ? bin.high_pct : gs.percentile_high;
  if (high != null) rp.PercentileHigh = high;
  const tol = lbl.match_tolerance_min != null ? lbl.match_tolerance_min : gs.match_tolerance_min;
  if (tol != null) rp.MatchToleranceMin = tol;
  return rp;
}

/**
 * The pain score the page's dropdown starts on (the PI, 2026-09-25 night): the one the band was
 * chosen under -- its label's, else its grid's (decision 254) -- or NRS when it carries none, with
 * `fromBand: false` so the page can say NRS was used for want of one.
 */
export function bandPainScore(bc) {
  const lbl = (bc && bc.label) || {};
  const gs = (bc && bc.grid_settings) || {};
  const key = lbl.pro_metric || gs.sweep_metric;
  const known = PAIN_SCORE_OPTIONS.some((m) => m.key === key);
  return known ? { key, fromBand: true } : { key: DEFAULT_PAIN_SCORE, fromBand: false };
}

/** The summary's request settings: the band's own, plus the clinic-sheet switch when it is on
 *  (the PI, 2026-09-24). Only "1" is ever sent; off sends nothing, as before the button existed.
 *  `painScore`, the page's dropdown (2026-09-25 night), overrides the band's own pain score, so the
 *  deployment ROC, the mixed model and the other panels sharing this request follow it. */
export function summaryRequestParams(bc, includeClinicSheets, painScore) {
  const rp = requestParamsFromCandidate(bc);
  if (painScore) rp.LabelMetric = painScore;
  return includeClinicSheets ? { ...rp, IncludeClinicSheetRatings: "1" } : rp;
}

/**
 * ONE BAND ON THE WHOLE PAGE (decision 302; the live bug of 2026-09-26).
 *
 * The page's results survive a change of settings in the result cache and come back marked stale
 * rather than refetched (the PI's rule; `useCachedResult`). A new band is such a change, so after a
 * band was chosen on the grid the page drew the NEW band's name over the OLD band's report: the
 * header said "L 1-3+ at 24.5 Hz" while the rule table under it was L 0-2+ at 23.5 Hz's ("D52 is
 * violated ... sensing on 0-2"). Stale is fine for a changed cut-point, which leaves the band's
 * report describing the same band; it is not fine for a changed band, because every sentence on the
 * page would be about a band the page does not name.
 *
 * The chosen band is the page's subject: the server's record when it has one (decision 249), and
 * this browser's copy until it answers. A report or summary computed for any other band is withheld
 * from every card, and the page says which band it was for and asks for Recompute.
 */
const bandText = (contact, hz, label) => `${label || contact || "a band"} at ${
  hz == null || !Number.isFinite(Number(hz)) ? "an unspecified" : Number(hz).toFixed(1)} Hz`;

function computedBand(data, kind) {
  if (!data) return null;
  if (kind === "summary") {
    const id = data.identity || {};
    return id.contact ? { contact: id.contact, hz: id.center_freq_hz } : null;
  }
  const c = (data.candidates || [])[0];
  return c && c.channel ? { contact: c.channel, hz: c.center_hz } : null;
}

/** True unless the result says it was computed for a band other than `bc`. */
export function reportIsForBand(data, bc, kind = "report") {
  const got = computedBand(data, kind);
  if (!got || !bc || !bc.contact) return true;
  return String(got.contact) === String(bc.contact)
    && Math.abs(Number(got.hz) - Number(bc.center_freq_hz)) < 1e-6;
}

/**
 * ONE PAIN SCORE AND ONE CLINIC-SHEET SETTING ON THE WHOLE PAGE (decision 307; the live bug of
 * 2026-09-26, the same class as the band). After the dropdown moved from Left Leg VAS to NRS, and
 * before Recompute, the decision card kept the Left Leg VAS verdict and values under a dropdown
 * reading NRS. `want` is the page's current choice: `painScore` (the report's `pain_score.key`, the
 * summary's `identity.pro_metric`) and `includeSheets` (the summary's
 * `identity.clinic_sheet_ratings.included`; the report takes no clinic-sheet switch). A result that
 * does not say what it was computed on is not contradicted, as before.
 */
function computedSettings(data, kind) {
  if (!data) return {};
  if (kind === "summary") {
    const id = data.identity || {};
    const cs = id.clinic_sheet_ratings;
    return { pain: id.pro_metric || null,
      sheets: cs && typeof cs.included === "boolean" ? cs.included : null };
  }
  return { pain: (data.pain_score && data.pain_score.key) || null, sheets: null };
}

const sheetsWords = (on) => (on ? "clinic-sheet ratings included" : "REDCap ratings only");

/** `{what, chosen, computedFor}` for the first setting `data` was computed on that differs from
 *  `want`, or null. */
export function settingsMismatch(data, want, kind = "report") {
  if (!data || !want) return null;
  const got = computedSettings(data, kind);
  if (want.painScore && got.pain && String(got.pain) !== String(want.painScore)) {
    return { what: "pain score", chosen: painScoreLabel(want.painScore),
      computedFor: (kind === "report" && data.pain_score && data.pain_score.label)
        || painScoreLabel(got.pain) };
  }
  if (typeof want.includeSheets === "boolean" && got.sheets != null
    && got.sheets !== want.includeSheets) {
    return { what: "clinic-sheet setting", chosen: sheetsWords(want.includeSheets),
      computedFor: sheetsWords(got.sheets) };
  }
  return null;
}

/** The hook's result unchanged when it is about `bc` (and, when `want` is given, on the page's
 *  current pain score and clinic-sheet setting); otherwise the same result with no data, an `err`
 *  saying why, and `bandMismatch` naming what differs (`what`), the page's choice and what the
 *  result was computed for. A different band is named before a different score. */
export function withheldIfOtherBand(result, bc, kind = "report", want = null) {
  const data = result && result.data;
  if (!data) return result;
  if (!reportIsForBand(data, bc, kind)) {
    const got = computedBand(data, kind);
    const chosen = bandText(bc.contact, bc.center_freq_hz, bc.contact_label);
    const computedFor = bandText(got.contact, got.hz);
    return {
      ...result,
      data: null,
      stale: true,
      err: `the analysis on screen is for ${computedFor}, not the chosen band; press Recompute`,
      bandMismatch: { what: "band", chosen, computedFor },
    };
  }
  const mis = settingsMismatch(data, want, kind);
  if (!mis) return result;
  return {
    ...result,
    data: null,
    stale: true,
    err: `the analysis on screen is for ${mis.computedFor}, not the chosen ${mis.what}; press Recompute`,
    bandMismatch: mis,
  };
}
