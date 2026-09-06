// Combine only adjacent intervals with identical labels. No samples are averaged,
// and gaps and category transitions retain their original boundaries.
export function categoricalIntervals(times, durations, values) {
  const x = [], y = [], base = [];
  for (let i = 0; i < times.length; i++) {
    const start = times[i] * 1000;
    const width = (typeof durations === "number" ? durations : durations[i]) * 1000;
    const last = x.length - 1;
    if (last >= 0 && y[last] === values[i] && base[last].getTime() + x[last] === start) {
      x[last] += width;
    } else {
      x.push(width); y.push(values[i]); base.push(new Date(start));
    }
  }
  return {x, y, base};
}

export function categoricalSegments(intervals) {
  const x = [], y = [];
  for (let i = 0; i < intervals.x.length; i++) {
    x.push(intervals.base[i], new Date(intervals.base[i].getTime() + intervals.x[i]), null);
    y.push(intervals.y[i], intervals.y[i], null);
  }
  return {x, y};
}
