/**
 * The top band of the Binarization card (the PI, 2026-09-21, option C): one bold sentence saying how
 * many pain reports the match window admits, then the three settings that decide what the card
 * pairs (the match window, the split rule, the match direction) in one row, then the timing
 * histogram that the window and direction redraw live. Everything here changes the card below it
 * without a Compute press; the left column's settings are sent on Compute.
 *
 * On screen: Biomarkers page, the Binarization card, full width above the two columns.
 */
import { Grid, Select, MenuItem, FormControl, Slider, TextField, ToggleButton, ToggleButtonGroup } from "@mui/material";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import TimingHistogram from "./TimingHistogram";

const LABEL_SX = { fontSize: 14, display: "block", mb: 0.5 };
const TOGGLE_SX = { "& .MuiToggleButton-root": { textTransform: "none", fontSize: 13, py: 0.5, px: 1.25, lineHeight: 1.2 } };

export default function MatchWindowBand({
  coverage, metricLabel,
  matchTolerance, setMatchTolerance,
  strategy, setStrategy, strategyOptions, percentileLow, percentileHigh,
  matchDirection, setMatchDirection,
  scanIndex, painSeries, showDescriptions = false,
}) {
  const score = metricLabel || "pain";
  const twoCut = strategy === "tertile" || strategy === "percentile";
  const lowPct = strategy === "tertile" ? 33.3 : percentileLow;
  const highPct = strategy === "tertile" ? 66.7 : percentileHigh;
  return (
    <MDBox px={2} pt={1.5} pb={1.25} display="flex" flexDirection="column" gap={1.25}
           sx={{ borderBottom: "1.5px solid #1A1A1A" }}>
      {/* THE COVERAGE SENTENCE: what the window admits and what it leaves out, following the slider live. */}
      {coverage && coverage.n_reports > 0 ? (
        <MDTypography variant="caption" color="dark" component="div" data-testid="report-coverage"
                      sx={{ fontSize: 14.5, lineHeight: 1.45 }} aria-live="polite">
          <b>{`${coverage.n_within_window.toLocaleString()} of ${coverage.n_reports.toLocaleString()} ${score} reports have a neural sample within ±${coverage.tolerance_min} min; ${coverage.n_within_10.toLocaleString()} within ±10 min; ${coverage.n_within_60.toLocaleString()} within ±60 min.`}</b>
        </MDTypography>
      ) : null}

      <Grid container spacing={2} alignItems="flex-start">
        {/* The match window: how far from a pain report a neural sample may sit and still carry its rating. */}
        <Grid item xs={12} md={5}>
          <MDTypography variant="caption" fontWeight="bold" color="dark" sx={LABEL_SX}>
            {"Match window"}
          </MDTypography>
          <MDBox display="flex" flexDirection="row" alignItems="center" gap={1.25}
                 sx={{ px: 1, py: 0.5, borderRadius: 1, backgroundColor: "#F4F6F8" }}>
            <MDTypography variant="caption" fontWeight="bold" color="dark" sx={{ fontSize: 14, whiteSpace: "nowrap" }}>
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
                style: { width: 56, padding: "5px 6px", fontSize: 14 } }}
            />
            <MDTypography variant="caption" color="dark" sx={{ fontSize: 14 }}>{"min"}</MDTypography>
          </MDBox>
          {showDescriptions ? (
            <MDTypography variant="caption" color="dark" fontStyle="italic" sx={{ fontSize: 13, display: "block", mt: 0.5 }}>
              {"A neural sample carries a pain rating only when a report falls within this many minutes of it. Widening the window pairs more reports with samples further from the moment of the rating."}
            </MDTypography>
          ) : null}
        </Grid>

        {/* The split: which pain values count as high and which as low. */}
        <Grid item xs={12} sm={6} md={3}>
          <MDTypography variant="caption" fontWeight="bold" color="dark" sx={LABEL_SX}>
            {"Split into high and low pain"}
          </MDTypography>
          <FormControl fullWidth size="small">
            <Select value={strategy} onChange={(e) => setStrategy(e.target.value)}
                    inputProps={{ "aria-label": "split rule" }} sx={{ fontSize: 14, fontWeight: 500 }}>
              {strategyOptions.map((s) => (
                <MenuItem key={s.key} value={s.key} sx={{ fontSize: 14 }}>{s.label}</MenuItem>
              ))}
            </Select>
          </FormControl>
          {twoCut ? (
            <MDBox display="flex" flexDirection="row" alignItems="baseline" gap={1.5} mt={0.5}>
              <MDTypography variant="caption" fontWeight="medium" color="dark" sx={{ fontSize: 13 }}>
                {"Low ≤ "}<b style={{ color: "#0072B2", fontSize: 14 }}>{`${lowPct.toFixed(0)}ᵗʰ pct`}</b>
              </MDTypography>
              <MDTypography variant="caption" fontWeight="medium" color="dark" sx={{ fontSize: 13 }}>
                {"High ≥ "}<b style={{ color: "#D55E00", fontSize: 14 }}>{`${highPct.toFixed(0)}ᵗʰ pct`}</b>
              </MDTypography>
            </MDBox>
          ) : null}
          {showDescriptions ? (
            <MDTypography variant="caption" color="dark" fontStyle="italic" sx={{ fontSize: 13, display: "block", mt: 0.5 }}>
              {strategy === "tertile"
                ? "Fixed cuts at the 33rd and 67th percentiles of the matched ratings; samples between them are left out of training. Drag the two handles above the histogram to move the cuts."
                : strategy === "percentile"
                  ? "Cuts at the two handles above the histogram; samples between them are left out of training."
                  : strategy === "median"
                    ? "Every matched sample is labelled at the median (about half high, half low)."
                    : "Two-cluster k-means on the matched ratings (kept for older results)."}
            </MDTypography>
          ) : null}
        </Grid>

        {/* The direction: which side of a report a sample may sit on. */}
        <Grid item xs={12} sm={6} md={4}>
          <MDTypography variant="caption" fontWeight="bold" color="dark" sx={LABEL_SX}>
            {"Match direction"}
          </MDTypography>
          <ToggleButtonGroup value={matchDirection} exclusive size="small" aria-label="Match direction"
                             onChange={(e, v) => { if (v) setMatchDirection(v); }} sx={TOGGLE_SX}>
            <ToggleButton value="pro_first" title="Walk the pain reports; each claims its closest neural samples on either side, up to the cap per rating">Report-first matching</ToggleButton>
            <ToggleButton value="nearest" title="Walk the neural samples; each pairs with the nearest pain report on either side">Neural-first matching</ToggleButton>
            <ToggleButton value="prior" title="Walk the neural samples; each pairs only with a pain report recorded after it (the closed-loop direction)">Neural-first, pre-report</ToggleButton>
          </ToggleButtonGroup>
          {showDescriptions ? (
            <MDTypography variant="caption" color="dark" fontStyle="italic" sx={{ fontSize: 13, display: "block", mt: 0.5 }}>
              {matchDirection === "pro_first"
                ? "The reports choose, in time order. Each pain report takes up to the cap of unclaimed neural samples per contact pair, the closest ones, on either side of it. A sample already taken by an earlier report is not taken again, and a sample whose nearest report is already full can be taken by another report inside the window; the gap rule is not used. The most reports enter, which suits asking whether a band tracks pain at all."
                : matchDirection === "nearest"
                  ? "The samples choose. Every neural sample is handed to its nearest pain report on either side; then each report keeps only its closest samples per contact pair up to the cap, with the gap rule between them, and every sample over the cap is dropped, not passed to the next-nearest report. Association at the same time, not forecasting."
                  : "The samples choose, one side only. Every neural sample is handed to the nearest pain report recorded after it; the cap and the gap rule then apply as under Neural-first matching. The direction a closed loop works in: the signal comes first, the rating follows. Samples recorded after their nearest report are left out, which is why this setting keeps fewer."}
            </MDTypography>
          ) : null}
        </Grid>
      </Grid>

      <TimingHistogram scanIndex={scanIndex} painSeries={painSeries} windowMin={matchTolerance}
                       matchDirection={matchDirection} metricLabel={metricLabel} />
    </MDBox>
  );
}
