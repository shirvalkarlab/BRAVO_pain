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

test("with a band on each side, each stimulator is checked with the band of the side driving it", () => {
  expect(controllers("independent", ["Left", "Right"], "Right")).toEqual([
    { stim: "Left", source: "Left", kind: "own" }, { stim: "Right", source: "Right", kind: "own" }]);
  // the page's band is on the left, but the wiring reads the right: both from the right band
  expect(controllers("right_both", ["Left", "Right"], "Left")).toEqual([
    { stim: "Left", source: "Right", kind: "contralateral" }, { stim: "Right", source: "Right", kind: "own" }]);
  // no wiring: the page's band on its own side, whatever else is chosen
  expect(controllers(null, ["Left", "Right"], "Right")).toEqual([{ stim: "Right", source: "Right", kind: "own" }]);
  expect(controllers(null, [], null)).toEqual([]);
});

test("the three choices sit in one row, not stacked (the PI, 2026-10-08)", () => {
  const src = require("fs").readFileSync(require("path").join(__dirname, "WiringCard.js"), "utf8");
  expect(src).toMatch(/flexWrap: "nowrap"/);
  expect(src).not.toMatch(/gridTemplateColumns/);
});

/* The simulated comparison on the card (decision 472). */
const COMPARISON = {
  available: true,
  record: { hours_both_sides: 4.83, n_ratings_high: 44, n_ratings_low: 68, n_days: 12, n_ratings_in_opening: 19,
    opening_s: 60 },
  pain_split: { why: "the pain scores were split into thirds" }, rating_tol_s: 60,
  response_per_mA: { "Left<Left": { slope_per_mA: -5.68, source: "stored pooled line" } },
  wirings: {
    independent: { scored: true, score: 0.356, score_interval: [0.097, 0.543], auc: { Left: 0.386, Right: 0.326 },
      switches_per_hour: 2.0, share_at_highest: { Left: 0.18, Right: 0.27 }, mean_current_mA: { Left: 3.1, Right: 3.2 },
      device_allows: false },
    left_both: { scored: true, score: 0.256, score_interval: [0.146, 0.418], auc: { Left: 0.27, Right: 0.24 },
      device_allows: false },
    right_both: { scored: true, score: 0.37, score_interval: [0.08, 0.57], auc: { Left: 0.41, Right: 0.33 },
      device_allows: true },
  },
};

test("no band on one side: the comparison asks for one", () => {
  render(wrap(<WiringCard value={null} onChange={() => {}} bandSides={["Left"]} comparison={null} />));
  expect(screen.getByTestId("wiring-comparison"))
    .toHaveTextContent("Choose a band on each side to compare the three wirings by simulation.");
});

test("none recommended: no button is marked, the reason is said, the numbers are folded shut", () => {
  const data = { ...COMPARISON, recommendation: { wiring: null, basis: "none_follows_pain",
    reason: "in none of the three wirings did the simulated current rise with pain" } };
  render(wrap(<WiringCard value={null} onChange={() => {}} bandSides={["Left", "Right"]}
    comparison={{ data, loading: false, err: null }} />));
  expect(screen.queryByTestId("wiring-recommended")).toBeNull();
  expect(screen.getByTestId("wiring-recommendation")).toHaveTextContent(
    "Simulation recommends none: in none of the three wirings did the simulated current rise with pain.");
  expect(screen.getByText(/Replay of 4.8 h recorded on both sides; 112 pain ratings/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Simulated comparison, every number/ }))
    .toHaveAttribute("aria-expanded", "false");
  expect(screen.getByTestId("wiring-row-right_both")).toHaveTextContent("0.37 (0.08–0.57)");
});

test("a recommendation marks its button", () => {
  const data = { ...COMPARISON, recommendation: { wiring: "right_both", basis: "clearly_best", reason: "x." } };
  render(wrap(<WiringCard value={null} onChange={() => {}} bandSides={["Left", "Right"]}
    comparison={{ data, loading: false, err: null }} />));
  expect(screen.getByTestId("wiring-right_both")).toContainElement(screen.getByTestId("wiring-recommended"));
  expect(screen.getAllByTestId("wiring-recommended")).toHaveLength(1);
});
