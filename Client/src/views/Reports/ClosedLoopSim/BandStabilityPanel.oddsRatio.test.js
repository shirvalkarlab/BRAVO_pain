/**
 * P-03 (June audit items [0] and [22], approved by the PI 2026-09-25).
 *
 * (a) The odds ratio in each stimulation state is printed WITH its 95% interval, in the open, on the
 *     stability card -- the one place on the page the live answer for the chosen band reaches. The
 *     band identity card's row, which reads a band file and so printed "not reported" for every band
 *     chosen on the grid, says where the numbers are instead.
 * (b) The card says how many pain reports had samples on both sides of a change of current, and
 *     that each is now counted once, in the state of its first sample.
 */
import fs from "fs";
import path from "path";
import React from "react";
import { render as rtlRender } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";
import theme from "assets/theme";
import { PlatformContextProvider } from "context";

import BandStabilityPanel from "./BandStabilityPanel";
import { fmtOddsRatioWithInterval } from "./deployFormat";

const text = (ui) => rtlRender(
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>,
).container.textContent;

const PER_STATE = {
  "stimulation off": { odds_ratio: 1.2214, low: 0.679, high: 2.199, n: 60 },
  "low current": { odds_ratio: 0.9048, low: 0.554, high: 1.477, n: 80 },
  "high current": { odds_ratio: null, low: null, high: null, n: 0 },
};
const RAN = {
  answer: "cannot tell", test_ran: true, band_center_hz: 24.5, band_width_hz: 5,
  odds_ratio_per_state: PER_STATE,
  odds_ratio_interval_method: "95% Wald interval from each state's own logistic fit",
  n_reports_split_across_states: 3, n_reports_split_across_weeks: 0,
};

describe("the odds ratio in each stimulation state carries its interval", () => {
  it("formats one odds ratio with its interval, without one, and when there is none", () => {
    expect(fmtOddsRatioWithInterval(1.2214, 0.679, 2.199)).toBe("1.22 (95% interval 0.68 to 2.20)");
    expect(fmtOddsRatioWithInterval(1.2214, null, null)).toBe("1.22 (no interval stored with it)");
    expect(fmtOddsRatioWithInterval(null, null, null)).toBe("could not be estimated");
  });

  it("prints every state's odds ratio beside its interval, in the open", () => {
    const t = text(<BandStabilityPanel stability={RAN} />);
    expect(t).toMatch(/Odds ratio per standard deviation of band power, in each stimulation state/);
    expect(t).toMatch(/stimulation off: 1\.22 \(95% interval 0\.68 to 2\.20\), 60 measurements/);
    expect(t).toMatch(/low current: 0\.90 \(95% interval 0\.55 to 1\.48\), 80 measurements/);
    expect(t).toMatch(/high current: could not be estimated, 0 measurements/);
    expect(t).toMatch(/95% Wald interval from each state's own logistic fit/);
  });

  it("says how many pain reports straddled a change of current and where each now counts", () => {
    expect(text(<BandStabilityPanel stability={RAN} />)).toMatch(
      /3 pain reports had samples recorded on both sides of a change of current; each is counted once, in the state of its first sample\./);
    // none split: said as none, not left out
    expect(text(<BandStabilityPanel stability={{ ...RAN, n_reports_split_across_states: 0 }} />))
      .toMatch(/No pain report had samples on both sides of a change of current\./);
  });

  it("an answer stored before the interval existed says so rather than inventing one", () => {
    const old = { ...RAN, odds_ratio_interval_method: null, n_reports_split_across_states: null,
      odds_ratio_per_state: { "stimulation off": { odds_ratio: 1.2214, low: null, high: null, n: 60 } } };
    const t = text(<BandStabilityPanel stability={old} />);
    expect(t).toMatch(/stimulation off: 1\.22 \(no interval stored with it\)/);
    expect(t).not.toMatch(/pain reports? had samples/);
  });

  it("prints no odds ratios when the test did not run", () => {
    expect(text(<BandStabilityPanel stability={{ answer: "not tested", test_ran: false }} />))
      .not.toMatch(/Odds ratio per standard deviation/);
  });
});

describe("the band identity card's per-state row", () => {
  // The band identity moved out of the page file into its own, inside the decision card's Details
  // fold (decision 302); the row is unchanged.
  const src = fs.readFileSync(path.join(__dirname, "BandCandidateIdentity.js"), "utf8");
  it("prints each state's interval when the band file carries one, and says where they are when not", () => {
    expect(src).toMatch(/Odds ratio per stimulation state \(off, low, high current\)/);
    expect(src).toMatch(/fmtOddsRatioWithInterval\(ev\.or_by_era\[t\]/);
    expect(src).toMatch(/this band's own, with intervals, are on the "\s*\+ "stability card above"/);
    expect(src).not.toMatch(/label="Odds ratio per era"/);
  });
});
