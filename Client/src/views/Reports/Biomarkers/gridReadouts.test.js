/**
 * Review 2026-09-15, findings B1 and B4. The heat maps compute, for each column's best cell, the
 * rating count, the bootstrap interval and the corrected q, and never printed them (B1); and no row
 * said whether its length of signal is an averaging window the device can be set to (B4). The
 * helpers here are what the grid component prints; they are tested against the LIVE numbers the
 * review measured on RCS08 (L 1-3+, 12.5 Hz, 300 s: r -0.534, interval -0.656 to -0.402, n 117,
 * q 0.0022) and the device ranges from the one home.
 */
import { bestCellReadout, hoverReadout, hoverCustomData, rowTier, tierBullets, deviceSpectrumBullets, secondsLabel, stabilityMark, stabilityBullet, clinicSheetBullets, sourceSplitLine } from "./gridReadouts";

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

describe("hoverReadout -- the hover's third line (the PI, 2026-09-16)", () => {
  // His words: delete the current third line and replace it with "X ratings, q=Y" and that is all;
  // X the number of samples, Y the q value; where no q exists, the raw p-value as "p = Y". The
  // interval, the answer and the stability word stay on the panel lines beside the scatter and violin.
  const withN = {
    ...SW,
    n_grid: Array.from({ length: 10 }, () => [40, 96, 50]),
    p_grid: Array.from({ length: 10 }, () => [0.4, 0.0507, 0.2]),
    auc_grid: Array.from({ length: 10 }, () => [0.5, 0.4, 0.3]),
    auc_p_grid: Array.from({ length: 10 }, () => [1.0, 0.2, 0.0153]),
    auc_n_high_grid: Array.from({ length: 10 }, () => [20, 30, 25]),
    auc_n_low_grid: Array.from({ length: 10 }, () => [20, 30, 25]),
  };
  test("the column's best cell: its ratings count and its corrected q, nothing else", () => {
    expect(hoverReadout(withN, "corr", 1, 9)).toBe("117 ratings, q = 0.0022");
    expect(hoverReadout(withN, "auc", 2, 3)).toBe("174 ratings, q = 0.029");
  });
  test("any other cell: its own count and its own uncorrected p, both read off the response", () => {
    // nothing is computed in the browser: `p_grid` (Pearson) and `auc_p_grid` (Mann-Whitney) come
    // from the backend (decision 188)
    expect(hoverReadout(withN, "corr", 1, 2)).toBe("96 ratings, p = 0.051");
    expect(hoverReadout(withN, "auc", 2, 0)).toBe("50 ratings, p = 0.015");
  });
  test("a response without the p grids (older stored) prints the count alone", () => {
    const noP = { ...withN, p_grid: undefined, auc_p_grid: undefined };
    expect(hoverReadout(noP, "corr", 1, 2)).toBe("96 ratings");
  });
  test("a best cell whose q was not assessed falls back to its raw p", () => {
    const noQ = { ...withN, best_correlation_rows: withN.best_correlation_rows.map((r) => ({ ...r, family_wise_q_8_to_30hz: null })) };
    expect(hoverReadout(noQ, "corr", 1, 9)).toBe("117 ratings, p = 0.000999");
  });
  test("a cell with no count prints nothing rather than a dash", () => {
    expect(hoverReadout(SW, "corr", 1, 2)).toBe("");
  });
  test("the cross-setting stability word is not on the hover (it is drawn as a symbol)", () => {
    const stab = { ...withN, best_correlation_rows: withN.best_correlation_rows.map((r) => ({ ...r, cross_setting_stability: { answer: "behaves differently" } })) };
    expect(hoverReadout(stab, "corr", 1, 9)).toBe("117 ratings, q = 0.0022");
  });
});

describe("hoverCustomData (B1)", () => {
  test("is a rows x columns grid of the hover readouts, so the hover template can print them", () => {
    const withN = { ...SW, n_grid: Array.from({ length: 10 }, () => [40, 96, 50]), p_grid: Array.from({ length: 10 }, () => [0.4, 0.0507, 0.2]) };
    const cd = hoverCustomData(withN, "corr");
    expect(cd.length).toBe(10);
    expect(cd[9].length).toBe(3);
    expect(cd[9][1]).toBe("117 ratings, q = 0.0022");
    expect(cd[2][1]).toBe("96 ratings, p = 0.051");
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
      // The PI's vocabulary on the heat maps (2026-09-25): TD and PSD, one word each, everywhere.
      "358 of 451 matched reports (79%) had no TD in the match window and were read from PSD: a row of N s uses the nearest ceil(N/30) PSDs, or nothing.",
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
  test("the best cell's panel line ends with the answer the Closed-Loop card gives", () => {
    const r = bestCellReadout(withStability("behaves differently", "the interaction test rejects"), "corr", 1, 9);
    expect(r.text).toBe("117 ratings · interval −0.66 to −0.40 · corrected q = 0.0022 · established · across settings: behaves differently");
  });
  test("an answer not yet computed says so in three words, not 'not tested'", () => {
    const r = bestCellReadout(withStability("not tested", "the cross-setting stability answer has not been computed for this grid yet"), "corr", 1, 9);
    expect(r.text.endsWith("across settings: not yet computed")).toBe(true);
  });
  test("a row carrying no answer at all leaves the panel line as it was", () => {
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

describe("clinic-sheet ratings on the heat maps (B5, decision 186)", () => {
  test("off: one bullet says the heat maps pool the chronic REDCap ratings only", () => {
    const b = clinicSheetBullets({ ...SW, clinic_sheet_ratings: { included: false, n_added: 0 } });
    expect(b).toHaveLength(1);
    expect(b[0]).toMatch(/chronic REDCap ratings only/);
    expect(b[0]).toMatch(/switch/i);
  });
  test("on: the bullet counts the sheet ratings this contact pair uses and says the scale", () => {
    const sw = { ...SW, clinic_sheet_ratings: { included: true, n_added: 152, sheet_column: "left_leg", scale: 10 },
                 n_pain_reports_from_clinic_sheet: 83, n_pain_reports: 222 };
    const b = clinicSheetBullets(sw);
    expect(b[0]).toMatch(/83 of the 222/);
    expect(b[0]).toMatch(/clinic titration sessions/);
    expect(b[0]).toMatch(/times 10/);
    b.forEach((line) => expect(line.split(" ").length).toBeLessThanOrEqual(30));
  });
  test("on for a score the sheets do not carry: the bullet says so and adds nothing", () => {
    const b = clinicSheetBullets({ ...SW, clinic_sheet_ratings: { included: true, n_added: 0, reason: "the sheets carry no column for MPQ Sum" } });
    expect(b[0]).toMatch(/no column for MPQ Sum/);
  });
  test("an older response without the block prints nothing", () => {
    expect(clinicSheetBullets(SW)).toEqual([]);
  });
});

describe("the effective count beside the raw count (panel A item 4, 2026-09-22)", () => {
  // Ratings filed close together, and band power that drifts slowly, are worth fewer independent
  // observations than their number. The backend puts `n_pain_reports_effective` on each column's
  // best row; the readouts print it inside the ratings part, and nowhere a response lacks it.
  const withEff = JSON.parse(JSON.stringify(SW));
  withEff.best_correlation_rows[0].n_pain_reports_effective = 98.4;
  withEff.n_grid = Array.from({ length: 10 }, () => [40, 96, 50]);
  withEff.p_grid = Array.from({ length: 10 }, () => [0.4, 0.0507, 0.2]);

  test("the hover on the best cell names about how many ratings are independent", () => {
    expect(hoverReadout(withEff, "corr", 1, 9)).toBe("117 ratings (about 98 independent), q = 0.0022");
  });
  test("the panel line names it too", () => {
    expect(bestCellReadout(withEff, "corr", 1, 9).text).toMatch(/^117 ratings \(about 98 independent\) · interval/);
  });
  test("a best row without the field, and any other cell, print exactly what they did", () => {
    expect(hoverReadout(withEff, "auc", 2, 3)).toMatch(/^174 ratings, q = /);
    expect(hoverReadout(withEff, "corr", 1, 2)).toBe("96 ratings, p = 0.051");
    expect(bestCellReadout(SW, "corr", 1, 9).text).toMatch(/^117 ratings · interval/);
  });
});

// P-19 (the PI, 2026-09-25): each cell's correlation on its TD reports alone and on its PSD reports
// alone, as ONE line of text above the scatter -- never in the hover, never a figure. The numbers
// are the live RCS08 cell the P-19 analysis measured (L 1-3+, 24.5 Hz, 30 s, NRS, daily defaults).
describe("the TD / PSD line above the scatter (P-19)", () => {
  const split = {
    available: true, min_reports: 8,
    td: { r_grid: [[-0.1, -0.0512]], n_grid: [[70, 76]], r_low_grid: [[-0.3, -0.2311]], r_high_grid: [[0.1, 0.1204]] },
    psd: { r_grid: [[-0.2, -0.3698]], n_grid: [[5, 86]], r_low_grid: [[null, -0.5611]], r_high_grid: [[null, -0.1893]] },
  };
  const sw = { center_freqs_hz: [23.5, 24.5], correlation_by_recording_source: split };
  test("both sources, each with its interval and count, in the PI's words", () => {
    expect(sourceSplitLine(sw, 1, 0)).toBe(
      "TD values: r \u22120.05 (\u22120.23 to +0.12), 76 reports \u00b7 PSD values: r \u22120.37 (\u22120.56 to \u22120.19), 86 reports");
  });
  test("a source under the minimum reads 'too few reports' with its count", () => {
    expect(sourceSplitLine(sw, 0, 0)).toBe(
      "TD values: r \u22120.10 (\u22120.30 to +0.10), 70 reports \u00b7 PSD values: too few reports (5)");
  });
  test("no line from a response without the split, or one that could not make it", () => {
    expect(sourceSplitLine({ center_freqs_hz: [24.5] }, 0, 0)).toBeNull();
    expect(sourceSplitLine({ correlation_by_recording_source: { available: false, reason: "x" } }, 0, 0)).toBeNull();
    expect(sourceSplitLine(null, 0, 0)).toBeNull();
  });
  test("the hover carries no source text (the PI: the hover stays as it is)", () => {
    const full = { ...SW, correlation_by_recording_source: { available: true, min_reports: 8,
      td: { r_grid: SW.correlation_grid, n_grid: SW.correlation_grid.map((r) => r.map(() => 50)),
        r_low_grid: SW.correlation_grid, r_high_grid: SW.correlation_grid },
      psd: { r_grid: SW.correlation_grid, n_grid: SW.correlation_grid.map((r) => r.map(() => 50)),
        r_low_grid: SW.correlation_grid, r_high_grid: SW.correlation_grid } } };
    expect(hoverCustomData(full, "corr")).toEqual(hoverCustomData(SW, "corr"));
    hoverCustomData(full, "corr").flat().forEach((h) => expect(h).not.toMatch(/TD|PSD/));
  });
});
