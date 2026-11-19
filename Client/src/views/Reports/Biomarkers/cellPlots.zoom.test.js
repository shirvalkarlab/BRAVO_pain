/**
 * The heat-map cell's scatter and violin plots zoom by dragging and reset on double-click, with no
 * toolbar (the PI, 2026-10-03). Read at the source because the two plots draw through
 * `PlotlyRenderManager`; the heat maps themselves keep double-click off (a click there pins a cell).
 */
const fs = require("fs");
const path = require("path");

const src = fs.readFileSync(path.join(__dirname, "BiomarkerHeatmapGrids.js"), "utf8");
const calls = src.match(/Plotly\.react\(divId, fig\.traces, fig\.layout, \{[^}]*\}\);/g) || [];

test("the violin and scatter plots reset on double-click, with no toolbar; the heat maps keep it off", () => {
  expect(calls.length).toBe(3);
  const [heatmap, violin, scatter] = calls;
  expect(heatmap).toMatch(/doubleClick: false/);
  [violin, scatter].forEach((c) => {
    expect(c).toMatch(/\.\.\.PLOTLY_CONFIG, doubleClick: "reset\+autosize"/);
    expect(c).not.toMatch(/WITH_TOOLBAR|displayModeBar: (true|"hover")/);
  });
});
