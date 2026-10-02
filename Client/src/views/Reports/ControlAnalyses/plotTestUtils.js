/**
 * Test helpers for the Plotly check figures: a Plotly stand-in that records every figure drawn, and
 * readers for what was drawn. Not a test file.
 */
export const plotlyMock = () => {
  const noop = () => {};
  const react = (el, data, layout, config) => {
    (global.__plots = global.__plots || []).push({ el, data, layout, config });
    return Promise.resolve();
  };
  const purge = (el) => { (global.__purged = global.__purged || []).push(el); };
  return { react, purge, Plots: { resize: noop } };
};

export const resetPlots = () => { global.__plots = []; global.__purged = []; };

/** The last figure drawn into each chart inside `node`. */
export const plotsIn = (node) => [...node.querySelectorAll('[data-testid="plotly-chart"]')]
  .map((el) => { const hits = (global.__plots || []).filter((p) => p.el === el); return hits[hits.length - 1]; })
  .filter(Boolean);

const colours = (v) => (Array.isArray(v) ? v : [v]).filter((c) => c !== undefined);
/** Every colour a figure's marks, lines and error bars use. */
export const markColours = (plot) => plot.data.flatMap((t) => [
  ...colours(t.marker && t.marker.color), ...colours(t.marker && t.marker.line && t.marker.line.color),
  ...colours(t.line && t.line.color), ...colours(t.error_y && t.error_y.color),
  ...colours(t.error_x && t.error_x.color)]);

/** Every hover text of a figure. */
export const hoverTexts = (plot) => plot.data.flatMap((t) => t.hovertext || []);

/** The x values of every trace of a figure, flat. */
export const allX = (plot) => plot.data.flatMap((t) => t.x || []);
