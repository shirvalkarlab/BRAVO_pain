/**
 * The one drawing of "the predicted gain against its own uncertainty", used by the decision strip
 * (per side) and the arms strip (per pain site and side), so the two cannot draw it differently.
 *
 * Lifted out of DecisionStrip.js on 2026-09-12 (page redesign, phase 4). The bar is one standard
 * deviation of the difference wide on each side, which is the width the resolution rule uses; it
 * is NOT a 95% interval and is not labelled as one. A band that straddles 0 is the visual form of
 * "this has not earned a recommendation". The verdict symbol beside it takes the three states the
 * page has always kept apart: tick = resolved, amber = not resolved (measured, too small to call),
 * open dashed = not determinable (the difference could not be formed).
 *
 * Resized 2026-09-12 (PI's review of the page): 220 x 40 px, the axis labels at 11 px in a band
 * of their own under the bar, so no label sits on the bar or the zero line.
 */
import MDBox from "components/MDBox";

import PAL from "views/Reports/ClosedLoopSim/palette";
import { TickGlyph, AmberGlyph, NotTestedGlyph } from "views/Reports/ClosedLoopSim/glyphs";

import { num } from "./stimFormat";
import { TYPE } from "./typeScale";

/** The gain and its one-standard-deviation band on a shared axis, 220 x 40 px by default. */
export function GainBar({ gain, sd, halfRange, width = 220 }) {
  const W = width, H = 40, PAD = 10, AXIS = 14; // AXIS: the band under the bar that holds the labels
  const mid = (H - AXIS) / 2;
  const g = num(gain), s = num(sd);
  const half = halfRange || 2;
  const x = (v) => PAD + ((v + half) / (2 * half)) * (W - 2 * PAD);
  const clamp = (v) => Math.max(-half, Math.min(half, v));
  if (g === null) {
    return (
      <svg width={W} height={H} role="img" aria-label="no gain could be formed">
        <line x1={x(0)} x2={x(0)} y1={3} y2={H - AXIS - 3} stroke="#9A9A9A" strokeWidth="1" />
        <text x={x(0) + 6} y={mid + 4} fontSize={TYPE.axis} fill="#7A7A7A">no difference formed</text>
      </svg>
    );
  }
  const lo = s === null ? g : g - s, hi = s === null ? g : g + s;
  return (
    <svg width={W} height={H} role="img"
      aria-label={`gain ${g.toFixed(2)} points, one standard deviation ${s === null ? "unknown" : s.toFixed(2)}`}>
      <line x1={x(-half)} x2={x(half)} y1={mid} y2={mid} stroke="#E0E0E0" strokeWidth="1" />
      <line x1={x(0)} x2={x(0)} y1={3} y2={H - AXIS - 3} stroke="#6A6A6A" strokeWidth="1" />
      {s !== null && (
        <rect x={x(clamp(lo))} y={mid - 6} width={Math.max(1, x(clamp(hi)) - x(clamp(lo)))} height={12}
          fill={PAL.neutralFill} stroke={PAL.neutralBorder} />
      )}
      <circle cx={x(clamp(g))} cy={mid} r={5} fill={PAL.accent} />
      <text x={x(-half)} y={H - 2} fontSize={TYPE.axis} fill="#7A7A7A">{`−${half}`}</text>
      <text x={x(0)} y={H - 2} fontSize={TYPE.axis} fill="#7A7A7A" textAnchor="middle">0</text>
      <text x={x(half)} y={H - 2} fontSize={TYPE.axis} fill="#7A7A7A" textAnchor="end">{`+${half}`}</text>
    </svg>
  );
}

export function VerdictGlyph({ resolved, size = TYPE.body }) {
  const text = { fontSize: size, fontWeight: 600, whiteSpace: "nowrap" };
  if (resolved === true) return (
    <MDBox display="inline-flex" alignItems="center" gap={0.6}>
      <TickGlyph label="resolved" size={16} /><span style={{ ...text, color: PAL.pass }}>resolved</span>
    </MDBox>);
  if (resolved === false) return (
    <MDBox display="inline-flex" alignItems="center" gap={0.6}>
      <AmberGlyph label="not resolved" size={16} /><span style={{ ...text, color: PAL.warnText }}>not resolved</span>
    </MDBox>);
  return (
    <MDBox display="inline-flex" alignItems="center" gap={0.6}>
      <NotTestedGlyph label="not determinable" size={16} /><span style={{ ...text, color: PAL.neutral }}>not determinable</span>
    </MDBox>);
}
