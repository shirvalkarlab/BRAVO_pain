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
import { Card, Divider } from "@mui/material";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import PAL from "./palette";
import { unevaluableFor } from "./deployFormat";

/** The four state shapes, drawn small enough to sit on a text baseline. */
function RuleGlyph({ state, size = 13 }) {
  const s = size;
  const c = s / 2;
  if (state === "satisfied") {
    return (
      <svg width={s} height={s} viewBox="0 0 16 16" aria-label="satisfied" role="img">
        <circle cx="8" cy="8" r="7" fill={PAL.pass} />
        <path d="M4.5 8.3 L7 10.8 L11.5 5.5" stroke="#fff" strokeWidth="1.9" fill="none"
          strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }
  if (state === "violated") {
    return (
      <svg width={s} height={s} viewBox="0 0 16 16" aria-label="violated" role="img">
        <rect x="1" y="1" width="14" height="14" rx="1.5" fill={PAL.fail} />
        <path d="M5 5 L11 11 M11 5 L5 11" stroke="#fff" strokeWidth="1.9" strokeLinecap="round" />
      </svg>
    );
  }
  if (state === "unevaluable") {
    return (
      <svg width={s} height={s} viewBox="0 0 16 16" aria-label="cannot be evaluated" role="img">
        <rect x="1.2" y="1.2" width="13.6" height="13.6" rx="1.5" fill="none" stroke={PAL.warnText}
          strokeWidth="1.6" strokeDasharray="3 2" />
        <text x="8" y="12" textAnchor="middle" fontSize="10" fontWeight="700"
          fill={PAL.warnText}>?</text>
      </svg>
    );
  }
  if (state === "deferred") {
    return (
      <svg width={s} height={s} viewBox="0 0 16 16" aria-label="deferred duplicate" role="img">
        <rect x="1.2" y="1.2" width="13.6" height="13.6" rx="1.5" fill="none" stroke={PAL.deferred}
          strokeWidth="1.6" />
        <path d="M4.5 6.5 H11.5 M4.5 9.5 H11.5" stroke={PAL.deferred} strokeWidth="1.6"
          strokeLinecap="round" />
      </svg>
    );
  }
  // Advisory: a filled disc with no mark inside, so it reads as "noted" rather than as a verdict.
  return (
    <svg width={s} height={s} viewBox="0 0 16 16" aria-label="advisory" role="img">
      <circle cx={c ? 8 : 8} cy="8" r="6.6" fill="none" stroke={PAL.neutral} strokeWidth="1.6" />
      <circle cx="8" cy="8" r="2.4" fill={PAL.neutral} />
    </svg>
  );
}

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
    <MDBox py={0.5} sx={{ borderTop: "1px solid rgba(0,0,0,0.07)" }}>
      <MDBox display="flex" flexDirection="row" alignItems="flex-start" gap={0.9}>
        <MDBox flex="0 0 auto" mt={0.2}><RuleGlyph state={state} /></MDBox>
        <MDBox flex="1 1 auto">
          <MDTypography variant="caption" sx={{ fontSize: 11.5, color: "#2A2A2A" }}>
            <b style={{ fontFamily: PAL.mono, color: ink }}>{row.rule_id}</b>
            {"  "}{row.title || "untitled rule"}
            {row.page ? <i style={{ color: "#7A7A7A" }}>{`  (${row.page}`}
              {row.source ? `, ${row.source}` : ""}{")"}</i> : null}
          </MDTypography>
          {copy ? (
            <MDTypography variant="caption" sx={{ display: "block", fontSize: 11, color: ink }}>
              {copy}
            </MDTypography>
          ) : null}
          {row.observed ? (
            <MDTypography variant="caption" sx={{ display: "block", fontSize: 11,
              fontFamily: PAL.mono, color: "#4A4A4A", mt: 0.2 }}>
              {`observed: ${row.observed}`}
            </MDTypography>
          ) : null}
          {row.why ? (
            <>
              <MDTypography variant="caption" onClick={() => setOpen((o) => !o)}
                sx={{ fontSize: 10.5, color: PAL.accent, cursor: "pointer", display: "block",
                  mt: 0.2, "&:hover": { textDecoration: "underline" } }}>
                {open ? "Hide the rule's own wording" : "Read the rule's own wording"}
              </MDTypography>
              {open ? (
                <MDTypography variant="caption" sx={{ display: "block", fontSize: 11,
                  color: "#3A3A3A", mt: 0.3, pl: 1,
                  borderLeft: "2px solid rgba(0,0,0,0.12)" }}>
                  {row.why}
                  {row.deferral_reason ? <><br /><br />{row.deferral_reason}</> : null}
                </MDTypography>
              ) : null}
            </>
          ) : null}
        </MDBox>
        {actor ? (
          <MDBox flex="0 0 auto" pl={1} sx={{ maxWidth: 190, textAlign: "right" }}>
            <MDTypography variant="caption" sx={{ fontSize: 10, fontWeight: "bold",
              letterSpacing: 0.3, color: ink }}>
              {actor.toUpperCase()}
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
    <MDBox display="flex" flexDirection="row" alignItems="center" gap={0.8} mt={1.2}>
      <RuleGlyph state={state} size={14} />
      <MDTypography variant="caption" sx={{ fontSize: 11, fontWeight: "bold", letterSpacing: 0.4,
        color: "#4A4A4A" }}>
        {`${title.toUpperCase()} \u00B7 ${count}`}
      </MDTypography>
      {note ? (
        <MDTypography variant="caption" sx={{ fontSize: 10.5, color: "#8A8A8A" }}>
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
          sx={{ fontSize: 10.5, color: PAL.accent, cursor: "pointer", display: "block", ml: 2.8,
            "&:hover": { textDecoration: "underline" } }}>
          {open ? "Collapse these rules"
            : `Show these ${rows.length} rules (${rows.map((r) => r.rule_id).join(", ")})`}
        </MDTypography>
      ) : null}
      {open ? rows.map((r) => (
        <RuleRow key={`cg-${r.rule_id}`} row={r} state={state} ink="#5A5A5A" copy={null}
          actor={null} />
      )) : null}
    </MDBox>
  );
}

export default function DeviceRuleLedger({ report }) {
  const { data, loading, err } = report || { data: null, loading: false, err: null };

  if (loading) {
    return (
      <Card><MDBox p={2}>
        <MDTypography variant="button">Running the encoded Percept rule table…</MDTypography>
      </MDBox></Card>
    );
  }
  if (!data || !data.eligibility) {
    return (
      <Card><MDBox p={2}>
        <MDTypography variant="h6" sx={{ fontSize: 15 }}>Device rule ledger</MDTypography>
        <MDTypography variant="caption" sx={{ display: "block", fontSize: 11.5,
          color: PAL.neutral }}>
          {`The rule table has not been run for this configuration${err ? ` (${err})` : ""}. `}
          Eligibility is evaluated for one channel and one centre frequency rather than for a
          participant, so a candidate configuration has to be chosen before these rules mean
          anything.
        </MDTypography>
      </MDBox></Card>
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
  // Any advisory kind this component has not been taught about. Collecting the remainder rather than
  // assuming four kinds means a new kind added upstream appears on the page as an unclassified row
  // instead of vanishing, which is the failure the previous single-kind filter had.
  const KNOWN = ["advisory_failed", "recorded_value", "advisory_no_predicate",
    "advisory_not_determinable"];
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

  return (
    <Card>
      <MDBox p={2}>
        <MDTypography variant="h6" sx={{ fontSize: 15 }}>Device rule ledger</MDTypography>
        <MDTypography variant="caption" sx={{ display: "block", fontSize: 11.5, color: "#4A4A4A" }}>
          {el.summary || "no summary reported"}
        </MDTypography>
        <MDTypography variant="caption" sx={{ display: "block", fontSize: 10.5, color: "#8A8A8A",
          mt: 0.3 }}>
          Each row carries the rule identifier and the document page it was read from, so a finding
          can be checked against the source rather than taken on trust. The label on the right of a
          row names who can resolve it.
        </MDTypography>

        <Divider sx={{ my: 1 }} />

        {/* VIOLATED. Drawn first because a violated rule is the only state that no further
            measurement or lookup can clear. */}
        <BucketHead state="violated" title="Violated" count={failures.length}
          note={failures.length === 0 ? "no rule is violated" : null} />
        {failures.map((f) => {
          const u = unevaluableFor(f.kind);
          return (
            <RuleRow key={`f-${f.rule_id}`} row={f} state="violated" ink={PAL.fail}
              copy={u.copy} actor={u.actor} />
          );
        })}

        {/* CANNOT BE EVALUATED, subdivided by kind so the actor is legible from position. */}
        <BucketHead state="unevaluable" title="Cannot be evaluated" count={unknowns.length}
          note={unknowns.length === 0 ? "every rule could be evaluated"
            : "these block: a rule that cannot be evaluated is not a rule that passed"} />
        {unknownKinds.map((g) => {
          const u = unevaluableFor(g.kind);
          return (
            <MDBox key={`uk-${g.kind}`} mt={0.6} ml={0.4}>
              <MDTypography variant="caption" sx={{ display: "block", fontSize: 10.5,
                fontWeight: "bold", color: PAL.warnText }}>
                {`${g.rows.length} ${g.rows.length === 1 ? "rule" : "rules"} \u2014 ${u.copy}`}
              </MDTypography>
              {g.rows.map((r) => (
                <RuleRow key={`u-${r.rule_id}`} row={r} state="unevaluable" ink={PAL.warnText}
                  copy={null} actor={u.actor} />
              ))}
            </MDBox>
          );
        })}

        {/* DEFERRED DUPLICATE. The finding is real and is counted once, against the rule that owns
            the narrower condition. Rendering it as a separate state stops a reader either
            double-counting it as a second failure or concluding the rule was never checked. */}
        <BucketHead state="deferred" title="Deferred to another rule" count={deferred.length}
          note={deferred.length === 0 ? "no rule deferred its finding"
            : "the same finding as another rule's, counted once"} />
        {deferred.map((d) => (
          <RuleRow key={`d-${d.rule_id}`} row={d} state="deferred" ink={PAL.deferred}
            copy={`This finding is owned by ${d.deferred_to || "another rule"} and is counted `
              + `there rather than here${d.counts_toward_verdict === false
                ? ", so it does not count towards the verdict twice" : ""}.`}
            actor={null} />
        ))}

        {/* ADVISORY SHORTFALLS: a predicate that returned false on a rule the documents phrase as a
            recommendation rather than a requirement. These do not block, and softening a rule must
            not make it invisible. */}
        <BucketHead state="advisory" title="Advisory shortfalls" count={advFailed.length}
          note="reported, not blocking" />
        {advFailed.map((a) => (
          <RuleRow key={`af-${a.rule_id}`} row={a} state="advisory" ink={PAL.warnText}
            copy="This rule's condition is not satisfied. The documents phrase it as a
              recommendation rather than a requirement, so it does not block."
            actor={null} />
        ))}

        {/* PINNED RECORDED VALUES: rules that PASSED and whose passing value the module pinned
            because the meaning of the rest of the report depends on it. Pinned open rather than
            collapsed with the other satisfied rules, and labelled so a reader understands it is
            here because the VALUE matters and not because the pass does. */}
        <BucketHead state="satisfied" title="Pinned values" count={recorded.length}
          note="satisfied, and shown because the recorded value is load-bearing" />
        {recorded.map((a) => (
          <RuleRow key={`rv-${a.rule_id}`} row={a} state="satisfied" ink={PAL.pass}
            copy="Pinned because the recorded VALUE matters to how the rest of this report reads,
              not because the rule passed."
            actor={null} />
        ))}

        {/* The two informational advisory kinds. Collapsed by default because there are twenty-two
            of them on RCS08 and each carries a paragraph, and expanding them by default would bury
            the buckets above. The counts and the rule identifiers are visible while collapsed, so
            nothing is hidden — only folded. */}
        <CollapsedGroup rows={advNotDeterminable} state="advisory"
          title="Advisory, could not be determined"
          note="the inputs for these advisory rules were absent" />
        <CollapsedGroup rows={advNoPredicate} state="advisory"
          title="Advisory, no machine check exists"
          note="recorded for the reader; the documents state no numeric condition" />
        {advOther.length > 0 ? (
          <CollapsedGroup rows={advOther} state="advisory" title="Advisory, unclassified kind"
            note="this interface does not recognise these kinds; report them" />
        ) : null}

        {/* SATISFIED, collapsed to a count. */}
        <BucketHead state="satisfied" title="Satisfied and not otherwise reported"
          count={satisfied == null ? "not derivable" : satisfied}
          note={el.checked != null
            ? `derived by subtraction from the ${el.checked} rules checked, not enumerated in the `
              + "payload"
            : null} />
      </MDBox>
    </Card>
  );
}
