/**
 * What would change this answer, ranked, with the actor named on every row.
 *
 * WHY THIS BAND EXISTS AND WHY IT SITS SECOND. A verdict compresses findings of very different
 * severity into one word, and the components are what determine what a reader does next. On RCS08
 * the verdict "blocked" is the sum of one violated sign rule, four rules that could not be
 * evaluated, and a coherence answer that came back negative for a subtle reason. Those are three
 * different people doing three different things on three different timescales: a violated sign rule
 * means this band is finished and a different one is needed; a rule whose value lives only on the
 * programmer is a thirty-second lookup by the clinician standing in front of the device; a rule
 * whose inputs were never routed into the module is a data-wiring change that cannot be resolved at
 * a programming visit at all. The interface used to present all of that as one undifferentiated
 * "not ready", leaving the reader to reconstruct the parts by reading down the page.
 *
 * This band is the only part of the page that speaks to the twenty minutes a clinician is actually
 * standing at the programmer, which is why it comes before the detail rather than after it.
 *
 * WHAT IT DOES NOT DO. It does not invent remedies. Every sentence of substance on a row is the
 * module's own text for that rule or that finding; what this component contributes is the ordering,
 * the actor, and a statement of which part of the page each item would unblock. Where the module
 * says nothing about how to resolve something, this band says that rather than filling the gap.
 */
import { useState } from "react";
import { Card } from "@mui/material";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import PAL from "./palette";
import { parseSignPattern, unevaluableFor } from "./deployFormat";
import { coherenceReading } from "./stateTracks";

/**
 * Build the ranked list from the payload.
 *
 * The ordering is by how much of the verdict an item clears, which is not the same as by severity.
 * A violated rule comes first because nothing else on the list can clear it and because it is the
 * only state that no measurement or lookup will change. Rules that could not be evaluated come next
 * and are ordered so that the ones a clinician can resolve at the device precede the ones that
 * cannot be resolved there, because that is the ordering that matters to someone holding the
 * programmer. The evidence findings come after the device findings, because a device refusal makes
 * the evidence question moot for today whatever its answer.
 */
function buildItems(data) {
  if (!data) return [];
  const items = [];
  const el = data.eligibility || {};

  (el.failures || []).forEach((f) => {
    const u = unevaluableFor(f.kind || "failed");
    items.push({
      key: `fail-${f.rule_id}`,
      rank: 1,
      ink: PAL.fail,
      actor: u.actor,
      title: `${f.rule_id} is violated: ${f.title || "untitled rule"}`,
      page: f.page,
      clears: "Nothing else on this list can clear this. Until it is resolved the device refuses "
            + "the configuration and no parameter value is shown.",
      observed: f.observed,
      why: f.why,
    });
  });

  // Within the unevaluable bucket, order by whether the actor is at the device. `value_not_read_
  // off_programmer` is the only kind a clinician can clear where they are standing.
  const KIND_RANK = {
    value_not_read_off_programmer: 2,
    input_not_supplied: 3,
    predicate_error: 4,
  };
  (el.unknowns || []).forEach((r) => {
    const u = unevaluableFor(r.kind);
    items.push({
      key: `unk-${r.rule_id}`,
      rank: KIND_RANK[r.kind] || 4,
      ink: PAL.warnText,
      actor: u.actor,
      title: `${r.rule_id} cannot be evaluated: ${r.title || "untitled rule"}`,
      page: r.page,
      clears: r.kind === "value_not_read_off_programmer"
        ? "Reading this value off the programmer would either clear this rule or turn it into a "
          + "definite failure. Either outcome is more useful than the present state, in which it "
          + "blocks without having been tested."
        : r.kind === "input_not_supplied"
          ? "This cannot be cleared at the programmer. It needs the fields the rule reads to be "
            + "routed into the module, which is a change to the analysis rather than to the device."
          : "This is a defect in the rule table and belongs to whoever maintains it.",
      observed: r.observed,
      why: r.why,
    });
  });

  // The evidence side. Ranked below the device rules because a device refusal makes today's
  // evidence question moot, and the two are cleared by different work in any case.
  const co = data.coherence;
  const vd = data.verdict_detail || {};
  if (co && co.coherent === false) {
    const r = coherenceReading(parseSignPattern(co.observed_pattern),
      parseSignPattern(co.expected_pattern));
    items.push({
      key: "coh-false",
      rank: 5,
      ink: PAL.warnText,
      actor: r.edgesAgreeInternally
        ? "band selection \u2014 not more measurement"
        : "measurement \u2014 the edges are not consistent",
      title: r.edgesAgreeInternally
        ? "The three edges agree with each other and are anti-aligned with the control law"
        : "The three edges do not agree with each other",
      page: null,
      clears: r.edgesAgreeInternally
        ? "Re-measuring this band would not change this, because the measurements are not in "
          + "conflict with each other. What would change it is a different band, a different "
          + "hemisphere, or a control law that runs the other way."
        : "Resolving which of the three edges is unreliable would change this. That is a "
          + "measurement question and the titration session is where it is answered.",
      observed: `observed ${co.observed_pattern} against required ${co.expected_pattern}`,
      why: co.note,
    });
  } else if (vd.all_edges_resolved !== true) {
    items.push({
      key: "edges-unresolved",
      rank: 5,
      ink: PAL.neutral,
      actor: "measurement \u2014 the titration session",
      title: "At least one edge of the amplitude, band power and pain triangle is unresolved",
      page: null,
      clears: "An unresolved edge is not a negative finding; it is an absent one. A titration "
            + "session sized to resolve it is what changes this, and no reprogramming will.",
      observed: null,
      why: null,
    });
  }

  // The replay refusal. Ranked last among the substantive items because it blocks one question on
  // one panel rather than the verdict.
  const replay = data.replay;
  if (replay && replay.params && replay.params.ramp_resolvable === false) {
    items.push({
      key: "replay-cadence",
      rank: 6,
      ink: PAL.neutral,
      actor: "recording \u2014 a streaming session",
      title: "The time-at-amplitude-limit question cannot be answered from chronic snapshots",
      page: null,
      clears: "This blocks the amplitude side of the duty-cycle panel only, not the verdict. Data "
            + "sampled at the device's own averaging rate during a streaming session is what "
            + "answers it.",
      observed: replay.params.median_interval_s != null
        ? `samples every ${replay.params.median_interval_s} s against a transition-up duration of `
          + `${replay.params.transition_up_s} s`
        : null,
      why: replay.note,
    });
  }

  (el.advisories || []).filter((a) => a && a.kind === "advisory_failed").forEach((a) => {
    items.push({
      key: `adv-${a.rule_id}`,
      rank: 7,
      ink: PAL.neutral,
      actor: "noted \u2014 does not block",
      title: `${a.rule_id} falls short of a recommendation: ${a.title || "untitled rule"}`,
      page: a.page,
      clears: "This does not block, so clearing it changes nothing about today's verdict. It is "
            + "here so that a shortfall against a documented recommendation is not invisible.",
      observed: a.observed,
      why: a.why,
    });
  });

  return items.sort((a, b) => a.rank - b.rank);
}

function Item({ item, n }) {
  const [open, setOpen] = useState(false);
  return (
    <MDBox display="flex" flexDirection="row" alignItems="flex-start" gap={1} py={0.6}
      sx={{ borderTop: "1px solid rgba(0,0,0,0.08)" }}>
      <MDBox flex="0 0 22px">
        <MDTypography variant="caption" sx={{ fontSize: 13, fontFamily: PAL.mono, fontWeight: 700,
          color: item.ink }}>
          {n}
        </MDTypography>
      </MDBox>
      <MDBox flex="1 1 auto">
        <MDTypography variant="caption" sx={{ display: "block", fontSize: 12,
          fontWeight: 600, color: "#1A1A1A" }}>
          {item.title}
          {item.page ? <i style={{ fontWeight: 400, color: "#7A7A7A" }}>{`  (${item.page})`}</i>
            : null}
        </MDTypography>
        <MDTypography variant="caption" sx={{ display: "block", fontSize: 11.5, color: "#3A3A3A" }}>
          {item.clears}
        </MDTypography>
        {item.observed ? (
          <MDTypography variant="caption" sx={{ display: "block", fontSize: 10.5,
            fontFamily: PAL.mono, color: "#5A5A5A", mt: 0.2 }}>
            {`observed: ${item.observed}`}
          </MDTypography>
        ) : null}
        {item.why ? (
          <>
            <MDTypography variant="caption" onClick={() => setOpen((o) => !o)}
              sx={{ fontSize: 10.5, color: PAL.accent, cursor: "pointer", display: "block",
                "&:hover": { textDecoration: "underline" } }}>
              {open ? "Hide the module's own wording" : "Read the module's own wording"}
            </MDTypography>
            {open ? (
              <MDTypography variant="caption" sx={{ display: "block", fontSize: 11, mt: 0.3, pl: 1,
                borderLeft: "2px solid rgba(0,0,0,0.12)", color: "#3A3A3A" }}>
                {item.why}
              </MDTypography>
            ) : null}
          </>
        ) : null}
      </MDBox>
      <MDBox flex="0 0 auto" pl={1} sx={{ maxWidth: 210, textAlign: "right" }}>
        <MDTypography variant="caption" sx={{ fontSize: 10, fontWeight: "bold", letterSpacing: 0.3,
          color: item.ink }}>
          {item.actor.toUpperCase()}
        </MDTypography>
      </MDBox>
    </MDBox>
  );
}

export default function WhatWouldChangeThis({ report }) {
  const { data, loading, err } = report || { data: null, loading: false, err: null };

  if (loading) {
    return (
      <Card><MDBox p={2}>
        <MDTypography variant="button">Working out what would change the answer…</MDTypography>
      </MDBox></Card>
    );
  }
  if (!data) {
    return (
      <Card><MDBox p={2}>
        <MDTypography variant="h6" sx={{ fontSize: 15 }}>What would change this answer</MDTypography>
        <MDTypography variant="caption" sx={{ display: "block", fontSize: 11.5,
          color: PAL.neutral }}>
          {`Nothing has been evaluated for this configuration yet${err ? ` (${err})` : ""}, so `}
          there is no answer to change.
        </MDTypography>
      </MDBox></Card>
    );
  }

  const items = buildItems(data);
  const atDevice = items.filter((i) => /clinician/.test(i.actor)).length;
  const notAtDevice = items.filter((i) => /analysis|developer/.test(i.actor)).length;

  return (
    <Card sx={{ width: "100%" }}>
      <MDBox p={2}>
        <MDTypography variant="h6" sx={{ fontSize: 15 }}>What would change this answer</MDTypography>
        <MDTypography variant="caption" sx={{ display: "block", fontSize: 11.5, color: "#4A4A4A" }}>
          {items.length === 0
            ? "Nothing on this page is unresolved. Every rule that could be evaluated is satisfied "
              + "and the evidence has answered its question."
            : `${items.length} outstanding `
              + `${items.length === 1 ? "item" : "items"}, ordered by how much of the answer each `
              + "one would settle. The label on the right of each row names who can resolve it."
              + (atDevice > 0
                ? ` ${atDevice} of them can be resolved at the programmer.`
                : " None of them can be resolved at the programmer.")
              + (notAtDevice > 0
                ? ` ${notAtDevice} cannot be resolved there at all and need a change to the `
                  + "analysis or to the rule table."
                : "")}
        </MDTypography>

        <MDBox mt={0.8}>
          {items.map((it, i) => <Item key={it.key} item={it} n={i + 1} />)}
        </MDBox>
      </MDBox>
    </Card>
  );
}
