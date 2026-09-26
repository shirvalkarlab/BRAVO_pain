/**
 * No column name on the evidence triangle (decision 314, following 313). The line that reads E2
 * again with the current taken out printed "the stimulation current in force (amp_mA_Left)": the
 * name of a table column, in front of a clinician. The server now sends the current in words
 * (`adjusted_for_words`, from the estimator's own table of words); the page prints those, and an
 * answer saved before the words were sent reads "the stimulation current in force", never the column.
 */
import "@testing-library/jest-dom";
import { render as rtlRender } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";

import theme from "assets/theme";
import { PlatformContextProvider } from "context";

jest.mock("plotly.js-dist", () => ({
  react: jest.fn(), purge: jest.fn(), restyle: jest.fn(), relayout: jest.fn(), newPlot: jest.fn(),
  toImage: jest.fn(),
}));

// eslint-disable-next-line import/first
import EvidenceTrianglePanel from "./EvidenceTrianglePanel";
import payload from "./__fixtures__/rcs08_deployment_payload_2026-09-15.json";

const wrap = (ui) => (
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>
);

const withAdjusted = (adjusted) => {
  const d = JSON.parse(JSON.stringify(payload));
  d.candidates = [{ ...(d.candidates || [{}])[0], channel: "ONE_THREE_LEFT", center_hz: 24.5 }];
  d.edges.E2.adjusted = adjusted;
  return { data: d };
};

const line = (container) => container.querySelector("[data-testid='e2-adjusted']").textContent;

describe("the evidence triangle names the current in words, never its column", () => {
  it("prints the words the server sends", () => {
    const { container } = rtlRender(wrap(<EvidenceTrianglePanel report={withAdjusted({
      available: true, adjusted_for: "amp_mA_Left", adjusted_for_words: "the left stimulation current",
      auc: 0.469, auc_low: 0.348, auc_high: 0.596, partial_r: -0.114, n_pain_reports: 30,
    })} />));
    expect(line(container)).toMatch(/^With the left stimulation current in force taken out of the band power: 0\.469/);
    expect(container.textContent).not.toMatch(/amp_mA/);
  });

  it("an answer saved before the words were sent still shows no column", () => {
    const { container } = rtlRender(wrap(<EvidenceTrianglePanel report={withAdjusted({
      available: false, adjusted_for: "amp_mA_Left",
      why: "this band's power moves almost exactly with the left stimulation current on these samples",
    })} />));
    expect(line(container)).toMatch(/^With the stimulation current in force taken out of the band power: not made here/);
    expect(container.textContent).not.toMatch(/amp_mA/);
  });
});
