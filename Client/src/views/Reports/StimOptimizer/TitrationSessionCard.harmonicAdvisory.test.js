/**
 * The titration card's harmonic wording is advisory, matching what the plan actually does with a
 * flagged band centre: `titration_plan.harmonic_avoidance` only sorts the 22 stored centres into
 * "clear" and "flagged" (`clear_hz` / `avoid_hz`); nothing downstream removes a flagged centre from
 * `CENTRES_HZ`, so every one of the 22 is analysed either way (decision 220: a warning, never a
 * refusal; the PI's correction of 2026-09-06). The card used to say a flagged centre "is struck",
 * which reads as dropped from the analysis -- wrong, and fixed here. No response field changed by
 * this fix, so no live proof is needed.
 */
import "@testing-library/jest-dom";
import { render as rtlRender, screen } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";
import theme from "assets/theme";
import { PlatformContextProvider } from "context";
import TitrationSessionCard from "./TitrationSessionCard";
import plan from "./__fixtures__/rcs08_titration_plan_exploratory.json";

jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn(() => Promise.resolve({ data: {} })) } }));

const wrap = (ui) => (
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>
);
const UID = "2e3c75c00d7f4f37b53a048d195f11da";

describe("the titration card's harmonic wording is advisory, never a refusal", () => {
  it("never says a flagged centre is struck, anywhere on the card", () => {
    rtlRender(wrap(<TitrationSessionCard plan={plan} participantUid={UID} />));
    expect(document.body.textContent).not.toMatch(/struck/i);
  });

  it("the band strip counts a flagged centre as flagged, not struck, and says both are analysed", () => {
    rtlRender(wrap(<TitrationSessionCard plan={plan} participantUid={UID} />));
    const left = plan.sides.Left.bands;
    expect(left.n_avoid).toBeGreaterThan(0);
    expect(screen.getAllByText(new RegExp(
      `${left.n_clear} clear, ${left.n_avoid} flagged \\(analysed either way\\)`)).length)
      .toBeGreaterThan(0);
  });

  it("a flagged centre carries no strikethrough style: it is still analysed, only greyed", () => {
    rtlRender(wrap(<TitrationSessionCard plan={plan} participantUid={UID} />));
    const flaggedHz = plan.sides.Left.bands.avoid_hz[0];
    const cell = screen.getAllByText(String(flaggedHz))[0];
    expect(cell).toBeTruthy();
    expect(cell.style.textDecoration).not.toBe("line-through");
  });

  it("the 'analyse at' row states the flag is advisory and drops nothing", () => {
    rtlRender(wrap(<TitrationSessionCard plan={plan} participantUid={UID} />));
    const t = document.body.textContent;
    expect(t).toMatch(/carries a folded multiple of the stimulation rate and is flagged, not dropped/);
    expect(t).toMatch(/every centre above is still analysed/);
    expect(t).toMatch(/advisory, the PI, 2026-09-06/);
  });
});
