/**
 * The clinic stream on the current map, 2026-09-23: the PI's ruling 5 answer at its head, and the
 * pooling toggle reaching it.
 *
 * (1) Ruling 5 (decision 233): the next session runs at the pairing in force and its ratings are
 * merged with the earlier clinic record at that rate. What that merged stratum still needs (decision
 * 239's measurement) now rides the clinic block as `next_session_coverage`, printed in the open at
 * the head of the clinic section.
 * (2) The clinic stream's own fit pooled over pulse widths was always built and never carried; the
 * "Pool pulse widths" toggle now swaps the clinic section too, where it is available.
 */
import "@testing-library/jest-dom";
import { render as rtlRender, screen, fireEvent } from "@testing-library/react";
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
    addHeatmap() {} addScatter() {} addShape() {} addAnnotation() {} setTitle() {} purge() {}
  },
}));

const wrap = (ui) => (
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>
);

function planWith({ nextSession, clinicPooling }) {
  const base = response.two_stage;
  const s1 = base.stage1;
  const fitted = s1.rate_strata_clinic.find((r) => r.fitted) || s1.rate_strata_clinic[0];
  const pooledClinicRow = { ...fitted, pooled_pulse_widths: true, n_pairings_pooled: 2, n_epochs: 34,
    n_reports: 140, pairings: [{ pw_us_left: 60, pw_us_right: 160, n_epochs: 24, n_reports: 100 },
      { pw_us_left: 100, pw_us_right: 150, n_epochs: 10, n_reports: 40 }] };
  return { ...base, stage1: { ...s1,
    clinic_stream: { ...s1.clinic_stream, next_session_coverage: nextSession },
    pulse_width_pooling: { available: true, default: "separate", note: "n",
      in_force_pairing: { pw_us_left: 60, pw_us_right: 160 },
      rate_strata_pooled: [{ ...s1.rate_strata.find((r) => r.fitted), pooled_pulse_widths: true,
        n_pairings_pooled: 3, pairings: [{ pw_us_left: 60, pw_us_right: 160, n_epochs: 17, n_reports: 120 }] }] },
    pulse_width_pooling_clinic: clinicPooling ? { available: true, default: "separate", note: "n",
      in_force_pairing: { pw_us_left: 100, pw_us_right: 150 }, rate_strata_pooled: [pooledClinicRow] }
      : { available: false, reason: "not requested", rate_strata_pooled: [] } } };
}

const NEXT = { available: true, rate_hz: 55, n_epochs: 34,
  pairings_merged: [{ pw_us_left: 100, pw_us_right: 150, n_epochs: 10, in_force: true },
    { pw_us_left: 60, pw_us_right: 160, n_epochs: 24, in_force: false }],
  coverage: { n_pairs: 5, n_pairs_required: 6, passes: false },
  gap: { n_pairs_missing: 1, cheapest_way: "repeat L3/R3 (1 more rating) -- settings the record already has, which need topping up rather than a new pair" },
  sentence: "The PI's ruling 5: the next session runs at 55 Hz at the pairing in force (100/150 us) and its ratings are merged with the clinic record at 60/160 us. Merged, 5 of 6 current pairs qualify." };

describe("CurrentMapCard: the clinic stream's next session and its pooled fit", () => {
  it("prints ruling 5's merged answer in the open at the head of the clinic section", () => {
    rtlRender(wrap(<CurrentMapCard plan={planWith({ nextSession: NEXT, clinicPooling: false })} />));
    const t = document.body.textContent;
    expect(t).toContain("Merged, 5 of 6 current pairs qualify.");
    expect(t).toContain("What the next session must deliver: repeat L3/R3 (1 more rating)");
  });

  it("the pooling toggle swaps the clinic section to its own pooled fit", () => {
    rtlRender(wrap(<CurrentMapCard plan={planWith({ nextSession: NEXT, clinicPooling: true })} />));
    fireEvent.click(screen.getByRole("button", { name: /Pool pulse widths/ }));
    const t = document.body.textContent;
    expect(t).toContain("60/160\u202f\u00b5s (24 epochs), 100/150\u202f\u00b5s (10 epochs)");
  });

  it("where the clinic pooled fit is not available the clinic section stays separate and says so", () => {
    rtlRender(wrap(<CurrentMapCard plan={planWith({ nextSession: null, clinicPooling: false })} />));
    fireEvent.click(screen.getByRole("button", { name: /Pool pulse widths/ }));
    expect(document.body.textContent).toMatch(/clinic sheets: pooling across pulse widths is not available/i);
  });
});
