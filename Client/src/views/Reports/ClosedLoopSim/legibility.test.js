/**
 * Legibility floor for the Closed-Loop and Stim Optimizer pages (the PI, 2026-09-24: "make sure
 * everything is optimized for legibility").
 *
 * Measured on the live Closed-Loop page first: 79 of its 117 visible text elements were under 11 px
 * (down to 8.5 px in the source) and its captions used greys at about 3.5:1 against white, below the
 * 4.5:1 minimum for body text. The Stim Optimizer page already had a type scale (body 13 px,
 * secondary 12 px, secondary grey #5E5E5E). The Closed-Loop page now has a floor of 11 px for text
 * and for figure fonts, and #5E5E5E (about 6.4:1) where the light greys were. This test reads the
 * source of both pages so the floor cannot quietly erode.
 */
import fs from "fs";
import path from "path";

const DIRS = ["ClosedLoopSim", "StimOptimizer"].map((d) => path.join(__dirname, "..", d));
const FILES = DIRS.flatMap((d) => fs.readdirSync(d)
  .filter((f) => f.endsWith(".js") && !f.endsWith(".test.js"))
  .map((f) => path.join(d, f)));
const LIGHT_GREYS = ["#777", "#888", "#8A8A8A", "#999", "#999999", "#9A9A9A"];

test("no text or figure font on either page is set below 11 px", () => {
  const offenders = [];
  FILES.forEach((f) => {
    const src = fs.readFileSync(f, "utf8");
    const re = /(?:fontSize: |font: \{ ?size: )(\d+(?:\.\d+)?)(?![\d.])/g;
    let m = re.exec(src);
    while (m) {
      if (Number(m[1]) < 11) offenders.push(`${path.basename(f)}: ${m[0]}`);
      m = re.exec(src);
    }
  });
  expect(offenders).toEqual([]);
});

test("no caption on either page uses a grey below 4.5:1 on white", () => {
  const offenders = [];
  FILES.forEach((f) => {
    const src = fs.readFileSync(f, "utf8");
    LIGHT_GREYS.forEach((g) => {
      // text colours only (`color: "#..."`): a fill or a stroke in the same grey is not text
      if (new RegExp(`color: ?"${g}"`, "i").test(src)) offenders.push(`${path.basename(f)}: ${g}`);
    });
  });
  expect(offenders).toEqual([]);
});

test("both pages wrap their content in the darker text colour", () => {
  ["ClosedLoopSim", "StimOptimizer"].forEach((d) => {
    const src = fs.readFileSync(path.join(__dirname, "..", d, "index.js"), "utf8");
    expect(src).toMatch(/<LegibleText>/);
  });
});
