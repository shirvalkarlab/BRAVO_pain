/**
 * Sense-to-control algorithm wiring (the PI, 2026-10-08): the three choices, what each needs, and
 * the card's clicks.
 */
import "@testing-library/jest-dom";
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { wrap } from "testUtils/render";
import { WIRINGS, sensedSides, wiringProblems, controllers } from "./wiring";
import WiringCard from "./WiringCard";

test("each wiring reads the sides it should, in the device's words", () => {
  expect(WIRINGS.map((w) => w.key)).toEqual(["independent", "left_both", "right_both"]);
  expect(sensedSides("independent")).toEqual(["Left", "Right"]);
  expect(sensedSides("left_both")).toEqual(["Left"]);
  expect(sensedSides("right_both")).toEqual(["Right"]);
  expect(WIRINGS[1].medtronic).toBe("Left: ipsilateral sensing. Right: contralateral sensing (from Left).");
});

test("a line only when a sensed side has no band", () => {
  expect(wiringProblems("left_both", ["Left"])).toEqual([]);
  expect(wiringProblems("right_both", ["Left"]))
    .toEqual(["No band chosen on the right: choose one in Band selection"]);
  expect(wiringProblems("independent", ["Left"]))
    .toEqual(["No band chosen on the right: choose one in Band selection"]);
  expect(wiringProblems("independent", ["Left", "Right"])).toEqual([]);
});

function Harness({ bandSides }) {
  const [v, setV] = React.useState(null);
  return <WiringCard value={v} onChange={setV} bandSides={bandSides} />;
}

test("clicking a choice selects it and says it in the device's words", () => {
  render(wrap(<Harness bandSides={["Left"]} />));
  expect(screen.getByText("Not chosen: the decision below checks the band's own side only")).toBeInTheDocument();
  expect(screen.queryAllByTestId("wiring-problem")).toHaveLength(0);
  fireEvent.click(screen.getByTestId("wiring-left_both"));
  expect(screen.getByTestId("wiring-left_both")).toHaveAttribute("aria-checked", "true");
  expect(screen.getByText(WIRINGS[1].medtronic)).toBeInTheDocument();
  expect(screen.queryAllByTestId("wiring-problem")).toHaveLength(0);
  fireEvent.click(screen.getByTestId("wiring-independent"));
  expect(screen.getAllByTestId("wiring-problem")).toHaveLength(1);
});

test("the stimulators the decision answers for, from the wiring and the band's side", () => {
  expect(controllers(null, "Left")).toEqual([{ stim: "Left", source: "Left", kind: "own" }]);
  expect(controllers("left_both", "Left")).toEqual([
    { stim: "Left", source: "Left", kind: "own" }, { stim: "Right", source: "Left", kind: "contralateral" }]);
  expect(controllers("independent", "Left")).toEqual([
    { stim: "Left", source: "Left", kind: "own" }, { stim: "Right", source: "Right", kind: "no_band" }]);
  expect(controllers("right_both", "Left").map((c) => c.kind)).toEqual(["no_band", "no_band"]);
});

test("the three choices sit in one row, not stacked (the PI, 2026-10-08)", () => {
  const src = require("fs").readFileSync(require("path").join(__dirname, "WiringCard.js"), "utf8");
  expect(src).toMatch(/flexWrap: "nowrap"/);
  expect(src).not.toMatch(/gridTemplateColumns/);
});
