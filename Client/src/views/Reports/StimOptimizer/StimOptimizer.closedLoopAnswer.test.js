/**
 * "Closed-loop readiness" starts closed (the PI, 2026-09-26), so its answer must be in view while
 * it is: the same count of the four checks the checks card prints ("No: 2 of 4 checks block, 1 not
 * assessed"), read from the two-stage plan's gate. Before 2026-09-26 the closed section showed its
 * title alone.
 */
import "@testing-library/jest-dom";
import { render as rtlRender } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";
import theme from "assets/theme";
import { PlatformContextProvider } from "context";
import response from "./__fixtures__/rcs08_stim_optimizer_2026-09-25.json";
import { gateHeadline } from "./ClosedLoopChecks";

jest.mock("react-router-dom", () => ({
  ...jest.requireActual("react-router-dom"),
  useParams: () => ({ participant_uid: "2e3c75c00d7f4f37b53a048d195f11da" }),
}));
jest.mock("layouts/DatabaseLayout", () => ({ children }) => <div>{children}</div>);
jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn(() => new Promise(() => {})) } }));
jest.mock("plotly.js-dist", () => ({
  react: () => Promise.resolve(), purge: () => {}, restyle: () => Promise.resolve(),
  relayout: () => Promise.resolve(), newPlot: () => Promise.resolve(), toImage: () => Promise.resolve(),
}));
jest.mock("views/Reports/RecomputeBar", () => () => <div>recompute bar</div>);
jest.mock("views/Reports/ControlAnalyses/ControlAnalysesCard", () => ({
  ControlAnalysesSection: () => <div data-testid="control-analyses">control analyses</div>,
}));
jest.mock("database/useCachedResult", () => ({
  useCachedResult: () => ({ data: global.__SO_FX__, loading: false, err: null, hasCached: true,
    stale: false, staleReasons: [], computedAt: null, notKept: false }),
}));

// eslint-disable-next-line import/first
import StimOptimizer from "./index";

const wrap = (ui) => (
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>
);

it("the closed-loop section says whether closed loop can start while it is closed", () => {
  global.__SO_FX__ = response;
  const { container } = rtlRender(wrap(<StimOptimizer />));
  const section = container.querySelector("section#closed-loop");
  expect(section).not.toBeNull();
  const body = section.querySelector("#closed-loop-body");
  expect(body.hidden).toBe(true);
  const shown = Array.from(section.querySelectorAll("p")).filter((p) => p.closest("[hidden]") === null)
    .map((p) => p.textContent).join(" ");
  expect(shown).toMatch(/^No: \d of \d checks block/);
  expect(shown).toContain(gateHeadline(response.two_stage));
});
