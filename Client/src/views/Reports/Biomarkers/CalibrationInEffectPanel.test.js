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
    // ruling C1 (the PI, 2026-09-21): the constant's uncertainty in raw units, from the payload
    expect(text).toMatch(/95% interval 339\.4–350\.7/);
    expect(text).toMatch(/1 MAD of the ratio is 18\.6 LSB per µV² \(5% of the constant\)/);
    expect(text).toMatch(/does not change with the power level over the 133 kept blocks/);
    expect(text).toMatch(/Spearman's rho -0\.02, p = 0\.78/);
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
    // the blocks figure draws the 1-MAD band either side of the line in effect
    const [, blockTraces] = Plotly.react.mock.calls[0];
    const band = blockTraces.filter((t) => /1 MAD/.test(t.name || ""));
    expect(band.length).toBe(2);
    band.forEach((t) => { expect(t.mode).toBe("lines"); expect(t.line.dash).toBe("dot"); });
    [1, 2].forEach(() => {
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

describe("the committed band's own refit panel is gone (the PI, 2026-09-21: redundant with this one)", () => {
  test("no source, no cache slot, no request to its endpoint", () => {
    const fs = require("fs");
    expect(fs.existsSync(path.join(__dirname, "..", "ClosedLoopSim", "PsdLsbPanel.js"))).toBe(false);
    expect(CL.psdLsb).toBeUndefined();
    const page = fs.readFileSync(path.join(__dirname, "index.js"), "utf8");
    expect(page).not.toMatch(/PsdLsbPanel|queryPsdLsbConversion\b|loadBandCandidate/);
  });
});

describe("neither component source carries a calibration constant", () => {
  const here = path.join(__dirname, "CalibrationInEffectPanel.js");
  test.each([["CalibrationInEffectPanel.js", here]])("%s", (_n, file) => {
    const code = fs.readFileSync(file, "utf8").split("\n").filter((l) => !/^\s*(\/\/|\*)/.test(l)).join("\n");
    ["345.59", "349.10", "352.62", "72.16", "72.90", "73.63", "4.789", "4.755"].forEach((tok) => {
      expect(code).not.toContain(tok);
    });
  });
});
