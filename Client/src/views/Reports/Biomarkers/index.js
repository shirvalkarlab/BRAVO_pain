/**
=========================================================
* UF BRAVO Platform -- Pain Biomarkers report (Shirvalkar Lab)
=========================================================
* Renders the selectable-source biomarker timeline (time-domain PSD<->pain and/or the
* power-domain ~10-min LFP threshold detector) returned by /api/queryBiomarkerAnalysis.
*/

import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { Card, Grid, ToggleButton, ToggleButtonGroup, Select, MenuItem, FormControl, InputLabel,
  Switch, Slider, TextField, FormControlLabel, Divider, Button } from "@mui/material";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import MDButton from "components/MDButton";
import LoadingProgress from "components/LoadingProgress";

import BiomarkerTimeline from "./BiomarkerTimeline";
import BiomarkerAnalytics from "./BiomarkerAnalytics";

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

function Biomarkers() {
  const navigate = useNavigate();
  const [controller, dispatch] = usePlatformContext();
  const { language } = controller;
  const { participant_uid } = useParams();

  const [data, setData] = useState(false);
  const [source, setSource] = useState("both");
  const [metric, setMetric] = useState("nrs");
  const [slidingWindow, setSlidingWindow] = useState(true);
  const [windowMonths, setWindowMonths] = useState(1);   // committed window (training) length
  const [monthsDraft, setMonthsDraft] = useState(1);     // live slider/field value (commit on release)
  const [windowStep, setWindowStep] = useState(0.5);     // committed window step (months)
  const [stepDraft, setStepDraft] = useState(0.5);       // live step value
  // The biomarker is EXPENSIVE (full-resolution detector over ~300k rows), so it is computed only
  // when the user clicks "Compute biomarker now" — never automatically on a settings change. This
  // holds the snapshot of options actually computed; the fetch effect runs only when it changes.
  const [requestParams, setRequestParams] = useState(null);
  const [alert, setAlert] = useState(null);

  const showWindowControls = source !== "timedomain";   // power-domain detector only

  const snapshot = () => ({
    source, LabelMetric: metric, SlidingWindow: slidingWindow,
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

  // Fetch ONLY when a compute was requested (requestParams set by the Compute button).
  useEffect(() => {
    if (!participant_uid || !requestParams) return;
    setAlert(<LoadingProgress />);
    SessionController.query("/api/queryBiomarkerAnalysis", {
      ParticipantId: participant_uid, ...requestParams,
    }).then((response) => {
      setData(response.data);
      setAlert(null);
    }).catch((error) => {
      SessionController.displayError(error, setAlert);
    });
  }, [participant_uid, requestParams]);

  const summaryLine = (label, s) => {
    if (!s) return null;
    if (s.best_threshold !== undefined) {
      return (
        <MDTypography variant="button" fontWeight="regular" color="text" display="block">
          {`${label}: threshold=${fmt(s.best_threshold)}  sens=${fmt(s.sens)}  spec=${fmt(s.spec)}  n_windows=${s.n_windows}`}
        </MDTypography>
      );
    }
    if (s.band !== undefined || s.freq_hz !== undefined) {
      return (
        <MDTypography variant="button" fontWeight="regular" color="text" display="block">
          {`${label}: ${s.channel || ""} ${fmt(s.freq_hz)} Hz  r=${fmt(s.r)}  p=${fmt(s.p)}`}
        </MDTypography>
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
                        onClick={compute}
                        sx={{ fontWeight: "bold", fontSize: 16, px: 3, py: 1.25,
                              backgroundColor: "#d32f2f", color: "#ffffff",
                              "&:hover": { backgroundColor: "#b71c1c" } }}
                      >
                        {data ? "↻ Recompute biomarker now" : "▶ Compute biomarker now"}
                      </MDButton>
                      {dirty && data ? (
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

                  <Grid item xs={12}>
                    <MDBox px={2} pb={1} display="flex" flexDirection="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={1}>
                      <MDTypography variant="h5" fontSize={28} fontWeight="bold">
                        {"Pain Biomarkers"}
                      </MDTypography>
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
                  </Grid>

                  {/* Pain-metric selector — larger box + text, centered (the biomarker target). */}
                  <Grid item xs={12}>
                    <MDBox px={2} pb={2} display="flex" flexDirection="column" alignItems="center">
                      <MDTypography variant="button" fontWeight="medium" color="text" sx={{ fontSize: 16 }} mb={0.5}>
                        {"Pain metric (biomarker target)"}
                      </MDTypography>
                      <FormControl sx={{ minWidth: 380 }}>
                        <Select
                          value={metric}
                          onChange={(e) => setMetric(e.target.value)}
                          sx={{ fontSize: 20, "& .MuiSelect-select": { py: 1.5, textAlign: "center" } }}
                        >
                          {((data && data.available_metrics) || DEFAULT_METRIC_OPTIONS).map((m) => (
                            <MenuItem key={m.key} value={m.key} sx={{ fontSize: 18 }}>{m.label}</MenuItem>
                          ))}
                        </Select>
                      </FormControl>
                    </MDBox>
                  </Grid>

                  {showWindowControls ? (
                    <Grid item xs={12}>
                      <Divider sx={{ my: 0 }} />
                      <MDBox px={2} py={1.5} display="flex" flexDirection="column" gap={1.5}>
                        <FormControlLabel
                          control={<Switch checked={slidingWindow} onChange={(e) => setSlidingWindow(e.target.checked)} />}
                          label={<MDTypography variant="button" fontWeight="medium">{"Sliding window (power-domain detector & performance)"}</MDTypography>}
                        />
                        {slidingWindow ? (
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
                        ) : (
                          <MDTypography variant="button" color="text">
                            {"Using all data (one threshold, no sliding window)"}
                          </MDTypography>
                        )}
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
                        {summaryLine("Time-domain", data.summary.timedomain)}
                        {summaryLine("Power-domain", data.summary.powerdomain)}
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
              <BiomarkerAnalytics analytics={data.analytics} />
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

export default Biomarkers;
