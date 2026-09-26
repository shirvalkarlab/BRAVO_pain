/**
 * The closed-loop card's folded table of fits prints a "best left / right current" per pulse-width
 * pairing, read from ONE fit pooled across every stimulation rate (on RCS08, 1.5 / 1.0 mA at
 * 55 Hz, 60/160 µs). Decision 253's block-of-time check is not run on that fit, because a stretch
 * of time held out of it is also a set of rates held out, and a miss could not be told apart from a
 * rate the fit had not learnt (the PI, 2026-09-25: "deal with the Q4 edge cases"). So the table
 * says, in plain words, that those currents are not checked and why, and carries no dagger; the
 * current the page recommends is read from each rate's own map, which is checked.
 */
import "@testing-library/jest-dom";
import { render as rtlRender } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";

import theme from "assets/theme";
import { PlatformContextProvider } from "context";

import TwoStagePlanCard, { ACROSS_RATES_NOT_CHECKED } from "./TwoStagePlanCard";
import response from "./__fixtures__/rcs08_stim_optimizer_two_stage.json";

const wrap = (ui) => (
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>
);

describe("the table of fits pooled across rates", () => {
  it("says its best currents are not checked for movement between blocks of time, and why", () => {
    const { container } = rtlRender(wrap(<TwoStagePlanCard plan={response.two_stage} loading={false} err={null} />));
    const t = container.textContent;
    expect(t).toContain("The fit for each pulse width and side");
    expect(t).toContain("best left current (mA)");
    expect(ACROSS_RATES_NOT_CHECKED).toMatch(/not checked for movement between blocks of time/);
    expect(ACROSS_RATES_NOT_CHECKED).toMatch(/pooled across every stimulation rate/);
    expect(ACROSS_RATES_NOT_CHECKED).toMatch(/rate the fit had not learnt/);
    expect(ACROSS_RATES_NOT_CHECKED).toMatch(/each rate's own map/);
    expect(t).toContain(ACROSS_RATES_NOT_CHECKED);
    expect(container.querySelectorAll('[data-testid="block-of-time-mark"]')).toHaveLength(0);
  });

  it("prints the sentence only where the table is drawn", () => {
    const plan = JSON.parse(JSON.stringify(response.two_stage));
    plan.stage1.strata = [];
    const { container } = rtlRender(wrap(<TwoStagePlanCard plan={plan} loading={false} err={null} />));
    expect(container.textContent).not.toContain("not checked for movement between blocks of time");
  });
});
