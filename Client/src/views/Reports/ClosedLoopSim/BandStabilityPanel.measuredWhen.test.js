/**
 * P-03 (June audit): the stability result did not say when it was measured. The panel now prints the
 * date its recordings, settings and pain reports were assembled, read from the report's own freshness
 * line, and only when the test actually ran: a "not tested" answer has nothing to date.
 */
import React from "react";
import { render as rtlRender } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";
import theme from "assets/theme";
import { PlatformContextProvider } from "context";

import BandStabilityPanel from "./BandStabilityPanel";

const text = (ui) => rtlRender(
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>,
).container.textContent;

const RAN = { answer: "cannot tell", test_ran: true, center_hz: 24.5, electrode: "L 1-3+" };
const STATUS = { last_built_utc: "2026-09-25T20:15:00Z" };

describe("the stability panel says when its answer was measured", () => {
  it("prints the assembly date when the test ran", () => {
    expect(text(<BandStabilityPanel stability={RAN} cacheStatus={STATUS} />))
      .toMatch(/Based on the recordings, settings and pain reports assembled .*2026/);
  });

  it("prints no date when the test did not run", () => {
    expect(text(<BandStabilityPanel stability={{ ...RAN, test_ran: false, answer: "not tested" }} cacheStatus={STATUS} />))
      .not.toMatch(/assembled/);
  });

  it("prints no date when the report carries no build time", () => {
    expect(text(<BandStabilityPanel stability={RAN} cacheStatus={{}} />)).not.toMatch(/assembled/);
    expect(text(<BandStabilityPanel stability={RAN} />)).not.toMatch(/assembled/);
  });
});
