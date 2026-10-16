/**
 * The recording timeline's detail panel (item P-18, the PI's go-ahead 2026-10-06).
 *
 * Pinned: nothing is fetched until a mark is clicked; the request carries the clicked mark's own
 * pair, kind and time; what the mark lacks is said in words, never drawn as an empty axis; the
 * trace note says when a long trace was thinned; and the timeline removes its click listener with
 * every redraw (decision 91), the panel sits under the plot, and the plot's width is untouched.
 */
import "@testing-library/jest-dom";
import fs from "fs";
import path from "path";
import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { SessionController } from "database/session-control";
import { wrap } from "testUtils/render";
import TimelineDetailPanel, { detailHeading, missingLines, pairLabel, traceNote, zeroRunsLine } from "./TimelineDetailPanel";

jest.mock("plotly.js-dist", () => ({
  react: jest.fn(), purge: jest.fn(), restyle: jest.fn(), relayout: jest.fn(), newPlot: jest.fn(),
}));
jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn() } }));

const SEL = { Channel: "ZERO_AND_THREE_LEFT_RING", Dtype: "psd", Product: "montage_psd", TStart: 1760000000 };
const DETAIL = {
  available: true, pair: "ZERO_THREE_LEFT", dtype: "psd", product: "montage_psd", t_start: 1760000000,
  trace: { unit: "µV", fs: 250, t0: 1760000000, n: 5000, dur_s: 20, every_nth: 1, envelope: false,
    x_s: null, y: [1, 2, 3] },
  psd: { unit: "µVp", freq: [0, 1], mag: [1, 2], peak_hz: 12.7, artifact_status: null, source: "montage or survey" },
  band_power: null,
  missing: { band_power: "the device sensed no band power on this pair within 12 h" },
};

beforeEach(() => { SessionController.query.mockReset(); });

test("the pair is named as the pages name it", () => {
  expect(pairLabel("ZERO_THREE_LEFT")).toBe("L 0⁻3⁺");
  expect(pairLabel("ONE_THREE_RIGHT")).toBe("R 1⁻3⁺");
});

test("the heading says pair, kind and time", () => {
  expect(detailHeading(SEL, DETAIL)).toMatch(/^L 0⁻3⁺ · montage or survey · /);
});

test("what a mark lacks is said in words", () => {
  expect(missingLines(DETAIL)).toEqual(["Band power: the device sensed no band power on this pair within 12 h."]);
  expect(missingLines({ missing: { trace: "no voltage trace: the device keeps none for a patient event" } }))
    .toEqual(["Voltage trace: no voltage trace: the device keeps none for a patient event."]);
});

test("a thinned trace says how it was thinned", () => {
  expect(traceNote({ n: 225000, fs: 250, dur_s: 900, envelope: true, every_nth: 8 }))
    .toBe("225,000 samples, 250 per second, 15.0 min; drawn as the lowest and highest of every 8 samples");
  expect(traceNote({ n: 5000, fs: 250, dur_s: 20, envelope: false, every_nth: 1 }))
    .toBe("5,000 samples, 250 per second, 20 s");
});

test("nothing is fetched until a mark is clicked", () => {
  render(wrap(<TimelineDetailPanel participantUid="u" selection={null} onClose={() => {}} />));
  expect(SessionController.query).not.toHaveBeenCalled();
  expect(screen.queryByTestId("timeline-detail-panel")).toBeNull();
});

test("a click asks for that mark and draws what came back", async () => {
  SessionController.query.mockResolvedValue({ data: DETAIL });
  render(wrap(<TimelineDetailPanel participantUid="u" selection={SEL} onClose={() => {}} />));
  expect(SessionController.query).toHaveBeenCalledWith("/api/queryTimelineDetail", { ParticipantId: "u", ...SEL });
  await waitFor(() => expect(screen.getByTestId("detail-trace")).toBeInTheDocument());
  expect(screen.getByTestId("detail-psd")).toBeInTheDocument();
  expect(screen.queryByTestId("detail-band-power")).toBeNull();
  expect(screen.getByText(/Band power: the device sensed no band power/)).toBeInTheDocument();
  expect(screen.getByText(/nothing here is matched to pain/)).toBeInTheDocument();
});

describe("the timeline's side", () => {
  const code = fs.readFileSync(path.join(__dirname, "BiomarkerDataTimeline.js"), "utf8");
  test("the click listener is removed with every redraw", () => {
    expect(code).toMatch(/gd\.on\("plotly_click", onClick\)/);
    expect(code).toMatch(/gd\.removeListener\("plotly_click", onClick\)/);
  });
  test("the panel sits under the plot, which keeps its full width", () => {
    const i = code.indexOf('<div ref={ref} style={{ width: "100%" }} />');
    expect(i).toBeGreaterThan(0);
    expect(code.indexOf("<TimelineDetailPanel", i)).toBeGreaterThan(i);
  });
  test("every kind of mark registers what it stands for", () => {
    ["Dtype: \"timedomain\"", "Dtype: \"psd\"", "Product: \"timeline_lsb\"", "Product: \"streaming_lsb\""]
      .forEach((s) => expect(code).toContain(s));
  });
});

test("the line under the timeline names the runs left out for reading 0 (decision 462)", () => {
  expect(zeroRunsLine({})).toBe("");
  expect(zeroRunsLine({ ZERO_TWO_LEFT: 27, ZERO_THREE_LEFT: 11, ZERO_THREE_RIGHT: 5 }))
    .toBe("Streaming runs reading 0 throughout, not counted as band power: L 0⁻2⁺ 27, L 0⁻3⁺ 11, R 0⁻3⁺ 5");
});
