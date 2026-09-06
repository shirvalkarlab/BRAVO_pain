import {localTime} from './data';

// Keep original phase boundaries; clip presentation to the selected Pacific
// calendar dates. A phase already active at the left edge must remain labeled.
export function trialPhasesInRange(phases = [], range) {
  if (!range?.start || !range?.end || range.start > range.end) return [];
  const start = `${range.start} 00:00:00`, end = `${range.end} 23:59:59`;
  const sorted = phases.filter(p => Number.isFinite(p.start)).slice().sort((a,b) => a.start-b.start);
  return sorted.flatMap((phase, index) => {
    const from = localTime(phase.start);
    const until = sorted[index+1] ? localTime(sorted[index+1].start) : null;
    if (from > end || (until && until <= start)) return [];
    const visibleStart = from < start ? start : from;
    const visibleEnd = until && until < end ? until : end;
    const through = until && until <= end ? localTime(sorted[index+1].start-1).slice(0,10) : range.end;
    return [{...phase, visibleStart, visibleEnd, fromDay: visibleStart.slice(0,10), throughDay: through,
      details: `${phase.label}. Phase begins ${from} Pacific${until ? `; next phase begins ${until} Pacific` : '; no later phase is recorded'}.`}];
  });
}

export function trialPhaseBands(phases, range) {
  return trialPhasesInRange(phases, range).map(phase => ({type:'rect', xref:'x', yref:'paper',
    x0:phase.visibleStart, x1:phase.visibleEnd, y0:0, y1:1, line:{width:0},
    fillcolor:phase.color, opacity:0.07, layer:'below', name:phase.label}));
}
