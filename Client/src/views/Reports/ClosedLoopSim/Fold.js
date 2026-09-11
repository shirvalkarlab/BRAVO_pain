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

export default function Fold({ show, hide, defaultOpen = false, children, mt = 0.6, dense = false }) {
  const [open, setOpen] = useState(!!defaultOpen);
  return (
    <MDBox mt={mt}>
      <MDTypography variant="caption" component="button" type="button"
        onClick={() => setOpen((o) => !o)} aria-expanded={open}
        sx={{ fontSize: dense ? 10.5 : 11, color: PAL.accent, cursor: "pointer", display: "inline-flex",
          alignItems: "center", gap: 0.5, background: "none", border: 0, padding: 0,
          fontFamily: "inherit", "&:hover": { textDecoration: "underline" },
          "&:focus-visible": { outline: `2px solid ${PAL.accent}`, outlineOffset: 2,
            borderRadius: "3px" } }}>
        <span aria-hidden="true" style={{ display: "inline-block", fontSize: 9,
          transform: open ? "rotate(90deg)" : "none", transition: "transform .15s" }}>▶</span>
        {open ? (hide || "Hide") : show}
      </MDTypography>
      <Collapse in={open} unmountOnExit={false}>
        <MDBox mt={0.4}>{children}</MDBox>
      </Collapse>
    </MDBox>
  );
}
