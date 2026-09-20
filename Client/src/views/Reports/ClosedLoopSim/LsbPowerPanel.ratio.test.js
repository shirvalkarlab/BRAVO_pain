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
    cutpoint={{ threshold: 1.5, matchDir: "prior" }} onLsbThreshold={() => {}} deploymentReport={{ data: null }} />));
  expect(await screen.findByText(/LSB threshold/)).toBeInTheDocument();
  const text = document.body.textContent;
  expect(text).toMatch(/1\.08× the constant in effect \(1 µV² = 345\.59 LSB\)/);
  expect(text).toMatch(/independent check of the constant in effect/);
  expect(text).not.toMatch(/0\.01 rule|rule of thumb/);
});

test("the card source carries no calibration constant", () => {
  const code = fs.readFileSync(path.join(__dirname, "LsbPowerPanel.js"), "utf8")
    .split("\n").filter((l) => !/^\s*(\/\/|\*)/.test(l)).join("\n");
  ["345.59", "352.62", "72.16", "0.01 rule"].forEach((tok) => expect(code).not.toContain(tok));
});
