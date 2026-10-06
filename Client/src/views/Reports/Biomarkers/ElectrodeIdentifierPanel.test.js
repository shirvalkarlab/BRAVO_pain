/**
 * The electrode identifier check in the Biomarkers page's bottom fold (the PI, 2026-10-06).
 *
 * Pinned: every headline is built from the payload's device rankings, per side and group; a run
 * the device could not separate is said so, never shown as ranked; nothing is fetched until the
 * fold is opened; the figure draws the device's own PSD on linear axes with the selected frequency
 * marked, and a flagged artefact is drawn dotted.
 */
import "@testing-library/jest-dom";
import React from "react";
import { render, screen } from "@testing-library/react";
import Plotly from "plotly.js-dist";
import { invalidateAll, putResult, settingsKey } from "database/resultCache";
import { SessionController } from "database/session-control";
import { BM } from "views/Reports/moduleCacheKeys";
import { wrap } from "testUtils/render";
import ElectrodeIdentifierPanel, { headline, rankingRows, runLine } from "./ElectrodeIdentifierPanel";

jest.mock("plotly.js-dist", () => ({
  react: jest.fn(), purge: jest.fn(), restyle: jest.fn(), relayout: jest.fn(), newPlot: jest.fn(),
}));
jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn() } }));

const UID = "u-test";
const FREQ = [0, 0.98, 1.95, 2.93];
const el = (electrode, ranking, extra = {}) => ({
  electrode, ranking, selected_hz: 11.72, peak_hz: 11.72, peak_uvrms: 1.2, artifact: false,
  freq: FREQ, uvp: [0.5, 0.4, 0.3, 0.2], ...extra,
});
const T0 = Date.UTC(2025, 6, 16, 18) / 1000;
const runs = [
  { t: T0, side: "Left", group: "rings", run_unknown: false, reference: "11 (right lead)", n_channels: 4, psd: "with values",
    electrodes: [el("0", "highest"), el("1", "middle"), el("2", "lowest", { artifact: true }), el("3", "lowest")] },
  { t: T0 + 86400, side: "Right", group: "rings", run_unknown: false, reference: "3 (left lead)", n_channels: 4, psd: "entries without values",
    electrodes: ["8", "9", "10", "11"].map((e) => el(e, "insufficient separation", { uvp: [], freq: [] })) },
];
const summary = {
  "Left rings": { side: "Left", group: "rings", n_runs: 6, n_with_spectra: 3, n_run_unknown: 0, n_ranked: 6,
    n_insufficient_separation: 1, highest_counts: { 0: 6, 1: 2 }, most_often_highest: ["0"],
    selected_hz: { n: 6, median: 11.72, min: 3.91, max: 23.44 }, n_spectra_with_artifact: 3 },
  "Right rings": { side: "Right", group: "rings", n_runs: 5, n_with_spectra: 2, n_run_unknown: 0, n_ranked: 0,
    n_insufficient_separation: 3, highest_counts: {}, most_often_highest: [],
    selected_hz: { n: 0, median: null, min: null, max: null }, n_spectra_with_artifact: 0 },
};
const payload = { available: true, runs, summary, n_runs: 2, n_days: 2 };

beforeEach(() => {
  invalidateAll("test setup");
  SessionController.query.mockReset();
  SessionController.query.mockImplementation(() => Promise.resolve({ data: { boot_token: "boot-1" } }));
  Plotly.react.mockReset();
});

test("the headlines are built from the device's rankings, per side and group", () => {
  expect(headline(summary["Left rings"]))
    .toBe("Left rings: 0 ranked highest in 6 of 6 ranked runs, selected 3.9–23.4 Hz; insufficient signal separation in 1");
  expect(headline(summary["Right rings"]))
    .toBe("Right rings: never ranked in 5 runs; insufficient signal separation in 3");
});

test("a run the device could not separate is said so, never shown as ranked", () => {
  const rows = rankingRows(runs);
  expect(rows.map((r) => r.highest)).toEqual(["0", "insufficient separation"]);
  expect(rows[1].middle).toBe("");
  expect(runLine(runs[0])).toBe("2025-07-16 · Left rings: 0 highest at 11.72 Hz");
  expect(runLine(runs[1])).toBe("2025-07-17 · Right rings: insufficient signal separation at 11.72 Hz");
});

test("nothing is fetched while the fold is closed", () => {
  render(wrap(<ElectrodeIdentifierPanel participantUid={UID} revealed={false} />));
  const urls = SessionController.query.mock.calls.map((c) => c[0]);
  expect(urls).not.toContain("/api/queryElectrodeIdentifierCheck");
  expect(Plotly.react).not.toHaveBeenCalled();
});

test("opened, it shows the status, headlines, ranking table and the chosen run's device PSD", async () => {
  putResult(BM.electrodeIdentifier, UID, settingsKey({}), payload);
  render(wrap(<ElectrodeIdentifierPanel participantUid={UID} revealed />));
  expect(await screen.findByText("Electrode identifier, stimulation off")).toBeInTheDocument();
  expect(screen.getByTestId("electrode-identifier-status").textContent)
    .toMatch(/2 runs on 2 visit days; 1 carry the device's PSD/);
  expect(screen.getAllByTestId("electrode-identifier-headline")).toHaveLength(2);
  expect(screen.getByTestId("electrode-identifier-table").textContent).toMatch(/insufficient separation/);
  expect(screen.getByTestId("electrode-identifier-run-line").textContent).toBe("2025-07-16 · Left rings: 0 highest at 11.72 Hz");
  expect(Plotly.react).toHaveBeenCalled();
  const [, traces, layout] = Plotly.react.mock.calls[Plotly.react.mock.calls.length - 1];
  expect(traces).toHaveLength(4);
  expect(traces[0].y).toEqual([0.5, 0.4, 0.3, 0.2]);                    // the device's values, unchanged
  expect(traces[2].line.dash).toBe("dot");                              // artefact flagged by the device
  expect(layout.yaxis.type).not.toBe("log");
  expect(layout.shapes[0].x0).toBe(11.72);                              // the selected frequency
});
