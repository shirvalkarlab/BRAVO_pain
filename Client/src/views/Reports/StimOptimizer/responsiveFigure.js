// Presentation only: never resample the posterior, safe-set boundary, or observed trajectory.
export const figureText = (text = "") => String(text).replace(/<br\s*\/?\s*>/gi, " · ").replace(/<[^>]*>/g, "");
const axisTitle = (title) => typeof title === "string" ? {text: title} : title;
const wrap = (text, limit) => figureText(text).split(" ").reduce((lines, word) => {
  if (lines[lines.length - 1].length + word.length > limit) lines.push(word);
  else lines[lines.length - 1] += (lines[lines.length - 1] ? " " : "") + word;
  return lines;
}, [""]).join("<br>");

export function responsiveFigure(figure, width) {
  const source = figure.layout || {};
  const compact = width < 700;
  const layout = {...source, autosize: true, width: undefined, title: undefined,
    font: {family: "Roboto, sans-serif", size: 12, color: "#344767"},
    paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)"};
  const notes = [figureText(typeof source.title === "string" ? source.title : source.title?.text)].filter(Boolean);
  const panels = Object.keys(source).filter((key) => /^xaxis\d*$/.test(key)).map((key) => {
    const x = source[key];
    const yKey = (x.anchor || key.replace("xaxis", "y")).replace(/^y/, "yaxis");
    const y = source[yKey] || {};
    return {key, yKey, x, y, xd: x.domain || [0, 1], yd: y.domain || [0, 1]};
  }).sort((a, b) => b.yd[1] - a.yd[1] || a.xd[0] - b.xd[0]);
  const count = Math.max(1, panels.length);
  const gap = 0.17 / count;
  panels.forEach((panel, index) => {
    const row = panels.filter((p) => p.yd[0] === panel.yd[0]);
    panel.domain = compact ? [1 - (index + 1) / count + gap, 1 - index / count] : panel.yd;
    layout[panel.key] = {...panel.x, domain: compact ? [0, 1] : panel.xd,
      automargin: true, nticks: compact ? 4 : 7, tickfont: {size: 11},
      title: {...axisTitle(panel.x.title || row.find((p) => axisTitle(p.x.title)?.text)?.x.title), font: {size: 12}, standoff: 10}};
    layout[panel.yKey] = {...panel.y, domain: panel.domain, automargin: true, tickfont: {size: 11},
      title: {...axisTitle(panel.y.title || row.find((p) => axisTitle(p.y.title)?.text)?.y.title), font: {size: 12}, standoff: 8}};
    if (compact && panel.x.tickvals?.length > 5) {
      const step = Math.ceil((panel.x.tickvals.length - 1) / 4);
      const indices = panel.x.tickvals.map((_, i) => i).filter((i) => i % step === 0 || i === panel.x.tickvals.length - 1);
      layout[panel.key].tickvals = indices.map((i) => panel.x.tickvals[i]);
      if (panel.x.ticktext) layout[panel.key].ticktext = indices.map((i) => panel.x.ticktext[i]);
    }
    // Shared axis labels were suppressed in the original adjacent panels; each stacked panel
    // needs its own scale labels. Matching itself still preserves the shared numerical range.
    if (compact) { layout[panel.key].showticklabels = true; layout[panel.yKey].showticklabels = true; }
  });
  layout.annotations = (source.annotations || []).flatMap((annotation) => {
    const a = {...annotation};
    if (a.yref === "paper" && (a.y < 0 || a.y > 1.05)) { notes.push(figureText(a.text)); return []; }
    if (compact && a.xref === "paper" && a.yref === "paper" && panels.length) {
      // Plotly subplot headings use paper coordinates at the original panel's top center.
      const panel = [...panels].sort((p, q) =>
        (Math.abs(p.yd[1] - a.y) + Math.abs((p.xd[0] + p.xd[1]) / 2 - a.x)) -
        (Math.abs(q.yd[1] - a.y) + Math.abs((q.xd[0] + q.xd[1]) / 2 - a.x)))[0];
      a.x = 0; a.xanchor = "left"; a.y = panel.domain[1]; a.yshift = 18; a.yanchor = "bottom";
    }
    if (compact) { a.text = wrap(a.text, 27); a.font = {...a.font, size: 11}; }
    return [a];
  });
  const data = (figure.data || []).map((trace) => {
    const next = {...trace};
    if (compact && next.name) next.name = wrap(next.name, 26);
    if (compact && next.text) {
      next.text = Array.isArray(next.text) ? next.text.map((text) => wrap(text, 24)) : wrap(next.text, 24);
      next.textposition = "top center";
    }
    if (compact && trace.colorbar) {
      const panel = panels.find((p) => p.yKey === (trace.yaxis || "y").replace(/^y/, "yaxis"));
      const domain = panel?.domain || [0, 1];
      next.colorbar = {...trace.colorbar, x: 1.02, y: (domain[0] + domain[1]) / 2,
        len: (domain[1] - domain[0]) * 0.8, thickness: 10, tickfont: {size: 10},
        title: {...axisTitle(trace.colorbar.title), font: {size: 11}}};
    }
    return next;
  });
  const legendRows = data.filter((trace) => trace.name && trace.showlegend !== false).length;
  layout.margin = {l: compact ? 52 : 70, r: compact ? 68 : 45, t: 75, b: 75 + (compact ? legendRows * 34 : 45)};
  layout.height = compact ? count * 350 + layout.margin.t + layout.margin.b : source.height || 520;
  layout.legend = {...source.legend, orientation: "h", x: 0, xanchor: "left", y: -0.04, yanchor: "top", font: {size: 11}};
  return {data, layout, notes};
}
