/**
 * The ⋯ menu at the right of the Closed-Loop page's controls row (SPEC 2026-09-26 section 4 rule 2:
 * "Developer actions (load a saved band file, clear, stored results) go in one ⋯ menu").
 *
 * Loading a saved band file and clearing the chosen band are actions a clinician rarely needs at
 * the programmer, so they leave the head of the page. The menu's content stays MOUNTED while it is
 * closed (hidden, not removed), so the stored-results line inside it can still be read by tests and
 * by search. It is a menu, not a fold: it floats over the page with the one soft shadow the design
 * allows for menus, and it closes on Escape.
 *
 * Props:
 *   onLoad    opens the file chooser for a saved band file
 *   onClear   clears the chosen band, or null when there is none to clear
 *   children  anything else for a developer (the "Stored results" fold)
 */
import { useEffect, useId, useState } from "react";
import PropTypes from "prop-types";

import { T, TYPE, SHADOW, RADIUS, CARD } from "assets/theme/base/tokens";

const ITEM = {
  ...TYPE.body, display: "block", width: "100%", textAlign: "left", background: "none", border: 0,
  padding: "4px 0", color: T.ink, cursor: "pointer", fontFamily: "inherit",
};

export default function DeveloperMenu({ onLoad, onClear, children }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);
  return (
    <div style={{ position: "relative" }}>
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open}
        aria-controls={id} aria-label="More actions: load a saved band file, clear, stored results"
        style={{ ...TYPE.lead, lineHeight: "20px", minWidth: 36, height: 36, background: T.surface,
          border: `1px solid ${T.ink3}`, borderRadius: RADIUS.sm, color: T.ink, cursor: "pointer",
          fontFamily: "inherit" }}>
        ⋯
      </button>
      <div id={id} hidden={!open} role="group" aria-label="More actions"
        style={{ ...CARD, boxShadow: SHADOW.overlay, position: "absolute", right: 0, top: 40,
          zIndex: 10, padding: 16, width: 300 }}>
        <button type="button" style={ITEM} onClick={() => { setOpen(false); if (onLoad) onLoad(); }}>
          Load a saved band file
        </button>
        {onClear ? (
          <button type="button" style={ITEM} onClick={() => { setOpen(false); onClear(); }}>
            Clear the chosen band
          </button>
        ) : null}
        {children ? <div style={{ marginTop: 8, borderTop: `1px solid ${T.rule}`, paddingTop: 8 }}>{children}</div> : null}
      </div>
    </div>
  );
}

DeveloperMenu.propTypes = {
  onLoad: PropTypes.func,
  onClear: PropTypes.func,
  children: PropTypes.node,
};

DeveloperMenu.defaultProps = { onLoad: null, onClear: null, children: null };
