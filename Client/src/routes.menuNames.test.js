/**
 * The menu names "Choosing stimulation settings" ONCE: the group that holds the three pain pages.
 * The 2026-09-26 redesign mapped "Customized Analysis / Analysis Builder" to that name, and it
 * landed on both the group and the platform's own Analysis Builder page (/analysis-builder), so
 * the menu showed it twice (the PI, 2026-10-01: "duplicated, fix this"). The page keeps its own
 * name, "Analysis builder". Read from source: importing routes.js would load every page.
 */
const fs = require("fs");
const path = require("path");

const routes = fs.readFileSync(path.join(__dirname, "routes.js"), "utf8");
const translation = fs.readFileSync(path.join(__dirname, "assets", "translation.js"), "utf8");

it("names the stimulation-settings group once and the Analysis Builder page by its own name", () => {
  const block = routes.slice(routes.indexOf('key: "AnalysisBuilder"') - 10, routes.indexOf('key: "AnalysisBuilder"') + 120);
  expect(block).toContain('name: "Analysis builder"');
  const sidebarNames = routes.match(/name: "Choosing stimulation settings"/g) || [];
  // the group's own name and its hidden title row, never a page
  expect(sidebarNames.length).toBe(2);
  // the breadcrumb for /analysis-builder reads `analysis`
  const analysis = translation.slice(translation.indexOf("    analysis: {"), translation.indexOf("    analysis: {") + 80);
  expect(analysis).toContain('en: "Analysis builder"');
});
