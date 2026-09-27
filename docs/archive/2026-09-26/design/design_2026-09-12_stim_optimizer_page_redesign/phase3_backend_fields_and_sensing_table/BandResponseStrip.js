/**
 * The 18 tested band centres as bars: height is the separation between the two captured power
 * readings (in units of their own scatter, `separation_d`), the line is the minimum the check
 * requires, the bar takes the pass ink when the band responds and the fail ink when it does not,
 * and the best-separated band carries its numbers as a direct label.
 *
 * Added 2026-09-12 (page redesign, phase 3). Reads the `verdict_rows`, `min_sep_d` and
 * `best_center_hz` the band-response check now puts in its evidence; draws nothing it cannot read
 * (a row without a finite separation is an open dashed mark at zero height).
 */
import PAL from "views/Reports/ClosedLoopSim/palette";

import { num } from "./stimFormat";

export default function BandResponseStrip({ rows, minSep, best, width = 340 }) {
  const list = (Array.isArray(rows) ? rows : []).filter((r) => r && num(r.center_hz) !== null)
    .sort((a, b) => num(a.center_hz) - num(b.center_hz));
  if (!list.length) return null;
  const W = width, H = 96, L = 26, R = 8, T = 22, B = 18;
  const lo = 8, hi = 30;
  const x = (c) => L + ((c - lo) / (hi - lo)) * (W - L - R);
  const ds = list.map((r) => num(r.separation_d)).filter((v) => v !== null);
  const dMax = Math.max(1, ...ds, num(minSep) || 0) * 1.1;
  const y = (d) => T + (1 - d / dMax) * (H - T - B);
  const bestRow = best != null ? list.find((r) => Math.abs(num(r.center_hz) - Number(best)) < 1e-9) : null;
  const bw = Math.max(3, ((W - L - R) / ((hi - lo) / 1)) * 0.8);
  return (
    <svg width={W} height={H} role="img" aria-label="separation per band centre against the required minimum">
      <line x1={L} x2={W - R} y1={y(0)} y2={y(0)} stroke="#D8D8D8" />
      {num(minSep) !== null && (
        <>
          <line x1={L} x2={W - R} y1={y(num(minSep))} y2={y(num(minSep))} stroke="#4A4A4A" strokeWidth="1" strokeDasharray="3 2" />
          <text x={W - R} y={y(num(minSep)) - 2} fontSize="8" fill="#4A4A4A" textAnchor="end">{`required d ≥ ${num(minSep).toFixed(2)}`}</text>
        </>
      )}
      <text x={2} y={T + 6} fontSize="8" fill="#9A9A9A">{dMax.toFixed(1)}</text>
      <text x={2} y={y(0) + 3} fontSize="8" fill="#9A9A9A">0</text>
      <text x={2} y={(T + y(0)) / 2} fontSize="8" fill="#9A9A9A">d</text>
      {[8, 12, 16, 20, 24, 28].map((t) => (
        <text key={t} x={x(t)} y={H - 6} fontSize="8" fill="#9A9A9A" textAnchor="middle">{t}</text>
      ))}
      <text x={W - R} y={H - 6} fontSize="8" fill="#6A6A6A" textAnchor="end">Hz</text>
      {list.map((r) => {
        const c = num(r.center_hz), d = num(r.separation_d);
        if (d === null) {
          return <circle key={c} cx={x(c)} cy={y(0) - 4} r="3" fill="none" stroke={PAL.neutral} strokeDasharray="2 2" />;
        }
        const ink = r.responds === true ? PAL.pass : (r.responds === false ? PAL.fail : PAL.neutral);
        return (
          <rect key={c} x={x(c) - bw / 2} y={y(Math.min(d, dMax))} width={bw} height={Math.max(0.5, y(0) - y(Math.min(d, dMax)))}
            fill={ink} rx="1" />
        );
      })}
      {bestRow && (
        <text x={Math.min(x(num(bestRow.center_hz)), W - R - 150)} y={T - 8} fontSize="9" fill="#1A1A1A">
          {`best ${num(bestRow.center_hz).toFixed(1)} Hz · d ${num(bestRow.separation_d) === null ? "—" : num(bestRow.separation_d).toFixed(2)}`
            + (num(bestRow.power_low) !== null && num(bestRow.power_high) !== null
              ? ` · ${num(bestRow.power_low).toFixed(1)} → ${num(bestRow.power_high).toFixed(1)} units at ${num(bestRow.amp_low_mA) === null ? "—" : num(bestRow.amp_low_mA).toFixed(1)} → ${num(bestRow.amp_high_mA) === null ? "—" : num(bestRow.amp_high_mA).toFixed(1)} mA`
              : "")}
        </text>
      )}
    </svg>
  );
}
