/**
 * The device rule ledger: every encoded Percept rule outcome, in the bucket its own `kind` puts it
 * in, with the actor who can resolve it named on the row.
 *
 * WHAT THIS REPLACES, AND WHY IT MATTERS CLINICALLY. The panel this supersedes rendered three of the
 * nine outcome kinds the rule evaluator produces, and it printed every row of the unevaluable bucket
 * with one fixed sentence saying the value had not been read off the programmer. For RCS08 that
 * sentence is true of exactly one of four unevaluable rules. The other three could not be evaluated
 * because the fields they read were never routed into the module, which is a defect in how the
 * analysis is wired and cannot be resolved at a programming visit — so the old copy sent a clinician
 * to the A610 to look for three values that are not on it. The copy is therefore keyed on the
 * payload's own `kind` here, and each row names its actor.
 *
 * WHY THE ADVISORY BUCKET IS SPLIT FOUR WAYS. The payload's `eligibility.advisories` list mixes four
 * kinds that mean different things: a predicate that returned false (`advisory_failed`), a rule
 * recorded for the reader with no predicate to check (`advisory_no_predicate`), a rule whose inputs
 * were absent (`advisory_not_determinable`), and a rule that PASSED and whose passing value the
 * module pinned because the meaning of the rest of the report depends on it (`recorded_value`). The
 * previous filter admitted only `advisory_failed`, so for RCS08 it discarded 24 of 26 rows including
 * both pinned values — and the pinned values are precisely the ones a reader must see, because one
 * of them records the programming mode in force, which is what makes the Adaptive workflow reachable
 * at all.
 *
 * WHY EVERY BLOCK IS DRAWN EVEN WHEN IT IS EMPTY. A bucket that disappears when it has no rows
 * cannot be distinguished from a bucket that was never rendered. Drawing the heading with a zero
 * count tells a reader that the state exists and is currently unoccupied, which is the same reason
 * the state tracks draw their unlit cells.
 *
 * WHY THE GLYPHS HAVE DISTINCT SHAPES AS WELL AS DISTINCT INKS. Around eight per cent of men cannot
 * separate the decision inks by hue, and this page prints. Each state carries a shape that reads
 * correctly with no colour at all: a filled disc with a tick is satisfied, a filled square with a
 * cross is violated, an open dashed square with a question mark could not be evaluated, and an open
 * square with an equals sign is a finding already counted against another rule. The open outline for
 * the unevaluable state is deliberate — emptiness reads as "nothing has been established here",
 * which is what the state means.
 */
import { useState } from "react";
import { Card } from "@mui/material";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import PAL from "./palette";
import { TYPE, WRAP, CARD, STATE } from "assets/theme/base/tokens";
import Fold from "./Fold";
import { refusalFor, unevaluableFor } from "./deployFormat";

/**
 * The state marks, as the shared glyphs (SPEC 2026-09-26 section 2.3): ✕ refuses (red), ○ could not
 * check (grey), ✓ allowed (ink), = counted under another rule, · a recommendation. Each is a SHAPE,
 * so the table reads correctly with no colour at all.
 */
const RULE_MARK = {
  violated: { glyph: STATE.refused.glyph, ink: STATE.refused.ink, label: "refuses" },
  unevaluable: { glyph: STATE.notChecked.glyph, ink: STATE.notChecked.ink, label: "could not check" },
  satisfied: { glyph: STATE.pass.glyph, ink: STATE.pass.ink, label: "allowed" },
  deferred: { glyph: "=", ink: PAL.ink3, label: "counted under another rule" },
  advisory: { glyph: "·", ink: PAL.ink3, label: "recommended, not required" },
};
function RuleGlyph({ state }) {
  const m = RULE_MARK[state] || RULE_MARK.advisory;
  return (
    <span role="img" aria-label={m.label} style={{ ...TYPE.body, fontWeight: 600, color: m.ink,
      display: "inline-block", width: "1.2em", textAlign: "center" }}>{m.glyph}</span>
  );
}

/** "clinician, at the A610" -> "Clinician, at the A610": sentence case, never capitals. */
const sentenceCase = (t) => (t ? String(t).charAt(0).toUpperCase() + String(t).slice(1) : t);

/**
 * One rule row. `actor` is rendered as a right-aligned label on the row rather than folded into the
 * explanatory sentence, so a reader can run their eye down the right-hand edge and see at once how
 * much of the ledger is theirs to fix. For RCS08 that column shows two rows belonging to the
 * clinician and two belonging to the analysis, which is the distinction the previous single sentence
 * erased.
 */
function RuleRow({ row, state, ink, copy, actor }) {
  const [open, setOpen] = useState(false);
  if (!row) return null;
  return (
    <MDBox py={1} sx={{ borderTop: `1px solid ${PAL.rule}` }}>
      <MDBox display="flex" flexDirection="row" alignItems="flex-start" gap={1}>
        <MDBox flex="0 0 auto"><RuleGlyph state={state} /></MDBox>
        <MDBox flex="1 1 auto">
          <MDTypography variant="caption" sx={{ ...TYPE.body, color: PAL.ink }}>
            {ink === PAL.warnText ? <span aria-hidden="true" style={{ marginRight: 4, color: ink }}>▲</span> : null}
            <b style={{ fontWeight: 600, color: ink }}>{row.rule_id}</b>
            {"  "}{row.title || "untitled rule"}
            {row.page ? <i style={{ color: PAL.ink3 }}>{`  (${row.page}`}
              {row.source ? `, ${row.source}` : ""}{")"}</i> : null}
          </MDTypography>
          {copy ? (
            <MDTypography variant="caption" sx={{ ...TYPE.body, display: "block", color: ink }}>
              {copy}
            </MDTypography>
          ) : null}
          {row.observed ? (
            <MDTypography variant="caption" sx={{ display: "block", fontSize: PAL.fs.body,
              color: PAL.ink2, mt: 0.25 }}>
              {`observed: ${row.observed}`}
            </MDTypography>
          ) : null}
          {/* The server's note on a row it kept although another rule owns the same finding (the
              owner could not be evaluated, or the two disagreed): why it still counts here. */}
          {row.deferral_note ? (
            <MDTypography variant="caption" data-deferral-note="" sx={{ ...TYPE.body, display: "block",
              color: PAL.ink2, mt: 0.25 }}>
              {row.deferral_note}
            </MDTypography>
          ) : null}
          {row.why ? (
            <>
              <MDTypography variant="caption" onClick={() => setOpen((o) => !o)}
                sx={{ fontSize: PAL.fs.body, color: PAL.accent, cursor: "pointer", display: "block",
                  mt: 0.2, "&:hover": { textDecoration: "underline" } }}>
                {open ? "Hide the rule's own wording" : "Read the rule's own wording"}
              </MDTypography>
              {open ? (
                <MDTypography variant="caption" sx={{ display: "block", fontSize: PAL.fs.body,
                  color: PAL.ink2, mt: 0.3, pl: 1,
                  borderLeft: `2px solid ${PAL.rule}` }}>
                  {row.why}
                  {row.deferral_reason ? <><br /><br />{row.deferral_reason}</> : null}
                </MDTypography>
              ) : null}
            </>
          ) : null}
        </MDBox>
        {actor ? (
          <MDBox flex="0 0 auto" pl={1} sx={{ maxWidth: 200, textAlign: "right" }}>
            <MDTypography variant="caption" sx={{ ...TYPE.body, fontWeight: 600, color: PAL.ink2 }}>
              {sentenceCase(actor)}
            </MDTypography>
          </MDBox>
        ) : null}
      </MDBox>
    </MDBox>
  );
}

/** A bucket heading that is drawn whether or not the bucket has rows in it. */
function BucketHead({ state, title, count, note }) {
  return (
    <MDBox display="flex" flexDirection="row" alignItems="baseline" gap={1} mt={2} flexWrap="wrap">
      <RuleGlyph state={state} />
      <MDTypography component="h3" variant="caption" sx={{ ...TYPE.body, fontWeight: 600, color: PAL.ink }}>
        {`${title} \u00B7 ${count}`}
      </MDTypography>
      {note ? (
        <MDTypography variant="caption" sx={{ ...TYPE.body, color: PAL.ink3 }}>
          {note}
        </MDTypography>
      ) : null}
    </MDBox>
  );
}

/** A collapsed group for the two informational advisory kinds, which are numerous and long. */
function CollapsedGroup({ rows, state, title, note }) {
  const [open, setOpen] = useState(false);
  return (
    <MDBox mt={0.8}>
      <BucketHead state={state} title={title} count={rows.length} note={note} />
      {rows.length > 0 ? (
        <MDTypography variant="caption" onClick={() => setOpen((o) => !o)}
          sx={{ ...TYPE.body, color: PAL.accent, cursor: "pointer", display: "block", ml: 3,
            "&:hover": { textDecoration: "underline" } }}>
          {open ? "Collapse these rules"
            : `Show these ${rows.length} rules (${rows.map((r) => r.rule_id).join(", ")})`}
        </MDTypography>
      ) : null}
      {open ? rows.map((r) => (
        <RuleRow key={`cg-${r.rule_id}`} row={r} state={state} ink={PAL.ink3} copy={null}
          actor={null} />
      )) : null}
    </MDBox>
  );
}

export default function DeviceRuleLedger({ report }) {
  const { data, loading, err } = report || { data: null, loading: false, err: null };

  if (loading) {
    return (
      <Card sx={{ ...CARD, p: 3 }}>
        <MDTypography component="h2" sx={{ ...TYPE.title, ...WRAP.balance, color: PAL.ink }}>Device rule check</MDTypography>
        <MDTypography sx={{ ...TYPE.lead, color: PAL.ink2, mt: 1 }}>Checking the device's rules…</MDTypography>
      </Card>
    );
  }
  if (!data || !data.eligibility) {
    return (
      <Card sx={{ ...CARD, p: 3 }}>
        <MDTypography component="h2" sx={{ ...TYPE.title, ...WRAP.balance, color: PAL.ink }}>Device rule check</MDTypography>
        <MDTypography sx={{ ...TYPE.lead, color: PAL.ink2, mt: 1, maxWidth: "68ch" }}>
          {`The device's rules have not been checked for this configuration${err ? ` (${err})` : ""}. `}
          They are checked for one sensing contact pair at one band, not for a participant, so a band
          has to be chosen before these rules mean anything.
        </MDTypography>
      </Card>
    );
  }

  const el = data.eligibility;
  const failures = el.failures || [];
  const unknowns = el.unknowns || [];
  const deferred = el.deferred || [];
  const advisories = el.advisories || [];

  const byKind = (k) => advisories.filter((a) => a && a.kind === k);
  const advFailed = byKind("advisory_failed");
  const recorded = byKind("recorded_value");
  const advNoPredicate = byKind("advisory_no_predicate");
  const advNotDeterminable = byKind("advisory_not_determinable");
  // An advisory whose own check raised: a defect in the rule table, named as one.
  const advError = byKind("predicate_error");
  // Any advisory kind this component has not been taught about. Collecting the remainder rather than
  // assuming four kinds means a new kind added upstream appears on the page as an unclassified row
  // instead of vanishing, which is the failure the previous single-kind filter had.
  const KNOWN = ["advisory_failed", "recorded_value", "advisory_no_predicate",
    "advisory_not_determinable", "predicate_error"];
  const advOther = advisories.filter((a) => a && KNOWN.indexOf(a.kind) < 0);

  // The satisfied rules are not enumerated in the payload; they are the rules that passed without
  // being pinned for any reason. The count is therefore derived by subtraction from `checked`, and
  // it is labelled as derived so a reader does not take it for a list they could go and read.
  const reported = failures.length + unknowns.length + deferred.length + advisories.length;
  const satisfied = el.checked != null ? Math.max(0, el.checked - reported) : null;

  // Group the unevaluable rules by kind, because position is a stronger cue than wording for a
  // reader who is skimming, and because the actor is a property of the kind.
  const unknownKinds = [];
  unknowns.forEach((u) => {
    const k = u.kind || "unclassified";
    let g = unknownKinds.find((x) => x.kind === k);
    if (!g) { g = { kind: k, rows: [] }; unknownKinds.push(g); }
    g.rows.push(u);
  });

  // THE FIVE COUNTS, always in the open, and made to ADD UP to the total checked (the PI,
  // 2026-09-26: Refuses + Could not check + Allowed had stopped summing to the total once any
  // deferred or advisory row existed, because those lived only inside the closed fold below).
  // "Allowed" means only rules that were satisfied with nothing to report; a rule that passed but
  // was pinned for its recorded value gets its own "Pinned" count rather than being folded into
  // Allowed; every remaining non-blocking row (deferred, a recommendation not met, one with no
  // automatic check, one whose inputs were absent, or an unrecognised kind) is "Notes". These are
  // the same rows the fold below lists one by one; this is only their count, named once each.
  const nAllowed = satisfied;
  const nPinned = recorded.length;
  const nNotes = deferred.length + advFailed.length + advNotDeterminable.length
    + advNoPredicate.length + advError.length + advOther.length;

  return (
    <Card sx={{ ...CARD, p: 3 }}>
      <MDTypography component="h2" sx={{ ...TYPE.title, ...WRAP.balance, color: PAL.ink }}>Device rule check</MDTypography>
      <MDTypography data-testid="rule-counts" sx={{ ...TYPE.lead, color: PAL.ink, mt: 1 }}>
        <span style={{ color: failures.length ? PAL.failText : PAL.ink }}>
          <span aria-hidden="true" style={{ marginRight: 4 }}>{STATE.refused.glyph}</span>
          {`Refuses (${failures.length})`}
        </span>
        {" · "}
        <span style={{ color: PAL.ink3 }}>
          <span aria-hidden="true" style={{ marginRight: 4 }}>{STATE.notChecked.glyph}</span>
          {`Could not check (${unknowns.length})`}
        </span>
        {" · "}
        <span>
          <span aria-hidden="true" style={{ marginRight: 4 }}>{STATE.pass.glyph}</span>
          {`Allowed (${nAllowed == null ? "not derivable" : nAllowed})`}
        </span>
        {" · "}
        <span style={{ color: PAL.ink3 }}>
          {`Passed, value shown (${nPinned})`}
        </span>
        {" · "}
        <span style={{ color: PAL.ink3 }}>
          {`Notes, not blocking (${nNotes})`}
        </span>
        {el.checked != null ? <span style={{ color: PAL.ink3 }}>{` of ${el.checked} rules checked`}</span> : null}
      </MDTypography>
      <MDTypography sx={{ ...TYPE.body, color: PAL.ink2, mt: 1, maxWidth: "68ch" }}>
        {el.summary || "no summary reported"}
      </MDTypography>

      {/* REFUSED rows stay in the open, in red with ✕ and in the rule table's own words: a refusal
          is the one state no further measurement or lookup can clear, and it is never folded. */}
      {failures.length > 0 ? (
        <MDBox mt={1}>
          <BucketHead state="violated" title="Refuses" count={failures.length} note={null} />
          {failures.map((f) => {
            const u = !f.kind || f.kind === "failed" ? refusalFor(f) : unevaluableFor(f.kind);
            return (
              <RuleRow key={`f-${f.rule_id}`} row={f} state="violated" ink={PAL.failText}
                copy={u.copy} actor={u.actor} />
            );
          })}
        </MDBox>
      ) : null}

      {/* COULD NOT CHECK, subdivided by kind so who can resolve it is legible from position. These
          still block: a rule that could not be checked is not a rule that passed. Open, like the
          refusals. */}
      {unknowns.length > 0 ? (
        <MDBox mt={1}>
          <BucketHead state="unevaluable" title="Could not check" count={unknowns.length}
            note="these still block: a rule that could not be checked is not a rule that passed" />
          {unknownKinds.map((g) => {
            const u = unevaluableFor(g.kind);
            return (
              <MDBox key={`uk-${g.kind}`} mt={1}>
                <MDTypography variant="caption" sx={{ ...TYPE.body, display: "block", color: PAL.ink2 }}>
                  {`${g.rows.length} ${g.rows.length === 1 ? "rule" : "rules"}: ${u.copy}`}
                </MDTypography>
                {g.rows.map((r) => (
                  <RuleRow key={`u-${r.rule_id}`} row={r} state="unevaluable" ink={PAL.ink2}
                    copy={null} actor={u.actor} />
                ))}
              </MDBox>
            );
          })}
        </MDBox>
      ) : null}

      <Fold show={`Notes and pinned values, not blocking (${nNotes} notes: counted under another rule, `
        + `recommendations; ${nPinned} pinned: passed, shown because the value matters)`}
        hide="Hide the notes" mt={2}>
        <MDTypography sx={{ ...TYPE.body, color: PAL.ink2, maxWidth: "68ch" }}>
          Each row carries the rule identifier and the document page it was read from, so a finding
          can be checked against the source rather than taken on trust. The label on the right of a
          row names who can resolve it.
        </MDTypography>

        {failures.length === 0 ? (
          <BucketHead state="violated" title="Refuses" count={0} note="the device refuses nothing" />
        ) : null}
        {unknowns.length === 0 ? (
          <BucketHead state="unevaluable" title="Could not check" count={0}
            note="every rule could be checked" />
        ) : null}

        {/* COUNTED UNDER ANOTHER RULE. The finding is real and is counted once, against the rule
            that owns the narrower condition, so a reader neither counts it twice nor concludes the
            rule was never checked. */}
        <BucketHead state="deferred" title="Counted under another rule" count={deferred.length}
          note={deferred.length === 0 ? "no rule passed its finding to another"
            : "the same finding as another rule's, counted once"} />
        {deferred.map((d) => (
          <RuleRow key={`d-${d.rule_id}`} row={d} state="deferred" ink={PAL.ink2}
            copy={`This finding is owned by ${d.deferred_to || "another rule"} and is counted `
              + `there rather than here${d.counts_toward_verdict === false
                ? ", so it does not count towards the verdict twice" : ""}.`}
            actor={null} />
        ))}

        {/* RECOMMENDATIONS NOT MET: rules the documents phrase as a recommendation rather than a
            requirement. They do not block, and softening a rule must not make it invisible. */}
        <BucketHead state="advisory" title="Recommended, not required: not met" count={advFailed.length}
          note="reported, not blocking" />
        {advFailed.map((a) => (
          <RuleRow key={`af-${a.rule_id}`} row={a} state="advisory" ink={PAL.warnText}
            copy="This rule's condition is not met. The documents phrase it as a recommendation
              rather than a requirement, so it does not block."
            actor={null} />
        ))}

        {/* VALUES THAT MATTER: rules that PASSED and whose value the module kept on show because
            the rest of the report reads differently depending on it. */}
        <BucketHead state="satisfied" title="Allowed, and shown because the value matters" count={recorded.length}
          note="the rule passed; the recorded value is what the rest of this report depends on" />
        {recorded.map((a) => (
          <RuleRow key={`rv-${a.rule_id}`} row={a} state="satisfied" ink={PAL.ink}
            copy="Shown because the recorded VALUE matters to how the rest of this report reads,
              not because the rule passed."
            actor={null} />
        ))}

        {/* The two informational kinds, numerous and long: the count and the rule identifiers are
            in the open inside these notes, the rows one click further. */}
        <CollapsedGroup rows={advNotDeterminable} state="advisory"
          title="Recommended, not required: could not be checked"
          note="the inputs for these rules were absent" />
        <CollapsedGroup rows={advNoPredicate} state="advisory"
          title="Recommended, not required: no automatic check exists"
          note="recorded for the reader; the documents state no number to check against" />
        {advError.length > 0 ? (
          <CollapsedGroup rows={advError} state="advisory"
            title="Recommended, not required: the check raised an error"
            note="a defect in the rule table, not a property of this configuration; it does not block" />
        ) : null}
        {advOther.length > 0 ? (
          <CollapsedGroup rows={advOther} state="advisory" title="Recommended, not required: unrecognised kind"
            note="this page does not recognise these kinds; report them" />
        ) : null}

        {/* ALLOWED and not otherwise reported, as a count. */}
        <BucketHead state="satisfied" title="Allowed and not otherwise reported"
          count={satisfied == null ? "not derivable" : satisfied}
          note={el.checked != null
            ? `counted by the server from the ${el.checked} rules checked, not listed one by one`
            : null} />
      </Fold>
    </Card>
  );
}
