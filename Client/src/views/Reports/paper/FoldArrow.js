/**
 * The toggle mark every fold, collapsible section and the matching panel's button draws beside
 * its label -- one shared, more prominent version (the PI, 2026-09-27: "make any clickable
 * drop-down area much more prominent, perhaps with a really big toggle arrow"). Before this, six
 * files each drew their own single character (`▸`, 14 px, the same grey as the label text it sat
 * beside), which read as decoration rather than a control. This is the ONE home for that mark, so
 * a future change to it is one edit, not six (the project's own rule against a second copy).
 *
 * The mark is a rounded chip, filled with the accent tint, holding a bold arrow in the accent
 * colour -- large and coloured enough that a reader sees a button, not a bullet. It carries no
 * click handler of its own: the row it sits in stays the button, so keyboard focus, `aria-
 * expanded` and the existing tests keep working unchanged. Rotation is instant under reduced
 * motion, same as before (the global rule sets every transition to 0 s).
 *
 * Props: `open` (bool), `size` ("md", the default, or "sm" for a tight row).
 */
import PropTypes from "prop-types";

import { T, RADIUS } from "assets/theme/base/tokens";

const BOX = { md: 22, sm: 18 };
const GLYPH = { md: 14, sm: 12 };

export default function FoldArrow({ open, size }) {
  const box = BOX[size] || BOX.md;
  const glyph = GLYPH[size] || GLYPH.md;
  return (
    <span aria-hidden="true" data-paper="fold-arrow" style={{
      display: "inline-flex", alignItems: "center", justifyContent: "center",
      width: box, height: box, minWidth: box, borderRadius: `${RADIUS.sm}px`,
      background: T.accentTint, border: `1px solid ${T.accent}`,
      color: T.accent, fontSize: glyph, fontWeight: 600, lineHeight: 1,
      transform: open ? "rotate(90deg)" : "none", transition: "transform .15s",
    }}>
      {"▸"}
    </span>
  );
}

FoldArrow.propTypes = { open: PropTypes.bool, size: PropTypes.oneOf(["md", "sm"]) };
FoldArrow.defaultProps = { open: false, size: "md" };
