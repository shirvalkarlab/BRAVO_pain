/** Independently authored UI contracts. No measured participant responses or empirical claims. */
const centres = [8.5, 9.5, 10.5, 11.5, 12.5, 15.5, 23.5, 24.5, 26.5, 29.5];
const seconds = [3, 30];
const matrix = (value) => seconds.map(() => centres.map(() => value));
const clone = (x) => JSON.parse(JSON.stringify(x));
const homeCentres = [8.5, 9.5, 10.5, 11.5, 24.5, 26.5];
const cut = { choice_cut_date: "2040-02-01", rolling: true };
const swing = { status: "measured", ratio: 3, warn_at_ratio: 2, hour_low: 8, hour_high: 20 };
const current = { status: "warning", p_rotation: 0.9 };
const recent = { status: "checked", pearson_r: 0.5, pearson_r_low: 0.2, pearson_r_high: 0.8, n_after: 6 };
const noHome = "no home record at this band";
const mixedWhy = "Mixed grid (TD, PSD where no TD): shown, never chooses a band; the band is chosen from the TD-only grid";
const psdWhy = "PSD only: shown, cannot choose a band; the band is chosen from the TD-only grid";
const perPair = {
  ZERO_THREE_LEFT: { display: "L 0⁻3⁺", n_in_family: 22 },
  ZERO_THREE_RIGHT: { display: "R 0⁻3⁺", n_in_family: 22 },
};
function sweep(channel, source) {
  const allowed = channel !== "ONE_THREE_LEFT";
  const isHome = (hz) => channel === "ZERO_THREE_RIGHT" && homeCentres.includes(hz);
  const rows = centres.map((hz) => ({
    band_center_hz: hz, integration_seconds_delivered: 30, pearson_r: -0.4,
    pearson_r_low: -0.6, pearson_r_high: -0.2, n_pain_reports: source === "td" ? 8 : source === "psd" ? 16 : 24,
    family_wise_q_8_to_30hz: 0.2, family_q: allowed ? 0.6 : null,
    family_q_status: allowed ? "in the family" : "not an allowed sensing pair",
    family_q_warning: channel === "ZERO_THREE_LEFT" && hz === 12.5 ? "this band's q is 0.60: it may be a chance finding" : null,
    grid_source: source, can_choose_band: source === "td", cannot_choose_why: source === "td" ? null : source === "psd" ? psdWhy : mixedWhy,
    choice_source: source === "td" ? (isHome(hz) ? "chronic" : "TD") : "none",
    chronic: isHome(hz) ? { covered: true, pearson_r: 0.2, pearson_r_low: -0.2, pearson_r_high: 0.6,
      n_reports: 12, n_reports_in_gap: 4, n_reports_log_elsewhere: 2, current_removed_check: current,
      daily_swing: swing, recent_check: recent } : { covered: false, words: noHome },
    daily_swing: { status: noHome },
  }));
  return {
    display_hemisphere: channel.endsWith("RIGHT") ? "Right" : "Left",
    display_short: channel === "ZERO_THREE_RIGHT" ? "R 0⁻3⁺" : channel === "ZERO_THREE_LEFT" ? "L 0⁻3⁺" : "L 1⁻3⁺",
    display_region: "Synthetic target", grid_source: source, center_freqs_hz: centres,
    integration_seconds_requested: seconds, integration_seconds_delivered: seconds,
    correlation_grid: matrix(source === "td" ? -0.4 : source === "psd" ? 0.1 : 0.3),
    n_grid: matrix(source === "td" ? 8 : source === "psd" ? 16 : 24), p_grid: matrix(0.2),
    auc_grid: matrix(0.6), auc_p_grid: matrix(0.3), auc_n_high_grid: matrix(4), auc_n_low_grid: matrix(4),
    device_spectrum_total_grid: matrix(24), n_pain_reports: 24, n_pain_reports_from_device_spectrum: 18,
    best_correlation_rows: rows, best_auc_rows: rows.map((r) => ({ ...r, auc: 0.6 })), recent_check_cut: cut,
  };
}
export const GRID = {
  _fixture_provenance: "Invented component contracts; not empirical validation",
  settings_applied: { match_tolerance_min: 15, chronic_match: "covering", chronic_match_is_default: true },
  recent_check_cut: cut, family_correction: { available: true, q_warn: 0.05, per_pair: perPair },
  band_time_sweep: Object.fromEntries(["ZERO_THREE_RIGHT", "ZERO_THREE_LEFT", "ONE_THREE_LEFT"].map((ch) => [ch,
    { ...sweep(ch, "td_psd_where_no_td"), by_source_grid: { td: sweep(ch, "td"), psd: sweep(ch, "psd") } }])),
};
export const GRID_WINDOW = clone(GRID);
GRID_WINDOW.settings_applied = { ...GRID.settings_applied, chronic_match: "window", chronic_match_is_default: false };
Object.values(GRID_WINDOW.band_time_sweep).forEach((sw) => sw.by_source_grid.td.best_correlation_rows.forEach((r) => {
  if (!r.chronic.covered) return;
  Object.assign(r.chronic, { pearson_r: -0.2, pearson_r_low: -0.6, pearson_r_high: 0.2, n_reports: 18,
    warning: "Not the recommended default: this home-record answer pairs each pain report with the chronic readings within the page's matching window (15 minutes either side)." });
  r.family_q = 0.7;
}));
export const AUCQ = { biomarkers: Object.fromEntries(Object.keys(GRID.band_time_sweep).map((ch) => [ch,
  centres.map((hz) => ({ band_center_hz: hz, family_q_auc: ch === "ONE_THREE_LEFT" ? null : 0.4,
    family_q_auc_status: ch === "ONE_THREE_LEFT" ? "not an allowed sensing pair" : "in the family",
    family_q_auc_warning: ch === "ZERO_THREE_LEFT" && hz === 29.5 ? "Synthetic AUC family warning" : null }))])),
  biomarkers_block: { per_pair_auc: perPair } };
const points = (n) => Array.from({ length: n }, (_, i) => ({
  power: i + 1, label_value: i % 5, label_time: i * 600, label: i < n / 2 ? "low" : "high",
}));
export const CELLS = Object.fromEntries([["td", 8], ["psd", 16], ["default", 24]].map(([source, n]) =>
  [source, { band_time_sweep_cell: { points: points(n) } }]));
