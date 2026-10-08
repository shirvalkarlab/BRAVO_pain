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
 *      rule table and the evidence triangle through the same state tracks the header used, and never
 *      better than the server's own verdict (`licensed`, `verdict_detail.blockers`).
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
 *      sign-off record. Closed by default whatever the verdict (the PI, 2026-10-08); the
 *      analysis's own reasons for stopping sit in the open under the bullets.
 *      The print stylesheet opens it, so the paper record keeps its full detail; the SCREEN is what
 *      is short.
 *
 * WHAT IS NOT HERE ANY MORE. The E1/E2/E3 lines and the sign-agreement track (they are on the
 * evidence card, which stays); the three state tracks side by side (the status line says the same
 * in one sentence); the caveat-count sentence (the count is on the Details control).
 */
import { Card } from "@mui/material";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import MDButton from "components/MDButton";

import PAL from "./palette";
import { TYPE, WRAP, STATE, decisionBar } from "assets/theme/base/tokens";
import Fold from "./Fold";
import { TRACKS } from "./stateTracks";
import { provisionalCaveat } from "./ProvisionalNote";
import { fmtHz } from "./deployFormat";
import ParameterTable, { ParameterDetails } from "./PrescriptionPanel";
import SignoffRecord, { useSignoffActions, StaleNotice, SnapshotFigures } from "./DeploySignoffCard";
import WhatWouldChangeThis from "./WhatWouldChangeThis";
import { JUMP_ROW_CLASS } from "views/Reports/paper/links";
import BandCandidateIdentity from "./BandCandidateIdentity";
import DeviceRuleLedger from "./DeviceRuleLedger";

// Jump targets, set as `id` on the Grid items in index.js, in the order the page draws them.
// DeploymentJumpLinks.order.test.js holds this list to the page's own order.
export const JUMPS = [
  { id: "cl-stim-program", label: "Stimulation program" },
  { id: "cl-wiring", label: "Sense-to-control algorithm wiring" },
  { id: "cl-decision", label: "Deployment decision" },
  { id: "cl-grid", label: "Band selection" },
  { id: "cl-evidence", label: "Evidence consistency" },
  { id: "cl-stability", label: "Stability across stimulation states" },
  { id: "cl-background", label: "Background" },
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
    return { key: "unevaluated", ink: PAL.ink3, glyph: STATE.notChecked.glyph,
      headline: "Device rules not evaluated", sub: "Nothing here is permission to program." };
  }
  if (device === 1) {
    return { key: "refused", ink: PAL.failText, glyph: STATE.refused.glyph,
      headline: "Device refuses this configuration",
      sub: "This record authorises nothing." };
  }
  if (evidence === 1) {
    return { key: "misaligned", ink: PAL.warnText, glyph: STATE.caution.glyph,
      headline: "Device allows it; evidence contradicts what the automatic adjustment assumes", sub: null };
  }
  if (evidence === 2) {
    return { key: "unestablished", ink: PAL.warnText, glyph: STATE.caution.glyph,
      headline: "Device allows it; evidence not established", sub: null };
  }
  // THE SERVER'S VERDICT BOUNDS THE HEADLINE. The server licenses a report only when the device
  // allows it, the three signs agree AND the analysis added no reason of its own to stop
  // (`verdict_detail.blockers`: a step that raised, a capture current above the module limit, a
  // control authority it could not estimate). Past the two checks above, a report the server did
  // not license reads "does not support it", never "supports it" (decision 242: one verdict, the
  // server's). Its reasons are the analysis's, not the device's, so the ink is not red. A response
  // that predates the `licensed` field is judged by its blocker list alone.
  const blockers = ((rep && rep.verdict_detail) || {}).blockers || [];
  if ((rep && rep.licensed === false) || blockers.length) {
    const n = blockers.length;
    return { key: "unsupported", ink: STATE.blocked.ink, glyph: STATE.blocked.glyph,
      headline: "Device allows it; the analysis does not support it",
      sub: n
        ? `The analysis stopped for ${n === 1 ? "a reason" : `${n} reasons`} of its own, listed `
          + "below. Nothing here is permission to program."
        : "The server's verdict is \"unsupported\". Nothing here is permission to program." };
  }
  if (provisionalCaveat(rep)) {
    return { key: "supported_provisional", ink: PAL.warnText, glyph: STATE.caution.glyph,
      headline: "Device allows it; evidence supports it (provisional)", sub: null };
  }
  return { key: "supported", ink: PAL.accent, glyph: STATE.pass.glyph,
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

function Bullets({ items, cls, ink, glyph, label }) {
  if (!items.length) return null;
  return (
    <MDBox component="ul" className={cls} aria-label={label}
      sx={{ listStyle: "none", p: 0, m: 0, mt: 1 }}>
      {items.map((b) => (
        <MDBox component="li" key={b.key} display="flex" alignItems="baseline" gap={1} py={0.25}
          title={b.title || b.why || undefined}>
          <span aria-hidden="true" style={{ color: ink, fontSize: PAL.fs.body, width: "1.2em",
            display: "inline-block" }}>{glyph}</span>
          <MDTypography variant="caption" component="span" data-bullet=""
            sx={{ ...TYPE.body, fontWeight: 600, color: ink }}>
            {b.text}
          </MDTypography>
        </MDBox>
      ))}
    </MDBox>
  );
}

/**
 * The contents row: the page's jump links, in one slim row under the head, never in a card. It
 * carries the shared jump-row class, so the global rule that underlines links inside sentences
 * leaves it alone (TASTE_AUDIT.md C3), and it has no "·" between links, only space (C11).
 */
export function ContentsRow() {
  return (
    <MDBox component="nav" className={`cl-jumps ${JUMP_ROW_CLASS}`} aria-label="On this page" display="flex"
      flexWrap="wrap" columnGap={3} rowGap={0.5} mt={2} pt={1.5}
      sx={{ borderTop: `1px solid ${PAL.rule}` }}>
      {JUMPS.map((j) => (
        <MDTypography key={j.id} variant="caption" component="button" type="button"
          onClick={() => jumpTo(j.id)}
          sx={{ ...TYPE.body, color: PAL.accent, cursor: "pointer", whiteSpace: "nowrap",
            background: "none", border: 0, p: 0, fontFamily: "inherit",
            "&:hover": { textDecoration: "underline" },
            "&:focus-visible": { outline: `2px solid ${PAL.accent}`, outlineOffset: 2 } }}>
          {j.label}
        </MDTypography>
      ))}
    </MDBox>
  );
}

/**
 * One part of the Details fold, under a plain heading. The parts are no longer folds of their own
 * (SPEC 2026-09-26 section 4 rule 4: no fold inside a fold); the print stylesheet still opens the
 * one Details fold, so the paper record keeps its full detail.
 */
function Section({ title, children }) {
  if (!children) return null;
  return (
    <MDBox mt={3} pt={2} sx={{ borderTop: `1px solid ${PAL.rule}` }}>
      {title ? (
        <MDTypography component="h3" sx={{ ...TYPE.body, fontWeight: 600, color: PAL.ink, mb: 1 }}>
          {title}
        </MDTypography>
      ) : null}
      {children}
    </MDBox>
  );
}

/** The one primary button on the card: accent fill, white text, 600, 36 px tall (SPEC rule 6). */
const PRIMARY = { textTransform: "none", ...TYPE.body, fontWeight: 600, minHeight: 36, height: 36,
  px: 2, borderRadius: "4px", boxShadow: "none", backgroundColor: PAL.accent, color: PAL.onFill,
  "&:hover": { backgroundColor: PAL.accent, boxShadow: "none" },
  "&.Mui-disabled": { backgroundColor: PAL.fillMuted, color: PAL.ink3 } };
/** A secondary button: white with a 1 px grey border. */
const SECONDARY = { textTransform: "none", ...TYPE.body, fontWeight: 400, minHeight: 36, height: 36,
  px: 2, borderRadius: "4px", boxShadow: "none", backgroundColor: PAL.surface, color: PAL.ink,
  border: `1px solid ${PAL.ink3}`, "&:hover": { backgroundColor: PAL.fillMuted } };

/**
 * The words naming which stimulator a card answers for, from the sense-to-control wiring (the PI,
 * 2026-10-08): "Right stimulator · contralateral sensing, from the left band". Null with no wiring.
 */
export function stimulatorLine(stimulator) {
  if (!stimulator) return null;
  const { stim, source, kind } = stimulator;
  if (kind === "contralateral") return `${stim} stimulator · contralateral sensing, from the ${source.toLowerCase()} band`;
  if (kind === "no_band") return `${stim} stimulator · driven by a ${source.toLowerCase()} band`;
  return `${stim} stimulator · ipsilateral sensing`;
}

/** A stimulator the wiring drives from a side with no band chosen: not checked, said in one card. */
export function UncheckedStimulatorCard({ stimulator }) {
  return (
    <Card className="cl-decision-card" data-testid={`decision-unchecked-${stimulator.stim}`}
      sx={{ width: "100%", backgroundColor: PAL.surface, border: `1px solid ${PAL.rule}`,
        borderRadius: "6px", boxShadow: "none" }}>
      <MDBox p={3}>
        <MDTypography sx={{ ...TYPE.body, fontWeight: 600, color: PAL.ink }}>{stimulatorLine(stimulator)}</MDTypography>
        <MDTypography component="h2" sx={{ ...TYPE.answer, ...WRAP.balance, color: STATE.notChecked.ink, mt: 0.5 }}>
          <span aria-hidden="true" style={{ marginRight: 8 }}>{STATE.notChecked.glyph}</span>
          {`Not checked: no band chosen on the ${stimulator.source.toLowerCase()}`}
        </MDTypography>
        <MDTypography sx={{ ...TYPE.lead, color: PAL.ink, mt: 1 }}>
          Nothing here is permission to program.
        </MDTypography>
      </MDBox>
    </Card>
  );
}

export default function DecisionCard({ participantUid, bandCandidate, summary, deploymentReport,
                                       chosenBand, bandRecord, cutpoint, mode, onMode, onRecompute,
                                       stimulator = null }) {
  const bc = bandCandidate || {};
  const rep = repOf(deploymentReport);
  const loading = !!(deploymentReport && deploymentReport.loading);
  // A report computed for a band other than the chosen one reaches this card with no data and this
  // field set (`withheldIfOtherBand`): the card names both bands and gives no verdict at all.
  const mismatch = deploymentReport && deploymentReport.bandMismatch;
  const reportErr = mismatch ? null : deploymentReport && deploymentReport.err;
  const sm = (summary && summary.data) || null;
  const status = mismatch
    ? { key: "other_band", ink: PAL.warnText, glyph: STATE.caution.glyph,
      headline: `Recompute: the analysis shown is for ${mismatch.computedFor}`,
      sub: `The chosen ${mismatch.what || "band"} is ${mismatch.chosen}. Nothing on this page `
        + "describes it until the analysis is recomputed." }
    : decisionStatus(rep);
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

  const eyebrow = [bc.contact_label || bc.contact || null,
    bc.center_freq_hz != null ? `${fmtHz(bc.center_freq_hz)} Hz` : null,
    bc.hemisphere ? `${String(bc.hemisphere).toLowerCase()} side` : null,
    pain && pain.label ? `pain score ${pain.label}` : null].filter(Boolean).join(" · ");
  const refused = status.key === "refused";

  return (
    <Card className="cl-decision-card" sx={{ width: "100%", backgroundColor: PAL.surface,
      border: `1px solid ${PAL.rule}`, ...decisionBar(refused), borderRadius: "6px", boxShadow: "none" }}>
      <MDBox p={3}>
        <StaleNotice inputsStale={actions.inputsStale} computedAt={actions.computedAt}
          staleWhy={actions.staleWhy} />

        {stimulator ? (
          <MDTypography data-testid="decision-stimulator" sx={{ ...TYPE.body, fontWeight: 600, color: PAL.ink }}>
            {stimulatorLine(stimulator)}
          </MDTypography>
        ) : null}
        {eyebrow ? (
          <MDTypography sx={{ ...TYPE.body, color: PAL.ink2 }}>{eyebrow}</MDTypography>
        ) : null}
        <MDTypography component="h2" sx={{ ...TYPE.answer, ...WRAP.balance, color: status.ink, mt: 0.5 }}>
          {loading ? "Evaluating the device rules and the evidence…" : (
            <>
              <span aria-hidden="true" style={{ marginRight: 8 }}>{status.glyph}</span>
              {status.headline}
            </>
          )}
        </MDTypography>
        {!loading && status.sub ? (
          <MDTypography sx={{ ...TYPE.lead, color: PAL.ink, mt: 1 }}>{status.sub}</MDTypography>
        ) : null}
        {reportErr ? (
          <MDTypography sx={{ ...TYPE.body, color: PAL.ink2, mt: 1 }}>
            {`The device rule table is unavailable: ${reportErr}`}
          </MDTypography>
        ) : null}

        {mismatch && onRecompute ? (
          <MDButton size="small" variant="contained" onClick={onRecompute} disabled={loading} sx={{ ...PRIMARY, mt: 2 }}>
            {`Recompute for ${mismatch.chosen}`}
          </MDButton>
        ) : null}

        {!loading ? (
          <>
            <Bullets items={red} cls="cl-bullets-red" ink={PAL.failText} glyph={STATE.refused.glyph}
              label="Why the device refuses" />
            <Bullets items={yellow} cls="cl-bullets-yellow" ink={PAL.warnText} glyph={STATE.caution.glyph}
              label="Evidence that was not evaluated" />
            {/* The module's blocker sentences, verbatim, in ink with ✕: the analysis's own reasons it
                could not go on (no thresholds placed, a step that failed), not the device refusing,
                and red is only for a device refusal or a value above the safe ceiling (the PI,
                2026-09-26, TASTE_AUDIT.md D14). In the open since the Details fold stays closed
                (the PI, 2026-10-08), so the reason is never one click away. */}
            {blockers.length ? (
              <MDBox className="cl-blockers" mt={1}>
                {blockers.map((b) => (
                  <MDTypography key={b} data-blocker="" sx={{ ...TYPE.body, fontWeight: 600, display: "block", color: STATE.blocked.ink, py: 0.25 }}>
                    <span aria-hidden="true" style={{ marginRight: 6 }}>{STATE.blocked.glyph}</span>
                    {b}
                  </MDTypography>
                ))}
              </MDBox>
            ) : null}
          </>
        ) : null}

        <MDBox mt={3} pt={2} sx={{ borderTop: `1px solid ${PAL.rule}` }}>
          <MDTypography component="h3" sx={{ ...TYPE.lead, fontWeight: 600, color: PAL.ink, mb: 1 }}>
            Values to enter on the A610
          </MDTypography>
          {/* Keyed on the band, so a read-back tick given for one band never survives a change of band. */}
          <ParameterTable key={`${bc.contact || ""}|${bc.center_freq_hz ?? ""}|${bc.bandwidth_hz ?? ""}`}
            report={mismatch ? { data: null } : deploymentReport} mode={mode} onMode={onMode} />
        </MDBox>

        <MDBox className="cl-signoff-actions" display="flex" gap={2} mt={3} flexWrap="wrap">
          <MDButton size="small" variant="contained" onClick={actions.printWithFigures}
            disabled={actions.capturing} sx={PRIMARY}>
            {actions.capturing ? "Capturing figures…" : "Sign and print"}
          </MDButton>
          <MDButton size="small" variant="outlined" onClick={actions.exportJson}
            disabled={actions.capturing || !actions.hasData} sx={SECONDARY}>
            Export JSON
          </MDButton>
        </MDBox>

        <MDBox className="cl-details" mt={3}>
          {/* Closed by default whatever the verdict (the PI, 2026-10-08: "have the details collapsed
              by default"); the red and caution bullets above already say why. Until then it opened
              by itself on any verdict but "allowed and supported". Keyed on the verdict, so a new
              answer starts closed again and a reader's own toggle survives every other re-render. */}
          <Fold key={status.key} show={detailsLabel} hide="Hide details">
            <WhatWouldChangeThis report={deploymentReport} bare />
            {/* The device rule check, every rule, here rather than in a card of its own (the PI,
                2026-10-08: "consolidate these"); its refusals are the red bullets above. */}
            <Section title="Device rule check, every rule">
              <DeviceRuleLedger report={deploymentReport} bare />
            </Section>
            <Section title="How each value was worked out and checked">
              <ParameterDetails report={deploymentReport} mode={mode} />
            </Section>
            <Section title="Sign-off record">
              <SignoffRecord bandCandidate={bandCandidate} summary={summary}
                deploymentReport={deploymentReport} chosenBand={chosenBand} bandRecord={bandRecord} />
            </Section>
            {bc.contact ? (
              <Section title="The band as chosen">
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
