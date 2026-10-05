/**
 * The titration card (TitrationSessionCard), rendered against the live RCS08 plan served on
 * 2026-09-21 (`__fixtures__/rcs08_titration_plan_exploratory.json`).
 * Merged here 2026-10-05: TitrationSessionCard.exportRequest.test.js,
 * TitrationSessionCard.harmonicAdvisory.test.js, TitrationSessionCard.heldCeiling.test.js,
 * TitrationSessionCard.leadInOpen.test.js. Each block keeps its file's reason.
 *
 * The exploratory ladder (the PI, 2026-09-21): the titration card carries a second ladder for
 * the stimulation configuration the readiness screen's best left sensing pair needs (L 0-3+
 * needs contacts 1 and 2 together, never yet powered on RCS08), built for two answers: how the
 * band power moves with current, and what the current does to pain over minutes.
 */
import "@testing-library/jest-dom";
import { render as rtlRender, screen, fireEvent, waitFor } from "@testing-library/react";
import { wrap } from "testUtils/render";
import { SessionController } from "database/session-control";
import TitrationSessionCard, { EXPLORATORY_TITLE } from "./TitrationSessionCard";
import CurrentMapCard from "./CurrentMapCard";
import { OPTIMIZER_REQUEST } from "./optimizerRequest";
import plan from "./__fixtures__/rcs08_titration_plan_exploratory.json";
import response from "./__fixtures__/rcs08_stim_optimizer_two_stage.json";
import response0925 from "./__fixtures__/rcs08_stim_optimizer_2026-09-25.json";

// The test setup resets every jest.fn's behaviour before each test, so this answer applies only
// while the modules load; every test sees a query that records its call and returns nothing.
jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn(() => Promise.resolve({ data: {} })) } }));
jest.mock("plotly.js-dist", () => require("testUtils/plotlyStubs").plotlyNoop());
jest.mock("graphing-utility/Plotly", () => require("testUtils/plotlyStubs").renderManagerStub());

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

// ---------------------------------------------------------------------------------------------
// The clinic-sheet export rebuilds the Stim Optimizer response from its own request (from
// TitrationSessionCard.exportRequest; `DataAnalysis.ExportTitrationSheet` hands `request.data` to
// `run_for_participant`). It sends the page's own request, so it is answered from the stored response
// the page already built, not by a full recompute under another key (before 2026-09-26 it sent the
// participant and date only, and the server's default figure backend made it a different stored answer).
it("the sheet export sends the page's own request with the participant and the visit date", async () => {
  rtlRender(wrap(<TitrationSessionCard plan={plan} participantUid={UID} />));
  fireEvent.click(screen.getAllByRole("button", { name: /Make Google sheet/, hidden: true })[0]);
  await waitFor(() => expect(SessionController.query).toHaveBeenCalled());
  const [url, body] = SessionController.query.mock.calls[0];
  expect(url).toBe("/api/exportTitrationSheet");
  expect(body).toEqual(expect.objectContaining({ ...OPTIMIZER_REQUEST, ParticipantId: UID }));
  expect(body.Backend).toBe("none");
  expect(body.VisitDate).toMatch(/^\d{4}-\d{2}-\d{2}$/);
});

// ---------------------------------------------------------------------------------------------
// The harmonic wording is advisory (from TitrationSessionCard.harmonicAdvisory), matching what the
// plan does with a flagged band centre: `titration_plan.harmonic_avoidance` only sorts the 22 stored
// centres into "clear" and "flagged" (`clear_hz` / `avoid_hz`); nothing downstream removes a flagged
// centre from `CENTRES_HZ`, so every one of the 22 is analysed either way (decision 220: a warning,
// never a refusal; the PI's correction of 2026-09-06). The card used to say a flagged centre "is
// struck", which reads as dropped from the analysis.
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
      `${left.n_clear} clear, ${left.n_avoid} flagged \\(all analysed\\)`)).length)
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
    expect(t).toMatch(/centres within ±\d+(\.\d+)? Hz are flagged, not dropped/);
    expect(t).toMatch(/stimulator artefact at/);
  });
});

// ---------------------------------------------------------------------------------------------
// A held side is never held above its safe ceiling (from TitrationSessionCard.heldCeiling; decision
// 308). The server holds a side whose current in force is above today's ceiling AT the ceiling and
// says why; the titration card and the next-visit line print that sentence in the warning colour, and
// print nothing new when the current in force is under the ceiling (RCS08 today: 3.0 mA left, 2.5 mA
// right, ceiling 4.5 mA). The plan's right side in force is raised to 4.8 mA, the value the left
// delivered before its ceiling was lowered.
const NOTE = "the Right side's current in force, 4.8 mA, is above today's safe ceiling for that side, "
  + "4.5 mA; it is held at 4.5 mA for this ladder, not at the current in force -- set it to 4.5 mA before the first step";

function heldAbove(p) {
  const left = p.sides.Left;
  return {
    ...p,
    sides: {
      ...p.sides,
      Left: { ...left, held_other_side: { ...left.held_other_side, current_mA: 4.5, in_force_mA: 4.8,
        ceiling_mA: 4.5, above_ceiling: true, note: NOTE } },
    },
  };
}

describe("the titration card: the held side above its ceiling", () => {
  it("prints the held current at the ceiling and the server's sentence saying why", () => {
    rtlRender(wrap(<TitrationSessionCard plan={heldAbove(plan)} participantUid={UID} />));
    const t = document.body.textContent;
    expect(t).toMatch(/left's ladder holds right at4\.5[\s ]mA/i);   // PIN CHANGED 2026-09-26: the header labels are sentence case (SPEC.md section 2.4); the current is unchanged
    expect(t).toContain("Held at the ceiling: the Right side's current in force, 4.8 mA, is above today's safe ceiling");
    expect(t).toContain("not at the current in force — set it to 4.5 mA before the first step");
    expect(t).not.toContain("in force -- set");
  });

  it("prints no such sentence when the current in force is under the ceiling", () => {
    rtlRender(wrap(<TitrationSessionCard plan={plan} participantUid={UID} />));
    expect(document.body.textContent).not.toMatch(/Held at the ceiling/);
    expect(document.querySelectorAll("[data-testid='held-above-ceiling']").length).toBe(0);
  });
});

describe("the next-visit line: the held side above its ceiling", () => {
  function planWithGap(gap) {
    const base = response.two_stage;
    const rows = base.stage1.rate_strata.map((r) => (r.fitted && r.rate_hz === 55
      ? { ...r, coverage_passes: false, coverage_gap: gap } : { ...r, coverage_gap: null }));
    return { ...base, stage1: { ...base.stage1, rate_strata: rows } };
  }
  const GAP = {
    n_pairs_missing: 1, stepped_side: "Left", held_side_mA: 4.5,
    pairs_to_top_up: [], pairs_to_add: [{ amp_mA_Left: 4, amp_mA_Right: 4.5 }],
    cheapest_way: "run L4/R4.5",
    why: "this stratum needs 1 more current pair carrying enough ratings on enough days",
    what_each_pair_needs: "at least 5 ratings at that setting, on at least 2 different days",
    held_side_note: NOTE.replace("for this ladder", "for these pairs"),
  };

  it("prints the held-side sentence under the cheapest way", () => {
    rtlRender(wrap(<CurrentMapCard plan={planWithGap(GAP)} />));
    const t = document.body.textContent;
    expect(t).toContain("What the next visit must deliver: run L4/R4.5.");
    expect(t).toContain("it is held at 4.5 mA for these pairs, not at the current in force — set it to 4.5 mA");
  });

  it("prints nothing new when no side was held above its ceiling", () => {
    const { held_side_note: _drop, ...plain } = GAP;
    rtlRender(wrap(<CurrentMapCard plan={planWithGap(plain)} />));
    expect(document.body.textContent).not.toMatch(/above today's safe ceiling/);
  });
});

// ---------------------------------------------------------------------------------------------
// The next-visit section starts closed (from TitrationSessionCard.leadInOpen; the PI, 2026-09-26),
// and two safety lines must stay in view while it is: decision 308's "Held at the ceiling"
// instruction, and the home schedule's line for a setting in force above the ceiling. Both are in
// the section's always-visible lead, outside its hidden body, and printed once. Neither appears when
// nothing is above a ceiling (RCS08 today).
const ABOVE = {
  amp_left_mA: 3.0, amp_right_mA: 4.8, above_ceiling: true, sides_above_ceiling: ["Right"],
  offered_as_target: false, label: "in force, above today's ceiling",
  why: "history: the setting in force today is above the safe ceiling on the Right side (4.8 mA against 4.5 mA), "
    + "so it is shown for reference and never offered as a step to hold",
};

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
    const schedule = { ...response0925.current_map_schedule, in_force: ABOVE };
    rtlRender(wrap(<TitrationSessionCard plan={plan} participantUid={UID} homeSchedule={schedule} />));
    const hits = screen.getAllByText(/In force, above today's ceiling: 3\.0 mA left \/ 4\.8 mA right/);
    expect(hits.length).toBe(1);
    expect(visible(hits[0])).toBe(true);
  });

  it("adds nothing to the lead when nothing is above a ceiling", () => {
    const schedule = { ...response0925.current_map_schedule };
    const { container } = rtlRender(wrap(<TitrationSessionCard plan={plan} participantUid={UID} homeSchedule={schedule} />));
    expect(container.querySelector('[data-testid="next-visit-safety-lead"]')).toBeNull();
    expect(container.textContent).not.toMatch(/Held at the ceiling|above today's ceiling/);
  });
});
