/**
 * The Closed-Loop and Stim Optimizer pages' text colour, darker than the app theme's (the PI,
 * 2026-09-24: "make sure everything is optimized for legibility").
 *
 * The theme's "text" colour (#7b809a) is about 3.9:1 against white, below the 4.5:1 minimum for
 * body text, and every `MDTypography color="text"` on these two pages uses it: measured live, 40
 * elements on the Stim Optimizer page and 5 on the Closed-Loop page. Wrapping each page's content
 * gives them #5E5E5E (about 6.4:1, the Stim Optimizer's own secondary grey) without changing the
 * theme for the rest of the application or its navigation.
 */
import { ThemeProvider } from "@mui/material/styles";

export const LEGIBLE_TEXT = "#5E5E5E";

const withLegibleText = (outer) => ({
  ...outer,
  palette: { ...outer.palette, text: { ...outer.palette.text, main: LEGIBLE_TEXT } },
});

export default function LegibleText({ children }) {
  return <ThemeProvider theme={withLegibleText}>{children}</ThemeProvider>;
}
