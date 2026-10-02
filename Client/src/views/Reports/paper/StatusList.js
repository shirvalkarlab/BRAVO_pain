/**
 * The status list under a page's status sentence: at most five short items, each with the glyph
 * of its state, so a reader never has to tell a meaning from colour alone.
 *
 * Written 2026-09-26 for the minimalist redesign (SPEC.md section 4, rule 1). States:
 *   "refused"    ✕ red   -- ONLY the device refuses, or a value is above the safe ceiling
 *   "blocked"    ✕ ink   -- a statistical or evidence result that stops closed loop ("Setting
 *                           not proven better", "No usable sensing pair", a "not usable" row);
 *                           never red (the PI's ruling of 2026-09-26)
 *   "caution"    ▲ amber -- needs more data; not yet certain; moves over time
 *   "notChecked" ○ grey  -- could not be checked (still blocks, but is counted separately)
 *   "pass"       ✓ ink   -- passes (there is no green in page text)
 * The wording of each item is the caller's: refusals are passed in word for word and shown as
 * sent. Items are never folded. `showKey` prints the one-line key of the glyphs.
 *
 * Props:
 *   items   [{ state, text, key? }]  -- text is a string or a React node
 *   showKey boolean (default false)
 *   label   accessible name for the list (default "Status")
 */
import PropTypes from "prop-types";

import { STATE, TYPE, SPACE, WEIGHT } from "assets/theme/base/tokens";

export const MAX_STATUS_ITEMS = 5;

export const STATUS_KEY = [
  // The key's ✕ is drawn in ink: it explains the glyph, and red is only for a device refusal
  // or a value above the safe ceiling.
  { state: "blocked", text: "blocks" },
  { state: "caution", text: "needs more data or caution" },
  { state: "notChecked", text: "not checked" },
];

function Glyph({ state }) {
  const s = STATE[state] || STATE.notChecked;
  return (
    <span aria-hidden="true" style={{ color: s.ink, display: "inline-block", minWidth: "1.2em" }}>
      {s.glyph}
    </span>
  );
}
Glyph.propTypes = { state: PropTypes.string.isRequired };

export default function StatusList({ items, showKey, label }) {
  const shown = (items || []).slice(0, MAX_STATUS_ITEMS);
  if (!shown.length && !showKey) return null;
  return (
    <div data-paper="status-list">
      {shown.length > 0 && (
        <ul aria-label={label}
          style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexWrap: "wrap",
            columnGap: SPACE.md, rowGap: SPACE.xs, ...TYPE.body }}>
          {shown.map((it, i) => {
            const s = STATE[it.state] || STATE.notChecked;
            return (
              <li key={it.key || i} data-state={it.state}
                style={{ color: s.ink, fontWeight: it.state === "pass" ? WEIGHT.regular : WEIGHT.strong }}>
                <Glyph state={it.state} />
                {it.text}
              </li>
            );
          })}
        </ul>
      )}
      {showKey && (
        <p style={{ margin: `${SPACE.xs}px 0 0`, ...TYPE.body, color: STATE.notChecked.ink }}>
          {STATUS_KEY.map((k, i) => (
            <span key={k.state}>
              {i > 0 ? " · " : ""}
              <Glyph state={k.state} />
              {k.text}
            </span>
          ))}
        </p>
      )}
    </div>
  );
}

StatusList.propTypes = {
  items: PropTypes.arrayOf(PropTypes.shape({
    state: PropTypes.oneOf(["refused", "blocked", "caution", "notChecked", "pass"]).isRequired,
    text: PropTypes.node.isRequired,
    key: PropTypes.string,
  })),
  showKey: PropTypes.bool,
  label: PropTypes.string,
};

StatusList.defaultProps = { items: [], showKey: false, label: "Status" };
