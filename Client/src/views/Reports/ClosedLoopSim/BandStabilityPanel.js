/**
 * Does the chosen band mean the same thing about pain whatever the stimulation is doing?
 *
 * WHY THIS BELONGS ON THIS PAGE AND NOT ONLY ON THE BIOMARKERS PAGE. Closed loop works by watching
 * the power in one band and moving the current when that power crosses a value programmed into the
 * stimulator. That is only sound if the band means the same thing about the patient's pain at every
 * current the loop will visit. If it does not, then the moment the loop starts changing the current
 * it damages the signal it is steering by. The answer has existed on the biomarkers page for some
 * time and never travelled to the page where somebody decides whether to switch closed loop on,
 * which is the page that needed it.
 *
 * WHY ALL FOUR POSSIBLE ANSWERS ARE DRAWN EVERY TIME, INCLUDING THE THREE THAT DID NOT HAPPEN. This
 * panel's whole job is to stop one particular mistake, which this project has made more than once
 * in both directions: the answer "we could not tell" being read as a pass, or being read as
 * "behaves differently". Printing only the answer that came out invites a reader to assume the
 * alternatives were a yes and a no. Printing all four, with the one that happened filled in and the
 * others greyed, makes it impossible to look at this panel without seeing that "cannot tell" was
 * among the options and what it would have meant.
 *
 * WHY "CANNOT TELL" IS AMBER AND NOT GREEN OR RED. The page's palette already reserves amber for
 * underpowered and grey for a check that did not run, and both meanings are exactly right here.
 * Green would say the band was shown to be steady when nothing of the kind was shown. Red would say
 * the band was shown to change when that was not shown either. "Cannot tell" is the most common
 * answer in a study this size and it needs its own colour, not a borrowed one.
 *
 * WHY THERE IS NO PASS OR FAIL BADGE ANYWHERE ON THIS CARD. Whether this finding should stop a
 * deployment has not been decided. The blocking rules on this page are device rules, each traceable
 * to a page of a Medtronic manual; this is a statistical finding about one participant's data and
 * carries no such warrant. So the card prints the backend's own words for the blocking status,
 * which say plainly that nobody has ruled on it, rather than a badge a reader would take for a
 * verdict.
 *
 * WHAT THE PANEL IS GIVEN. The `stability` prop is exactly what
 * `ClosedLoopDeployment.stability.BandStabilityFinding.as_payload()` returns. It carries no
 * true-or-false summary of the answer, on purpose, so there is nothing here for this file to pick
 * up and accidentally flatten.
 */
import { Card } from "@mui/material";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import PAL from "./palette";
import { fmtNum, fmtP } from "./deployFormat";

/**
 * The four answers, in a fixed order, with the colour and the plain-English gloss for each.
 *
 * Held as data in this file rather than read from the payload's `answers_possible` so that the
 * panel draws the same four rows even when the backend sends nothing at all. A card that showed
 * fewer options on an empty response would be least informative exactly when a reader is most
 * likely to guess.
 */
const ANSWERS = [
  {
    key: "behaves the same",
    ink: PAL.pass,
    onInk: "#ffffff",
    gloss: "any remaining change with stimulation is smaller than the change we said in advance " +
           "would matter",
  },
  {
    key: "behaves differently",
    ink: PAL.fail,
    onInk: "#ffffff",
    gloss: "the band's relationship to pain demonstrably changes with the stimulation",
  },
  {
    key: "cannot tell",
    ink: PAL.warn,
    onInk: PAL.onWarn,
    gloss: "the data cannot separate a steady band from one that changes. Not a pass, and not a " +
           "failure",
  },
  {
    key: "not tested",
    ink: PAL.indeterminate,
    onInk: "#ffffff",
    gloss: "the test could not be run, so nothing is known either way",
  },
];

const isNum = (v) => v != null && Number.isFinite(Number(v));

/** One of the four answers, filled in when it is the one that happened and greyed when it is not. */
function AnswerRow({ answer, lit }) {
  return (
    <MDBox display="flex" alignItems="flex-start" mb={0.6}>
      <MDBox
        flexShrink={0}
        px={0.9}
        py={0.35}
        mr={1}
        minWidth="9.6rem"
        borderRadius="4px"
        sx={{
          backgroundColor: lit ? answer.ink : "transparent",
          border: `1px ${lit ? "solid" : "dashed"} ${lit ? answer.ink : PAL.neutralBorder}`,
        }}
      >
        <MDTypography
          variant="caption"
          fontWeight={lit ? "bold" : "regular"}
          sx={{ color: lit ? answer.onInk : PAL.neutral, lineHeight: 1.3 }}
        >
          {answer.key}
        </MDTypography>
      </MDBox>
      <MDTypography
        variant="caption"
        sx={{ color: lit ? "#1A1A1A" : PAL.neutral, lineHeight: 1.35 }}
      >
        {answer.gloss}
      </MDTypography>
    </MDBox>
  );
}

/** One label-and-value line from the evidence behind the answer. */
function Fact({ label, value }) {
  return (
    <MDBox display="flex" justifyContent="space-between" alignItems="baseline" mb={0.25}>
      <MDTypography variant="caption" sx={{ color: "#4A4A4A", mr: 1.5 }}>
        {label}
      </MDTypography>
      <MDTypography variant="caption" fontWeight="medium" sx={{ color: "#1A1A1A" }}>
        {value}
      </MDTypography>
    </MDBox>
  );
}

export default function BandStabilityPanel({ stability }) {
  const s = stability || null;
  const answer = s && s.answer ? s.answer : "not tested";

  // The band this answer is about. Printed in the subtitle so the answer can never be read as
  // being about a different band than the one the rest of the page is discussing.
  const bandPhrase = (s && isNum(s.band_center_hz))
    ? `${fmtNum(s.band_center_hz, 1)} Hz centre, ${fmtNum(s.band_width_hz, 1)} Hz wide` +
      (s.electrode ? `, on ${s.electrode}` : "")
    : "no band assessed";

  const perState = (s && s.measurements_per_state) || {};
  const stateCounts = Object.keys(perState)
    .filter((k) => isNum(perState[k]))
    .map((k) => `${k}: ${perState[k]}`)
    .join("  \u00b7  ");

  const interval = (s && Array.isArray(s.difference_interval) && s.difference_interval.length === 2)
    ? `${fmtNum(s.difference_interval[0], 2)} to ${fmtNum(s.difference_interval[1], 2)}`
    : null;

  return (
    <Card sx={{ p: 2, height: "100%" }}>
      <MDTypography variant="h6" fontWeight="medium" sx={{ lineHeight: 1.3 }}>
        Does this band mean the same thing about pain at every stimulation current?
      </MDTypography>
      <MDTypography variant="caption" sx={{ color: "#4A4A4A" }}>
        {bandPhrase}
      </MDTypography>

      <MDBox mt={1.5} mb={1.25}>
        {ANSWERS.map((a) => (
          <AnswerRow key={a.key} answer={a} lit={a.key === answer} />
        ))}
      </MDBox>

      {s && s.reason ? (
        <MDBox
          px={1}
          py={0.75}
          mb={1.25}
          borderRadius="4px"
          sx={{
            backgroundColor: answer === "cannot tell" ? PAL.warnFill : PAL.neutralFill,
            border: `1px solid ${answer === "cannot tell" ? PAL.warnBorder : PAL.neutralBorder}`,
          }}
        >
          <MDTypography
            variant="caption"
            sx={{ color: answer === "cannot tell" ? PAL.warnText : "#1A1A1A", lineHeight: 1.4 }}
          >
            {s.reason}
          </MDTypography>
        </MDBox>
      ) : null}

      {s && s.test_ran ? (
        <MDBox mb={1.25}>
          <MDTypography variant="caption" fontWeight="bold" sx={{ color: "#1A1A1A" }}>
            What the answer rests on
          </MDTypography>
          <MDBox mt={0.5}>
            {isNum(s.largest_difference) ? (
              <Fact
                label="biggest difference seen between two stimulation states"
                value={fmtNum(s.largest_difference, 2)}
              />
            ) : null}
            {interval ? (
              <Fact label="range that difference could plausibly lie in" value={interval} />
            ) : null}
            {isNum(s.declared_margin) ? (
              <Fact
                label="difference we said in advance would matter"
                value={fmtNum(s.declared_margin, 2)}
              />
            ) : null}
            {isNum(s.p_value) ? (
              <Fact
                label="chance of a difference this large if the band were steady"
                value={fmtP(s.p_value)}
              />
            ) : null}
            {isNum(s.n_measurements) ? (
              <Fact label="measurements used" value={String(s.n_measurements)} />
            ) : null}
            {isNum(s.n_time_blocks) ? (
              <Fact
                label="separate blocks of time they came from"
                value={String(s.n_time_blocks)}
              />
            ) : null}
            {isNum(s.n_states_compared) ? (
              <Fact
                label="stimulation states that could be compared"
                value={`${s.n_states_compared} of 3`}
              />
            ) : null}
            {stateCounts ? (
              <Fact label="measurements in each state" value={stateCounts} />
            ) : null}
          </MDBox>
        </MDBox>
      ) : null}

      {/*
        Two things that change how much the answer is worth. Both are drawn only when the backend
        actually knows them: a missing value is left out rather than printed as "no", because "no"
        would say the problem was looked for and ruled out.
      */}
      {s && s.rate_moved_with_current === true ? (
        <MDBox
          px={1}
          py={0.75}
          mb={1}
          borderRadius="4px"
          sx={{ backgroundColor: PAL.warnFill, border: `1px solid ${PAL.warnBorder}` }}
        >
          <MDTypography variant="caption" sx={{ color: PAL.warnText, lineHeight: 1.4 }}>
            The stimulation rate was changing at the same times as the current, so this answer is
            partly about the rate rather than only about the current.
          </MDTypography>
        </MDBox>
      ) : null}
      {s && isNum(s.distance_to_nearest_artifact_hz)
        && Number(s.distance_to_nearest_artifact_hz) <= 2.5 ? (
          <MDBox
            px={1}
            py={0.75}
            mb={1}
            borderRadius="4px"
            sx={{ backgroundColor: PAL.warnFill, border: `1px solid ${PAL.warnBorder}` }}
          >
            <MDTypography variant="caption" sx={{ color: PAL.warnText, lineHeight: 1.4 }}>
              A multiple of the stimulation rate folds back into the recording
              {" "}{fmtNum(s.distance_to_nearest_artifact_hz, 1)} Hz from the middle of this band,
              so some of the power here is a folded multiple of the stimulation rate.
            </MDTypography>
          </MDBox>
        ) : null}

      <MDBox
        mt="auto"
        pt={1}
        sx={{ borderTop: `1px solid ${PAL.neutralBorder}` }}
      >
        <MDTypography variant="caption" sx={{ color: PAL.neutral, lineHeight: 1.4 }}>
          Whether this stops a deployment:{" "}
          {(s && s.blocking_status)
            || "not decided - reported for the PI to rule on, blocks nothing today"}
        </MDTypography>
      </MDBox>

      {!s ? (
        <MDBox mt={1}>
          <MDTypography variant="caption" sx={{ color: PAL.neutral, lineHeight: 1.4 }}>
            The report carried no answer for this band, so nothing is known either way. This is not
            a pass.
          </MDTypography>
        </MDBox>
      ) : null}
    </Card>
  );
}
