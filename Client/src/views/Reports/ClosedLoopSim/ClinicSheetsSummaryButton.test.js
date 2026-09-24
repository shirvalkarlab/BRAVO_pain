/**
 * The clinic-sheet ratings in the deployment summary, behind one red-outlined button (the PI,
 * 2026-09-24: "a toggle or an option to include the clinic sheets in the summary or not ... a simple
 * button with a red outline"). Off by default; when on, the summary's request -- which the ROC and
 * the other sign-off panels share -- carries the switch, so every number on the sheet uses the same
 * ratings. Remembered per participant in this browser.
 */
import "@testing-library/jest-dom";

jest.mock("plotly.js-dist", () => ({
  react: jest.fn(), purge: jest.fn(), restyle: jest.fn(), relayout: jest.fn(), newPlot: jest.fn(), toImage: jest.fn(),
}));
jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn() } }));
import { render as rtlRender, screen, fireEvent } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";
import theme from "assets/theme";
import { PlatformContextProvider } from "context";

import ClinicSheetsSummaryButton, { loadSummarySheets, saveSummarySheets } from "./ClinicSheetsSummaryButton";
import { summaryRequestParams } from "./candidateRequestParams";
import PAL from "./palette";

const wrap = (ui) => (
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>
);
const UID = "2e3c75c00d7f4f37b53a048d195f11da";

beforeEach(() => window.localStorage.clear());

test("it says plainly which ratings the summary uses, and has a red outline", () => {
  const { rerender } = rtlRender(wrap(<ClinicSheetsSummaryButton on={false} onToggle={() => {}} />));
  const btn = screen.getByRole("button", { name: /Clinic-sheet ratings in the summary: off/i });
  expect(btn).toHaveStyle(`border: 2px solid ${PAL.fail}`);
  rerender(wrap(<ClinicSheetsSummaryButton on onToggle={() => {}} />));
  expect(screen.getByRole("button", { name: /Clinic-sheet ratings in the summary: on/i })).toBeInTheDocument();
});

test("one click asks to flip it", () => {
  const onToggle = jest.fn();
  rtlRender(wrap(<ClinicSheetsSummaryButton on={false} onToggle={onToggle} />));
  fireEvent.click(screen.getByRole("button"));
  expect(onToggle).toHaveBeenCalledWith(true);
});

test("off by default, remembered per participant", () => {
  expect(loadSummarySheets(UID)).toBe(false);
  saveSummarySheets(UID, true);
  expect(loadSummarySheets(UID)).toBe(true);
  expect(loadSummarySheets("another")).toBe(false);
});

test("the summary request carries the switch only when it is on, beside the band's own settings", () => {
  const bc = { label: {}, grid_settings: { sweep_metric: "left_leg_vas" } };
  expect(summaryRequestParams(bc, false)).toEqual({ LabelMetric: "left_leg_vas" });
  expect(summaryRequestParams(bc, true)).toEqual({ LabelMetric: "left_leg_vas", IncludeClinicSheetRatings: "1" });
});

test("the sign-off sheet says which ratings the summary used", () => {
  // eslint-disable-next-line global-require
  const { ratingsUsedText } = require("./DeploySignoffCard");
  expect(ratingsUsedText(null)).toBe("REDCap reports only (clinic-sheet ratings off)");
  expect(ratingsUsedText({ included: true, n_added: 75, reason: null }))
    .toBe("REDCap reports plus 75 clinic-sheet ratings");
  expect(ratingsUsedText({ included: true, n_added: 0, reason: "the sheets carry no column for MPQ" }))
    .toMatch(/asked for, but the sheets carry no column/);
});
