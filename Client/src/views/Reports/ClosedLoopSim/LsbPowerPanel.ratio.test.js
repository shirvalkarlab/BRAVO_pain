/**
 * The "LSB & power" card's µV²/LSB line compares the independent pairing with the constant in
 * effect, read from the served payload (decision 214). Until 2026-09-20 it printed "N× the 0.01
 * rule": a rule of thumb nothing else on the platform used, on a ratio the backend had computed
 * with the stored trace scaled by 0.146 as if it were ADC counts.
 */
import "@testing-library/jest-dom";
import fs from "fs";
import path from "path";
import React from "react";
import { render, screen } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";

import theme from "assets/theme";
import { PlatformContextProvider } from "context";
import { invalidateAll, putResult, settingsKey } from "database/resultCache";
import { CL } from "views/Reports/moduleCacheKeys";
import LsbPowerPanel from "./LsbPowerPanel";

jest.mock("plotly.js-dist", () => ({
  react: jest.fn(), purge: jest.fn(), restyle: jest.fn(), relayout: jest.fn(), newPlot: jest.fn(),
}));
// eslint-disable-next-line import/first
import Plotly from "plotly.js-dist";
jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn() } }));
// eslint-disable-next-line import/first
import { SessionController } from "database/session-control";

const UID = "2e3c75c00d7f4f37b53a048d195f11da";
const BC = { contact: "ONE_THREE_LEFT", center_freq_hz: 24.5, bandwidth_hz: 5.0 };
const REQ = { LabelMetric: "nrs" };
const wrap = (ui) => (
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>
);

beforeEach(() => {
  invalidateAll("test setup");
  SessionController.query.mockReset();
  SessionController.query.mockImplementation(() => Promise.resolve({ data: { boot_token: "boot-1" } }));
  Plotly.react.mockReset();
});

test("the ratio line names the constant in effect from the payload and not a rule of thumb", async () => {
  putResult(CL.lsbPower, UID, settingsKey({ Channel: BC.contact, CenterHz: 24.5, BandWidthHz: 5.0,
    MatchDirection: "prior", Cutpoint: 1.5, ...REQ }), {
    available: true,
    lsb_ratio: { available: true, n: 218, median: 0.00312, cv: 0.33, confidence: "high",
      constant_in_effect_uv2_per_lsb: 1 / 345.59, fold_of_constant_in_effect: 1.08 },
    threshold_lsb: { available: false, reason: "none in this test" },
    power: { available: false, reason: "none in this test" },
    threshold_modes: null,
  });
  render(wrap(<LsbPowerPanel participantUid={UID} bandCandidate={BC} requestParams={REQ}
    cutpoint={{ threshold: 1.5, matchDir: "prior" }} onLsbThreshold={() => {}} />));
  // Title changed on purpose by decision 302: the panel says where the cut-point sits in device
  // units, never a "threshold" to program.
  // The title is a question since the redesign of 2026-09-26.
  expect(await screen.findByText(/Switching point in device units/)).toBeInTheDocument();
  const text = document.body.textContent;
  expect(text).toMatch(/1\.08× the constant in effect \(1 µV² = 345\.59 LSB\)/);
  expect(text).toMatch(/independent check, not a programmed value/);
  expect(text).not.toMatch(/0\.01 rule|rule of thumb/);
});

// The PI, 2026-09-26: the toolbar restored so reviewers can save figures for the deployment
// record -- but only on the figure that had one at commit d54bc614 (the power-vs-sample-size
// curve); the switching-point/device-readings gauge below it never carried a toolbar and stays off.
test("the power-vs-sample-size curve has the restored toolbar; the switching-point gauge stays off", async () => {
  putResult(CL.lsbPower, UID, settingsKey({ Channel: BC.contact, CenterHz: 24.5, BandWidthHz: 5.0,
    MatchDirection: "prior", Cutpoint: 1.5, ...REQ }), {
    available: true,
    lsb_ratio: { available: false, reason: "none in this test" },
    threshold_lsb: { available: true, upper_lsb: 141.7, estimated: false, method: "anchored",
      percentile: 62, device_lsb_p10: 40, device_lsb_median: 90, device_lsb_p90: 200 },
    power: { available: true, curve: { n: [10, 20, 40, 80], power: [0.2, 0.4, 0.7, 0.9] },
      target_power: 0.80, more_data_needed: true, n_ratings_current: 30, power_current: 0.5,
      n_ratings_needed: 60, design_effect: 1.0 },
    threshold_modes: null,
  });
  render(wrap(<LsbPowerPanel participantUid={UID} bandCandidate={BC} requestParams={REQ}
    cutpoint={{ threshold: 1.5, matchDir: "prior" }} onLsbThreshold={() => {}} />));
  await screen.findByText(/Switching point in device units/);
  expect(Plotly.react).toHaveBeenCalled();
  const calls = Plotly.react.mock.calls;
  // the power curve names its y-axis "chance of detecting a real link with pain (%)"
  const powerCall = calls.find(([, , layout]) => /chance of detecting a real link/.test(
    (layout.yaxis && layout.yaxis.title && layout.yaxis.title.text) || ""));
  expect(powerCall).toBeDefined();
  expect(powerCall[3].displayModeBar).not.toBe(false);
  // the switching-point gauge names its x-axis "band power (device units, LSB)"
  const gaugeCall = calls.find(([, , layout]) => /band power \(device units, LSB\)/.test(
    (layout.xaxis && layout.xaxis.title && layout.xaxis.title.text) || ""));
  expect(gaugeCall).toBeDefined();
  expect(gaugeCall[3].displayModeBar).toBe(false);
});

test("the card source carries no calibration constant", () => {
  const code = fs.readFileSync(path.join(__dirname, "LsbPowerPanel.js"), "utf8")
    .split("\n").filter((l) => !/^\s*(\/\/|\*)/.test(l)).join("\n");
  ["345.59", "352.62", "72.16", "0.01 rule"].forEach((tok) => expect(code).not.toContain(tok));
});

test("the panel never offers a value to program, and the recommended-vs-programmed box is gone (decision 302)", () => {
  const code = fs.readFileSync(path.join(__dirname, "LsbPowerPanel.js"), "utf8")
    .split("\n").filter((l) => !/^\s*(\/\/|\*)/.test(l) && !/\{\/\*/.test(l)).join("\n");
  expect(code).not.toMatch(/THRESHOLD TO PROGRAM/);
  expect(code).not.toMatch(/RECOMMENDED vs PROGRAMMED/);
  expect(code).not.toMatch(/recommended_vs_programmed/);
  expect(code).toMatch(/not a value to program/);
});
