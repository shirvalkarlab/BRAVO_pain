/**
 * Review 2026-09-15, findings B1 and B4. The heat maps compute, for each column's best cell, the
 * rating count, the bootstrap interval and the corrected q, and never printed them (B1); and no row
 * said whether its length of signal is an averaging window the device can be set to (B4). The
 * helpers here are what the grid component prints; they are tested against the LIVE numbers the
 * review measured on RCS08 (L 1-3+, 12.5 Hz, 300 s: r -0.534, interval -0.656 to -0.402, n 117,
 * q 0.0022) and the device ranges from the one home.
 */
import { bestCellReadout, hoverCustomData, rowTier, rowLabelWithTier, tierCaption } from "./gridReadouts";

const RANGES = {
  averaging_s: [0, 30],
  averaging_source: "Medtronic BrainSense Tip Cards (2020, FIELDPORTAL1594651482409), p. 8",
  averaging_caveat: "The 0-30 s range is printed in a 2020 sensing-era tip card ... not stated ...",
  onset_dual_s: [0, 360],
  onset_source: "FDA SSED P960009/S478 (20 Feb 2025), Table 2 'Key aDBS Configurable Parameters', p. 8",
  onset_meaning: "The onset duration does not average: it holds an averaged reading past a threshold ...",
};

const SW = {
  center_freqs_hz: [11.5, 12.5, 13.5],
  integration_seconds_delivered: [3, 6, 9, 15, 21, 24, 30, 45, 60, 300],
  correlation_grid: Array.from({ length: 10 }, () => [-0.1, -0.2, -0.3]),
  best_correlation_rows: [
    { band_center_hz: 12.5, pearson_r: -0.5335247321989319, pearson_r_low: -0.6562928729386238,
      pearson_r_high: -0.4020824075079909, n_pain_reports: 117, p_selection_aware: 0.000999,
      family_wise_q_8_to_30hz: 0.002197802197802198, family_wise_significant_8_to_30hz: true,
      integration_seconds_delivered: 300.0, answer: "established" },
    { band_center_hz: 13.5, pearson_r: -0.515, pearson_r_low: -0.626, pearson_r_high: -0.382,
      n_pain_reports: 117, p_selection_aware: 0.000999, family_wise_q_8_to_30hz: 0.0022,
      family_wise_significant_8_to_30hz: true, integration_seconds_delivered: 300.0, answer: "established" },
  ],
  best_auc_rows: [
    { band_center_hz: 13.5, auc: 0.24314841784721303, n_pain_reports: 174, p_selection_aware: 0.003996,
      family_wise_q_8_to_30hz: 0.0293040293040293, family_wise_significant_8_to_30hz: true,
      integration_seconds_delivered: 15.0, answer: "established" },
  ],
};

describe("bestCellReadout (B1)", () => {
  test("the column's best cell prints n, the interval and the corrected q", () => {
    const r = bestCellReadout(SW, "corr", 1, 9);   // 12.5 Hz, 300 s
    expect(r.isBest).toBe(true);
    expect(r.text).toBe("117 ratings · interval −0.66 to −0.40 · corrected q = 0.0022 · established");
  });
  test("a cell that is not its column's best says the corrected statistic exists only for the best", () => {
    const r = bestCellReadout(SW, "corr", 1, 2);   // 12.5 Hz, 9 s
    expect(r.isBest).toBe(false);
    expect(r.text).toBe("corrected statistics are computed for this column's best cell only (5m, circled)");
  });
  test("the AUC grid reads its own best row", () => {
    const r = bestCellReadout(SW, "auc", 2, 3);    // 13.5 Hz, 15 s
    expect(r.isBest).toBe(true);
    expect(r.text).toBe("174 ratings · corrected q = 0.029 · established");
  });
  test("a column with no best row says so rather than printing nothing", () => {
    expect(bestCellReadout(SW, "auc", 0, 0).text).toBe("no corrected statistic for this column");
  });
});

describe("hoverCustomData (B1)", () => {
  test("is a rows x columns grid of the same readouts, so the hover template can print them", () => {
    const cd = hoverCustomData(SW, "corr");
    expect(cd.length).toBe(10);
    expect(cd[9].length).toBe(3);
    expect(cd[9][1]).toMatch(/^117 ratings/);
    expect(cd[2][1]).toMatch(/best cell only/);
  });
});

describe("rowTier (B4)", () => {
  test("a row at or under the documented averaging range is an averaging window", () => {
    expect(rowTier(30, RANGES).tier).toBe("averaging");
    expect(rowTier(3, RANGES).tier).toBe("averaging");
  });
  test("a row above the averaging range but inside the Dual onset range is a held level, not a mean", () => {
    expect(rowTier(45, RANGES).tier).toBe("onset");
    expect(rowTier(300, RANGES).tier).toBe("onset");
  });
  test("a row beyond the onset range is beyond anything the device can be set to", () => {
    expect(rowTier(600, RANGES).tier).toBe("beyond");
  });
  test("with no ranges on the response the tier is unknown and the label is untouched", () => {
    expect(rowTier(300, null).tier).toBe("unknown");
    expect(rowLabelWithTier(300, null)).toBe("5m");
  });
  test("the row label carries the tier where it is not an averaging window", () => {
    expect(rowLabelWithTier(30, RANGES)).toBe("30s");
    expect(rowLabelWithTier(45, RANGES)).toBe("45s ⏵ onset");
    expect(rowLabelWithTier(300, RANGES)).toBe("5m ⏵ onset");
  });
  test("the caption names the boundary, the source, and that an onset holds rather than averages", () => {
    const c = tierCaption(RANGES, SW.integration_seconds_delivered);
    expect(c).toContain("Rows up to 30s are an averaging window the device can be set to");
    expect(c).toContain("Tip Cards");
    expect(c).toContain("Rows from 45s to 5m");
    expect(c).toContain("holds");
    expect(c).toContain("sensing-era");
  });
});
