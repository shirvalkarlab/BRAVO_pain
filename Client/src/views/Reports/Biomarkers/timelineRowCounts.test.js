/**
 * Two row subtitles in the timeline's left gutter ran off the figure (found 2026-09-26): the
 * EVENTS row's "260 labeled · 3271 streaming" by about 11 px and, in the high / low view, the pain
 * row's "241 matched · 528 unmatched of 769 (31.3%)" by about 110 px. Wrapping them collided with
 * the rows above and below, and the PI ruled out moving them into the hover ("that should be
 * minimal"). So each says less: the EVENTS row counts only what it draws (the labeled presses; the
 * streaming snapshots are drawn on the lanes and keyed there), and the matched count reads
 * "241 of 769 matched" (the unmatched count and the percentage follow from it). Both must fit one
 * line at 13 px inside the figure for RCS08's pairs, even at four-digit counts.
 *
 * Merged here 2026-10-05: timelineGutter.test.js, timelineLegendRows.source.test.js,
 * timelinePainLabel.source.test.js, acquisitionTimeline.source.test.js. Each merged file's tests
 * sit in a describe block named after it, with its reason above it.
 */

import fs from "fs";
import path from "path";
import { eventsRowSubtitle, fitRowLabel, gutterGeometry, matchedRowSubtitle, textW } from "./timelineGutter";
import { PAIN_SCORE_OPTIONS, painScoreLabel } from "views/Reports/painScores";

const RCS08 = ["L 0⁻2⁺", "L 0⁻3⁺", "L 1⁻3⁺", "R 0⁻2⁺", "R 0⁻3⁺", "R 1⁻3⁺"];
const g = gutterGeometry(RCS08);
const fits = (s) => g.X_CONTACT - textW(s, 13, false) >= -g.MARGIN_L + g.LBL_GAP;

test("the two subtitles say only what their row shows", () => {
  expect(eventsRowSubtitle(260)).toBe("260 labeled");
  expect(matchedRowSubtitle(241, 769)).toBe("241 of 769 matched");
});

test.each([[260, 241, 769], [9999, 9999, 9999]])(
  "both fit one line at 13 px inside the figure (%i events, %i of %i matched)", (ev, used, total) => {
    expect(fits(eventsRowSubtitle(ev))).toBe(true);
    expect(fits(matchedRowSubtitle(used, total))).toBe(true);
  });

test("the old strings are gone from the timeline, which prints the helpers", () => {
  const code = fs.readFileSync(path.join(__dirname, "BiomarkerDataTimeline.js"), "utf8")
    .split("\n").filter((l) => !/^\s*(\/\/|\*|\/\*)/.test(l)).join("\n");
  expect(code).not.toMatch(/streaming`/);
  expect(code).not.toMatch(/unmatched of/);
  expect(code).toMatch(/eventsRowSubtitle\(evList\.length\)/);
  expect(code).toMatch(/matchedRowSubtitle\(su\.n_pro_used \|\| 0, su\.n_pro_total\)/);
});

/* From timelineGutter.test.js.
 * The timeline's left gutter holds with the longest pain-score label (2026-09-26). The gutter's
 * three columns (tick numbers, contact names, the rotated region tab) are laid from estimated text
 * widths (the bravo-timeline-layout rule), but the PAIN row's subtitle -- the score's display label,
 * at 14 px in the contact column -- was never in that budget. "Composite (MPQ + Left Leg VAS)",
 * 30 characters, is about 244 px wide against the 154 px the pain row has between the tick column
 * and the figure's left edge, so it ran about 78 px off the figure and was clipped.
 * The subtitle is now wrapped at word breaks to the space it has, and shrunk 1 px at a time (floor
 * 11 px, the house minimum) only if a single word still does not fit.
 */
describe("from timelineGutter", () => {
  // RCS08's six sensing pairs, as the timeline prints them
  const RCS08 = ["L 0⁻2⁺", "L 0⁻3⁺", "L 1⁻3⁺", "R 0⁻2⁺", "R 0⁻3⁺", "R 1⁻3⁺"];

  const overlap = (a, b) => a[0] < b[1] && b[0] < a[1];

  test("the three columns are disjoint and the margin is within its cap (RCS08's pairs)", () => {
    const g = gutterGeometry(RCS08);
    const tick = [g.X_TICK - g.W_tick, g.X_TICK];
    const contact = [g.X_CONTACT - g.W_contact, g.X_CONTACT];
    const region = [g.X_REGION - g.W_region / 2, g.X_REGION + g.W_region / 2];
    expect(overlap(tick, contact)).toBe(false);
    expect(overlap(contact, region)).toBe(false);
    expect(g.MARGIN_L).toBeLessThanOrEqual(g.LEFT_CAP);
    expect(region[0]).toBeGreaterThanOrEqual(-g.MARGIN_L);
    // the same numbers the skill's kernel gives for these labels
    expect([g.X_TICK, g.X_CONTACT, g.X_REGION, g.MARGIN_L]).toEqual([-12, -58, -189, 224]);
  });

  test.each(PAIN_SCORE_OPTIONS.map((o) => [o.label]))(
    "the pain row's subtitle %s stays inside the figure and clear of the tick column", (label) => {
      const g = gutterGeometry(RCS08);
      const fit = fitRowLabel(label, g, 14);
      expect(fit.fontPx).toBeGreaterThanOrEqual(11);
      expect(fit.lines.join(" ")).toBe(label);                 // nothing dropped or reordered
      fit.lines.forEach((ln) => {
        const left = g.X_CONTACT - textW(ln, fit.fontPx, false);
        expect(left).toBeGreaterThanOrEqual(-g.MARGIN_L + g.LBL_GAP);
      });
    });

  test("the longest label wraps onto two lines at 14 px; a short one is untouched", () => {
    const g = gutterGeometry(RCS08);
    expect(fitRowLabel("Composite (MPQ + Left Leg VAS)", g, 14))
      .toEqual({ lines: ["Composite (MPQ +", "Left Leg VAS)"], fontPx: 14 });
    expect(fitRowLabel("NRS (0–10)", g, 14)).toEqual({ lines: ["NRS (0–10)"], fontPx: 14 });
  });

  test("a single word too long for the space shrinks the font, never below 11 px", () => {
    const g = gutterGeometry(RCS08);
    const fit = fitRowLabel("Supercalifragilisticexpialidocious", g, 14);
    expect(fit.fontPx).toBe(11);
    expect(fit.lines).toEqual(["Supercalifragilisticexpialidocious"]);
  });
});

/* From timelineLegendRows.source.test.js.
 * The timeline's legend height is counted from the legend entries actually drawn, so the box cannot
 * rise over the title when an entry is added or a long name wraps (page review 2026-10-02: in
 * Multimodal colouring the key overlapped "Biomarker Data Timeline"). A source check, like the
 * other `*.source.test.js` files, because the figure is drawn by Plotly and has no DOM to read.
 */
describe("from timelineLegendRows.source", () => {
  const src = fs.readFileSync(path.join(__dirname, "BiomarkerDataTimeline.js"), "utf8");

  test("the legend row count comes from the key traces, with a long name counted twice", () => {
    expect(src).toMatch(/const keyNames = traces\.filter\(\(t\) => t\.showlegend !== false && t\.name\)/);
    expect(src).toMatch(/keyNames\.filter\(\(n\) => n\.length > 70\)\.length/);
    expect(src).not.toMatch(/const nLegRows = binMode \? 5 : 7;/);
  });

  test("the pain-split histogram leaves room above the plot for the high-cut label (raised at 1.13)", () => {
    const prev = fs.readFileSync(path.join(__dirname, "BinarizationPreview.js"), "utf8");
    expect(prev).toMatch(/margin: \{ l: 56, r: 16, t: 80, b: 44 \}/);
  });
});

/* From timelinePainLabel.source.test.js.
 * The timeline's pain row is labelled with the score's display label, not its key (decision 309:
 * the row read "PAIN left_leg_vas"). The label comes from the one list of pain scores
 * (`views/Reports/painScores.js`), so a score renamed there is renamed here. A source-text check,
 * the pattern `acquisitionTimeline.source.test.js` uses: rendering the timeline pulls in Plotly and
 * every panel and would prove nothing more. The label geometry is not touched.
 */
describe("from timelinePainLabel.source", () => {
  const code = fs.readFileSync(path.join(__dirname, "BiomarkerDataTimeline.js"), "utf8")
    .split("\n").filter((l) => !/^\s*(\/\/|\*|\/\*)/.test(l)).join("\n");

  describe("the timeline's pain row names its score", () => {
    test("the label and both hovers print painScoreLabel(pain.metric), never the bare key", () => {
      expect(code).toMatch(/import \{ painScoreLabel \} from "views\/Reports\/painScores"/);
      // wrapped to the gutter's width since 2026-09-26 (timelineGutter.test.js)
      expect(code).toMatch(/fitRowLabel\(pain\.metric \? painScoreLabel\(pain\.metric\) : "", GUTTER, 14\)/);
      expect(code).toMatch(/<b>PAIN<\/b><br><span[^`]*\$\{painSub\.lines\.join\("<br>"\)\}/);
      expect(code).not.toMatch(/\$\{pain\.metric \|\| ""\}/);
      expect(code).not.toMatch(/\$\{pain\.metric \|\| "pain"\}/);
      expect((code.match(/painScoreLabel\(pain\.metric\)/g) || []).length).toBe(3);
    });
    test("the key the row carries today reads as its label", () => {
      expect(painScoreLabel("left_leg_vas")).toBe("Left Leg VAS");
      expect(painScoreLabel("nrs")).toBe("NRS (0–10)");
    });
  });
});

/* From acquisitionTimeline.source.test.js.
 * The top timeline is an acquisition timeline (decision 216): nothing it draws comes from a pain
 * report. Two source-text checks, the pattern `Biomarkers.referent.test.js` uses for the page:
 * a render of the whole timeline pulls in every panel and its network calls and would prove
 * nothing these are for.
 */
describe("from acquisitionTimeline.source", () => {
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

  describe("the timeline reads only fields the acquisition-timeline endpoint sends", () => {
    // review of 2026-09-26: the endpoint sends {availability, available_metrics, message}; nothing on
    // the server writes a participant label or a region map to it, so these reads were always empty
    const code = codeOnly(read("BiomarkerDataTimeline.js"));
    test.each(["participant_label", "region_map", "av.participant"])("no read of %s", (tok) => {
      expect(code).not.toContain(tok);
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
});
