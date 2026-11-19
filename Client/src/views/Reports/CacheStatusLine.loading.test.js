/**
 * Page review 2026-10-02 (item 4.7): the Biomarkers "Stored results, memory" fold opened onto an
 * empty body during the first load, because this line printed nothing until the status arrived.
 * While the page is loading it now says so; with no status and no load it still prints nothing.
 */
import { render as rtlRender } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";
import theme from "assets/theme";
import { PlatformContextProvider } from "context";
import CacheStatusLine from "./CacheStatusLine";

const render = (ui) => rtlRender(<ThemeProvider theme={theme}>
  <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider></ThemeProvider>);

describe("CacheStatusLine while the page loads", () => {
  it("says it is reading the stored results while loading", () => {
    expect(render(<CacheStatusLine status={null} loading />).container.textContent.trim())
      .toBe("Reading stored results…");
  });
  it("prints nothing with no status and no load", () => {
    expect(render(<CacheStatusLine status={null} />).container.textContent.trim()).toBe("");
  });
  it("a status, once it arrives, replaces the reading line", () => {
    const t = render(<CacheStatusLine status={{ exists: true, last_built_utc: "2026-10-02T12:00:00Z" }} loading />)
      .container.textContent;
    expect(t).toContain("Stored results last built");
    expect(t).not.toContain("Reading");
  });
});
