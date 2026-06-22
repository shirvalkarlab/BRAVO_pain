/**
=========================================================
* UF BRAVO Platform -- Pain Biomarkers report (Shirvalkar Lab)
=========================================================
* Renders the selectable-source biomarker timeline (time-domain PSD<->pain and/or the
* power-domain ~10-min LFP threshold detector) returned by /api/queryBiomarkerAnalysis.
*/

import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { Card, Grid, Select, MenuItem, FormControl,
  Slider, LinearProgress, CircularProgress } from "@mui/material";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import MDButton from "components/MDButton";

import BiomarkerTimeline from "./BiomarkerTimeline";
import BiomarkerDataTimeline from "./BiomarkerDataTimeline";
import BiomarkerAnalytics from "./BiomarkerAnalytics";
import BinarizationPreview from "./BinarizationPreview";

import DatabaseLayout from "layouts/DatabaseLayout";

import { SessionController } from "database/session-control";
import { usePlatformContext, setContextState } from "context.js";

// Pain metric the LFP biomarker is computed against (sent as LabelMetric). Used until the server
// echoes its own `available_metrics` list. The composite blends MPQ sum + left-leg VAS.
const DEFAULT_METRIC_OPTIONS = [
  { key: "nrs", label: "NRS (0–10)" },
  { key: "vas", label: "Overall VAS" },
  { key: "left_leg_vas", label: "Left Leg VAS" },
  { key: "back_vas", label: "Back VAS" },
  { key: "mpq_sum", label: "MPQ Sum" },
  { key: "composite_mpq_leftleg", label: "Composite (MPQ + Left Leg VAS)" },
];

// How the continuous pain score is turned into the binary high/low pain_level the detector trains
// on (sent as LabelStrategy). "tertile" (default) splits low/high and drops the ambiguous middle —
// the cleanest detector target on RCS08; "median" keeps every day at a 50/50 split; "kmeans" is the
// legacy 2-cluster notebook labeler. The cut is computed on the DAILY PRO distribution and
// broadcast to samples, so recording density no longer biases the split.
// See docs/binarization_recommendation_RCS08.md.
const DEFAULT_STRATEGY_OPTIONS = [
  { key: "tertile", label: "Tertile (low/high, drop middle)" },
  { key: "median", label: "Median split" },
  { key: "kmeans", label: "KMeans (legacy)" },
];

function Biomarkers() {
  const navigate = useNavigate();
  const [controller, dispatch] = usePlatformContext();
  const { language } = controller;
  const { participant_uid } = useParams();

  const [data, setData] = useState(false);
  // Source tabs (time-domain / power-domain / both) removed — the analysis is always unified
  // (time-domain streaming PSD + power-domain band power together). One code path, no tab.
  const source = "both";
  const [metric, setMetric] = useState("nrs");
  const [strategy, setStrategy] = useState("tertile");   // binarization labeler (default tertile)
  const [percentileLow, setPercentileLow] = useState(33.3);   // tertile/percentile low cut
  const [percentileHigh, setPercentileHigh] = useState(66.7);  // tertile/percentile high cut
  const slidingWindow = false;   // sliding-window analysis removed — always all-data, one threshold
  // The biomarker is EXPENSIVE (full-resolution detector over ~300k rows), so it is computed only
  // when the user clicks "Compute biomarker now" — never automatically on a settings change. This
  // holds the snapshot of options actually computed; the fetch effect runs only when it changes.
  const [requestParams, setRequestParams] = useState(null);
  const [computing, setComputing] = useState(false);
  const [alert, setAlert] = useState(null);

  // Raw pain-score distribution for the LIVE binarization preview card. Fetched once per
  // participant (lightweight — daily PRO survey rows only, no LFP); the card recomputes the
  // high/low cuts client-side as the user changes strategy or drags the percentile sliders,
  // so no /queryBiomarkerAnalysis roundtrip is needed for the preview.
  const [painScores, setPainScores] = useState(null);
  const [painLoading, setPainLoading] = useState(false);

  // ALWAYS-ON data-availability timeline. This is for visualization/exploration and must show on
  // page load WITHOUT requiring "Compute biomarker now" — so it has its own lightweight endpoint
  // (/queryDataAvailability assembles records/pain/stim/freq_bands with NO biomarker computation),
  // fetched once per participant. The heavy compute still returns its own availability payload;
  // we prefer the live one here so the timeline is populated before (and independent of) compute.
  const [availData, setAvailData] = useState(null);
  const [availLoading, setAvailLoading] = useState(false);

  const snapshot = () => ({
    source, LabelMetric: metric, LabelStrategy: strategy,
    PercentileLow: percentileLow, PercentileHigh: percentileHigh,
    SlidingWindow: slidingWindow,
  });
  const compute = () => setRequestParams(snapshot());
  // "Dirty" = the live options differ from what's currently displayed (or nothing computed yet),
  // so the shown results are stale and a (re)compute is needed.
  const dirty = !requestParams || JSON.stringify(requestParams) !== JSON.stringify(snapshot());

  useEffect(() => {
    if (!participant_uid) {
      navigate("/database", { replace: false });
      return;
    }
    setContextState(dispatch, "report", "CustomizedAnalysis");
  }, [participant_uid]);

  // Fetch ONLY when a compute was requested (requestParams set by the Compute button). Progress is
  // shown INLINE (a labeled bar in the card) instead of the generic "loading data" overlay.
  useEffect(() => {
    if (!participant_uid || !requestParams) return;
    setComputing(true);
    SessionController.query("/api/queryBiomarkerAnalysis", {
      ParticipantId: participant_uid, ...requestParams,
    }).then((response) => {
      setData(response.data);
      setComputing(false);
    }).catch((error) => {
      setComputing(false);
      SessionController.displayError(error, setAlert);
    });
  }, [participant_uid, requestParams]);

  // Fetch raw pain-score reports ONCE per participant (no LFP, just the PRO surveys) so the
  // binarization preview card can show a live histogram with cuts before any heavy compute.
  useEffect(() => {
    if (!participant_uid) return;
    setPainLoading(true);
    SessionController.query("/api/queryPainScores", { ParticipantId: participant_uid })
      .then((response) => {
        setPainScores(response.data);
        setPainLoading(false);
      })
      .catch(() => { setPainLoading(false); /* preview is optional — degrade silently */ });
  }, [participant_uid]);

  // Fetch the data-availability payload ONCE per participant (lightweight, no biomarker compute),
  // so the timeline renders immediately on page load.
  useEffect(() => {
    if (!participant_uid) return;
    setAvailLoading(true);
    SessionController.query("/api/queryDataAvailability", { ParticipantId: participant_uid })
      .then((response) => {
        setAvailData(response.data);
        setAvailLoading(false);
      })
      .catch(() => { setAvailLoading(false); /* timeline is optional — degrade silently */ });
  }, [participant_uid]);

  // The object handed to the timeline: prefer the live availability payload; fall back to the
  // availability embedded in a heavy compute result if the live fetch is unavailable.
  const timelineData = (availData && availData.availability && availData.availability.records
    && availData.availability.records.length > 0)
    ? availData
    : data;

  // The points array for the currently-selected pain metric, fed straight into the preview card.
  // The composite metric ("composite_mpq_leftleg") is NOT a raw PRO column returned by
  // /queryPainScores; it is synthesized here exactly as the backend does — the per-day average of
  // z(MPQ-sum) and z(left-leg-VAS) across all surveys, keeping a day when either part exists.
  const previewPoints = (() => {
    if (!painScores || !Array.isArray(painScores.metrics)) return [];
    if (metric === "composite_mpq_leftleg") {
      const get = (k) => {
        const m = painScores.metrics.find((x) => x.key === k);
        return m ? m.points : [];
      };
      const zStats = (pts) => {
        const vs = pts.map((p) => p.v).filter((v) => v != null && Number.isFinite(v));
        if (vs.length < 2) return null;
        const mu = vs.reduce((s, v) => s + v, 0) / vs.length;
        const sd = Math.sqrt(vs.reduce((s, v) => s + (v - mu) ** 2, 0) / vs.length) || 1;
        return { mu, sd };
      };
      const mpq = get("mpq_sum"), leg = get("left_leg_vas");
      const sM = zStats(mpq), sL = zStats(leg);
      if (!sM && !sL) return [];
      // Index each part's z-score by timestamp, then average the available parts per day.
      const zByT = {};
      const add = (pts, st, slot) => {
        if (!st) return;
        pts.forEach((p) => {
          if (p.v == null || !Number.isFinite(p.v)) return;
          const key = String(p.t);
          (zByT[key] = zByT[key] || {})[slot] = (p.v - st.mu) / st.sd;
        });
      };
      add(mpq, sM, "m"); add(leg, sL, "l");
      return Object.keys(zByT).sort().map((t) => {
        const z = zByT[t];
        const parts = [z.m, z.l].filter((v) => v != null && Number.isFinite(v));
        return parts.length ? { t, v: parts.reduce((s, v) => s + v, 0) / parts.length } : null;
      }).filter(Boolean);
    }
    const m = painScores.metrics.find((x) => x.key === metric);
    return m ? m.points : [];
  })();
  const previewMetricLabel = (((data && data.available_metrics) || DEFAULT_METRIC_OPTIONS)
    .find((m) => m.key === metric) || {}).label || metric;

  // Live pain series for the timeline's pain row, in the {metric, t:[epoch_s], y:[]} shape the
  // BiomarkerDataTimeline expects. Built from the lightweight previewPoints (fetched once per
  // participant) so changing the metric updates the pain plot INSTANTLY — no recompute. previewPoints
  // carry `t` as a timestamp string and `v` as the value; convert to epoch seconds.
  // Memoized so its object identity is STABLE across re-renders that don't touch its inputs (e.g.
  // dragging the tertile sliders, which changes binarization but not the pain row). A new identity
  // would re-run the timeline's Plotly effect and reset the page scroll, so only recompute when the
  // metric or the underlying preview points actually change.
  const painSeriesLive = useMemo(() => {
    if (!previewPoints || !previewPoints.length) return null;
    const pairs = previewPoints
      .map((p) => [Date.parse(p.t) / 1000, p.v])
      .filter(([t, v]) => Number.isFinite(t) && v != null && Number.isFinite(v))
      .sort((a, b) => a[0] - b[0]);
    return { metric, t: pairs.map((p) => p[0]), y: pairs.map((p) => p[1]) };
  }, [previewPoints, metric]);

  // Render an honest, multi-line summary for a branch: the headline estimate plus the rigor
  // statistics (FDR q, permutation p, autocorrelation-adjusted effective n, Fisher-z CI for the
  // time domain; balanced accuracy vs chance + AUC for the power domain) and any caveats.
  const summaryLine = (label, s) => {
    if (!s) return null;
    const Line = ({ children, color = "dark", bold = false }) => (
      <MDTypography variant="button" fontWeight={bold ? "medium" : "regular"} color={color} display="block">
        {children}
      </MDTypography>
    );
    // Small italic caption for honesty caveats (provenance, CI conditions, label source).
    const Note = ({ children, color = "dark" }) => (
      <MDTypography variant="caption" fontStyle="italic" color={color} display="block">
        {children}
      </MDTypography>
    );

    // Power-domain (threshold detector) branch.
    if (s.best_threshold !== undefined) {
      const aucTxt = s.auc != null ? `  AUC=${fmt(s.auc)} (in-sample)` : "";
      const rhoTxt = s.lfp_vs_continuous_pain_spearman != null
        ? `  Spearman ρ(LFP, pain)=${fmt(s.lfp_vs_continuous_pain_spearman)}` : "";
      return (
        <MDBox mb={0.5}>
          <Line bold>
            {`${label}: threshold=${fmt(s.best_threshold)}  sens=${fmt(s.sens)}  spec=${fmt(s.spec)}  n_windows=${s.n_windows ?? "—"}`}
          </Line>
          <Line>
            {`balanced accuracy=${fmt(s.balanced_accuracy)} vs chance=${fmt(s.chance_accuracy != null ? s.chance_accuracy : 0.5)}` +
             `  (prevalence=${fmt(s.prevalence)}` +
             `${s.majority_accuracy != null ? `, majority-class raw acc=${fmt(s.majority_accuracy)}` : ""})${aucTxt}${rhoTxt}`}
          </Line>
          {s.overfit_warning ? <Line color="warning">{`⚠ ${s.overfit_warning}`}</Line> : null}
          {s.batch_confound_warning ? <Line color="warning">{`⚠ ${s.batch_confound_warning}`}</Line> : null}
          {s.in_sample ? (
            <Line color="warning">{`⚠ ${s.note || "All-data fit: scored on the same data (in-sample, optimistic — not a generalization estimate)."}`}</Line>
          ) : null}
          {s.pain_level_note ? <Note>{s.pain_level_note}</Note> : null}
        </MDBox>
      );
    }

    // Time-domain (PSD↔pain correlation) branch.
    if (s.band !== undefined || s.freq_hz !== undefined) {
      const ci = Array.isArray(s.r_ci) ? s.r_ci : null;
      const ciTxt = ci && ci[0] != null && ci[1] != null ? `  95% CI [${fmt(ci[0])}, ${fmt(ci[1])}]` : "";
      const fdrTxt = s.fdr_q != null ? `  FDR q=${fmtP(s.fdr_q)}${s.fdr_significant ? " ✓" : ""}` : "";
      // Lead with the selection- and autocorrelation-aware permutation p (the only honest headline
      // significance for a selected band); fall back to the raw per-test p only if perm p is absent.
      const permTxt = s.perm_p != null ? `  perm p=${fmtP(s.perm_p)}` : `  p=${fmtP(s.p)}`;
      const nTxt = s.n != null
        ? `n=${s.n}${s.n_effective != null ? ` (effective n=${fmt(s.n_effective)} after autocorrelation)` : ""}`
        : "";
      // Honest significance verdict: the band is "real" only if it survives BOTH the selection-
      // aware permutation test AND the per-cell FDR. perm_p is the primary statement.
      const permSig = s.perm_p != null && s.perm_p < 0.05;
      const notSignificant = (s.perm_p != null || s.fdr_q != null) && !permSig && !s.fdr_significant;
      return (
        <MDBox mb={0.5}>
          <Line bold>
            {`${label}: ${s.channel || ""} ${fmt(s.freq_hz)} Hz  r=${fmt(s.r)}${ciTxt}${permTxt}${fdrTxt}`}
          </Line>
          {nTxt ? <Line>{nTxt}</Line> : null}
          {s.stim_adjusted_r != null ? (
            <Line>{`stim-adjusted r=${fmt(s.stim_adjusted_r)} (partial correlation removing stim amplitude)`}</Line>
          ) : s.stim_adjusted_note ? (
            <Line>{`stim adjustment: ${s.stim_adjusted_note}`}</Line>
          ) : null}
          {s.narrow_peak_warning ? (
            <Line color="warning">{"⚠ Correlation is concentrated in a single ~1 Hz bin on a stimulated lead — check for a stim/sensing line artifact, not a broad neural rhythm."}</Line>
          ) : null}
          {notSignificant ? (
            <Line color="error">{"⚠ NOT statistically significant after correcting for the band search (permutation p) and temporal autocorrelation (FDR q). This correlation is consistent with chance — treat as a negative/exploratory result, not a validated biomarker."}</Line>
          ) : (!s.fdr_significant && permSig ? (
            <Line color="warning">{"Significant by the selection-corrected permutation test but not the more conservative per-cell FDR — treat the permutation result as primary."}</Line>
          ) : null)}
          {s.r_ci_note ? <Note>{`r and CI are ${s.r_ci_note}`}</Note> : null}
        </MDBox>
      );
    }
    return null;
  };

  return (
    <>
      {alert}
      <DatabaseLayout>
        <MDBox pt={3}>
          <Grid container spacing={2}>
            <Grid item xs={12}>
              <Card sx={{ width: "100%" }}>
                <Grid container>
                  {/* Title row (source tabs removed — analysis is always unified time + power) */}
                  <Grid item xs={12}>
                    <MDBox px={2} pt={2} pb={1} display="flex" flexDirection="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={2}>
                      <MDTypography variant="h5" fontSize={28} fontWeight="bold">
                        {"Pain Biomarkers"}
                      </MDTypography>
                    </MDBox>
                  </Grid>

                  {/* ── DATA-AVAILABILITY TIMELINE up front (ALWAYS shown) ────────────────────
                      For visualization/exploration: rendered on page load from the lightweight
                      /queryDataAvailability payload (timelineData), with NO "Compute biomarker
                      now" required. The pain row is driven LIVE by the selected metric
                      (painSeriesLive) so it updates instantly when the metric picker below
                      changes. Falls back to the legacy timeline only if no availability payload
                      is available at all. The Compute button lives BELOW this. */}
                  {timelineData && timelineData.availability && timelineData.availability.records
                        && timelineData.availability.records.length > 0 ? (
                    <Grid item xs={12}>
                      <BiomarkerDataTimeline data={timelineData} painOverride={painSeriesLive} />
                    </Grid>
                  ) : (timelineData && timelineData.timeline && timelineData.timeline.length > 0 ? (
                    <Grid item xs={12}>
                      <BiomarkerTimeline data={timelineData} figureTitle={"BiomarkerTimeline"} />
                    </Grid>
                  ) : (
                    <Grid item xs={12}>
                      <MDBox px={2} pb={1.5}>
                        <MDTypography variant="button" color="text" fontStyle="italic">
                          {availLoading ? "Loading data-availability timeline…"
                                        : "No decoded Percept recordings available for this participant yet."}
                        </MDTypography>
                      </MDBox>
                    </Grid>
                  ))}

                  {/* Pain-metric picker DIRECTLY BELOW the timeline — drives the pain row live. */}
                  {timelineData && timelineData.availability && timelineData.availability.records
                        && timelineData.availability.records.length > 0 ? (
                    <Grid item xs={12}>
                      <MDBox px={2} pb={1.5} display="flex" flexDirection="row" alignItems="center"
                             gap={2} flexWrap="wrap" justifyContent="center">
                        <MDTypography variant="button" fontWeight="bold" color="dark" sx={{ fontSize: 15 }}>
                          {"Pain metric (drives the pain plot above):"}
                        </MDTypography>
                        <FormControl size="small" sx={{ minWidth: 260 }}>
                          <Select value={metric} onChange={(e) => setMetric(e.target.value)}
                                  sx={{ fontSize: 15, fontWeight: 500 }}>
                            {((timelineData && timelineData.available_metrics)
                               || (data && data.available_metrics) || DEFAULT_METRIC_OPTIONS).map((m) => (
                              <MenuItem key={m.key} value={m.key} sx={{ fontSize: 15 }}>{m.label}</MenuItem>
                            ))}
                          </Select>
                        </FormControl>
                      </MDBox>
                    </Grid>
                  ) : null}

                  {/* ── Biomarker COMPUTE below the exploration timeline ──────────────────────
                      The timeline above is for visualization and needs no compute. The heavy
                      biomarker analysis (detector over full-resolution data) runs ONLY when this
                      button is clicked; settings (metric / binarization / window) are chosen in
                      the card below first. */}
                  <Grid item xs={12}>
                    <MDBox px={2} pt={1} pb={1} display="flex" flexDirection="row" alignItems="center" gap={2} flexWrap="wrap"
                           sx={{ borderTop: "1px solid #E0E0E0" }}>
                      <MDButton
                        variant="contained" color="error" size="large"
                        onClick={compute} disabled={computing}
                        sx={{ fontWeight: "bold", fontSize: 16, px: 3, py: 1.25,
                              backgroundColor: "#d32f2f", color: "#ffffff",
                              "&:hover": { backgroundColor: "#b71c1c" },
                              "&.Mui-disabled": { backgroundColor: "#e57373", color: "#ffffff" } }}
                      >
                        {computing ? (
                          <><CircularProgress size={18} sx={{ color: "#fff", mr: 1 }} />{"Computing…"}</>
                        ) : (data ? "↻ Recompute biomarker now" : "▶ Compute biomarker now")}
                      </MDButton>
                      {!computing && dirty && data ? (
                        <MDTypography variant="button" color="error" fontWeight="medium">
                          {"Settings changed — click to recompute."}
                        </MDTypography>
                      ) : null}
                      {data && data.timeline_points_full ? (
                        <MDTypography variant="caption" color="dark">
                          {`(computed on ${Number(data.timeline_points_full).toLocaleString()} full-resolution samples)`}
                        </MDTypography>
                      ) : null}
                    </MDBox>
                  </Grid>

                  {computing ? (
                    <Grid item xs={12}>
                      <MDBox px={2} pb={1}>
                        <MDTypography variant="button" fontWeight="medium" color="dark" display="block" mb={0.5}>
                          {"Computing time-domain + power-domain biomarker on full-resolution data — this can take ~10–40 s…"}
                        </MDTypography>
                        <LinearProgress color="error" />
                      </MDBox>
                    </Grid>
                  ) : null}

                  {/* Controls row: LEFT box = pain metric + binarization selector + sliders
                                   RIGHT box = live binarization preview histogram
                      Thick black border wraps both panels. Renders on every tab.               */}
                  <Grid item xs={12}>
                    <MDBox px={2} pb={1.5}>
                      <Card sx={{ border: "2.5px solid #1A1A1A", boxShadow: "none", borderRadius: 2 }}>
                        <Grid container sx={{ minHeight: 480 }}>

                          {/* LEFT: pain metric dropdown + binarization dropdown + sliders */}
                          <Grid item xs={12} md={5}
                            sx={{ borderRight: { md: "1.5px solid #1A1A1A" }, borderBottom: { xs: "1.5px solid #1A1A1A", md: "none" } }}>
                            <MDBox p={2} display="flex" flexDirection="column" gap={1.5}>
                              <MDBox>
                                <MDTypography variant="button" fontWeight="bold" color="dark" sx={{ fontSize: 17 }}>
                                  {"Binarization (high vs low pain label)"}
                                </MDTypography>
                                <FormControl fullWidth size="medium" sx={{ mt: 0.5 }}>
                                  <Select
                                    value={strategy}
                                    onChange={(e) => setStrategy(e.target.value)}
                                    sx={{ fontSize: 16, fontWeight: 500 }}
                                  >
                                    {((data && data.available_strategies) || DEFAULT_STRATEGY_OPTIONS).map((s) => (
                                      <MenuItem key={s.key} value={s.key} sx={{ fontSize: 16 }}>{s.label}</MenuItem>
                                    ))}
                                  </Select>
                                </FormControl>
                              </MDBox>
                              {strategy === "tertile" || strategy === "percentile" ? (
                                <MDBox display="flex" flexDirection="column" gap={1}>
                                  <MDBox display="flex" flexDirection="row" alignItems="center" gap={1.5}>
                                    <MDTypography variant="caption" fontWeight="medium" color="dark" sx={{ minWidth: 80, fontSize: 14 }}>
                                      {"Low ≤ pct"}
                                    </MDTypography>
                                    <Slider
                                      value={percentileLow} min={5} max={50} step={1}
                                      valueLabelDisplay="auto" size="small" sx={{ flex: 1 }}
                                      onChange={(e, v) => { const lo = Math.min(v, percentileHigh - 1); setPercentileLow(lo); }}
                                    />
                                  </MDBox>
                                  <MDBox display="flex" flexDirection="row" alignItems="center" gap={1.5}>
                                    <MDTypography variant="caption" fontWeight="medium" color="dark" sx={{ minWidth: 80, fontSize: 14 }}>
                                      {"High ≥ pct"}
                                    </MDTypography>
                                    <Slider
                                      value={percentileHigh} min={50} max={95} step={1}
                                      valueLabelDisplay="auto" size="small" sx={{ flex: 1 }}
                                      onChange={(e, v) => { const hi = Math.max(v, percentileLow + 1); setPercentileHigh(hi); }}
                                    />
                                  </MDBox>
                                </MDBox>
                              ) : null}
                              <MDTypography variant="caption" color="dark" fontStyle="italic" sx={{ fontSize: 13 }}>
                                {strategy === "tertile" || strategy === "percentile"
                                  ? "Days between the cuts are excluded from training."
                                  : strategy === "median"
                                    ? "Every day is labeled at the median split (~50/50)."
                                    : "Legacy 2-cluster KMeans labeler."}
                              </MDTypography>
                            </MDBox>
                          </Grid>

                          {/* RIGHT: live binarization preview histogram */}
                          <Grid item xs={12} md={7}>
                            <MDBox p={1.5} sx={{ height: "100%" }}>
                              <BinarizationPreview
                                points={previewPoints}
                                strategy={strategy}
                                percentileLow={percentileLow}
                                percentileHigh={percentileHigh}
                                metricLabel={previewMetricLabel}
                                metricKey={metric}
                                loading={painLoading}
                              />
                            </MDBox>
                          </Grid>

                        </Grid>
                      </Card>
                    </MDBox>
                  </Grid>

                  {!data && !alert ? (
                    <Grid item xs={12}>
                      <MDBox p={2}>
                        <MDTypography variant="button" color="dark">
                          {"Choose a source, pain metric, and (for Power-domain) the window above, then click "}
                          <strong>Compute biomarker now</strong>{" to run the analysis."}
                        </MDTypography>
                      </MDBox>
                    </Grid>
                  ) : null}

                  {data && data.message ? (
                    <Grid item xs={12}>
                      <MDBox p={2}>
                        <MDTypography variant="h6" color="error" fontSize={18}>
                          {data.message}
                        </MDTypography>
                        <MDTypography variant="button" color="dark">
                          {"Upload a Percept session for this participant and configure REDCap (REDCAP_API_URL / REDCAP_API_TOKEN), then reload."}
                        </MDTypography>
                      </MDBox>
                    </Grid>
                  ) : null}

                  {data && data.summary ? (
                    <Grid item xs={12}>
                      <MDBox px={2} pb={1}>
                        {data.label_metric ? (
                          <MDTypography variant="button" fontWeight="medium" color="dark" display="block">
                            {"Biomarker computed against: "}
                            {(((data && data.available_metrics) || DEFAULT_METRIC_OPTIONS)
                              .find((m) => m.key === data.label_metric) || {}).label || data.label_metric}
                          </MDTypography>
                        ) : null}
                        {data.label_strategy ? (
                          <MDTypography variant="caption" color="dark" display="block">
                            {"Binarized by: "}
                            {(((data && data.available_strategies) || DEFAULT_STRATEGY_OPTIONS)
                              .find((s) => s.key === data.label_strategy) || {}).label || data.label_strategy}
                            {(data.label_strategy === "tertile" || data.label_strategy === "percentile")
                              && data.percentile_low != null
                              ? ` (≤${Number(data.percentile_low).toFixed(0)}th / ≥${Number(data.percentile_high).toFixed(0)}th pct, daily)`
                              : ""}
                          </MDTypography>
                        ) : null}
                        {summaryLine("Time-domain", data.summary.timedomain)}
                        {summaryLine("Power-domain", data.summary.powerdomain)}
                        {data.powerdomain_pooled_warning ? (
                          <MDTypography variant="button" fontWeight="medium" color="warning" display="block">
                            {`⚠ ${data.powerdomain_pooled_warning}`}
                          </MDTypography>
                        ) : null}
                        {data.recorded_powers && data.recorded_powers.length ? (() => {
                          const left  = data.recorded_powers.filter((p) => /\bL\b|Left/i.test(p.label));
                          const right = data.recorded_powers.filter((p) => /\bR\b|Right/i.test(p.label));
                          const other = data.recorded_powers.filter((p) =>
                            !(/\bL\b|Left/i.test(p.label)) && !(/\bR\b|Right/i.test(p.label)));
                          const noFreq = data.recorded_powers.every((p) => p.center_hz == null);
                          const anyAboveCap = data.recorded_powers.some((p) => p.above_cap);
                          const fmt = (p) => {
                            const base = p.region ? `${p.label} (${p.region})` : p.label;
                            const withHz = p.center_hz != null ? `${base} @ ${Number(p.center_hz).toFixed(1)} Hz` : base;
                            return p.above_cap ? `${withHz} ⚠︎` : withHz;
                          };
                          // Above-cap (≥50 Hz) sensing bands are rendered in the warning color.
                          const rowLine = (p, i) => (
                            <MDTypography key={i} variant="caption"
                              color={p.above_cap ? "warning" : "text"} sx={{ fontSize: 12 }}>
                              {fmt(p)}
                            </MDTypography>
                          );
                          return (
                            <MDBox display="flex" flexDirection="column" alignItems="center" mt={0.5}>
                              <MDTypography variant="button" fontWeight="medium" color="dark" mb={0.25}>
                                {"Recorded power channels"}
                              </MDTypography>
                              <MDBox display="flex" flexDirection="row" gap={4} justifyContent="center" flexWrap="wrap">
                                {left.length > 0 && (
                                  <MDBox display="flex" flexDirection="column" alignItems="center">
                                    <MDTypography variant="caption" fontWeight="medium" color="dark" sx={{ fontSize: 11, textDecoration: "underline" }}>
                                      {"Left"}
                                    </MDTypography>
                                    {left.map(rowLine)}
                                  </MDBox>
                                )}
                                {right.length > 0 && (
                                  <MDBox display="flex" flexDirection="column" alignItems="center">
                                    <MDTypography variant="caption" fontWeight="medium" color="dark" sx={{ fontSize: 11, textDecoration: "underline" }}>
                                      {"Right"}
                                    </MDTypography>
                                    {right.map(rowLine)}
                                  </MDBox>
                                )}
                                {other.map(rowLine)}
                              </MDBox>
                              {anyAboveCap && (
                                <MDTypography variant="caption" color="warning" fontStyle="italic" sx={{ fontSize: 10, mt: 0.25 }}>
                                  {"⚠︎ Sensing band ≥ 50 Hz — outside the validated theta/alpha/beta/low-gamma biomarker range."}
                                </MDTypography>
                              )}
                              {noFreq && (
                                <MDTypography variant="caption" color="dark" fontStyle="italic" sx={{ fontSize: 10, mt: 0.25 }}>
                                  {"Sensing-band center frequency not present in this device export."}
                                </MDTypography>
                              )}
                            </MDBox>
                          );
                        })() : null}
                      </MDBox>
                    </Grid>
                  ) : null}

                </Grid>
              </Card>
            </Grid>

            {data && data.analytics ? (
              <BiomarkerAnalytics analytics={data.analytics} summary={data.summary}
                recordedPowers={data.recorded_powers}
                programmedThresholds={data.programmed_thresholds}
                binStrategy={strategy} binMetricKey={metric}
                binPercentileLow={percentileLow} binPercentileHigh={percentileHigh}
                metricLabel={(((data && data.available_metrics) || DEFAULT_METRIC_OPTIONS)
                  .find((m) => m.key === data.label_metric) || {}).label || data.label_metric} />
            ) : null}
          </Grid>
        </MDBox>
      </DatabaseLayout>
    </>
  );
}

function fmt(x) {
  if (x === null || x === undefined || Number.isNaN(x)) return "—";
  if (typeof x === "number") return Math.abs(x) >= 100 ? x.toFixed(1) : x.toFixed(3);
  return String(x);
}

// Compact p-value formatter: scientific notation for tiny p, 3 decimals otherwise.
function fmtP(x) {
  if (x === null || x === undefined || Number.isNaN(x)) return "—";
  const n = Number(x);
  if (!Number.isFinite(n)) return "—";
  if (n > 0 && n < 1e-3) return n.toExponential(1);
  return n.toFixed(3);
}

export default Biomarkers;
