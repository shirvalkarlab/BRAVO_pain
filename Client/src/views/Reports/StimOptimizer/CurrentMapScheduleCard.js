/**
 * "Home programming schedule to map the two currents" -- decision 158's joint titration schedule
 * (`current_map_schedule`, added 2026-09-14), drawn as a printable sheet a clinician can hand to
 * whoever programs the device next: which (left current, right current) combination to hold, for
 * how many days, and why, so the record clears the coverage check `CurrentMapCard.js` shows
 * failing today.
 *
 * Read straight from `data.current_map_schedule` (computed with the page's own main response, not
 * the two-stage plan's separate fetch); nothing here is recomputed.
 */
import { Card, Table, TableBody, TableCell, TableHead, TableRow } from "@mui/material";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import PAL from "views/Reports/ClosedLoopSim/palette";

import { num, fmtHz, fmtUs, fmtMa } from "./stimFormat";
import { TYPE, HEAD } from "./typeScale";

const CHECK_MARK = "✓";
const CROSS_MARK = "✗";

function daysWord(n) {
  const v = Math.round(num(n) ?? 0);
  return `${v} day${v === 1 ? "" : "s"}`;
}

export default function CurrentMapScheduleCard({ schedule }) {
  if (!schedule) return null;

  if (!schedule.available) {
    return (
      <Card>
        <MDBox p={2}>
          <MDTypography variant="h6" sx={{ fontSize: TYPE.section }}>
            Home programming schedule to map the two currents
          </MDTypography>
          <MDTypography variant="caption" component="div" color="text" sx={{ fontSize: TYPE.body, mt: 0.8 }}>
            {schedule.reason || "no schedule could be built from this record."}
          </MDTypography>
        </MDBox>
      </Card>
    );
  }

  const steps = Array.isArray(schedule.steps) ? schedule.steps : [];
  const rt = schedule.record_today || {};
  const wtb = rt.what_this_buys || {};
  const hold = schedule.hold || {};
  const rpd = schedule.reports_per_day || {};

  return (
    <Card>
      <MDBox p={2}>
        <MDTypography variant="h6" sx={{ fontSize: TYPE.section }}>
          Home programming schedule to map the two currents
        </MDTypography>

        <MDBox mt={1} display="flex" columnGap={4} rowGap={1} flexWrap="wrap">
          {[
            ["stimulation speed", fmtHz(schedule.rate_hz)],
            ["left pulse width", fmtUs(schedule.pulse_width_us_left)],
            ["right pulse width", fmtUs(schedule.pulse_width_us_right)],
            ["left ceiling", fmtMa(schedule.ceiling_left_mA)],
            ["right ceiling", fmtMa(schedule.ceiling_right_mA)],
            ["total length", daysWord(schedule.total_days)],
          ].map(([k, v]) => (
            <MDBox key={k}>
              <MDTypography variant="caption" component="div" sx={HEAD}>{k}</MDTypography>
              <MDTypography variant="h6" sx={{ fontSize: TYPE.numLarge, fontFamily: PAL.mono }}>{v}</MDTypography>
            </MDBox>
          ))}
        </MDBox>

        <MDTypography variant="caption" component="div" color="text" sx={{ fontSize: TYPE.body, mt: 1.2 }}>
          {schedule.why_pulse_widths}
        </MDTypography>
        {hold.why && (
          <MDTypography variant="caption" component="div" color="text" sx={{ fontSize: TYPE.body, mt: 0.6 }}>
            {`How long to hold each step: ${hold.why}`}
          </MDTypography>
        )}
        {rpd.note && (
          <MDTypography variant="caption" component="div" color="text" sx={{ fontSize: TYPE.small, mt: 0.3 }}>
            {`Reporting rate this schedule is sized on: ${rpd.note}`}
          </MDTypography>
        )}
        {schedule.safety_model_note && (
          <MDTypography variant="caption" component="div" color="text" sx={{ fontSize: TYPE.small, mt: 0.3 }}>
            {schedule.safety_model_note}
          </MDTypography>
        )}

        <MDBox sx={{ overflowX: "auto", mt: 1.5 }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                {["step", "left current", "right current", "days", "target reports", "why", "safe"].map((h) => (
                  <TableCell key={h} sx={{ py: 0.6 }}>
                    <MDTypography variant="caption" sx={HEAD}>{h}</MDTypography>
                  </TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {steps.map((s, i) => (
                <TableRow key={i}>
                  <TableCell sx={{ py: 0.5 }}>
                    <MDTypography variant="caption" sx={{ fontSize: TYPE.body, fontFamily: PAL.mono }}>{s.step}</MDTypography>
                  </TableCell>
                  <TableCell sx={{ py: 0.5 }}>
                    <MDTypography variant="caption" sx={{ fontSize: TYPE.body, fontFamily: PAL.mono, whiteSpace: "nowrap" }}>{fmtMa(s.amp_left_mA)}</MDTypography>
                  </TableCell>
                  <TableCell sx={{ py: 0.5 }}>
                    <MDTypography variant="caption" sx={{ fontSize: TYPE.body, fontFamily: PAL.mono, whiteSpace: "nowrap" }}>{fmtMa(s.amp_right_mA)}</MDTypography>
                  </TableCell>
                  <TableCell sx={{ py: 0.5 }}>
                    <MDTypography variant="caption" sx={{ fontSize: TYPE.body, fontFamily: PAL.mono }}>{daysWord(s.planned_days)}</MDTypography>
                  </TableCell>
                  <TableCell sx={{ py: 0.5 }}>
                    <MDTypography variant="caption" sx={{ fontSize: TYPE.body, fontFamily: PAL.mono }}>{num(s.target_reports) ?? "—"}</MDTypography>
                  </TableCell>
                  <TableCell sx={{ py: 0.5, maxWidth: 360 }}>
                    <MDTypography variant="caption" sx={{ fontSize: TYPE.small }}>{s.why}</MDTypography>
                  </TableCell>
                  <TableCell sx={{ py: 0.5 }}>
                    <span style={{ color: s.in_safe_set === false ? PAL.warnText : "#1B7A3D", fontWeight: 700 }}>
                      {s.in_safe_set === false ? CROSS_MARK : CHECK_MARK}
                    </span>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </MDBox>

        <MDBox mt={2}>
          <MDTypography variant="caption" fontWeight="medium" component="div" sx={{ fontSize: TYPE.num }}>
            What is already in the record today
          </MDTypography>
          <MDBox display="flex" columnGap={4} rowGap={0.6} flexWrap="wrap" mt={0.5}>
            {[
              ["design points considered", num(rt.n_design_points_considered) ?? 0],
              ["excluded, unsafe", num(rt.n_excluded_unsafe) ?? 0],
              ["already covered", num(rt.n_already_covered) ?? 0],
              ["remaining to run", num(rt.n_remaining_to_run) ?? 0],
              ["existing epochs at this stratum", num(rt.n_existing_epochs_at_this_stratum) ?? 0],
            ].map(([k, v]) => (
              <MDBox key={k}>
                <MDTypography variant="caption" component="div" sx={HEAD}>{k}</MDTypography>
                <MDTypography variant="caption" component="div" sx={{ fontSize: TYPE.num, fontFamily: PAL.mono }}>{v}</MDTypography>
              </MDBox>
            ))}
          </MDBox>
          {Array.isArray(rt.excluded_unsafe) && rt.excluded_unsafe.length > 0 && (
            <MDTypography variant="caption" component="div" color="text" sx={{ fontSize: TYPE.small, mt: 0.6 }}>
              {`Excluded as unsafe: ${rt.excluded_unsafe.map((p) => `${fmtMa(p.amp_left_mA)} / ${fmtMa(p.amp_right_mA)}`).join(", ")}`}
            </MDTypography>
          )}
          {Array.isArray(rt.already_covered) && rt.already_covered.length > 0 && (
            <MDTypography variant="caption" component="div" color="text" sx={{ fontSize: TYPE.small, mt: 0.3 }}>
              {`Already covered, not repeated: ${rt.already_covered.map((p) => `${fmtMa(p.amp_left_mA)} / ${fmtMa(p.amp_right_mA)}`).join(", ")}`}
            </MDTypography>
          )}
        </MDBox>

        <MDTypography variant="caption" component="div" fontWeight="medium"
          sx={{ fontSize: TYPE.body, mt: 1.2, color: wtb.resolution_coverage_would_pass ? "#1B7A3D" : PAL.warnText }}>
          {wtb.note || ""}
        </MDTypography>
      </MDBox>
    </Card>
  );
}
