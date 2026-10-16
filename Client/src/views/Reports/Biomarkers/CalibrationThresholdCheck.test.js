/**
 * The calibration panel shows the threshold band-power streams' check of the PSD->LSB route (the PI,
 * 2026-10-05: "wired to sanity check the PSD->LSB calibration including the visuals in biomarker
 * page", decision 447): one status line beside the two constants, and in the fold a figure of each
 * stream's measured LSB against the LSB the bridge predicts from a same-export device spectrum.
 * Every number comes from the served `threshold_check`; none is written in the component.
 */
import "@testing-library/jest-dom";
import React from "react";
import { render, screen } from "@testing-library/react";
import { invalidateAll, putResult, settingsKey } from "database/resultCache";
import { CL } from "views/Reports/moduleCacheKeys";
import { SessionController } from "database/session-control";
import Plotly from "plotly.js-dist";
import { wrap } from "testUtils/render";
import CalibrationInEffectPanel from "./CalibrationInEffectPanel";
import base from "./__fixtures__/rcs08_calibration_in_effect.json";

jest.mock("plotly.js-dist", () => ({
  react: jest.fn(), purge: jest.fn(), restyle: jest.fn(), relayout: jest.fn(), newPlot: jest.fn(),
}));
jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn() } }));

const UID = "2e3c75c00d7f4f37b53a048d195f11da";
const CHECK = {
  available: true, n_streams: 76,
  by_source: { "signal check": { n: 74, median_ratio: 1.002, ratio_p10_p90: [0.535, 1.844] },
    montage: { n: 60, median_ratio: 1.066, ratio_p10_p90: [0.506, 1.813] } },
  rows: [{ time: 1753900000, side: "RIGHT", channel: "ZERO_TWO_RIGHT", center_hz: 23.44, measured_lsb: 62,
    predicted_lsb: { "signal check": 65.1, montage: 70.4 }, upper_threshold: 87, lower_threshold: 56 }],
};

beforeEach(() => {
  invalidateAll("test setup");
  SessionController.query.mockReset();
  SessionController.query.mockImplementation(() => Promise.resolve({ data: { boot_token: "boot-1" } }));
  Plotly.react.mockReset();
});

test("one status line names the streams and the median measured ÷ predicted per source", async () => {
  putResult(CL.conversionModel, UID, settingsKey({}), { ...base, threshold_check: CHECK });
  render(wrap(<CalibrationInEffectPanel participantUid={UID} />));
  const line = await screen.findByTestId("threshold-check-status");
  expect(line.textContent).toBe(
    "Checked on 76 threshold streams: measured ÷ predicted LSB 1.00 (signal check, n=74), 1.07 (montage, n=60)");
});

test("without threshold streams the status says so", async () => {
  putResult(CL.conversionModel, UID, settingsKey({}),
    { ...base, threshold_check: { available: false, reason: "no threshold band-power streams are stored for this participant" } });
  render(wrap(<CalibrationInEffectPanel participantUid={UID} />));
  const line = await screen.findByTestId("threshold-check-status");
  expect(line.textContent).toBe("No threshold check: no threshold band-power streams are stored for this participant");
});
