/**
 * Each reading against its OWN shuffled-data range (decision 314, following 276 and 310). The
 * reading with the current taken out has its own null -- the rotations refitted with the current
 * taken out -- and the figures drew only the plain reading's 95th percentile beside it, so a dot
 * inside its own range could look outside it, or the reverse. Each reading's bar now sits at its own
 * dot, in its colour, at its own 95th percentile; the current alone has none and gets none.
 */
import React from "react";
import { render } from "@testing-library/react";

import { CurrentExplainsFigure, BandDetectorResearchFigure } from "./figures";
import { resetPlots, plotsIn } from "./plotTestUtils";

jest.mock("plotly.js-dist", () => require("./plotTestUtils").plotlyMock());
beforeEach(() => resetPlots());

// The short bar beside a dot is a trace named "null:<reading>"; its x is that reading's own level.
const bars = (container) => Object.fromEntries(
  plotsIn(container)[0].data.filter((t) => t.name.startsWith("null:")).map((t) => [t.name.slice(5), t]),
);
const dots = (container) => Object.fromEntries(
  plotsIn(container)[0].data.filter((t) => !t.name.startsWith("null:")).map((t) => [t.name, t]),
);

describe("each reading is drawn against its own shuffled-data 95th percentile", () => {
  it("What the current explains: every band against its null, the current taken out against its own", () => {
    const result = { rows: [{ pair: "ONE_THREE_LEFT", seconds: 60, n: 187, current_alone: 0.483, bands: 0.589,
      bands_without_current: 0.56, null_p50: 0.5, null_p95: 0.673, p: 0.189,
      bands_without_current_null_p50: 0.5, bands_without_current_null_p95: 0.61, bands_without_current_p: 0.184 }] };
    const { container } = render(<CurrentExplainsFigure result={result} />);
    const b = bars(container);
    expect(Object.keys(b).sort()).toEqual(["bands", "bands_without_current"]);
    expect(b.bands.x).toEqual([0.673]);
    expect(b.bands_without_current.x).toEqual([0.61]);
    // each bar sits on its own dot's row and in its dot's colour
    const d = dots(container);
    ["bands", "bands_without_current"].forEach((k) => {
      expect(b[k].y).toEqual(d[k].y);
      expect(b[k].marker.color).toBe(d[k].marker.line.color);
    });
    expect(container.textContent).toMatch(/its own shuffled data/);
  });

  it("an older saved row with no null of its own for the adjusted reading draws no bar for it", () => {
    const result = { rows: [{ pair: "ONE_THREE_LEFT", seconds: 60, n: 187, current_alone: 0.7, bands: 0.74,
      bands_without_current: 0.68, null_p50: 0.52, null_p95: 0.673, p: 0.04 }] };
    const { container } = render(<CurrentExplainsFigure result={result} />);
    expect(Object.keys(bars(container))).toEqual(["bands"]);
  });

  it("the research band detector: the current-taken-out reading against its own rotations", () => {
    const rb = (rho, p95) => ({ rho, lo: rho - 0.1, hi: rho + 0.1, p: 0.2, q: 0.3, null_p50: 0, null_p95: p95 });
    const result = { modes: { off: { rows: [{ pair: "ONE_THREE_LEFT", seconds: 60,
      reading: { n: 187, current_alone: { rho: 0.01, lo: -0.1, hi: 0.1 }, bands: rb(0.24, 0.18),
        bands_without_current: rb(0.25, 0.16) } }] } } };
    const { container } = render(<BandDetectorResearchFigure result={result} clinicSheets={false} />);
    const b = bars(container);
    expect(Object.keys(b).sort()).toEqual(["bands", "bands_without_current"]);
    expect(b.bands.x).toEqual([0.18]);
    expect(b.bands_without_current.x).toEqual([0.16]);
    expect(b.bands_without_current.marker.color).not.toBe(b.bands.marker.color);
    expect(container.textContent).toMatch(/its own rotated ratings/);
  });
});
