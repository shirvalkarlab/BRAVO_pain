/**
 * The page skeleton for screen readers (TASTE_AUDIT.md C7, 2026-09-26): one <main> region with
 * the id the "Skip to content" link moves focus to, the top bar outside it, and a name on every
 * icon-only button of the top bar and the side menu.
 */
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { ThemeProvider } from "@mui/material/styles";

import theme from "assets/theme";
import { PlatformContextProvider } from "context";
import DashboardLayout, { MAIN_CONTENT_ID } from "layouts/DatabaseLayout/DashboardLayout";
import DashboardNavbar from "components/Navbars/DashboardNavbar";
import SkipToContent, { SKIP_LINK_TEXT } from "components/Navbars/DashboardNavbar/SkipToContent";
import SideMenu from "components/SideMenu";

jest.mock("database/session-control", () => ({
  SessionController: {
    setSession: jest.fn(),
    query: jest.fn(() => Promise.resolve({ data: {} })),
    getServer: jest.fn(() => "http://localhost"),
    logout: jest.fn(() => Promise.resolve({})),
  },
}));

const wrap = (ui, user = { name: "tester" }) => (
  <MemoryRouter initialEntries={["/reports/biomarkers/abc"]}>
    <ThemeProvider theme={theme}>
      <PlatformContextProvider initialStates={{ language: "en", user, report: "", participant_uid: "abc" }}>
        {ui}
      </PlatformContextProvider>
    </ThemeProvider>
  </MemoryRouter>
);

let realWebSocket;
beforeAll(() => {
  realWebSocket = global.WebSocket;
  global.WebSocket = function NoSocket() { throw new Error("no socket in tests"); };
});
afterAll(() => { global.WebSocket = realWebSocket; });

test("the page body sits in one main region with the skip link's target id", () => {
  render(wrap(<DashboardLayout navbar={<header>bar</header>}><p>page body</p></DashboardLayout>));
  const main = screen.getByRole("main");
  expect(main.id).toBe(MAIN_CONTENT_ID);
  expect(MAIN_CONTENT_ID).toBe("main-content");
  expect(main.getAttribute("tabindex")).toBe("-1");
  expect(main.textContent).toBe("page body");
  expect(main.contains(screen.getByText("bar"))).toBe(false);
});

test("'Skip to content' is the top bar's first link and moves focus to the main region", () => {
  render(wrap(<DashboardLayout navbar={<DashboardNavbar fixedNavbar />}><p>page body</p></DashboardLayout>));
  const links = screen.getAllByRole("link");
  expect(links[0].textContent).toBe(SKIP_LINK_TEXT);
  expect(SKIP_LINK_TEXT).toBe("Skip to content");
  fireEvent.click(links[0]);
  expect(document.activeElement).toBe(screen.getByRole("main"));
});

test("every icon-only button in the top bar has a name", () => {
  render(wrap(<DashboardNavbar fixedNavbar />));
  expect(screen.getByRole("button", { name: "Shrink the side menu" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "Hide the side menu" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "Account menu: profile and log out" })).toBeTruthy();
  screen.getAllByRole("button").forEach((b) => {
    expect(b.getAttribute("aria-label")).toBeTruthy();
  });
});

test("the side menu is a named navigation landmark with a named close button", () => {
  const routes = { Main: { children: [] } };
  render(wrap(<SideMenu brandName="UF BRAVO Platform" routes={routes} />));
  expect(screen.getByRole("navigation", { name: "Main menu" })).toBeTruthy();
  const close = screen.getByRole("button", { name: "Close the side menu" });
  expect(close.tagName).toBe("BUTTON");
});

test("the skip link does nothing harmful when the page has no main region", () => {
  render(wrap(<SkipToContent />));
  fireEvent.click(screen.getByRole("link", { name: SKIP_LINK_TEXT }));
  expect(document.activeElement).toBe(document.body);
});
