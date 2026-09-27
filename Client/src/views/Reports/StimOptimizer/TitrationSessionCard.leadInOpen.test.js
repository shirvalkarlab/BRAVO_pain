/**
 * The next-visit section starts closed (the PI, 2026-09-26), and two safety lines must stay in view
 * while it is: decision 308's "Held at the ceiling" instruction for a held side whose current in
 * force is above its safe ceiling, and the home schedule's line for a setting in force above the
 * ceiling. Both are in the section's always-visible lead, outside its hidden body, and printed
 * once. Neither appears when nothing is above a ceiling (RCS08 today).
 */
import "@testing-library/jest-dom";
import { render as rtlRender, screen } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";
import theme from "assets/theme";
import { PlatformContextProvider } from "context";
import TitrationSessionCard from "./TitrationSessionCard";
import plan from "./__fixtures__/rcs08_titration_plan_exploratory.json";
import response from "./__fixtures__/rcs08_stim_optimizer_2026-09-25.json";

jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn(() => Promise.resolve({ data: {} })) } }));

const wrap = (ui) => (
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>
);
const UID = "2e3c75c00d7f4f37b53a048d195f11da";
const NOTE = "the Right side's current in force, 4.8 mA, is above today's safe ceiling for that side, "
  + "4.5 mA; it is held at 4.5 mA for this ladder, not at the current in force -- set it to 4.5 mA before the first step";
const ABOVE = {
  amp_left_mA: 3.0, amp_right_mA: 4.8, above_ceiling: true, sides_above_ceiling: ["Right"],
  offered_as_target: false, label: "in force, above today's ceiling",
  why: "history: the setting in force today is above the safe ceiling on the Right side (4.8 mA against 4.5 mA), "
    + "so it is shown for reference and never offered as a step to hold",
};

function heldAbove(p) {
  const left = p.sides.Left;
  return { ...p, sides: { ...p.sides, Left: { ...left, held_other_side: { ...left.held_other_side,
    current_mA: 4.5, in_force_mA: 4.8, ceiling_mA: 4.5, above_ceiling: true, note: NOTE } } } };
}

const visible = (el) => el.closest("[hidden]") === null;

describe("the next-visit section keeps its safety lines in view while closed", () => {
  it("shows the held-at-the-ceiling instruction outside the hidden body, once", () => {
    rtlRender(wrap(<TitrationSessionCard plan={heldAbove(plan)} participantUid={UID} />));
    const hits = screen.getAllByText(/Held at the ceiling: the Right side's current in force, 4\.8 mA/);
    expect(hits.length).toBe(1);
    expect(visible(hits[0])).toBe(true);
    expect(hits[0].textContent).toContain("set it to 4.5 mA before the first step");
  });

  it("shows the home schedule's in-force-above-ceiling line outside the hidden body, once", () => {
    const schedule = { ...response.current_map_schedule, in_force: ABOVE };
    rtlRender(wrap(<TitrationSessionCard plan={plan} participantUid={UID} homeSchedule={schedule} />));
    const hits = screen.getAllByText(/In force, above today's ceiling: 3\.0 mA left \/ 4\.8 mA right/);
    expect(hits.length).toBe(1);
    expect(visible(hits[0])).toBe(true);
  });

  it("adds nothing to the lead when nothing is above a ceiling", () => {
    const schedule = { ...response.current_map_schedule };
    const { container } = rtlRender(wrap(<TitrationSessionCard plan={plan} participantUid={UID} homeSchedule={schedule} />));
    expect(container.querySelector('[data-testid="next-visit-safety-lead"]')).toBeNull();
    expect(container.textContent).not.toMatch(/Held at the ceiling|above today's ceiling/);
  });
});
