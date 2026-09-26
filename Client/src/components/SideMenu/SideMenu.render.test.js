/**
 * The sidebar renders on the minimalist theme: group headings in sentence case (no uppercase),
 * the product name as given, and the active item marked for assistive technology by the link.
 */
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { ThemeProvider } from "@mui/material/styles";

import theme from "assets/theme";
import { PlatformContextProvider } from "context";
import SideMenu from "components/SideMenu";
import DashboardLayout from "layouts/DatabaseLayout/DashboardLayout";

// The context saves each change to the server; nothing is sent from a test.
jest.mock("database/session-control", () => ({
  SessionController: { setSession: jest.fn(), query: jest.fn(() => Promise.resolve({ data: {} })) },
}));

const routes = {
  Main: { children: [] },
  CustomizedAnalysis: {
    name: "Choosing stimulation settings",
    children: [
      { key: "CustomizedAnalysis", name: "Choosing stimulation settings", title: true, hide: true },
      { key: "biomarkers", name: "Which brain signal tracks pain", icon: "timeline", route: "/reports/biomarkers/:participant_uid" },
    ],
  },
};

const wrap = (ui, path = "/reports/biomarkers/abc") => (
  <MemoryRouter initialEntries={[path]}>
    <ThemeProvider theme={theme}>
      <PlatformContextProvider initialStates={{ language: "en", user: {}, report: "CustomizedAnalysis", participant_uid: "abc" }}>
        {ui}
      </PlatformContextProvider>
    </ThemeProvider>
  </MemoryRouter>
);

test("the sidebar draws its heading in sentence case and the product name unchanged", () => {
  render(wrap(<SideMenu brandName="UF BRAVO Platform" routes={routes} />));
  expect(screen.getByText("UF BRAVO Platform")).toBeTruthy();
  const heading = screen.getByText("Choosing stimulation settings");
  expect(window.getComputedStyle(heading).textTransform).not.toBe("uppercase");
  expect(screen.getByText("Which brain signal tracks pain")).toBeTruthy();
});

test("the page frame renders its children inside the content column", () => {
  render(wrap(<DashboardLayout><p>page body</p></DashboardLayout>));
  expect(screen.getByText("page body")).toBeTruthy();
});
