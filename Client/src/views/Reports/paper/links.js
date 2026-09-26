/**
 * Links (TASTE_AUDIT.md C3 and C11, 2026-09-26).
 *
 * A link INSIDE A SENTENCE is underlined by the global styles (assets/theme/base/globals.js),
 * so it is recognisable without colour: the accent blue against body text is only 1.63:1.
 * Pages need do nothing for that; a link inside a <p>, <li>, <td>, <dd> or <figcaption> is
 * underlined.
 *
 * A JUMP-LINK ROW (the slim "on this page" contents row under a page's status list, SPEC.md
 * section 4 rule 7) is navigation, not prose, and stays un-underlined. For future page work:
 *   - either render <JumpRow items={[{ href: "#section-id", label: "Heat maps" }]} />, which
 *     draws the row as a <nav> with the right class and spacing;
 *   - or, for a hand-built row, give its container `className={JUMP_ROW_CLASS}` (every link
 *     inside it loses the underline) or a single link `className={JUMP_LINK_CLASS}`, and style
 *     the link with `JUMP_ROW_LINK`.
 * NO "·" SEPARATORS in a jump-link row (C11: a middle dot starts a line on a phone); the links
 * are separated by space (`JUMP_ROW`'s gap). The approved middle-dot pairing line under a page
 * title ("RCS08 · pain score Left Leg VAS") is not a jump-link row and keeps its dot.
 */
import PropTypes from "prop-types";

import { T, TYPE, SPACE, WEIGHT } from "assets/theme/base/tokens";
import { JUMP_ROW_CLASS, JUMP_LINK_CLASS } from "assets/theme/base/globals";

export { JUMP_ROW_CLASS, JUMP_LINK_CLASS };

/** The row: links side by side, wrapping on a phone, separated by space only. */
export const JUMP_ROW = {
  display: "flex",
  flexWrap: "wrap",
  columnGap: SPACE.md,
  rowGap: SPACE.xs,
  listStyle: "none",
  margin: 0,
  padding: 0,
  ...TYPE.body,
};

/** One jump link: the accent, 14 px, no underline. */
export const JUMP_ROW_LINK = {
  color: T.accent,
  textDecoration: "none",
  fontWeight: WEIGHT.regular,
  ...TYPE.body,
};

export function JumpRow({ items, label, onJump }) {
  if (!items || !items.length) return null;
  return (
    <nav aria-label={label} className={JUMP_ROW_CLASS} data-paper="jump-row">
      <ul style={JUMP_ROW}>
        {items.map((it) => (
          <li key={it.href}>
            <a href={it.href} className={JUMP_LINK_CLASS} style={JUMP_ROW_LINK}
              onClick={onJump ? (e) => onJump(e, it.href) : undefined}>
              {it.label}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}

JumpRow.propTypes = {
  items: PropTypes.arrayOf(PropTypes.shape({
    href: PropTypes.string.isRequired,
    label: PropTypes.node.isRequired,
  })),
  label: PropTypes.string,
  onJump: PropTypes.func,
};

JumpRow.defaultProps = { items: [], label: "On this page", onJump: null };

export default JumpRow;
