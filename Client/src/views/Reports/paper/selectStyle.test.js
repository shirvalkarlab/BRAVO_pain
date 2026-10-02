/**
 * Every dropdown on the report pages carries the one blue-border style (the PI, 2026-10-02).
 * A source check, like the other `*.source.test.js` files: each `<Select` in the report-page files
 * below must spread `promptSelectSx` in the same tag, so a new dropdown cannot go back to the faint
 * grey outline unnoticed. The style itself is pinned: the accent blue, 1.5 px, 2 px on focus.
 */
import fs from "fs";
import path from "path";
import { T } from "assets/theme/base/tokens";
import { promptSelectSx } from "./selectStyle";

const ROOT = path.resolve(__dirname, "..");
const FILES = ["Biomarkers/MatchWindowBand.js", "Biomarkers/BandTimeSweepPanel.js", "Biomarkers/index.js",
  "ClosedLoopSim/PainScoreSelect.js", "ControlAnalyses/ControlAnalysesCard.js"];

test("the style is the accent blue at 1.5 px, 2 px when focused", () => {
  expect(promptSelectSx["& .MuiOutlinedInput-notchedOutline"]).toEqual({ borderColor: T.accent, borderWidth: "1.5px" });
  expect(promptSelectSx["&.Mui-focused .MuiOutlinedInput-notchedOutline"].borderWidth).toBe("2px");
});

test.each(FILES)("every <Select> in %s uses it", (rel) => {
  const text = fs.readFileSync(path.join(ROOT, rel), "utf8");
  const tags = text.split("<Select").slice(1).map((t) => t.slice(0, t.indexOf(">\n") === -1 ? 600 : t.indexOf(">\n") + 300));
  expect(tags.length).toBeGreaterThan(0);
  tags.forEach((t) => expect(t).toMatch(/promptSelectSx/));
});

test("the plain <select> boxes of the offline checks carry the same blue outline", () => {
  const text = fs.readFileSync(path.join(ROOT, "ControlAnalyses/figures.js"), "utf8");
  const block = text.slice(text.indexOf("const SELECT = {"), text.indexOf("};", text.indexOf("const SELECT = {")));
  expect(block).toMatch(/1\.5px solid \$\{T\.accent\}/);
});
