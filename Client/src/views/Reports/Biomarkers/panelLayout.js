/**
 * One definition of where the drawn plot area sits inside each of the four plots under the Biomarkers
 * heat-map title: the two heat maps, the scatter and the violin (the PI, 2026-10-02: the scatter and
 * violin sat off to the left of the heat maps above them).
 *
 * The left margin holds the axis labels and the right margin is a small gap; both come from here, so
 * the four plot areas have the same inset from their own box. The scatter and the violin are squares
 * no wider than `side`; their box is centred in the column the heat map fills, so the centre of each
 * square's plot area is the centre of the heat map's plot area above it, at every column width. They
 * carry no fixed pixel width, so on a phone the square shrinks to its column instead of overflowing.
 */
export const PLOT_MARGIN = { l: 56, r: 8, t: 8, b: 44 };

/** One bottom margin for both heat maps, the scatter and the violin, so the bottom edges of their
 *  plot areas sit on one line (the PI, 2026-10-02: "make sure plots are vertically aligned"; the
 *  scatter had 36 px, the others 44). */
export const PLOT_BOTTOM = 44;

/** The shared margin, with the bottom margin a plot needs for its own axis. */
export const plotMargin = (b = PLOT_MARGIN.b) => ({ ...PLOT_MARGIN, b });

/** The style of a square plot's box: the column's width up to `side`, centred. */
export const panelBoxStyle = (side) => ({
  width: "100%", maxWidth: side, margin: "0 auto", aspectRatio: "1 / 1",
});
