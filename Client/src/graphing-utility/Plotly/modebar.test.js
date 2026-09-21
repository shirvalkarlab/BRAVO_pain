/**
 * Every custom mode-bar button's icon names its width and height. Plotly builds the icon's SVG
 * viewBox from them; an icon without them gets viewBox "0 0 undefined NaN", and the browser logs
 * "<svg> attribute viewBox: Expected number" once per figure on every page that draws through
 * the render manager (three on the Biomarkers page). Present since 2023-09-07; found 2026-09-21.
 */
jest.mock("plotly.js-dist", () => ({ react: () => Promise.resolve(), purge: () => {}, toImage: () => Promise.resolve("") }));

import { MODEBAR_EXTRA_BUTTONS } from "./index";

describe("the render manager's extra mode-bar buttons", () => {
  it("give every drawn icon a numeric width and height", () => {
    const drawn = MODEBAR_EXTRA_BUTTONS.filter((b) => typeof b === "object" && b.icon);
    expect(drawn.map((b) => b.name)).toEqual(["Download Vector File", "Download Raw Series"]);
    for (const b of drawn) {
      expect(Number.isFinite(b.icon.width)).toBe(true);
      expect(Number.isFinite(b.icon.height)).toBe(true);
      expect(String([0, 0, b.icon.width, b.icon.height].join(" "))).not.toMatch(/NaN|undefined/);
    }
  });
});
