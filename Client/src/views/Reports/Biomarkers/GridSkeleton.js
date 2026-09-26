/**
 * A still placeholder shaped like the answer that is on its way (taste audit C2, 2026-09-26): grey
 * blocks where the pair thumbnails and the two heat maps (or a table's rows) will be drawn, in place
 * of a spinner. Nothing moves: no shimmer, no pulse (motion must never hide or delay a clinical
 * value). The waiting words are the caller's own and are printed above the blocks, in the open.
 *
 * Props:
 *   words   the waiting sentence ("Computing the calibrated grid…")
 *   shape   "heatmaps" (six thumbnails, then two maps side by side) or "table" (a header and rows)
 *   rows    rows of a "table" shape (default 6)
 */
import PropTypes from "prop-types";

import { T, TYPE, SPACE, RADIUS } from "assets/theme/base/tokens";

const BLOCK = { background: T.fillMuted, borderRadius: RADIUS.sm };

export default function GridSkeleton({ words, shape, rows }) {
  return (
    <div data-testid="grid-skeleton" data-shape={shape} role="status" aria-live="polite">
      <p style={{ ...TYPE.body, color: T.ink3, margin: `${SPACE.xs}px 0 ${SPACE.sm}px` }}>{words}</p>
      {shape === "table" ? (
        <div aria-hidden="true" data-skeleton="blocks">
          <div style={{ ...BLOCK, height: 18, marginBottom: SPACE.xs }} />
          {Array.from({ length: rows }, (_, i) => (
            <div key={i} style={{ ...BLOCK, height: 14, marginBottom: SPACE.xxs, width: "100%" }} />
          ))}
        </div>
      ) : (
        <div aria-hidden="true" data-skeleton="blocks">
          <div style={{ display: "flex", flexWrap: "wrap", gap: SPACE.sm, marginBottom: SPACE.md }}>
            {Array.from({ length: 6 }, (_, i) => (
              <div key={i} style={{ ...BLOCK, width: 120, height: 60 }} />
            ))}
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: SPACE.md }}>
            {[0, 1].map((i) => (
              <div key={i} style={{ flex: "1 1 280px" }}>
                <div style={{ ...BLOCK, height: 8, marginBottom: SPACE.xs }} />
                <div style={{ ...BLOCK, height: 320 }} />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

GridSkeleton.propTypes = {
  words: PropTypes.node.isRequired,
  shape: PropTypes.oneOf(["heatmaps", "table"]),
  rows: PropTypes.number,
};

GridSkeleton.defaultProps = { shape: "heatmaps", rows: 6 };
