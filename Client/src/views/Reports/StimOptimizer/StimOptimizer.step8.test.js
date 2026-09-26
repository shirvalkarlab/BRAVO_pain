/**
 * Step 8 of the research panels' build order: the Stim Optimizer page's order and wording, and the
 * two numbers panel C asked to be visible (panel C items 5, 6 and 4; report C §5.2-5.3).
 *
 * Pinned on the words a clinician reads, against the RCS08 fixture the page is already tested on,
 * with the step-8 fields patched in where the fixture predates them:
 *
 *  1. The decision card's title is COMPUTED from the per-side verdicts, never a fixed description,
 *     and "resolved" is defined once, at the top of the strip, not only in a footer.
 *  2. The strip says how many "proven better" comparisons ran and what that exposes (item 4).
 *  3. The closed-loop checks name the recording-site check in plain words and point to the
 *     readiness table that holds its evidence; the readiness table points back.
 *  4. The readiness table's FIRST sentence is the device's sensing rule with the count it explains
 *     (decision 217), and each band that rises with pain says whether it still does once the
 *     current in force is taken out (item 6), or why that is not assessed.
 *  5. The page's order: readiness, then the decision, then the current map, the next session and
 *     its home schedule together, then the plan card; the evidence base as a one-line footer.
 */
import "@testing-library/jest-dom";
import { render as rtlRender } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";

import theme from "assets/theme";
import { PlatformContextProvider } from "context";

import DecisionStrip, { decisionHeadline } from "./DecisionStrip";
import ClosedLoopChecks from "./ClosedLoopChecks";
import SensingEvidenceTable from "./SensingEvidenceTable";
import response from "./__fixtures__/rcs08_stim_optimizer_two_stage.json";

const wrap = (ui) => (
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>
);
const clone = (x) => JSON.parse(JSON.stringify(x));

// --- 1. the decision card's computed title, and "resolved" defined once -------------------------
describe("the decision card's title states the finding", () => {
  it("reads 'no side' when neither side's preferred setting is resolved (the fixture)", () => {
    expect(decisionHeadline(response.two_stage, response.in_force_by_side))
      .toBe("No side has a setting proven better than today's");
  });

  it("names the side when one side resolves and the other does not", () => {
    const plan = clone(response.two_stage);
    plan.stage1.strata.forEach((s) => { if (s.hemisphere === "Left" && s.pw_us === 60) s.optimum_resolved = true; });
    expect(decisionHeadline(plan, response.in_force_by_side))
      .toBe("Left has a setting proven better than today's; Right does not");
  });

  it("says when a comparison could not be formed rather than calling it unresolved", () => {
    const plan = clone(response.two_stage);
    plan.stage1.strata.forEach((s) => { s.optimum_resolved = null; });
    plan.stage1.frozen_configuration.settings.forEach((s) => { s.resolved = null; });
    expect(decisionHeadline(plan, response.in_force_by_side))
      .toBe("No side's preferred setting could be compared with today's");
  });

  // PIN CHANGED 2026-09-26 (the design review; the PI moved 243(b) into a fold): the word is
  // "proven better", the one the headline uses, and its definition sits ONCE in the strip's fold.
  it("defines 'proven better' once, in the strip's fold", () => {
    const { container } = rtlRender(wrap(
      <DecisionStrip arms={{}} plan={response.two_stage} inForce={response.in_force_by_side} />));
    const text = container.textContent;
    const hits = text.match(/Proven better means/g) || [];
    expect(hits.length).toBe(1);
    expect(text).not.toMatch(/Resolved means/);
    const def = Array.from(container.querySelectorAll("div")).find((d) => /^Proven better means/.test(d.textContent));
    expect(def.closest(".MuiCollapse-hidden")).not.toBeNull();
  });
});

// --- 2. the exposure line ------------------------------------------------------------------------
describe("the strip says how many comparisons ran and what that exposes", () => {
  it("prints the server's sentence when the audit carries it", () => {
    const plan = clone(response.two_stage);
    plan.stage1.audit = { ...(plan.stage1.audit || {}), resolution_exposure: {
      n_tests: 4, k: 1, false_pass_rate_per_test: 0.1587, chance_of_at_least_one_false_pass: 0.4995,
      sentence: "The \"proven better than today's setting\" comparison ran 4 times on this record ... upper bound ... changes nothing" } };
    const { container } = rtlRender(wrap(
      <DecisionStrip arms={{}} plan={plan} inForce={response.in_force_by_side} />));
    expect(container.textContent).toMatch(/comparison ran 4 times/);
  });

  it("prints nothing about it when the response predates the field", () => {
    const { container } = rtlRender(wrap(
      <DecisionStrip arms={{}} plan={response.two_stage} inForce={response.in_force_by_side} />));
    expect(container.textContent).not.toMatch(/comparison ran/);
  });
});

// --- 3. the checks card: plain label, and the link to the readiness table ----------------------
describe("the closed-loop checks", () => {
  it("names the recording-site check in plain words and retires the mechanism-first label", () => {
    const { container } = rtlRender(wrap(<ClosedLoopChecks plan={response.two_stage} />));
    expect(container.textContent).toMatch(/Does a usable recording site's power change with current\?/);
    expect(container.textContent).not.toMatch(/A sensed band inside 8–30 Hz responds to stimulation current/);
  });

  // PIN CHANGED 2026-09-26 (the design review): the two cards no longer point at each other; a
  // sentence that only says where another card is was removed from both.
  it("no longer carries a sentence that only points at the readiness table", () => {
    const { container } = rtlRender(wrap(<ClosedLoopChecks plan={response.two_stage} />));
    expect(container.textContent).not.toMatch(/readiness table at the top of this page/i);
  });
});

// --- 4. the readiness table ----------------------------------------------------------------------
const RULE_SENTENCE = "While today's contacts are stimulating, the device allows one sensing pair per lead: "
  + "L 1⁻3⁺ and R 0⁻3⁺. Neither has a usable band, so 0 of 50 contact-and-rate combinations are usable for closed loop.";

const withStep8 = (still) => {
  const cl = clone(response.closed_loop);
  cl.sensing_rule = { sentence: RULE_SENTENCE, by_side: {} };
  cl.pain_relationship = { ...(cl.pain_relationship || {}), available: true, score_label: "NRS",
    by_channel: { ZERO_THREE_LEFT: { display_short: "L 0⁻3⁺", n_supported_positive: 2, n_established_positive: 0 } },
    still_positive_without_current: still };
  return cl;
};

describe("the readiness table", () => {
  it("opens with the device's sensing rule and the count it explains, before the count headline", () => {
    const { container } = rtlRender(wrap(
      <SensingEvidenceTable closedLoop={withStep8({ available: false, by_channel: {}, reason: "no grid" })} />));
    const text = container.textContent;
    expect(text).toContain(RULE_SENTENCE);
    // The count headline reads "N of M contact-and-rate combinations usable for closed loop"
    // (no "are"), which the rule sentence never contains, so this finds the headline alone.
    const headlineAt = text.indexOf("combinations usable for closed loop");
    expect(headlineAt).toBeGreaterThan(-1);
    expect(text.indexOf(RULE_SENTENCE)).toBeLessThan(headlineAt);
  });

  // PIN CHANGED 2026-09-26 (the design review): see the checks card's pin above.
  it("no longer carries a sentence that only points at the checks card", () => {
    const { container } = rtlRender(wrap(
      <SensingEvidenceTable closedLoop={withStep8({ available: false, by_channel: {}, reason: "no grid" })} />));
    expect(container.textContent).not.toMatch(/Closed loop: may it start on the frozen setting\?/);
  });

  it("says for each band that rises with pain whether it still does with the current taken out", () => {
    const still = { available: true, note: "adjusted POINT value only -- no interval", by_channel: {
      ZERO_THREE_LEFT: [
        { center_hz: 24.5, pearson_r: 0.207, pearson_r_adjusted: 0.113, answer: "yes" },
        { center_hz: 25.5, pearson_r: 0.18, pearson_r_adjusted: -0.02, answer: "no" },
      ] } };
    const { container } = rtlRender(wrap(<SensingEvidenceTable closedLoop={withStep8(still)} />));
    const text = container.textContent;
    expect(text).toMatch(/still positive with the current taken out/i);
    expect(text).toMatch(/24\.5 Hz yes \(\+0\.207 → \+0\.113\)/);
    expect(text).toMatch(/25\.5 Hz no \(\+0\.180 → −0\.020\)/);
    expect(text).toMatch(/no interval/i);
  });

  it("says why it is not assessed when no adjusted grid is stored", () => {
    const still = { available: false, by_channel: {}, reason: "no grid with the stimulation current taken out is stored under these settings; the Biomarkers page's switch builds one" };
    const { container } = rtlRender(wrap(<SensingEvidenceTable closedLoop={withStep8(still)} />));
    expect(container.textContent).toMatch(/not assessed: no grid with the stimulation current taken out is stored/i);
  });

  it("no longer says the pain leg needs an 'established' correlation (decision 210 made it 'supported')", () => {
    const { container } = rtlRender(wrap(
      <SensingEvidenceTable closedLoop={withStep8({ available: false, by_channel: {}, reason: "x" })} />));
    expect(container.textContent).not.toMatch(/a positive, established correlation with the pain score/);
  });
});

// --- 6. the search's own stopping rule, shown (the PI, 2026-09-23) -------------------------------
describe("the decision strip shows the search's stopping rule per side", () => {
  it("says it cannot be assessed on this record, and why, with the combinations still worth trying", () => {
    const { container } = rtlRender(wrap(
      <DecisionStrip arms={{}} plan={response.two_stage} inForce={response.in_force_by_side} />));
    const text = container.textContent;
    expect(text).toMatch(/When to stop searching/);
    // PIN CHANGED 2026-09-26: the two sides read alike, so the rule prints once, "Both sides".
    expect(text).toMatch(/Both sides: not assessable/);
    expect(text).toMatch(/no batch of suggested settings has been run and rated in turn/);
    expect(text).toMatch(/3,184 untried combinations still look worth trying/);
  });

  it("says stop when the rule says stop", () => {
    const plan = clone(response.two_stage);
    plan.stage1.strata.forEach((s) => { s.stop = true; s.stop_binding = "plateau and coverage"; s.queue_size = 0; });
    const { container } = rtlRender(wrap(
      <DecisionStrip arms={{}} plan={plan} inForce={response.in_force_by_side} />));
    expect(container.textContent).toMatch(/Both sides: stop/);   // PIN CHANGED 2026-09-26, as above
  });

  it("prints each side on its own when the two sides read differently (2026-09-26)", () => {
    const plan = clone(response.two_stage);
    plan.stage1.strata.forEach((s) => {
      if (s.hemisphere === "Left") { s.stop = true; s.stop_binding = "plateau and coverage"; s.queue_size = 0; }
      else { s.stop = false; s.stop_binding = "coverage"; s.queue_size = 7; }
    });
    const { container } = rtlRender(wrap(
      <DecisionStrip arms={{}} plan={plan} inForce={response.in_force_by_side} />));
    const t = container.querySelector('[data-testid="stopping-rule"]').textContent;
    expect(t).toMatch(/Left: stop/);
    expect(t).toMatch(/Right: keep searching — 7 untried combinations/);
    expect(t).not.toMatch(/Both sides/);
  });

  it("says keep going when combinations are still worth trying and there is a history", () => {
    const plan = clone(response.two_stage);
    plan.stage1.strata.forEach((s) => { s.stop = false; s.stop_binding = "coverage"; s.queue_size = 12; });
    const { container } = rtlRender(wrap(
      <DecisionStrip arms={{}} plan={plan} inForce={response.in_force_by_side} />));
    expect(container.textContent).toMatch(/Both sides: keep searching — 12 untried combinations still look worth trying/);   // PIN CHANGED 2026-09-26, as above
  });
});
