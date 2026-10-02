/**
 * The research band detector on the Biomarkers page's control-analysis card (the PI's rulings 5a-5c,
 * 2026-09-25). Ruling 5a: the clinic-sheet ratings are shown ONLY when the page's clinic-sheet switch
 * is on -- the card then reads the run with the sheets merged in; otherwise the REDCap-only run, and
 * never both. The two figures draw what the server saved, with intervals, in real colours.
 */
import React from "react";
import { render as rtlRender, screen, fireEvent } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";
import theme from "assets/theme";
import { PlatformContextProvider } from "context";

import ControlAnalysesCard from "./ControlAnalysesCard";
import { resetPlots, plotsIn, markColours, hoverTexts, allX } from "./plotTestUtils";

jest.mock("plotly.js-dist", () => require("./plotTestUtils").plotlyMock());
beforeEach(() => resetPlots());

const render = (ui) => rtlRender(
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>,
);

const rb = (rho, p = 0.2, q = 0.4) => ({ rho, lo: rho - 0.15, hi: rho + 0.15, r2: 0.02, n_scored: 180, p, q,
  null_p50: 0.0, null_p95: 0.12 });
const researchRow = (pair, seconds, plain, adj) => ({
  pair, seconds, n_from_sheets: 0,
  reading: { n: 187, n_days: 120, current_alone: { rho: 0.2, lo: 0.05, hi: 0.35 }, bands: rb(plain),
    bands_without_current: rb(adj) },
  same_current: { current_mA: 3.0, from: "2026-09-03", to: "2026-09-23", reading: { reason: "12 ratings" } },
});
const RESEARCH = {
  key: "band_detector_research", title: "Band detector, research version (pain as a number)",
  what: "Every band of one sensing pair read together.", literature: [], n_runs: 1,
  snapshot: {
    run_at: "2026-09-25T23:00:00Z", data_from: "2025-07-16", data_through: "2026-09-23", settings: {},
    reading: ["REDCAP-ONLY LINE: L 1-3+, 60 s."],
    result: {
      reading_by_sheets_switch: { off: ["REDCAP-ONLY LINE: L 1-3+, 60 s."], on: ["SHEETS-MERGED LINE: L 1-3+, 60 s."] },
      modes: {
        off: { rows: [researchRow("ONE_THREE_LEFT", 60, 0.21, 0.08), researchRow("ZERO_THREE_RIGHT", 60, -0.05, 0.01)] },
        on: { rows: [researchRow("ONE_THREE_LEFT", 60, 0.44, 0.02)] },
      },
    },
  },
};
const db = (c, auc, q) => ({ centre_hz: c, carries_folded_multiple: c > 22,
  reading: { n: 120, n_days: 90, current_alone: { auc: 0.61, lo: 0.52, hi: 0.7 },
    band: { auc, lo: auc - 0.1, hi: auc + 0.1, p: 0.03, q, direction: "rises with pain" },
    band_without_current: { auc: 0.5, lo: 0.4, hi: 0.6, p: 0.5, q: 0.9 } } });
const DEVICE = {
  key: "band_detector_device", title: "Band detector, device-shaped version (one band, two pain groups)",
  what: "What the device could read.", literature: [], n_runs: 1,
  snapshot: {
    run_at: "2026-09-25T23:10:00Z", data_from: "2025-07-16", data_through: "2026-09-23", settings: {},
    reading: ["DEVICE REDCAP LINE"],
    result: {
      reading_by_sheets_switch: { off: ["DEVICE REDCAP LINE"], on: ["DEVICE SHEETS LINE"] },
      modes: {
        off: { pairs: [{ pair: "ONE_THREE_LEFT", bands: [db(20.5, 0.6, 0.3), db(24.5, 0.66, 0.04)] }] },
        on: { pairs: [{ pair: "ONE_THREE_LEFT", bands: [db(20.5, 0.55, 0.5)] }] },
      },
    },
  },
};
const PAYLOAD = { page: "biomarkers", analyses: [RESEARCH, DEVICE] };

describe("the band detector on the control-analysis card", () => {
  it("shows the REDCap-only run when the page's clinic-sheet switch is off, and says so", () => {
    render(<ControlAnalysesCard payload={PAYLOAD} clinicSheets={false} />);
    expect(screen.getByText(/REDCAP-ONLY LINE/)).toBeTruthy();
    expect(screen.queryByText(/SHEETS-MERGED LINE/)).toBeNull();
    expect(screen.getByText(/the home pain surveys alone;/)).toBeTruthy();
    // the row names are the figure's y-axis labels
    const rowNames = (plotsIn(screen.getByTestId("figure-band_detector_research"))[0] || {}).layout.yaxis.ticktext;
    expect(rowNames.join("|")).toMatch(/R 0-3/);
  });

  it("shows the sheets-merged run only when the switch is on, and says so", () => {
    render(<ControlAnalysesCard payload={PAYLOAD} clinicSheets />);
    expect(screen.getByText(/SHEETS-MERGED LINE/)).toBeTruthy();
    expect(screen.queryByText(/REDCAP-ONLY LINE/)).toBeNull();
    expect(screen.getByText(/clinic-sheet ratings merged in/)).toBeTruthy();
    const rowNames = plotsIn(screen.getByTestId("figure-band_detector_research"))[0].layout.yaxis.ticktext;
    expect(rowNames.join("|")).not.toMatch(/R 0-3/);
  });

  it("draws the device-shaped version per band with its interval, and follows the switch", () => {
    const { rerender } = render(<ControlAnalysesCard payload={PAYLOAD} clinicSheets={false} />);
    fireEvent.change(screen.getByLabelText("Which check"), { target: { value: "band_detector_device" } });
    const fig = screen.getByTestId("figure-band_detector_device");
    // one dot per band in each of the two readings: 2 bands, plain and with the current taken out
    const bandsDrawn = (c) => plotsIn(c)[0].data.filter((t) => t.name === "band")[0].x.length;
    expect(bandsDrawn(fig)).toBe(2);
    expect(screen.getByText(/DEVICE REDCAP LINE/)).toBeTruthy();
    rerender(
      <ThemeProvider theme={theme}>
        <PlatformContextProvider initialStates={{ darkMode: false }}>
          <ControlAnalysesCard payload={PAYLOAD} clinicSheets />
        </PlatformContextProvider>
      </ThemeProvider>,
    );
    expect(screen.getByText(/DEVICE SHEETS LINE/)).toBeTruthy();
    expect(bandsDrawn(screen.getByTestId("figure-band_detector_device"))).toBe(1);
  });

  it("draws every mark of both figures in a real colour", () => {
    const { container } = render(<ControlAnalysesCard payload={PAYLOAD} clinicSheets={false} />);
    fireEvent.change(screen.getByLabelText("Which check"), { target: { value: "band_detector_device" } });
    const plots = plotsIn(container);
    expect(plots.length).toBeGreaterThan(0);
    plots.forEach((plot) => {
      markColours(plot).forEach((c) => expect(c).toMatch(/^#[0-9A-Fa-f]{3,8}$/));
      hoverTexts(plot).forEach((t) => expect(t).not.toMatch(/undefined|NaN/));
    });
  });

  it("hovering a band of the device-shaped figure prints its AUC, 95% range, q, p, and the ratings; the y axis is named AUC", () => {
    const { container } = render(<ControlAnalysesCard payload={PAYLOAD} clinicSheets={false} />);
    fireEvent.change(screen.getByLabelText("Which check"), { target: { value: "band_detector_device" } });
    const [plot] = plotsIn(container);
    expect(plot.layout.yaxis.title.text).toBe("AUC");
    expect(plot.data.find((t) => t.name === "band").hovertext[1]).toBe([
      "24.5 Hz \u00b7 the band", "area under the curve 0.66 (95% range 0.56 to 0.76)",
      "q 0.04 (after allowing for the bands tested) \u00b7 p 0.03",
      "carries a folded multiple of the rate in force (advisory)", "120 ratings in the two pain groups"].join("<br>"));
    // the x axis ends on a labelled tick at or beyond the last band
    expect(plot.layout.xaxis.ticktext[plot.layout.xaxis.ticktext.length - 1]).toBe(String(plot.layout.xaxis.range[1]));
    expect(plot.layout.xaxis.range[1]).toBeGreaterThanOrEqual(Math.max(...allX(plot)));
  });
});
