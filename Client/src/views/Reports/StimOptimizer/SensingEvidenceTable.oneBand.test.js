/**
 * Decision 199 (2026-09-17): the sensing-evidence table draws the one-band rule -- a contact and
 * rate is usable when at least one band both falls with current (time removed) and rises with
 * pain on the Biomarkers grid -- and says which bands those are, and which of them sit on the
 * stimulator's own harmonics. The values are RCS08's on 2026-09-17, copied from the live response.
 *
 * Merged here 2026-10-05: SensingEvidenceTable.harmonic.test.js,
 * SensingEvidenceTable.notListed.test.js. Each merged file's tests sit in a describe block named
 * after it, with its reason above it.
 */

import React from "react";
import { render as rtlRender } from "@testing-library/react";
import SensingEvidenceTable from "./SensingEvidenceTable";
import { wrap } from "testUtils/render";

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
    by_channel: { ONE_THREE_RIGHT: { display_short: "R 1⁻3⁺", centers_hz: [14.5, 23.5, 24.5, 25.5, 26.5, 27.5, 28.5, 29.5], n_supported_positive: 8, n_established_positive: 5, supported_not_established_hz: [26.5, 27.5, 28.5], n_established_negative: 0, n_positive_not_supported: 0 },
      ONE_THREE_LEFT: { display_short: "L 1⁻3⁺", centers_hz: [], n_supported_positive: 0, n_established_positive: 0, supported_not_established_hz: [], n_established_negative: 16, n_positive_not_supported: 0 } } },
  responding_cells: [
    cell(),
    cell({ channel: "ONE_THREE_LEFT", hemisphere: "Left", rate_hz: 55, n_responding: 0, n_era_negative_significant: 18,
      n_pain_positive: 0, n_qualifying: 0, qualifying_centers_hz: [], qualifying_near_stim_harmonic_hz: [], stim_harmonic_notes: {},
      deployable: false, display_short: "L 1⁻3⁺", display_hemisphere: "Left", display_contacts: "1⁻3⁺",
      blocking_reasons: "no band on this contact has a supported positive relationship with pain on the Biomarkers grid (power rising with pain), which the device's control polarity needs" }),
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

  it("states the pain leg's rule as the interval above zero and reports the stricter count beside it (decision 210)", () => {
    const { container } = rtlRender(wrap(<SensingEvidenceTable closedLoop={closedLoop} />));
    const t = container.textContent;
    expect(t).toMatch(/interval (lies )?wholly above zero/i);
    expect(t).not.toMatch(/the grid calls it established\./);
    expect(t).toContain("R 1⁻3⁺: 8 rise (5 of them established)");
    expect(t).toContain("L 1⁻3⁺: 0 rise, 16 fall");
  });

  it("no longer says a majority is needed", () => {
    const { container } = rtlRender(wrap(<SensingEvidenceTable closedLoop={closedLoop} />));
    expect(container.textContent).not.toMatch(/50%/);
    expect(container.textContent).not.toMatch(/at least 50/);
  });

  it("marks a qualifying band that sits on the stimulator's own harmonic", () => {
    const { container } = rtlRender(wrap(<SensingEvidenceTable closedLoop={closedLoop} />));
    // PIN CHANGED 2026-09-26: the PI's advisory wording (2026-09-06), "carries a folded multiple of
    // the stimulation rate", in place of "on a stimulator harmonic".
    expect(container.textContent).toMatch(/carries a folded multiple of the rate/i);
    expect(container.textContent).not.toMatch(/on a stimulator harmonic/i);
  });

  it("says which grid the pain half was read from", () => {
    const { container } = rtlRender(wrap(<SensingEvidenceTable closedLoop={closedLoop} />));
    expect(container.textContent).toContain("NRS (0–10)");
  });
});

/* From SensingEvidenceTable.harmonic.test.js.
 * The harmonic rule on the readiness screen is a WARNING, never a refusal (the PI, 2026-09-21:
 * "put a warning for the harmonic rule, but don't make it blocking"). A usable row whose
 * qualifying bands all sit on a stimulator harmonic keeps its tick and gains a warning the
 * clinician can read without hovering; the screen prints one sentence counting such rows and
 * naming whether the best combination is one of them. A row with a clear band beside a
 * harmonic one gets a note, not a warning.
 */
describe("from SensingEvidenceTable.harmonic", () => {
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
});

/* From SensingEvidenceTable.notListed.test.js.
 * The readiness list holds only the combinations with something on them (a band that qualifies,
 * falls with current, or responds to a change in current), at most 30
 * (`bravo_service.closed_loop_readiness`). A pair the device allows today that has no row was
 * still screened and is counted in the sentence above; the page says it is not in the list, never
 * that "nothing was screened" on it (2026-09-26).
 */
describe("from SensingEvidenceTable.notListed", () => {
  const closedLoop = {
    available: true, ready: false, n_cells_screened: 50, n_cells_deployable: 0,
    sensing_rule: { sentence: "One sensing pair per lead: L 1-3+ and R 0-3+.", by_side: {
      Left: { rule_applied: true, allowed_channel: "ONE_THREE_LEFT", allowed_display: "L 1⁻3⁺", n_usable_on_allowed_pair: 0 },
      Right: { rule_applied: true, allowed_channel: "ZERO_THREE_RIGHT", allowed_display: "R 0⁻3⁺", n_usable_on_allowed_pair: 0 } } },
    responding_cells: [{ channel: "ZERO_TWO_LEFT", hemisphere: "Left", rate_hz: 55, n_bands: 22, n_responding: 1,
      n_era_negative_significant: 0, n_pain_positive: 0, n_qualifying: 0, qualifying_centers_hz: [],
      deployable: false, blocking_reasons: "sensing pair not allowed", display_short: "L 0⁻2⁺" }],
  };

  it("says an allowed pair with no row is not in the list, not that nothing was screened", () => {
    const { container } = rtlRender(wrap(<SensingEvidenceTable closedLoop={closedLoop} />));
    const t = container.textContent;
    expect(t).not.toMatch(/Nothing was screened/);
    expect(t).toContain("No combination on L 1⁻3⁺ or R 0⁻3⁺ is in this list");
    expect(t).toMatch(/only combinations with a band that qualifies, falls with current or responds to a change in current/);
  });
});
