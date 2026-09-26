/**
 * ONE VOCABULARY FOR THE TWO SOURCES ON THE HEAT MAPS (the PI, 2026-09-25). Each pain report's band
 * power comes from the time-domain recording, "TD", or from the device's 30 s snapshots, "PSD".
 * The two heat maps, their captions, side panels, legends and the "How to read this" drawer use
 * those two words and nothing else; the drawer introduces them once as "time domain (TD)" and
 * "PSD (the device's 30 s snapshot)". This reads every string literal the heat-map components can
 * print (comments stripped) and fails if an older word for either source comes back, and checks
 * the drawer defines both terms.
 */
import fs from "fs";
import path from "path";

import { bulletsFor } from "./BiomarkerHeatmapGrids";

jest.mock("plotly.js-dist", () => ({ react: () => Promise.resolve(), purge: () => {} }));
jest.mock("graphing-utility/Plotly", () => ({ PlotlyRenderManager: class {} }));

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
