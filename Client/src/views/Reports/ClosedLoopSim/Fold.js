/**
 * A reveal/hide control for explanatory text, so the numbers on a card stay in the open and the
 * prose that explains them sits one click away.
 *
 * Added 2026-09-11 for the Closed-Loop page redesign. The PI's words: "Text everywhere makes it
 * really verbose, so maybe it should be a dropdown like reveal this, don't reveal this panel."
 * Every panel on the page folds its explanatory paragraphs through this one component, so the
 * control looks and behaves the same everywhere: a small link-styled toggle, closed by default,
 * that opens a Collapse. Values, verdicts, symbols and warnings are never put inside a Fold --
 * only the sentences that say how they were arrived at.
 *
 * `show` / `hide` are the two labels; `show` should name what is inside ("How this is measured",
 * "Show all 51 rules") so a reader knows what the click buys before making it.
 */
import { useState } from "react";
import { Collapse } from "@mui/material";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import PAL from "./palette";
import FoldArrow from "../paper/FoldArrow";

export default function Fold({ show, hide, defaultOpen = false, children, mt = 0.6, dense = false,
  onChange = null }) {
  const [open, setOpen] = useState(!!defaultOpen);
  // `onChange(open)` (2026-09-12) lets a caller learn when the fold is first opened: a Plotly
  // figure first drawn inside a hidden container measures itself at 0 px wide (the Closed-Loop
  // page's three-source panel met this, decision 123), so the Stim Optimizer page mounts its
  // surfaces on first reveal rather than on first render. Children stay mounted, as before.
  const toggle = () => setOpen((o) => { const n = !o; if (onChange) onChange(n); return n; });
  // Drawn as the redesign's fold row (SPEC 2026-09-26 section 4 rule 4): one 14 px row in the body
  // ink, "▸ Label", the arrow turning when open. `dense` is kept for callers and changes nothing:
  // no text on the page is smaller than 12 px.
  return (
    <MDBox mt={mt} data-dense={dense ? "" : undefined}>
      <MDTypography variant="caption" component="button" type="button"
        onClick={toggle} aria-expanded={open}
        sx={{ fontSize: PAL.fs.body, lineHeight: "22px", color: PAL.ink2, cursor: "pointer",
          display: "inline-flex", alignItems: "center", gap: 1, background: "none", border: 0,
          padding: 0, fontFamily: "inherit", textAlign: "left",
          "&:hover": { textDecoration: "underline" },
          "&:focus-visible": { outline: `2px solid ${PAL.accent}`, outlineOffset: 2,
            borderRadius: "4px" } }}>
        <FoldArrow open={open} />
        {show}
      </MDTypography>
      <Collapse in={open} unmountOnExit={false}>
        <MDBox mt={1}>{children}</MDBox>
      </Collapse>
    </MDBox>
  );
}
