/**
 * The safe current ceiling line, on the Stim Optimizer and Closed-Loop pages:
 * "Safe current ceiling: 4.5 mA left, 4.5 mA right (set by the PI). Nothing above it is offered
 * on this page."
 *
 * Written 2026-09-26 for the minimalist redesign (SPEC.md section 4, rule 1). The two values
 * are READ FROM THE SERVER and passed in; nothing here types a current. When a side's value is
 * missing the line says so rather than printing a number. Never folded.
 *
 * Props:
 *   leftMa, rightMa  numbers (mA) from the server's response, or null when not sent
 *   source           who set it (default "set by the PI")
 */
import PropTypes from "prop-types";

import { T, TYPE } from "assets/theme/base/tokens";

export function formatMa(v) {
  if (v === null || v === undefined || !Number.isFinite(Number(v))) return null;
  const n = Number(v);
  return `${Number.isInteger(n) ? n.toFixed(1) : String(n)} mA`;
}

export function ceilingSentence(leftMa, rightMa, source = "set by the PI") {
  const l = formatMa(leftMa);
  const r = formatMa(rightMa);
  if (!l && !r) {
    return "Safe current ceiling: not received from the server, so no current is offered on this page.";
  }
  const left = l ? `${l} left` : "left not received";
  const right = r ? `${r} right` : "right not received";
  return `Safe current ceiling: ${left}, ${right} (${source}). Nothing above it is offered on this page.`;
}

export default function CeilingLine({ leftMa, rightMa, source }) {
  return (
    <p data-paper="ceiling-line" style={{ margin: 0, ...TYPE.body, color: T.ink }}>
      {ceilingSentence(leftMa, rightMa, source)}
    </p>
  );
}

CeilingLine.propTypes = {
  leftMa: PropTypes.number,
  rightMa: PropTypes.number,
  source: PropTypes.string,
};

CeilingLine.defaultProps = { leftMa: null, rightMa: null, source: "set by the PI" };
