// Two re-render costs on the Biomarkers page (speed-up items C3 and C4, 2026-10-01).
// C3: the composite pain preview was rebuilt as a new array on every render, so `painSeriesLive`
//     and the matched-scan model re-ran on every slider tick when the composite score was chosen.
// C4: the timeline's draw effect listed `scanModel` among its dependencies although every read of
//     it sits behind `binMode`, so each settled slider drag redrew the whole timeline in the default
//     (multimodal) view and produced the same picture.
const fs = require("fs");
const path = require("path");

const page = fs.readFileSync(path.join(__dirname, "index.js"), "utf8");
const timeline = fs.readFileSync(path.join(__dirname, "BiomarkerDataTimeline.js"), "utf8");

test("C3: the preview points are memoised on the pain scores and the metric", () => {
  expect(page).toMatch(/const previewPoints = useMemo\(\(\) => \{/);
  expect(page).toMatch(/\}, \[painScores, metric\]\);\s*\n\s*const previewMetricLabel/);
});

test("C4: the timeline redraws on a new scan model only in the high/low split view", () => {
  const deps = timeline.match(/\}, \[av, channels, height, painOverride, data, [^\]]*\]\);/);
  expect(deps).not.toBeNull();
  expect(deps[0]).not.toMatch(/[, ]scanModel[,\]]/);
  expect(deps[0]).toContain("scanModelForPlot");
  expect(timeline).toMatch(/const scanModelForPlot = binMode \? scanModel : null;/);
});
