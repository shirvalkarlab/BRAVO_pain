/**
 * The one drawing of "the predicted gain against its own uncertainty", used by the decision strip
 * (per side) and the arms strip (per pain site and side), so the two cannot draw it differently.
 *
 * Lifted out of DecisionStrip.js on 2026-09-12 (page redesign, phase 4). The bar is one standard
 * deviation of the difference wide on each side, which is the width the resolution rule uses; it
 * is NOT a 95% interval and is not labelled as one. A band that straddles 0 is the visual form of
 * "this has not earned a recommendation". The verdict symbol beside it takes the three states the
 * page has always kept apart: tick = proven better, amber = not proven (measured, too small to call),
 * open dashed = not determinable (the difference could not be formed). The words are "proven better"
 * and "not proven" since the design review of 2026-09-26: the page's headline already said "proven
 * better" for what the strip called "resolved", two names for one thing.
 *
 * Redrawn 2026-09-26 for the minimalist redesign (SPEC.md section 5.3, §1): the interval in the
 * graphic grey, the point in the accent blue, the ends labelled in words, "worse" on the left and
 * "better" on the right (a positive gain favours the suggested setting), the unit "pain points".
 * Every text is 12 px in the lightest allowed grey; the verdict is a glyph with its words:
 * ✓ proven better, ▲ not proven, ○ not determinable.
 */
import MDBox from "components/MDBox";

import { SVG_TEXT } from "views/Reports/figureStyle";

import { num } from "./stimFormat";
import { T, TYPE, WEIGHT, Mark } from "./typeScale";

/** The gain and its one-standard-deviation band on a shared axis, 220 x 46 px by default. */
export function GainBar({ gain, sd, halfRange, width = 220 }) {
  const W = width, H = 46, PAD = 12, AXIS = 18; // AXIS: the band under the bar that holds the labels
  const mid = (H - AXIS) / 2;
  const g = num(gain), s = num(sd);
  const half = halfRange || 2;
  const x = (v) => PAD + ((v + half) / (2 * half)) * (W - 2 * PAD);
  const clamp = (v) => Math.max(-half, Math.min(half, v));
  const text = { ...SVG_TEXT };
  if (g === null) {
    return (
      <svg width={W} height={H} role="img" aria-label="no gain could be formed">
        <line x1={x(0)} x2={x(0)} y1={3} y2={H - AXIS - 3} stroke={T.graphic} strokeWidth="1" />
        <text x={x(0) + 6} y={mid + 4} {...text}>no difference formed</text>
      </svg>
    );
  }
  const lo = s === null ? g : g - s, hi = s === null ? g : g + s;
  return (
    <svg width={W} height={H} role="img"
      aria-label={`gain ${g.toFixed(2)} pain points, one standard deviation ${s === null ? "unknown" : s.toFixed(2)}; left is worse than today, right is better`}>
      <line x1={x(0)} x2={x(0)} y1={3} y2={H - AXIS - 3} stroke={T.graphic} strokeWidth="1" strokeDasharray="3 3" />
      {s !== null && (
        <line x1={x(clamp(lo))} x2={x(clamp(hi))} y1={mid} y2={mid} stroke={T.graphic} strokeWidth="2" />
      )}
      <circle cx={x(clamp(g))} cy={mid} r={5} fill={T.accent} />
      <text x={x(-half)} y={H - 3} {...text}>{`← worse`}</text>
      <text x={x(0)} y={H - 3} {...text} textAnchor="middle">0</text>
      <text x={x(half)} y={H - 3} {...text} textAnchor="end">{`better →`}</text>
    </svg>
  );
}

export function VerdictGlyph({ resolved, size = TYPE.body }) {
  const text = { fontSize: size, fontWeight: WEIGHT.strong, whiteSpace: "nowrap" };
  if (resolved === true) return (
    <MDBox display="inline-flex" alignItems="center" gap={0.6}>
      <Mark state="pass" label="proven better" /><span style={{ ...text, color: T.ink }}>proven better</span>
    </MDBox>);
  if (resolved === false) return (
    <MDBox display="inline-flex" alignItems="center" gap={0.6}>
      <Mark state="caution" label="not proven" /><span style={{ ...text, color: T.caution }}>not proven</span>
    </MDBox>);
  return (
    <MDBox display="inline-flex" alignItems="center" gap={0.6}>
      <Mark state="notChecked" label="not determinable" /><span style={{ ...text, color: T.notChecked }}>not determinable</span>
    </MDBox>);
}
