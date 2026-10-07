/**
 * Lead names come from the participant's stored lead names, never from the page code (decision 467:
 * RCS08's leads are Left GPe and Right MD Thal; the old timeline had "GPi" / "VIM" written in).
 */
import fs from "fs";
import path from "path";
import { regionForSide } from "./BiomarkerTimeline";

jest.mock("plotly.js-dist", () => ({ react: jest.fn(), purge: jest.fn(), newPlot: jest.fn() }));

test("each side's label is the stored lead name, and empty when none is sent", () => {
  const rp = [{ raw: "ZERO_THREE_LEFT", region: "Left GPe" }, { raw: "ZERO_THREE_RIGHT", region: "Right MD Thal" }];
  expect(regionForSide(rp, "Left")).toBe("Left GPe");
  expect(regionForSide(rp, "RIGHT")).toBe("Right MD Thal");
  expect(regionForSide([], "Left")).toBe("");
});

test("no brain region is written into the old timeline's code", () => {
  const code = fs.readFileSync(path.join(__dirname, "BiomarkerTimeline.js"), "utf8");
  expect(code).not.toMatch(/region: "(GPi|VIM)"/);
});
