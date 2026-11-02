/** Independently authored UI examples, not participant data or validation results. */
import BASE_REPORT from "./synthetic_refused_right.json";
import BASE_SUMMARY from "./synthetic_summary_right.json";
import { GRID, AUCQ as BIO_AUCQ } from "../../Biomarkers/__fixtures__/synthetic_source_grids";
const copy = (x) => JSON.parse(JSON.stringify(x));
export const CLGRID = copy(GRID);
Object.values(CLGRID.band_time_sweep).forEach((sw) => {
  Object.assign(sw, copy(sw.by_source_grid.td));
  sw.best_correlation_rows.forEach((r) => {
    r.recent_check = { status: "too few recent reports", n_after: 4 };
    if (!r.chronic.covered) return;
    r.td_values = { pearson_r: r.pearson_r, pearson_r_low: r.pearson_r_low,
      pearson_r_high: r.pearson_r_high, n_pain_reports: r.n_pain_reports };
    r.decided_by = "chronic";
    Object.assign(r, { pearson_r: r.chronic.pearson_r, pearson_r_low: r.chronic.pearson_r_low,
      pearson_r_high: r.chronic.pearson_r_high, n_pain_reports: r.chronic.n_reports,
      daily_swing: r.chronic.daily_swing, current_removed_check: { ...r.chronic.current_removed_check,
        words: "Synthetic warning: the current-removed interval crosses zero" },
      recent_check: { ...r.chronic.recent_check, words: "Synthetic recent reports retain the same sign" } });
  });
});
export const AUCQ = { closed_loop: copy(BIO_AUCQ.biomarkers), closed_loop_block: copy(BIO_AUCQ.biomarkers_block) };
export const SWING_WARNING = "Synthetic home power swings 3.0-fold across the day; these thresholds were set from clinic recordings only, so time of day may cross them.";
function report() {
  const r = copy(BASE_REPORT);
  r.threshold_placement = { home_swing: { ratio: 3, thresholds_from: "clinic recordings only", warning: SWING_WARNING } };
  r.peak_above_background = { available: true, median_ratio: 1.5, n_psds: 12 };
  r.prescriptions.modes.dual.fields.filter((f) => f.parameter.includes("LFP threshold"))
    .forEach((f) => { f.why = `Placed from the synthetic record. ${SWING_WARNING}`; });
  return r;
}
export const REP_R = report();
export const REP_L26 = report();
REP_L26.eligibility.advisories.push({ rule_id: "D53", severity: "advisory", kind: "advisory_failed",
  short_label: "No folded multiple of the stimulation rate in or near the band", title: "No folded multiple of the stimulation rate in or near the band" });
REP_L26.peak_above_background = { available: true, median_ratio: 2, n_psds: 16 };
const family = (home) => ({ family_q_status: "in the family", family_q: home ? 0.6 : 0.7,
  family_n: 22, family_p_source: home ? "chronic" : "TD", family_n_auc: 22,
  family_q_auc_status: "in the family", family_q_auc: home ? 0.4 : 0.3, family_q_auc_warning: null });
function summary(home, auc = false) {
  const s = copy(BASE_SUMMARY);
  s.gates.push({ key: "validated", label: "Band validated (rotation test)", state: "fail", evaluated: true });
  s.evidence = { ...s.evidence, p_glmer: 0.04, p_rotation: 0.6, rotation_n_orders: 20,
    current_removed_check: home ? { status: "warning", p: 0.8 } : null,
    recent_check: home ? { status: "checked", choice_cut_date: "2040-02-02", pearson_r: 0.4,
      pearson_r_low: -0.2, pearson_r_high: 0.7, n_after: 12,
      warning: "Synthetic recent reports were also used in choosing, so this checks consistency over time, not an independent test" }
      : { status: "too few recent reports", choice_cut_date: "2040-02-02", n_after: 4,
        note: "Recent-reports check: only 4 reports after 2040-02-02 (fewer than 10), not checked" },
    family_correction: family(home) };
  if (!auc) Object.keys(s.evidence.family_correction).filter((k) => k.includes("auc")).forEach((k) => delete s.evidence.family_correction[k]);
  return s;
}
export const SUM_R = summary(true);
export const SUM_L = summary(false);
export const AUC_SUM_R = summary(true, true);
export const AUC_SUM_L = summary(false, true);
export const BELOW_WARNING = "The lower threshold is below zero (−20.00); band power cannot go below zero, so the device would never cross it.";
export const REP26 = report();
REP26.threshold = { upper: 80, lower: -20 };
const bz = { below_zero: ["lower"], warning: BELOW_WARNING, warnings: { lower: BELOW_WARNING } };
REP26.threshold_placement.below_zero = bz;
REP26.closed_loop_design_rule = { below_zero: bz };
REP26.prescriptions.modes.dual.fields.filter((f) => f.parameter === "Lower LFP threshold").forEach((f) => {
  f.value = -20; f.why += ` ${BELOW_WARNING}`;
});
REP26.prescriptions.modes.single.fields = [{ parameter: "Single LFP threshold", value: 50, why: "Synthetic single threshold", units: "LFP power" }];
const shares = { above: 0.25, between: 0.5, below: 0.25, n_above: 2, n_between: 4, n_below: 2, n: 8 };
const pain = { n_reports: 8, difference: { value: 4, low: -2, high: 10, p_rotation: 0.5, n_above: 2, n_rest: 6 } };
const keys = ["programmed", "clinic_recordings", "manufacturer_guidance", "fitted_on_earlier_reports"];
const labels = ["Programmed now", "(a) Clinic recordings", "(b) Daytime 25th/75th", "(c) Fitted, earlier reports"];
export const REP27 = report();
REP27.threshold_comparison = { available: true, pain_score: "NRS", programmed: { group: "GROUP_A", side: { upper: 120, lower: 60, centre_hz: 27.5 } },
  band: { pair: "ZERO_THREE_LEFT", home_freq_hz: 27.5, n_home_readings: 24 }, n_reports: 8,
  fit: { n_fit: 5, n_held_out: 3 }, too_few_reports: true,
  rows: keys.map((key, i) => ({ key, label: labels[i], upper: 120 + i * 10, lower: 60 + i * 10,
    shares: { all: copy(shares), day: copy(shares), night: copy(shares) }, time_high: { high: 0.25 },
    pain: copy(pain), design_rule: { applies: true, crossings_per_hour_at_most: 4 } })),
  limits: "8 NRS reports have a home reading at this band. Too few for an independent comparison. A clinician programs the device; nothing here writes to it.",
  notes: ["Synthetic device frequency bins are shown without inventing home data."],
};
export const REP15 = report();
REP15.threshold_comparison = copy(REP27.threshold_comparison);
Object.assign(REP15.threshold_comparison, { band: { pair: "ZERO_THREE_LEFT", home_freq_hz: null }, n_reports: 0,
  notes: ["The device runs L 0-3 27.50 Hz; this report's band is L 0-3 15.5 Hz", "No home record at this band"] });
REP15.threshold_comparison.rows = REP15.threshold_comparison.rows.slice(0, 2);
Object.assign(REP15.threshold_comparison.rows[0], { same_band_as_report: false, pair: "ZERO_THREE_LEFT", centre_hz: 27.5 });
Object.assign(REP15.threshold_comparison.rows[1], { shares: {}, time_high: {}, pain: { n_reports: 0 } });
