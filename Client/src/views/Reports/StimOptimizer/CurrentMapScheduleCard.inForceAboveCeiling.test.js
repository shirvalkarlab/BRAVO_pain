/** Synthetic display-contract regression tests.
 * Independently authored examples; no participant responses or live scientific validation.
 */
import "@testing-library/jest-dom";
import { render, screen, fireEvent } from "@testing-library/react";
import { HomeScheduleSection } from "./CurrentMapScheduleCard";
import response from "./__fixtures__/synthetic_optimizer_cautions.json";
import { wrap } from "testUtils/render";

const ABOVE = {
  amp_left_mA: 3.0, amp_right_mA: 4.8, above_ceiling: true, sides_above_ceiling: ["Right"],
  offered_as_target: false, label: "in force, above today's ceiling",
  why: "history: the setting in force today is above the safe ceiling on the Right side (4.8 mA against 4.5 mA), "
    + "so it is shown for reference and never offered as a step to hold; the schedule has no baseline step to repeat",
};

test("a setting in force above the ceiling is printed in the open, labelled as history", () => {
  const schedule = { ...response.current_map_schedule, in_force: ABOVE };
  render(wrap(<HomeScheduleSection schedule={schedule} />));
  const line = screen.getByTestId("home-schedule-in-force");
  expect(line).toHaveTextContent("In force, above today's ceiling: 3.0 mA left / 4.8 mA right");
  expect(line).toHaveTextContent("never offered as a step to hold");
});

test("in the table it is a row with no step number and no safe mark", () => {
  const schedule = { ...response.current_map_schedule, in_force: ABOVE };
  render(wrap(<HomeScheduleSection schedule={schedule} />));
  fireEvent.click(screen.getByText(/Show the schedule/));
  const row = screen.getByTestId("home-schedule-in-force-row");
  expect(row).toHaveTextContent("history");
  expect(row).toHaveTextContent("4.8 mA");
  expect(row).not.toHaveTextContent("✓");
  // the numbered steps are the server's steps, none of them the in-force pair
  const n = response.current_map_schedule.steps.length;
  expect(screen.getAllByRole("row").length).toBe(n + 2);   // header + in-force row + steps
});

test("a setting in force under the ceiling adds nothing new", () => {
  const schedule = {
    ...response.current_map_schedule,
    in_force: { ...ABOVE, amp_right_mA: 2.5, above_ceiling: false, sides_above_ceiling: [],
      offered_as_target: true, label: "in force" },
  };
  render(wrap(<HomeScheduleSection schedule={schedule} />));
  expect(screen.queryByTestId("home-schedule-in-force")).toBeNull();
  expect(screen.queryByText(/above today's ceiling/)).toBeNull();
});
