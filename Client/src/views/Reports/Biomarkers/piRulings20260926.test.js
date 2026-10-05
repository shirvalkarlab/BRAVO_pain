/**
 * The PI's requests of 2026-09-26 for the Biomarkers page, pinned:
 *  - one large "Adjust matching parameters" button, closed by default, opening one compact panel
 *    with every matching control, the extra options and the high / low split's own controls;
 *  - the two heat maps and the clicked square's scatter and violin share rows, so the two columns
 *    start at the same height; the right map's title is "High vs Low Pain Logistic classification";
 *  - "R" for the correlation, no "for this square alone", every p and q at most two decimals, and
 *    the heat maps' hover text smaller than the figure text.
 */
import fs from "fs";
import path from "path";
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";

import "@testing-library/jest-dom";
import MatchWindowBand from "./MatchWindowBand";
import { fmtP, hoverReadout } from "./gridReadouts";
import { wrap } from "testUtils/render";

jest.mock("plotly.js-dist", () => {
  const noop = () => {};
  return { react: () => Promise.resolve(), purge: noop, restyle: noop, relayout: noop, newPlot: noop };
});

const read = (f) => fs.readFileSync(path.join(__dirname, f), "utf8");

describe("the matching panel", () => {
  const props = {
    coverage: null, metricLabel: "NRS", matchTolerance: 5, setMatchTolerance: () => {},
    strategy: "median", setStrategy: () => {}, strategyOptions: [{ key: "median", label: "Median" }],
    percentileLow: 33, percentileHigh: 67, matchDirection: "pro_first", setMatchDirection: () => {},
    scanIndex: null, painSeries: null,
  };

  test("one large button, closed by default, opens every control and the split controls", () => {
    const { container } = render(wrap(
      <MatchWindowBand {...props} moreOptions={<span>cap-and-gap</span>}
        binarization={<span>split-preview</span>} />));
    const btn = screen.getByRole("button", { name: /Adjust matching parameters/ });
    expect(btn.getAttribute("aria-expanded")).toBe("false");
    const panel = container.querySelector('[data-testid="matching-panel"]');
    expect(panel.hidden).toBe(true);
    ["Match window", "Split into high and low pain", "Match direction", "cap-and-gap", "split-preview"]
      .forEach((t) => expect(panel.textContent).toContain(t));
    fireEvent.click(btn);
    expect(btn.getAttribute("aria-expanded")).toBe("true");
    expect(panel.hidden).toBe(false);
  });

  test("no small fold rows are left for the matching settings", () => {
    const src = read("MatchWindowBand.js");
    expect(src).not.toMatch(/<Fold\b/);
    expect(src).not.toMatch(/More options/);
  });

  test("the page hands the high / low split's controls to the panel", () => {
    expect(read("index.js")).toMatch(/binarization=\{\(\s*<BinarizationPreview/);
  });
});

describe("the heat maps", () => {
  const src = read("BiomarkerHeatmapGrids.js");

  test("the right map's title fits one line, the left one says R", () => {
    expect(src).toContain('{"High vs. low pain classification"}');
    expect(src).toContain('{"R with pain"}');
  });

  test("titles, keys, maps, statistics and plots share rows across the two columns", () => {
    expect(src).toMatch(/md: `"t1 t2" "k1 k2" "m1 m2" "pt pt" "s1 s2" "g1 g2" "cap cap"`/);
    expect(src).toMatch(/<ViolinPanel part="stats"/);
    expect(src).toMatch(/<ViolinPanel part="plot"/);
  });

  test("the hover is set smaller than the figure text", () => {
    expect(src).toMatch(/HEATMAP_HOVERLABEL = \{ \.\.\.PLOTLY_LAYOUT\.hoverlabel,\s*font: \{ \.\.\.PLOTLY_LAYOUT\.hoverlabel\.font, size: 11 \}/);
    expect(src).toMatch(/hoverlabel: HEATMAP_HOVERLABEL/);
  });
});

describe("words and numbers", () => {
  test("no 'for this square alone', and no 'correlation' printed on the heat maps", () => {
    const printed = (s) => (s.match(/"[^"\n]*"|`[^`\n]*`/g) || []).join("\n");
    ["BiomarkerHeatmapGrids.js", "gridReadouts.js"].forEach((f) => {
      expect(printed(read(f))).not.toMatch(/for this square alone/);
    });
    expect(read("BiomarkerHeatmapGrids.js")).not.toMatch(/"correlation"\} %\{z/);
  });

  test("p and q print at most two decimals, never as zero", () => {
    expect(fmtP(0.0512)).toBe("0.05");
    expect(fmtP(0.0022)).toBe("< 0.01");
    expect(fmtP(0.7)).toBe("0.70");
    const sw = { center_freqs_hz: [10.5], integration_seconds_delivered: [30],
      p_grid: [[0.01234]], n_grid: [[40]], best_correlation_rows: [] };
    expect(hoverReadout(sw, "corr", 0, 0)).toBe("40 ratings · p 0.01");
  });
});

test("a small p reads 'p < 0.01', never 'p = < 0.01'", () => {
  const { pEquals } = require("./gridReadouts");
  expect(pEquals(0.001)).toBe("p < 0.01");
  expect(pEquals(0.031)).toBe("p = 0.03");
  expect(read("BiomarkerHeatmapGrids.js")).not.toMatch(/p = \$\{fmtP\(/);
});
