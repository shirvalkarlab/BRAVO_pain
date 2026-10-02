/**
 * The decision strip reads each side's verdict and gain from the setting the server FROZE
 * (`stage1.frozen_configuration.settings[]`), and each side's stratum row from the JOINT stratum
 * that setting was chosen from (`detail.best_pw_us_left` / `best_pw_us_right`).
 *
 * Before 2026-09-26 it read the stratum row's `optimum_resolved`, which is the rate move alone: the
 * server downgrades the frozen setting when the per-rate current check fails, and a setting whose
 * pulse-width pair is the one in force is never "proven better" (`stage1_openloop._freeze_joint`;
 * the gate reads `frozen.resolved`). And it matched a side's stratum on that side's pulse width
 * alone, while strata are (left, right) pairs.
 */
import "@testing-library/jest-dom";
import { render as rtlRender } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";
import theme from "assets/theme";
import { PlatformContextProvider } from "context";
import DecisionStrip, { decisionHeadline, sideVerdicts } from "./DecisionStrip";
import response from "./__fixtures__/rcs08_stim_optimizer_two_stage.json";

const wrap = (ui) => (
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>
);
const clone = (x) => JSON.parse(JSON.stringify(x));
const inForce = response.in_force_by_side;

describe("the strip's verdict is the frozen setting's, not the rate move's", () => {
  it("does not say proven better when the rate move clears but the current check failed", () => {
    const plan = clone(response.two_stage);
    plan.stage1.strata.forEach((s) => { s.optimum_resolved = true; });
    // the server: rate_resolved downgraded to False because no current could be recommended
    plan.stage1.frozen_configuration.settings.forEach((s) => {
      s.rate_resolved = false; s.pulse_width_resolved = true; s.resolved = false;
    });
    expect(decisionHeadline(plan, inForce)).toBe("No side has a setting proven better than today's");
    expect(sideVerdicts(plan, inForce).map((v) => v.res)).toEqual([false, false]);
  });

  it("does not say proven better when the chosen pulse-width pair is the one in force", () => {
    const plan = clone(response.two_stage);
    plan.stage1.strata.forEach((s) => { s.optimum_resolved = true; });
    plan.stage1.frozen_configuration.settings.forEach((s) => {
      s.rate_resolved = true; s.pulse_width_resolved = false; s.resolved = false;
    });
    expect(decisionHeadline(plan, inForce)).toBe("No side has a setting proven better than today's");
  });

  it("says proven better only when the frozen setting is resolved", () => {
    const plan = clone(response.two_stage);
    plan.stage1.frozen_configuration.settings.forEach((s) => {
      s.rate_resolved = true; s.pulse_width_resolved = true; s.resolved = true;
    });
    expect(decisionHeadline(plan, inForce)).toBe("Both sides have a setting proven better than today's");
  });

  it("calls a side not determinable when the rate comparison could not be formed", () => {
    const plan = clone(response.two_stage);
    plan.stage1.frozen_configuration.settings.forEach((s) => {
      s.rate_resolved = null; s.pulse_width_resolved = false; s.resolved = false;
    });
    expect(decisionHeadline(plan, inForce)).toBe("No side's preferred setting could be compared with today's");
  });
});

describe("each side reads the joint stratum its setting was chosen from", () => {
  function twoStrataSharingLeftWidth() {
    const plan = clone(response.two_stage);
    const chosen = plan.stage1.strata.filter((r) => r.joint_stratum_key === "60_160");
    // a second joint stratum with the same LEFT pulse width, listed first, reading differently
    const other = chosen.map((r) => ({ ...r, pw_us_left: 60, pw_us_right: 60, joint_stratum_key: "60_60",
      pw_us: 60, gain: 1.5, sd_of_difference: 0.2, optimum_resolved: true,
      stop: false, stop_binding: "coverage", queue_size: 9 }));
    plan.stage1.strata = [...other, ...chosen];
    return plan;
  }

  it("prints one stopping rule for both sides, the chosen stratum's", () => {
    const { container } = rtlRender(wrap(
      <DecisionStrip arms={{}} plan={twoStrataSharingLeftWidth()} inForce={inForce} />));
    const t = container.querySelector('[data-testid="stopping-rule"]').textContent;
    expect(t).toMatch(/Both sides: not assessable/);
    expect(t).toMatch(/3,184 untried combinations/);
    expect(t).not.toMatch(/9 untried/);
  });

  it("shows the same predicted change on both sides, the frozen setting's", () => {
    const { container } = rtlRender(wrap(
      <DecisionStrip arms={{}} plan={twoStrataSharingLeftWidth()} inForce={inForce} />));
    const sides = Array.from(container.querySelectorAll('[data-testid="decision-side"]'));
    expect(sides.length).toBe(2);
    sides.forEach((el) => expect(el.textContent).not.toMatch(/\+1\.50 pain points/));
    expect(sides[0].textContent.match(/Predicted change[^.]*\./)[0])
      .toBe(sides[1].textContent.match(/Predicted change[^.]*\./)[0]);
  });
});

describe("a gain the server discarded is not drawn", () => {
  it("prints no predicted change when the chosen stratum never delivered the rate in force", () => {
    const plan = clone(response.two_stage);
    plan.stage1.strata.forEach((s) => {
      s.optimum_resolved = null; s.incumbent_rate_supported = false; s.gain = 0.83;
    });
    plan.stage1.frozen_configuration.settings.forEach((s) => {
      s.rate_resolved = null; s.resolved = false; s.gain = 0.83;
    });
    const { container } = rtlRender(wrap(<DecisionStrip arms={{}} plan={plan} inForce={inForce} />));
    const t = container.textContent;
    expect(t).not.toMatch(/0\.83/);
    expect(t).toMatch(/Predicted change in pain against today's setting: no difference could be formed/);
  });
});

describe("a flat fit says so beside its predicted change (the PI, 2026-10-02)", () => {
  // RCS08 L C+2- 60/160 us: the fitted effect of current sat at the kernel's smallest value, so the
  // "+0.00 ± 1.24" on both sides was no effect of current and the scatter of the ratings.
  const withFlat = (flag) => {
    const plan = clone(response.two_stage);
    plan.stage1.strata = plan.stage1.strata.map((r) => (r.joint_stratum_key === "60_160"
      ? { ...r, current_effect_at_minimum: flag } : r));
    return plan;
  };
  it("names the ± as rating scatter when the fit found no effect of current", () => {
    const { container } = rtlRender(wrap(<DecisionStrip arms={{}} plan={withFlat(true)} inForce={inForce} />));
    const sides = Array.from(container.querySelectorAll('[data-testid="decision-side"]'));
    sides.forEach((el) => {
      expect(el.textContent).toMatch(/No effect of current found on these stretches; ± \d+\.\d\d is the scatter of the pain ratings\./);
      expect(el.textContent).not.toMatch(/with an uncertainty of/);
    });
  });
  it("keeps the uncertainty wording when the fit found an effect", () => {
    const { container } = rtlRender(wrap(<DecisionStrip arms={{}} plan={withFlat(false)} inForce={inForce} />));
    expect(container.textContent).toMatch(/with an uncertainty of/);
    expect(container.textContent).not.toMatch(/No effect of current found/);
  });
});
