/**
 * "Home record match" (wave 2, C5, decision 493; the PI, 2026-10-19: "Make it the 10 min average
 * covering it - but the [page setting] can change it with a warning that these are recommended
 * default settings"). How each pain report meets the home record (chronic log) when that log decides
 * a band: the one 10-minute average whose time covers the report (the recommended default), or the
 * readings inside the page's matching window. The page sends `ChronicMatch` only when it is not the
 * default (`matchingDefaults.chronicMatchParam`).
 */
import { FormControl, MenuItem, Select } from "@mui/material";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import { promptSelectSx } from "views/Reports/paper/selectStyle";
import { T, TYPE } from "assets/theme/base/tokens";
import { ControlLabel } from "./MatchWindowBand";
import { CHRONIC_MATCH_OPTIONS, MATCHING_DEFAULTS } from "./matchingDefaults";

export default function HomeRecordMatchControl({ value, onChange }) {
  const v = value || MATCHING_DEFAULTS.chronicMatch;
  const isDefault = v === MATCHING_DEFAULTS.chronicMatch;
  return (
    <MDBox data-testid="home-record-match">
      <ControlLabel note="Used where the home record (chronic log) decides a band; heat maps only.">
        {"Home record match"}
      </ControlLabel>
      <FormControl size="small" sx={{ minWidth: 240 }}>
        <Select value={v} onChange={(e) => onChange && onChange(e.target.value)}
          inputProps={{ id: "biomarkers-home-record-match", "aria-label": "home record match" }}
          sx={{ ...promptSelectSx, "& .MuiSelect-select": { ...TYPE.body, color: `${T.ink} !important` } }}>
          {CHRONIC_MATCH_OPTIONS.map((o) => (
            <MenuItem key={o.value} value={o.value} sx={{ ...TYPE.body }}>{o.label}</MenuItem>
          ))}
        </Select>
      </FormControl>
      {isDefault ? null : (
        <MDTypography component="p" data-testid="home-record-match-warning"
          sx={{ ...TYPE.body, color: T.caution, mt: 0.5, mb: 0 }}>
          {"\u25b2 Not the recommended default; every home-record answer carries a warning."}
        </MDTypography>
      )}
    </MDBox>
  );
}
