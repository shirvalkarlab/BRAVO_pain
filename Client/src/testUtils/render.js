/**
 * Shared set-up for the page tests (2026-10-05, when the page tests were consolidated): the theme
 * and platform wrapper every card and page is rendered in, and the deep copy the tests use to edit
 * a fixture without touching it. Not a test file: jest collects only `*.test.js`.
 */
import { render as rtlRender } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";
import theme from "assets/theme";
import { PlatformContextProvider } from "context";

/** A component inside the app's theme and its platform context, light mode. */
export const wrap = (ui) => (
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>
);

/** Render inside `wrap`. */
export const renderWrapped = (ui, options) => rtlRender(wrap(ui), options);

/** A deep copy of a JSON fixture, so one test's edits never reach another test. */
export const clone = (x) => JSON.parse(JSON.stringify(x));
