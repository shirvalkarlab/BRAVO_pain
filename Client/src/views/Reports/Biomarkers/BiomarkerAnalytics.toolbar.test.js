/**
 * The "Band–pain link over time" section (BiomarkerAnalytics.js) drew its
 * sliding-correlation heat map with a save-as-PNG/zoom/pan toolbar until the minimalist redesign
 * of 2026-09-26 (SPEC.md section 3) took it off every figure that had one, with no way for a
 * reviewer to get a copy of the figure out of the browser for the deployment record. The PI put
 * it back the same day (decisions 320-322 corrected).
 */
import "@testing-library/jest-dom";
import React from "react";
import { render } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";

import theme from "assets/theme";
import { PlatformContextProvider } from "context";
import BiomarkerAnalytics from "./BiomarkerAnalytics";

jest.mock("plotly.js-dist", () => ({
  react: jest.fn(), purge: jest.fn(), restyle: jest.fn(), relayout: jest.fn(), newPlot: jest.fn(),
}));
// eslint-disable-next-line import/first
import Plotly from "plotly.js-dist";

const wrap = (ui) => (
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>
);

const analytics = {
  timedomain: {
    sliding_corr_spectrum: {
      channels: [
        { channel: "L 1-3+", freqs: [10, 15, 20], window_starts: ["2026-01-01", "2026-02-01"],
          r: [[0.1, 0.2], [0.1, 0.2], [0.1, 0.2]] },
      ],
    },
  },
};

beforeEach(() => { Plotly.react.mockReset(); });

test("the sliding-correlation heat map draws with the restored toolbar, on hover, PNG export", () => {
  render(wrap(<BiomarkerAnalytics analytics={analytics} metricLabel="Left Leg VAS" />));
  expect(Plotly.react).toHaveBeenCalledTimes(1);
  const [, , , config] = Plotly.react.mock.calls[0];
  // the PI, 2026-09-26: toolbar restored so reviewers can save figures for the deployment record
  expect(config.displayModeBar).not.toBe(false);
  expect(config.displaylogo).toBe(false);
  expect(config.toImageButtonOptions.format).toBe("png");
});
