/**
 * The Biomarkers page's fold is the shared one, `views/Reports/paper/Fold` (taste audit C6,
 * 2026-09-26: the page no longer keeps its own copy of the row). This file only keeps the page's
 * prop names, which source tests outside this folder pin (`show="..."`), and the one thing the
 * shared fold does not do: a different label while the fold is open (`hide`).
 *
 * The content stays MOUNTED while closed (the shared fold hides it with the `hidden` attribute),
 * so tests and search still read it. Never fold a device refusal. No fold inside a fold.
 *
 * Props:
 *   show         the row's label (what the fold holds)
 *   inside       optional short note of what is inside, printed in brackets after the label
 *   hide         optional label while open (default: the same label)
 *   defaultOpen  boolean (default false)
 *   onChange     called with the new open state after each click
 */
import { useState } from "react";

import PaperFold from "views/Reports/paper/Fold";

export default function Fold({ show, hide = null, inside = null, defaultOpen = false, onChange = null,
  children }) {
  const [open, setOpen] = useState(!!defaultOpen);
  const handle = (next) => { setOpen(next); if (onChange) onChange(next); };
  return (
    <PaperFold label={show} inside={inside} defaultOpen={!!defaultOpen}
      onChange={handle}>
      {children}
    </PaperFold>
  );
}
