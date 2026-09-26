/**
 * A colour key: a thin bar, 8 px tall, above a heat map (or once per row of small multiples),
 * its ends and middle labelled in words in grey, e.g.
 *   "falls with pain  ←  0  →  rises with pain"
 *   "lower in high pain  ←  0.5 coin toss  →  higher in high pain"
 *
 * Written 2026-09-26 for the minimalist redesign (SPEC.md section 3.2). The range is fixed and
 * printed; values beyond it draw at the end colour, and the hover still prints the true value.
 *
 * Props:
 *   scale     Plotly-style stops [[0, "#hex"], ..., [1, "#hex"]] (default DIVERGING)
 *   range     [low, high] printed at the ends (numbers)
 *   lowLabel  words for the low end ("falls with pain")
 *   midLabel  words for the middle ("0" or "0.5 coin toss"); omitted when not given
 *   highLabel words for the high end ("rises with pain")
 *   title     optional words above the bar ("correlation with pain")
 *   width     bar width in px or CSS (default "100%", at most 320 px)
 */
import PropTypes from "prop-types";

import { T, TYPE, SPACE } from "assets/theme/base/tokens";
import { DIVERGING } from "assets/theme/base/dataColors";

export function gradientCss(scale, direction = "to right") {
  return `linear-gradient(${direction}, ${scale.map(([s, c]) => `${c} ${s * 100}%`).join(", ")})`;
}

function fmt(v) {
  if (v === null || v === undefined || !Number.isFinite(Number(v))) return "";
  const n = Number(v);
  return n < 0 ? `−${Math.abs(n)}` : String(n);
}

export default function ColorKey({ scale, range, lowLabel, midLabel, highLabel, title, width }) {
  const [lo, hi] = range || [];
  return (
    <div data-paper="color-key" style={{ width, maxWidth: 320, ...TYPE.caption, color: T.ink3 }}>
      {title ? <div style={{ marginBottom: SPACE.xxs }}>{title}</div> : null}
      <div aria-hidden="true" style={{ height: 8, background: gradientCss(scale),
        borderRadius: 1 }} />
      <div style={{ display: "flex", justifyContent: "space-between", gap: SPACE.xs,
        marginTop: SPACE.xxs }}>
        <span>{`${fmt(lo)}${lowLabel ? ` ${lowLabel}` : ""}`}</span>
        {midLabel ? <span>{midLabel}</span> : null}
        <span style={{ textAlign: "right" }}>{`${highLabel ? `${highLabel} ` : ""}${fmt(hi)}`}</span>
      </div>
    </div>
  );
}

ColorKey.propTypes = {
  scale: PropTypes.arrayOf(PropTypes.array),
  range: PropTypes.arrayOf(PropTypes.number),
  lowLabel: PropTypes.string,
  midLabel: PropTypes.string,
  highLabel: PropTypes.string,
  title: PropTypes.string,
  width: PropTypes.oneOfType([PropTypes.number, PropTypes.string]),
};

ColorKey.defaultProps = {
  scale: DIVERGING, range: [-0.5, 0.5], lowLabel: "", midLabel: "", highLabel: "", title: "",
  width: "100%",
};
