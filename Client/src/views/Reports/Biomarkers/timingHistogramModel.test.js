/**
 * The timing histogram at the top of the Binarization card (the PI, 2026-09-21, option C): when each
 * neural sample falls relative to the nearest pain report, one translucent series per source
 * overlaid (the offline figure's look), the x-axis following the match-window slider with 25% extra
 * shown greyed on each side, and the direction toggle deciding which side is in colour.
 */
import "@testing-library/jest-dom";
import { render as rtlRender } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";
import theme from "assets/theme";
import { PlatformContextProvider } from "context";

import { timingHistogramData, sampleOffsetsMin, SOURCE_SERIES } from "./timingHistogramModel";
import TimingHistogram from "./TimingHistogram";

jest.mock("plotly.js-dist", () => {
  const noop = () => {};
  const calls = [];
  const react = (el, traces, layout) => { calls.push({ traces, layout }); return Promise.resolve(); };
  return { react, purge: noop, restyle: noop, relayout: noop, newPlot: noop, __calls: calls };
});
// eslint-disable-next-line import/first
import Plotly from "plotly.js-dist";

const wrap = (ui) => (
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>
);

const H = 3600;
const painSeries = { t: [0, H, 2 * H], y: [5, 6, 7] };
const scanIndex = [
  { t: -30, channel: "A", source: "Indefinite stream" },          // 0.5 min BEFORE report 0
  { t: 90, channel: "A", source: "BrainSense streaming" },         // 1.5 min after report 0
  { t: H + 60, channel: "B", source: "Patient event" },            // 1 min after report 1
  { t: H + 150, channel: "B", source: "Patient event" },           // 2.5 min after report 1 (tail at W=2)
  { t: 2 * H - 120, channel: "A", source: "Montage" },             // 2 min before report 2 (edge, inside)
  { t: 2 * H + 3600, channel: "A", source: "Montage" },            // 60 min after: off the axis
];

describe("sampleOffsetsMin", () => {
  it("gives each sample its signed minutes to the nearest report, negative before", () => {
    const off = sampleOffsetsMin(scanIndex, painSeries);
    expect(off.map((o) => o.dtMin)).toEqual([-0.5, 1.5, 1, 2.5, -2, 60]);
    expect(off.map((o) => o.series)).toEqual(["trace", "trace", "event", "event", "montage", "montage"]);
  });
});

describe("timingHistogramData", () => {
  it("bins each source over ±1.25 × window and splits inside from outside", () => {
    const d = timingHistogramData(sampleOffsetsMin(scanIndex, painSeries), { windowMin: 2, matchDirection: "nearest" });
    expect(d.limMin).toBe(2.5);
    expect(d.edges[0]).toBeLessThanOrEqual(-2.5);
    expect(d.edges[d.edges.length - 1]).toBeGreaterThanOrEqual(2.5);
    const sum = (a) => a.reduce((s, v) => s + v, 0);
    expect(sum(d.series.trace.inside)).toBe(2);
    expect(sum(d.series.event.inside)).toBe(1);
    expect(sum(d.series.event.outside)).toBe(1);      // the 2.5-min sample sits in the tail
    expect(sum(d.series.montage.inside)).toBe(1);     // exactly at the edge counts inside
    expect(sum(d.series.montage.outside)).toBe(0);    // the 60-min sample is off the axis
    expect(d.nInside).toBe(4);
    expect(d.nTails).toBe(1);
  });

  it("under the prior direction only samples BEFORE the report are in colour; the after side is greyed", () => {
    const d = timingHistogramData(sampleOffsetsMin(scanIndex, painSeries), { windowMin: 2, matchDirection: "prior" });
    const sum = (a) => a.reduce((s, v) => s + v, 0);
    expect(sum(d.series.trace.inside)).toBe(1);       // -0.5 min
    expect(sum(d.series.trace.outside)).toBe(1);      // +1.5 min, after: greyed
    expect(sum(d.series.event.inside)).toBe(0);
    expect(sum(d.series.montage.inside)).toBe(1);
    expect(d.nInside).toBe(2);
  });

  it("returns an empty shape without inputs", () => {
    const d = timingHistogramData([], { windowMin: 2, matchDirection: "nearest" });
    expect(d.nInside).toBe(0);
    expect(SOURCE_SERIES.map((s) => s.key)).toEqual(["trace", "event", "montage"]);
  });
});

describe("TimingHistogram", () => {
  it("draws one translucent overlaid series per source plus its greyed twin, the window band, and the axis at ±1.25 window", () => {
    Plotly.__calls.length = 0;
    rtlRender(wrap(<TimingHistogram scanIndex={scanIndex} painSeries={painSeries} windowMin={2} matchDirection="nearest" metricLabel="Left Leg VAS" />));
    const last = Plotly.__calls[Plotly.__calls.length - 1];
    expect(last).toBeDefined();
    expect(last.layout.barmode).toBe("overlay");
    expect(last.layout.xaxis.range).toEqual([-2.5, 2.5]);
    const names = last.traces.map((t) => t.name);
    expect(names).toEqual(expect.arrayContaining(["time-domain signal", "patient-event FFT", "montage FFT"]));
    const coloured = last.traces.filter((t) => t.showlegend !== false);
    expect(coloured.every((t) => t.opacity === 0.6)).toBe(true);
    expect(last.layout.shapes.some((s) => s.type === "rect" && s.x0 === -2 && s.x1 === 2)).toBe(true);
    expect(typeof last.layout.uirevision).toBe("string");
  });

  it("prints the counts in words under the figure", () => {
    const { container } = rtlRender(wrap(<TimingHistogram scanIndex={scanIndex} painSeries={painSeries} windowMin={2} matchDirection="nearest" metricLabel="Left Leg VAS" />));
    expect(container.textContent).toContain("4 samples inside ±2 min");
    expect(container.textContent).toContain("1 in the greyed tails");
  });
});
