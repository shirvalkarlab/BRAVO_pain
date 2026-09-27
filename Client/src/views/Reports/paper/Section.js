/**
 * A page section: a question as its title, a one-sentence answer carrying the number and its
 * meaning, then one figure or a short table, at most three sentences of reading and at most one
 * "How this was worked out" fold.
 *
 * Written 2026-09-26 for the minimalist redesign (SPEC.md section 4, rule 3). A section is a
 * white card with a 1 px hairline border and no shadow; it is never put inside another card.
 * 8 px from the title to the answer, 16 px from the answer to the figure, and 64 px to the next
 * section (SPEC.md section 2.5, `LAYOUT.betweenSections`; the PI's ruling D13 of 2026-09-26).
 * The title breaks lines evenly (`text-wrap: balance`) and the answer and reading avoid a lone
 * last word (`pretty`) (TASTE_AUDIT.md C5).
 *
 * Props:
 *   id        anchor for the contents row's jump links
 *   question  the title, written as a question
 *   answer    the one-sentence answer (string or node)
 *   actions   optional controls drawn at the right of the title row (a segmented control)
 *   reading   optional short reading under the figure (at most three sentences)
 *   method    optional content of the one "How this was worked out" fold
 *   methodLabel  label of that fold (default "How this was worked out")
 *   children  the figure or table
 *   collapsible  the title row opens and closes the section's body (the PI, 2026-09-26: "make this
 *             panel collapsible and other crazy long ones too"); the answer stays in view, the body
 *             stays MOUNTED while closed (hidden), and a jump link to the section opens it
 *   defaultOpen  whether a collapsible section starts open (default false)
 *   lead      optional content that stays in view under the answer even while the section is
 *             closed (a caveat the PI has ruled must never be hidden, e.g. decision 235)
 */
import { useEffect, useState } from "react";
import PropTypes from "prop-types";

import { T, TYPE, LAYOUT, CARD, SPACE, WRAP } from "assets/theme/base/tokens";

import Fold from "./Fold";

export default function Section({ id, question, answer, actions, reading, method, methodLabel,
  children, collapsible, defaultOpen, lead }) {
  const headingId = id ? `${id}-title` : undefined;
  const bodyId = id ? `${id}-body` : undefined;
  const [open, setOpen] = useState(!collapsible || !!defaultOpen);
  // A jump link (or a shared address) to a closed section opens it.
  useEffect(() => {
    if (!collapsible || !id || typeof window === "undefined") return undefined;
    const check = () => { if (window.location.hash === `#${id}`) setOpen(true); };
    check();
    window.addEventListener("hashchange", check);
    return () => window.removeEventListener("hashchange", check);
  }, [collapsible, id]);
  const title = collapsible ? (
    <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} aria-controls={bodyId}
      data-paper="section-toggle"
      style={{ font: "inherit", color: "inherit", background: "none", border: 0, padding: 0,
        margin: 0, textAlign: "left", cursor: "pointer", display: "inline-flex",
        alignItems: "baseline", gap: SPACE.xs }}>
      <span aria-hidden="true" style={{ display: "inline-block", width: "1em", color: T.ink3,
        transform: open ? "rotate(90deg)" : "none" }}>{"\u25B8"}</span>
      <span>{question}</span>
      {!open ? <span style={{ ...TYPE.body, color: T.ink3 }}>{"(show)"}</span> : null}
    </button>
  ) : question;
  return (
    <section id={id} aria-labelledby={headingId} data-paper="section"
      style={{ ...CARD, padding: LAYOUT.cardPadding, marginBottom: LAYOUT.betweenSections }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline",
        flexWrap: "wrap", gap: SPACE.sm }}>
        <h2 id={headingId} style={{ margin: 0, ...TYPE.title, color: T.ink, ...WRAP.balance }}>{title}</h2>
        {actions ? <div>{actions}</div> : null}
      </div>
      {answer ? (
        <p style={{ margin: `${LAYOUT.titleToAnswer}px 0 0`, ...TYPE.lead, color: T.ink,
          maxWidth: LAYOUT.proseMax, ...WRAP.pretty }}>
          {answer}
        </p>
      ) : null}
      {lead ? <div style={{ marginTop: LAYOUT.titleToAnswer }}>{lead}</div> : null}
      <div id={bodyId} hidden={!open} data-paper="section-body">
      {children ? <div style={{ marginTop: LAYOUT.answerToFigure }}>{children}</div> : null}
      {reading ? (
        <p style={{ margin: `${LAYOUT.answerToFigure}px 0 0`, ...TYPE.body, color: T.ink2,
          maxWidth: LAYOUT.proseMax, ...WRAP.pretty }}>
          {reading}
        </p>
      ) : null}
      {method ? (
        <div style={{ marginTop: LAYOUT.answerToFigure }}>
          <Fold label={methodLabel}>{method}</Fold>
        </div>
      ) : null}
      </div>
    </section>
  );
}

Section.propTypes = {
  id: PropTypes.string,
  question: PropTypes.node.isRequired,
  answer: PropTypes.node,
  actions: PropTypes.node,
  reading: PropTypes.node,
  method: PropTypes.node,
  methodLabel: PropTypes.string,
  children: PropTypes.node,
  collapsible: PropTypes.bool,
  defaultOpen: PropTypes.bool,
  lead: PropTypes.node,
};

Section.defaultProps = {
  id: undefined, answer: null, actions: null, reading: null, method: null,
  methodLabel: "How this was worked out", children: null, collapsible: false, defaultOpen: false,
  lead: null,
};
