import {homeNeuralPlot, neuralTime} from './homeNeuralChartData';

// Keep each period's settings, thresholds and observation basis intact. Joining
// their traces into one side's chart must not join guides across period edges.
export function summaryNeuralGroups(data) {
  const groups = new Map();
  const periods = [...(data?.windows || []), ...(data?.observation_windows || [])
    .filter(period => period.display_basis === 'recorded_observations')];
  for (const period of periods) for (const panel of period.panels || []) {
    if (!groups.has(panel.side)) groups.set(panel.side, {side:panel.side, parts:[]});
    groups.get(panel.side).parts.push({period, panel});
  }
  return [...groups.values()].map(group => {
    // Settings IDs may be reused in separately requested windows. Namespace
    // only repeated IDs so a click always selects the displayed source interval.
    const counts = new Map();
    for (const {panel} of group.parts) for (const segment of panel.segments || []) {
      counts.set(segment.id, (counts.get(segment.id) || 0) + 1);
    }
    const parts = group.parts.map(({period,panel}, index) => ({period, panel:{...panel,
      segments:(panel.segments || []).map((segment, position) => ({...segment,
        id:counts.get(segment.id) > 1 ? `summary:${index}:${position}:${segment.id}:${segment.start}:${segment.end}` : segment.id,
      })),
    }}));
    return {...group,parts,segments:parts.flatMap(({panel}) => panel.segments)};
  });
}

export function summaryNeuralPlot(group, participant) {
  const result = {traces:[],descriptions:[],observedPower:0,observedAmplitude:0,latestTime:null};
  const seen = {power:new Set(),amplitude:new Set()};
  for (const {panel,period} of group.parts) {
    const start = neuralTime(period.start), end = neuralTime(period.end);
    const independentCurrent = Array.isArray(panel.amplitude_series);
    // The API returns disjoint windows. If a response repeats an observation,
    // suppress only identical metric/time/value AND source/settings provenance.
    // Equal values on different sensing configurations are distinct evidence.
    const unique = (point, metric, a, b, source) => {
      const time = neuralTime(point.time), value = point[metric];
      if (a === null || b === null || time === null || time < a || time >= b
          || !Number.isFinite(value) || point[`${metric}_conflict`]) return value;
      const {time:recordedTime,power,amplitude,power_conflict,amplitude_conflict,...pointSource} = point;
      const key = JSON.stringify([time,value,source,pointSource]);
      if (seen[metric].has(key)) return null;
      seen[metric].add(key);
      return value;
    };
    const prepared = {...panel,segments:panel.segments.map(segment => {
      // IDs and bounds can change when the same source interval is clipped into
      // different requested windows. Preserve every other metadata field in the
      // identity, including contacts, frequency, settings and evidence labels.
      const {id,start:recordedStart,end:recordedEnd,points,...source} = segment;
      const segmentStart = neuralTime(segment.start), segmentEnd = neuralTime(segment.end);
      const a = start === null || segmentStart === null ? null : Math.max(start,segmentStart);
      const b = end === null || segmentEnd === null ? null : Math.min(end,segmentEnd);
      return {...segment,points:(segment.points || []).map(point => ({...point,
        power:unique(point,'power',a,b,source),
        ...(!independentCurrent ? {amplitude:unique(point,'amplitude',a,b,source)} : {}),
      }))};
    }), ...(independentCurrent ? {amplitude_series:panel.amplitude_series.map(point => ({...point,
      amplitude:unique(point,'amplitude',start,end,panel.amplitude_provenance),
    }))} : {})};
    const plot = homeNeuralPlot(prepared,period,participant,600);
    result.traces.push(...plot.traces);
    result.descriptions.push(...plot.descriptions);
    result.observedPower += plot.observedPower;
    result.observedAmplitude += plot.observedAmplitude;
    if (plot.latestTime !== null) result.latestTime = result.latestTime === null ? plot.latestTime : Math.max(result.latestTime,plot.latestTime);
  }
  return result;
}
