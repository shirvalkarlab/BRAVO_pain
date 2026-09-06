import {memo, useEffect, useMemo, useRef} from 'react';
import Plotly from 'plotly.js-dist';
import {stageShapes, transitionLayout} from './data';
import {ouraTraces} from './ouraData';
import TrialPhaseLegend from './TrialPhaseLegend';
import {trialPhaseBands} from './trialPhases';

const EMPTY = [];

export default memo(function OuraChart({metric, range, phases, smooth, markers, transitions = EMPTY, homeTransitions = EMPTY, unknownIntervals = EMPTY, onTransition}) {
  const ref = useRef(null);
  const traces = useMemo(() => ouraTraces(metric, range, phases, smooth, markers, homeTransitions, unknownIntervals), [metric, range, phases, smooth, markers, homeTransitions, unknownIntervals]);
  useEffect(() => {const element = ref.current; return () => Plotly.purge(element);}, []);
  useEffect(() => {
    const element = ref.current;
    const showTrend = smooth;
    const context = transitionLayout(transitions);
    const midpoint = (Date.parse(`${range.start}T00:00:00Z`) + Date.parse(`${range.end}T23:59:59Z`)) / 2;
    context.annotations = context.annotations.map(annotation => ({...annotation, xanchor: Date.parse(annotation.x.replace(' ', 'T')+'Z') > midpoint ? 'right' : 'left'}));
    Plotly.react(element, traces, {
      autosize: true, height: transitions.length ? 480 : 380, margin: {l: 65, r: 20, t: transitions.length ? 110 : 15, b: showTrend ? 105 : 75},
      paper_bgcolor: 'transparent', plot_bgcolor: 'transparent', font: {family: 'Roboto, sans-serif', color: '#344767', size: 15},
      xaxis: {type: 'date', range: [`${range.start} 00:00:00`, `${range.end} 23:59:59`], title: metric.resolution === 'sample' ? 'Date and time · Pacific' : 'Oura day', nticks: 7, automargin: true},
      yaxis: {title: metric.unit, automargin: true, zeroline: false, gridcolor: '#edf0f4'},
      shapes: [...trialPhaseBands(phases, range), ...stageShapes(phases, range), ...context.shapes], annotations: context.annotations, hovermode: 'closest', showlegend: showTrend,
      legend: {orientation: 'h', x: 0, y: -0.3, yanchor: 'top'},
      uirevision: `${metric.key}:${range.start}:${range.end}`,
    }, {responsive: true, displaylogo: false, scrollZoom: false, modeBarButtonsToRemove: ['select2d', 'lasso2d']});
    const select = event => onTransition?.(event.annotation.name);
    if (element.on) element.on('plotly_clickannotation', select);
    return () => {if (element.removeListener) element.removeListener('plotly_clickannotation', select);};
  }, [traces, metric, range, phases, smooth, transitions, onTransition]);
  useEffect(() => {
    if (typeof ResizeObserver === 'undefined') return;
    const element = ref.current;
    let frame;
    const observer = new ResizeObserver(() => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {if (element._fullLayout) Plotly.Plots.resize(element);});
    });
    observer.observe(element);
    return () => {observer.disconnect(); cancelAnimationFrame(frame);};
  }, []);
  return <div style={{minWidth:0}}><TrialPhaseLegend phases={phases} range={range}/><div ref={ref} role="img" aria-label={`${metric.label} Oura timeline`} style={{width: '100%', minWidth: 0, minHeight: 380}} /></div>;
});
