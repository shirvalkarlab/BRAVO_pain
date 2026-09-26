/**
 * Colours for data: marks, fills and colour scales in figures. Page text never uses these
 * directly; it uses `T.ink`, `T.ink3` or the text-safe variant in TEXT_VARIANT.
 *
 * Source: artifacts/design_2026-09-26_minimalist_redesign/SPEC.md section 3.1. The categorical
 * set is Okabe-Ito, readable by people with the common colour-vision differences, in a fixed order.
 */

// Okabe-Ito, fixed order. Marks and fills only.
export const CATEGORICAL = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9", "#D55E00"];

// The brain side, on every page, always: left blue, right orange.
export const SIDE = { left: "#0072B2", right: "#E69F00" };

// Pain groups: high vermillion, low blue, the middle third (not used) light grey.
export const PAIN = { high: "#D55E00", low: "#0072B2", middle: "#BDBDBD" };

// Grey marks drawn for context (3.36:1 on white).
export const CONTEXT = "#8C8C8C";

// When a figure colour must appear as text, the darker variant with at least 4.5:1 on white.
export const TEXT_VARIANT = { "#D55E00": "#A84300", "#009E73": "#00755A" };

/** The text-safe ink for a figure colour: its dark variant when it has one, else the colour. */
export const textInk = (color) => TEXT_VARIANT[color] || color;

// Diverging, blue -> light grey -> vermillion, nine stops. The ends and midpoint keep the
// StimOptimizer.designReview.test.js colour-stop pin (#0072B2, #E4E4E4, #D55E00).
export const DIVERGING = [
  [0.0, "#0072B2"], [0.125, "#3F8FC4"], [0.25, "#86B6D8"], [0.375, "#C4DAEA"],
  [0.5, "#E4E4E4"],
  [0.625, "#F1CDB0"], [0.75, "#E8A273"], [0.875, "#DE7B3A"], [1.0, "#D55E00"],
];

// Fixed symmetric ranges, printed on each key; values beyond saturate (the hover prints the
// true value). Current maps use +/- the largest |predicted pain - today's| across the card.
export const RANGE = {
  correlation: [-0.5, 0.5],
  areaUnderCurve: [0.25, 0.75], // centred on 0.5 = coin toss
};

// Sequential (cividis), for ordered quantities: frequency lanes, counts.
export const SEQUENTIAL = ["#00204D", "#213D6B", "#555B6C", "#7B7A77", "#A59C74", "#D3C064", "#FFE945"];

/** The DIVERGING stops as a CSS linear-gradient, for colour keys drawn in HTML. */
export const divergingGradient = (direction = "to right") =>
  `linear-gradient(${direction}, ${DIVERGING.map(([s, c]) => `${c} ${s * 100}%`).join(", ")})`;

export default { CATEGORICAL, SIDE, PAIN, CONTEXT, TEXT_VARIANT, DIVERGING, RANGE, SEQUENTIAL };
