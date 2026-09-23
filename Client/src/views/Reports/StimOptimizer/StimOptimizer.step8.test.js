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

  it("defines 'resolved' once, at the top of the strip", () => {
    const { container } = rtlRender(wrap(
      <DecisionStrip arms={{}} plan={response.two_stage} inForce={response.in_force_by_side} />));
    const text = container.textContent;
    const hits = text.match(/Resolved means/g) || [];
    expect(hits.length).toBe(1);
    expect(text.indexOf("Resolved means")).toBeLessThan(text.indexOf("programmed now"));
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

  it("points to the readiness table that holds that check's evidence", () => {
    const { container } = rtlRender(wrap(<ClosedLoopChecks plan={response.two_stage} />));
    expect(container.textContent).toMatch(/readiness table at the top of this page/i);
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

  it("points to the checks card that decides whether closed loop may start", () => {
    const { container } = rtlRender(wrap(
      <SensingEvidenceTable closedLoop={withStep8({ available: false, by_channel: {}, reason: "no grid" })} />));
    expect(container.textContent).toMatch(/Closed loop: may it start on the frozen setting\?/);
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
