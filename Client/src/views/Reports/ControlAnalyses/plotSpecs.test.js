/**
 * The titles and the row shading of the check figures (the PI, 2026-10-02).
 *
 * What is pinned:
 *   1. every figure has a short title (at most six words) that says what is plotted;
 *   2. the two figures drawn as rows of dots (one row per sensing pair and length of signal) have
 *      very light alternating bands behind every second row, drawn below the data, in a neutral
 *      that no dot, bar or line of any figure uses, so a row can be followed across the plot;
 *   3. the bands are layout shapes, so they are in no hover and no legend.
 */
import {
  TITLE, ROW_SHADE, rowShades, zeroMaSpec, currentExplainsSpec, currentMemorySpec, regressionToMeanSpec,
  carryOverSpec, ratingPersistenceSpec, steppedCurrentSpec, bandDetectorResearchSpec, bandDeviceSpec,
} from "./plotSpecs";
import { markColours } from "./plotTestUtils";

const row = (pair, seconds) => ({ pair, seconds, n: 100, current_alone: 0.6, bands: 0.7, bands_without_current: 0.65,
  null_p95: 0.62, bands_without_current_null_p95: 0.6, p: 0.04, bands_without_current_p: 0.05 });
const rb = (rho) => ({ rho, lo: rho - 0.1, hi: rho + 0.1, p: 0.2, q: 0.3, null_p95: 0.12 });
const rrow = (pair, seconds) => ({ pair, seconds, reading: { n: 9, current_alone: { rho: 0.2, lo: 0, hi: 0.4 }, bands: rb(0.3), bands_without_current: rb(0.1) } });
const SPECS = {
  zeroMa: zeroMaSpec({ rows: [{ stretch: "s", centre: 21.5, rho: 0.3, lo: 0.1, hi: 0.5, q: 0.04, p: 0.01, n: 5, days: 3 }], stretches: ["s"] }),
  currentExplains: currentExplainsSpec({ rows: [row("ONE_THREE_LEFT", 60), row("ZERO_THREE_RIGHT", 60), row("ONE_THREE_RIGHT", 60)] }),
  currentMemory: currentMemorySpec({ curves: [{ score: "vas", n: 9, rows: [{ tau_h: 0, r2: 0.1 }, { tau_h: 24, r2: 0.2 }] }] }),
  regression: regressionToMeanSpec({ result: { setting: { amp_mA_Left: 1, amp_mA_Right: 1 }, n_blocks: 2,
    target: { by_block: [{ block: 0, n: 1, mean: 1, se: 0.1 }] }, other: { by_block: [{ block: 0, n: 1, mean: 0.5, se: 0.1 }] } } }),
  carryOver: carryOverSpec({ pts: [{ side: "Left", current_mA: 1, diff: -1, rising: 4, falling: 3, falling_first: false, minutes_apart: 9 }] }),
  persistence: ratingPersistenceSpec({ lags: [{ lag_days: 1, r: 0.5, n_pairs: 9 }], score: "vas", nRatings: 9, nDays: 5 }),
  stepped: steppedCurrentSpec({ rows: [{ centre_hz: 24.5, group: "family", relative_slope_per_mA: 0.1, lo: 0.05, hi: 0.15, n: 3, n_runs: 2 }] }),
  research: bandDetectorResearchSpec({ rows: [rrow("ONE_THREE_LEFT", 60), rrow("ZERO_THREE_RIGHT", 60), rrow("ONE_THREE_RIGHT", 60)] }),
  device: bandDeviceSpec({ p: { pair: "ONE_THREE_LEFT", bands: [{ centre_hz: 20.5, reading: { n: 9, band: { auc: 0.6, lo: 0.5, hi: 0.7 } } }] } }),
};

test("1. every figure has a short title that says what is plotted", () => {
  Object.entries(SPECS).forEach(([key, spec]) => {
    expect(spec.layout.title.text).toBe(TITLE[key]);
    expect(TITLE[key].split(/\s+/).length).toBeLessThanOrEqual(6);
  });
  expect(TITLE.currentExplains).toBe("Out-of-sample stimulation-current prediction");
});

test("2. the row figures have alternating light bands below the data, in a neutral no figure uses", () => {
  ["currentExplains", "research"].forEach((key) => {
    const bands = SPECS[key].layout.shapes.filter((sh) => sh.type === "rect");
    expect(bands.map((b) => [b.y0, b.y1])).toEqual([[0.5, 1.5]]);          // 3 rows: the second one is shaded
    bands.forEach((b) => {
      expect(b.layer).toBe("below");
      expect(b.fillcolor).toBe(ROW_SHADE);
      expect(b.line.width).toBe(0);
    });
  });
  expect(rowShades(5).map((b) => b.y0)).toEqual([0.5, 2.5]);
  const used = new Set(Object.values(SPECS).flatMap((spec) => markColours(spec).map((c) => String(c).toLowerCase())));
  expect(used.has(ROW_SHADE.toLowerCase())).toBe(false);
});

test("3. the bands are layout shapes, not traces, so they are in no hover and no legend", () => {
  ["currentExplains", "research"].forEach((key) => {
    SPECS[key].data.forEach((t) => {
      expect(t.hoverinfo).toBe("text");
      expect(t.showlegend).toBe(false);
      (t.hovertext || []).forEach((h) => expect(h).not.toMatch(/shade|band background/i));
    });
    expect(SPECS[key].layout.showlegend).toBe(false);
  });
});
