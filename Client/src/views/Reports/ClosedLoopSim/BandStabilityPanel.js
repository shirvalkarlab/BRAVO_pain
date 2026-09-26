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
import { TYPE, WRAP, CARD, STATE } from "assets/theme/base/tokens";
import Fold from "./Fold";
import { fmtNum, fmtOddsRatioWithInterval, fmtP } from "./deployFormat";

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
    st: STATE.pass,
    glyph: STATE.pass.glyph,
    gloss: "any remaining change with stimulation is smaller than the change we said in advance " +
           "would matter",
  },
  {
    key: "behaves differently",
    st: STATE.caution,
    glyph: STATE.caution.glyph,
    gloss: "the band's relationship to pain demonstrably changes with the stimulation",
  },
  {
    key: "cannot tell",
    st: STATE.caution,
    glyph: "?",
    gloss: "the data cannot separate a steady band from one that changes. Not a pass, and not a " +
           "failure",
  },
  {
    key: "not tested",
    st: STATE.notChecked,
    glyph: STATE.notChecked.glyph,
    gloss: "the test could not be run, so nothing is known either way",
  },
];

const isNum = (v) => v != null && Number.isFinite(Number(v));

/**
 * When the recordings and settings behind this answer were put together (audit item P-03: "the
 * stability result does not say when it was measured"). This test is refit on every request from
 * the same recordings, therapy settings and pain reports the rest of the report reads, so the date
 * that matters is the one already on the report's own freshness line (`cache_status`,
 * `CacheStatusLine.js`) rather than a second, separately-tracked timestamp for this one card. A
 * missing or unreadable status prints nothing here, the same rule `CacheStatusLine` follows: silence
 * about freshness must never be dressed up as a real date.
 */
function whenBuilt(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

/**
 * The four answers as one segmented row, always drawn so a reader sees that "cannot tell" was one
 * of them; the answer that happened carries its glyph, its ink and a tint, the others are plain.
 * Its sentence is printed once, as the section's answer (decision 302: the three unlit sentences
 * were read by nobody).
 */
function AnswerRow({ answer, lit, i, n }) {
  return (
    <MDBox role="listitem" data-lit={lit ? "true" : "false"} px={1.5} py={0.5}
      sx={{ border: `1px solid ${lit ? answer.st.ink : PAL.rule}`, marginLeft: i === 0 ? 0 : "-1px",
        position: "relative", zIndex: lit ? 1 : 0, backgroundColor: lit ? answer.st.tint : PAL.surface,
        borderRadius: i === 0 ? "4px 0 0 4px" : (i === n - 1 ? "0 4px 4px 0" : 0) }}>
      <MDTypography variant="caption" sx={{ ...TYPE.body, fontWeight: lit ? 600 : 400,
        color: lit ? answer.st.ink : PAL.ink3 }}>
        {lit ? <span aria-hidden="true" style={{ marginRight: 6 }}>{answer.glyph}</span> : null}
        {answer.key}
      </MDTypography>
    </MDBox>
  );
}

/** One label-and-value line from the evidence behind the answer. */
function Fact({ label, value }) {
  return (
    <MDBox display="flex" justifyContent="space-between" alignItems="baseline" mb={0.25}>
      <MDTypography variant="caption" sx={{ ...TYPE.body, color: PAL.ink2, mr: 2 }}>
        {label}
      </MDTypography>
      <MDTypography variant="caption" sx={{ ...TYPE.body, fontWeight: 600, color: PAL.ink }}>
        {value}
      </MDTypography>
    </MDBox>
  );
}

export default function BandStabilityPanel({ stability, cacheStatus, painScore }) {
  const s = stability || null;
  const answer = s && s.answer ? s.answer : "not tested";

  // The band this answer is about. Printed in the subtitle so the answer can never be read as
  // being about a different band than the one the rest of the page is discussing.
  const bandPhrase = (s && isNum(s.band_center_hz))
    ? `${fmtNum(s.band_center_hz, 1)} Hz centre, ${fmtNum(s.band_width_hz, 1)} Hz wide` +
      (s.electrode ? `, on ${s.electrode}` : "")
    : "no band assessed";

  // WHEN, audit item P-03. Only printed once the test actually ran: a "not tested" answer has no
  // record to date, and dating it would read as though something had been measured.
  const builtWhen = (s && s.test_ran && cacheStatus) ? whenBuilt(cacheStatus.last_built_utc) : null;

  const perState = (s && s.measurements_per_state) || {};
  const stateCounts = Object.keys(perState)
    .filter((k) => isNum(perState[k]))
    .map((k) => `${k}: ${perState[k]}`)
    .join("  \u00b7  ");

  // THE ODDS RATIO IN EACH STIMULATION STATE, WITH ITS INTERVAL (P-03, June audit item [0]). The
  // numbers stay in the open (Fold's rule: values never folded). Printed only when the test ran.
  const perStateOr = (s && s.test_ran && s.odds_ratio_per_state) || {};
  const orLines = Object.keys(perStateOr).map((k) => {
    const v = perStateOr[k] || {};
    return `${k}: ${fmtOddsRatioWithInterval(v.odds_ratio, v.low, v.high)}`
      + (isNum(v.n) ? `, ${v.n} measurements` : "");
  });
  // ONE PAIN REPORT, ONE STATE (P-03, June audit item [22]). Said when the answer carries the
  // count, including when it is zero; an answer from before the rule carries none and says nothing.
  const nSplit = s && s.test_ran ? s.n_reports_split_across_states : null;
  const splitLine = !isNum(nSplit) ? null
    : Number(nSplit) === 0 ? "No pain report had samples on both sides of a change of current."
      : `${nSplit} pain report${Number(nSplit) === 1 ? "" : "s"} had samples recorded on both sides `
        + "of a change of current; each is counted once, in the state of its first sample.";

  const interval = (s && Array.isArray(s.difference_interval) && s.difference_interval.length === 2)
    ? `${fmtNum(s.difference_interval[0], 2)} to ${fmtNum(s.difference_interval[1], 2)}`
    : null;

  const lit = ANSWERS.find((x) => x.key === answer) || ANSWERS[3];
  const note = (children) => (
    <MDTypography variant="caption" display="block" sx={{ ...TYPE.body, color: PAL.warnText, mb: 1, maxWidth: "68ch" }}>
      <span aria-hidden="true" style={{ marginRight: 6 }}>{STATE.caution.glyph}</span>
      {children}
    </MDTypography>
  );

  return (
    <Card sx={{ ...CARD, p: 3, height: "100%" }}>
      <MDTypography component="h2" sx={{ ...TYPE.title, ...WRAP.balance, color: PAL.ink }}>
        Does the band mean the same at every stimulation state?
      </MDTypography>
      <MDTypography data-testid="stability-answer" sx={{ ...TYPE.lead, color: PAL.ink, mt: 1, maxWidth: "68ch" }}>
        <span aria-hidden="true" style={{ color: lit.st.ink, marginRight: 6 }}>{lit.glyph}</span>
        <b style={{ fontWeight: 600, color: lit.st.ink }}>{`${lit.key.charAt(0).toUpperCase()}${lit.key.slice(1)}`}</b>
        {`: ${lit.gloss}.`}
      </MDTypography>
      <MDTypography variant="caption" sx={{ ...TYPE.caption, color: PAL.ink3, display: "block", mt: 0.5 }}>
        {bandPhrase}
        {painScore && painScore.key ? (
          <span data-testid="stability-pain-score">
            {` · Pain score: ${painScore.label || painScore.key}.`}
          </span>
        ) : null}
      </MDTypography>
      {builtWhen ? (
        <MDTypography variant="caption" display="block" sx={{ ...TYPE.caption, color: PAL.ink3 }}>
          {`Measured on the recordings, settings and pain reports assembled ${builtWhen}; this test is `
            + "refit fresh every time this page is read."}
        </MDTypography>
      ) : null}

      <MDBox role="list" aria-label="The four possible answers" display="flex" flexWrap="wrap" mt={2} mb={2}>
        {ANSWERS.map((a, i) => (
          <AnswerRow key={a.key} answer={a} lit={a.key === answer} i={i} n={ANSWERS.length} />
        ))}
      </MDBox>

      {s && s.reason ? (
        <MDTypography variant="caption" display="block"
          sx={{ ...TYPE.body, color: PAL.ink2, mb: 2, maxWidth: "68ch" }}>
          {s.reason}
        </MDTypography>
      ) : null}

      {orLines.length ? (
        <MDBox mb={2}>
          <MDTypography component="h3" variant="caption" display="block"
            sx={{ ...TYPE.body, fontWeight: 600, color: PAL.ink }}>
            Odds ratio per standard deviation of band power, in each stimulation state
          </MDTypography>
          <MDTypography variant="caption" display="block" sx={{ ...TYPE.caption, color: PAL.ink3, mb: 0.5 }}>
            How much the odds of a high-pain report change when band power rises by its own typical
            spread; 1 means no change. Each with its 95% range.
          </MDTypography>
          {orLines.map((line) => (
            <MDTypography key={line} variant="caption" display="block"
              sx={{ ...TYPE.body, color: PAL.ink, py: 0.25, borderTop: `1px solid ${PAL.rule}` }}>
              {line}
            </MDTypography>
          ))}
          {splitLine ? (
            <MDTypography variant="caption" display="block" sx={{ ...TYPE.body, color: PAL.ink2, mt: 0.5 }}>
              {splitLine}
            </MDTypography>
          ) : null}
        </MDBox>
      ) : null}

      {/*
        Two things that change how much the answer is worth. Both are drawn only when the backend
        actually knows them: a missing value is left out rather than printed as "no", because "no"
        would say the problem was looked for and ruled out.
      */}
      {s && s.rate_moved_with_current === true ? note(
        "The stimulation rate was changing at the same times as the current, so this answer is "
          + "partly about the rate rather than only about the current.",
      ) : null}
      {s && isNum(s.distance_to_nearest_artifact_hz)
        && Number(s.distance_to_nearest_artifact_hz) <= 2.5 ? note(
          `A multiple of the stimulation rate folds back into the recording ${fmtNum(s.distance_to_nearest_artifact_hz, 1)} Hz `
            + "from the middle of this band, so some of the power here is a folded multiple of the stimulation rate.",
        ) : null}

      {s && s.test_ran ? (
        <MDBox mb={2}>
          <Fold show="How this was worked out (what the answer rests on, how the ranges were computed)"
            hide="Hide how this was worked out" mt={0}>
            <MDBox mt={0.5}>
              {isNum(s.largest_difference) ? (
                <Fact label="biggest difference seen between two stimulation states"
                  value={fmtNum(s.largest_difference, 2)} />
              ) : null}
              {interval ? (
                <Fact label="range that difference could plausibly lie in" value={interval} />
              ) : null}
              {isNum(s.declared_margin) ? (
                <Fact label="difference we said in advance would matter"
                  value={fmtNum(s.declared_margin, 2)} />
              ) : null}
              {isNum(s.p_value) ? (
                <Fact label="chance of a difference this large if the band were steady"
                  value={fmtP(s.p_value)} />
              ) : null}
              {isNum(s.n_measurements) ? (
                <Fact label="measurements used" value={String(s.n_measurements)} />
              ) : null}
              {isNum(s.n_time_blocks) ? (
                <Fact label="separate blocks of time they came from" value={String(s.n_time_blocks)} />
              ) : null}
              {isNum(s.n_states_compared) ? (
                <Fact label="stimulation states that could be compared" value={`${s.n_states_compared} of 3`} />
              ) : null}
              {stateCounts ? (
                <Fact label="measurements in each state" value={stateCounts} />
              ) : null}
              {s.odds_ratio_interval_method ? (
                <MDTypography variant="caption" display="block" sx={{ ...TYPE.body, color: PAL.ink2, mt: 1 }}>
                  {s.odds_ratio_interval_method}
                </MDTypography>
              ) : null}
            </MDBox>
          </Fold>
        </MDBox>
      ) : null}

      <MDBox pt={1.5} sx={{ borderTop: `1px solid ${PAL.rule}` }}>
        <MDTypography variant="caption" sx={{ ...TYPE.body, color: PAL.ink2 }}>
          Whether this stops a deployment:{" "}
          {(s && s.blocking_status)
            || "not decided - reported for the PI to rule on, blocks nothing today"}
        </MDTypography>
      </MDBox>

      {!s ? (
        <MDBox mt={1}>
          <MDTypography variant="caption" sx={{ ...TYPE.body, color: PAL.ink2 }}>
            The report carried no answer for this band, so nothing is known either way. This is not
            a pass.
          </MDTypography>
        </MDBox>
      ) : null}
    </Card>
  );
}
