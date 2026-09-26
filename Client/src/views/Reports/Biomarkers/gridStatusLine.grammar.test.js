/**
 * The heat maps' status line agrees in number: "1 band rises", "2 bands rise" (seen live
 * 2026-09-26 as "1 band rise with pain").
 */
jest.mock("plotly.js-dist", () => ({ react: () => Promise.resolve(), purge: () => {}, restyle: () => {},
  relayout: () => {}, newPlot: () => {}, Plots: { resize: () => {} } }));
jest.mock("graphing-utility/Plotly", () => ({ PlotlyRenderManager: class {} }));
import { gridStatusLine } from "./BiomarkerHeatmapGrids";

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
