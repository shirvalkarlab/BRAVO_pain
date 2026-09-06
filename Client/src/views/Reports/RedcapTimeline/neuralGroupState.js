// A610 pp35/39: cycling is group-wide and unavailable with adaptive therapy;
// every adaptive program in a group uses the same threshold mode.
const recorded = value => typeof value === 'string' && value.trim() !== '' && !/^(not recorded|unknown|na)$/i.test(value.trim());
const normalize = value => String(value ?? '').trim().toLowerCase().replace(/[_-]+/g,' ').replace(/\s+/g,' ');
const values = rows => Object.fromEntries((rows || []).map(row => [row.label,row.value]));
const missing = label => ({label,order:[9]});
const conflict = warning => ({label:`Conflicting settings · ${warning}`,order:[10],warning});

function programs(settings) {
  return ['left','right'].flatMap(side => {
    const result = new Map();
    for (const row of settings[side] || []) {
      const match = row.label.match(/^Program (\d+) · (.+)$/);
      const key = match ? match[1] : '';
      if (!result.has(key)) result.set(key,{});
      result.get(key)[match ? match[2] : row.label] = row.value;
    }
    return [...result.values()];
  });
}

function duration(raw) {
  const match = String(raw).trim().match(/^([+]?(?:\d+(?:\.\d*)?|\.\d+))\s*(s|sec|seconds?|ms|milliseconds?|min|minutes?)$/i);
  if (!match || !Number.isFinite(Number(match[1]))) return null;
  const unit = match[2].toLowerCase();
  return Number(match[1]) / (/^(ms|millisecond)/.test(unit) ? 60000 : /^min/.test(unit) ? 1 : 60);
}

function cycling(raw) {
  if (/^off$/i.test(String(raw).trim())) return {enabled:false};
  const match = String(raw).trim().match(/^on\s*·\s*on\s+(.+?)\s*\/\s*off\s+(.+)$/i);
  if (match) return {enabled:true,on:duration(match[1]),off:duration(match[2])};
  if (/^on$/i.test(String(raw).trim())) return {enabled:true,on:null,off:null};
  return {enabled:null};
}

const minutes = value => value === null ? 'not recorded' : `${Number(value.toPrecision(6))} min`;

export function groupState(settings = {}) {
  const source = settings || {};
  const shared = values(source.group);
  const mode = normalize(shared['Mode at observation']);
  const fixed = /^(open loop|open loop \/ fixed stimulation|open loop \/ fixed|fixed stimulation)$/.test(mode);
  const closed = mode === 'closed loop';
  const cycle = cycling(shared.Cycling);
  const channels = programs(source);
  const states = channels.map(program => normalize(program['Adaptive state']));
  const running = states.some(state => state === 'running');
  const configured = channels.filter(program => {
    const state = normalize(program['Adaptive state']);
    return state === 'running' || state === 'suspended' || state === 'paused';
  });
  const thresholds = configured.map(program => normalize(program['Threshold mode']));
  const knownThresholds = thresholds.filter(recorded);
  if (new Set(knownThresholds).size > 1) return conflict('Adaptive programs report different threshold modes');
  if (cycle.enabled && configured.length) return conflict('Cycling and configured adaptive therapy are both recorded');
  if (fixed && running) return conflict('Group mode is open loop but an adaptive program is running');
  if (closed && states.length && !running && states.every(state => ['suspended','paused','not configured'].includes(state))) {
    return conflict('Group mode is closed loop but no recorded adaptive program is running');
  }
  if (!fixed && !closed) {
    return missing(recorded(shared['Mode at observation']) ? `Group mode not recognized · ${shared['Mode at observation']}` : 'Group mode not recorded');
  }
  if (fixed) {
    const paused = states.some(state => state === 'paused' || state === 'suspended');
    const label = paused ? 'Adaptive paused / fixed' : 'Open loop / fixed';
    if (cycle.enabled === false) return {label:`${label} · No cycling`,order:[0]};
    if (cycle.enabled === null) return missing(`${label} · Cycling not recorded`);
    const text = `${label} · Cycling on ${minutes(cycle.on)} / off ${minutes(cycle.off)}`;
    return {label:text,order:cycle.on === null || cycle.off === null ? [9] : [1,cycle.on,cycle.off]};
  }
  if (cycle.enabled === true) return conflict('Closed-loop group also records cycling');
  if (cycle.enabled === null) return missing('Closed loop · Cycling not recorded');
  if (!thresholds.length || thresholds.some(value => !recorded(value))) return missing('Closed loop · Threshold mode not recorded');
  const threshold = knownThresholds[0];
  if (/^single threshold inverse$/.test(threshold)) return conflict('Single threshold inverse is sensing-only, not adaptive delivery');
  if (/^single threshold(?: direct)?$/.test(threshold)) return {label:'Closed loop · single threshold',order:[2,0]};
  if (/^dual threshold(?: direct)?$/.test(threshold)) return {label:'Closed loop · dual threshold',order:[2,1]};
  return missing(`Closed loop · Threshold mode not recognized: ${threshold}`);
}

export function compareGroupStates(a,b) {
  const length = Math.max(a.order.length,b.order.length);
  for (let index=0; index<length; index++) {
    const difference = (a.order[index] ?? 0) - (b.order[index] ?? 0);
    if (difference) return difference;
  }
  return a.label.localeCompare(b.label);
}
