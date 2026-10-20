/**
 * ONE VOCABULARY FOR THE TWO SOURCES ON THE HEAT MAPS (the PI, 2026-09-25). Each pain report's band
 * power comes from the time-domain recording, "TD", or from the device's 30 s snapshots, "PSD".
 * The two heat maps, their captions, side panels, legends and the "Reading guide" drawer use
 * those two words and nothing else; the drawer introduces them once as "time domain (TD)" and
 * "PSD (the device's 30 s snapshot)". This reads every string literal the heat-map components can
 * print (comments stripped) and fails if an older word for either source comes back, and checks
 * the drawer defines both terms.
 *
 * Merged here 2026-10-05: gridStatusLine.grammar.test.js, ScatterStatsLine.sourceSplit.test.js.
 * Each merged file's tests sit in a describe block named after it, with its reason above it.
 */

import fs from "fs";
import path from "path";
import { bulletsFor, gridStatusLine, gridStatusLine as _gsl, ScatterStatsLine } from "./BiomarkerHeatmapGrids";
import "@testing-library/jest-dom";
import { render } from "@testing-library/react";
import { wrap } from "testUtils/render";

jest.mock("plotly.js-dist", () => ({ react: () => Promise.resolve(), purge: () => {}, restyle: () => {},
  relayout: () => {}, newPlot: () => {}, Plots: { resize: () => {} } }));
jest.mock("graphing-utility/Plotly", () => ({ PlotlyRenderManager: class {} }));
jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn() } }));

const FILES = ["BiomarkerHeatmapGrids.js", "gridReadouts.js"];
const ALLOWED = ["time domain (TD)", "PSD (the device's 30 s snapshot)"];
const OLD_WORDS = /voltage|\btraces?\b|snapshots?|\bFFT\b|streaming|time.domain|device's own spectrum|-served|-read\b/i;

function stringLiterals(src) {
  const code = src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:"'\\])\/\/[^\n]*/g, "$1");
  return code.match(/"(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*'|`(?:[^`\\]|\\.)*`/g) || [];
}

describe("the heat maps name the two sources TD and PSD only", () => {
  FILES.forEach((f) => {
    test(`${f}: no older word for either source in any printable string`, () => {
      const src = fs.readFileSync(path.join(__dirname, f), "utf8");
      const bad = stringLiterals(src)
        .map((lit) => ALLOWED.reduce((s, a) => s.split(a).join(""), lit))
        .filter((lit) => OLD_WORDS.test(lit));
      expect(bad).toEqual([]);
    });
  });
  test("the drawer defines both terms, once each, at their first mention", () => {
    const bullets = bulletsFor({ notes: [] });
    const joined = bullets.join(" ");
    expect(joined.split("time domain (TD)").length - 1).toBe(1);
    expect(joined.split("PSD (the device's 30 s snapshot)").length - 1).toBe(1);
    const first = bullets.findIndex((b) => /\bTD\b|\bPSD\b/.test(b));
    expect(bullets[first]).toMatch(/time domain \(TD\)/);
    expect(bullets[first]).toMatch(/PSD \(the device's 30 s snapshot\)/);
  });
  test("the guard itself catches an old word (negative control)", () => {
    const lits = stringLiterals('const a = "read from the device\'s 30 s FFT snapshots"; // voltage trace in a comment is fine');
    expect(lits.filter((l) => OLD_WORDS.test(l)).length).toBe(1);
    expect(stringLiterals("// only a comment about the voltage trace").length).toBe(0);
  });
});

/* From gridStatusLine.grammar.test.js.
 * The heat maps' status line agrees in number: "1 band rises", "2 bands rise" (seen live
 * 2026-09-26 as "1 band rise with pain").
 */
describe("from gridStatusLine.grammar", () => {
  const row = (r) => ({ pearson_r: r, family_wise_q_8_to_30hz: 0.01 });
  const result = (rows) => ({ band_time_sweep: { ONE_THREE_LEFT: { display_short: "L 1-3+", best_correlation_rows: rows } } });

  describe("the heat maps' status line", () => {
    it("says one band rises and one falls in the singular", () => {
      expect(gridStatusLine(result([row(0.3), row(-0.3)]), "NRS"))
        .toMatch(/1 band rises with pain and 1 falls with it/);
    });
    it("keeps the plural for other counts", () => {
      expect(gridStatusLine(result([row(0.3), row(0.2), row(-0.3), row(-0.2)]), "NRS"))
        .toMatch(/2 bands rise with pain and 2 fall with it/);
    });
  });

  test("the status line says the 22 bands are tested in each pair, so counts above 22 read right", () => {
    expect(_gsl({ band_time_sweep: {} }, "Left Leg VAS")).toMatch(/22 bands tested in each pair/);
  });
});

/* From ScatterStatsLine.sourceSplit.test.js.
 * P-19 (the PI, 2026-09-25): the TD / PSD line sits in the side panel ABOVE the scatter, as one line
 * of text, under the cell's own statistics; the hover is untouched. Rendered with a constructed grid
 * response and a loaded cell, since the page reaches this panel only after a click Plotly delivers.
 */
describe("from ScatterStatsLine.sourceSplit", () => {
  // Independently authored response fields; no participant measurements.
  const SW = {
    center_freqs_hz: [24.5],
    integration_seconds_delivered: [30],
    correlation_grid: [[-0.1]], p_grid: [[0.5]], n_grid: [[30]],
    best_correlation_rows: [],
    correlation_by_recording_source: {
      available: true, min_reports: 8,
      td: { r_grid: [[-0.1]], n_grid: [[14]], r_low_grid: [[-0.3]], r_high_grid: [[0.2]] },
      psd: { r_grid: [[-0.4]], n_grid: [[16]], r_low_grid: [[-0.6]], r_high_grid: [[-0.2]] },
    },
  };
  const CELL = { loading: false, points: [{ pain: 7, power: 100, label: "high" }] };
  const PINNED = { row: 0, col: 0, channel: "ONE_THREE_LEFT", center: 24.5, seconds: 30 };

  test("the line is printed under the cell's own statistics, in the PI's words", () => {
    const { container, getByTestId } = render(
      wrap(<ScatterStatsLine cell={CELL} pinnedCell={PINNED} sw={SW} />));
    const line = getByTestId("source-split-line");
    expect(line.textContent).toBe(
      "TD values: R \u22120.10 (\u22120.30 to +0.20), n=14\nPSD values: R \u22120.40 (\u22120.60 to \u22120.20), n=16");
    // The cell's own statistics line ("r = ..., p = ..., n = ...") comes first, then the source split.
    const text = container.textContent;
    const own = text.indexOf("r = -0.10, p = 0.50, n = 30");
    expect(own).toBeGreaterThanOrEqual(0);
    expect(own).toBeLessThan(text.indexOf("TD values:"));
  });

  test("no line for a stored grid built before the split", () => {
    const { queryByTestId } = render(
      wrap(<ScatterStatsLine cell={CELL} pinnedCell={PINNED}
        sw={{ ...SW, correlation_by_recording_source: undefined }} />));
    expect(queryByTestId("source-split-line")).toBeNull();
  });
});
