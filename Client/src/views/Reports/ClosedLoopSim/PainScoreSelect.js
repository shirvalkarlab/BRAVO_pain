/**
 * The pain score every band-to-pain reading on the Closed-Loop page is computed on (the PI,
 * 2026-09-25 night: nothing on this page is computed on NRS alone). Beside the band selection at the
 * top. It offers the Biomarkers heat maps' own choices -- the server's list when the grid has sent
 * one, else the shared copy -- and starts on the pain score of the grid the chosen band came from
 * (decision 254), or on NRS, said as such, when the band carries none. The choice drives the
 * evidence triangle's band-to-pain and current-to-pain readings, the stability card and its
 * per-state odds ratios, and the deployment summary with its mixed model.
 */
import { FormControl, MenuItem, Select } from "@mui/material";
import MDBox from "components/MDBox";
import { promptSelectSx } from "views/Reports/paper/selectStyle";
import MDTypography from "components/MDTypography";

import { PAIN_SCORE_OPTIONS, painScoreLabel } from "views/Reports/painScores";
import PAL from "./palette";

export function painScoreSourceText(value, bandDefault, options = PAIN_SCORE_OPTIONS) {
  const d = bandDefault || {};
  if (!d.fromBand) {
    return value === d.key
      ? "The chosen band carries no pain score, so NRS is used until another is chosen here."
      : `Chosen here; the band carries no pain score of its own.`;
  }
  return value === d.key
    ? "The pain score of the grid this band was chosen on."
    : `Chosen here; the band was chosen on ${painScoreLabel(d.key, options)}.`;
}

/**
 * The pain score the page head names: the report's own label when a report is on screen, else the
 * dropdown's choice by its label (while the report loads, or is withheld for another band or score).
 * The old fallback read a `label` that `bandPainScore` never returns, so the head dropped the score.
 */
export function pageHeadPainLabel(reportData, painScore, options = PAIN_SCORE_OPTIONS) {
  const own = reportData && reportData.pain_score && reportData.pain_score.label;
  if (own) return own;
  return painScore ? painScoreLabel(painScore, options) : null;
}

export default function PainScoreSelect({ value, bandDefault, options, onChange }) {
  const opts = (options && options.length) ? options : PAIN_SCORE_OPTIONS;
  return (
    <MDBox display="flex" flexDirection="column" sx={{ minWidth: 230, maxWidth: 360 }}>
      <MDBox display="flex" alignItems="center" gap={1}>
        <MDTypography variant="caption" sx={{ fontSize: PAL.fs.body, fontWeight: 600, color: PAL.ink }}>
          Pain score
        </MDTypography>
        <FormControl size="small">
          <Select value={value} onChange={(e) => onChange(e.target.value)}
            inputProps={{ "aria-label": "Pain score for every band-to-pain reading on this page" }}
            sx={{ fontSize: PAL.fs.body, minWidth: 180, ...promptSelectSx, "& .MuiSelect-select": { py: 0.75 } }}>
            {opts.map((m) => (
              <MenuItem key={m.key} value={m.key} sx={{ fontSize: PAL.fs.body }}>{m.label}</MenuItem>
            ))}
          </Select>
        </FormControl>
      </MDBox>
      <MDTypography variant="caption" sx={{ fontSize: PAL.fs.body, lineHeight: "18px", color: PAL.ink3, mt: 0.5 }}>
        {`Every chart below uses this score. ${painScoreSourceText(value, bandDefault, opts)}`}
      </MDTypography>
    </MDBox>
  );
}
