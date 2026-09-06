// Pearson calculation adapted from FreeReps (MIT), copyright 2025–2026 meltforce.
// See docs/third-party/FreeReps-LICENSE.txt. Centered sums avoid cancellation.
export const STAGES = ["Awake", "REM", "Light", "Deep"];
export const COLORS = {Awake: "#c65d39", REM: "#b6c8cc", Light: "#658890", Deep: "#183f4b"};
const DAY = 86400000;

export function filterPoints(points, start, end) {
  return points.filter(p => Number.isFinite(p.value) && (!start || p.day >= start) && (!end || p.day <= end));
}

export function aggregatePoints(points, interval) {
  const groups = new Map();
  for (const p of points) {
    if (!Number.isFinite(p.value)) continue;
    let day = p.day;
    if (interval === "month") day = day.slice(0, 7) + "-01";
    if (interval === "week") {
      const date = new Date(day + "T00:00:00Z");
      date.setUTCDate(date.getUTCDate() - (date.getUTCDay() + 6) % 7);
      day = date.toISOString().slice(0, 10);
    }
    const group = groups.get(day) || {day, sum: 0, count: 0};
    group.sum += p.value; group.count += 1; groups.set(day, group);
  }
  return [...groups.values()].sort((a, b) => a.day.localeCompare(b.day))
    .map(p => ({day: p.day, value: p.sum / p.count, count: p.count}));
}

export function pairDays(xs, ys) {
  const lookup = new Map(ys.filter(p => Number.isFinite(p.value)).map(p => [p.day, p.value]));
  return xs.filter(p => Number.isFinite(p.value) && lookup.has(p.day))
    .map(p => ({day: p.day, x: p.value, y: lookup.get(p.day)}));
}

export function pearsonR(pairs) {
  if (pairs.length < 3) return null;
  const n = pairs.length;
  const mx = pairs.reduce((sum, p) => sum + p.x, 0) / n;
  const my = pairs.reduce((sum, p) => sum + p.y, 0) / n;
  let xx = 0, yy = 0, xy = 0;
  for (const p of pairs) {
    xx += (p.x - mx) ** 2; yy += (p.y - my) ** 2; xy += (p.x - mx) * (p.y - my);
  }
  const denominator = Math.sqrt(xx * yy);
  if (!Number.isFinite(denominator) || denominator === 0) return null;
  return Math.max(-1, Math.min(1, xy / denominator));
}

export function calendarSeries(points) {
  // Missing dates are explicit breaks: never draw across QC-excluded days.
  const result = [];
  for (const point of points) {
    const previous = result[result.length - 1];
    if (previous && new Date(point.day) - new Date(previous.day) > DAY) {
      result.push({day: new Date(new Date(previous.day).getTime() + DAY).toISOString().slice(0, 10), value: null});
    }
    result.push(point);
  }
  return result;
}

export function stageBlocks(stages, start, end) {
  if (!(end > start)) return [];
  return stages.filter(s => STAGES.includes(s.stage) && s.end > s.start && s.end > start && s.start < end)
    .map(s => ({...s, left: (Math.max(start, s.start) - start) / (end - start) * 100,
      width: (Math.min(end, s.end) - Math.max(start, s.start)) / (end - start) * 100,
      lane: STAGES.indexOf(s.stage)}));
}

export function defaultRange(metrics) {
  const days = metrics.flatMap(m => m.points.map(p => p.day)).sort();
  if (!days.length) return {start: "", end: ""};
  const end = days[days.length - 1];
  const start = new Date(new Date(end + "T00:00:00Z").getTime() - 89 * DAY).toISOString().slice(0, 10);
  return {start, end};
}
