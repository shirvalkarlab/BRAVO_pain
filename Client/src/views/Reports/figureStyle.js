/**
 * The figure defaults for every Plotly and SVG figure on the three pain pages (Biomarkers,
 * Closed-Loop, Stim Optimizer). Nothing else defines figure fonts, greys or Plotly configuration.
 *
 * Written 2026-09-26 for the minimalist redesign (SPEC.md section 3). The figure's title is its
 * card's question, so nothing is written on the canvas above the plot: no title, no legend box,
 * no gridlines, no zoom toolbar. Series are named by a label at their right end (`directLabel`).
 * Every size is 12 px, which keeps a margin above the 11 px minimum as drawn on screen.
 *
 * Use:
 *   const layout = plotlyLayout({ xaxis: { title: { text: "Current (mA)" } } });
 *   <Plot layout={layout} config={PLOTLY_CONFIG} ... />
 */
import { T, FONT_FAMILY as TOKEN_FONT } from "assets/theme/base/tokens";

export const FONT_FAMILY = TOKEN_FONT;

/** The one text size used inside figures, in px. */
export const FIGURE_TEXT_PX = 12;

const AXIS = {
  showgrid: false,
  zeroline: false,
  showline: true,
  linecolor: T.graphic,
  linewidth: 1,
  ticks: "outside",
  ticklen: 4,
  tickcolor: T.graphic,
  tickfont: { family: FONT_FAMILY, size: FIGURE_TEXT_PX, color: T.ink3 },
  title: { font: { family: FONT_FAMILY, size: FIGURE_TEXT_PX, color: T.ink3 }, standoff: 8 },
  automargin: true,
};

export const PLOTLY_LAYOUT = {
  font: { family: FONT_FAMILY, size: FIGURE_TEXT_PX, color: T.ink },
  paper_bgcolor: T.surface,
  plot_bgcolor: T.surface,
  margin: { l: 56, r: 72, t: 16, b: 44 }, // the right margin holds the direct labels
  showlegend: false, // series are labelled directly instead
  hoverlabel: {
    font: { family: FONT_FAMILY, size: FIGURE_TEXT_PX, color: T.ink },
    bgcolor: T.surface,
    bordercolor: T.rule,
  },
  xaxis: AXIS,
  yaxis: AXIS,
};

/** No zoom toolbar, no logo; the figure follows its container's width. Kept off for the figures
 * that have never carried a toolbar (the Biomarkers heat maps since decision 88; the current map;
 * the binarization preview). */
export const PLOTLY_CONFIG = { displayModeBar: false, responsive: true, displaylogo: false };

/**
 * The zoom/pan/save-as-PNG toolbar the redesign of 2026-09-26 took off every figure that had it,
 * with no way for a reviewer to save one for the deployment record; the PI put it back the same
 * day on the figures that had it before (the ROC curve, the per-state refit, statistical power,
 * the simulation, the three-source response, the sliding-correlation heat map, the band-time
 * sweep, the calibration panel). Shown on hover so it does not sit on the canvas otherwise; the
 * PNG export is a crisp 2x render for slides. Figures that never had a toolbar stay on
 * `PLOTLY_CONFIG` above.
 */
export const PLOTLY_CONFIG_WITH_TOOLBAR = {
  responsive: true,
  displaylogo: false,
  displayModeBar: "hover",
  modeBarButtonsToRemove: ["lasso2d", "select2d", "autoScale2d", "toggleSpikelines",
    "hoverClosestCartesian", "hoverCompareCartesian"],
  toImageButtonOptions: { format: "png", scale: 2 },
};

// Reference lines: chance, zero, the safe ceiling. Always labelled at the line's end.
export const REF_LINE = { color: T.graphic, width: 1, dash: "dash" };
/** The safe current ceiling; label it "safe ceiling 4.5 mA" (the value read from the server) in T.refused. */
export const CEILING_LINE = { color: T.refused, width: 1.5, dash: "dash" };
/** Month lines, on the timeline only. A line, never text. */
export const MONTH_GRID = "#EEEEEC";

/** A direct label: text at the right end of a series, in ink (or the series' text-safe ink). */
export const directLabel = (x, y, text, color = T.ink) => ({
  x,
  y,
  text,
  xanchor: "left",
  xshift: 6,
  showarrow: false,
  font: { family: FONT_FAMILY, size: FIGURE_TEXT_PX, color },
});

/**
 * Text inside SVG figures. SVG figures are drawn at the container's real pixel width (measured),
 * never scaled through a viewBox, so 12 px text stays 12 px on screen; below 480 px wide the
 * figure scrolls inside its card instead of shrinking.
 */
export const SVG_TEXT = { fontFamily: FONT_FAMILY, fontSize: FIGURE_TEXT_PX, fill: T.ink3 };
/** The narrowest an SVG figure is drawn; narrower cards scroll it sideways. */
export const SVG_MIN_WIDTH_PX = 480;

function isPlainObject(v) {
  return v !== null && typeof v === "object" && !Array.isArray(v);
}

/** Deep merge of plain objects; arrays and other values in `over` replace those in `base`. */
export function mergeDeep(base, over) {
  if (!isPlainObject(over)) return over === undefined ? base : over;
  const out = { ...(isPlainObject(base) ? base : {}) };
  Object.keys(over).forEach((k) => {
    out[k] = mergeDeep(out[k], over[k]);
  });
  return out;
}

/**
 * The default layout with a figure's own settings merged on top. Extra axes (`xaxis2`,
 * `yaxis2`, ...) named in `overrides` start from the same axis defaults.
 */
export function plotlyLayout(overrides = {}) {
  const base = { ...PLOTLY_LAYOUT };
  Object.keys(overrides).forEach((k) => {
    if (/^[xy]axis\d+$/.test(k) && !base[k]) base[k] = AXIS;
  });
  return mergeDeep(base, overrides);
}

export default PLOTLY_LAYOUT;
