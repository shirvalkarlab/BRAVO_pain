/**
 * The check figures are Plotly figures (the PI, 2026-10-02), drawn the way the page's other Plotly
 * figures are: not before the enclosing fold has been opened (a graph first drawn in a hidden
 * container measures zero pixels wide), redrawn in place on a new spec, destroyed only on unmount,
 * and with one constant `uirevision`. And each x axis ends on a labelled tick: the stepped-current
 * figure's band axis used to stop at a fixed 50 Hz tick while bands run to 100 Hz, so its right-hand
 * edge carried no number.
 */
import React from "react";
import { render } from "@testing-library/react";

import { SectionRevealedContext } from "views/Reports/paper/Section";

import PlotlyChart from "./PlotlyChart";
import { niceAxis, steppedCurrentSpec, UIREVISION, zeroMaSpec, bandDeviceSpec, bandDetectorResearchSpec } from "./plotSpecs";
import { resetPlots, plotsIn } from "./plotTestUtils";

jest.mock("plotly.js-dist", () => require("./plotTestUtils").plotlyMock());
beforeEach(() => resetPlots());

const SPEC = { data: [{ type: "scatter", x: [1], y: [2] }], layout: { uirevision: UIREVISION } };
const wrap = (revealed, spec) => (
  <SectionRevealedContext.Provider value={revealed}>
    <PlotlyChart spec={spec} height={200} label="a check" />
  </SectionRevealedContext.Provider>);

describe("when the figure is drawn and destroyed", () => {
  it("draws nothing while its fold has never been opened, then draws once when it is", () => {
    const { rerender, container } = render(wrap(false, SPEC));
    expect(global.__plots).toHaveLength(0);
    rerender(wrap(true, SPEC));
    expect(global.__plots).toHaveLength(1);
    expect(plotsIn(container)).toHaveLength(1);
  });

  it("redraws in place when the spec changes, and purges only on unmount", async () => {
    const { rerender, unmount } = render(wrap(true, SPEC));
    await Promise.resolve();
    rerender(wrap(true, { ...SPEC, data: [{ type: "scatter", x: [3], y: [4] }] }));
    await Promise.resolve();
    expect(global.__plots).toHaveLength(2);
    expect(global.__purged).toHaveLength(0);          // the redraw did not tear the graph down
    unmount();
    expect(global.__purged).toHaveLength(1);
  });

  it("every figure carries the one constant uirevision, so a redraw keeps the reader's zoom", () => {
    const device = { pair: "ONE_THREE_LEFT", bands: [{ centre_hz: 20.5, reading: { n: 9, band: { auc: 0.6 } } }] };
    [zeroMaSpec({ rows: [], stretches: [] }), steppedCurrentSpec({ rows: [] }), bandDeviceSpec({ p: device }),
      bandDetectorResearchSpec({ rows: [] })].forEach((s) => expect(s.layout.uirevision).toBe(UIREVISION));
    const { container } = render(wrap(true, SPEC));
    expect(plotsIn(container)[0].layout.uirevision).toBe(UIREVISION);
  });
});

describe("an axis ends on a labelled tick", () => {
  it("runs from a tick to a tick and labels the last one", () => {
    const a = niceAxis([8.5, 29.5], 5, [8, 30]);
    expect(a.range).toEqual([5, 30]);
    expect(a.tickvals).toEqual([5, 10, 15, 20, 25, 30]);
    expect(a.ticktext[a.ticktext.length - 1]).toBe("30");
    const b = niceAxis([0.31, 0.74], 0.1, [0.3, 0.9]);
    expect(b.range).toEqual([0.3, 0.9]);
    expect(b.ticktext).toEqual(["0.3", "0.4", "0.5", "0.6", "0.7", "0.8", "0.9"]);
    // a value just past a tick moves the edge to the next tick, never to an unlabelled point
    expect(niceAxis([0.95], 0.1).range[1]).toBe(1);
  });

  it("the stepped-current band axis reaches 100 Hz with a number on the right-hand edge", () => {
    const band = (c) => ({ route: "r", pair: "ONE_THREE_LEFT", centre_hz: c, group: "far", n: 5, n_runs: 2,
      relative_slope_per_mA: 0.05, lo: 0.01, hi: 0.09 });
    const spec = steppedCurrentSpec({ rows: [band(5.5), band(24.5), band(60.5), band(98.5)] });
    expect(spec.layout.xaxis.range).toEqual([0, 100]);
    expect(spec.layout.xaxis.tickvals).toEqual([0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]);
    expect(spec.layout.xaxis.ticktext[spec.layout.xaxis.ticktext.length - 1]).toBe("100");
  });

  it("the research band detector's axis labels its upper end (it used to stop unlabelled at 0.8)", () => {
    const rb = (rho) => ({ rho, lo: rho - 0.1, hi: rho + 0.1, p: 0.2, q: 0.3, null_p95: 0.12 });
    const row = { pair: "ONE_THREE_LEFT", seconds: 60, reading: { n: 9, current_alone: { rho: 0.2, lo: 0, hi: 0.4 }, bands: rb(0.7), bands_without_current: rb(0.1) } };
    const { xaxis } = bandDetectorResearchSpec({ rows: [row] }).layout;
    expect(xaxis.ticktext[xaxis.ticktext.length - 1]).toBe(xaxis.range[1].toFixed(1));
    expect(xaxis.range[1]).toBeGreaterThanOrEqual(0.8);
  });
});
