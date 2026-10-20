import {useCallback, useMemo, useState} from 'react';
import {Alert, Button, Card, FormControlLabel, Stack, Switch, TextField} from '@mui/material';
import MDTypography from 'components/MDTypography';
import {localTime, past28Range} from './data';
import {useOuraTimeline} from './useOuraTimeline';
import {useHomeNeuralTimeline} from './useHomeNeuralTimeline';
import {homeNeuralPlot, neuralSourceLabel} from './homeNeuralChartData';
import {NeuralLegend, NeuralSensingIntervals} from './HomeNeuralChart';
import {NeuralSettingsSelector, NeuralAnalysisPolicy} from './HomeNeuralData';
import StimulationContext from './StimulationContext';
import MultimodalChart from './MultimodalChart';
import StandardMPQNotice from './StandardMPQNotice';
import {SUMMARY_COLORS, summaryEvents, summaryOuraTraces, summarySurveyTraces, summarySurveyMetrics} from './multimodalData';

const EMPTY = [], EMPTY_OBJECT = {};
function Legend({left,right}) {
  return <Stack direction="row" flexWrap="wrap" gap="6px 24px" sx={{fontSize:14,mx:1,my:1}}>
    <span style={{color:SUMMARY_COLORS[0]}}>● {left} · left axis</span>
    <span style={{color:SUMMARY_COLORS[1]}}>● {right} · right axis</span>
  </Stack>;
}
function NeuralSummary({panel,period,participant,chartProps}) {
  const plot = useMemo(() => homeNeuralPlot(panel,period,participant,600), [panel,period,participant]);
  const [selection,setSelection] = useState(null), [open,setOpen] = useState(false);
  const selected = panel.segments.find(segment=>segment.id === selection) || panel.segments.at(-1);
  const choose = useCallback(id=>{setSelection(id);setOpen(true);}, []);
  const target = neuralSourceLabel(panel.side,participant);
  return <Card sx={{p:{xs:1,md:3},minWidth:0}}>
    <MDTypography variant="h5" px={1}>{target} · home neural recordings</MDTypography>
    <NeuralLegend target={target} traces={plot.traces} independentCurrent={Array.isArray(panel.amplitude_series)}/>
    {panel.amplitude_provenance&&<Alert severity="info">{panel.amplitude_provenance}</Alert>}
    <MultimodalChart {...chartProps} title={`${target} Multimodal Summary neural timeline`} traces={plot.traces} neuralPeriod={period} onPoint={choose} left="Biomarker (LSB)" right="Stim amp (mA)"/>
    <MDTypography variant="body2" px={1}>{plot.observedPower.toLocaleString()} biomarker averages · {plot.observedAmplitude.toLocaleString()} amplitude averages. {plot.latestTime !== null && <>Latest recorded average: {localTime(plot.latestTime).slice(0,16)} Pacific. </>}Native ten-minute records; no rolling median is applied. Points are recorded averages; connecting lines are guides. Missing ten-minute bins and unavailable values remain open.</MDTypography>
    {!plot.observedPower && <Alert severity="info">No established biomarker samples in this range.</Alert>}
    {!plot.observedAmplitude && <Alert severity="info">No established amplitude samples in this range.</Alert>}
    <NeuralSensingIntervals descriptions={plot.descriptions} onSegment={choose}/>
    <NeuralSettingsSelector segments={panel.segments} selected={selected} participant={participant} open={open} setOpen={setOpen} choose={choose} hasRecordedCurrent={plot.observedAmplitude > 0}/>
  </Card>;
}

export default function MultimodalSummary({participant,redcap,revision}) {
  const today = localTime(Date.now()/1000).slice(0,10);
  const [recent,setRecent] = useState(true), [custom,setCustom] = useState(() => past28Range(today));
  const [smooth,setSmooth] = useState(true), [context,setContext] = useState(true);
  const [xRange,setXRange] = useState(null), [cursor,setCursor] = useState(null);
  const [selection,setSelection] = useState(''), [details,setDetails] = useState(false);
  const range = useMemo(() => recent ? past28Range(today) : custom, [recent,today,custom]);
  const valid = Boolean(range.start && range.end && range.start <= range.end && range.end <= today);
  const oura = useOuraTimeline(participant,revision);
  const request = recent ? 'past28' : {window:'custom',start_date:range.start,end_date:range.end};
  const neural = useHomeNeuralTimeline(valid ? participant : null,revision,request,true);
  const metrics = redcap.metrics || EMPTY, phases = redcap.phases || EMPTY;
  const homes = redcap.stimulation?.home_transitions || EMPTY, unknown = redcap.stimulation?.home_unknown_intervals || EMPTY;
  const visits = redcap.visits?.metrics || EMPTY_OBJECT;
  const events = useMemo(() => summaryEvents(homes,range), [homes,range]);
  const selected = events.find(event => event.id === selection) || events.at(-1);
  const previous = homes.filter(event => localTime(event.time).slice(0,10) < range.start).at(-1);
  const chartEvents = useMemo(() => !context ? EMPTY : events.length > 12 ? [selected] : events, [context,events,selected]);
  const choose = useCallback(id => {setSelection(id);setDetails(true);}, []);
  const zoom = useCallback(next => setXRange(prior => JSON.stringify(prior) === JSON.stringify(next) ? prior : next), []);
  const surveyMetrics = useMemo(() => summarySurveyMetrics(metrics), [metrics]);
  const surveyLimits = useMemo(() => surveyMetrics.map(metric => metric?.range), [surveyMetrics]);
  const surveyLabel = index => surveyMetrics[index]?.label || (index ? "Standard MPQ (0–45) unavailable" : "Pain score unavailable");
  const surveyLegend = index => `${surveyLabel(index)}${surveyLimits[index] ? ` (${surveyLimits[index].join("–")})` : ""}`;
  const surveys = useMemo(() => summarySurveyTraces(metrics,visits,phases,range,smooth,homes,unknown), [metrics,visits,phases,range,smooth,homes,unknown]);
  const ouraTraces = useMemo(() => summaryOuraTraces(oura.data?.metrics || EMPTY,range,smooth,neural.data?.visit_days || EMPTY), [oura.data,range,smooth,neural.data]);
  const chartProps = {range,xRange,onRange:zoom,events:chartEvents,onTransition:choose,cursor,onCursor:setCursor};
  const dates = (key,value) => {setRecent(false);setCustom({...range,[key]:value});setXRange(null);};
  return <Stack spacing={3} component="section" aria-label="Multimodal Summary">
    <Card sx={{p:{xs:2,md:3},minWidth:0}}><Stack spacing={2}>
      <MDTypography variant="h4">Multimodal Summary</MDTypography>
      <Stack direction="row" flexWrap="wrap" gap={2} alignItems="center">
        <FormControlLabel control={<Switch checked={smooth} onChange={event=>setSmooth(event.target.checked)}/>} label="5-point rolling median"/>
        <FormControlLabel control={<Switch checked={recent} onChange={event=>{setRecent(event.target.checked);setCustom(range);setXRange(null);}}/>} label="Past 28 days"/>
        <FormControlLabel control={<Switch checked={context} onChange={event=>setContext(event.target.checked)}/>} label="Stimulation context"/>
        <TextField label="Summary from" type="date" value={range.start} inputProps={{max:range.end}} InputLabelProps={{shrink:true}} onChange={event=>dates('start',event.target.value)}/>
        <TextField label="Summary through" type="date" value={range.end} inputProps={{max:today}} InputLabelProps={{shrink:true}} onChange={event=>dates('end',event.target.value)}/>
        <Button onClick={()=>setXRange(null)}>Reset shared zoom</Button>
      </Stack>
      <StandardMPQNotice provenance={redcap.provenance?.standard_mpq} />
      {!surveyMetrics[1]?.points.some(point => Number.isFinite(point.value)) && <Alert severity="info">Standard MPQ (0–45) observations are unavailable. The distinct legacy MPQ sum is not substituted.</Alert>}
      <MDTypography variant="body2">One Pacific calendar range for every plot. Drag to zoom all plots together; hover shows the observation and a shared date guide. Daily Oura values are placed at noon for alignment, not as a measurement time.</MDTypography>
      <MDTypography variant="body2">Dots show recorded observations; X marks supplied clinic-sheet ratings and Oura observations on reviewed visit days. Raw points and X markers remain visible when overlays or medians are hidden. Lines show centered medians of up to five observations, calculated before date filtering; missing days remain gaps.</MDTypography>
      <MDTypography variant="body2">Neural panels follow the stimulated side and identify the actual sensing source below each plot. Clinic-testing dates and overlapping averaging bins remain excluded from home recordings. Recorded settings do not establish exact activation times. Dashed lines show configured control thresholds; ten-minute averages cannot reveal every threshold crossing. Sensing-only intervals have no active control threshold. Click a neural observation or interval for complete settings.</MDTypography>
    </Stack></Card>
    {!valid ? <Alert severity="warning">Choose valid dates with From on or before Through, no later than today.</Alert> : <>
      {context && <StimulationContext events={events} selected={selected} previous={previous} onSelect={choose} limited={events.length>12} openDetails={details} onDetailsChange={setDetails}/>}
      {redcap.visits && !redcap.visits.available && <Alert severity="info">{redcap.visits.message}</Alert>}
      <Card sx={{p:{xs:1,md:3},minWidth:0}}>
        <MDTypography variant="h5" px={1}>REDCap · pain outcomes</MDTypography>
        <Legend left={surveyLegend(0)} right={surveyLegend(1)}/>
        <MultimodalChart {...chartProps} title="Multimodal Summary REDCap pain outcomes" traces={surveys} left={surveyLabel(0)} right={surveyLabel(1)} limits={surveyLimits}/>
        {surveyMetrics[0] && surveyMetrics[0].key !== "left_leg_vas_intensity" && <MDTypography variant="body2">Left-leg VAS is unavailable; this summary shows {surveyMetrics[0].label} as labeled.</MDTypography>}
        {!surveys.some(trace=>trace.y.length) && <Alert severity="info">No recorded survey observations in this range.</Alert>}
      </Card>
      <Card sx={{p:{xs:1,md:3},minWidth:0}}>
        <MDTypography variant="h5" px={1}>Oura · activity and sleep</MDTypography>
        <Legend left="Steps" right="Total sleep including naps (hours)"/>
        {oura.loading && <MDTypography role="status">Loading stored Oura observations…</MDTypography>}
        {oura.error && <Alert severity="error">{oura.error}</Alert>}
        {oura.freshnessError && <Alert severity="warning">{oura.freshnessError}</Alert>}
        {oura.data?.message && <Alert severity="info">{oura.data.message}</Alert>}
        <MultimodalChart {...chartProps} title="Multimodal Summary Oura activity and sleep" traces={ouraTraces} left="Steps" right="Sleep (hours)"/>
        {oura.data && !ouraTraces.some(trace=>trace.y.length) && <Alert severity="info">No recorded Oura observations in this range.</Alert>}
        {!neural.data && <MDTypography variant="body2">Visit-day markers will be available when the reviewed visit calendar loads.</MDTypography>}
      </Card>
      {neural.loading && <MDTypography role="status">Loading home neural recordings and reviewed visit calendar…</MDTypography>}
      {neural.error && <Alert severity="error">{neural.error} Use Refresh view to retry.</Alert>}
      {neural.freshnessError && <Alert severity="warning">{neural.freshnessError}</Alert>}
      <NeuralAnalysisPolicy policy={neural.data?.chronic_analysis_policy}/>
      {neural.data && !neural.data.windows?.length && <Alert severity="info">{neural.data.message || "A reviewed stimulation-visit calendar is needed to define home neural periods."}</Alert>}
      {neural.data?.windows?.map(period => period.panels.map(panel => <NeuralSummary key={panel.side} participant={participant} period={period} panel={panel} chartProps={chartProps}/>))}
    </>}
  </Stack>;
}
