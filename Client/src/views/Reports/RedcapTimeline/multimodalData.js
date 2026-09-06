import {escapeText, filterPoints, metricTraces, transitionLayout} from './data';
import {homeNeuralLayout} from './homeNeuralChartData';
import {dailySeries, fivePointMedian, ouraPoints} from './ouraData';

export const SUMMARY_COLORS = ['#356E9B', '#B86C2D'];
export const SUMMARY_METRICS = ['left_leg_vas_intensity', 'mpq_standard_0_45'];
export const SUMMARY_OURA = ['steps', 'sleep_total'];
const dayStamp = day => Date.parse(`${day.slice(0, 10)}T12:00:00Z`);

// Survey dates without observations remain visibly empty. This is a display
// break only; the centered five-observation estimate still uses reviewed points.
export function surveyGapTrace(trace) {
  const x = [], y = [], customdata = [];
  trace.x.forEach((stamp, i) => {
    if (i && dayStamp(stamp) - dayStamp(trace.x[i - 1]) > 86400000) {
      x.push(null); y.push(null); customdata.push(null);
    }
    x.push(stamp); y.push(trace.y[i]); customdata.push(trace.customdata[i]);
  });
  return {...trace, x, y, customdata, connectgaps: false};
}

export function summarySurveyTraces(metrics, visits, phases, range, smooth, homes, unknown) {
  return SUMMARY_METRICS.flatMap((key, index) => {
    const metric = metrics.find(item => item.key === key);
    if (!metric) return [];
    return metricTraces(metric, phases, range, smooth, visits[key] || [], homes, true, unknown).map(original => {
      const trend = original.mode === 'lines';
      const trace = trend ? surveyGapTrace(original) : original;
      return {...trace, name: `${metric.label} · ${trend ? '5-point median' : original.name}`,
        yaxis: index ? 'y2' : 'y', showlegend: false,
        line: {...trace.line, color: SUMMARY_COLORS[index]},
        marker: {...trace.marker, color: SUMMARY_COLORS[index]}, connectgaps: false};
    });
  });
}

export function summaryOuraTraces(metrics, range, smooth, visitDays) {
  const days = new Set(visitDays);
  return SUMMARY_OURA.flatMap((key, index) => {
    const metric = metrics.find(item => item.key === key);
    if (!metric) return [];
    const eligible = metric.points.filter(point => Number.isFinite(point.value));
    const make = (points, trend) => {
      const series = dailySeries(ouraPoints(points, range));
      return {type: 'scatter', mode: trend ? 'lines' : 'markers', name: `${metric.label}${trend ? ' · 5-point median' : ''}`,
        x: series.map(point => `${point.day} 12:00:00`), y: series.map(point => point.value), yaxis: index ? 'y2' : 'y',
        showlegend: false, connectgaps: false, line: {color: SUMMARY_COLORS[index], width: 2.5},
        marker: {color: SUMMARY_COLORS[index], size: series.map(point => days.has(point.day) ? 10 : 6), symbol: series.map(point => days.has(point.day) ? 'x' : 'circle')},
        customdata: series.map(point => `${point.day} · Oura day${days.has(point.day) ? '<br>Stimulation-visit day; daily summary may span settings changes.' : ''}${trend ? '<br>Centered median of up to five observed daily values.' : ''}`),
        hovertemplate: `<b>${escapeText(metric.label)}: %{y:.2f} ${escapeText(metric.unit)}</b><br>%{customdata}<extra></extra>`};
    };
    return [make(eligible, false), ...(smooth ? [make(fivePointMedian(eligible), true)] : [])];
  });
}

export function summaryEvents(transitions, range) {
  return filterPoints(transitions, range.start, range.end).map((event, index) => ({...event, number: index + 1}));
}

export function summaryLayout({range, xRange, width, left, right, limits, events, neuralPeriod}) {
  const compact = width > 0 && width < 600;
  const context = transitionLayout(events);
  // Number-only anchors stay readable on narrow screens. Full existing concise
  // setting/timing context remains on hover and in the shared selector.
  context.annotations = context.annotations.map(annotation => ({...annotation,
    text: String(events.find(event => event.id === annotation.name).number), y: 1.03, yanchor: 'bottom', xanchor: 'center'}));
  return {autosize: true, height: compact ? 370 : 410,
    margin: {l: compact ? 56 : 80, r: compact ? 58 : 80, t: 35, b: 65},
    paper_bgcolor: 'transparent', plot_bgcolor: 'transparent', font: {family: 'Roboto, sans-serif', color: '#344767', size: compact ? 12 : 14},
    xaxis: {type: 'date', range: xRange || [`${range.start} 00:00:00`, `${range.end} 23:59:59`],
      title: {text: 'Date · Pacific time', standoff: 12}, nticks: compact ? 3 : 7, automargin: true, showgrid: false},
    yaxis: {title: {text: left, standoff: 8}, ...(limits ? {range: limits[0]} : {rangemode: 'tozero'}),
      color: SUMMARY_COLORS[0], automargin: true, zeroline: false, gridcolor: '#edf0f4'},
    yaxis2: {title: {text: right, standoff: 8}, ...(limits ? {range: limits[1]} : {rangemode: 'tozero'}),
      color: SUMMARY_COLORS[1], overlaying: 'y', side: 'right', automargin: true, zeroline: false, showgrid: false},
    ...(neuralPeriod ? (() => {const neural = homeNeuralLayout(neuralPeriod,width); return {yaxis:neural.yaxis,yaxis2:neural.yaxis2};})() : {}),
    shapes: context.shapes, annotations: context.annotations, showlegend: false, hovermode: 'closest',
    hoverlabel: {align: 'left'}, uirevision: `${range.start}:${range.end}`};
}

export function relayoutRange(event) {
  if (event['xaxis.autorange']) return null;
  if (event['xaxis.range']) return event['xaxis.range'];
  if (event['xaxis.range[0]'] !== undefined && event['xaxis.range[1]'] !== undefined) return [event['xaxis.range[0]'], event['xaxis.range[1]']];
  return undefined;
}
export function hoverTime(value) {
  return typeof value === 'number' ? new Date(value).toISOString().replace('T', ' ').slice(0, 23) : value;
}
