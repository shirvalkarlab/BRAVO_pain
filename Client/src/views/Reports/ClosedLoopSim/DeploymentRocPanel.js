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
import { useCachedResult } from "database/useCachedResult";

import { CL, recomputeSlots } from "views/Reports/moduleCacheKeys";
import PanelStaleNote from "./PanelStaleNote";
import PAL from "./palette";
import RocCurrentRemovedLine from "./RocCurrentRemovedLine";
import { TYPE, CARD, STATE } from "assets/theme/base/tokens";
import { plotlyLayout, REF_LINE, directLabel } from "views/Reports/figureStyle";

const fmt = (v, d = 2) => (v == null || !Number.isFinite(Number(v)) ? "—" : Number(v).toFixed(d));

// Audit C9: the cut-point marker lives at a FIXED trace index so effect (B) can move it in place via
// Plotly.restyle without rebuilding the curve (the no-reset discipline). That index was hardcoded as
// a bare `[2]` in two restyle calls and described in two comments — a single source here keeps the
// draw order (effect A) and the restyle target (effect B) from silently drifting apart. Order in the
// base trace array MUST be: 0 = chance line, 1 = ROC curve, 2 = cut-point marker.
const CUTPOINT_TRACE = 2;

// Audit [5]: prefer the backend's FULL-ARRAY operating point. The backend (analytics.deployment_roc)
// now solves every rule on the un-downsampled ROC and ships roc.operating_points = {youden, f1, cost:[
// {log_cost, cost_ratio, ...}]}. The browser's solveCutpoint below re-solves on the DOWNSAMPLED
// fpr/tpr/thr, so its vertex could drift slightly from the backend's exact optimum and that drift
// propagated to Phases C–E. When operating_points is present we snap to it; for 'cost' we pick the
// precomputed point at the slider's nearest log2 cost ratio. Returns the same shape as solveCutpoint
// (so downstream code is unchanged), or null when the payload predates this field (older payloads).
function pickServerCutpoint(roc, rule, logCost) {
  const ops = roc && roc.operating_points;
  if (!ops) return null;
  if (rule === "cost") {
    const list = Array.isArray(ops.cost) ? ops.cost : null;
    if (!list || !list.length) return null;
    // Snap to the precomputed cost point whose log_cost is nearest the slider (grid step 0.25).
    let best = null; let bestD = Infinity;
    for (let i = 0; i < list.length; i += 1) {
      const lc = list[i] && list[i].log_cost;
      if (lc == null || !Number.isFinite(lc)) continue;
      const d = Math.abs(lc - logCost);
      if (d < bestD) { bestD = d; best = list[i]; }
    }
    return best || null;
  }
  const op = ops[rule];
  return (op && Number.isFinite(op.threshold)) ? op : null;
}

// Solve the operating point on the ROC for a given rule, in the browser, from the parallel
// fpr/tpr/thr arrays + prevalence. Returns {k, fpr, tpr, threshold, sensitivity, specificity, ...}.
// Audit [5]: this is now the FALLBACK for payloads that predate roc.operating_points; live callers
// prefer pickServerCutpoint (full-array, exact) and only fall back here for older payloads.
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

function DeploymentRocPanel({ participantUid, bandCandidate, requestParams, onCutpoint, lsbThreshold }) {
  const ref = useRef(null);
  const histRef = useRef(null);
  const fwdRef = useRef(null);
  const [matchDir, setMatchDir] = useState("prior");      // deploy default = causal forecasting
  const [rule, setRule] = useState("youden");
  const [logCost, setLogCost] = useState(0);              // log2(cFP/cFN); 0 => symmetric
  // The figures carry no title on the canvas (SPEC section 3.2); their readings are printed above them.
  const [rocCaption, setRocCaption] = useState(null);
  const [forwardCaption, setForwardCaption] = useState(null);
  const bc = bandCandidate || {};
  const channelRaw = bc.contact;
  const centerHz = bc.center_freq_hz;
  const bandWidthHz = bc.bandwidth_hz || 5.0;

  // THE REQUEST, MINUS THE PARTICIPANT, IS THE CACHE KEY.
  //
  // The match direction belongs in it and the two controls beside it do not, and the difference is
  // worth being explicit about because all three look alike on screen. The match direction changes
  // which neural samples are paired with which pain rating, so it changes what the server computes
  // and it is part of the request. The decision rule and the cost ratio only choose a point ON the
  // curve the server already returned; that solve happens in this browser, so putting either in the
  // key would throw away a curve and refit it in order to move a marker along it.
  const settings = {
    Channel: channelRaw,
    CenterHz: centerHz == null ? null : Number(centerHz),
    BandWidthHz: Number(bandWidthHz),
    MatchDirection: matchDir,
    ...requestParams,
  };

  const cached = useCachedResult({
    moduleKey: CL.roc,
    uid: participantUid,
    settings,
    enabled: !!participantUid && channelRaw != null && centerHz != null,
    fetcher: () => SessionController.query("/api/queryDeploymentROC",
      { ParticipantId: participantUid, ...settings })
      .then((response) => (response && response.data) || null),
  });

  // The envelope is cached and the two pieces this panel draws are read out of it, rather than the
  // pieces being cached separately: they came from one response and are only meaningful together,
  // and the reason an unavailable answer gives lives in the envelope beside them.
  const env = cached.data;
  const envOk = !!(env && env.available && env.roc && env.roc.available);
  const roc = envOk ? env.roc : null;
  const forward = envOk ? (env.forward || null) : null;   // audit C2: held-out forward-chaining trace
  const loading = cached.loading;
  const err = cached.err
    || (env && !envOk
      ? ((env.reason || (env.roc && env.roc.reason)) || "ROC unavailable")
      : null);

  const costRatio = Math.pow(2, logCost);
  // Audit [5]: snap to the backend's full-array operating point when available; fall back to the
  // browser's downsampled-curve solver only for payloads that predate roc.operating_points.
  const op = roc ? (pickServerCutpoint(roc, rule, logCost) || solveCutpoint(roc, rule, costRatio)) : null;
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
        line: REF_LINE, hoverinfo: "skip", showlegend: false },
      { x: roc.fpr, y: roc.tpr, type: "scatter", mode: "lines", name: "ROC",
        line: { color: PAL.series, width: 2 }, showlegend: false,
        hovertemplate: "low-pain moments flagged as high %{x:.0%} · high-pain moments caught %{y:.0%}<extra></extra>" },
      // cut-point marker placeholder at index CUTPOINT_TRACE (=2) — kept fixed so restyle can move it.
      { x: [], y: [], type: "scatter", mode: "markers", name: "cut-point", showlegend: false,
        marker: { color: PAL.cutpoint, size: 12, line: { color: PAL.surface, width: 2 } },
        hovertemplate: "cut-point<extra></extra>" },
    ];
    // No title on the canvas (SPEC section 3.2): the reading is printed above the figure instead.
    setRocCaption(`How well it tells high pain from low: ${fmt(roc.auc)} (0.5 = coin toss, 1 = perfect)`
      + `${ciTxt}${bootTxt}${smallTxt}`);
    const layout = plotlyLayout({
      margin: { l: 56, r: 16, t: 16, b: 48 }, height: 320,
      xaxis: { title: { text: "low-pain moments flagged as high" }, range: [-0.02, 1.02], tickformat: ".0%" },
      yaxis: { title: { text: "high-pain moments caught" }, range: [-0.02, 1.02], tickformat: ".0%" },
      annotations: [directLabel(0.62, 0.6, "coin toss", PAL.ink3)],
    });
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
        hovertemplate: [`switching point (${op.rule})<br>power ≥ ${fmt(op.threshold)}<br>`
          + `high-pain moments caught ${fmt(op.sensitivity)} · low-pain moments left alone ${fmt(op.specificity)}<extra></extra>`],
      }, [CUTPOINT_TRACE]);
      // Flip the label offset toward the plot interior near the top/right edges so it never clips
      // off-panel (F1 lands near (0.67,0.95); a low cost ratio pushes the point toward (0.94,1.0)).
      const nearRight = op.fpr > 0.65;
      const nearTop = op.tpr > 0.85;
      const ax = nearRight ? -30 : 28;
      const ay = nearTop ? 24 : -26;   // positive ay pushes the box DOWN (interior) when near the top
      // Audit C6: white-on-#E69F00 (the degenerate warn fill) is 2.25:1 — below WCAG. Use near-black
      // text on the orange callout (7.7:1); keep white only on the bluish-green non-degenerate marker.
      const labelTextColor = PAL.onFill;
      Plotly.relayout(gd, { annotations: [{
        x: op.fpr, y: op.tpr, xref: "x", yref: "y",
        text: `<b>power ≥ ${fmt(op.threshold)}</b>`, showarrow: true, arrowhead: 0,
        arrowcolor: mColor, ax, ay, font: { size: PAL.fs.caption, color: labelTextColor },
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
        marker: { color: PAL.painLow, opacity: 0.55 }, showlegend: false,
        hovertemplate: "low pain<br>power %{x:.2f}<br>%{y} samples<extra></extra>" },
      { x: fh.bin_centers, y: fh.counts_high, type: "bar", name: "pain-high",
        marker: { color: "rgba(0,0,0,0)", line: { color: PAL.painHighOutline, width: 1.6 } }, showlegend: false,
        hovertemplate: "high pain<br>power %{x:.2f}<br>%{y} samples<extra></extra>" },
    ];
    const binW = (fh.bin_centers.length > 1)
      ? (fh.bin_centers[1] - fh.bin_centers[0]) : (fh.x_max - fh.x_min) || 1;
    const layout = plotlyLayout({
      barmode: "overlay", bargap: 0.04,
      margin: { l: 56, r: 16, t: 24, b: 48 }, height: 188,
      xaxis: { title: { text: "band power, standardised (0 = its average; higher goes with more pain)" },
        range: [fh.x_min - binW, fh.x_max + binW] },
      yaxis: { title: { text: "band-power readings" } },
      shapes: [], annotations: [],
    });
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
      // Audit [42]: annotate the cut line with the RESULTING device LSB (lifted from Phase C) right
      // beside the oriented-log-power cut, so the histogram shows BOTH numbers the deployment
      // connects — not just the feature-scale cut whose LSB the reader had to find in the next panel.
      const lsbTxt = (lsbThreshold && Number.isFinite(Number(lsbThreshold.upperLsb)))
        ? `<br>${lsbThreshold.estimated ? "≈" : "="} ${fmt(lsbThreshold.upperLsb, 1)} LSB${lsbThreshold.estimated ? " (est.)" : ""}`
        : "";
      Plotly.relayout(gd, {
        shapes: [{ type: "line", x0: opThr, x1: opThr, yref: "paper", y0: 0, y1: 1,
          line: { color: lineColor, width: 2, dash: "dash" } }],
        annotations: [{ x: opThr, y: 1, yref: "paper", yanchor: "bottom",
          text: `cut ≥ ${fmt(opThr)}${lsbTxt}`, showarrow: false, align: "center",
          font: { size: PAL.fs.caption, color: lineColor },
          xanchor: opThr > (fh.x_min + fh.x_max) / 2 ? "right" : "left" }],
      });
    } else {
      Plotly.relayout(gd, { shapes: [], annotations: [] });
    }
  }, [roc, opThr, op && op.degenerate, lsbThreshold]);  // eslint-disable-line react-hooks/exhaustive-deps

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
    // Above the coin toss filled, at or below it hollow: shape, not a red-green pair.
    const symbols = folds.map((f) => (f.test_auc > 0.5 ? "circle" : "circle-open"));
    const xlo = Math.min(...xs) - 0.5;
    const xhi = Math.max(...xs) + 0.5;
    const traces = [
      // pooled held-out CI band (drawn first so it sits behind everything)
      ...(forward.held_out_auc_lo != null && forward.held_out_auc_hi != null ? [{
        x: [xlo, xhi, xhi, xlo], y: [forward.held_out_auc_lo, forward.held_out_auc_lo,
          forward.held_out_auc_hi, forward.held_out_auc_hi],
        fill: "toself", type: "scatter", mode: "lines", line: { width: 0 },
        fillcolor: PAL.fillMuted, hoverinfo: "skip", showlegend: false, name: "held-out 95% range",
      }] : []),
      { x: [xlo, xhi], y: [0.5, 0.5], type: "scatter", mode: "lines", name: "chance",
        line: REF_LINE, hoverinfo: "skip", showlegend: false },
      // in-sample AUC reference (the optimistic number the forward trace is judged against)
      ...(forward.in_sample_auc != null ? [{
        x: [xlo, xhi], y: [forward.in_sample_auc, forward.in_sample_auc], type: "scatter", mode: "lines",
        name: "on the data it was fitted to", line: { color: PAL.gray, dash: "dash", width: 1.2 },
        hovertemplate: `measured on the data it was fitted to: ${fmt(forward.in_sample_auc)}<extra></extra>`, showlegend: false,
      }] : []),
      // pooled held-out AUC reference line
      ...(forward.held_out_auc != null ? [{
        x: [xlo, xhi], y: [forward.held_out_auc, forward.held_out_auc], type: "scatter", mode: "lines",
        name: "all later weeks together", line: { color: PAL.ink, width: 1 },
        hovertemplate: `all later weeks together: ${fmt(forward.held_out_auc)}<extra></extra>`, showlegend: false,
      }] : []),
      // per-fold held-out AUC (the trace itself)
      { x: xs, y: ys, type: "scatter", mode: "lines+markers", name: "per-fold held-out",
        line: { color: PAL.series, width: 1.5 }, showlegend: false,
        marker: { color: PAL.series, symbol: symbols, size: 9, line: { color: PAL.series, width: 1.5 } },
        customdata: folds.map((f) => [f.n_train_clusters, f.n_test_clusters,
          f.sens == null ? "—" : fmt(f.sens), f.spec == null ? "—" : fmt(f.spec)]),
        hovertemplate: "week %{x} · on that week, not fitted on it: %{y:.2f}<br>trained on %{customdata[0]} / tested on %{customdata[1]} separate groups of ratings"
          + "<br>high-pain moments caught %{customdata[2]} · low-pain moments left alone %{customdata[3]}<extra></extra>" },
    ];
    setForwardCaption("Tested on each later week after training on the weeks before: "
      + `${fmt(forward.held_out_auc)}`
      + (forward.held_out_auc_lo != null ? ` (95% range ${fmt(forward.held_out_auc_lo)} to ${fmt(forward.held_out_auc_hi)})` : "")
      + `, against ${fmt(forward.in_sample_auc)} measured on the data it was fitted to (0.5 = coin toss).`);
    const layout = plotlyLayout({
      margin: { l: 56, r: 72, t: 16, b: 48 }, height: 200,
      xaxis: { title: { text: "week tested (trained on every earlier week)" }, range: [xlo, xhi] },
      yaxis: { title: { text: "how well it tells high pain from low" }, range: [-0.02, 1.02] },
      annotations: [directLabel(xhi, 0.5, "coin toss", PAL.ink3),
        ...(forward.in_sample_auc != null ? [directLabel(xhi, forward.in_sample_auc, "fitted data", PAL.ink3)] : [])],
    });
    Plotly.react(gd, traces, layout, PAL.MODEBAR);
  }, [forward]);  // eslint-disable-line react-hooks/exhaustive-deps

  // Purge only on unmount (NOT on every roc/op change) so the figure nodes are reused across refits.
  useEffect(() => {
    const g1 = ref.current; const g2 = histRef.current; const g3 = fwdRef.current;
    return () => { if (g1) Plotly.purge(g1); if (g2) Plotly.purge(g2); if (g3) Plotly.purge(g3); };
  }, []);

  return (
    <Card sx={{ ...CARD, width: "100%" }}>
      <MDBox p={3}>
        <MDBox display="flex" justifyContent="space-between" alignItems="baseline" mb={1} flexWrap="wrap" gap={1}>
          <MDTypography component="h3" sx={{ ...TYPE.title, color: PAL.ink }}>
            Where does the switching point sit?
          </MDTypography>
          {/* Match direction changes which neural samples are paired with which pain rating, so it
              changes the fit rather than the view. It is labelled in clinical terms (not the internal
              'prior'/'pro_first' keys) and the deploy default is marked. Since results are now kept
              across navigation, switching it no longer refits immediately: the curve on screen stays,
              the notice below says it was computed under the other direction, and the refit happens
              when it is asked for. */}
          <ToggleButtonGroup size="small" exclusive value={matchDir}
            onChange={(e, v) => { if (v) setMatchDir(v); }}
            title="Each recording picks the next report after it: the question the device faces, and the default. Each report picks its nearest recordings: exploratory. Switching does not refit on its own; the curve already computed stays on screen and is marked, and Recompute refits it.">
            <ToggleButton value="prior" sx={{ ...TYPE.body, textTransform: "none", py: 0.5 }}>
              Next report after each recording (default)
            </ToggleButton>
            <ToggleButton value="pro_first" sx={{ ...TYPE.body, textTransform: "none", py: 0.5 }}>
              Nearest recordings to each report
            </ToggleButton>
          </ToggleButtonGroup>
        </MDBox>

        <PanelStaleNote stale={cached.stale} staleReasons={cached.staleReasons}
          loading={cached.loading} notKept={cached.notKept}
          onRecompute={() => recomputeSlots(participantUid, [CL.roc])} />

        {/* Status banner sits ABOVE the figure; the graph node below stays mounted across refits so
            its zoom/pan and DOM are preserved (Plotly.react updates it in place). */}
        {loading ? (
          <MDTypography sx={{ ...TYPE.body, color: PAL.ink2 }}>
            Working out how well band power tells high pain from low, with its 95% range…
          </MDTypography>
        ) : err ? (
          <MDTypography sx={{ ...TYPE.body, color: PAL.ink2 }}>
            <span aria-hidden="true" style={{ marginRight: 6 }}>{STATE.notChecked.glyph}</span>
            {`Not available: ${err}.`}
          </MDTypography>
        ) : null}
        {roc && rocCaption ? (
          <MDTypography sx={{ ...TYPE.body, color: PAL.ink, mb: 1 }}>{rocCaption}</MDTypography>
        ) : null}

        {/* Always-mounted figure container. Hidden (not unmounted) when there's no ROC yet, so the
            Plotly graph object survives loading/refit cycles instead of being torn down. */}
        <div ref={ref} style={{ width: "100%", display: roc ? "block" : "none" }} />
        {/* The same area with the stimulation current taken out (2026-09-26), descriptive only. */}
        <RocCurrentRemovedLine plainAuc={roc ? roc.auc : null} adjusted={envOk ? env.auc_current_removed : null} />

        {/* Feature-distribution histogram beneath the ROC (pain-high vs pain-low), with the cut-point
            threshold line drawn on top. Also always-mounted so it survives refits. Only shown when
            the backend returns feature_hist (older payloads / off-band candidates may omit it). */}
        {roc && roc.feature_hist ? (
          <MDTypography sx={{ ...TYPE.caption, color: PAL.ink3, mt: 2 }}>
            Filled bars: readings matched to low-pain reports. Outlined bars: readings matched to
            high-pain reports. The dashed line is the switching point.
          </MDTypography>
        ) : null}
        <div ref={histRef}
          style={{ width: "100%", display: roc && roc.feature_hist ? "block" : "none" }} />

        {/* Forward-chaining held-out AUC trace (audit C2). Always-mounted so it survives refits; shown
            only when the backend returns a usable forward block with at least one fold. */}
        {forward && forward.available && forwardCaption ? (
          <MDTypography sx={{ ...TYPE.body, color: PAL.ink, mt: 2 }}>{forwardCaption}</MDTypography>
        ) : null}
        <div ref={fwdRef}
          style={{ width: "100%",
            display: forward && forward.available && forward.folds && forward.folds.length ? "block" : "none" }} />

        {/* Plain-language read of the forward result: clears chance / collapses forward / underpowered /
            not assessable. This is the out-of-sample number to weight, beside the optimistic in-sample one. */}
        {forward && forward.available && forward.held_out_auc != null ? (
          <MDTypography display="block" sx={{ ...TYPE.body, mt: 1,
            color: forward.beats_chance_forward ? PAL.ink : PAL.warnText }}>
            <span aria-hidden="true" style={{ marginRight: 6 }}>
              {forward.beats_chance_forward ? STATE.pass.glyph : STATE.caution.glyph}
            </span>
            {forward.beats_chance_forward
              ? `Holds on later weeks: ${fmt(forward.held_out_auc)} on weeks it was not fitted on, better than a coin toss across ${forward.n_folds} weeks (it reads ${fmt(forward.optimism)} lower than on the data it was fitted to). This is the number to weigh.`
              : (forward.held_out_auc <= 0.55
                ? `Does not hold on later weeks: ${fmt(forward.held_out_auc)} on weeks it was not fitted on, about a coin toss, though it reads ${fmt(forward.in_sample_auc)} on the data it was fitted to (${fmt(forward.optimism)} higher). Training on the past does not predict the future for this band.`
                : `Not enough weeks yet: ${fmt(forward.held_out_auc)} on weeks it was not fitted on, near the ${fmt(forward.in_sample_auc)} on the data it was fitted to, but its 95% range still includes a coin toss; more weeks of ratings are needed.`)}
          </MDTypography>
        ) : (forward && !forward.available ? (
          <MDTypography display="block" sx={{ ...TYPE.body, mt: 1, color: PAL.ink2 }}>
            <span aria-hidden="true" style={{ marginRight: 6 }}>{STATE.notChecked.glyph}</span>
            {`Could not test it on later weeks (${forward.reason || "the ratings do not span enough weeks"}): every reading above is on the data it was fitted to.`}
          </MDTypography>
        ) : null)}

        {roc && !loading && !err ? (
          <>
            <Grid container spacing={1.5} alignItems="center" mt={0.2}>
              <Grid item xs={12} md={7}>
                <MDTypography variant="caption" sx={{ ...TYPE.caption, fontWeight: 600, color: PAL.ink3 }}>
                  How the switching point is chosen
                </MDTypography>
                {/* 'net benefit' removed: its objective equals prevalence x the cost objective, so it
                    always picked the same point as 'cost'. Each remaining rule carries a plain-language
                    descriptor of what it optimizes clinically. */}
                <ToggleButtonGroup size="small" exclusive value={rule} sx={{ ml: 1 }}
                  onChange={(e, v) => { if (v) setRule(v); }}>
                  {[["youden", "Balanced", "weighs catching high pain and leaving low pain alone equally, whatever the share of high-pain reports (Youden's rule)"],
                    ["f1", "Favour catching pain", "rewards catching high pain; moves with the share of high-pain reports and can switch often when it should not (the F1 rule)"],
                    ["cost", "Weighted", "set the cost of a needless switch against a missed high-pain moment with the slider"]].map(([k, lbl, tip]) => (
                    <ToggleButton key={k} value={k} title={tip}
                      sx={{ ...TYPE.body, textTransform: "none", py: 0.5, px: 1 }}>{lbl}</ToggleButton>
                  ))}
                </ToggleButtonGroup>
              </Grid>
              {rule === "cost" ? (
                <Grid item xs={12} md={5}>
                  <MDTypography variant="caption" sx={{ ...TYPE.caption, color: PAL.ink3 }}>
                    {`cost of a needless switch against a missed high-pain moment = ${costRatio.toFixed(2)} : 1`}
                  </MDTypography>
                  <Slider size="small" min={-3} max={3} step={0.25} value={logCost}
                    onChange={(e, v) => setLogCost(v)} sx={{ mt: -0.5 }}
                    aria-label="false-trigger to missed-pain cost ratio" />
                  <MDBox display="flex" justifyContent="space-between" sx={{ mt: -0.8 }}>
                    <MDTypography variant="caption" sx={{ ...TYPE.caption, color: PAL.ink3 }}>
                      ← fewer needless switches
                    </MDTypography>
                    <MDTypography variant="caption" sx={{ fontSize: PAL.fs.caption, color: PAL.ink3 }}>
                      catch more pain →
                    </MDTypography>
                  </MDBox>
                </Grid>
              ) : null}
            </Grid>

            {op ? (
              <MDBox mt={2} pt={2} sx={{ borderTop: `1px solid ${PAL.rule}` }}>
                {op.degenerate ? (
                  <MDTypography display="block" sx={{ ...TYPE.body, fontWeight: 600, color: PAL.warnText, mb: 0.5 }}>
                    <span aria-hidden="true" style={{ marginRight: 6 }}>{STATE.caution.glyph}</span>
                    This switching point would switch almost{op.sensitivity < 0.30 ? " never" : " always"} (high-pain moments caught {fmt(op.sensitivity)} · low-pain moments left alone {fmt(op.specificity)}). It could not be used to drive closed-loop stimulation; move the slider toward balance.
                  </MDTypography>
                ) : null}
                <MDTypography sx={{ ...TYPE.body, color: PAL.ink }}>
                  <b style={{ fontWeight: 600 }}>Switching point ({op.rule}):</b>{` power ≥ ${fmt(op.threshold, 3)} `}
                  <span style={{ color: PAL.ink3 }}>(oriented, standardized band power units → device LSB in the next panel)</span>
                </MDTypography>
                <MDTypography display="block" sx={{ ...TYPE.body, color: PAL.ink, mt: 0.5 }}>
                  <b style={{ fontWeight: 600 }}>High-pain moments caught {fmt(op.sensitivity)}</b> · <b style={{ fontWeight: 600 }}>low-pain moments left alone {fmt(op.specificity)}</b>
                </MDTypography>
                <MDTypography display="block" sx={{ ...TYPE.body, color: PAL.ink2, mt: 0.5 }}>
                  The switching point was chosen on these same data, so both numbers are optimistic; expect lower accuracy on new ratings.
                </MDTypography>
                <MDTypography display="block" sx={{ ...TYPE.caption, color: PAL.ink3, mt: 0.5 }}>
                  {`${roc.n_samples} band-power readings · ${roc.n_clusters} separate groups of pain reports, `
                    + `at least ${env.refractory_min != null ? fmt(env.refractory_min, 0) : "?"} minutes apart · `
                    + `share of high-pain reports ${fmt(roc.prevalence)} · ${roc.n_boot_ok} resamples · `
                    + `matching: ${matchDir === "prior" ? "next report after each recording" : "nearest recordings to each report"}`}
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
