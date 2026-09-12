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
 */
import MDBox from "components/MDBox";

import PAL from "views/Reports/ClosedLoopSim/palette";
import { TickGlyph, AmberGlyph, NotTestedGlyph } from "views/Reports/ClosedLoopSim/glyphs";

import { num } from "./stimFormat";

/** The gain and its one-standard-deviation band on a shared axis, 180 x 26 px. */
export function GainBar({ gain, sd, halfRange }) {
  const W = 180, H = 26, PAD = 6;
  const g = num(gain), s = num(sd);
  const half = halfRange || 2;
  const x = (v) => PAD + ((v + half) / (2 * half)) * (W - 2 * PAD);
  const clamp = (v) => Math.max(-half, Math.min(half, v));
  if (g === null) {
    return (
      <svg width={W} height={H} role="img" aria-label="no gain could be formed">
        <line x1={x(0)} x2={x(0)} y1={3} y2={H - 3} stroke="#9A9A9A" strokeWidth="1" />
        <text x={x(0) + 4} y={H / 2 + 4} fontSize="9" fill="#9A9A9A">no difference formed</text>
      </svg>
    );
  }
  const lo = s === null ? g : g - s, hi = s === null ? g : g + s;
  return (
    <svg width={W} height={H} role="img"
      aria-label={`gain ${g.toFixed(2)} points, one standard deviation ${s === null ? "unknown" : s.toFixed(2)}`}>
      <line x1={x(-half)} x2={x(half)} y1={H / 2} y2={H / 2} stroke="#E0E0E0" strokeWidth="1" />
      <line x1={x(0)} x2={x(0)} y1={3} y2={H - 3} stroke="#6A6A6A" strokeWidth="1" />
      {s !== null && (
        <rect x={x(clamp(lo))} y={H / 2 - 5} width={Math.max(1, x(clamp(hi)) - x(clamp(lo)))} height={10}
          fill={PAL.neutralFill} stroke={PAL.neutralBorder} />
      )}
      <circle cx={x(clamp(g))} cy={H / 2} r={4.5} fill={PAL.accent} />
      <text x={x(-half)} y={H - 1} fontSize="8" fill="#9A9A9A">{`−${half}`}</text>
      <text x={x(half)} y={H - 1} fontSize="8" fill="#9A9A9A" textAnchor="end">{`+${half}`}</text>
    </svg>
  );
}

export function VerdictGlyph({ resolved }) {
  if (resolved === true) return (
    <MDBox display="inline-flex" alignItems="center" gap={0.5}>
      <TickGlyph label="resolved" /><span style={{ fontSize: 11.5, color: PAL.pass, fontWeight: 600 }}>resolved</span>
    </MDBox>);
  if (resolved === false) return (
    <MDBox display="inline-flex" alignItems="center" gap={0.5}>
      <AmberGlyph label="not resolved" /><span style={{ fontSize: 11.5, color: PAL.warnText, fontWeight: 600 }}>not resolved</span>
    </MDBox>);
  return (
    <MDBox display="inline-flex" alignItems="center" gap={0.5}>
      <NotTestedGlyph label="not determinable" /><span style={{ fontSize: 11.5, color: PAL.neutral, fontWeight: 600 }}>not determinable</span>
    </MDBox>);
}
