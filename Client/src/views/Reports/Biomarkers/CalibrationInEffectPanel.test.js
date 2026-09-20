/**
 * The Biomarkers page's bottom-right calibration panel draws the calibration IN EFFECT (decision
 * 212, the PI, 2026-09-20). Rendered against the REAL response for RCS08 captured that day
 * (`__fixtures__/rcs08_calibration_in_effect.json`, from `/api/queryPsdLsbConversionModel` after
 * the endpoint was repointed at the recipe in `routines/calibration.py`).
 *
 * WHAT WAS WRONG. Until now the panel drew the frozen June log-log model: per-band gain anchors
 * fitted on log power and per-channel slopes 0.85 / 0.52 -- not the constant the platform
 * converts with (345.59 LSB per uV^2 since decision 211), and a model no calculation has read
 * since 2026-06-28, under a caption that still called it the threshold estimator's fallback.
 *
 * Every number on the panel comes from the served payload; the component source carries no
 * calibration constant, so the day the constant moves again the panel cannot print a stale one.
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

import CalibrationInEffectPanel from "./CalibrationInEffectPanel";
import PsdLsbPanel from "views/Reports/ClosedLoopSim/PsdLsbPanel";
import payload from "./__fixtures__/rcs08_calibration_in_effect.json";

jest.mock("plotly.js-dist", () => ({
  react: jest.fn(), purge: jest.fn(), restyle: jest.fn(), relayout: jest.fn(), newPlot: jest.fn(),
}));
jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn() } }));
// eslint-disable-next-line import/first
import { SessionController } from "database/session-control";
// eslint-disable-next-line import/first
import Plotly from "plotly.js-dist";

const UID = "2e3c75c00d7f4f37b53a048d195f11da";
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

describe("the calibration-in-effect panel, on the served RCS08 payload", () => {
  beforeEach(() => putResult(CL.conversionModel, UID, settingsKey({}), payload));

  test("names the constant in effect, its recipe and its fit, from the payload", async () => {
    render(wrap(<CalibrationInEffectPanel participantUid={UID} />));
    expect(await screen.findByText(/Calibration in effect/)).toBeInTheDocument();
    const text = document.body.textContent;
    // the transform constant, from `deployed.k`, with the recipe's own fit beside it
    expect(text).toMatch(/1 µV² = 345\.59 LSB/);
    expect(text).toMatch(/133 blocks/);
    expect(text).toMatch(/r = 0\.99/);
    expect(text).toMatch(/at least 3 s of signal and 6 device readings/);
    expect(text).toMatch(/5 MAD/);
    // the June reference the table reproduces, and how many blocks are new since
    expect(text).toMatch(/352\.62/);
    expect(text).toMatch(/through 2026-09-03/);
    // the composed bridge: the ratio in effect, the refit, the composed constant
    expect(text).toMatch(/4\.789/);
    expect(text).toMatch(/4\.755/);
    expect(text).toMatch(/1 device-µV² = 72\.16 LSB/);
    expect(text).toMatch(/composed/);
    // where the two constants are used on the platform
    expect(text).toMatch(/Biomarkers timeline/);
    expect(text).toMatch(/Closed-Loop/);
  });

  test("draws both figures on raw axes, never a logarithmic one", async () => {
    render(wrap(<CalibrationInEffectPanel participantUid={UID} />));
    await screen.findByText(/Calibration in effect/);
    expect(Plotly.react).toHaveBeenCalledTimes(2);
    Plotly.react.mock.calls.forEach(([, traces, layout]) => {
      Object.keys(layout).filter((k) => /^[xy]axis/.test(k)).forEach((k) => {
        expect(layout[k].type).not.toBe("log");
      });
      expect(traces.length).toBeGreaterThan(0);
    });
    // figure 1: the 170 blocks, kept blocks separated from gated and flagged ones, and the line
    const [, blockTraces] = Plotly.react.mock.calls[0];
    const nPoints = blockTraces.filter((t) => t.mode === "markers")
      .reduce((s, t) => s + t.x.length, 0);
    expect(nPoints).toBe(170);
    expect(blockTraces.some((t) => /kept/i.test(t.name))).toBe(true);
    expect(blockTraces.some((t) => /gated|flagged|excluded/i.test(t.name))).toBe(true);
    expect(blockTraces.some((t) => t.mode === "lines")).toBe(true);
    // figure 2: the bridge ratio per centre (21) with the ratio in effect as a line
    const [, bridgeTraces, bridgeLayout] = Plotly.react.mock.calls[1];
    expect(bridgeTraces.some((t) => t.x.length === 21)).toBe(true);
    expect((bridgeLayout.shapes || []).length + bridgeTraces.filter((t) => t.mode === "lines").length)
      .toBeGreaterThan(0);
  });

  test("retired words are gone", async () => {
    render(wrap(<CalibrationInEffectPanel participantUid={UID} />));
    await screen.findByText(/Calibration in effect/);
    const text = document.body.textContent;
    ["frozen", "common slope", "gain anchor", "Iglewicz", "conversion model", "fallback",
     "deployment lookup", "log"].forEach((w) => {
      expect(text.toLowerCase()).not.toContain(w.toLowerCase());
    });
  });
});

test("with no payload the panel prints the server's reason and no number", async () => {
  putResult(CL.conversionModel, UID, settingsKey({}), { available: false, reason: "no calibration table for TEST01" });
  render(wrap(<CalibrationInEffectPanel participantUid={UID} />));
  expect(await screen.findByText(/no calibration table for TEST01/)).toBeInTheDocument();
  expect(document.body.textContent).not.toMatch(/\d{3}\.\d{2}/);
});

describe("the committed band's own refit (bottom-left) draws the constant in effect beside its own", () => {
  const BC = { contact: "ZERO_THREE_LEFT", center_freq_hz: 9.77, bandwidth_hz: 5.0 };
  const REQ = { LabelMetric: "nrs" };
  const served = {
    available: true, n_pairs: 40, spearman: 0.9, k_lsb_per_uv2: 300.0, uv2_per_lsb: 1 / 300.0,
    k_in_effect: payload.deployed.k, resid_log_sigma_fold: 1.2, loglog_slope: 0.98,
    loglog_slope_ci: [0.9, 1.05], slope_consistent_with_unity: true,
    scatter: { psd_uv2: [0.5, 1, 2, 4], lsb: [150, 300, 600, 1200] },
    center_hz_mode: "fixed 9.77 Hz", band_width_hz: 5.0,
  };
  test("prints the served constant and draws its line", async () => {
    putResult(CL.psdLsb, UID, settingsKey({ Channel: BC.contact, CenterHz: 9.77, BandWidthHz: 5.0,
      MatchWindowH: 1.0, ...REQ }), served);
    render(wrap(<PsdLsbPanel participantUid={UID} bandCandidate={BC} requestParams={REQ} />));
    expect(await screen.findByText(/1 µV² ≈ 300 LSB/)).toBeInTheDocument();
    expect(document.body.textContent).toMatch(/in effect: 1 µV² = 345\.59 LSB/);
    const [, traces] = Plotly.react.mock.calls[0];
    expect(traces.some((t) => t.mode === "lines" && /in effect/.test(t.name || t.hovertemplate || ""))).toBe(true);
  });
});

describe("neither component source carries a calibration constant", () => {
  const here = path.join(__dirname, "CalibrationInEffectPanel.js");
  const left = path.join(__dirname, "..", "ClosedLoopSim", "PsdLsbPanel.js");
  test.each([["CalibrationInEffectPanel.js", here], ["PsdLsbPanel.js", left]])("%s", (_n, file) => {
    const code = fs.readFileSync(file, "utf8").split("\n").filter((l) => !/^\s*(\/\/|\*)/.test(l)).join("\n");
    ["345.59", "349.10", "352.62", "72.16", "72.90", "73.63", "4.789", "4.755"].forEach((tok) => {
      expect(code).not.toContain(tok);
    });
  });
});
