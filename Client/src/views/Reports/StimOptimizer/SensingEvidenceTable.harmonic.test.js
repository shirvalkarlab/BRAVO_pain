/**
 * The harmonic rule on the readiness screen is a WARNING, never a refusal (the PI, 2026-09-21:
 * "put a warning for the harmonic rule, but don't make it blocking"). A usable row whose
 * qualifying bands all sit on a stimulator harmonic keeps its tick and gains a warning the
 * clinician can read without hovering; the screen prints one sentence counting such rows and
 * naming whether the best combination is one of them. A row with a clear band beside a
 * harmonic one gets a note, not a warning.
 */
import React from "react";
import { render as rtlRender } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";
import theme from "assets/theme";
import { PlatformContextProvider } from "context";

import SensingEvidenceTable from "./SensingEvidenceTable";

const wrap = (ui) => (
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>
);

const WARNING = "Warning: this combination qualifies only through bands on a stimulator harmonic at 55 Hz (27.5 Hz: within 2.5 Hz of 27.5 Hz (half the rate)). A fall there with current may be the stimulator, not the brain. It stays usable: by the PI's ruling of 2026-09-21 this is a warning, not a refusal.";
const NOTE = "27.5 Hz sits on a stimulator harmonic at 55 Hz; 24.5 Hz is clear, so the combination does not rest on the harmonic band alone.";
const SENTENCE = "Warning: 1 of 2 usable combinations qualifies only through bands on a stimulator harmonic, where a fall with current may be the stimulator and not the brain, and the best combination is one of them. They stay usable: by the PI's ruling of 2026-09-21 this is a warning, not a refusal.";

const cell = (over) => ({
  channel: "ONE_THREE_RIGHT", hemisphere: "Right", rate_hz: 55, n_bands: 18, n_responding: 0,
  n_era_negative_significant: 2, n_pain_positive: 6, n_qualifying: 1, qualifying_centers_hz: [27.5],
  qualifying_near_stim_harmonic_hz: [27.5], qualifying_clear_of_stim_harmonics_hz: [],
  stim_harmonic_notes: { "27.5": "within 2.5 Hz of 27.5 Hz (half the rate)" },
  harmonic_only: true, harmonic_warning: WARNING, harmonic_note: null,
  amp_low_mA: 1.3, amp_high_mA: 4.0, median_separation_d: 0.659, laterality: "ipsilateral",
  deployable: true, blocking_reasons: "", display_short: "R 1⁻3⁺", display_hemisphere: "Right", display_contacts: "1⁻3⁺",
  ...over,
});

const closedLoop = {
  available: true, ready: true, n_cells_screened: 50, n_cells_deployable: 2,
  selected: { channel: "ONE_THREE_RIGHT", hemisphere: "Right", rate_hz: 55, display_short: "R 1⁻3⁺", harmonic_only: true },
  amp_hard_limit_mA: 5, adaptive_window_hz: [8, 30], min_adaptive_rate_hz: 55,
  harmonic_warning: { n_usable: 2, n_usable_only_through_harmonics: 1,
    cells_only_through_harmonics: [{ channel: "ONE_THREE_RIGHT", hemisphere: "Right", rate_hz: 55 }],
    selected_only_through_harmonics: true, sentence: SENTENCE },
  pain_relationship: { available: true, score: "nrs", score_label: "NRS (0–10)", by_channel: {} },
  responding_cells: [
    cell(),
    cell({ channel: "ZERO_TWO_RIGHT", display_short: "R 0⁻2⁺", display_contacts: "0⁻2⁺",
      n_qualifying: 2, qualifying_centers_hz: [24.5, 27.5], qualifying_clear_of_stim_harmonics_hz: [24.5],
      harmonic_only: false, harmonic_warning: null, harmonic_note: NOTE }),
  ],
};

describe("SensingEvidenceTable: the harmonic rule as a warning", () => {
  it("keeps the tick on a row that qualifies only through harmonic bands and prints the warning in full", () => {
    const { container, getAllByLabelText } = rtlRender(wrap(<SensingEvidenceTable closedLoop={closedLoop} />));
    const t = container.textContent;
    expect(getAllByLabelText("usable").length).toBe(2);      // both rows still usable
    expect(t).toContain(WARNING);                             // readable, not only a tooltip
    expect(t).toMatch(/warning/i);
  });

  it("prints the note, not a warning, on a row with a clear band beside a harmonic one", () => {
    const { container } = rtlRender(wrap(<SensingEvidenceTable closedLoop={closedLoop} />));
    const t = container.textContent;
    expect(t).toContain(NOTE);
    expect((t.match(/qualifies only through bands/g) || []).length).toBe(2); // the row's and the screen's, no third
  });

  it("prints the screen's one sentence and says the best combination is affected", () => {
    const { container } = rtlRender(wrap(<SensingEvidenceTable closedLoop={closedLoop} />));
    expect(container.textContent).toContain(SENTENCE);
  });

  it("prints no screen sentence when no usable row depends on a harmonic band", () => {
    const quiet = { ...closedLoop, harmonic_warning: { n_usable: 2, n_usable_only_through_harmonics: 0, cells_only_through_harmonics: [], selected_only_through_harmonics: false, sentence: null },
      responding_cells: [closedLoop.responding_cells[1]] };
    const { container } = rtlRender(wrap(<SensingEvidenceTable closedLoop={quiet} />));
    expect(container.textContent).not.toMatch(/qualifies only through/);
  });
});
