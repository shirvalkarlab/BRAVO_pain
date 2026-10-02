/**
 * "Ruled-out settings, drawn" draws one panel per side, each with that side's per-pulse-
 * width best cells (grey marks labelled with the side's own pulse width). The strata list carries a
 * Left and a Right row per joint fit; the table of fits keeps one row per joint fit, but the drawing
 * needs both sides' rows, or the Right panel draws none of its own (found 2026-09-26).
 */
import "@testing-library/jest-dom";
import { render as rtlRender } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";
import theme from "assets/theme";
import { PlatformContextProvider } from "context";
import TwoStagePlanCard from "./TwoStagePlanCard";
import response from "./__fixtures__/rcs08_stim_optimizer_two_stage.json";

const wrap = (ui) => (
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>
);

const panelLabels = (container, side) => {
  const svg = container.querySelector(`svg[aria-label^="${side} side"]`);
  return svg ? Array.from(svg.querySelectorAll("text")).map((t) => t.textContent).filter((t) => /µs$/.test(t)) : null;
};

describe("the ruled-out settings drawing", () => {
  it("draws each side's own per-pulse-width best cells", () => {
    const { container } = rtlRender(wrap(<TwoStagePlanCard plan={response.two_stage} loading={false} err={null} />));
    const right = response.two_stage.stage1.strata.filter((r) => r.hemisphere === "Right").map((r) => `${r.pw_us.toFixed(0)} µs`);
    const left = response.two_stage.stage1.strata.filter((r) => r.hemisphere === "Left").map((r) => `${r.pw_us.toFixed(0)} µs`);
    expect(right.length).toBeGreaterThan(0);
    expect(panelLabels(container, "Right")).toEqual(expect.arrayContaining(right));
    expect(panelLabels(container, "Left")).toEqual(expect.arrayContaining(left));
  });

  it("keeps one row per joint fit in the table", () => {
    const { container } = rtlRender(wrap(<TwoStagePlanCard plan={response.two_stage} loading={false} err={null} />));
    const joint = new Set(response.two_stage.stage1.strata.map((r) => r.joint_stratum_key));
    const table = Array.from(container.querySelectorAll("table")).find((t) => /Left pulse width/.test(t.textContent));
    expect(table.querySelectorAll("tbody tr").length).toBe(joint.size);
  });
});
