/**
 * THE ONE DROPDOWN STYLE for every pain-score, contact-pair, split-rule and check selector on the
 * report pages (the PI, 2026-10-02: "make these metric dropdowns slightly more prominent with a blue
 * border"; it was hard to tell what was a control on the Closed-Loop, Biomarkers and Adjust-matching
 * pages). A 1.5 px outline in the page's one accent blue (`T.accent`, the colour that already marks
 * the selected tab and the primary button), 2 px when focused, on the white surface. Spread it into
 * a MUI `Select`'s `sx`: `sx={{ ...TYPE.body, ...promptSelectSx }}`.
 */
import { T } from "assets/theme/base/tokens";

export const promptSelectSx = {
  borderRadius: "6px",
  background: T.surface,
  "& .MuiOutlinedInput-notchedOutline": { borderColor: T.accent, borderWidth: "1.5px" },
  "&:hover .MuiOutlinedInput-notchedOutline": { borderColor: T.accent, borderWidth: "1.5px" },
  "&.Mui-focused .MuiOutlinedInput-notchedOutline": { borderColor: T.accent, borderWidth: "2px" },
};
