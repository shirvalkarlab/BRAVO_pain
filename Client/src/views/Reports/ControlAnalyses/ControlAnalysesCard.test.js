/**
 * The control analyses card (the PI, 2026-09-24: saved results, 1, 2 and 4 first, each with the
 * literature link). It draws what the server saved and nothing else: the dated stamp, the reading,
 * the figure, the literature; an analysis never run says so; the dropdown switches between them.
 */
import React from "react";
import { render as rtlRender, screen, fireEvent } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";
import theme from "assets/theme";
import { PlatformContextProvider } from "context";

import ControlAnalysesCard from "./ControlAnalysesCard";

const render = (ui) => rtlRender(
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>,
);

const LIT = [{ label: "Synthesis: same current, wash-in", url: "https://github.com/x/blob/y/artifacts/s.md" }];
const band = (stretch, kind, c, rho, q) => ({ score: "vas", pair: "ONE_THREE_LEFT", stretch, kind, centre: c,
  n: 75, days: 25, rho, lo: rho - 0.2, hi: rho + 0.2, p: 0.01, q, band_vs_time: 0.3, pain_vs_time: 0.17 });

export const PAYLOAD = {
  page: "biomarkers",
  analyses: [
    { key: "zero_ma_within_stretch", title: "Band against pain with the current off", what: "Within each stretch.",
      literature: LIT, n_runs: 2,
      snapshot: { run_at: "2026-09-24T23:30:00Z", data_from: "2025-07-16", data_through: "2026-09-23",
        settings: { seconds_of_signal: 60 },
        reading: ["both off, 2025-07-16 to 2025-08-22, ONE_THREE_LEFT, vas (75 ratings, 25 days): rise with pain at 21.5 Hz (+0.38)."],
        result: {
          stretches: [{ label: "both off, 2025-07-16 to 2025-08-22", kind: "both off", days: 37 }],
          coverage: [{ score: "vas", pair: "ONE_THREE_LEFT", stretch: "both off, 2025-07-16 to 2025-08-22",
            kind: "both off", reports: 96, days_with_reports: 33, matched_60min: 17, matched_same_day: 75, days_matched: 25 }],
          bands: [band("both off, 2025-07-16 to 2025-08-22", "both off", 21.5, 0.38, 0.044),
                  band("both off, 2025-07-16 to 2025-08-22", "both off", 22.5, 0.35, 0.044),
                  band("left off, right on, 2025-08-22 to 2025-10-21", "left off, right on", 21.5, -0.34, 0.002)],
          pooled_both_off: [] } } },
    { key: "current_explains", title: "What the stimulation current explains", what: "Pain read out of sample.",
      literature: LIT, n_runs: 1,
      snapshot: { run_at: "2026-09-24T23:40:00Z", data_from: "2025-07-16", data_through: "2026-09-23", settings: {},
        reading: ["ONE_THREE_LEFT, 60 s (187 ratings): current alone 0.708, every band 0.743, bands without the current 0.683 (outside the shuffled-data 95th, 0.673)."],
        result: { rows: [{ pair: "ONE_THREE_LEFT", seconds: 60, n: 187, current_alone: 0.708, bands: 0.743,
          bands_without_current: 0.683, null_p50: 0.52, null_p95: 0.673, p: 0.04 }] } } },
    { key: "time_of_day", title: "Time of day and weekends", what: "Clock and weekend.", literature: LIT,
      n_runs: 0, snapshot: null },
  ],
};

describe("the control analyses card", () => {
  it("opens on the first analysis with its dated stamp, reading, figure and literature", () => {
    render(<ControlAnalysesCard payload={PAYLOAD} />);
    expect(screen.getByText(/^Run .*2026.* on data 2025-07-16 to 2026-09-23/)).toBeTruthy();
    expect(screen.getByText(/2 runs kept/)).toBeTruthy();
    expect(screen.getByText(/rise with pain at 21.5 Hz/)).toBeTruthy();
    expect(screen.getByTestId("figure-zero_ma_within_stretch")).toBeTruthy();
    const link = screen.getByRole("link", { name: /Synthesis: same current, wash-in/ });
    expect(link.getAttribute("href")).toBe(LIT[0].url);
    expect(link.getAttribute("target")).toBe("_blank");
    expect(screen.getByText(/feeds no recommendation/)).toBeTruthy();
  });

  it("shows how many 0 mA ratings had a recording, within 60 minutes and the same day", () => {
    render(<ControlAnalysesCard payload={PAYLOAD} />);
    const table = screen.getByTestId("zero-ma-coverage");
    expect(table.textContent).toMatch(/96/);
    expect(table.textContent).toMatch(/17/);
    expect(table.textContent).toMatch(/75/);
  });

  it("switches to another analysis from the dropdown", () => {
    render(<ControlAnalysesCard payload={PAYLOAD} />);
    fireEvent.change(screen.getByLabelText("Control analysis"), { target: { value: "current_explains" } });
    expect(screen.getByTestId("figure-current_explains")).toBeTruthy();
    expect(screen.getByText(/bands without the current 0.683/)).toBeTruthy();
  });

  it("draws every mark in a real colour, never an undefined one", () => {
    const { container } = render(<ControlAnalysesCard payload={PAYLOAD} />);
    const marks = [...container.querySelectorAll("circle, line, polyline")];
    expect(marks.length).toBeGreaterThan(0);
    // React leaves an undefined colour out altogether, so a missing attribute is the failure.
    marks.forEach((m) => {
      const a = m.tagName === "circle" ? "fill" : "stroke";
      expect(m.getAttribute(a)).toMatch(/^#[0-9A-Fa-f]{3,8}$/);
    });
  });

  it("draws the on/off switches as a table of mean pain around each switch", () => {
    const payload = { analyses: [{ key: "onoff_switches", title: "Pain around each on/off switch", what: "Around each switch.",
      literature: LIT, n_runs: 1, snapshot: { run_at: "2026-09-24T23:50:00Z", data_from: "2025-07-16", data_through: "2026-09-23",
        settings: {}, reading: ["Descriptive."], result: { switches: [{ label: "the right side on, 2025-08-22", direction: "on",
          before: { mean: 8.86, n: 42 }, after: [{ days: "0-2", mean: 8.83, n: 6 }, { days: "14-28", mean: 7.64, n: 36 }] }] } } }] };
    render(<ControlAnalysesCard payload={payload} />);
    const fig = screen.getByTestId("figure-onoff_switches");
    expect(fig.textContent).toMatch(/the right side on, 2025-08-22/);
    expect(fig.textContent).toMatch(/8\.86 \(42\)/);
    expect(fig.textContent).toMatch(/7\.64 \(36\)/);
  });

  it("draws the carry-over test per current, marks the order, and says when only one order occurs", () => {
    const summ = (mean, n) => ({ mean, lo: null, hi: null, n_pairs: n, n_visits: n ? 1 : 0, n_lower: 0, n_higher: 0, n_same: 0 });
    const payload = { analyses: [{ key: "carry_over_ladder", title: "Up the ladder and down (carry-over)", what: "Rise against fall.",
      literature: LIT, n_runs: 1, snapshot: { run_at: "2026-09-25T10:00:00Z", data_from: "2025-07-16", data_through: "2026-09-24",
        settings: {}, reading: ["overall (NRS): 8 currents rated on both legs, 1 visits."],
        result: { n_visits: 30,
          pain: [{ item: "overall", words: "overall (NRS)", verdict: "one order", sentence: "only one order occurs",
            summary: { all: summ(0.12, 8), "falling after rising": summ(0.12, 8), "falling before rising": summ(null, 0) },
            by_side: { Left: summ(-0.75, 4), Right: summ(1.0, 4) },
            by_current: [
              { side: "Left", current_mA: 0.5, falling_first: false, n_pairs: 1, rising: 5, falling: 3.5, diff: -1.5, minutes_apart: 38.8 },
              { side: "Right", current_mA: 1.5, falling_first: false, n_pairs: 1, rising: 1.5, falling: 3, diff: 1.5, minutes_apart: 18 }] }],
          holds: [{ item: "overall", words: "overall (NRS)", on: true, mean: -0.06, lo: -0.26, hi: 0.27, n_pairs: 62, n_visits: 13,
            n_lower: 17, n_higher: 9, n_same: 36, minutes_median: 1 }],
          ladder: [{ source: "time domain voltage trace", pair: "ZERO_THREE_RIGHT", n_runs: 2, n_bands: 15, bands_higher: 11,
            bands_lower: 4, median_over_bands: 0.094, verdict: "one order",
            summary: { all: summ(0.2, 30), "falling after rising": summ(0.2, 30), "falling before rising": summ(null, 0) } }] } } }] };
    const { container } = render(<ControlAnalysesCard payload={payload} />);
    const fig = screen.getByTestId("figure-carry_over_ladder");
    expect(fig.textContent).toMatch(/every fall came after its rise/i);
    expect(fig.textContent).toMatch(/left -0\.75 \(4 currents\)/);
    const marks = [...fig.querySelectorAll("circle")];
    expect(marks.length).toBe(2);
    marks.forEach((m) => expect(m.getAttribute("fill")).toMatch(/^#[0-9A-Fa-f]{3,8}$/));
    expect(screen.getByTestId("carry-over-holds").textContent).toMatch(/-0\.06/);
    expect(screen.getByTestId("carry-over-holds").textContent).toMatch(/62/);
    const ladder = screen.getByTestId("carry-over-ladder-power");
    expect(ladder.textContent).toMatch(/R 0-3/);
    expect(ladder.textContent).toMatch(/\+9\.4%/);
    expect(container.textContent).not.toMatch(/undefined|NaN/);
  });

  it("draws the regression-to-mean check with its block averages and comparisons, marks in hex colours, no text under 11 px", () => {
    const payload = { analyses: [{ key: "regression_to_mean", title: "Regression to the mean at one setting",
      what: "At the setting delivered most often in one rate/pulse-width group.", literature: LIT, n_runs: 1,
      snapshot: { run_at: "2026-09-25T12:00:00Z", data_from: "2025-07-16", data_through: "2026-09-24",
        settings: { target_stratum: { freq_hz: 55, pw_us_Left: 60, pw_us_Right: 160 } },
        reading: ["Target setting 1.6/1.2 mA (8 of 19 setting-periods in this group): block 0: +1.51 (n 3, se 0.12); block 1: +0.53 (n 3, se 0.24); block 2: -0.06 (n 2, se 1.50)."],
        result: {
          setting: { amp_mA_Left: 1.6, amp_mA_Right: 1.2 }, n_target: 8, n_other: 11, n_blocks: 3,
          target: { by_block: [{ block: 0, n: 3, mean: 1.51, se: 0.12 }, { block: 1, n: 3, mean: 0.53, se: 0.24 }, { block: 2, n: 2, mean: -0.06, se: 1.5 }],
            heterogeneity: { q: 30.2, p: 0.0006, grand_mean: 0.8, df: 2, reason: null },
            trend: { slope: -0.79, intercept: 1.4, reason: null } },
          other: { by_block: [{ block: 0, n: 4, mean: 0.9, se: 0.3 }, { block: 1, n: 4, mean: 0.6, se: 0.3 }, { block: 2, n: 3, mean: 0.5, se: 0.4 }],
            heterogeneity: { q: 1.1, p: 0.58, grand_mean: 0.67, df: 2, reason: null },
            trend: { slope: -0.2, intercept: 0.9, reason: null } },
          internal_comparison: { p_two_sided: 0.02, p_same_direction: 0.015, n_valid: 75000, n_total: 75582, q_real: 30.2, trend_real: -0.79, floor: "< 1.3e-05" },
          outside_comparison: { n_windows: 85, fraction_ge: 0.08, window_size: 8, q_real: 30.2 },
          extremity: { value: 3.4, block1_mean: 1.51, block1_se: 0.12, record_mean: 0.6, reason: null },
        } } }] };
    const { container } = render(<ControlAnalysesCard payload={payload} />);
    const fig = screen.getByTestId("figure-regression_to_mean");
    expect(fig.textContent).toMatch(/1\.6\/1\.2 mA/);
    expect(fig.textContent).toMatch(/2\.0% of splits/);
    const table = screen.getByTestId("regression-to-mean-comparisons");
    expect(table.textContent).toMatch(/8\.0% of runs elsewhere/);
    expect(table.textContent).toMatch(/\+3\.4 standard errors/);
    const marks = [...fig.querySelectorAll("circle, line, polyline")];
    expect(marks.length).toBeGreaterThan(0);
    marks.forEach((m) => {
      const a = m.tagName === "circle" ? "fill" : "stroke";
      expect(m.getAttribute(a)).toMatch(/^#[0-9A-Fa-f]{3,8}$/);
    });
    [...fig.querySelectorAll("text")].forEach((t) => {
      expect(Number(t.getAttribute("font-size"))).toBeGreaterThanOrEqual(11);
    });
    [...container.querySelectorAll("[style]")].forEach((el) => {
      const fs = el.style && el.style.fontSize;
      if (fs) expect(parseFloat(fs)).toBeGreaterThanOrEqual(11);
    });
    expect(container.textContent).not.toMatch(/undefined|NaN/);
  });

  it("says the regression-to-mean check has nothing to read when no setting-periods matched", () => {
    const payload = { analyses: [{ key: "regression_to_mean", title: "Regression to the mean at one setting",
      what: "At the setting delivered most often.", literature: LIT, n_runs: 1,
      snapshot: { run_at: "2026-09-25T12:00:00Z", data_from: "2025-07-16", data_through: "2026-09-24",
        settings: {}, reading: ["No setting-periods matched the target group; nothing to read."],
        result: { setting: null, reason: "no setting-periods matched the target group" } } }] };
    render(<ControlAnalysesCard payload={payload} />);
    expect(screen.getByTestId("figure-regression_to_mean").textContent).toMatch(/no setting-periods matched/i);
  });

  it("says an analysis has not been run yet rather than drawing nothing", () => {
    render(<ControlAnalysesCard payload={PAYLOAD} />);
    fireEvent.change(screen.getByLabelText("Control analysis"), { target: { value: "time_of_day" } });
    expect(screen.getByText(/Not run yet for this participant/)).toBeTruthy();
  });
});
