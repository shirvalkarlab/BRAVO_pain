/**
 * The capped upper limit on the decision card (decision 306).
 *
 * Found live on 2026-09-26: "Values to enter on the A610" read "Adaptive amplitude limit, upper
 * 4.80 mA" for RCS08 (L 1-3+ at 24.5 Hz), above the 4.5 mA per side the PI stated on 2026-09-14.
 * The server now caps every current it recommends at the participant's safe ceiling and says so on
 * the row (`ceiling_note`). These pins check that a clinician reading the table in the open sees the
 * capped value AND the sentence on the same row, that the read-back box still attests to the capped
 * value, and that a row the ceiling did not touch says nothing about it. The CL-DBS simulation card
 * names the capped limits the same way.
 *
 * The fixture is the live left response of 2026-09-25, with its upper-limit rows set to what the
 * server sends after the fix (live values re-measured in decision 306's proof).
 */
import "@testing-library/jest-dom";
import { render as rtlRender, fireEvent, screen } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";

import theme from "assets/theme";
import { PlatformContextProvider } from "context";

jest.mock("plotly.js-dist", () => ({
  react: jest.fn(), purge: jest.fn(), restyle: jest.fn(), relayout: jest.fn(), newPlot: jest.fn(),
  toImage: jest.fn(),
}));
jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn() } }));

// eslint-disable-next-line import/first
import DecisionCard from "./DecisionCard";
// eslint-disable-next-line import/first
import { limitsSourceWords } from "./ClosedLoopSimulationPanel";
import LEFT from "./__fixtures__/rcs08_cl_L13_24p5_2026-09-25.json";
import SUM_L from "./__fixtures__/rcs08_summary_L13_24p5_2026-09-25.json";

const NOTE = "Capped at the 4.5 mA safe ceiling; the highest current measured was 4.8 mA.";
const UPPER = "Adaptive amplitude limit, upper";

const wrap = (ui) => (
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>
);
const BC_L = { contact: "ONE_THREE_LEFT", contact_label: "L 1-3+", center_freq_hz: 24.5, bandwidth_hz: 5,
  hemisphere: "Left" };

/** The live left response with its upper-limit rows as the capped server sends them. */
function capped() {
  const rep = JSON.parse(JSON.stringify(LEFT));
  const fix = (rows) => (rows || []).forEach((r) => {
    if (r.parameter === UPPER) { r.value = 4.5; r.ceiling_note = NOTE; }
  });
  Object.values(rep.prescriptions.modes).forEach((m) => fix(m.fields));
  if (rep.prescription) fix(rep.prescription.fields);
  return rep;
}

const card = (rep) => rtlRender(wrap(
  <DecisionCard participantUid="uid" bandCandidate={BC_L} deploymentReport={{ data: rep, loading: false, err: null }}
    summary={{ data: SUM_L, loading: false, err: null }}
    chosenBand={{ band_candidate: BC_L, committed_at: "2026-09-23T08:00:00.000Z" }}
    bandRecord={{ where: "server", saved: true, chosenBy: "clinician@example.org" }}
    mode={null} onMode={() => {}} />));

/** Text a reader can see: everything outside a closed fold. */
function visibleText(container) {
  const c = container.cloneNode(true);
  c.querySelectorAll(".MuiCollapse-hidden").forEach((n) => n.remove());
  return c.textContent;
}

describe("the capped upper limit on the decision card", () => {
  it("shows 4.50 mA and the one-sentence reason in the open, on that row", () => {
    const { container } = card(capped());
    const text = visibleText(container);
    expect(text).toContain(NOTE);
    expect(text).not.toMatch(/4\.80/);
    const row = screen.getByText(UPPER).closest("[data-param-row]");
    expect(row).not.toBeNull();
    expect(row.textContent).toContain("4.50");
    expect(row.textContent).toContain(NOTE);
  });

  it("keeps the read-back box working on the capped value", () => {
    card(capped());
    const box = screen.getByLabelText(`The programmer now displays ${UPPER} as 4.50 mA`);
    expect(box).not.toBeDisabled();
    fireEvent.click(box);
    expect(box).toBeChecked();
  });

  it("says nothing about a ceiling on a row the ceiling did not touch", () => {
    const { container } = card(capped());
    const lower = screen.getByText("Adaptive amplitude limit, lower").closest("[data-param-row]");
    expect(lower.textContent).not.toMatch(/ceiling/i);
    // and the uncapped live response carries no such sentence anywhere in the open
    const { container: c2 } = card(LEFT);
    expect(visibleText(c2)).not.toMatch(/Capped at the/);
    expect(container).toBeTruthy();
  });
});

describe("the CL-DBS simulation names the limits it ran between", () => {
  it("says the range was capped when the server capped it", () => {
    expect(limitsSourceWords({ amp_limit_note: NOTE }))
      .toBe("the capture range, capped at the safe ceiling");
  });
  it("keeps the old words for a range the ceiling did not touch", () => {
    expect(limitsSourceWords({})).toBe("the capture range, held");
    expect(limitsSourceWords({ amp_limit_note: null })).toBe("the capture range, held");
  });
});
