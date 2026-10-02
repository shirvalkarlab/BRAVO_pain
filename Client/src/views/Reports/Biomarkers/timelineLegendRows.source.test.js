/**
 * The timeline's legend height is counted from the legend entries actually drawn, so the box cannot
 * rise over the title when an entry is added or a long name wraps (page review 2026-10-02: in
 * Multimodal colouring the key overlapped "Biomarker Data Timeline"). A source check, like the
 * other `*.source.test.js` files, because the figure is drawn by Plotly and has no DOM to read.
 */
import fs from "fs";
import path from "path";

const src = fs.readFileSync(path.join(__dirname, "BiomarkerDataTimeline.js"), "utf8");

test("the legend row count comes from the key traces, with a long name counted twice", () => {
  expect(src).toMatch(/const keyNames = traces\.filter\(\(t\) => t\.showlegend !== false && t\.name\)/);
  expect(src).toMatch(/keyNames\.filter\(\(n\) => n\.length > 70\)\.length/);
  expect(src).not.toMatch(/const nLegRows = binMode \? 5 : 7;/);
});

test("the pain-split histogram leaves room above the plot for the high-cut label (raised at 1.13)", () => {
  const prev = fs.readFileSync(path.join(__dirname, "BinarizationPreview.js"), "utf8");
  expect(prev).toMatch(/margin: \{ l: 56, r: 16, t: 80, b: 44 \}/);
});
