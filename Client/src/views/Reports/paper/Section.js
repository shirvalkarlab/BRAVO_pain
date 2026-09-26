/**
 * A page section: a question as its title, a one-sentence answer carrying the number and its
 * meaning, then one figure or a short table, at most three sentences of reading and at most one
 * "How this was worked out" fold.
 *
 * Written 2026-09-26 for the minimalist redesign (SPEC.md section 4, rule 3). A section is a
 * white card with a 1 px hairline border and no shadow; it is never put inside another card.
 * 8 px from the title to the answer, 16 px from the answer to the figure.
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
 */
import PropTypes from "prop-types";

import { T, TYPE, LAYOUT, CARD } from "assets/theme/base/tokens";

import Fold from "./Fold";

export default function Section({ id, question, answer, actions, reading, method, methodLabel,
  children }) {
  const headingId = id ? `${id}-title` : undefined;
  return (
    <section id={id} aria-labelledby={headingId} data-paper="section"
      style={{ ...CARD, padding: LAYOUT.cardPadding, marginBottom: LAYOUT.betweenCards }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline",
        flexWrap: "wrap", gap: 16 }}>
        <h2 id={headingId} style={{ margin: 0, ...TYPE.title, color: T.ink }}>{question}</h2>
        {actions ? <div>{actions}</div> : null}
      </div>
      {answer ? (
        <p style={{ margin: `${LAYOUT.titleToAnswer}px 0 0`, ...TYPE.lead, color: T.ink,
          maxWidth: LAYOUT.proseMax }}>
          {answer}
        </p>
      ) : null}
      {children ? <div style={{ marginTop: LAYOUT.answerToFigure }}>{children}</div> : null}
      {reading ? (
        <p style={{ margin: `${LAYOUT.answerToFigure}px 0 0`, ...TYPE.body, color: T.ink2,
          maxWidth: LAYOUT.proseMax }}>
          {reading}
        </p>
      ) : null}
      {method ? (
        <div style={{ marginTop: LAYOUT.answerToFigure }}>
          <Fold label={methodLabel}>{method}</Fold>
        </div>
      ) : null}
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
};

Section.defaultProps = {
  id: undefined, answer: null, actions: null, reading: null, method: null,
  methodLabel: "How this was worked out", children: null,
};
