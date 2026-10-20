/** Keep measured zeroes and missing gaps; an unknown interval is a point, not a hold. */
export function timelinePoints(times, values, durations) {
  const line = { x: [], y: [] };
  const points = { x: [], y: [] };
  times.forEach((time, index) => {
    const value = values[index];
    if (!Number.isFinite(time) || !Number.isFinite(value)) return;
    const start = time * 1000;
    if (!Number.isFinite(new Date(start).getTime())) return;
    const duration = typeof durations === "number" ? durations : durations?.[index];
    const end = start + duration * 1000;
    if (Number.isFinite(duration) && duration > 0 && Number.isFinite(new Date(end).getTime())) {
      // A null delimiter prevents Plotly connecting separate observed intervals.
      line.x.push(new Date(start), new Date(end), null);
      line.y.push(value, value, null);
    } else {
      points.x.push(new Date(start));
      points.y.push(value);
    }
  });
  return { line, points };
}

export function timelineChannelUnit(data, channel) {
  const units = new Set();
  data.forEach((series) => {
    const index = series.ChannelNames.indexOf(channel);
    if (index < 0) return;
    const unit = series.ChannelUnits?.[index];
    if (unit && unit !== "Category") units.add(unit);
  });
  // A shared axis must never be assigned one of several incompatible units.
  return units.size === 1 ? [...units][0] : "";
}
