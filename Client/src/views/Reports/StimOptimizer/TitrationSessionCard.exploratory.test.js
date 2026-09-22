/**
 * The exploratory ladder (the PI, 2026-09-21): the titration card carries a second ladder for
 * the stimulation configuration the readiness screen's best left sensing pair needs (L 0-3+
 * needs contacts 1 and 2 together, never yet powered on RCS08), built for two answers: how the
 * band power moves with current, and what the current does to pain over minutes. Rendered
 * against the live RCS08 plan served on 2026-09-21 (`__fixtures__/rcs08_titration_plan_exploratory.json`).
 */
import "@testing-library/jest-dom";
import { render as rtlRender, screen } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";
import theme from "assets/theme";
import { PlatformContextProvider } from "context";
import TitrationSessionCard, { EXPLORATORY_TITLE } from "./TitrationSessionCard";
import plan from "./__fixtures__/rcs08_titration_plan_exploratory.json";

jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn(() => Promise.resolve({ data: {} })) } }));

const wrap = (ui) => (
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>
);
const UID = "2e3c75c00d7f4f37b53a048d195f11da";

describe("the exploratory ladder on the titration card", () => {
  it("names the configuration, why, the pair it serves, the rate of the cell, and the record's exposure", () => {
    rtlRender(wrap(<TitrationSessionCard plan={plan} participantUid={UID} />));
    const t = document.body.textContent;
    expect(t).toContain(EXPLORATORY_TITLE);
    expect(t).toContain("L C+1-2-");
    expect(t).toMatch(/L 0⁻3⁺/);
    expect(t).toMatch(/contacts it flanks \(1, 2\) stimulate together/);
    expect(t).toMatch(/125 Hz/);
    expect(t).toMatch(/in force today: 55 Hz/);
    expect(t).toMatch(/24\.5, 25\.5, 26\.5, 27\.5 Hz/);
    expect(t).toMatch(/at 0\.0 mA only: the full rings have never carried current/);
    expect(t).toMatch(/L C\+1a-2a-.*1 mA for 24 h/);
  });

  it("prints the two answers, the stop rule, the ladder and the three blind holds with a rating every minute", () => {
    rtlRender(wrap(<TitrationSessionCard plan={plan} participantUid={UID} />));
    const t = document.body.textContent;
    expect(t).toMatch(/Two answers from one visit/);
    expect(t).toMatch(/side-effect score of 2 or more/);
    expect(t).toMatch(/0 → 0\.5 → … → 4\.5 → … → 0 mA/);
    expect(t).toMatch(/15 steps, 10 distinct currents/);
    expect(t).toMatch(/off \/ on \/ off/);
    expect(t).toMatch(/a rating every 1 min/);
    expect(t).toMatch(/blind/);
    expect(t).toMatch(/right side held at 2\.5[\s\u202f]mA/);
    expect(t).toMatch(/51 min/);
  });

  it("carries its own sheet table: two rows a step, then one row a hold, all L C+1-2- at 125 Hz", () => {
    rtlRender(wrap(<TitrationSessionCard plan={plan} participantUid={UID} />));
    const titles = screen.getAllByText(/Exploratory ladder — L C\+1-2-/);
    expect(titles.length).toBeGreaterThan(0);
    const rows = plan.sheet_rows.filter((r) => String(r.block).startsWith("exploratory_left"));
    expect(rows.length).toBe(33);
    expect(rows.filter((r) => r.row_kind === "hold").length).toBe(3);
    const cells = document.body.textContent;
    expect(cells).toMatch(/L C\+1-2- \/ R C\+1-2-/);
    expect(cells).toMatch(/hold 2 of 3, stimulation on/);
  });

  it("shows nothing of it when the plan carries no proposal", () => {
    const bare = { ...plan, proposed: {}, sheet_rows: plan.sheet_rows.filter((r) => !String(r.block).startsWith("exploratory")) };
    rtlRender(wrap(<TitrationSessionCard plan={bare} participantUid={UID} />));
    expect(document.body.textContent).not.toContain(EXPLORATORY_TITLE);
  });
});
