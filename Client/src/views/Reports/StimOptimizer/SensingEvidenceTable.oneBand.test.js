/**
 * Decision 199 (2026-09-17): the sensing-evidence table draws the one-band rule -- a contact and
 * rate is usable when at least one band both falls with current (time removed) and rises with
 * pain on the Biomarkers grid -- and says which bands those are, and which of them sit on the
 * stimulator's own harmonics. The values are RCS08's on 2026-09-17, copied from the live response.
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

const cell = (over) => ({
  channel: "ONE_THREE_RIGHT", hemisphere: "Right", rate_hz: 110, n_bands: 18, n_responding: 0,
  n_era_negative_significant: 2, n_pain_positive: 6, n_qualifying: 2, qualifying_centers_hz: [26.5, 27.5],
  qualifying_near_stim_harmonic_hz: [26.5, 27.5], stim_harmonic_notes: { "27.5": "within 2.5 Hz of 27.5 Hz (a quarter of the rate)" },
  amp_low_mA: 1.3, amp_high_mA: 4.0, median_separation_d: 0.659, laterality: "ipsilateral",
  deployable: true, blocking_reasons: "", display_short: "R 1⁻3⁺", display_hemisphere: "Right", display_contacts: "1⁻3⁺",
  ...over,
});

const closedLoop = {
  available: true, ready: true, n_cells_screened: 50, n_cells_deployable: 4,
  selected: { channel: "ONE_THREE_RIGHT", hemisphere: "Right", rate_hz: 110, display_short: "R 1⁻3⁺" },
  amp_hard_limit_mA: 5, adaptive_window_hz: [8, 30], min_adaptive_rate_hz: 55,
  pain_relationship: { available: true, score: "nrs", score_label: "NRS (0–10)", stored_utc: "2026-09-17T21:10:55+00:00",
    by_channel: { ONE_THREE_RIGHT: { centers_hz: [14.5, 23.5, 24.5, 25.5, 26.5, 27.5, 28.5, 29.5], n_established_positive: 8, n_established_negative: 0, n_positive_not_established: 0 },
      ONE_THREE_LEFT: { centers_hz: [], n_established_positive: 0, n_established_negative: 16, n_positive_not_established: 0 } } },
  responding_cells: [
    cell(),
    cell({ channel: "ONE_THREE_LEFT", hemisphere: "Left", rate_hz: 55, n_responding: 0, n_era_negative_significant: 18,
      n_pain_positive: 0, n_qualifying: 0, qualifying_centers_hz: [], qualifying_near_stim_harmonic_hz: [], stim_harmonic_notes: {},
      deployable: false, display_short: "L 1⁻3⁺", display_hemisphere: "Left", display_contacts: "1⁻3⁺",
      blocking_reasons: "no band on this contact has an established positive relationship with pain on the Biomarkers grid (power rising with pain), which the device's control polarity needs" }),
  ],
};

describe("SensingEvidenceTable under the one-band rule", () => {
  it("names the two halves of the rule as columns and prints the qualifying bands", () => {
    const { container } = rtlRender(wrap(<SensingEvidenceTable closedLoop={closedLoop} />));
    const t = container.textContent;
    expect(t).toMatch(/falls with current/i);
    expect(t).toMatch(/rises with pain/i);
    expect(t).toMatch(/both/i);
    expect(t).toContain("26.5, 27.5 Hz");
    expect(t).toContain("6 of 18");                   // pain-positive bands on R 1-3+
    expect(t).toContain("0 of 18");                   // on L 1-3+
  });

  it("no longer says a majority is needed", () => {
    const { container } = rtlRender(wrap(<SensingEvidenceTable closedLoop={closedLoop} />));
    expect(container.textContent).not.toMatch(/50%/);
    expect(container.textContent).not.toMatch(/at least 50/);
  });

  it("marks a qualifying band that sits on the stimulator's own harmonic", () => {
    const { container } = rtlRender(wrap(<SensingEvidenceTable closedLoop={closedLoop} />));
    expect(container.textContent).toMatch(/on a stimulator harmonic/i);
  });

  it("says which grid the pain half was read from", () => {
    const { container } = rtlRender(wrap(<SensingEvidenceTable closedLoop={closedLoop} />));
    expect(container.textContent).toContain("NRS (0–10)");
  });
});
