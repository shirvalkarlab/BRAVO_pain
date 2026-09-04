/**
 * One reconciled verdict for the whole page, replacing the three separate verdict statements that
 * used to sit on it.
 *
 * THE PROBLEM THIS SOLVES. Until this rebuild the page carried three headline answers computed from
 * two different endpoints. The verdict strip and the sign-off card each printed a readiness
 * sentence derived from /api/queryDeploymentSummary, which evaluates the STATISTICAL gates, while
 * the evidence panel printed a third derived from /api/queryClosedLoopDeployment, which evaluates
 * the DEVICE RULES. The two endpoints answer different questions, so the three statements could
 * disagree with each other, and a reader had no way to tell which of them governed. On RCS08 they
 * did disagree: the statistical summary could report a threshold while the device rule table
 * refused the configuration outright.
 *
 * WHY THREE CELLS RATHER THAN ONE WORD. The action a reader should take depends on WHICH conjunct
 * failed, and the remedies are not interchangeable. A device refusal is resolved at the programmer
 * or by choosing a different configuration. Unestablished evidence is resolved only by measuring
 * more, and no amount of reprogramming touches it. A single word cannot carry that, and a reader
 * must be able to see which conjunct failed without scrolling, so the three sub-answers are drawn
 * side by side and each one is a state track with all of its states visible.
 *
 * WHY NO THRESHOLD VALUE APPEARS HERE AT ALL. The component this replaces printed a value to
 * program at nineteen-point type, and it did so gated only on the statistical endpoint. The
 * rightmost cell of this header answers whether there is anything to transcribe and says WITHHELD
 * when there is not; the numbers themselves live in the prescription panel, which withholds the
 * whole table on the same condition. A number in a headline position during a programming visit
 * gets typed, so the headline carries no numbers a reader could type.
 *
 * The statistical gate counts remain on the page in the row beneath, explicitly labelled as
 * evidence rather than as a verdict. They are informative and they are not permission.
 */
import { Card, Icon } from "@mui/material";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import PAL from "./palette";
import StateTrack from "./StateTrack";
import { TRACKS } from "./stateTracks";
import { fmtHz } from "./deployFormat";

// Jump targets, set as `id` on the Grid items in index.js. The order is the reading order of the
// clinician route, so the links double as a table of contents for the page.
const JUMPS = [
  { id: "cl-what-changes", label: "What would change this" },
  { id: "cl-rules", label: "Device rules" },
  { id: "cl-evidence", label: "Evidence triangle" },
  { id: "cl-prescription", label: "Parameters" },
  { id: "cl-duty", label: "Predicted duty cycle" },
  { id: "cl-signoff", label: "Sign-off \u2193" },
];

function jumpTo(id) {
  const el = document.getElementById(id);
  if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
}

/**
 * The one sentence at the top, built from the conjunction of the three sub-answers rather than from
 * any single endpoint.
 *
 * Each branch names what a reader should do next, because a verdict that does not imply an action
 * gets read as a score. The wording avoids the word "ready", which the previous strip used for a
 * state in which the device would have refused the configuration.
 */
function reconcile(device, evidence, transcription) {
  if (device === 2) {
    return {
      ink: PAL.neutral, icon: "hourglass_empty",
      headline: "The device rules have not been evaluated for this configuration",
      body: "Nothing on this page is a permission to program until they have been. An absent "
          + "verdict is not the same as a favourable one.",
    };
  }
  if (device === 1) {
    return {
      ink: PAL.fail, icon: "block",
      headline: "This configuration cannot be programmed: the device refuses it",
      body: "At least one encoded Percept rule is violated, or reads a value that has not been "
          + "supplied. The device rule ledger below names each one with its page citation. The "
          + "parameter values are withheld rather than shown, because a number on screen during a "
          + "programming visit gets entered.",
    };
  }
  if (evidence === 1) {
    return {
      ink: PAL.warn, icon: "report_problem",
      headline: "The device permits this configuration, and the evidence does not support it",
      body: "The three edges are resolved and their signs are not the ones the selected control "
          + "law assumes. Read the evidence panel before deciding: the edges can disagree with "
          + "each other, or agree with each other and disagree with the control law, and those "
          + "two findings call for different responses.",
    };
  }
  if (evidence === 2) {
    return {
      ink: PAL.warn, icon: "help_outline",
      headline: "The device permits this configuration; the evidence has not established that it "
              + "would work",
      body: "This is a measurement problem rather than a programming one. At least one edge of the "
          + "amplitude-power-pain triangle is unresolved, or the coherence test could not be run, "
          + "so the evidence has not answered the question in either direction.",
    };
  }
  if (transcription === 0) {
    return {
      ink: PAL.pass, icon: "check_circle",
      headline: "The device permits this configuration and the evidence supports it",
      body: "The parameter table below is shown with its read-back checklist enabled. Confirm "
          + "every value against what the programmer displays before accepting it, and note that "
          + "several ranges are unpublished and have to be checked on the device.",
    };
  }
  return {
    ink: PAL.neutral, icon: "help_outline",
    headline: "The three answers below have not been reconciled",
    body: "This combination of sub-answers was not anticipated, so no single verdict is asserted. "
        + "Read the three cells individually.",
  };
}

/**
 * One sub-answer cell. `flex` rather than a fixed width so three long state labels wrap inside
 * their own cell instead of pushing the third cell off the row.
 */
function Cell({ track, data, first }) {
  return (
    <MDBox flex="1 1 240px" px={1.4} py={0.6}
      sx={{ borderLeft: first ? "none" : "1px solid rgba(0,0,0,0.12)" }}>
      <StateTrack track={track} data={data} dense showBlurb />
    </MDBox>
  );
}

export default function DeploymentDecisionHeader({ bandCandidate, summary, deploymentReport }) {
  const bc = bandCandidate || {};
  const rep = (deploymentReport && deploymentReport.data) || null;
  const loading = !!(deploymentReport && deploymentReport.loading);
  const reportErr = deploymentReport && deploymentReport.err;

  const device = TRACKS.device.lit(rep);
  const evidence = TRACKS.evidence.lit(rep);
  const transcription = TRACKS.transcription.lit(rep);
  const v = reconcile(device, evidence, transcription);

  const sm = (summary && summary.data) || null;
  const blockers = ((rep && rep.verdict_detail) || {}).blockers || [];
  const el = (rep && rep.eligibility) || null;

  return (
    // `cl-verdict-strip` is the class the print stylesheet re-shows, so the printed record still
    // begins with the reconciled verdict. The class name is kept from the component this replaces
    // rather than renamed, because renaming it would silently drop the header from every printout.
    <Card id="cl-verdict-strip" className="cl-verdict-strip"
      sx={{ width: "100%", position: "sticky", top: 8, zIndex: 5,
        border: `2px solid ${v.ink}`, backgroundColor: "#FFFFFF" }}>
      <MDBox px={2} pt={1.2} pb={1}>
        {/* The reconciled sentence. */}
        <MDBox display="flex" flexDirection="row" alignItems="flex-start" gap={1.2}>
          <Icon sx={{ fontSize: "28px !important", color: v.ink, mt: 0.2 }}>
            {loading ? "hourglass_empty" : v.icon}
          </Icon>
          <MDBox flex="1 1 auto">
            <MDTypography variant="h6" sx={{ fontSize: 16, lineHeight: 1.25, color: v.ink }}>
              {loading ? "Evaluating the device rules and the evidence triangle\u2026" : v.headline}
            </MDTypography>
            <MDTypography variant="caption" sx={{ display: "block", fontSize: 11.5, mt: 0.3,
              color: "#4A4A4A" }}>
              {loading ? "\u00A0" : v.body}
            </MDTypography>
            <MDTypography variant="caption" sx={{ display: "block", fontSize: 10.5, mt: 0.4,
              color: "#7A7A7A" }}>
              {`${bc.contact_label || bc.contact || "band"} at `
                + `${fmtHz(bc.center_freq_hz) || "an unspecified"} Hz`
                + `${bc.hemisphere ? `, ${bc.hemisphere} hemisphere` : ""}`
                + `${el ? ` \u00B7 ${el.checked} device rules checked` : ""}`
                + `${reportErr ? ` \u00B7 device rule table unavailable: ${reportErr}` : ""}`}
            </MDTypography>
          </MDBox>

          {/* Jump links. Hidden in print, because a paper record has no anchors to follow. */}
          <MDBox className="cl-jumps" display="flex" flexDirection="column" gap={0.2}
            flex="0 0 auto" alignItems="flex-end">
            {JUMPS.map((j) => (
              <MDTypography key={j.id} variant="caption" onClick={() => jumpTo(j.id)}
                sx={{ fontSize: 10.5, color: PAL.accent, cursor: "pointer", whiteSpace: "nowrap",
                  "&:hover": { textDecoration: "underline" } }}>
                {j.label}
              </MDTypography>
            ))}
          </MDBox>
        </MDBox>

        {/* The three sub-answers, side by side so the failing conjunct is visible without
            scrolling. */}
        <MDBox display="flex" flexDirection="row" flexWrap="wrap" mt={1}
          sx={{ borderTop: "1px solid rgba(0,0,0,0.10)", pt: 0.8 }}>
          <Cell track={TRACKS.device} data={rep} first />
          <Cell track={TRACKS.evidence} data={rep} />
          <Cell track={TRACKS.transcription} data={rep} />
        </MDBox>

        {/* The statistical gate counts, kept on the page as evidence and labelled as such. They
            come from the OTHER endpoint and they are not a permission to program; saying so here is
            the whole reason they were demoted out of the headline. */}
        <MDBox mt={0.8} pt={0.6} sx={{ borderTop: "1px solid rgba(0,0,0,0.10)" }}>
          <MDTypography variant="caption" sx={{ fontSize: 10, fontWeight: "bold",
            letterSpacing: 0.4, color: "#8A8A8A" }}>
            STATISTICAL GATES, FROM THE SEPARATE DEPLOYMENT SUMMARY — EVIDENCE, NOT PERMISSION
          </MDTypography>
          <MDTypography variant="caption" sx={{ display: "block", fontSize: 11, color: "#4A4A4A" }}>
            {sm
              ? `${sm.n_necessary_passed ?? "an unreported number"} of `
                + `${sm.n_necessary ?? "an unreported number"} required gates passed, `
                + `${sm.n_gates_passed ?? "an unreported number"} of `
                + `${sm.n_gates ?? "an unreported number"} gates in total`
                + `${sm.n_gates_indeterminate ? `, ${sm.n_gates_indeterminate} not tested` : ""}`
                + `${sm.verdict ? `. Summary verdict: ${sm.verdict}` : ""}.`
                + " These gates ask whether the band discriminates, which is a different question"
                + " from whether the device will accept the configuration."
              : (summary && summary.loading)
                ? "Loading the statistical gate summary\u2026"
                : "The statistical gate summary is not available for this configuration. That does"
                  + " not change either of the two answers above, which are computed from the"
                  + " device rule table and the evidence triangle."}
          </MDTypography>
        </MDBox>

        {/* The module's own blocker sentences, verbatim. These are the shortest statement of why
            the device refuses, and they are written by the rule table rather than by this page. */}
        {blockers.length > 0 ? (
          <MDBox mt={0.8} p={1} sx={{ backgroundColor: PAL.failFill, borderRadius: "4px",
            border: `1px solid ${PAL.failBorder}` }}>
            <MDTypography variant="caption" sx={{ fontSize: 10, fontWeight: "bold",
              letterSpacing: 0.4, color: PAL.fail }}>
              {`WHY THE DEVICE REFUSES \u2014 ${blockers.length} `
                + `${blockers.length === 1 ? "STATEMENT" : "STATEMENTS"} FROM THE RULE TABLE`}
            </MDTypography>
            {blockers.map((b, i) => (
              <MDTypography key={`blk${i}`} variant="caption"
                sx={{ display: "block", fontSize: 11, color: "#3A3A3A", mt: 0.3 }}>
                {b}
              </MDTypography>
            ))}
          </MDBox>
        ) : null}
      </MDBox>
    </Card>
  );
}
