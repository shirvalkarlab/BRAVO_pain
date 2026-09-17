/**
 * Review 2026-09-15, findings B1 and B4. The heat maps compute, for each column's best cell, the
 * rating count, the bootstrap interval and the corrected q, and never printed them (B1); and no row
 * said whether its length of signal is an averaging window the device can be set to (B4). The
 * helpers here are what the grid component prints; they are tested against the LIVE numbers the
 * review measured on RCS08 (L 1-3+, 12.5 Hz, 300 s: r -0.534, interval -0.656 to -0.402, n 117,
 * q 0.0022) and the device ranges from the one home.
 */
import { bestCellReadout, hoverCustomData, rowTier, tierBullets, deviceSpectrumBullets, secondsLabel, stabilityMark, stabilityBullet } from "./gridReadouts";

// The block the sweep response carries (DecodeCommon.device_ranges.timing_ranges_for_page), as
// corrected against the clinician tablet on 2026-09-15: onset (Dual) 0-30 s, not the FDA's 6 min.
const RANGES = {
  averaging_s: [0, 30],
  averaging_source: "Medtronic BrainSense Tip Cards (2020, FIELDPORTAL1594651482409), p. 8",
  averaging_caveat: "The 0-30 s range ... confirmed on the clinician tablet's adaptive setup screen ...",
  onset_dual_s: [0, 30],
  onset_source: "Clinician tablet (A610), Adaptive Therapy setup screens, read by the PI on 2026-09-15",
  onset_note: "The FDA summary prints 0 to 6 min ...",
  onset_meaning: "The onset duration does not average: it holds an averaged reading past a threshold ...",
  hold_horizon_s: 60,
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
  test("a cell that is not its column's best points at the circled best cell, in the PI's own words", () => {
    // The PI, 2026-09-15: replace the sentence with "best cell corrected (1m circled)".
    const r = bestCellReadout(SW, "corr", 1, 2);   // 12.5 Hz, 9 s; the column's best is at 300 s = 5m
    expect(r.isBest).toBe(false);
    expect(r.text).toBe("best cell corrected (5m circled)");
  });
  test("the panel lines drop the ratings count, which the plain line beside them already carries", () => {
    // The PI, 2026-09-15: "no reason to say '96 ratings' again".
    expect(bestCellReadout(SW, "corr", 1, 9, { includeN: false }).text)
      .toBe("interval −0.66 to −0.40 · corrected q = 0.0022 · established");
    expect(bestCellReadout(SW, "auc", 2, 3, { includeN: false }).text)
      .toBe("corrected q = 0.029 · established");
    // the hover keeps the count: nothing else on a hover carries it
    expect(bestCellReadout(SW, "corr", 1, 9).text).toMatch(/^117 ratings/);
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
    expect(cd[2][1]).toBe("best cell corrected (5m circled)");
  });
});

describe("row labels and tier bullets (B4)", () => {
  test("the row label is the plain length of signal, nothing appended", () => {
    // The PI, 2026-09-15: "why does it say onset?!" -- the tier is explained in the caption, not the label.
    expect(secondsLabel(45)).toBe("45s");
    expect(secondsLabel(60)).toBe("1m");
    expect(secondsLabel(30)).toBe("30s");
  });
  test("a row at or under the averaging range is an averaging window; above it up to the hold horizon a held level; beyond that nothing", () => {
    expect(rowTier(30, RANGES).tier).toBe("averaging");
    expect(rowTier(45, RANGES).tier).toBe("onset");
    expect(rowTier(60, RANGES).tier).toBe("onset");
    expect(rowTier(300, RANGES).tier).toBe("beyond");
    expect(rowTier(300, null).tier).toBe("unknown");
  });
  test("the caption is short bullets: which rows the device can average, which it can only hold, no sources spelled out", () => {
    const b = tierBullets(RANGES, [3, 6, 9, 15, 21, 24, 30, 45, 60]);
    expect(b.length).toBe(2);
    expect(b[0]).toBe("Rows to 30s: an averaging window the device can be set to (0-30 s on the tablet).");
    expect(b[1]).toBe("Rows 45s-1m: one averaging window plus an onset hold (each \u226430 s); the device holds a level there, it does not average.");
    b.forEach((line) => expect(line.split(" ").length).toBeLessThanOrEqual(24));
  });
  test("no ranges on the response, no bullets", () => {
    expect(tierBullets(null, [3, 30])).toEqual([]);
  });
});

describe("deviceSpectrumBullets", () => {
  test("two short bullets with the count, the share and the 30 s rule; nothing when no report was snapshot-served", () => {
    const sw = { n_pain_reports_from_device_spectrum: 358, device_spectrum_total_grid: [[451, 451], [451, 451]] };
    const b = deviceSpectrumBullets(sw);
    expect(b).toEqual([
      "358 of 451 matched reports (79%) had no voltage trace in the match window and were read from the device's 30 s FFT snapshots: a row of N s uses the nearest ceil(N/30) snapshots, or nothing.",
      "Matching here uses the histogram card's tolerance.",
    ]);
    expect(deviceSpectrumBullets({ n_pain_reports_from_device_spectrum: 0 })).toEqual([]);
    expect(deviceSpectrumBullets(null)).toEqual([]);
  });
});

describe("cross-setting stability on the grid (B3, decision 185)", () => {
  const withStability = (answer, reason) => ({
    ...SW,
    best_correlation_rows: SW.best_correlation_rows.map((r) =>
      r.band_center_hz === 12.5 ? { ...r, cross_setting_stability: { answer, reason, from_store: answer !== "not tested" } } : r),
  });
  test("the best cell's hover ends with the answer the Closed-Loop card gives", () => {
    const r = bestCellReadout(withStability("behaves differently", "the interaction test rejects"), "corr", 1, 9);
    expect(r.text).toBe("117 ratings · interval −0.66 to −0.40 · corrected q = 0.0022 · established · across settings: behaves differently");
  });
  test("an answer not yet computed says so in three words, not 'not tested'", () => {
    const r = bestCellReadout(withStability("not tested", "the cross-setting stability answer has not been computed for this grid yet"), "corr", 1, 9);
    expect(r.text.endsWith("across settings: not yet computed")).toBe(true);
  });
  test("a row carrying no answer at all leaves the hover as it was", () => {
    expect(bestCellReadout(SW, "corr", 1, 9).text).toBe("117 ratings · interval −0.66 to −0.40 · corrected q = 0.0022 · established");
  });
  test("one symbol per answer, the Closed-Loop card's: tick, cross, amber disc, nothing", () => {
    expect(stabilityMark({ answer: "behaves the same" })).toEqual({ symbol: "circle", color: "#2e7d32", label: "behaves the same at every setting" });
    expect(stabilityMark({ answer: "behaves differently" })).toEqual({ symbol: "x", color: "#c62828", label: "behaves differently across settings" });
    expect(stabilityMark({ answer: "cannot tell" })).toEqual({ symbol: "diamond", color: "#e0a100", label: "cannot tell" });
    expect(stabilityMark({ answer: "not tested" })).toBeNull();
    expect(stabilityMark(undefined)).toBeNull();
  });
  test("the caption bullet names the three symbols in under 24 words", () => {
    const line = stabilityBullet();
    expect(line).toMatch(/tick/);
    expect(line).toMatch(/cross/);
    expect(line).toMatch(/amber/);
    expect(line.split(" ").length).toBeLessThanOrEqual(24);
  });
});
