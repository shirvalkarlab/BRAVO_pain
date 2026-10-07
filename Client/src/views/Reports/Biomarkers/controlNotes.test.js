/**
 * The matching panel's notes are folded behind each control's "?" (the PI, 2026-10-07: the notes
 * under every slider spread the panel out and pushed the high / low preview down), and the grey
 * caption that repeated the readout line under "Readings available to split into high and low pain"
 * is gone in matched mode.
 */
import "@testing-library/jest-dom";
import fs from "fs";
import path from "path";
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { wrap } from "testUtils/render";
import { ControlLabel } from "./MatchWindowBand";

jest.mock("plotly.js-dist", () => ({
  react: jest.fn(), purge: jest.fn(), restyle: jest.fn(), relayout: jest.fn(), newPlot: jest.fn(),
}));

test("the note is hidden until the ? is clicked, and folds again", () => {
  render(wrap(<ControlLabel note="How far from a report a reading may be.">{"Match window"}</ControlLabel>));
  expect(screen.getByText("Match window")).toBeInTheDocument();
  expect(screen.queryByText("How far from a report a reading may be.")).toBeNull();
  fireEvent.click(screen.getByTestId("control-note-toggle"));
  expect(screen.getByText("How far from a report a reading may be.")).toBeInTheDocument();
  fireEvent.click(screen.getByTestId("control-note-toggle"));
  expect(screen.queryByText("How far from a report a reading may be.")).toBeNull();
});

test("no note, no ?", () => {
  render(wrap(<ControlLabel>{"Clinic sheet scores"}</ControlLabel>));
  expect(screen.queryByTestId("control-note-toggle")).toBeNull();
});

test("every note in the panel and its extra options is folded", () => {
  const read = (f) => fs.readFileSync(path.join(__dirname, f), "utf8");
  expect(read("MatchWindowBand.js")).not.toMatch(/sx=\{NOTE_SX\}/);
  expect((read("index.js").match(/<ControlLabel/g) || []).length).toBe(5);
});

test("the grey caption that repeated the readout is not drawn in matched mode", () => {
  const code = fs.readFileSync(path.join(__dirname, "BinarizationPreview.js"), "utf8");
  expect(code).toMatch(/\{matchedMode \? null : \(\s*<MDTypography variant="caption" sx=\{\{ \.\.\.TYPE\.body, color: T\.ink3 \}\}>\s*\{headerCaption\}/);
});
