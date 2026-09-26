/**
 * How a page opens: the title as a question; one grey line naming the participant (the
 * de-identified code, never the uid) and the pain score; the status sentence; the status list;
 * and, on the Stim Optimizer and Closed-Loop pages, the safe current ceiling line.
 *
 * Written 2026-09-26 for the minimalist redesign (SPEC.md section 4, rule 1). The status
 * sentence is shown as the server wrote it where the server writes one. Nothing in the head is
 * folded.
 *
 * Props:
 *   title        the page's question ("Which brain signal tracks pain?")
 *   participant  the de-identified code ("RCS08")
 *   painScore    the pain score's display label ("Left Leg VAS")
 *   status       the status sentence (string or node)
 *   items        status-list items, see StatusList
 *   showKey      print the glyph key under the status list
 *   ceiling      { leftMa, rightMa } from the server, or omitted on pages without a ceiling line
 *   children     anything else that belongs in the head (the contents row)
 */
import PropTypes from "prop-types";

import { T, TYPE, SPACE } from "assets/theme/base/tokens";

import StatusList from "./StatusList";
import CeilingLine from "./CeilingLine";

export function contextLine(participant, painScore) {
  const parts = [];
  if (participant) parts.push(participant);
  if (painScore) parts.push(`pain score ${painScore}`);
  return parts.join(" · ");
}

export default function PageHead({ title, participant, painScore, status, items, showKey,
  ceiling, children }) {
  const context = contextLine(participant, painScore);
  return (
    <header data-paper="page-head" style={{ marginBottom: SPACE.lg }}>
      <h1 style={{ margin: 0, ...TYPE.title, color: T.ink }}>{title}</h1>
      {context ? (
        <p style={{ margin: `${SPACE.xxs}px 0 0`, ...TYPE.caption, color: T.ink3 }}>{context}</p>
      ) : null}
      {status ? (
        <p role="status" style={{ margin: `${SPACE.sm}px 0 0`, ...TYPE.answer, color: T.ink }}>
          {status}
        </p>
      ) : null}
      {(items && items.length) || showKey ? (
        <div style={{ marginTop: SPACE.xs }}>
          <StatusList items={items} showKey={showKey} />
        </div>
      ) : null}
      {ceiling ? (
        <div style={{ marginTop: SPACE.xs }}>
          <CeilingLine leftMa={ceiling.leftMa} rightMa={ceiling.rightMa}
            source={ceiling.source || "set by the PI"} />
        </div>
      ) : null}
      {children ? <div style={{ marginTop: SPACE.sm }}>{children}</div> : null}
    </header>
  );
}

PageHead.propTypes = {
  title: PropTypes.node.isRequired,
  participant: PropTypes.string,
  painScore: PropTypes.string,
  status: PropTypes.node,
  items: PropTypes.arrayOf(PropTypes.object),
  showKey: PropTypes.bool,
  ceiling: PropTypes.shape({
    leftMa: PropTypes.number,
    rightMa: PropTypes.number,
    source: PropTypes.string,
  }),
  children: PropTypes.node,
};

PageHead.defaultProps = {
  participant: null, painScore: null, status: null, items: [], showKey: false, ceiling: null,
  children: null,
};
