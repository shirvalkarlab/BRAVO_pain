import {useCallback, useMemo, useState} from 'react';
import {Alert, Autocomplete, Button, Card, Chip, FormControlLabel, Stack, Switch, TextField} from '@mui/material';
import MDTypography from 'components/MDTypography';
import {filterPoints, localTime, past28Range, unknownIntervalsInRange} from './data';
import {OURA_DEFAULTS, ouraPoints, ouraRange, visiblePhases} from './ouraData';
import {useOuraTimeline} from './useOuraTimeline';
import OuraChart from './OuraChart';
import StimulationContext from './StimulationContext';

const EMPTY = [];
export default function OuraTimeline({participant, phases = EMPTY, homeTransitions = EMPTY, unknownIntervals = EMPTY}) {
  const [revision, setRevision] = useState(0);
  const [selected, setSelected] = useState(OURA_DEFAULTS);
  const [range, setRange] = useState(null);
  const [smooth, setSmooth] = useState(true);
  const [context, setContext] = useState(true);
  const [selectedTransition, setSelectedTransition] = useState('');
  const [detailsExpanded, setDetailsExpanded] = useState(false);
  const selectTransition = useCallback(id => {setSelectedTransition(id); setDetailsExpanded(true);}, []);
  const query = useOuraTimeline(participant, revision);
  const metrics = query.data?.metrics || EMPTY;
  const options = useMemo(() => [...metrics].sort((a, b) => (a.group || '').localeCompare(b.group || '') || a.label.localeCompare(b.label)), [metrics]);
  const today = localTime(Date.now() / 1000).slice(0, 10);
  const defaults = useMemo(() => ouraRange(metrics, today), [metrics, today]);
  const dates = range || defaults;
  const recent = past28Range(today);
  const isRecent = dates.start === recent.start && dates.end === recent.end;
  const valid = Boolean(dates.start && dates.end && dates.start <= dates.end && dates.end <= today);
  const shown = selected.map(key => metrics.find(metric => metric.key === key)).filter(Boolean);
  const studyPhases = useMemo(() => valid ? visiblePhases(phases, dates) : EMPTY, [valid, phases, dates]);
  const events = useMemo(() => valid ? filterPoints(homeTransitions, dates.start, dates.end).map((event, index) => ({...event, number: index + 1})) : EMPTY, [valid, homeTransitions, dates]);
  const currentEvent = events.find(event => event.id === selectedTransition) || events[events.length - 1];
  const previous = useMemo(() => [...homeTransitions].filter(event => localTime(event.time).slice(0, 10) < dates.start).sort((a,b) => a.time-b.time).slice(-1)[0], [homeTransitions, dates.start]);
  const chartEvents = useMemo(() => !context ? EMPTY : events.length > 12 ? [currentEvent] : events, [context, events, currentEvent]);
  const visibleUnknown = useMemo(() => valid ? unknownIntervalsInRange(unknownIntervals, dates) : EMPTY, [valid, unknownIntervals, dates]);
  return <Stack spacing={3}>
    <Card sx={{p: {xs: 2, md: 3}, minWidth: 0}}><Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" flexWrap="wrap" gap={2}>
        <div><MDTypography variant="h4">Oura</MDTypography><MDTypography variant="body2">Sleep, physiology and activity across the study.</MDTypography></div>
        <Button variant="outlined" disabled={query.loading} onClick={() => setRevision(value => value + 1)}>Refresh Oura view</Button>
      </Stack>
      <Autocomplete multiple disableCloseOnSelect options={options} value={shown} getOptionLabel={metric => metric.label} groupBy={metric => metric.group || 'Other measures'}
        isOptionEqualToValue={(a, b) => a.key === b.key} getOptionDisabled={metric => !metric.points.some(p => Number.isFinite(p.value))}
        onChange={(_, values) => setSelected(values.map(metric => metric.key))}
        renderInput={params => <TextField {...params} label="Oura metrics" helperText="Add or remove metrics. Measures without eligible data are listed but unavailable." />}
        renderOption={(props, metric) => <li {...props}>{metric.label} · {metric.unit} · {metric.points.filter(p => Number.isFinite(p.value)).length.toLocaleString()} {metric.resolution === 'sample' ? 'readings' : 'days'}</li>}
        sx={{'& .MuiChip-label': {fontSize: 15}}} />
      <Stack direction="row" flexWrap="wrap" gap={2} alignItems="center">
        <TextField label="From" type="date" value={dates.start} InputLabelProps={{shrink: true}} onChange={event => setRange({...dates, start: event.target.value})} />
        <TextField label="Through" type="date" value={dates.end} inputProps={{max: today}} InputLabelProps={{shrink: true}} onChange={event => setRange({...dates, end: event.target.value})} />
        <Button onClick={() => setRange(null)}>Full Oura history</Button>
        <Button onClick={() => setSelected(OURA_DEFAULTS)}>Default Oura metrics</Button>
        <FormControlLabel control={<Switch checked={smooth} onChange={event => setSmooth(event.target.checked)} />} label="5-point rolling median" />
        <FormControlLabel control={<Switch checked={isRecent} onChange={event => setRange(event.target.checked ? recent : null)} />} label="Past 28 days" />
        <FormControlLabel control={<Switch checked={context} onChange={event => setContext(event.target.checked)} />} label="Stimulation context" />
      </Stack>
      {studyPhases.length > 0 && <Stack direction="row" flexWrap="wrap" gap={1}>{studyPhases.map(phase => <Chip key={phase.key} variant="outlined" label={`${phase.label} · ${localTime(phase.start).slice(0, 10)}`}
        sx={{borderColor: phase.color, height: 'auto', '& .MuiChip-label': {whiteSpace: 'normal', py: 1}}} />)}</Stack>}
      <MDTypography variant="body2">Heart rate and HRV retain their recorded times, including daytime readings when available. Steps, estimated total calories and sleep totals are daily measures. Missing or excluded readings remain gaps.</MDTypography>
      <MDTypography variant="body2">The first sleep chart shows the longest sleep episode; the second adds all other recorded sleep, including naps. Both exclude awake time. Hover for values and dates. Drag to zoom; double-click to reset.</MDTypography>
      {smooth && <MDTypography variant="body2">The red line is a centered five-point median: each observation plus up to two before and two after it. Daily charts use five observed daily values; HR and HRV use five recorded readings. Fewer points are used at the ends. The window can cross study phases and missing periods; it is not a five-day window. Raw observations are unconnected points; only the median is drawn as a line. Gaps remain visible.</MDTypography>}
    </Stack></Card>
    {query.data && valid && context && <StimulationContext events={events} selected={currentEvent} onSelect={selectTransition} previous={previous} limited={events.length > 12} openDetails={detailsExpanded} onDetailsChange={setDetailsExpanded} />}
    {query.data && valid && visibleUnknown.length > 0 && <Alert severity="info">Home settings are not established for part of this period. Timed-reading tooltips mark these gaps instead of carrying earlier settings forward.</Alert>}
    {context && <MDTypography variant="body2">Red markers show reviewed home-program records. Click a marker label for complete settings. Daily totals can span stimulation changes; they are not assigned a single program.</MDTypography>}
    {query.loading && <MDTypography role="status">Loading Oura timeline…</MDTypography>}
    {query.error && <Alert severity="error">{query.error}</Alert>}
    {!valid && <Alert severity="warning">Choose valid dates with From on or before Through, and Through no later than today.</Alert>}
    {query.data && valid && <>
      {!metrics.some(metric => metric.points.some(p => Number.isFinite(p.value))) && <Alert severity="info">No eligible Oura observations are available for this participant.</Alert>}
      {!shown.length && <Alert severity="info">Select an Oura metric above to display its timeline.</Alert>}
      {shown.map(metric => {
        const points = ouraPoints(metric.points, dates);
        return <Card key={metric.key} sx={{p: {xs: 1, md: 3}, minWidth: 0}}>
          <Stack direction="row" flexWrap="wrap" justifyContent="space-between" alignItems="baseline" gap={1} px={1}>
            <MDTypography variant="h4">{metric.label}</MDTypography>
            <MDTypography variant="body2">{metric.resolution === 'sample' ? `${points.length.toLocaleString()} readings across ${new Set(points.map(p => p.day)).size} days` : `${points.length} observed days`} · {metric.unit}</MDTypography>
          </Stack>
          {(metric.definition || metric.coverage_note) && <MDTypography variant="body2" px={1}>{metric.definition || metric.coverage_note}</MDTypography>}
          {points.length ? <OuraChart metric={metric} range={dates} phases={studyPhases} smooth={smooth} markers={true} transitions={chartEvents} homeTransitions={homeTransitions} unknownIntervals={unknownIntervals} onTransition={selectTransition} />
            : <Alert severity="info" sx={{my: 2}}>No eligible observations for this metric in the selected period.</Alert>}
        </Card>;
      })}
    </>}
  </Stack>;
}
