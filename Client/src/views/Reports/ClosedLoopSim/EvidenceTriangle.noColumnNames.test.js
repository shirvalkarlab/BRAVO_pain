/**
 * No column name on the evidence triangle (decision 314, following 313). The line that reads E2
 * again with the current taken out printed "the stimulation current in force (amp_mA_Left)": the
 * name of a table column, in front of a clinician. Since 2026-10-02 the line reads the summary's
 * match-window reading, which names the side (`hemisphere`); with no side it reads "the stimulation
 * current in force", never the column.
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

const report = () => {
  const d = JSON.parse(JSON.stringify(payload));
  d.candidates = [{ ...(d.candidates || [{}])[0], channel: "ONE_THREE_LEFT", center_hz: 24.5 }];
  return { data: d };
};

const line = (container) => container.querySelector("[data-testid='e2-adjusted']").textContent;

describe("the evidence triangle names the current in words, never its column", () => {
  it("names the side in words", () => {
    const { container } = rtlRender(wrap(<EvidenceTrianglePanel report={report()} matchWindowAuc={{
      available: true, adjusted_for: "amp_mA_Left", hemisphere: "Left",
      auc: 0.469, auc_low: 0.348, auc_high: 0.596, partial_r: -0.114, n_pain_reports: 30,
    }} />));
    expect(line(container)).toMatch(/^With the left stimulation current in force taken out of the band power, on the biomarker match window: 0\.47/);
    expect(container.textContent).not.toMatch(/amp_mA/);
  });

  it("with no side named, still shows no column", () => {
    const { container } = rtlRender(wrap(<EvidenceTrianglePanel report={report()} matchWindowAuc={{
      available: false, adjusted_for: "amp_mA_Left",
      why: "this band's power moves almost exactly with the left stimulation current on these samples",
    }} />));
    expect(line(container)).toMatch(/^With the stimulation current in force taken out of the band power, on the biomarker match window: not made here/);
    expect(container.textContent).not.toMatch(/amp_mA/);
  });
});
