/**
 * The top timeline is an acquisition timeline (decision 216): nothing it draws comes from a pain
 * report. Two source-text checks, the pattern `Biomarkers.referent.test.js` uses for the page:
 * a render of the whole timeline pulls in every panel and its network calls and would prove
 * nothing these are for.
 */
import fs from "fs";
import path from "path";

const read = (f) => fs.readFileSync(path.join(__dirname, f), "utf8");
const codeOnly = (src) => src.split("\n").filter((l) => !/^\s*(\/\/|\*|\/\*)/.test(l)).join("\n");

describe("the timeline component draws no per-report matched values", () => {
  const code = codeOnly(read("BiomarkerDataTimeline.js"));
  test.each(["pro_lsb", "proLsbFor", "per-rating modeled LSB"])("no %s in the code", (tok) => {
    expect(code).not.toContain(tok);
  });
  test("the axis span is widened by the live pain series, so reports newer than the last recording are not clipped", () => {
    // the served span ends at the last recording (nothing pain-derived is in the payload); the pain
    // row comes from /api/queryPainScores and can run past it
    expect(code).toMatch(/painT\.length \? Math\.max\(t1Served, \.\.\.painT\) : t1Served/);
  });
  test("the header names the endpoints it consumes", () => {
    const src = read("BiomarkerDataTimeline.js");
    expect(src).toMatch(/queryDataAvailability/);
    expect(src).not.toMatch(/Consumes `data.availability` from QueryBiomarkerAnalysis/);
  });
});

describe("the page asks the timeline endpoint for no matching window and fetches the sample index on its own", () => {
  const code = codeOnly(read("index.js"));
  test("the timeline fetch carries only the participant", () => {
    const m = code.match(/SessionController\.query\("\/api\/queryDataAvailability",\s*\{([^}]*)\}/);
    expect(m).not.toBeNull();
    expect(m[1]).toMatch(/ParticipantId/);
    expect(m[1]).not.toMatch(/MatchToleranceMin/);
  });
  test("the sample index has its own fetch", () => {
    expect(code).toMatch(/\/api\/queryPsdScanIndex/);
  });
  test("the paragraph about the timeline's own 120 s window is gone", () => {
    expect(read("index.js")).not.toMatch(/Timeline's own match window/);
  });
});
