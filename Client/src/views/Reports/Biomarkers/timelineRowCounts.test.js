/**
 * Two row subtitles in the timeline's left gutter ran off the figure (found 2026-09-26): the
 * EVENTS row's "260 labeled · 3271 streaming" by about 11 px and, in the high / low view, the pain
 * row's "241 matched · 528 unmatched of 769 (31.3%)" by about 110 px. Wrapping them collided with
 * the rows above and below, and the PI ruled out moving them into the hover ("that should be
 * minimal"). So each says less: the EVENTS row counts only what it draws (the labeled presses; the
 * streaming snapshots are drawn on the lanes and keyed there), and the matched count reads
 * "241 of 769 matched" (the unmatched count and the percentage follow from it). Both must fit one
 * line at 13 px inside the figure for RCS08's pairs, even at four-digit counts.
 */
import fs from "fs";
import path from "path";
import { gutterGeometry, textW, eventsRowSubtitle, matchedRowSubtitle } from "./timelineGutter";

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
