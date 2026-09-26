/**
 * A fold: one 14 px row, "▸ Label (what is inside)", that opens to show its content.
 *
 * Written 2026-09-26 for the minimalist redesign (SPEC.md section 4, rule 4). The content stays
 * MOUNTED while closed (it is hidden, not removed), so tests and search can still read it.
 * Fold methods, alternative views, rows for combinations the device refuses today, research
 * checks and calibration. Never fold a device refusal, the safe ceiling, "not a value to
 * program" or a "held, not refused" note. No fold inside a fold.
 *
 * Props:
 *   label        what the row says ("How this was worked out")
 *   inside       optional short note of what is inside, printed in brackets
 *   defaultOpen  boolean (default false)
 *   onChange     called with the new open state after each click
 *   children     the folded content
 */
import { useState, useId } from "react";
import PropTypes from "prop-types";

import { T, TYPE, SPACE } from "assets/theme/base/tokens";

export default function Fold({ label, inside, defaultOpen, onChange, children }) {
  const [open, setOpen] = useState(!!defaultOpen);
  const id = useId();
  const toggle = () => {
    const next = !open;
    setOpen(next);
    if (onChange) onChange(next);
  };
  return (
    <div data-paper="fold">
      <button type="button" onClick={toggle} aria-expanded={open} aria-controls={id}
        style={{ ...TYPE.body, color: T.ink2, background: "none", border: 0, padding: 0,
          cursor: "pointer", fontFamily: "inherit", textAlign: "left", display: "inline-flex",
          gap: SPACE.xs, alignItems: "baseline" }}>
        <span aria-hidden="true" style={{ color: T.ink3, display: "inline-block", width: "1em",
          transform: open ? "rotate(90deg)" : "none", transition: "transform .15s" }}>▸</span>
        <span>
          {label}
          {inside ? <span style={{ color: T.ink3 }}>{` (${inside})`}</span> : null}
        </span>
      </button>
      <div id={id} hidden={!open} style={{ marginTop: SPACE.xs, ...TYPE.body, color: T.ink2 }}>
        {children}
      </div>
    </div>
  );
}

Fold.propTypes = {
  label: PropTypes.node.isRequired,
  inside: PropTypes.node,
  defaultOpen: PropTypes.bool,
  onChange: PropTypes.func,
  children: PropTypes.node,
};

Fold.defaultProps = { inside: null, defaultOpen: false, onChange: null, children: null };
