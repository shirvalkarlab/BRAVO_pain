/**
=========================================================
* UF BRAVO Platform -- Pain Scores report (Shirvalkar Lab)
=========================================================
* Visualizes all patient-reported pain-score metrics over time (NRS, VAS, MPQ subscales, ...)
* from /api/queryPainScores, as a grid of per-metric charts (small multiples).
*/

import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import Plotly from "plotly.js-dist";
import { Card, Chip, Grid, Stack } from "@mui/material";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import LoadingProgress from "components/LoadingProgress";

import DatabaseLayout from "layouts/DatabaseLayout";

import { SessionController } from "database/session-control";
import { usePlatformContext, setContextState } from "context.js";

const PALETTE = ["#E53935", "#1A73E8", "#00897B", "#FB8C00", "#8E24AA",
  "#3949AB", "#43A047", "#F4511E", "#6D4C41", "#00ACC1"];

function movingAverage(y, w = 3) {
  return y.map((_, i) => {
    const lo = Math.max(0, i - Math.floor(w / 2));
    const hi = Math.min(y.length, i + Math.ceil(w / 2));
    const seg = y.slice(lo, hi).filter((v) => v != null);
    return seg.length ? seg.reduce((a, b) => a + b, 0) / seg.length : null;
  });
}

// --- Stage helpers (trial stages: pre-op / Stage 0 / 1 / 2) -----------------------------------
function hexA(hex, a) {
  const h = hex.replace("#", "");
  const r = parseInt(h.slice(0, 2), 16), g = parseInt(h.slice(2, 4), 16), b = parseInt(h.slice(4, 6), 16);
  return `rgba(${r},${g},${b},${a})`;
}

// Background bands for the active stages.
function stageShapes(stages, active) {
  if (!stages) return [];
  return stages
    .filter((s) => !active || active.includes(s.key))
    .map((s) => ({ type: "rect", xref: "x", yref: "paper", x0: s.start, x1: s.end, y0: 0, y1: 1,
      fillcolor: hexA(s.color, 0.13), line: { width: 0 }, layer: "below" }));
}

// A point is hidden only if it falls inside an INACTIVE stage; un-staged points always show.
function inActiveStage(t, stages, active) {
  if (!stages || !stages.length) return true;
  const ms = typeof t === "string" ? Date.parse(t) : new Date(t).getTime();
  let owning = null;
  for (const s of stages) {
    if (ms >= Date.parse(s.start) && ms < Date.parse(s.end)) { owning = s; break; }
  }
  if (!owning) return true;
  return !active || active.includes(owning.key);
}

function MetricChart({ metric, color, stages, stageActive }) {
  const ref = useRef(null);
  useEffect(() => {
    if (!ref.current) return;
    const pts = metric.points.filter((p) => inActiveStage(p.t, stages, stageActive));
    const x = pts.map((p) => new Date(p.t));
    const y = pts.map((p) => p.v);
    const traces = [
      { x, y, name: "report", type: "scatter", mode: "lines+markers",
        line: { color, width: 1.5 }, marker: { size: 5, color }, opacity: 0.55 },
      { x, y: movingAverage(y, 3), name: "3-pt avg", type: "scatter", mode: "lines",
        line: { color, width: 3 }, hoverinfo: "skip" },
    ];
    Plotly.react(ref.current, traces, {
      height: 240, margin: { l: 46, r: 14, t: 12, b: 34 }, showlegend: false,
      xaxis: { type: "date" },
      yaxis: { range: [metric.range[0], metric.range[1] * 1.02], title: { text: metric.label, font: { size: 12 } } },
      shapes: stageShapes(stages, stageActive),
    }, { responsive: true, displaylogo: false });
    return () => { if (ref.current) Plotly.purge(ref.current); };
  }, [metric, color, stages, stageActive]);
  return <div ref={ref} style={{ width: "100%" }} />;
}

// All metrics on one normalized [0,1] axis (each scaled by its own range) to compare trajectories.
function NormalizedOverlay({ metrics, active, stages, stageActive }) {
  const ref = useRef(null);
  useEffect(() => {
    if (!ref.current || !metrics.length) return;
    const traces = [];
    metrics.forEach((m, i) => {
      if (active && !active.includes(m.key)) return;  // metric toggle affects the overlay only
      const [lo, hi] = m.range;
      const color = PALETTE[i % PALETTE.length];
      const pts = m.points.filter((p) => inActiveStage(p.t, stages, stageActive));
      traces.push({
        x: pts.map((p) => new Date(p.t)),
        y: pts.map((p) => (hi > lo ? (p.v - lo) / (hi - lo) : null)),
        name: m.label, type: "scatter", mode: "lines+markers",
        line: { color, width: 2 }, marker: { size: 3, color }, connectgaps: false,
      });
    });
    Plotly.react(ref.current, traces, {
      height: 400, margin: { l: 52, r: 16, t: 12, b: 40 },
      xaxis: { type: "date", title: "Time" },
      yaxis: { title: "Normalized (0 = best, 1 = worst of range)", range: [-0.03, 1.05] },
      legend: { orientation: "h", y: -0.2 }, hovermode: "x unified",
      shapes: stageShapes(stages, stageActive),
    }, { responsive: true, displaylogo: false });
    return () => { if (ref.current) Plotly.purge(ref.current); };
  }, [metrics, active, stages, stageActive]);
  return <div ref={ref} style={{ width: "100%" }} />;
}

// Pearson correlation heatmap: every metric vs every other metric.
function CorrelationHeatmap({ correlation }) {
  const ref = useRef(null);
  useEffect(() => {
    if (!ref.current || !correlation || !correlation.matrix || correlation.matrix.length < 2) return;
    const labels = correlation.labels;
    const z = correlation.matrix;
    const ann = [];
    for (let i = 0; i < z.length; i++) {
      for (let j = 0; j < z.length; j++) {
        const v = z[i][j];
        if (v != null) ann.push({ x: labels[j], y: labels[i], text: v.toFixed(2), showarrow: false,
          font: { size: 10, color: Math.abs(v) > 0.55 ? "white" : "#344767" } });
      }
    }
    Plotly.react(ref.current, [{
      type: "heatmap", z, x: labels, y: labels, zmin: -1, zmax: 1,
      // blue (negative) -> white (0) -> red (positive)
      colorscale: [[0, "#2166AC"], [0.5, "#F7F7F7"], [1, "#B2182B"]], colorbar: { title: "r" },
      hovertemplate: "%{y} ↔ %{x}<br>r = %{z:.2f}<extra></extra>",
    }], {
      height: 480, margin: { l: 140, r: 20, t: 16, b: 140 },
      annotations: ann, xaxis: { tickangle: -40, automargin: true },
      yaxis: { autorange: "reversed", automargin: true },
    }, { responsive: true, displaylogo: false });
    return () => { if (ref.current) Plotly.purge(ref.current); };
  }, [correlation]);
  return <div ref={ref} style={{ width: "100%" }} />;
}

function PainScores() {
  const navigate = useNavigate();
  const [controller, dispatch] = usePlatformContext();
  const { participant_uid } = useParams();

  const [data, setData] = useState(false);
  const [overlayActive, setOverlayActive] = useState(null);  // metric keys shown in the overlay
  const [stageActive, setStageActive] = useState(null);      // visible trial stages (all plots)
  const [alert, setAlert] = useState(null);

  useEffect(() => {
    if (!participant_uid) { navigate("/database", { replace: false }); return; }
    setContextState(dispatch, "report", "SurveyReports");
    setAlert(<LoadingProgress />);
    SessionController.query("/api/queryPainScores", { ParticipantId: participant_uid })
      .then((response) => {
        setData(response.data);
        setOverlayActive((response.data.metrics || []).map((m) => m.key));
        setStageActive((response.data.stages || []).map((s) => s.key));
        setAlert(null);
      })
      .catch((error) => { SessionController.displayError(error, setAlert); });
  }, [participant_uid]);

  const metrics = (data && data.metrics) || [];
  const stages = (data && data.stages) || [];
  const activeStages = stageActive || stages.map((s) => s.key);
  const toggleOverlay = (key) => setOverlayActive((cur) => {
    const base = cur || metrics.map((m) => m.key);
    return base.includes(key) ? base.filter((k) => k !== key) : [...base, key];
  });
  const toggleStage = (key) => setStageActive((cur) => {
    const base = cur || stages.map((s) => s.key);
    return base.includes(key) ? base.filter((k) => k !== key) : [...base, key];
  });

  return (
    <>
      {alert}
      <DatabaseLayout>
        <MDBox pt={3}>
          <Grid container spacing={2}>
            <Grid item xs={12}>
              <Card sx={{ width: "100%" }}>
                <MDBox p={2} display="flex" flexDirection="row" justifyContent="space-between" alignItems="center">
                  <MDTypography variant="h6" fontSize={22}>Pain Score Reports</MDTypography>
                  {data ? (
                    <MDTypography variant="button" color="text">
                      {`${data.n_reports || 0} reports · ${metrics.length} metrics`}
                    </MDTypography>
                  ) : null}
                </MDBox>
                {data && data.message ? (
                  <MDBox px={2} pb={1}>
                    <MDTypography variant="button" color={metrics.length ? "text" : "error"}>
                      {data.message}
                    </MDTypography>
                  </MDBox>
                ) : null}
                {stages.length ? (
                  <MDBox px={2} pb={2}>
                    <MDTypography variant="button" fontWeight="medium" color="text">Stages (applies to all time plots):</MDTypography>
                    <Stack direction="row" flexWrap="wrap" sx={{ gap: 0.6, mt: 0.5 }}>
                      {stages.map((s) => {
                        const on = activeStages.includes(s.key);
                        return (
                          <Chip key={s.key} label={s.name} size="small" onClick={() => toggleStage(s.key)}
                            variant={on ? "filled" : "outlined"}
                            sx={{ bgcolor: on ? s.color : "transparent", color: on ? "#fff" : "text.primary",
                                  borderColor: s.color, cursor: "pointer", "&:hover": { opacity: 0.85 } }} />
                        );
                      })}
                    </Stack>
                  </MDBox>
                ) : null}
              </Card>
            </Grid>

            {metrics.length > 0 ? (
              <Grid item xs={12}>
                <Card sx={{ width: "100%" }}>
                  <MDBox p={2}>
                    <MDTypography variant="h6" fontSize={18} mb={0.5}>Normalized trajectories (all metrics)</MDTypography>
                    <Stack direction="row" flexWrap="wrap" sx={{ gap: 0.6, mb: 1 }}>
                      {metrics.map((m, i) => {
                        const on = overlayActive ? overlayActive.includes(m.key) : true;
                        const c = PALETTE[i % PALETTE.length];
                        return (
                          <Chip key={m.key} label={m.label} size="small" onClick={() => toggleOverlay(m.key)}
                            variant={on ? "filled" : "outlined"}
                            sx={{ bgcolor: on ? c : "transparent", color: on ? "#fff" : "text.primary",
                                  borderColor: c, cursor: "pointer", "&:hover": { opacity: 0.85 } }} />
                        );
                      })}
                    </Stack>
                    <NormalizedOverlay metrics={metrics} active={overlayActive || metrics.map((m) => m.key)}
                      stages={stages} stageActive={activeStages} />
                  </MDBox>
                </Card>
              </Grid>
            ) : null}

            {data && data.correlation && data.correlation.matrix && data.correlation.matrix.length > 1 ? (
              <Grid item xs={12} lg={8}>
                <Card sx={{ width: "100%" }}>
                  <MDBox p={2}>
                    <MDTypography variant="h6" fontSize={18} mb={0.5}>Metric correlation (Pearson r)</MDTypography>
                    <CorrelationHeatmap correlation={data.correlation} />
                  </MDBox>
                </Card>
              </Grid>
            ) : null}

            {metrics.map((m, i) => (
              <Grid item xs={12} md={6} lg={4} key={m.key}>
                <Card sx={{ width: "100%", height: "100%" }}>
                  <MDBox p={2}>
                    <MDTypography variant="h6" fontSize={16} mb={0.5}>{m.label}</MDTypography>
                    <MetricChart metric={m} color={PALETTE[i % PALETTE.length]} stages={stages} stageActive={activeStages} />
                  </MDBox>
                </Card>
              </Grid>
            ))}
          </Grid>
        </MDBox>
      </DatabaseLayout>
    </>
  );
}

export default PainScores;
