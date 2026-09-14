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
 * sides are never pooled). Vertical axis: predicted pain against the setting in force, in points,
 * lower is better, 0 = the setting in force. The excluded region is left of the minimum and
 * shaded; the excluded cell is an open vermillion circle, the chosen cell a filled blue disc,
 * joined by an arrow.
 *
 * Redrawn 2026-09-12 after the PI's review ("UNREADABLE"): each side 600 x 250 px, the two sides
 * side by side when the card is wide enough and stacked otherwise; the rate axis is CATEGORICAL,
 * one equal slot per grid rate, because on a log axis the grid's 110, 125, 130, 145 and 165 Hz
 * sit so close that their tick labels ran into one another ("110 1380145 165"); every label is
 * outside the plot area: the adaptive minimum is named once at the top of its line, and the
 * ruled-out and chosen settings are named in a label band above the plot, on separate rows, each
 * joined to its point by a leader line, so the two can never overlap whatever the data. A legend
 * beneath says what each mark means.
 */
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import PAL from "views/Reports/ClosedLoopSim/palette";

import { num } from "./stimFormat";
import { TYPE, SMALL } from "./typeScale";

/** The optimiser's rate grid (`StimOptimizer/routines/plots.py`, `FREQ_GRID`), in Hz. */
const RATE_GRID = [10, 20, 30, 40, 55, 70, 85, 110, 125, 130, 145, 165];
const lf = (f) => Math.log2(f);

const fmtPts = (v) => `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(2)} pts`;
const fmtMa = (v) => (v != null ? `${v.toFixed(1)} mA` : "— mA");

function SidePanel({ side, exclusions, strata, minRate, width }) {
  // T holds three label rows above the plot (the ruled-out setting, the chosen setting, then the
  // adaptive minimum directly at the top of its line); B holds the tick labels and the axis title.
  const W = width || 600, H = 250, L = 64, R = 20, T = 62, B = 44;
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
  // The categorical rate axis: the grid rates, plus any rate the data carry that is not on the
  // grid (so a point is never placed off the axis), one equal slot each.
  const rates = [...new Set([...RATE_GRID, ...pts.map((p) => p.rate), ...(minRate != null ? [minRate] : [])]
    .filter((v) => v !== null && Number.isFinite(v)))].sort((a, b) => a - b);
  const slot = (W - L - R) / rates.length;
  const xi = (f) => {
    const i = rates.indexOf(f);
    if (i >= 0) return L + (i + 0.5) * slot;
    // not a grid rate: interpolate between its neighbours in log2 space
    let j = rates.findIndex((r) => r > f);
    if (j <= 0) return L + (j === 0 ? 0.5 : rates.length - 0.5) * slot;
    const a = rates[j - 1], b = rates[j];
    return L + (j - 0.5 + (lf(f) - lf(a)) / (lf(b) - lf(a))) * slot;
  };
  const ys = pts.map((p) => p.y).filter((v) => v !== null);
  const yMax = Math.max(0.5, ...ys.map((v) => Math.abs(v))) * 1.15;
  const y = (v) => T + ((yMax - v) / (2 * yMax)) * (H - T - B);
  // A point without a predicted value cannot be placed, so it is not drawn.
  const ex = pts.find((p) => p.kind === "excluded" && p.y !== null);
  const ch = pts.find((p) => p.kind === "chosen" && p.y !== null);
  // The minimum sits at the left edge of its own slot: every rate below it is excluded.
  const minX = minRate != null ? xi(minRate) - slot / 2 : null;
  // The three label rows above the plot. The minimum's line starts just under its own label, so
  // it never crosses the two rows of text above it.
  const ROW1 = 16, ROW2 = 34, ROW3 = 54;
  const leader = (x1, y1, x2, y2, ink) => (
    <line x1={x1} y1={y1} x2={x2} y2={y2} stroke={ink} strokeWidth="1" strokeDasharray="2 2" />
  );
  return (
    <svg width={W} height={H} role="img" aria-label={`${side} side: the excluded and the chosen setting`}>
      <text x={4} y={ROW1} fontSize={TYPE.body} fontWeight="700" fill="#2A2A2A">{side}</text>
      {/* excluded region: rates below the adaptive minimum, the line named once at its top */}
      {minX !== null && (
        <>
          <rect x={L} y={T} width={Math.max(0, minX - L)} height={H - T - B} fill={PAL.failFill} />
          <line x1={minX} x2={minX} y1={ROW3 + 4} y2={H - B} stroke={PAL.fail} strokeWidth="1.4" strokeDasharray="4 3" />
          <text x={minX + 5} y={ROW3} fontSize={TYPE.axis} fill={PAL.fail}>{`adaptive minimum ${minRate} Hz`}</text>
        </>
      )}
      {/* the two settings, named above the plot on rows of their own and joined to their points:
          the ruled-out one at the left (its point is left of the minimum), the chosen one at the
          right, so the two labels cannot overlap whatever the data */}
      {ex && (
        <>
          {leader(L + 4, ROW1 + 3, xi(ex.rate), y(ex.y) - 8, PAL.fail)}
          <text x={L} y={ROW1} fontSize={TYPE.small} fill={PAL.fail} fontWeight="600">
            {`ruled out: ${ex.rate} Hz · ${fmtMa(ex.amp)} · ${fmtPts(ex.y)}`}
          </text>
        </>
      )}
      {ch && (
        <>
          {leader(W - R - 4, ROW2 + 3, xi(ch.rate), y(ch.y) - 8, PAL.accent)}
          <text x={W - R} y={ROW2} fontSize={TYPE.small} fill={PAL.accent} fontWeight="600" textAnchor="end">
            {`chosen: ${ch.rate} Hz · ${fmtMa(ch.amp)} · ${fmtPts(ch.y)}`}
          </text>
        </>
      )}
      {/* zero = the setting in force; the y axis */}
      <line x1={L} x2={W - R} y1={y(0)} y2={y(0)} stroke="#6A6A6A" strokeWidth="1" />
      <line x1={L} x2={L} y1={T} y2={H - B} stroke="#D8D8D8" />
      <text x={L - 8} y={T + 4} fontSize={TYPE.axis} fill="#7A7A7A" textAnchor="end">{`+${yMax.toFixed(1)}`}</text>
      <text x={L - 8} y={y(0) + 4} fontSize={TYPE.axis} fill="#7A7A7A" textAnchor="end">0</text>
      <text x={L - 8} y={H - B} fontSize={TYPE.axis} fill="#7A7A7A" textAnchor="end">{`−${yMax.toFixed(1)}`}</text>
      <text x={14} y={(T + H - B) / 2} fontSize={TYPE.axis} fill="#7A7A7A" textAnchor="middle"
        transform={`rotate(-90 14 ${(T + H - B) / 2})`}>predicted pain (pts)</text>
      {/* rate axis, one equal slot per grid rate */}
      <line x1={L} x2={W - R} y1={H - B} y2={H - B} stroke="#D8D8D8" />
      {rates.map((f) => (
        <text key={f} x={xi(f)} y={H - B + 16} fontSize={TYPE.axis} fill="#7A7A7A" textAnchor="middle">{f}</text>
      ))}
      <text x={(L + W - R) / 2} y={H - 4} fontSize={TYPE.axis} fill="#5E5E5E" textAnchor="middle">stimulation rate (Hz)</text>
      {/* each pulse-width group's own best cell, small grey, its pulse width beside it */}
      {pts.filter((p) => p.kind === "stratum").map((p, i) => (
        <g key={`s${i}`}>
          <circle cx={xi(p.rate)} cy={y(p.y)} r="3.5" fill="#B8B8B8" />
          <text x={xi(p.rate) + 9} y={y(p.y) + 4} fontSize={TYPE.axis} fill="#8A8A8A">{p.pw != null ? `${p.pw.toFixed(0)} µs` : ""}</text>
        </g>
      ))}
      {/* the arrow from excluded to chosen */}
      {ex && ch && (
        <line x1={xi(ex.rate)} y1={y(ex.y)} x2={xi(ch.rate)} y2={y(ch.y)} stroke="#4A4A4A" strokeWidth="1.2" markerEnd={`url(#arrow-${side})`} />
      )}
      <defs>
        <marker id={`arrow-${side}`} markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
          <path d="M0,0 L8,4 L0,8 z" fill="#4A4A4A" />
        </marker>
      </defs>
      {ex && <circle cx={xi(ex.rate)} cy={y(ex.y)} r="6.5" fill="none" stroke={PAL.fail} strokeWidth="2" />}
      {ch && <circle cx={xi(ch.rate)} cy={y(ch.y)} r="6.5" fill={PAL.accent} />}
    </svg>
  );
}

function Legend() {
  const item = { display: "inline-flex", alignItems: "center", gap: 6, whiteSpace: "nowrap" };
  const sw = (children) => <svg width="16" height="14" aria-hidden="true">{children}</svg>;
  return (
    <MDBox display="flex" flexWrap="wrap" columnGap={2.5} rowGap={0.5} mt={0.8} sx={SMALL}>
      <span style={item}>{sw(<circle cx="8" cy="7" r="5" fill="none" stroke={PAL.fail} strokeWidth="2" />)} ruled out: the unconstrained search&apos;s preference, below the adaptive minimum</span>
      <span style={item}>{sw(<circle cx="8" cy="7" r="5" fill={PAL.accent} />)} chosen: the best setting adaptive mode can use</span>
      <span style={item}>{sw(<circle cx="8" cy="7" r="3.5" fill="#B8B8B8" />)} each pulse-width group&apos;s own best cell</span>
      <span style={item}>{sw(<rect x="1" y="1" width="14" height="12" fill={PAL.failFill} stroke={PAL.fail} strokeDasharray="2 2" />)} rates adaptive mode cannot run</span>
      <span style={item}>{sw(<line x1="1" x2="15" y1="7" y2="7" stroke="#6A6A6A" />)} 0 = the setting in force; predicted pain in points, lower is better</span>
    </MDBox>
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
      <MDTypography variant="caption" component="div" sx={{ fontSize: TYPE.body, color: "#2A2A2A" }}>
        {`${num(env.n_exclusions) ?? 0} setting${num(env.n_exclusions) === 1 ? "" : "s"} ruled out because adaptive mode cannot run below ${env.min_rate_hz != null ? `${env.min_rate_hz} Hz` : "its minimum rate"}`}
        {excludedRates.length ? ` · grid rates ${excludedRates.map((r) => Number(r)).join(", ")} Hz excluded` : ""}
      </MDTypography>
      {/* 600 px per side: side by side when the card is at least about 1230 px wide, else stacked. */}
      <MDBox display="flex" columnGap={3} rowGap={2} flexWrap="wrap" mt={1}>
        {sides.map((s) => (
          <SidePanel key={s} side={s} exclusions={Array.isArray(ex[s]) ? ex[s] : []} strata={strata} minRate={num(env.min_rate_hz)} />
        ))}
      </MDBox>
      <Legend />
    </MDBox>
  );
}
