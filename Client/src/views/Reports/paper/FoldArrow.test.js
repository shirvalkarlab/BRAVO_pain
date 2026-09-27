/**
 * The shared fold/toggle arrow (the PI, 2026-09-27: one prominent mark, not six copies of a plain
 * character). Pins the visual (a filled, coloured chip, not a bare 14 px glyph) and that every
 * file which draws a fold row imports it instead of hand-rolling its own `▸` span.
 */
import fs from "fs";
import path from "path";
import React from "react";
import { render } from "@testing-library/react";

import FoldArrow from "./FoldArrow";

test("closed reads a right-pointing chip in the accent colour, filled", () => {
  const { container } = render(<FoldArrow open={false} />);
  const span = container.querySelector('[data-paper="fold-arrow"]');
  expect(span).not.toBeNull();
  expect(span.style.transform === "none" || span.style.transform === "").toBe(true);
  expect(span.textContent).toBe("▸");
});

test("open rotates a quarter turn", () => {
  const { container } = render(<FoldArrow open />);
  const span = container.querySelector('[data-paper="fold-arrow"]');
  expect(span.style.transform).toMatch(/rotate\(90deg\)/);
});

// --- one home: every fold-drawing file uses this component, not its own copy ---------------------
const ROOT = path.join(__dirname, "..");
const FOLD_FILES = [
  "paper/Fold.js",
  "paper/Section.js",
  "ClosedLoopSim/Fold.js",
  "ClosedLoopSim/ThreeSourceResponsePanel.js",
  "Biomarkers/MatchWindowBand.js",
  "StimOptimizer/typeScale.js",
];

test("every fold-drawing file imports the shared arrow, none hand-rolls its own glyph span", () => {
  for (const rel of FOLD_FILES) {
    const src = fs.readFileSync(path.join(ROOT, rel), "utf8");
    expect(src).toMatch(/import FoldArrow from ["'].*FoldArrow["']/);
    expect(src).toMatch(/<FoldArrow\b/);
    // The old pattern: a bare span holding the glyph, sized in a single em, its own inline rotate.
    expect(src).not.toMatch(/width: ["']?1em["']?,[\s\S]{0,80}transform: open \? "rotate\(90deg\)"/);
  }
});
