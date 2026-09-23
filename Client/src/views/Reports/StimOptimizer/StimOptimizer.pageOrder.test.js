/**
 * The Stim Optimizer page's order (panel C item 5; report C §5.2 with the panel's two corrections):
 * readiness, then the decision, then the current map, then the next session and its home schedule
 * together, then the plan card with its four checks; the evidence base as a one-line footer.
 *
 * The page is rendered whole against the RCS08 fixture, with its two data requests answered from
 * that fixture, and the order is read off the rendered text -- the order a reader meets the cards
 * in, not the order of lines in the source.
 */
import "@testing-library/jest-dom";
import { render as rtlRender } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";

import theme from "assets/theme";
import { PlatformContextProvider } from "context";

import response from "./__fixtures__/rcs08_stim_optimizer_two_stage.json";

jest.mock("react-router-dom", () => ({
  ...jest.requireActual("react-router-dom"),
  useParams: () => ({ participant_uid: "2e3c75c00d7f4f37b53a048d195f11da" }),
}));
jest.mock("layouts/DatabaseLayout", () => ({ children }) => <div>{children}</div>);
jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn() } }));
jest.mock("plotly.js-dist", () => ({
  react: () => Promise.resolve(), purge: () => {}, restyle: () => Promise.resolve(),
  relayout: () => Promise.resolve(), newPlot: () => Promise.resolve(), toImage: () => Promise.resolve(),
}));
// The current map is drawn with Plotly through the project's graphing utility, which jsdom cannot
// host. Its drawing is not what this test is about -- its place on the page is -- so it stands in
// as its own title, which is what the order is read from.
jest.mock("./CurrentMapCard", () => () => <div>Where the two currents have been tried, and what the record says</div>);
jest.mock("views/Reports/RecomputeBar", () => () => <div>recompute bar</div>);
jest.mock("views/Reports/CacheStatusLine", () => () => null);
// The page's own response and the two-stage plan, both from the fixture. The hook is the PI's
// file and is not edited; it is only stood in for here.
jest.mock("database/useCachedResult", () => {
  // eslint-disable-next-line global-require
  const fx = require("./__fixtures__/rcs08_stim_optimizer_two_stage.json");
  return {
    useCachedResult: () => ({
      data: fx,                                        // both requests answer with the full response
      loading: false, err: null, hasCached: true, stale: false, staleReasons: [],
      computedAt: null, notKept: false,
    }),
  };
});

// eslint-disable-next-line import/first
import StimOptimizer from "./index";

const wrap = (ui) => (
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>
);

describe("the page's order", () => {
  it("meets the reader in the order the panel adopted", () => {
    const { container } = rtlRender(wrap(<StimOptimizer />));
    const text = container.textContent;
    const at = (needle) => {
      const i = text.indexOf(needle);
      if (i < 0) throw new Error(`not on the page: ${needle}`);
      return i;
    };
    const readiness = at("contact-and-rate combinations usable for closed loop");
    const decision = at("No side has a setting proven better than today's");
    const map = at("Where the two currents have been tried");
    // The plan card's title also appears earlier, inside the readiness table's pointer to it, so
    // the card itself is its LAST occurrence.
    const checks = text.lastIndexOf("Closed loop: may it start on the frozen setting?");
    const footer = at("Evidence base:");
    expect(readiness).toBeLessThan(decision);
    expect(decision).toBeLessThan(map);
    expect(map).toBeLessThan(checks);
    expect(checks).toBeLessThan(footer);
  });

  it("no longer prints the method-describing title", () => {
    const { container } = rtlRender(wrap(<StimOptimizer />));
    expect(container.textContent).not.toMatch(/What the joint search prefers, per side/);
  });

  it("prints the evidence base as one line, not a card of six numbers", () => {
    const { getByTestId } = rtlRender(wrap(<StimOptimizer />));
    const f = getByTestId("evidence-base-footer");
    expect(f.textContent).toMatch(/^Evidence base: \d+ stretches of unchanged settings · \d+ pain reports used/);
    expect(response.design_matrix.n_epochs).toBeGreaterThan(0);
  });
});
