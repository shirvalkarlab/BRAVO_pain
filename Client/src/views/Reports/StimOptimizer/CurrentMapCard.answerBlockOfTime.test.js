/**
 * The current map starts closed, so its answer is what a reader sees. When a map that can
 * recommend a current "moves between blocks of time" (decision 253's check, marked with a dagger
 * since decision 294), the answer says so in the open rather than giving the count alone.
 */
import "@testing-library/jest-dom";
import { render as rtlRender } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";
import theme from "assets/theme";
import { PlatformContextProvider } from "context";
import CurrentMapCard from "./CurrentMapCard";
import response from "./__fixtures__/rcs08_stim_optimizer_two_stage.json";

jest.mock("plotly.js-dist", () => {
  const noop = () => {};
  return { react: () => Promise.resolve(), purge: noop, restyle: noop, relayout: noop, newPlot: noop };
});

const wrap = (ui) => (
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>
);
const clone = (x) => JSON.parse(JSON.stringify(x));

function planWith(verdict) {
  const plan = clone(response.two_stage);
  let first = true;
  plan.stage1.rate_strata = plan.stage1.rate_strata.map((r) => {
    if (!r.fitted || !first) return r;
    first = false;
    return { ...r, resolved: true, amp_mA_left: 2.0, amp_mA_right: 1.5,
      calibration: { diagnosis: { verdict } } };
  });
  return plan;
}
const openAnswer = (container) => Array.from(container.querySelectorAll("section#current-map p"))
  .filter((p) => p.closest("[hidden]") === null).map((p) => p.textContent).join(" ");

describe("the current map's open answer carries the block-of-time qualifier", () => {
  it("says when a map that can recommend a current moves between blocks of time", () => {
    const { container } = rtlRender(wrap(<CurrentMapCard plan={planWith("moves between blocks of time")} />));
    const a = openAnswer(container);
    expect(a).toMatch(/^1 of the \d pain maps drawn can recommend a current/);
    expect(a).toContain("moves between blocks of time");
    expect(a).toContain("†");
  });

  it("adds nothing when the map was checked and holds", () => {
    const { container } = rtlRender(wrap(<CurrentMapCard plan={planWith("calibrated")} />));
    const a = openAnswer(container);
    expect(a).toMatch(/^1 of the \d pain maps drawn can recommend a current, marked best ★\.$/);
  });
});
