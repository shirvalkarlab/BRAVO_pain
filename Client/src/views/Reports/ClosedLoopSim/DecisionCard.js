/**
 * The decision card: the one card a clinician reads at the programmer (decision 302).
 *
 * THE PI, 2026-09-26: "Combine the full parameter recommendation with the deployment card to create
 * one simple, streamlined card. Keep the evidence cards separate." And: "If the device permits this
 * configuration and the evidence supports it, the detailed text below should be hidden or
 * collapsible. If the device doesn't permit the configuration, there should be red bullet points
 * below that list, in five words or less, why it's blocked. Similarly, if the evidence wasn't
 * evaluated but should have been, use yellow bullet points with the same format."
 *
 * It replaces three things: the sticky verdict header, the "Full parameter recommendation" card
 * and the "Deploy-to-Percept review" sign-off card. Top to bottom:
 *
 *   1. ONE STATUS LINE, the reconciled verdict (decision 242: one verdict), computed from the device
 *      rule table and the evidence triangle through the same state tracks the header used.
 *   2. RED BULLETS, only when the device refuses: one per blocking rule, "Unmet: <label>" or
 *      "Unchecked: <label>", the label the rule table itself carries (at most four words, so the
 *      bullet is at most five). YELLOW BULLETS for evidence that should have been evaluated and was
 *      not, "Untested: <label>", from the report's own list and the summary's gates. Both carry a
 *      word and an icon as well as a colour.
 *   3. THE VALUES TO ENTER, only when the device allows them (withheld otherwise, with the planning
 *      view behind a button, as before), with what the device runs today in its own column.
 *   4. SIGN AND PRINT, and Export.
 *   5. ONE "Details" FOLD holding everything that explained the above: who can resolve each item,
 *      the rule table's own sentences, how each value was derived and checked, and the full
 *      sign-off record. Closed when the configuration is allowed and supported, open otherwise.
 *      The print stylesheet opens it, so the paper record keeps its full detail; the SCREEN is what
 *      is short.
 *
 * WHAT IS NOT HERE ANY MORE. The E1/E2/E3 lines and the sign-agreement track (they are on the
 * evidence card, which stays); the three state tracks side by side (the status line says the same
 * in one sentence); the caveat-count sentence (the count is on the Details control).
 */
import { Card, Icon } from "@mui/material";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import MDButton from "components/MDButton";

import PAL from "./palette";
import Fold from "./Fold";
import { TRACKS } from "./stateTracks";
import { provisionalCaveat } from "./ProvisionalNote";
import { fmtHz } from "./deployFormat";
import ParameterTable, { ParameterDetails } from "./PrescriptionPanel";
import SignoffRecord, { useSignoffActions, StaleNotice, SnapshotFigures } from "./DeploySignoffCard";
import WhatWouldChangeThis from "./WhatWouldChangeThis";
import BandCandidateIdentity from "./BandCandidateIdentity";

// Jump targets, set as `id` on the Grid items in index.js, in the order the page draws them.
// DeploymentJumpLinks.order.test.js holds this list to the page's own order.
export const JUMPS = [
  { id: "cl-rules", label: "Device rules" },
  { id: "cl-evidence", label: "Evidence" },
  { id: "cl-stability", label: "Stability" },
  { id: "cl-three-source", label: "Current and band power" },
  { id: "cl-simulation", label: "CL-DBS simulations" },
];

function jumpTo(id) {
  const el = document.getElementById(id);
  if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
}

const repOf = (deploymentReport) => (deploymentReport && deploymentReport.data !== undefined
  ? deploymentReport.data : deploymentReport) || null;

/** The one verdict, from the device rule table and the evidence triangle together. */
export function decisionStatus(rep) {
  const device = TRACKS.device.lit(rep);
  const evidence = TRACKS.evidence.lit(rep);
  if (device === 2) {
    return { key: "unevaluated", ink: "#4A4A4A", icon: "help_outline",
      headline: "Device rules not evaluated", sub: "Nothing here is permission to program." };
  }
  if (device === 1) {
    return { key: "refused", ink: PAL.failText, icon: "block",
      headline: "Device refuses this configuration",
      sub: "This record authorises nothing." };
  }
  if (evidence === 1) {
    return { key: "misaligned", ink: PAL.warnText, icon: "report_problem",
      headline: "Device allows it; evidence contradicts the control law", sub: null };
  }
  if (evidence === 2) {
    return { key: "unestablished", ink: PAL.warnText, icon: "help_outline",
      headline: "Device allows it; evidence not established", sub: null };
  }
  if (provisionalCaveat(rep)) {
    return { key: "supported_provisional", ink: PAL.warnText, icon: "check_circle",
      headline: "Device allows it; evidence supports it (provisional)", sub: null };
  }
  return { key: "supported", ink: PAL.passText, icon: "check_circle",
    headline: "Device allows it; evidence supports it", sub: null };
}

/** "Single neurostimulator implanted" -> "single neurostimulator implanted", leaving "DBS" alone. */
const lc = (s) => {
  const t = String(s || "");
  return t.length > 1 && /[a-z]/.test(t[1]) ? t[0].toLowerCase() + t.slice(1) : t;
};

/** Red bullets: one per blocking rule, and only when the device refuses. */
export function deviceBullets(rep) {
  if (TRACKS.device.lit(rep) !== 1) return [];
  const el = (rep && rep.eligibility) || {};
  const row = (r, state) => ({
    key: `${state}-${r.rule_id}`,
    ruleId: r.rule_id,
    title: r.title || "",
    text: `${state} ${lc(r.short_label || `rule ${r.rule_id}`)}`,
  });
  return [
    ...(el.failures || []).filter((r) => r.counts_toward_verdict !== false).map((r) => row(r, "Unmet:")),
    ...(el.unknowns || []).map((r) => row(r, "Unchecked:")),
  ];
}

/** Yellow bullets: evidence that should have been evaluated and was not. An answer that came back
 *  unsettled is an answer, and is read on its own card, never here. */
export function unevaluatedBullets(rep, summaryData) {
  const fromReport = ((rep && rep.evidence_not_evaluated) || []).map((r) => ({
    key: `ev-${r.key}`, text: `Untested: ${lc(r.label)}`, why: r.why }));
  const fromGates = ((summaryData && summaryData.gates) || [])
    .filter((g) => g && g.evaluated === false)
    .map((g) => ({ key: `gate-${g.key}`, text: `Untested: ${lc(g.short_label || g.label)}`, why: g.detail }));
  return [...fromReport, ...fromGates];
}

function Bullets({ items, cls, ink, icon, label }) {
  if (!items.length) return null;
  return (
    <MDBox component="ul" className={cls} aria-label={label}
      sx={{ listStyle: "none", p: 0, m: 0, mt: 0.8 }}>
      {items.map((b) => (
        <MDBox component="li" key={b.key} display="flex" alignItems="center" gap={0.6} py={0.15}
          title={b.title || b.why || undefined}>
          <Icon aria-hidden="true" sx={{ fontSize: "18px !important", color: ink }}>{icon}</Icon>
          <MDTypography variant="caption" component="span" data-bullet=""
            sx={{ fontSize: 13.5, fontWeight: 600, color: ink, lineHeight: 1.3 }}>
            {b.text}
          </MDTypography>
        </MDBox>
      ))}
    </MDBox>
  );
}

/**
 * One part of the Details fold. `folded` parts (the long reference material: how each value was
 * derived, the full sign-off record, the band file) are their own closed folds even when Details
 * opens by itself, so an open Details shows why the answer is what it is and who can change it,
 * and not three thousand words; the print stylesheet opens every fold.
 */
function Section({ title, children, folded = false }) {
  if (!children) return null;
  return (
    <MDBox mt={1.2} pt={1} sx={{ borderTop: "1px solid rgba(0,0,0,0.10)" }}>
      {folded ? (
        <Fold show={title} hide={`Hide: ${title.toLowerCase()}`} mt={0}>{children}</Fold>
      ) : (
        <>
          {title ? (
            <MDTypography variant="caption" sx={{ display: "block", fontSize: 12, fontWeight: 700,
              color: "#1A1A1A", mb: 0.4 }}>
              {title}
            </MDTypography>
          ) : null}
          {children}
        </>
      )}
    </MDBox>
  );
}

export default function DecisionCard({ participantUid, bandCandidate, summary, deploymentReport,
                                       chosenBand, bandRecord, cutpoint, mode, onMode, onRecompute }) {
  const bc = bandCandidate || {};
  const rep = repOf(deploymentReport);
  const loading = !!(deploymentReport && deploymentReport.loading);
  // A report computed for a band other than the chosen one reaches this card with no data and this
  // field set (`withheldIfOtherBand`): the card names both bands and gives no verdict at all.
  const mismatch = deploymentReport && deploymentReport.bandMismatch;
  const reportErr = mismatch ? null : deploymentReport && deploymentReport.err;
  const sm = (summary && summary.data) || null;
  const status = mismatch
    ? { key: "other_band", ink: PAL.warnText, icon: "sync_problem",
      headline: `Recompute: the analysis shown is for ${mismatch.computedFor}`,
      sub: `The chosen band is ${mismatch.chosen}. Nothing on this page describes it until the `
        + "analysis is recomputed." }
    : decisionStatus(rep);
  const allowedAndSupported = status.key === "supported" || status.key === "supported_provisional";
  const red = deviceBullets(rep);
  const yellow = unevaluatedBullets(rep, sm);
  const vd = (rep && rep.verdict_detail) || {};
  const blockers = vd.blockers || [];
  const caveats = (rep && Array.isArray(rep.caveats)) ? rep.caveats : [];
  const nHigh = caveats.filter((c) => c && c.severity === "high").length;
  const actions = useSignoffActions({ participantUid, bandCandidate, summary, cutpoint, chosenBand,
    bandRecord });
  const pain = rep && rep.pain_score;

  const detailsLabel = caveats.length
    ? `Details (${caveats.length} caveat${caveats.length === 1 ? "" : "s"}${nHigh ? `, ${nHigh} serious` : ""})`
    : "Details";

  return (
    <Card className="cl-decision-card" sx={{ width: "100%", border: `2px solid ${status.ink}`,
      boxShadow: "none" }}>
      <MDBox px={2.2} pt={1.8} pb={1.6}>
        <StaleNotice inputsStale={actions.inputsStale} computedAt={actions.computedAt}
          staleWhy={actions.staleWhy} />

        <MDBox display="flex" flexDirection="row" alignItems="flex-start" gap={1.2}>
          <Icon aria-hidden="true" sx={{ fontSize: "30px !important", color: status.ink, mt: 0.1 }}>
            {loading ? "hourglass_empty" : status.icon}
          </Icon>
          <MDBox flex="1 1 auto">
            <MDTypography variant="h5" component="h2" sx={{ fontSize: 19, lineHeight: 1.25, color: status.ink }}>
              {loading ? "Evaluating the device rules and the evidence…" : status.headline}
            </MDTypography>
            {!loading && status.sub ? (
              <MDTypography variant="caption" sx={{ display: "block", fontSize: 13, color: "#2A2A2A", mt: 0.2 }}>
                {status.sub}
              </MDTypography>
            ) : null}
            <MDTypography variant="caption" sx={{ display: "block", fontSize: 12.5, color: "#4A4A4A", mt: 0.3 }}>
              {`${bc.contact_label || bc.contact || "band"} at ${fmtHz(bc.center_freq_hz) || "an unspecified"} Hz`
                + `${bc.hemisphere ? `, ${bc.hemisphere} side` : ""}`
                + `${pain && pain.label ? `, pain score ${pain.label}` : ""}`
                + `${reportErr ? `. The device rule table is unavailable: ${reportErr}` : ""}`}
            </MDTypography>
          </MDBox>
          <MDBox component="nav" className="cl-jumps" aria-label="On this page" display="flex"
            flexDirection="column" gap={0.2} flex="0 0 auto" alignItems="flex-end">
            {JUMPS.map((j) => (
              <MDTypography key={j.id} variant="caption" component="button" type="button"
                onClick={() => jumpTo(j.id)}
                sx={{ fontSize: 12, color: PAL.accent, cursor: "pointer", whiteSpace: "nowrap",
                  background: "none", border: 0, p: 0, fontFamily: "inherit",
                  "&:hover": { textDecoration: "underline" },
                  "&:focus-visible": { outline: `2px solid ${PAL.accent}`, outlineOffset: 2 } }}>
                {j.label}
              </MDTypography>
            ))}
          </MDBox>
        </MDBox>

        {mismatch && onRecompute ? (
          <MDButton size="small" variant="contained" color="info" onClick={onRecompute}
            sx={{ textTransform: "none", fontSize: 12.5, mt: 1 }}>
            {`Recompute for ${mismatch.chosen}`}
          </MDButton>
        ) : null}

        {!loading ? (
          <>
            <Bullets items={red} cls="cl-bullets-red" ink={PAL.failText} icon="close"
              label="Why the device refuses" />
            <Bullets items={yellow} cls="cl-bullets-yellow" ink={PAL.warnText} icon="priority_high"
              label="Evidence that was not evaluated" />
          </>
        ) : null}

        <MDBox mt={1.6} pt={1.2} sx={{ borderTop: "1px solid rgba(0,0,0,0.10)" }}>
          <MDTypography variant="caption" sx={{ display: "block", fontSize: 13, fontWeight: 700,
            color: "#1A1A1A", mb: 0.6 }}>
            Values to enter on the A610
          </MDTypography>
          <ParameterTable report={mismatch ? { data: null } : deploymentReport} mode={mode} onMode={onMode} />
        </MDBox>

        <MDBox className="cl-signoff-actions" display="flex" gap={1} mt={1.6} flexWrap="wrap">
          <MDButton size="small" variant="outlined" color="dark" onClick={actions.printWithFigures}
            disabled={actions.capturing} sx={{ textTransform: "none", fontSize: 12.5 }}>
            {actions.capturing ? "Capturing figures…" : "Sign and print"}
          </MDButton>
          <MDButton size="small" variant="text" color="info" onClick={actions.exportJson}
            disabled={actions.capturing || !actions.hasData} sx={{ textTransform: "none", fontSize: 12.5 }}>
            Export JSON
          </MDButton>
        </MDBox>

        <MDBox className="cl-details" mt={1.2}>
          {/* Keyed on the verdict, so the fold opens by itself when the answer changes to one that
              needs reading, and a reader's own toggle survives every other re-render. */}
          <Fold key={status.key} show={detailsLabel} hide="Hide details" defaultOpen={!allowedAndSupported}>
            <WhatWouldChangeThis report={deploymentReport} bare />
            {/* The module's blocker sentences, verbatim. Its warnings (today the two D26 capture
                checks) are not repeated here: they are the first entries of the caveats list in the
                sign-off record below, and the D26 row above quotes them too. */}
            {blockers.length ? (
              <Section title="The rule table's own sentences">
                {blockers.map((b) => (
                  <MDTypography key={b} variant="caption" sx={{ display: "block", fontSize: 11.5, color: PAL.failText, mt: 0.3 }}>
                    {b}
                  </MDTypography>
                ))}
              </Section>
            ) : null}
            <Section title="How each value was derived and checked" folded>
              <ParameterDetails report={deploymentReport} mode={mode} />
            </Section>
            <Section title="The sign-off record: gates, evidence, caveats, the band signed for" folded>
              <SignoffRecord bandCandidate={bandCandidate} summary={summary}
                deploymentReport={deploymentReport} chosenBand={chosenBand} bandRecord={bandRecord} />
            </Section>
            {bc.contact ? (
              <Section title="The band as committed" folded>
                <BandCandidateIdentity bc={bc} envelope={chosenBand} />
              </Section>
            ) : null}
          </Fold>
        </MDBox>

        <SnapshotFigures snapshots={actions.snapshots} />
      </MDBox>
    </Card>
  );
}
