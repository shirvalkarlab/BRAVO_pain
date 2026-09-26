/**
 * The timeline's pain row is labelled with the score's display label, not its key (decision 309:
 * the row read "PAIN left_leg_vas"). The label comes from the one list of pain scores
 * (`views/Reports/painScores.js`), so a score renamed there is renamed here. A source-text check,
 * the pattern `acquisitionTimeline.source.test.js` uses: rendering the timeline pulls in Plotly and
 * every panel and would prove nothing more. The label geometry is not touched.
 */
import fs from "fs";
import path from "path";
import { painScoreLabel } from "views/Reports/painScores";

const code = fs.readFileSync(path.join(__dirname, "BiomarkerDataTimeline.js"), "utf8")
  .split("\n").filter((l) => !/^\s*(\/\/|\*|\/\*)/.test(l)).join("\n");

describe("the timeline's pain row names its score", () => {
  test("the label and both hovers print painScoreLabel(pain.metric), never the bare key", () => {
    expect(code).toMatch(/import \{ painScoreLabel \} from "views\/Reports\/painScores"/);
    expect(code).toMatch(/<b>PAIN<\/b><br><span[^`]*\$\{pain\.metric \? painScoreLabel\(pain\.metric\) : ""\}/);
    expect(code).not.toMatch(/\$\{pain\.metric \|\| ""\}/);
    expect(code).not.toMatch(/\$\{pain\.metric \|\| "pain"\}/);
    expect((code.match(/painScoreLabel\(pain\.metric\)/g) || []).length).toBe(3);
  });
  test("the key the row carries today reads as its label", () => {
    expect(painScoreLabel("left_leg_vas")).toBe("Left Leg VAS");
    expect(painScoreLabel("nrs")).toBe("NRS (0–10)");
  });
});
