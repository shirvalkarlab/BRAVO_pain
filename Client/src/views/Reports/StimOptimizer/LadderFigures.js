/**
 * The next-visit section's two small figures (SPEC.md section 5.3, §4), drawn in SVG at the
 * container's real pixel width so 12 px text stays 12 px on screen:
 *
 *  - `LadderPlot`: one side's ladder as a step plot of current against step number, the side in
 *    its page-wide colour (left blue, right orange), the safe ceiling a dashed red line labelled
 *    "safe ceiling" (its value is on the axis and stated once in the session line above), and the
 *    side held still named in words. Read from `sides[side].ladder.steps_mA`; nothing recomputed.
 *  - `BandAxis`: the 22 band centres on an 8–30 Hz axis, a clear centre a filled dot and a flagged
 *    one a hollow ring, with each folded multiple of the rate that lands on the axis marked and
 *    labelled ("rate ×4 → 30 Hz"). Flagged is advisory: every centre is analysed either way (the
 *    PI's wording, "carries a folded multiple of the stimulation rate", is kept in the fold).
 */
import { SVG_TEXT, CEILING_LINE } from "views/Reports/figureStyle";
import { SIDE } from "assets/theme/base/dataColors";

import { num } from "./stimFormat";
import { T, WEIGHT } from "./typeScale";
import useMeasuredWidth from "./useMeasuredWidth";

const sideColour = (side) => (side === "Right" ? SIDE.right : SIDE.left);

export function LadderPlot({ side, steps, ceilingMa, heldText }) {
  const [ref, width] = useMeasuredWidth(420, 320);
  const xs = (Array.isArray(steps) ? steps : []).map((v) => num(v)).filter((v) => v !== null);
  if (!xs.length) return null;
  const W = Math.min(width, 560), H = 170, L = 44, R = 92, TOP = 26, B = 36;
  const ceil = num(ceilingMa);
  const yMax = Math.max(1, ...xs, ceil ?? 0) + 0.5;
  const n = xs.length;
  const x = (i) => L + (i / n) * (W - L - R);            // step i occupies [i, i+1)
  const y = (v) => TOP + (1 - v / yMax) * (H - TOP - B);
  let d = "";
  xs.forEach((v, i) => { d += `${i === 0 ? "M" : "L"}${x(i)},${y(v)} L${x(i + 1)},${y(v)} `; });
  const ticks = [];
  for (let t = 0; t <= yMax - 0.5 + 1e-9; t += 1) ticks.push(t);
  const ink = sideColour(side);
  return (
    <div ref={ref} style={{ width: "100%", overflowX: "auto" }}>
      <svg width={W} height={H} role="img"
        aria-label={`${side} ladder: ${n} steps, ${xs.map((v) => `${v} mA`).join(", ")}${ceil !== null ? `; safe ceiling ${ceil} mA` : ""}`}>
        {heldText ? <text x={L} y={14} {...SVG_TEXT}>{heldText}</text> : null}
        <line x1={L} x2={L} y1={TOP} y2={H - B} stroke={T.graphic} />
        <line x1={L} x2={W - R} y1={H - B} y2={H - B} stroke={T.graphic} />
        {ticks.map((t) => (
          <text key={t} x={L - 6} y={y(t) + 4} {...SVG_TEXT} textAnchor="end">{t}</text>
        ))}
        <text x={L - 6} y={TOP - 8} {...SVG_TEXT} textAnchor="end">mA</text>
        {[1, n].map((s) => (
          <text key={s} x={x(s - 0.5)} y={H - B + 16} {...SVG_TEXT} textAnchor="middle">{s}</text>
        ))}
        <text x={(L + W - R) / 2} y={H - 4} {...SVG_TEXT} textAnchor="middle">step</text>
        {ceil !== null && (
          <>
            <line x1={L} x2={W - R} y1={y(ceil)} y2={y(ceil)} stroke={CEILING_LINE.color}
              strokeWidth={CEILING_LINE.width} strokeDasharray="5 4" />
            <text x={W - R + 6} y={y(ceil) + 4} {...SVG_TEXT} fill={T.refused}>safe ceiling</text>
          </>
        )}
        <path d={d} fill="none" stroke={ink} strokeWidth="2" />
        <text x={x(n) + 6} y={y(xs[n - 1]) + 4} {...SVG_TEXT} fill={T.ink} fontWeight={WEIGHT.strong}>{side}</text>
      </svg>
    </div>
  );
}

/** "rate ×4", "rate ÷2", ... from the server's key for a landing. */
function landingName(key) {
  if (key === "half_rate") return "rate ÷2";
  if (key === "quarter_rate") return "rate ÷4";
  if (key === "three_quarters_rate") return "rate ×¾";
  const m = /^multiple_(\d+)$/.exec(String(key));
  return m ? `rate ×${m[1]}` : String(key).replace(/_/g, " ");
}

export function BandAxis({ bands }) {
  const [ref, width] = useMeasuredWidth(420, 320);
  if (!bands || !Array.isArray(bands.centres_hz)) return null;
  const lo = 8, hi = 30;
  const W = Math.min(width, 560), L = 12, R = 12;
  const x = (f) => L + ((f - lo) / (hi - lo)) * (W - L - R);
  const flagged = new Set((bands.avoid_hz || []).map((v) => Number(v)));
  // The landings on the axis, labelled on as many rows as they need not to overlap.
  const landings = Object.entries(bands.harmonics_hz || {})
    .map(([k, v]) => ({ k, f: num(v) })).filter((l) => l.f !== null && l.f >= lo && l.f <= hi)
    .sort((a, b) => a.f - b.f);
  const LABEL_W = 110;
  const rowEnds = [];
  const placed = landings.map((l) => {
    const cx = x(l.f);
    let row = rowEnds.findIndex((end) => cx - LABEL_W / 2 > end + 6);
    if (row < 0) { row = rowEnds.length; rowEnds.push(-Infinity); }
    rowEnds[row] = cx + LABEL_W / 2;
    return { ...l, cx, row };
  });
  const DOT_Y = 12, AXIS_Y = 24, TICK_Y = 38, LAB0 = 56, ROW = 16;
  const H = LAB0 + Math.max(0, rowEnds.length - 1) * ROW + 6;
  return (
    <div ref={ref} style={{ width: "100%", overflowX: "auto" }}>
      <svg width={W} height={H} role="img"
        aria-label={`band centres 8 to 30 Hz: ${bands.n_clear ?? "—"} clear, ${bands.n_avoid ?? "—"} flagged`}>
        <line x1={x(lo)} x2={x(hi)} y1={AXIS_Y} y2={AXIS_Y} stroke={T.graphic} />
        {[10, 15, 20, 25, 30].map((t) => (
          <text key={t} x={x(t)} y={TICK_Y} {...SVG_TEXT} textAnchor="middle">{t}</text>
        ))}
        {bands.centres_hz.map((c) => {
          const f = Number(c);
          return flagged.has(f)
            ? <circle key={f} cx={x(f)} cy={DOT_Y} r="3.5" fill={T.surface} stroke={T.graphic} strokeWidth="1.5" />
            : <circle key={f} cx={x(f)} cy={DOT_Y} r="3.5" fill={T.ink} />;
        })}
        {placed.map((l) => (
          <g key={l.k}>
            <line x1={l.cx} x2={l.cx} y1={DOT_Y - 8} y2={AXIS_Y + 3} stroke={T.caution} strokeDasharray="2 2" />
            <text x={l.cx} y={LAB0 + l.row * ROW} {...SVG_TEXT} textAnchor="middle">
              {`${landingName(l.k)} → ${l.f} Hz`}
            </text>
          </g>
        ))}
      </svg>
    </div>
  );
}
