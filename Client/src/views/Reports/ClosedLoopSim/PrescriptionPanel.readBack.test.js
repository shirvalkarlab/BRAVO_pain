/** Synthetic UI contract regression. No live participant response or empirical validation. */
import "@testing-library/jest-dom";
import { render as rtlRender, fireEvent } from "@testing-library/react";
import { wrap, clone } from "testUtils/render";

jest.mock("plotly.js-dist", () => ({
  react: jest.fn(), purge: jest.fn(), restyle: jest.fn(), relayout: jest.fn(), newPlot: jest.fn(),
  toImage: jest.fn(),
}));
jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn() } }));

// eslint-disable-next-line import/first
import ParameterTable from "./PrescriptionPanel";
// eslint-disable-next-line import/first
import DecisionCard from "./DecisionCard";
import LEFT from "./__fixtures__/synthetic_allowed_left.json";
import SUM_L from "./__fixtures__/synthetic_summary_left.json";

const boxes = (c) => Array.from(c.querySelectorAll(".cl-prescription-authorised input[type=checkbox]"));
const nTicked = (c) => boxes(c).filter((b) => b.checked).length;
const tickAll = (c) => boxes(c).forEach((b) => fireEvent.click(b));
const rep = (data) => ({ data, loading: false, err: null });

describe("read-back ticks belong to one report, one band, one mode and one value", () => {
  it("ticks are counted while the same report is on screen", () => {
    const { container, rerender } = rtlRender(wrap(<ParameterTable report={rep(LEFT)} mode="dual" />));
    tickAll(container);
    expect(nTicked(container)).toBe(boxes(container).length);
    rerender(wrap(<ParameterTable report={rep(LEFT)} mode="dual" />));
    expect(nTicked(container)).toBe(boxes(container).length);
    expect(container.textContent).toMatch(/16 of 16 read back/);
  });

  it("a recomputed report clears every tick, even when its values are the same", () => {
    const { container, rerender } = rtlRender(wrap(<ParameterTable report={rep(LEFT)} mode="dual" />));
    tickAll(container);
    rerender(wrap(<ParameterTable report={rep(clone(LEFT))} mode="dual" />));
    expect(nTicked(container)).toBe(0);
    expect(container.textContent).toMatch(/0 of 16 read back/);
  });

  it("a report that goes away (loading, or withheld) and comes back clears every tick", () => {
    const { container, rerender } = rtlRender(wrap(<ParameterTable report={rep(LEFT)} mode="dual" />));
    tickAll(container);
    rerender(wrap(<ParameterTable report={{ data: null, loading: true }} mode="dual" />));
    rerender(wrap(<ParameterTable report={rep(LEFT)} mode="dual" />));
    expect(nTicked(container)).toBe(0);
  });

  it("switching the mode away and back clears every tick, as the file header says", () => {
    const { container, rerender } = rtlRender(wrap(<ParameterTable report={rep(LEFT)} mode="dual" />));
    tickAll(container);
    rerender(wrap(<ParameterTable report={rep(LEFT)} mode="single" />));
    rerender(wrap(<ParameterTable report={rep(LEFT)} mode="dual" />));
    expect(nTicked(container)).toBe(0);
  });

  it("an earlier tick does not survive a band change on the decision card", () => {
    const BC_A = { contact: "ONE_THREE_LEFT", contact_label: "L 1-3+", center_freq_hz: 24.5, hemisphere: "Left" };
    const BC_B = { contact: "ONE_THREE_LEFT", contact_label: "L 1-3+", center_freq_hz: 22.5, hemisphere: "Left" };
    const cardFor = (bc) => wrap(
      <DecisionCard participantUid="uid" bandCandidate={bc} deploymentReport={rep(LEFT)}
        summary={{ data: SUM_L, loading: false, err: null }} mode="dual" onMode={() => {}} />);
    const { container, rerender } = rtlRender(cardFor(BC_A));
    tickAll(container);
    expect(nTicked(container)).toBe(16);
    // The same report object handed back under another band (a cached result): no tick survives.
    rerender(cardFor(BC_B));
    expect(nTicked(container)).toBe(0);
  });
});
