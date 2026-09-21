/**
 * The matcher's shared-report warning (the PI, 2026-09-21): printed in full when any matched
 * pain report is claimed by more than one session; nothing when none is, or on the same-day
 * path, or before Compute.
 */
import React from "react";
import { render as rtlRender } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";
import theme from "assets/theme";
import { PlatformContextProvider } from "context";

import ReportSharingNote from "./ReportSharingNote";

const wrap = (ui) => (
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>
);

const WARNING = "Warning: 19 of 46 matched pain reports are claimed by more than one recording session (66 sessions; at most 7 per report). within the cap of 3 sessions per report set on this page. The correlation's p-value is grouped on the report, so a shared report counts once there.";

describe("ReportSharingNote", () => {
  it("prints the warning in full when reports are shared", () => {
    const summary = { timedomain: { report_sharing: { mode: "time_window", n_reports_shared: 19, warning: WARNING } } };
    const { container } = rtlRender(wrap(<ReportSharingNote summary={summary} />));
    expect(container.textContent).toContain(WARNING);
  });

  it("draws nothing when no report is shared, on the same-day path, or before Compute", () => {
    for (const summary of [
      { timedomain: { report_sharing: { mode: "time_window", n_reports_shared: 0, warning: null } } },
      { timedomain: { report_sharing: { mode: "same_day", n_reports_shared: 0, warning: null } } },
      { timedomain: null },
      null,
    ]) {
      const { container } = rtlRender(wrap(<ReportSharingNote summary={summary} />));
      expect(container.textContent.trim()).toBe("");
    }
  });
});
