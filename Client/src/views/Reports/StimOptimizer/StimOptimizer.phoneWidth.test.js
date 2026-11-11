/**
 * The Stim Optimizer page fits a phone screen (SPEC.md section 2.5): the page never scrolls
 * sideways; a table wider than its card scrolls inside its own wrapper instead.
 *
 * Measured in a real browser at a 390 px window (the screenshot harness): the page was 634 px wide
 * before this change and 390 px after. jsdom has no layout, so this file pins the structure that
 * makes that true: every wide table sits inside a wrapper marked `data-scroll-x` whose style scrolls
 * sideways and never grows past its card, and the side-by-side layouts can shrink and stack.
 */
import "@testing-library/jest-dom";
import fs from "fs";
import path from "path";
import { render as rtlRender } from "@testing-library/react";

import newResponse from "./__fixtures__/rcs08_stim_optimizer_2026-09-25.json";
import DecisionStrip from "./DecisionStrip";
import SensingEvidenceTable from "./SensingEvidenceTable";
import { wrap } from "testUtils/render";

const render = (ui) => rtlRender(wrap(ui));
const src = (f) => fs.readFileSync(path.join(__dirname, f), "utf8");

const WRAPPED = ["DecisionStrip.js", "CurrentMapCard.js", "CurrentMapScheduleCard.js",
  "SensingEvidenceTable.js", "TitrationSessionCard.js", "TwoStagePlanCard.js"];

describe("wide tables scroll inside their own card, never the page", () => {
  it("every wide-table wrapper scrolls sideways and is capped at its card's width", () => {
    WRAPPED.forEach((f) => {
      const wrappers = src(f).match(/data-scroll-x=""[^\n]*/g) || [];
      expect(wrappers.length).toBeGreaterThan(0);
      wrappers.forEach((w) => {
        expect(w).toMatch(/overflowX: "auto"/);
        expect(w).toMatch(/maxWidth: "100%"/);
      });
    });
  });

  it("the readiness rows sit inside a sideways-scrolling wrapper", () => {
    const { container } = render(<SensingEvidenceTable closedLoop={newResponse.closed_loop} />);
    const rows = container.querySelectorAll('[data-testid="readiness-row"]');
    expect(rows.length).toBeGreaterThan(0);
    rows.forEach((r) => expect(r.closest("[data-scroll-x]")).not.toBeNull());
  });

  it("side-by-side layouts can shrink below their content and stack on a phone", () => {
    // A bare "1fr" column is minmax(auto, 1fr): it never shrinks below its widest word, which is
    // what pushed the next-visit card's two sides to 520 px on a 390 px screen.
    const titration = src("TitrationSessionCard.js");
    expect(titration).not.toMatch(/gridTemplateColumns: \{ xs: "1fr"/);
    expect(titration).toMatch(/xs: "minmax\(0, 1fr\)", md: "repeat\(2, minmax\(0, 1fr\)\)"/);
    ["ClosedLoopChecks.js", "TwoStagePlanCard.js"].forEach((f) => {
      expect(src(f)).not.toMatch(/gridTemplateColumns: "minmax\(260px, 1fr\) minmax\(300px, 1\.5fr\)"/);
      expect(src(f)).toMatch(/xs: "minmax\(0, 1fr\)", sm: "minmax\(0, 1fr\) minmax\(0, 1\.5fr\)"/);
    });
  });
});
