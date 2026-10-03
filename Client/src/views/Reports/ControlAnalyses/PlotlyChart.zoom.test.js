/**
 * The offline checks' figures zoom, pan, save as PNG from the toolbar and reset on double-click, as
 * the Biomarker Data Timeline does (the PI, 2026-10-03: "make them work in a similar model as they
 * do with the biomarker data timeline, where if you double-click it resets the view").
 */
import { render } from "@testing-library/react";
import Plotly from "plotly.js-dist";
import { SectionRevealedContext } from "views/Reports/paper/Section";

jest.mock("plotly.js-dist", () => ({ react: jest.fn(() => Promise.resolve()), purge: jest.fn(), Plots: { resize: jest.fn() } }));

// eslint-disable-next-line import/first
import PlotlyChart from "./PlotlyChart";

test("the toolbar shows (with PNG save) and double-click resets the view", () => {
  render(
    <SectionRevealedContext.Provider value>
      <PlotlyChart spec={{ data: [{ x: [1, 2], y: [3, 4] }], layout: {} }} height={200} label="a figure" />
    </SectionRevealedContext.Provider>);
  expect(Plotly.react).toHaveBeenCalled();
  const config = Plotly.react.mock.calls[Plotly.react.mock.calls.length - 1][3];
  expect(config.displayModeBar).not.toBe(false);
  expect(config.toImageButtonOptions).toEqual(expect.objectContaining({ format: "png" }));
  expect(config.doubleClick).toBe("reset+autosize");
  const layout = Plotly.react.mock.calls[Plotly.react.mock.calls.length - 1][2];
  expect(layout.dragmode).toBe("zoom");
});
