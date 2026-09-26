/**
 * "How are reports paired with recordings?" -- the matching section of the Biomarkers page (the PI,
 * 2026-09-21, option C; laid out again in the redesign of 2026-09-26, SPEC.md section 5.1 item 3).
 *
 * One bold sentence says how many pain reports the match window admits (the section's answer); the
 * timing histogram is its figure; the settings that decide what is paired sit in one fold whose row
 * reads the settings in force ("Paired within ±60 min · each report picks its nearest recordings
 * ..."), and the rest under "More options". Each control carries one short sentence under it, always
 * shown (the "Expand descriptions" button is gone). Everything here changes the card below it
 * without a Recompute press.
 *
 * On screen: Biomarkers page, the matching section, above the high / low split preview.
 */
import { Grid, Select, MenuItem, FormControl, Slider, TextField, ToggleButton, ToggleButtonGroup } from "@mui/material";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import { T, TYPE } from "assets/theme/base/tokens";
import { PAIN } from "assets/theme/base/dataColors";

import TimingHistogram from "./TimingHistogram";
import Fold from "./Fold";

const LABEL_SX = { ...TYPE.body, fontWeight: 600, color: T.ink, display: "block", mb: 0.5 };
const NOTE_SX = { ...TYPE.caption, color: T.ink3, display: "block", mt: 0.5 };
// A small colour swatch beside a word (the colour is a mark, never the text's own colour).
const SWATCH = { display: "inline-block", width: 10, height: 10, marginRight: 6 };
const TOGGLE_SX = { "& .MuiToggleButton-root": { textTransform: "none", ...TYPE.body, py: 0.5, px: 1.25, lineHeight: 1.2 } };

/** The three ways a report and its recordings are paired, in plain words (SPEC.md section 6). */
export const DIRECTION_WORDS = {
  pro_first: "Each report picks its nearest recordings",
  nearest: "Each recording picks its nearest report",
  prior: "Each recording picks the next report after it",
};

/** The one-line summary the matching fold's row prints. */
export function matchingSummary({ matchTolerance, matchDirection, maxPerRating, includeClinicSheetRatings }) {
  const parts = [`Paired within \u00b1${matchTolerance} min`];
  if (DIRECTION_WORDS[matchDirection]) parts.push(DIRECTION_WORDS[matchDirection].toLowerCase());
  if (maxPerRating != null) parts.push(`up to ${maxPerRating} per report`);
  if (includeClinicSheetRatings != null) {
    parts.push(includeClinicSheetRatings ? "home surveys and clinic sheets" : "home surveys only");
  }
  return parts.join(" \u00b7 ");
}

/** "33rd", "67th": the percentile as a word, rounded to a whole number as the page always printed it. */
function ordinal(v) {
  const n = Math.round(Number(v));
  const tens = n % 100;
  const suffix = tens >= 11 && tens <= 13 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" }[n % 10] || "th");
  return `${n}${suffix}`;
}

export default function MatchWindowBand({
  coverage, metricLabel,
  matchTolerance, setMatchTolerance,
  strategy, setStrategy, strategyOptions, percentileLow, percentileHigh,
  matchDirection, setMatchDirection,
  scanIndex, painSeries,
  maxPerRating = null, includeClinicSheetRatings = null,
  extraControls = null, moreOptions = null,
}) {
  const score = metricLabel || "pain";
  const twoCut = strategy === "tertile" || strategy === "percentile";
  const lowPct = strategy === "tertile" ? 33.3 : percentileLow;
  const highPct = strategy === "tertile" ? 66.7 : percentileHigh;
  return (
    <MDBox display="flex" flexDirection="column" gap={2}>
      {/* THE COVERAGE SENTENCE: what the window admits and what it leaves out, following the slider live. */}
      {coverage && coverage.n_reports > 0 ? (
        <MDTypography component="div" data-testid="report-coverage"
                      sx={{ ...TYPE.lead, color: T.ink, maxWidth: "68ch" }} aria-live="polite">
          <b style={{ fontWeight: 600 }}>{`${coverage.n_within_window.toLocaleString()} of ${coverage.n_reports.toLocaleString()} ${score} reports have a band-power reading within ±${coverage.tolerance_min} min; ${coverage.n_within_10.toLocaleString()} within ±10 min; ${coverage.n_within_60.toLocaleString()} within ±60 min.`}</b>
        </MDTypography>
      ) : null}

      <TimingHistogram scanIndex={scanIndex} painSeries={painSeries} windowMin={matchTolerance}
                       matchDirection={matchDirection} metricLabel={metricLabel} />

      <Fold show={matchingSummary({ matchTolerance, matchDirection, maxPerRating, includeClinicSheetRatings })}
            inside="change">
      <Grid container spacing={3} alignItems="flex-start">
        {/* The match window: how far from a pain report a neural sample may sit and still carry its rating. */}
        <Grid item xs={12} md={5}>
          <MDTypography component="span" sx={LABEL_SX}>
            {"Match window"}
          </MDTypography>
          <MDBox display="flex" flexDirection="row" alignItems="center" gap={1.25}
                 sx={{ py: 0.5 }}>
            <MDTypography component="span" sx={{ ...TYPE.body, color: T.ink, whiteSpace: "nowrap" }}>
              {"±"}
            </MDTypography>
            <Slider
              value={Math.min(Number(matchTolerance) || 0, 240)} min={1} max={240} step={1}
              valueLabelDisplay="auto" size="small" sx={{ flex: 1, mx: 0.5 }}
              aria-label="match window (minutes)"
              onChange={(e, v) => setMatchTolerance(v)}
            />
            <TextField
              value={matchTolerance} type="number" size="small" variant="outlined"
              onChange={(e) => {
                const v = parseFloat(e.target.value);
                if (Number.isFinite(v) && v > 0) setMatchTolerance(v);
              }}
              inputProps={{ min: 1, max: 240, step: 1, "aria-label": "match window in minutes",
                style: { width: 56, padding: "5px 6px", fontSize: TYPE.body.fontSize } }}
            />
            <MDTypography component="span" sx={{ ...TYPE.body, color: T.ink }}>{"min"}</MDTypography>
          </MDBox>
          <MDTypography component="span" sx={NOTE_SX}>
            {"How far from a report a reading may be and still carry its rating."}
          </MDTypography>
        </Grid>

        {/* The split: which pain values count as high and which as low. */}
        <Grid item xs={12} sm={6} md={3}>
          <MDTypography component="span" sx={LABEL_SX}>
            {"Split into high and low pain"}
          </MDTypography>
          <FormControl fullWidth size="small">
            <Select value={strategy} onChange={(e) => setStrategy(e.target.value)}
                    inputProps={{ "aria-label": "split rule" }} sx={{ ...TYPE.body }}>
              {strategyOptions.map((s) => (
                <MenuItem key={s.key} value={s.key} sx={{ ...TYPE.body }}>{s.label}</MenuItem>
              ))}
            </Select>
          </FormControl>
          {twoCut ? (
            <MDBox display="flex" flexDirection="row" alignItems="baseline" gap={1.5} mt={0.5}>
              <MDTypography component="span" sx={{ ...TYPE.caption, color: T.ink }}>
                <span aria-hidden="true" style={{ ...SWATCH, background: PAIN.low }} />
                {`Low: ratings at or below the ${ordinal(lowPct)} percentile`}
              </MDTypography>
              <MDTypography component="span" sx={{ ...TYPE.caption, color: T.ink }}>
                <span aria-hidden="true" style={{ ...SWATCH, background: PAIN.high }} />
                {`High: at or above the ${ordinal(highPct)}`}
              </MDTypography>
            </MDBox>
          ) : null}
          <MDTypography component="span" sx={NOTE_SX}>
            {strategy === "tertile"
              ? "Lowest and highest thirds of ratings; the middle third is left out."
              : strategy === "percentile"
                ? "Cuts at the two handles above the histogram; the middle is left out."
                : strategy === "median"
                  ? "Ratings above the median are high, the rest low."
                  : "Split where the ratings fall into two clusters (kept for older results)."}
          </MDTypography>
        </Grid>

        {/* The direction: which side of a report a sample may sit on. */}
        <Grid item xs={12} sm={6} md={4}>
          <MDTypography component="span" sx={LABEL_SX}>
            {"Match direction"}
          </MDTypography>
          <ToggleButtonGroup value={matchDirection} exclusive size="small" aria-label="Match direction"
                             onChange={(e, v) => { if (v) setMatchDirection(v); }} sx={TOGGLE_SX}>
            <ToggleButton value="pro_first" title="Each pain report claims its closest readings on either side, up to the cap per report">{DIRECTION_WORDS.pro_first}</ToggleButton>
            <ToggleButton value="nearest" title="Each reading pairs with the nearest pain report on either side">{DIRECTION_WORDS.nearest}</ToggleButton>
            <ToggleButton value="prior" title="Each reading pairs only with a pain report recorded after it (the closed-loop direction)">{DIRECTION_WORDS.prior}</ToggleButton>
          </ToggleButtonGroup>
          <MDTypography component="span" sx={NOTE_SX}>
            {matchDirection === "pro_first"
              ? "Reports choose in time order; the most reports enter."
              : matchDirection === "nearest"
                ? "Readings choose; readings over a report's cap are dropped."
                : "The closed-loop direction: the signal first, the rating after."}
          </MDTypography>
        </Grid>
        {extraControls ? <Grid item xs={12} sm={6} md={4}>{extraControls}</Grid> : null}
      </Grid>
      </Fold>
      {moreOptions ? (
        <Fold show="More options" inside="the cap per report, the gap, the length of signal, reuse">
          {moreOptions}
        </Fold>
      ) : null}
    </MDBox>
  );
}
