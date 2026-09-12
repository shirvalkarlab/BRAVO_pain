/**
 * What adaptive mode ruled out, drawn: per side, the setting the unconstrained search would have
 * preferred against the setting it chose inside the range adaptive mode can use, on an axis of
 * stimulation rate with the adaptive minimum marked.
 *
 * Added 2026-09-12 (page redesign, phase 2). Reads
 * `two_stage.stage1.frozen_configuration.adaptive_envelope` (the exclusions per side, the grid
 * rates excluded, the minimum rate) and `two_stage.stage1.strata` (each pulse-width group's own
 * best cell, so a reader sees the candidates the side had). Every number is the server's; the
 * chart only places them.
 *
 * Small multiples, one per side (decision 2 of the figure conventions: the unit is the side and
 * sides are never pooled). Rate on a log2 axis, as the optimiser's own figures draw it. Vertical
 * axis: predicted pain against the setting in force, in points, lower is better, 0 = the setting
 * in force. The excluded region is left of the minimum and shaded; the excluded cell is an open
 * vermillion circle, the chosen cell a filled blue disc, joined by an arrow; both carry their
 * rate, current and predicted value as direct labels. No legend.
 */
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import PAL from "views/Reports/ClosedLoopSim/palette";

import { num } from "./stimFormat";

const RATE_GRID = [10, 20, 30, 40, 55, 70, 85, 110, 125, 130, 145, 165];
const lf = (f) => Math.log2(f);

function SidePanel({ side, exclusions, strata, minRate, width }) {
  const W = width || 420, H = 170, L = 44, R = 12, T = 22, B = 30;
  const xs = [lf(RATE_GRID[0]) - 0.15, lf(RATE_GRID[RATE_GRID.length - 1]) + 0.15];
  const x = (f) => L + ((lf(f) - xs[0]) / (xs[1] - xs[0])) * (W - L - R);
  const pts = [];
  (exclusions || []).forEach((e) => {
    if (num(e.unconstrained_rate_hz) !== null) pts.push({ kind: "excluded", rate: num(e.unconstrained_rate_hz), amp: num(e.unconstrained_amp_mA), y: num(e.unconstrained_posterior_mean), pw: num(e.pw_us) });
    if (num(e.constrained_rate_hz) !== null) pts.push({ kind: "chosen", rate: num(e.constrained_rate_hz), amp: num(e.constrained_amp_mA), y: num(e.constrained_posterior_mean), pw: num(e.pw_us) });
  });
  (strata || []).filter((r) => r && r.hemisphere === side).forEach((r) => {
    if (num(r.opt_rate_hz) !== null && num(r.opt_posterior_mean) !== null) {
      pts.push({ kind: "stratum", rate: num(r.opt_rate_hz), amp: num(r.opt_amp_mA), y: num(r.opt_posterior_mean), pw: num(r.pw_us), resolved: r.optimum_resolved });
    }
  });
  const ys = pts.map((p) => p.y).filter((v) => v !== null);
  const yMax = Math.max(0.5, ...ys.map((v) => Math.abs(v))) * 1.15;
  const y = (v) => T + ((yMax - v) / (2 * yMax)) * (H - T - B);
  const ex = pts.find((p) => p.kind === "excluded"), ch = pts.find((p) => p.kind === "chosen");
  const minX = minRate != null ? x(minRate) : null;
  return (
    <svg width={W} height={H} role="img" aria-label={`${side} side: the excluded and the chosen setting`}>
      <text x={L} y={12} fontSize="11" fontWeight="600" fill="#2A2A2A">{side}</text>
      {/* excluded region: rates below the adaptive minimum */}
      {minX !== null && (
        <>
          <rect x={L} y={T} width={Math.max(0, minX - L)} height={H - T - B} fill={PAL.failFill} />
          <line x1={minX} x2={minX} y1={T} y2={H - B} stroke={PAL.fail} strokeWidth="1.4" strokeDasharray="4 3" />
          <text x={minX + 3} y={T + 9} fontSize="9" fill={PAL.fail}>{`adaptive minimum ${minRate} Hz`}</text>
        </>
      )}
      {/* zero = the setting in force */}
      <line x1={L} x2={W - R} y1={y(0)} y2={y(0)} stroke="#6A6A6A" strokeWidth="1" />
      <text x={W - R} y={y(0) - 3} fontSize="8.5" fill="#6A6A6A" textAnchor="end">0 = setting in force</text>
      <text x={4} y={T + 8} fontSize="8" fill="#9A9A9A">{`+${yMax.toFixed(1)}`}</text>
      <text x={4} y={H - B} fontSize="8" fill="#9A9A9A">{`−${yMax.toFixed(1)}`}</text>
      <text x={4} y={(T + H - B) / 2} fontSize="8" fill="#9A9A9A">pts</text>
      {/* rate axis */}
      <line x1={L} x2={W - R} y1={H - B} y2={H - B} stroke="#D8D8D8" />
      {RATE_GRID.map((f) => (
        <text key={f} x={x(f)} y={H - B + 11} fontSize="8" fill="#9A9A9A" textAnchor="middle">{f}</text>
      ))}
      <text x={W - R} y={H - 2} fontSize="8.5" fill="#6A6A6A" textAnchor="end">stimulation rate (Hz)</text>
      {/* each pulse-width group's own best cell, small grey */}
      {pts.filter((p) => p.kind === "stratum").map((p, i) => (
        <g key={`s${i}`}>
          <circle cx={x(p.rate)} cy={y(p.y)} r="3" fill="#B8B8B8" />
          <text x={x(p.rate) + 5} y={y(p.y) + 3} fontSize="8" fill="#8A8A8A">{`${p.pw != null ? `${p.pw.toFixed(0)} µs` : ""}`}</text>
        </g>
      ))}
      {/* the arrow from excluded to chosen */}
      {ex && ch && (
        <line x1={x(ex.rate)} y1={y(ex.y)} x2={x(ch.rate)} y2={y(ch.y)} stroke="#4A4A4A" strokeWidth="1.2" markerEnd={`url(#arrow-${side})`} />
      )}
      <defs>
        <marker id={`arrow-${side}`} markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
          <path d="M0,0 L8,4 L0,8 z" fill="#4A4A4A" />
        </marker>
      </defs>
      {ex && (
        <g>
          <circle cx={x(ex.rate)} cy={y(ex.y)} r="5.5" fill="none" stroke={PAL.fail} strokeWidth="2" />
          <text x={x(ex.rate)} y={y(ex.y) - 9} fontSize="9" fill={PAL.fail} textAnchor="middle">
            {`ruled out: ${ex.rate} Hz · ${ex.amp != null ? ex.amp.toFixed(1) : "—"} mA · ${ex.y >= 0 ? "+" : "−"}${Math.abs(ex.y).toFixed(2)} pts`}
          </text>
        </g>
      )}
      {ch && (
        <g>
          <circle cx={x(ch.rate)} cy={y(ch.y)} r="5.5" fill={PAL.accent} />
          <text x={x(ch.rate) + 9} y={y(ch.y) + 3} fontSize="9" fill={PAL.accent}>
            {`chosen: ${ch.rate} Hz · ${ch.amp != null ? ch.amp.toFixed(1) : "—"} mA · ${ch.y >= 0 ? "+" : "−"}${Math.abs(ch.y).toFixed(2)} pts`}
          </text>
        </g>
      )}
    </svg>
  );
}

export default function ExcludedSettingsChart({ envelope, strata }) {
  const env = envelope || {};
  const ex = env.exclusions || {};
  const sides = ["Left", "Right"].filter((s) => (Array.isArray(ex[s]) && ex[s].length) || (strata || []).some((r) => r && r.hemisphere === s));
  if (!sides.length) return null;
  const excludedRates = Array.isArray(env.grid_rates_excluded) ? env.grid_rates_excluded : [];
  return (
    <MDBox>
      <MDTypography variant="caption" component="div" sx={{ fontSize: 11, color: "#2A2A2A" }}>
        {`${num(env.n_exclusions) ?? 0} setting${num(env.n_exclusions) === 1 ? "" : "s"} ruled out because adaptive mode cannot run below ${env.min_rate_hz != null ? `${env.min_rate_hz} Hz` : "its minimum rate"}`}
        {excludedRates.length ? ` · grid rates ${excludedRates.map((r) => Number(r)).join(", ")} Hz excluded` : ""}
      </MDTypography>
      <MDBox display="flex" gap={2} flexWrap="wrap" mt={0.5}>
        {sides.map((s) => (
          <SidePanel key={s} side={s} exclusions={Array.isArray(ex[s]) ? ex[s] : []} strata={strata} minRate={num(env.min_rate_hz)} />
        ))}
      </MDBox>
      <MDTypography variant="caption" component="div" sx={{ fontSize: 10.5, color: "#6A6A6A" }}>
        Grey dots: each pulse-width group&apos;s own best cell. Predicted pain is in points against the
        setting in force; lower is better.
      </MDTypography>
    </MDBox>
  );
}
