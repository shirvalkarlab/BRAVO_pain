/**
 * The timeline's left gutter holds with the longest pain-score label (2026-09-26). The gutter's
 * three columns (tick numbers, contact names, the rotated region tab) are laid from estimated text
 * widths (the bravo-timeline-layout rule), but the PAIN row's subtitle -- the score's display label,
 * at 14 px in the contact column -- was never in that budget. "Composite (MPQ + Left Leg VAS)",
 * 30 characters, is about 244 px wide against the 154 px the pain row has between the tick column
 * and the figure's left edge, so it ran about 78 px off the figure and was clipped.
 * The subtitle is now wrapped at word breaks to the space it has, and shrunk 1 px at a time (floor
 * 11 px, the house minimum) only if a single word still does not fit.
 */
import { gutterGeometry, fitRowLabel, textW } from "./timelineGutter";
import { PAIN_SCORE_OPTIONS } from "views/Reports/painScores";

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

