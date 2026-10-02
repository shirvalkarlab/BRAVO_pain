/**
 * Places where the redesign did not match its own specification, fixed (decision 321; the taste
 * audit of 2026-09-26, section E). Pinned here:
 *   E1. on a phone the Closed-Loop values table and the Stim Optimizer's Today / Suggested /
 *       Difference tables scroll inside their own card, never widening the page;
 *   E2. every caution-coloured word on those tables carries its ▲, and the clinician's
 *       instructions ("Enter, check range", "Your choice", "Device computes; don't type",
 *       "enter as ...", "differs") are plain ink, not caution;
 *   E3. the line under each title names the participant by its study code when one is given, and
 *       never prints a person's name or the long participant id;
 *   E6. the Closed-Loop ceiling line is the shared sentence, one side printed and the other said
 *       not to have been sent.
 */
import "@testing-library/jest-dom";
import { render as rtlRender } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";

import theme from "assets/theme";
import { PlatformContextProvider } from "context";
import { T } from "assets/theme/base/tokens";

import ParameterTable, { ACTION, TABLE_MIN_WIDTH } from "./ClosedLoopSim/PrescriptionPanel";
import payload from "./ClosedLoopSim/__fixtures__/rcs08_deployment_payload.json";
import DecisionStrip from "./StimOptimizer/DecisionStrip";
import response from "./StimOptimizer/__fixtures__/rcs08_stim_optimizer_two_stage.json";
import PageHead, { contextLine } from "./paper/PageHead";
import { ceilingSentence } from "./paper/CeilingLine";
import { studyCode } from "./paper/studyCode";

jest.mock("layouts/DatabaseLayout", () => ({ children }) => <div>{children}</div>);
jest.mock("plotly.js-dist", () => ({ react: () => Promise.resolve(), purge: () => {}, newPlot: () => {} }));
jest.mock("graphing-utility/Plotly", () => ({
  PlotlyRenderManager: class { subplots() {} clearData() {} render() {} setLayoutProps() {} purge() {} },
}));

// eslint-disable-next-line import/first
import { ceilingLineProps, CEILING_NOT_SENT } from "./ClosedLoopSim/index";

const wrap = (ui) => (
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>
);
const clone = (x) => JSON.parse(JSON.stringify(x));

/** The RCS08 payload with the device permitting the configuration, so the table shows its rows. */
function allowedReport() {
  const d = clone(payload);
  d.available = true;
  d.verdict_detail = { ...(d.verdict_detail || {}), device_eligible: true };
  return { data: d, loading: false, err: null };
}

describe("E1: tables scroll inside their own card on a phone", () => {
  test("the Closed-Loop values table sits in a wrapper that scrolls sideways", () => {
    const { container } = rtlRender(wrap(<ParameterTable report={allowedReport()} />));
    const wrapper = container.querySelector("[data-param-table-scroll]");
    expect(wrapper).not.toBeNull();
    expect(getComputedStyle(wrapper).overflowX).toBe("auto");
    expect(wrapper.querySelectorAll("[data-param-row]").length).toBeGreaterThan(0);
    expect(getComputedStyle(wrapper.firstElementChild).minWidth).toBe(`${TABLE_MIN_WIDTH}px`);
  });

  test("each Stim Optimizer Today / Suggested / Difference table sits in a wrapper that scrolls sideways", () => {
    const { container } = rtlRender(wrap(
      <DecisionStrip arms={{}} plan={response.two_stage} inForce={response.in_force_by_side} />));
    const sides = container.querySelectorAll("[data-testid='decision-side']");
    expect(sides.length).toBeGreaterThan(0);
    sides.forEach((side) => {
      const w = side.querySelector("[data-compare-scroll]");
      expect(w).not.toBeNull();
      expect(getComputedStyle(w).overflowX).toBe("auto");
      expect(w.textContent).toMatch(/Today.*Suggested.*Difference/);
      // a grid item may shrink below its content, so the wrapper (not the page) scrolls
      expect(getComputedStyle(side).minWidth).toBe("0");
    });
  });
});

describe("E2: a caution ink always carries ▲; instructions are ink", () => {
  test("the three instructions to the clinician are drawn in ink", () => {
    ["check_on_device", "must_choose", "verify_only"].forEach((k) => {
      expect(ACTION[k].ink).toBe(T.ink);
    });
  });

  test("no text on the values table is in the caution ink without a ▲", () => {
    const { container } = rtlRender(wrap(<ParameterTable report={allowedReport()} />));
    const rows = container.querySelector("[data-param-table-scroll]");
    Array.from(rows.querySelectorAll("*")).forEach((el) => {
      if (getComputedStyle(el).color === "rgb(138, 90, 0)" && el.textContent.trim()) {
        expect(el.textContent).toMatch(/▲/);
      }
    });
    expect(rows.textContent).toMatch(/enter as /);
  });

  test("'no current' on the decision strip carries its ▲", () => {
    const p = clone(response.two_stage);
    p.stage1.frozen_configuration.settings.forEach((s) => { s.amplitude_preferred_mA = null; });
    const { container } = rtlRender(wrap(
      <DecisionStrip arms={{}} plan={p} inForce={response.in_force_by_side} />));
    const cells = Array.from(container.querySelectorAll("[data-compare-scroll] span"))
      .filter((el) => /^▲ ?no current$/.test(el.textContent.trim()));
    expect(cells.length).toBeGreaterThan(0);
  });
});

describe("E3: the line under the title names the study code", () => {
  test("the context line prints the code and the pain score", () => {
    expect(contextLine("RCS08", "Left Leg VAS")).toBe("RCS08 · pain score Left Leg VAS");
    expect(contextLine(null, "NRS (0-10)")).toBe("pain score NRS (0-10)");
    const { container } = rtlRender(wrap(
      <PageHead title="Brain signal vs. pain" participant="RCS08" painScore="Left Leg VAS" />));
    expect(container.textContent).toContain("RCS08 · pain score Left Leg VAS");
  });

  test("only a study code is printed: never a person's name or the long participant id", () => {
    const uid = "2e3c75c00d7f4f37b53a048d195f11da";
    expect(studyCode("RCS08", uid)).toBe("RCS08");
    expect(studyCode(" RCS08 ", uid)).toBe("RCS08");
    expect(studyCode("Jane Doe", uid)).toBeNull();
    expect(studyCode("Jane", uid)).toBeNull();
    expect(studyCode(uid, uid)).toBeNull();
    expect(studyCode(uid, null)).toBeNull();
    expect(studyCode("", uid)).toBeNull();
    expect(studyCode(null, uid)).toBeNull();
  });
});

describe("E6: the Closed-Loop ceiling line is the shared sentence, read from the report", () => {
  test("one side sent: that side printed, the other said not to have been sent", () => {
    const props = ceilingLineProps({ safety_ceiling_mA: 4.5,
      safety_ceiling_provenance: "stated by PI, 2026-09-14 (was 5.0 mA)" }, "Left");
    expect(props).toEqual({ leftMa: 4.5, rightMa: null, source: "set by the PI" });
    expect(ceilingSentence(props.leftMa, props.rightMa, props.source)).toBe(
      "Safe current ceiling: 4.5 mA left, right not sent by the server (set by the PI). "
      + "Nothing above it is offered on this page.");
  });

  test("a ceiling that is not the PI's is named as the server named it", () => {
    const props = ceilingLineProps({ safety_ceiling_mA: 5,
      safety_ceiling_provenance: "module hard limit, no PI-stated ceiling for this participant" }, "Right");
    expect(props.source).toBe("module hard limit, no PI-stated ceiling for this participant");
    expect(props.rightMa).toBe(5);
  });

  test("no ceiling on the report: no number, and the page says it was not sent", () => {
    expect(ceilingLineProps({}, "Left")).toBeNull();
    expect(ceilingLineProps(null, "Left")).toBeNull();
    expect(CEILING_NOT_SENT).not.toMatch(/\d/);
  });
});
