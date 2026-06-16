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
  Switch, Slider, TextField, FormControlLabel, Divider } from "@mui/material";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
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
  const [windowMonths, setWindowMonths] = useState(1);   // committed value -> drives the query
  const [monthsDraft, setMonthsDraft] = useState(1);     // live slider/field value (commit on release)
  const [alert, setAlert] = useState(null);

  const showWindowControls = source !== "timedomain";   // power-domain detector only

  useEffect(() => {
    if (!participant_uid) {
      navigate("/database", { replace: false });
      return;
    }
    setContextState(dispatch, "report", "CustomizedAnalysis");

    setAlert(<LoadingProgress />);
    SessionController.query("/api/queryBiomarkerAnalysis", {
      ParticipantId: participant_uid,
      source: source,
      LabelMetric: metric,
      SlidingWindow: slidingWindow,
      WindowMonths: windowMonths,
    }).then((response) => {
      setData(response.data);
      setAlert(null);
    }).catch((error) => {
      SessionController.displayError(error, setAlert);
    });
  }, [participant_uid, source, metric, slidingWindow, windowMonths]);

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
                  <Grid item xs={12}>
                    <MDBox p={2} display="flex" flexDirection="row" justifyContent="space-between" alignItems="center">
                      <MDTypography variant="h6" fontSize={24}>
                        {"Pain Biomarkers"}
                      </MDTypography>
                      <MDBox display="flex" flexDirection="row" alignItems="center" gap={2}>
                        <FormControl size="small" sx={{ minWidth: 240 }}>
                          <InputLabel id="biomarker-metric-label">Pain metric</InputLabel>
                          <Select
                            labelId="biomarker-metric-label"
                            label="Pain metric"
                            value={metric}
                            onChange={(e) => setMetric(e.target.value)}
                          >
                            {((data && data.available_metrics) || DEFAULT_METRIC_OPTIONS).map((m) => (
                              <MenuItem key={m.key} value={m.key}>{m.label}</MenuItem>
                            ))}
                          </Select>
                        </FormControl>
                        <ToggleButtonGroup
                          value={source}
                          exclusive
                          size="small"
                          onChange={(e, v) => { if (v) setSource(v); }}
                        >
                          <ToggleButton value="timedomain">Time-domain</ToggleButton>
                          <ToggleButton value="powerdomain">Power-domain</ToggleButton>
                          <ToggleButton value="both">Both</ToggleButton>
                        </ToggleButtonGroup>
                      </MDBox>
                    </MDBox>
                  </Grid>

                  {showWindowControls ? (
                    <Grid item xs={12}>
                      <Divider sx={{ my: 0 }} />
                      <MDBox px={2} py={1.5} display="flex" flexDirection="row" alignItems="center" gap={3} flexWrap="wrap">
                        <FormControlLabel
                          control={<Switch checked={slidingWindow} onChange={(e) => setSlidingWindow(e.target.checked)} />}
                          label={<MDTypography variant="button" fontWeight="medium">{"Sliding window"}</MDTypography>}
                        />
                        {slidingWindow ? (
                          <MDBox display="flex" flexDirection="row" alignItems="center" gap={2} sx={{ minWidth: 360 }}>
                            <MDTypography variant="button" color="text" sx={{ whiteSpace: "nowrap" }}>
                              {"Window (months)"}
                            </MDTypography>
                            <Slider
                              value={typeof monthsDraft === "number" ? monthsDraft : 1}
                              min={0.25} max={12} step={0.25}
                              valueLabelDisplay="auto"
                              marks={[{ value: 0.25, label: "0.25" }, { value: 3, label: "3" }, { value: 6, label: "6" }, { value: 12, label: "12" }]}
                              onChange={(e, v) => setMonthsDraft(v)}
                              onChangeCommitted={(e, v) => setWindowMonths(v)}
                              sx={{ flex: 1, minWidth: 160 }}
                            />
                            <TextField
                              type="number" size="small" value={monthsDraft}
                              inputProps={{ min: 0.25, max: 12, step: 0.25, style: { width: 64 } }}
                              onChange={(e) => {
                                const raw = e.target.value;
                                if (raw === "") { setMonthsDraft(""); return; }
                                const n = Number(raw);
                                if (!Number.isNaN(n)) setMonthsDraft(n);   // ignore transient invalid input (e.g. "1e")
                              }}
                              onBlur={() => { const v = commitMonths(monthsDraft); setMonthsDraft(v); setWindowMonths(v); }}
                              onKeyDown={(e) => { if (e.key === "Enter") { const v = commitMonths(monthsDraft); setMonthsDraft(v); setWindowMonths(v); } }}
                            />
                          </MDBox>
                        ) : (
                          <MDTypography variant="button" color="text">
                            {"Using all data (one threshold, no sliding window)"}
                          </MDTypography>
                        )}
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

function fmt(x) {
  if (x === null || x === undefined || Number.isNaN(x)) return "—";
  if (typeof x === "number") return Math.abs(x) >= 100 ? x.toFixed(1) : x.toFixed(3);
  return String(x);
}

export default Biomarkers;
