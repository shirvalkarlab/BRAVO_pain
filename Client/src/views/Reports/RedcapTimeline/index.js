import {useCallback, useEffect, useMemo, useState} from "react";
import {useParams} from "react-router-dom";
import {Alert, Autocomplete, Button, Card, Chip, FormControlLabel, Stack, Switch, Tab, Tabs, TextField} from "@mui/material";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import DatabaseLayout from "layouts/DatabaseLayout";
import {usePlatformContext, setContextState} from "context.js";
import {DEFAULT_METRICS, filterPoints, fullRange, localTime, past28Range, unknownIntervalsInRange} from "./data";
import {useRedcapTimeline} from "./useRedcapTimeline";
import MetricChart from "./MetricChart";
import StimulationContext from "./StimulationContext";
import StimulationPrograms from "./StimulationPrograms";
import Medications from "./Medications";
import OuraTimeline from "./OuraTimeline";
import StimProgramSettings from "./NeuralData";
import HomeNeuralData from "./HomeNeuralData";
import MultimodalSummary from "./MultimodalSummary";

const EMPTY = [];

export default function RedcapTimeline() {
  const {participant_uid} = useParams();
  const [, dispatch] = usePlatformContext();
  const [view, setView] = useState("summary");
  const [revision, setRevision] = useState(0);
  const [selected, setSelected] = useState(DEFAULT_METRICS);
  const [smooth, setSmooth] = useState(true);
  const [range, setRange] = useState(null);
  const [contextVisible, setContextVisible] = useState(true);
  const [selectedTransition, setSelectedTransition] = useState("");
  const [detailsExpanded, setDetailsExpanded] = useState(false);
  const selectTransition = useCallback(id => {setSelectedTransition(id); setDetailsExpanded(true);}, []);
  const query = useRedcapTimeline(participant_uid, revision);
  const metrics = query.data?.metrics || EMPTY;
  const phases = query.data?.phases || EMPTY;
  const defaults = useMemo(() => fullRange(metrics), [metrics]);
  const dates = range || defaults;
  const recent = past28Range(defaults.end);
  const transitions = query.data?.stimulation?.home_transitions || EMPTY;
  const unknownIntervals = query.data?.stimulation?.home_unknown_intervals || EMPTY;
  const visibleUnknown = useMemo(() => unknownIntervalsInRange(unknownIntervals, dates), [unknownIntervals, dates]);
  const events = useMemo(() => filterPoints(transitions, dates.start, dates.end).map((event, index) => ({...event, number: index + 1})), [transitions, dates.start, dates.end]);
  const currentEvent = events.find(event => event.id === selectedTransition) || events[events.length - 1];
  const previous = transitions.filter(event => localTime(event.time).slice(0, 10) < dates.start).slice(-1)[0];
  const chartEvents = useMemo(() => !contextVisible ? EMPTY : events.length > 12 ? [currentEvent] : events, [contextVisible, events, currentEvent]);
  const shown = useMemo(() => selected.map(key => metrics.find(m => m.key === key)).filter(Boolean), [selected, metrics]);
  useEffect(() => {
    setContextState(dispatch, "report", "CustomizedAnalysis");
    setView("summary"); setSelected(DEFAULT_METRICS); setRange(null); setSelectedTransition(""); setDetailsExpanded(false);
  }, [participant_uid, dispatch]);
  const invalidRange = !dates.start || !dates.end || dates.start > dates.end || dates.end > defaults.end;
  return <DatabaseLayout><MDBox py={3}>
    <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={2} mb={3}>
      <div><MDTypography variant="h3">Aditya - All Data Streams</MDTypography>
        <MDTypography variant="body1">Survey outcomes, stimulation settings, medications and wearable data across the study.</MDTypography></div>
      <Button variant="outlined" disabled={query.loading} onClick={() => setRevision(r => r + 1)}>Refresh view</Button>
    </Stack>
    {query.loading && <MDTypography role="status">Loading reviewed REDCap timeline…</MDTypography>}
    {query.error && <Alert severity="error">{query.error}</Alert>}
    {query.data && <>
      <Tabs value={view} onChange={(_, value) => setView(value)} variant="scrollable" scrollButtons="auto" aria-label="All data stream views" sx={{mb:3}}>
        <Tab value="summary" label="Multimodal Summary" />
        <Tab value="timeline" label="REDCap" />
        <Tab value="stimulation" label="Stim Program Boxplots" />
        <Tab value="settings" label="Stim Program Settings" />
        <Tab value="neural" label="Neural Data" />
        <Tab value="medications" label="Medications" />
        <Tab value="oura" label="Oura" />
      </Tabs>
      {view !== "summary" && view !== "oura" && view !== "neural" && view !== "settings" && <Card sx={{p: 3, mb: 3}}><Stack spacing={3}>
        <Autocomplete multiple disableCloseOnSelect options={metrics} value={shown} getOptionLabel={m => m.label}
          isOptionEqualToValue={(a, b) => a.key === b.key} getOptionDisabled={m => !m.points.length}
          onChange={(_, values) => setSelected(values.map(m => m.key))}
          renderInput={params => <TextField {...params} label="Clinical metrics" helperText="Choose from 27 clinical metrics. Measures with no reviewed observations are unavailable." />}
          renderOption={(props, metric) => <li {...props}>{metric.label} · {metric.range.join("–")} · {metric.points.length.toLocaleString()} observations</li>}
          sx={{"& .MuiInputBase-root": {fontSize: 17}, "& .MuiChip-label": {fontSize: 15}}} />
        {view !== "timeline" && <Button onClick={() => setSelected(DEFAULT_METRICS)}>Default metrics</Button>}
        {view === "timeline" && <><Stack direction="row" flexWrap="wrap" gap={2} alignItems="center">
          <TextField label="From" type="date" value={dates.start} InputLabelProps={{shrink: true}} onChange={e => setRange({...dates, start: e.target.value})} />
          <TextField label="Through" type="date" value={dates.end} inputProps={{max: defaults.end}} InputLabelProps={{shrink: true}} onChange={e => setRange({...dates, end: e.target.value})} />
          <Button onClick={() => setRange(null)}>Pre-trial to today</Button>
          <Button onClick={() => setSelected(DEFAULT_METRICS)}>Default metrics</Button>
          <FormControlLabel control={<Switch checked={smooth} onChange={e => setSmooth(e.target.checked)} />} label="5-survey rolling median" />
          <FormControlLabel control={<Switch checked={dates.start === recent.start && dates.end === recent.end} onChange={e => setRange(e.target.checked ? recent : null)} />} label="Past 28 days" />
          <FormControlLabel control={<Switch checked={contextVisible} onChange={e => setContextVisible(e.target.checked)} />} label="Stimulation context" />
        </Stack>
        <Stack direction="row" flexWrap="wrap" gap={1}>{phases.map(phase => <Chip key={phase.key} variant="outlined" label={`${phase.label} · ${localTime(phase.start).slice(0, 10)}`}
          sx={{borderColor: phase.color, color: "#344767", fontSize: 15, height: "auto", "& .MuiChip-label": {whiteSpace: "normal", py: 1}}} />)}</Stack>
        <MDTypography variant="body2">Dots are individual reviewed surveys; colors mark study phases. Hover for scores, dates and home-program settings. Drag to zoom; double-click to reset.</MDTypography>
        {smooth && <MDTypography variant="body2">The red line is a continuous centered five-survey median, including QC-valid visit-day surveys. It crosses study phases and gaps; connecting segments do not imply measurements between surveys.</MDTypography>}
        {contextVisible && <MDTypography variant="body2">X markers are QC-valid stimulation-test visit-day surveys. They contribute to this display’s median even when stimulation context is hidden; routine analysis QC is unchanged.</MDTypography>}
        {contextVisible && query.data.visits && !query.data.visits.available && <Alert severity="info">{query.data.visits.message}</Alert>}
        </>}
      </Stack></Card>}
      {view === "timeline" && <>{!invalidRange && visibleUnknown.length > 0 && <Alert severity="info" sx={{mb: 3}}>Home settings are not established for part of this period. Survey tooltips mark these gaps instead of carrying earlier settings forward.</Alert>}
      {!invalidRange && contextVisible && <StimulationContext events={events} selected={currentEvent} onSelect={selectTransition} previous={previous} limited={events.length > 12} openDetails={detailsExpanded} onDetailsChange={setDetailsExpanded} />}
      {invalidRange ? <Alert severity="warning">Choose valid dates with From on or before Through, and Through no later than today.</Alert> : <Stack spacing={3}>
        {!shown.length && <Alert severity="info">Select a clinical metric above to display its timeline.</Alert>}
        {shown.map(metric => {
          const count = filterPoints(metric.points, dates.start, dates.end).length;
          const visits = query.data.visits?.metrics?.[metric.key] || EMPTY;
          const visitCount = contextVisible ? filterPoints(visits, dates.start, dates.end).length : 0;
          const medianCount = smooth ? filterPoints(visits, dates.start, dates.end).length : 0;
          return <Card key={metric.key} sx={{p: {xs: 1, md: 3}}}>
            <Stack direction="row" justifyContent="space-between" alignItems="baseline" flexWrap="wrap" gap={1} px={1}>
              <MDTypography variant="h4">{metric.label}</MDTypography>
              <MDTypography variant="body2">{count.toLocaleString()} observations{visitCount > 0 && ` + ${visitCount} visit-day surveys (X)`} · scale {metric.range.join("–")}</MDTypography>
            </Stack>
            {count || visitCount || medianCount ? <MetricChart metric={metric} phases={phases} range={dates} smooth={smooth} visits={visits} transitions={chartEvents} homeTransitions={transitions} unknownIntervals={unknownIntervals} showVisits={contextVisible} onTransition={selectTransition} /> : <Alert severity="info" sx={{my: 2}}>No reviewed observations for this metric in the selected period.</Alert>}
          </Card>;
        })}
      </Stack>}</>}
      {view === "stimulation" && <StimulationPrograms participant={participant_uid} comparison={query.data.comparisons?.stimulation} metrics={shown} />}
      {view === "medications" && <Medications comparison={query.data.comparisons?.medications} metrics={shown} today={defaults.end} phases={phases} />}
      {view === "settings" && <StimProgramSettings key={participant_uid} participant={participant_uid} phases={phases} homeTransitions={transitions} unknownIntervals={unknownIntervals} />}
      {view === "summary" && <MultimodalSummary key={participant_uid} participant={participant_uid} redcap={query.data} revision={revision} />}
      {view === "neural" && <HomeNeuralData key={participant_uid} participant={participant_uid} />}
      {view === "oura" && <OuraTimeline key={participant_uid} participant={participant_uid} phases={phases} homeTransitions={transitions} unknownIntervals={unknownIntervals} />}
    </>}
  </MDBox></DatabaseLayout>;
}
