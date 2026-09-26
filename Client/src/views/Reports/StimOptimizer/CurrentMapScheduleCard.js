/**
 * "Home programming schedule to map the two currents" -- decision 158's joint titration schedule
 * (`current_map_schedule`, added 2026-09-14), drawn as a printable sheet a clinician can hand to
 * whoever programs the device next: which (left current, right current) combination to hold, for
 * how many days, and why, so the record clears the coverage check `CurrentMapCard.js` shows
 * failing today.
 *
 * Read straight from `data.current_map_schedule` (computed with the page's own main response, not
 * the two-stage plan's separate fetch); nothing here is recomputed.
 *
 * SINCE 2026-09-26 A SECTION OF THE NEXT-VISIT CARD, not a card of its own (the PI amended his
 * ruling of 2026-09-12 in the design review): `HomeScheduleSection` prints its heading and one line
 * in the open and folds the rest (the table, the reasons, what the record already holds). The
 * ceiling is not repeated here; the next-visit card's header states it once.
 */
import { Card, Table, TableBody, TableCell, TableHead, TableRow } from "@mui/material";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import PAL from "views/Reports/ClosedLoopSim/palette";

import { num, fmtHz, fmtUs, fmtMa } from "./stimFormat";
import { TYPE, HEAD, SMALL, SizedFold } from "./typeScale";

const CHECK_MARK = "✓";
const CROSS_MARK = "✗";

function daysWord(n) {
  const v = Math.round(num(n) ?? 0);
  return `${v} day${v === 1 ? "" : "s"}`;
}

export const HOME_SCHEDULE_TITLE = "Home programming schedule to map the two currents";

/** The schedule as a section: heading and one line open, everything else in one fold. */
export function HomeScheduleSection({ schedule }) {
  if (!schedule) return null;
  if (!schedule.available) {
    return (
      <MDBox mt={2} pt={1.5} data-testid="home-schedule" sx={{ borderTop: `1px solid ${PAL.neutralBorder}` }}>
        <MDTypography variant="h6" sx={{ fontSize: TYPE.section }}>{HOME_SCHEDULE_TITLE}</MDTypography>
        <MDTypography variant="caption" component="div" color="text" sx={{ fontSize: TYPE.body, mt: 0.6 }}>
          {schedule.reason || "no schedule could be built from this record."}
        </MDTypography>
      </MDBox>
    );
  }

  const steps = Array.isArray(schedule.steps) ? schedule.steps : [];
  const rt = schedule.record_today || {};
  const wtb = rt.what_this_buys || {};
  const hold = schedule.hold || {};
  const rpd = schedule.reports_per_day || {};
  // The setting in force when it is above today's ceiling (2026-09-26): history, drawn and labelled,
  // never a numbered step (the server keeps it out of `steps` and says so in `why`).
  const inForce = schedule.in_force && schedule.in_force.above_ceiling === true ? schedule.in_force : null;
  const HISTORY_INK = "#5E5E5E";

  return (
    <MDBox mt={2} pt={1.5} data-testid="home-schedule" sx={{ borderTop: `1px solid ${PAL.neutralBorder}` }}>
      <MDTypography variant="h6" sx={{ fontSize: TYPE.section }}>{HOME_SCHEDULE_TITLE}</MDTypography>
      <MDTypography variant="caption" component="div" sx={{ fontSize: TYPE.body, mt: 0.4 }}>
        <span style={{ fontFamily: PAL.mono }}>
          {`${fmtHz(schedule.rate_hz)} · left ${fmtUs(schedule.pulse_width_us_left)} / right ${fmtUs(schedule.pulse_width_us_right)} · ${steps.length} step${steps.length === 1 ? "" : "s"} over ${daysWord(schedule.total_days)}`}
        </span>
        {wtb.note ? (
          <span style={{ display: "block", fontWeight: 500, marginTop: 2,
            color: wtb.resolution_coverage_would_pass ? "#1B7A3D" : PAL.warnText }}>{wtb.note}</span>
        ) : null}
      </MDTypography>
      {inForce && (
        <MDTypography variant="caption" component="div" data-testid="home-schedule-in-force"
          sx={{ fontSize: TYPE.body, mt: 0.4, color: HISTORY_INK }}>
          <span style={{ fontWeight: 700, color: PAL.warnText }}>
            {`In force, above today's ceiling: ${fmtMa(inForce.amp_left_mA)} left / ${fmtMa(inForce.amp_right_mA)} right`}
          </span>
          {` -- ${inForce.why || "history, never offered as a step to hold"}.`}
        </MDTypography>
      )}

      <SizedFold show={`Show the schedule (${steps.length} steps) and why`} hide="Hide the schedule">
        <MDTypography variant="caption" component="div" color="text" sx={{ fontSize: TYPE.body }}>
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
            <TableHead sx={{ display: "table-header-group", p: 0 }}>
              <TableRow>
                {["step", "left current", "right current", "days", "target reports", "why", "safe"].map((h) => (
                  <TableCell key={h} sx={{ py: 0.6 }}>
                    <MDTypography variant="caption" sx={HEAD}>{h}</MDTypography>
                  </TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {inForce && (
                <TableRow data-testid="home-schedule-in-force-row">
                  <TableCell sx={{ py: 0.5 }}>
                    <MDTypography variant="caption" sx={{ fontSize: TYPE.body, fontFamily: PAL.mono, color: HISTORY_INK }}>—</MDTypography>
                  </TableCell>
                  <TableCell sx={{ py: 0.5 }}>
                    <MDTypography variant="caption" sx={{ fontSize: TYPE.body, fontFamily: PAL.mono, whiteSpace: "nowrap", color: HISTORY_INK }}>{fmtMa(inForce.amp_left_mA)}</MDTypography>
                  </TableCell>
                  <TableCell sx={{ py: 0.5 }}>
                    <MDTypography variant="caption" sx={{ fontSize: TYPE.body, fontFamily: PAL.mono, whiteSpace: "nowrap", color: HISTORY_INK }}>{fmtMa(inForce.amp_right_mA)}</MDTypography>
                  </TableCell>
                  <TableCell sx={{ py: 0.5 }} colSpan={2}>
                    <MDTypography variant="caption" sx={{ fontSize: TYPE.small, color: HISTORY_INK }}>not a step</MDTypography>
                  </TableCell>
                  <TableCell sx={{ py: 0.5, maxWidth: 360 }}>
                    <MDTypography variant="caption" sx={{ fontSize: TYPE.small, color: HISTORY_INK }}>
                      {`${inForce.label || "in force, above today's ceiling"} -- history, never offered as a step to hold`}
                    </MDTypography>
                  </TableCell>
                  <TableCell sx={{ py: 0.5 }}>
                    <span style={{ color: PAL.warnText, fontWeight: 700 }}>above ceiling</span>
                  </TableCell>
                </TableRow>
              )}
              {steps.map((st, i) => (
                <TableRow key={i}>
                  <TableCell sx={{ py: 0.5 }}>
                    <MDTypography variant="caption" sx={{ fontSize: TYPE.body, fontFamily: PAL.mono }}>{st.step}</MDTypography>
                  </TableCell>
                  <TableCell sx={{ py: 0.5 }}>
                    <MDTypography variant="caption" sx={{ fontSize: TYPE.body, fontFamily: PAL.mono, whiteSpace: "nowrap" }}>{fmtMa(st.amp_left_mA)}</MDTypography>
                  </TableCell>
                  <TableCell sx={{ py: 0.5 }}>
                    <MDTypography variant="caption" sx={{ fontSize: TYPE.body, fontFamily: PAL.mono, whiteSpace: "nowrap" }}>{fmtMa(st.amp_right_mA)}</MDTypography>
                  </TableCell>
                  <TableCell sx={{ py: 0.5 }}>
                    <MDTypography variant="caption" sx={{ fontSize: TYPE.body, fontFamily: PAL.mono }}>{daysWord(st.planned_days)}</MDTypography>
                  </TableCell>
                  <TableCell sx={{ py: 0.5 }}>
                    <MDTypography variant="caption" sx={{ fontSize: TYPE.body, fontFamily: PAL.mono }}>{num(st.target_reports) ?? "—"}</MDTypography>
                  </TableCell>
                  <TableCell sx={{ py: 0.5, maxWidth: 360 }}>
                    <MDTypography variant="caption" sx={{ fontSize: TYPE.small }}>{st.why}</MDTypography>
                  </TableCell>
                  <TableCell sx={{ py: 0.5 }}>
                    <span style={{ color: st.in_safe_set === false ? PAL.warnText : "#1B7A3D", fontWeight: 700 }}>
                      {st.in_safe_set === false ? CROSS_MARK : CHECK_MARK}
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
              ["stretches already at these pulse widths", num(rt.n_existing_epochs_at_this_stratum) ?? 0],
            ].map(([k, v]) => (
              <MDBox key={k}>
                <MDTypography variant="caption" component="div" sx={HEAD}>{k}</MDTypography>
                <MDTypography variant="caption" component="div" sx={{ fontSize: TYPE.num, fontFamily: PAL.mono }}>{v}</MDTypography>
              </MDBox>
            ))}
          </MDBox>
          {Array.isArray(rt.excluded_unsafe) && rt.excluded_unsafe.length > 0 && (
            <MDTypography variant="caption" component="div" color="text" sx={{ fontSize: TYPE.small, mt: 0.6 }}>
              {`Excluded as unsafe: ${rt.excluded_unsafe.map((q) => `${fmtMa(q.amp_left_mA)} / ${fmtMa(q.amp_right_mA)}`).join(", ")}`}
            </MDTypography>
          )}
          {Array.isArray(rt.already_covered) && rt.already_covered.length > 0 && (
            <MDTypography variant="caption" component="div" color="text" sx={{ ...SMALL, fontSize: TYPE.small, mt: 0.3 }}>
              {`Already covered, not repeated: ${rt.already_covered.map((q) => `${fmtMa(q.amp_left_mA)} / ${fmtMa(q.amp_right_mA)}`).join(", ")}`}
            </MDTypography>
          )}
        </MDBox>
      </SizedFold>
    </MDBox>
  );
}

/** The schedule as a card of its own, for any reader that still wants one; the page embeds the
 *  section in the next-visit card instead. */
export default function CurrentMapScheduleCard({ schedule }) {
  if (!schedule) return null;
  return (
    <Card>
      <MDBox p={2}>
        <HomeScheduleSection schedule={schedule} />
      </MDBox>
    </Card>
  );
}
