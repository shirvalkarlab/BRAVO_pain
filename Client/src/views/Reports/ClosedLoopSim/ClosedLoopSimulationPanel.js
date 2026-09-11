/**
 * CL-DBS simulations (Phase 8 of the 2026-09-11 redesign). The device's Dual Threshold controller
 * run over this participant's own recorded band power three ways, drawn rather than described:
 *
 *   M0  replayed over the power as recorded (the card this one replaces showed exactly this);
 *   M1  the loop closed through the fitted straight-line response of power to amplitude
 *       (M2, the peaked response, takes its place once a bend is established);
 *   M3  M1 rerun with the response refitted on runs resampled with replacement -- the interval.
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
import { useEffect, useRef } from "react";
import Plotly from "plotly.js-dist";
import { Card } from "@mui/material";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import { PAL, OKABE_ITO } from "./palette";
import { fmtNum, fmtPct } from "./deployFormat";
import Fold from "./Fold";

const isNum = (v) => v != null && Number.isFinite(Number(v));
const INK_M0 = PAL.neutral;
const INK_ACTIVE = PAL.accent;
const FILL_M3 = "rgba(0,114,178,0.16)";
const FILL_WRONG = "rgba(230,159,0,0.25)";
const FILL_FITTED = "rgba(108,117,125,0.10)";
const FONT = { family: "Helvetica, Arial, sans-serif", size: 11, color: "#222" };
const AXIS = { showgrid: false, zeroline: false, showline: true, linecolor: "#444", linewidth: 1,
  ticks: "outside", ticklen: 3, tickcolor: "#444", tickfont: { size: 10 } };

function modelLabel(name) {
  return { M0: "M0 · replay, power as recorded", M1: "M1 · loop closed, straight-line response",
    M2: "M2 · loop closed, peaked response" }[name] || name;
}

/** The sentence that states what the numbers show, built from them (never hardcoded). */
function headline(sim) {
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
      fill: "tonexty", fillcolor: FILL_M3, name: "M3 · 2.5–97.5 % of resampled runs",
      hoverinfo: "skip", xaxis: "x", yaxis: "y" });
  }
  traces.push({ x: mins, y: d.a_obs, type: "scatter", mode: "lines", name: "amplitude the device delivered",
    line: { color: OKABE_ITO.black, width: 0.8, dash: "dot" }, xaxis: "x", yaxis: "y",
    hovertemplate: "recorded %{y:.2f} mA<extra></extra>" });
  traces.push({ x: mins, y: d.models.M0.amp, type: "scatter", mode: "lines", name: modelLabel("M0"),
    line: { color: INK_M0, width: 1.4, dash: "dash" }, xaxis: "x", yaxis: "y",
    hovertemplate: "M0 %{y:.2f} mA<extra></extra>" });
  traces.push({ x: mins, y: d.models[act].amp, type: "scatter", mode: "lines", name: modelLabel(act),
    line: { color: INK_ACTIVE, width: 1.8 }, xaxis: "x", yaxis: "y",
    hovertemplate: `${act} %{y:.2f} mA<extra></extra>` });
  traces.push({ x: mins, y: d.p_obs, type: "scatter", mode: "lines", name: "band power as recorded",
    line: { color: INK_M0, width: 1.0 }, xaxis: "x", yaxis: "y2",
    hovertemplate: "recorded %{y:.1f}<extra></extra>" });
  traces.push({ x: mins, y: d.models[act].p_sim, type: "scatter", mode: "lines",
    name: `band power the ${act} controller sees`, line: { color: INK_ACTIVE, width: 1.2 },
    xaxis: "x", yaxis: "y2", hovertemplate: `${act} %{y:.1f}<extra></extra>` });
  const hline = (y, yref, dash) => ({ type: "line", xref: "paper", x0: 0, x1: 1, yref, y0: y, y1: y,
    line: { color: PAL.thresholdLine, width: 0.8, dash } });
  const layout = {
    margin: { l: 58, r: 14, t: 8, b: 40 }, height: 380, font: FONT, hovermode: "x unified",
    uirevision: "cl-sim-traj", showlegend: true,
    legend: { orientation: "h", y: 1.02, yanchor: "bottom", x: 0, font: { size: 10 } },
    xaxis: { ...AXIS, title: { text: "Minutes from the start of the stretch", standoff: 6 }, domain: [0, 1] },
    yaxis: { ...AXIS, domain: [0.56, 1], title: { text: `${hemisphere || ""} amplitude (mA)`.trim(), standoff: 8 },
      range: [P.amp_low_mA - 0.05 * (P.amp_high_mA - P.amp_low_mA), P.amp_high_mA + 0.05 * (P.amp_high_mA - P.amp_low_mA)] },
    yaxis2: { ...AXIS, domain: [0, 0.44], title: { text: "Band power (device units)", standoff: 8 } },
    shapes: [hline(P.amp_low_mA, "y", "solid"), hline(P.amp_high_mA, "y", "solid"),
      hline(P.lower, "y2", "dash"), hline(P.upper, "y2", "dash")],
    annotations: [
      { xref: "paper", x: 1, yref: "y", y: P.amp_high_mA, text: "upper limit", showarrow: false, xanchor: "right", yanchor: "bottom", font: { size: 9, color: "#444" } },
      { xref: "paper", x: 1, yref: "y", y: P.amp_low_mA, text: "lower limit", showarrow: false, xanchor: "right", yanchor: "top", font: { size: 9, color: "#444" } },
      { xref: "paper", x: 1, yref: "y2", y: P.upper, text: "upper threshold", showarrow: false, xanchor: "right", yanchor: "bottom", font: { size: 9, color: "#444" } },
      { xref: "paper", x: 1, yref: "y2", y: P.lower, text: "lower threshold", showarrow: false, xanchor: "right", yanchor: "top", font: { size: 9, color: "#444" } },
    ],
  };
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
    marker: { size: 9, color: filled ? INK_ACTIVE : "#fff", line: { color: filled ? INK_ACTIVE : INK_M0, width: 1.6 } },
    error_x: ivs ? { type: "data", symmetric: false, array: ivs.map((v, i) => (v ? v[1] - xs[i] : 0)),
      arrayminus: ivs.map((v, i) => (v ? xs[i] - v[0] : 0)), color: INK_ACTIVE, thickness: 1.2, width: 0 } : undefined,
    hovertemplate: `${name} %{x:.3~f}<extra></extra>`,
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
  const layout = {
    margin: { l: 210, r: 12, t: 26, b: 36 }, height: 200 + 16 * rows.length, font: FONT,
    uirevision: "cl-sim-compare", showlegend: false,
    yaxis: { ...AXIS, showline: false, ticks: "", categoryorder: "array",
      categoryarray: [...labels, "state changes per hour", "longest stretch at the upper limit"].reverse(),
      tickfont: { size: 10.5 } },
    xaxis: { ...AXIS, domain: [0, 0.56], title: { text: "% of controller steps", standoff: 4 }, rangemode: "tozero" },
    xaxis2: { ...AXIS, domain: [0.62, 0.79], title: { text: "per hour", standoff: 4 }, rangemode: "tozero" },
    xaxis3: { ...AXIS, domain: [0.85, 1], title: { text: "minutes", standoff: 4 }, rangemode: "tozero" },
    annotations: [
      { xref: "paper", yref: "paper", x: 0, y: 1.06, xanchor: "left", showarrow: false, font: { size: 10 },
        text: `<span style="color:${INK_M0}">○ M0 replay</span>   <span style="color:${INK_ACTIVE}">● ${act} loop closed</span>`
          + (sim.models.M3 ? `   <span style="color:${INK_ACTIVE}">— M3 interval, ${sim.models.M3.n_replicates} resampled runs</span>` : "") },
    ],
  };
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
      name: "M0", xaxis: "x", yaxis: "y", hovertemplate: "M0 %{y:.1f} %<extra></extra>" },
    { x: mids, y: norm(sim.models[act].amp_hist), type: "scatter", mode: "lines", line: { shape: "hvh", color: INK_ACTIVE, width: 1.8 },
      name: act, xaxis: "x", yaxis: "y", hovertemplate: `${act} %{y:.1f} %<extra></extra>` },
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
      annotations.push({ xref: "x2", yref: "paper", x: 0.5 * (a + b), y: 0.96, text: "power rises with current: positive feedback",
        showarrow: false, font: { size: 9, color: PAL.warnText } });
    }
    if (isNum(curve.peak_mA)) {
      shapes.push({ type: "line", xref: "x2", yref: "paper", x0: curve.peak_mA, x1: curve.peak_mA, y0: 0, y1: 1,
        line: { color: PAL.thresholdLine, width: 0.8, dash: "dot" } });
    }
  } else {
    annotations.push({ xref: "x2 domain", yref: "y2 domain", x: 0.5, y: 0.5, showarrow: false,
      font: { size: 10.5, color: PAL.neutral }, text: "no response curve stored yet" });
  }
  const layout = {
    margin: { l: 52, r: 12, t: 24, b: 38 }, height: 230, font: FONT, uirevision: "cl-sim-dist", showlegend: false,
    xaxis: { ...AXIS, domain: [0, 0.44], title: { text: "Commanded amplitude (mA)", standoff: 4 }, range: [P.amp_low_mA, P.amp_high_mA] },
    yaxis: { ...AXIS, title: { text: "% of controller steps", standoff: 6 }, rangemode: "tozero" },
    xaxis2: { ...AXIS, domain: [0.56, 1], title: { text: "Amplitude (mA)", standoff: 4 }, range: [P.amp_low_mA, P.amp_high_mA], anchor: "y2" },
    yaxis2: { ...AXIS, anchor: "x2", title: { text: "Power change from the lower limit", standoff: 6 } },
    shapes, annotations: [
      ...annotations,
      { xref: "paper", yref: "paper", x: 0, y: 1.08, xanchor: "left", showarrow: false, font: { size: 10 },
        text: `<span style="color:${INK_M0}">- - M0</span>  <span style="color:${INK_ACTIVE}">— ${act}</span>  where the amplitude sits` },
      { xref: "paper", yref: "paper", x: 0.56, y: 1.08, xanchor: "left", showarrow: false, font: { size: 10 },
        text: `the response the loop is closed through${curve && curve.kind !== "none" ? " (grey: currents the fit rests on)" : ""}` },
    ],
  };
  Plotly.react(gd, traces, layout, PAL.MODEBAR);
}

function Caption({ children }) {
  return (
    <MDTypography variant="caption" sx={{ display: "block", fontSize: 11, color: "#4A4A4A", mt: 0.3 }}>
      {children}
    </MDTypography>
  );
}

function Line({ children }) {
  return (
    <MDTypography variant="caption" sx={{ display: "block", fontSize: 11, fontFamily: PAL.mono, color: "#2A2A2A", mt: 0.25 }}>
      {children}
    </MDTypography>
  );
}

export default function ClosedLoopSimulationPanel({ sim, hemisphere, contactLabel, bandCandidate }) {
  const { data, loading, err } = sim || { data: null, loading: false, err: null };
  const trajRef = useRef(null); const cmpRef = useRef(null); const distRef = useRef(null);

  useEffect(() => {
    if (!data || data.refused || !data.models || !data.models.M0) return;
    if (trajRef.current) drawTrajectory(trajRef.current, data, hemisphere);
    if (cmpRef.current) drawComparison(cmpRef.current, data);
    if (distRef.current) drawDistributionAndCurve(distRef.current, data);
  }, [data, hemisphere]);
  // purge on unmount only: cleanup on every redraw would destroy the figures the reader is looking at
  useEffect(() => () => {
    [trajRef, cmpRef, distRef].forEach((r) => { if (r.current) Plotly.purge(r.current); });
  }, []);

  const title = "CL-DBS simulations";
  const label = contactLabel && bandCandidate && bandCandidate.channel
    ? `${contactLabel(bandCandidate.channel)} · ${fmtNum(bandCandidate.center_freq_hz, 1)} Hz` : null;

  if (loading && !data) {
    return (<Card sx={{ border: "2px dashed rgba(0,0,0,0.28)" }}><MDBox p={2}>
      <MDTypography variant="h6" sx={{ fontSize: 15 }}>{title}</MDTypography>
      <Caption>Fetching the stored simulation…</Caption>
    </MDBox></Card>);
  }
  if (!data || data.refused || !data.models || !data.models.M0) {
    return (<Card sx={{ border: "2px dashed rgba(0,0,0,0.28)" }}><MDBox p={2}>
      <MDTypography variant="h6" sx={{ fontSize: 15 }}>{title}</MDTypography>
      <MDTypography variant="button" sx={{ display: "block", fontSize: 12.5, mt: 0.4 }}>
        {data ? headline(data) : "No simulation is stored for this configuration yet"}
      </MDTypography>
      <Caption>{(data && data.absent_reason) || err || "The report writes one the next time it runs with thresholds placed for a candidate."}</Caption>
      {data && isNum(data.median_interval_s) ? (
        <Line>{`samples every ${fmtNum(data.median_interval_s, 0)} s · ramp resolvable: ${String(data.ramp_resolvable)}`}</Line>
      ) : null}
    </MDBox></Card>);
  }

  const act = data.active_model;
  const d0 = data.drawn && data.drawn[0];
  const rec = data.record || {};
  const inp = data.inputs || {};
  const st = data.settling || {};
  const rs = data.resampling || {};
  const P = data.params || {};
  const diff = data.closed_loop_difference || {};
  const stretchDate = d0 && isNum(d0.start_epoch_s) ? new Date(d0.start_epoch_s * 1000).toLocaleString() : null;

  return (
    <Card sx={{ width: "100%", border: "2px dashed rgba(0,0,0,0.28)" }}>
      <MDBox p={2}>
        <MDBox display="flex" justifyContent="space-between" alignItems="baseline" flexWrap="wrap" gap={1}>
          <MDTypography variant="h6" sx={{ fontSize: 15, lineHeight: 1.3 }}>{title}</MDTypography>
          {label ? <MDTypography variant="caption" sx={{ fontSize: 11, color: "#6A6A6A" }}>{label}</MDTypography> : null}
        </MDBox>
        <MDTypography variant="button" sx={{ display: "block", fontSize: 12.5, fontWeight: 600, mt: 0.3, lineHeight: 1.35 }}>
          {headline(data)}
        </MDTypography>
        {data.wrong_side && data.wrong_side.warning ? (
          <MDBox mt={0.6} p={0.8} sx={{ backgroundColor: PAL.warnFill, borderRadius: "4px", border: `1px solid ${PAL.warnBorder}` }}>
            <MDTypography variant="caption" sx={{ display: "block", fontSize: 11, color: PAL.warnText }}>
              {data.wrong_side.warning}
            </MDTypography>
          </MDBox>
        ) : null}

        {/* A -- the mechanism, dominant */}
        <MDBox mt={1.2}>
          <div ref={trajRef} style={{ width: "100%", minHeight: 380 }} />
          <Caption>
            {d0
              ? `A · the longest continuous stretch of streaming, ${fmtNum(d0.n_steps * d0.dt_s / 60, 1)} min from ${stretchDate}: `
                + `the amplitude each controller commands (top; dashed grey M0, blue ${act}, shaded band M3, dotted black what the device delivered) `
                + "over the band power each one sees (bottom; grey as recorded, blue moved by the commanded amplitude). Solid lines are the amplitude limits, dashed the thresholds."
              : "A · no stretch long enough to draw."}
          </Caption>
        </MDBox>

        {/* B -- every number, compared */}
        <MDBox mt={1.2}>
          <div ref={cmpRef} style={{ width: "100%", minHeight: 260 }} />
          <Caption>
            {`B · each quantity for the replay (open) and the closed loop (filled), over ${fmtNum(rec.hours_of_signal, 1)} h of streaming in `
              + `${rec.n_segments_used} stretches; `
              + (data.models.M3 ? `the bar is the 2.5–97.5 % range across ${rs.n_fitted || 0} refits on resampled runs. `
                : `no interval is drawn${rs.reason ? ` (${rs.reason})` : ""}. `)
              + `Closing the loop changes time at the upper limit by ${isNum(diff.frac_time_at_upper) ? `${(100 * diff.frac_time_at_upper).toFixed(1)} points` : "—"} `
              + `and state changes by ${isNum(diff.transitions_per_hour) ? `${diff.transitions_per_hour.toFixed(0)} per hour` : "—"}.`}
          </Caption>
        </MDBox>

        {/* C -- where the amplitude sits, and the curve */}
        <MDBox mt={1.2}>
          <div ref={distRef} style={{ width: "100%", minHeight: 230 }} />
          <Caption>
            {`C · left, the share of controller steps at each commanded amplitude between the limits ${fmtNum(P.amp_low_mA, 1)}–${fmtNum(P.amp_high_mA, 1)} mA; `
              + `right, the fitted change in band power against amplitude the loop is closed through`
              + (data.models.M3 && data.models.M3.slope_interval_per_mA ? ", with the resampled slope range shaded" : "")
              + (data.curves && data.curves.M2 ? "; the dotted line is the fitted peak." : ".")}
          </Caption>
        </MDBox>

        <Fold show="How this was modelled" hide="Hide the method" mt={1} dense>
          <Line>{`response curve: ${act} ${data.curves && data.curves[act] ? data.curves[act].source : ""} · slope ${fmtNum(data.curves && data.curves[act] && data.curves[act].slope_per_mA, 3)} ± ${fmtNum(data.curves && data.curves[act] && data.curves[act].slope_stderr, 3)} units/mA · fitted on ${data.n_points_in_curve} points, ${data.n_runs_in_curve} runs`}</Line>
          <Line>{`M2 (peaked): ${data.curves && data.curves.M2 ? "active" : (data.m2_absent_reason || "absent")}`}</Line>
          <Line>{`settling time τ = ${fmtNum(st.tau_s, 1)} s · ${st.source || ""}`}</Line>
          <Line>{`series: ${inp.n_pieces} three-second pieces on ${inp.contact} at ${fmtNum(inp.centre_used_hz, 1)} Hz · ${inp.n_unusable_pieces} unusable (held as missing) · ${inp.n_dropped_no_amplitude} dropped for no known amplitude · amplitude from the device's own record for ${inp.n_from_device_current}, from the settings history for ${inp.n_from_epochs}`}</Line>
          <Line>{`record: ${rec.n_segments} stretches, ${rec.n_segments_used} run, ${rec.n_segments_skipped} shorter than 3 steps · ${rec.n_cells_without_a_piece} device-clock cells without a piece (held), ${rec.n_cells_merging_pieces} merging two · ${fmtNum(rec.hours_of_signal, 2)} h of signal across ${fmtNum((rec.span_s || 0) / 86400, 0)} days (coverage ${fmtPct(rec.coverage_frac, 3)})`}</Line>
          <Line>{`controller: thresholds ${fmtNum(P.lower, 1)} / ${fmtNum(P.upper, 1)} device units · limits ${fmtNum(P.amp_low_mA, 2)}–${fmtNum(P.amp_high_mA, 2)} mA (the capture range, held) · ramp ${fmtNum(P.ramp_up_mA_per_s, 4)} mA/s up, ${fmtNum(P.ramp_down_mA_per_s, 4)} down · step ${fmtNum(P.dt_controller_s, 1)} s · onset ${P.onset_steps} step(s), blanking ${P.blanking_steps}`}</Line>
          <Line>{`M3: ${rs.n_fitted || 0} of ${rs.n_resample || 0} refits on ${rs.n_runs || 0} runs resampled with replacement${rs.reason ? ` · ${rs.reason}` : ""}`}</Line>
          <Caption>{data.caveat}</Caption>
          <Caption>Dashed frame: every number here is modelled, not measured. It gates nothing.</Caption>
        </Fold>
      </MDBox>
    </Card>
  );
}
