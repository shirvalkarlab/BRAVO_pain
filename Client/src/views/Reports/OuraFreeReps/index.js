// FreeReps dashboard/sleep/trends/correlation workflows adapted for BRAVO.
// MIT source attribution and exact revision: docs/oura-freereps.md.
import { useEffect, useMemo, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { Alert, Button, Card, Chip, Grid, Stack, Tab, Tabs, TextField, MenuItem } from "@mui/material";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import DatabaseLayout from "layouts/DatabaseLayout";
import { usePlatformContext, setContextState } from "context.js";
import Chart from "./Chart";
import Hypnogram, {localTime} from "./Hypnogram";
import {useOuraData} from "./useOuraData";
import {aggregatePoints, calendarSeries, defaultRange, filterPoints, pairDays, pearsonR} from "./data";

const EMPTY = [];
const display = value => Number.isFinite(value) ? value.toLocaleString("en-US", {maximumFractionDigits: 2}) : "Unavailable";

function MetricSelect({label, value, onChange, metrics}) {
  return <TextField select label={label} value={value} onChange={e => onChange(e.target.value)} size="small" sx={{minWidth: 240, flex: 1}}>
    {metrics.map(m => <MenuItem key={m.key} value={m.key}>{m.label} ({m.unit})</MenuItem>)}
  </TextField>;
}

function MetricPlot({metric, points, interval = "day"}) {
  const traces = useMemo(() => {
    const data = interval === "day" ? calendarSeries(points) : points;
    return [{x: data.map(p => p.day), y: data.map(p => p.value), type: "scatter", mode: interval === "day" ? "lines+markers" : "markers",
      marker: {size: 5, color: "#237f83"}, line: {width: 1.5, color: "#237f83"}, connectgaps: false,
      customdata: data.map(p => p.count || 1), hovertemplate: "%{x}<br>%{y:.2f}<br>Observed days: %{customdata}<extra></extra>"}];
  }, [points, interval]);
  return <Chart traces={traces} yTitle={`${metric.label} (${metric.unit})`} xTitle={interval === "day" ? "Oura day" : `${interval === "week" ? "Week (Monday)" : "Month"} starting — mean of observed days`} />;
}

function SleepView({participant, sessions, revision}) {
  const [selected, setSelected] = useState("");
  const id = sessions.some(s => s.id === selected) ? selected : sessions[0]?.id;
  const detail = useOuraData(participant, id, revision, Boolean(id));
  const sleep = detail.data?.sleep;
  const hr = useMemo(() => [{x: (sleep?.heart_rate || EMPTY).map(p => (p.time - sleep.start) / 3600), y: (sleep?.heart_rate || EMPTY).map(p => p.value),
    type: "scatter", mode: "markers", marker: {color: "#237f83", size: 4}}], [sleep]);
  const hrv = useMemo(() => [{x: (sleep?.hrv_series || EMPTY).map(p => (p.time - sleep.start) / 3600), y: (sleep?.hrv_series || EMPTY).map(p => p.value),
    type: "scatter", mode: "markers", marker: {color: "#8564ad", size: 4}}], [sleep]);
  if (!sessions.length) return <Alert severity="info">No eligible sleep sessions in this date range.</Alert>;
  return <Stack spacing={2}>
    <TextField select label="Sleep session (Pacific time)" value={id} onChange={e => setSelected(e.target.value)}>
      {sessions.map(s => <MenuItem key={s.id} value={s.id}>{s.day} · {localTime(s.start)} · {display(s.duration_hours)} h sleep</MenuItem>)}
    </TextField>
    {detail.loading && <MDTypography role="status">Loading sleep detail…</MDTypography>}
    {detail.error && <Alert severity="error">{detail.error}</Alert>}
    {sleep && <>
      <Stack direction="row" flexWrap="wrap" gap={1}>
        <Chip label={`Sleep: ${display(sleep.duration_hours)} h`} /><Chip label={`Efficiency: ${display(sleep.efficiency)} %`} />
        <Chip label={`Mean HR: ${display(sleep.hr)} bpm`} /><Chip label={`Mean HRV: ${display(sleep.hrv)} ms`} />
      </Stack>
      <Card sx={{p: 3}}><MDTypography variant="h6" mb={2}>Sleep stages</MDTypography><Hypnogram sleep={sleep} /></Card>
      <Grid container spacing={2}><Grid item xs={12} lg={6}><Card><Chart traces={hr} yTitle="Heart rate (bpm)" xTitle="Hours since session start" /></Card></Grid>
        <Grid item xs={12} lg={6}><Card><Chart traces={hrv} yTitle="Heart rate variability (ms)" xTitle="Hours since session start" /></Card></Grid></Grid>
    </>}
  </Stack>;
}

export default function OuraFreeReps() {
  const {participant_uid} = useParams();
  const [, dispatch] = usePlatformContext();
  const [tab, setTab] = useState(0);
  const [revision, setRevision] = useState(0);
  const [range, setRange] = useState(null);
  const [metricKey, setMetricKey] = useState("");
  const [compareKey, setCompareKey] = useState("");
  const [interval, setInterval] = useState("day");
  const query = useOuraData(participant_uid, null, revision);
  const metrics = query.data?.metrics || EMPTY;
  const defaults = useMemo(() => defaultRange(metrics), [metrics]);
  const dates = range || defaults;
  useEffect(() => {
    setContextState(dispatch, "report", "CustomizedAnalysis");
    setRange(null); setMetricKey(""); setCompareKey("");
  }, [participant_uid, dispatch]);
  const shown = useMemo(() => metrics.map(m => ({...m, points: filterPoints(m.points, dates.start, dates.end)})), [metrics, dates.start, dates.end]);
  const metric = shown.find(m => m.key === metricKey) || shown[0];
  const compare = shown.find(m => m.key === compareKey) || shown[1] || shown[0];
  const series = useMemo(() => aggregatePoints(metric?.points || EMPTY, interval), [metric, interval]);
  const pairs = useMemo(() => pairDays(metric?.points || EMPTY, compare?.points || EMPTY), [metric, compare]);
  const coefficient = useMemo(() => pearsonR(pairs), [pairs]);
  const scatter = useMemo(() => [{x: pairs.map(p => p.x), y: pairs.map(p => p.y), text: pairs.map(p => p.day),
    type: "scatter", mode: "markers", marker: {color: "#237f83", size: 7, opacity: 0.75},
    hovertemplate: "%{text}<br>X: %{x:.2f}<br>Y: %{y:.2f}<extra></extra>"}], [pairs]);
  const sessions = useMemo(() => (query.data?.sleep || EMPTY).filter(s => (!dates.start || s.day >= dates.start) && (!dates.end || s.day <= dates.end))
    .slice().sort((a, b) => b.start - a.start), [query.data, dates.start, dates.end]);
  const invalidRange = Boolean(dates.start && dates.end && dates.start > dates.end);
  return <DatabaseLayout><MDBox py={3}>
    <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={2} mb={2}>
      <div><MDTypography variant="h3">Oura – FreeReps</MDTypography>
        <MDTypography variant="body2">Explore sleep, recovery and activity from your stored Oura data.</MDTypography></div>
      <Button variant="outlined" disabled={query.loading} onClick={() => setRevision(r => r + 1)}>Refresh view</Button>
    </Stack>
    <Stack direction="row" flexWrap="wrap" gap={1} mb={2}>
      <Chip label="BRAVO approved data" color="info" variant="outlined" />
      <Button component={Link} to={`/reports/multimodal-timeline-report/${participant_uid}?source=oura`}>Open shared timeline</Button>
    </Stack>
    {query.loading && <MDTypography role="status">Loading Oura dashboard…</MDTypography>}
    {query.error && <Alert severity="error">{query.error} Use Refresh view to retry.</Alert>}
    {query.data && <>
      {!metrics.length && <Alert severity="info">No eligible Oura measurements are stored for this participant.</Alert>}
      <Card sx={{p: 2, my: 2}}><Stack direction="row" flexWrap="wrap" gap={2} alignItems="center">
        <TextField label="From Oura day" type="date" value={dates.start} onChange={e => setRange({...dates, start: e.target.value})} InputLabelProps={{shrink: true}} size="small" />
        <TextField label="Through Oura day" type="date" value={dates.end} onChange={e => setRange({...dates, end: e.target.value})} InputLabelProps={{shrink: true}} size="small" />
        <Button onClick={() => setRange(null)}>Latest 90 days</Button><Button onClick={() => setRange({start: "", end: ""})}>All history</Button>
      </Stack></Card>
      <MDTypography variant="caption" display="block" mb={2}>Daily charts use Oura’s day labels; session times use America/Los_Angeles. QC exclusions remain applied. Missing values are never filled with zero.</MDTypography>
      <Tabs value={tab} onChange={(_, value) => setTab(value)} aria-label="Oura analysis views" variant="scrollable" sx={{mb: 3}}>
        {["Overview", "Sleep", "Trends", "Compare"].map(label => <Tab key={label} label={label} />)}
      </Tabs>
      {invalidRange ? <Alert severity="warning">Choose a start date on or before the end date.</Alert> : <>
        {tab === 0 && <Grid container spacing={2}>{shown.map(m => {
          const last = m.points[m.points.length - 1];
          return <Grid item xs={12} md={6} xl={4} key={m.key}><Card sx={{p: 2, height: "100%"}}>
            <MDTypography variant="h6">{m.label}</MDTypography><MDTypography variant="h4">{display(last?.value)} <small style={{fontSize: 14}}>{m.unit}</small></MDTypography>
            <MDTypography variant="caption">{last ? `Latest: ${last.day} · ${m.points.length} observed days` : "No observations in selected range"}</MDTypography>
            <Button sx={{alignSelf: "start"}} onClick={() => {setMetricKey(m.key); setTab(2);}}>Explore trend</Button>
          </Card></Grid>;
        })}</Grid>}
        {tab === 1 && <SleepView participant={participant_uid} sessions={sessions} revision={revision} />}
        {tab === 2 && metric && <Stack spacing={2}>
          <Stack direction="row" flexWrap="wrap" gap={2}><MetricSelect label="Trend metric" value={metric.key} onChange={setMetricKey} metrics={shown} />
            <TextField select label="Display interval" value={interval} onChange={e => setInterval(e.target.value)} size="small" sx={{minWidth: 200}}>
              <MenuItem value="day">Daily</MenuItem><MenuItem value="week">Weekly mean</MenuItem><MenuItem value="month">Monthly mean</MenuItem>
            </TextField></Stack>
          <Card sx={{p: 2}}><MetricPlot metric={metric} points={series} interval={interval} /></Card>
          <MDTypography variant="caption">{metric.points.length} observed days. Weekly/monthly means use available days only; hover for counts. Sleep metrics use the longest eligible session per Oura day.</MDTypography>
        </Stack>}
        {tab === 3 && metric && compare && <Stack spacing={2}>
          <Stack direction="row" flexWrap="wrap" gap={2}><MetricSelect label="X metric" value={metric.key} onChange={setMetricKey} metrics={shown} />
            <MetricSelect label="Y metric" value={compare.key} onChange={setCompareKey} metrics={shown} /></Stack>
          <MDTypography variant="h6">Pearson r: {display(coefficient)} · {pairs.length} paired days</MDTypography>
          {coefficient === null && <Alert severity="info">A correlation needs at least three paired days and variation in both metrics.</Alert>}
          <Card sx={{p: 2}}><Chart traces={scatter} xTitle={`${metric.label} (${metric.unit})`} yTitle={`${compare.label} (${compare.unit})`} height={420} /></Card>
          <MDTypography variant="caption">Exploratory same-day association using only dates observed in both metrics. Repeated days are not independent; this is not a causal effect or clinical recommendation.</MDTypography>
        </Stack>}
      </>}
      <MDTypography variant="caption" display="block" mt={3}>Sleep HR/HRV means use eligible samples. Refresh view reads stored data; the platform’s existing sync updates it.</MDTypography>
    </>}
    <MDTypography variant="caption" display="block" mt={3}>Adapted from <a href="https://github.com/meltforce/FreeReps" target="_blank" rel="noreferrer">FreeReps</a> (<a href="/third-party/FreeReps-LICENSE.txt" target="_blank" rel="noreferrer">MIT license</a>). Integrated with BRAVO’s participant access and data processing.</MDTypography>
  </MDBox></DatabaseLayout>;
}
