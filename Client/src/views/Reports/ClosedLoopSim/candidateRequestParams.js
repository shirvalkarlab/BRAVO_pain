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

/** The summary's request settings: the band's own, plus the clinic-sheet switch when it is on
 *  (the PI, 2026-09-24). Only "1" is ever sent; off sends nothing, as before the button existed. */
export function summaryRequestParams(bc, includeClinicSheets) {
  const rp = requestParamsFromCandidate(bc);
  return includeClinicSheets ? { ...rp, IncludeClinicSheetRatings: "1" } : rp;
}
