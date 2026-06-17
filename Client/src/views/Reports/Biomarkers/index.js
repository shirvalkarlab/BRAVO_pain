/**
=========================================================
* UF BRAVO Platform -- Pain Biomarkers report (Shirvalkar Lab)
=========================================================
* Renders the selectable-source biomarker timeline (time-domain PSD<->pain and/or the
* power-domain ~10-min LFP threshold detector) returned by /api/queryBiomarkerAnalysis.
*/

import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { Card, Grid, ToggleButton, ToggleButtonGroup, Select, MenuItem, FormControl,
  Switch, Slider, TextField, FormControlLabel, Divider, LinearProgress, CircularProgress } from "@mui/material";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import MDButton from "components/MDButton";

import BiomarkerTimeline from "./BiomarkerTimeline";
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
  const [source, setSource] = useState("both");
  const [metric, setMetric] = useState("nrs");
  const [strategy, setStrategy] = useState("tertile");   // binarization labeler (default tertile)
  const [percentileLow, setPercentileLow] = useState(33.3);   // tertile/percentile low cut
  const [percentileHigh, setPercentileHigh] = useState(66.7);  // tertile/percentile high cut
  const [slidingWindow, setSlidingWindow] = useState(true);
  const [windowMonths, setWindowMonths] = useState(1);   // committed window (training) length
  const [monthsDraft, setMonthsDraft] = useState(1);     // live slider/field value (commit on release)
  const [windowStep, setWindowStep] = useState(0.5);     // committed window step (months)
  const [stepDraft, setStepDraft] = useState(0.5);       // live step value
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

  // Window/step now drive BOTH the time-domain sliding correlation heatmap and the power-domain
  // detector/performance, so show them for every source. The sliding ON/OFF switch is
  // power-domain-specific (all-data vs sliding), so it's hidden on the time-domain-only tab.
  const showWindowControls = true;
  const showSlidingSwitch = source !== "timedomain";

  const snapshot = () => ({
    source, LabelMetric: metric, LabelStrategy: strategy,
    PercentileLow: percentileLow, PercentileHigh: percentileHigh,
    SlidingWindow: slidingWindow,
    WindowMonths: windowMonths, WindowStep: windowStep,
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

  // The points array for the currently-selected pain metric, fed straight into the preview card.
  const previewPoints = (() => {
    if (!painScores || !Array.isArray(painScores.metrics)) return [];
    const m = painScores.metrics.find((x) => x.key === metric);
    return m ? m.points : [];
  })();
  const previewMetricLabel = (((data && data.available_metrics) || DEFAULT_METRIC_OPTIONS)
    .find((m) => m.key === metric) || {}).label || metric;

  // Render an honest, multi-line summary for a branch: the headline estimate plus the rigor
  // statistics (FDR q, permutation p, autocorrelation-adjusted effective n, Fisher-z CI for the
  // time domain; balanced accuracy vs chance + AUC for the power domain) and any caveats.
  const summaryLine = (label, s) => {
    if (!s) return null;
    const Line = ({ children, color = "text", bold = false }) => (
      <MDTypography variant="button" fontWeight={bold ? "medium" : "regular"} color={color} display="block">
        {children}
      </MDTypography>
    );
    // Small italic caption for honesty caveats (provenance, CI conditions, label source).
    const Note = ({ children, color = "text" }) => (
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
            {`balanced accuracy=${fmt(s.balanced_accuracy)} vs chance=${fmt(s.chance_accuracy)} (whole series)` +
             `  (prevalence=${fmt(s.prevalence)})${aucTxt}${rhoTxt}`}
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
                  {/* Big red COMPUTE button at the top — biomarkers (re)compute ONLY when clicked,
                      so the user can set source / metric / window freely before running. */}
                  <Grid item xs={12}>
                    <MDBox px={2} pt={2} pb={1} display="flex" flexDirection="row" alignItems="center" gap={2} flexWrap="wrap">
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
                        <MDTypography variant="caption" color="text">
                          {`(computed on ${Number(data.timeline_points_full).toLocaleString()} full-resolution samples)`}
                        </MDTypography>
                      ) : null}
                    </MDBox>
                  </Grid>

                  {computing ? (
                    <Grid item xs={12}>
                      <MDBox px={2} pb={1}>
                        <MDTypography variant="button" fontWeight="medium" color="text" display="block" mb={0.5}>
                          {`Computing ${source === "both" ? "time-domain + power-domain" : source === "timedomain" ? "time-domain" : "power-domain"} biomarker on full-resolution data — this can take ~10–40 s…`}
                        </MDTypography>
                        <LinearProgress color="error" />
                      </MDBox>
                    </Grid>
                  ) : null}

                  {/* Title + source toggle + pain-metric selector all on one row. Pain-metric was
                      previously a wide centered block of its own; collapsing it inline here frees
                      vertical space and puts every "what is being computed" control in one strip. */}
                  <Grid item xs={12}>
                    <MDBox px={2} pb={1} display="flex" flexDirection="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={2}>
                      <MDTypography variant="h5" fontSize={28} fontWeight="bold">
                        {"Pain Biomarkers"}
                      </MDTypography>
                      <MDBox display="flex" flexDirection="row" alignItems="center" gap={2} flexWrap="wrap">
                        <MDBox display="flex" flexDirection="column" alignItems="flex-start">
                          <MDTypography variant="caption" color="text" sx={{ fontSize: 11, lineHeight: 1 }}>
                            {"Pain metric (biomarker target)"}
                          </MDTypography>
                          <FormControl size="small" sx={{ minWidth: 280, mt: 0.5 }}>
                            <Select
                              value={metric}
                              onChange={(e) => setMetric(e.target.value)}
                              sx={{ fontSize: 14, "& .MuiSelect-select": { py: 0.75 } }}
                            >
                              {((data && data.available_metrics) || DEFAULT_METRIC_OPTIONS).map((m) => (
                                <MenuItem key={m.key} value={m.key} sx={{ fontSize: 14 }}>{m.label}</MenuItem>
                              ))}
                            </Select>
                          </FormControl>
                        </MDBox>
                        <ToggleButtonGroup
                          value={source}
                          exclusive
                          size="medium"
                          onChange={(e, v) => { if (v) setSource(v); }}
                        >
                          <ToggleButton value="timedomain">Time-domain</ToggleButton>
                          <ToggleButton value="powerdomain">Power-domain</ToggleButton>
                          <ToggleButton value="both">Both</ToggleButton>
                        </ToggleButtonGroup>
                      </MDBox>
                    </MDBox>
                  </Grid>

                  {/* Binarization PREVIEW stacked DIRECTLY above the binarization SELECTOR — both
                      inside one bordered Card so the visual link is unambiguous and there is no
                      white space between them. Source-independent: this whole block lives in the
                      top controls and renders identically on every tab. The preview recomputes
                      client-side whenever metric / strategy / percentile sliders change.          */}
                  <Grid item xs={12}>
                    <MDBox px={2} pb={1.5}>
                      <Card variant="outlined" sx={{ border: "1px solid #E0E4E8", boxShadow: "none" }}>
                        <MDBox p={1.25} pb={0.5}>
                          <BinarizationPreview
                            points={previewPoints}
                            strategy={strategy}
                            percentileLow={percentileLow}
                            percentileHigh={percentileHigh}
                            metricLabel={previewMetricLabel}
                            loading={painLoading}
                          />
                        </MDBox>
                        <Divider sx={{ my: 0 }} />
                        <MDBox px={1.5} py={1} display="flex" flexDirection="column" alignItems="center">
                          <MDTypography variant="button" fontWeight="medium" color="text" sx={{ fontSize: 14, lineHeight: 1.1 }} mb={0.5}>
                            {"Binarization (high vs low pain label)"}
                          </MDTypography>
                          <FormControl size="small" sx={{ minWidth: 300 }}>
                            <Select
                              value={strategy}
                              onChange={(e) => setStrategy(e.target.value)}
                              sx={{ fontSize: 14, "& .MuiSelect-select": { py: 0.75, textAlign: "center" } }}
                            >
                              {((data && data.available_strategies) || DEFAULT_STRATEGY_OPTIONS).map((s) => (
                                <MenuItem key={s.key} value={s.key} sx={{ fontSize: 14 }}>{s.label}</MenuItem>
                              ))}
                            </Select>
                          </FormControl>
                          {strategy === "tertile" || strategy === "percentile" ? (
                            <MDBox display="flex" flexDirection="row" alignItems="center" gap={1.5} mt={1} flexWrap="wrap" justifyContent="center">
                              <MDTypography variant="caption" color="text" sx={{ minWidth: 70, fontSize: 11 }}>
                                {"Low ≤ pct"}
                              </MDTypography>
                              <Slider
                                value={percentileLow} min={5} max={50} step={1}
                                valueLabelDisplay="auto" size="small" sx={{ width: 120 }}
                                onChange={(e, v) => { const lo = Math.min(v, percentileHigh - 1); setPercentileLow(lo); }}
                              />
                              <MDTypography variant="caption" color="text" sx={{ minWidth: 70, fontSize: 11 }}>
                                {"High ≥ pct"}
                              </MDTypography>
                              <Slider
                                value={percentileHigh} min={50} max={95} step={1}
                                valueLabelDisplay="auto" size="small" sx={{ width: 120 }}
                                onChange={(e, v) => { const hi = Math.max(v, percentileLow + 1); setPercentileHigh(hi); }}
                              />
                            </MDBox>
                          ) : null}
                          <MDTypography variant="caption" color="text" fontStyle="italic" sx={{ fontSize: 10, mt: 0.25, textAlign: "center", maxWidth: 520 }}>
                            {strategy === "tertile" || strategy === "percentile"
                              ? "Days between the cuts are excluded from training (the detector sees only clearly-high vs clearly-low days)."
                              : strategy === "median"
                                ? "Every day is labeled at the median split (~50/50)."
                                : "Legacy 2-cluster KMeans labeler (data-driven but less transparent and density-sensitive)."}
                          </MDTypography>
                        </MDBox>
                      </Card>
                    </MDBox>
                  </Grid>

                  {showWindowControls ? (
                    <Grid item xs={12}>
                      <Divider sx={{ my: 0 }} />
                      <MDBox px={2} py={1.5} display="flex" flexDirection="column" gap={1.5}>
                        {showSlidingSwitch ? (
                          <FormControlLabel
                            control={<Switch checked={slidingWindow} onChange={(e) => setSlidingWindow(e.target.checked)} />}
                            label={<MDTypography variant="button" fontWeight="medium">{"Sliding window (power-domain detector & performance)"}</MDTypography>}
                          />
                        ) : null}
                        {(source !== "powerdomain" || slidingWindow) ? (
                          <MDBox display="flex" flexDirection="column" gap={1.5}>
                            {[
                              { lbl: "Window (months)", draft: monthsDraft, setDraft: setMonthsDraft, setVal: setWindowMonths,
                                commit: commitMonths, min: 0.25, max: 12, step: 0.25,
                                marks: [{ value: 1, label: "1" }, { value: 3, label: "3" }, { value: 6, label: "6" }, { value: 9, label: "9" }, { value: 12, label: "12" }] },
                              { lbl: "Step (months)", draft: stepDraft, setDraft: setStepDraft, setVal: setWindowStep,
                                commit: commitStep, min: 0.1, max: 6, step: 0.1,
                                marks: [{ value: 0.25, label: "0.25" }, { value: 1, label: "1" }, { value: 3, label: "3" }, { value: 6, label: "6" }] },
                            ].map((c) => (
                              <MDBox key={c.lbl} display="flex" flexDirection="row" alignItems="center" gap={2} flexWrap="wrap">
                                <MDTypography variant="button" color="text" sx={{ whiteSpace: "nowrap", minWidth: 150 }}>
                                  {c.lbl}
                                </MDTypography>
                                <Slider
                                  value={typeof c.draft === "number" ? c.draft : c.min}
                                  min={c.min} max={c.max} step={c.step} valueLabelDisplay="auto" marks={c.marks}
                                  onChange={(e, v) => c.setDraft(v)}
                                  onChangeCommitted={(e, v) => c.setVal(v)}
                                  sx={{ flex: 1, minWidth: 200, maxWidth: 420 }}
                                />
                                <TextField
                                  type="number" size="small" value={c.draft}
                                  inputProps={{ min: c.min, max: c.max, step: c.step, style: { width: 64 } }}
                                  onChange={(e) => {
                                    const raw = e.target.value;
                                    if (raw === "") { c.setDraft(""); return; }
                                    const n = Number(raw);
                                    if (!Number.isNaN(n)) c.setDraft(n);
                                  }}
                                  onBlur={() => { const v = c.commit(c.draft); c.setDraft(v); c.setVal(v); }}
                                  onKeyDown={(e) => { if (e.key === "Enter") { const v = c.commit(c.draft); c.setDraft(v); c.setVal(v); } }}
                                />
                              </MDBox>
                            ))}
                          </MDBox>
                        ) : null}
                        {(showSlidingSwitch && !slidingWindow) ? (
                          <MDTypography variant="button" color="text">
                            {"Power-domain: using all data (one threshold, no sliding window)."}
                          </MDTypography>
                        ) : null}
                      </MDBox>
                    </Grid>
                  ) : null}

                  {!data && !alert ? (
                    <Grid item xs={12}>
                      <MDBox p={2}>
                        <MDTypography variant="button" color="text">
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
                        <MDTypography variant="button" color="text">
                          {"Upload a Percept session for this participant and configure REDCap (REDCAP_API_URL / REDCAP_API_TOKEN), then reload."}
                        </MDTypography>
                      </MDBox>
                    </Grid>
                  ) : null}

                  {data && data.summary ? (
                    <Grid item xs={12}>
                      <MDBox px={2} pb={1}>
                        {data.label_metric ? (
                          <MDTypography variant="button" fontWeight="medium" color="text" display="block">
                            {"Biomarker computed against: "}
                            {(((data && data.available_metrics) || DEFAULT_METRIC_OPTIONS)
                              .find((m) => m.key === data.label_metric) || {}).label || data.label_metric}
                          </MDTypography>
                        ) : null}
                        {data.label_strategy ? (
                          <MDTypography variant="caption" color="text" display="block">
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
                        {data.recorded_powers && data.recorded_powers.length ? (
                          <MDTypography variant="button" fontWeight="regular" color="text" display="block">
                            {"Powers recorded per channel: "}
                            {data.recorded_powers.map((p) => {
                              const base = p.region ? `${p.label} (${p.region})` : p.label;
                              return p.center_hz != null ? `${base} @ ${Number(p.center_hz).toFixed(1)} Hz` : base;
                            }).join(",  ")}
                            {data.recorded_powers.every((p) => p.center_hz == null) ? (
                              <MDTypography variant="caption" color="text" fontStyle="italic" display="block" sx={{ fontSize: 10 }}>
                                {"(Sensing-band center frequency not present in this device export.)"}
                              </MDTypography>
                            ) : null}
                          </MDTypography>
                        ) : null}
                      </MDBox>
                    </Grid>
                  ) : null}

                  {data && data.timeline && data.timeline.length > 0 ? (
                    <Grid item xs={12}>
                      <BiomarkerTimeline data={data} figureTitle={"BiomarkerTimeline"} height={420} />
                    </Grid>
                  ) : null}
                </Grid>
              </Card>
            </Grid>

            {data && data.analytics ? (
              <BiomarkerAnalytics analytics={data.analytics} summary={data.summary}
                metricLabel={(((data && data.available_metrics) || DEFAULT_METRIC_OPTIONS)
                  .find((m) => m.key === data.label_metric) || {}).label || data.label_metric} />
            ) : null}
          </Grid>
        </MDBox>
      </DatabaseLayout>
    </>
  );
}

// Clamp a typed month value to the slider's range [0.25, 12]; fall back to 1 on invalid input.
function commitMonths(v) {
  const n = Number(v);
  if (!Number.isFinite(n)) return 1;
  return Math.min(12, Math.max(0.25, n));
}

// Clamp the window step to [0.1, 6] months; fall back to 0.5 on invalid input.
function commitStep(v) {
  const n = Number(v);
  if (!Number.isFinite(n)) return 0.5;
  return Math.min(6, Math.max(0.1, n));
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
