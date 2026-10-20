/**
 * The matching panel's notes are folded away (the PI, 2026-10-07: the notes under every slider spread
 * the panel out), all shown or hidden by ONE switch at the top of the panel (the PI, same day: a "?"
 * per control meant clicking each one), and the grey
 * caption that repeated the readout line under "Readings available to split into high and low pain"
 * is gone in matched mode.
 */
import "@testing-library/jest-dom";
import fs from "fs";
import path from "path";
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { wrap } from "testUtils/render";
import { ControlLabel, ControlNotesProvider, NotesSwitch } from "./MatchWindowBand";

jest.mock("plotly.js-dist", () => ({
  react: jest.fn(), purge: jest.fn(), restyle: jest.fn(), relayout: jest.fn(), newPlot: jest.fn(),
}));

function Two() {
  const [shown, setShown] = React.useState(false);
  return (
    <ControlNotesProvider value={shown}>
      <NotesSwitch shown={shown} setShown={setShown} />
      <ControlLabel note="How far from a report a reading may be.">{"Match window"}</ControlLabel>
      <ControlLabel note="Ratings above the median are high.">{"Split"}</ControlLabel>
    </ControlNotesProvider>
  );
}

test("one switch shows every note and hides them all again; no per-control button", () => {
  render(wrap(<Two />));
  expect(screen.getByText("Match window")).toBeInTheDocument();
  expect(screen.queryAllByTestId("control-note")).toHaveLength(0);
  expect(screen.queryByTestId("control-note-toggle")).toBeNull();
  fireEvent.click(screen.getByTestId("control-notes-switch"));
  expect(screen.getAllByTestId("control-note")).toHaveLength(2);
  expect(screen.getByTestId("control-notes-switch")).toHaveTextContent("Hide explanations");
  fireEvent.click(screen.getByTestId("control-notes-switch"));
  expect(screen.queryAllByTestId("control-note")).toHaveLength(0);
  expect(screen.getByTestId("control-notes-switch")).toHaveTextContent("Show explanations");
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
