/**
 * When the clinic fit is unavailable the server says why under `reason`
 * (`clinic_pain.fit_clinic_rate_strata`, `bravo_service._clinic_stream_stage1_block`); `note` is
 * the success path's own remark (the pooled-variance note). The clinic section prints the reason,
 * and never the success note as the explanation for an empty section.
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

describe("the clinic section says why it has nothing to draw", () => {
  it("prints the server's reason when the clinic fit is unavailable", () => {
    const plan = clone(response.two_stage);
    plan.stage1.clinic_stream = { available: false,
      reason: "fewer than two clinic settings carry Left Leg pain readings" };
    plan.stage1.rate_strata_clinic = [];
    const { container } = rtlRender(wrap(<CurrentMapCard plan={plan} />));
    expect(container.textContent).toContain("fewer than two clinic settings carry Left Leg pain readings");
    expect(container.textContent).not.toContain("no clinic or home-testing workbooks could be read");
  });

  it("does not offer the success note as the reason when no rate came back", () => {
    const plan = clone(response.two_stage);
    plan.stage1.rate_strata_clinic = [];
    const { container } = rtlRender(wrap(<CurrentMapCard plan={plan} />));
    expect(container.textContent).not.toContain("pooled within-setting variance (2.6762) was estimable and used");
    expect(container.textContent).toContain("the fit returned no rate to draw");
  });
});
