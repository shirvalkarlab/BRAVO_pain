import {memo, useEffect, useMemo, useRef, useState} from "react";
import Plotly from "plotly.js-dist";
import {metricTraces, stageShapes, transitionLayout, calendarTicks} from "./data";

import TrialPhaseLegend from "./TrialPhaseLegend";
import {trialPhaseBands} from "./trialPhases";

const EMPTY = [];

export default memo(function MetricChart({metric, phases, range, smooth, visits = EMPTY, transitions = EMPTY, homeTransitions = EMPTY, showVisits = true, unknownIntervals = EMPTY, onTransition}) {
  const ref = useRef(null);
  const [width, setWidth] = useState(0);
  const calendar = calendarTicks(range);
  const tickBudget = Math.max(2, Math.floor((width - 95) / 42));
  const tickStep = Math.ceil(28 / tickBudget);
  const ticks = calendar.tickvals && width > 0 ? {...calendar,
    tickvals: calendar.tickvals.filter((_, i) => i === 27 || (i % tickStep === 0 && 27 - i >= tickStep)),
    ticktext: calendar.ticktext.filter((_, i) => i === 27 || (i % tickStep === 0 && 27 - i >= tickStep)),
  } : calendar;
  const traces = useMemo(() => metricTraces(metric, phases, range, smooth, visits, homeTransitions, showVisits, unknownIntervals), [metric, phases, range, smooth, visits, homeTransitions, showVisits, unknownIntervals]);
  useEffect(() => {
    const element = ref.current;
    return () => Plotly.purge(element);
  }, []);
  useEffect(() => {
    const context = transitionLayout(transitions);
    const midpoint = (Date.parse(`${range.start}T00:00:00`) + Date.parse(`${range.end}T23:59:59`)) / 2;
    context.annotations = context.annotations.map(annotation => ({...annotation,
      xanchor: Date.parse(annotation.x.replace(" ", "T")) > midpoint ? "right" : "left"}));
    const element = ref.current;
    Plotly.react(element, traces, {
      height: transitions.length ? 505 : 420, margin: {l: width > 0 && width < 600 ? 50 : 75, r: 20, t: transitions.length ? 100 : 15, b: 130}, paper_bgcolor: "transparent", plot_bgcolor: "transparent",
      font: {family: "Roboto, sans-serif", color: "#344767", size: 16}, hoverlabel: {font: {size: 16}},
      xaxis: {type: "date", range: [`${range.start} 00:00:00`, `${range.end} 23:59:59`], title: {text: "Date · Pacific time", font: {size: 17}, standoff: 15}, automargin: true, showgrid: false, nticks: width > 0 && width < 600 ? 4 : 7, ...ticks},
      yaxis: {range: [metric.range[0] - metric.range[1] * 0.03, metric.range[1] * 1.04], title: {text: `Score (${metric.range.join("–")})`, font: {size: 17}}, zeroline: false, automargin: true, gridcolor: "#edf0f4"},
      showlegend: smooth || (showVisits && visits.length > 0), legend: {orientation: "h", x: 0, xanchor: "left", y: -0.34, yanchor: "top", font: {size: 15}},
      shapes: [...trialPhaseBands(phases, range), ...stageShapes(phases, range), ...context.shapes], annotations: context.annotations,
      uirevision: `${metric.key}:${range.start}:${range.end}`,
    }, {responsive: true, displaylogo: false, scrollZoom: false, modeBarButtonsToRemove: ["select2d", "lasso2d"]});
    const select = event => onTransition?.(event.annotation.name);
    if (element.on) element.on("plotly_clickannotation", select);
    return () => {if (element.removeListener) element.removeListener("plotly_clickannotation", select);};
  }, [metric, phases, range, smooth, traces, visits, transitions, showVisits, onTransition, width]);
  useEffect(() => {
    if (typeof ResizeObserver === "undefined") return;
    const element = ref.current;
    let frame;
    const measure = () => setWidth(element.getBoundingClientRect().width);
    measure();
    const observer = new ResizeObserver(() => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => { measure(); if (element._fullLayout) Plotly.Plots.resize(element); });
    });
    observer.observe(element);
    return () => { observer.disconnect(); cancelAnimationFrame(frame); };
  }, []);
  return <div style={{minWidth:0}}><TrialPhaseLegend phases={phases} range={range}/><div style={{width: "100%", minWidth: 0}}><div ref={ref} role="img" aria-label={`${metric.label} interactive timeline`} style={{width: "100%", minWidth: 0, minHeight: 420}} /></div></div>;
});
