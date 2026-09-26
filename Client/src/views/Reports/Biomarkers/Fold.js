/**
 * The Biomarkers page's fold: one 14 px row, "▸ Label (what is inside)", that opens to show its
 * content (the redesign of 2026-09-26, SPEC.md section 4 rule 4; the shared `paper/Fold` draws the
 * same row). This page keeps its own copy built on MUI's Collapse, because the page's layout test
 * reads "what a reader sees" as everything outside a closed Collapse (`.MuiCollapse-hidden`), and
 * because the Closed-Loop page's fold, which this page used to borrow, belongs to another package.
 *
 * The content stays MOUNTED while closed (hidden, not removed), so tests and search still read it.
 * Never fold a device refusal. No fold inside a fold.
 *
 * Props:
 *   show         the row's label (what the fold holds)
 *   inside       optional short note of what is inside, printed in brackets after the label
 *   hide         optional label while open (default: the same label)
 *   defaultOpen  boolean (default false)
 *   onChange     called with the new open state after each click
 */
import { useState } from "react";
import { Collapse } from "@mui/material";

import { T, TYPE, SPACE } from "assets/theme/base/tokens";

export default function Fold({ show, hide = null, inside = null, defaultOpen = false, onChange = null,
  children }) {
  const [open, setOpen] = useState(!!defaultOpen);
  const toggle = () => setOpen((o) => { const n = !o; if (onChange) onChange(n); return n; });
  return (
    <div data-paper="fold" style={{ marginTop: SPACE.xs }}>
      <button type="button" onClick={toggle} aria-expanded={open}
        style={{ ...TYPE.body, color: T.ink2, background: "none", border: 0, padding: 0,
          cursor: "pointer", fontFamily: "inherit", textAlign: "left", display: "inline-flex",
          gap: SPACE.xs, alignItems: "baseline" }}>
        <span aria-hidden="true" style={{ color: T.ink3, display: "inline-block", width: "1em",
          transform: open ? "rotate(90deg)" : "none", transition: "transform .15s" }}>{"▸"}</span>
        <span>{open && hide ? hide : show}</span>
        {inside ? <span style={{ color: T.ink3 }}>{`(${inside})`}</span> : null}
      </button>
      <Collapse in={open} unmountOnExit={false}>
        <div style={{ marginTop: SPACE.xs, ...TYPE.body, color: T.ink2 }}>{children}</div>
      </Collapse>
    </div>
  );
}
