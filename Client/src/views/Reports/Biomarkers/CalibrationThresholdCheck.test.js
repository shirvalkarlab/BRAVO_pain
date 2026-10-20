// Uses independently authored synthetic response fixtures; no participant-validation claim.
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
import base from "./__fixtures__/synthetic_calibration_in_effect.json";

jest.mock("plotly.js-dist", () => ({
  react: jest.fn(), purge: jest.fn(), restyle: jest.fn(), relayout: jest.fn(), newPlot: jest.fn(),
}));
jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn() } }));

const UID = "synthetic-biomarker-subject";
// Independent synthetic response fields: two sources, distinct medians and counts.
const CHECK = {
  available:true,n_streams:3,
  by_source:{"signal check":{n:3,median_ratio:1.2,ratio_p10_p90:[1.1,1.3]},montage:{n:2,median_ratio:.8,ratio_p10_p90:[.7,.9]}},
  rows:[{time:946684800,side:"RIGHT",channel:"ZERO_TWO_RIGHT",center_hz:15.5,measured_lsb:60,predicted_lsb:{"signal check":50,montage:75},upper_threshold:80,lower_threshold:40}],
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
    "Checked on 3 threshold streams: measured ÷ predicted LSB 1.20 (signal check, n=3), 0.80 (montage, n=2)");
});

test("without threshold streams the status says so", async () => {
  putResult(CL.conversionModel, UID, settingsKey({}),
    { ...base, threshold_check: { available: false, reason: "no threshold band-power streams are stored for this participant" } });
  render(wrap(<CalibrationInEffectPanel participantUid={UID} />));
  const line = await screen.findByTestId("threshold-check-status");
  expect(line.textContent).toBe("No threshold check: no threshold band-power streams are stored for this participant");
});
