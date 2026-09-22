/**
 * The current-map card must not be readable as "higher current lowers this patient's pain".
 *
 * WHY. Across the whole record the two do move together: Left Leg VAS averages 58 at 0 mA and 46 to
 * 53 between 3.0 and 4.8 mA. Measured on 2026-09-22, out of sample it does not hold -- a model given
 * only the current in force forecasts whether a rating will be high or low no better than chance
 * (area under the curve 0.41 on the left current alone, 0.49 on both, against a shuffled level whose
 * 95th percentile is 0.57, over 611 ratings, with the folds separated in time). The honest reading
 * is that the good stretches happened also to be the high-current stretches. This card draws pain
 * against the two currents, so it is exactly where that could be misread, and the sentence belongs
 * in the open rather than behind the descriptions button.
 */
import "@testing-library/jest-dom";
import { render as rtlRender, screen } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";

import theme from "assets/theme";
import { PlatformContextProvider } from "context";
import CurrentMapCard from "./CurrentMapCard";
import response from "./__fixtures__/rcs08_stim_optimizer_two_stage.json";

jest.mock("plotly.js-dist", () => {
  const noop = () => {};
  return { react: () => Promise.resolve(), purge: noop, restyle: noop, relayout: noop, newPlot: noop };
});
jest.mock("graphing-utility/Plotly", () => ({
  PlotlyRenderManager: class {
    constructor() { this.traces = []; this.layout = {}; }
    subplots() {} clearData() {} render() {} setLayoutProps() {} setXlabel() {} setYlabel() {}
    addHeatmap() {} addScatter() {} addShape() {} addAnnotation() {} setTitle() {}
  },
}));

const wrap = (ui) => (
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>
);

const plan = response.two_stage;

describe("the current-map card says the current-and-pain association does not hold out of sample", () => {
  it("prints the caveat in the open, without pressing the descriptions button", () => {
    const { container } = rtlRender(wrap(<CurrentMapCard plan={plan} />));
    const node = Array.from(container.querySelectorAll('[data-testid="current-pain-caveat"]'))[0];
    expect(node).toBeTruthy();
    const text = node.textContent;
    expect(text).toMatch(/does not hold up out of sample/i);
    expect(text).toMatch(/0\.41/);          // the measured area under the curve
    expect(text).toMatch(/0\.57/);          // the level chance reaches
    expect(text).toMatch(/611 ratings/);
    expect(text).toMatch(/not evidence that raising the current lowers this patient/i);
  });

  it("does not hide it behind the descriptions button", () => {
    rtlRender(wrap(<CurrentMapCard plan={plan} />));
    // the button is there and still closed; the caveat is readable anyway
    expect(screen.getByText(/description/i)).toBeTruthy();
    expect(screen.getByTestId("current-pain-caveat")).toBeVisible();
  });
});
