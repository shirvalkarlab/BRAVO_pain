/**
 * "How are reports paired with recordings?" -- the matching section of the Biomarkers page (the PI,
 * 2026-09-21, option C; laid out again in the redesign of 2026-09-26, SPEC.md section 5.1 item 3).
 *
 * One bold sentence says how many pain reports the match window admits (the section's answer); the
 * timing histogram is its figure. Every setting that decides what is paired, the extra options (cap
 * per report, gap, length of signal, reuse) and the high / low split's own controls sit in ONE
 * compact panel behind a large "Adjust matching parameters" button, closed by default, with the
 * settings in force printed beside it ("Paired within ±15 min · each recording picks its nearest
 * report · high / low split: lowest and highest thirds ...") (the PI, 2026-09-26; the defaults since
 * decision 331, from `matchingDefaults.js`). Each control
 * carries one short sentence under it. The coverage sentence, the timing histogram and the high / low
 * preview follow every control at once. The heat maps and the all-band scan do NOT: a moved setting
 * leaves them on screen as computed, the heat maps say which setting changed, and the page's
 * Recompute rebuilds both (review of 2026-09-26).
 *
 * On screen: Biomarkers page, the matching section, under the heat maps.
 */
import { useState } from "react";
import { Grid, Select, MenuItem, FormControl, Slider, TextField, ToggleButton, ToggleButtonGroup } from "@mui/material";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import { T, TYPE, RADIUS, FOCUS_RING } from "assets/theme/base/tokens";
import { PAIN } from "assets/theme/base/dataColors";

import TimingHistogram from "./TimingHistogram";

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

/** The split rule in a few words, for the summary line. A tertile split always cuts at the thirds. */
function splitWords(strategy, percentileLow, percentileHigh) {
  if (strategy === "tertile") return "high / low split: lowest and highest thirds";
  if (strategy === "percentile" && percentileLow != null && percentileHigh != null) {
    return `high / low split at the ${ordinal(percentileLow)} and ${ordinal(percentileHigh)} percentiles`;
  }
  if (strategy === "median") return "median split";
  if (strategy === "kmeans") return "high / low split: two clusters";
  return null;
}

/** The one-line summary printed beside the "Adjust matching parameters" button: the settings that
 *  decide the heat maps (the window, the direction, the split and the clinic sheets). The cap per
 *  report is not named here: the heat maps do not read it (review of 2026-09-26). */
export function matchingSummary({ matchTolerance, matchDirection, includeClinicSheetRatings,
  strategy, percentileLow, percentileHigh }) {
  const parts = [`Paired within \u00b1${matchTolerance} min`];
  if (DIRECTION_WORDS[matchDirection]) parts.push(DIRECTION_WORDS[matchDirection].toLowerCase());
  const split = splitWords(strategy, percentileLow, percentileHigh);
  if (split) parts.push(split);
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
  includeClinicSheetRatings = null,
  extraControls = null, moreOptions = null, binarization = null, defaultOpen = false,
}) {
  // THE MATCHING PANEL (the PI, 2026-09-26): one large bold button, closed by default, opens a
  // compact panel with every matching control, the extra options and the high / low split's own
  // controls. The panel stays MOUNTED while closed (hidden), so tests and search still read it.
  const [open, setOpen] = useState(!!defaultOpen);
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

      <MDBox display="flex" flexDirection="row" flexWrap="wrap" alignItems="center" gap={1.5}>
        <MDBox component="button" type="button" onClick={() => setOpen(!open)} aria-expanded={open}
               aria-controls="matching-panel" data-testid="adjust-matching"
               sx={{ ...TYPE.lead, fontFamily: "inherit", fontWeight: 600, color: T.accent,
                 background: T.surface, border: `2px solid ${T.accent}`, borderRadius: `${RADIUS.sm}px`,
                 px: 2.25, py: 1.25, cursor: "pointer", whiteSpace: "nowrap",
                 display: "inline-flex", alignItems: "center", gap: 1.25,
                 "&:hover": { background: T.accentTint }, "&:active": { transform: "translateY(1px)" },
                 "&:focus-visible": FOCUS_RING }}>
          <span aria-hidden="true" style={{ display: "inline-block", width: "1em",
            transform: open ? "rotate(90deg)" : "none" }}>{"\u25B8"}</span>
          {"Adjust matching parameters"}
        </MDBox>
        <MDTypography component="span" sx={{ ...TYPE.body, color: T.ink2 }} data-testid="matching-summary">
          {matchingSummary({ matchTolerance, matchDirection, includeClinicSheetRatings,
            strategy, percentileLow, percentileHigh })}
        </MDTypography>
      </MDBox>
      <MDBox id="matching-panel" hidden={!open} data-testid="matching-panel"
             sx={{ borderLeft: `2px solid ${T.accent}`, pl: 2, py: 1 }}>
      <Grid container spacing={2} alignItems="flex-start">
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
            <ToggleButton value="pro_first" title="Each pain report claims its closest readings on either side (in the all-band scan, up to the cap per report)">{DIRECTION_WORDS.pro_first}</ToggleButton>
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
      {moreOptions ? (
        <MDBox mt={2} pt={2} sx={{ borderTop: `1px solid ${T.rule}` }} data-testid="more-matching-options">
          {moreOptions}
        </MDBox>
      ) : null}
      {binarization ? (
        <MDBox mt={2} pt={2} sx={{ borderTop: `1px solid ${T.rule}` }} data-testid="split-controls">
          {binarization}
        </MDBox>
      ) : null}
      </MDBox>
    </MDBox>
  );
}
