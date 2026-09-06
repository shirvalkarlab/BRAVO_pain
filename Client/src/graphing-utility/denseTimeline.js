// Dense timelines use one accelerated trace per identical channel/style. Null
// separators preserve every recording boundary; all original points remain.
export function mergeDenseLineSeries(series, threshold = 10000) {
  const groups = new Map();
  for (const item of series) {
    if (item.type !== "lineseries") continue;
    const key = JSON.stringify([item.axName, item.options]);
    if (!groups.has(key)) groups.set(key, {items: [], count: 0});
    const group = groups.get(key); group.items.push(item); group.count += item.x.length;
  }
  const replacements = new Map();
  for (const group of groups.values()) {
    if (group.count <= threshold) continue;
    const x = [], y = [];
    for (const item of group.items) {
      for (let i = 0; i < item.x.length; i++) { x.push(item.x[i]); y.push(item.y[i]); }
      x.push(null); y.push(null);
      replacements.set(item, null);
    }
    const first = group.items[0];
    replacements.set(first, {...first, x, y, options: {...first.options, type: "scattergl", connectgaps: false}});
  }
  return series.flatMap(item => replacements.has(item) ? (replacements.get(item) ? [replacements.get(item)] : []) : [item]);
}

export function mergeAnnotationSeries(series, threshold = 100) {
  const groups = new Map();
  for (const item of series) {
    if (item.type !== 'annotations') continue;
    const {id, ...style} = item.options;
    const key = JSON.stringify([item.axName, style]);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(item);
  }
  const replacements = new Map();
  for (const items of groups.values()) {
    if (items.length <= threshold) continue;
    const x = [], y = [], customdata = [];
    for (const item of items) {
      for (let i = 0; i < item.x.length; i++) {
        x.push(item.x[i]); y.push(item.y[i]); customdata.push(item.options.id);
      }
      x.push(null); y.push(null); customdata.push(null);
      replacements.set(item, null);
    }
    const first = items[0];
    replacements.set(first, {...first, x, y, options: {...first.options, customdata, type: "scattergl", connectgaps: false}});
  }
  return series.flatMap(item => replacements.has(item) ? (replacements.get(item) ? [replacements.get(item)] : []) : [item]);
}
