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

function MetricChart({ metric, color }) {
  const ref = useRef(null);
  useEffect(() => {
    if (!ref.current) return;
    const x = metric.points.map((p) => new Date(p.t));
    const y = metric.points.map((p) => p.v);
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
    }, { responsive: true, displaylogo: false });
    return () => { if (ref.current) Plotly.purge(ref.current); };
  }, [metric, color]);
  return <div ref={ref} style={{ width: "100%" }} />;
}

// All metrics on one normalized [0,1] axis (each scaled by its own range) to compare trajectories.
function NormalizedOverlay({ metrics, active }) {
  const ref = useRef(null);
  useEffect(() => {
    if (!ref.current || !metrics.length) return;
    const traces = [];
    metrics.forEach((m, i) => {
      if (active && !active.includes(m.key)) return;  // toggle affects the overlay only
      const [lo, hi] = m.range;
      const color = PALETTE[i % PALETTE.length];
      traces.push({
        x: m.points.map((p) => new Date(p.t)),
        y: m.points.map((p) => (hi > lo ? (p.v - lo) / (hi - lo) : null)),
        name: m.label, type: "scatter", mode: "lines+markers",
        line: { color, width: 2 }, marker: { size: 3, color }, connectgaps: false,
      });
    });
    Plotly.react(ref.current, traces, {
      height: 400, margin: { l: 52, r: 16, t: 12, b: 40 },
      xaxis: { type: "date", title: "Time" },
      yaxis: { title: "Normalized (0 = best, 1 = worst of range)", range: [-0.03, 1.05] },
      legend: { orientation: "h", y: -0.2 }, hovermode: "x unified",
    }, { responsive: true, displaylogo: false });
    return () => { if (ref.current) Plotly.purge(ref.current); };
  }, [metrics, active]);
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
  const [overlayActive, setOverlayActive] = useState(null);  // keys shown in the overlay
  const [alert, setAlert] = useState(null);

  useEffect(() => {
    if (!participant_uid) { navigate("/database", { replace: false }); return; }
    setContextState(dispatch, "report", "SurveyReports");
    setAlert(<LoadingProgress />);
    SessionController.query("/api/queryPainScores", { ParticipantId: participant_uid })
      .then((response) => {
        setData(response.data);
        setOverlayActive((response.data.metrics || []).map((m) => m.key));
        setAlert(null);
      })
      .catch((error) => { SessionController.displayError(error, setAlert); });
  }, [participant_uid]);

  const metrics = (data && data.metrics) || [];
  const toggleOverlay = (key) => setOverlayActive((cur) => {
    const base = cur || metrics.map((m) => m.key);
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
                    <NormalizedOverlay metrics={metrics} active={overlayActive || metrics.map((m) => m.key)} />
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
                    <MetricChart metric={m} color={PALETTE[i % PALETTE.length]} />
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
