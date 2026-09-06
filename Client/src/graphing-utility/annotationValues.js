export function annotationValues(data, annotation, channel) {
  // Point events have no interval to summarize. Avoid scanning an entire
  // multiyear series once for every instantaneous event.
  if (!(annotation.Duration > 0)) return [];
  const values = [], end = annotation.Date + annotation.Duration;
  for (const series of data) {
    for (let j = 0; j < series.ChannelNames.length; j++) {
      if (series.ChannelNames[j] !== channel || !series.Data?.[j]) continue;
      for (let k = 0; k < series.Time.length; k++) {
        const value = series.Data[j][k];
        if (typeof value === 'number' && Number.isFinite(value) &&
            series.Time[k] > annotation.Date && series.Time[k] < end) values.push(value);
      }
    }
  }
  return values;
}
