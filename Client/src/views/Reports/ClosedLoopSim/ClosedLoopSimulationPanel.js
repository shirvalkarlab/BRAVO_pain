/**
 * CL-DBS simulations (Phase 8 of the 2026-09-11 redesign; T2, 2026-09-13, replays TWO timing
 * regimes rather than one). The device's Dual Threshold controller run over this participant's own
 * recorded band power, three response models, drawn rather than described:
 *
 *   M0  replayed over the power as recorded (the card this one replaces showed exactly this);
 *   M1  the loop closed through the fitted straight-line response of power to amplitude
 *       (M2, the peaked response, takes its place once a bend is established);
 *   M3  M1 rerun with the response refitted on runs resampled with replacement -- the interval.
 *
 * TWO TIMING REGIMES, labelled and never silently swapped (contest_2026-09-13_SYNTHESIS.md
 * section 4, T2): "As programmed today" replays the averaging, onset, blanking and ramp durations
 * the device's own newest session report shows programmed on this candidate's hemisphere; "Record-
 * derived recommendation" replays the participant's own measured recommendation (decision 150). A
 * small toggle picks which one the three figures below draw; a summary line always shows both
 * regimes' switch rate and how many of those switches were undone within one onset, so a reader
 * never has to trust one number over the other from memory.
 *
 * FIGURES, in the order the question is asked (the panel that answers it is the largest):
 *   A  the longest continuous stretch: the amplitude each model commands, with the recorded
 *      amplitude and the limits, over the band power each model sees, with the thresholds;
 *   B  every summary number as a dot plot, M0 against the closed loop, with M3's interval --
 *      "compared to what?" answered on one axis;
 *   C  where the amplitude sits (a histogram per model) and the response curve the loop is
 *      closed through, with the fitted range and any wrong-side stretch marked.
 *
 * HOUSE RULES FOLLOWED: the headline is derived from the numbers at render time; three states
 * (a number, an interval, "not assessable") are never collapsed; Plotly nodes are purged on
 * unmount only, with a constant uirevision; every figure is drawn from the stored payload and no
 * number is recomputed here. The card is dashed because everything in it is modelled.
 */
import { useEffect, useRef, useState } from "react";
import Plotly from "plotly.js-dist";
import { Card } from "@mui/material";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import { PAL } from "./palette";
import { TYPE, WRAP, CARD } from "assets/theme/base/tokens";
import { plotlyLayout, directLabel } from "views/Reports/figureStyle";
import { fmtNum, fmtPct } from "./deployFormat";
import Fold from "./Fold";
import PanelStaleNote from "./PanelStaleNote";

const isNum = (v) => v != null && Number.isFinite(Number(v));
// Marks: the replay in the context grey, the closed loop in the series blue; fills from the tokens.
const INK_M0 = PAL.gray;
const INK_ACTIVE = PAL.series;
const FILL_M3 = PAL.accentFill;
const FILL_WRONG = PAL.warnFill;
const FILL_FITTED = PAL.fillMuted;
const AXIS = plotlyLayout().xaxis;

/** The model names in words (SPEC section 6: no M-codes in visible text). */
const MODEL_WORDS = { M0: "as recorded", M1: "straight-line response", M2: "peaked response",
  M3: "range over resampled runs" };

/**
 * The words after the controller's limits (decision 306). The simulation runs between the limits
 * the decision card recommends: the capture currents, each held at or below the participant's safe
 * ceiling; `amp_limit_note` is the server's sentence when the ceiling lowered one of them. A stored
 * simulation from before the ceiling carries no such field and reads as before.
 */
export function limitsSourceWords(P) {
  return P && P.amp_limit_note ? "the capture range, capped at the safe ceiling" : "the capture range, held";
}

function modelLabel(name) {
  return { M0: "replay, power as recorded", M1: "loop closed, straight-line response",
    M2: "loop closed, peaked response" }[name] || name;
}

/** The sentence that states what the numbers show, built from them (never hardcoded). */
export function headline(sim) {
  const body = headlineBody(sim);
  // C3 (2026-09-15 review, decision 200): the record-derived regime rests on timing values the
  // parameter card grades Low (the two transitions and the detection blanking on RCS08); the
  // backend names them per regime (`timing_qualifier`) and the headline says so first.
  const q = sim && sim.timing_qualifier;
  if (!body || !q) return body;
  return `${q.charAt(0).toUpperCase()}${q.slice(1)}: ${body}`;
}

function headlineBody(sim) {
  if (!sim) return null;
  if (sim.refused) return "The simulation could not run on this record";
  const active = sim.models && sim.models[sim.active_model];
  const base = sim.models && sim.models.M0;
  const curve = sim.curves && sim.curves[sim.active_model];
  if (!active || !base) return "The simulation ran but reported no models";
  if (!curve || curve.kind === "none") {
    // the fit's own verdict says why (too few points, one visit, no movement): three states,
    // never a silent zero
    const why = curve && curve.note ? ` (${curve.note})` : "";
    return `No response curve can be fitted for this band yet${why}, so the loop cannot be closed: `
      + "the closed-loop model equals the replay";
  }
  const m3 = sim.models.M3 && sim.models.M3.intervals && sim.models.M3.intervals.frac_time_at_upper;
  const iv = m3 ? ` (runs resampled: ${fmtPct(m3[0], 0)} to ${fmtPct(m3[1], 0)})` : "";
  const dir = curve.slope_per_mA < 0 ? "falls" : "rises";
  return `Closing the loop moves time at the upper amplitude limit from ${fmtPct(base.frac_time_at_upper, 1)} `
    + `to ${fmtPct(active.frac_time_at_upper, 1)}${iv}; the band ${dir} ${fmtNum(Math.abs(curve.slope_per_mA), 2)} `
    + `device units per mA (${curve.n_points} points, ${curve.n_runs} runs)`;
}

function drawTrajectory(gd, sim, hemisphere) {
  const d = sim.drawn && sim.drawn[0];
  if (!d) { Plotly.purge(gd); return false; }
  const act = sim.active_model;
  const mins = d.t_s.map((v) => v / 60);
  const P = sim.params || {};
  const traces = [];
  if (d.m3_amp_band) {
    traces.push({ x: mins, y: d.m3_amp_band[0], type: "scatter", mode: "lines", line: { width: 0 },
      hoverinfo: "skip", showlegend: false, xaxis: "x", yaxis: "y" });
    traces.push({ x: mins, y: d.m3_amp_band[1], type: "scatter", mode: "lines", line: { width: 0 },
      fill: "tonexty", fillcolor: FILL_M3, name: "range over resampled runs (2.5 to 97.5%)",
      hoverinfo: "skip", xaxis: "x", yaxis: "y" });
  }
  traces.push({ x: mins, y: d.a_obs, type: "scatter", mode: "lines", name: "amplitude the device delivered",
    line: { color: PAL.ink, width: 0.8, dash: "dot" }, xaxis: "x", yaxis: "y",
    hovertemplate: "recorded %{y:.2f} mA<extra></extra>" });
  traces.push({ x: mins, y: d.models.M0.amp, type: "scatter", mode: "lines", name: modelLabel("M0"),
    line: { color: INK_M0, width: 1.4, dash: "dash" }, xaxis: "x", yaxis: "y",
    hovertemplate: "as recorded %{y:.2f} mA<extra></extra>" });
  traces.push({ x: mins, y: d.models[act].amp, type: "scatter", mode: "lines", name: modelLabel(act),
    line: { color: INK_ACTIVE, width: 1.8 }, xaxis: "x", yaxis: "y",
    hovertemplate: `loop closed %{y:.2f} mA<extra></extra>` });
  traces.push({ x: mins, y: d.p_obs, type: "scatter", mode: "lines", name: "band power as recorded",
    line: { color: INK_M0, width: 1.0 }, xaxis: "x", yaxis: "y2",
    hovertemplate: "recorded %{y:.1f}<extra></extra>" });
  traces.push({ x: mins, y: d.models[act].p_sim, type: "scatter", mode: "lines",
    name: "band power the closed loop sees", line: { color: INK_ACTIVE, width: 1.2 },
    xaxis: "x", yaxis: "y2", hovertemplate: "loop closed %{y:.1f}<extra></extra>" });
  const hline = (y, yref, dash) => ({ type: "line", xref: "paper", x0: 0, x1: 1, yref, y0: y, y1: y,
    line: { color: PAL.thresholdLine, width: 0.8, dash } });
  // Lines are labelled at their right end (SPEC section 3.2), not in a legend box.
  const lastX = mins.length ? mins[mins.length - 1] : 0;
  const lastOf = (arr) => (arr && arr.length ? arr[arr.length - 1] : null);
  const ends = [
    [lastOf(d.a_obs), "y", "delivered", PAL.ink],
    [lastOf(d.models.M0.amp), "y", "as recorded", PAL.ink3],
    [lastOf(d.models[act].amp), "y", "loop closed", INK_ACTIVE],
    [lastOf(d.p_obs), "y2", "power as recorded", PAL.ink3],
    [lastOf(d.models[act].p_sim), "y2", "power, loop closed", INK_ACTIVE],
  ].filter(([y]) => isNum(y)).map(([y, yref, text, color]) => ({ ...directLabel(lastX, y, text, color), yref }));
  const layout = plotlyLayout({
    margin: { l: 58, r: 132, t: 16, b: 48 }, height: 380, hovermode: "x unified",
    uirevision: "cl-sim-traj", showlegend: false,
    xaxis: { ...AXIS, title: { text: "minutes from the start of the stretch", standoff: 6 }, domain: [0, 1] },
    yaxis: { ...AXIS, domain: [0.56, 1], title: { text: `${hemisphere || ""} current (mA)`.trim(), standoff: 8 },
      range: [P.amp_low_mA - 0.05 * (P.amp_high_mA - P.amp_low_mA), P.amp_high_mA + 0.05 * (P.amp_high_mA - P.amp_low_mA)] },
    yaxis2: { ...AXIS, domain: [0, 0.44], title: { text: "band power (device units, LSB)", standoff: 8 } },
    shapes: [hline(P.amp_low_mA, "y", "solid"), hline(P.amp_high_mA, "y", "solid"),
      hline(P.lower, "y2", "dash"), hline(P.upper, "y2", "dash")],
    annotations: [
      ...ends,
      { xref: "paper", x: 1, yref: "y", y: P.amp_high_mA, text: "upper limit", showarrow: false, xanchor: "right", yanchor: "bottom", font: { size: PAL.fs.caption, color: PAL.ink2 } },
      { xref: "paper", x: 1, yref: "y", y: P.amp_low_mA, text: "lower limit", showarrow: false, xanchor: "right", yanchor: "top", font: { size: PAL.fs.caption, color: PAL.ink2 } },
      { xref: "paper", x: 1, yref: "y2", y: P.upper, text: "upper threshold", showarrow: false, xanchor: "right", yanchor: "bottom", font: { size: PAL.fs.caption, color: PAL.ink2 } },
      { xref: "paper", x: 1, yref: "y2", y: P.lower, text: "lower threshold", showarrow: false, xanchor: "right", yanchor: "top", font: { size: PAL.fs.caption, color: PAL.ink2 } },
    ],
  });
  Plotly.react(gd, traces, layout, PAL.MODEBAR);
  return true;
}

function drawComparison(gd, sim) {
  const act = sim.active_model;
  const A = sim.models[act]; const B = sim.models.M0;
  const iv = (sim.models.M3 && sim.models.M3.intervals) || {};
  const rows = [
    ["frac_time_at_upper", "time at the upper amplitude limit"],
    ["frac_time_at_lower", "time at the lower amplitude limit"],
    ["frac_time_above", "power above the upper threshold"],
    ["frac_time_between", "power between the thresholds"],
    ["frac_time_below", "power below the lower threshold"],
  ];
  if (sim.wrong_side && sim.wrong_side.range_mA) rows.push(["frac_time_wrong_side", "amplitude on the wrong side of the peak"]);
  const labels = rows.map((r) => r[1]);
  const traces = [];
  const dot = (xs, ys, name, filled, xaxis, ivs) => ({
    x: xs, y: ys, type: "scatter", mode: "markers", name, xaxis, yaxis: "y", showlegend: false,
    marker: { size: 9, color: filled ? INK_ACTIVE : PAL.surface, line: { color: filled ? INK_ACTIVE : INK_M0, width: 1.6 } },
    error_x: ivs ? { type: "data", symmetric: false, array: ivs.map((v, i) => (v ? v[1] - xs[i] : 0)),
      arrayminus: ivs.map((v, i) => (v ? xs[i] - v[0] : 0)), color: INK_ACTIVE, thickness: 1.2, width: 0 } : undefined,
    hovertemplate: `${MODEL_WORDS[name] || "loop closed"} %{x:.3~f}<extra></extra>`,
  });
  const pct = (v) => (isNum(v) ? 100 * v : null);
  traces.push(dot(rows.map((r) => pct(B[r[0]])), labels, "M0", false, "x"));
  traces.push(dot(rows.map((r) => pct(A[r[0]])), labels, act, true, "x",
    rows.map((r) => (iv[r[0]] ? [pct(iv[r[0]][0]), pct(iv[r[0]][1])] : null))));
  traces.push(dot([B.transitions_per_hour], ["state changes per hour"], "M0", false, "x2"));
  traces.push(dot([A.transitions_per_hour], ["state changes per hour"], act, true, "x2",
    [iv.transitions_per_hour || null]));
  traces.push(dot([B.longest_run_at_upper_s / 60], ["longest stretch at the upper limit"], "M0", false, "x3"));
  traces.push(dot([A.longest_run_at_upper_s / 60], ["longest stretch at the upper limit"], act, true, "x3",
    [iv.longest_run_at_upper_s ? iv.longest_run_at_upper_s.map((v) => v / 60) : null]));
  const layout = plotlyLayout({
    margin: { l: 230, r: 16, t: 32, b: 48 }, height: 210 + 18 * rows.length,
    uirevision: "cl-sim-compare", showlegend: false,
    yaxis: { ...AXIS, showline: false, ticks: "", categoryorder: "array",
      categoryarray: [...labels, "state changes per hour", "longest stretch at the upper limit"].reverse(),
      tickfont: { size: PAL.fs.caption } },
    xaxis: { ...AXIS, domain: [0, 0.56], title: { text: "% of the device's adjustment steps", standoff: 4 }, rangemode: "tozero" },
    xaxis2: { ...AXIS, domain: [0.62, 0.79], title: { text: "per hour", standoff: 4 }, rangemode: "tozero" },
    xaxis3: { ...AXIS, domain: [0.85, 1], title: { text: "minutes", standoff: 4 }, rangemode: "tozero" },
    annotations: [
      { xref: "paper", yref: "paper", x: 0, y: 1.06, xanchor: "left", showarrow: false, font: { size: PAL.fs.caption },
        text: `○ as recorded   ● loop closed (${MODEL_WORDS[act] || act})`
          + (sim.models.M3 ? `   — range over ${sim.models.M3.n_replicates} resampled runs` : "") },
    ],
  });
  Plotly.react(gd, traces, layout, PAL.MODEBAR);
}

function drawDistributionAndCurve(gd, sim) {
  const act = sim.active_model;
  const P = sim.params || {};
  const edges = sim.amp_hist_edges_mA || [];
  const mids = edges.slice(0, -1).map((e, i) => 0.5 * (e + edges[i + 1]));
  const norm = (h) => { const s = h.reduce((a, b) => a + b, 0) || 1; return h.map((v) => 100 * v / s); };
  const traces = [
    { x: mids, y: norm(sim.models.M0.amp_hist), type: "scatter", mode: "lines", line: { shape: "hvh", color: INK_M0, width: 1.4, dash: "dash" },
      name: "as recorded", xaxis: "x", yaxis: "y", hovertemplate: "as recorded %{y:.1f} %<extra></extra>" },
    { x: mids, y: norm(sim.models[act].amp_hist), type: "scatter", mode: "lines", line: { shape: "hvh", color: INK_ACTIVE, width: 1.8 },
      name: "loop closed", xaxis: "x", yaxis: "y", hovertemplate: "loop closed %{y:.1f} %<extra></extra>" },
  ];
  const curve = sim.curves && sim.curves[act];
  const shapes = []; const annotations = [];
  if (curve && curve.kind !== "none" && isNum(P.amp_low_mA) && isNum(P.amp_high_mA)) {
    const xs = []; const n = 80;
    for (let i = 0; i <= n; i += 1) xs.push(P.amp_low_mA + (P.amp_high_mA - P.amp_low_mA) * i / n);
    const g = (x) => {
      if (curve.kind === "linear") return curve.slope_per_mA * x;
      const q = curve.quad_per_mA2 * x * x + curve.quad_lin_per_mA * x;
      if (isNum(curve.peak_mA) && isNum(curve.post_peak_slope_per_mA) && x > curve.peak_mA) {
        const gp = curve.quad_per_mA2 * curve.peak_mA ** 2 + curve.quad_lin_per_mA * curve.peak_mA;
        return gp + curve.post_peak_slope_per_mA * (x - curve.peak_mA);
      }
      return q;
    };
    const g0 = g(P.amp_low_mA);
    const ys = xs.map((x) => g(x) - g0);
    const m3s = sim.models.M3 && sim.models.M3.slope_interval_per_mA;
    if (m3s && curve.kind === "linear") {
      traces.push({ x: xs, y: xs.map((x) => m3s[0] * (x - P.amp_low_mA)), type: "scatter", mode: "lines",
        line: { width: 0 }, hoverinfo: "skip", showlegend: false, xaxis: "x2", yaxis: "y2" });
      traces.push({ x: xs, y: xs.map((x) => m3s[1] * (x - P.amp_low_mA)), type: "scatter", mode: "lines",
        line: { width: 0 }, fill: "tonexty", fillcolor: FILL_M3, hoverinfo: "skip", showlegend: false,
        xaxis: "x2", yaxis: "y2" });
    }
    traces.push({ x: xs, y: ys, type: "scatter", mode: "lines", name: "fitted response", showlegend: false,
      line: { color: INK_ACTIVE, width: 1.8 }, xaxis: "x2", yaxis: "y2",
      hovertemplate: "%{x:.2f} mA → %{y:+.1f} units<extra></extra>" });
    if (isNum(curve.fitted_lo_mA) && isNum(curve.fitted_hi_mA)) {
      shapes.push({ type: "rect", xref: "x2", yref: "paper", x0: Math.max(curve.fitted_lo_mA, P.amp_low_mA),
        x1: Math.min(curve.fitted_hi_mA, P.amp_high_mA), y0: 0, y1: 1, fillcolor: FILL_FITTED, line: { width: 0 }, layer: "below" });
    }
    if (sim.wrong_side && sim.wrong_side.range_mA) {
      const [a, b] = sim.wrong_side.range_mA;
      shapes.push({ type: "rect", xref: "x2", yref: "paper", x0: a, x1: b, y0: 0, y1: 1, fillcolor: FILL_WRONG,
        line: { width: 0 }, layer: "below" });
      annotations.push({ xref: "x2", yref: "paper", x: 0.5 * (a + b), y: 0.96, text: "▲ power rises with current: positive feedback",
        showarrow: false, font: { size: PAL.fs.caption, color: PAL.warnText } });
    }
    if (isNum(curve.peak_mA)) {
      shapes.push({ type: "line", xref: "x2", yref: "paper", x0: curve.peak_mA, x1: curve.peak_mA, y0: 0, y1: 1,
        line: { color: PAL.thresholdLine, width: 0.8, dash: "dot" } });
    }
  } else {
    annotations.push({ xref: "x2 domain", yref: "y2 domain", x: 0.5, y: 0.5, showarrow: false,
      font: { size: PAL.fs.caption, color: PAL.ink3 }, text: "no response curve stored yet" });
  }
  const layout = plotlyLayout({
    margin: { l: 56, r: 16, t: 32, b: 48 }, height: 250, uirevision: "cl-sim-dist", showlegend: false,
    xaxis: { ...AXIS, domain: [0, 0.44], title: { text: "current the device would command (mA)", standoff: 4 }, range: [P.amp_low_mA, P.amp_high_mA] },
    yaxis: { ...AXIS, title: { text: "% of adjustment steps", standoff: 6 }, rangemode: "tozero" },
    xaxis2: { ...AXIS, domain: [0.56, 1], title: { text: "current (mA)", standoff: 4 }, range: [P.amp_low_mA, P.amp_high_mA], anchor: "y2" },
    yaxis2: { ...AXIS, anchor: "x2", title: { text: "power change from the lower limit", standoff: 6 } },
    shapes, annotations: [
      ...annotations,
      { xref: "paper", yref: "paper", x: 0, y: 1.1, xanchor: "left", showarrow: false, font: { size: PAL.fs.caption },
        text: "dashed: as recorded · solid: loop closed · where the current sits" },
      { xref: "paper", yref: "paper", x: 0.56, y: 1.08, xanchor: "left", showarrow: false, font: { size: PAL.fs.caption },
        text: `the response the loop is closed through${curve && curve.kind !== "none" ? " (grey: currents the fit rests on)" : ""}` },
    ],
  });
  Plotly.react(gd, traces, layout, PAL.MODEBAR);
}

function Caption({ children }) {
  return (
    <MDTypography variant="caption" sx={{ ...TYPE.body, display: "block", color: PAL.ink2, mt: 0.5, maxWidth: "68ch" }}>
      {children}
    </MDTypography>
  );
}

function Line({ children }) {
  return (
    <MDTypography variant="caption" sx={{ ...TYPE.body, display: "block", color: PAL.ink, mt: 0.25 }}>
      {children}
    </MDTypography>
  );
}

const RUN_KEYS = ["programmed", "recommended"];
const RUN_TAB_LABEL = { programmed: "As programmed today", recommended: "Record-derived recommendation" };

/** The switch rate and how many of those switches were undone within one onset, for the base
 * replay (M0 -- the recorded power, no response curve), under one timing regime. This is the
 * quantity the contest's own held-out proof reports (contest_2026-09-13_SYNTHESIS.md section 2),
 * so it is shown for BOTH regimes side by side regardless of which one the figures below draw. */
function RunSummaryRow({ label, run, active, onClick }) {
  const m0 = run && !run.refused && run.models ? run.models.M0 : null;
  const params = run && run.timing_params_ms;
  return (
    <MDBox onClick={onClick} sx={{
      flex: "1 1 260px", minWidth: 240, p: 1.5, borderRadius: "4px", cursor: onClick ? "pointer" : "default",
      border: `1px solid ${active ? PAL.accent : PAL.rule}`,
      backgroundColor: active ? PAL.accentFill : PAL.surface,
    }}>
      <MDTypography variant="caption" sx={{ ...TYPE.body, display: "block", fontWeight: 600, color: active ? PAL.accent : PAL.ink2 }}>
        {label}{active ? " (shown below)" : ""}
      </MDTypography>
      {run && run.refused ? (
        <Caption>{run.absent_reason || "could not be replayed at this timing"}</Caption>
      ) : m0 ? (
        <>
          <Line>{`${fmtNum(m0.transitions_per_hour, 1)} switches an hour · ${m0.n_transitions_undone} undone within one wait before switching (${fmtNum(m0.undone_per_hour, 1)} an hour)`}</Line>
          <Line>{`at upper limit ${fmtPct(m0.frac_time_at_upper, 1)} · at lower ${fmtPct(m0.frac_time_at_lower, 1)} · mean ${fmtNum(m0.mean_amplitude_mA, 2)} mA`}</Line>
        </>
      ) : (
        <Caption>no run stored for this timing</Caption>
      )}
      {params ? (
        <Line>{`averaging ${fmtNum(params.averaging_ms, 0)} ms · wait before switching ${fmtNum(params.onset_ms, 0)} ms · pause after it ${fmtNum(params.detection_blanking_ms, 0)} ms · ramps ${fmtNum(params.transition_up_ms, 0)}/${fmtNum(params.transition_down_ms, 0)} ms`}</Line>
      ) : null}
    </MDBox>
  );
}

/** Printed in place of a controller number while the device has not allowed the configuration. */
export const WITHHELD_WORDS = "withheld: the device has not allowed this configuration";

export default function ClosedLoopSimulationPanel({ sim, hemisphere, contactLabel, bandCandidate,
  deviceAllows = false }) {
  const { data, loading, err, stale, staleReasons, recompute, bandMismatch } = sim
    || { data: null, loading: false, err: null };
  const runs = (data && data.timing_runs) || {};
  const hasAnyRun = RUN_KEYS.some((k) => runs[k] && !runs[k].refused && runs[k].models && runs[k].models.M0);
  const [selected, setSelected] = useState("recommended");
  // if the preferred regime could not be replayed but the other one could, show the one that can
  const effective = (runs[selected] && !runs[selected].refused && runs[selected].models && runs[selected].models.M0)
    ? selected : RUN_KEYS.find((k) => runs[k] && !runs[k].refused && runs[k].models && runs[k].models.M0) || selected;
  const run = runs[effective];

  const trajRef = useRef(null); const cmpRef = useRef(null); const distRef = useRef(null);

  useEffect(() => {
    if (!run || run.refused || !run.models || !run.models.M0) return;
    if (trajRef.current) drawTrajectory(trajRef.current, run, hemisphere);
    if (cmpRef.current) drawComparison(cmpRef.current, run);
    if (distRef.current) drawDistributionAndCurve(distRef.current, run);
  }, [run, hemisphere]);
  // purge on unmount only: cleanup on every redraw would destroy the figures the reader is looking at
  useEffect(() => () => {
    [trajRef, cmpRef, distRef].forEach((r) => { if (r.current) Plotly.purge(r.current); });
  }, []);

  const title = "What the automatic adjustment would have done: simulated, not measured, decides nothing";
  // The page hands in the chosen band, which carries `contact`; `channel` is the request's spelling.
  const bcContact = bandCandidate && (bandCandidate.contact || bandCandidate.channel);
  const label = bcContact
    ? `${(contactLabel && contactLabel(bcContact)) || bandCandidate.contact_label || bcContact} · `
      + `${fmtNum(bandCandidate.center_freq_hz, 1)} Hz` : null;

  // A simulation computed for another band (`withheldIfOtherBand`) is not drawn at all: the page
  // names both bands and asks for Recompute, as the decision card does for the report.
  if (bandMismatch) {
    return (<Card sx={{ ...CARD, border: `1px dashed ${PAL.graphic}` }}><MDBox p={3}>
      <MDTypography component="h3" sx={{ ...TYPE.title, ...WRAP.balance, color: PAL.ink }}>{title}</MDTypography>
      <MDTypography sx={{ ...TYPE.lead, display: "block", color: PAL.warnText, mt: 1 }}>
        <span aria-hidden="true" style={{ marginRight: 6 }}>▲</span>
        {`The stored simulation is for ${bandMismatch.computedFor}, not the chosen `
          + `${bandMismatch.what || "band"}, ${bandMismatch.chosen}. It is not drawn; press Recompute.`}
      </MDTypography>
    </MDBox></Card>);
  }

  if (loading && !data) {
    return (<Card sx={{ ...CARD, border: `1px dashed ${PAL.graphic}` }}><MDBox p={3}>
      <MDTypography component="h3" sx={{ ...TYPE.title, ...WRAP.balance, color: PAL.ink }}>{title}</MDTypography>
      <Caption>Fetching the stored simulation…</Caption>
    </MDBox></Card>);
  }

  const runSelector = (
    <MDBox mt={1} mb={0.6} display="flex" flexWrap="wrap" gap={1}>
      {RUN_KEYS.map((k) => (
        <RunSummaryRow key={k} label={RUN_TAB_LABEL[k]} run={runs[k]} active={k === effective}
          onClick={hasAnyRun ? () => setSelected(k) : null} />
      ))}
    </MDBox>
  );

  if (!data || !hasAnyRun) {
    return (<Card sx={{ ...CARD, border: `1px dashed ${PAL.graphic}` }}><MDBox p={3}>
      <MDTypography component="h3" sx={{ ...TYPE.title, ...WRAP.balance, color: PAL.ink }}>{title}</MDTypography>
      <MDTypography sx={{ ...TYPE.lead, display: "block", color: PAL.ink, mt: 1 }}>
        No simulation is stored for this configuration yet
      </MDTypography>
      <Caption>{(data && data.absent_reason) || err || "The report writes one the next time it runs with thresholds placed for a candidate."}</Caption>
      {data && data.timing_runs && Object.keys(data.timing_runs).length ? runSelector : null}
    </MDBox></Card>);
  }

  const act = run.active_model;
  const d0 = run.drawn && run.drawn[0];
  const rec = run.record || {};
  const inp = data.inputs || {};
  const st = run.settling || {};
  const rs = run.resampling || {};
  const P = run.params || {};
  const diff = run.closed_loop_difference || {};
  const stretchDate = d0 && isNum(d0.start_epoch_s) ? new Date(d0.start_epoch_s * 1000).toLocaleString() : null;

  return (
    <Card sx={{ ...CARD, width: "100%", border: `1px dashed ${PAL.graphic}` }}>
      <MDBox p={3}>
        <MDTypography component="h3" sx={{ ...TYPE.title, ...WRAP.balance, color: PAL.ink }}>{title}</MDTypography>
        {label ? <MDTypography sx={{ ...TYPE.caption, color: PAL.ink3 }}>{label}</MDTypography> : null}
        <MDBox mt={1}>
          <PanelStaleNote stale={!!stale} staleReasons={staleReasons || []} loading={!!loading}
            onRecompute={recompute} />
        </MDBox>
        <MDTypography sx={{ ...TYPE.lead, display: "block", color: PAL.ink, mt: 1, maxWidth: "68ch" }}>
          {headline(run)}
        </MDTypography>
        <Caption>Two sets of timing settings, replayed separately and never silently swapped for each other; click a box to draw its figures below.</Caption>
        {runSelector}
        <Caption>{run.timing_source}</Caption>
        {run.wrong_side && run.wrong_side.warning ? (
          <MDBox mt={1}>
            <MDTypography variant="caption" sx={{ ...TYPE.body, display: "block", color: PAL.warnText }}>
              <span aria-hidden="true" style={{ marginRight: 6 }}>▲</span>
              {run.wrong_side.warning}
            </MDTypography>
          </MDBox>
        ) : null}

        {/* A -- the mechanism, dominant */}
        <MDBox mt={1.2}>
          <div ref={trajRef} style={{ width: "100%", minHeight: 380 }} />
          <Caption>
            {d0
              ? `A · the longest continuous stretch of streaming, ${fmtNum(d0.n_steps * d0.dt_s / 60, 1)} min from ${stretchDate}: `
                + "the current each version would command (top; dashed grey as recorded, blue with the loop closed, the shaded band its range over resampled runs, dotted black what the device delivered) "
                + "over the band power each one sees (bottom; grey as recorded, blue moved by the commanded current). Solid lines are the current limits, dashed the switching thresholds."
              : "A · no stretch long enough to draw."}
          </Caption>
        </MDBox>

        {/* B -- every number, compared */}
        <MDBox mt={1.2}>
          <div ref={cmpRef} style={{ width: "100%", minHeight: 260 }} />
          <Caption>
            {`B · each quantity as recorded (open) and with the loop closed (filled), over ${fmtNum(rec.hours_of_signal, 1)} h of streaming in `
              + `${rec.n_segments_used} stretches; `
              + (run.models.M3 ? `the bar is the 2.5–97.5 % range across ${rs.n_fitted || 0} refits on resampled runs. `
                : `no interval is drawn${rs.reason ? ` (${rs.reason})` : ""}. `)
              + `Closing the loop changes time at the upper limit by ${isNum(diff.frac_time_at_upper) ? `${(100 * diff.frac_time_at_upper).toFixed(1)} points` : "not reported"} `
              + `and state changes by ${isNum(diff.transitions_per_hour) ? `${diff.transitions_per_hour.toFixed(0)} per hour` : "not reported"}.`}
          </Caption>
        </MDBox>

        {/* C -- where the amplitude sits, and the curve */}
        <MDBox mt={1.2}>
          <div ref={distRef} style={{ width: "100%", minHeight: 230 }} />
          <Caption>
            {`C · left, the share of adjustment steps at each commanded current between the limits ${deviceAllows
              ? `${fmtNum(P.amp_low_mA, 2)}–${fmtNum(P.amp_high_mA, 2)} mA` : `(${WITHHELD_WORDS})`}; `
              + `right, the fitted change in band power against current the loop is closed through`
              + (run.models.M3 && run.models.M3.slope_interval_per_mA ? ", with the resampled slope range shaded" : "")
              + (run.curves && run.curves.M2 ? "; the dotted line is the fitted peak." : ".")}
          </Caption>
        </MDBox>

        <Fold show="How this was worked out (the model, the record, the controller settings)" hide="Hide the method" mt={2} dense>
          <Line>{`timing settings drawn above: ${RUN_TAB_LABEL[effective]} · ${run.timing_source || ""}`}</Line>
          <Line>{`response curve: ${MODEL_WORDS[act] || act} ${run.curves && run.curves[act] ? run.curves[act].source : ""} · change in band power per milliamp ${fmtNum(run.curves && run.curves[act] && run.curves[act].slope_per_mA, 3)} ± ${fmtNum(run.curves && run.curves[act] && run.curves[act].slope_stderr, 3)} device units · fitted on ${run.n_points_in_curve} points, ${run.n_runs_in_curve} runs`}</Line>
          <Line>{`peaked response: ${run.curves && run.curves.M2 ? "in use" : (run.m2_absent_reason || "not in use")}`}</Line>
          <Line>{`how long power takes to settle: ${fmtNum(st.tau_s, 1)} s · ${st.source || ""}`}</Line>
          <Line>{`series: ${inp.n_pieces} three-second pieces on ${inp.contact} at ${fmtNum(inp.centre_used_hz, 1)} Hz · ${inp.n_unusable_pieces} unusable (held as missing) · ${inp.n_dropped_no_amplitude} dropped for no known amplitude · amplitude from the device's own record for ${inp.n_from_device_current}, from the settings history for ${inp.n_from_epochs}`}</Line>
          <Line>{`record: ${rec.n_segments} stretches, ${rec.n_segments_used} run, ${rec.n_segments_skipped} shorter than 3 steps · ${rec.n_cells_without_a_piece} device-clock cells without a piece (held), ${rec.n_cells_merging_pieces} merging two · ${fmtNum(rec.hours_of_signal, 2)} h of signal across ${fmtNum((rec.span_s || 0) / 86400, 0)} days (coverage ${fmtPct(rec.coverage_frac, 3)})`}</Line>
          <Line>{`controller: ${deviceAllows
            ? `thresholds ${fmtNum(P.lower, 1)} / ${fmtNum(P.upper, 1)} device units · limits ${fmtNum(P.amp_low_mA, 2)}–${fmtNum(P.amp_high_mA, 2)} mA (${limitsSourceWords(P)})`
            : `thresholds and current limits ${WITHHELD_WORDS}`} · ramp ${fmtNum(P.ramp_up_mA_per_s, 4)} mA/s up, ${fmtNum(P.ramp_down_mA_per_s, 4)} down · step ${fmtNum(P.dt_controller_s, 1)} s · onset ${P.onset_steps} step(s), blanking ${P.blanking_steps}`}</Line>
          {P.amp_limit_note ? <Line>{P.amp_limit_note}</Line> : null}
          <Line>{`range over resampled runs: ${rs.n_fitted || 0} of ${rs.n_resample || 0} refits on ${rs.n_runs || 0} runs resampled with replacement${rs.reason ? ` · ${rs.reason}` : ""}`}</Line>
          <Caption>{run.caveat}</Caption>
          <Caption>Dashed frame: every number here is modelled, not measured. It decides nothing.</Caption>
        </Fold>
      </MDBox>
    </Card>
  );
}
