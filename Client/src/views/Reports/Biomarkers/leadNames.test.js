/** Lead labels must come from stored metadata, never inferred from a study code. */
import fs from "fs";
import path from "path";
import { regionForSide } from "./BiomarkerTimeline";

jest.mock("plotly.js-dist", () => ({ react: jest.fn(), purge: jest.fn(), newPlot: jest.fn() }));

test("each side's label is the stored lead name, and empty when none is sent", () => {
  const rp = [{ raw: "ZERO_THREE_LEFT", region: "Left STN" }, { raw: "ZERO_THREE_RIGHT", region: "Right GPi" }];
  expect(regionForSide(rp, "Left")).toBe("Left STN");
  expect(regionForSide(rp, "RIGHT")).toBe("Right GPi");
  expect(regionForSide([], "Left")).toBe("");
});

test("no brain region is written into the old timeline's code", () => {
  const code = fs.readFileSync(path.join(__dirname, "BiomarkerTimeline.js"), "utf8");
  expect(code).not.toMatch(/region: "(GPi|VIM)"/);
});
