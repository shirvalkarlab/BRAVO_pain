/**
 * Referent audit, 2026-09-15 (`.planning/2026-09-15-rendered-text-referent-audit-three-pages/
 * findings.md` §3). Every card on the Closed-Loop Deployment page is rendered against the REAL
 * /api/queryClosedLoopDeployment response for RCS08 captured that evening, and the assertions pin
 * the text a clinician reads against what the data actually say.
 *
 * THE DEFECT CLASS. A sentence on a card can say a number the data no longer carry (the sweep tries
 * nine lengths since decision 170; two strings on this page still typed "10"/"ten"), or say one fact
 * three times in one glance (the provisional count in the sticky header), or carry a hand-written
 * explanation beside a field the backend already explains (the reliable-change card's, since
 * deleted with the index on 2026-09-22, decision 231). None of these throws, none fails a suite, and every one was on screen. The tests here
 * were written RED against the current components and are meant to go green only when the
 * component (or, for item 6, the backend and its re-captured fixture) is fixed -- never by editing
 * an assertion to match the page.
 *
 * Items are numbered as in the ranked list. The 2026-09-04 fixture is left to `panels.payload.test.js`;
 * this file reads the dated capture, whose verdict is the provisional "supported" state.
 */
import "@testing-library/jest-dom";
import { render as rtlRender, screen, fireEvent } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";

import theme from "assets/theme";
import { PlatformContextProvider } from "context";

import BandSweepGridPanel from "./BandSweepGridPanel";
import DeploymentDecisionHeader from "./DeploymentDecisionHeader";
import WhatWouldChangeThis from "./WhatWouldChangeThis";
import ProvisionalNote from "./ProvisionalNote";
import PrescriptionPanel from "./PrescriptionPanel";
import payload from "./__fixtures__/rcs08_deployment_payload_2026-09-15.json";

// The Material Dashboard primitives read the MUI theme and the platform controller out of context
// (see `panels.payload.test.js` for why both are needed), so every render goes through one wrapper.
const wrap = (ui) => (
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>
);
const render = (ui) => rtlRender(wrap(ui));

const report = { data: payload, loading: false, err: null };
const UID = payload.participant || "RCS08";

/** How many times a phrase occurs in a block of text, case-insensitively. */
function countOf(text, phrase) {
  const re = new RegExp(phrase.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi");
  return (text.match(re) || []).length;
}

describe("the dated fixture is the state these assertions were written against", () => {
  it("carries the provisional verdict, nine lengths, a what_it_means and the threshold notes", () => {
    expect(payload.available).toBe(true);
    expect(payload.verdict).toBe("supported (point signs only; 2 of 3 intervals span zero)");
    expect(payload.verdict_detail.provisional).toBe(true);
    expect(payload.verdict_detail.n_edges_unestablished).toBe(2);
    const sw = payload.band_sweep_grid.band_time_sweep.ONE_THREE_LEFT;
    expect(new Set(sw.best_auc_rows.map((r) => r.chosen_as_best_of_n_windows))).toEqual(new Set([9]));
    expect(new Set(sw.best_correlation_rows.map((r) => r.chosen_as_best_of_n_windows))).toEqual(new Set([9]));
    const dual = payload.prescriptions.modes.dual.fields;
    const upper = dual.find((f) => f.parameter === "Upper LFP threshold");
    expect(upper.design_rule_note).toMatch(/^Noise-only design rule/);
    expect(upper.occupancy_note).toMatch(/^At the 3 s averaging duration in force/);
  });
});

describe("Choose a band (BandSweepGridPanel)", () => {
  // Item 1, STALE-1. `aucTip` types "best of 10 lengths" while `corrTip` beside it reads the row's
  // own `chosen_as_best_of_n_windows` (9 on every row of this fixture). Both hover texts must come
  // from the data, and "10 lengths" must not be printable from a nine-length sweep.
  it("item 1: the AUC hover says 'best of 9 lengths' and no hover says '10 lengths'", () => {
    const { container } = render(
      <BandSweepGridPanel grid={payload.band_sweep_grid} participantUid={UID}
        committed={{ contact: "ONE_THREE_LEFT", centerHz: 12.5 }} onCandidateChosen={() => {}} />,
    );
    const titles = Array.from(container.querySelectorAll("div[title]")).map((el) => el.getAttribute("title"));
    const aucTitles = titles.filter((t) => /^AUC = /.test(t));
    const corrTitles = titles.filter((t) => /^r = /.test(t));
    expect(aucTitles.length).toBeGreaterThan(0);
    expect(corrTitles.length).toBeGreaterThan(0);
    // The correlation side already reads the field, so it is the control: 9 on every row.
    corrTitles.forEach((t) => expect(t).toMatch(/best of 9 lengths/));
    // The AUC side must say the same number for the same rows. RED today: it prints 10.
    aucTitles.forEach((t) => expect(t).toMatch(/best of 9 lengths/));
    expect(titles.filter((t) => /10 lengths/.test(t))).toEqual([]);
  });

  // Item 5, STALE-2. The fold "How to read this, and what it cannot tell you" says "the strongest
  // of ten lengths of signal". The Biomarkers copy of this sentence was corrected at decision 172;
  // this copy was not. The count must come from the data (nine here), never a typed word.
  it("item 5: the how-to-read fold does not say 'ten lengths' and states the count from the data", () => {
    const { container } = render(
      <BandSweepGridPanel grid={payload.band_sweep_grid} participantUid={UID}
        committed={null} onCandidateChosen={() => {}} />,
    );
    fireEvent.click(screen.getByText(/How to read this, and what it cannot tell you/));
    const text = container.textContent;
    expect(text).not.toMatch(/ten lengths/i);
    expect(text).toMatch(/\b(nine|9) lengths\b/i);
  });
});

describe("the sticky verdict header (DeploymentDecisionHeader)", () => {
  // Item 4, DUP-2. With the provisional verdict, the headline prints "(provisional: 2 of 3
  // intervals span zero)" AND each of the two ProvisionalNote boxes beneath prints "2 OF 3 INTERVALS
  // SPAN ZERO" -- the same count three times in one glance. The two boxes are deliberate
  // (ProvisionalNote.js: under the evidence answer and under the transcription answer, never in a
  // fold), so the fix is to the headline, and the ceiling here is two, not one.
  it("item 4: 'of 3 intervals span zero' appears at most twice, and both ProvisionalNote boxes stay", () => {
    const { container } = render(
      <DeploymentDecisionHeader deploymentReport={report} summary={{ data: null, loading: false }}
        bandCandidate={{ contact: "ZERO_TWO_LEFT", contact_label: "L 0⁻2⁺", center_freq_hz: 24.5,
          hemisphere: "Left" }} />,
    );
    // The deliberate pair, asserted so nobody makes the count assertion pass by removing a box.
    expect(container.querySelectorAll(".cl-provisional")).toHaveLength(2);
    // RED today: three.
    expect(countOf(container.textContent, "of 3 intervals span zero")).toBeLessThanOrEqual(2);
  });
});

describe("Full parameter recommendation, threshold rows (PrescriptionPanel)", () => {
  // Item 6, DUP-3. On the Upper/Lower LFP threshold rows the `design_rule_note` says "at this
  // timing (3 s averaging / 30 s onset)" and the `occupancy_note` directly beneath opens with "At
  // the 3 s averaging duration in force" -- the timing twice in two stacked lines under one field.
  // THE FIX IS ON THE BACKEND (`prescription.design_rule_note`: "at the timing shown on this card"
  // when the timing matches), so this test is RED on the current fixture and STAYS RED until the
  // verifier re-captures `rcs08_deployment_payload_2026-09-15.json` after that fix lands. The
  // occupancy note keeps its number, because its percentages depend on it.
  it("item 6: the design-rule note beside the occupancy note does not restate 's averaging /'", () => {
    const { container } = render(<PrescriptionPanel report={report} mode="dual" onMode={() => {}} />);
    // The device permits this configuration in the fixture, so the values and their notes are in
    // the open without the planning view.
    expect(container.textContent).toMatch(/Upper LFP threshold/);
    const notes = Array.from(container.querySelectorAll("*"))
      .filter((el) => el.children.length === 0 && /^Noise-only design rule/.test(el.textContent || ""))
      .map((el) => el.textContent);
    expect(notes.length).toBeGreaterThanOrEqual(2);   // the upper and the lower row
    const occupancy = Array.from(container.querySelectorAll("*"))
      .filter((el) => el.children.length === 0 && /^At the 3 s averaging duration in force/.test(el.textContent || ""));
    expect(occupancy.length).toBeGreaterThanOrEqual(2);
    notes.forEach((n) => expect(n).not.toMatch(/s averaging \//));
  });
});

describe("What would change this answer (WhatWouldChangeThis)", () => {
  // The PI, 2026-09-15 evening, after the browser walk: this card printed "The verdict is
  // provisional: 2 of 3 intervals span zero (E1, E2)" -- the header's count a fourth time on the
  // page. This card's own contribution is WHICH edges and what would establish them; the count and
  // the word "provisional" belong to the verdict header and its two boxes.
  it("names the edges whose intervals span zero without restating the header's count", () => {
    const { container } = render(<WhatWouldChangeThis report={{ data: payload, loading: false, err: null }} />);
    const text = container.textContent;
    expect(text).toMatch(/E1 and E2/);
    expect(text).not.toMatch(/of 3 intervals span zero/);
    expect(text).not.toMatch(/The verdict is provisional/);
    // What establishes them stays on the card.
    expect(text).toMatch(/titration session/i);
  });
});

describe("Deploy-to-Percept review (the sign-off sheet) and its provisional box", () => {
  // The PI, 2026-09-15 evening: the sheet printed the module's verbatim verdict ("supported (point
  // signs only; 2 of 3 intervals span zero)") and, directly beneath it, the provisional box whose
  // headline repeats the same count. The verdict line is the headline on that sheet; the box keeps
  // the per-edge intervals and p, which are printed nowhere else on it.
  it("the provisional box can drop its headline and keep the per-edge lines", () => {
    const { container } = render(<ProvisionalNote deploymentReport={payload} headline={false} />);
    const text = container.textContent;
    expect(text).not.toMatch(/INTERVALS SPAN ZERO/);
    expect(text).toMatch(/E1 sign/);
    expect(text).toMatch(/E2 sign/);
  });
  it("the sign-off sheet passes the verdict line as the headline and the box without one", () => {
    const fs = require("fs");
    const src = fs.readFileSync(require.resolve("./DeploySignoffCard.js"), "utf8");
    expect(src).toMatch(/<ProvisionalNote[^>]*headline=\{false\}/);
  });
});

describe("Full parameter recommendation, the checks under a number (panel D item 7)", () => {
  // The design-rule, occupancy, start-of-stretch and robustness notes were printed one after
  // another with nothing saying they are separate checks, each measured on this participant's own
  // record, rather than one argument in steps. The panel asked for one heading, "Four independent
  // checks on this number"; on the record no row carries four (the threshold rows carry two, the
  // onset and start-up rows one each), so the heading counts the notes on its own row.
  it("heads each row's notes with how many separate checks they are", () => {
    const { container } = render(<PrescriptionPanel report={report} mode="dual" onMode={() => {}} />);
    const text = container.textContent;
    expect(text.match(/Two separate checks on this number, each measured on this participant's own record/g) || [])
      .toHaveLength(2);
    expect(text.match(/A check on this number, measured on this participant's own record/g) || [])
      .toHaveLength(3);
    expect(text).not.toMatch(/Four independent checks/);
  });
});
