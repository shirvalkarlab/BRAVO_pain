/**
 * The current-limits check fails for several reasons (`stage_gate.check_amplitude_limits`): a
 * proposed upper limit above the side's safe ceiling, limits that are not finite (no delivered
 * range), a maximum not above the minimum, or a limit outside the currents ever delivered. Only the
 * first is the ceiling, and only the first is red (the PI's ruling of 2026-09-26, D14); the others
 * block in ink with their own short name.
 */
import { statusSummary } from "./StatusLine";
import { conditionFailState } from "./ClosedLoopChecks";
import response from "./__fixtures__/rcs08_stim_optimizer_two_stage.json";

const clone = (x) => JSON.parse(JSON.stringify(x));
const NAME = "amplitude_limits_inside_envelope_and_under_ceiling";

function planWith(evidence, detail) {
  const plan = clone(response.two_stage);
  plan.gate.conditions = plan.gate.conditions.map((c) => (c.name === NAME
    ? { ...c, verdict: "FAIL", passed: false, detail, evidence: { ...c.evidence, ...evidence } } : c));
  return plan;
}
const CEIL = { ceiling_mA: 4.5, ceiling_by_side: { Left: { ceiling_mA: 4.5 }, Right: { ceiling_mA: 4.5 } } };
const bulletsOf = (plan) => statusSummary(response, plan).bullets;

describe("the current-limits bullet names what actually failed", () => {
  it("a proposed limit above the ceiling is the red ceiling refusal", () => {
    const plan = planWith({ ...CEIL, defaulted: [], checked: {
      Left: { amp_min_mA: 1.0, amp_max_mA: 4.8, envelope: [0, 4.8] },
      Right: { amp_min_mA: 1.0, amp_max_mA: 3.0, envelope: [0, 4.5] } } },
    "Left: upper limit 4.8 mA exceeds the declared ceiling of 4.5 mA");
    const b = bulletsOf(plan).find((x) => /ceiling/i.test(x.text));
    expect(b).toBeTruthy();
    expect(b.text).toBe("Current limits above ceiling");
    expect(b.kind).toBe("refused");
    expect(conditionFailState(plan.gate.conditions.find((c) => c.name === NAME))).toBe("refused");
  });

  it("a side delivered at one current only is not called above the ceiling", () => {
    const plan = planWith({ ...CEIL, defaulted: [], checked: {
      Left: { amp_min_mA: 2.0, amp_max_mA: 2.0, envelope: [2.0, 2.0] },
      Right: { amp_min_mA: 1.0, amp_max_mA: 3.0, envelope: [0, 4.5] } } },
    "Left: limits must satisfy max > min (got 2, 2); the device needs a range to move within");
    const bs = bulletsOf(plan);
    expect(bs.some((x) => x.text === "Current limits above ceiling")).toBe(false);
    const b = bs.find((x) => x.text === "Current limits have no range");
    expect(b).toBeTruthy();
    expect(b.kind).toBe("blocked");
    expect(conditionFailState(plan.gate.conditions.find((c) => c.name === NAME))).toBe("blocked");
  });

  it("an empty delivered range and a limit beyond the delivered currents get their own names", () => {
    const plan = planWith({ ...CEIL, defaulted: [], checked: {
      Left: { amp_min_mA: null, amp_max_mA: null, envelope: [null, null] },
      Right: { amp_min_mA: 0.5, amp_max_mA: 4.0, envelope: [1.0, 3.0] } } },
    "Left: limits are not finite; Right: upper limit 4 mA is above the highest amplitude ever delivered");
    const texts = bulletsOf(plan).filter((x) => x.kind === "blocked").map((x) => x.text);
    expect(texts).toContain("No delivered current range");
    expect(texts).toContain("Limit beyond delivered currents");
    expect(texts).not.toContain("Current limits above ceiling");
    texts.forEach((t) => expect(t.split(/\s+/).length).toBeLessThanOrEqual(5));
  });
});
