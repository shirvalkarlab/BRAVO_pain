import {escapeText, homeTiming, localTime, rollingMedian, settingsSummary} from './data';

export const OURA_DEFAULTS = ['steps', 'heart_rate', 'hrv', 'total_calories', 'sleep_duration', 'sleep_total'];
const DAY = 86400000;
const stamp = day => Date.parse(`${day}T12:00:00Z`);
export const ouraPoints = (points, range) => points.filter(p => Number.isFinite(p.value) && p.day >= range.start && p.day <= range.end);
export function ouraRange(metrics, today) {
  const days = metrics.flatMap(m => m.points.filter(p => Number.isFinite(p.value)).map(p => p.day)).sort();
  return {start: days[0] || today, end: today};
}
export function dailySeries(points) {
  const sorted = [...points].sort((a, b) => a.day.localeCompare(b.day));
  const result = [];
  sorted.forEach((point, i) => {
    if (i && stamp(point.day) - stamp(sorted[i - 1].day) > DAY) {
      result.push({day: new Date(stamp(sorted[i - 1].day) + DAY).toISOString().slice(0, 10), value: null});
    }
    result.push(point);
  });
  return result;
}
export function fivePointMedian(points) {
  // Use the same centered observed-point window as REDCap. Never include null
  // source readings as zero or let date-range filtering change edge estimates.
  return rollingMedian(points.filter(p => Number.isFinite(p.value)).map(p => ({...p, time: Number.isFinite(p.time) ? p.time : stamp(p.day) / 1000})));
}
export function visiblePhases(phases, range) {
  const sorted = [...phases].sort((a, b) => a.start - b.start);
  return sorted.filter((p, i) => localTime(p.start).slice(0, 10) <= range.end &&
    (!sorted[i + 1] || localTime(sorted[i + 1].start).slice(0, 10) > range.start));
}
export function ouraTraces(metric, range, phases, smooth, markers, homes = [], unknownIntervals = []) {
  if (metric.resolution === 'sample') return sampleTraces(metric, range, phases, markers, smooth, homes, unknownIntervals);
  const eligible = metric.points.filter(p => Number.isFinite(p.value));
  const phaseFor = day => [...phases].sort((a, b) => a.start - b.start).filter(p => localTime(p.start).slice(0, 10) <= day).slice(-1)[0];
  const makeTrace = (series, trend) => ({type: 'scatter', mode: trend ? 'lines' : 'markers',
    name: trend ? '5-point rolling median' : metric.label, x: series.map(p => p.day), y: series.map(p => p.value),
    connectgaps: false, line: {color: trend ? '#A84747' : '#356E9B', width: trend ? 2.5 : 1.5},
    marker: {size: 6, color: series.map(p => phaseFor(p.day)?.color || '#356E9B')},
    customdata: series.map(p => `${escapeText(phaseFor(p.day)?.label || '')}${trend ? '<br>Centered median of up to five observed daily values' : ''}<br>Daily summary; stimulation may change within this Oura day. See home-program records for timing and settings.`),
    hovertemplate: `<b>${escapeText(trend ? 'Rolling median' : metric.label)}: %{y:.2f} ${escapeText(metric.unit)}</b><br>%{x} · Oura day<br>%{customdata}<extra></extra>`});
  const traces = [makeTrace(dailySeries(ouraPoints(eligible, range)), false)];
  if (smooth) traces.push(makeTrace(dailySeries(ouraPoints(fivePointMedian(eligible), range)), true));
  return traces;
}

// Keep recorded timestamps and null cells. A missing interval stays a gap even
// when the source omitted missing cells instead of storing explicit nulls.
export function sampleSeries(points, range, maxGap = 600) {
  const sorted = points.filter(p => {
    if (!Number.isFinite(p.time)) return false;
    const day = p.day || localTime(p.time).slice(0, 10);
    return day >= range.start && day <= range.end;
  })
    .sort((a, b) => a.time - b.time);
  const result = [];
  sorted.forEach((point, i) => {
    if (i && point.time - sorted[i - 1].time > maxGap) result.push({time: sorted[i - 1].time + 1, value: null});
    result.push({...point, value: Number.isFinite(point.value) ? point.value : null});
  });
  return result;
}
export function sampleHomeContext(homes, unknownIntervals) {
  const sorted = [...homes].sort((a,b) => a.time-b.time);
  const summaries = sorted.map(home => settingsSummary(home.settings));
  const cache = new Map();
  return point => {
    if (!Number.isFinite(point.value)) return '';
    const unknown = unknownIntervals.find(interval => point.time >= interval.start && (interval.end === null || point.time < interval.end));
    if (unknown) return `Home settings not established for this interval.<br>${escapeText(unknown.reason)}`;
    let lo = 0, hi = sorted.length;
    while (lo < hi) {const mid = (lo + hi) >> 1; if (sorted[mid].time <= point.time) lo = mid + 1; else hi = mid;}
    if (!lo) return 'Home settings not established';
    const home = sorted[lo-1];
    const day = home.time_precision === 'day' ? point.day || localTime(point.time).slice(0,10) : '';
    const key = `${lo}:${day}`;
    if (!cache.has(key)) cache.set(key, `Home program context<br>${summaries[lo-1]}<br>${homeTiming(home, point).replace('survey may precede change', 'reading may precede change')}`);
    return cache.get(key);
  };
}

export function sampleTraces(metric, range, phases, markers, smooth = false, homes = [], unknownIntervals = []) {
  const series = sampleSeries(metric.points, range, metric.max_gap_seconds);
  const sortedPhases = [...phases].sort((a, b) => a.start - b.start);
  const phaseFor = time => sortedPhases.filter(p => p.start <= time).slice(-1)[0];
  const homeContext = sampleHomeContext(homes, unknownIntervals);
  const makeTrace = (series, trend) => ({type: 'scattergl', mode: trend ? 'lines' : 'markers', name: trend ? '5-point rolling median' : metric.label,
    x: series.map(p => localTime(p.time)), y: series.map(p => p.value), connectgaps: false,
    line: {color: trend ? '#A84747' : '#356E9B', width: trend ? 2 : 1}, marker: {size: 3, color: '#356E9B'},
    customdata: series.map(p => [escapeText(phaseFor(p.time)?.label || ''), escapeText(p.source || ''), homeContext(p)]),
    hovertemplate: `<b>${escapeText(trend ? '5-point rolling median' : metric.label)}: %{y:.2f} ${escapeText(metric.unit)}</b><br>%{x} Pacific<br>%{customdata[0]}<br>%{customdata[1]}<br>%{customdata[2]}${trend ? '<br>Centered median of up to five recorded readings; settings describe the center timestamp.' : ''}<extra></extra>`});
  const traces = [makeTrace(series, false)];
  if (smooth) {
    const medians = new Map(fivePointMedian(metric.points.filter(p => Number.isFinite(p.time))).map(p => [p.time,p.value]));
    traces.push(makeTrace(series.map(p => ({...p, value: Number.isFinite(p.value) ? medians.get(p.time) : null})), true));
  }
  return traces;
}
