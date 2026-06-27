/**
 * Phase B panel: deployment ROC + cut-point search for one committed BandCandidate.
 *
 * Fetches /api/queryDeploymentROC (rating-clustered bootstrap AUC CI) and renders:
 *   - a Plotly ROC curve with the AUC + clustered 95% CI in the title,
 *   - a match-direction toggle (prior/forecasting [deploy default] vs pro_first [discovery]),
 *   - a cut-point rule selector (Youden J / max-F1 / cost-sensitive / net-benefit) that re-solves
 *     the operating point LIVE in the browser from the returned fpr/tpr/thr/prevalence and draws it
 *     on the curve, surfacing the threshold on the oriented log-power feature scale (Phase C maps
 *     it to LSB).
 *
 * The cut-point chosen here is lifted to the parent (onCutpoint) so Phases C–E can consume it.
 */
import { useEffect, useRef, useState } from "react";
import Plotly from "plotly.js-dist";

import { Card, Grid, ToggleButton, ToggleButtonGroup, Slider } from "@mui/material";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import { SessionController } from "database/session-control";
import PAL from "./palette";

const fmt = (v, d = 2) => (v == null || !Number.isFinite(Number(v)) ? "—" : Number(v).toFixed(d));

// Audit C9: the cut-point marker lives at a FIXED trace index so effect (B) can move it in place via
// Plotly.restyle without rebuilding the curve (the no-reset discipline). That index was hardcoded as
// a bare `[2]` in two restyle calls and described in two comments — a single source here keeps the
// draw order (effect A) and the restyle target (effect B) from silently drifting apart. Order in the
// base trace array MUST be: 0 = chance line, 1 = ROC curve, 2 = cut-point marker.
const CUTPOINT_TRACE = 2;

// Solve the operating point on the ROC for a given rule, in the browser, from the parallel
// fpr/tpr/thr arrays + prevalence. Returns {k, fpr, tpr, threshold, sensitivity, specificity, ...}.
function solveCutpoint(roc, rule, costRatio) {
  if (!roc || !Array.isArray(roc.fpr) || !roc.fpr.length) return null;
  const { fpr, tpr, thr } = roc;
  const p = roc.prevalence;
  let bestK = -1, bestU = -Infinity;
  for (let i = 0; i < fpr.length; i += 1) {
    if (thr[i] == null) continue;                 // skip the +inf sentinel at (0,0)
    let u;
    if (rule === "youden") {
      u = tpr[i] - fpr[i];
    } else if (rule === "f1") {
      // F1 from sens/ppv needs prevalence: TP=tpr*P, FP=fpr*(1-P), FN=(1-tpr)*P.
      if (!Number.isFinite(p) || p <= 0 || p >= 1) { u = tpr[i] - fpr[i]; }
      else {
        const tp = tpr[i] * p, fp = fpr[i] * (1 - p), fn = (1 - tpr[i]) * p;
        const denom = 2 * tp + fp + fn;
        u = denom > 0 ? (2 * tp) / denom : -Infinity;
      }
    } else if (rule === "cost") {
      // Cost-sensitive tangent: maximize tpr - slope*fpr, slope = costRatio*(1-p)/p.
      // NOTE: a "net benefit" rule that maximizes (tpr*p - fpr*(1-p)*costRatio) was removed because
      // its objective is exactly prevalence times this one (u_nb = p * u_cost), so it selects the
      // IDENTICAL operating point at every cost ratio — two device-threshold buttons that can never
      // disagree, with floating-point ties occasionally flipping the winner and reading as a bug.
      // True Vickers net benefit is a decision CURVE across threshold probabilities, not a single
      // point-selection rule, and is tracked as a Phase-2 panel rather than a co-equal toggle here.
      if (!Number.isFinite(p) || p <= 0 || p >= 1) { u = tpr[i] - fpr[i]; }
      else { u = tpr[i] - (costRatio * (1 - p) / p) * fpr[i]; }
    } else {
      u = tpr[i] - fpr[i];
    }
    // Strictly-greater keeps the FIRST (lowest-index) maximizer deterministically; ties never flip.
    if (u > bestU) { bestU = u; bestK = i; }
  }
  if (bestK < 0) return null;
  const sens = tpr[bestK];
  const spec = 1 - fpr[bestK];
  // A data-chosen tangent at an extreme cost ratio (or F1 at high prevalence) can land on a corner of
  // the empirical ROC — "alarm almost always" (spec~0) or "alarm almost never" (sens~0). Such a point
  // is mathematically a valid optimum but a clinically useless controller; flag it so the UI can warn
  // and refuse to present it as a clean deployable threshold rather than silently lifting it to Phase C.
  const degenerate = (spec < 0.10) || (sens < 0.30) || (fpr[bestK] > 0.95) || (fpr[bestK] < 0.02 && sens < 0.5);
  return {
    k: bestK, fpr: fpr[bestK], tpr: tpr[bestK], threshold: thr[bestK],
    sensitivity: sens, specificity: spec, rule, degenerate,
  };
}

function DeploymentRocPanel({ participantUid, bandCandidate, requestParams, onCutpoint }) {
  const ref = useRef(null);
  const histRef = useRef(null);
  const fwdRef = useRef(null);
  const [matchDir, setMatchDir] = useState("prior");      // deploy default = causal forecasting
  const [rule, setRule] = useState("youden");
  const [logCost, setLogCost] = useState(0);              // log2(cFP/cFN); 0 => symmetric
  const [roc, setRoc] = useState(null);
  const [forward, setForward] = useState(null);   // audit C2: forward-chaining / out-of-sample block
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);

  const bc = bandCandidate || {};
  const channelRaw = bc.contact;
  const centerHz = bc.center_freq_hz;
  const bandWidthHz = bc.bandwidth_hz || 5.0;

  // Fetch ROC whenever the band or the match direction changes.
  useEffect(() => {
    if (!participantUid || channelRaw == null || centerHz == null) return;
    setLoading(true); setErr(null);
    SessionController.query("/api/queryDeploymentROC", {
      ParticipantId: participantUid,
      Channel: channelRaw,
      CenterHz: Number(centerHz),
      BandWidthHz: Number(bandWidthHz),
      MatchDirection: matchDir,
      ...requestParams,
    }).then((response) => {
      const data = response && response.data;
      if (data && data.available && data.roc && data.roc.available) {
        setRoc(data.roc);
        setForward(data.forward || null);   // audit C2: held-out forward-chaining trace
      } else {
        setRoc(null);
        setForward(null);
        setErr((data && (data.reason || (data.roc && data.roc.reason))) || "ROC unavailable");
      }
      setLoading(false);
    }).catch(() => { setRoc(null); setErr("ROC request failed"); setLoading(false); });
  }, [participantUid, channelRaw, centerHz, bandWidthHz, matchDir, requestParams]);

  const costRatio = Math.pow(2, logCost);
  const op = roc ? solveCutpoint(roc, rule, costRatio) : null;
  const opThr = op ? op.threshold : null;
  const opRule = op ? op.rule : null;
  const rocAuc = roc ? roc.auc : null;

  // Lift the chosen cut-point to the parent for Phases C–E. Keyed on the stable primitives (not the
  // freshly-rebuilt op object) so it fires only when the actual operating point changes. DEBOUNCED:
  // dragging the cost slider re-solves the operating point on every tick; without the delay each
  // tick would push a new cut-point to the parent, re-rendering the LSB/era panels and re-firing the
  // LSB fetch mid-drag. A 250 ms settle lets the drag finish before downstream panels recompute,
  // while the on-curve marker (effect B) still tracks the slider live.
  useEffect(() => {
    if (!onCutpoint) return undefined;
    const payload = opThr != null ? { threshold: opThr, rule: opRule, matchDir, auc: rocAuc,
      sensitivity: op && op.sensitivity, specificity: op && op.specificity,
      fpr: op && op.fpr, tpr: op && op.tpr, degenerate: op && op.degenerate } : null;
    const t = setTimeout(() => onCutpoint(payload), 250);
    return () => clearTimeout(t);
  }, [opThr, opRule, matchDir, rocAuc]);  // eslint-disable-line react-hooks/exhaustive-deps

  // (A) Draw the ROC BASE (chance line + curve + an empty cut-point trace) once per ROC dataset.
  // The cut-point marker is trace index CUTPOINT_TRACE; updated in place by effect (B) so changing rule
  // or dragging the cost slider never rebuilds the curve and never discards the user's zoom/pan.
  useEffect(() => {
    if (!ref.current || !roc) return;
    // Audit C7 + [3]/[16]: name the CI method ON the figure. The interval is a BCa (bias-corrected &
    // accelerated) interval on a rating-clustered moving-block bootstrap — the properties that
    // distinguish it from a naive over-tight CI. block_len>1 means serial autocorrelation widened it.
    const ciKind = (roc.ci_interval === "BCa" ? "BCa" : "percentile");
    const blockTxt = (roc.block_len != null && roc.block_len > 1) ? `, block=${roc.block_len}` : "";
    const ciTxt = (roc.auc_lo != null && roc.auc_hi != null)
      ? ` (95% clustered-bootstrap ${ciKind} CI ${fmt(roc.auc_lo)}–${fmt(roc.auc_hi)}${blockTxt})` : "";
    // Audit [8]: below the cluster floor the asymptotic AUC inference is approximate — say so on the
    // figure. Advisory label only; no number changes (the flag comes straight from the backend).
    const smallTxt = roc.small_sample
      ? `  ·  small sample (${roc.n_clusters} ratings < ${roc.small_sample_floor}) — approximate` : "";
    // Audit [3]: surface how many bootstrap replicates the CI rests on. The CI is now SUPPRESSED by the
    // backend below the valid-replicate floor (ci_valid_floor, =100); when it is shown, flag a thin
    // resample as unstable. The 2.5/97.5 percentiles of few replicates sit near the min/max and are noisy.
    const nbOk = (roc.n_boot_ok != null) ? roc.n_boot_ok : null;
    const floor = (roc.ci_valid_floor != null) ? roc.ci_valid_floor : 100;
    const bootTxt = (ciTxt && nbOk != null)
      ? (nbOk < floor ? `  ·  CI on ${nbOk} bootstrap replicates — unstable` : `  ·  ${nbOk} bootstrap replicates`)
      : "";
    const traces = [
      { x: [0, 1], y: [0, 1], type: "scatter", mode: "lines", name: "chance",
        line: { color: "#bbb", dash: "dot", width: 1 }, hoverinfo: "skip", showlegend: false },
      { x: roc.fpr, y: roc.tpr, type: "scatter", mode: "lines", name: "ROC",
        line: { color: PAL.accent, width: 2.2 }, showlegend: false,
        hovertemplate: "FPR %{x:.2f} · TPR %{y:.2f}<extra></extra>" },
      // cut-point marker placeholder at index CUTPOINT_TRACE (=2) — kept fixed so restyle can move it.
      { x: [], y: [], type: "scatter", mode: "markers", name: "cut-point", showlegend: false,
        marker: { color: PAL.cutpoint, size: 12, line: { color: "#fff", width: 2 } },
        hovertemplate: "cut-point<extra></extra>" },
    ];
    const layout = {
      title: { text: `AUC = ${fmt(roc.auc)}${ciTxt}${bootTxt}${smallTxt}`, font: { size: 13 } },
      margin: { l: 46, r: 12, t: 32, b: 42 }, height: 320,
      xaxis: { title: { text: "False positive rate", font: { size: 11 } }, range: [-0.02, 1.02],
        zeroline: false, tickfont: { size: 10 } },
      yaxis: { title: { text: "True positive rate", font: { size: 11 } }, range: [-0.02, 1.02],
        zeroline: false, tickfont: { size: 10 } },
      annotations: [],
    };
    Plotly.react(ref.current, traces, layout, PAL.MODEBAR);
  }, [roc]);  // eslint-disable-line react-hooks/exhaustive-deps

  // (B) Move ONLY the cut-point marker + its annotation when the operating point changes (rule or
  // cost slider). Uses restyle/relayout on the existing graph — O(1), no curve redraw, zoom preserved.
  useEffect(() => {
    const gd = ref.current;
    if (!gd || !roc || !gd.data) return;
    if (op) {
      // Degenerate operating points get an amber marker so the warning box and the curve agree.
      const mColor = op.degenerate ? PAL.cutpointDegenerate : PAL.cutpoint;
      Plotly.restyle(gd, {
        x: [[op.fpr]], y: [[op.tpr]],
        "marker.color": [mColor],
        hovertemplate: [`cut-point (${op.rule})<br>power ≥ ${fmt(op.threshold)}<br>`
          + `sens ${fmt(op.sensitivity)} · spec ${fmt(op.specificity)}<extra></extra>`],
      }, [CUTPOINT_TRACE]);
      // Flip the label offset toward the plot interior near the top/right edges so it never clips
      // off-panel (F1 lands near (0.67,0.95); a low cost ratio pushes the point toward (0.94,1.0)).
      const nearRight = op.fpr > 0.65;
      const nearTop = op.tpr > 0.85;
      const ax = nearRight ? -30 : 28;
      const ay = nearTop ? 24 : -26;   // positive ay pushes the box DOWN (interior) when near the top
      // Audit C6: white-on-#E69F00 (the degenerate warn fill) is 2.25:1 — below WCAG. Use near-black
      // text on the orange callout (7.7:1); keep white only on the bluish-green non-degenerate marker.
      const labelTextColor = op.degenerate ? PAL.onWarn : "#fff";
      Plotly.relayout(gd, { annotations: [{
        x: op.fpr, y: op.tpr, xref: "x", yref: "y",
        text: `<b>power ≥ ${fmt(op.threshold)}</b>`, showarrow: true, arrowhead: 0,
        arrowcolor: mColor, ax, ay, font: { size: 11, color: labelTextColor },
        bgcolor: mColor, bordercolor: mColor, borderpad: 3,
        xanchor: nearRight ? "right" : "left", yanchor: nearTop ? "top" : "bottom",
      }] });
    } else {
      Plotly.restyle(gd, { x: [[]], y: [[]] }, [CUTPOINT_TRACE]);
      Plotly.relayout(gd, { annotations: [] });
    }
  }, [roc, opThr, opRule, op && op.degenerate]);  // eslint-disable-line react-hooks/exhaustive-deps

  // (C) Draw the FEATURE-DISTRIBUTION HISTOGRAM base once per ROC dataset: the per-sample oriented
  // log-power feature split into pain-high vs pain-low, overlaid on shared bins. This is the most
  // direct view of WHY the band separates pain — it shows the clinician the class overlap the AUC
  // summarizes and where any cut-point falls within it. The feature scale here is identical to the
  // cut-point threshold scale (op.threshold), so the threshold line (effect D) maps directly on top.
  // Drawn once and updated in place; the threshold line is a layout shape moved by relayout, never a
  // rebuild — same no-reset discipline as the ROC.
  useEffect(() => {
    const gd = histRef.current;
    const fh = roc && roc.feature_hist;
    if (!gd || !fh) return;
    // Audit C7: pain-low as a SOLID filled bar; pain-high as an OUTLINE-only bar (transparent fill,
    // 2px vermillion edge). Overlaying two semi-opaque fills blended to a muddy purple-brown in the
    // exact separation zone the figure exists to show — and vanished in grayscale. A fill-vs-outline
    // pair never blends into a phantom third category and survives a printout. Still one trace per
    // class, drawn once per dataset — the Plotly.react-once discipline is untouched.
    const traces = [
      { x: fh.bin_centers, y: fh.counts_low, type: "bar", name: "pain-low",
        marker: { color: PAL.painLow, opacity: 0.55 },
        hovertemplate: "low pain<br>power %{x:.2f}<br>%{y} samples<extra></extra>" },
      { x: fh.bin_centers, y: fh.counts_high, type: "bar", name: "pain-high",
        marker: { color: "rgba(0,0,0,0)", line: { color: PAL.painHighOutline, width: 1.6 } },
        hovertemplate: "high pain<br>power %{x:.2f}<br>%{y} samples<extra></extra>" },
    ];
    const binW = (fh.bin_centers.length > 1)
      ? (fh.bin_centers[1] - fh.bin_centers[0]) : (fh.x_max - fh.x_min) || 1;
    const layout = {
      barmode: "overlay", bargap: 0.04,
      margin: { l: 46, r: 12, t: 8, b: 38 }, height: 168,
      xaxis: { title: { text: "Oriented band power (standardized, cut-point scale)", font: { size: 10.5 } },
        zeroline: false, tickfont: { size: 9.5 },
        range: [fh.x_min - binW, fh.x_max + binW] },
      yaxis: { title: { text: "samples", font: { size: 10 } }, zeroline: false,
        tickfont: { size: 9.5 } },
      legend: { orientation: "h", x: 0, y: 1.16, font: { size: 9.5 } },
      shapes: [], annotations: [],
    };
    Plotly.react(gd, traces, layout, PAL.MODEBAR);
  }, [roc]);  // eslint-disable-line react-hooks/exhaustive-deps

  // (D) Move ONLY the threshold line on the histogram when the operating point changes — a vertical
  // layout shape via relayout, so dragging the cost slider slides the line across the class overlap
  // live with no histogram rebuild.
  useEffect(() => {
    const gd = histRef.current;
    const fh = roc && roc.feature_hist;
    if (!gd || !fh || !gd.layout) return;
    if (opThr != null && Number.isFinite(Number(opThr))) {
      const lineColor = (op && op.degenerate) ? PAL.cutpointDegenerate : PAL.thresholdLine;
      Plotly.relayout(gd, {
        shapes: [{ type: "line", x0: opThr, x1: opThr, yref: "paper", y0: 0, y1: 1,
          line: { color: lineColor, width: 2, dash: "dash" } }],
        annotations: [{ x: opThr, y: 1, yref: "paper", yanchor: "bottom",
          text: `cut ≥ ${fmt(opThr)}`, showarrow: false, font: { size: 9.5, color: lineColor },
          xanchor: opThr > (fh.x_min + fh.x_max) / 2 ? "right" : "left" }],
      });
    } else {
      Plotly.relayout(gd, { shapes: [], annotations: [] });
    }
  }, [roc, opThr, op && op.degenerate]);  // eslint-disable-line react-hooks/exhaustive-deps

  // (E) Forward-chaining trace (audit C2): per-fold HELD-OUT AUC across elapsed weeks, drawn beside
  // the in-sample number. Each marker is one expanding-window fold — train on all weeks before it,
  // test on that week — so a reader sees WHEN the band stops generalizing, not just a pooled number.
  // Markers are colored by whether the fold cleared chance (green) or not (vermillion). Overlaid:
  // a dotted chance line at 0.5, the in-sample AUC as a dashed grey reference (the optimistic number),
  // and the pooled held-out AUC + its bootstrap CI as a shaded band. Same Plotly.react-once discipline.
  useEffect(() => {
    const gd = fwdRef.current;
    if (!gd || !forward || !forward.available || !Array.isArray(forward.folds) || !forward.folds.length) return;
    const folds = forward.folds;
    const xs = folds.map((f) => f.test_week_start);
    const ys = folds.map((f) => f.test_auc);
    const cols = folds.map((f) => (f.test_auc >= 0.5 ? PAL.pass : PAL.fail));
    const xlo = Math.min(...xs) - 0.5;
    const xhi = Math.max(...xs) + 0.5;
    const traces = [
      // pooled held-out CI band (drawn first so it sits behind everything)
      ...(forward.held_out_auc_lo != null && forward.held_out_auc_hi != null ? [{
        x: [xlo, xhi, xhi, xlo], y: [forward.held_out_auc_lo, forward.held_out_auc_lo,
          forward.held_out_auc_hi, forward.held_out_auc_hi],
        fill: "toself", type: "scatter", mode: "lines", line: { width: 0 },
        fillcolor: "rgba(0,158,115,0.10)", hoverinfo: "skip", showlegend: false, name: "held-out 95% CI",
      }] : []),
      { x: [xlo, xhi], y: [0.5, 0.5], type: "scatter", mode: "lines", name: "chance",
        line: { color: "#bbb", dash: "dot", width: 1 }, hoverinfo: "skip", showlegend: false },
      // in-sample AUC reference (the optimistic number the forward trace is judged against)
      ...(forward.in_sample_auc != null ? [{
        x: [xlo, xhi], y: [forward.in_sample_auc, forward.in_sample_auc], type: "scatter", mode: "lines",
        name: "in-sample AUC", line: { color: PAL.gray, dash: "dash", width: 1.4 },
        hovertemplate: `in-sample AUC ${fmt(forward.in_sample_auc)}<extra></extra>`, showlegend: false,
      }] : []),
      // pooled held-out AUC reference line
      ...(forward.held_out_auc != null ? [{
        x: [xlo, xhi], y: [forward.held_out_auc, forward.held_out_auc], type: "scatter", mode: "lines",
        name: "pooled held-out", line: { color: PAL.pass, width: 1.2 },
        hovertemplate: `pooled held-out AUC ${fmt(forward.held_out_auc)}<extra></extra>`, showlegend: false,
      }] : []),
      // per-fold held-out AUC (the trace itself)
      { x: xs, y: ys, type: "scatter", mode: "lines+markers", name: "per-fold held-out",
        line: { color: PAL.accent, width: 1.6 },
        marker: { color: cols, size: 9, line: { color: "#fff", width: 1.4 } },
        customdata: folds.map((f) => [f.n_train_clusters, f.n_test_clusters,
          f.sens == null ? "—" : fmt(f.sens), f.spec == null ? "—" : fmt(f.spec)]),
        hovertemplate: "week %{x} · held-out AUC %{y:.2f}<br>train %{customdata[0]} / test %{customdata[1]} clusters"
          + "<br>sens %{customdata[2]} · spec %{customdata[3]}<extra></extra>" },
    ];
    const layout = {
      title: {
        text: `Forward-chained held-out AUC — pooled ${fmt(forward.held_out_auc)}`
          + (forward.held_out_auc_lo != null ? ` (CI ${fmt(forward.held_out_auc_lo)}–${fmt(forward.held_out_auc_hi)})` : "")
          + ` vs in-sample ${fmt(forward.in_sample_auc)}`,
        font: { size: 11.5 },
      },
      margin: { l: 46, r: 12, t: 26, b: 36 }, height: 188,
      xaxis: { title: { text: "Test fold — elapsed week (train = all earlier weeks)", font: { size: 10 } },
        zeroline: false, tickfont: { size: 9.5 }, range: [xlo, xhi] },
      yaxis: { title: { text: "held-out AUC", font: { size: 10 } }, zeroline: false,
        tickfont: { size: 9.5 }, range: [-0.02, 1.02] },
    };
    Plotly.react(gd, traces, layout, PAL.MODEBAR);
  }, [forward]);  // eslint-disable-line react-hooks/exhaustive-deps

  // Purge only on unmount (NOT on every roc/op change) so the figure nodes are reused across refits.
  useEffect(() => {
    const g1 = ref.current; const g2 = histRef.current; const g3 = fwdRef.current;
    return () => { if (g1) Plotly.purge(g1); if (g2) Plotly.purge(g2); if (g3) Plotly.purge(g3); };
  }, []);

  return (
    <Card sx={{ width: "100%" }}>
      <MDBox p={2}>
        <MDBox display="flex" justifyContent="space-between" alignItems="center" mb={1} flexWrap="wrap" gap={1}>
          <MDTypography variant="h6" sx={{ fontSize: 14 }}>Deployment ROC + cut-point</MDTypography>
          {/* Match direction silently refits the ROC, the LSB threshold and the sign-off, so label it
              in clinical terms (not the internal 'prior'/'pro_first' keys) and mark the deploy default. */}
          <ToggleButtonGroup size="small" exclusive value={matchDir}
            onChange={(e, v) => { if (v) setMatchDir(v); }}
            title="Forecasting predicts the NEXT rating from neural data recorded before it (the causal, deployable question). Concurrent pairs each rating with the same-window recording (exploratory). Switching refits the threshold.">
            <ToggleButton value="prior" sx={{ fontSize: 10, textTransform: "none", py: 0.2 }}>
              Forecasting (deploy default)
            </ToggleButton>
            <ToggleButton value="pro_first" sx={{ fontSize: 10, textTransform: "none", py: 0.2 }}>
              Concurrent (exploratory)
            </ToggleButton>
          </ToggleButtonGroup>
        </MDBox>

        {/* Status banner sits ABOVE the figure; the graph node below stays mounted across refits so
            its zoom/pan and DOM are preserved (Plotly.react updates it in place). */}
        {loading ? (
          <MDTypography variant="caption" color="text" sx={{ fontStyle: "italic", fontSize: 11 }}>
            Computing rating-clustered ROC (bootstrap CI)…
          </MDTypography>
        ) : err ? (
          <MDTypography variant="caption" sx={{ fontSize: 11, color: PAL.fail }}>
            {`ROC unavailable: ${err}.`}
          </MDTypography>
        ) : null}

        {/* Always-mounted figure container. Hidden (not unmounted) when there's no ROC yet, so the
            Plotly graph object survives loading/refit cycles instead of being torn down. */}
        <div ref={ref} style={{ width: "100%", display: roc ? "block" : "none" }} />

        {/* Feature-distribution histogram beneath the ROC (pain-high vs pain-low), with the cut-point
            threshold line drawn on top. Also always-mounted so it survives refits. Only shown when
            the backend returns feature_hist (older payloads / off-band candidates may omit it). */}
        <div ref={histRef}
          style={{ width: "100%", display: roc && roc.feature_hist ? "block" : "none" }} />

        {/* Forward-chaining held-out AUC trace (audit C2). Always-mounted so it survives refits; shown
            only when the backend returns a usable forward block with at least one fold. */}
        <div ref={fwdRef}
          style={{ width: "100%",
            display: forward && forward.available && forward.folds && forward.folds.length ? "block" : "none" }} />

        {/* Plain-language read of the forward result: clears chance / collapses forward / underpowered /
            not assessable. This is the out-of-sample number to weight, beside the optimistic in-sample one. */}
        {forward && forward.available && forward.held_out_auc != null ? (
          <MDTypography variant="caption" display="block" sx={{
            fontSize: 10.5, mt: 0.3,
            color: forward.beats_chance_forward ? PAL.pass : PAL.warnText }}>
            {forward.beats_chance_forward
              ? `Forward-validated: held-out AUC ${fmt(forward.held_out_auc)} clears chance across ${forward.n_folds} weekly folds (forward optimism ${fmt(forward.optimism)}). This is the out-of-sample number to weight.`
              : (forward.held_out_auc <= 0.55
                ? `Forward FAIL: held-out AUC ${fmt(forward.held_out_auc)} collapses to chance though in-sample is ${fmt(forward.in_sample_auc)} (optimism ${fmt(forward.optimism)}). Training on the past does not predict the future for this band.`
                : `Forward UNDERPOWERED: held-out AUC ${fmt(forward.held_out_auc)} holds near in-sample ${fmt(forward.in_sample_auc)} but its CI does not yet exclude chance — more weeks of ratings needed.`)}
          </MDTypography>
        ) : (forward && !forward.available ? (
          <MDTypography variant="caption" display="block" sx={{ fontSize: 10.5, mt: 0.3, color: PAL.warnText }}>
            {`Forward validation not assessable (${forward.reason || "insufficient temporal span"}): every AUC above is in-sample.`}
          </MDTypography>
        ) : null)}

        {roc && !loading && !err ? (
          <>
            <Grid container spacing={1.5} alignItems="center" mt={0.2}>
              <Grid item xs={12} md={7}>
                <MDTypography variant="caption" sx={{ fontSize: 10, fontWeight: "bold", color: "#999" }}>
                  CUT-POINT RULE
                </MDTypography>
                {/* 'net benefit' removed: its objective equals prevalence x the cost objective, so it
                    always picked the same point as 'cost'. Each remaining rule carries a plain-language
                    descriptor of what it optimizes clinically. */}
                <ToggleButtonGroup size="small" exclusive value={rule} sx={{ ml: 1 }}
                  onChange={(e, v) => { if (v) setRule(v); }}>
                  {[["youden", "Balanced (Youden)", "balances sensitivity and specificity; prevalence-independent"],
                    ["f1", "Favor detection (F1)", "rewards catching pain; shifts with prevalence, can allow many false triggers"],
                    ["cost", "Cost-weighted", "tune the miss-vs-false-trigger trade-off with the slider"]].map(([k, lbl, tip]) => (
                    <ToggleButton key={k} value={k} title={tip}
                      sx={{ fontSize: 9.5, textTransform: "none", py: 0.2, px: 0.8 }}>{lbl}</ToggleButton>
                  ))}
                </ToggleButtonGroup>
              </Grid>
              {rule === "cost" ? (
                <Grid item xs={12} md={5}>
                  <MDTypography variant="caption" sx={{ fontSize: 9.5, color: "#777" }}>
                    {`FP:FN cost = ${costRatio.toFixed(2)} : 1`}
                  </MDTypography>
                  <Slider size="small" min={-3} max={3} step={0.25} value={logCost}
                    onChange={(e, v) => setLogCost(v)} sx={{ mt: -0.5 }}
                    aria-label="false-trigger to missed-pain cost ratio" />
                  <MDBox display="flex" justifyContent="space-between" sx={{ mt: -0.8 }}>
                    <MDTypography variant="caption" sx={{ fontSize: 8.5, color: "#999" }}>
                      ← fewer false triggers
                    </MDTypography>
                    <MDTypography variant="caption" sx={{ fontSize: 8.5, color: "#999" }}>
                      catch more pain →
                    </MDTypography>
                  </MDBox>
                </Grid>
              ) : null}
            </Grid>

            {op ? (
              <MDBox mt={1} p={1} sx={{
                backgroundColor: op.degenerate ? PAL.warnFill : PAL.passFill, borderRadius: "6px",
                border: op.degenerate ? `1px solid ${PAL.warnBorder}` : "none" }}>
                {op.degenerate ? (
                  <MDTypography variant="caption" display="block" sx={{ fontSize: 11, fontWeight: "bold", color: PAL.warnText, mb: 0.3 }}>
                    ⚠ Degenerate operating point — this cut alarms almost{op.sensitivity < 0.30 ? " never" : " always"} (sensitivity {fmt(op.sensitivity)} · specificity {fmt(op.specificity)}). Not a deployable threshold; move the cost slider toward balance.
                  </MDTypography>
                ) : null}
                <MDTypography variant="caption" sx={{ fontSize: 11.5 }}>
                  <b>Cut-point ({op.rule}):</b>{` power ≥ ${fmt(op.threshold, 3)} `}
                  <span style={{ color: "#777" }}>(oriented log-power units → device LSB in the next panel)</span>
                </MDTypography>
                <MDTypography variant="caption" display="block" sx={{ fontSize: 11.5, mt: 0.2 }}>
                  <b>Sensitivity {fmt(op.sensitivity)}</b> (catches high-pain) · <b>Specificity {fmt(op.specificity)}</b> (avoids false triggers)
                </MDTypography>
                <MDTypography variant="caption" display="block" color="text" sx={{ fontSize: 9.5, mt: 0.3, fontStyle: "italic" }}>
                  Operating point chosen on these data — sensitivity/specificity are optimistic; expect lower accuracy on new ratings.
                </MDTypography>
                <MDTypography variant="caption" display="block" color="text" sx={{ fontSize: 10, mt: 0.3 }}>
                  {`${roc.n_samples} samples · ${roc.n_clusters} independent ratings · `
                    + `prevalence ${fmt(roc.prevalence)} · ${roc.n_boot_ok} bootstrap replicates · `
                    + `match: ${matchDir}`}
                </MDTypography>
              </MDBox>
            ) : null}
          </>
        ) : null}
      </MDBox>
    </Card>
  );
}

export default DeploymentRocPanel;
