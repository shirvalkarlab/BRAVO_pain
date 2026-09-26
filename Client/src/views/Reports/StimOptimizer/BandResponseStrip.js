/**
 * The 18 tested band centres as bars: height is the separation between the two captured power
 * readings (in units of their own scatter, `separation_d`), the line is the minimum the check
 * requires, the bar takes the pass ink when the band responds and the fail ink when it does not,
 * and the best-separated band carries its numbers as a caption under the chart.
 *
 * Added 2026-09-12 (page redesign, phase 3). Reads the `verdict_rows`, `min_sep_d` and
 * `best_center_hz` the band-response check now puts in its evidence; draws nothing it cannot read
 * (a row without a finite separation is an open dashed mark at zero height).
 *
 * Redrawn 2026-09-12 after the PI's review: 560 x 170 px, every tick and label at 11 px, the
 * required-minimum label in the right margin outside the plot, the best bar's value above its bar
 * and never on it, and the caption a 12 px line under the chart rather than text inside it.
 *
 * BOTH HALVES OF THE RULE (review S4, 2026-09-12). "This band responds" is the readiness screen's
 * rule, and it has two halves: the two captured readings point the right way and are separated
 * (`responds`), AND the band's power falls with current once time is removed -- the era-blocked
 * slope is negative and significant (`era_negative_significant`). A bar takes the pass ink only
 * when both hold; a band that responds by direction alone is drawn in the amber ink, because on
 * this record a falling capture with a rising adjusted slope is a time artefact, not a response.
 *
 * A SHAPE PER STATE, NOT COLOUR ALONE (the design review of 2026-09-26, S9; WCAG 1.4.1): a band that
 * does both is a solid bar; direction alone is a hatched bar; a band that does not respond is an
 * open bar, outline only; a band that could not be measured is a dashed open circle. The four are
 * named in a key under the chart. The axis text is #5E5E5E (6.4:1; it was #7A7A7A, 4.29:1), and
 * "separation (SD)" is said in the house words: the gap between the two measured power levels, in
 * units of their own scatter.
 */
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import PAL from "views/Reports/ClosedLoopSim/palette";

import { num } from "./stimFormat";
import { TYPE, SMALL } from "./typeScale";

/** What each bar shape means, one swatch each, so no state is told apart by colour alone. */
function BandStateKey({ showDirection }) {
  const item = { display: "inline-flex", alignItems: "center", gap: 5, whiteSpace: "nowrap" };
  const sw = (children) => <svg width="14" height="14" aria-hidden="true">{children}</svg>;
  return (
    <MDBox display="flex" flexWrap="wrap" columnGap={2} rowGap={0.3} sx={SMALL}>
      <span style={item}>{sw(<rect x="2" y="1" width="10" height="12" fill={PAL.pass} />)} solid: responds by its two readings and falls with current after removing differences between clinic visits</span>
      {showDirection && (
        <span style={item}>{sw(<><rect x="2" y="1" width="10" height="12" fill="#FFFFFF" stroke={PAL.warn} strokeWidth="1" /><path d="M2,6 L7,1 M2,11 L12,1 M5,13 L12,6" stroke={PAL.warn} strokeWidth="1.6" /></>)} hatched: direction alone</span>
      )}
      <span style={item}>{sw(<rect x="2.75" y="1.75" width="8.5" height="10.5" fill="#FFFFFF" stroke={PAL.fail} strokeWidth="1.5" />)} open: does not respond</span>
      <span style={item}>{sw(<circle cx="7" cy="7" r="3.5" fill="none" stroke={PAL.neutral} strokeDasharray="2 2" />)} dashed circle: not measurable</span>
    </MDBox>
  );
}

// 520 px (was 560, 2026-09-26): the checks card's evidence column is about 547 px wide on a
// 1,280 px laptop, so a 560 px chart scrolled inside it.
export default function BandResponseStrip({ rows, minSep, best, width = 520 }) {
  const list = (Array.isArray(rows) ? rows : []).filter((r) => r && num(r.center_hz) !== null)
    .sort((a, b) => num(a.center_hz) - num(b.center_hz));
  if (!list.length) return null;
  // L: the y-axis labels; R: the right margin that holds the "required ≥" label; T: room for the
  // best bar's value above the tallest bar; B: the tick labels and the axis title.
  const W = width, H = 170, L = 52, R = 118, T = 22, B = 36;
  const lo = 8, hi = 30;
  const x = (c) => L + ((c - lo) / (hi - lo)) * (W - L - R);
  const ds = list.map((r) => num(r.separation_d)).filter((v) => v !== null);
  const dMax = Math.max(1, ...ds, num(minSep) || 0) * 1.1;
  const y = (d) => T + (1 - d / dMax) * (H - T - B);
  const bestRow = best != null ? list.find((r) => Math.abs(num(r.center_hz) - Number(best)) < 1e-9) : null;
  const bw = Math.max(4, ((W - L - R) / (hi - lo)) * 0.72);
  const bestD = bestRow ? num(bestRow.separation_d) : null;
  const caption = bestRow
    ? `best ${num(bestRow.center_hz).toFixed(1)} Hz · gap ${bestD === null ? "—" : bestD.toFixed(2)} scatter units`
      + (num(bestRow.power_low) !== null && num(bestRow.power_high) !== null
        ? ` · ${num(bestRow.power_low).toFixed(1)} → ${num(bestRow.power_high).toFixed(1)} units at ${num(bestRow.amp_low_mA) === null ? "—" : num(bestRow.amp_low_mA).toFixed(1)} → ${num(bestRow.amp_high_mA) === null ? "—" : num(bestRow.amp_high_mA).toFixed(1)} mA`
        : "")
    : "";
  return (
    <MDBox>
      <svg width={W} height={H} role="img" aria-label="gap between the two power levels per band centre, against the required minimum">
        <defs>
          <pattern id="band-direction-only" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <rect width="5" height="5" fill="#FFFFFF" />
            <line x1="0" y1="0" x2="0" y2="5" stroke={PAL.warn} strokeWidth="3" />
          </pattern>
        </defs>
        {/* y axis */}
        <line x1={L} x2={L} y1={T} y2={y(0)} stroke="#D8D8D8" />
        <line x1={L} x2={W - R} y1={y(0)} y2={y(0)} stroke="#D8D8D8" />
        <text x={L - 6} y={y(0) + 4} fontSize={TYPE.axis} fill="#5E5E5E" textAnchor="end">0</text>
        <text x={L - 6} y={y(dMax / 2) + 4} fontSize={TYPE.axis} fill="#5E5E5E" textAnchor="end">{(dMax / 2).toFixed(1)}</text>
        <text x={L - 6} y={T + 4} fontSize={TYPE.axis} fill="#5E5E5E" textAnchor="end">{dMax.toFixed(1)}</text>
        <text x={12} y={(T + y(0)) / 2} fontSize={TYPE.axis} fill="#5E5E5E" textAnchor="middle"
          transform={`rotate(-90 12 ${(T + y(0)) / 2})`}>gap (scatter units)</text>
        {/* the required minimum, labelled in the right margin so it never crosses a bar */}
        {num(minSep) !== null && (
          <>
            <line x1={L} x2={W - R} y1={y(num(minSep))} y2={y(num(minSep))} stroke="#4A4A4A" strokeWidth="1" strokeDasharray="4 3" />
            <text x={W - R + 6} y={y(num(minSep)) + 4} fontSize={TYPE.axis} fill="#4A4A4A">{`required ≥ ${num(minSep).toFixed(2)}`}</text>
          </>
        )}
        {/* x axis */}
        {[8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30].map((t) => (
          <text key={t} x={x(t)} y={H - B + 16} fontSize={TYPE.axis} fill="#5E5E5E" textAnchor="middle">{t}</text>
        ))}
        <text x={(L + W - R) / 2} y={H - 4} fontSize={TYPE.axis} fill="#5E5E5E" textAnchor="middle">band centre (Hz)</text>
        {list.map((r) => {
          const c = num(r.center_hz), d = num(r.separation_d);
          if (d === null) {
            return <circle key={c} cx={x(c)} cy={y(0) - 5} r="3.5" fill="none" stroke={PAL.neutral} strokeDasharray="2 2" />;
          }
          const both = r.responds === true && r.era_negative_significant === true;
          const directionOnly = r.responds === true && r.era_negative_significant === false;
          const top = y(Math.min(d, dMax));
          const h = Math.max(0.5, y(0) - top);
          // solid: both halves; hatched: direction alone; open outline: does not respond
          if (both) return <rect key={c} x={x(c) - bw / 2} y={top} width={bw} height={h} fill={PAL.pass} rx="1" data-state="both" />;
          if (directionOnly) {
            return <rect key={c} x={x(c) - bw / 2} y={top} width={bw} height={h} fill="url(#band-direction-only)"
              stroke={PAL.warn} strokeWidth="1" rx="1" data-state="direction-only" />;
          }
          return (
            <rect key={c} x={x(c) - bw / 2 + 0.75} y={top + 0.75} width={Math.max(0.5, bw - 1.5)} height={Math.max(0.5, h - 1.5)}
              fill="#FFFFFF" stroke={r.responds === false ? PAL.fail : PAL.neutral} strokeWidth="1.5" rx="1"
              data-state={r.responds === false ? "no-response" : "unknown"} />
          );
        })}
        {/* the best bar's value, above the bar */}
        {bestRow && bestD !== null && (
          <text x={x(num(bestRow.center_hz))} y={y(Math.min(bestD, dMax)) - 5} fontSize={TYPE.axis} fontWeight="600"
            fill="#1A1A1A" textAnchor="middle" stroke="#FFFFFF" strokeWidth="3" paintOrder="stroke">{bestD.toFixed(2)}</text>
        )}
      </svg>
      {caption && (
        <MDTypography variant="caption" component="div" sx={{ ...SMALL, color: "#1A1A1A", fontFamily: PAL.mono }}>
          {caption}
        </MDTypography>
      )}
      <BandStateKey showDirection={list.some((r) => r.era_negative_significant != null)} />
      <MDTypography variant="caption" component="div" sx={{ ...SMALL, color: "#5E5E5E" }}>
        Bar height: the gap between the two measured power levels, in units of their own scatter.
      </MDTypography>
    </MDBox>
  );
}
