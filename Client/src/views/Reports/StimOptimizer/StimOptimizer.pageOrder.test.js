/**
 * The Stim Optimizer page's order. ORDER CHANGED 2026-09-26 by the minimalist redesign (SPEC.md
 * section 5.3), which amends panel C item 5: the page opens with its answer, then four sections
 * written as questions -- is any setting proven better (the decision), where have currents been
 * tried (the current map), can closed loop start (the readiness blocks, then the four checks), what
 * must the next visit deliver -- and the evidence base as a one-line footer.
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
jest.mock("./CurrentMapCard", () => () => <div>Sampled currents, predicted pain</div>);
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
  // PIN CHANGED 2026-09-26 (SPEC.md section 5.3): the order is the four sections' order.
  it("meets the reader in the order of the four questions", () => {
    const { container } = rtlRender(wrap(<StimOptimizer />));
    const text = container.textContent;
    const at = (needle) => {
      const i = text.indexOf(needle);
      if (i < 0) throw new Error(`not on the page: ${needle}`);
      return i;
    };
    const status = at("Keep today's setting on both sides; closed loop cannot start.");
    const decision = at("No side has a setting proven better than today's");
    const map = at("Sampled currents");
    const readiness = at("contact-and-rate combinations usable for closed loop");
    const checks = text.lastIndexOf("Closed loop at frozen rate and pulse width");
    const next = at("Next-visit requirements");
    const footer = at("Evidence base:");
    expect(status).toBeLessThan(decision);
    expect(decision).toBeLessThan(map);
    expect(map).toBeLessThan(readiness);
    expect(readiness).toBeLessThan(checks);
    expect(checks).toBeLessThan(next);
    expect(next).toBeLessThan(footer);
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
